"""Unit-of-work coordination unit tests (m-unit-work, Docker-free).

Exercises the writable coordinator of one attempt independently of any real
port or runner (each span a flush executes is simulated, lowering through the
dry traversal and running nothing, and row acquisition is an injected
reader): the pre-commit and read-dependency flushes, discarding buffered
effects, read-your-own-writes force-flush, Clock injection, the attempt
lifetime it consults and dooms, and what buffering admits: the claim each
admitted write names, all or nothing, and the pending-insert transition it reports.
The attempt's own lifecycle — commit admission, joins, and rollback — is the
managed runner's, and is tested there.
"""

from __future__ import annotations

import datetime as dt
import gc
import weakref
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from decimal import Decimal
from types import TracebackType
from typing import Any

import pytest

from parallax.conformance import models
from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.conformance.class_models import MODELS as CLASS_MODELS
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import Attr, DomainModel, Entity, attr, inheritance, opt_lock, temporal_read
from parallax.core import predicate as predicate_algebra
from parallax.core._execution import _planning as planning_composition
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._transaction._lifetime import TxnAttemptLifetime
from parallax.core._execution._unit_work.acquisition import (
    AcquireRows,
    CoverageReadRequest,
    RowConsumer,
    RowRequest,
    TargetReadRequest,
)
from parallax.core._execution._unit_work.admission import NO_INSERTION_AUTHORITY
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    PreparedPredicateInstruction,
    PreparedTargetInstruction,
    TargetWriteInstruction,
    prepare_typed_write,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.retain import InsertionIdentity, ReadEvidence
from parallax.core._execution._unit_work.strategy import ActorIdentity
from parallax.core._execution._unit_work.uow import EscapedTransactionError, OpenFlush
from parallax.core._execution._unit_work.write_items import (
    InsertionAuthorizedWrite,
    StateObservedWrite,
    target_write,
)
from parallax.core._execution._unit_work.write_runner import (
    ExecuteCountedStep,
    ExecuteWriteSteps,
)
from parallax.core.base import INFINITY
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.metamodel import AttributeIdentity, Metamodel
from parallax.core.unit_work import (
    AdmittedWrite,
    BufferOutcome,
    Clock,
    FlushTrigger,
    KeyedMutation,
    KeyedWriteInstruction,
    PredicateSelection,
    PredicateWriteInstruction,
    RetainedObservation,
    RollbackOnlyError,
    SystemClock,
    TransactionInstant,
    TransactionSettings,
    UnitOfWork,
    UnitOfWorkError,
    WriteAssignment,
    WriteEvidenceError,
    WritePlanner,
    WritePlanningRequest,
    WritePreconditionError,
    admitted_write,
)
from parallax.core.write_plan import (
    ObjectStateKey,
    PlannedInsert,
    PredecessorRow,
    TemporalObservation,
    VersionObservation,
    WritePlan,
    WritePlanningError,
    object_state_key_from_observation,
)
from parallax.core.write_plan.keys import VersionedObjectStateKey
from parallax.core.write_plan.plan import (
    OPEN_BITEMPORAL_ENDS,
    TemporalRowCoordinates,
)
from parallax.core.write_plan.steps import INFINITY as PLANNED_INFINITY
from parallax.core.write_plan.steps import (
    NEW_LINEAGE,
    Finite,
    PlannedDelete,
    PlannedUpdate,
)
from tests._support.clock_probes import CountingClock
from tests._support.planner_probes import (
    NO_COUNTED_STEPS,
    TEST_ACTOR_IDENTITY,
    admitted_writes,
    object_source,
    plan_steps,
    settled_writes,
)
from tests.unit._corpus_identity_support import corpus_object_key
from tests.unit._where_position_model import (
    WherePosition,
)
from tests.unit.core._execution._unit_work._acquired_rows_support import HeldRows
from tests.unit.core._execution._unit_work._audit_support import RecordingAudit
from tests.unit.core._execution._unit_work._flush_support import ObservedSteps, statement_kinds

PERSON = CLASS_MODELS["person"]

_MODELS = models.load_models()
_ACCOUNT = _MODELS["account"]
"""What a verb classifies an Account update assigning a new balance as."""
_BALANCE = _MODELS["balance"]
_FIXED = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


def _simulated(meta: Metamodel = _ACCOUNT) -> SimulatedWriteSteps:
    """Step execution recording the statements each span of ``meta``'s writes
    lowers to, and running none."""
    return SimulatedWriteSteps(build_write_planner(meta).payloads, meta, POSTGRES)


def _kinds(simulated: SimulatedWriteSteps) -> list[str]:
    return statement_kinds(simulated.statements)


def _run[T](
    body: Callable[[UnitOfWork], T],
    *,
    clock: Clock | None = None,
    steps: ExecuteWriteSteps | None = None,
    settings: TransactionSettings | None = None,
    meta: Metamodel | None = None,
    opening: OpenFlush | None = None,
    rows: AcquireRows | None = None,
    lifetime: TxnAttemptLifetime | None = None,
    counted: ExecuteCountedStep | None = None,
) -> T:
    """Drive ``body`` against a unit of work whose row reads answer ``rows``, or
    find no row at all, and whose spans ``steps`` executes, then flush what it
    left as the attempt's pre-commit flush, and end the attempt's lifetime
    either way.

    Coordination only: what an attempt does around that flush — refusing a
    doomed commit, discarding on failure, binding joins — is the runner's.
    """
    resolved_meta = meta or _ACCOUNT
    attempt = lifetime or TxnAttemptLifetime()
    uow = UnitOfWork(
        settings=settings or TransactionSettings(),
        lifetime=attempt,
        clock=clock or FixedClock(_FIXED),
        meta=resolved_meta,
        execute_write_steps=steps or _simulated(resolved_meta),
        execute_counted_step=counted or NO_COUNTED_STEPS,
        acquire_rows=rows or HeldRows(resolved_meta),
        planner=build_write_planner(resolved_meta),
        actor_identity=TEST_ACTOR_IDENTITY,
        evidence_policy_for=opt_lock.view(resolved_meta).required_key,
        flush_opening=opening,
    )
    try:
        result = body(uow)
        uow.flush(trigger="pre_commit")
        return result
    finally:
        attempt.close()


def _prepared_keyed(write: KeyedWriteInstruction, model: Metamodel) -> PreparedKeyedInstruction:
    prepared = prepare_typed_write(write, model)
    assert isinstance(prepared, PreparedKeyedInstruction)
    return prepared


def _account_insert(account_id: int) -> PreparedKeyedInstruction:
    return _prepared_keyed(
        KeyedWriteInstruction(
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
# The pre-commit flush, discarding, and the lifetime it consults.              #
# --------------------------------------------------------------------------- #
def test_the_pre_commit_flush_plans_what_is_buffered() -> None:
    simulated = _simulated()

    def body(tx: UnitOfWork) -> str:
        tx.buffer(_account_insert(9))
        return "ok"

    assert _run(body, steps=simulated) == "ok"
    assert _kinds(simulated) == ["insert"]


def test_discarding_drops_every_buffered_write() -> None:
    order: list[str] = []
    simulated = _simulated()

    def body(tx: UnitOfWork) -> None:
        tx.buffer(_account_insert(9))
        tx.discard()

    _run(body, steps=simulated, opening=_opener(order))
    # Nothing buffered survives to be planned, so no flush opens.
    assert (order, simulated.statements) == ([], ())


def test_a_doomed_lifetime_refuses_the_pre_commit_flush_with_its_first_cause() -> None:
    order: list[str] = []
    lifetime = TxnAttemptLifetime()
    first = RuntimeError("first")

    def body(tx: UnitOfWork) -> str:
        tx.buffer(_account_insert(9))
        lifetime.doom(first)
        lifetime.doom(RuntimeError("second"))
        with pytest.raises(RollbackOnlyError):
            tx.buffer(_account_insert(10))
        return "withheld"

    with pytest.raises(RollbackOnlyError) as exc:
        _run(body, lifetime=lifetime, opening=_opener(order))
    assert exc.value.__cause__ is first
    assert order == []  # the flush was refused before it planned


def test_settings_are_carried_on_the_unit_of_work() -> None:
    def body(tx: UnitOfWork) -> str:
        return tx.settings.concurrency

    assert _run(body, settings=TransactionSettings(concurrency="optimistic")) == "optimistic"


# --------------------------------------------------------------------------- #
# Read-your-own-writes force-flush.                                            #
# --------------------------------------------------------------------------- #
def test_read_force_flushes_pending_writes_first() -> None:
    order: list[str] = []
    simulated = _simulated()

    def body(tx: UnitOfWork) -> str:
        tx.buffer(_account_insert(9))
        result = tx.read(lambda: (order.append("read"), "row")[1])
        order.append("after")
        return result

    assert _run(body, steps=simulated, opening=_opener(order)) == "row"
    # The dependent read observes the flushed write, and the outermost flush
    # finds an empty buffer.
    assert order == ["opened:read_dependency", "left:read_dependency", "read", "after"]
    assert _kinds(simulated) == ["insert"]


def test_read_without_pending_writes_does_not_flush() -> None:
    order: list[str] = []

    def body(tx: UnitOfWork) -> str:
        return tx.read(lambda: "row")

    assert _run(body, opening=_opener(order)) == "row"
    assert order == []


# --------------------------------------------------------------------------- #
# Clock injection.                                                             #
# --------------------------------------------------------------------------- #
def test_clock_supplies_the_flush_transaction_time_instant() -> None:
    # `WritePlan` retains no Transaction Instant of its own (`m-unit-work`):
    # the captured value survives only where a settled step already carries
    # it, so the audit-only insert's own `txStart` cell is the observable.
    simulated = _simulated(_BALANCE)

    def body(tx: UnitOfWork) -> None:
        tx.buffer(
            _prepared_keyed(
                KeyedWriteInstruction(
                    "insert", "Balance", ({"id": 9, "acctNum": "D", "value": Decimal("100.00")},)
                ),
                _BALANCE,
            )
        )

    _run(body, clock=FixedClock(_FIXED), steps=simulated, meta=_BALANCE)
    (statement,) = simulated.statements
    assert statement.sql.startswith("insert")
    assert _FIXED in statement.binds


def test_system_clock_reads_an_aware_utc_instant() -> None:
    instant = SystemClock().now()
    assert instant.tzinfo is not None
    assert instant.utcoffset() == dt.timedelta(0)


def test_an_observation_a_buffered_write_carries_binds_into_its_settled_step() -> None:
    # The whole round trip through the shell: an observation is recorded under
    # the state its read observed, a reread of that state answers the recorded
    # evidence before the write is buffered, and it travels to planning ON the
    # write. `PlannedUpdate` carries no raw observation — the recorded version
    # survives only as the statement's own advanced assignment.
    simulated = _simulated()
    state = VersionedObjectStateKey(corpus_object_key("Account", ("id", 1)), 7)
    retained = RetainedObservation(state, VersionObservation(observed_version=7), None)

    def body(tx: UnitOfWork) -> None:
        tx.retain(retained)
        reread = RetainedObservation(state, VersionObservation(observed_version=7), None)
        resolved = tx.retain(reread)
        assert resolved is retained
        tx.buffer(
            StateObservedWrite(
                instruction=_prepared_keyed(
                    KeyedWriteInstruction(
                        "amend", "Account", ({"id": 1, "balance": Decimal("0.00")},)
                    ),
                    _ACCOUNT,
                ),
                retained_observation=resolved,
            )
        )

    _run(body, steps=simulated)
    (statement,) = simulated.statements
    assert _kinds(simulated) == ["update"]
    assert statement.binds == (Decimal("0.00"), 8, 1, 7)


def test_an_insert_refuses_to_carry_a_write_observation() -> None:
    # `m-unit-work` makes absence structural in both directions: an opening row
    # observes nothing, so the observed write around one is what cannot exist rather
    # than a null field flowing downstream. Three planner stages read that as a
    # guarantee — coalescing folds an update into a pending insert without
    # unwrapping it, opening-row canonicalization treats every observed write as
    # a revising write, and insert batching excludes observed writes — so an insert that
    # reached planning wearing evidence would corrupt each in turn.
    with pytest.raises(ValueError, match="an insert carries no State Observation"):
        StateObservedWrite(
            instruction=_prepared_keyed(
                KeyedWriteInstruction(
                    "insert",
                    "Account",
                    ({"id": 1, "owner": "N", "balance": Decimal("5.00"), "version": 1},),
                ),
                _ACCOUNT,
            ),
            retained_observation=RetainedObservation(
                _account_state(1, 1), VersionObservation(observed_version=1), None
            ),
        )


def test_a_multi_row_keyed_write_refuses_to_carry_one_write_observation() -> None:
    # `m-unit-work`: each observed version belongs to exactly one row, and
    # `m-opt-lock` binds the version the unit of work observed FOR THAT ROW.
    # Accepted, one observation would license every row the instruction
    # addresses: the planner unwraps it once, builds a multi-key target, and
    # advances every key from `observed + 1`, so a version observed for `id 1`
    # would carry `id 2` to the same new version and expect two affected rows.
    with pytest.raises(ValueError, match="evidence about one row"):
        admitted_write(
            _prepared_keyed(
                KeyedWriteInstruction(
                    "amend",
                    "Account",
                    ({"id": 1, "balance": Decimal("0.00")}, {"id": 2, "balance": Decimal("0.00")}),
                ),
                _ACCOUNT,
            ),
            RetainedObservation(_account_state(1, 7), VersionObservation(observed_version=7), None),
        )


def test_an_insertion_authority_licenses_no_insert_and_no_multi_row_write() -> None:
    # An insertion's authority licenses writes of the one object it opened:
    # an insert is admitted by its own verb, and an instruction naming several
    # rows names no single object at all.
    authority = InsertionIdentity(corpus_object_key("Account", ("id", 1)))
    with pytest.raises(ValueError, match="admitted by its own verb"):
        InsertionAuthorizedWrite(instruction=_account_insert(1), identity=authority)
    with pytest.raises(ValueError, match="the one object it opened"):
        admitted_write(
            _prepared_keyed(
                KeyedWriteInstruction(
                    "amend",
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
        KeyedWriteInstruction("amend", "Account", ({"id": 1, "balance": Decimal("1.00")},)),
        _ACCOUNT,
    )

    def body(tx: UnitOfWork) -> None:
        stranger = InsertionIdentity(corpus_object_key("Account", ("id", 1)))
        with pytest.raises(UnitOfWorkError, match="no longer stands"):
            tx.buffer(admitted_write(update, None, authority=stranger))
        tx.buffer(_account_insert(1))
        standing = tx.insertion_identity(corpus_object_key("Account", ("id", 1)))
        assert standing is not None
        assert tx.insertion_authority(stranger) is NO_INSERTION_AUTHORITY
        # A standing insertion of an object without Valid Time has no window,
        # which is not the absence of its authority.
        assert tx.insertion_authority(standing) is None

    _run(body)


def test_evidence_of_this_attempt_carrying_no_observation_licenses_no_gated_write() -> None:
    # Every read the Optimistic strategy answers retains the observation its gate
    # binds, so evidence of this attempt carrying none has nothing to gate on and
    # is refused at the verb rather than settled against nothing.
    account = _ACCOUNT.entities[0]
    key = corpus_object_key("Account", ("id", 1))

    def body(tx: UnitOfWork) -> None:
        evidence = ReadEvidence(account.identity, key, tx.participation, None)
        with pytest.raises(WriteEvidenceError) as refusal:
            tx.resolve_read_evidence(account, evidence, mutation="amend", object_key=key)
        assert refusal.value.code == "write-evidence-unavailable"

    _run(body)


def test_two_writes_of_one_claim_merge_and_advance_it_once() -> None:
    # Two edits of a single source value hold one claim, and Observed-State
    # Coalescing makes them one write: the assignments merge in authored order,
    # the later value wins the member both name, and the merged write's one
    # settled write advances the state both observed, once.
    state = VersionedObjectStateKey(corpus_object_key("Account", ("id", 1)), 7)
    retained = RetainedObservation(state, VersionObservation(observed_version=7), None)
    observed = [
        admitted_write(
            _prepared_keyed(
                KeyedWriteInstruction("amend", "Account", ({"id": 1, "balance": balance},)),
                _ACCOUNT,
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
            composed_writes=admitted_writes(_ACCOUNT, observed),
        )
    )
    (step,) = plan_steps(finalized)
    assert isinstance(step, PlannedUpdate)
    assert _member_value(step.assignments.attributes, "balance") == Decimal("150.00")
    assert [(tuple(write.changed), write.advanced) for write in settled_writes(finalized)] == [
        ((state,), (state,))
    ]


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
    simulated = _simulated(_BALANCE)

    def body(tx: UnitOfWork) -> None:
        tx.buffer(
            _prepared_keyed(
                KeyedWriteInstruction(
                    "insert", "Balance", ({"id": 9, "acctNum": "D", "value": Decimal("1.00")},)
                ),
                _BALANCE,
            )
        )
        tx.read(lambda: "row")  # forces the first flush
        tx.buffer(
            _prepared_keyed(
                KeyedWriteInstruction(
                    "insert", "Balance", ({"id": 10, "acctNum": "E", "value": Decimal("2.00")},)
                ),
                _BALANCE,
            )
        )

    _run(body, clock=clock, steps=simulated, meta=_BALANCE)
    # The forced flush and the commit flush carry the SAME holder, so consuming
    # either yields one Transaction-Time instant for the whole transaction
    # (Reladomo's per-transaction timestamp) — observable only through each
    # insert's own stamped `txStart`, since a Write Plan retains no
    # Transaction Instant of its own.
    assert _kinds(simulated) == ["insert", "insert"]
    assert all(_FIXED in statement.binds for statement in simulated.statements)
    assert clock.calls == 1


# --------------------------------------------------------------------------- #
# The flush scope.                                                             #
# --------------------------------------------------------------------------- #
class _Scope:
    """One opened flush scope, recording each transition it makes."""

    def __init__(self, order: list[str], trigger: FlushTrigger) -> None:
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


def _opener(order: list[str]) -> OpenFlush:
    return lambda trigger: _Scope(order, trigger)


def test_each_flush_is_a_scope_around_its_own_planning_and_execution() -> None:
    order: list[str] = []
    steps = ObservedSteps(_simulated(), observe=lambda _position, _steps: order.append("executed"))

    def body(tx: UnitOfWork) -> None:
        tx.buffer(_account_insert(1))
        tx.read(lambda: None)
        tx.buffer(_account_insert(2))

    _run(body, steps=steps, opening=_opener(order))
    assert order == [
        "opened:read_dependency",
        "executed",
        "left:read_dependency",
        "opened:pre_commit",
        "executed",
        "left:pre_commit",
    ]


def test_a_unit_of_work_without_a_flush_opening_still_flushes() -> None:
    simulated = _simulated()

    def body(tx: UnitOfWork) -> None:
        tx.buffer(_account_insert(3))

    _run(body, steps=simulated)
    assert _kinds(simulated) == ["insert"]


# --------------------------------------------------------------------------- #
# Use after the attempt's lifetime ended.                                      #
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
                VersionedObjectStateKey(corpus_object_key("Account", ("id", 1)), 1),
                VersionObservation(observed_version=1),
                None,
            )
        )
    with pytest.raises(EscapedTransactionError):
        tx.flush(trigger="pre_commit")
    with pytest.raises(EscapedTransactionError):
        tx.read(lambda: None)


# --------------------------------------------------------------------------- #
# The keyed writes the claim tests buffer.                                     #
# --------------------------------------------------------------------------- #
_TX_START = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def _balance_members(key: int, tx_start: object = _TX_START) -> dict[str, object]:
    return {
        "id": key,
        "acctNum": "A",
        "value": Decimal("1.00"),
        "txStart": tx_start,
        "txEnd": INFINITY,
    }


def _account_state(key: int, version: int) -> VersionedObjectStateKey:
    return VersionedObjectStateKey(corpus_object_key("Account", ("id", key)), version)


def _balance_state(key: int) -> ObjectStateKey:
    object_key = corpus_object_key("Balance", ("id", key))
    shape = temporal_read.view(_BALANCE).shape(object_key.entity)
    assert shape is not None
    return object_state_key_from_observation(
        object_key,
        TemporalObservation(predecessor=PredecessorRow(_balance_members(key))),
        shape,
    )


def _account_write(mutation: KeyedMutation, account_id: int, version: int) -> AdmittedWrite:
    row: dict[str, object] = {"id": account_id}
    if mutation == "amend":
        row["balance"] = Decimal("1.00")
    evidence = VersionObservation(observed_version=version)
    return admitted_write(
        _prepared_keyed(KeyedWriteInstruction(mutation, "Account", (row,)), _ACCOUNT),
        RetainedObservation(_account_state(account_id, version), evidence, None),
    )


def _balance_update(key: int) -> AdmittedWrite:
    observation = TemporalObservation(predecessor=PredecessorRow(_balance_members(key)))
    return admitted_write(
        _prepared_keyed(
            KeyedWriteInstruction("amend", "Balance", ({"id": key, "value": Decimal("2.00")},)),
            _BALANCE,
        ),
        RetainedObservation(_balance_state(key), observation, None),
    )


def _refused_as_claimed(uow: UnitOfWork, item: AdmittedWrite) -> WriteEvidenceError:
    with pytest.raises(WriteEvidenceError) as refusal:
        uow.buffer(item)
    assert refusal.value.code == "write-evidence-already-claimed"
    return refusal.value


# --------------------------------------------------------------------------- #
# Buffering a keyed write admits the claim its admitted write names, or       #
# refuses it and changes nothing.                                             #
# --------------------------------------------------------------------------- #
_PERSON_META = model_of(PERSON)


def _person_write(
    mutation: KeyedMutation, person_id: int, source: ReadEvidence | None = None
) -> AdmittedWrite:
    """An unversioned Non-Temporal Person write settling against its object."""
    row: dict[str, object] = {"id": person_id}
    if mutation == "amend":
        row["name"] = "Grace"
    prepared = _prepared_keyed(KeyedWriteInstruction(mutation, "Person", (row,)), _PERSON_META)
    key = corpus_object_key("Person", ("id", person_id))
    return admitted_write(prepared, key, source=object_source(key) if source is None else source)


def test_a_retained_observation_claims_its_state_and_compatible_intents_combine() -> None:
    simulated = _simulated()

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_account_write("amend", 1, 7))
        uow.buffer(_account_write("amend", 1, 7))
        uow.buffer(_account_write("delete", 1, 7))
        uow.buffer(_account_write("delete", 1, 7))
        refusal = _refused_as_claimed(uow, _account_write("amend", 1, 7))
        assert refusal.object_key == corpus_object_key("Account", ("id", 1))
        assert "parallax.compatibility.Account" in refusal.message

    _run(body, steps=simulated)
    assert _kinds(simulated) == ["delete"]


def test_a_retained_claim_is_taken_at_the_exact_observed_state() -> None:
    # Two states of one object are two scopes: a destruction of one leaves the
    # other's assignment unrefused.
    def body(uow: UnitOfWork) -> None:
        uow.buffer(_account_write("delete", 1, 7))
        uow.buffer(_account_write("amend", 1, 8))
        _refused_as_claimed(uow, _account_write("amend", 1, 7))
        raise _Abandoned

    with pytest.raises(_Abandoned):
        _run(body)


def test_an_object_locked_write_claims_its_instructions_object() -> None:
    simulated = _simulated(_PERSON_META)

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_person_write("amend", 1))
        uow.buffer(_person_write("delete", 1))
        refusal = _refused_as_claimed(uow, _person_write("amend", 1))
        assert refusal.object_key == corpus_object_key("Person", ("id", 1))
        uow.buffer(_person_write("amend", 2))

    _run(body, steps=simulated, meta=_PERSON_META)
    assert sorted(_kinds(simulated)) == ["delete", "update"]


def _buffer_composed_person_writes(uow: UnitOfWork) -> list[weakref.ref[ReadEvidence]]:
    # The second amendment of 1 coalesces into the first, the first deletion
    # supersedes their merge, and the second deduplicates into it. The two
    # sources of 1's deletions are equal yet distinct.
    one = corpus_object_key("Person", ("id", 1))
    sources = [
        object_source(one),
        object_source(corpus_object_key("Person", ("id", 2))),
        object_source(one),
        object_source(one),
        object_source(one),
    ]
    writes: tuple[tuple[KeyedMutation, int], ...] = (
        ("amend", 1),
        ("amend", 2),
        ("amend", 1),
        ("delete", 1),
        ("delete", 1),
    )
    for (mutation, person_id), source in zip(writes, sources, strict=True):
        uow.buffer(_person_write(mutation, person_id, source))
    return [weakref.ref(source) for source in sources]


def test_every_composed_object_source_stays_reachable_until_its_settled_write_is_gone() -> None:
    simulated = _simulated(_PERSON_META)
    held: list[weakref.ref[ReadEvidence]] = []
    seen: list[int] = []

    def observe(_position: int, _steps: object) -> None:
        gc.collect()
        seen.append(sum(source() is not None for source in held))

    def body(uow: UnitOfWork) -> None:
        held.extend(_buffer_composed_person_writes(uow))
        gc.collect()
        # Only the pending writes reach the sources now.
        assert all(source() is not None for source in held)

    steps = ObservedSteps(simulated, observe=observe)
    _run(body, steps=steps, meta=_PERSON_META)
    assert sorted(_kinds(simulated)) == ["delete", "update"]
    # Coalescing, supersession, and deduplication kept every source while the
    # plan executed, and nothing kept any once the flush released its plan.
    assert seen == [len(held)] * steps.executions
    gc.collect()
    assert all(source() is None for source in held)


def test_a_refused_admitted_write_or_claim_leaves_claims_and_pending_inserts_as_they_were() -> None:
    def body(uow: UnitOfWork) -> None:
        uow.buffer(_account_insert(9))
        uow.buffer(_account_write("delete", 1, 7))
        with pytest.raises(ValueError, match="evidence about one row"):
            uow.buffer(
                admitted_write(
                    _prepared_keyed(
                        KeyedWriteInstruction("delete", "Account", ({"id": 9}, {"id": 1})), _ACCOUNT
                    ),
                    RetainedObservation(
                        _account_state(1, 7), VersionObservation(observed_version=7), None
                    ),
                )
            )
        _refused_as_claimed(uow, _account_write("amend", 1, 7))
        assert uow.buffer(_account_delete(9)) is BufferOutcome.CANCELLED_PENDING_INSERT
        _refused_as_claimed(uow, _account_write("amend", 1, 7))

    _run(body)


class _Abandoned(Exception):
    """Ends a body whose buffer no flush is meant to plan."""


# --------------------------------------------------------------------------- #
# Buffering reports the pending-insert transition it made.                    #
# --------------------------------------------------------------------------- #
def _account_delete(account_id: int) -> PreparedKeyedInstruction:
    return _prepared_keyed(
        KeyedWriteInstruction("delete", "Account", ({"id": account_id},)), _ACCOUNT
    )


def test_a_destructive_write_of_a_pending_insert_reports_the_cancellation() -> None:
    simulated = _simulated()

    def body(uow: UnitOfWork) -> None:
        assert uow.buffer(_account_insert(9)) is BufferOutcome.BUFFERED
        assert uow.buffer(_account_delete(8)) is BufferOutcome.BUFFERED
        assert uow.buffer(_account_delete(9)) is BufferOutcome.CANCELLED_PENDING_INSERT
        assert uow.buffer(_account_insert(9)) is BufferOutcome.BUFFERED
        assert uow.buffer(_account_delete(9)) is BufferOutcome.CANCELLED_PENDING_INSERT
        assert uow.buffer(_account_delete(9)) is BufferOutcome.BUFFERED
        raise _Abandoned

    with pytest.raises(_Abandoned):
        _run(body, steps=simulated)
    assert simulated.statements == ()


def test_every_other_accepted_item_reports_plain_buffering() -> None:
    def body(uow: UnitOfWork) -> None:
        assert uow.buffer(_account_write("amend", 1, 7)) is BufferOutcome.BUFFERED
        assert uow.buffer(_account_write("delete", 2, 7)) is BufferOutcome.BUFFERED
        raise _Abandoned

    with pytest.raises(_Abandoned):
        _run(body)

    def unversioned(uow: UnitOfWork) -> None:
        assert uow.buffer(_person_write("amend", 1)) is BufferOutcome.BUFFERED
        assert uow.buffer(_person_write("delete", 2)) is BufferOutcome.BUFFERED
        raise _Abandoned

    with pytest.raises(_Abandoned):
        _run(unversioned, meta=_PERSON_META)


def test_a_destructive_write_after_the_insert_flushed_cancels_nothing() -> None:
    simulated = _simulated()

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_account_insert(9))
        uow.read(lambda: None)
        assert uow.buffer(_account_write("delete", 9, 1)) is BufferOutcome.BUFFERED

    _run(body, steps=simulated)
    assert _kinds(simulated) == ["insert", "delete"]


# --------------------------------------------------------------------------- #
# Settled writes: completion, ownership, freshness and failure containment.   #
# --------------------------------------------------------------------------- #
def _balance_insert(key: int) -> PreparedKeyedInstruction:
    return _prepared_keyed(
        KeyedWriteInstruction(
            "insert", "Balance", ({"id": key, "acctNum": "A", "value": Decimal("1.00")},)
        ),
        _BALANCE,
    )


def _balance_update_from(key: int, tx_start: object) -> AdmittedWrite:
    members = _balance_members(key, tx_start)
    observation = TemporalObservation(predecessor=PredecessorRow(members))
    state = object_state_key_from_observation(
        corpus_object_key("Balance", ("id", key)),
        observation,
        _balance_shape(),
    )
    return admitted_write(
        _prepared_keyed(
            KeyedWriteInstruction("amend", "Balance", ({"id": key, "value": Decimal("2.00")},)),
            _BALANCE,
        ),
        RetainedObservation(state, observation, None),
    )


def _balance_shape() -> temporal_read.TemporalShape:
    shape = temporal_read.view(_BALANCE).shape(corpus_object_key("Balance", ("id", 1)).entity)
    assert shape is not None
    return shape


def test_a_row_an_earlier_flush_opened_is_revised_rather_than_closed() -> None:
    simulated = _simulated(_BALANCE)

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_balance_insert(1))
        uow.read(lambda: None)
        uow.buffer(_balance_update_from(1, _FIXED))

    _run(body, meta=_BALANCE, steps=simulated)
    assert _kinds(simulated) == ["insert", "update"]


def _balance_terminate_from(key: int, tx_start: object) -> AdmittedWrite:
    members = _balance_members(key, tx_start)
    observation = TemporalObservation(predecessor=PredecessorRow(members))
    state = object_state_key_from_observation(
        corpus_object_key("Balance", ("id", key)), observation, _balance_shape()
    )
    return admitted_write(
        _prepared_keyed(KeyedWriteInstruction("terminate", "Balance", ({"id": key},)), _BALANCE),
        RetainedObservation(state, observation, None),
    )


def test_a_row_its_settled_write_removed_is_no_longer_owned() -> None:
    simulated = _simulated(_BALANCE)

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

    _run(body, meta=_BALANCE, steps=simulated)
    assert _kinds(simulated) == ["insert", "delete", "delete", "close", "insert"]


def test_a_row_whose_start_is_the_attempts_instant_is_not_owned_without_its_opening() -> None:
    simulated = _simulated(_BALANCE)

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_balance_update_from(1, _FIXED))

    _run(body, meta=_BALANCE, steps=simulated)
    assert _kinds(simulated) == ["close", "insert"]


def test_each_settled_write_publishes_its_change_before_the_next_group_executes() -> None:
    writes = (
        _account_write("amend", 1, 7),
        _account_write("amend", 2, 3),
        _account_write("delete", 3, 1),
    )
    retained = tuple(
        write.retained_observation for write in writes if isinstance(write, StateObservedWrite)
    )
    seen: list[tuple[bool, ...]] = []

    def spent() -> tuple[bool, ...]:
        return tuple(observation.invalidated for observation in retained)

    def body(uow: UnitOfWork) -> None:
        for observation in retained:
            assert uow.retain(observation) is observation
        for write in writes:
            uow.buffer(write)

    _run(
        body,
        steps=ObservedSteps(_simulated(), observe=lambda _position, _steps: seen.append(spent())),
    )
    # The two amendments share the update phase's group; the deletion is the
    # delete phase's own.
    assert [*seen, spent()] == [
        (False, False, False),
        (True, True, False),
        (True, True, True),
    ]


def test_full_groups_publish_in_turn_and_a_failed_one_ends_the_flush() -> None:
    claims = [_account_claim(account_id, 1) for account_id in range(1, 131)]
    spent: list[int] = []

    def body(uow: UnitOfWork) -> None:
        for account_id, claim in enumerate(claims, start=1):
            uow.buffer(_account_amend(account_id, uow.retain(claim)))
        uow.read(lambda: None)

    _run(
        body,
        steps=ObservedSteps(
            _simulated(),
            observe=lambda _position, _steps: spent.append(sum(c.invalidated for c in claims)),
        ),
    )
    assert spent == [0, 64, 128]
    assert all(claim.invalidated for claim in claims)

    failing = [_account_claim(account_id, 1) for account_id in range(1, 131)]
    steps = ObservedSteps(_simulated(), failing=1, failure=RuntimeError("the second group failed"))

    def failed(uow: UnitOfWork) -> None:
        for account_id, claim in enumerate(failing, start=1):
            uow.buffer(_account_amend(account_id, uow.retain(claim)))
        with pytest.raises(RuntimeError, match="the second group failed"):
            uow.read(lambda: None)

    with pytest.raises(RollbackOnlyError):
        _run(failed, steps=steps)
    assert [claim.invalidated for claim in failing] == [True] * 64 + [False] * 66
    assert steps.executions == 2


def test_a_caught_execution_failure_still_dooms_the_attempt() -> None:
    failure = RuntimeError("the statement failed")
    claimed = _account_write("amend", 1, 7)
    assert isinstance(claimed, StateObservedWrite)
    steps = ObservedSteps(_simulated(), failing=0, failure=failure)

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
        _run(body, steps=steps)
    assert exc.value.__cause__ is failure
    assert not claimed.retained_observation.invalidated


def test_a_planning_refusal_leaves_the_attempt_usable() -> None:
    bare_close = _prepared_keyed(
        KeyedWriteInstruction("amend", "Balance", ({"id": 1, "value": Decimal("2.00")},)), _BALANCE
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
        assert unsubmitted.invalidated
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


def test_a_write_that_changes_nothing_leaves_its_source_and_its_state_as_they_were() -> None:
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
    state = object_state_key_from_observation(
        corpus_object_key("Position", ("id", 1)), observation, shape
    )
    simulated = _simulated(_POSITION)
    coverage = HeldRows(_POSITION)

    def body(uow: UnitOfWork) -> None:
        uow.buffer(
            _prepared_keyed(
                KeyedWriteInstruction(
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
            admitted_write(
                _prepared_keyed(
                    KeyedWriteInstruction("terminate", "Position", ({"id": 1},), valid_from=_DEC),
                    _POSITION,
                ),
                claim,
            )
        )
        uow.read(lambda: None)
        assert not claim.invalidated
        late = uow.retain(RetainedObservation(state, observation, None), read_at=read_at)
        assert not late.invalidated

    _run(body, meta=_POSITION, steps=simulated, rows=coverage)
    # The range read its coverage and bound to nothing to execute.
    assert _kinds(simulated) == ["insert"]
    assert [type(request) for request in coverage.requests] == [CoverageReadRequest]


@pytest.mark.parametrize(
    ("value", "kept"), [("100.00", True), ("150.00", False)], ids=["unchanged", "changed"]
)
def test_a_guarded_write_leaves_an_unchanged_state_fresh(value: str, kept: bool) -> None:
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
    state = object_state_key_from_observation(key, observation, shape)
    simulated = _simulated(_BALANCE)

    def body(uow: UnitOfWork) -> None:
        read_at = uow.freshness
        claim = uow.retain(RetainedObservation(state, observation, None))
        uow.buffer(
            admitted_write(
                _prepared_keyed(
                    KeyedWriteInstruction(
                        "amend", "Balance", ({"id": 1, "value": Decimal(value)},)
                    ),
                    _BALANCE,
                ),
                claim,
            )
        )
        uow.read(lambda: None)
        assert claim.invalidated is not kept
        # Evidence an earlier read of the same rows builds now is still evidence
        # of the stored state exactly when the settled write left that state as it was.
        late = uow.retain(RetainedObservation(state, observation, None), read_at=read_at)
        assert late.invalidated is not kept

    _run(
        body,
        meta=_BALANCE,
        steps=simulated,
        settings=TransactionSettings(counts_unchanged_rows=True),
    )
    assert _kinds(simulated) == (["guard"] if kept else ["close", "insert"])


def _account_amend(account_id: int, claim: RetainedObservation) -> AdmittedWrite:
    row = {"id": account_id, "balance": Decimal("1.00")}
    return admitted_write(
        _prepared_keyed(KeyedWriteInstruction("amend", "Account", (row,)), _ACCOUNT), claim
    )


def _account_claim(account_id: int, version: int) -> RetainedObservation:
    return RetainedObservation(
        _account_state(account_id, version), VersionObservation(observed_version=version), None
    )


def test_each_settled_write_names_its_sources_state_itself() -> None:
    first, second = _account_claim(1, 7), _account_claim(2, 3)
    plan = build_write_planner(_ACCOUNT).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=TransactionInstant(FixedClock(_FIXED)),
            concurrency="optimistic",
            composed_writes=admitted_writes(
                _ACCOUNT, [_account_amend(1, first), _account_amend(2, second)]
            ),
        )
    )
    # Nothing infers a settled write's changed state from a step.
    assert [(tuple(write.changed), write.advanced) for write in settled_writes(plan)] == [
        ((first.key,), (first.key,)),
        ((second.key,), (second.key,)),
    ]


@pytest.mark.parametrize(
    ("failing", "published"),
    [(0, (False, False, False)), (1, (True, True, False))],
    ids=["the-amendments-group-fails", "the-deletion-group-fails"],
)
def test_a_failed_group_publishes_nothing_while_the_group_before_it_stays_published(
    failing: int, published: tuple[bool, ...]
) -> None:
    failure = RuntimeError("the group failed")
    claims: list[RetainedObservation] = []

    def body(uow: UnitOfWork) -> None:
        for account_id, version in ((1, 7), (2, 3)):
            claim = uow.retain(_account_claim(account_id, version))
            claims.append(claim)
            uow.buffer(_account_amend(account_id, claim))
        deleted = uow.retain(_account_claim(3, 1))
        claims.append(deleted)
        uow.buffer(
            admitted_write(
                _prepared_keyed(KeyedWriteInstruction("delete", "Account", ({"id": 3},)), _ACCOUNT),
                deleted,
            )
        )
        with pytest.raises(RuntimeError, match="the group failed"):
            uow.read(lambda: None)

    with pytest.raises(RollbackOnlyError):
        _run(body, steps=ObservedSteps(_simulated(), failing=failing, failure=failure))
    assert tuple(claim.invalidated for claim in claims) == published


def test_a_settled_write_with_no_step_changes_nothing() -> None:
    members = {
        "id": 1,
        "acctNum": "A",
        "value": Decimal("100.00"),
        "txStart": _JAN,
        "txEnd": INFINITY,
    }
    observation = TemporalObservation(predecessor=PredecessorRow(members))
    key = corpus_object_key("Balance", ("id", 1))
    state = object_state_key_from_observation(key, observation, _balance_shape())
    simulated = _simulated(_BALANCE)

    def body(uow: UnitOfWork) -> None:
        claim = uow.retain(RetainedObservation(state, observation, uow.participation))
        uow.buffer(
            admitted_write(
                _prepared_keyed(
                    KeyedWriteInstruction(
                        "amend", "Balance", ({"id": 1, "value": Decimal("100.00")},)
                    ),
                    _BALANCE,
                ),
                claim,
            )
        )
        uow.read(lambda: None)
        assert not claim.invalidated

    _run(
        body,
        meta=_BALANCE,
        steps=simulated,
        settings=TransactionSettings(concurrency="locking"),
    )
    assert simulated.statements == ()


class ShellTag(Entity, table="shell_tag", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


class ShellKey(Entity, table="shell_key", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)


_PREDICATED = model_of(DomainModel(WherePosition, ShellTag, ShellKey))
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


@dataclass(slots=True)
class _Watched:
    """``held``'s answers, ``watch`` called as each read is asked for."""

    held: HeldRows
    watch: Callable[[], object]

    def __call__[Request: RowRequest, Result](
        self, request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        self.watch()
        return self.held(request, consumer)


def _position_target(start: dt.datetime, until: dt.datetime) -> PreparedTargetInstruction:
    prepared = prepare_wire_write(
        TargetWriteInstruction(
            "amendUntil",
            "WherePosition",
            {"id": 1, "value": "175.00"},
            if_tx_start=_T0,
            valid_from=start,
            until=until,
        ),
        _PREDICATED,
    )
    assert isinstance(prepared, PreparedTargetInstruction)
    return prepared


def _observed_amendment(claim: RetainedObservation) -> AdmittedWrite:
    observed = prepare_wire_write(
        KeyedWriteInstruction(
            "amendUntil",
            "WherePosition",
            ({"id": 1, "acctNum": "O"},),
            valid_from=_FEB,
            until=_APR,
        ),
        _PREDICATED,
    )
    assert isinstance(observed, PreparedKeyedInstruction)
    return admitted_write(observed, claim)


def test_a_target_after_a_predicate_write_judges_its_condition_on_what_the_earlier_write_left() -> (
    None
):
    original = TemporalObservation(predecessor=_position_row(_JAN, _T0))
    key = corpus_object_key("WherePosition", ("id", 1))
    shape = temporal_read.view(_PREDICATED).shape(key.entity)
    assert shape is not None
    state = object_state_key_from_observation(key, original, shape)
    held: list[RetainedObservation] = []
    coverage = HeldRows(_PREDICATED)
    simulated = _simulated(_PREDICATED)

    def body(uow: UnitOfWork) -> None:
        claim = uow.retain(RetainedObservation(state, original, uow.participation))
        held.append(claim)
        uow.buffer(_observed_amendment(claim))
        uow.execute_predicate(_shell_predicate_write())
        uow.buffer_target(_position_target(_JUN, _AUG))
        uow.read(lambda: None)

    with pytest.raises(WritePreconditionError):
        _run(body, meta=_PREDICATED, steps=simulated, rows=coverage, counted=simulated.counted)
    # The predicate write's flush completed the earlier write, which changed
    # the shared source's state; the start the later target's caller states,
    # literally, is gone from the coverage it reads, so it executes nothing.
    (claim,) = held
    assert claim.invalidated
    assert statement_kinds(simulated.statements) == ["close", "insert", "update"]


def test_writes_of_one_source_predicate_writes_flush_each_continue_from_what_the_last_left() -> (
    None
):
    original = TemporalObservation(predecessor=_position_row(_JAN, _T0))
    key = corpus_object_key("WherePosition", ("id", 1))
    shape = temporal_read.view(_PREDICATED).shape(key.entity)
    assert shape is not None
    state = object_state_key_from_observation(key, original, shape)
    held = HeldRows(_PREDICATED)
    simulated = _simulated(_PREDICATED)

    def body(uow: UnitOfWork) -> None:
        claim = uow.retain(RetainedObservation(state, original, uow.participation))
        uow.buffer(_observed_amendment(claim))
        for window in ((_JUN, _AUG), (_SEP, _OCT)):
            uow.execute_predicate(_shell_predicate_write())
            uow.buffer(_observed_value(claim, *window))
        uow.read(lambda: None)

    _run(body, meta=_PREDICATED, steps=simulated, rows=held, counted=simulated.counted)
    # Each later write bound to the rows the one before it produced, which
    # the attempt holds for the source they share: nothing was read again, and
    # only the first closed anything.
    assert held.requests == []
    assert statement_kinds(simulated.statements).count("close") == 1


def _observed_value(
    claim: RetainedObservation, start: dt.datetime, until: dt.datetime
) -> AdmittedWrite:
    observed = prepare_wire_write(
        KeyedWriteInstruction(
            "amendUntil",
            "WherePosition",
            ({"id": 1, "value": "175.00"},),
            valid_from=start,
            until=until,
        ),
        _PREDICATED,
    )
    assert isinstance(observed, PreparedKeyedInstruction)
    return admitted_write(observed, claim)


def _account_target(version: int) -> PreparedTargetInstruction:
    prepared = prepare_wire_write(
        TargetWriteInstruction(
            "amend", "Account", {"id": 1, "balance": "6.00"}, if_version=version
        ),
        _ACCOUNT,
    )
    assert isinstance(prepared, PreparedTargetInstruction)
    return prepared


@pytest.mark.parametrize(
    ("meta", "target", "rows"),
    [
        pytest.param(_ACCOUNT, lambda: _account_target(3), (), id="non-temporal"),
        pytest.param(
            _PREDICATED,
            lambda: _position_target(_JUN, _AUG),
            (_position_row(_JAN, _T0),),
            id="temporal",
        ),
    ],
)
def test_a_target_write_is_admitted_as_its_verb_admits_it(
    meta: Metamodel,
    target: Callable[[], PreparedTargetInstruction],
    rows: tuple[PredecessorRow, ...],
) -> None:
    # Buffered directly or through its verb, one acceptance judges it: the
    # Optimistic strategy reads nothing at the call, and the flush makes the
    # same statements of it.
    def flushed(
        buffering: Callable[[UnitOfWork, PreparedTargetInstruction], object],
    ) -> tuple[list[object], tuple[object, ...], list[RowRequest]]:
        simulated = _simulated(meta)
        held = HeldRows(meta, rows)
        outcomes: list[object] = []
        _run(
            lambda uow: outcomes.append(buffering(uow, target())),
            meta=meta,
            steps=simulated,
            rows=held,
        )
        return outcomes, simulated.statements, held.requests

    outcomes, carried, carried_reads = flushed(
        lambda uow, prepared: uow.buffer(target_write(prepared, inheritance.view(meta)))
    )
    _admitted, admitted, admitted_reads = flushed(lambda uow, prepared: uow.buffer_target(prepared))
    assert outcomes == [BufferOutcome.BUFFERED]
    assert carried and carried == admitted
    assert carried_reads == admitted_reads
    assert not any(isinstance(request, TargetReadRequest) for request in carried_reads)


@pytest.mark.parametrize("route", ["admitted-write", "verb"])
def test_a_locking_target_write_is_confirmed_once_on_every_route(route: str) -> None:
    stored = PredecessorRow(
        members={"id": 1, "owner": "Ada", "balance": Decimal("5.00"), "version": 2}
    )
    locking = TransactionSettings(concurrency="locking")

    def buffering(uow: UnitOfWork, version: int) -> None:
        prepared = _account_target(version)
        if route == "admitted-write":
            uow.buffer(target_write(prepared, inheritance.view(_ACCOUNT)))
        else:
            uow.buffer_target(prepared)

    held = HeldRows(_ACCOUNT, (stored,))
    with pytest.raises(WritePreconditionError):
        _run(lambda uow: buffering(uow, 3), settings=locking, rows=held)
    assert [type(request) for request in held.requests] == [TargetReadRequest]
    held.requests.clear()
    simulated = _simulated()
    _run(lambda uow: buffering(uow, 2), settings=locking, steps=simulated, rows=held)
    assert [type(request) for request in held.requests] == [TargetReadRequest]
    assert _kinds(simulated) == ["update"]


def _shell_predicate_write(
    assignments: tuple[WriteAssignment, ...] = (WriteAssignment("ShellTag.label", "q"),),
) -> PreparedPredicateInstruction:
    prepared = prepare_wire_write(
        PredicateWriteInstruction(
            "amend",
            PredicateSelection(
                "ShellTag",
                predicate_algebra.Comparison(
                    "eq", predicate_algebra.FieldSubject("ShellTag.id"), 1
                ),
            ),
            assignments=assignments,
        ),
        _PREDICATED,
    )
    assert isinstance(prepared, PreparedPredicateInstruction)
    return prepared


def _tag_insert(tag_id: int) -> PreparedKeyedInstruction:
    return _prepared_keyed(
        KeyedWriteInstruction("insert", "ShellTag", ({"id": tag_id, "label": "t"},)), _PREDICATED
    )


# --------------------------------------------------------------------------- #
# A predicate-selected write executes at the call, after what is buffered.     #
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class _Counted:
    """Counted step execution through ``simulated``, answering ``count``, or
    raising ``failure`` instead where it is given."""

    simulated: SimulatedWriteSteps
    order: list[str]
    count: int = 3
    failure: BaseException | None = None

    def __call__(self, step: PlannedUpdate | PlannedDelete, /) -> int:
        self.order.append("counted")
        if self.failure is not None:
            raise self.failure
        self.simulated.counted(step)
        return self.count


def test_a_predicate_write_runs_after_everything_buffered_in_one_flush_and_answers_its_count() -> (
    None
):
    order: list[str] = []
    simulated = _simulated(_PREDICATED)
    steps = ObservedSteps(simulated, observe=lambda _position, _steps: order.append("executed"))
    answered: list[int] = []

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_tag_insert(2))
        answered.append(uow.execute_predicate(_shell_predicate_write()))
        # Nothing is left buffered for a later flush.
        uow.read(lambda: None)

    _run(
        body,
        meta=_PREDICATED,
        steps=steps,
        opening=_opener(order),
        counted=_Counted(simulated, order, count=7),
    )
    assert answered == [7]
    assert order == ["opened:predicate_write", "executed", "counted", "left:predicate_write"]
    assert statement_kinds(simulated.statements) == ["insert", "update"]


def test_a_predicate_write_with_nothing_buffered_is_its_flushs_only_statement() -> None:
    order: list[str] = []
    simulated = _simulated(_PREDICATED)
    steps = ObservedSteps(simulated, observe=lambda _position, _steps: order.append("executed"))

    def body(uow: UnitOfWork) -> int:
        return uow.execute_predicate(_shell_predicate_write())

    assert (
        _run(
            body,
            meta=_PREDICATED,
            steps=steps,
            opening=_opener(order),
            counted=_Counted(simulated, order, count=0),
        )
        == 0
    )
    assert order == ["opened:predicate_write", "counted", "left:predicate_write"]


def test_a_predicate_write_whose_buffered_writes_cancelled_executes_no_other_statement() -> None:
    order: list[str] = []
    simulated = _simulated(_PREDICATED)

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_tag_insert(2))
        assert uow.buffer(
            _prepared_keyed(KeyedWriteInstruction("delete", "ShellTag", ({"id": 2},)), _PREDICATED)
        ) is (BufferOutcome.CANCELLED_PENDING_INSERT)
        uow.execute_predicate(_shell_predicate_write())

    _run(
        body,
        meta=_PREDICATED,
        steps=simulated,
        opening=_opener(order),
        counted=_Counted(simulated, order),
    )
    assert order == ["opened:predicate_write", "counted", "left:predicate_write"]
    assert statement_kinds(simulated.statements) == ["update"]


@pytest.mark.parametrize("mutation", ["amend", "replace"])
def test_an_empty_predicate_write_answers_zero_and_leaves_the_buffer_pending(
    mutation: str,
) -> None:
    order: list[str] = []
    simulated = _simulated(_PREDICATED)
    empty = (
        _shell_predicate_write(assignments=())
        if mutation == "amend"
        else prepare_wire_write(
            PredicateWriteInstruction(
                "replace",
                PredicateSelection("ShellKey", predicate_algebra.TrueNode()),
                row={},
            ),
            _PREDICATED,
        )
    )
    assert isinstance(empty, PreparedPredicateInstruction)
    assert not empty.assigns

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_tag_insert(2))
        assert uow.execute_predicate(empty) == 0
        order.append("answered")

    _run(
        body,
        meta=_PREDICATED,
        steps=simulated,
        opening=_opener(order),
        counted=_Counted(simulated, order),
    )
    # The buffered insert waited for the pre-commit flush.
    assert order == ["answered", "opened:pre_commit", "left:pre_commit"]
    assert statement_kinds(simulated.statements) == ["insert"]


def test_an_empty_predicate_write_is_refused_once_the_lifetime_has_ended() -> None:
    captured: dict[str, UnitOfWork] = {}

    def body(tx: UnitOfWork) -> None:
        captured["tx"] = tx

    _run(body, meta=_PREDICATED)
    with pytest.raises(EscapedTransactionError):
        captured["tx"].execute_predicate(_shell_predicate_write(assignments=()))


def test_a_doomed_lifetime_refuses_an_empty_predicate_write() -> None:
    lifetime = TxnAttemptLifetime()

    refused: list[RollbackOnlyError] = []

    def body(tx: UnitOfWork) -> None:
        lifetime.doom(RuntimeError("doomed"))
        with pytest.raises(RollbackOnlyError) as exc:
            tx.execute_predicate(_shell_predicate_write(assignments=()))
        refused.append(exc.value)

    with pytest.raises(RollbackOnlyError):
        _run(body, meta=_PREDICATED, lifetime=lifetime)
    assert refused


def test_a_planning_refusal_before_a_predicate_write_keeps_the_buffer_and_the_attempt() -> None:
    order: list[str] = []
    bare_close = _prepared_keyed(
        KeyedWriteInstruction(
            "amendUntil",
            "WherePosition",
            ({"id": 1, "acctNum": "O"},),
            valid_from=_FEB,
            until=_APR,
        ),
        _PREDICATED,
    )
    simulated = _simulated(_PREDICATED)

    def body(uow: UnitOfWork) -> None:
        uow.buffer(bare_close)
        with pytest.raises(WritePlanningError):
            uow.execute_predicate(_shell_predicate_write())
        assert uow.read(lambda: "still usable") == "still usable"

    # The refused write is still buffered, so the commit flush refuses it again
    # rather than the attempt being doomed.
    with pytest.raises(WritePlanningError):
        _run(
            body,
            meta=_PREDICATED,
            steps=simulated,
            opening=_opener(order),
            counted=_Counted(simulated, order),
        )
    assert order[:2] == ["opened:predicate_write", "failed:predicate_write"]
    assert "counted" not in order


def test_an_execution_failure_before_a_predicate_write_dooms_it_unplanned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("the insert failed")
    order: list[str] = []
    simulated = _simulated(_PREDICATED)
    steps = ObservedSteps(simulated, failing=0, failure=failure)
    planned: list[object] = []
    planning = WritePlanner.predicate_step

    def recording(self: WritePlanner, *args: Any, **kwargs: Any) -> PlannedUpdate | PlannedDelete:
        planned.append(args)
        return planning(self, *args, **kwargs)

    monkeypatch.setattr(WritePlanner, "predicate_step", recording)

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_tag_insert(2))
        with pytest.raises(RuntimeError, match="the insert failed"):
            uow.execute_predicate(_shell_predicate_write())

    with pytest.raises(RollbackOnlyError) as doomed:
        _run(body, meta=_PREDICATED, steps=steps, counted=_Counted(simulated, order))
    assert doomed.value.__cause__ is failure
    assert (planned, order) == ([], [])


def test_a_refused_predicate_step_fails_its_flush_without_dooming_or_restoring_earlier_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    monkeypatch.setattr(planning_composition, "NO_AUDIT", _ReshapingAudit())
    simulated = _simulated(_PREDICATED)

    def body(uow: UnitOfWork) -> str:
        uow.buffer(_tag_insert(2))
        with pytest.raises(WritePlanningError):
            uow.execute_predicate(_shell_predicate_write())
        return uow.read(lambda: "still usable")

    assert (
        _run(
            body,
            meta=_PREDICATED,
            steps=simulated,
            opening=_opener(order),
            counted=_Counted(simulated, order),
        )
        == "still usable"
    )
    # The insert the flush executed stays executed; nothing restores it to the
    # buffer for the pre-commit flush, which has nothing to do.
    assert order == ["opened:predicate_write", "failed:predicate_write"]
    assert statement_kinds(simulated.statements) == ["insert"]


def test_a_failure_executing_a_predicate_write_dooms_the_attempt() -> None:
    failure = RuntimeError("the predicate statement failed")
    order: list[str] = []
    simulated = _simulated(_PREDICATED)

    def body(uow: UnitOfWork) -> str:
        with pytest.raises(RuntimeError, match="the predicate statement failed"):
            uow.execute_predicate(_shell_predicate_write())
        with pytest.raises(RollbackOnlyError) as refused:
            uow.read(lambda: None)
        assert refused.value.__cause__ is failure
        return "withheld"

    with pytest.raises(RollbackOnlyError):
        _run(
            body,
            meta=_PREDICATED,
            steps=simulated,
            opening=_opener(order),
            counted=_Counted(simulated, order, failure=failure),
        )
    assert order == ["opened:predicate_write", "counted", "failed:predicate_write"]


class _ReshapingAudit(RecordingAudit):
    """An audit decorating every update into an update of another Entity,
    which no decoration may change."""

    def decorate_update(
        self,
        update: PlannedUpdate,
        *,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
    ) -> PlannedUpdate:
        del actor_identity, transaction_instant
        return replace(update, entity=corpus_object_key("WherePosition", ("id", 1)).entity)


def _opening_geometry(plan: WritePlan) -> set[tuple[object, object, object]]:
    """Each row a plan's inserts open, by Valid Time and value."""
    rows: set[tuple[object, object, object]] = set()
    for step in plan_steps(plan):
        if isinstance(step, PlannedInsert):
            (entry,) = step.entries
            cells = {identity.name: value for identity, value in entry.row.attributes.items()}
            rows.add((cells["validStart"], cells["validEnd"], cells["value"]))
    return rows


def test_a_pending_opening_settles_as_one_write_of_the_new_lineages_its_edits_leave() -> None:
    insert = _prepared_keyed(
        KeyedWriteInstruction(
            "insert",
            "WherePosition",
            ({"id": 1, "acctNum": "A", "value": Decimal("1.00")},),
            valid_from=_FEB,
        ),
        _PREDICATED,
    )
    edit = _prepared_keyed(
        KeyedWriteInstruction(
            "amendUntil", "WherePosition", ({"id": 1, "value": Decimal("2.00")},), _FEB, _APR
        ),
        _PREDICATED,
    )
    destroy = _prepared_keyed(
        KeyedWriteInstruction("terminateUntil", "WherePosition", ({"id": 1},), _JUN, _AUG),
        _PREDICATED,
    )
    plan = build_write_planner(_PREDICATED).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=TransactionInstant(FixedClock(_FIXED)),
            concurrency="optimistic",
            composed_writes=admitted_writes(_PREDICATED, [insert, edit, destroy]),
        )
    )
    # No predecessor is fabricated for the insert: every surviving part of its
    # own window opens as a new lineage, together, as one write.
    (write,) = settled_writes(plan)
    assert {type(step) for step in plan_steps(plan)} == {PlannedInsert}
    assert {step.entries[0].origin for step in plan_steps(plan)} == {NEW_LINEAGE}  # type: ignore[union-attr]
    assert _opening_geometry(plan) == {
        (_FEB, _APR, Decimal("2.00")),
        (_APR, _JUN, Decimal("1.00")),
        (_AUG, INFINITY, Decimal("1.00")),
    }
    assert tuple(write.opened.continued) == (
        _position_endpoint(_APR),
        _position_endpoint(_JUN),
        _position_endpoint(None),
    )
    assert (tuple(write.changed), tuple(write.opened.fresh)) == ((), ())


def _position_endpoint(end: dt.datetime | None) -> TemporalRowCoordinates:
    entity = corpus_object_key("WherePosition", ("id", 1)).entity
    if end is None:
        return TemporalRowCoordinates(entity, (1,), OPEN_BITEMPORAL_ENDS)
    return TemporalRowCoordinates(entity, (1,), (Finite(instant=end), PLANNED_INFINITY))
