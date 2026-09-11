"""The page policy, called directly: what a page asks for, and what survives it.

`m-snapshot-read` *Streamed delivery* settles both — a page reads one root past
its batch, an authored limit caps that lookahead, and two adjacent roots at one
evaluated coordinate end the delivery after the maximal strictly ordered prefix.
The arithmetic behind those rules is computation over counts and coordinates with
no port, no SQL, and no graph under it, which is what lets the lookahead discard,
the tie, and the ordinal of the first undeliverable root be exercised here with
hand-built coordinates instead of only through a scripted database.

This is an internal seam rather than a surface: what a DELIVERY does about a tie
is graded in `test_snapshot_stream.py`, against the stream, and holds through any
refactor of the functions below.
"""

from __future__ import annotations

import pytest
from _corpus_model_support import model as accepted_model
from _corpus_model_support import target as entity_of

from parallax.core import continuation
from parallax.core.metamodel import Metamodel
from parallax.core.object_query import object_query, validate_object_query
from parallax.core.object_query._validated import ContinuationCoordinate
from parallax.core.predicate import All
from parallax.snapshot.handle._page import PagePlan, PageRequest, page_decision

ORDERS: Metamodel = accepted_model("orders")

_TERMS = ()
"""The Continuation Order a tie reports.

Empty here because these readings are about the arithmetic: a verdict carries the
order through to the refusal without reading it, and which Attributes are in it is
`test_continuation.py`'s subject.
"""


def _page_plan(*, batch_size: int, limit: int | None = None) -> PagePlan:
    entity = entity_of(ORDERS, "Order")
    query = object_query(entity.identity, All(), limit=limit)
    return PagePlan(
        continuation.plan(validate_object_query(entity, query, ORDERS), ORDERS),
        batch_size,
        limit,
    )


def _coordinates(*carriers: object) -> tuple[ContinuationCoordinate, ...]:
    return tuple(ContinuationCoordinate((carrier,)) for carrier in carriers)


# --------------------------------------------------------------------------- #
# What a page asks the database for.                                          #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("emitted", [0, 1, 40])
def test_an_uncapped_page_asks_for_one_root_more_than_it_delivers(emitted: int) -> None:
    # The lookahead root, at every position of the delivery: it is what proves
    # exhaustion without a terminal statement, and what puts the first root of the
    # next page inside this page's own tie scan.
    assert _page_plan(batch_size=8).page_request(emitted) == PageRequest(
        size=9, lookahead=True, emitted=emitted
    )


def test_a_limit_further_than_a_page_away_still_leaves_room_for_the_lookahead() -> None:
    # The extra root is inside the limit, so reading it crosses no boundary: 40
    # roots are still undelivered and the page delivers 8 of them.
    assert _page_plan(batch_size=8, limit=50).page_request(10) == PageRequest(
        size=9, lookahead=True, emitted=10
    )


@pytest.mark.parametrize("remaining", [1, 7, 8])
def test_the_final_page_a_limit_caps_asks_for_the_remainder_and_no_lookahead(
    remaining: int,
) -> None:
    # An authored limit is a hard database-read boundary rather than a filter, so
    # the page it caps reads no root the limit excludes — not even to inspect one.
    plan = _page_plan(batch_size=8, limit=50)
    assert plan.page_request(50 - remaining) == PageRequest(
        size=remaining, lookahead=False, emitted=50 - remaining
    )


def test_the_smallest_page_still_reads_two_roots() -> None:
    assert _page_plan(batch_size=1).page_request(0) == PageRequest(
        size=2, lookahead=True, emitted=0
    )


# --------------------------------------------------------------------------- #
# Which of the roots a page returned it may deliver.                          #
# --------------------------------------------------------------------------- #
def test_a_page_that_read_its_lookahead_root_drops_it_and_continues() -> None:
    request = PageRequest(size=3, lookahead=True, emitted=4)
    verdict = page_decision(request, _TERMS, _coordinates(1, 2, 3))
    assert (verdict.keep, verdict.exhausted, verdict.tie) == (2, False, None)


def test_a_page_short_of_what_it_asked_for_keeps_everything_and_exhausts() -> None:
    request = PageRequest(size=3, lookahead=True, emitted=0)
    verdict = page_decision(request, _TERMS, _coordinates(1, 2))
    assert (verdict.keep, verdict.exhausted, verdict.tie) == (2, True, None)


def test_an_empty_page_keeps_nothing_and_exhausts() -> None:
    request = PageRequest(size=3, lookahead=True, emitted=6)
    verdict = page_decision(request, _TERMS, ())
    assert (verdict.keep, verdict.exhausted, verdict.tie) == (0, True, None)


def test_the_final_page_a_limit_caps_exhausts_however_full_it_came_back() -> None:
    # A full result proves nothing about what follows a no-lookahead page, and it
    # needs to prove nothing: the limit is delivered in full.
    request = PageRequest(size=2, lookahead=False, emitted=8)
    verdict = page_decision(request, _TERMS, _coordinates(9, 10))
    assert (verdict.keep, verdict.exhausted, verdict.tie) == (2, True, None)


# --------------------------------------------------------------------------- #
# Two roots at one coordinate.                                                #
# --------------------------------------------------------------------------- #
def test_adjacent_equal_coordinates_keep_the_prefix_before_them() -> None:
    # `p, q, q` at a page size of 2: the tie is found at the LOOKAHEAD root, so
    # only `p` may be delivered — resuming from the first `q` would emit a strict
    # comparison stepping straight over its twin.
    request = PageRequest(size=3, lookahead=True, emitted=0)
    verdict = page_decision(request, _TERMS, _coordinates("p", "q", "q"))
    assert (verdict.keep, verdict.exhausted) == (1, True)
    assert verdict.tie is not None
    assert (verdict.tie.ordinal, verdict.tie.coordinate) == (1, ("q",))


def test_a_tie_at_the_head_of_a_page_publishes_nothing_at_all() -> None:
    request = PageRequest(size=3, lookahead=True, emitted=12)
    verdict = page_decision(request, _TERMS, _coordinates("q", "q", "r"))
    assert (verdict.keep, verdict.exhausted) == (0, True)
    assert verdict.tie is not None
    assert (verdict.tie.ordinal, verdict.tie.coordinate) == (12, ("q",))


def test_a_ties_ordinal_counts_from_the_start_of_the_delivery() -> None:
    # The position the refusal reports is the first UNDELIVERABLE result, which is
    # what the pages before this one already delivered plus the prefix this one
    # keeps — arithmetic that belongs beside the rest of the page's rather than in
    # the raiser.
    request = PageRequest(size=4, lookahead=True, emitted=100)
    verdict = page_decision(request, _TERMS, _coordinates(1, 2, 3, 3))
    assert verdict.tie is not None
    assert (verdict.keep, verdict.tie.ordinal) == (2, 102)


def test_a_tie_is_found_on_a_no_lookahead_page_too() -> None:
    # The limit bounds what a page READS, never what it inspects: two tied roots
    # inside it end the delivery exactly as they do anywhere else.
    request = PageRequest(size=3, lookahead=False, emitted=0)
    verdict = page_decision(request, _TERMS, _coordinates(1, 2, 2))
    assert verdict.tie is not None
    assert (verdict.keep, verdict.tie.ordinal) == (1, 1)


def test_the_tie_reports_an_inert_copy_rather_than_a_coordinate() -> None:
    # What crosses to a caller is readable and comparable and is no cursor: a
    # provider may still own the buffer behind a carrier, so byte-likes are copied
    # and nothing turns the result back into pagination authority.
    carrier = bytearray(b"\x0a\x1b")
    coordinates = (ContinuationCoordinate((carrier,)), ContinuationCoordinate((carrier,)))
    request = PageRequest(size=2, lookahead=True, emitted=0)
    verdict = page_decision(request, _TERMS, coordinates)
    assert verdict.tie is not None
    carrier.clear()
    assert verdict.tie.coordinate == (b"\x0a\x1b",)
    assert not isinstance(verdict.tie.coordinate, ContinuationCoordinate)


def test_sameness_is_the_coordinates_own_rule_over_every_term() -> None:
    # Two roots agreeing on the leading term and parting on another are not tied,
    # which is the whole reason the Continuation Order carries more than one term.
    wide = (
        ContinuationCoordinate((1, "a")),
        ContinuationCoordinate((1, "b")),
        ContinuationCoordinate((1, "b")),
    )
    request = PageRequest(size=3, lookahead=True, emitted=0)
    verdict = page_decision(request, _TERMS, wide)
    assert verdict.tie is not None
    assert (verdict.keep, verdict.tie.coordinate) == (1, (1, "b"))
