"""The composed Valid-Time transform observed writes finalize to, and how it binds
one predecessor's coverage."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

from parallax.core.base import INFINITY, TemporalBound
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work.strategy import CARRIED_STATE
from parallax.core.unit_work.temporal import (
    EMPTY_TRANSFORM,
    BoundPiece,
    TemporalSegment,
    TemporalTransform,
    literal_successor,
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
    transform = EMPTY_TRANSFORM.then(
        valid_time_window=_iv(_MAR, _SEP), assigned={"amount": 150, "label": "a"}
    ).then(valid_time_window=_iv(_JUN, _NOV), assigned={"amount": 200})
    assert transform.segments == (
        TemporalSegment(_iv(_MAR, _JUN), {"amount": 150, "label": "a"}),
        TemporalSegment(_iv(_JUN, _SEP), {"amount": 200, "label": "a"}),
        TemporalSegment(_iv(_SEP, _NOV), {"amount": 200}),
    )


def test_an_earlier_window_written_later_still_wins_over_the_overlap() -> None:
    transform = EMPTY_TRANSFORM.then(
        valid_time_window=_iv(_JUN, _NOV), assigned={"amount": 200}
    ).then(valid_time_window=_iv(_MAR, INFINITY), assigned={"amount": 150})
    assert transform.segments == (TemporalSegment(_iv(_MAR, INFINITY), {"amount": 150}),)
    assert transform.enclosing_window() == _iv(_MAR, INFINITY)


def test_a_write_wholly_before_and_after_existing_segments_keeps_start_order() -> None:
    later = EMPTY_TRANSFORM.then(valid_time_window=_iv(_JUN, _SEP), assigned={"amount": 1})
    assert later.then(valid_time_window=_iv(_JAN, _MAR), assigned={"amount": 2}).segments == (
        TemporalSegment(_iv(_JAN, _MAR), {"amount": 2}),
        TemporalSegment(_iv(_JUN, _SEP), {"amount": 1}),
    )
    assert later.then(valid_time_window=_iv(_OCT, _DEC), assigned={"amount": 2}).segments == (
        TemporalSegment(_iv(_JUN, _SEP), {"amount": 1}),
        TemporalSegment(_iv(_OCT, _DEC), {"amount": 2}),
    )


def test_a_write_spanning_separate_segments_fills_between_and_around_them() -> None:
    transform = (
        EMPTY_TRANSFORM.then(valid_time_window=_iv(_MAR, _APR), assigned={"a": 1})
        .then(valid_time_window=_iv(_JUN, _JUL), assigned={"a": 2})
        .then(valid_time_window=_iv(_FEB, _SEP), assigned={"b": 3})
    )
    assert transform.segments == (
        TemporalSegment(_iv(_FEB, _MAR), {"b": 3}),
        TemporalSegment(_iv(_MAR, _APR), {"a": 1, "b": 3}),
        TemporalSegment(_iv(_APR, _JUN), {"b": 3}),
        TemporalSegment(_iv(_JUN, _JUL), {"a": 2, "b": 3}),
        TemporalSegment(_iv(_JUL, _SEP), {"b": 3}),
    )


def test_adjacent_segments_left_equal_join_into_one() -> None:
    transform = EMPTY_TRANSFORM.then(valid_time_window=_iv(_MAR, _JUN), assigned={"a": 1}).then(
        valid_time_window=_iv(_JUN, _SEP), assigned={"a": 1}
    )
    assert transform.segments == (TemporalSegment(_iv(_MAR, _SEP), {"a": 1}),)
    separated = EMPTY_TRANSFORM.then(valid_time_window=_iv(_MAR, _APR), assigned={"a": 1}).then(
        valid_time_window=_iv(_JUN, _SEP), assigned={"a": 1}
    )
    assert len(separated.segments) == 2


def test_a_lone_write_shares_its_prepared_window_as_segment_and_envelope() -> None:
    window = _iv(_MAR, _SEP)
    transform = EMPTY_TRANSFORM.then(valid_time_window=window, assigned={"a": 1})
    (segment,) = transform.segments
    assert segment.valid_time_window is window
    assert transform.enclosing_window() is window


def test_the_envelope_of_several_segments_spans_their_gaps() -> None:
    transform = EMPTY_TRANSFORM.then(valid_time_window=_iv(_MAR, _APR), assigned={"a": 1}).then(
        valid_time_window=_iv(_JUN, INFINITY), assigned=None
    )
    assert transform.enclosing_window() == _iv(_MAR, INFINITY)


def test_a_baseline_equal_restatement_is_still_an_assignment() -> None:
    transform = (
        EMPTY_TRANSFORM.then(valid_time_window=_iv(_MAR, _NOV), assigned={"amount": 150})
        .then(valid_time_window=_iv(_JUN, _SEP), assigned={"amount": 200})
        .then(valid_time_window=_iv(_JUN, _SEP), assigned={"amount": 120})
    )
    assert [segment.assigned for segment in transform.segments] == [
        {"amount": 150},
        {"amount": 120},
        {"amount": 150},
    ]


def test_binding_carries_the_predecessor_outside_and_skips_what_it_does_not_cover() -> None:
    transform = EMPTY_TRANSFORM.then(valid_time_window=_iv(_MAR, _SEP), assigned={"amount": 150})
    assert transform.pieces(_iv(_JAN, _JUN)) == (
        BoundPiece(_iv(_JAN, _MAR), None),
        BoundPiece(_iv(_MAR, _JUN), {"amount": 150}),
    )
    assert transform.pieces(_iv(_JUN, INFINITY)) == (
        BoundPiece(_iv(_JUN, _SEP), {"amount": 150}),
        BoundPiece(_iv(_SEP, INFINITY), None),
    )
    assert not transform.touches(_iv(_SEP, _DEC))
    assert transform.touches(_iv(_AUG, _DEC))


def test_an_open_segment_over_open_coverage_takes_the_rest_of_it() -> None:
    transform = EMPTY_TRANSFORM.then(valid_time_window=_iv(_MAR, INFINITY), assigned={"a": 1})
    assert transform.pieces(_iv(_JAN, INFINITY)) == (
        BoundPiece(_iv(_JAN, _MAR), None),
        BoundPiece(_iv(_MAR, INFINITY), {"a": 1}),
    )


def test_a_piece_the_transform_leaves_whole_shares_the_coverage_it_binds() -> None:
    coverage = _iv(_APR, _JUN)
    transform = EMPTY_TRANSFORM.then(valid_time_window=_iv(_MAR, _SEP), assigned={"amount": 1})
    (piece,) = transform.pieces(coverage)
    assert piece.valid_time_coverage is coverage


def test_a_destroyed_interval_opens_nothing_and_never_an_empty_piece() -> None:
    transform = EMPTY_TRANSFORM.then(valid_time_window=_iv(_MAR, INFINITY), assigned=None)
    assert transform.pieces(_iv(_MAR, _DEC)) == ()
    assert transform.pieces(_iv(_JAN, _DEC)) == (BoundPiece(_iv(_JAN, _MAR), None),)
    assert not transform.assigns


def test_a_segment_beyond_a_predecessor_contributes_no_piece_of_it() -> None:
    transform = EMPTY_TRANSFORM.then(
        valid_time_window=_iv(_MAR, _JUN), assigned={"amount": 1}
    ).then(valid_time_window=_iv(_SEP, _NOV), assigned={"amount": 2})
    assert transform.pieces(_iv(_JAN, _JUN)) == (
        BoundPiece(_iv(_JAN, _MAR), None),
        BoundPiece(_iv(_MAR, _JUN), {"amount": 1}),
    )


def test_instants_one_microsecond_apart_bind_exactly_through_the_last_year() -> None:
    first = dt.datetime(9999, 1, 1, tzinfo=dt.UTC)
    second = first + dt.timedelta(microseconds=1)
    third = second + dt.timedelta(microseconds=1)
    transform = EMPTY_TRANSFORM.then(valid_time_window=_iv(second, INFINITY), assigned={"a": 1})
    assert transform.pieces(_iv(first, third)) == (
        BoundPiece(_iv(first, second), None),
        BoundPiece(_iv(second, third), {"a": 1}),
    )


def test_a_transaction_time_only_transform_spans_the_whole_axis() -> None:
    assigned = EMPTY_TRANSFORM.then(valid_time_window=None, assigned={"amount": 1}).then(
        valid_time_window=None, assigned={"label": "b"}
    )
    assert assigned.pieces(None) == (BoundPiece(None, {"amount": 1, "label": "b"}),)
    assert assigned.touches(None)
    assert assigned.enclosing_window() is None
    destroyed = assigned.then(valid_time_window=None, assigned=None)
    assert destroyed.pieces(None) == ()
    assert not destroyed.assigns


def test_a_piece_names_its_own_endpoints_as_a_literal_successor_window() -> None:
    piece = BoundPiece(_iv(_MAR, INFINITY), None)
    successor = literal_successor(CARRIED_STATE, piece.valid_time_coverage)
    assert successor.window is not None
    assert literal_successor(CARRIED_STATE, None).window is None


_REPLACED = {"amount": 300, "label": None}


def test_a_replacement_takes_every_gap_of_its_extent_and_a_patch_none() -> None:
    replaced = EMPTY_TRANSFORM.then(
        valid_time_window=_iv(_MAR, _DEC), assigned=_REPLACED, replaces=True
    )
    coverage = (_iv(_JAN, _JUN), _iv(_SEP, _NOV))
    assert replaced.gaps(coverage) == (
        BoundPiece(_iv(_JUN, _SEP), _REPLACED),
        BoundPiece(_iv(_NOV, _DEC), _REPLACED),
    )
    assert replaced.pieces(_iv(_JAN, _JUN)) == (
        BoundPiece(_iv(_JAN, _MAR), None),
        BoundPiece(_iv(_MAR, _JUN), _REPLACED),
    )
    patched = EMPTY_TRANSFORM.then(valid_time_window=_iv(_MAR, _DEC), assigned={"amount": 1})
    assert patched.gaps(coverage) == ()


def test_an_unbounded_replacement_fills_after_the_last_coverage_ends() -> None:
    replaced = EMPTY_TRANSFORM.then(
        valid_time_window=_iv(_MAR, INFINITY), assigned=_REPLACED, replaces=True
    )
    assert replaced.gaps((_iv(_JAN, _JUN),)) == (BoundPiece(_iv(_JUN, INFINITY), _REPLACED),)
    assert replaced.gaps((_iv(_JAN, INFINITY),)) == ()


def test_an_uncovered_replacement_shares_its_window_as_its_one_gap() -> None:
    window = _iv(_MAR, _JUN)
    replaced = EMPTY_TRANSFORM.then(valid_time_window=window, assigned=_REPLACED, replaces=True)
    (gap,) = replaced.gaps(())
    assert gap.valid_time_coverage is window
    (later,) = replaced.gaps((_iv(_JUL, _SEP),))
    assert later.valid_time_coverage is window


def test_a_later_assignment_keeps_the_replacement_extent_and_overlays_its_gaps() -> None:
    transform = EMPTY_TRANSFORM.then(
        valid_time_window=_iv(_MAR, _DEC), assigned=_REPLACED, replaces=True
    ).then(valid_time_window=_iv(_MAR, _DEC), assigned={"label": "patched"})
    assert transform.gaps((_iv(_JAN, _JUN),)) == (
        BoundPiece(_iv(_JUN, _DEC), {"amount": 300, "label": "patched"}),
    )


def test_a_replacement_over_earlier_assignments_discards_their_values() -> None:
    transform = EMPTY_TRANSFORM.then(
        valid_time_window=_iv(_MAR, _DEC), assigned={"note": "a"}
    ).then(valid_time_window=_iv(_MAR, _DEC), assigned=_REPLACED, replaces=True)
    assert transform.segments == (TemporalSegment(_iv(_MAR, _DEC), _REPLACED, fills=True),)


def test_a_destruction_ends_a_replacement_extent_without_creating_coverage() -> None:
    transform = EMPTY_TRANSFORM.then(
        valid_time_window=_iv(_MAR, _DEC), assigned=_REPLACED, replaces=True
    ).then(valid_time_window=_iv(_MAR, _DEC), assigned=None)
    assert transform.gaps((_iv(_JAN, _JUN),)) == ()
    assert transform.pieces(_iv(_JAN, _JUN)) == (BoundPiece(_iv(_JAN, _MAR), None),)


def test_a_transaction_time_only_replacement_has_no_gap_to_fill() -> None:
    replaced = EMPTY_TRANSFORM.then(valid_time_window=None, assigned=_REPLACED, replaces=True)
    assert replaced.gaps(()) == ()
    assert replaced.pieces(None) == (BoundPiece(None, _REPLACED),)


def test_a_gap_is_read_only_off_the_coverage_inside_the_replacement_extent() -> None:
    replaced = EMPTY_TRANSFORM.then(
        valid_time_window=_iv(_MAR, _JUN), assigned=_REPLACED, replaces=True
    )
    coverage = (_iv(_JAN, _FEB), _iv(_APR, _MAY), _iv(_JUL, _SEP), _iv(_NOV, _DEC))
    assert replaced.gaps(coverage) == (
        BoundPiece(_iv(_MAR, _APR), _REPLACED),
        BoundPiece(_iv(_MAY, _JUN), _REPLACED),
    )


def _replacing_three_extents_around_a_patch() -> TemporalTransform:
    """Replacements over [Feb, Apr), [Jun, Aug) and [Oct, Dec), with a patch
    over [Apr, Jun) between the first two that fills nothing."""
    return (
        EMPTY_TRANSFORM.then(valid_time_window=_iv(_FEB, _APR), assigned=_REPLACED, replaces=True)
        .then(valid_time_window=_iv(_JUN, _AUG), assigned=_REPLACED, replaces=True)
        .then(valid_time_window=_iv(_OCT, _DEC), assigned=_REPLACED, replaces=True)
        .then(valid_time_window=_iv(_APR, _JUN), assigned={"label": "patched"})
    )


def test_coverage_spanning_several_replacement_segments_stays_current_across_them() -> None:
    transform = _replacing_three_extents_around_a_patch()
    assert [segment.fills for segment in transform.segments] == [True, False, True, True]
    coverage = _Consumed(_iv(_JAN, _MAR), _iv(_MAR, _JUL), _iv(_NOV, INFINITY))
    assert transform.gaps(coverage) == (
        BoundPiece(_iv(_JUL, _AUG), _REPLACED),
        BoundPiece(_iv(_OCT, _NOV), _REPLACED),
    )
    assert coverage.passes == 1
    assert coverage.handed == list(coverage.intervals)


def test_a_segment_that_fills_nothing_consumes_none_of_the_coverage_after_it() -> None:
    transform = _replacing_three_extents_around_a_patch()
    coverage = _Consumed(_iv(_APR, _JUL))
    assert transform.gaps(coverage) == (
        BoundPiece(_iv(_FEB, _APR), _REPLACED),
        BoundPiece(_iv(_JUL, _AUG), _REPLACED),
        BoundPiece(_iv(_OCT, _DEC), _REPLACED),
    )
    assert coverage.passes == 1


def test_the_gap_sweep_reads_each_coverage_interval_once_and_stops_with_the_last_extent() -> None:
    replaced = EMPTY_TRANSFORM.then(
        valid_time_window=_iv(_FEB, _APR), assigned=_REPLACED, replaces=True
    ).then(valid_time_window=_iv(_MAY, _JUL), assigned=_REPLACED, replaces=True)
    beyond = _iv(_SEP, _OCT)
    coverage = _Consumed(_iv(_JAN, _MAR), _iv(_JUN, _AUG), beyond, _iv(_NOV, _DEC))
    assert replaced.gaps(coverage) == (
        BoundPiece(_iv(_MAR, _APR), _REPLACED),
        BoundPiece(_iv(_MAY, _JUN), _REPLACED),
    )
    assert coverage.passes == 1
    assert coverage.handed == [_iv(_JAN, _MAR), _iv(_JUN, _AUG)]
