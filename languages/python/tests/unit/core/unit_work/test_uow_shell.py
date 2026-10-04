"""Unit-of-work shell unit tests (m-unit-work, Docker-free).

Exercises the transaction-scope state machine independently of any real port or
SQL lowering (the flush is an injected neutral executor): the frame stack (a
nested scope joins the active transaction, ADR 0005), rollback-only doom and
re-entry refusal, abort that discards buffered effects and withholds the callback
value (ADR 0006), read-your-own-writes force-flush, Clock injection,
use-after-scope rejection, and what buffering admits: the claim each carrier
names, all or nothing, and the pending-insert transition it reports.
"""

from __future__ import annotations

import contextlib
import datetime as dt
from collections.abc import Callable, Mapping
from decimal import Decimal
from types import TracebackType

import pytest

from parallax.conformance import models
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import opt_lock, temporal_read
from parallax.core import predicate as predicate_algebra
from parallax.core.base import INFINITY
from parallax.core.document_codec import EffectiveChangeSet
from parallax.core.entity._model import model_of
from parallax.core.metamodel import AttributeIdentity, Metamodel
from parallax.core.temporal_read import TemporalReadError
from parallax.core.unit_work import (
    SUPERSEDED,
    TERMINATED,
    BufferItem,
    BufferOutcome,
    Clock,
    KeyedMutation,
    KeyedWrite,
    MaterializedWriteGroup,
    ObservedStateKey,
    PlannedInsert,
    PlanningRequest,
    PredecessorRow,
    PredicateSelection,
    PredicateWrite,
    RetainedObservation,
    RollbackOnlyError,
    SystemClock,
    TemporalObservation,
    TransactionInstant,
    TransactionSettings,
    UnitOfWork,
    UnitOfWorkError,
    VersionedEvidenceBuilder,
    VersionObservation,
    WriteBatchTrigger,
    WriteEvidenceError,
    WritePlan,
    WritePlanningError,
    active_unit_of_work,
    buffered_write,
    observed_state_key,
    run_unit_of_work,
)
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    prepare_typed_write,
)
from parallax.core.unit_work.materialized import ObservedKeyedWrite
from parallax.core.unit_work.plan import ExecutionUnit
from parallax.core.unit_work.planned import PlannedClose, PlannedUpdate
from parallax.core.unit_work.planner import VersionedStateKey
from parallax.core.unit_work.uow import EscapedTransactionError, FlushExecutor, WriteBatchOpening
from parallax.snapshot.handle import build_write_planner
from tests._support.clock_probes import CountingClock
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._corpus_identity_support import corpus_object_key
from tests.unit._temporal_group_support import temporal_group
from tests.unit._transact_support import PERSON

_MODELS = models.load_models()
_ACCOUNT = _MODELS["account"]
_BALANCE_CHANGED = EffectiveChangeSet(effective=frozenset({"balance"}), restored=frozenset())
"""What a verb classifies an Account update assigning a new balance as."""
_BALANCE = _MODELS["balance"]
_FIXED = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


class _Recorder:
    """Records each Write Plan the shell hands the executor, with the flush
    trigger it travelled under."""

    def __init__(self) -> None:
        self.plans: list[WritePlan] = []
        self.triggers: list[WriteBatchTrigger] = []

    def __call__(
        self,
        plan: WritePlan,
        *,
        trigger: WriteBatchTrigger,
        completed: Callable[[ExecutionUnit], None],
    ) -> None:
        self.plans.append(plan)
        self.triggers.append(trigger)


def _noop(
    plan: WritePlan, *, trigger: WriteBatchTrigger, completed: Callable[[ExecutionUnit], None]
) -> None:
    return None


def _run[T](
    body: Callable[[UnitOfWork], T],
    *,
    clock: Clock | None = None,
    executor: FlushExecutor | None = None,
    settings: TransactionSettings | None = None,
    meta: Metamodel | None = None,
    opening: WriteBatchOpening | None = None,
) -> T:
    resolved_meta = meta or _ACCOUNT
    return run_unit_of_work(
        body,
        settings=settings or TransactionSettings(),
        clock=clock or FixedClock(_FIXED),
        meta=resolved_meta,
        flush_executor=executor or _noop,
        planner=build_write_planner(resolved_meta),
        actor_identity=TEST_ACTOR_IDENTITY,
        evidence_policy_for=opt_lock.view(resolved_meta).required_key,
        write_batch_opening=opening,
    )


def _prepared_keyed(write: KeyedWrite, model: Metamodel) -> PreparedKeyedWrite:
    prepared = prepare_typed_write(write, model)
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


def _account_insert(account_id: int) -> PreparedKeyedWrite:
    return _prepared_keyed(
        KeyedWrite(
            "insert", "Account", ({"id": account_id, "owner": "N", "balance": Decimal("5.00")},)
        ),
        _ACCOUNT,
    )


def _member_value(attributes: Mapping[AttributeIdentity, object], name: str) -> object:
    """The planned value carried under the Attribute spelled ``name``, from a
    Planned Row's or Planned Assignments' own ``attributes`` mapping."""
    for identity, value in attributes.items():
        if identity.name == name:
            return value
    raise AssertionError(f"no attribute named {name!r} in {attributes!r}")  # pragma: no cover


# --------------------------------------------------------------------------- #
# Commit / abort at the outermost boundary.                                    #
# --------------------------------------------------------------------------- #
def test_outermost_commit_flushes_and_returns_value() -> None:
    recorder = _Recorder()

    def body(tx: UnitOfWork) -> str:
        tx.buffer(_account_insert(9))
        return "ok"

    assert _run(body, executor=recorder) == "ok"
    assert len(recorder.plans) == 1
    assert len(recorder.plans[0].steps) == 1


def test_active_unit_of_work_tracks_the_scope() -> None:
    assert active_unit_of_work() is None
    seen: dict[str, object] = {}

    def body(tx: UnitOfWork) -> None:
        seen["same"] = active_unit_of_work() is tx

    _run(body)
    assert seen["same"] is True
    assert active_unit_of_work() is None


def test_body_exception_aborts_discards_and_withholds() -> None:
    recorder = _Recorder()
    captured: dict[str, UnitOfWork] = {}

    def body(tx: UnitOfWork) -> str:
        tx.buffer(_account_insert(9))
        captured["tx"] = tx
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        _run(body, executor=recorder)
    assert recorder.plans == []  # never committed — the write is withheld
    with pytest.raises(EscapedTransactionError):
        captured["tx"].buffer(_account_insert(1))  # discarded + closed


def test_rollback_only_refuses_commit_and_withholds_value() -> None:
    recorder = _Recorder()
    cause = RuntimeError("inner")

    def body(tx: UnitOfWork) -> str:
        tx.buffer(_account_insert(9))
        tx.mark_rollback_only(cause)
        return "ignored"

    with pytest.raises(RollbackOnlyError) as exc:
        _run(body, executor=recorder)
    assert exc.value.__cause__ is cause
    assert recorder.plans == []  # commit (flush) refused


def test_first_rollback_cause_is_preserved() -> None:
    first = RuntimeError("first")
    second = RuntimeError("second")

    def body(tx: UnitOfWork) -> None:
        tx.mark_rollback_only(first)
        tx.mark_rollback_only(second)

    with pytest.raises(RollbackOnlyError) as exc:
        _run(body)
    assert exc.value.__cause__ is first


def test_settings_are_carried_on_the_unit_of_work() -> None:
    def body(tx: UnitOfWork) -> str:
        return tx.settings.concurrency

    assert _run(body, settings=TransactionSettings(concurrency="optimistic")) == "optimistic"


# --------------------------------------------------------------------------- #
# Read-your-own-writes force-flush.                                            #
# --------------------------------------------------------------------------- #
def test_read_force_flushes_pending_writes_first() -> None:
    order: list[str] = []
    recorder = _Recorder()

    def executor(
        plan: WritePlan, *, trigger: WriteBatchTrigger, completed: Callable[[ExecutionUnit], None]
    ) -> None:
        order.append("flush")
        recorder(plan, trigger=trigger, completed=completed)

    def body(tx: UnitOfWork) -> str:
        tx.buffer(_account_insert(9))
        result = tx.read(lambda: (order.append("read"), "row")[1])
        order.append("after")
        return result

    assert _run(body, executor=executor) == "row"
    assert order == ["flush", "read", "after"]  # the dependent read observes the flushed write
    assert len(recorder.plans) == 1  # the outermost flush finds an empty buffer


def test_read_without_pending_writes_does_not_flush() -> None:
    recorder = _Recorder()

    def body(tx: UnitOfWork) -> str:
        return tx.read(lambda: "row")

    assert _run(body, executor=recorder) == "row"
    assert recorder.plans == []


# --------------------------------------------------------------------------- #
# Clock injection.                                                             #
# --------------------------------------------------------------------------- #
def test_clock_supplies_the_flush_transaction_time_instant() -> None:
    # `WritePlan` retains no Transaction Instant of its own (`m-unit-work`):
    # the captured value survives only where a settled step already carries
    # it, so the audit-only insert's own `txStart` cell is the observable.
    recorder = _Recorder()

    def body(tx: UnitOfWork) -> None:
        tx.buffer(
            _prepared_keyed(
                KeyedWrite(
                    "insert", "Balance", ({"id": 9, "acctNum": "D", "value": Decimal("100.00")},)
                ),
                _BALANCE,
            )
        )

    _run(body, clock=FixedClock(_FIXED), executor=recorder, meta=_BALANCE)
    (step,) = recorder.plans[0].steps
    assert isinstance(step, PlannedInsert)
    (entry,) = step.entries
    assert _member_value(entry.row.attributes, "txStart") == _FIXED


def test_system_clock_reads_an_aware_utc_instant() -> None:
    instant = SystemClock().now()
    assert instant.tzinfo is not None
    assert instant.utcoffset() == dt.timedelta(0)


def test_an_observation_a_buffered_write_carries_binds_into_its_settled_step() -> None:
    # The whole round trip through the shell: an observation is recorded under
    # the state its read observed, a reread of that state answers the recorded
    # evidence before the write is buffered, and it travels to planning ON the
    # write. `PlannedUpdate` carries no raw observation — the recorded version
    # survives only as the settled step's own advanced assignment.
    recorder = _Recorder()
    state = VersionedStateKey(corpus_object_key("Account", ("id", 1)), 7)
    retained = RetainedObservation(state, VersionObservation(observed_version=7), None)

    def body(tx: UnitOfWork) -> None:
        tx.retain(retained)
        reread = RetainedObservation(state, VersionObservation(observed_version=7), None)
        resolved = tx.retain(reread)
        assert resolved is retained
        tx.buffer(
            ObservedKeyedWrite(
                instruction=_prepared_keyed(
                    KeyedWrite("update", "Account", ({"id": 1, "balance": Decimal("0.00")},)),
                    _ACCOUNT,
                ),
                observation=resolved.evidence,
                change=_BALANCE_CHANGED,
            )
        )

    _run(body, executor=recorder)
    (step,) = recorder.plans[0].steps
    assert isinstance(step, PlannedUpdate)
    assert _member_value(step.assignments.attributes, "version") == 8


def test_an_insert_refuses_to_carry_a_write_observation() -> None:
    # `m-unit-work` makes absence structural in both directions: an opening row
    # observes nothing, so the carrier around one is what cannot exist rather
    # than a null field flowing downstream. Three planner stages read that as a
    # guarantee — coalescing folds an update into a pending insert without
    # unwrapping it, opening-row canonicalization treats every carrier as a
    # revising write, and insert batching excludes carriers — so an insert that
    # reached planning wearing evidence would corrupt each in turn.
    with pytest.raises(ValueError, match="an insert carries no Write Observation"):
        ObservedKeyedWrite(
            instruction=_prepared_keyed(
                KeyedWrite(
                    "insert",
                    "Account",
                    ({"id": 1, "owner": "N", "balance": Decimal("5.00"), "version": 1},),
                ),
                _ACCOUNT,
            ),
            observation=VersionObservation(observed_version=1),
        )


def test_a_multi_row_keyed_write_refuses_to_carry_one_write_observation() -> None:
    # `m-unit-work`: each observed version belongs to exactly one row, and
    # `m-opt-lock` binds the version the unit of work observed FOR THAT ROW.
    # Accepted, one observation would license every row the instruction
    # addresses: the planner unwraps it once, builds a multi-key target, and
    # advances every key from `observed + 1`, so a version observed for `id 1`
    # would carry `id 2` to the same new version and expect two affected rows.
    with pytest.raises(ValueError, match="evidence about one row"):
        buffered_write(
            _prepared_keyed(
                KeyedWrite(
                    "update",
                    "Account",
                    ({"id": 1, "balance": Decimal("0.00")}, {"id": 2, "balance": Decimal("0.00")}),
                ),
                _ACCOUNT,
            ),
            VersionObservation(observed_version=7),
        )


def test_a_carrier_refuses_a_claim_naming_other_evidence() -> None:
    # The claim a carrier holds is the retained form of the observation it
    # settles against, and the flush spends the claim while the planner settles
    # the observation. Two different pieces of evidence in one carrier would let
    # a write gate on one state and retire another's claim, so the pairing is
    # refused where the carrier is built.
    state = VersionedStateKey(corpus_object_key("Account", ("id", 1)), 7)
    other = RetainedObservation(state, VersionObservation(observed_version=7), None)
    with pytest.raises(ValueError, match="the retained form of the observation"):
        ObservedKeyedWrite(
            instruction=_prepared_keyed(
                KeyedWrite("update", "Account", ({"id": 1, "balance": Decimal("0.00")},)), _ACCOUNT
            ),
            observation=VersionObservation(observed_version=7),
            claim=other,
        )


def test_two_writes_of_one_claim_merge_and_answer_it_once() -> None:
    # Consumption records a fact about an OBSERVED STATE, so a flush spends one
    # claim once however many of its buffered writes settled against it. Two
    # edits of a single source value are exactly that shape, and Observed-State
    # Coalescing is what makes them one write: the assignments merge in authored
    # order, the later value wins the member both name, and the merged carrier
    # keeps the identical retained observation both held.
    state = VersionedStateKey(corpus_object_key("Account", ("id", 1)), 7)
    retained = RetainedObservation(state, VersionObservation(observed_version=7), None)
    carriers = [
        buffered_write(
            _prepared_keyed(
                KeyedWrite("update", "Account", ({"id": 1, "balance": balance},)), _ACCOUNT
            ),
            retained,
            change=_BALANCE_CHANGED,
        )
        for balance in (Decimal("125.00"), Decimal("150.00"))
    ]
    finalized = build_write_planner(_ACCOUNT).finalize(
        PlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=TransactionInstant(FixedClock(_FIXED)),
            concurrency="locking",
            buffered_writes=carriers,
        )
    )
    (step,) = finalized.plan.steps
    assert isinstance(step, PlannedUpdate)
    assert _member_value(step.assignments.attributes, "balance") == Decimal("150.00")
    assert finalized.claims == (retained,)


def test_a_predicate_write_cannot_be_buffered_with_one_observation() -> None:
    # A predicate-selected write settles per RESOLVED row, against a Materialized
    # Write Group's own aligned observation columns. There is no single
    # observation for the set it selects, so offering this seam one is a caller
    # wiring defect rather than a shape it should quietly wrap.
    predicate = PredicateWrite(
        "delete", PredicateSelection("Account", predicate_algebra.Comparison("eq", "Account.id", 1))
    )
    prepared = prepare_typed_write(predicate, _ACCOUNT)
    assert isinstance(prepared, PreparedPredicateWrite)
    with pytest.raises(TypeError, match="only a keyed write settles against evidence of its own"):
        buffered_write(prepared, VersionObservation(observed_version=1))


def test_a_fully_empty_transaction_never_touches_the_clock() -> None:
    # `flush()` returns on an empty buffer before it even builds a plan, so a
    # read-only transaction never calls `Clock.now()`.
    clock = CountingClock([dt.datetime(2024, 6, 1, tzinfo=dt.UTC)])

    def body(tx: UnitOfWork) -> str:
        return tx.read(lambda: "row")

    assert _run(body, clock=clock) == "row"
    assert clock.calls == 0


def test_transaction_time_instant_is_captured_once_per_transaction() -> None:
    clock = CountingClock(
        [dt.datetime(2024, 6, 1, tzinfo=dt.UTC), dt.datetime(2025, 1, 1, tzinfo=dt.UTC)]
    )
    recorder = _Recorder()

    def body(tx: UnitOfWork) -> None:
        tx.buffer(
            _prepared_keyed(
                KeyedWrite(
                    "insert", "Balance", ({"id": 9, "acctNum": "D", "value": Decimal("1.00")},)
                ),
                _BALANCE,
            )
        )
        tx.read(lambda: "row")  # forces the first flush
        tx.buffer(
            _prepared_keyed(
                KeyedWrite(
                    "insert", "Balance", ({"id": 10, "acctNum": "E", "value": Decimal("2.00")},)
                ),
                _BALANCE,
            )
        )

    _run(body, clock=clock, executor=recorder, meta=_BALANCE)
    # The forced flush and the commit flush carry the SAME holder, so consuming
    # either yields one Transaction-Time instant for the whole transaction
    # (Reladomo's per-transaction timestamp) — observable only through the
    # settled step's own stamped `txStart`, since a Write Plan retains no
    # Transaction Instant of its own.
    tx_starts: list[object] = []
    for plan in recorder.plans:
        (step,) = plan.steps
        assert isinstance(step, PlannedInsert)
        (entry,) = step.entries
        tx_starts.append(_member_value(entry.row.attributes, "txStart"))
    assert tx_starts == [_FIXED] * 2
    assert clock.calls == 1


# --------------------------------------------------------------------------- #
# Frame stack — join, doom, re-entry.                                          #
# --------------------------------------------------------------------------- #
def test_nested_transaction_joins_the_active_one() -> None:
    outer_exec = _Recorder()
    inner_exec = _Recorder()
    seen: dict[str, object] = {}

    def inner(tx: UnitOfWork) -> str:
        seen["inner_tx"] = tx
        tx.buffer(_account_insert(10))
        return "inner-result"

    def outer(tx: UnitOfWork) -> str:
        seen["outer_tx"] = tx
        seen["inner_ret"] = _run(inner, executor=inner_exec)  # joins the active transaction
        tx.buffer(_account_insert(9))
        return "outer-result"

    assert _run(outer, executor=outer_exec) == "outer-result"
    assert seen["inner_tx"] is seen["outer_tx"]  # the same unit of work
    assert seen["inner_ret"] == "inner-result"  # a joined body returns immediately
    assert inner_exec.plans == []  # the joined call's executor is ignored
    assert len(outer_exec.plans) == 1  # one flush at the outermost boundary
    # Both buffered writes reached the SAME outermost flush — the production
    # planner's own batching then collapses the two uniform Account inserts
    # into one multi-row step, so the entry count is the observable, not the
    # step count.
    (step,) = outer_exec.plans[0].steps
    assert isinstance(step, PlannedInsert)
    assert len(step.entries) == 2


def test_inner_failure_dooms_the_transaction_even_if_caught() -> None:
    outer_exec = _Recorder()
    cause = RuntimeError("inner boom")

    def inner(tx: UnitOfWork) -> None:
        raise cause

    def outer(tx: UnitOfWork) -> str:
        # The outer body catches the inner failure and would return normally.
        with contextlib.suppress(RuntimeError):
            _run(inner)  # joins; the failure dooms the whole transaction
        return "outer-ok"

    with pytest.raises(RollbackOnlyError) as exc:
        _run(outer, executor=outer_exec)
    assert exc.value.__cause__ is cause  # the original cause + classification survives
    assert outer_exec.plans == []  # commit refused despite the caught exception


def test_reentry_into_a_rollback_only_transaction_is_refused() -> None:
    cause = RuntimeError("first failure")
    ran: dict[str, bool] = {"inner": False}

    def inner(tx: UnitOfWork) -> None:
        ran["inner"] = True

    def outer(tx: UnitOfWork) -> str:
        tx.mark_rollback_only(cause)
        with pytest.raises(RollbackOnlyError) as exc:
            _run(inner)  # joining a doomed scope raises before running the body
        assert exc.value.__cause__ is cause
        return "done"

    with pytest.raises(RollbackOnlyError):
        _run(outer)
    assert ran["inner"] is False


# --------------------------------------------------------------------------- #
# The batch scope.                                                             #
# --------------------------------------------------------------------------- #
class _Scope:
    """One opened batch scope, recording each transition it makes."""

    def __init__(self, order: list[str], trigger: WriteBatchTrigger) -> None:
        self._order = order
        self._trigger = trigger

    def __enter__(self) -> object:
        self._order.append(f"opened:{self._trigger}")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        self._order.append(f"{'left' if exc is None else 'failed'}:{self._trigger}")


def _opener(order: list[str]) -> WriteBatchOpening:
    return lambda trigger: _Scope(order, trigger)


def test_each_batch_is_a_scope_around_its_own_planning_and_execution() -> None:
    order: list[str] = []

    def executor(
        plan: WritePlan, *, trigger: WriteBatchTrigger, completed: Callable[[ExecutionUnit], None]
    ) -> None:
        order.append(f"executed:{trigger}")

    def body(tx: UnitOfWork) -> None:
        tx.buffer(_account_insert(1))
        tx.read(lambda: None)
        tx.buffer(_account_insert(2))

    _run(body, executor=executor, opening=_opener(order))
    assert order == [
        "opened:read_dependency",
        "executed:read_dependency",
        "left:read_dependency",
        "opened:pre_commit",
        "executed:pre_commit",
        "left:pre_commit",
    ]


def test_a_unit_of_work_without_a_batch_opening_still_flushes() -> None:
    recorder = _Recorder()

    def body(tx: UnitOfWork) -> None:
        tx.buffer(_account_insert(3))

    _run(body, executor=recorder)
    assert recorder.triggers == ["pre_commit"]


# --------------------------------------------------------------------------- #
# Use-after-scope.                                                             #
# --------------------------------------------------------------------------- #
def test_escaped_reference_raises_on_every_use() -> None:
    captured: dict[str, UnitOfWork] = {}

    def body(tx: UnitOfWork) -> None:
        captured["tx"] = tx

    _run(body)
    tx = captured["tx"]
    with pytest.raises(EscapedTransactionError):
        tx.buffer(_account_insert(1))
    with pytest.raises(EscapedTransactionError):
        tx.retain(
            RetainedObservation(
                VersionedStateKey(corpus_object_key("Account", ("id", 1)), 1),
                VersionObservation(observed_version=1),
                None,
            )
        )
    with pytest.raises(EscapedTransactionError):
        tx.flush(trigger="pre_commit")
    with pytest.raises(EscapedTransactionError):
        tx.read(lambda: None)


# --------------------------------------------------------------------------- #
# Buffering a Materialized Write Group installs its selection claims with it, #
# or neither.                                                                  #
# --------------------------------------------------------------------------- #
_TX_START = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def _account_group(*states: tuple[int, int]) -> MaterializedWriteGroup:
    evidence = VersionedEvidenceBuilder(key_position=0, version_position=1)
    for state in states:
        evidence.append(state)
    sealed = evidence.seal()
    assert sealed is not None
    prepared = prepare_typed_write(
        PredicateWrite(
            "delete",
            PredicateSelection(
                "Account", predicate_algebra.Comparison("lessThan", "Account.id", 100)
            ),
        ),
        _ACCOUNT,
    )
    assert isinstance(prepared, PreparedPredicateWrite)
    return MaterializedWriteGroup(mutation=prepared, evidence=sealed)


def _balance_members(key: int, tx_start: object = _TX_START) -> dict[str, object]:
    return {
        "id": key,
        "acctNum": "A",
        "value": Decimal("1.00"),
        "txStart": tx_start,
        "txEnd": INFINITY,
    }


def _balance_group(*rows: dict[str, object]) -> MaterializedWriteGroup:
    return temporal_group(
        PredicateWrite(
            "terminate",
            PredicateSelection(
                "Balance", predicate_algebra.Comparison("lessThan", "Balance.value", "100.00")
            ),
        ),
        _BALANCE,
        rows,
    )


def _account_state(key: int, version: int) -> VersionedStateKey:
    return VersionedStateKey(corpus_object_key("Account", ("id", key)), version)


def _balance_state(key: int) -> ObservedStateKey:
    target = _balance_group(_balance_members(key)).mutation.selection.target
    shape = temporal_read.view(_BALANCE).shape(target.identity)
    assert shape is not None
    return observed_state_key(
        corpus_object_key("Balance", ("id", key)),
        TemporalObservation(predecessor=PredecessorRow(_balance_members(key))),
        shape,
    )


def _account_write(
    mutation: KeyedMutation, account_id: int, version: int, *, retained: bool = True
) -> BufferItem:
    """A keyed write of one Account state, carrying its source's evidence:
    the retained observation a read of that state claims, or (``retained=False``)
    the same evidence as a caller-held value, which claims nothing."""
    row: dict[str, object] = {"id": account_id}
    if mutation == "update":
        row["balance"] = Decimal("1.00")
    evidence = VersionObservation(observed_version=version)
    return buffered_write(
        _prepared_keyed(KeyedWrite(mutation, "Account", (row,)), _ACCOUNT),
        RetainedObservation(_account_state(account_id, version), evidence, None)
        if retained
        else evidence,
        change=_BALANCE_CHANGED if mutation == "update" else None,
    )


def _balance_update(key: int) -> BufferItem:
    observation = TemporalObservation(predecessor=PredecessorRow(_balance_members(key)))
    return buffered_write(
        _prepared_keyed(
            KeyedWrite("update", "Balance", ({"id": key, "value": Decimal("2.00")},)), _BALANCE
        ),
        RetainedObservation(_balance_state(key), observation, None),
        change=_VALUE_CHANGED,
    )


_VALUE_CHANGED = EffectiveChangeSet(effective=frozenset({"value"}), restored=frozenset())


def _refused_as_claimed(uow: UnitOfWork, item: BufferItem) -> WriteEvidenceError:
    with pytest.raises(WriteEvidenceError) as refusal:
        uow.buffer(item)
    assert refusal.value.code == "write-evidence-already-claimed"
    return refusal.value


def _step_kinds(recorder: _Recorder) -> list[str]:
    return [type(step).__name__ for plan in recorder.plans for step in plan.steps]


def test_buffering_a_group_claims_every_state_it_selected_as_a_keyed_read_would_key_it() -> None:
    recorder = _Recorder()

    def body(uow: UnitOfWork) -> None:
        assert uow.buffer(_account_group((1, 7), (2, 3))) is BufferOutcome.BUFFERED
        _refused_as_claimed(uow, _account_write("update", 1, 7))
        _refused_as_claimed(uow, _account_write("delete", 2, 3))
        # Another state of a selected object is another claim scope.
        assert uow.buffer(_account_write("update", 2, 7)) is BufferOutcome.BUFFERED

    _run(body, executor=recorder)
    assert sorted(_step_kinds(recorder)) == ["PlannedDelete", "PlannedDelete", "PlannedUpdate"]

    def temporal(uow: UnitOfWork) -> None:
        uow.buffer(_balance_group(_balance_members(1), _balance_members(2)))
        _refused_as_claimed(uow, _balance_update(1))
        _refused_as_claimed(uow, _balance_update(2))

    _run(temporal, meta=_BALANCE)


def test_a_late_milestone_edge_failure_withdraws_only_the_admitted_prefix() -> None:
    # The third row's axis start is no instant, so deriving its state key fails
    # after two claims were admitted. Those two are withdrawn, the claim held
    # before the group is untouched, and the group is never buffered.
    recorder = _Recorder()

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_balance_update(9))
        group = _balance_group(
            _balance_members(1), _balance_members(2), _balance_members(3, tx_start="soon")
        )
        with pytest.raises(TemporalReadError):
            uow.buffer(group)
        uow.buffer(_balance_group(_balance_members(1), _balance_members(2)))
        with pytest.raises(UnitOfWorkError, match="collides with a claim"):
            uow.buffer(_balance_group(_balance_members(9)))

    _run(body, meta=_BALANCE, executor=recorder)
    closes = [
        step for plan in recorder.plans for step in plan.steps if isinstance(step, PlannedClose)
    ]
    assert {type(close.cause) for close in closes} == {type(SUPERSEDED), type(TERMINATED)}


def test_a_late_collision_leaves_the_pending_claim_it_met_standing() -> None:
    recorder = _Recorder()

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_account_write("update", 3, 7))
        with pytest.raises(UnitOfWorkError, match="collides with a claim"):
            uow.buffer(_account_group((1, 7), (2, 7), (3, 7), (4, 7)))
        with pytest.raises(UnitOfWorkError, match="collides with a claim"):
            uow.buffer(_account_group((3, 7)))
        for account_id in (1, 2, 4):
            uow.buffer(_account_write("delete", account_id, 7))

    _run(body, executor=recorder)
    assert set(_step_kinds(recorder)) == {"PlannedUpdate", "PlannedDelete"}
    (update,) = (
        step for plan in recorder.plans for step in plan.steps if isinstance(step, PlannedUpdate)
    )
    assert _member_value(update.assignments.attributes, "version") == 8


def test_a_group_selecting_one_state_twice_is_refused_and_leaves_no_claim() -> None:
    recorder = _Recorder()

    def body(uow: UnitOfWork) -> None:
        with pytest.raises(UnitOfWorkError, match="incompatible"):
            uow.buffer(_account_group((1, 7), (2, 7), (1, 7)))
        uow.buffer(_account_write("update", 1, 7))
        uow.buffer(_account_write("update", 2, 7))

    _run(body, executor=recorder)
    assert set(_step_kinds(recorder)) == {"PlannedUpdate"}


# --------------------------------------------------------------------------- #
# Buffering a keyed write admits the claim its carrier names, or refuses it    #
# and changes nothing.                                                         #
# --------------------------------------------------------------------------- #
_PERSON_META = model_of(PERSON)


def _person_write(mutation: KeyedMutation, person_id: int) -> BufferItem:
    """An unversioned Non-Temporal Person write settling against its object."""
    row: dict[str, object] = {"id": person_id}
    if mutation == "update":
        row["name"] = "Grace"
    prepared = _prepared_keyed(KeyedWrite(mutation, "Person", (row,)), _PERSON_META)
    return buffered_write(
        prepared,
        corpus_object_key("Person", ("id", person_id)),
        change=(
            EffectiveChangeSet(effective=frozenset({"name"}), restored=frozenset())
            if mutation == "update"
            else None
        ),
    )


def test_a_retained_observation_claims_its_state_and_compatible_intents_combine() -> None:
    recorder = _Recorder()

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_account_write("update", 1, 7))
        uow.buffer(_account_write("update", 1, 7))
        uow.buffer(_account_write("delete", 1, 7))
        uow.buffer(_account_write("delete", 1, 7))
        refusal = _refused_as_claimed(uow, _account_write("update", 1, 7))
        assert refusal.object_key == corpus_object_key("Account", ("id", 1))
        assert "parallax.compatibility.Account" in refusal.message

    _run(body, executor=recorder)
    assert _step_kinds(recorder) == ["PlannedDelete"]


def test_a_retained_claim_is_taken_at_the_exact_observed_state() -> None:
    # Two states of one object are two scopes: a destruction of one leaves the
    # other's assignment unrefused.
    def body(uow: UnitOfWork) -> None:
        uow.buffer(_account_write("delete", 1, 7))
        uow.buffer(_account_write("update", 1, 8))
        _refused_as_claimed(uow, _account_write("update", 1, 7))
        raise _Abandoned

    with pytest.raises(_Abandoned):
        _run(body)


def test_a_caller_held_observation_claims_nothing() -> None:
    def body(uow: UnitOfWork) -> None:
        uow.buffer(_account_write("delete", 1, 7, retained=False))
        uow.buffer(_account_write("update", 1, 7, retained=False))
        # Nor did either take the retained form's claim at that state.
        uow.buffer(_account_write("update", 1, 7))
        raise _Abandoned

    with pytest.raises(_Abandoned):
        _run(body)


def test_an_object_claimed_write_claims_its_instructions_object() -> None:
    recorder = _Recorder()

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_person_write("update", 1))
        uow.buffer(_person_write("delete", 1))
        refusal = _refused_as_claimed(uow, _person_write("update", 1))
        assert refusal.object_key == corpus_object_key("Person", ("id", 1))
        uow.buffer(_person_write("update", 2))

    _run(body, executor=recorder, meta=_PERSON_META)
    assert sorted(_step_kinds(recorder)) == ["PlannedDelete", "PlannedUpdate"]


def test_a_refused_carrier_or_claim_leaves_claims_and_pending_inserts_as_they_were() -> None:
    def body(uow: UnitOfWork) -> None:
        uow.buffer(_account_insert(9))
        uow.buffer(_account_write("delete", 1, 7))
        with pytest.raises(ValueError, match="evidence about one row"):
            uow.buffer(
                buffered_write(
                    _prepared_keyed(
                        KeyedWrite("delete", "Account", ({"id": 9}, {"id": 1})), _ACCOUNT
                    ),
                    RetainedObservation(
                        _account_state(1, 7), VersionObservation(observed_version=7), None
                    ),
                )
            )
        _refused_as_claimed(uow, _account_write("update", 1, 7))
        assert uow.buffer(_account_delete(9)) is BufferOutcome.CANCELLED_PENDING_INSERT
        _refused_as_claimed(uow, _account_write("update", 1, 7))

    _run(body)


class _Abandoned(Exception):
    """Ends a body whose buffer no flush is meant to plan."""


# --------------------------------------------------------------------------- #
# Buffering reports the pending-insert transition it made.                    #
# --------------------------------------------------------------------------- #
def _account_delete(account_id: int) -> PreparedKeyedWrite:
    return _prepared_keyed(KeyedWrite("delete", "Account", ({"id": account_id},)), _ACCOUNT)


def test_a_destructive_write_of_a_pending_insert_reports_the_cancellation() -> None:
    recorder = _Recorder()

    def body(uow: UnitOfWork) -> None:
        assert uow.buffer(_account_insert(9)) is BufferOutcome.BUFFERED
        assert uow.buffer(_account_delete(8)) is BufferOutcome.BUFFERED
        assert uow.buffer(_account_delete(9)) is BufferOutcome.CANCELLED_PENDING_INSERT
        assert uow.buffer(_account_insert(9)) is BufferOutcome.BUFFERED
        assert uow.buffer(_account_delete(9)) is BufferOutcome.CANCELLED_PENDING_INSERT
        assert uow.buffer(_account_delete(9)) is BufferOutcome.BUFFERED
        raise _Abandoned

    with pytest.raises(_Abandoned):
        _run(body, executor=recorder)
    assert recorder.plans == []


def test_every_other_accepted_item_reports_plain_buffering() -> None:
    predicate = prepare_typed_write(
        PredicateWrite(
            "delete",
            PredicateSelection("Account", predicate_algebra.Comparison("eq", "Account.id", 1)),
        ),
        _ACCOUNT,
    )

    def body(uow: UnitOfWork) -> None:
        assert uow.buffer(_account_write("update", 1, 7)) is BufferOutcome.BUFFERED
        assert uow.buffer(_account_write("delete", 2, 7)) is BufferOutcome.BUFFERED
        assert uow.buffer(_account_write("delete", 3, 7, retained=False)) is (
            BufferOutcome.BUFFERED
        )
        assert uow.buffer(predicate) is BufferOutcome.BUFFERED
        assert uow.buffer(_account_group((4, 7))) is BufferOutcome.BUFFERED
        raise _Abandoned

    with pytest.raises(_Abandoned):
        _run(body)

    def unversioned(uow: UnitOfWork) -> None:
        assert uow.buffer(_person_write("update", 1)) is BufferOutcome.BUFFERED
        assert uow.buffer(_person_write("delete", 2)) is BufferOutcome.BUFFERED
        raise _Abandoned

    with pytest.raises(_Abandoned):
        _run(unversioned, meta=_PERSON_META)


def test_a_destructive_write_after_the_insert_flushed_cancels_nothing() -> None:
    recorder = _Recorder()

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_account_insert(9))
        uow.read(lambda: None)
        assert uow.buffer(_account_write("delete", 9, 1, retained=False)) is (
            BufferOutcome.BUFFERED
        )

    _run(body, executor=recorder)
    assert _step_kinds(recorder) == ["PlannedInsert", "PlannedDelete"]


# --------------------------------------------------------------------------- #
# Execution units: completion, ownership, freshness and failure containment.  #
# --------------------------------------------------------------------------- #
def _balance_insert(key: int) -> PreparedKeyedWrite:
    return _prepared_keyed(
        KeyedWrite("insert", "Balance", ({"id": key, "acctNum": "A", "value": Decimal("1.00")},)),
        _BALANCE,
    )


def _balance_update_from(key: int, tx_start: object) -> BufferItem:
    members = _balance_members(key, tx_start)
    observation = TemporalObservation(predecessor=PredecessorRow(members))
    state = observed_state_key(
        corpus_object_key("Balance", ("id", key)),
        observation,
        _balance_shape(),
    )
    return buffered_write(
        _prepared_keyed(
            KeyedWrite("update", "Balance", ({"id": key, "value": Decimal("2.00")},)), _BALANCE
        ),
        RetainedObservation(state, observation, None),
        change=_VALUE_CHANGED,
    )


def _balance_shape() -> temporal_read.TemporalShape:
    shape = temporal_read.view(_BALANCE).shape(corpus_object_key("Balance", ("id", 1)).entity)
    assert shape is not None
    return shape


def test_a_row_an_earlier_flush_opened_is_revised_rather_than_closed() -> None:
    recorder = _Recorder()

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_balance_insert(1))
        uow.read(lambda: None)
        uow.buffer(_balance_update_from(1, _FIXED))

    _run(body, meta=_BALANCE, executor=recorder)
    assert _step_kinds(recorder) == ["PlannedInsert", "PlannedTemporalRevision"]


def _balance_terminate_from(key: int, tx_start: object) -> BufferItem:
    members = _balance_members(key, tx_start)
    observation = TemporalObservation(predecessor=PredecessorRow(members))
    state = observed_state_key(
        corpus_object_key("Balance", ("id", key)), observation, _balance_shape()
    )
    return buffered_write(
        _prepared_keyed(KeyedWrite("terminate", "Balance", ({"id": key},)), _BALANCE),
        RetainedObservation(state, observation, None),
    )


def test_a_row_its_unit_removed_is_no_longer_owned() -> None:
    recorder = _Recorder()

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_balance_insert(1))
        uow.buffer(_balance_insert(2))
        uow.read(lambda: None)
        uow.buffer(_balance_terminate_from(1, _FIXED))
        uow.read(lambda: None)
        uow.buffer(_balance_terminate_from(2, _FIXED))
        uow.read(lambda: None)
        # Both owned rows are gone, so a row read at the attempt's instant now
        # is one the attempt does not own.
        uow.buffer(_balance_update_from(1, _FIXED))

    _run(body, meta=_BALANCE, executor=recorder)
    assert _step_kinds(recorder) == [
        "PlannedInsert",
        "PlannedInsert",
        "PlannedTemporalRemoval",
        "PlannedTemporalRemoval",
        "PlannedClose",
        "PlannedInsert",
    ]


def test_a_row_whose_start_is_the_attempts_instant_is_not_owned_without_its_opening() -> None:
    recorder = _Recorder()

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_balance_update_from(1, _FIXED))

    _run(body, meta=_BALANCE, executor=recorder)
    assert _step_kinds(recorder) == ["PlannedClose", "PlannedInsert"]


def test_each_unit_spends_its_evidence_before_the_next_unit_executes() -> None:
    first = _account_write("update", 1, 7)
    second = _account_write("update", 2, 3)
    assert isinstance(first, ObservedKeyedWrite) and isinstance(second, ObservedKeyedWrite)
    claims = (first.claim, second.claim)
    seen: list[tuple[bool, ...]] = []

    def executor(
        plan: WritePlan, *, trigger: WriteBatchTrigger, completed: Callable[[ExecutionUnit], None]
    ) -> None:
        for unit in plan.units:
            seen.append(tuple(claim is not None and claim.consumed for claim in claims))
            completed(unit)
        seen.append(tuple(claim is not None and claim.consumed for claim in claims))

    def body(uow: UnitOfWork) -> None:
        uow.buffer(first)
        uow.buffer(second)

    _run(body, executor=executor)
    assert seen == [(False, False), (True, False), (True, True)]


def test_a_unit_reported_out_of_order_dooms_the_attempt() -> None:
    def executor(
        plan: WritePlan, *, trigger: WriteBatchTrigger, completed: Callable[[ExecutionUnit], None]
    ) -> None:
        completed(plan.units[1])

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_account_write("update", 1, 7))
        uow.buffer(_account_write("update", 2, 3))
        with pytest.raises(UnitOfWorkError, match="out of order"):
            uow.read(lambda: None)

    with pytest.raises(RollbackOnlyError):
        _run(body, executor=executor)


def test_a_caught_execution_failure_still_dooms_the_attempt() -> None:
    failure = RuntimeError("the statement failed")
    claimed = _account_write("update", 1, 7)
    assert isinstance(claimed, ObservedKeyedWrite) and claimed.claim is not None

    def executor(
        plan: WritePlan, *, trigger: WriteBatchTrigger, completed: Callable[[ExecutionUnit], None]
    ) -> None:
        raise failure

    def body(uow: UnitOfWork) -> str:
        uow.buffer(claimed)
        with pytest.raises(RuntimeError, match="the statement failed"):
            uow.read(lambda: None)
        with pytest.raises(RollbackOnlyError) as refused:
            uow.read(lambda: None)
        assert refused.value.__cause__ is failure
        with pytest.raises(RollbackOnlyError):
            uow.buffer(_account_insert(5))
        return "withheld"

    with pytest.raises(RollbackOnlyError) as exc:
        _run(body, executor=executor)
    assert exc.value.__cause__ is failure
    assert claimed.claim is not None and not claimed.claim.consumed


def test_a_planning_refusal_leaves_the_attempt_usable() -> None:
    bare_close = _prepared_keyed(
        KeyedWrite("update", "Balance", ({"id": 1, "value": Decimal("2.00")},)), _BALANCE
    )

    def body(uow: UnitOfWork) -> None:
        uow.buffer(bare_close)
        with pytest.raises(WritePlanningError):
            uow.read(lambda: None)
        assert uow.read(lambda: "still usable") == "still usable"

    # The refused write is still buffered, so the commit flush refuses it again
    # rather than the attempt being doomed.
    with pytest.raises(WritePlanningError):
        _run(body, meta=_BALANCE)


def test_evidence_built_from_a_read_that_predates_an_own_change_is_invalidated() -> None:
    def fresh_observation(key: int) -> RetainedObservation:
        return RetainedObservation(
            _balance_state(key),
            TemporalObservation(predecessor=PredecessorRow(_balance_members(key))),
            None,
        )

    def body(uow: UnitOfWork) -> None:
        read_at = uow.freshness
        unsubmitted = uow.retain(fresh_observation(1))
        unaffected = uow.retain(fresh_observation(2))
        uow.buffer(_balance_update(1))
        assert not unsubmitted.invalidated
        uow.read(lambda: None)
        assert unsubmitted.invalidated and not unsubmitted.consumed
        assert not unaffected.invalidated
        late = uow.retain(fresh_observation(1), read_at=read_at)
        assert late.invalidated
        fresh = uow.retain(fresh_observation(1))
        assert not fresh.invalidated
        assert uow.retain(fresh_observation(1)) is fresh

    _run(body, meta=_BALANCE)
