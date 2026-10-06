"""The Coverage Transform composed writes finalize to, the successors it leaves
of one predecessor's coverage, and the gaps a replacement fills."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest

from parallax.core.base import INFINITY, TemporalBound
from parallax.core.temporal_read import TimeInterval
from parallax.core.temporal_write.coverage import (
    CARRIED_HEAD,
    CARRIED_TAIL,
    NO_TRANSFORM,
    WITHIN,
    CoverageGap,
    CoverageSegment,
    CoverageTransform,
    Successor,
)

_JAN, _FEB, _MAR, _APR, _MAY, _JUN, _JUL, _AUG, _SEP, _OCT, _NOV, _DEC = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in range(1, 13)
)


def _iv(start: dt.datetime, end: dt.datetime | TemporalBound) -> TimeInterval:
    assert end is INFINITY or isinstance(end, dt.datetime)
    return TimeInterval(start, end)


class _Consumed:
    """Ordered coverage that records each interval as it is handed out, so a
    traversal that restarts or reads ahead is visible."""

    def __init__(self, *intervals: TimeInterval) -> None:
        self.intervals = intervals
        self.handed: list[TimeInterval] = []
        self.passes = 0

    def __iter__(self) -> Iterator[TimeInterval]:
        self.passes += 1
        for interval in self.intervals:
            self.handed.append(interval)
            yield interval


def test_a_later_write_wins_where_windows_overlap_and_each_keeps_its_own_elsewhere() -> None:
    transform = NO_TRANSFORM.followed_by(
        _iv(_MAR, _SEP), {"amount": 150, "label": "a"}, replaces=False
    ).followed_by(_iv(_JUN, _NOV), {"amount": 200}, replaces=False)
    assert transform.segments == (
        CoverageSegment(_iv(_MAR, _JUN), {"amount": 150, "label": "a"}),
        CoverageSegment(_iv(_JUN, _SEP), {"amount": 200, "label": "a"}),
        CoverageSegment(_iv(_SEP, _NOV), {"amount": 200}),
    )


def test_an_earlier_window_written_later_still_wins_over_the_overlap() -> None:
    transform = NO_TRANSFORM.followed_by(
        _iv(_JUN, _NOV), {"amount": 200}, replaces=False
    ).followed_by(_iv(_MAR, INFINITY), {"amount": 150}, replaces=False)
    assert transform.segments == (CoverageSegment(_iv(_MAR, INFINITY), {"amount": 150}),)
    assert transform.valid_time_window == _iv(_MAR, INFINITY)


def test_a_write_wholly_before_and_after_existing_segments_keeps_start_order() -> None:
    later = NO_TRANSFORM.followed_by(_iv(_JUN, _SEP), {"amount": 1}, replaces=False)
    assert later.followed_by(_iv(_JAN, _MAR), {"amount": 2}, replaces=False).segments == (
        CoverageSegment(_iv(_JAN, _MAR), {"amount": 2}),
        CoverageSegment(_iv(_JUN, _SEP), {"amount": 1}),
    )
    assert later.followed_by(_iv(_OCT, _DEC), {"amount": 2}, replaces=False).segments == (
        CoverageSegment(_iv(_JUN, _SEP), {"amount": 1}),
        CoverageSegment(_iv(_OCT, _DEC), {"amount": 2}),
    )


def test_a_write_spanning_separate_segments_fills_between_and_around_them() -> None:
    transform = (
        NO_TRANSFORM.followed_by(_iv(_MAR, _APR), {"a": 1}, replaces=False)
        .followed_by(_iv(_JUN, _JUL), {"a": 2}, replaces=False)
        .followed_by(_iv(_FEB, _SEP), {"b": 3}, replaces=False)
    )
    assert transform.segments == (
        CoverageSegment(_iv(_FEB, _MAR), {"b": 3}),
        CoverageSegment(_iv(_MAR, _APR), {"a": 1, "b": 3}),
        CoverageSegment(_iv(_APR, _JUN), {"b": 3}),
        CoverageSegment(_iv(_JUN, _JUL), {"a": 2, "b": 3}),
        CoverageSegment(_iv(_JUL, _SEP), {"b": 3}),
    )


def test_adjacent_segments_left_equal_join_into_one() -> None:
    transform = NO_TRANSFORM.followed_by(_iv(_MAR, _JUN), {"a": 1}, replaces=False).followed_by(
        _iv(_JUN, _SEP), {"a": 1}, replaces=False
    )
    assert transform.segments == (CoverageSegment(_iv(_MAR, _SEP), {"a": 1}),)
    separated = NO_TRANSFORM.followed_by(_iv(_MAR, _APR), {"a": 1}, replaces=False).followed_by(
        _iv(_JUN, _SEP), {"a": 1}, replaces=False
    )
    assert len(separated.segments) == 2


def test_a_lone_write_shares_its_prepared_window_as_segment_and_envelope() -> None:
    window = _iv(_MAR, _SEP)
    transform = NO_TRANSFORM.followed_by(window, {"a": 1}, replaces=False)
    (segment,) = transform.segments
    assert segment.valid_time_window is window
    assert transform.valid_time_window is window


def test_the_envelope_of_several_segments_spans_their_gaps() -> None:
    transform = NO_TRANSFORM.followed_by(_iv(_MAR, _APR), {"a": 1}, replaces=False).followed_by(
        _iv(_JUN, INFINITY), None, replaces=False
    )
    assert transform.valid_time_window == _iv(_MAR, INFINITY)


def test_a_baseline_equal_restatement_is_still_an_assignment() -> None:
    transform = (
        NO_TRANSFORM.followed_by(_iv(_MAR, _NOV), {"amount": 150}, replaces=False)
        .followed_by(_iv(_JUN, _SEP), {"amount": 200}, replaces=False)
        .followed_by(_iv(_JUN, _SEP), {"amount": 120}, replaces=False)
    )
    assert [segment.assigned for segment in transform.segments] == [
        {"amount": 150},
        {"amount": 120},
        {"amount": 150},
    ]


def test_binding_carries_the_predecessor_outside_and_skips_what_it_does_not_cover() -> None:
    transform = NO_TRANSFORM.followed_by(_iv(_MAR, _SEP), {"amount": 150}, replaces=False)
    assert transform.successors_of(_iv(_JAN, _JUN)) == (
        Successor(_iv(_JAN, _MAR), None),
        Successor(_iv(_MAR, _JUN), {"amount": 150}),
    )
    assert transform.successors_of(_iv(_JUN, INFINITY)) == (
        Successor(_iv(_JUN, _SEP), {"amount": 150}),
        Successor(_iv(_SEP, INFINITY), None),
    )
    assert not transform.reaches(_iv(_SEP, _DEC))
    assert transform.reaches(_iv(_AUG, _DEC))


def test_an_open_segment_over_open_coverage_takes_the_rest_of_it() -> None:
    transform = NO_TRANSFORM.followed_by(_iv(_MAR, INFINITY), {"a": 1}, replaces=False)
    assert transform.successors_of(_iv(_JAN, INFINITY)) == (
        Successor(_iv(_JAN, _MAR), None),
        Successor(_iv(_MAR, INFINITY), {"a": 1}),
    )


def test_a_successor_the_transform_leaves_whole_shares_the_coverage_it_binds() -> None:
    coverage = _iv(_APR, _JUN)
    transform = NO_TRANSFORM.followed_by(_iv(_MAR, _SEP), {"amount": 1}, replaces=False)
    (successor,) = transform.successors_of(coverage)
    assert successor.valid_time_coverage is coverage


def test_a_destroyed_interval_opens_nothing_and_never_an_empty_successor() -> None:
    transform = NO_TRANSFORM.followed_by(_iv(_MAR, INFINITY), None, replaces=False)
    assert transform.successors_of(_iv(_MAR, _DEC)) == ()
    assert transform.successors_of(_iv(_JAN, _DEC)) == (Successor(_iv(_JAN, _MAR), None),)
    assert not transform.assigns


def test_a_segment_beyond_a_predecessor_contributes_no_successor_of_it() -> None:
    transform = NO_TRANSFORM.followed_by(
        _iv(_MAR, _JUN), {"amount": 1}, replaces=False
    ).followed_by(_iv(_SEP, _NOV), {"amount": 2}, replaces=False)
    assert transform.successors_of(_iv(_JAN, _JUN)) == (
        Successor(_iv(_JAN, _MAR), None),
        Successor(_iv(_MAR, _JUN), {"amount": 1}),
    )


def test_instants_one_microsecond_apart_bind_exactly_through_the_last_year() -> None:
    first = dt.datetime(9999, 1, 1, tzinfo=dt.UTC)
    second = first + dt.timedelta(microseconds=1)
    third = second + dt.timedelta(microseconds=1)
    transform = NO_TRANSFORM.followed_by(_iv(second, INFINITY), {"a": 1}, replaces=False)
    assert transform.successors_of(_iv(first, third)) == (
        Successor(_iv(first, second), None),
        Successor(_iv(second, third), {"a": 1}),
    )


def test_a_transaction_time_only_transform_spans_the_whole_axis() -> None:
    assigned = NO_TRANSFORM.followed_by(None, {"amount": 1}, replaces=False).followed_by(
        None, {"label": "b"}, replaces=False
    )
    assert assigned.successors_of(None) == (Successor(None, {"amount": 1, "label": "b"}),)
    assert assigned.reaches(None)
    assert assigned.valid_time_window is None
    destroyed = assigned.followed_by(None, None, replaces=False)
    assert destroyed.successors_of(None) == ()
    assert not destroyed.assigns


_REPLACED = {"amount": 300, "label": None}


def test_a_replacement_takes_every_gap_of_its_extent_and_a_patch_none() -> None:
    replaced = NO_TRANSFORM.followed_by(_iv(_MAR, _DEC), _REPLACED, replaces=True)
    coverage = (_iv(_JAN, _JUN), _iv(_SEP, _NOV))
    assert replaced.gaps(coverage) == (
        CoverageGap(_iv(_JUN, _SEP), _REPLACED),
        CoverageGap(_iv(_NOV, _DEC), _REPLACED),
    )
    assert replaced.successors_of(_iv(_JAN, _JUN)) == (
        Successor(_iv(_JAN, _MAR), None),
        Successor(_iv(_MAR, _JUN), _REPLACED),
    )
    patched = NO_TRANSFORM.followed_by(_iv(_MAR, _DEC), {"amount": 1}, replaces=False)
    assert patched.gaps(coverage) == ()


def test_an_unbounded_replacement_fills_after_the_last_coverage_ends() -> None:
    replaced = NO_TRANSFORM.followed_by(_iv(_MAR, INFINITY), _REPLACED, replaces=True)
    assert replaced.gaps((_iv(_JAN, _JUN),)) == (CoverageGap(_iv(_JUN, INFINITY), _REPLACED),)
    assert replaced.gaps((_iv(_JAN, INFINITY),)) == ()


def test_an_uncovered_replacement_shares_its_window_as_its_one_gap() -> None:
    window = _iv(_MAR, _JUN)
    replaced = NO_TRANSFORM.followed_by(window, _REPLACED, replaces=True)
    (gap,) = replaced.gaps(())
    assert gap.valid_time_window is window
    (later,) = replaced.gaps((_iv(_JUL, _SEP),))
    assert later.valid_time_window is window


def test_a_later_assignment_keeps_the_replacement_extent_and_overlays_its_gaps() -> None:
    transform = NO_TRANSFORM.followed_by(_iv(_MAR, _DEC), _REPLACED, replaces=True).followed_by(
        _iv(_MAR, _DEC), {"label": "patched"}, replaces=False
    )
    assert transform.gaps((_iv(_JAN, _JUN),)) == (
        CoverageGap(_iv(_JUN, _DEC), {"amount": 300, "label": "patched"}),
    )


def test_a_replacement_over_earlier_assignments_discards_their_values() -> None:
    transform = NO_TRANSFORM.followed_by(
        _iv(_MAR, _DEC), {"note": "a"}, replaces=False
    ).followed_by(_iv(_MAR, _DEC), _REPLACED, replaces=True)
    assert transform.segments == (CoverageSegment(_iv(_MAR, _DEC), _REPLACED, replaces=True),)


def test_a_destruction_ends_a_replacement_extent_without_creating_coverage() -> None:
    transform = NO_TRANSFORM.followed_by(_iv(_MAR, _DEC), _REPLACED, replaces=True).followed_by(
        _iv(_MAR, _DEC), None, replaces=False
    )
    assert transform.gaps((_iv(_JAN, _JUN),)) == ()
    assert transform.successors_of(_iv(_JAN, _JUN)) == (Successor(_iv(_JAN, _MAR), None),)


def test_a_transaction_time_only_replacement_has_no_gap_to_fill() -> None:
    replaced = NO_TRANSFORM.followed_by(None, _REPLACED, replaces=True)
    assert replaced.gaps(()) == ()
    assert replaced.successors_of(None) == (Successor(None, _REPLACED),)


def test_a_gap_is_read_only_off_the_coverage_inside_the_replacement_extent() -> None:
    replaced = NO_TRANSFORM.followed_by(_iv(_MAR, _JUN), _REPLACED, replaces=True)
    coverage = (_iv(_JAN, _FEB), _iv(_APR, _MAY), _iv(_JUL, _SEP), _iv(_NOV, _DEC))
    assert replaced.gaps(coverage) == (
        CoverageGap(_iv(_MAR, _APR), _REPLACED),
        CoverageGap(_iv(_MAY, _JUN), _REPLACED),
    )


def _replacing_three_extents_around_a_patch() -> CoverageTransform:
    """Replacements over [Feb, Apr), [Jun, Aug) and [Oct, Dec), with a patch
    over [Apr, Jun) between the first two that fills nothing."""
    return (
        NO_TRANSFORM.followed_by(_iv(_FEB, _APR), _REPLACED, replaces=True)
        .followed_by(_iv(_JUN, _AUG), _REPLACED, replaces=True)
        .followed_by(_iv(_OCT, _DEC), _REPLACED, replaces=True)
        .followed_by(_iv(_APR, _JUN), {"label": "patched"}, replaces=False)
    )


def test_coverage_spanning_several_replacement_segments_stays_current_across_them() -> None:
    transform = _replacing_three_extents_around_a_patch()
    assert [segment.replaces for segment in transform.segments] == [True, False, True, True]
    coverage = _Consumed(_iv(_JAN, _MAR), _iv(_MAR, _JUL), _iv(_NOV, INFINITY))
    assert transform.gaps(coverage) == (
        CoverageGap(_iv(_JUL, _AUG), _REPLACED),
        CoverageGap(_iv(_OCT, _NOV), _REPLACED),
    )
    assert coverage.passes == 1
    assert coverage.handed == list(coverage.intervals)


def test_a_segment_that_fills_nothing_consumes_none_of_the_coverage_after_it() -> None:
    transform = _replacing_three_extents_around_a_patch()
    coverage = _Consumed(_iv(_APR, _JUL))
    assert transform.gaps(coverage) == (
        CoverageGap(_iv(_FEB, _APR), _REPLACED),
        CoverageGap(_iv(_JUL, _AUG), _REPLACED),
        CoverageGap(_iv(_OCT, _DEC), _REPLACED),
    )
    assert coverage.passes == 1


def test_the_gap_sweep_reads_each_coverage_interval_once_and_stops_with_the_last_extent() -> None:
    replaced = NO_TRANSFORM.followed_by(_iv(_FEB, _APR), _REPLACED, replaces=True).followed_by(
        _iv(_MAY, _JUL), _REPLACED, replaces=True
    )
    beyond = _iv(_SEP, _OCT)
    coverage = _Consumed(_iv(_JAN, _MAR), _iv(_JUN, _AUG), beyond, _iv(_NOV, _DEC))
    assert replaced.gaps(coverage) == (
        CoverageGap(_iv(_MAR, _APR), _REPLACED),
        CoverageGap(_iv(_MAY, _JUN), _REPLACED),
    )
    assert coverage.passes == 1
    assert coverage.handed == [_iv(_JAN, _MAR), _iv(_JUN, _AUG)]


def _positional(transform: CoverageTransform, coverage: TimeInterval) -> list[Successor]:
    """What one-segment scalar access answers for ``coverage``, as successors."""
    positions = transform.successor_positions(coverage.start, coverage.end)
    assert positions is not None
    successors: list[Successor] = []
    for position in (CARRIED_HEAD, WITHIN, CARRIED_TAIL):
        if positions & position:
            start, end = transform.successor_extent(position, coverage.start, coverage.end)
            assert isinstance(start, dt.datetime)
            assert end is INFINITY or isinstance(end, dt.datetime)
            assigned = transform.segments[0].assigned if position == WITHIN else None
            successors.append(Successor(TimeInterval(start, end), assigned))
    return successors


@pytest.mark.parametrize("window", [_iv(_MAR, _SEP), _iv(_MAR, INFINITY)], ids=["bounded", "open"])
@pytest.mark.parametrize("assigned", [{"amount": 150}, None], ids=["assigns", "destroys"])
@pytest.mark.parametrize(
    "coverage",
    [
        _iv(_JAN, INFINITY),
        _iv(_MAR, INFINITY),
        _iv(_MAY, INFINITY),
        _iv(_JAN, _JUN),
        _iv(_JAN, _SEP),
        _iv(_JAN, _OCT),
        _iv(_APR, _JUN),
    ],
)
def test_one_segment_scalar_access_answers_what_successors_of_answers(
    window: TimeInterval, assigned: dict[str, object] | None, coverage: TimeInterval
) -> None:
    # A group sizes each selected row from its two Valid-Time cells alone, and
    # what it decides must be exactly the successors the interval traversal
    # derives for the same coverage, a predecessor starting inside or past the
    # window included.
    transform = NO_TRANSFORM.followed_by(window, assigned, replaces=False)
    assert _positional(transform, coverage) == list(transform.successors_of(coverage))


def test_one_segment_scalar_access_reaches_nothing_beyond_the_window() -> None:
    transform = NO_TRANSFORM.followed_by(_iv(_MAR, _JUN), {"amount": 150}, replaces=False)
    assert transform.successor_positions(_JUN, INFINITY) is None
    assert transform.successor_positions(_JAN, _MAR) is None
    assert not transform.reaches(_iv(_JUN, INFINITY))


def test_a_transaction_time_only_segment_keeps_its_one_successor_where_it_assigns() -> None:
    assigning = NO_TRANSFORM.followed_by(None, {"amount": 150}, replaces=False)
    destroying = NO_TRANSFORM.followed_by(None, None, replaces=False)
    assert assigning.successor_positions(None, None) == WITHIN
    assert assigning.successor_extent(WITHIN, None, None) == (None, None)
    assert destroying.successor_positions(None, None) == 0
