"""Page-wide Entity State and root-local Snapshot publication."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

import pytest

from parallax.conformance.story_models import ORDERS_MODEL
from parallax.core.base import SQL_NULL
from parallax.core.deep_fetch import RelationshipViewKey
from parallax.core.entity._model import model_of
from parallax.core.metamodel import RelationshipIdentity
from parallax.core.temporal_read import Pin
from parallax.snapshot.materialize import PageBuilder, RootView
from parallax.snapshot.materialize._page import page_rows, root_last_uses
from parallax.snapshot.materialize._views import ROOT_LEVEL, ViewSchema
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._prepared_read_support import bound_read
from tests.unit.snapshot._encoded_page_models import ENCODED_ORDERS
from tests.unit.snapshot._snapshot_page_support import (
    PageFixture,
    RecordingObserver,
    identity_of,
    recorded_conversion_dependencies,
    rendered_members,
)

_ENCODED = model_of(ENCODED_ORDERS)
_ANIMAL = corpus_model("animal")


def _order(order_id: object, name: str = "Ada") -> dict[str, object]:
    return {
        "id": order_id,
        "name": name,
        "sku": "A-100",
        "qty": 5,
        "price": 10,
        "active": True,
        "ordered_on": None,
    }


def _encoded_order(key: str | None, name: str = "Ada", badge: str = "0f") -> dict[str, object]:
    return {"id_hex": key, "name": name, "badge_hex": badge, "address": SQL_NULL}


def _page(
    occurrences: tuple[tuple[int, dict[str, object]], ...],
    observer: RecordingObserver | None = None,
) -> tuple[object, tuple[int, ...]]:
    source_count = max((source for source, _row in occurrences), default=0) + 1
    builder = PageBuilder(ViewSchema(tuple(() for _ in range(source_count))), observer)
    prepared = bound_read(_ENCODED, "EncodedOrder")
    roots = tuple(
        prepared.convert_row(row, builder, source=source)[0] for source, row in occurrences
    )
    return builder.finish(roots, Pin()), roots


def test_equal_witnesses_decode_once_and_share_one_page_state() -> None:
    with recorded_conversion_dependencies() as calls:
        page, _roots = _page(
            ((ROOT_LEVEL, _encoded_order("01")), (ROOT_LEVEL, _encoded_order("01")))
        )
        assert calls.decoded == ["01", "01"]

        first = RootView(cast("Any", page), 0)
        second = RootView(cast("Any", page), 1)

    assert calls.decoded == ["01", "01", "0f"]
    assert len(page_rows(page).judged_states.group(0)) == 1
    assert first.member_values(0) is second.member_values(0)


def test_separate_roots_may_store_unequal_witnesses_for_one_logical_key() -> None:
    page, _roots = _page(((0, _encoded_order("01", "Ada")), (1, _encoded_order("01", "Grace"))))

    first = RootView(cast("Any", page), 0)
    second = RootView(cast("Any", page), 1)

    assert first.member_values(0)[1] == "Ada"
    assert second.member_values(0)[1] == "Grace"
    assert len(page_rows(page).judged_states.group(0)) == 2


def test_keyless_occurrences_are_judged_only_when_their_root_is_requested() -> None:
    with recorded_conversion_dependencies() as calls:
        page, _roots = _page(
            ((0, _encoded_order(None, badge="0e")), (0, _encoded_order(None, badge="0f")))
        )
        assert calls.decoded == []
        assert page_rows(cast("Any", page)).roots == (0, 1)

        first = RootView(cast("Any", page), 0)
        assert calls.decoded == ["0e"]
        assert [root.ordinal for root in first.invalid_roots] == [0]

        second = RootView(cast("Any", page), 1)
        assert calls.decoded == ["0e", "0f"]
        assert [root.ordinal for root in second.invalid_roots] == [1]


def test_a_root_view_reaches_only_its_roots_nodes_and_unions_its_views() -> None:
    fixture = PageFixture(ORDERS_MODEL, "Order.items", "Order.itemsByShipDate")
    first = fixture.node("Order", _order(1))
    second = fixture.node("Order", _order(2, "Grace"))
    item = fixture.node(
        "OrderItem",
        {"id": 10, "order_id": 1, "sku": "A-100", "quantity": 1, "shipped_on": None},
    )
    fixture.attach(first, "Order.items", (item,))
    fixture.attach(first, "Order.itemsByShipDate", (item,))
    fixture.attach(second, "Order.items", ())
    fixture.attach(second, "Order.itemsByShipDate", ())
    page = fixture.page(first, second)

    first_view = RootView(page, 0)
    second_view = RootView(page, 1)

    assert [identity.name for identity in first_view.order] == ["Order", "OrderItem"]
    assert [identity.name for identity in second_view.order] == ["Order"]
    assert first_view.view(0, 0) == first_view.view(0, 1) == (1,)


def test_page_storage_reports_projection_width_and_handles_a_view_cycle() -> None:
    fixture = PageFixture(ORDERS_MODEL, "Order.items", "OrderItem.order")
    order = fixture.node("Order", _order(1))
    item = fixture.node(
        "OrderItem",
        {"id": 10, "order_id": 1, "sku": "A-100", "quantity": 1, "shipped_on": None},
    )
    fixture.attach(order, "Order.items", (item,))
    fixture.attach(item, "OrderItem.order", order)
    page = fixture.page(order)
    rows = page_rows(page)

    assert len(rows.issues) == 2
    assert len(rows.decoders) == 2
    assert len(rows.overwritten_edges) == 2
    projection_last, logical_last = root_last_uses(page)
    assert tuple(projection_last) == (0, 0)
    assert tuple(logical_last) == (0, 0)


def test_releasing_a_root_view_twice_is_idempotent() -> None:
    page, _roots = _page(((ROOT_LEVEL, _order(1)),))
    root = RootView(cast("Any", page), 0)

    root.release_finished_page_rows(0, root_last_uses(cast("Any", page)))
    root.release_finished_page_rows(0, root_last_uses(cast("Any", page)))


def publish_roots(page: Any, observer: RecordingObserver) -> Iterator[object]:
    from parallax.snapshot.handle._materialization import Materializer

    def publish(_root: RootView, position: int) -> Iterator[object]:
        yield position

    yield from Materializer(observer).roots(page, publish)


def test_root_zero_publishes_before_root_one_state_is_decoded() -> None:
    observer = RecordingObserver()
    page, _roots = _page(
        ((ROOT_LEVEL, _encoded_order("01")), (ROOT_LEVEL, _encoded_order("02"))), observer
    )

    assert list(publish_roots(page, observer)) == [0, 1]
    relevant = [
        name for name, _value in observer.events if name in {"states_decoded", "root_published"}
    ]
    assert relevant == ["states_decoded", "root_published", "states_decoded", "root_published"]


def _shared_keyless_animal(owners: tuple[int, ...], animal_row: dict[str, object]) -> object:
    """A Page rooted at ``owners``, each Person owning the one keyless Animal
    occurrence ``animal_row`` claims."""
    animals = RelationshipViewKey(RelationshipIdentity(identity_of(_ANIMAL, "Person"), "animals"))
    builder = PageBuilder(ViewSchema.of(animals))
    animal, *_ = bound_read(_ANIMAL, "Animal").convert_row(animal_row, builder, source=ROOT_LEVEL)
    people = bound_read(_ANIMAL, "Person")
    roots = tuple(
        people.convert_row({"id": owner, "name": f"P{owner}"}, builder, source=ROOT_LEVEL)[0]
        for owner in owners
    )
    for root in roots:
        builder.write_view(root, animals, (animal,))
    return builder.finish(roots, Pin())


@pytest.mark.parametrize(
    ("owners", "atomic"),
    [
        pytest.param((1, 2), False, id="streamed"),
        pytest.param((1, 2), True, id="atomic"),
        pytest.param((1, 2, 1), True, id="atomic-releasing-at-last-use"),
    ],
)
@pytest.mark.parametrize(
    ("animal_row", "expected"),
    [
        pytest.param(
            {"id": 7, "kind": "unicorn", "owner_id": 1},
            ({"id": 7, "ownerId": 1}, [("stored-data-family-tag-unknown", "unicorn")]),
            id="unknown-concrete",
        ),
        pytest.param(
            {"kind": "dog", "name": "Rex", "owner_id": 1},
            ({"name": "Rex", "ownerId": 1}, list[object]()),
            id="without-key-column",
        ),
    ],
)
def test_a_keyless_occurrence_is_judged_again_for_every_root_reaching_it(
    owners: tuple[int, ...],
    atomic: bool,
    animal_row: dict[str, object],
    expected: tuple[object, ...],
) -> None:
    # A keyless claim shares no judged state, so each root reaching it judges its
    # payload anew, after earlier roots released what they alone reached.
    from parallax.snapshot.handle._materialization import Materializer

    page = _shared_keyless_animal(owners, animal_row)

    def publish(root: RootView, _position: int) -> Iterator[tuple[object, ...]]:
        (node,) = (node for node, concrete in enumerate(root.order) if concrete.name != "Person")
        yield (
            rendered_members(root.layout(node), root.member_values(node)),
            [(issue.code, issue.stored_value) for issue in root.issues(node)],
        )

    published = list(
        Materializer(RecordingObserver()).roots(
            cast("Any", page), publish, atomic=atomic, model=_ANIMAL
        )
    )

    assert published == [expected] * len(owners)
