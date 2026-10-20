from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, replace
from types import TracebackType
from typing import Literal, Protocol, cast
from weakref import WeakValueDictionary

from parallax.core import inheritance, temporal_read
from parallax.core._execution._unit_work.acquisition import (
    AcquireRows,
    TargetReadRequest,
    consume_target,
)
from parallax.core._execution._unit_work.admission import (
    WRITE_EVIDENCE_CODES,
    BufferOutcome,
    NoInsertionAuthority,
    UnitOfWorkError,
    WriteAdmission,
    WriteEvidenceError,
    WriteEvidenceErrorCode,
)
from parallax.core._execution._unit_work.claims import SettledEvidence, claimed_object
from parallax.core._execution._unit_work.clock import Clock, TransactionInstant
from parallax.core._execution._unit_work.effects import (
    CardinalityCorruptionError,
    WritePreconditionError,
)
from parallax.core._execution._unit_work.instructions import (
    AMEND_MUTATIONS,
    ExpectedTxStart,
    KeyedMutation,
    PreparedPredicateWrite,
    PreparedTargetWrite,
)
from parallax.core._execution._unit_work.retain import (
    InsertionIdentity,
    KeyedWriteRefusalAdvice,
    ParticipationToken,
    ReadEvidence,
    RetainedObservation,
    RetainedTargetState,
)
from parallax.core._execution._unit_work.strategy import (
    ActorIdentity,
    Concurrency,
    EvidencePolicyLookup,
)
from parallax.core._execution._unit_work.write_items import (
    BufferItem,
    TargetKeyedWrite,
    readless_write,
    target_write,
)
from parallax.core._execution._unit_work.write_planner import WritePlanner, WritePlanningRequest
from parallax.core._execution._unit_work.write_runner import ExecuteWriteSteps, run_write_plan
from parallax.core.base import normalize_instant
from parallax.core.inheritance import InheritanceEntityView
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.temporal_read import (
    Bitemporal,
    Edge,
    TimeInterval,
    TransactionTimeOnly,
    milestone_edge,
)
from parallax.core.write_plan.keys import (
    ObjectKey,
    ObjectStateKey,
    TemporalObjectStateKey,
    VersionedObjectStateKey,
)
from parallax.core.write_plan.observe import PredecessorRow
from parallax.core.write_plan.plan import (
    ExecutionUnit,
    UnitEffects,
)
from parallax.core.write_plan.steps import KeyTarget

__all__ = [
    "WRITE_EVIDENCE_CODES",
    "AttemptLifetime",
    "BufferOutcome",
    "Concurrency",
    "OpenWriteBatch",
    "RollbackOnlyError",
    "StoredTarget",
    "TransactionSettings",
    "UnitOfWork",
    "UnitOfWorkError",
    "WriteBatchReason",
    "WriteEvidenceError",
    "WriteEvidenceErrorCode",
]

type WriteBatchReason = Literal["read_dependency", "pre_commit"]
"""The CLOSED set of reasons a unit of work flushes its buffer.

``read_dependency`` is the batch :meth:`UnitOfWork.read` forces out so a
dependent read observes it; ``pre_commit`` is the boundary-owned final batch
the transaction attempt flushes once its callback has returned. There
is no size-based, periodic, or caller-invoked third trigger, which is what lets
an observer state which of the two produced a batch instead of guessing from
position.

The second trigger is named for WHEN it runs rather than for what it does,
because "finalization" already names the planner stage every batch of either
trigger goes through.
"""


class WriteBatchScope(Protocol):
    """The composition-layer scope one flush runs inside.

    Left however the flush leaves — a planning refusal, a failed statement, a
    shortfall the enforcer raised, or success — so a composition layer that
    observes the transaction can never be told a batch began and not told how it
    ended.
    """

    def __enter__(self) -> object: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None: ...


class OpenWriteBatch(Protocol):
    """The composition-layer opener a flush announces itself to.

    Called once per flush that has something to flush, BEFORE the buffered
    writes are planned and therefore before any statement exists, and the scope
    it answers spans planning as well as execution. A flush that fails in
    planning is therefore inside the scope and never executes a step, which
    is the whole distinction this exists to make available: an observer can tell
    a batch that failed before it ran anything from work that is not a batch at
    all. Optional, because the shell itself needs nothing from it.
    """

    def __call__(self, trigger: WriteBatchReason, /) -> WriteBatchScope: ...


class AttemptLifetime(Protocol):
    """The lifetime of the transaction attempt a unit of work coordinates.

    The attempt owns it; the unit of work only asks it to admit work, which it
    refuses once the attempt ended or became rollback-only, and dooms it when a
    flush fails while executing.
    """

    def ensure_open(self) -> None: ...

    def doom(self, cause: BaseException, /) -> None: ...


@dataclass(frozen=True, slots=True)
class StoredTarget:
    """What a target acquisition found of the stored state a caller-addressed
    write starts from: its version, where its family has one, or its current
    Transaction-Time start, where its family is temporal."""

    version: int | None = None
    tx_start: object | None = None


class EscapedTransactionError(UnitOfWorkError):
    """A transaction reference was used after its attempt ended."""


class RollbackOnlyError(UnitOfWorkError):
    """A doomed (rollback-only) transaction refused work, a join, or commit.

    Raised when further work, a joining invocation, or the outermost attempt's
    commit reaches a transaction a failure doomed, carrying the original failure
    as its cause (``__cause__``), so its retriability classification survives
    for the outermost retry loop.
    """


@dataclass(frozen=True, slots=True)
class TransactionSettings:
    """A unit of work's fixed Concurrency Preference, and what its database's
    write counts report.

    The default is `optimistic` (`m-unit-work` "Strategy selection"): a
    preference, not a uniform strategy — each Entity's own Optimistic Lock Facet
    decides whether it yields Optimistic or the mandatory Locking fallback
    (`m-opt-lock`). ``counts_unchanged_rows`` is the connection's dialect fact
    every flush plans with
    (:class:`~parallax.core._execution._unit_work.write_planner.WritePlanningRequest`).
    """

    concurrency: Concurrency = "optimistic"
    counts_unchanged_rows: bool = False


class UnitOfWork:
    """The buffering, observing, flushing coordinator of one writable
    transaction attempt's work (m-unit-work).

    It is not the transaction: the attempt owns the native transaction and its
    lifetime, and hands this the lifetime to consult and doom rather than a
    state of its own. The attempt drives it with :meth:`buffer`,
    :meth:`buffer_predicate`, :meth:`buffer_target`, :meth:`retain`, and
    :meth:`read`, asking :meth:`resolve_read_evidence` what a keyed write's
    source licenses here, flushes it once more before commit, and has it
    :meth:`discard` its state when the attempt does not commit.

    Every row a write reads — a caller-addressed target's starting state, a
    deferred range's coverage — is read through ``acquire_rows`` and consumed
    into evidence while the read's resources are live.
    """

    __slots__ = (
        "_actor_identity",
        "_admission",
        "_changed",
        "_evidence_policy_for",
        "_freshness",
        "_lifetime",
        "_observations",
        "_participation",
        "_planner",
        "_transaction_instant",
        "acquire_rows",
        "clock",
        "execute_write_steps",
        "meta",
        "settings",
        "write_batch_opening",
    )

    def __init__(
        self,
        *,
        settings: TransactionSettings,
        lifetime: AttemptLifetime,
        clock: Clock,
        meta: Metamodel,
        execute_write_steps: ExecuteWriteSteps,
        acquire_rows: AcquireRows,
        planner: WritePlanner,
        actor_identity: ActorIdentity,
        evidence_policy_for: EvidencePolicyLookup,
        write_batch_opening: OpenWriteBatch | None = None,
    ) -> None:
        self.settings = settings
        self._lifetime = lifetime
        self.clock = clock
        self.meta = meta
        self.execute_write_steps = execute_write_steps
        self.acquire_rows = acquire_rows
        self.write_batch_opening = write_batch_opening
        # The injected Write Planner (`m-unit-work`'s single finalization
        # authority) — constructed once per accepted Metamodel by the
        # execution's model preparation (`parallax.core.execution.prepare_model`),
        # which alone may wire the optional policy modules the planner reaches
        # only through its strategy ports. Production and the conformance
        # engine both drive writes through this SAME shell.
        self._planner = planner
        # The Actor Identity execution orchestration supplies for every flush
        # this attempt plans. A forced flush reuses it unchanged; a retry attempt
        # receives its own new `UnitOfWork` and therefore its own copy.
        self._actor_identity = actor_identity
        # The connected model's write-evidence policy, bound once per accepted
        # model by model preparation, which alone may reach `m-opt-lock`.
        self._evidence_policy_for = evidence_policy_for
        # The accepted writes, composed as each is admitted, each carrying the
        # claims its verbs resolved for it — the strong reference that keeps a
        # write's evidence alive after its source value is released, and what a
        # successful flush spends through — beside this attempt's admitted
        # insertions and the current temporal rows it opened.
        self._admission = WriteAdmission(meta, inserted_version=planner.inserted_version)
        # This index is not an owner: a retained observation lives as
        # long as some source value or buffered write reaches it, and this entry
        # disappears with the last of them (`m-unit-work` "Observation lifetime").
        # What the index is for is recognizing a state this transaction has
        # already seen, so a reread of one state answers the evidence the earlier
        # read's values already carry rather than a second copy of it.
        self._observations: WeakValueDictionary[ObjectStateKey, RetainedObservation] = (
            WeakValueDictionary()
        )
        # How many execution units have changed an observed state so far, and
        # the count at which each changed state last changed. A read captures
        # the count when it runs, so evidence it builds later, from rows it
        # already holds, is known to predate any change completed in between.
        self._freshness = 0
        self._changed: dict[ObjectStateKey, int] = {}
        # This scope's participation identity: what a read of THIS unit of work
        # stamps on the values it produces, and what a keyed write tests its
        # source against.
        self._participation = ParticipationToken()
        # One attempt, one lazy instant: constructing it reads no clock, and
        # every flush this scope plans carries the SAME holder, so all
        # timestamp-requiring work in the attempt shares one captured value
        # while work that needs none never captures at all.
        self._transaction_instant = TransactionInstant(clock)

    @property
    def participation(self) -> ParticipationToken:
        """This scope's participation identity — what its own reads stamp on the
        values they produce, and what a keyed write proves its source against."""
        self._ensure_open()
        return self._participation

    def buffer(
        self, item: BufferItem, *, insertion_advice: KeyedWriteRefusalAdvice | None = None
    ) -> BufferOutcome:
        """Admit ``item`` under the authority it carries and buffer it for flush
        at the unit-of-work boundary — all of it, or nothing
        (:meth:`~parallax.core._execution._unit_work.admission.WriteAdmission.admit`).

        The claim is read off the carrier itself
        (:func:`~parallax.core._execution._unit_work.write_items.buffered_write`): a
        retained observation claims the state it observed, and an
        object-claimed write claims its instruction's object (`m-unit-work`
        "Observed-State Coalescing"). An insert and a bare instruction claim
        nothing. An arriving keyed intent the held claim cannot absorb raises
        :class:`WriteEvidenceError` (``write-evidence-already-claimed``), and
        the pending writes, their claims, and the pending inserts are left as
        they were.

        A carrier built from a read's retained observation brings it along,
        so the buffer is what keeps a write's evidence alive once the caller
        releases the source value it came from, and what a successful flush
        spends it through.

        A caller-addressed carrier
        (:class:`~parallax.core._execution._unit_work.write_items.TargetKeyedWrite`)
        is admitted as :meth:`buffer_target` describes, its caller's revision
        confirmed under this attempt's concurrency strategy.

        An insert admits an insertion of the object it opens and issues that
        insertion's identity (:meth:`insertion_identity`), and retains
        ``insertion_advice`` for a repeat of it (:meth:`insertion_advice`).
        Where an earlier insertion of the object is stored and a pending write
        removes all of it, the insert executes after that removal. A write an
        insertion authorized
        (:class:`~parallax.core._execution._unit_work.write_items.InsertionKeyedWrite`) is
        admitted only while that authority stands, and a write leaving nothing
        of what a still-unflushed insertion opened ends it.

        The outcome reports the pending-insert transition buffering made: a
        destructive write that leaves nothing of an object's still-unflushed
        insert, and reaches no stored coverage past it, cancels that pair —
        recognized when the pair is complete rather than when it is planned.
        """
        self._ensure_open()
        return self._admission.admit(
            item, confirm_target=self._confirm_target, insertion_advice=insertion_advice
        )

    def buffer_predicate(self, prepared: PreparedPredicateWrite) -> None:
        """Buffer a prepared predicate-selected write, which settles as one
        readless statement (`m-batch-write` "Predicate-selected readless
        forms"): preparation has refused every target that needs an
        observation."""
        self.buffer(readless_write(prepared))

    def buffer_target(self, prepared: PreparedTargetWrite) -> None:
        """Admit a caller-addressed write and buffer it — all of it, or nothing.

        An amendment that assigns no member is the empty write: it is dropped
        here, having been validated, before any condition, participation, or
        other pending work is consulted. A deletion or termination assigns
        nothing either and is never empty: it reaches the condition like every
        other target write. Every other target write is refused, with nothing
        buffered and the pending writes as they were, where:

        * this attempt admitted an insertion of the object, before or after a
          flush (``write-evidence-inserted``) — such an object is written
          through its insertion's source or a fresh read until commit;
        * it cannot join the object's pending writes
          (``write-evidence-already-claimed``) — another write of the object
          stands at another stated revision or observed state, a temporal one
          overlaps its window without stating exactly that window, an observed
          rectangle holding its start stands at another revision, or the write
          it meets is a destruction it would undo; or
        * under the Locking strategy, the stored state does not match the
          caller's stated revision (:class:`WritePreconditionError`).

        Under Locking, the participation the write needs is taken from a write
        of the same state already pending — over exactly its window, for a
        temporal object — else from a live read of exactly that state this
        attempt holds, else by reading the stored row under the shared lock
        through ``acquire_rows``, executing nothing pending. That read's root
        count decides first: more than one stored row is Cardinality
        Corruption, whatever those rows hold, and none means no row stands.
        A temporal object's row is read whole and kept with the write, for its
        range to reuse while it is still current (:class:`RetainedTargetState`).
        The Optimistic strategy reads nothing: the caller's revision becomes
        the write's gate.
        A temporal target names its state by its stated Transaction-Time start
        and, on a Bitemporal object, by the coverage at its ``valid_from``.
        """
        self._ensure_open()
        if prepared.mutation in AMEND_MUTATIONS and not prepared.assigns:
            return
        item = target_write(prepared, inheritance.view(self.meta))
        self._admission.admit(item, confirm_target=self._confirm_target)

    def _confirm_target(self, item: TargetKeyedWrite) -> TargetKeyedWrite:
        """``item`` once its caller's revision is confirmed under its target's
        Effective Concurrency Strategy, answered with the row it read where it
        read one, or refused.

        Admission has already found no pending write proving that revision.
        Under Locking a live read of exactly that state this attempt holds
        proves it, else the stored row is read under the shared lock; the
        Optimistic strategy reads nothing.
        """
        target = item.instruction.target
        policy = self._evidence_policy_for(target.identity)
        if policy.effective_strategy(self.settings.concurrency) != "locking":
            return item
        expectation = item.expectation
        scope = item.scope
        key = claimed_object(scope)
        if isinstance(expectation, ExpectedTxStart):
            return self._confirm_temporal_target(item, key, expectation)
        if not self._participates(scope):
            stored, _row, _document = self._stored_target(target, key, None)
            if stored is None or stored.version != expectation.version:
                raise WritePreconditionError(
                    target.identity, dict(key.primary_key), expectation.version
                )
        return item

    def _confirm_temporal_target(
        self, item: TargetKeyedWrite, key: ObjectKey, expectation: ExpectedTxStart
    ) -> TargetKeyedWrite:
        """Prove a Locking caller-addressed write of a temporal object starts
        from the state its caller stated, or refuse it, answering the write
        with the row it read where it read one.

        A live read of the state this attempt holds proves it, else it is
        read, whole, and kept with the write as the state the read found at
        this point of the attempt's changes.
        """
        window = item.instruction.valid_time_window
        valid_from = None if window is None else window.start
        if self._participates(
            TemporalObjectStateKey(key, Edge(tx_time=expectation.instant, valid_time=valid_from))
        ):
            return item
        target = item.instruction.target
        read_at = self._freshness
        stored, row, document = self._stored_target(target, key, valid_from, retains=True)
        if stored is None or stored.tx_start != expectation.instant:
            raise WritePreconditionError(
                target.identity, dict(key.primary_key), expectation.instant
            )
        assert row is not None  # a stored revision was read off this row
        selection = self._family(target).member_selection
        shape = temporal_read.view(self.meta).shape(target.identity)
        assert isinstance(shape, TransactionTimeOnly | Bitemporal)  # a temporal target
        state = TemporalObjectStateKey(
            key, milestone_edge(shape, PredecessorRow.over_row(selection, row, None, None), None)
        )
        return replace(item, retained=RetainedTargetState(state, read_at, row, document))

    def _stored_target(
        self,
        target: EntityMetadata,
        key: ObjectKey,
        valid_from: dt.datetime | None,
        *,
        retains: bool = False,
    ) -> tuple[StoredTarget | None, tuple[object, ...] | None, object | None]:
        """The stored revision of the row ``key`` names, read under the shared
        lock, or ``None`` where no row stands — judged once the read is over,
        from its root count first and the unique row's revision cell after —
        beside that row and its raw document, read whole where it ``retains``
        them."""
        count, row, document = self.acquire_rows(
            TargetReadRequest(target, key, valid_from, retains=retains), consume_target
        )
        view = self._family(target)
        if count > 1:
            ((_name, value),) = key.primary_key
            raise CardinalityCorruptionError(
                target.identity,
                KeyTarget(key_attributes=(view.primary_key.identity,), key_values=((value,),)),
                1,
                count,
            )
        if row is None:
            return None, None, None
        selection = view.member_selection
        shape = temporal_read.view(self.meta).shape(target.identity)
        if isinstance(shape, TransactionTimeOnly | Bitemporal):
            start = row[selection.position(shape.transaction_time.start_attribute)]
            stored = StoredTarget(tx_start=normalize_instant(cast("dt.datetime", start)))
            return stored, row, document
        version = self._planner.version_attribute(target.identity)
        assert version is not None  # preparation refuses a target with no revision
        return StoredTarget(cast("int", row[selection.position(version)])), row, document

    def _family(self, entity: EntityMetadata) -> InheritanceEntityView:
        view = inheritance.view(self.meta).entity(entity.identity)
        if view is None:  # pragma: no cover - the facet covers every accepted Entity
            raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
        return view

    def _participates(self, scope: ObjectStateKey | ObjectKey) -> bool:
        """Whether a live read of exactly ``scope`` this attempt holds — under
        its shared lock, unspent, and describing the stored state — already
        proves it."""
        if isinstance(scope, ObjectKey):
            return False
        held = self._observations.get(scope)
        return (
            held is not None
            and held.participation is self._participation
            and not held.consumed
            and not held.invalidated
        )

    def insertion_identity(self, target: ObjectKey) -> InsertionIdentity | None:
        """The authority the standing admitted insertion of ``target`` grants,
        or ``None`` where none stands — the identity a source the insertion was
        stated through carries from then on."""
        self._ensure_open()
        return self._admission.insertion_identity(target)

    def insertion_authority(
        self, identity: InsertionIdentity
    ) -> TimeInterval | NoInsertionAuthority | None:
        """The Valid-Time window the insertion ``identity`` names was admitted
        with — whose start is where a write it authorizes starts — while its
        authority stands in this unit of work, ``None`` for a standing insertion
        of an object without Valid Time, or
        :data:`~parallax.core._execution._unit_work.admission.NO_INSERTION_AUTHORITY`
        once it does not stand: never issued here, retired by the complete
        removal of what it opened, or superseded by a later insertion of the
        same object."""
        self._ensure_open()
        return self._admission.insertion_authority(identity)

    def insertion_advice(self, target: ObjectKey) -> KeyedWriteRefusalAdvice | None:
        """The refusal advice of the admitted insertion of ``target`` that a
        further insertion of it would repeat, or ``None`` where an insertion of
        it is a first opening or its opener supplied none
        (:meth:`~parallax.core._execution._unit_work.admission.WriteAdmission.insertion_advice`)."""
        self._ensure_open()
        return self._admission.insertion_advice(target)

    def resolve_read_evidence(
        self,
        target: EntityMetadata,
        read_evidence: ReadEvidence | None,
        *,
        mutation: KeyedMutation,
        object_key: ObjectKey,
    ) -> SettledEvidence | None:
        """What a keyed write of ``target`` against existing state settles
        against, read off its source's ``read_evidence``, or :class:`WriteEvidenceError`
        where this unit of work cannot use it.

        One resolution serves the address, the gate, the version advance, and
        the claim, so they cannot disagree. Under either Effective Concurrency
        Strategy (`m-opt-lock`) the source must have been read in THIS unit of
        work: a standalone read, a read-only transaction's read, and an earlier
        attempt's read participated in nothing this attempt can stand on,
        whatever key or revision they share with it. The strategy then decides
        what that participating read proves:

        * **Locking** — the license is the shared row lock the read holds. That
          holds for unversioned Non-Temporal targets too: the lock is the whole
          of their evidence, and unconditional intent has its own
          predicate-selected spelling.
        * **Optimistic** — the license is the database gate, so the read must
          also have retained the observation the gate binds.

        Evidence a successful flush already spent, or describing a state a
        later successful change of this transaction replaced, is refused under
        BOTH strategies: either way the state the source observed is no longer
        the stored state, and a held lock does not restore it. A source with no
        observation — an unversioned Non-Temporal row's — is spent the same way
        once a write through it completes, on its read evidence rather than on an
        observation it does not have.
        """
        self._ensure_open()
        identity = target.identity.canonical
        if read_evidence is None or read_evidence.participation is not self._participation:
            raise WriteEvidenceError(
                code="write-evidence-unavailable",
                message=(
                    f"{identity}: a keyed write is licensed only by a read of THIS transaction "
                    "attempt, and the value handed to the verb came from no such read — a "
                    "standalone read, a read-only transaction, and an earlier attempt license "
                    "nothing here; read the row through this transaction and write what that "
                    "read returned, or state the revision you observed through the `*_if` verb"
                ),
                object_key=object_key,
            )
        policy = self._evidence_policy_for(target.identity)
        observation = read_evidence.observation
        settled = policy.settled_evidence(mutation, object_key=object_key, observation=observation)
        if policy.effective_strategy(self.settings.concurrency) == "optimistic" and (
            observation is None
        ):
            raise WriteEvidenceError(
                code="write-evidence-unavailable",
                message=(
                    f"{identity}: the Optimistic strategy gates this write on the state its "
                    "source observed, and the value handed to the verb carries no retained "
                    "observation; read the row through a `find` and write what it returned"
                ),
                object_key=object_key,
            )
        if read_evidence.consumed:
            raise WriteEvidenceError(
                code="write-evidence-consumed",
                message=(
                    f"{identity}: a write through this value's source already completed in a "
                    "flush of this unit of work, so its evidence is spent; read the row again "
                    "and write what that read returns"
                ),
                object_key=object_key,
            )
        if observation is not None and observation.invalidated:
            raise WriteEvidenceError(
                code="write-evidence-consumed",
                message=(
                    f"{identity}: this transaction has since changed the state this value "
                    "observed, so its evidence no longer describes the stored row; read the row "
                    "again and write what that read returns"
                ),
                object_key=object_key,
            )
        return settled

    @property
    def freshness(self) -> int:
        """What a read captures when it runs, so that evidence it builds later
        from the rows it holds is judged against the state those rows had
        (:meth:`retain`)."""
        self._ensure_open()
        return self._freshness

    def retain(
        self, observation: RetainedObservation, /, *, read_at: int | None = None
    ) -> RetainedObservation:
        """Index ``observation`` under the state it observed, answering the
        evidence this unit of work already holds for that state where it holds
        any.

        A reread that resolves to a state some live value already observed
        answers THAT value's evidence, so one observed state has one claim
        within a transaction however many reads reach it — the same rule
        graph aliases already follow. A state whose evidence a flush has spent
        is not reused: the row has moved on, so a fresh read is fresh evidence.

        ``read_at`` is the :attr:`freshness` the producing read captured, by
        default now. Evidence built from a read that ran before a later
        successful change of the same state is answered invalidated and never
        indexed: its rows describe a state this attempt has since replaced.
        """
        self._ensure_open()
        key = observation.key
        if not self._current(key, self._freshness if read_at is None else read_at):
            observation.invalidate()
            return observation
        held = self._observations.get(key)
        if held is not None and not held.consumed and not held.invalidated:
            return held
        self._observations[key] = observation
        return observation

    def _current(self, state: ObjectStateKey, read_at: int) -> bool:
        """Whether no execution unit that completed after a read capturing
        :attr:`freshness` ``read_at`` changed ``state``: what that read found
        of ``state`` is still what the attempt stores, whatever else changed.
        An unchanged milestone a guard proved is no change."""
        log = self._changed
        changed = log.get(state) if log else None
        return changed is None or changed <= read_at

    def read[T](self, read_fn: Callable[[], T]) -> T:
        """Serve a call-time read, force-flushing pending writes first.

        Read-your-own-writes: buffered writes are flushed inside the still-open
        atomic scope before the dependent read runs, so the read never observes
        stale in-transaction state. An abort still erases the force-flushed write
        (the DB rollback the enclosing transaction performs, upstream).
        """
        self._ensure_open()
        if self._admission:
            self.flush(trigger="read_dependency")
        return read_fn()

    def flush(self, *, trigger: WriteBatchReason) -> None:
        """Plan the buffered writes and run the plan unit by unit, each span of
        its steps executed and enforced through the injected
        :class:`~parallax.core._execution._unit_work.write_runner.ExecuteWriteSteps`.

        ``trigger`` names which of the two flush reasons this call is, and every
        caller already knows its own: :meth:`read` serves a read dependency and
        the attempt runs the boundary's pre-commit batch. The whole
        flush runs inside the injected :class:`OpenWriteBatch`'s scope, so a
        planning refusal is inside the batch rather than beside it and a batch
        planning reduces to no DML at all still ends the way it began.

        Each execution unit of the plan completes as soon as its steps succeed,
        before any step of the next unit is taken: it spends the evidence every
        write it composed was admitted through — an overwritten or physically
        empty one included — invalidates evidence of the states it changed,
        retires the owned rows it removed, and registers the rows it opened. A
        deferred unit binds at its turn against what every earlier unit
        published. Sources that carry no observation are spent once the whole
        flush succeeds. Only an update that assigns no member leaves its
        evidence eligible, because it stated no write at all. Spending is
        idempotent, so a claim several units carry is spent once.

        A failure while executing, binding, or completing dooms the attempt's
        lifetime before it propagates, so a caller that catches it can do no
        further work and cannot commit. A planning refusal precedes
        execution and leaves the transaction usable.

        The claims the pending writes took travel out with them: what a later
        write may claim is decided by what is still pending, and after a flush
        nothing is.
        """
        self._ensure_open()
        if not self._admission:
            return
        opening = self.write_batch_opening
        if opening is None:
            self._flush_buffer()
            return
        with opening(trigger):
            self._flush_buffer()

    def _flush_buffer(self) -> None:
        admission = self._admission
        # The planning request is the flush's last reference to the writes it
        # planned, so it ends with the call: once planning succeeds and the
        # batch drains, what a plan's deferred unit took over is released as
        # that unit executes rather than held until the flush ends.
        plan = self._planner.finalize(
            WritePlanningRequest(
                actor_identity=self._actor_identity,
                transaction_instant=self._transaction_instant,
                concurrency=self.settings.concurrency,
                buffered_writes=admission.composed_writes(),
                ownership=admission.ownership,
                counts_unchanged_rows=self.settings.counts_unchanged_rows,
            )
        )
        sources = admission.drain_planned()
        try:
            run_write_plan(self, plan, self.execute_write_steps)
            for source in sources:
                source.consume()
        except BaseException as failure:
            self._lifetime.doom(failure)
            raise
        finally:
            admission.release_continuity()

    def _complete_unit(
        self, unit: ExecutionUnit, effects: UnitEffects, allocated: tuple[object, ...]
    ) -> None:
        """Publish one successful execution unit's ``effects``: its own, or
        those of the range its deferred coverage bound.

        Every source authority the unit's writes settled against is spent;
        live evidence of every state it changed is invalidated and the change
        recorded, so a read that ran before it cannot later build eligible
        evidence of that state; then the owned rows it removed are retired before
        the rows it opened, completed by the keys the database ``allocated``,
        are registered.

        What the unit ``derived`` from its originals stays for the writes a
        barrier kept after it: those were admitted with conditions on the same
        originals, which this unit's guarded effects or held locks have now
        proven. Spending and invalidation still apply to them; no later
        submission is admitted on these proofs. The object's proofs end when
        the unit that ``concludes`` it completes, or with the flush.
        """
        claim = unit.claim
        if claim is not None:
            claim.consume()
        stamp = self._freshness + 1
        changed_any = False
        for key in effects.changed:
            changed_any = True
            self._invalidate(key, stamp)
        if changed_any:
            self._freshness = stamp
        self._admission.complete_unit(effects, allocated)

    def _invalidate(self, key: ObjectStateKey, stamp: int) -> None:
        held = self._observations.get(key)
        if held is not None:
            held.invalidate()
        self._changed[key] = stamp
        if isinstance(key, VersionedObjectStateKey):
            self._admission.record_version_advance(key)

    def _ensure_open(self) -> None:
        self._lifetime.ensure_open()

    def discard(self) -> None:
        """Drop every buffered and in-memory effect of an attempt that will not
        commit.

        The rollback the attempt performs erases any force-flushed rows, and
        buffered claims are released rather than spent: nothing this attempt
        wrote survives, so evidence a later attempt is handed is still about
        stored state.
        """
        self._admission.discard()
        self._observations.clear()
        self._changed.clear()
