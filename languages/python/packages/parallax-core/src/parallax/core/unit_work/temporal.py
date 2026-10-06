from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final, Literal

from parallax.core.base import INFINITY, TemporalBound
from parallax.core.metamodel import AsOfAxisMetadata, AttributeIdentity, ValueObjectIdentity
from parallax.core.temporal_read import Bitemporal, TimeInterval, TransactionTimeOnly
from parallax.core.unit_work.observe import PredecessorRow
from parallax.core.unit_work.planned import (
    NEW_LINEAGE,
    CarriedFrom,
    ChangedFrom,
    InsertEntry,
    InsertOrigin,
    PlannedValue,
    adopt_planned_row,
)
from parallax.core.unit_work.strategy import (
    AuthoredFrom,
    AuthoredState,
    AuthoredUntil,
    CarriedState,
    ChangedState,
    MilestoneSuccessor,
    OpenEnd,
    PredecessorEnd,
    PredecessorStart,
    SuccessorState,
    ValidTimeBound,
)

type _Cursor = dt.datetime | Literal[TemporalBound.INFINITY]

__all__ = [
    "EMPTY_TRANSFORM",
    "BoundPiece",
    "ResolvedSuccessor",
    "TemporalSegment",
    "TemporalTransform",
    "bind_successor",
    "literal_successor",
    "resolve_successors",
    "successor_bounds",
]


@dataclass(frozen=True, slots=True)
class _Literal:
    """One Valid-Time bound already resolved to a group-wide constant."""

    value: object


type ResolvedBound = _Literal | PredecessorStart | PredecessorEnd
"""One successor's Valid-Time bound, resolved as far as group-wide data
allows: a literal value once the mutation's own authored bound or the open
end already decides it, or the Predecessor Start/End marker unchanged when
only a row's own predecessor can supply it."""


@dataclass(frozen=True, slots=True)
class ResolvedWindow:
    """One successor's Valid-Time window with every group-wide bound resolved."""

    start: ResolvedBound
    end: ResolvedBound


@dataclass(frozen=True, slots=True)
class ResolvedSuccessor:
    """One Milestone Successor with every group-wide fact already decided.

    ``state`` fixes the Insert Origin kind (`m-unit-work` "Insert Origin and
    Close Cause"): a resolved successor's ONLY remaining unknowns are one
    row's own predecessor and authored values, which :func:`bind_successor`
    substitutes.
    """

    state: SuccessorState
    window: ResolvedWindow | None = None


def resolve_successors(
    successors: tuple[MilestoneSuccessor, ...],
    *,
    valid_time_window: TimeInterval | None = None,
) -> tuple[ResolvedSuccessor, ...]:
    """``successors`` with every Valid-Time bound group-wide data can decide.

    An authored bound or the open end is the same for every row one
    Materialized Write Group resolves, so binding it here — once, for the
    whole group — is what keeps :func:`bind_successor` a pure per-row data
    substitution rather than a repeated decision.
    """
    return tuple(
        ResolvedSuccessor(
            state=successor.state,
            window=(
                None
                if successor.valid_window is None
                else ResolvedWindow(
                    start=_resolve_bound(successor.valid_window.start, valid_time_window),
                    end=_resolve_bound(successor.valid_window.end, valid_time_window),
                )
            ),
        )
        for successor in successors
    )


def _resolve_bound(bound: ValidTimeBound, window: TimeInterval | None) -> ResolvedBound:
    match bound:
        case AuthoredFrom():
            assert window is not None  # every windowed mutation authors one
            return _Literal(window.start)
        case AuthoredUntil():
            assert window is not None and window.end is not INFINITY  # a bounded mutation's
            return _Literal(window.end)
        case OpenEnd():
            return _Literal(INFINITY)
        case PredecessorStart() | PredecessorEnd():
            return bound


def bind_successor(
    successor: ResolvedSuccessor,
    shape: TransactionTimeOnly | Bitemporal,
    *,
    transaction_instant: object,
    attributes: dict[AttributeIdentity, PlannedValue],
    value_objects: dict[ValueObjectIdentity, object],
    predecessor: PredecessorRow | None,
) -> InsertEntry:
    """One already-resolved successor built directly into its final insert entry.

    Every opened row carries the fresh Transaction-Time interval
    ``[transaction_instant, infinity)``: a successor is always current when it
    is written, whatever Valid-Time window it covers.
    """
    if successor.window is not None:
        assert isinstance(shape, Bitemporal)  # only a Bitemporal topology windows a successor
        valid_time = shape.valid_time
        attributes[valid_time.start_attribute] = _bind_bound(
            successor.window.start, valid_time, predecessor
        )
        attributes[valid_time.end_attribute] = _bind_bound(
            successor.window.end, valid_time, predecessor
        )
    attributes[shape.transaction_time.start_attribute] = transaction_instant
    attributes[shape.transaction_time.end_attribute] = INFINITY
    return InsertEntry(
        row=adopt_planned_row(attributes, value_objects),
        origin=_origin(successor.state, predecessor),
    )


def successor_bounds(
    successor: ResolvedSuccessor, *, predecessor_start: object, predecessor_end: object
) -> tuple[object, object]:
    """The Valid-Time start and end ``successor`` binds, given its predecessor's
    own Valid-Time start and end cells — the values :func:`bind_successor`
    writes, read without building the row."""
    window = successor.window
    assert window is not None  # only a Bitemporal successor binds a window
    return (
        _bound_value(window.start, predecessor_start, predecessor_end),
        _bound_value(window.end, predecessor_start, predecessor_end),
    )


def _bound_value(resolved: ResolvedBound, start: object, end: object) -> object:
    match resolved:
        case _Literal(value):
            return value
        case PredecessorStart():
            return start
        case PredecessorEnd():
            return end


def _origin(state: SuccessorState, predecessor: PredecessorRow | None) -> InsertOrigin:
    match state:
        case AuthoredState():
            return NEW_LINEAGE
        case CarriedState():
            assert predecessor is not None  # a carried successor observed one
            return CarriedFrom(predecessor=predecessor)
        case ChangedState():
            assert predecessor is not None  # a changed successor observed one
            return ChangedFrom(predecessor=predecessor)


def _bind_bound(
    resolved: ResolvedBound, valid_time: AsOfAxisMetadata, predecessor: PredecessorRow | None
) -> object:
    match resolved:
        case _Literal(value):
            return value
        case PredecessorStart():
            assert predecessor is not None
            return predecessor.cell(valid_time.start_attribute)
        case PredecessorEnd():
            assert predecessor is not None
            return predecessor.cell(valid_time.end_attribute)


def literal_successor(state: SuccessorState, coverage: TimeInterval | None) -> ResolvedSuccessor:
    """One successor whose Valid-Time bounds are ``coverage``'s own endpoints,
    or which has no Valid-Time window where ``coverage`` is ``None``."""
    if coverage is None:
        return ResolvedSuccessor(state=state)
    return ResolvedSuccessor(
        state=state,
        window=ResolvedWindow(start=_Literal(coverage.start), end=_Literal(coverage.end)),
    )


@dataclass(frozen=True, slots=True)
class TemporalSegment:
    """One requested Valid-Time interval of a finalized transform, and what every
    existing interval inside it becomes.

    ``valid_time_window`` is the segment's extent, or ``None`` on a
    Transaction-Time-Only target, whose one segment spans the whole axis.
    ``assigned`` maps each assigned member's declared name to its managed value,
    the last authored value per member, or is ``None`` where the segment
    destroys existing coverage. ``fills`` marks a replacement's extent:
    ``assigned`` there is a complete state, which a gap in existing coverage
    takes too.
    """

    valid_time_window: TimeInterval | None
    assigned: Mapping[str, object] | None
    fills: bool = False


@dataclass(frozen=True, slots=True)
class BoundPiece:
    """One nonempty interval of one predecessor's coverage after a transform:
    the predecessor's own state where ``assigned`` is ``None``, or that state
    with ``assigned`` overlaid. ``valid_time_coverage`` is ``None`` on a
    Transaction-Time-Only target."""

    valid_time_coverage: TimeInterval | None
    assigned: Mapping[str, object] | None


@dataclass(frozen=True, slots=True)
class TemporalTransform:
    """What a target's composed observed writes do to its existing coverage,
    decided before any coverage is known.

    ``segments`` are disjoint and ordered by start. Outside them every existing
    interval is carried unchanged; inside one, each existing interval keeps its
    own unassigned members and takes the segment's assignments, or is destroyed.
    Gaps stay gaps, except inside a replacement's extent (``fills``), where a gap
    takes the complete replacement state; no other segment creates coverage.
    """

    segments: tuple[TemporalSegment, ...] = ()

    def then(
        self,
        *,
        valid_time_window: TimeInterval | None,
        assigned: Mapping[str, object] | None,
        replaces: bool = False,
    ) -> TemporalTransform:
        """This transform followed by one more write over ``valid_time_window``
        — the whole axis where it is ``None`` — which assigns ``assigned``
        there, later values winning per member, or destroys coverage there when
        ``assigned`` is ``None``.

        A write that ``replaces`` states a complete state, and its window becomes
        a replacement's extent. A later assignment over that extent keeps it, so
        the extent's gaps take the overlaid state; a destruction ends it, so no
        coverage is created only to be destroyed.

        A destroyed interval is never assigned again: admission refuses such a
        resurrection before a transform is asked for it.
        """
        window = valid_time_window
        if window is None:
            previous = self.segments[0] if self.segments else None
            return TemporalTransform((_overlaid(None, previous, assigned, replaces=replaces),))
        composed: list[TemporalSegment] = []
        # Where the part of the window no earlier segment reaches resumes; the
        # window's end once that part is composed.
        cursor: _Cursor = window.start
        for segment in self.segments:
            extent = segment.valid_time_window
            assert extent is not None  # every segment of a Valid-Time transform has an extent
            overlap = extent.intersection(window)
            if overlap is None:
                if not window.ends_after(extent.start):
                    cursor = _rest(composed, window, cursor, assigned, replaces)
                composed.append(segment)
                continue
            if window.starts_after(extent.start):
                head = extent.clipped(end=window.start)
                composed.append(TemporalSegment(head, segment.assigned, segment.fills))
            if cursor is not INFINITY and overlap.starts_after(cursor):
                stretch = window.clipped(start=cursor, end=overlap.start)
                composed.append(TemporalSegment(stretch, assigned, replaces))
            composed.append(_overlaid(overlap, segment, assigned, replaces=replaces))
            end = window.end
            if end is not INFINITY and extent.ends_after(end):
                tail = extent.clipped(start=end)
                composed.append(TemporalSegment(tail, segment.assigned, segment.fills))
            cursor = overlap.end
        _rest(composed, window, cursor, assigned, replaces)
        return TemporalTransform(_joined(composed))

    def enclosing_window(self) -> TimeInterval | None:
        """The one Valid-Time interval from the first segment's start to the
        last one's end — gaps between segments included, so it is a window
        rather than a claim of continuous coverage — or ``None`` on a
        Transaction-Time-Only target. A single segment answers its own
        extent."""
        first = self.segments[0].valid_time_window
        last = self.segments[-1].valid_time_window
        if first is None or last is None or last is first:
            return first
        return TimeInterval(first.start, last.end)

    @property
    def assigns(self) -> bool:
        """Whether some segment assigns rather than destroys."""
        return any(segment.assigned is not None for segment in self.segments)

    def pieces(self, coverage: TimeInterval | None) -> tuple[BoundPiece, ...]:
        """The nonempty intervals one predecessor covering ``coverage`` becomes;
        ``coverage`` is ``None`` on a Transaction-Time-Only target."""
        if coverage is None:
            (segment,) = self.segments
            assigned = segment.assigned
            return () if assigned is None else (BoundPiece(None, assigned),)
        pieces: list[BoundPiece] = []
        cursor = coverage.start
        for segment in self.segments:
            extent = segment.valid_time_window
            assert extent is not None  # every segment of a Valid-Time transform has an extent
            overlap = extent.intersection(coverage)
            if overlap is None:
                continue
            if overlap.starts_after(cursor):
                carried = coverage.clipped(start=cursor, end=overlap.start)
                pieces.append(BoundPiece(carried, None))
            if segment.assigned is not None:
                pieces.append(BoundPiece(overlap, segment.assigned))
            end = overlap.end
            if end is INFINITY:
                return tuple(pieces)
            cursor = end
        if coverage.ends_after(cursor):
            pieces.append(BoundPiece(coverage.clipped(start=cursor), None))
        return tuple(pieces)

    def touches(self, coverage: TimeInterval | None) -> bool:
        """Whether a predecessor covering ``coverage`` lies inside some
        segment."""
        if coverage is None:
            return bool(self.segments)
        return any(
            segment.valid_time_window is not None and segment.valid_time_window.overlaps(coverage)
            for segment in self.segments
        )

    def gaps(self, coverage: Iterable[TimeInterval]) -> tuple[BoundPiece, ...]:
        """The nonempty intervals of a replacement's extent that ``coverage`` —
        the existing intervals, disjoint and ordered by start — leaves
        uncovered, each with the complete state it takes there.

        ``coverage`` is consumed once, forward, across every segment: an
        interval reaching past one segment stays current for the next, and a
        segment that fills nothing consumes none of it. A Transaction-Time-Only
        transform has no Valid Time for a gap to lie on.
        """
        pieces: list[BoundPiece] = []
        remaining = iter(coverage)
        current = next(remaining, None)
        for segment in self.segments:
            window = segment.valid_time_window
            if not segment.fills or window is None:
                continue
            assigned = segment.assigned
            assert assigned is not None  # a destruction ends a replacement's extent
            cursor = window.start
            while True:
                while current is not None and not current.ends_after(cursor):
                    current = next(remaining, None)
                if current is None:
                    pieces.append(BoundPiece(window.clipped(start=cursor), assigned))
                    break
                if current.starts_after(cursor):
                    pieces.append(
                        BoundPiece(window.clipped(start=cursor, end=current.start), assigned)
                    )
                    if not window.ends_after(current.start):
                        break
                covered = current.end
                if covered is INFINITY or not window.ends_after(covered):
                    break
                cursor = covered
                current = next(remaining, None)
        return tuple(pieces)


EMPTY_TRANSFORM: Final[TemporalTransform] = TemporalTransform()


def _rest(
    composed: list[TemporalSegment],
    window: TimeInterval,
    cursor: _Cursor,
    assigned: Mapping[str, object] | None,
    replaces: bool,
) -> _Cursor:
    """Compose the part of ``window`` from ``cursor`` on that no earlier segment
    reached, where any is left, answering the window's end."""
    if cursor is not INFINITY and window.ends_after(cursor):
        composed.append(TemporalSegment(window.clipped(start=cursor), assigned, replaces))
    return window.end


def _overlaid(
    window: TimeInterval | None,
    previous: TemporalSegment | None,
    assigned: Mapping[str, object] | None,
    *,
    replaces: bool,
) -> TemporalSegment:
    """One write over ``window`` where ``previous`` already stated something, or
    nothing did."""
    if assigned is None:
        return TemporalSegment(window, None)
    if previous is None or previous.assigned is None:
        assert previous is None  # admission refuses an assignment over destroyed coverage
        return TemporalSegment(window, assigned, replaces)
    if replaces:
        return TemporalSegment(window, assigned, fills=True)
    return TemporalSegment(window, {**previous.assigned, **assigned}, previous.fills)


def _joined(segments: list[TemporalSegment]) -> tuple[TemporalSegment, ...]:
    """``segments`` with each run of adjacent segments that end up stating the
    same thing joined into one, so a later write over part of an earlier one's
    window never splits coverage that both leave equal."""
    joined: list[TemporalSegment] = []
    for segment in segments:
        previous = joined[-1] if joined else None
        if (
            previous is not None
            and previous.valid_time_window is not None
            and segment.valid_time_window is not None
            and previous.valid_time_window.meets(segment.valid_time_window)
            and previous.assigned == segment.assigned
            and previous.fills == segment.fills
        ):
            joined[-1] = TemporalSegment(
                TimeInterval(previous.valid_time_window.start, segment.valid_time_window.end),
                previous.assigned,
                previous.fills,
            )
        else:
            joined.append(segment)
    return tuple(joined)
