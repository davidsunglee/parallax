from __future__ import annotations

import bisect
import datetime as dt
import threading
from collections.abc import Callable, Hashable, Iterable, Iterator
from dataclasses import dataclass
from enum import Enum
from itertools import islice
from types import TracebackType
from typing import Final, Literal, Protocol, final
from weakref import WeakValueDictionary

from parallax.core import inheritance
from parallax.core.base import INFINITY, TemporalBound
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.temporal_read import Edge, TimeInterval
from parallax.core.unit_work.claims import (
    SELECTION_INTENT,
    ClaimScope,
    ClaimTable,
    SettledEvidence,
    claimed_object,
    keyed_intent,
)
from parallax.core.unit_work.clock import Clock, TransactionInstant
from parallax.core.unit_work.effects import WritePreconditionError
from parallax.core.unit_work.instructions import (
    DESTRUCTIVE_MUTATIONS,
    INSERT_MUTATIONS,
    ExpectedTxStart,
    ExpectedVersion,
    KeyedMutation,
    PreparedKeyedWrite,
    PreparedTargetWrite,
)
from parallax.core.unit_work.keys import resolve_object_key
from parallax.core.unit_work.materialized import (
    BufferItem,
    InsertionKeyedWrite,
    MaterializedWriteGroup,
    ObjectClaimedWrite,
    ObservedKeyedWrite,
    TargetKeyedWrite,
    buffered_instruction,
    group_state_keys,
    target_write,
)
from parallax.core.unit_work.retain import (
    InsertionIdentity,
    ParticipationToken,
    ReadOrigin,
    RetainedObservation,
)
from parallax.core.unit_work.strategy import ActorIdentity, Concurrency, EvidencePolicyLookup
from parallax.core.unit_work.write_planner import (
    PendingWrites,
    PlanningRequest,
    WritePlanner,
)
from parallax.core.write_plan.keys import (
    ObjectKey,
    ObservedStateKey,
    TemporalStateKey,
    VersionedStateKey,
)
from parallax.core.write_plan.materialized import PredecessorRows
from parallax.core.write_plan.plan import (
    AllocatedOpening,
    BoundRange,
    DeferredRange,
    Derivation,
    Descent,
    ExecutionUnit,
    Openings,
    OwnedEndpoint,
    UnitEffects,
    WritePlan,
)
from parallax.core.write_plan.steps import Finite

__all__ = [
    "NO_INSERTION_AUTHORITY",
    "WRITE_EVIDENCE_CODES",
    "BufferOutcome",
    "Concurrency",
    "DeferredBinder",
    "NoInsertionAuthority",
    "RollbackOnlyError",
    "StoredTarget",
    "TargetAcquisition",
    "TransactionSettings",
    "UnitOfWork",
    "UnitOfWorkError",
    "UnitReport",
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


class UnitReport(Protocol):
    """How a :class:`FlushExecutor` reports one execution unit it completed:
    with the range its coverage bound, if deferred, and the key each of its
    inserts answered for a row whose key the database allocated, in step
    order."""

    def __call__(
        self,
        unit: ExecutionUnit,
        bound: BoundRange | None,
        /,
        *,
        allocated: tuple[object, ...] = (),
    ) -> None: ...


class DeferredBinder(Protocol):
    """How a :class:`FlushExecutor` binds a deferred range to the coverage its
    acquisition read — ``None`` where the read found no row — once every
    earlier unit of the flush has completed."""

    def __call__(
        self, description: DeferredRange, rows: PredecessorRows | None, /
    ) -> BoundRange: ...


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
    reached with no step: the executor acquires its coverage, binds it through
    ``bind_deferred`` once, executes and enforces every bound step, and reports
    the unit with that bound range; every other unit is reported with ``None``.
    A unit opening rows whose keys the database allocates is reported with
    those keys. A normal return reports every unit not yet reported; an
    exception reports none after it.
    """

    def __call__(
        self,
        plan: WritePlan,
        /,
        *,
        trigger: WriteBatchTrigger,
        bind_deferred: DeferredBinder,
        completed: UnitReport,
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


@dataclass(frozen=True, slots=True)
class StoredTarget:
    """What an internal acquisition found of the stored state a caller-addressed
    write starts from: its version, where its family has one, or its current
    Transaction-Time start, where its family is temporal."""

    version: int | None = None
    tx_start: object | None = None


class TargetAcquisition(Protocol):
    """The composition-layer capability that reads the stored state a
    caller-addressed write of ``key`` starts from, under the shared row lock,
    on the transaction's own connection: the row current at Valid-Time
    ``valid_from`` of a Bitemporal object, which is ``None`` for any other.

    It executes no pending write and publishes nothing to any caller: what it
    answers is participation and the stored revision, and ``None`` where no
    current row stands.
    """

    def __call__(
        self, target: EntityMetadata, key: ObjectKey, valid_from: object | None, /
    ) -> StoredTarget | None: ...


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
    "write-evidence-inserted",
]
"""The write-evidence refusals a keyed verb raises.

The first three partition what can be wrong with a source's evidence at the
verb: there is none the target Entity's Effective Concurrency Strategy can use,
the evidence there is has been spent by a successful flush, or a write already
buffered in this unit of work claimed the scope this one settles against, for an
intent this one cannot join. The fourth refuses a caller's own condition on an
object this attempt inserted, which only that insertion's source or a read
addresses. A conflict the database discovers later is a different thing
entirely and keeps its own flush-time classification.
"""

WRITE_EVIDENCE_CODES: Final[frozenset[str]] = frozenset(
    {
        "write-evidence-unavailable",
        "write-evidence-consumed",
        "write-evidence-already-claimed",
        "write-evidence-inserted",
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
    ``CANCELLED_PENDING_INSERT`` reports a destructive keyed write that left
    nothing of a still-unflushed insert of its object — the pair the flush
    emits nothing for — and nothing about SQL.
    """

    BUFFERED = "buffered"
    CANCELLED_PENDING_INSERT = "cancelled-pending-insert"


@dataclass(frozen=True, slots=True)
class TransactionSettings:
    """A unit of work's fixed Concurrency Preference, and what its database's
    write counts report.

    The default is `optimistic` (`m-unit-work` "Strategy selection"): a
    preference, not a uniform strategy — each Entity's own Optimistic Lock Facet
    decides whether it yields Optimistic or the mandatory Locking fallback
    (`m-opt-lock`). ``counts_unchanged_rows`` is the connection's dialect fact
    every flush plans with (:class:`~parallax.core.unit_work.write_planner.PlanningRequest`).
    """

    concurrency: Concurrency = "optimistic"
    counts_unchanged_rows: bool = False


class _TargetRecord:
    """What one attempt holds about one object it inserted.

    ``opener`` labels the interface that admitted the latest insertion, kept
    for its caller's diagnostics, and ``valid_time_window`` is the window it was
    admitted with, ``None`` for an object without Valid Time — its start is the
    anchor every write it authorizes starts at. ``identity`` is the
    authority that insertion grants while it stands, and ``None`` once its
    complete removal retired it. ``pending_insert`` lasts until the next flush.

    What survives of the object's admitted insertions is counted where it is
    stored: ``live`` — the owned current rows an admission of the object
    opened, by their tags — for a Bitemporal object, whose coverage a write can
    remove in part, and ``row`` for any other, which a removal takes whole.
    ``floor`` is the earliest anchor of any admission whose coverage may still
    be stored — once a flush executes an insertion, its own anchor, since what
    an earlier admission opened was removed before it — and ``advanced_from``
    the version the last completed update of a versioned row advanced from.
    ``removal`` keeps the stored removal window once it is asked for
    (:meth:`_TargetWriteState.removal_window`), until what it derives from
    changes. A record lasts until the attempt ends, whatever became of the
    insertion: it is also the fact that this attempt admitted one.
    """

    __slots__ = (
        "advanced_from",
        "bitemporal",
        "floor",
        "identity",
        "live",
        "opener",
        "pending_insert",
        "removal",
        "row",
        "valid_time_window",
    )

    def __init__(
        self,
        opener: Hashable | None,
        valid_time_window: TimeInterval | None,
        identity: InsertionIdentity,
        *,
        bitemporal: bool,
    ) -> None:
        self.opener = opener
        self.valid_time_window = valid_time_window
        self.identity: InsertionIdentity | None = identity
        self.pending_insert = True
        self.bitemporal = bitemporal
        self.row = False
        self.live = 0
        self.floor = _window_start(valid_time_window)
        self.advanced_from: int | None = None
        self.removal: TimeInterval | _Uncomputed = _UNCOMPUTED

    def set_floor(self, floor: dt.datetime | None) -> None:
        """Retain ``floor`` as the earliest stored anchor, dropping a removal
        window derived from the previous one."""
        if floor != self.floor:
            self.floor = floor
            self.removal = _UNCOMPUTED

    @property
    def stored(self) -> bool:
        """Whether anything an admitted insertion of the object opened may
        still be stored."""
        return self.live > 0 if self.bitemporal else self.row


@final
class _Uncomputed:
    """The removal window a record has not derived since what it derives from
    last changed — distinct from every window, and from a missing Valid-Time
    axis."""

    __slots__ = ()


_UNCOMPUTED: Final = _Uncomputed()


@final
class NoInsertionAuthority:
    """The answer :meth:`UnitOfWork.insertion_authority` gives where no admitted
    insertion's authority stands: distinct from the ``None`` window of a
    standing insertion without Valid Time."""

    __slots__ = ()


NO_INSERTION_AUTHORITY: Final = NoInsertionAuthority()


def _window_start(window: TimeInterval | None) -> dt.datetime | None:
    return None if window is None else window.start


type _Address = tuple[EntityIdentity, tuple[object, ...]]


class _TargetWriteState:
    """The attempt's write-owned facts about the objects it writes.

    Each target's admitted insertion, and every current temporal row the
    attempt successfully opened, by complete physical address. A row of a
    Bitemporal object that continues an admission standing when it opens — the
    admission's own insert, or a successor of a row tagged with an admission —
    is tagged with that admission's identity; a successor of a row no
    admission opened is not. Reads never add to it, so its size follows what
    the attempt wrote rather than what it read.
    """

    __slots__ = ("_addresses", "_continuity", "_endpoints", "_owning", "_records", "_tags")

    def __init__(self) -> None:
        self._records: dict[ObjectKey, _TargetRecord] = {}
        # The Bitemporal records again, by the address an owned row names its
        # object with, so tagging a row needs no key of its own.
        self._addresses: dict[_Address, _TargetRecord] = {}
        self._endpoints: set[OwnedEndpoint] = set()
        self._tags: dict[OwnedEndpoint, InsertionIdentity] = {}
        # Every Entity some owned row has been an object of, so a group of an
        # Entity the attempt never opened a row of is planned without a
        # per-row check. It only grows; an Entity whose rows were all removed
        # merely keeps its groups on the per-row path.
        self._owning: set[EntityIdentity] = set()
        # What units of the running flush proved for later ones, allocated by
        # the first unit that records anything and released once no object's
        # proofs remain, or when the flush ends however it ends.
        self._continuity: _Continuity | None = None

    def owns(self, endpoint: OwnedEndpoint, /) -> bool:
        return endpoint in self._endpoints

    def owns_any(self, entity: EntityIdentity, /) -> bool:
        return entity in self._owning

    def continues_insertion(self, endpoint: OwnedEndpoint, /) -> bool:
        return endpoint in self._tags

    def proven(self, original: ObservedStateKey, /) -> Derivation | None:
        continuity = self._continuity
        proofs = None if continuity is None else continuity.proofs.get(original.object)
        return None if proofs is None else proofs.get(original)

    def descendants(
        self, original: ObservedStateKey, valid_time_window: TimeInterval | None, /
    ) -> Iterator[tuple[OwnedEndpoint, Descent]]:
        continuity = self._continuity
        assert continuity is not None  # a proven original's rows are kept
        descents = continuity.descents
        for endpoint in continuity.lineage[original].reaching(valid_time_window):
            descent = descents[endpoint]
            coverage = descent.valid_time_coverage
            if valid_time_window is None or (
                coverage is not None and coverage.overlaps(valid_time_window)
            ):
                yield endpoint, descent

    def descent(self, endpoint: OwnedEndpoint, /) -> Descent | None:
        continuity = self._continuity
        return None if continuity is None else continuity.descents.get(endpoint)

    def record(self, target: ObjectKey) -> _TargetRecord | None:
        return self._records.get(target)

    def authority(self, identity: InsertionIdentity) -> _TargetRecord | None:
        """The record whose standing authority ``identity`` is, if any."""
        record = self._records.get(identity.object_key)
        return record if record is not None and record.identity is identity else None

    def open_insert(
        self,
        target: ObjectKey,
        opener: Hashable | None,
        valid_time_window: TimeInterval | None,
        *,
        bitemporal: bool,
    ) -> InsertionIdentity:
        identity = InsertionIdentity(target)
        record = self._records.get(target)
        if record is None:
            record = _TargetRecord(opener, valid_time_window, identity, bitemporal=bitemporal)
            self._records[target] = record
            if bitemporal:
                self._addresses[_address(target)] = record
            return identity
        if not record.stored:
            record.set_floor(_window_start(valid_time_window))
        record.opener = opener
        record.valid_time_window = valid_time_window
        record.identity = identity
        record.pending_insert = True
        record.advanced_from = None
        return identity

    def store_pending_insert(self, target: ObjectKey) -> None:
        """Count the pending insertion of ``target`` as stored, because a later
        pending write removes the whole row it opens: what is pending of the
        object is then that removal."""
        record = self._records.get(target)
        if record is not None and record.pending_insert:
            record.pending_insert = False
            record.row = True

    def cancel_insert(self, target: ObjectKey) -> None:
        # The record stays: the attempt admitted an insertion of the object
        # whatever became of it, and a caller-addressed write consults that.
        record = self._records[target]
        record.identity = None
        record.pending_insert = False

    def removal_window(self, record: _TargetRecord) -> TimeInterval:
        """The Valid Time a removal of everything a Bitemporal ``record``'s
        admissions left stored must destroy: from its retained floor to the
        latest end among the owned rows they opened, the open bound included.

        It encloses that coverage rather than tracing it, and is derived when
        first asked, then kept on the record until a row it derives from is
        tagged or retired or the floor moves.
        """
        removal = record.removal
        if isinstance(removal, TimeInterval):
            return removal
        floor = record.floor
        assert floor is not None  # a Bitemporal opening states its start
        removal = record.removal = TimeInterval(floor, self._latest_end(record))
        return removal

    def _latest_end(self, record: _TargetRecord) -> dt.datetime | Literal[TemporalBound.INFINITY]:
        """The latest Valid-Time end among the owned rows ``record``'s
        admissions opened, each physical end read as its managed endpoint; the
        open bound where one runs on, or where none is tagged."""
        latest: dt.datetime | None = None
        for endpoint in self._tags:
            if self._addresses.get((endpoint.entity, endpoint.key)) is not record:
                continue
            end = endpoint.ends[0]
            if not isinstance(end, Finite):
                return INFINITY
            instant = end.instant
            assert isinstance(instant, dt.datetime)  # a finite Valid-Time end is an instant
            if latest is None or instant > latest:
                latest = instant
        return INFINITY if latest is None else latest

    def advanced(self, state: VersionedStateKey) -> None:
        record = self._records.get(state.object)
        if record is not None:
            record.advanced_from = state.version

    def end_flush(self, removed: Iterable[ObjectKey]) -> None:
        records = self._records
        for target in removed:
            record = records.get(target)
            if record is None:
                continue
            record.row = False
            if not record.pending_insert:
                record.identity = None
        for record in records.values():
            if record.pending_insert:
                record.pending_insert = False
                record.row = True
                record.set_floor(_window_start(record.valid_time_window))

    def complete(
        self,
        removed: Iterable[OwnedEndpoint],
        opened: Openings,
        derived: tuple[Derivation, ...] = (),
        concludes: ObjectKey | None = None,
    ) -> None:
        """Retire the owned rows one execution unit removed, then register the
        rows it opened. An admission whose last tagged row the unit removed is
        retired only if no row the unit opened continues it.

        Each original the unit ``derived`` rows from that stood before the
        flush began is proven until the object's last consumer — the unit that
        ``concludes`` it — completes, or the flush ends, and each row it derived
        descends from it; a row derived from one an earlier unit of the flush
        derived descends from what that one did."""
        continuity = self._continuity
        if derived and continuity is None:
            continuity = self._continuity = _Continuity()
        inherited = continuity.inherited(derived) if continuity is not None else ()
        drained = self._retire(removed, continuity)
        for endpoint in opened.fresh:
            self._register(endpoint)
        for endpoint in opened.continued:
            self._register(endpoint)
            self._tag(endpoint)
        for record, tag in drained:
            if not record.live and record.identity is tag and not record.pending_insert:
                # The last row this admission opened is gone: it was removed
                # completely, and its authority ends with it.
                record.identity = None
        if continuity is not None:
            continuity.derive(derived, inherited)
            if concludes is not None:
                continuity.release(concludes)
                if not continuity.proofs:
                    self._continuity = None

    def _retire(
        self, removed: Iterable[OwnedEndpoint], continuity: _Continuity | None
    ) -> list[tuple[_TargetRecord, InsertionIdentity]]:
        """Retire each removed row, answering every admission whose last tagged
        row went with them."""
        drained: list[tuple[_TargetRecord, InsertionIdentity]] = []
        for endpoint in removed:
            self._endpoints.remove(endpoint)  # planning removes only a row this attempt owns
            if continuity is not None:
                continuity.forget(endpoint)
            tag = self._tags.pop(endpoint, None) if self._tags else None
            if tag is None:
                continue
            record = self._addresses[(endpoint.entity, endpoint.key)]
            record.live -= 1
            record.removal = _UNCOMPUTED
            if not record.live:
                drained.append((record, tag))
        return drained

    def release_continuity(self) -> None:
        """End the flush's proofs: no later submission carries them."""
        self._continuity = None

    def _register(self, endpoint: OwnedEndpoint) -> None:
        self._endpoints.add(endpoint)
        self._owning.add(endpoint.entity)

    def _tag(self, endpoint: OwnedEndpoint) -> None:
        record = self._addresses.get((endpoint.entity, endpoint.key))
        if record is not None and record.identity is not None:
            self._tags[endpoint] = record.identity
            record.live += 1
            record.removal = _UNCOMPUTED

    def clear(self) -> None:
        self._records.clear()
        self._addresses.clear()
        self._endpoints.clear()
        self._tags.clear()
        self._owning.clear()
        self.release_continuity()


def _with_allocated(opened: Openings, allocated: tuple[object, ...]) -> Openings:
    named = tuple(
        _allocated_endpoint(opening, key)
        for opening, key in zip(opened.allocated, allocated, strict=True)
    )
    return Openings(fresh=(*opened.fresh, *named), continued=opened.continued)


def _allocated_endpoint(opening: AllocatedOpening, key: object) -> OwnedEndpoint:
    return OwnedEndpoint(opening.entity, (key,), opening.ends)


class _Continuity:
    """What the running flush's units proved for later units of the same
    objects: each original transformed under protection that stood before the
    flush began, which current row derives from which of them, and each one's
    current rows in Valid-Time order."""

    __slots__ = ("descents", "lineage", "proofs")

    def __init__(self) -> None:
        self.proofs: dict[ObjectKey, dict[ObservedStateKey, Derivation]] = {}
        self.descents: dict[OwnedEndpoint, Descent] = {}
        self.lineage: dict[ObservedStateKey, _Lineage] = {}

    def inherited(self, derived: tuple[Derivation, ...]) -> tuple[ObservedStateKey | None, ...]:
        """The original each one in ``derived`` was itself derived from earlier
        in the flush, if any, read before the unit's removals retire it."""
        descents = self.descents
        inherited: list[ObservedStateKey | None] = []
        for derivation in derived:
            owned = derivation.owned
            descent = None if owned is None else descents.get(owned)
            inherited.append(None if descent is None else descent.original)
        return tuple(inherited)

    def derive(
        self, derived: tuple[Derivation, ...], inherited: tuple[ObservedStateKey | None, ...]
    ) -> None:
        for derivation, earlier in zip(derived, inherited, strict=True):
            original = derivation.original
            if earlier is None:
                self.proofs.setdefault(original.object, {})[original] = derivation
            else:
                original = earlier
            rows = self.lineage.get(original)
            if rows is None:
                rows = self.lineage[original] = _Lineage()
            # A row revised in place is re-derived at its own address, so what
            # it descended from is forgotten before any row is added again.
            for endpoint, _coverage in derivation.rows:
                self.forget(endpoint)
            for endpoint, coverage in derivation.rows:
                self.descents[endpoint] = Descent(coverage, original)
                rows.add(endpoint, coverage)

    def forget(self, endpoint: OwnedEndpoint) -> None:
        descent = self.descents.pop(endpoint, None)
        if descent is not None:
            self.lineage[descent.original].discard(endpoint, descent.valid_time_coverage)

    def release(self, target: ObjectKey) -> None:
        """Drop everything proven about ``target``: its last consumer is done."""
        descents = self.descents
        for original in self.proofs.pop(target, ()):
            for endpoint in self.lineage.pop(original).rows:
                del descents[endpoint]


class _Lineage:
    """The current rows derived from one proven original, in Valid-Time order.

    They are pieces of one original's coverage and so never overlap, which is
    what lets a range find the ones its window may reach by their starts alone
    rather than by visiting every row the original's units left. An original
    without Valid Time has one current row at a time, keyed at the earliest
    instant.
    """

    __slots__ = ("_keys", "_rows")

    def __init__(self) -> None:
        self._keys: list[dt.datetime] = []
        self._rows: list[OwnedEndpoint] = []

    def add(self, endpoint: OwnedEndpoint, coverage: TimeInterval | None) -> None:
        key = _lineage_key(coverage)
        position = bisect.bisect_right(self._keys, key)
        self._keys.insert(position, key)
        self._rows.insert(position, endpoint)

    def discard(self, endpoint: OwnedEndpoint, coverage: TimeInterval | None) -> None:
        position = bisect.bisect_left(self._keys, _lineage_key(coverage))
        assert self._rows[position] == endpoint  # no two current pieces share a start
        del self._keys[position]
        del self._rows[position]

    @property
    def rows(self) -> list[OwnedEndpoint]:
        return self._rows

    def reaching(self, window: TimeInterval | None) -> Iterator[OwnedEndpoint]:
        """The rows that may overlap ``window``, every one where it is
        ``None``: those starting before its end, from the last one starting at
        or before its start."""
        rows = self._rows
        if window is None:
            yield from rows
            return
        keys = self._keys
        first = max(bisect.bisect_right(keys, window.start) - 1, 0)
        end = window.end
        last = len(keys) if end is INFINITY else bisect.bisect_left(keys, end)
        for position in range(first, last):
            yield rows[position]


_AXISLESS: Final = dt.datetime.min.replace(tzinfo=dt.UTC)


def _lineage_key(coverage: TimeInterval | None) -> dt.datetime:
    return _AXISLESS if coverage is None else coverage.start


def _address(target: ObjectKey) -> _Address:
    return (target.entity, tuple(value for _name, value in target.primary_key))


class UnitOfWork:
    """The buffering, observing, flushing transaction scope (m-unit-work).

    Run it through :meth:`run_outermost` or :func:`run_unit_of_work`, which own
    the frame lifecycle; the body receives the unit of work and drives it with
    :meth:`buffer`, :meth:`retain`, and :meth:`read`, asking
    :meth:`resolve_write_evidence` what a keyed write's source licenses here.
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
        # What this attempt holds about each object it writes: its admitted
        # insertion and the authority that grants, and the current temporal
        # rows it opened.
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

        An insert admits an insertion of the object it opens and issues that
        insertion's identity (:meth:`insertion_identity`), which ``opener``
        labels with the interface that opened it. Where an earlier insertion of
        the object is stored and a pending write removes all of it, the insert
        executes after that removal. A write an insertion authorized
        (:class:`~parallax.core.unit_work.materialized.InsertionKeyedWrite`) is
        admitted only while that authority stands.

        The outcome reports the pending-insert transition buffering made: a
        destructive write that leaves nothing of an object's still-unflushed
        insert cancels that pair — recognized when the pair is complete rather
        than when it is planned.
        """
        self._ensure_open()
        if isinstance(item, InsertionKeyedWrite):
            item = self._authorized(item)
        instruction = buffered_instruction(item)
        key = self._addressed_object(item)
        if isinstance(item, MaterializedWriteGroup):
            self._claim_selection(item)
        elif self._pending.is_temporal(item):
            assert isinstance(item, ObservedKeyedWrite | InsertionKeyedWrite)
            self._claim_composed(item)
        else:
            self._claim_keyed(item, key)
        targets = self._targets
        if key is not None and instruction.mutation in INSERT_MUTATIONS:
            assert isinstance(instruction, PreparedKeyedWrite)  # only a keyed write inserts
            record = targets.record(key)
            self._pending.add(
                item,
                key,
                after_removal=record is not None and self._removed_whole(key, record),
            )
            targets.open_insert(
                key,
                opener,
                instruction.valid_time_window,
                bitemporal=self._pending.is_bitemporal_target(instruction),
            )
            return BufferOutcome.BUFFERED
        folds = key is not None and self._pending.folds_into_opening(key)
        if self._pending.add(item, key):
            assert key is not None  # only a write of one object cancels its insert
            targets.cancel_insert(key)
            return BufferOutcome.CANCELLED_PENDING_INSERT
        if (
            key is not None
            and not folds
            and instruction.mutation in DESTRUCTIVE_MUTATIONS
            and self._pending.removes(key)
        ):
            # A barrier kept this removal after the object's pending insert,
            # which therefore executes and opens the row this one removes.
            targets.store_pending_insert(key)
        return BufferOutcome.BUFFERED

    def buffer_target(self, prepared: PreparedTargetWrite, *, acquire: TargetAcquisition) -> None:
        """Admit a caller-addressed write and buffer it — all of it, or nothing.

        A patch that assigns no member is the empty write: it is dropped here,
        having been validated, before any condition, participation, or other
        pending work is consulted. Every other target write is refused, with
        nothing buffered and the pending writes as they were, where:

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
        attempt holds, else by ``acquire`` — which reads the stored row under
        the shared lock and executes nothing pending. The Optimistic
        strategy reads nothing: the caller's revision becomes the write's gate.
        A temporal target names its state by its stated Transaction-Time start
        and, on a Bitemporal object, by the coverage at its ``valid_from``.
        """
        self._ensure_open()
        if not prepared.replaces and not prepared.assigns:
            return
        target = prepared.target
        item = target_write(prepared, inheritance.view(self.meta))
        scope = item.scope
        key = claimed_object(scope)
        if self._targets.record(key) is not None:
            raise WriteEvidenceError(
                code="write-evidence-inserted",
                message=(
                    f"{target.identity.canonical}: this transaction inserted the object this write "
                    "addresses, so no caller's revision describes it; until the transaction "
                    "commits, write it through the value the insert took or a read of it"
                ),
                object_key=key,
            )
        expectation = prepared.expectation
        temporal = self._pending.is_temporal(item)
        admitted = (
            self._pending.admits_temporal(item, key)
            if temporal
            else self._pending.admits_target(item, key)
        )
        if not admitted or self._claims.claims_object(key):
            raise _already_claimed(target, key)
        policy = self._evidence_policy_for(target.identity)
        if policy.effective_strategy(self.settings.concurrency) == "locking":
            if temporal:
                assert isinstance(expectation, ExpectedTxStart)  # a temporal target's revision
                self._acquire_temporal(item, key, expectation, acquire)
            elif not (self._pending.holds_scope(scope) or self._participates(scope)):
                stored = acquire(target, key, None)
                if isinstance(expectation, ExpectedVersion) and (
                    stored is None or stored.version != expectation.version
                ):
                    raise WritePreconditionError(
                        target.identity, dict(key.primary_key), expectation.version
                    )
        self._pending.add(item, key)

    def _acquire_temporal(
        self,
        item: TargetKeyedWrite,
        key: ObjectKey,
        expectation: ExpectedTxStart,
        acquire: TargetAcquisition,
    ) -> None:
        """Prove a Locking caller-addressed write of a temporal object starts
        from the state its caller stated, or refuse it.

        A pending write of the object over exactly this window already holds
        that state: admission required it to start from exactly this one. A
        write over a disjoint window starts elsewhere and proves nothing here.
        Otherwise a live read of the state this attempt holds does, else
        ``acquire`` reads it.
        """
        window = item.instruction.valid_time_window
        if self._pending.states_window(key, window):
            return
        valid_from = _window_start(window)
        if self._participates(
            TemporalStateKey(key, Edge(tx_time=expectation.instant, valid_time=valid_from))
        ):
            return
        target = item.instruction.target
        stored = acquire(target, key, valid_from)
        if stored is None or stored.tx_start != expectation.instant:
            raise WritePreconditionError(
                target.identity, dict(key.primary_key), expectation.instant
            )

    def _participates(self, scope: ObservedStateKey | ObjectKey) -> bool:
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

    def _authorized(self, item: InsertionKeyedWrite) -> InsertionKeyedWrite:
        """``item`` checked against the authority it carries, and given the
        claim scope its stored Non-Temporal row takes, or refused."""
        record = self._targets.authority(item.identity)
        instruction = item.instruction
        if record is None:
            raise UnitOfWorkError(
                f"{instruction.target.identity.canonical}: the insertion this write was authored "
                "through no longer stands in this unit of work"
            )
        key = item.identity.object_key
        if record.pending_insert and self._pending.folds_into_opening(key):
            if not self._pending.opening_admits(key, instruction):
                raise _already_claimed(instruction.target, key)
            return item
        if self._pending.is_temporal(item):
            return item
        version = self._planner.inserted_version(instruction.target.identity, record.advanced_from)
        scope = key if version is None else VersionedStateKey(key, version)
        return InsertionKeyedWrite(instruction=instruction, identity=item.identity, scope=scope)

    def _removed_whole(self, key: ObjectKey, record: _TargetRecord) -> bool:
        """Whether the pending writes of ``key`` remove everything its
        admissions opened, so a further insertion of it is a first opening.

        An insertion still pending is removed whole only from beyond a barrier,
        since a removal beside it cancels it instead. A Non-Temporal or
        Transaction-Time-Only removal there already counts the insertion as
        stored, so only a Bitemporal opening is judged here: the writes buffered
        after it must destroy all the coverage it opens.
        """
        if not record.pending_insert:
            return record.stored and self._removes_stored(key, record)
        if not record.bitemporal or self._pending.folds_into_opening(key):
            return False
        window = record.valid_time_window
        assert window is not None  # a Bitemporal opening states its window
        return (
            window.first_uncovered(self._pending.destroyed_coverage(key, after_opening=True))
            is None
        )

    def _removes_stored(self, key: ObjectKey, record: _TargetRecord) -> bool:
        """Whether the pending writes of ``key`` remove everything its admitted
        insertions left stored.

        A Non-Temporal row is removed whole by a pending delete, and so is a
        Transaction-Time-Only object by a termination. A Bitemporal object's
        stored coverage lies between its earliest admitted anchor and the latest
        end among the rows those admissions opened, so the pending writes must
        destroy all of that window.
        """
        if not record.bitemporal:
            return self._pending.removes(key)
        window = self._targets.removal_window(record)
        return window.first_uncovered(self._pending.destroyed_coverage(key)) is None

    def insertion_identity(self, target: ObjectKey) -> InsertionIdentity | None:
        """The authority the standing admitted insertion of ``target`` grants,
        or ``None`` where none stands — the identity a source the insertion was
        stated through carries from then on."""
        self._ensure_open()
        record = self._targets.record(target)
        return None if record is None else record.identity

    def insertion_authority(
        self, identity: InsertionIdentity
    ) -> TimeInterval | NoInsertionAuthority | None:
        """The Valid-Time window the insertion ``identity`` names was admitted
        with — whose start is where a write it authorizes starts — while its
        authority stands in this unit of work, ``None`` for a standing insertion
        of an object without Valid Time, or :data:`NO_INSERTION_AUTHORITY` once
        it does not stand: never issued here, retired by the complete removal of
        what it opened, or superseded by a later insertion of the same
        object."""
        self._ensure_open()
        record = self._targets.authority(identity)
        return NO_INSERTION_AUTHORITY if record is None else record.valid_time_window

    def opened_by(self, target: ObjectKey) -> Hashable | None:
        """The label of the admitted insertion of ``target`` that a further
        insertion of it would repeat, or ``None`` where an insertion of it is a
        first opening.

        An insertion still pending is repeated by another; so is one whose
        coverage is stored and survives what is pending. Once everything the
        object's admissions opened has been removed — or a pending write
        removes all of it — the object can be inserted again.
        """
        self._ensure_open()
        record = self._targets.record(target)
        if record is None or self._removed_whole(target, record):
            return None
        return record.opener if record.pending_insert or record.stored else None

    def _addressed_object(self, item: BufferItem) -> ObjectKey | None:
        """The one object ``item`` addresses where buffering needs it — to claim
        it, or to open or cancel a pending insert of it — derived once."""
        if isinstance(item, MaterializedWriteGroup):
            return None
        if isinstance(item, InsertionKeyedWrite):
            return item.identity.object_key
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
        elif isinstance(item, InsertionKeyedWrite):
            scope = item.scope
        else:
            return
        if scope is None or keyed_intent(item.instruction) is None:
            return
        object_scope = scope if isinstance(scope, ObjectKey) else scope.object
        conditioned = self._pending.target_scope(object_scope)
        if (
            self._claims.held(scope) is None
            and conditioned in (None, scope)
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

    def _claim_composed(self, item: ObservedKeyedWrite | InsertionKeyedWrite) -> None:
        """Admit a temporal object's write against existing coverage into
        composition with the object's pending writes, or refuse it
        (`m-unit-work` "Observed-State Coalescing").

        Judged over every write of the object still pending, whatever state
        each observed, before anything changes. A write an insertion
        authorized of an object whose insert is still pending composes with
        that opening instead, which buffering has already judged.
        """
        instruction = item.instruction
        if isinstance(item, InsertionKeyedWrite):
            key: ObjectKey | None = item.identity.object_key
            scope = None
        else:
            key = resolve_object_key(instruction, inheritance.view(self.meta))
            scope = None if item.claim is None else item.claim.key
        assert key is not None  # such a write names one object
        if not self._pending.admits_temporal(item, key) or (
            scope is not None and self._claims.held(scope) is not None
        ):
            raise _already_claimed(instruction.target, key)

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
            counts_unchanged_rows=self.settings.counts_unchanged_rows,
        )
        finalized = self._planner.finalize(request)
        sources = self._pending.sources()
        removed = self._pending.removals()
        self._pending.clear()
        self._claims.clear()
        self._targets.end_flush(removed)
        units = finalized.plan.units
        self._reporting = units
        self._reported = 0
        try:
            self.flush_executor(
                finalized.plan,
                trigger=trigger,
                bind_deferred=self._bind_deferred,
                completed=self._report,
            )
            for unit in units[self._reported :]:
                self._report(unit, None)
            for source in sources:
                source.consume()
        except BaseException as failure:
            self.mark_rollback_only(failure)
            raise
        finally:
            self._reporting = ()
            self._targets.release_continuity()

    def _bind_deferred(
        self, description: DeferredRange, rows: PredecessorRows | None, /
    ) -> BoundRange:
        """Bind a deferred range of the running flush under this attempt's
        current ownership and continuity proofs — those every earlier unit
        published — and its configured provenance decoration."""
        return self._planner.bind_deferred(
            description,
            rows,
            ownership=self._targets,
            actor_identity=self._actor_identity,
            transaction_instant=self._transaction_instant,
        )

    def _report(
        self,
        unit: ExecutionUnit,
        bound: BoundRange | None,
        /,
        *,
        allocated: tuple[object, ...] = (),
    ) -> None:
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
        if len(allocated) != len(unit.opened.allocated):
            raise UnitOfWorkError(
                f"an execution unit opening {len(unit.opened.allocated)} row(s) whose keys the "
                f"database allocates was reported with {len(allocated)} key(s)"
            )
        self._reported = reported + 1
        self._complete(unit, unit if bound is None else bound, allocated)

    def _complete(
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
        opened = effects.opened
        self._targets.complete(
            effects.removed,
            _with_allocated(opened, allocated) if allocated else opened,
            effects.derived,
            effects.concludes,
        )

    def _invalidate(self, key: ObservedStateKey, stamp: int) -> None:
        held = self._observations.get(key)
        if held is not None:
            held.invalidate()
        self._changed[key] = stamp
        if isinstance(key, VersionedStateKey):
            self._targets.advanced(key)

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


def _already_claimed(target: EntityMetadata, key: ObjectKey) -> WriteEvidenceError:
    return WriteEvidenceError(
        code="write-evidence-already-claimed",
        message=(
            f"{target.identity.canonical}: a write already buffered in this transaction cannot "
            "be composed with this one — an assignment after a destructive intent over its "
            "window resurrects nothing, a destructive intent composes only with writes of "
            "exactly its own window, and a predicate write's selected rows are one compact "
            "group; read the row through this transaction to flush the buffered intent and "
            "settle against fresh state"
        ),
        object_key=key,
    )


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
