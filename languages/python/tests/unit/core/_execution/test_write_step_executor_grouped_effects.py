"""Grouped effects through the production step executor (`m-execution`,
`m-db-port`, `m-unit-work`).

An effect span on a dialect binding arrays is one row-producing Database Call
returning each changed row's source ordinal. The whole result is validated
before any count is read, then each original step is enforced, in order,
against how often its own ordinal returned. These cases answer the call from a
stand-in connection, so each result — malformed ones included — is whatever
the case says the database returned.
"""

from __future__ import annotations

import dataclasses
import gc
import weakref
from collections.abc import Sequence
from decimal import Decimal
from typing import Any, cast

import pytest

from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.core import storage_layout
from parallax.core._execution._write_step_executor import WriteStepExecutor
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    ArrayBind,
    DatabaseConnection,
    OrderedWriteResultComplete,
    OrderedWriteTransport,
    WriteResultIntegrityError,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.execution_lifecycle import (
    DatabaseCallFinished,
    DatabaseCallStarted,
    DatabaseWriteRowsCompleted,
)
from parallax.core.unit_work import (
    CardinalityCorruptionError,
    MissingTargetError,
    OptimisticLockConflictError,
    StaleWriteError,
    WritePreconditionError,
)
from parallax.core.write_payload import LayoutPayloadPreparer
from parallax.core.write_plan import WritePlan
from parallax.core.write_plan.plan import EffectSpan, SettledWrite, WriteGroup
from parallax.core.write_plan.steps import (
    FAILED_PRECONDITION,
    STALE_WRITE,
    UNGATED,
    ExactCount,
    PlannedStep,
    PlannedUpdate,
    Versioned,
)
from tests._support.db_port import Read, ScriptedAdapter
from tests.unit.core._execution._grouped_effect_support import (
    ACCOUNT,
    BALANCE,
    POSITION,
    WALLET,
    close,
    delete,
    instant,
    milestone,
    removal,
    update,
)
from tests.unit.core._execution._write_step_support import open_flush, run_plan


class _Port:
    """A connection answering each ``execute`` with the next of ``answers`` —
    rows, or an exception raised — and each ``execute_write`` with one row,
    recording every call."""

    def __init__(
        self, *answers: object, dialect: Dialect = POSTGRES, ordered: bool = False
    ) -> None:
        self.dialect = dialect
        self.answers = list(answers)
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.ordered_write_transport: OrderedWriteTransport | None = (
            self._ordered if ordered else None
        )

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: object = (),
        *,
        read_only: bool = False,
    ) -> object:
        assert not read_only
        self.calls.append((sql, tuple(binds)))
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.calls.append((sql, tuple(binds)))
        return 1

    def _ordered(self, statements: Sequence[Any]) -> OrderedWriteResultComplete:
        self.calls.append(("ordered", tuple(statement.sql for statement in statements)))
        return OrderedWriteResultComplete(tuple(1 for _ in statements))


def _grouped(steps: Sequence[PlannedStep], meta: Any = WALLET) -> WriteGroup:
    return WriteGroup.from_members(
        ((SettledWrite(), (step,)) for step in steps),
        effect_shape=LayoutPayloadPreparer(meta).effect_shape,
    )


def _executor(
    port: _Port,
    meta: Any = WALLET,
    payloads: Any = None,
    recognized: list[DatabaseError] | None = None,
) -> WriteStepExecutor:
    return WriteStepExecutor(
        cast("DatabaseConnection", port),
        payloads=LayoutPayloadPreparer(meta) if payloads is None else payloads,
        meta=meta,
        recoverable=(lambda error: None) if recognized is None else recognized.append,
    )


def _run(
    port: _Port,
    group: WriteGroup,
    *,
    meta: Any = WALLET,
    payloads: Any = None,
    provider: RecordingLifecycleProvider | None = None,
    recognized: list[DatabaseError] | None = None,
) -> BaseException | None:
    try:
        with open_flush(provider) as flush:
            _executor(port, meta, payloads, recognized).execute(
                group.steps, effect_spans=group.effect_spans, allocates=False, flush=flush
            )
    except BaseException as error:
        return error
    return None


def _wallets(*keys: int) -> list[PlannedUpdate]:
    return [update(WALLET, "Wallet", key, {"balance": Decimal(key)}) for key in keys]


def test_ordinals_returned_in_any_order_satisfy_every_step() -> None:
    port = _Port([(3,), (1,), (2,)])
    assert _run(port, _grouped(_wallets(1, 2, 3))) is None
    ((sql, binds),) = port.calls
    assert sql.startswith("update wallet t set balance = v.c2 from unnest(")
    assert len(binds) == 2


def test_an_empty_result_counts_zero_for_every_step() -> None:
    steps = _wallets(1, 2)
    raised = _run(_Port([]), _grouped(steps))
    assert isinstance(raised, MissingTargetError)
    assert raised.target is steps[0].target
    assert raised.actual == 0


def test_a_missing_ordinal_names_its_own_step_under_its_own_policy() -> None:
    steps = [
        update(ACCOUNT, "Account", key, {"balance": Decimal(key)}, observed=1) for key in (1, 2, 3)
    ]
    raised = _run(_Port([(1,), (3,)]), _grouped(steps, ACCOUNT), meta=ACCOUNT)
    assert isinstance(raised, OptimisticLockConflictError)
    assert raised.target is steps[1].target
    assert (raised.expected, raised.actual) == (1, 0)


def test_the_earliest_short_step_in_canonical_order_is_reported() -> None:
    steps = _wallets(1, 2, 3)
    raised = _run(_Port([(1,)]), _grouped(steps))
    assert isinstance(raised, MissingTargetError)
    assert raised.target is steps[1].target


def test_a_stale_write_policy_raises_its_own_error() -> None:
    gated = [
        update(ACCOUNT, "Account", key, {"balance": Decimal(key)}, observed=1) for key in (1, 2)
    ]
    steps = [
        dataclasses.replace(
            step,
            concurrency=Versioned(cast("Versioned", step.concurrency).attribute, UNGATED),
            affected_rows=ExactCount(1, STALE_WRITE),
        )
        for step in gated
    ]
    raised = _run(_Port([(1,)]), _grouped(steps, ACCOUNT), meta=ACCOUNT)
    assert isinstance(raised, StaleWriteError)
    assert raised.target is steps[1].target


def test_a_repeated_ordinal_is_an_excess_for_its_step() -> None:
    steps = _wallets(1, 2)
    raised = _run(_Port([(2,), (1,), (2,)]), _grouped(steps))
    assert isinstance(raised, CardinalityCorruptionError)
    assert raised.target is steps[1].target
    assert raised.actual == 2


@pytest.mark.parametrize(
    "rows",
    [
        [(1,), (True,)],
        [(1,), (0,)],
        [(1,), (3,)],
        [(1,), ("2",)],
        [(1, 2)],
        [()],
        [1],
        "rows",
        None,
        3,
        iter([(1,), (2,)]),
    ],
    ids=[
        "bool",
        "zero",
        "past-the-end",
        "text",
        "two-cells",
        "no-cell",
        "bare",
        "not-rows",
        "none",
        "integer",
        "iterator",
    ],
)
@pytest.mark.parametrize("observed", [False, True], ids=["unobserved", "observed"])
def test_a_malformed_result_is_refused_before_any_step_is_enforced(
    rows: object, observed: bool
) -> None:
    # The first step is short too; the malformed row still outranks it.
    provider = RecordingLifecycleProvider() if observed else None
    raised = _run(_Port(rows), _grouped(_wallets(1, 2)), provider=provider)
    assert isinstance(raised, WriteResultIntegrityError)
    assert "grouped effect" in str(raised)


def test_a_malformed_result_diagnostic_copies_no_value() -> None:
    raised = _run(_Port([("secret-text",)]), _grouped(_wallets(1, 2)))
    assert isinstance(raised, WriteResultIntegrityError)
    assert "secret-text" not in str(raised)


def test_a_grouped_effect_is_one_database_call_completing_with_its_rows() -> None:
    provider = RecordingLifecycleProvider()
    assert _run(_Port([(1,), (2,)]), _grouped(_wallets(1, 2)), provider=provider) is None
    events = [event for root in provider.roots for event in root.events]
    started = [event for event in events if isinstance(event, DatabaseCallStarted)]
    finished = [event for event in events if isinstance(event, DatabaseCallFinished)]
    assert len(started) == len(finished) == 1
    assert isinstance(finished[0].outcome, DatabaseWriteRowsCompleted)


def test_a_statement_failure_propagates_as_itself_unattributed() -> None:
    failure = DatabaseError(category="uniqueViolation", native_code="23505", message="dup")
    port = _Port(failure)
    assert _run(port, _grouped(_wallets(1, 2))) is failure
    assert len(port.calls) == 1


def test_a_cancellation_propagates_and_executes_nothing_further() -> None:
    port = _Port(KeyboardInterrupt(), [(1,)])
    raised = _run(port, _grouped([*_wallets(1, 2), update(WALLET, "Wallet", 3, {"owner": "x"})]))
    assert isinstance(raised, KeyboardInterrupt)
    assert len(port.calls) == 1


class _Refused(Exception):
    pass


class _Failing(LayoutPayloadPreparer):
    __slots__ = ("failing", "failure")

    def __init__(self, failing: PlannedUpdate, failure: BaseException) -> None:
        super().__init__(WALLET)
        self.failing = failing
        self.failure = failure

    def assignments(self, entity: Any, assignments: Any) -> Any:
        if assignments is self.failing.assignments:
            raise self.failure
        return super().assignments(entity, assignments)


def test_a_preparation_failure_waits_for_its_prefix_to_be_applied_and_enforced() -> None:
    steps = _wallets(1, 2, 3)
    failure = _Refused()
    port = _Port([(1,), (2,)])
    raised = _run(port, _grouped(steps), payloads=_Failing(steps[2], failure))
    assert raised is failure
    ((_sql, binds),) = port.calls
    assert cast("ArrayBind", binds[0]).values == [1, 2]


def test_a_prefix_shortfall_outranks_and_releases_the_held_preparation_failure() -> None:
    steps = _wallets(1, 2, 3)
    failure = _Refused()
    held = weakref.ref(failure)
    port = _Port([(1,)])
    raised = _run(port, _grouped(steps), payloads=_Failing(steps[2], failure))
    assert isinstance(raised, MissingTargetError)
    del failure
    raised = None
    gc.collect()
    assert held() is None


def test_a_statement_failure_outranks_the_held_preparation_failure() -> None:
    steps = _wallets(1, 2, 3)
    statement_failure = DatabaseError(category="deadlock", native_code="40P01", message="d")
    raised = _run(
        _Port(statement_failure), _grouped(steps), payloads=_Failing(steps[2], _Refused())
    )
    assert raised is statement_failure


def test_a_first_step_preparation_failure_executes_nothing() -> None:
    steps = _wallets(1, 2)
    failure = _Refused()
    port = _Port()
    assert _run(port, _grouped(steps), payloads=_Failing(steps[0], failure)) is failure
    assert port.calls == []


def test_a_fatal_preparation_failure_executes_none_of_the_span() -> None:
    steps = _wallets(1, 2, 3)
    port = _Port()
    raised = _run(port, _grouped(steps), payloads=_Failing(steps[2], KeyboardInterrupt()))
    assert isinstance(raised, KeyboardInterrupt)
    assert port.calls == []


def test_ordered_transport_never_takes_the_step_opening_a_span() -> None:
    # A lone shape before the span would join an ordered run with the span's
    # first step if lookahead ignored the span.
    lone = update(WALLET, "Wallet", 9, {"owner": "x"})
    steps = [lone, *_wallets(1, 2)]
    group = _grouped(steps)
    assert group.effect_spans == (EffectSpan(1, 3, group.effect_spans[0].shape),)
    port = _Port([(1,), (2,)], ordered=True)
    assert _run(port, group) is None
    assert [sql.split(" ")[:3] for sql, _ in port.calls] == [
        ["update", "wallet", "set"],
        ["update", "wallet", "t"],
    ]


def test_ordered_transport_stops_its_run_before_a_span() -> None:
    # Two effects of distinct lone shapes form an ordered run, which ends at the
    # step opening the span rather than taking it.
    steps = [
        update(WALLET, "Wallet", 7, {"owner": "a", "balance": Decimal(1)}),
        update(WALLET, "Wallet", 8, {"owner": "b"}),
        *_wallets(1, 2),
    ]
    group = _grouped(steps)
    port = _Port([(1,), (2,)], ordered=True)
    assert _run(port, group) is None
    assert port.calls[0][0] == "ordered"
    assert len(port.calls[0][1]) == 2
    assert port.calls[1][0].startswith("update wallet t ")


def test_an_array_less_dialect_ignores_the_spans() -> None:
    arrayless = dataclasses.replace(POSTGRES, name="mariadb", binds_arrays=False)
    port = _Port(dialect=arrayless)
    assert _run(port, _grouped(_wallets(1, 2))) is None
    assert [sql for sql, _ in port.calls] == ["update wallet set balance = %s where id = %s"] * 2


@pytest.mark.parametrize(("rows", "completes"), [([1, 2], True), ([1], False)])
def test_a_group_completes_its_writes_only_once_its_grouped_effect_is_enforced(
    rows: list[int], completes: bool
) -> None:
    group = _grouped(_wallets(1, 2))
    port = ScriptedAdapter(Read(rows=[{"v.ord": ordinal} for ordinal in rows]))
    completed: list[int] = []
    try:
        with open_flush() as flush:
            run_plan(port, WritePlan((group,)), flush, WALLET, completed=completed)
    except MissingTargetError:
        assert not completes
    assert completed == ([1, 1] if completes else [])
    assert len(port.calls) == 1


@pytest.mark.parametrize(("rows", "completes"), [([2, 1], True), ([2], False)])
def test_a_group_completes_its_closes_only_once_their_grouped_effect_is_enforced(
    rows: list[int], completes: bool
) -> None:
    steps = [
        close(BALANCE, "Balance", milestone(BALANCE, "Balance", key, bitemporal=False))
        for key in (1, 2)
    ]
    group = _grouped(steps, BALANCE)
    port = ScriptedAdapter(Read(rows=[{"v.ord": ordinal} for ordinal in rows]))
    completed: list[int] = []
    try:
        with open_flush() as flush:
            run_plan(port, WritePlan((group,)), flush, BALANCE, completed=completed)
    except StaleWriteError:
        assert not completes
    assert completed == ([1, 1] if completes else [])
    assert len(port.calls) == 1


def test_a_failed_precondition_policy_raises_its_own_error() -> None:
    steps = [
        dataclasses.replace(step, affected_rows=ExactCount(1, FAILED_PRECONDITION))
        for step in (
            update(ACCOUNT, "Account", key, {"balance": Decimal(key)}, observed=4) for key in (1, 2)
        )
    ]
    raised = _run(_Port([(2,)]), _grouped(steps, ACCOUNT), meta=ACCOUNT)
    assert isinstance(raised, WritePreconditionError)
    assert raised.expected == 4


def test_a_deletes_missing_ordinal_names_its_own_key() -> None:
    steps = [delete(ACCOUNT, "Account", key, observed=1) for key in (1, 2)]
    port = _Port([(1,)])
    raised = _run(port, _grouped(steps, ACCOUNT), meta=ACCOUNT)
    assert isinstance(raised, OptimisticLockConflictError)
    assert raised.target is steps[1].target
    ((sql, _binds),) = port.calls
    assert sql.startswith("delete from account t using unnest(")


@pytest.mark.parametrize(
    ("observed", "error"),
    [(None, StaleWriteError), (instant(1), OptimisticLockConflictError)],
    ids=["ungated", "gated"],
)
def test_a_closes_missing_ordinal_names_its_own_milestone(
    observed: Any, error: type[BaseException]
) -> None:
    steps = [
        close(
            BALANCE,
            "Balance",
            milestone(BALANCE, "Balance", key, bitemporal=False),
            observed=observed,
        )
        for key in (1, 2, 3)
    ]
    raised = _run(_Port([(3,), (1,)]), _grouped(steps, BALANCE), meta=BALANCE)
    assert isinstance(raised, error)
    assert isinstance(raised, StaleWriteError | OptimisticLockConflictError)
    assert raised.target is steps[1].target


def test_a_matched_milestone_counts_once_whatever_it_changed() -> None:
    steps = [
        removal(POSITION, "Position", milestone(POSITION, "Position", key), observed=instant(1))
        for key in (1, 2)
    ]
    assert _run(_Port([(2,), (1,)]), _grouped(steps, POSITION), meta=POSITION) is None


def test_an_exclusion_refusal_is_recognized_against_the_statements_entity() -> None:
    steps = [close(POSITION, "Position", milestone(POSITION, "Position", key)) for key in (1, 2)]
    exclusion = storage_layout.view(POSITION).entity(steps[0].entity)
    assert exclusion is not None and exclusion.layout.temporal_constraints is not None
    failure = DatabaseError(
        category="constraintViolation",
        native_code="23P01",
        message="conflicting key value violates exclusion constraint",
        constraint_name=exclusion.layout.temporal_constraints.exclusion_name,
    )
    recognized: list[DatabaseError] = []
    raised = _run(_Port(failure), _grouped(steps, POSITION), meta=POSITION, recognized=recognized)
    assert raised is failure
    assert recognized == [failure]


def test_a_shortfall_is_no_exclusion_and_is_not_recognized_as_one() -> None:
    steps = [close(POSITION, "Position", milestone(POSITION, "Position", key)) for key in (1, 2)]
    recognized: list[DatabaseError] = []
    raised = _run(_Port([(2,)]), _grouped(steps, POSITION), meta=POSITION, recognized=recognized)
    assert isinstance(raised, StaleWriteError)
    assert recognized == []
