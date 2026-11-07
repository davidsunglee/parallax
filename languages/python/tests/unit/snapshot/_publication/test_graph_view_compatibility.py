"""The decision whether a Page's roots share one graph, over real Pages.

Each compatibility condition is a pair that differs only in that condition, because
the decision's input space is larger than a seeded database can reach: a Page
hand-built here states a concrete collision, a coordinate split, and a slot's exact
contents directly.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

import pytest

from parallax.core import ONE_TO_MANY, Attr, Bitemporal, DomainModel, Entity, Int32, Rel, attr, rel
from parallax.core.base import SQL_NULL
from parallax.core.read_delivery._page import PageSchedule, page_rows
from parallax.snapshot._publication._graph_view import GraphView
from tests._support.tpcs_inverse_models import INVERSE_MODEL, LINK_ROW
from tests.unit.snapshot._encoded_identity_read import encoded_identity_read
from tests.unit.snapshot._encoded_page_models import ENCODED_ORDERS
from tests.unit.snapshot._snapshot_page_support import PageFixture

_NS: Final = "parallax.compatibility"
_ITEMS: Final = f"{_NS}.EncodedOrder.items"
_BY_CODE: Final = f"{_NS}.EncodedOrder.itemsByCode"
_PARENTS: Final = "InverseOwner.parents"
_LINKS: Final = "InverseParent.links"
_UNDECODABLE: Final = "not-hex"
_FIRST_START: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_SECOND_START: Final = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
_END: Final = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
_SPAN: Final = "Entry.span"


class Span(Bitemporal, table="compatibility_span"):
    id: Attr[int] = attr(primary_key=True)
    rate: Attr[int] = attr(type=Int32)
    entries: Rel[tuple[Entry, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "span_id"))


class Entry(Entity, table="compatibility_entry"):
    id: Attr[int] = attr(primary_key=True)
    span_id: Attr[int]
    span: Rel[Span | None] = rel(reverse_of="entries")


_SPANS: Final = DomainModel(Span, Entry)


def _resolved(fixture: PageFixture, *roots: int) -> tuple[frozenset[int] | None, GraphView]:
    view = GraphView(page_rows(fixture.page(*roots)), PageSchedule(None, False), read_evidence={})
    return view.resolve_shared_roots(), view


def _order(fixture: PageFixture, order_id: int) -> int:
    return fixture.node(
        "EncodedOrder",
        {"id": order_id, "name": "order", "badge_hex": None, "address": None},
    )


def _item(fixture: PageFixture, *, code: str = "0c") -> int:
    return fixture.node("EncodedOrderItem", {"id": 11, "order_id": 1, "code_hex": code})


def _orders_reaching_one_item(fixture: PageFixture) -> tuple[int, int]:
    first, second = _order(fixture, 1), _order(fixture, 2)
    item = _item(fixture)
    fixture.attach(first, _ITEMS, (item,))
    fixture.attach(second, _ITEMS, (item,))
    return first, second


def test_roots_reaching_one_row_share_it_and_keep_their_own_nodes() -> None:
    fixture = PageFixture(ENCODED_ORDERS, _ITEMS)
    first, second = _orders_reaching_one_item(fixture)

    invalid, view = _resolved(fixture, first, second)

    assert invalid == frozenset()
    assert len(view) == 3
    assert view.root_node(0) != view.root_node(1)


def test_a_diamond_within_one_root_is_no_overlap() -> None:
    fixture = PageFixture(ENCODED_ORDERS, _ITEMS, _BY_CODE)
    first, second = _order(fixture, 1), _order(fixture, 2)
    fixture.attach(first, _ITEMS, (_item(fixture),))
    fixture.attach(first, _BY_CODE, (_item(fixture),))

    assert _resolved(fixture, first, second)[0] is None


@pytest.mark.parametrize(("views", "shares"), [((_ITEMS,), True), ((), False)])
def test_roots_carrying_no_view_are_not_walked(views: tuple[str, ...], shares: bool) -> None:
    fixture = PageFixture(ENCODED_ORDERS, *views)
    roots = (_order(fixture, 1), _order(fixture, 1))

    assert (_resolved(fixture, *roots)[0] is not None) is shares


@pytest.mark.parametrize(("code", "shares"), [("0c", True), ("0d", False)])
def test_stored_state_must_be_equal(code: str, shares: bool) -> None:
    fixture = PageFixture(ENCODED_ORDERS, _ITEMS)
    first, second = _order(fixture, 1), _order(fixture, 2)
    fixture.attach(first, _ITEMS, (_item(fixture),))
    fixture.attach(second, _ITEMS, (_item(fixture, code=code),))

    assert (_resolved(fixture, first, second)[0] is not None) is shares


def _span(fixture: PageFixture, start: dt.datetime, *, rate: int = 1) -> int:
    return fixture.node(
        "Span",
        {"id": 1, "rate": rate, "from_z": start, "thru_z": _END, "in_z": start, "out_z": _END},
    )


def _entry(fixture: PageFixture, *spans: int) -> int:
    entry = fixture.node("Entry", {"id": 11, "span_id": 1})
    for span in spans:
        fixture.attach(span, "Span.entries", (entry,))
    return entry


@pytest.mark.parametrize(
    ("second_start", "nodes"), [(_SECOND_START, 3), (_FIRST_START, None)], ids=["split", "same"]
)
def test_temporal_coordinates_keep_unequal_rows_apart(
    second_start: dt.datetime, nodes: int | None
) -> None:
    fixture = PageFixture(_SPANS, "Span.entries")
    first, second = _span(fixture, _FIRST_START), _span(fixture, second_start, rate=2)
    _entry(fixture, first, second)

    invalid, view = _resolved(fixture, first, second)

    assert (None if invalid is None else len(view)) == nodes


def _inverse_owner(fixture: PageFixture, owner_id: int) -> int:
    return fixture.node("InverseOwner", {"id": owner_id})


def _parent(fixture: PageFixture, concrete: str = "InverseAlpha") -> int:
    return fixture.node(concrete, {"id": 1, "label": "same", "owner_id": 10})


@pytest.mark.parametrize(("concrete", "shares"), [("InverseAlpha", True), ("InverseBeta", False)])
def test_the_concrete_must_be_the_same(concrete: str, shares: bool) -> None:
    fixture = PageFixture(INVERSE_MODEL, _PARENTS)
    first, second = _inverse_owner(fixture, 10), _inverse_owner(fixture, 11)
    fixture.attach(first, _PARENTS, (_parent(fixture),))
    fixture.attach(second, _PARENTS, (_parent(fixture, concrete),))

    assert (_resolved(fixture, first, second)[0] is not None) is shares


def _link(fixture: PageFixture, link_id: int) -> int:
    return fixture.node("InverseLink", {**LINK_ROW, "id": link_id})


def _parents_of_one_row(fixture: PageFixture) -> tuple[int, int, int, int]:
    """Two owners reaching one Parent through two fetched rows, the first of which
    loads links 11 and 12. Answers the owners and the second row, and link 12."""
    first_owner, second_owner = _inverse_owner(fixture, 10), _inverse_owner(fixture, 11)
    first, second = _parent(fixture), _parent(fixture)
    fixture.attach(first_owner, _PARENTS, (first,))
    fixture.attach(second_owner, _PARENTS, (second,))
    link = _link(fixture, 12)
    fixture.attach(first, _LINKS, (_link(fixture, 11), link))
    return first_owner, second_owner, second, link


def test_a_view_loaded_at_only_one_position_is_compatible() -> None:
    fixture = PageFixture(INVERSE_MODEL, _PARENTS, _LINKS)
    first_owner, second_owner, _second, _link_12 = _parents_of_one_row(fixture)

    assert _resolved(fixture, first_owner, second_owner)[0] == frozenset()


def test_a_view_naming_the_same_nodes_through_other_fetched_rows_is_compatible() -> None:
    fixture = PageFixture(INVERSE_MODEL, _PARENTS, _LINKS)
    first_owner, second_owner, second, _link_12 = _parents_of_one_row(fixture)
    fixture.attach(second, _LINKS, (_link(fixture, 11), _link(fixture, 12)))

    assert _resolved(fixture, first_owner, second_owner)[0] == frozenset()


@pytest.mark.parametrize("ids", [(11,), (12, 11)], ids=["members", "order"])
def test_a_view_must_name_the_same_members_in_the_same_order(ids: tuple[int, ...]) -> None:
    fixture = PageFixture(INVERSE_MODEL, _PARENTS, _LINKS)
    first_owner, second_owner, second, _link_12 = _parents_of_one_row(fixture)
    fixture.attach(second, _LINKS, tuple(_link(fixture, link_id) for link_id in ids))

    assert _resolved(fixture, first_owner, second_owner)[0] is None


@pytest.mark.parametrize(
    ("second_start", "shares"), [(_FIRST_START, True), (_SECOND_START, False)], ids=["one", "two"]
)
def test_a_back_reference_must_name_one_logical_row(
    second_start: dt.datetime, shares: bool
) -> None:
    fixture = PageFixture(_SPANS, "Span.entries", references={_SPAN: ("Span",)})
    first, second = _span(fixture, _FIRST_START), _span(fixture, second_start)
    entry = _entry(fixture, first, second)
    fixture.attach_reference(entry, _SPAN, "Span", "Entry.spanId")

    assert (_resolved(fixture, first, second)[0] is not None) is shares


@pytest.mark.parametrize(("code", "shares"), [("0c", True), (_UNDECODABLE, False)])
def test_a_finding_on_a_reached_row_keeps_the_page_from_sharing(code: str, shares: bool) -> None:
    fixture = PageFixture(ENCODED_ORDERS, _ITEMS)
    first, second = _order(fixture, 1), _order(fixture, 2)
    item = _item(fixture, code=code)
    fixture.attach(first, _ITEMS, (item,))
    fixture.attach(second, _ITEMS, (item,))

    assert (_resolved(fixture, first, second)[0] is not None) is shares


@pytest.mark.parametrize("keyless", [False, True], ids=["keyed", "keyless"])
def test_a_keyless_root_keeps_the_page_from_sharing(keyless: bool) -> None:
    fixture = PageFixture(ENCODED_ORDERS, _ITEMS)
    roots = _orders_reaching_one_item(fixture)
    if keyless:
        row = encoded_identity_read().record_row((None, None, SQL_NULL), fixture.builder, source=0)
        roots = (*roots, row[0])

    assert (_resolved(fixture, *roots)[0] is None) is keyless
