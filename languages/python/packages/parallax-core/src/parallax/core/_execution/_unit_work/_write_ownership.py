from __future__ import annotations

import bisect
import datetime as dt
from collections.abc import Iterable, Iterator
from typing import Final, Literal, final

from parallax.core._execution._unit_work.retain import InsertionIdentity, KeyedWriteRefusalAdvice
from parallax.core.base import INFINITY, TemporalBound
from parallax.core.metamodel import EntityIdentity
from parallax.core.temporal_read import TimeInterval
from parallax.core.write_plan.keys import ObjectKey, ObjectStateKey
from parallax.core.write_plan.plan import Derivation, Descent, Openings, OwnedEndpoint
from parallax.core.write_plan.steps import Finite

__all__ = ["InsertionRecord", "PendingInsertionState", "WriteOwnership"]

type PendingInsertionState = Literal["opening", "before_removal", "ended_opening"]
"""How an insertion of the buffer stands, while the buffer links it.

``opening`` is the object's current insertion, still to execute; a write folds
into it only from its own barrier region. ``before_removal`` is an insertion a
later write of the buffer removes whole, already counted as stored.
``ended_opening`` is a Bitemporal opening whose writes left nothing of it while
a composed replacement still reaches the object's older stored coverage, so it
folds nothing and its object is opened again only after that replacement.
"""


class InsertionRecord:
    """What one attempt holds about one object it inserted.

    ``insertion_advice`` is the refusal advice the latest insertion's opener
    supplied, kept for a repeat's diagnostics, and ``valid_time_window`` is the
    window it was admitted with, ``None`` for an object without Valid Time — its
    start is the anchor every write it authorizes starts at. ``identity`` is the
    authority that insertion grants while it stands, and ``None`` once its
    complete removal retired it. ``pending_position`` and ``pending_state`` link
    the insertion to the buffer that buffered it, at its position there,
    until the buffer drains or composition cancels it.

    What survives of the object's admitted insertions is counted where it is
    stored: ``stored_count`` — the owned current rows an admission of the
    object opened, by their tags — for a Bitemporal object, whose coverage a
    write can remove in part, and zero or one for any other, which a removal
    takes whole. ``earliest_stored_anchor`` is the earliest anchor of any
    admission whose coverage may still be stored — once a flush executes an
    insertion, its own anchor, since what an earlier admission opened was
    removed before it — and ``advanced_from`` the version the last completed
    update of a versioned row advanced from. ``cached_removal_window`` keeps the
    stored removal window once it is asked for
    (:meth:`WriteOwnership.removal_window`), until what it derives from
    changes. A record lasts until the attempt ends, whatever became of the
    insertion: it is also the fact that this attempt admitted one.
    """

    __slots__ = (
        "advanced_from",
        "cached_removal_window",
        "earliest_stored_anchor",
        "identity",
        "insertion_advice",
        "pending_position",
        "pending_state",
        "stored_count",
        "valid_time_window",
    )

    def __init__(
        self,
        insertion_advice: KeyedWriteRefusalAdvice | None,
        valid_time_window: TimeInterval | None,
        identity: InsertionIdentity,
        pending_position: int,
    ) -> None:
        self.insertion_advice = insertion_advice
        self.valid_time_window = valid_time_window
        self.identity: InsertionIdentity | None = identity
        self.pending_position: int | None = pending_position
        self.pending_state: PendingInsertionState | None = "opening"
        self.stored_count = 0
        self.earliest_stored_anchor = _window_start(valid_time_window)
        self.advanced_from: int | None = None
        self.cached_removal_window: TimeInterval | _Uncomputed = _UNCOMPUTED

    def set_earliest_stored_anchor(self, anchor: dt.datetime | None) -> None:
        if anchor != self.earliest_stored_anchor:
            self.earliest_stored_anchor = anchor
            self.cached_removal_window = _UNCOMPUTED

    @property
    def has_stored_coverage(self) -> bool:
        """Whether anything an admitted insertion of the object opened may
        still be stored."""
        return self.stored_count > 0

    def unlink(self) -> None:
        self.pending_position = None
        self.pending_state = None


@final
class _Uncomputed:
    """The removal window a record has not derived since what it derives from
    last changed — distinct from every window, and from a missing Valid-Time
    axis."""

    __slots__ = ()


_UNCOMPUTED: Final = _Uncomputed()


def _window_start(window: TimeInterval | None) -> dt.datetime | None:
    return None if window is None else window.start


type _ObjectAddress = tuple[EntityIdentity, tuple[object, ...]]

type _InsertionTag = tuple[InsertionIdentity, tuple[TimeInterval, ...] | None]
"""The admission an owned row continues, and the parts of the row it
contributed in order, ``None`` where it contributed the whole row."""


class WriteOwnership:
    """The attempt's write-owned facts about the objects it writes.

    Each target's admitted insertion, and every current temporal row the
    attempt successfully opened, by complete physical address. A row of a
    Bitemporal object that continues an admission standing when it opens — the
    admission's own insert, or a successor of the part of a row an admission
    contributed — is tagged with that admission's identity, and with the parts
    of it the admission contributed where that is not the whole row; a
    successor of coverage no admission opened is not. Reads never add to it,
    so its size follows what the attempt wrote rather than what it read.
    """

    __slots__ = ("_addresses", "_continuity", "_endpoints", "_records", "_tags")

    def __init__(self) -> None:
        self._records: dict[ObjectKey, InsertionRecord] = {}
        # The Bitemporal records again, by the address an owned row names its
        # object with, so tagging a row needs no key of its own.
        self._addresses: dict[_ObjectAddress, InsertionRecord] = {}
        self._endpoints: set[OwnedEndpoint] = set()
        self._tags: dict[OwnedEndpoint, _InsertionTag] = {}
        # What settled writes of the running flush proved for later ones, allocated by
        # the first write that records anything and released once no object's
        # proofs remain, or when the flush ends however it ends.
        self._continuity: _FlushContinuity | None = None

    def owns(self, endpoint: OwnedEndpoint, /) -> bool:
        return endpoint in self._endpoints

    def continues_insertion(self, endpoint: OwnedEndpoint, /) -> bool:
        return endpoint in self._tags

    def insertion_coverage(
        self, endpoint: OwnedEndpoint, valid_time_coverage: TimeInterval | None, /
    ) -> tuple[TimeInterval | None, ...]:
        tag = self._tags.get(endpoint) if self._tags else None
        if tag is None:
            return ()
        parts = tag[1]
        if parts is None or valid_time_coverage is None:
            return (valid_time_coverage,)
        return tuple(
            part
            for part in (part.intersection(valid_time_coverage) for part in parts)
            if part is not None
        )

    def proven(self, original: ObjectStateKey, /) -> Derivation | None:
        continuity = self._continuity
        proofs = None if continuity is None else continuity.proofs.get(original.object)
        return None if proofs is None else proofs.get(original)

    def descendants(
        self, original: ObjectStateKey, valid_time_window: TimeInterval | None, /
    ) -> Iterator[tuple[OwnedEndpoint, Descent]]:
        continuity = self._continuity
        assert continuity is not None  # a proven original's rows are kept
        descents = continuity.descents
        for endpoint, contributed in continuity.lineage[original].reaching(valid_time_window):
            if valid_time_window is None or (
                contributed is not None and contributed.overlaps(valid_time_window)
            ):
                yield endpoint, descents[endpoint]

    def descent(self, endpoint: OwnedEndpoint, /) -> Descent | None:
        continuity = self._continuity
        return None if continuity is None else continuity.descents.get(endpoint)

    def insertion_record(self, target: ObjectKey) -> InsertionRecord | None:
        return self._records.get(target)

    def authorized_insertion(self, identity: InsertionIdentity) -> InsertionRecord | None:
        """The record whose standing authority ``identity`` is, if any."""
        record = self._records.get(identity.object_key)
        return record if record is not None and record.identity is identity else None

    def open_insert(
        self,
        target: ObjectKey,
        insertion_advice: KeyedWriteRefusalAdvice | None,
        valid_time_window: TimeInterval | None,
        pending_position: int,
    ) -> InsertionRecord:
        """Admit an insertion of ``target`` pending at ``pending_position``,
        superseding the authority of any earlier one, and answer its record."""
        identity = InsertionIdentity(target)
        record = self._records.get(target)
        if record is None:
            record = InsertionRecord(
                insertion_advice, valid_time_window, identity, pending_position
            )
            self._records[target] = record
            if valid_time_window is not None:
                self._addresses[_address(target)] = record
            return record
        if not record.has_stored_coverage:
            record.set_earliest_stored_anchor(_window_start(valid_time_window))
        record.insertion_advice = insertion_advice
        record.valid_time_window = valid_time_window
        record.identity = identity
        record.pending_position = pending_position
        record.pending_state = "opening"
        record.advanced_from = None
        return record

    def removal_window(self, record: InsertionRecord) -> TimeInterval:
        """The Valid Time a removal of everything a Bitemporal ``record``'s
        admissions left stored must destroy: from its earliest stored anchor to
        the latest end among the owned rows they opened, the open bound
        included.

        It encloses that coverage rather than tracing it, and is derived when
        first asked, then kept on the record until a row it derives from is
        tagged or retired or the anchor moves.
        """
        removal = record.cached_removal_window
        if isinstance(removal, TimeInterval):
            return removal
        anchor = record.earliest_stored_anchor
        assert anchor is not None  # a Bitemporal opening states its start
        removal = record.cached_removal_window = TimeInterval(anchor, self._latest_end(record))
        return removal

    def _latest_end(self, record: InsertionRecord) -> dt.datetime | Literal[TemporalBound.INFINITY]:
        """The latest Valid-Time end among the coverage ``record``'s admissions
        contributed to owned rows — a whole row's physical end read as its
        managed endpoint, a contributed part's own end — the open bound where
        one runs on, or where none is tagged."""
        latest: dt.datetime | None = None
        for endpoint, (_identity, parts) in self._tags.items():
            if self._addresses.get((endpoint.entity, endpoint.key)) is not record:
                continue
            if parts is None:
                end = endpoint.ends[0]
                if not isinstance(end, Finite):
                    return INFINITY
                instant = end.instant
            else:
                instant = parts[-1].end
                if instant is INFINITY:
                    return INFINITY
            assert isinstance(instant, dt.datetime)  # a finite Valid-Time end is an instant
            if latest is None or instant > latest:
                latest = instant
        return INFINITY if latest is None else latest

    def complete(
        self,
        removed: Iterable[OwnedEndpoint],
        opened: Openings,
        derived: tuple[Derivation, ...] = (),
        concludes: ObjectKey | None = None,
    ) -> None:
        """Retire the owned rows one settled write removed, then register the
        rows it opened, each tagged with the parts an admission contributed to
        it, or no longer tagged where it names a row again that none did. An
        admission whose last tagged row the write removed or untagged is retired
        only if no row the write opened continues it.

        Each original the write ``derived`` rows from that stood before the
        flush began is proven until the object's last consumer — the write that
        ``concludes`` it — completes, or the flush ends, and each row it derived
        descends from it over the part it contributed; a row derived from one
        an earlier settled write of the flush derived descends from the originals that
        one did, each over the part of the row that came from its own
        contribution."""
        continuity = self._continuity
        if derived and continuity is None:
            continuity = self._continuity = _FlushContinuity()
        inherited = continuity.inherited(derived) if continuity is not None else ()
        drained = self._retire(removed, continuity)
        self._open(opened, drained)
        for record, tag in drained:
            if (
                not record.stored_count
                and record.identity is tag
                and record.pending_state != "opening"
            ):
                # Nothing this admission contributed is left: it was removed
                # completely, and its authority ends with it.
                record.identity = None
        if continuity is not None:
            continuity.derive(derived, inherited)
            if concludes is not None:
                continuity.release(concludes)
                if not continuity.proofs:
                    self._continuity = None

    def _open(
        self, opened: Openings, drained: list[tuple[InsertionRecord, InsertionIdentity]]
    ) -> None:
        """Register each row ``opened`` names, tagged with what an admission
        contributed to it and with nothing where it names none."""
        for endpoint in opened.fresh:
            self._register(endpoint)
            if self._tags:
                self._untag(endpoint, drained)
        for endpoint in opened.continued:
            self._register(endpoint)
            self._tag(endpoint, None, drained)
        for endpoint, parts in opened.shared:
            self._register(endpoint)
            self._tag(endpoint, parts, drained)

    def _retire(
        self, removed: Iterable[OwnedEndpoint], continuity: _FlushContinuity | None
    ) -> list[tuple[InsertionRecord, InsertionIdentity]]:
        """Retire each removed row, answering every admission whose last tagged
        row went with them."""
        drained: list[tuple[InsertionRecord, InsertionIdentity]] = []
        for endpoint in removed:
            self._endpoints.remove(endpoint)  # planning removes only a row this attempt owns
            if continuity is not None:
                continuity.forget(endpoint)
            if self._tags:
                self._untag(endpoint, drained)
        return drained

    def release_continuity(self) -> None:
        """End the flush's proofs: no later submission carries them."""
        self._continuity = None

    def _register(self, endpoint: OwnedEndpoint) -> None:
        self._endpoints.add(endpoint)

    def _tag(
        self,
        endpoint: OwnedEndpoint,
        parts: tuple[TimeInterval, ...] | None,
        drained: list[tuple[InsertionRecord, InsertionIdentity]],
    ) -> None:
        """Tag ``endpoint`` with the standing admission of its object over
        ``parts`` of it, the whole row where ``None``, replacing any tag it
        held."""
        record = self._addresses.get((endpoint.entity, endpoint.key))
        if record is None or record.identity is None:
            if self._tags:
                self._untag(endpoint, drained)
            return
        if endpoint not in self._tags:
            record.stored_count += 1
        self._tags[endpoint] = (record.identity, parts)
        record.cached_removal_window = _UNCOMPUTED

    def _untag(
        self, endpoint: OwnedEndpoint, drained: list[tuple[InsertionRecord, InsertionIdentity]]
    ) -> None:
        tag = self._tags.pop(endpoint, None)
        if tag is not None:
            self._drain(endpoint, tag[0], drained)

    def _drain(
        self,
        endpoint: OwnedEndpoint,
        identity: InsertionIdentity,
        drained: list[tuple[InsertionRecord, InsertionIdentity]],
    ) -> None:
        record = self._addresses[(endpoint.entity, endpoint.key)]
        record.stored_count -= 1
        record.cached_removal_window = _UNCOMPUTED
        if not record.stored_count:
            drained.append((record, identity))

    def clear(self) -> None:
        self._records.clear()
        self._addresses.clear()
        self._endpoints.clear()
        self._tags.clear()
        self.release_continuity()


class _FlushContinuity:
    """What the running flush's settled writes proved for later settled writes of the same
    objects: each original transformed under protection that stood before the
    flush began, which current row descends from which of them over which part
    of it, and each one's contributed parts of current rows in Valid-Time
    order."""

    __slots__ = ("descents", "lineage", "proofs")

    def __init__(self) -> None:
        self.proofs: dict[ObjectKey, dict[ObjectStateKey, Derivation]] = {}
        self.descents: dict[OwnedEndpoint, Descent] = {}
        self.lineage: dict[ObjectStateKey, _Lineage] = {}

    def inherited(
        self, derived: tuple[Derivation, ...]
    ) -> tuple[tuple[tuple[ObjectStateKey, TimeInterval | None], ...] | None, ...]:
        """The originals, each over its part, each one in ``derived`` was itself
        derived from earlier in the flush, if any, read before the write's
        removals retire it."""
        descents = self.descents
        inherited: list[tuple[tuple[ObjectStateKey, TimeInterval | None], ...] | None] = []
        for derivation in derived:
            owned = derivation.owned
            descent = None if owned is None else descents.get(owned)
            inherited.append(None if descent is None else descent.contributions)
        return tuple(inherited)

    def derive(
        self,
        derived: tuple[Derivation, ...],
        inherited: tuple[tuple[tuple[ObjectStateKey, TimeInterval | None], ...] | None, ...],
    ) -> None:
        """Record each row ``derived`` names as descending from its originals.

        A row derived from an original no earlier settled write derived descends from
        that original over the part it contributed. One derived from a row an
        earlier settled write derived descends from that row's own originals, each over
        the part of the contribution that came from its own part, never over
        the rest. A row revised in place, or derived from several originals, is
        re-derived at its own address, so what it descended from is forgotten
        before any row is added again."""
        for derivation in derived:
            for row in derivation.rows:
                self.forget(row.endpoint)
        contributions: dict[OwnedEndpoint, list[tuple[ObjectStateKey, TimeInterval | None]]] = {}
        coverages: dict[OwnedEndpoint, TimeInterval | None] = {}
        for derivation, earlier in zip(derived, inherited, strict=True):
            original = derivation.original
            if earlier is None:
                self.proofs.setdefault(original.object, {})[original] = derivation
                if original not in self.lineage:  # kept even where it contributed no row
                    self.lineage[original] = _Lineage()
                sources: tuple[tuple[ObjectStateKey, TimeInterval | None], ...] = (
                    (original, derivation.valid_time_coverage),
                )
            else:
                sources = earlier
            for row in derivation.rows:
                coverages[row.endpoint] = row.valid_time_coverage
                _contribute(contributions.setdefault(row.endpoint, []), row.contributed, sources)
        for endpoint, parts in contributions.items():
            if not parts:  # only coverage no proven original held, such as a gap opened
                continue
            joined = _joined(parts)
            self.descents[endpoint] = Descent(coverages[endpoint], joined)
            for source, contributed in joined:
                self.lineage[source].add(endpoint, contributed)

    def forget(self, endpoint: OwnedEndpoint) -> None:
        descent = self.descents.pop(endpoint, None)
        if descent is not None:
            for original, contributed in descent.contributions:
                self.lineage[original].discard(endpoint, contributed)

    def release(self, target: ObjectKey) -> None:
        """Drop everything proven about ``target``: its last consumer is done."""
        descents = self.descents
        lineage = self.lineage
        for original in self.proofs.pop(target, ()):
            for endpoint, _contributed in lineage.pop(original).rows:
                descents.pop(endpoint, None)


def _contribute(
    parts: list[tuple[ObjectStateKey, TimeInterval | None]],
    contributed: TimeInterval | None,
    sources: tuple[tuple[ObjectStateKey, TimeInterval | None], ...],
) -> None:
    """Add to ``parts`` each of ``sources`` over the part of ``contributed`` its
    own part shares — every one on a Transaction-Time-Only object, where both
    are ``None`` — and none over Valid Time it does not share."""
    for source, part in sources:
        if contributed is None or part is None:
            parts.append((source, None))
            continue
        shared = contributed.intersection(part)
        if shared is not None:
            parts.append((source, shared))


def _joined(
    parts: list[tuple[ObjectStateKey, TimeInterval | None]],
) -> tuple[tuple[ObjectStateKey, TimeInterval | None], ...]:
    """``parts`` in Valid-Time order, each original's adjacent parts one."""
    if len(parts) < 2:
        return tuple(parts)
    parts.sort(key=_part_start)
    joined: list[tuple[ObjectStateKey, TimeInterval | None]] = []
    for original, contributed in parts:
        if joined:
            previous, earlier = joined[-1]
            if (
                previous == original
                and earlier is not None
                and contributed is not None
                and earlier.meets(contributed)
            ):
                joined[-1] = (original, TimeInterval(earlier.start, contributed.end))
                continue
        joined.append((original, contributed))
    return tuple(joined)


def _part_start(part: tuple[ObjectStateKey, TimeInterval | None]) -> dt.datetime:
    return _lineage_key(part[1])


class _Lineage:
    """The parts of current rows one proven original contributed, in
    Valid-Time order.

    They are pieces of one original's coverage and so never overlap, which is
    what lets a range find the ones its window may reach by their starts alone
    rather than by visiting every row the original's settled writes left. A row that
    merged several contributors appears once per part this original
    contributed. An original without Valid Time has one current row at a time,
    keyed at the earliest instant.
    """

    __slots__ = ("_keys", "_rows")

    def __init__(self) -> None:
        self._keys: list[dt.datetime] = []
        self._rows: list[tuple[OwnedEndpoint, TimeInterval | None]] = []

    def add(self, endpoint: OwnedEndpoint, contributed: TimeInterval | None) -> None:
        key = _lineage_key(contributed)
        position = bisect.bisect_right(self._keys, key)
        self._keys.insert(position, key)
        self._rows.insert(position, (endpoint, contributed))

    def discard(self, endpoint: OwnedEndpoint, contributed: TimeInterval | None) -> None:
        position = bisect.bisect_left(self._keys, _lineage_key(contributed))
        assert self._rows[position][0] == endpoint  # no two contributed parts share a start
        del self._keys[position]
        del self._rows[position]

    @property
    def rows(self) -> list[tuple[OwnedEndpoint, TimeInterval | None]]:
        return self._rows

    def reaching(
        self, window: TimeInterval | None
    ) -> Iterator[tuple[OwnedEndpoint, TimeInterval | None]]:
        """The parts that may overlap ``window``, every one where it is
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


def _address(target: ObjectKey) -> _ObjectAddress:
    return (target.entity, tuple(value for _name, value in target.primary_key))
