"""The composed Valid-Time transform observed writes finalize to, and how it binds
one predecessor's coverage."""

from __future__ import annotations

import datetime as dt

from parallax.core.base import INFINITY
from parallax.core.unit_work.temporal import (
    EMPTY_TRANSFORM,
    BoundPiece,
    TemporalSegment,
    covers,
    instant_order,
)

_JAN, _FEB, _MAR, _JUN, _SEP, _NOV, _DEC = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 2, 3, 6, 9, 11, 12)
)


def test_a_later_write_wins_where_windows_overlap_and_each_keeps_its_own_elsewhere() -> None:
    transform = EMPTY_TRANSFORM.then(
        valid_from=_MAR, until=_SEP, assigned={"amount": 150, "label": "a"}
    ).then(valid_from=_JUN, until=_NOV, assigned={"amount": 200})
    assert transform.segments == (
        TemporalSegment(_MAR, _JUN, {"amount": 150, "label": "a"}),
        TemporalSegment(_JUN, _SEP, {"amount": 200, "label": "a"}),
        TemporalSegment(_SEP, _NOV, {"amount": 200}),
    )


def test_an_earlier_window_written_later_still_wins_over_the_overlap() -> None:
    transform = EMPTY_TRANSFORM.then(valid_from=_JUN, until=_NOV, assigned={"amount": 200}).then(
        valid_from=_MAR, until=None, assigned={"amount": 150}
    )
    assert [(segment.start, segment.assigned) for segment in transform.segments] == [
        (_MAR, {"amount": 150})
    ]
    assert transform.end is INFINITY


def test_a_baseline_equal_restatement_is_still_an_assignment() -> None:
    transform = (
        EMPTY_TRANSFORM.then(valid_from=_MAR, until=_NOV, assigned={"amount": 150})
        .then(valid_from=_JUN, until=_SEP, assigned={"amount": 200})
        .then(valid_from=_JUN, until=_SEP, assigned={"amount": 120})
    )
    assert [segment.assigned for segment in transform.segments] == [
        {"amount": 150},
        {"amount": 120},
        {"amount": 150},
    ]


def test_binding_carries_the_predecessor_outside_and_skips_what_it_does_not_cover() -> None:
    transform = EMPTY_TRANSFORM.then(valid_from=_MAR, until=_SEP, assigned={"amount": 150})
    assert transform.pieces(_JAN, _JUN) == (
        BoundPiece(_JAN, _MAR, None),
        BoundPiece(_MAR, _JUN, {"amount": 150}),
    )
    assert transform.pieces(_JUN, INFINITY) == (
        BoundPiece(_JUN, _SEP, {"amount": 150}),
        BoundPiece(_SEP, INFINITY, None),
    )
    assert not transform.touches(_SEP, _DEC)


def test_a_destroyed_interval_opens_nothing_and_never_an_empty_piece() -> None:
    transform = EMPTY_TRANSFORM.then(valid_from=_MAR, until=None, assigned=None)
    assert transform.pieces(_MAR, _DEC) == ()
    assert transform.pieces(_JAN, _DEC) == (BoundPiece(_JAN, _MAR, None),)
    assert not transform.assigns


def test_coverage_answers_the_first_point_its_intervals_leave_open() -> None:
    assert covers(((_JAN, _JUN),), _MAR, _JUN) is None
    assert covers(((_JAN, _JUN),), _MAR, INFINITY) == _JUN
    assert covers(((_JAN, _MAR), (_JUN, INFINITY)), _JAN, INFINITY) == _MAR


def test_instants_one_microsecond_apart_order_exactly_through_the_last_year() -> None:
    first = dt.datetime(9999, 1, 1, tzinfo=dt.UTC)
    second = first + dt.timedelta(microseconds=1)
    third = second + dt.timedelta(microseconds=1)
    intervals = sorted(((second, third), (first, second)), key=lambda iv: instant_order(iv[0]))
    assert intervals == [(first, second), (second, third)]
    assert covers(tuple(intervals), first, third) is None


def test_a_segment_beyond_a_predecessor_contributes_no_piece_of_it() -> None:
    transform = EMPTY_TRANSFORM.then(valid_from=_MAR, until=_JUN, assigned={"amount": 1}).then(
        valid_from=_SEP, until=_NOV, assigned={"amount": 2}
    )
    assert transform.pieces(_JAN, _JUN) == (
        BoundPiece(_JAN, _MAR, None),
        BoundPiece(_MAR, _JUN, {"amount": 1}),
    )


def test_coverage_reaching_past_the_window_leaves_nothing_open() -> None:
    assert covers(((_JAN, _MAR), (_MAR, _JUN), (_JUN, _DEC)), _JAN, _MAR) is None


def test_a_transaction_time_only_transform_spans_the_whole_axis() -> None:
    assigned = EMPTY_TRANSFORM.then(valid_from=None, until=None, assigned={"amount": 1}).then(
        valid_from=None, until=None, assigned={"label": "b"}
    )
    assert assigned.pieces(None, None) == (BoundPiece(None, None, {"amount": 1, "label": "b"}),)
    assert assigned.touches(None, None)
    destroyed = assigned.then(valid_from=None, until=None, assigned=None)
    assert destroyed.pieces(None, None) == ()
    assert not destroyed.assigns


_REPLACED = {"amount": 300, "label": None}


def test_a_replacement_takes_every_gap_of_its_extent_and_a_patch_none() -> None:
    replaced = EMPTY_TRANSFORM.then(valid_from=_MAR, until=_DEC, assigned=_REPLACED, replaces=True)
    coverage = ((_JAN, _JUN), (_SEP, _NOV))
    assert replaced.gaps(coverage) == (
        BoundPiece(_JUN, _SEP, _REPLACED),
        BoundPiece(_NOV, _DEC, _REPLACED),
    )
    assert replaced.pieces(_JAN, _JUN) == (
        BoundPiece(_JAN, _MAR, None),
        BoundPiece(_MAR, _JUN, _REPLACED),
    )
    patched = EMPTY_TRANSFORM.then(valid_from=_MAR, until=_DEC, assigned={"amount": 1})
    assert patched.gaps(coverage) == ()


def test_an_unbounded_replacement_fills_after_the_last_coverage_ends() -> None:
    replaced = EMPTY_TRANSFORM.then(valid_from=_MAR, until=None, assigned=_REPLACED, replaces=True)
    (tail,) = replaced.gaps(((_JAN, _JUN),))
    assert (tail.start, tail.assigned) == (_JUN, _REPLACED)
    assert tail.end is INFINITY
    assert replaced.gaps(((_JAN, INFINITY),)) == ()


def test_a_later_assignment_keeps_the_replacement_extent_and_overlays_its_gaps() -> None:
    transform = EMPTY_TRANSFORM.then(
        valid_from=_MAR, until=_DEC, assigned=_REPLACED, replaces=True
    ).then(valid_from=_MAR, until=_DEC, assigned={"label": "patched"})
    assert transform.gaps(((_JAN, _JUN),)) == (
        BoundPiece(_JUN, _DEC, {"amount": 300, "label": "patched"}),
    )


def test_a_replacement_over_earlier_assignments_discards_their_values() -> None:
    transform = EMPTY_TRANSFORM.then(valid_from=_MAR, until=_DEC, assigned={"note": "a"}).then(
        valid_from=_MAR, until=_DEC, assigned=_REPLACED, replaces=True
    )
    assert transform.segments == (TemporalSegment(_MAR, _DEC, _REPLACED, fills=True),)


def test_a_destruction_ends_a_replacement_extent_without_creating_coverage() -> None:
    transform = EMPTY_TRANSFORM.then(
        valid_from=_MAR, until=_DEC, assigned=_REPLACED, replaces=True
    ).then(valid_from=_MAR, until=_DEC, assigned=None)
    assert transform.gaps(((_JAN, _JUN),)) == ()
    assert transform.pieces(_JAN, _JUN) == (BoundPiece(_JAN, _MAR, None),)


def test_a_transaction_time_only_replacement_has_no_gap_to_fill() -> None:
    replaced = EMPTY_TRANSFORM.then(valid_from=None, until=None, assigned=_REPLACED, replaces=True)
    assert replaced.gaps(()) == ()
    assert replaced.pieces(None, None) == (BoundPiece(None, None, _REPLACED),)


def test_a_gap_is_read_only_off_the_coverage_inside_the_replacement_extent() -> None:
    replaced = EMPTY_TRANSFORM.then(valid_from=_MAR, until=_JUN, assigned=_REPLACED, replaces=True)
    april, may, july = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (4, 5, 7))
    coverage = ((_JAN, _FEB), (april, may), (july, _SEP), (_NOV, _DEC))
    assert replaced.gaps(coverage) == (
        BoundPiece(_MAR, april, _REPLACED),
        BoundPiece(may, _JUN, _REPLACED),
    )
