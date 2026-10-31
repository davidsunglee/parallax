"""Page-wide Entity State and root-local Snapshot publication."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Final, cast

import pytest

from parallax.conformance.story_models import ORDERS_MODEL
from parallax.core.base import SQL_NULL
from parallax.core.deep_fetch import RelationshipViewKey
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.metamodel import EntityIdentity, RelationshipIdentity
from parallax.core.read_delivery import InvalidData
from parallax.core.read_delivery._page import (
    ABSENT,
    ROOT_LEVEL,
    EntityState,
    PageBuilder,
    ViewSchema,
    entity_state,
    page_rows,
    page_schedule,
    reach_into,
    release_finished_rows,
)
from parallax.core.temporal_read import Pin
from parallax.snapshot._publication._root import RootView
from parallax.snapshot._publication._root_publication import publish_roots
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._prepared_read_support import compiled_read, convert_cells, uncarried
from tests.unit._root_publication_support import each_root, observed_roots
from tests.unit.snapshot._encoded_identity_read import ENCODED_IDENTITY, encoded_identity_page
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


def _every_family_versioned(_entity: EntityIdentity) -> bool:
    return True


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


_PETS: Final[Mapping[str, object]] = {
    "license_id": None,
    "indoor": None,
    "bark_volume": None,
    "tusk_length": None,
}


def _encoded_order(key: str | None, name: str = "Ada", badge: str = "0f") -> dict[str, object]:
    return {
        "id": int(key) if key is not None else None,
        "name": name,
        "badge_hex": badge,
        "address": SQL_NULL,
    }


def _page(
    occurrences: tuple[tuple[int, dict[str, object]], ...],
    observer: RecordingObserver | None = None,
) -> tuple[object, tuple[int, ...]]:
    source_count = max((source for source, _row in occurrences), default=0) + 1
    builder = PageBuilder(ViewSchema(tuple(() for _ in range(source_count))), observer)
    compiled = compiled_read(_ENCODED, "EncodedOrder")
    cataloged = CatalogedModel(_ENCODED)
    roots = tuple(
        convert_cells(cataloged, compiled, row, builder, source=source)
        for source, row in occurrences
    )
    return builder.finish(roots, Pin()), roots


def test_equal_witnesses_decode_once_and_share_one_page_state() -> None:
    with recorded_conversion_dependencies() as calls:
        page, _roots = _page(
            ((ROOT_LEVEL, _encoded_order("01")), (ROOT_LEVEL, _encoded_order("01")))
        )
        assert calls.decoded == []

        first, second = observed_roots(cast("Any", page), _ENCODED)

    assert calls.decoded == ["0f"]
    assert len(page_rows(page).judged_states.group(0)) == 1
    assert first.member_values[0] is second.member_values[0]


def test_separate_roots_may_store_unequal_witnesses_for_one_logical_key() -> None:
    page, _roots = _page(((0, _encoded_order("01", "Ada")), (1, _encoded_order("01", "Grace"))))

    first, second = observed_roots(cast("Any", page), _ENCODED)

    assert first.member_values[0][1] == "Ada"
    assert second.member_values[0][1] == "Grace"
    assert len(page_rows(page).judged_states.group(0)) == 2


def test_keyless_occurrences_are_judged_only_when_their_root_is_requested() -> None:
    with recorded_conversion_dependencies() as calls:
        page = encoded_identity_page((None, "0e", SQL_NULL), (None, "0f", SQL_NULL))
        assert calls.decoded == []
        assert page_rows(cast("Any", page)).roots == (0, 1)

        def judged_so_far(root: RootView, _ordinal: int) -> tuple[list[object], int | None]:
            invalid = root.invalid_root
            return list(calls.decoded), None if invalid is None else invalid.ordinal

        assert each_root(cast("Any", page), ENCODED_IDENTITY, judged_so_far) == [
            (["0e"], 0),
            (["0e", "0f"], 1),
        ]


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

    first_view, second_view = observed_roots(page, fixture.model)

    assert first_view.names == ["Order", "OrderItem"]
    assert second_view.names == ["Order"]
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
    last_uses = page_schedule(page, _every_family_versioned, atomic=True).last_uses
    assert last_uses is not None
    projection_last, logical_last = last_uses
    assert tuple(projection_last) == (0, 0)
    assert tuple(logical_last) == (0, 0)


def test_releasing_a_finished_root_twice_is_idempotent() -> None:
    page, (root,) = _page(((ROOT_LEVEL, _encoded_order("01")),))
    rows = page_rows(cast("Any", page))
    schedule = page_schedule(cast("Any", page), _every_family_versioned, atomic=True)
    reached: list[int] = []
    reach_into(rows, root, reached)
    entity_state(rows, root)
    assert rows.judged_states.singleton(0) is not None

    release_finished_rows(cast("Any", page), schedule, 0, reached)
    released = (list(rows.member_rows), list(rows.keys), list(rows.logical_rows))
    release_finished_rows(cast("Any", page), schedule, 0, reached)

    assert released == ([()], [None], [0])
    assert (list(rows.member_rows), list(rows.keys), list(rows.logical_rows)) == released
    assert rows.judged_states.singleton(0) is None


def _published_positions(page: Any) -> Iterator[object]:
    return publish_roots(page, lambda _root, ordinal: (ordinal,), _ENCODED)


def test_root_zero_publishes_before_root_one_state_is_decoded() -> None:
    observer = RecordingObserver()
    page, _roots = _page(
        ((ROOT_LEVEL, _encoded_order("01")), (ROOT_LEVEL, _encoded_order("02"))), observer
    )

    assert list(_published_positions(page)) == [0, 1]
    relevant = [
        name for name, _value in observer.events if name in {"states_decoded", "root_published"}
    ]
    assert relevant == ["states_decoded", "root_published", "states_decoded", "root_published"]


def _shared_keyless_animal(
    owners: tuple[int, ...],
    animal_row: dict[str, object],
    uncarrying: tuple[str, ...],
    *,
    proved: bool = False,
) -> object:
    """A Page rooted at ``owners``, each Person owning the one keyless Animal
    fetched row ``animal_row`` records through a read carrying no source for the
    members stored under ``uncarrying``, on a ``proved`` level where its level
    records each row key at most once."""
    animals = RelationshipViewKey(RelationshipIdentity(identity_of(_ANIMAL, "Person"), "animals"))
    builder = PageBuilder(ViewSchema.of(animals, repeating_levels=frozenset() if proved else None))
    cataloged = CatalogedModel(_ANIMAL)
    animal = convert_cells(
        cataloged,
        uncarried(compiled_read(_ANIMAL, "Animal"), *uncarrying),
        animal_row,
        builder,
        source=ROOT_LEVEL,
        singleton=proved,
    )
    people = compiled_read(_ANIMAL, "Person")
    roots = tuple(
        convert_cells(
            cataloged,
            people,
            {"id": owner, "name": f"P{owner}"},
            builder,
            source=ROOT_LEVEL,
            singleton=proved,
        )
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
    ("animal_row", "uncarrying", "expected"),
    [
        pytest.param(
            {**_PETS, "id": 7, "kind": "unicorn", "name": "Uni", "owner_id": 1},
            (),
            (
                {"id": 7, "name": "Uni", "ownerId": 1},
                [("stored-data-family-tag-unknown", "unicorn")],
            ),
            id="unknown-concrete",
        ),
        pytest.param(
            {**_PETS, "id": 7, "kind": "dog", "name": "Rex", "owner_id": 1},
            ("id",),
            (
                {"name": "Rex", "ownerId": 1, "licenseId": None, "barkVolume": None},
                list[object](),
            ),
            id="without-key",
        ),
    ],
)
@pytest.mark.parametrize("proved", [False, True], ids=["deferred", "proved"])
def test_a_keyless_fetched_row_publishes_the_same_state_to_every_root_reaching_it(
    owners: tuple[int, ...],
    atomic: bool,
    animal_row: dict[str, object],
    uncarrying: tuple[str, ...],
    expected: tuple[object, ...],
    proved: bool,
) -> None:
    # A deferred keyless fetched row shares no judged state, so each root reaching
    # it judges its payload anew, after earlier roots released what they alone
    # reached; a proved one was judged once, as it was recorded.
    page = _shared_keyless_animal(owners, animal_row, uncarrying, proved=proved)

    def publish(root: RootView, _ordinal: int) -> tuple[object, ...]:
        (node,) = (node for node in range(len(root)) if root.layout(node).concrete.name != "Person")
        return (
            (
                rendered_members(root.layout(node), root.member_values(node)),
                [(issue.code, issue.stored_value) for issue in root.issues(node)],
            ),
        )

    published = list(publish_roots(cast("Any", page), publish, _ANIMAL, atomic=atomic))

    assert published == [expected] * len(owners)


def _proved_orders(*badges: str) -> tuple[object, tuple[int, ...]]:
    """A one-level proved Page of EncodedOrder roots, one per badge spelling."""
    builder = PageBuilder(ViewSchema(((),), repeating_levels=frozenset()))
    compiled = compiled_read(_ENCODED, "EncodedOrder")
    cataloged = CatalogedModel(_ENCODED)
    roots = tuple(
        convert_cells(
            cataloged,
            compiled,
            _encoded_order(f"{ordinal:02d}", badge=badge),
            builder,
            source=ROOT_LEVEL,
            singleton=True,
        )
        for ordinal, badge in enumerate(badges, 1)
    )
    return builder.finish(roots, Pin()), roots


def test_a_proved_level_judges_each_row_as_it_is_recorded_and_publication_reads_it() -> None:
    with recorded_conversion_dependencies() as calls:
        page, _roots = _proved_orders("0e", "0f")
        assert calls.decoded == ["0e", "0f"]

        first, second = observed_roots(cast("Any", page), _ENCODED)

    assert calls.decoded == ["0e", "0f"]
    assert [first.member_values[0][2], second.member_values[0][2]] == [b"\x0e", b"\x0f"]
    rows = page_rows(page)
    assert list(rows.stored_values) == [None, None]
    assert len(rows.decoders) == 2
    assert not any(rows.decoders.pending(fetched_row) for fetched_row in (0, 1))


def test_a_proved_row_judged_without_findings_is_held_as_its_member_row_alone() -> None:
    page, _roots = _proved_orders("0e", "not-hex")
    recorded = page_rows(page).judged_states.by_logical_row

    first, second = recorded[0], recorded[1]
    assert type(first) is tuple
    assert first[2] == b"\x0e"
    assert type(second) is EntityState
    assert second.findings


def test_a_keyless_proved_row_recorded_without_findings_answers_its_member_row() -> None:
    builder = PageBuilder(ViewSchema(((),), repeating_levels=frozenset()))
    layout = CatalogedModel(_ENCODED).layouts.entity(identity_of(_ENCODED, "EncodedOrder"))
    values = tuple(ABSENT for _ in layout.members)
    fetched_row = builder.add_fetched_row(ROOT_LEVEL, layout, None, values, values, (), values)
    rows = page_rows(builder.finish((fetched_row,), Pin()))

    assert entity_state(rows, fetched_row) == EntityState(values, ())


def test_proved_and_merged_levels_number_their_logical_rows_densely() -> None:
    builder = PageBuilder(ViewSchema(((), (), ()), repeating_levels=frozenset({0, 2})))
    compiled = compiled_read(_ENCODED, "EncodedOrder")
    cataloged = CatalogedModel(_ENCODED)

    def record(source: int, key: str) -> int:
        return convert_cells(
            cataloged,
            compiled,
            _encoded_order(key),
            builder,
            source=source,
            singleton=source == 1,
        )

    fetched = (record(0, "01"), record(0, "01"), record(1, "02"), record(2, "03"))
    rows = page_rows(builder.finish(fetched[:1], Pin()))

    assert list(rows.logical_rows) == [0, 0, 1, 2]
    assert list(rows.fetched_rows_by_logical_row) == [(0, 1), 2, 3]
    assert rows.judged_states.by_logical_row[0] is None
    assert rows.judged_states.by_logical_row[1] is not None


def test_a_row_judged_as_it_is_recorded_is_refused_on_a_level_that_may_repeat_rows() -> None:
    builder = PageBuilder(ViewSchema.of())

    with pytest.raises(ValueError, match="compared before it is judged"):
        convert_cells(
            CatalogedModel(_ENCODED),
            compiled_read(_ENCODED, "EncodedOrder"),
            _encoded_order("01"),
            builder,
            source=ROOT_LEVEL,
            singleton=True,
        )


def test_a_proved_row_reached_by_several_roots_shares_its_state_but_not_its_node() -> None:
    fixture = PageFixture(ENCODED_ORDERS, "EncodedOrderItem.order", proved=True)
    order = fixture.node("EncodedOrder", _encoded_order("01"))
    items = tuple(
        fixture.node("EncodedOrderItem", {"id": item, "order_id": 1, "code_hex": "0a"})
        for item in (10, 11)
    )
    for item in items:
        fixture.attach(item, "EncodedOrderItem.order", order)

    first, second = fixture.materialize(*items)

    first_order = cast("Any", first).order
    second_order = cast("Any", second).order
    assert first_order is not second_order
    assert first_order == second_order
    assert first_order.badge == b"\x0f"


def test_a_proved_row_no_root_reaches_classifies_no_root() -> None:
    fixture = PageFixture(ENCODED_ORDERS, proved=True)
    valid = fixture.node("EncodedOrder", _encoded_order("01"))
    fixture.node("EncodedOrder", _encoded_order("02", badge="not-hex"))

    (published,) = fixture.materialize(valid)

    assert not isinstance(published, InvalidData)
