from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from itertools import islice
from types import TracebackType
from typing import Final, Literal, Protocol
from weakref import WeakValueDictionary

from parallax.core import inheritance
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.unit_work.claims import (
    SELECTION_INTENT,
    ClaimScope,
    ClaimTable,
    SettledEvidence,
    claim_scope,
    claimed_object,
    keyed_intent,
)
from parallax.core.unit_work.clock import Clock, TransactionInstant
from parallax.core.unit_work.instructions import (
    DESTRUCTIVE_MUTATIONS,
    INSERT_MUTATIONS,
    KeyedMutation,
)
from parallax.core.unit_work.materialized import (
    BufferItem,
    MaterializedWriteGroup,
    ObjectClaimedWrite,
    ObservedKeyedWrite,
    buffered_instruction,
    group_state_keys,
)
from parallax.core.unit_work.plan import WritePlan
from parallax.core.unit_work.planner import (
    ObjectKey,
    ObservedStateKey,
    resolve_object_key,
)
from parallax.core.unit_work.retain import ParticipationToken, ReadOrigin, RetainedObservation
from parallax.core.unit_work.strategy import ActorIdentity, Concurrency, EvidencePolicyLookup
from parallax.core.unit_work.write_planner import PlanningRequest, WritePlanner

__all__ = [
    "WRITE_EVIDENCE_CODES",
    "BufferOutcome",
    "Concurrency",
    "RollbackOnlyError",
    "TransactionSettings",
    "UnitOfWork",
    "UnitOfWorkError",
    "WriteBatchTrigger",
    "WriteEvidenceError",
    "WriteEvidenceErrorCode",
    "active_unit_of_work",
    "run_unit_of_work",
]

type WriteBatchTrigger = Literal["read_dependency", "pre_commit"]
"""The CLOSED set of reasons a unit of work flushes its buffer.

``read_dependency`` is the batch :meth:`UnitOfWork.read` forces out so a
dependent read observes it; ``pre_commit`` is the boundary-owned final batch
:meth:`UnitOfWork.run_outermost` flushes once the callback has returned. There
is no size-based, periodic, or caller-invoked third trigger, which is what lets
an observer state which of the two produced a batch instead of guessing from
position.

The second trigger is named for WHEN it runs rather than for what it does,
because "finalization" already names the planner stage every batch of either
trigger goes through.
"""


class FlushExecutor(Protocol):
    """The composition-layer sink a Write Plan is handed to for lowering and
    execution. It is neutral because m-unit-work takes no m-sql edge.

    ``trigger`` travels with the plan rather than being inferred by the sink: the
    unit of work is the only participant that knows why it flushed, and an
    observer downstream would otherwise have to reconstruct the reason from the
    order it saw batches arrive in.
    """

    def __call__(self, plan: WritePlan, /, *, trigger: WriteBatchTrigger) -> None: ...


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


class WriteBatchOpening(Protocol):
    """The composition-layer opener a flush announces itself to.

    Called once per flush that has something to flush, BEFORE the buffered
    writes are planned and therefore before any statement exists, and the scope
    it answers spans planning as well as execution. A flush that fails in
    planning is therefore inside the scope and never reaches the executor, which
    is the whole distinction this exists to make available: an observer can tell
    a batch that failed before it ran anything from work that is not a batch at
    all. Optional, because the shell itself needs nothing from it.
    """

    def __call__(self, trigger: WriteBatchTrigger, /) -> WriteBatchScope: ...


class UnitOfWorkError(RuntimeError):
    """A unit of work was driven into an illegal state."""


class EscapedTransactionError(UnitOfWorkError):
    """A unit-of-work reference was used after its owning scope ended."""


class RollbackOnlyError(UnitOfWorkError):
    """A doomed (rollback-only) transaction refused commit or re-entry.

    Raised when the outermost boundary would commit a transaction an inner failure
    marked rollback-only, and when a nested scope tries to join one — carrying the
    original failure as its cause (``__cause__``), so its retriability classification
    survives for the outermost retry loop.
    """


type WriteEvidenceErrorCode = Literal[
    "write-evidence-unavailable",
    "write-evidence-consumed",
    "write-evidence-already-claimed",
]
"""The write-evidence refusals a keyed verb raises.

The three partition what can be wrong with a source's evidence at the verb:
there is none the target Entity's Effective Concurrency Strategy can use, the
evidence there is has been spent by a successful flush, or a write already
buffered in this unit of work claimed the scope this one settles against, for an
intent this one cannot join. A conflict the database discovers later is a
different thing entirely and keeps its own flush-time classification.
"""

WRITE_EVIDENCE_CODES: Final[frozenset[str]] = frozenset(
    {
        "write-evidence-unavailable",
        "write-evidence-consumed",
        "write-evidence-already-claimed",
    }
)
"""The complete set of codes :class:`WriteEvidenceError` carries."""


class WriteEvidenceError(LookupError):
    """A keyed write verb was handed a source whose write evidence it cannot use.

    A ``LookupError`` because every code reports that the evidence this write
    needs is not there for it to use: never recorded for this source, recorded
    and already spent, or still live but claimed by an intent this unit of work
    already buffered at the scope this write settles against, which this one
    cannot join. ``object_key`` is the object the write addressed, always
    visible so a caller can say WHICH write was refused; the Read Origin and the
    claim scope behind it stay implementation state.

    Raised synchronously at the verb, before any buffering and before any
    database access. A conflict the database discovers later is a different
    thing entirely and keeps its own flush-time classification.
    """

    def __init__(
        self, *, code: WriteEvidenceErrorCode, message: str, object_key: ObjectKey
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code: Final = code
        self.message: Final = message
        self.object_key: Final = object_key


class BufferOutcome(Enum):
    """What buffering one accepted item did to the buffer's pending inserts.

    Both values mean the item was buffered; a refused item raises instead.
    ``CANCELLED_PENDING_INSERT`` reports a destructive keyed write that removed
    a still-unflushed insert of its object from the pending set — the pair the
    flush will annihilate — and nothing about SQL: the insert stays buffered
    until planning coalesces the two.
    """

    BUFFERED = "buffered"
    CANCELLED_PENDING_INSERT = "cancelled-pending-insert"


@dataclass(frozen=True, slots=True)
class TransactionSettings:
    """A unit of work's fixed Concurrency Preference.

    The default is `optimistic` (`m-unit-work` "Strategy selection"): a
    preference, not a uniform strategy — each Entity's own Optimistic Lock Facet
    decides whether it yields Optimistic or the mandatory Locking fallback
    (`m-opt-lock`).
    """

    concurrency: Concurrency = "optimistic"


class UnitOfWork:
    """The buffering, observing, flushing transaction scope (m-unit-work).

    Construct via :func:`run_unit_of_work` (which owns the frame lifecycle); the
    body receives the unit of work and drives it with :meth:`buffer`, :meth:`retain`,
    and :meth:`read`, asking :meth:`holds_assignment` and
    :meth:`resolve_write_evidence` what a keyed write's source licenses here.
    """

    __slots__ = (
        "_actor_identity",
        "_buffer",
        "_claims",
        "_closed",
        "_evidence_policy_for",
        "_observations",
        "_participation",
        "_pending_inserts",
        "_planner",
        "_rollback_cause",
        "_rollback_only",
        "_transaction_instant",
        "clock",
        "companion",
        "flush_executor",
        "meta",
        "settings",
        "write_batch_opening",
    )

    def __init__(
        self,
        *,
        settings: TransactionSettings,
        clock: Clock,
        meta: Metamodel,
        flush_executor: FlushExecutor,
        planner: WritePlanner,
        actor_identity: ActorIdentity,
        evidence_policy_for: EvidencePolicyLookup,
        write_batch_opening: WriteBatchOpening | None = None,
    ) -> None:
        self.settings = settings
        self.clock = clock
        self.meta = meta
        self.flush_executor = flush_executor
        self.write_batch_opening = write_batch_opening
        # The injected Write Planner (`m-unit-work`'s single finalization
        # authority) — constructed once per accepted Metamodel by the
        # composition layer (`parallax.snapshot.handle.build_write_planner`),
        # which alone may wire the optional policy modules the planner reaches
        # only through its strategy ports. Production and the conformance
        # engine both drive writes through this SAME shell.
        self._planner = planner
        # The Actor Identity execution orchestration supplies for every flush
        # this attempt plans. A forced flush reuses it unchanged; a retry attempt
        # receives its own new `UnitOfWork` and therefore its own copy.
        self._actor_identity = actor_identity
        # The connected model's write-evidence policy, bound once per accepted
        # model by the composition root, which alone may reach `m-opt-lock`.
        self._evidence_policy_for = evidence_policy_for
        # An opaque demarcation-layer companion (the `db.transact` transaction
        # facade), published for the scope's duration so a joining call recovers
        # it via `active_unit_of_work()`. The shell never reads it, and it needs
        # no cleanup of its own: it is reachable only through the per-thread
        # active binding, which `run_outermost` already clears on every exit.
        self.companion: object | None = None
        # The buffered writes, each carrying the claim its verb resolved for it —
        # the strong reference that keeps a write's evidence alive after its
        # source value is released, and what a successful flush spends through.
        self._buffer: list[BufferItem] = []
        # What the buffered writes have claimed, by the scope each claim is taken
        # at. It travels with the buffer rather than with the scope:
        # a flush spends what it planned, so what a later write may claim
        # is decided by what is still pending.
        self._claims = ClaimTable()
        # The objects the buffer currently holds an unflushed insert of: the
        # planner's own `pending_insert` map, kept live as writes arrive instead
        # of rebuilt when they are planned. `buffer` and `_coalesce` read the
        # SAME two mutation families over the same object key, so the outcome a
        # verb is told cannot disagree with what the flush does with the pair.
        self._pending_inserts: set[ObjectKey] = set()
        # The ledger is an INDEX, not an owner: a retained observation lives as
        # long as some source value or buffered write reaches it, and this entry
        # disappears with the last of them (`m-unit-work` "Observation lifetime").
        # What the index is for is recognizing a state this transaction has
        # already seen, so a reread of one state answers the evidence the earlier
        # read's values already carry rather than a second copy of it.
        self._observations: WeakValueDictionary[ObservedStateKey, RetainedObservation] = (
            WeakValueDictionary()
        )
        # This scope's participation identity: what a read of THIS unit of work
        # stamps on the values it produces, and what an effective-Locking write
        # tests its source against.
        self._participation = ParticipationToken()
        self._rollback_only = False
        self._rollback_cause: BaseException | None = None
        # One attempt, one lazy instant: constructing it reads no clock, and
        # every flush this scope plans carries the SAME holder, so all
        # timestamp-requiring work in the attempt shares one captured value
        # while work that needs none never captures at all.
        self._transaction_instant = TransactionInstant(clock)
        self._closed = False

    @property
    def participation(self) -> ParticipationToken:
        """This scope's participation identity — what its own reads stamp on the
        values they produce, and what an effective-Locking keyed write proves its
        source against."""
        self._ensure_open()
        return self._participation

    def buffer(self, item: BufferItem) -> BufferOutcome:
        """Admit ``item``'s claim and buffer it for flush at the unit-of-work
        boundary — all of it, or nothing.

        The claim is read off the carrier itself
        (:func:`~parallax.core.unit_work.materialized.buffered_write`): a
        retained observation claims the state it observed, an object-claimed
        write claims its instruction's object, and a Materialized Write Group
        claims every state it selected (`m-unit-work` "Observed-State
        Coalescing"). A caller-held observation, an insert, and a bare
        instruction claim nothing. An arriving keyed intent the held claim
        cannot absorb raises :class:`WriteEvidenceError`
        (``write-evidence-already-claimed``); a group colliding with a held
        claim raises :class:`UnitOfWorkError`, withdrawing the claims it had
        admitted. Either way the buffer, the claims, and the pending inserts are
        left as they were.

        A carrier built from a read's retained claim brings that claim with it,
        so the buffer is what keeps a write's evidence alive once the caller
        releases the source value it came from, and what a successful flush
        spends it through.

        The outcome reports the pending-insert transition buffering made: an
        insert records the object it opens, and a destructive write of an object
        whose insert is still unflushed cancels that pair — recognized when the
        pair is complete rather than when it is planned.
        """
        self._ensure_open()
        instruction = buffered_instruction(item)
        key = self._addressed_object(item)
        if isinstance(item, MaterializedWriteGroup):
            self._claim_selection(item)
        else:
            self._claim_keyed(item, key)
        self._buffer.append(item)
        mutation = instruction.mutation
        if key is not None and mutation in INSERT_MUTATIONS:
            self._pending_inserts.add(key)
        elif key in self._pending_inserts and mutation in DESTRUCTIVE_MUTATIONS:
            self._pending_inserts.discard(key)
            return BufferOutcome.CANCELLED_PENDING_INSERT
        return BufferOutcome.BUFFERED

    def _addressed_object(self, item: BufferItem) -> ObjectKey | None:
        """The one object ``item`` addresses where buffering needs it — to claim
        it, or to open or cancel a pending insert of it — derived once."""
        if isinstance(item, MaterializedWriteGroup):
            return None
        instruction = buffered_instruction(item)
        mutation = instruction.mutation
        if (
            isinstance(item, ObjectClaimedWrite)
            or mutation in INSERT_MUTATIONS
            or mutation in DESTRUCTIVE_MUTATIONS
        ):
            return resolve_object_key(instruction, inheritance.view(self.meta))
        return None

    def _claim_keyed(self, item: BufferItem, key: ObjectKey | None) -> None:
        if isinstance(item, ObservedKeyedWrite):
            scope: ClaimScope | None = None if item.claim is None else item.claim.key
        elif isinstance(item, ObjectClaimedWrite):
            scope = key
        else:
            return
        intent = keyed_intent(item.instruction)
        if scope is None or intent is None:
            return
        if self._claims.claim(scope, intent) != "incompatible":
            return
        raise WriteEvidenceError(
            code="write-evidence-already-claimed",
            message=(
                f"{item.instruction.target.identity.canonical}: a write already buffered in this "
                "transaction claims what this one settles against, for an intent it cannot be "
                "combined with — a different Valid-Time region composes no interval, an "
                "assignment after a destructive intent resurrects nothing, and a predicate "
                "write's selected rows are one compact group; read the row through this "
                "transaction to flush the buffered intent and settle against fresh state"
            ),
            object_key=claimed_object(scope),
        )

    def _claim_selection(self, group: MaterializedWriteGroup) -> None:
        # The resolving read force-flushed the buffer, so no pending intent can
        # hold a state the group selected; a collision is a caller defect, and
        # rollback re-derives only the admitted prefix rather than retaining
        # every key on the success path.
        admitted = 0
        try:
            for state in group_state_keys(group, self.meta):
                verdict = self._claims.claim(state, SELECTION_INTENT)
                if verdict != "admit":
                    raise UnitOfWorkError(
                        f"a Materialized Write Group's selection of {state!r} collides "
                        f"with a claim this buffer already holds ({verdict})"
                    )
                admitted += 1
        except BaseException:
            self._claims.release(islice(group_state_keys(group, self.meta), admitted))
            raise

    def holds_assignment(
        self, target: EntityMetadata, origin: ReadOrigin | None, *, mutation: KeyedMutation
    ) -> bool:
        """Whether this buffer already holds an ASSIGNMENT at the scope a write
        of ``mutation`` from ``origin`` would claim.

        The question a wholly restoring update asks before it decides whether it
        has anything to cancel, so it demands no usable evidence: a net-zero
        chain off a value the write would refuse still buffers nothing rather
        than raising (`m-opt-lock`'s no-op-first ordering). The scope is the one
        ``target``'s policy derives, so a versioned write is asked about the
        exact state its source observed and an unversioned Non-Temporal one
        about its object. A source from no read cancels nothing.
        """
        self._ensure_open()
        if origin is None:
            return False
        scope = claim_scope(
            self._evidence_policy_for(target.identity).settled_evidence(
                mutation, object_key=origin.object_key, observation=origin.observation
            )
        )
        if scope is None:  # pragma: no cover - a Read Origin reaches its target's own arm
            return False
        held = self._claims.held(scope)
        return held is not None and held.kind == "assignment"

    def resolve_write_evidence(
        self,
        target: EntityMetadata,
        origin: ReadOrigin | None,
        *,
        mutation: KeyedMutation,
        object_key: ObjectKey,
    ) -> SettledEvidence | None:
        """What a keyed write of ``target`` against existing state settles
        against, read off its source's ``origin``, or :class:`WriteEvidenceError`
        where this unit of work cannot use it.

        One resolution serves the address, the gate, the version advance, and
        the claim, so they cannot disagree. It follows ``target``'s Effective
        Concurrency Strategy (`m-opt-lock`), not the preference alone:

        * **Locking** — the license is the shared row lock, so the source read
          must have run in THIS unit of work. A source from another scope, or
          none at all, proves no held lock. That holds for unversioned
          Non-Temporal targets too: the lock is the whole of their evidence, and
          unconditional intent has its own predicate-selected spelling.
        * **Optimistic** — the license is the database gate, so the retained
          observation IS the evidence, and a standalone read's source carries it
          exactly as a participating read's does.

        Evidence a successful flush already spent is refused under BOTH
        strategies: consumption says the state the source observed is no longer
        the stored state, and a held lock does not restore it.
        """
        self._ensure_open()
        policy = self._evidence_policy_for(target.identity)
        observation = None if origin is None else origin.observation
        settled = policy.settled_evidence(mutation, object_key=object_key, observation=observation)
        identity = target.identity.canonical
        if policy.effective_strategy(self.settings.concurrency) == "locking":
            if origin is None or origin.participation is not self._participation:
                raise WriteEvidenceError(
                    code="write-evidence-unavailable",
                    message=(
                        f"{identity}: the Locking strategy licenses this write through the "
                        "shared row lock a read of THIS transaction holds, and the value handed "
                        "to the verb came from no such read; read the row through this "
                        "transaction and write what that read returned"
                    ),
                    object_key=object_key,
                )
        elif observation is None:
            raise WriteEvidenceError(
                code="write-evidence-unavailable",
                message=(
                    f"{identity}: the Optimistic strategy gates this write on the state its "
                    "source observed, and the value handed to the verb carries no retained "
                    "observation; read the row through a `find` and write what it returned"
                ),
                object_key=object_key,
            )
        if observation is not None and observation.consumed:
            raise WriteEvidenceError(
                code="write-evidence-consumed",
                message=(
                    f"{identity}: the state this value observed was already written by a flush "
                    "of this unit of work, so its evidence is spent; read the row again and "
                    "write what that read returns"
                ),
                object_key=object_key,
            )
        return settled

    def retain(self, observation: RetainedObservation) -> RetainedObservation:
        """Index ``observation`` under the state it observed, answering the
        evidence this unit of work already holds for that state where it holds
        any.

        A reread that resolves to a state some live value already observed
        answers THAT value's evidence, so one observed state has one claim
        within a transaction however many reads reach it — the same rule
        graph aliases already follow. A state whose evidence a flush has spent
        is not reused: the row has moved on, so a fresh read is fresh evidence.
        """
        self._ensure_open()
        held = self._observations.get(observation.key)
        if held is not None and not held.consumed:
            return held
        self._observations[observation.key] = observation
        return observation

    def read[T](self, read_fn: Callable[[], T]) -> T:
        """Serve a call-time read, force-flushing pending writes first.

        Read-your-own-writes: buffered writes are flushed inside the still-open
        atomic scope before the dependent read runs, so the read never observes
        stale in-transaction state. An abort still erases the force-flushed write
        (the DB rollback the enclosing transaction performs, upstream).
        """
        self._ensure_open()
        if self._buffer:
            self.flush(trigger="read_dependency")
        return read_fn()

    def flush(self, *, trigger: WriteBatchTrigger) -> None:
        """Plan and execute the buffered writes (the injected executor lowers them).

        ``trigger`` names which of the two flush reasons this call is, and every
        caller already knows its own: :meth:`read` serves a read dependency and
        :meth:`run_outermost` runs the boundary's pre-commit batch. The whole
        flush runs inside the injected :class:`WriteBatchOpening`'s scope, so a
        planning refusal is inside the batch rather than beside it and a batch
        planning reduces to no DML at all still ends the way it began.

        Evidence is spent AFTER the executor returns, and only by the writes that
        survived finalization: a buffered intent coalesced away or eliminated as
        a no-op leaves its evidence eligible, because no write of it reached the
        database — even where a sibling write in the same batch did. Finalization
        is what names those survivors' claims, since it alone knows which items
        it retired, and it names each one once however many surviving writes
        settled against it. A flush that fails aborts the transaction, so
        evidence needs no restoring.

        The claims the buffer took travel out with it: what a later write may
        claim is decided by what is still pending, and after a flush nothing is.
        """
        self._ensure_open()
        if not self._buffer:
            return
        opening = self.write_batch_opening
        if opening is None:
            self._flush_buffer(trigger)
            return
        with opening(trigger):
            self._flush_buffer(trigger)

    def _flush_buffer(self, trigger: WriteBatchTrigger) -> None:
        """Plan the buffer, execute what survived, and spend the survivors' claims."""
        request = PlanningRequest(
            actor_identity=self._actor_identity,
            transaction_instant=self._transaction_instant,
            concurrency=self.settings.concurrency,
            buffered_writes=tuple(self._buffer),
        )
        finalized = self._planner.finalize(request)
        self._buffer.clear()
        self._claims.clear()
        self._pending_inserts.clear()
        self.flush_executor(finalized.plan, trigger=trigger)
        for claim in finalized.claims:
            claim.consume()

    def mark_rollback_only(self, cause: BaseException) -> None:
        """Doom the transaction: commit will be refused. The first cause is kept."""
        self._rollback_only = True
        if self._rollback_cause is None:
            self._rollback_cause = cause

    def ensure_not_rollback_only(self) -> None:
        """Refuse new joined work when the transaction is already doomed."""
        if self._rollback_only:
            raise RollbackOnlyError(
                "cannot join a rollback-only transaction"
            ) from self._rollback_cause

    def _ensure_open(self) -> None:
        if self._closed:
            raise EscapedTransactionError(
                "the unit of work has ended; a reference escaped its scope"
            )

    def _discard(self) -> None:
        # Abort: drop buffered + force-flushed in-memory state. The DB rollback the
        # enclosing transaction performs (upstream) erases any force-flushed rows.
        # Buffered claims are released rather than spent: nothing this scope wrote
        # survives, so evidence a later scope is handed is still about stored state.
        self._buffer.clear()
        self._claims.clear()
        self._pending_inserts.clear()
        self._observations.clear()

    def run_outermost[T](self, body: Callable[[UnitOfWork], T]) -> T:
        """Run ``body`` as the outermost frame: commit (flush) on success, else abort.

        Driven by :func:`run_unit_of_work`; not part of the developer surface.
        """
        _bind_active(self)
        try:
            result = body(self)
            if self._rollback_only:
                # An inner failure doomed the scope; commit is refused even though
                # the outer body returned normally, and the value is withheld.
                raise RollbackOnlyError(
                    "transaction is rollback-only; commit refused"
                ) from self._rollback_cause
            self.flush(trigger="pre_commit")
            return result
        except BaseException:
            # Abort: discard buffered effects and withhold the callback value.
            self._discard()
            raise
        finally:
            self._closed = True
            _clear_active()

    def run_joined[T](self, body: Callable[[UnitOfWork], T]) -> T:
        """Run ``body`` as a joined (nested) frame: return immediately, doom on failure.

        Driven by :func:`run_unit_of_work`; not part of the developer surface.
        """
        self.ensure_not_rollback_only()
        try:
            # The joined body returns immediately; commit/abort/retry belong to the
            # outermost boundary. An inner failure dooms the whole txn.
            return body(self)
        except BaseException as exc:
            self.mark_rollback_only(exc)
            raise


class _ActiveState(threading.local):
    """Per-thread holder for the active unit of work (the class default is the
    per-thread fallback until a thread binds its own instance attribute)."""

    uow: UnitOfWork | None = None


_active = _ActiveState()


def active_unit_of_work() -> UnitOfWork | None:
    """The unit of work active on the current thread, or ``None``."""
    return _active.uow


def _bind_active(uow: UnitOfWork) -> None:
    _active.uow = uow


def _clear_active() -> None:
    _active.uow = None


def run_unit_of_work[T](
    body: Callable[[UnitOfWork], T],
    *,
    settings: TransactionSettings,
    clock: Clock,
    meta: Metamodel,
    flush_executor: FlushExecutor,
    planner: WritePlanner,
    actor_identity: ActorIdentity,
    evidence_policy_for: EvidencePolicyLookup,
    write_batch_opening: WriteBatchOpening | None = None,
) -> T:
    """Run ``body`` in a unit of work — joining the active one or opening a new frame.

    A call while a transaction is active on the current thread **joins** it: the
    body receives the same unit of work and its return value is returned
    immediately (commit and abort belong to the outermost frame), and the passed
    ``settings`` / ``clock`` / ``meta`` / ``flush_executor`` /
    ``write_batch_opening`` / ``planner`` / ``actor_identity`` /
    ``evidence_policy_for`` are ignored in favor of the active transaction's
    (``db.transact`` performs the option-conflict check before calling).
    Otherwise a new outermost frame is opened, and its value is returned only
    after a durable flush; an abort withholds it. ``planner`` is the injected
    Write Planner a new outermost frame's flushes call, and ``actor_identity``
    the boundary-captured Actor Identity every one of its Planning Requests
    carries, and ``evidence_policy_for`` the connected model's write-evidence
    policy its keyed writes are admitted under.
    """
    active = active_unit_of_work()
    if active is not None:
        return active.run_joined(body)
    uow = UnitOfWork(
        settings=settings,
        clock=clock,
        meta=meta,
        flush_executor=flush_executor,
        planner=planner,
        actor_identity=actor_identity,
        evidence_policy_for=evidence_policy_for,
        write_batch_opening=write_batch_opening,
    )
    return uow.run_outermost(body)
