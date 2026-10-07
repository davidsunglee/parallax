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
from parallax.conformance.class_models import MODELS as CLASS_MODELS
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import Attr, DomainModel, Entity, attr, opt_lock, temporal_read
from parallax.core import predicate as predicate_algebra
from parallax.core.base import INFINITY
from parallax.core.entity._model import model_of
from parallax.core.execution._planning import build_write_planner
from parallax.core.metamodel import AttributeIdentity, Metamodel
from parallax.core.temporal_read import TemporalReadError, TimeInterval
from parallax.core.unit_work import (
    BufferItem,
    BufferOutcome,
    Clock,
    KeyedMutation,
    KeyedWrite,
    MaterializedWriteGroup,
    PredicateSelection,
    PredicateWrite,
    RetainedObservation,
    RollbackOnlyError,
    SystemClock,
    TransactionInstant,
    TransactionSettings,
    UnitOfWork,
    UnitOfWorkError,
    VersionedEvidenceBuilder,
    WriteAssignment,
    WriteBatchReason,
    WriteEvidenceError,
    WritePlanningRequest,
    WritePreconditionError,
    active_unit_of_work,
    buffered_write,
    run_unit_of_work,
)
from parallax.core.unit_work.acquisition import AcquireRows, CoverageReadRequest
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedTargetWrite,
    TargetWrite,
    prepare_typed_write,
    prepare_wire_write,
)
from parallax.core.unit_work.materialized import (
    InsertionKeyedWrite,
    ObservedKeyedWrite,
    readless_write,
)
from parallax.core.unit_work.retain import InsertionIdentity
from parallax.core.unit_work.uow import (
    NO_INSERTION_AUTHORITY,
    BindDeferredRange,
    EscapedTransactionError,
    ExecuteFlush,
    OpenWriteBatch,
    ReportUnitCompletion,
    _TargetWriteState,  # pyright: ignore[reportPrivateUsage] - the owner of the removal window and lineage it is tested at
)
from parallax.core.unit_work.write_planner import PendingWrites, compose_writes
from parallax.core.write_plan import (
    SUPERSEDED,
    TERMINATED,
    ObservedStateKey,
    PlannedInsert,
    PredecessorRow,
    TemporalObservation,
    VersionObservation,
    WritePlan,
    WritePlanningError,
    observed_state_key,
)
from parallax.core.write_plan.keys import VersionedStateKey
from parallax.core.write_plan.plan import (
    NO_OPENINGS,
    OPEN_BITEMPORAL_ENDS,
    BoundRange,
    Derivation,
    ExecutionUnit,
    Openings,
    OwnedEndpoint,
)
from parallax.core.write_plan.steps import INFINITY as PLANNED_INFINITY
from parallax.core.write_plan.steps import Finite, PlannedClose, PlannedUpdate
from tests._support.clock_probes import CountingClock
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._corpus_identity_support import corpus_object_key
from tests.unit._temporal_group_support import temporal_group
from tests.unit._where_position_model import (
    WherePosition,
)
from tests.unit.core.unit_work._acquired_rows_support import HeldRows

PERSON = CLASS_MODELS["person"]

_MODELS = models.load_models()
_ACCOUNT = _MODELS["account"]
"""What a verb classifies an Account update assigning a new balance as."""
_BALANCE = _MODELS["balance"]
_FIXED = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


class _Recorder:
    """Records each Write Plan the shell hands the executor, with the flush
    trigger it travelled under, binding each deferred range through the unit
    of work to whatever coverage its row acquisition holds."""

    def __init__(self) -> None:
        self.plans: list[WritePlan] = []
        self.triggers: list[WriteBatchReason] = []
        self.bound: list[BoundRange] = []

    def __call__(
        self,
        plan: WritePlan,
        *,
        trigger: WriteBatchReason,
        bind_deferred: BindDeferredRange,
        completed: Callable[[ExecutionUnit, BoundRange | None], None],
    ) -> None:
        self.plans.append(plan)
        self.triggers.append(trigger)
        for unit in plan.units:
            deferred = unit.deferred
            bound = None if deferred is None else bind_deferred(deferred)
            if bound is not None:
                self.bound.append(bound)
            completed(unit, bound)


def _noop(
    plan: WritePlan,
    *,
    trigger: WriteBatchReason,
    bind_deferred: BindDeferredRange,
    completed: Callable[[ExecutionUnit, BoundRange | None], None],
) -> None:
    return None


def _run[T](
    body: Callable[[UnitOfWork], T],
    *,
    clock: Clock | None = None,
    executor: ExecuteFlush | None = None,
    settings: TransactionSettings | None = None,
    meta: Metamodel | None = None,
    opening: OpenWriteBatch | None = None,
    rows: AcquireRows | None = None,
) -> T:
    """Run ``body`` in a unit of work whose row reads answer ``rows``, or find
    no row at all."""
    resolved_meta = meta or _ACCOUNT
    return run_unit_of_work(
        body,
        settings=settings or TransactionSettings(),
        clock=clock or FixedClock(_FIXED),
        meta=resolved_meta,
        flush_executor=executor or _noop,
        acquire_rows=rows or HeldRows(resolved_meta),
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
        plan: WritePlan,
        *,
        trigger: WriteBatchReason,
        bind_deferred: BindDeferredRange,
        completed: Callable[[ExecutionUnit, BoundRange | None], None],
    ) -> None:
        order.append("flush")
        recorder(plan, trigger=trigger, bind_deferred=bind_deferred, completed=completed)

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


def test_an_insertion_authority_licenses_no_insert_and_no_multi_row_write() -> None:
    # An insertion's authority licenses writes of the one object it opened:
    # an insert is admitted by its own verb, and an instruction naming several
    # rows names no single object at all.
    authority = InsertionIdentity(corpus_object_key("Account", ("id", 1)))
    with pytest.raises(ValueError, match="admitted by its own verb"):
        InsertionKeyedWrite(instruction=_account_insert(1), identity=authority)
    with pytest.raises(ValueError, match="the one object it opened"):
        buffered_write(
            _prepared_keyed(
                KeyedWrite(
                    "update",
                    "Account",
                    ({"id": 1, "balance": Decimal("0.00")}, {"id": 2, "balance": Decimal("0.00")}),
                ),
                _ACCOUNT,
            ),
            None,
            authority=authority,
        )


def test_a_write_carrying_an_authority_no_standing_insertion_granted_is_refused() -> None:
    # The verb asks whether an insertion still stands before it builds the
    # write; buffering asks again, so an authority this unit of work never
    # issued — or one a later insertion of the object superseded — is refused
    # rather than settled.
    update = _prepared_keyed(
        KeyedWrite("update", "Account", ({"id": 1, "balance": Decimal("1.00")},)), _ACCOUNT
    )

    def body(tx: UnitOfWork) -> None:
        stranger = InsertionIdentity(corpus_object_key("Account", ("id", 1)))
        with pytest.raises(UnitOfWorkError, match="no longer stands"):
            tx.buffer(buffered_write(update, None, authority=stranger))
        tx.buffer(_account_insert(1))
        standing = tx.insertion_identity(corpus_object_key("Account", ("id", 1)))
        assert standing is not None
        assert tx.insertion_authority(stranger) is NO_INSERTION_AUTHORITY
        # A standing insertion of an object without Valid Time has no window,
        # which is not the absence of its authority.
        assert tx.insertion_authority(standing) is None

    _run(body)


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
    # Two edits of a single source value hold one claim, and Observed-State
    # Coalescing makes them one write: the assignments merge in authored order,
    # the later value wins the member both name, and the merged write's one
    # execution unit keeps the identical retained observation both held.
    state = VersionedStateKey(corpus_object_key("Account", ("id", 1)), 7)
    retained = RetainedObservation(state, VersionObservation(observed_version=7), None)
    carriers = [
        buffered_write(
            _prepared_keyed(
                KeyedWrite("update", "Account", ({"id": 1, "balance": balance},)), _ACCOUNT
            ),
            retained,
        )
        for balance in (Decimal("125.00"), Decimal("150.00"))
    ]
    finalized = build_write_planner(_ACCOUNT).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=TransactionInstant(FixedClock(_FIXED)),
            concurrency="locking",
            buffered_writes=compose_writes(_ACCOUNT, carriers),
        )
    )
    (step,) = finalized.steps
    assert isinstance(step, PlannedUpdate)
    assert _member_value(step.assignments.attributes, "balance") == Decimal("150.00")
    assert [unit.claim for unit in finalized.units] == [retained]


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

    def __init__(self, order: list[str], trigger: WriteBatchReason) -> None:
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


def _opener(order: list[str]) -> OpenWriteBatch:
    return lambda trigger: _Scope(order, trigger)


def test_each_batch_is_a_scope_around_its_own_planning_and_execution() -> None:
    order: list[str] = []

    def executor(
        plan: WritePlan,
        *,
        trigger: WriteBatchReason,
        bind_deferred: BindDeferredRange,
        completed: Callable[[ExecutionUnit, BoundRange | None], None],
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
    )


def _balance_update(key: int) -> BufferItem:
    observation = TemporalObservation(predecessor=PredecessorRow(_balance_members(key)))
    return buffered_write(
        _prepared_keyed(
            KeyedWrite("update", "Balance", ({"id": key, "value": Decimal("2.00")},)), _BALANCE
        ),
        RetainedObservation(_balance_state(key), observation, None),
    )


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
        assert uow.buffer(readless_write(predicate)) is BufferOutcome.BUFFERED
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
        plan: WritePlan,
        *,
        trigger: WriteBatchReason,
        bind_deferred: BindDeferredRange,
        completed: Callable[[ExecutionUnit, BoundRange | None], None],
    ) -> None:
        for unit in plan.units:
            seen.append(tuple(claim is not None and claim.consumed for claim in claims))
            completed(unit, None)
        seen.append(tuple(claim is not None and claim.consumed for claim in claims))

    def body(uow: UnitOfWork) -> None:
        uow.buffer(first)
        uow.buffer(second)

    _run(body, executor=executor)
    assert seen == [(False, False), (True, False), (True, True)]


def test_a_unit_reported_out_of_order_dooms_the_attempt() -> None:
    def executor(
        plan: WritePlan,
        *,
        trigger: WriteBatchReason,
        bind_deferred: BindDeferredRange,
        completed: Callable[[ExecutionUnit, BoundRange | None], None],
    ) -> None:
        completed(plan.units[1], None)

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_account_write("update", 1, 7))
        uow.buffer(_account_write("update", 2, 3))
        with pytest.raises(UnitOfWorkError, match="out of order"):
            uow.read(lambda: None)

    with pytest.raises(RollbackOnlyError):
        _run(body, executor=executor)


def test_a_bound_range_reported_for_a_planned_unit_dooms_the_attempt() -> None:
    def executor(
        plan: WritePlan,
        *,
        trigger: WriteBatchReason,
        bind_deferred: BindDeferredRange,
        completed: Callable[[ExecutionUnit, BoundRange | None], None],
    ) -> None:
        completed(plan.units[0], BoundRange(steps=()))

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_account_write("update", 1, 7))
        with pytest.raises(UnitOfWorkError, match="deferred range"):
            uow.read(lambda: None)

    with pytest.raises(RollbackOnlyError):
        _run(body, executor=executor)


def test_a_unit_reported_with_keys_it_never_allocated_dooms_the_attempt() -> None:
    def executor(
        plan: WritePlan,
        *,
        trigger: WriteBatchReason,
        bind_deferred: BindDeferredRange,
        completed: ReportUnitCompletion,
    ) -> None:
        completed(plan.units[0], None, allocated=(8,))

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_account_write("update", 1, 7))
        with pytest.raises(UnitOfWorkError, match=r"opening 0 row\(s\).*with 1 key"):
            uow.read(lambda: None)

    with pytest.raises(RollbackOnlyError):
        _run(body, executor=executor)


def test_a_caught_execution_failure_still_dooms_the_attempt() -> None:
    failure = RuntimeError("the statement failed")
    claimed = _account_write("update", 1, 7)
    assert isinstance(claimed, ObservedKeyedWrite) and claimed.claim is not None

    def executor(
        plan: WritePlan,
        *,
        trigger: WriteBatchReason,
        bind_deferred: BindDeferredRange,
        completed: Callable[[ExecutionUnit, BoundRange | None], None],
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


_POSITION = _MODELS["position"]
_JAN = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_DEC = dt.datetime(2024, 12, 1, tzinfo=dt.UTC)


def test_a_unit_that_changes_nothing_spends_its_evidence_and_leaves_its_state_fresh() -> None:
    # A termination starting where the rectangle the attempt opened already
    # ends reaches past it, so its coverage is read at execution; finding none
    # there, the range binds to no step at all.
    members = {
        "id": 1,
        "acctNum": "A",
        "value": Decimal("1.00"),
        "txStart": _FIXED,
        "txEnd": INFINITY,
        "validStart": _JAN,
        "validEnd": _DEC,
    }
    observation = TemporalObservation(predecessor=PredecessorRow(members))
    shape = temporal_read.view(_POSITION).shape(corpus_object_key("Position", ("id", 1)).entity)
    assert shape is not None
    state = observed_state_key(corpus_object_key("Position", ("id", 1)), observation, shape)
    recorder = _Recorder()

    def body(uow: UnitOfWork) -> None:
        uow.buffer(
            _prepared_keyed(
                KeyedWrite(
                    "insertUntil",
                    "Position",
                    ({"id": 1, "acctNum": "A", "value": Decimal("1.00")},),
                    valid_from=_JAN,
                    until=_DEC,
                ),
                _POSITION,
            )
        )
        uow.read(lambda: None)
        read_at = uow.freshness
        claim = uow.retain(RetainedObservation(state, observation, None))
        uow.buffer(
            buffered_write(
                _prepared_keyed(
                    KeyedWrite("terminate", "Position", ({"id": 1},), valid_from=_DEC), _POSITION
                ),
                claim,
            )
        )
        uow.read(lambda: None)
        assert claim.consumed and not claim.invalidated
        late = uow.retain(RetainedObservation(state, observation, None), read_at=read_at)
        assert not late.invalidated and not late.consumed

    _run(body, meta=_POSITION, executor=recorder)
    assert _step_kinds(recorder) == ["PlannedInsert"]
    assert [bound.steps for bound in recorder.bound] == [()]


@pytest.mark.parametrize(
    ("value", "kept"), [("100.00", True), ("150.00", False)], ids=["unchanged", "changed"]
)
def test_a_guarded_unit_spends_its_source_and_leaves_an_unchanged_state_fresh(
    value: str, kept: bool
) -> None:
    members = {
        "id": 1,
        "acctNum": "A",
        "value": Decimal("100.00"),
        "txStart": _JAN,
        "txEnd": INFINITY,
    }
    observation = TemporalObservation(predecessor=PredecessorRow(members))
    key = corpus_object_key("Balance", ("id", 1))
    shape = temporal_read.view(_BALANCE).shape(key.entity)
    assert shape is not None
    state = observed_state_key(key, observation, shape)
    recorder = _Recorder()

    def body(uow: UnitOfWork) -> None:
        read_at = uow.freshness
        claim = uow.retain(RetainedObservation(state, observation, None))
        uow.buffer(
            buffered_write(
                _prepared_keyed(
                    KeyedWrite("update", "Balance", ({"id": 1, "value": Decimal(value)},)),
                    _BALANCE,
                ),
                claim,
            )
        )
        uow.read(lambda: None)
        assert claim.consumed
        assert claim.invalidated is not kept
        # Evidence an earlier read of the same rows builds now is still evidence
        # of the stored state exactly when the unit left that state as it was.
        late = uow.retain(RetainedObservation(state, observation, None), read_at=read_at)
        assert late.invalidated is not kept

    _run(
        body,
        meta=_BALANCE,
        executor=recorder,
        settings=TransactionSettings(counts_unchanged_rows=True),
    )
    assert _step_kinds(recorder) == (
        ["PlannedTemporalGuard"] if kept else ["PlannedClose", "PlannedInsert"]
    )


def test_a_unit_names_its_sources_state_and_a_failed_unit_publishes_nothing() -> None:
    failure = RuntimeError("the second unit failed")
    named: list[tuple[ObservedStateKey, ...]] = []

    def executor(
        plan: WritePlan,
        *,
        trigger: WriteBatchReason,
        bind_deferred: BindDeferredRange,
        completed: Callable[[ExecutionUnit, BoundRange | None], None],
    ) -> None:
        named.extend(tuple(unit.changed) for unit in plan.units)
        completed(plan.units[0], None)
        raise failure

    claims: list[RetainedObservation] = []

    def body(uow: UnitOfWork) -> None:
        for account_id, version in ((1, 7), (2, 3)):
            claim = uow.retain(
                RetainedObservation(
                    _account_state(account_id, version),
                    VersionObservation(observed_version=version),
                    None,
                )
            )
            claims.append(claim)
            row = {"id": account_id, "balance": Decimal("1.00")}
            uow.buffer(
                buffered_write(
                    _prepared_keyed(KeyedWrite("update", "Account", (row,)), _ACCOUNT), claim
                )
            )
        with pytest.raises(RuntimeError, match="the second unit failed"):
            uow.read(lambda: None)

    with pytest.raises(RollbackOnlyError):
        _run(body, executor=executor)
    first, second = claims
    # Each unit names the state it changes itself; nothing infers it from a step.
    assert named == [(first.key,), (second.key,)]
    assert (first.consumed, first.invalidated) == (True, True)
    assert (second.consumed, second.invalidated) == (False, False)


def test_a_unit_with_no_step_spends_its_source_and_changes_nothing() -> None:
    members = {
        "id": 1,
        "acctNum": "A",
        "value": Decimal("100.00"),
        "txStart": _JAN,
        "txEnd": INFINITY,
    }
    observation = TemporalObservation(predecessor=PredecessorRow(members))
    key = corpus_object_key("Balance", ("id", 1))
    state = observed_state_key(key, observation, _balance_shape())
    recorder = _Recorder()

    def body(uow: UnitOfWork) -> None:
        claim = uow.retain(RetainedObservation(state, observation, uow.participation))
        uow.buffer(
            buffered_write(
                _prepared_keyed(
                    KeyedWrite("update", "Balance", ({"id": 1, "value": Decimal("100.00")},)),
                    _BALANCE,
                ),
                claim,
            )
        )
        uow.read(lambda: None)
        assert claim.consumed and not claim.invalidated

    _run(
        body,
        meta=_BALANCE,
        executor=recorder,
        settings=TransactionSettings(concurrency="locking"),
    )
    ((unit,),) = (plan.units for plan in recorder.plans)
    assert (unit.end, tuple(unit.changed)) == (0, ())


def _position_write(
    mutation: KeyedMutation,
    claim: RetainedObservation,
    *,
    valid_from: dt.datetime,
    until: dt.datetime | None = None,
    **members: object,
) -> BufferItem:
    return buffered_write(
        _prepared_keyed(
            KeyedWrite(mutation, "Position", ({"id": 1, **members},), valid_from, until),
            _POSITION,
        ),
        claim,
    )


def test_a_row_a_unit_removes_and_reopens_at_one_address_stays_owned() -> None:
    # The attempt opens [January, December); a termination reaching past it is
    # bound at execution, and here its bound range removes that row and reopens
    # it at the same address.
    members = {
        "id": 1,
        "acctNum": "A",
        "value": Decimal("1.00"),
        "txStart": _FIXED,
        "txEnd": INFINITY,
        "validStart": _JAN,
        "validEnd": _DEC,
    }
    observation = TemporalObservation(predecessor=PredecessorRow(members))
    key = corpus_object_key("Position", ("id", 1))
    shape = temporal_read.view(_POSITION).shape(key.entity)
    assert shape is not None
    state = observed_state_key(key, observation, shape)
    endpoint = OwnedEndpoint(key.entity, (1,), (Finite(instant=_DEC), PLANNED_INFINITY))
    recorder = _Recorder()

    def executor(
        plan: WritePlan,
        *,
        trigger: WriteBatchReason,
        bind_deferred: BindDeferredRange,
        completed: Callable[[ExecutionUnit, BoundRange | None], None],
    ) -> None:
        (unit,) = plan.units
        if unit.deferred is None:
            recorder(plan, trigger=trigger, bind_deferred=bind_deferred, completed=completed)
            return
        completed(
            unit,
            BoundRange(steps=(), removed=(endpoint,), opened=Openings(fresh=(endpoint,))),
        )

    def body(uow: UnitOfWork) -> None:
        uow.buffer(
            _prepared_keyed(
                KeyedWrite(
                    "insertUntil",
                    "Position",
                    ({"id": 1, "acctNum": "A", "value": Decimal("1.00")},),
                    valid_from=_JAN,
                    until=_DEC,
                ),
                _POSITION,
            )
        )
        uow.read(lambda: None)
        claim = uow.retain(RetainedObservation(state, observation, None))
        uow.buffer(_position_write("terminate", claim, valid_from=_DEC))
        uow.read(lambda: None)
        later = uow.retain(RetainedObservation(state, observation, None))
        uow.buffer(
            _position_write(
                "updateUntil", later, valid_from=_JAN, until=_DEC, value=Decimal("2.00")
            )
        )

    _run(body, meta=_POSITION, executor=executor)
    # The removal was retired before the opening registered, so the row the
    # unit reopened at its own address is still the attempt's to revise.
    assert _step_kinds(recorder) == ["PlannedInsert", "PlannedTemporalRevision"]


class ShellTag(Entity, table="shell_tag", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


_BARRIERED = model_of(DomainModel(WherePosition, ShellTag))
_T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_FEB, _APR, _JUN, _AUG, _SEP, _OCT = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (2, 4, 6, 8, 9, 10)
)


def _position_row(start: dt.datetime, tx_start: dt.datetime) -> PredecessorRow:
    return PredecessorRow(
        members={
            "id": 1,
            "acctNum": "A",
            "value": Decimal("100.00"),
            "validStart": start,
            "validEnd": INFINITY,
            "txStart": tx_start,
            "txEnd": INFINITY,
        }
    )


def _bind(
    bind_deferred: BindDeferredRange, held: HeldRows, unit: ExecutionUnit, start: dt.datetime
) -> BoundRange:
    """``unit``'s deferred range bound through the flush's own binder, its
    coverage read finding the one current row starting at ``start``."""
    deferred = unit.deferred
    assert deferred is not None
    held.rows = [_position_row(start, _FIXED)]
    return bind_deferred(deferred)


def _position_target(start: dt.datetime, until: dt.datetime) -> PreparedTargetWrite:
    prepared = prepare_wire_write(
        TargetWrite(
            "updateUntil",
            "WherePosition",
            {"id": 1, "value": "175.00"},
            if_tx_start=_T0,
            valid_from=start,
            until=until,
        ),
        _BARRIERED,
    )
    assert isinstance(prepared, PreparedTargetWrite)
    return prepared


def test_a_unit_a_barrier_kept_back_binds_on_what_the_earlier_unit_spent_and_proved() -> None:
    original = TemporalObservation(predecessor=_position_row(_JAN, _T0))
    key = corpus_object_key("WherePosition", ("id", 1))
    shape = temporal_read.view(_BARRIERED).shape(key.entity)
    assert shape is not None
    state = observed_state_key(key, original, shape)
    held: list[RetainedObservation] = []
    seen: list[tuple[bool, bool]] = []

    def executor(
        plan: WritePlan,
        *,
        trigger: WriteBatchReason,
        bind_deferred: BindDeferredRange,
        completed: Callable[[ExecutionUnit, BoundRange | None], None],
    ) -> None:
        if len(plan.units) == 1:
            (unit,) = plan.units
            assert unit.deferred is not None
            # A later flush carries no proof: the original's token is stale.
            _bind(bind_deferred, coverage, unit, _AUG)
            return
        first, barrier, later = plan.units
        assert first.derived and not barrier.derived
        completed(first, None)
        completed(barrier, None)
        (claim,) = held
        seen.append((claim.consumed, claim.invalidated))
        assert later.deferred is not None
        bound = _bind(bind_deferred, coverage, later, _APR)
        assert not any(isinstance(step, PlannedClose) for step in bound.steps)
        completed(later, bound)

    def body(uow: UnitOfWork) -> None:
        claim = uow.retain(RetainedObservation(state, original, uow.participation))
        held.append(claim)
        observed = prepare_wire_write(
            KeyedWrite(
                "updateUntil",
                "WherePosition",
                ({"id": 1, "acctNum": "O"},),
                valid_from=_FEB,
                until=_APR,
            ),
            _BARRIERED,
        )
        assert isinstance(observed, PreparedKeyedWrite)
        uow.buffer(buffered_write(observed, claim))
        barrier = prepare_wire_write(
            PredicateWrite(
                "update",
                PredicateSelection(
                    "ShellTag", predicate_algebra.Comparison("eq", "ShellTag.id", 1)
                ),
                assignments=(WriteAssignment("ShellTag.label", "q"),),
            ),
            _BARRIERED,
        )
        assert isinstance(barrier, PreparedPredicateWrite)
        uow.buffer_predicate(barrier)
        uow.buffer_target(_position_target(_JUN, _AUG))
        uow.read(lambda: None)
        uow.buffer_target(_position_target(_SEP, _OCT))

    coverage = HeldRows(_BARRIERED)
    with pytest.raises(WritePreconditionError):
        _run(body, meta=_BARRIERED, executor=executor, rows=coverage)
    # The earlier unit spent the shared source and invalidated its state
    # before the later one bound.
    assert seen == [(True, True)]
    _assert_optimistic_targets_read_nothing(coverage)


def test_an_objects_proofs_end_when_its_last_following_unit_completes() -> None:
    original = TemporalObservation(predecessor=_position_row(_JAN, _T0))
    key = corpus_object_key("WherePosition", ("id", 1))
    shape = temporal_read.view(_BARRIERED).shape(key.entity)
    assert shape is not None
    state = observed_state_key(key, original, shape)

    def executor(
        plan: WritePlan,
        *,
        trigger: WriteBatchReason,
        bind_deferred: BindDeferredRange,
        completed: Callable[[ExecutionUnit, BoundRange | None], None],
    ) -> None:
        first, barrier, middle, again, last = plan.units
        completed(first, None)
        completed(barrier, None)
        assert middle.deferred is not None and last.deferred is not None
        bound = _bind(bind_deferred, held, middle, _APR)
        assert bound.concludes is None  # a later region still follows it
        completed(middle, bound)
        completed(again, None)
        bound = _bind(bind_deferred, held, last, _AUG)
        assert bound.concludes == key
        assert not any(isinstance(step, PlannedClose) for step in bound.steps)
        completed(last, bound)
        # Nothing the earlier units proved survives the last consumer, even
        # before the flush ends.
        with pytest.raises(WritePreconditionError):
            _bind(bind_deferred, held, last, _AUG)

    def body(uow: UnitOfWork) -> None:
        claim = uow.retain(RetainedObservation(state, original, uow.participation))
        observed = prepare_wire_write(
            KeyedWrite(
                "updateUntil",
                "WherePosition",
                ({"id": 1, "acctNum": "O"},),
                valid_from=_FEB,
                until=_APR,
            ),
            _BARRIERED,
        )
        assert isinstance(observed, PreparedKeyedWrite)
        uow.buffer(buffered_write(observed, claim))
        for window in ((_JUN, _AUG), (_SEP, _OCT)):
            barrier = prepare_wire_write(
                PredicateWrite(
                    "update",
                    PredicateSelection(
                        "ShellTag", predicate_algebra.Comparison("eq", "ShellTag.id", 1)
                    ),
                    assignments=(WriteAssignment("ShellTag.label", "q"),),
                ),
                _BARRIERED,
            )
            assert isinstance(barrier, PreparedPredicateWrite)
            uow.buffer_predicate(barrier)
            uow.buffer_target(_position_target(*window))
        uow.read(lambda: None)

    held = HeldRows(_BARRIERED)
    _run(body, meta=_BARRIERED, executor=executor, rows=held)
    _assert_optimistic_targets_read_nothing(held)


def _assert_optimistic_targets_read_nothing(held: HeldRows) -> None:
    """An Optimistic caller-addressed write reads nothing at its call: every
    read the unit of work asked for was a deferred range's coverage."""
    assert held.requests
    assert all(isinstance(request, CoverageReadRequest) for request in held.requests)


def _position_destroy(start: dt.datetime, until: dt.datetime) -> ObservedKeyedWrite:
    prepared = prepare_wire_write(
        KeyedWrite("terminateUntil", "WherePosition", ({"id": 1},), valid_from=start, until=until),
        _BARRIERED,
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    return ObservedKeyedWrite(
        instruction=prepared, observation=TemporalObservation(predecessor=_position_row(_JAN, _T0))
    )


def _shell_barrier() -> PreparedPredicateWrite:
    barrier = prepare_wire_write(
        PredicateWrite(
            "update",
            PredicateSelection("ShellTag", predicate_algebra.Comparison("eq", "ShellTag.id", 1)),
            assignments=(WriteAssignment("ShellTag.label", "q"),),
        ),
        _BARRIERED,
    )
    assert isinstance(barrier, PreparedPredicateWrite)
    return barrier


def _window(start: dt.datetime, end: dt.datetime) -> TimeInterval:
    return TimeInterval(start, end)


def test_pending_destruction_is_merged_into_start_order_across_authored_barrier_regions() -> None:
    key = corpus_object_key("WherePosition", ("id", 1))
    pending = PendingWrites(_BARRIERED)
    later = _position_destroy(_JUN, _AUG)
    pending.add(later, key)
    pending.add(_position_destroy(_SEP, _OCT), key)
    pending.add(readless_write(_shell_barrier()))
    earlier = _position_destroy(_FEB, _APR)
    pending.add(earlier, key)
    destroyed = list(pending.destroyed_coverage(key))
    assert destroyed == [_window(_FEB, _APR), _window(_JUN, _AUG), _window(_SEP, _OCT)]
    # Each region hands on intervals it already holds rather than copies.
    assert destroyed[0] is earlier.instruction.valid_time_window


def test_pending_destruction_after_an_opening_leaves_out_what_precedes_the_insert() -> None:
    key = corpus_object_key("WherePosition", ("id", 1))
    insert = prepare_wire_write(
        KeyedWrite(
            "insert",
            "WherePosition",
            ({"id": 1, "acctNum": "A", "value": "1.00"},),
            valid_from=_FEB,
        ),
        _BARRIERED,
    )
    assert isinstance(insert, PreparedKeyedWrite)
    pending = PendingWrites(_BARRIERED)
    pending.add(_position_destroy(_JUN, _AUG), key)
    pending.add(insert, key)
    pending.add(readless_write(_shell_barrier()))
    pending.add(_position_destroy(_FEB, _APR), key)
    assert list(pending.destroyed_coverage(key, after_opening=True)) == [_window(_FEB, _APR)]
    assert list(pending.destroyed_coverage(key)) == [_window(_FEB, _APR), _window(_JUN, _AUG)]


def _position_endpoint(end: dt.datetime | None) -> OwnedEndpoint:
    entity = corpus_object_key("WherePosition", ("id", 1)).entity
    if end is None:
        return OwnedEndpoint(entity, (1,), OPEN_BITEMPORAL_ENDS)
    return OwnedEndpoint(entity, (1,), (Finite(instant=end), PLANNED_INFINITY))


def test_a_stored_insertions_removal_window_is_kept_until_what_it_derives_from_changes() -> None:
    key = corpus_object_key("WherePosition", ("id", 1))
    targets = _TargetWriteState()
    targets.open_insert(key, None, TimeInterval(_FEB, INFINITY), bitemporal=True)
    targets.end_flush(())
    record = targets.record(key)
    assert record is not None
    open_row = _position_endpoint(None)
    targets.complete((), Openings(continued=(open_row,)))
    window = targets.removal_window(record)
    assert window == TimeInterval(_FEB, INFINITY)
    assert targets.removal_window(record) is window
    # Retiring the open row and tagging a bounded one leaves an earlier end.
    bounded = _position_endpoint(_JUN)
    targets.complete((open_row,), Openings(continued=(bounded,)))
    narrowed = targets.removal_window(record)
    assert narrowed == TimeInterval(_FEB, _JUN)
    assert narrowed is not window
    # A stored object's further admission keeps its floor until a flush
    # executes it, and cancelling authority changes neither tags nor floor.
    targets.open_insert(key, None, TimeInterval(_APR, INFINITY), bitemporal=True)
    assert targets.removal_window(record) is narrowed
    targets.end_flush(())
    moved = targets.removal_window(record)
    assert moved == TimeInterval(_APR, _JUN)
    targets.cancel_insert(key)
    assert targets.removal_window(record) is moved


def test_a_proven_originals_descendants_are_exactly_those_overlapping_the_window() -> None:
    key = corpus_object_key("WherePosition", ("id", 1))
    original = observed_state_key(
        key, TemporalObservation(predecessor=_position_row(_JAN, _T0)), _barriered_shape()
    )
    rows = (
        (_position_endpoint(_FEB), TimeInterval(_JAN, _FEB)),
        (_position_endpoint(_JUN), TimeInterval(_APR, _JUN)),
        (_position_endpoint(None), TimeInterval(_AUG, INFINITY)),
    )
    targets = _TargetWriteState()
    for endpoint, _coverage in rows:
        targets.complete((), Openings(fresh=(endpoint,)))
    targets.complete(
        (), NO_OPENINGS, (Derivation(original, TimeInterval(_JAN, INFINITY), None, rows),)
    )
    # [Feb, Sep) starts where the first row ends: the start index still
    # reaches that row, which the window does not overlap.
    reached = list(targets.descendants(original, TimeInterval(_FEB, _SEP)))
    assert [(endpoint, descent.valid_time_coverage) for endpoint, descent in reached] == [
        rows[1],
        rows[2],
    ]
    assert all(
        descent.valid_time_coverage is coverage
        for (_e, descent), (_r, coverage) in zip(reached, rows[1:], strict=True)
    )
    assert list(targets.descendants(original, TimeInterval(_FEB, _APR))) == []
    assert [endpoint for endpoint, _descent in targets.descendants(original, None)] == [
        endpoint for endpoint, _coverage in rows
    ]


def _barriered_shape() -> temporal_read.TemporalShape:
    shape = temporal_read.view(_BARRIERED).shape(
        corpus_object_key("WherePosition", ("id", 1)).entity
    )
    assert shape is not None
    return shape
