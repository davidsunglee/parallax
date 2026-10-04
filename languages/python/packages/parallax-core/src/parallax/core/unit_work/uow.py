from __future__ import annotations

import threading
from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass
from enum import Enum
from itertools import islice
from types import TracebackType
from typing import Final, Literal, Protocol
from weakref import WeakValueDictionary

from parallax.core import inheritance
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.unit_work.claims import (
    SELECTION_INTENT,
    ClaimScope,
    ClaimTable,
    SettledEvidence,
    admits_composed,
    claimed_object,
    keyed_intent,
)
from parallax.core.unit_work.clock import Clock, TransactionInstant
from parallax.core.unit_work.instructions import (
    DESTRUCTIVE_MUTATIONS,
    INSERT_MUTATIONS,
    KeyedMutation,
    PreparedKeyedWrite,
    PreparedTemporalBounds,
)
from parallax.core.unit_work.materialized import (
    BufferItem,
    MaterializedWriteGroup,
    ObjectClaimedWrite,
    ObservedKeyedWrite,
    buffered_instruction,
    group_state_keys,
)
from parallax.core.unit_work.plan import BoundRange, ExecutionUnit, OwnedEndpoint, WritePlan
from parallax.core.unit_work.planner import (
    ObjectKey,
    ObservedStateKey,
    resolve_object_key,
)
from parallax.core.unit_work.retain import ParticipationToken, ReadOrigin, RetainedObservation
from parallax.core.unit_work.strategy import ActorIdentity, Concurrency, EvidencePolicyLookup
from parallax.core.unit_work.write_planner import (
    PendingWrites,
    PlanningRequest,
    WritePlanner,
    composed_intents,
)

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

    ``completed`` is called with each of the plan's execution units, in order,
    as soon as every step of that unit has executed and been enforced, and
    before any step of a later unit executes. A unit with a deferred range is
    reported with the range its acquired coverage bound, once the bound steps
    have executed; every other unit with ``None``. A normal return reports
    every unit not yet reported; an exception reports none after it.
    """

    def __call__(
        self,
        plan: WritePlan,
        /,
        *,
        trigger: WriteBatchTrigger,
        completed: Callable[[ExecutionUnit, BoundRange | None], None],
    ) -> None: ...


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


class _TargetRecord:
    """What one attempt holds about one object it inserts.

    ``pending_insert`` lasts until the next flush. The admitted insertion —
    ``opener``, the opaque label of the interface that opened it, kept for its
    caller's diagnostics, and the ``bounds`` it was admitted with — lasts until
    the attempt ends or a cancelling destructive write retires it. A record
    exists only while one of them holds.
    """

    __slots__ = ("bounds", "opener", "pending_insert")

    def __init__(self, opener: Hashable | None, bounds: PreparedTemporalBounds) -> None:
        self.pending_insert = True
        self.opener = opener
        self.bounds = bounds


class _TargetWriteState:
    """The attempt's write-owned facts about the objects it writes.

    Each target's still-unflushed insert and admitted insertion, and every
    current temporal row the attempt successfully opened, by complete physical
    address. Reads never add to it, so its size follows what the attempt wrote
    rather than what it read.
    """

    __slots__ = ("_endpoints", "_owning", "_records")

    def __init__(self) -> None:
        self._records: dict[ObjectKey, _TargetRecord] = {}
        self._endpoints: set[OwnedEndpoint] = set()
        # Every Entity some owned row has been an object of, so a group of an
        # Entity the attempt never opened a row of is planned without a
        # per-row check. It only grows; an Entity whose rows were all removed
        # merely keeps its groups on the per-row path.
        self._owning: set[EntityIdentity] = set()

    def owns(self, endpoint: OwnedEndpoint, /) -> bool:
        return endpoint in self._endpoints

    def owns_any(self, entity: EntityIdentity, /) -> bool:
        return entity in self._owning

    def opened_by(self, target: ObjectKey) -> Hashable | None:
        record = self._records.get(target)
        return None if record is None else record.opener

    def insertion_bounds(self, target: ObjectKey) -> PreparedTemporalBounds | None:
        record = self._records.get(target)
        return None if record is None else record.bounds

    def has_pending_insert(self, target: ObjectKey) -> bool:
        record = self._records.get(target)
        return record is not None and record.pending_insert

    def open_insert(
        self, target: ObjectKey, opener: Hashable | None, bounds: PreparedTemporalBounds
    ) -> None:
        self._records[target] = _TargetRecord(opener, bounds)

    def cancel_insert(self, target: ObjectKey) -> None:
        del self._records[target]

    def end_flush(self) -> None:
        records = self._records
        for target in [target for target, record in records.items() if record.pending_insert]:
            record = records[target]
            if record.opener is None:
                del records[target]
            else:
                record.pending_insert = False

    def register(self, endpoint: OwnedEndpoint) -> None:
        self._endpoints.add(endpoint)
        self._owning.add(endpoint.entity)

    def retire(self, endpoint: OwnedEndpoint) -> None:
        self._endpoints.remove(endpoint)  # planning removes only a row this attempt owns

    def clear(self) -> None:
        self._records.clear()
        self._endpoints.clear()
        self._owning.clear()


class UnitOfWork:
    """The buffering, observing, flushing transaction scope (m-unit-work).

    Construct via :func:`run_unit_of_work` (which owns the frame lifecycle); the
    body receives the unit of work and drives it with :meth:`buffer`, :meth:`retain`,
    and :meth:`read`, asking :meth:`resolve_write_evidence` what a keyed write's
    source licenses here.
    """

    __slots__ = (
        "_actor_identity",
        "_changed",
        "_claims",
        "_closed",
        "_evidence_policy_for",
        "_freshness",
        "_observations",
        "_participation",
        "_pending",
        "_planner",
        "_reported",
        "_reporting",
        "_rollback_cause",
        "_rollback_only",
        "_targets",
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
        # The buffered writes, composed as each is admitted, each carrying the
        # claims its verbs resolved for it — the strong reference that keeps a
        # write's evidence alive after its source value is released, and what a
        # successful flush spends through.
        self._pending = PendingWrites(meta)
        # What the buffered writes have claimed, by the scope each claim is taken
        # at. It travels with the buffer rather than with the scope:
        # a flush spends what it planned, so what a later write may claim
        # is decided by what is still pending.
        self._claims = ClaimTable()
        # What this attempt holds about each object it writes: an unflushed
        # insert — the planner's own `pending_insert` map, kept live as writes
        # arrive, over the SAME two mutation families and object key `_coalesce`
        # reads, so the outcome a verb is told cannot disagree with what the
        # flush does with the pair — its admitted insertion, and the current
        # temporal rows it opened.
        self._targets = _TargetWriteState()
        # The ledger is an INDEX, not an owner: a retained observation lives as
        # long as some source value or buffered write reaches it, and this entry
        # disappears with the last of them (`m-unit-work` "Observation lifetime").
        # What the index is for is recognizing a state this transaction has
        # already seen, so a reread of one state answers the evidence the earlier
        # read's values already carry rather than a second copy of it.
        self._observations: WeakValueDictionary[ObservedStateKey, RetainedObservation] = (
            WeakValueDictionary()
        )
        # How many execution units have changed an observed state so far, and
        # the count at which each changed state last changed. A read captures
        # the count when it runs, so evidence it builds later, from rows it
        # already holds, is known to predate any change completed in between.
        self._freshness = 0
        self._changed: dict[ObservedStateKey, int] = {}
        self._reporting: tuple[ExecutionUnit, ...] = ()
        self._reported = 0
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

    def buffer(self, item: BufferItem, *, opener: Hashable | None = None) -> BufferOutcome:
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

        ``opener`` labels an insert's admission with the interface that opened
        it, which :meth:`opened_by` answers until the attempt ends or a
        cancelling destructive write retires the admission.
        """
        self._ensure_open()
        instruction = buffered_instruction(item)
        key = self._addressed_object(item)
        if isinstance(item, MaterializedWriteGroup):
            self._claim_selection(item)
        elif isinstance(item, ObservedKeyedWrite) and self._pending.is_temporal(item):
            self._claim_composed(item)
        else:
            self._claim_keyed(item, key)
        self._pending.add(item, key)
        mutation = instruction.mutation
        targets = self._targets
        if key is not None and mutation in INSERT_MUTATIONS:
            assert isinstance(instruction, PreparedKeyedWrite)  # only a keyed write inserts
            targets.open_insert(key, opener, instruction.bounds)
        elif (
            key is not None
            and mutation in DESTRUCTIVE_MUTATIONS
            and targets.has_pending_insert(key)
        ):
            targets.cancel_insert(key)
            return BufferOutcome.CANCELLED_PENDING_INSERT
        return BufferOutcome.BUFFERED

    def opened_by(self, target: ObjectKey | None) -> Hashable | None:
        """The label an admitted insertion of ``target`` was buffered with, or
        ``None`` where this attempt holds no such insertion.

        An admission outlives the flush that executes its insert and ends with
        the attempt, or when a destructive write cancels the still-pending
        insert. ``None`` names no object and is never held.
        """
        self._ensure_open()
        return None if target is None else self._targets.opened_by(target)

    def insertion_bounds(self, target: ObjectKey | None) -> PreparedTemporalBounds | None:
        """The bounds an admitted insertion of ``target`` was buffered with —
        where a write authored from its insertion source starts — or ``None``
        where this attempt holds no such insertion."""
        self._ensure_open()
        return None if target is None else self._targets.insertion_bounds(target)

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
        if scope is None or keyed_intent(item.instruction) is None:
            return
        object_scope = scope if isinstance(scope, ObjectKey) else scope.object
        if (
            self._claims.held(scope) is None
            and self._pending.verdict(item, object_scope) != "incompatible"
        ):
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

    def _claim_composed(self, item: ObservedKeyedWrite) -> None:
        """Admit a temporal object's observed write into composition with the
        object's pending observed writes, or refuse it (`m-unit-work`
        "Observed-State Coalescing").

        Judged over every write of the object still pending, whatever state
        each observed, before anything changes.
        """
        instruction = item.instruction
        key = resolve_object_key(instruction, inheritance.view(self.meta))
        intent = keyed_intent(instruction)
        assert key is not None and intent is not None  # an observed write names one object
        scope = None if item.claim is None else item.claim.key
        held = self._pending.temporal(key)
        if (
            held is not None
            and admits_composed(composed_intents(held), scope, intent) == "incompatible"
        ) or (scope is not None and self._claims.held(scope) is not None):
            raise WriteEvidenceError(
                code="write-evidence-already-claimed",
                message=(
                    f"{instruction.target.identity.canonical}: a write already buffered in this "
                    "transaction cannot be composed with this one — an assignment after a "
                    "destructive intent over its window resurrects nothing, a destructive "
                    "intent composes only with writes of exactly its own window, and a "
                    "predicate write's selected rows are one compact group; read the row "
                    "through this transaction to flush the buffered intent and settle against "
                    "fresh state"
                ),
                object_key=key,
            )

    def _claim_selection(self, group: MaterializedWriteGroup) -> None:
        # The resolving read force-flushed the buffer, so no pending intent can
        # hold a state the group selected; a collision is a caller defect, and
        # rollback re-derives only the admitted prefix rather than retaining
        # every key on the success path.
        admitted = 0
        try:
            for state in group_state_keys(group, self.meta):
                verdict = (
                    "incompatible"
                    if self._pending.holds(state)
                    else self._claims.claim(state, SELECTION_INTENT)
                )
                if verdict != "admit":
                    raise UnitOfWorkError(
                        f"a Materialized Write Group's selection of {state!r} collides "
                        f"with a claim this buffer already holds ({verdict})"
                    )
                admitted += 1
        except BaseException:
            self._claims.release(islice(group_state_keys(group, self.meta), admitted))
            raise

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

        Evidence a successful flush already spent, or describing a state a
        later successful change of this transaction replaced, is refused under
        BOTH strategies: either way the state the source observed is no longer
        the stored state, and a held lock does not restore it. A source with no
        observation — an unversioned Non-Temporal row's — is spent the same way
        once a write through it completes, on its origin rather than on an
        observation it does not have.
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
        if origin is not None and origin.consumed:
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
        log = self._changed
        changed = log.get(key) if log else None
        if changed is not None and changed > (self._freshness if read_at is None else read_at):
            observation.invalidate()
            return observation
        held = self._observations.get(key)
        if held is not None and not held.consumed and not held.invalidated:
            return held
        self._observations[key] = observation
        return observation

    def read[T](self, read_fn: Callable[[], T]) -> T:
        """Serve a call-time read, force-flushing pending writes first.

        Read-your-own-writes: buffered writes are flushed inside the still-open
        atomic scope before the dependent read runs, so the read never observes
        stale in-transaction state. An abort still erases the force-flushed write
        (the DB rollback the enclosing transaction performs, upstream).
        """
        self._ensure_open()
        if self._pending:
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

        Each execution unit of the plan completes as soon as its steps succeed,
        before the next unit executes: it spends the evidence every write it
        composed was admitted through — an overwritten or physically empty one
        included — invalidates evidence of the states it changed, retires the
        owned rows it removed, and registers the rows it opened. Sources that
        carry no observation are spent once the whole flush succeeds. Only an
        update that assigns no member leaves its evidence eligible, because it
        stated no write at all. Spending is idempotent, so a claim several
        units carry is spent once.

        A failure while executing, enforcing, or completing marks the
        transaction rollback-only before it propagates, so a caller that catches
        it can do no further work and cannot commit. A planning refusal precedes
        execution and leaves the transaction usable.

        The claims the buffer took travel out with it: what a later write may
        claim is decided by what is still pending, and after a flush nothing is.
        """
        self._ensure_open()
        if not self._pending:
            return
        opening = self.write_batch_opening
        if opening is None:
            self._flush_buffer(trigger)
            return
        with opening(trigger):
            self._flush_buffer(trigger)

    def _flush_buffer(self, trigger: WriteBatchTrigger) -> None:
        request = PlanningRequest(
            actor_identity=self._actor_identity,
            transaction_instant=self._transaction_instant,
            concurrency=self.settings.concurrency,
            buffered_writes=self._pending.writes(),
            ownership=self._targets,
        )
        finalized = self._planner.finalize(request)
        sources = self._pending.sources()
        self._pending.clear()
        self._claims.clear()
        self._targets.end_flush()
        units = finalized.plan.units
        self._reporting = units
        self._reported = 0
        try:
            self.flush_executor(finalized.plan, trigger=trigger, completed=self._report)
            for unit in units[self._reported :]:
                self._report(unit, None)
            for source in sources:
                source.consume()
        except BaseException as failure:
            self.mark_rollback_only(failure)
            raise
        finally:
            self._reporting = ()

    def _report(self, unit: ExecutionUnit, bound: BoundRange | None) -> None:
        reported = self._reported
        units = self._reporting
        if reported >= len(units) or unit is not units[reported]:
            raise UnitOfWorkError(
                "an execution unit was reported out of order, or was not one of the plan's"
            )
        if (unit.deferred is None) != (bound is None):
            raise UnitOfWorkError(
                "a deferred range is reported with the range its coverage bound, and no other "
                "unit is"
            )
        self._reported = reported + 1
        if bound is None:
            self._complete(
                unit,
                executed=unit.end > (units[reported - 1].end if reported else 0),
                changed=unit.changed,
                removed=unit.removed,
                opened=unit.opened,
            )
            return
        self._complete(
            unit,
            executed=bool(bound.steps),
            changed=bound.changed,
            removed=bound.removed,
            opened=bound.opened,
        )

    def _complete(
        self,
        unit: ExecutionUnit,
        *,
        executed: bool,
        changed: Iterable[ObservedStateKey],
        removed: Iterable[OwnedEndpoint],
        opened: Iterable[OwnedEndpoint],
    ) -> None:
        """Publish one successful execution unit's effects.

        Every source authority the unit's writes settled against is spent;
        live evidence of every state it changed is invalidated and the change
        recorded, so a read that ran before it cannot later build eligible
        evidence of that state; then the owned rows it removed are retired before
        the rows it opened are registered. A single retained claim's own state
        counts as changed exactly when the unit ``executed`` a step; a unit
        that composed several sources states every state it changed itself.
        """
        stamp = self._freshness + 1
        claim = unit.claim
        changed_any = False
        if claim is not None:
            claim.consume()
            if executed and isinstance(claim, RetainedObservation):
                changed_any = True
                self._invalidate(claim.key, stamp)
        for key in changed:
            changed_any = True
            self._invalidate(key, stamp)
        if changed_any:
            self._freshness = stamp
        targets = self._targets
        for endpoint in removed:
            targets.retire(endpoint)
        for endpoint in opened:
            targets.register(endpoint)

    def _invalidate(self, key: ObservedStateKey, stamp: int) -> None:
        held = self._observations.get(key)
        if held is not None:
            held.invalidate()
        self._changed[key] = stamp

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
        if self._rollback_only:
            raise RollbackOnlyError(
                "the transaction is rollback-only; it accepts no further work"
            ) from self._rollback_cause

    def _discard(self) -> None:
        # Abort: drop buffered + force-flushed in-memory state. The DB rollback the
        # enclosing transaction performs (upstream) erases any force-flushed rows.
        # Buffered claims are released rather than spent: nothing this scope wrote
        # survives, so evidence a later scope is handed is still about stored state.
        self._pending.clear()
        self._claims.clear()
        self._targets.clear()
        self._observations.clear()
        self._changed.clear()

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
