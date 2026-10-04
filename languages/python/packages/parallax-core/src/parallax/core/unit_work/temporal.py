from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from parallax.core.base import INFINITY_LITERAL, TemporalBound, normalize_instant
from parallax.core.metamodel import AsOfAxisMetadata, AttributeIdentity, ValueObjectIdentity
from parallax.core.temporal_read import Bitemporal, TransactionTimeOnly
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

__all__ = [
    "EMPTY_TRANSFORM",
    "BoundPiece",
    "ResolvedSuccessor",
    "TemporalSegment",
    "TemporalTransform",
    "bind_successor",
    "covers",
    "instant_order",
    "is_open_bound",
    "literal_successor",
    "precedes",
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
    valid_from: object | None = None,
    until: object | None = None,
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
                    start=_resolve_bound(successor.valid_window.start, valid_from, until),
                    end=_resolve_bound(successor.valid_window.end, valid_from, until),
                )
            ),
        )
        for successor in successors
    )


def _resolve_bound(
    bound: ValidTimeBound, valid_from: object | None, until: object | None
) -> ResolvedBound:
    match bound:
        case AuthoredFrom():
            assert valid_from is not None  # every windowed mutation authors one
            return _Literal(valid_from)
        case AuthoredUntil():
            assert until is not None  # every bounded mutation authors one
            return _Literal(until)
        case OpenEnd():
            return _Literal(INFINITY_LITERAL)
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
    attributes[shape.transaction_time.end_attribute] = INFINITY_LITERAL
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


def literal_successor(state: SuccessorState, start: object, end: object) -> ResolvedSuccessor:
    """One successor whose Valid-Time bounds are already concrete values, or
    which has no Valid-Time window when both are ``None``."""
    if start is None and end is None:
        return ResolvedSuccessor(state=state)
    return ResolvedSuccessor(
        state=state, window=ResolvedWindow(start=_Literal(start), end=_Literal(end))
    )


def is_open_bound(bound: object) -> bool:
    """Whether one Valid-Time end is the open upper bound."""
    return bound == INFINITY_LITERAL or bound is TemporalBound.INFINITY


def precedes(earlier: object, later: object) -> bool:
    """Whether Valid-Time bound ``earlier`` lies strictly before ``later``, the
    open upper bound after every instant.

    A bound may arrive as a managed instant or in its canonical ISO spelling,
    as a row a case or a fixture states it does; both name one instant.
    """
    if is_open_bound(later):
        return not is_open_bound(earlier)
    if is_open_bound(earlier):
        return False
    return _instant(earlier) < _instant(later)


def instant_order(bound: object) -> float:
    """A sort key placing finite Valid-Time bounds in time order."""
    return _instant(bound).timestamp()


def _instant(bound: object) -> dt.datetime:
    if isinstance(bound, str):
        return normalize_instant(dt.datetime.fromisoformat(bound))
    assert isinstance(bound, dt.datetime)  # a finite Valid-Time bound is an instant
    return normalize_instant(bound)


def _earliest(first: object, second: object) -> object:
    return second if precedes(second, first) else first


def _latest(first: object, second: object) -> object:
    return second if precedes(first, second) else first


@dataclass(frozen=True, slots=True)
class TemporalSegment:
    """One requested Valid-Time interval of a finalized transform, and what every
    existing interval inside it becomes.

    ``start`` and ``end`` are managed bounds, ``end`` the open bound for an
    unbounded window; on a Transaction-Time-Only target both are ``None`` and the
    one segment spans the whole axis. ``assigned`` maps each assigned member's
    declared name to its managed value, the last authored value per member, or
    is ``None`` where the segment destroys existing coverage. ``fills`` marks a
    replacement's extent: ``assigned`` there is a complete state, which a gap in
    existing coverage takes too.
    """

    start: object | None
    end: object | None
    assigned: Mapping[str, object] | None
    fills: bool = False


@dataclass(frozen=True, slots=True)
class BoundPiece:
    """One nonempty interval of one predecessor's coverage after a transform:
    the predecessor's own state where ``assigned`` is ``None``, or that state
    with ``assigned`` overlaid."""

    start: object | None
    end: object | None
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
        valid_from: object | None,
        until: object | None,
        assigned: Mapping[str, object] | None,
        replaces: bool = False,
    ) -> TemporalTransform:
        """This transform followed by one more write over ``[valid_from, until)``
        — the whole axis when ``valid_from`` is ``None`` — which assigns
        ``assigned`` there, later values winning per member, or destroys coverage
        there when ``assigned`` is ``None``.

        A write that ``replaces`` states a complete state, and its window becomes
        a replacement's extent. A later assignment over that extent keeps it, so
        the extent's gaps take the overlaid state; a destruction ends it, so no
        coverage is created only to be destroyed.

        A destroyed interval is never assigned again: admission refuses such a
        resurrection before a transform is asked for it.
        """
        if valid_from is None:
            previous = self.segments[0] if self.segments else None
            return TemporalTransform(
                (_overlaid(None, None, previous, assigned, replaces=replaces),)
            )
        start: object = valid_from
        end: object = INFINITY_LITERAL if until is None else until
        composed: list[TemporalSegment] = []
        cursor = start
        for segment in self.segments:
            if not precedes(segment.start, end) or not precedes(start, segment.end):
                composed.append(segment)
                continue
            if precedes(segment.start, start):
                composed.append(
                    TemporalSegment(segment.start, start, segment.assigned, segment.fills)
                )
            overlap_start = _latest(segment.start, start)
            overlap_end = _earliest(segment.end, end)
            if precedes(cursor, overlap_start):
                composed.append(TemporalSegment(cursor, overlap_start, assigned, replaces))
            composed.append(
                _overlaid(overlap_start, overlap_end, segment, assigned, replaces=replaces)
            )
            if precedes(end, segment.end):
                composed.append(TemporalSegment(end, segment.end, segment.assigned, segment.fills))
            cursor = overlap_end
        if precedes(cursor, end):
            composed.append(TemporalSegment(cursor, end, assigned, replaces))
        composed.sort(key=_segment_order)
        return TemporalTransform(_joined(composed))

    @property
    def start(self) -> object | None:
        """Where the transform's first segment starts."""
        return self.segments[0].start

    @property
    def end(self) -> object | None:
        """Where the transform's last segment ends."""
        return self.segments[-1].end

    @property
    def assigns(self) -> bool:
        """Whether some segment assigns rather than destroys."""
        return any(segment.assigned is not None for segment in self.segments)

    def pieces(self, start: object | None, end: object | None) -> tuple[BoundPiece, ...]:
        """The nonempty intervals one predecessor covering ``[start, end)``
        becomes; both bounds are ``None`` on a Transaction-Time-Only target."""
        if start is None:
            (segment,) = self.segments
            assigned = segment.assigned
            return () if assigned is None else (BoundPiece(None, None, assigned),)
        pieces: list[BoundPiece] = []
        cursor = start
        for segment in self.segments:
            if not precedes(segment.start, end) or not precedes(cursor, segment.end):
                continue
            overlap_start = _latest(segment.start, cursor)
            if precedes(cursor, overlap_start):
                pieces.append(BoundPiece(cursor, overlap_start, None))
            overlap_end = _earliest(segment.end, end)
            if segment.assigned is not None:
                pieces.append(BoundPiece(overlap_start, overlap_end, segment.assigned))
            cursor = overlap_end
        if precedes(cursor, end):
            pieces.append(BoundPiece(cursor, end, None))
        return tuple(pieces)

    def touches(self, start: object | None, end: object | None) -> bool:
        """Whether a predecessor covering ``[start, end)`` lies inside some
        segment."""
        if start is None:
            return bool(self.segments)
        return any(
            precedes(segment.start, end) and precedes(start, segment.end)
            for segment in self.segments
        )

    def gaps(self, coverage: Sequence[tuple[object, object]]) -> tuple[BoundPiece, ...]:
        """The nonempty intervals of a replacement's extent that ``coverage`` —
        the existing intervals, disjoint and ordered by start — leaves
        uncovered, each with the complete state it takes there.

        A Transaction-Time-Only transform has no Valid Time for a gap to lie on.
        """
        pieces: list[BoundPiece] = []
        for segment in self.segments:
            if not segment.fills or segment.start is None:
                continue
            assert segment.assigned is not None  # a destruction ends a replacement's extent
            cursor = segment.start
            for start, end in coverage:
                if not precedes(cursor, segment.end):
                    break
                if not precedes(cursor, end):
                    continue
                if precedes(cursor, start):
                    gap_end = _earliest(start, segment.end)
                    pieces.append(BoundPiece(cursor, gap_end, segment.assigned))
                cursor = end
            if precedes(cursor, segment.end):
                pieces.append(BoundPiece(cursor, segment.end, segment.assigned))
        return tuple(pieces)


EMPTY_TRANSFORM: Final[TemporalTransform] = TemporalTransform()


def covers(
    intervals: tuple[tuple[object, object], ...], start: object, end: object
) -> object | None:
    """The first point of ``[start, end)`` the ordered, disjoint ``intervals``
    leave uncovered, or ``None`` where they cover it whole."""
    cursor = start
    for interval_start, interval_end in intervals:
        if not precedes(cursor, end):
            return None
        if precedes(cursor, interval_start):
            return cursor
        if precedes(cursor, interval_end):
            cursor = interval_end
    return cursor if precedes(cursor, end) else None


def _overlaid(
    start: object | None,
    end: object | None,
    previous: TemporalSegment | None,
    assigned: Mapping[str, object] | None,
    *,
    replaces: bool,
) -> TemporalSegment:
    """One write over ``[start, end)`` where ``previous`` already stated
    something, or nothing did."""
    if assigned is None:
        return TemporalSegment(start, end, None)
    if previous is None or previous.assigned is None:
        assert previous is None  # admission refuses an assignment over destroyed coverage
        return TemporalSegment(start, end, assigned, replaces)
    if replaces:
        return TemporalSegment(start, end, assigned, fills=True)
    return TemporalSegment(start, end, {**previous.assigned, **assigned}, previous.fills)


def _joined(segments: list[TemporalSegment]) -> tuple[TemporalSegment, ...]:
    """``segments`` with each run of adjacent segments that end up stating the
    same thing joined into one, so a later write over part of an earlier one's
    window never splits coverage that both leave equal."""
    joined: list[TemporalSegment] = []
    for segment in segments:
        previous = joined[-1] if joined else None
        if (
            previous is not None
            and previous.end == segment.start
            and previous.assigned == segment.assigned
            and previous.fills == segment.fills
        ):
            joined[-1] = TemporalSegment(
                previous.start, segment.end, previous.assigned, previous.fills
            )
        else:
            joined.append(segment)
    return tuple(joined)


def _segment_order(segment: TemporalSegment) -> dt.datetime:
    return _instant(segment.start)
