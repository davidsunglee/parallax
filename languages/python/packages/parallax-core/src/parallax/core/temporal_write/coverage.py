from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final, Literal, cast

from parallax.core.base import INFINITY, TemporalBound
from parallax.core.temporal_read import TimeInterval

type _Cursor = dt.datetime | Literal[TemporalBound.INFINITY]

__all__ = [
    "CARRIED_HEAD",
    "CARRIED_TAIL",
    "NO_TRANSFORM",
    "WITHIN",
    "CoverageGap",
    "CoverageSegment",
    "CoverageTransform",
    "Successor",
]

CARRIED_HEAD: Final = 1
"""The carried successor before a one-segment transform's window."""

WITHIN: Final = 2
"""The assigned successor inside a one-segment transform's window."""

CARRIED_TAIL: Final = 4
"""The carried successor after a one-segment transform's window."""


@dataclass(frozen=True, slots=True)
class CoverageSegment:
    """One requested Valid-Time interval of a finalized transform, and what every
    existing interval inside it becomes.

    ``valid_time_window`` is the segment's extent, or ``None`` on a
    Transaction-Time-Only target, whose one segment spans the whole axis.
    ``assigned`` maps each assigned member's declared name to its managed value,
    the last authored value per member, or is ``None`` where the segment
    destroys existing coverage. ``replaces`` marks a replacement's extent:
    ``assigned`` there is a complete state, which a gap in existing coverage
    takes too.
    """

    valid_time_window: TimeInterval | None
    assigned: Mapping[str, object] | None
    replaces: bool = False


@dataclass(frozen=True, slots=True)
class Successor:
    """One nonempty interval of one predecessor's coverage after a transform:
    the predecessor's own state where ``assigned`` is ``None`` (carried), or that
    state with ``assigned`` overlaid (changed). ``valid_time_coverage`` is
    ``None`` on a Transaction-Time-Only target."""

    valid_time_coverage: TimeInterval | None
    assigned: Mapping[str, object] | None


@dataclass(frozen=True, slots=True)
class CoverageGap:
    """One nonempty interval of a replacement's extent no existing coverage
    holds, and the complete state a new lineage opens there."""

    valid_time_window: TimeInterval
    assigned: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class CoverageTransform:
    """What a target's composed writes do to its existing coverage, decided
    before any coverage is known.

    ``segments`` are disjoint and ordered by start. Outside them every existing
    interval is carried unchanged; inside one, each existing interval keeps its
    own unassigned members and takes the segment's assignments, or is destroyed.
    Gaps stay gaps, except inside a replacement's extent, where a gap takes the
    complete replacement state; no other segment creates coverage.
    """

    segments: tuple[CoverageSegment, ...] = ()

    def followed_by(
        self,
        window: TimeInterval | None,
        assigned: Mapping[str, object] | None,
        *,
        replaces: bool,
    ) -> CoverageTransform:
        """This transform followed by one more write over ``window`` — the whole
        axis where it is ``None`` — which assigns ``assigned`` there, later
        values winning per member, or destroys coverage there when ``assigned``
        is ``None``.

        A write that ``replaces`` states a complete state, and its window becomes
        a replacement's extent. A later assignment over that extent keeps it, so
        the extent's gaps take the overlaid state; a destruction ends it, so no
        coverage is created only to be destroyed.

        A destroyed interval is never assigned again: admission refuses such a
        resurrection before a transform is asked for it.
        """
        if window is None:
            previous = self.segments[0] if self.segments else None
            return CoverageTransform((_overlaid(None, previous, assigned, replaces=replaces),))
        composed: list[CoverageSegment] = []
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
                composed.append(CoverageSegment(head, segment.assigned, segment.replaces))
            if cursor is not INFINITY and overlap.starts_after(cursor):
                stretch = window.clipped(start=cursor, end=overlap.start)
                composed.append(CoverageSegment(stretch, assigned, replaces))
            composed.append(_overlaid(overlap, segment, assigned, replaces=replaces))
            end = window.end
            if end is not INFINITY and extent.ends_after(end):
                tail = extent.clipped(start=end)
                composed.append(CoverageSegment(tail, segment.assigned, segment.replaces))
            cursor = overlap.end
        _rest(composed, window, cursor, assigned, replaces)
        return CoverageTransform(_joined(composed))

    @property
    def valid_time_window(self) -> TimeInterval | None:
        """The one Valid-Time interval from the first segment's start to the
        last one's end — gaps between segments included, so it is a window
        rather than a claim of continuous coverage — or ``None`` on a
        Transaction-Time-Only target. A single segment answers its own extent;
        a caller needing it repeatedly derives it once."""
        first = self.segments[0].valid_time_window
        last = self.segments[-1].valid_time_window
        if first is None or last is None or last is first:
            return first
        return TimeInterval(first.start, last.end)

    @property
    def assigns(self) -> bool:
        """Whether some segment assigns rather than destroys."""
        return any(segment.assigned is not None for segment in self.segments)

    def successors_of(self, coverage: TimeInterval | None) -> tuple[Successor, ...]:
        """The nonempty intervals one predecessor covering ``coverage`` becomes;
        ``coverage`` is ``None`` on a Transaction-Time-Only target."""
        if coverage is None:
            (segment,) = self.segments
            assigned = segment.assigned
            return () if assigned is None else (Successor(None, assigned),)
        successors: list[Successor] = []
        cursor = coverage.start
        for segment in self.segments:
            extent = segment.valid_time_window
            assert extent is not None  # every segment of a Valid-Time transform has an extent
            overlap = extent.intersection(coverage)
            if overlap is None:
                continue
            if overlap.starts_after(cursor):
                carried = coverage.clipped(start=cursor, end=overlap.start)
                successors.append(Successor(carried, None))
            if segment.assigned is not None:
                successors.append(Successor(overlap, segment.assigned))
            end = overlap.end
            if end is INFINITY:
                return tuple(successors)
            cursor = end
        if coverage.ends_after(cursor):
            successors.append(Successor(coverage.clipped(start=cursor), None))
        return tuple(successors)

    def successor_positions(self, start: object, end: object) -> int | None:
        """Which successors a predecessor covering ``[start, end)`` keeps under a
        transform of one segment — ``start`` and ``end`` are ``None`` without
        Valid Time — as a union of :data:`CARRIED_HEAD`, :data:`WITHIN`, and
        :data:`CARRIED_TAIL`, in that order by start, or ``None`` where the
        transform does not reach it.

        The answer equals what :meth:`successors_of` decides for the same
        coverage, read from the two bounds alone, so a caller sizing many
        predecessors allocates nothing per predecessor to learn it.
        """
        (segment,) = self.segments
        within = 0 if segment.assigned is None else WITHIN
        window = segment.valid_time_window
        if window is None:
            return within
        first, last = window.start, window.end
        start, end = cast("dt.datetime", start), cast("_Cursor", end)
        if not (_before(start, last) and _before(first, end)):
            return None
        head = CARRIED_HEAD if start < first else 0
        tail = CARRIED_TAIL if last is not INFINITY and _before(last, end) else 0
        return head | within | tail

    def successor_extent(self, position: int, start: object, end: object) -> tuple[object, object]:
        """The Valid-Time bounds of the successor at ``position``
        (:meth:`successor_positions`) of a predecessor covering ``[start,
        end)``; ``(None, None)`` without Valid Time."""
        window = self.segments[0].valid_time_window
        if window is None:
            return None, None
        if position == CARRIED_HEAD:
            return start, window.start
        if position == CARRIED_TAIL:
            return window.end, end
        first, last = window.start, window.end
        later = cast("dt.datetime", start) > first
        earlier = last is INFINITY or (end is not INFINITY and cast("dt.datetime", end) <= last)
        return (start if later else first), (end if earlier else last)

    def reaches(self, coverage: TimeInterval | None) -> bool:
        """Whether some segment overlaps a predecessor covering ``coverage``."""
        if coverage is None:
            return bool(self.segments)
        return any(
            segment.valid_time_window is not None and segment.valid_time_window.overlaps(coverage)
            for segment in self.segments
        )

    def gaps(self, coverage: Iterable[TimeInterval]) -> tuple[CoverageGap, ...]:
        """The nonempty intervals of a replacement's extent that ``coverage`` —
        the existing intervals, disjoint and ordered by start — leaves
        uncovered, each with the complete state it takes there.

        ``coverage`` is consumed once, forward, across every segment: an
        interval reaching past one segment stays current for the next, and a
        segment that replaces nothing consumes none of it. A
        Transaction-Time-Only transform has no Valid Time for a gap to lie on.
        """
        gaps: list[CoverageGap] = []
        remaining = iter(coverage)
        current = next(remaining, None)
        for segment in self.segments:
            window = segment.valid_time_window
            if not segment.replaces or window is None:
                continue
            assigned = segment.assigned
            assert assigned is not None  # a destruction ends a replacement's extent
            cursor = window.start
            while True:
                while current is not None and not current.ends_after(cursor):
                    current = next(remaining, None)
                if current is None:
                    rest = window.clipped(start=cursor)
                    assert rest is not None  # the cursor lies inside the extent
                    gaps.append(CoverageGap(rest, assigned))
                    break
                if current.starts_after(cursor):
                    gap = window.clipped(start=cursor, end=current.start)
                    assert gap is not None  # coverage starts after the cursor, inside the extent
                    gaps.append(CoverageGap(gap, assigned))
                    if not window.ends_after(current.start):
                        break
                covered = current.end
                if covered is INFINITY or not window.ends_after(covered):
                    break
                cursor = covered
                current = next(remaining, None)
        return tuple(gaps)


NO_TRANSFORM: Final[CoverageTransform] = CoverageTransform()


def _before(instant: dt.datetime, end: _Cursor) -> bool:
    return end is INFINITY or instant < end


def _rest(
    composed: list[CoverageSegment],
    window: TimeInterval,
    cursor: _Cursor,
    assigned: Mapping[str, object] | None,
    replaces: bool,
) -> _Cursor:
    """Compose the part of ``window`` from ``cursor`` on that no earlier segment
    reached, where any is left, answering the window's end."""
    if cursor is not INFINITY and window.ends_after(cursor):
        composed.append(CoverageSegment(window.clipped(start=cursor), assigned, replaces))
    return window.end


def _overlaid(
    window: TimeInterval | None,
    previous: CoverageSegment | None,
    assigned: Mapping[str, object] | None,
    *,
    replaces: bool,
) -> CoverageSegment:
    """One write over ``window`` where ``previous`` already stated something, or
    nothing did."""
    if assigned is None:
        return CoverageSegment(window, None)
    if previous is None or previous.assigned is None:
        assert previous is None  # admission refuses an assignment over destroyed coverage
        return CoverageSegment(window, assigned, replaces)
    if replaces:
        return CoverageSegment(window, assigned, replaces=True)
    return CoverageSegment(window, {**previous.assigned, **assigned}, previous.replaces)


def _joined(segments: list[CoverageSegment]) -> tuple[CoverageSegment, ...]:
    """``segments`` with each run of adjacent segments that end up stating the
    same thing joined into one, so a later write over part of an earlier one's
    window never splits coverage that both leave equal."""
    joined: list[CoverageSegment] = []
    for segment in segments:
        previous = joined[-1] if joined else None
        if (
            previous is not None
            and previous.valid_time_window is not None
            and segment.valid_time_window is not None
            and previous.valid_time_window.meets(segment.valid_time_window)
            and previous.assigned == segment.assigned
            and previous.replaces == segment.replaces
        ):
            joined[-1] = CoverageSegment(
                TimeInterval(previous.valid_time_window.start, segment.valid_time_window.end),
                previous.assigned,
                previous.replaces,
            )
        else:
            joined.append(segment)
    return tuple(joined)
