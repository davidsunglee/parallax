"""Unit-of-work coordination unit tests (m-unit-work, Docker-free).

Exercises the writable coordinator of one attempt independently of any real
port or runner (each span a flush executes is simulated, lowering through the
dry traversal and running nothing, and row acquisition is an injected
reader): the pre-commit and read-dependency flushes, discarding buffered
effects, read-your-own-writes force-flush, Clock injection, the attempt
lifetime it consults and dooms, and what buffering admits: the claim each
carrier names, all or nothing, and the pending-insert transition it reports.
The attempt's own lifecycle — commit admission, joins, and rollback — is the
managed runner's, and is tested there.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import TracebackType

import pytest

from parallax.conformance import models
from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.conformance.class_models import MODELS as CLASS_MODELS
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import Attr, DomainModel, Entity, attr, inheritance, opt_lock, temporal_read
from parallax.core import predicate as predicate_algebra
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._transaction._lifetime import TxnAttemptLifetime
from parallax.core._execution._unit_work.acquisition import (
    AcquireRows,
    CoverageReadRequest,
    RowConsumer,
    RowRequest,
    TargetReadRequest,
)
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedTargetWrite,
    TargetWrite,
    prepare_typed_write,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.retain import InsertionIdentity, ReadEvidence
from parallax.core._execution._unit_work.uow import (
    NO_INSERTION_AUTHORITY,
    EscapedTransactionError,
    OpenWriteBatch,
    _TargetWriteState,  # pyright: ignore[reportPrivateUsage] - the owner of the removal window and lineage it is tested at
)
from parallax.core._execution._unit_work.write_items import (
    InsertionKeyedWrite,
    ObservedKeyedWrite,
    readless_write,
    target_write,
)
from parallax.core._execution._unit_work.write_planner import PendingWrites, compose_writes
from parallax.core._execution._unit_work.write_runner import ExecuteWriteSteps
from parallax.core.base import INFINITY
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
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
    buffered_write,
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
    NO_OPENINGS,
    OPEN_BITEMPORAL_ENDS,
    Derivation,
    DerivedRow,
    Openings,
    OwnedEndpoint,
    SourceAuthority,
)
from parallax.core.write_plan.steps import INFINITY as PLANNED_INFINITY
from parallax.core.write_plan.steps import NEW_LINEAGE, Finite, PlannedUpdate
from tests._support.clock_probes import CountingClock
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, RecordingSource
from tests.unit._corpus_identity_support import corpus_object_key
from tests.unit._temporal_group_support import temporal_group
from tests.unit._where_position_model import (
    WherePosition,
)
from tests.unit.core._execution._unit_work._acquired_rows_support import HeldRows
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
    opening: OpenWriteBatch | None = None,
    rows: AcquireRows | None = None,
    lifetime: TxnAttemptLifetime | None = None,
) -> T:
    """Drive ``body`` against a unit of work whose row reads answer ``rows``, or
    find no row at all, and whose spans ``steps`` executes, then flush what it
    left as the attempt's pre-commit batch, and end the attempt's lifetime
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
        acquire_rows=rows or HeldRows(resolved_meta),
        planner=build_write_planner(resolved_meta),
        actor_identity=TEST_ACTOR_IDENTITY,
        evidence_policy_for=opt_lock.view(resolved_meta).required_key,
        write_batch_opening=opening,
    )
    try:
        result = body(uow)
        uow.flush(trigger="pre_commit")
        return result
    finally:
        attempt.close()


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
    # Nothing buffered survives to be planned, so no batch opens.
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
                KeyedWrite(
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
            ObservedKeyedWrite(
                instruction=_prepared_keyed(
                    KeyedWrite("amend", "Account", ({"id": 1, "balance": Decimal("0.00")},)),
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
        buffered_write(
            _prepared_keyed(
                KeyedWrite(
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
        InsertionKeyedWrite(instruction=_account_insert(1), identity=authority)
    with pytest.raises(ValueError, match="the one object it opened"):
        buffered_write(
            _prepared_keyed(
                KeyedWrite(
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
        KeyedWrite("amend", "Account", ({"id": 1, "balance": Decimal("1.00")},)), _ACCOUNT
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


def test_two_writes_of_one_claim_merge_and_answer_it_once() -> None:
    # Two edits of a single source value hold one claim, and Observed-State
    # Coalescing makes them one write: the assignments merge in authored order,
    # the later value wins the member both name, and the merged write's one
    # execution unit keeps the identical retained observation both held.
    state = VersionedObjectStateKey(corpus_object_key("Account", ("id", 1)), 7)
    retained = RetainedObservation(state, VersionObservation(observed_version=7), None)
    carriers = [
        buffered_write(
            _prepared_keyed(
                KeyedWrite("amend", "Account", ({"id": 1, "balance": balance},)), _ACCOUNT
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
    simulated = _simulated(_BALANCE)

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
    steps = ObservedSteps(_simulated(), observe=lambda _span: order.append("executed"))

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


def test_a_unit_of_work_without_a_batch_opening_still_flushes() -> None:
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
                "Account",
                predicate_algebra.Comparison(
                    "lessThan", predicate_algebra.FieldSubject("Account.id"), 100
                ),
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
                "Balance",
                predicate_algebra.Comparison(
                    "lessThan", predicate_algebra.FieldSubject("Balance.value"), "100.00"
                ),
            ),
        ),
        _BALANCE,
        rows,
    )


def _account_state(key: int, version: int) -> VersionedObjectStateKey:
    return VersionedObjectStateKey(corpus_object_key("Account", ("id", key)), version)


def _balance_state(key: int) -> ObjectStateKey:
    target = _balance_group(_balance_members(key)).mutation.selection.target
    shape = temporal_read.view(_BALANCE).shape(target.identity)
    assert shape is not None
    return object_state_key_from_observation(
        corpus_object_key("Balance", ("id", key)),
        TemporalObservation(predecessor=PredecessorRow(_balance_members(key))),
        shape,
    )


def _account_write(mutation: KeyedMutation, account_id: int, version: int) -> BufferItem:
    row: dict[str, object] = {"id": account_id}
    if mutation == "amend":
        row["balance"] = Decimal("1.00")
    evidence = VersionObservation(observed_version=version)
    return buffered_write(
        _prepared_keyed(KeyedWrite(mutation, "Account", (row,)), _ACCOUNT),
        RetainedObservation(_account_state(account_id, version), evidence, None),
    )


def _balance_update(key: int) -> BufferItem:
    observation = TemporalObservation(predecessor=PredecessorRow(_balance_members(key)))
    return buffered_write(
        _prepared_keyed(
            KeyedWrite("amend", "Balance", ({"id": key, "value": Decimal("2.00")},)), _BALANCE
        ),
        RetainedObservation(_balance_state(key), observation, None),
    )


def _refused_as_claimed(uow: UnitOfWork, item: BufferItem) -> WriteEvidenceError:
    with pytest.raises(WriteEvidenceError) as refusal:
        uow.buffer(item)
    assert refusal.value.code == "write-evidence-already-claimed"
    return refusal.value


def test_buffering_a_group_claims_every_state_it_selected_as_a_keyed_read_would_key_it() -> None:
    simulated = _simulated()

    def body(uow: UnitOfWork) -> None:
        assert uow.buffer(_account_group((1, 7), (2, 3))) is BufferOutcome.BUFFERED
        _refused_as_claimed(uow, _account_write("amend", 1, 7))
        _refused_as_claimed(uow, _account_write("delete", 2, 3))
        # Another state of a selected object is another claim scope.
        assert uow.buffer(_account_write("amend", 2, 7)) is BufferOutcome.BUFFERED

    _run(body, steps=simulated)
    assert sorted(_kinds(simulated)) == ["delete", "delete", "update"]

    def temporal(uow: UnitOfWork) -> None:
        uow.buffer(_balance_group(_balance_members(1), _balance_members(2)))
        _refused_as_claimed(uow, _balance_update(1))
        _refused_as_claimed(uow, _balance_update(2))

    _run(temporal, meta=_BALANCE)


def test_a_late_milestone_edge_failure_withdraws_only_the_admitted_prefix() -> None:
    # The third row's axis start is no instant, so deriving its state key fails
    # after two claims were admitted. Those two are withdrawn, the claim held
    # before the group is untouched, and the group is never buffered.
    simulated = _simulated(_BALANCE)

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

    _run(body, meta=_BALANCE, steps=simulated)
    # The amendment of 9 closes and reopens it; the group terminates 1 and 2.
    assert _kinds(simulated) == ["close", "insert", "close", "close"]
    assert [
        statement.binds[1]
        for statement in simulated.statements
        if statement.sql.startswith("update")
    ] == [9, 1, 2]


def test_a_late_collision_leaves_the_pending_claim_it_met_standing() -> None:
    simulated = _simulated()

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_account_write("amend", 3, 7))
        with pytest.raises(UnitOfWorkError, match="collides with a claim"):
            uow.buffer(_account_group((1, 7), (2, 7), (3, 7), (4, 7)))
        with pytest.raises(UnitOfWorkError, match="collides with a claim"):
            uow.buffer(_account_group((3, 7)))
        for account_id in (1, 2, 4):
            uow.buffer(_account_write("delete", account_id, 7))

    _run(body, steps=simulated)
    assert set(_kinds(simulated)) == {"update", "delete"}
    (update,) = (
        statement for statement in simulated.statements if statement.sql.startswith("update")
    )
    assert update.binds == (Decimal("1.00"), 8, 3, 7)


def test_a_group_selecting_one_state_twice_is_refused_and_leaves_no_claim() -> None:
    simulated = _simulated()

    def body(uow: UnitOfWork) -> None:
        with pytest.raises(UnitOfWorkError, match="incompatible"):
            uow.buffer(_account_group((1, 7), (2, 7), (1, 7)))
        uow.buffer(_account_write("amend", 1, 7))
        uow.buffer(_account_write("amend", 2, 7))

    _run(body, steps=simulated)
    assert set(_kinds(simulated)) == {"update"}


# --------------------------------------------------------------------------- #
# Buffering a keyed write admits the claim its carrier names, or refuses it    #
# and changes nothing.                                                         #
# --------------------------------------------------------------------------- #
_PERSON_META = model_of(PERSON)


def _person_write(
    mutation: KeyedMutation, person_id: int, source: SourceAuthority | None = None
) -> BufferItem:
    """An unversioned Non-Temporal Person write settling against its object."""
    row: dict[str, object] = {"id": person_id}
    if mutation == "amend":
        row["name"] = "Grace"
    prepared = _prepared_keyed(KeyedWrite(mutation, "Person", (row,)), _PERSON_META)
    return buffered_write(
        prepared,
        corpus_object_key("Person", ("id", person_id)),
        source=RecordingSource() if source is None else source,
    )


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


def test_an_object_claimed_write_claims_its_instructions_object() -> None:
    simulated = _simulated(_PERSON_META)

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_person_write("amend", 1))
        uow.buffer(_person_write("delete", 1))
        refusal = _refused_as_claimed(uow, _person_write("amend", 1))
        assert refusal.object_key == corpus_object_key("Person", ("id", 1))
        uow.buffer(_person_write("amend", 2))

    _run(body, steps=simulated, meta=_PERSON_META)
    assert sorted(_kinds(simulated)) == ["delete", "update"]


@dataclass(frozen=True, slots=True)
class _OrderedSource:
    name: str
    spent: list[str]

    def consume(self) -> None:
        self.spent.append(self.name)


def _buffer_composed_person_writes(uow: UnitOfWork, spent: list[str]) -> None:
    # The second amendment of 1 coalesces into the first, the first deletion
    # supersedes their merge, and the second deduplicates into it.
    uow.buffer(_person_write("amend", 1, _OrderedSource("amend", spent)))
    uow.buffer(_person_write("amend", 2, _OrderedSource("other", spent)))
    uow.buffer(_person_write("amend", 1, _OrderedSource("coalesced", spent)))
    uow.buffer(_person_write("delete", 1, _OrderedSource("delete", spent)))
    uow.buffer(_person_write("delete", 1, _OrderedSource("again", spent)))


def test_every_accepted_object_source_is_spent_in_buffering_order_after_the_flush() -> None:
    simulated = _simulated(_PERSON_META)
    spent: list[str] = []
    seen: list[list[str]] = []
    steps = ObservedSteps(simulated, observe=lambda _span: seen.append(list(spent)))

    _run(lambda uow: _buffer_composed_person_writes(uow, spent), steps=steps, meta=_PERSON_META)
    assert sorted(_kinds(simulated)) == ["delete", "update"]
    assert steps.spans > 1
    assert seen == [[]] * steps.spans
    assert spent == ["amend", "other", "coalesced", "delete", "again"]

    failure = RuntimeError("the last unit failed")
    unspent: list[str] = []
    failing = ObservedSteps(_simulated(_PERSON_META), failing=steps.spans - 1, failure=failure)
    with pytest.raises(RuntimeError, match="the last unit failed"):
        _run(
            lambda uow: _buffer_composed_person_writes(uow, unspent),
            steps=failing,
            meta=_PERSON_META,
        )
    assert unspent == []


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
        _refused_as_claimed(uow, _account_write("amend", 1, 7))
        assert uow.buffer(_account_delete(9)) is BufferOutcome.CANCELLED_PENDING_INSERT
        _refused_as_claimed(uow, _account_write("amend", 1, 7))

    _run(body)


class _Abandoned(Exception):
    """Ends a body whose buffer no flush is meant to plan."""


# --------------------------------------------------------------------------- #
# Buffering reports the pending-insert transition it made.                    #
# --------------------------------------------------------------------------- #
def _account_delete(account_id: int) -> PreparedKeyedWrite:
    return _prepared_keyed(KeyedWrite("delete", "Account", ({"id": account_id},)), _ACCOUNT)


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
    predicate = prepare_typed_write(
        PredicateWrite(
            "delete",
            PredicateSelection(
                "Account",
                predicate_algebra.Comparison("eq", predicate_algebra.FieldSubject("Account.id"), 1),
            ),
        ),
        _ACCOUNT,
    )

    def body(uow: UnitOfWork) -> None:
        assert uow.buffer(_account_write("amend", 1, 7)) is BufferOutcome.BUFFERED
        assert uow.buffer(_account_write("delete", 2, 7)) is BufferOutcome.BUFFERED
        assert uow.buffer(readless_write(predicate)) is BufferOutcome.BUFFERED
        assert uow.buffer(_account_group((4, 7))) is BufferOutcome.BUFFERED
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
    state = object_state_key_from_observation(
        corpus_object_key("Balance", ("id", key)),
        observation,
        _balance_shape(),
    )
    return buffered_write(
        _prepared_keyed(
            KeyedWrite("amend", "Balance", ({"id": key, "value": Decimal("2.00")},)), _BALANCE
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


def _balance_terminate_from(key: int, tx_start: object) -> BufferItem:
    members = _balance_members(key, tx_start)
    observation = TemporalObservation(predecessor=PredecessorRow(members))
    state = object_state_key_from_observation(
        corpus_object_key("Balance", ("id", key)), observation, _balance_shape()
    )
    return buffered_write(
        _prepared_keyed(KeyedWrite("terminate", "Balance", ({"id": key},)), _BALANCE),
        RetainedObservation(state, observation, None),
    )


def test_a_row_its_unit_removed_is_no_longer_owned() -> None:
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
    assert _kinds(simulated) == ["insert", "insert", "delete", "delete", "close", "insert"]


def test_a_row_whose_start_is_the_attempts_instant_is_not_owned_without_its_opening() -> None:
    simulated = _simulated(_BALANCE)

    def body(uow: UnitOfWork) -> None:
        uow.buffer(_balance_update_from(1, _FIXED))

    _run(body, meta=_BALANCE, steps=simulated)
    assert _kinds(simulated) == ["close", "insert"]


def test_each_unit_spends_its_evidence_before_the_next_unit_executes() -> None:
    first = _account_write("amend", 1, 7)
    second = _account_write("amend", 2, 3)
    assert isinstance(first, ObservedKeyedWrite) and isinstance(second, ObservedKeyedWrite)
    retained = (first.retained_observation, second.retained_observation)
    seen: list[tuple[bool, ...]] = []

    def spent() -> tuple[bool, ...]:
        return tuple(observation.consumed for observation in retained)

    def body(uow: UnitOfWork) -> None:
        uow.buffer(first)
        uow.buffer(second)

    _run(body, steps=ObservedSteps(_simulated(), observe=lambda _span: seen.append(spent())))
    assert [*seen, spent()] == [(False, False), (True, False), (True, True)]


def test_a_caught_execution_failure_still_dooms_the_attempt() -> None:
    failure = RuntimeError("the statement failed")
    claimed = _account_write("amend", 1, 7)
    assert isinstance(claimed, ObservedKeyedWrite)
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
    assert not claimed.retained_observation.consumed


def test_a_planning_refusal_leaves_the_attempt_usable() -> None:
    bare_close = _prepared_keyed(
        KeyedWrite("amend", "Balance", ({"id": 1, "value": Decimal("2.00")},)), _BALANCE
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
    state = object_state_key_from_observation(
        corpus_object_key("Position", ("id", 1)), observation, shape
    )
    simulated = _simulated(_POSITION)
    coverage = HeldRows(_POSITION)

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

    _run(body, meta=_POSITION, steps=simulated, rows=coverage)
    # The range read its coverage and bound to nothing to execute.
    assert _kinds(simulated) == ["insert"]
    assert [type(request) for request in coverage.requests] == [CoverageReadRequest]


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
    state = object_state_key_from_observation(key, observation, shape)
    simulated = _simulated(_BALANCE)

    def body(uow: UnitOfWork) -> None:
        read_at = uow.freshness
        claim = uow.retain(RetainedObservation(state, observation, None))
        uow.buffer(
            buffered_write(
                _prepared_keyed(
                    KeyedWrite("amend", "Balance", ({"id": 1, "value": Decimal(value)},)),
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
        steps=simulated,
        settings=TransactionSettings(counts_unchanged_rows=True),
    )
    assert _kinds(simulated) == (["guard"] if kept else ["close", "insert"])


def _account_amend(account_id: int, claim: RetainedObservation) -> BufferItem:
    row = {"id": account_id, "balance": Decimal("1.00")}
    return buffered_write(_prepared_keyed(KeyedWrite("amend", "Account", (row,)), _ACCOUNT), claim)


def _account_claim(account_id: int, version: int) -> RetainedObservation:
    return RetainedObservation(
        _account_state(account_id, version), VersionObservation(observed_version=version), None
    )


def test_each_unit_names_its_sources_state_itself() -> None:
    first, second = _account_claim(1, 7), _account_claim(2, 3)
    plan = build_write_planner(_ACCOUNT).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=TransactionInstant(FixedClock(_FIXED)),
            concurrency="optimistic",
            buffered_writes=compose_writes(
                _ACCOUNT, [_account_amend(1, first), _account_amend(2, second)]
            ),
        )
    )
    # Nothing infers a unit's changed state from a step.
    assert [tuple(unit.changed) for unit in plan.units] == [(first.key,), (second.key,)]


def test_a_failed_unit_publishes_nothing_while_the_unit_before_it_stays_published() -> None:
    failure = RuntimeError("the second unit failed")
    claims: list[RetainedObservation] = []

    def body(uow: UnitOfWork) -> None:
        for account_id, version in ((1, 7), (2, 3)):
            claim = uow.retain(_account_claim(account_id, version))
            claims.append(claim)
            uow.buffer(_account_amend(account_id, claim))
        with pytest.raises(RuntimeError, match="the second unit failed"):
            uow.read(lambda: None)

    with pytest.raises(RollbackOnlyError):
        _run(body, steps=ObservedSteps(_simulated(), failing=1, failure=failure))
    first, second = claims
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
    state = object_state_key_from_observation(key, observation, _balance_shape())
    simulated = _simulated(_BALANCE)

    def body(uow: UnitOfWork) -> None:
        claim = uow.retain(RetainedObservation(state, observation, uow.participation))
        uow.buffer(
            buffered_write(
                _prepared_keyed(
                    KeyedWrite("amend", "Balance", ({"id": 1, "value": Decimal("100.00")},)),
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
        steps=simulated,
        settings=TransactionSettings(concurrency="locking"),
    )
    assert simulated.statements == ()


def test_a_row_a_unit_removes_and_reopens_at_one_address_stays_owned() -> None:
    # Removals are retired before openings register, so the row a unit
    # reopened at the address it removed is still the attempt's to revise.
    key = corpus_object_key("Position", ("id", 1))
    endpoint = OwnedEndpoint(key.entity, (1,), (Finite(instant=_DEC), PLANNED_INFINITY))
    targets = _TargetWriteState()
    targets.complete((), Openings(fresh=(endpoint,)))
    targets.complete((endpoint,), Openings(fresh=(endpoint,)))
    assert targets.owns(endpoint)


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


def _position_target(start: dt.datetime, until: dt.datetime) -> PreparedTargetWrite:
    prepared = prepare_wire_write(
        TargetWrite(
            "amendUntil",
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


def _observed_amendment(claim: RetainedObservation) -> BufferItem:
    observed = prepare_wire_write(
        KeyedWrite(
            "amendUntil",
            "WherePosition",
            ({"id": 1, "acctNum": "O"},),
            valid_from=_FEB,
            until=_APR,
        ),
        _BARRIERED,
    )
    assert isinstance(observed, PreparedKeyedWrite)
    return buffered_write(observed, claim)


def test_a_unit_a_barrier_kept_back_binds_on_what_the_earlier_unit_spent_and_proved() -> None:
    original = TemporalObservation(predecessor=_position_row(_JAN, _T0))
    key = corpus_object_key("WherePosition", ("id", 1))
    shape = temporal_read.view(_BARRIERED).shape(key.entity)
    assert shape is not None
    state = object_state_key_from_observation(key, original, shape)
    held: list[RetainedObservation] = []
    coverage = HeldRows(_BARRIERED)
    simulated = _simulated(_BARRIERED)
    seen: list[tuple[bool, bool, int]] = []

    def reading() -> None:
        (claim,) = held
        seen.append((claim.consumed, claim.invalidated, len(simulated.statements)))

    later: list[str] = []

    def body(uow: UnitOfWork) -> None:
        claim = uow.retain(RetainedObservation(state, original, uow.participation))
        held.append(claim)
        uow.buffer(_observed_amendment(claim))
        uow.buffer_predicate(_shell_barrier())
        uow.buffer_target(_position_target(_JUN, _AUG))
        coverage.rows = [_position_row(_APR, _FIXED)]
        uow.read(lambda: None)
        later.extend(statement_kinds(simulated.statements[seen[0][2] :]))
        # A later flush carries no proof: the original's token is stale.
        coverage.rows = [_position_row(_AUG, _FIXED)]
        uow.buffer_target(_position_target(_SEP, _OCT))

    with pytest.raises(WritePreconditionError):
        _run(body, meta=_BARRIERED, steps=simulated, rows=_Watched(coverage, reading))
    # The earlier unit spent the shared source and invalidated its state
    # before the later one bound, which then ran no close of its own.
    assert seen[0][:2] == (True, True)
    assert later and "close" not in later
    _assert_optimistic_targets_read_nothing(coverage)


def test_an_objects_proofs_serve_every_unit_following_it_in_the_flush() -> None:
    original = TemporalObservation(predecessor=_position_row(_JAN, _T0))
    key = corpus_object_key("WherePosition", ("id", 1))
    shape = temporal_read.view(_BARRIERED).shape(key.entity)
    assert shape is not None
    state = object_state_key_from_observation(key, original, shape)
    held = HeldRows(_BARRIERED)
    answers = iter([[_position_row(_APR, _FIXED)], [_position_row(_AUG, _FIXED)]])
    reached: list[int] = []
    simulated = _simulated(_BARRIERED)

    def reading() -> None:
        reached.append(len(simulated.statements))
        held.rows = next(answers)

    def body(uow: UnitOfWork) -> None:
        claim = uow.retain(RetainedObservation(state, original, uow.participation))
        uow.buffer(_observed_amendment(claim))
        for window in ((_JUN, _AUG), (_SEP, _OCT)):
            uow.buffer_predicate(_shell_barrier())
            uow.buffer_target(_position_target(*window))
        uow.read(lambda: None)

    _run(body, meta=_BARRIERED, steps=simulated, rows=_Watched(held, reading))
    # Each unit a barrier kept back read its own coverage and bound on what
    # the earlier unit proved; the last ran no close of its own.
    assert len(reached) == 2
    assert "close" not in statement_kinds(simulated.statements[reached[1] :])
    _assert_optimistic_targets_read_nothing(held)


def _account_target(version: int) -> PreparedTargetWrite:
    prepared = prepare_wire_write(
        TargetWrite("amend", "Account", {"id": 1, "balance": "6.00"}, if_version=version),
        _ACCOUNT,
    )
    assert isinstance(prepared, PreparedTargetWrite)
    return prepared


@pytest.mark.parametrize(
    ("meta", "target", "rows"),
    [
        pytest.param(_ACCOUNT, lambda: _account_target(3), (), id="non-temporal"),
        pytest.param(
            _BARRIERED,
            lambda: _position_target(_JUN, _AUG),
            (_position_row(_JAN, _T0),),
            id="temporal",
        ),
    ],
)
def test_a_caller_addressed_carrier_buffers_as_its_admission_appends_it(
    meta: Metamodel,
    target: Callable[[], PreparedTargetWrite],
    rows: tuple[PredecessorRow, ...],
) -> None:
    # Its caller's condition is the whole of what it is: buffering it judges
    # none of that and reads nothing, and what the flush makes of it is what
    # the admission that does judge it buffers.
    def flushed(
        buffering: Callable[[UnitOfWork, PreparedTargetWrite], object],
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


def test_a_locking_admission_still_reads_and_judges_the_row_its_carrier_does_not() -> None:
    stored = PredecessorRow(
        members={"id": 1, "owner": "Ada", "balance": Decimal("5.00"), "version": 2}
    )
    held = HeldRows(_ACCOUNT, (stored,))
    locking = TransactionSettings(concurrency="locking")
    with pytest.raises(WritePreconditionError):
        _run(lambda uow: uow.buffer_target(_account_target(3)), settings=locking, rows=held)
    assert [type(request) for request in held.requests] == [TargetReadRequest]
    held.requests.clear()
    simulated = _simulated()
    _run(
        lambda uow: uow.buffer(target_write(_account_target(3), inheritance.view(_ACCOUNT))),
        settings=locking,
        steps=simulated,
        rows=held,
    )
    assert held.requests == []
    assert _kinds(simulated) == ["update"]


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
    # Each destruction observed the rectangle its window starts in, so writes
    # over disjoint windows claim distinct states and compose.
    observation = TemporalObservation(predecessor=_position_row(start, _T0))
    state = object_state_key_from_observation(
        corpus_object_key("WherePosition", ("id", 1)), observation, _barriered_shape()
    )
    return ObservedKeyedWrite(prepared, RetainedObservation(state, observation, None))


def _shell_barrier() -> PreparedPredicateWrite:
    barrier = prepare_wire_write(
        PredicateWrite(
            "amend",
            PredicateSelection(
                "ShellTag",
                predicate_algebra.Comparison(
                    "eq", predicate_algebra.FieldSubject("ShellTag.id"), 1
                ),
            ),
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


def _opening_geometry(plan: WritePlan) -> set[tuple[object, object, object]]:
    """Each row a plan's inserts open, by Valid Time and value."""
    rows: set[tuple[object, object, object]] = set()
    for step in plan.steps:
        if isinstance(step, PlannedInsert):
            (entry,) = step.entries
            cells = {identity.name: value for identity, value in entry.row.attributes.items()}
            rows.add((cells["validStart"], cells["validEnd"], cells["value"]))
    return rows


def test_a_pending_opening_settles_as_one_unit_of_the_new_lineages_its_edits_leave() -> None:
    insert = _prepared_keyed(
        KeyedWrite(
            "insert",
            "WherePosition",
            ({"id": 1, "acctNum": "A", "value": Decimal("1.00")},),
            valid_from=_FEB,
        ),
        _BARRIERED,
    )
    edit = _prepared_keyed(
        KeyedWrite(
            "amendUntil", "WherePosition", ({"id": 1, "value": Decimal("2.00")},), _FEB, _APR
        ),
        _BARRIERED,
    )
    destroy = _prepared_keyed(
        KeyedWrite("terminateUntil", "WherePosition", ({"id": 1},), _JUN, _AUG),
        _BARRIERED,
    )
    plan = build_write_planner(_BARRIERED).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=TransactionInstant(FixedClock(_FIXED)),
            concurrency="optimistic",
            buffered_writes=compose_writes(_BARRIERED, [insert, edit, destroy]),
        )
    )
    # No predecessor is fabricated for the insert: every surviving part of its
    # own window opens as a new lineage, together, as one unit.
    (unit,) = plan.units
    assert {type(step) for step in plan.steps} == {PlannedInsert}
    assert {step.entries[0].origin for step in plan.steps} == {NEW_LINEAGE}  # type: ignore[union-attr]
    assert _opening_geometry(plan) == {
        (_FEB, _APR, Decimal("2.00")),
        (_APR, _JUN, Decimal("1.00")),
        (_AUG, INFINITY, Decimal("1.00")),
    }
    assert tuple(unit.opened.continued) == (
        _position_endpoint(_APR),
        _position_endpoint(_JUN),
        _position_endpoint(None),
    )
    assert (tuple(unit.changed), tuple(unit.opened.fresh)) == ((), ())


def _position_endpoint(end: dt.datetime | None) -> OwnedEndpoint:
    entity = corpus_object_key("WherePosition", ("id", 1)).entity
    if end is None:
        return OwnedEndpoint(entity, (1,), OPEN_BITEMPORAL_ENDS)
    return OwnedEndpoint(entity, (1,), (Finite(instant=end), PLANNED_INFINITY))


def test_a_stored_insertions_removal_window_is_kept_until_what_it_derives_from_changes() -> None:
    key = corpus_object_key("WherePosition", ("id", 1))
    targets = _TargetWriteState()
    targets.open_insert(key, None, TimeInterval(_FEB, INFINITY))
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
    targets.open_insert(key, None, TimeInterval(_APR, INFINITY))
    assert targets.removal_window(record) is narrowed
    targets.end_flush(())
    moved = targets.removal_window(record)
    assert moved == TimeInterval(_APR, _JUN)
    targets.cancel_insert(key)
    assert targets.removal_window(record) is moved


def test_a_proven_originals_descendants_are_exactly_those_overlapping_the_window() -> None:
    key = corpus_object_key("WherePosition", ("id", 1))
    original = object_state_key_from_observation(
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
        (),
        NO_OPENINGS,
        (
            Derivation(
                original,
                TimeInterval(_JAN, INFINITY),
                None,
                tuple(DerivedRow(endpoint, coverage, coverage) for endpoint, coverage in rows),
            ),
        ),
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


_SECOND_START = dt.datetime(2023, 12, 15, tzinfo=dt.UTC)


def _original(start: dt.datetime, tx_start: dt.datetime) -> ObjectStateKey:
    key = corpus_object_key("WherePosition", ("id", 1))
    return object_state_key_from_observation(
        key, TemporalObservation(predecessor=_position_row(start, tx_start)), _barriered_shape()
    )


def _merged_derivations(
    first: ObjectStateKey, second: ObjectStateKey, merged: OwnedEndpoint
) -> tuple[Derivation, Derivation]:
    """P1 over [January, June) and P2 over [June, infinity), both amended from
    April through August into one row over [April, August)."""
    whole = TimeInterval(_APR, _AUG)
    return (
        Derivation(
            first,
            TimeInterval(_JAN, _JUN),
            None,
            (
                DerivedRow(
                    _position_endpoint(_APR), TimeInterval(_JAN, _APR), TimeInterval(_JAN, _APR)
                ),
                DerivedRow(merged, whole, TimeInterval(_APR, _JUN)),
            ),
        ),
        Derivation(
            second,
            TimeInterval(_JUN, INFINITY),
            None,
            (
                DerivedRow(merged, whole, TimeInterval(_JUN, _AUG)),
                DerivedRow(
                    _position_endpoint(None),
                    TimeInterval(_AUG, INFINITY),
                    TimeInterval(_AUG, INFINITY),
                ),
            ),
        ),
    )


def test_a_merged_row_descends_from_each_original_over_its_own_part_only() -> None:
    first, second = _original(_JAN, _T0), _original(_JUN, _SECOND_START)
    merged = _position_endpoint(_AUG)
    targets = _TargetWriteState()
    targets.complete(
        (),
        Openings(fresh=(_position_endpoint(_APR), merged, _position_endpoint(None))),
        _merged_derivations(first, second, merged),
    )
    descent = targets.descent(merged)
    assert descent is not None
    assert descent.valid_time_coverage == TimeInterval(_APR, _AUG)
    assert descent.contributions == (
        (first, TimeInterval(_APR, _JUN)),
        (second, TimeInterval(_JUN, _AUG)),
    )
    assert (descent.original_at(_FEB), descent.original_at(_APR)) == (None, first)
    assert descent.original_at(dt.datetime(2024, 7, 1, tzinfo=dt.UTC)) == second
    # Only the original whose part a window overlaps reaches the merged row.
    assert [endpoint for endpoint, _ in targets.descendants(first, TimeInterval(_JUN, _SEP))] == []
    assert [endpoint for endpoint, _ in targets.descendants(second, TimeInterval(_FEB, _JUN))] == []
    assert [endpoint for endpoint, _ in targets.descendants(second, TimeInterval(_JUN, _SEP))] == [
        merged,
        _position_endpoint(None),
    ]


def test_a_row_derived_from_a_merged_row_inherits_each_original_by_intersection() -> None:
    first, second = _original(_JAN, _T0), _original(_JUN, _SECOND_START)
    merged = _position_endpoint(_AUG)
    targets = _TargetWriteState()
    targets.complete(
        (),
        Openings(fresh=(_position_endpoint(_APR), merged, _position_endpoint(None))),
        _merged_derivations(first, second, merged),
    )
    # A later unit splits the merged row at May: its head [April, May) came
    # from the first original alone, its tail [May, August) from both.
    may = dt.datetime(2024, 5, 1, tzinfo=dt.UTC)
    revised = _original(_APR, _FIXED)
    head = _position_endpoint(may)
    targets.complete(
        (),
        Openings(fresh=(head,)),
        (
            Derivation(
                revised,
                TimeInterval(_APR, _AUG),
                merged,
                (
                    DerivedRow(head, TimeInterval(_APR, may), TimeInterval(_APR, may)),
                    DerivedRow(merged, TimeInterval(may, _AUG), TimeInterval(may, _AUG)),
                ),
            ),
        ),
    )
    split_head = targets.descent(head)
    tail = targets.descent(merged)
    assert split_head is not None and tail is not None
    assert split_head.contributions == ((first, TimeInterval(_APR, may)),)
    assert tail.contributions == (
        (first, TimeInterval(may, _JUN)),
        (second, TimeInterval(_JUN, _AUG)),
    )
    # The revised row is no proven original of its own.
    assert targets.proven(revised) is None


def test_an_insertion_keeps_only_its_own_part_of_a_merged_row_and_ends_with_it() -> None:
    key = corpus_object_key("WherePosition", ("id", 1))
    targets = _TargetWriteState()
    identity = targets.open_insert(key, None, TimeInterval(_JAN, _APR))
    targets.end_flush(())
    record = targets.record(key)
    assert record is not None
    merged = _position_endpoint(_JUN)
    targets.complete((), Openings(shared=((merged, (TimeInterval(_JAN, _APR),)),)))
    assert targets.continues_insertion(merged)
    assert targets.insertion_coverage(merged, TimeInterval(_JAN, _JUN)) == (
        TimeInterval(_JAN, _APR),
    )
    # Its removal window ends where its own part does, not the merged row.
    assert targets.removal_window(record) == TimeInterval(_JAN, _APR)
    assert record.identity is identity
    # Revised in place to [April, June), the row holds none of its part.
    targets.complete((), Openings(fresh=(merged,)))
    assert not targets.continues_insertion(merged)
    assert targets.owns(merged)
    assert record.identity is None


def test_a_row_still_holding_part_of_an_insertion_keeps_it_standing() -> None:
    key = corpus_object_key("WherePosition", ("id", 1))
    targets = _TargetWriteState()
    identity = targets.open_insert(key, None, TimeInterval(_JAN, _APR))
    targets.end_flush(())
    record = targets.record(key)
    assert record is not None
    merged = _position_endpoint(_JUN)
    targets.complete((), Openings(shared=((merged, (TimeInterval(_JAN, _APR),)),)))
    narrowed = (TimeInterval(_FEB, _APR),)
    targets.complete((), Openings(shared=((merged, narrowed),)))
    assert targets.insertion_coverage(merged, TimeInterval(_FEB, _JUN)) == narrowed
    assert record.identity is identity
    # Whole again once a successor lies inside the part it contributed.
    head = _position_endpoint(_FEB)
    targets.complete((merged,), Openings(continued=(head,)))
    assert targets.insertion_coverage(head, TimeInterval(_JAN, _FEB)) == (TimeInterval(_JAN, _FEB),)
    assert record.identity is identity


def test_an_insertions_part_running_on_without_end_leaves_its_removal_window_open() -> None:
    key = corpus_object_key("WherePosition", ("id", 1))
    targets = _TargetWriteState()
    targets.open_insert(key, None, TimeInterval(_JAN, _APR))
    targets.end_flush(())
    record = targets.record(key)
    assert record is not None
    merged = _position_endpoint(None)
    untagged = _position_endpoint(_JAN)
    targets.complete(
        (), Openings(fresh=(untagged,), shared=((merged, (TimeInterval(_APR, INFINITY),)),))
    )
    assert targets.insertion_coverage(untagged, TimeInterval(_JAN, _FEB)) == ()
    assert targets.removal_window(record) == TimeInterval(_JAN, INFINITY)


def test_a_row_named_again_after_its_insertion_ended_is_no_longer_tagged() -> None:
    key = corpus_object_key("WherePosition", ("id", 1))
    targets = _TargetWriteState()
    targets.open_insert(key, None, TimeInterval(_JAN, _APR))
    targets.end_flush(())
    row = _position_endpoint(_APR)
    targets.complete((), Openings(continued=(row,)))
    targets.cancel_insert(key)
    targets.complete((), Openings(continued=(row,)))
    assert not targets.continues_insertion(row)
    assert targets.owns(row)


def test_a_row_merged_from_one_originals_adjacent_parts_names_it_once() -> None:
    first = _original(_JAN, _T0)
    targets = _TargetWriteState()
    left, right = _position_endpoint(_APR), _position_endpoint(_JUN)
    targets.complete(
        (),
        Openings(fresh=(left, right)),
        (
            Derivation(
                first,
                TimeInterval(_JAN, _JUN),
                None,
                (
                    DerivedRow(left, TimeInterval(_JAN, _APR), TimeInterval(_JAN, _APR)),
                    DerivedRow(right, TimeInterval(_APR, _JUN), TimeInterval(_APR, _JUN)),
                ),
            ),
        ),
    )
    # A later unit merges both rows the original left, revising the second
    # into [January, June); each part inherits the original over its own
    # Valid Time, and the two parts are one.
    revised_left, revised_right = _original(_JAN, _FIXED), _original(_APR, _FIXED)
    merged = TimeInterval(_JAN, _JUN)
    targets.complete(
        (left,),
        NO_OPENINGS,
        (
            Derivation(
                revised_left,
                TimeInterval(_JAN, _APR),
                left,
                (DerivedRow(right, merged, TimeInterval(_JAN, _APR)),),
            ),
            Derivation(
                revised_right,
                TimeInterval(_APR, _JUN),
                right,
                (DerivedRow(right, merged, TimeInterval(_APR, _JUN)),),
            ),
        ),
    )
    descent = targets.descent(right)
    assert descent is not None
    assert descent.contributions == ((first, merged),)


def test_a_part_of_a_row_no_proven_original_held_descends_from_none() -> None:
    first = _original(_JAN, _T0)
    targets = _TargetWriteState()
    merged = _position_endpoint(_JUN)
    # The original contributed [January, April) of the merged row; a gap
    # opened the rest.
    targets.complete(
        (),
        Openings(fresh=(merged,)),
        (
            Derivation(
                first,
                TimeInterval(_JAN, _APR),
                None,
                (DerivedRow(merged, TimeInterval(_JAN, _JUN), TimeInterval(_JAN, _APR)),),
            ),
        ),
    )
    tail = _position_endpoint(_AUG)
    targets.complete(
        (),
        Openings(fresh=(tail,)),
        (
            Derivation(
                _original(_JAN, _FIXED),
                TimeInterval(_JAN, _JUN),
                merged,
                (DerivedRow(tail, TimeInterval(_APR, _AUG), TimeInterval(_APR, _JUN)),),
            ),
        ),
    )
    assert targets.descent(tail) is None


def test_an_original_that_left_no_row_stays_proven_until_its_object_concludes() -> None:
    first = _original(_JAN, _T0)
    targets = _TargetWriteState()
    # Terminated over its whole coverage, the original contributed no row.
    targets.complete((), NO_OPENINGS, (Derivation(first, TimeInterval(_JAN, _APR), None, ()),))
    assert targets.proven(first) is not None
    assert list(targets.descendants(first, TimeInterval(_JAN, INFINITY))) == []
    targets.complete((), NO_OPENINGS, concludes=first.object)
    assert targets.proven(first) is None
