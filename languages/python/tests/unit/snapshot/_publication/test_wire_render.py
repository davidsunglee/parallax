"""Wire rendering from prepared model facts and include-tree plans."""

from __future__ import annotations

from typing import Any, Final, cast

import pytest

from parallax.core._execution import _planning as planning_module
from parallax.core._execution._concurrency import CONCURRENCY
from parallax.core.base import DATE, STRING
from parallax.core.deep_fetch import IncludeTree
from parallax.core.document_codec import _occurrence as occurrence_codec
from parallax.core.entity._layout import CatalogedModel
from parallax.core.read_delivery._page import ABSENT
from parallax.core.temporal_read import Pin
from parallax.core.wire import _facts as facts_module
from parallax.core.wire._codec import encode_managed_wire
from parallax.core.wire._facts import (
    ENCODE_MANY,
    OCCURRENCE,
    PASS,
    PASS_MANY,
    WireModelFacts,
    WireOccurrenceFacts,
)
from parallax.snapshot import Snapshot
from parallax.snapshot._publication import _wire_render
from parallax.snapshot._publication._root_publication import publish_roots
from parallax.snapshot._publication._wire_render import (
    WireRootPublisher,
    _occurrence,  # pyright: ignore[reportPrivateUsage] - the record rule is under test
    entity_plan,
    requested_plan,
)
from tests._support.model_capabilities import graph_construction_for, wire_facts_for
from tests.unit.snapshot._encoded_page_models import ENCODED_ORDERS
from tests.unit.snapshot._snapshot_page_support import PageFixture, identity_of

_NS: Final = "parallax.compatibility"
_ITEMS: Final = f"{_NS}.EncodedOrder.items"
_ITEM_ORDER: Final = f"{_NS}.EncodedOrderItem.order"


def _fixture() -> PageFixture:
    return PageFixture(ENCODED_ORDERS, _ITEMS, references={_ITEM_ORDER: ("EncodedOrder",)})


def _order(fixture: PageFixture, order_id: int) -> int:
    order = fixture.node(
        "EncodedOrder",
        {
            "id": order_id,
            "name": f"order-{order_id}",
            "badge_hex": "0a",
            "address": {"street": f"{order_id} Main", "city": "Oslo"},
        },
    )
    items = tuple(
        fixture.node(
            "EncodedOrderItem",
            {"id": order_id * 10 + offset, "order_id": order_id, "code_hex": "0c"},
        )
        for offset in (1, 2)
    )
    fixture.attach(order, _ITEMS, items)
    for item in items:
        fixture.attach_reference(item, _ITEM_ORDER, "EncodedOrder", "EncodedOrderItem.orderId")
    return order


def _includes(fixture: PageFixture) -> IncludeTree:
    return fixture.include_tree(
        "EncodedOrder",
        (0, _ITEMS, "EncodedOrderItem"),
        (1, _ITEM_ORDER, "EncodedOrder"),
    )


def _published(
    fixture: PageFixture, includes: IncludeTree, facts: WireModelFacts, *roots: int
) -> tuple[Any, ...]:
    page = fixture.page(*roots)
    publisher = WireRootPublisher(fixture.model, facts, CONCURRENCY, includes)
    return tuple(publish_roots(page, publisher, fixture.model))


def _expected(order_id: int) -> dict[str, object]:
    order: dict[str, object] = {
        "id": order_id,
        "name": f"order-{order_id}",
        "badge": "0a",
        "address": {"street": f"{order_id} Main", "city": "Oslo", "phones": []},
    }
    return {
        **order,
        "items": [
            {"id": order_id * 10 + offset, "orderId": order_id, "code": "0c", "order": order}
            for offset in (1, 2)
        ],
    }


def _refuse(*_args: object, **_kwargs: object) -> Any:
    raise AssertionError("rendering resolved a shape, an include or an encoding per node")


def test_value_object_facts_recurse_through_every_nested_occurrence() -> None:
    facts = wire_facts_for(ENCODED_ORDERS)
    order = facts.entity(identity_of(_fixture().model, "EncodedOrder"))
    ((key, address),) = order.occurrences

    assert order.attribute_keys == ("id", "name", "badge")
    assert key == "address"
    assert address.many is False
    nested = [
        (name, detail)
        for name, encoding, detail in zip(
            address.keys, address.encodings, address.details, strict=True
        )
        if encoding == OCCURRENCE
    ]
    assert nested
    assert all(isinstance(detail, WireOccurrenceFacts) for _name, detail in nested)


def test_a_warm_plan_renders_a_new_page_without_resolving_anything_per_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture()
    includes = _includes(fixture)
    facts = wire_facts_for(ENCODED_ORDERS)
    first = _order(fixture, 1)
    assert _published(fixture, includes, facts, first) == (_expected(1),)

    for name in ("child_groups", "admitted_children", "render_token"):
        monkeypatch.setattr(IncludeTree, name, _refuse)
    monkeypatch.setattr(_wire_render, "_plan", _refuse)
    monkeypatch.setattr(planning_module, "_wire_entity_facts", _refuse)
    monkeypatch.setattr(facts_module, "scalar_encoding", _refuse)
    monkeypatch.setattr(occurrence_codec, "encode_occurrence", _refuse)

    later = _fixture()
    roots = (_order(later, 2), _order(later, 3))
    assert _published(later, includes, facts, *roots) == (_expected(2), _expected(3))


def test_direct_reads_and_typed_projection_render_through_the_same_plans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture()
    includes = _includes(fixture)
    cataloged = CatalogedModel(fixture.model)
    facts = wire_facts_for(cataloged)
    order = _order(fixture, 1)
    direct = _published(fixture, includes, facts, order)
    monkeypatch.setattr(_wire_render, "_plan", _refuse)

    typed = fixture.materialize(order)
    snapshot = Snapshot(
        cast("Any", typed),
        Pin(),
        "fixture",
        includes,
        graph_construction_for(ENCODED_ORDERS),
        facts,
    )
    assert snapshot.wire().results() == list(direct)


def test_two_preparations_render_through_their_own_plans() -> None:
    fixture = _fixture()
    includes = _includes(fixture)
    order_entity = identity_of(fixture.model, "EncodedOrder")
    first, second = wire_facts_for(ENCODED_ORDERS), wire_facts_for(ENCODED_ORDERS)

    first_plan = requested_plan(includes, first, includes.root, order_entity)
    second_plan = requested_plan(includes, second, includes.root, order_entity)

    assert first_plan is not None and second_plan is not None
    assert first_plan is not second_plan
    assert first_plan.facts is first.entity(order_entity)
    assert second_plan.facts is second.entity(order_entity)
    assert requested_plan(includes, first, includes.root, order_entity) is first_plan
    assert entity_plan(includes, first, first_plan.token, order_entity) is first_plan


def test_a_relationship_resolves_each_target_plan_once_on_its_first_node() -> None:
    fixture = _fixture()
    includes = _includes(fixture)
    facts = wire_facts_for(ENCODED_ORDERS)
    order_entity = identity_of(fixture.model, "EncodedOrder")
    item_entity = identity_of(fixture.model, "EncodedOrderItem")
    plan = requested_plan(includes, facts, includes.root, order_entity)
    assert plan is not None
    (items,) = plan.relationships
    assert items.key == "items"
    assert items.targets == {}

    _published(fixture, includes, facts, _order(fixture, 1))

    item_plan = items.targets[item_entity]
    assert items.target(item_entity) is item_plan
    (back,) = item_plan.relationships
    assert back.key == "order"
    assert back.targets[order_entity].relationships == ()
    assert items.target(order_entity) is None


def test_an_absent_collection_member_renders_empty_and_any_other_absent_member_is_omitted() -> None:
    nested = WireOccurrenceFacts(many=True, keys=(), encodings=(), details=())
    facts = WireOccurrenceFacts(
        many=False,
        keys=("tags", "label", "days", "children"),
        encodings=(PASS_MANY, PASS, ENCODE_MANY, OCCURRENCE),
        details=(STRING, STRING, DATE, nested),
    )

    rendered = _occurrence((ABSENT,) * 4, facts, encode_managed_wire, None)

    assert rendered == {"tags": [], "days": [], "children": []}
    assert _occurrence(None, nested, encode_managed_wire, None) == []
