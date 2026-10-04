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
    is_open_bound,
)

_JAN, _MAR, _JUN, _SEP, _NOV, _DEC = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 6, 9, 11, 12)
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
    assert is_open_bound(transform.end)


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
