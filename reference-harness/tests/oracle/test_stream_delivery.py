"""Streamed delivery through ``assert_case_read``.

A streamed read is not the eager read with a cap: its ``then.statements`` is the
pages' own ``1 + L`` groups concatenated, so the partition has to be recovered
before anything can be graded, and each continuing page's SQL is graded against a
seek the Continuation Order composes rather than against the text the case
authored. Almost every test below therefore damages one thing in a shipped case
that still reaches plausible rows, and asserts the delivery is refused anyway.

The scripted adapter decides what each page returns, so a page's result is chosen
here rather than read out of the fixtures — which is what lets one shipped case
drive both its own delivery and a page that returns the wrong number of roots.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest

from reference_harness.case import Case
from reference_harness.case_assertions import CaseFailure
from reference_harness.case_preflight import preflight_case_literals
from reference_harness.object_query_oracle import assert_case_read

from .conftest import ScriptedReads

CaseLoader = Callable[[str], Case]

_DEEP_FETCH = "m-snapshot-read-027-streamed-deep-fetch.yaml"
_TERMINAL_PAGE = "m-snapshot-read-028-stream-empty-terminal-page.yaml"
_BATCH_TWIN_2 = "m-snapshot-read-029-page-invariance-batch-size-twin-2.yaml"
_BATCH_TWIN_3 = "m-snapshot-read-030-page-invariance-batch-size-twin-3.yaml"
_MIXED_DIRECTIONS = "m-snapshot-read-031-stream-order-mixed-directions.yaml"
_NULLABLE_PLACEMENT = "m-snapshot-read-032-stream-order-nullable-placement.yaml"
_MULTI_TERM_SEEK = "m-snapshot-read-033-stream-order-multi-term-seek.yaml"
_DOCUMENT_RESIDENT = "m-snapshot-read-035-stream-order-document-resident.yaml"
_HISTORY_BOUNDARY = "m-snapshot-read-036-stream-history-page-boundary.yaml"
_MILESTONE_EDGE_PINS = "m-snapshot-read-037-stream-milestone-edge-pins.yaml"
_TABLELESS_POSITION = "m-inheritance-136-tpcs-union-vo-projection.yaml"

_TYPED_COORDINATES = (
    (
        "m_snapshot_read_038",
        "m-snapshot-read-038-stream-order-date-coordinate.yaml",
        "day",
        "2026-01-15",
    ),
    (
        "m_snapshot_read_039",
        "m-snapshot-read-039-stream-order-time-coordinate.yaml",
        "clock",
        "09:30:00",
    ),
    (
        "m_snapshot_read_040",
        "m-snapshot-read-040-stream-order-decimal-coordinate.yaml",
        "amount",
        "10.25",
    ),
    (
        "m_snapshot_read_041",
        "m-snapshot-read-041-stream-order-bytes-coordinate.yaml",
        "payload",
        "0a1b",
    ),
    (
        "m_snapshot_read_042",
        "m-snapshot-read-042-stream-order-uuid-coordinate.yaml",
        "token",
        "00000000-0000-4000-8000-0000000000ab",
    ),
    (
        "m_snapshot_read_043",
        "m-snapshot-read-043-stream-order-timestamp-coordinate.yaml",
        "instant",
        "2026-01-15T09:30:00.000000Z",
    ),
    (
        "m_snapshot_read_044",
        "m-snapshot-read-044-stream-order-float32-coordinate.yaml",
        "f32",
        1.5,
    ),
    (
        "m_snapshot_read_045",
        "m-snapshot-read-045-stream-order-float64-coordinate.yaml",
        "f64",
        2.25,
    ),
)

# --- the physical rows the pages return --------------------------------------

_ORDERS: dict[int, dict[str, Any]] = {
    1: {
        "id": 1,
        "name": "Ada",
        "sku": "A-100",
        "qty": 5,
        "price": Decimal("10.50"),
        "active": True,
        "ordered_on": "2024-01-05",
    },
    2: {
        "id": 2,
        "name": "Linus",
        "sku": "B-200",
        "qty": 10,
        "price": Decimal("20.00"),
        "active": True,
        "ordered_on": "2024-02-10",
    },
    3: {
        "id": 3,
        "name": "ada",
        "sku": "A-300",
        "qty": 15,
        "price": Decimal("30.25"),
        "active": False,
        "ordered_on": "2024-03-15",
    },
    4: {
        "id": 4,
        "name": "Margaret",
        "sku": None,
        "qty": 20,
        "price": Decimal("40.00"),
        "active": True,
        "ordered_on": "2024-04-20",
    },
    5: {
        "id": 5,
        "name": "Alan",
        "sku": "C_50%",
        "qty": 25,
        "price": Decimal("50.75"),
        "active": False,
        "ordered_on": "2024-05-25",
    },
    42: {
        "id": 42,
        "name": "Grace",
        "sku": "A-999",
        "qty": 30,
        "price": Decimal("99.99"),
        "active": True,
        "ordered_on": "2024-06-30",
    },
}

_ITEMS: dict[int, dict[str, Any]] = {
    11: {"id": 11, "order_id": 1, "sku": "A-100", "quantity": 2, "shipped_on": None},
    12: {"id": 12, "order_id": 1, "sku": "B-200", "quantity": 1, "shipped_on": "2024-02-15"},
    21: {"id": 21, "order_id": 2, "sku": "A-300", "quantity": 4, "shipped_on": "2024-02-20"},
    421: {"id": 421, "order_id": 42, "sku": "A-999", "quantity": 3, "shipped_on": "2024-03-10"},
    422: {"id": 422, "order_id": 42, "sku": "B-200", "quantity": 5, "shipped_on": "2024-02-05"},
}

_STATUSES: dict[int, dict[str, Any]] = {
    201: {"id": 201, "order_id": 1, "order_item_id": 11, "code": "PICKED"},
    202: {"id": 202, "order_id": 1, "order_item_id": 11, "code": "PACKED"},
    203: {"id": 203, "order_id": 1, "order_item_id": 12, "code": "PICKED"},
    204: {"id": 204, "order_id": 42, "order_item_id": 421, "code": "PICKED"},
}

_TRIPS: dict[int, dict[str, Any]] = {
    51: {"id": 51, "traveler_id": 1, "payload": {"destination": "Oslo", "nights": 3}},
    52: {"id": 52, "traveler_id": 1, "payload": {"destination": "Bergen", "nights": 1}},
    53: {"id": 53, "traveler_id": 2, "payload": {"destination": "Bergen", "nights": 7}},
}

_TRIP_REFERENCE: list[dict[str, Any]] = [
    {"id": 51, "traveler_id": 1, "destination": "Oslo", "nights": 3},
    {"id": 53, "traveler_id": 2, "destination": "Bergen", "nights": 7},
    {"id": 52, "traveler_id": 1, "destination": "Bergen", "nights": 1},
]

# One `invoice_line` key at two transaction-time milestones, plus a second key at
# one — the milestone set a `history` read delivers one root at a time.
_LINES: list[dict[str, Any]] = [
    {
        "id": 1000,
        "invoice_id": 100,
        "amount": Decimal("50.00"),
        "in_z": "2024-01-01T00:00:00+00:00",
        "out_z": "2024-04-01T00:00:00+00:00",
    },
    {
        "id": 1000,
        "invoice_id": 100,
        "amount": Decimal("75.00"),
        "in_z": "2024-04-01T00:00:00+00:00",
        "out_z": "infinity",
    },
    {
        "id": 1001,
        "invoice_id": 100,
        "amount": Decimal("25.00"),
        "in_z": "2024-01-01T00:00:00+00:00",
        "out_z": "infinity",
    },
]

_POSITIONS: list[dict[str, Any]] = [
    {
        "pos_id": 1,
        "acct_num": "A",
        "val": Decimal("90.00"),
        "from_z": "2024-01-01T00:00:00+00:00",
        "thru_z": "infinity",
        "in_z": "2024-01-01T00:00:00+00:00",
        "out_z": "2024-04-01T00:00:00+00:00",
    },
    {
        "pos_id": 1,
        "acct_num": "A",
        "val": Decimal("100.00"),
        "from_z": "2024-01-01T00:00:00+00:00",
        "thru_z": "2024-06-01T00:00:00+00:00",
        "in_z": "2024-04-01T00:00:00+00:00",
        "out_z": "infinity",
    },
    {
        "pos_id": 1,
        "acct_num": "A",
        "val": Decimal("200.00"),
        "from_z": "2024-06-01T00:00:00+00:00",
        "thru_z": "infinity",
        "in_z": "2024-04-01T00:00:00+00:00",
        "out_z": "infinity",
    },
]


def _rows(source: dict[int, dict[str, Any]], *keys: int) -> list[dict[str, Any]]:
    return [dict(source[key]) for key in keys]


def _statements(case: Case) -> list[dict[str, Any]]:
    return case.then["statements"]


# --- the deliveries a shipped case authors -----------------------------------


def _deep_fetch_script() -> list[list[dict[str, Any]]]:
    """`m-snapshot-read-027`: two pages of a two-level deep fetch, plus its oracle."""
    return [
        _rows(_ORDERS, 1, 2),
        _rows(_ITEMS, 21, 12, 11),
        _rows(_STATUSES, 202, 201, 203),
        _rows(_ORDERS, 42),
        _rows(_ITEMS, 422, 421),
        _rows(_STATUSES, 204),
        _rows(_ORDERS, 1, 2, 42),
    ]


def _terminal_page_script() -> list[list[dict[str, Any]]]:
    """`m-snapshot-read-028`: two full pages, then the empty one exhaustion costs."""
    return [
        _rows(_ORDERS, 1, 2),
        _rows(_ITEMS, 21, 12, 11),
        _rows(_ORDERS, 3, 42),
        _rows(_ITEMS, 422, 421),
        [],
        _rows(_ORDERS, 1, 2, 3, 42),
    ]


def _multi_term_script() -> list[list[dict[str, Any]]]:
    """`m-snapshot-read-033`: three full pages under a two-term order, then empty."""
    return [
        _rows(_ORDERS, 5, 3),
        [],
        _rows(_ORDERS, 42, 4),
        _rows(_ITEMS, 422, 421),
        _rows(_ORDERS, 2, 1),
        _rows(_ITEMS, 21, 12, 11),
        [],
        _rows(_ORDERS, 5, 3, 42, 4, 2, 1),
    ]


def _nullable_script() -> list[list[dict[str, Any]]]:
    """`m-snapshot-read-032`: a nullable Sort Key delivered nulls-last, then empty."""
    return [
        _rows(_ORDERS, 1, 3),
        _rows(_ORDERS, 42, 2),
        _rows(_ORDERS, 5, 4),
        [],
        _rows(_ORDERS, 1, 2, 3, 4, 5, 42),
    ]


def _mixed_directions_script() -> list[list[dict[str, Any]]]:
    """`m-snapshot-read-031`: `active desc, qty asc` over three full pages."""
    return [
        _rows(_ORDERS, 1, 2),
        _rows(_ORDERS, 4, 42),
        _rows(_ORDERS, 3, 5),
        [],
        _rows(_ORDERS, 1, 2, 3, 4, 5, 42),
    ]


def _resident_script() -> list[list[dict[str, Any]]]:
    """`m-snapshot-read-035`: one root per page under two document-resident terms."""
    return [
        _rows(_TRIPS, 51),
        _rows(_TRIPS, 53),
        _rows(_TRIPS, 52),
        [],
        [dict(row) for row in _TRIP_REFERENCE],
    ]


def _typed_coordinate_script(member: str, value: object) -> list[list[dict[str, Any]]]:
    document = {
        "day": "2026-01-15",
        "clock": "09:30:00",
        "amount": "10.25",
        "payload": "0a1b",
        "token": "00000000-0000-4000-8000-0000000000ab",
        "instant": "2026-01-15T09:30:00.000000Z",
        "f32": 1.5,
        "f64": 2.25,
    }
    document[member] = value
    reference = {
        "id": 101,
        "day": "2026-01-15",
        "clock": "09:30:00",
        "amount": Decimal("10.25"),
        "payload": "0a1b",
        "token": "00000000-0000-4000-8000-0000000000ab",
        "instant": "2026-01-15T09:30:00+00:00",
        "f32": 1.5,
        "f64": 2.25,
    }
    return [[{"id": 101, "coordinates": document}], [], [reference]]


def _history_script() -> list[list[dict[str, Any]]]:
    """`m-snapshot-read-036`: one milestone per page, then the empty terminal page."""
    return [[_LINES[0]], [_LINES[1]], [_LINES[2]], [], [dict(row) for row in _LINES]]


def test_a_delivery_whose_pages_return_the_authored_roots_passes(corpus_case: CaseLoader) -> None:
    case = corpus_case(_DEEP_FETCH)
    reads = ScriptedReads(results=_deep_fetch_script())

    assert_case_read(case, reads)

    assert len(reads.calls) == 7


def test_each_pages_child_levels_are_consumed_before_the_next_pages_root(
    corpus_case: CaseLoader,
) -> None:
    """The page partition is recovered as the delivery runs, never sliced up front.

    Page one's group is its root plus two child levels; page two's root is the
    fourth statement, not the second. A grader that sliced ``1 + L`` off the front
    would send page two's root through the items level.
    """
    case = corpus_case(_DEEP_FETCH)
    reads = ScriptedReads(results=_deep_fetch_script())

    assert_case_read(case, reads)

    statements = case.golden_statements("postgres")
    assert reads.statements[3] == statements[3]
    assert reads.calls[3][1] == (1, 2, 42, 2, 2)


def test_a_full_final_page_costs_one_more_root_statement(corpus_case: CaseLoader) -> None:
    """Exhaustion is proven, not assumed: the terminal page returns no roots at all.

    Its Include level is elided with it — a level whose parents gathered no keys
    consumes nothing — so the empty page's group is one statement wide.
    """
    case = corpus_case(_TERMINAL_PAGE)
    reads = ScriptedReads(results=_terminal_page_script())

    assert_case_read(case, reads)

    assert len(reads.calls) == 6
    assert reads.calls[4][1] == (1, 2, 3, 42, 42, 2)


def test_the_same_delivery_at_two_batch_sizes_publishes_the_same_roots(
    corpus_case: CaseLoader,
) -> None:
    """A page size is a performance dial and nothing else.

    The batch-size twins share one model, one Object Query, and one ``then.graph``;
    only the partition differs, so the same four roots are graded against the same
    claim over three page statements and over two.
    """
    at_two = corpus_case(_BATCH_TWIN_2)
    at_three = corpus_case(_BATCH_TWIN_3)
    two_pages = ScriptedReads(
        results=[
            _rows(_ORDERS, 1, 2),
            _rows(_ORDERS, 3, 42),
            [],
            _rows(_ORDERS, 1, 2, 3, 42),
        ]
    )
    three_pages = ScriptedReads(
        results=[_rows(_ORDERS, 1, 2, 3), _rows(_ORDERS, 42), _rows(_ORDERS, 1, 2, 3, 42)]
    )

    assert_case_read(at_two, two_pages)
    assert_case_read(at_three, three_pages)

    assert at_two.expected_graph == at_three.expected_graph
    assert len(two_pages.calls) == 4
    assert len(three_pages.calls) == 3


def test_a_short_page_ends_the_delivery_without_a_terminal_statement(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_BATCH_TWIN_3)
    reads = ScriptedReads(
        results=[_rows(_ORDERS, 1, 2, 3), _rows(_ORDERS, 42), _rows(_ORDERS, 1, 2, 3, 42)]
    )

    assert_case_read(case, reads)

    assert len(case.golden_statements("postgres")) == 2


def test_a_nullable_sort_key_seeks_a_null_coordinate_through_a_null_test(
    corpus_case: CaseLoader,
) -> None:
    """Under Nulls Last a null coordinate ties through `is null` and compares nowhere.

    The last page seeks past a root whose `sku` is null, so its seek is the single
    branch the primary key contributes and it binds one coordinate, not three.
    """
    case = corpus_case(_NULLABLE_PLACEMENT)
    reads = ScriptedReads(results=_nullable_script())

    assert_case_read(case, reads)

    assert reads.calls[3][1] == (4, 2)


def test_a_multi_term_order_binds_a_coordinate_at_every_tie_depth(
    corpus_case: CaseLoader,
) -> None:
    case = corpus_case(_MIXED_DIRECTIONS)
    reads = ScriptedReads(results=_mixed_directions_script())

    assert_case_read(case, reads)

    assert reads.calls[1][1] == (True, True, True, 10, True, 10, 2, 2)


def test_a_page_returning_more_roots_than_it_asked_for_is_refused(
    corpus_case: CaseLoader,
) -> None:
    """The page size bounds the root positions a page delivers, whatever it returned."""
    case = corpus_case(_BATCH_TWIN_3)
    reads = ScriptedReads(results=[_rows(_ORDERS, 1, 2, 3, 42)])

    with pytest.raises(CaseFailure, match="A page size bounds the root positions"):
        assert_case_read(case, reads)


@pytest.mark.parametrize("dialect", ["postgres", "mariadb"])
def test_a_document_resident_order_seeks_through_its_own_extraction(
    corpus_case: CaseLoader, dialect: str
) -> None:
    """A resident member binds its Document Path ahead of every coordinate.

    One hole per segment on Postgres and one whole JSON path on MariaDB, so the
    same Continuation Order is a different bind list on the two — which is why the
    seek is derived per dialect rather than translated between them.
    """
    case = corpus_case(_DOCUMENT_RESIDENT)
    reads = ScriptedReads(dialect, results=_resident_script())

    assert_case_read(case, reads)

    assert reads.calls[1][1] == tuple(case.statement_binds(1, dialect))


@pytest.mark.parametrize(
    ("_case_id", "case_name", "member", "value"),
    _TYPED_COORDINATES,
    ids=[entry[0] for entry in _TYPED_COORDINATES],
)
def test_streamed_coordinate_types_share_declared_projection_across_authored_and_generated_terms(
    corpus_case: CaseLoader,
    _case_id: str,
    case_name: str,
    member: str,
    value: object,
) -> None:
    case = corpus_case(case_name)
    preflight_case_literals(case)
    reads = ScriptedReads(results=_typed_coordinate_script(member, value))

    assert_case_read(case, reads)

    assert reads.calls[1][1] == tuple(case.statement_binds(1, "postgres"))


def test_a_streamed_coordinate_refuses_decimal_text_equivalence_for_a_float_bind(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case("m-snapshot-read-044-stream-order-float32-coordinate.yaml")
    _statements(case)[1]["binds"]["postgres"][3] = Decimal("1.5")
    reads = ScriptedReads(results=_typed_coordinate_script("f32", 1.5))

    with pytest.raises(CaseFailure, match="root binds"):
        assert_case_read(case, reads)


def test_a_milestone_set_delivery_pins_each_root_at_its_own_edge(
    corpus_case: CaseLoader,
) -> None:
    """A `history` delivery publishes roots, and the declared graphs partition them.

    The Continuation Order's appended milestone edge makes each root arrive at its
    own edge, so the two declared pins recover two graphs from three roots
    delivered one at a time — the same partition interpretation the eager
    ``then.graphs`` terminal uses.
    """
    case = corpus_case(_HISTORY_BOUNDARY)
    reads = ScriptedReads(results=_history_script())

    assert_case_read(case, reads)

    assert reads.calls[2][1] == (
        100,
        1000,
        1000,
        1000,
        "2024-04-01T00:00:00.000000Z",
        1,
    )


# --- a delivery that reached the right rows the wrong way --------------------


def test_a_page_seeking_from_the_wrong_root_is_refused(damaged_case: CaseLoader) -> None:
    """The continuation is the previous page's LAST root, derived rather than trusted."""
    case = damaged_case(_DEEP_FETCH)
    _statements(case)[3]["binds"][3] = 1
    reads = ScriptedReads(results=_deep_fetch_script())

    with pytest.raises(CaseFailure, match="Continuation Order coordinate"):
        assert_case_read(case, reads)


def test_a_page_asking_for_the_wrong_size_is_refused(damaged_case: CaseLoader) -> None:
    """The requested size is `batchSize`, not whatever the golden happens to bind."""
    case = damaged_case(_DEEP_FETCH)
    _statements(case)[0]["binds"][-1] = 3
    reads = ScriptedReads(results=_deep_fetch_script())

    with pytest.raises(CaseFailure, match="the size it is asking for"):
        assert_case_read(case, reads)


def test_a_delivery_ending_on_a_full_page_is_refused(damaged_case: CaseLoader) -> None:
    """A full final page proves nothing, so dropping the terminal statement fails."""
    case = damaged_case(_TERMINAL_PAGE)
    del _statements(case)[4]
    reads = ScriptedReads(results=_terminal_page_script()[:4])

    with pytest.raises(CaseFailure, match="the delivery is not exhausted"):
        assert_case_read(case, reads)


def test_a_statement_after_the_delivery_ended_is_refused(damaged_case: CaseLoader) -> None:
    """A stream stops at its first short page, so nothing may follow it."""
    case = damaged_case(_DEEP_FETCH)
    entries = _statements(case)
    entries.append(copy.deepcopy(entries[3]))
    reads = ScriptedReads(results=_deep_fetch_script())

    with pytest.raises(CaseFailure, match="after the delivery ended"):
        assert_case_read(case, reads)


def test_a_continuing_page_that_does_not_seek_is_refused(damaged_case: CaseLoader) -> None:
    """A continuing page carries a conjunct the first page has no coordinate for.

    The bind oracle alone would accept this: the binds are unchanged and still
    name the right coordinate. What refuses it is that the two root SQL texts are
    equal, which no keyset-paged delivery can produce.
    """
    case = damaged_case(_DEEP_FETCH)
    entries = _statements(case)
    entries[3]["sql"] = copy.deepcopy(entries[0]["sql"])
    reads = ScriptedReads(results=_deep_fetch_script())

    with pytest.raises(CaseFailure, match="repeats the FIRST page's root SQL"):
        assert_case_read(case, reads)


def test_a_page_hoisting_the_wrong_leading_coordinate_is_refused(
    damaged_case: CaseLoader,
) -> None:
    """The hoisted range is DERIVED from the leading term's own coordinate.

    Its bind repeats a value the remainder binds again, so a golden that got it
    wrong still selects a plausible row set — and here selects the right one, the
    remainder being unchanged. What refuses it is that the derivation says which
    coordinate the range compares against.
    """
    case = damaged_case(_MIXED_DIRECTIONS)
    _statements(case)[1]["binds"][0] = False
    reads = ScriptedReads(results=_mixed_directions_script())

    with pytest.raises(CaseFailure, match="Continuation Order coordinate"):
        assert_case_read(case, reads)


def test_a_page_binding_the_wrong_tie_coordinate_is_refused(damaged_case: CaseLoader) -> None:
    """Every term of the order supplies its own coordinate, at every tie depth.

    The damaged bind is the second branch's `qty` coordinate — neither the
    leading term nor the primary key — so an oracle that continued from the last
    root's KEY alone, as a single-term order allows, would accept it.
    """
    case = damaged_case(_MIXED_DIRECTIONS)
    _statements(case)[1]["binds"][3] = 5
    reads = ScriptedReads(results=_mixed_directions_script())

    with pytest.raises(CaseFailure, match="Continuation Order coordinate"):
        assert_case_read(case, reads)


def test_a_page_dropping_its_hoisted_range_is_refused(damaged_case: CaseLoader) -> None:
    """The range is redundant by rows and required by contract.

    Removing it leaves a statement that selects exactly the same roots, so every
    result-level oracle passes; the delivery has simply given up the leading
    index range a non-nullable leading term is entitled to.
    """
    case = damaged_case(_MIXED_DIRECTIONS)
    entry = _statements(case)[1]
    entry["sql"] = {
        dialect: sql.replace("where t0.active <= ? and (", "where (")
        for dialect, sql in entry["sql"].items()
    }
    del entry["binds"][0]
    reads = ScriptedReads(results=_mixed_directions_script())

    with pytest.raises(CaseFailure, match="Continuation Order coordinate"):
        assert_case_read(case, reads)


def test_a_continuing_page_respelling_its_seek_is_refused(damaged_case: CaseLoader) -> None:
    """Two pages seeking coordinates of the same NULLNESS seek the same way.

    The damaged page reorders one disjunction, which no bind comparison sees: the
    binds are unchanged, in the same positions, and the statement selects exactly
    the same rows. Only the text is different, and a delivery whose page
    statements drift apart is one whose seek is not a function of its order.
    """
    case = damaged_case(_NULLABLE_PLACEMENT)
    entry = _statements(case)[2]
    entry["sql"] = {
        dialect: sql.replace(
            "where (t0.sku > ? or t0.sku is null or", "where (t0.sku is null or t0.sku > ? or"
        )
        for dialect, sql in entry["sql"].items()
    }
    reads = ScriptedReads(results=_nullable_script())

    with pytest.raises(CaseFailure, match="seeking the same shape of coordinates"):
        assert_case_read(case, reads)


def test_a_page_seeking_the_wrong_WAY_past_the_right_coordinates_is_refused(
    damaged_case: CaseLoader,
) -> None:
    """A page's binds carry its coordinates and never the direction it compares them in.

    The damaged page is the terminal one, whose coordinates are null where no
    other page's are, so no sibling page constrains its text; its binds are
    untouched and correct; and it still returns nothing, the one root it could
    have reached having been delivered already. Every other oracle here passes.
    What refuses it is that the Continuation Order composes the comparator, and
    an ascending term is never sought backwards.
    """
    case = damaged_case(_NULLABLE_PLACEMENT)
    entry = _statements(case)[3]
    entry["sql"] = {
        dialect: sql.replace("t0.id > ?", "t0.id < ?") for dialect, sql in entry["sql"].items()
    }
    reads = ScriptedReads(results=_nullable_script())

    with pytest.raises(CaseFailure, match="seeks .*, not "):
        assert_case_read(case, reads)


def test_continuing_pages_drifting_outside_their_seek_are_refused(
    damaged_case: CaseLoader,
) -> None:
    """A continuing page is the first page's statement plus the seek, and nothing else.

    Every continuing page here reverses the same ordering term, so they still
    agree with each other and the same-shape rule sees nothing; the seek they
    spell is untouched and so are their binds. What refuses it is that the pages
    no longer read the same rows the same way: a delivery whose later pages
    reorder themselves is not one read paged.
    """
    case = damaged_case(_MULTI_TERM_SEEK)
    for index in (2, 4, 6):
        entry = _statements(case)[index]
        entry["sql"] = {
            dialect: sql.replace(
                "order by t0.active asc, t0.id desc", "order by t0.active asc, t0.id asc"
            )
            for dialect, sql in entry["sql"].items()
        }
    reads = ScriptedReads(results=_multi_term_script())

    with pytest.raises(CaseFailure, match="ONE conjunct spliced into it"):
        assert_case_read(case, reads)


def test_a_continuing_page_negating_its_seek_is_refused(damaged_case: CaseLoader) -> None:
    """A seek is the expression an order COMPOSES, not the comparisons it mentions.

    The damaged page mentions exactly the comparisons and null checks its own
    coordinates compose, in exactly their order, and binds exactly what a correct
    page binds. It is the terminal one, whose null coordinate no sibling page's
    text constrains, and it still returns nothing. Only the Boolean shape is
    different, and a Continuation Order composes no negation at any depth.
    """
    case = damaged_case(_NULLABLE_PLACEMENT)
    entry = _statements(case)[3]
    entry["sql"] = {
        dialect: sql.replace("t0.id > ?", "not not t0.id > ?")
        for dialect, sql in entry["sql"].items()
    }
    reads = ScriptedReads(results=_nullable_script())

    with pytest.raises(CaseFailure, match="seeks .*, not "):
        assert_case_read(case, reads)


# --- the two spellings of a negated null test --------------------------------

# Under Nulls First what follows a null coordinate is the non-nulls, which the
# seek spells as a negated null test — the one leaf a page may write two ways.
# No shipped case authors Nulls First, so the delivery below is authored here: a
# nullable `sku` ordered nulls-first at `batchSize: 1`, delivering the null root
# and then one non-null one.
_NULLS_FIRST_BASE = (
    "select t0.id, t0.name, t0.sku, t0.qty, t0.price, t0.active, t0.ordered_on, "
    "t0.sku parallax_seek_0, t0.id parallax_seek_1 from orders t0"
)
_NULLS_FIRST_TAIL = " order by t0.sku asc nulls first, t0.id asc limit ?"


# The appended `id asc` is non-nullable, so its branch admits NULLs wherever the
# EMITTED clause placed them, which is each dialect's own convention: Postgres
# trails them on `asc` and MariaDB leads them. The two spellings therefore differ
# on that leaf alone, over a column that holds no NULL.
_KEY_AFTER = {"postgres": "(t0.id > ? or t0.id is null)", "mariadb": "t0.id > ?"}


def _nulls_first_case(case: Case, non_nulls: str) -> Case:
    """*case* re-authored as a Nulls First delivery, its second page spelled as given."""
    case.when["objectQuery"]["orderBy"] = [
        {"attr": "parallax.compatibility.Order.sku", "nulls": "first"}
    ]
    case.when["stream"]["batchSize"] = 1
    pages = [
        {dialect: f"{_NULLS_FIRST_BASE}{_NULLS_FIRST_TAIL}" for dialect in _KEY_AFTER},
        {
            dialect: f"{_NULLS_FIRST_BASE} where ({non_nulls} or (t0.sku is null and {key}))"
            f"{_NULLS_FIRST_TAIL}"
            for dialect, key in _KEY_AFTER.items()
        },
        {
            dialect: f"{_NULLS_FIRST_BASE} where (t0.sku > ? or (t0.sku = ? and {key}))"
            f"{_NULLS_FIRST_TAIL}"
            for dialect, key in _KEY_AFTER.items()
        },
    ]
    binds: list[list[Any]] = [[1], [4, 1], ["A-100", "A-100", 1, 1]]
    case.then["statements"] = [
        {"sql": sql, "binds": bound} for sql, bound in zip(pages, binds, strict=True)
    ]
    case.then["graph"] = {
        "Order": [
            {
                "id": 4,
                "name": "Margaret",
                "sku": None,
                "qty": 20,
                "price": "40.00",
                "active": True,
                "orderedOn": "2024-04-20",
            },
            {
                "id": 1,
                "name": "Ada",
                "sku": "A-100",
                "qty": 5,
                "price": "10.50",
                "active": True,
                "orderedOn": "2024-01-05",
            },
        ]
    }
    del case.then["referenceSql"]
    return case


@pytest.mark.parametrize("spelling", ["t0.sku is not null", "not t0.sku is null"])
@pytest.mark.parametrize("dialect", ["postgres", "mariadb"])
def test_either_production_spelling_of_a_negated_null_check_is_accepted(
    damaged_case: CaseLoader, dialect: str, spelling: str
) -> None:
    """A valid continuation is accepted however its null check is written.

    sqlglot reads `x is not null` into `not x is null`'s tree under MariaDB and
    keeps the two apart under Postgres. Both are one leaf of the expression the
    order composes, so a seek graded as an expression must accept either on
    either dialect.
    """
    case = _nulls_first_case(damaged_case(_NULLABLE_PLACEMENT), spelling)
    reads = ScriptedReads(dialect, results=[_rows(_ORDERS, 4), _rows(_ORDERS, 1), []])

    assert_case_read(case, reads)


@pytest.mark.parametrize("dialect", ["postgres", "mariadb"])
def test_a_DOUBLY_negated_null_check_is_refused_on_either_dialect(
    damaged_case: CaseLoader, dialect: str
) -> None:
    """One negation is a spelling of the leaf; two are a shape the order never composes.

    The damaged page selects exactly the rows a correct one selects — `not sku is
    not null` is `sku is null` — and binds exactly what a correct page binds, so
    only the composed Boolean shape tells them apart. sqlglot hands the dialects
    different trees for it, so folding the pair away rather than one negation
    would make the same text's verdict depend on which parser read it.
    """
    case = _nulls_first_case(damaged_case(_NULLABLE_PLACEMENT), "not t0.sku is not null")
    reads = ScriptedReads(dialect, results=[_rows(_ORDERS, 4), _rows(_ORDERS, 1), []])

    with pytest.raises(CaseFailure, match="seeks .*, not "):
        assert_case_read(case, reads)


# --- a document-resident Continuation Order ----------------------------------

# The Document Path spellings the resident case's pages carry, per dialect: one
# hole per segment on Postgres, one whole JSON path on MariaDB.
_RESIDENT_EXTRACTIONS = {
    "postgres": (
        "cast(jsonb_extract_path_text(t0.payload, ?) as bigint)",
        "jsonb_extract_path_text(t0.payload, ?)",
    ),
    "mariadb": (
        "cast(json_value(t0.payload, ?) as signed)",
        "json_value(t0.payload, ?)",
    ),
}

# The same extraction under a target m-dialect does NOT give `nights`, spelled so
# that it orders the fixture's values exactly as the declared target does.
_RETARGETED_RESIDENT_CAST = {
    "postgres": "cast(jsonb_extract_path_text(t0.payload, ?) as decimal(18, 2))",
    "mariadb": "cast(json_value(t0.payload, ?) as decimal(18, 2))",
}


def _respell_resident_pages(case: Case, was: str, now: str) -> None:
    """Rewrite every continuing page of the resident case, each dialect its own way."""
    for entry in _statements(case)[1:]:
        entry["sql"] = {
            dialect: sql.replace(
                was.format(*_RESIDENT_EXTRACTIONS[dialect]),
                now.format(*_RESIDENT_EXTRACTIONS[dialect]),
            )
            for dialect, sql in entry["sql"].items()
        }


def test_a_resident_branch_that_dropped_its_grouping_is_refused(
    damaged_case: CaseLoader,
) -> None:
    """A tie's own two-way branch has to be grouped, and the seek grades that.

    Ungrouped, `and` binds tighter than `or`, so the second branch becomes
    "destination at its coordinate and nights strictly after its own" OR "nights
    is null" — which admits every null-`nights` trip whatever its destination,
    re-delivering roots the stream already published. The fixtures have no such
    trip, so the damaged pages return exactly the rows the correct ones return
    and bind exactly what they bind. The runner's canonical-SQL layer refuses the
    spelling first; here, with only the read oracle running, what refuses it is
    that the flattened branch is not the expression the order composes.
    """
    case = damaged_case(_DOCUMENT_RESIDENT)
    _respell_resident_pages(case, "and ({0} < ? or {1} is null))", "and {0} < ? or {1} is null)")
    reads = ScriptedReads(results=_resident_script())

    with pytest.raises(CaseFailure, match="seeks .*, not "):
        assert_case_read(case, reads)


def test_a_resident_null_check_spelled_against_the_cast_is_refused(
    damaged_case: CaseLoader,
) -> None:
    """Presence is asked of the extraction, and the cast is not part of the question.

    Casting before a null test selects the same rows — a cast of NULL is NULL — so
    the damaged pages deliver the same graph and bind the same paths in the same
    places. What differs is that the statement claims the declared type stands
    between the document and a presence question that never asks it.
    """
    case = damaged_case(_DOCUMENT_RESIDENT)
    _respell_resident_pages(case, "or {1} is null))", "or {0} is null))")
    reads = ScriptedReads(results=_resident_script())

    with pytest.raises(CaseFailure, match="seeks .*, not "):
        assert_case_read(case, reads)


def test_a_resident_comparison_that_dropped_its_cast_is_refused(
    damaged_case: CaseLoader,
) -> None:
    """A member whose document form does not order as text compares under its cast.

    `nights` is an `int32`, so the damaged page compares `"7"` against `"1"` as
    text. Both fixture values are single digits, so the rows and the ordering are
    unchanged and every bind still lands where it did — the statement simply stops
    claiming the cast m-dialect's table gives the numeric family.
    """
    case = damaged_case(_DOCUMENT_RESIDENT)
    _respell_resident_pages(case, "{0} < ?", "{1} < ?")
    reads = ScriptedReads(results=_resident_script())

    with pytest.raises(CaseFailure, match="seeks .*, not "):
        assert_case_read(case, reads)


def test_a_resident_comparison_under_ANOTHER_cast_target_is_refused(
    damaged_case: CaseLoader,
) -> None:
    """A cast is graded down to the target m-dialect's table names for the type.

    The damaged pages still cast, and to a target that orders the fixture's
    `nights` exactly as the declared one does — so they select the same rows, hand
    the next page the same cursor, and bind what a correct page binds. Nothing
    downstream of the statement can tell them apart: only the target itself says
    which type the comparison claims to be in.
    """
    case = damaged_case(_DOCUMENT_RESIDENT)
    for entry in _statements(case)[1:]:
        entry["sql"] = {
            dialect: sql.replace(
                f"{_RESIDENT_EXTRACTIONS[dialect][0]} <", f"{_RETARGETED_RESIDENT_CAST[dialect]} <"
            ).replace(
                f"{_RESIDENT_EXTRACTIONS[dialect][0]} =", f"{_RETARGETED_RESIDENT_CAST[dialect]} ="
            )
            for dialect, sql in entry["sql"].items()
        }
    reads = ScriptedReads(results=_resident_script())

    with pytest.raises(CaseFailure, match="seeks .*, not "):
        assert_case_read(case, reads)


def test_a_resident_page_binding_the_wrong_path_first_is_refused(
    damaged_case: CaseLoader,
) -> None:
    """Which member an extraction reads is a BIND, so the paths are graded as binds.

    Two resident terms over one Structured Column spell one expression and are
    told apart only by the Document Paths their holes carry, in the order the seek
    composes them. Swapping the leading branch's path for the second term's leaves
    the statement text untouched.

    The seek's own binds begin after the two coordinate cells the page captures,
    whose paths precede everything the `where` clause binds.
    """
    case = damaged_case(_DOCUMENT_RESIDENT)
    cells = 2
    for entry in _statements(case)[1:]:
        for dialect, binds in entry["binds"].items():
            entry["binds"][dialect] = [*binds]
            entry["binds"][dialect][cells] = binds[cells + 5]
    reads = ScriptedReads(results=_resident_script())

    with pytest.raises(CaseFailure, match="root binds"):
        assert_case_read(case, reads)


def test_a_resident_sort_key_at_a_TABLELESS_POSITION_issues_no_query(
    damaged_case: CaseLoader,
) -> None:
    """Residence belongs to a Table, and an abstract position holds none of its own.

    The read is at a table-per-concrete-subtype root ordered by `title`: every
    concrete branch keeps that member inside its own document, while the root
    itself has no Table to be asked. No one extraction spells it, so the order
    cannot be derived — a refusal knowable before execution, which therefore
    issues no query.
    """
    case = damaged_case(_TABLELESS_POSITION)
    case.when["stream"] = {"batchSize": 1}
    reads = ScriptedReads()

    with pytest.raises(CaseFailure, match="document-resident member"):
        assert_case_read(case, reads)

    assert reads.calls == []


# --- a milestone set's own third order component -----------------------------


def test_a_milestone_page_seeking_past_the_key_alone_is_refused(
    damaged_case: CaseLoader,
) -> None:
    """A page that dropped the edge from its seek still reaches real rows.

    Damaged this way, page 2 asks for everything after line 1000 rather than
    after line 1000's FIRST milestone, which is exactly the skip the edge exists
    to prevent — and the rows it returns are a legal suffix of the result, so
    nothing about the page itself looks wrong. What refuses it is that the seek
    is derived from the Continuation Order, whose last term is the edge.
    """
    case = damaged_case(_HISTORY_BOUNDARY)
    for entry in _statements(case)[1:]:
        entry["sql"] = {
            dialect: sql.replace(
                "and t0.id >= ? and (t0.id > ? or (t0.id = ? and t0.in_z > ?))", "and t0.id > ?"
            )
            for dialect, sql in entry["sql"].items()
        }
        entry["binds"] = [entry["binds"][0], entry["binds"][1], entry["binds"][-1]]
    reads = ScriptedReads(results=_history_script())

    with pytest.raises(CaseFailure, match="root binds"):
        assert_case_read(case, reads)


def test_a_milestone_page_continuing_from_another_milestone_is_refused(
    damaged_case: CaseLoader,
) -> None:
    """The coordinate is the edge of the root the previous page ENDED on.

    Every bind here names a real milestone of the object the page is continuing
    through, and the damaged page still returns rows in the right order — it
    simply resumes from the wrong rectangle. Only the derivation says which.
    """
    case = damaged_case(_MILESTONE_EDGE_PINS)
    binds = _statements(case)[2]["binds"]
    binds[7] = _statements(case)[1]["binds"][7]
    reads = ScriptedReads(results=[[_POSITIONS[0]], [_POSITIONS[1]]])

    with pytest.raises(CaseFailure, match="Continuation Order coordinate"):
        assert_case_read(case, reads)


def test_a_streamed_milestone_graph_claiming_the_wrong_root_is_refused(
    damaged_case: CaseLoader,
) -> None:
    """`then.graphs` states which milestone each DELIVERED root stands at.

    Moving one root between two declared graphs leaves the delivery, its pages,
    and its seek coordinates untouched, and the two graphs still hold every root
    exactly once between them. What refuses it is the pin partition: a root is
    grouped by the edge it was published at, not by the entry that names it.
    """
    case = damaged_case(_HISTORY_BOUNDARY)
    graphs = case.then["graphs"]
    graphs[1]["graph"]["InvoiceLine"].append(graphs[0]["graph"]["InvoiceLine"].pop())
    reads = ScriptedReads(results=_history_script())

    with pytest.raises(CaseFailure, match="assembled graph"):
        assert_case_read(case, reads)


# --- infrastructure failure is not a mismatch --------------------------------


def test_a_driver_exception_from_a_page_propagates_unchanged(corpus_case: CaseLoader) -> None:
    case = corpus_case(_BATCH_TWIN_3)
    boom = RuntimeError("connection reset")
    reads = ScriptedReads(results=[_rows(_ORDERS, 1, 2, 3), boom])

    with pytest.raises(RuntimeError, match="connection reset"):
        assert_case_read(case, reads)
