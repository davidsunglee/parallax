"""The Snapshot-owned inspection surface (``parallax.snapshot._inspection``):
``is_view_loaded`` / ``view`` / ``pin_of`` / ``edge_of`` over graphs the
materializer produced, plus the refusals that precede every other check.

The suite drives whole graphs rather than hand-attached state, because what these
operations require is exactly what a Snapshot read attaches and nothing else.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import threading
from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any, Final, cast

import pytest

from parallax.conformance import animal_owner, read_models
from parallax.core import (
    ONE_TO_MANY,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Rel,
    TablePerHierarchy,
    attr,
    rel,
)
from parallax.core._execution._publication import read_projection
from parallax.core.entity import UnloadedRelationshipError
from parallax.core.execution import ModelSelection, ServingModel, prepare_model
from parallax.core.temporal_read import Edge, Pin, TemporalReadError, milestone_edge
from parallax.snapshot import (
    Database,
    SnapshotInspectionError,
    _inspection,
    edge_of,
    is_view_loaded,
    pin_of,
    view,
)
from parallax.snapshot._inspection import (
    SNAPSHOT_INSPECTION_CODES,
    NarrowedViews,
    snapshot_state_of,
)
from tests._support import snapshot_models as sm
from tests._support.db_port import Read, ScriptedAdapter
from tests._support.root_ownership import own_root
from tests.unit import _deep_include_support as deep
from tests.unit._gc_reachability import reachable_objects
from tests.unit.snapshot._snapshot_page_support import PageFixture

_ORDERS = sm.SNAP_ORDERS_MODEL
_ANIMAL = sm.ANIMAL_MODEL
_BALANCE = read_models.BALANCE_MODEL

_ORDER_ROW: dict[str, object] = {
    "id": 1,
    "name": "Ada",
    "sku": None,
    "qty": 1,
    "price": Decimal("1.00"),
    "active": True,
    "ordered_on": dt.date(2024, 1, 1),
}
_DOG_ROW: dict[str, object] = {
    "id": 1,
    "name": "Rex",
    "owner_id": 10,
    "license_id": None,
    "bark_volume": 7,
}
_OWNER_ROW: dict[str, object] = {"id": 10, "name": "Alice", "favorite_id": None}


def _item_row(item_id: int) -> dict[str, object]:
    return {"id": item_id, "order_id": 1, "sku": "x", "quantity": 1, "shipped_on": None}


def _status_row(status_id: int) -> dict[str, object]:
    return {
        "id": status_id,
        "order_id": 1,
        "order_item_id": None,
        "code": "SHIPPED",
        "primary_tag": None,
        "tags": None,
    }


def _order_graph(*, items: tuple[dict[str, object], ...] | None = None) -> Any:
    """One `SnapOrder` root, optionally with a loaded `items` view."""
    fixture = PageFixture(_ORDERS, "parallax.compatibility.SnapOrder.items")
    order = fixture.node("SnapOrder", _ORDER_ROW)
    if items is not None:
        refs = tuple(fixture.node("SnapOrderItem", row) for row in items)
        fixture.attach(order, "parallax.compatibility.SnapOrder.items", refs)
    (root,) = fixture.materialize(order)
    return root


# --------------------------------------------------------------------------- #
# `snapshot-node-required` precedes every other question.                      #
# --------------------------------------------------------------------------- #


def _loaded(node: object) -> object:
    return is_view_loaded(node, sm.SnapOrder.items)


def _viewed(node: object) -> object:
    return view(node, sm.SnapOrder.items)


@pytest.mark.parametrize(
    ("operation", "call"),
    [
        ("is_view_loaded", _loaded),
        ("view", _viewed),
        ("pin_of", pin_of),
        ("edge_of", edge_of),
    ],
)
def test_every_operation_refuses_a_node_this_lifecycle_did_not_produce(
    operation: str, call: Callable[[object], object]
) -> None:
    plain = sm.SnapOrder(
        id=1,
        name="Ada",
        sku=None,
        qty=1,
        price=Decimal("1.00"),
        active=True,
        ordered_on=dt.date(2024, 1, 1),
    )
    with pytest.raises(SnapshotInspectionError) as refusal:
        call(plain)
    assert refusal.value.code == "snapshot-node-required"
    assert refusal.value.operation == operation


def test_the_lifecycle_refusal_precedes_the_owner_check() -> None:
    # The path's owner is unrelated to the object AND the object carries no
    # Snapshot state; the lifecycle refusal is the one that fires.
    with pytest.raises(SnapshotInspectionError) as refusal:
        is_view_loaded(object(), sm.SnapOrder.items)
    assert refusal.value.code == "snapshot-node-required"


# --------------------------------------------------------------------------- #
# Owner application and the path-only argument rule.                           #
# --------------------------------------------------------------------------- #


def test_a_path_whose_owner_does_not_apply_raises_rather_than_answering_false() -> None:
    with pytest.raises(SnapshotInspectionError) as refusal:
        is_view_loaded(_order_graph(), sm.AnimalOwner.pets)
    assert refusal.value.code == "snapshot-view-owner-mismatch"
    assert refusal.value.entity == sm.SnapOrder.identity


def test_a_bare_relationship_name_is_not_an_accepted_argument() -> None:
    with pytest.raises(SnapshotInspectionError) as refusal:
        is_view_loaded(_order_graph(), cast("Any", "items"))
    assert refusal.value.code == "snapshot-view-owner-mismatch"


def test_a_relationship_an_ancestor_declares_applies_to_its_concrete_subtype() -> None:
    # `owner` is declared on the family root `Animal`; the node is a `Dog`, and
    # a subtype never redeclares an inherited relationship.
    fixture = PageFixture(animal_owner.ANIMAL_MODEL)
    (root,) = fixture.materialize(fixture.node("Dog", _DOG_ROW))
    assert type(root) is read_models.Dog
    assert is_view_loaded(root, read_models.Animal.owner) is False


# --------------------------------------------------------------------------- #
# Loaded state and traversal.                                                  #
# --------------------------------------------------------------------------- #


def test_a_loaded_view_answers_true_and_an_unrequested_one_answers_false() -> None:
    root = _order_graph(items=(_item_row(11),))
    assert is_view_loaded(root, sm.SnapOrder.items) is True
    assert is_view_loaded(root, sm.SnapOrder.statuses) is False


def test_view_answers_the_loaded_value_and_raises_for_an_unloaded_one() -> None:
    root = _order_graph(items=(_item_row(11),))
    items = cast("tuple[Any, ...]", view(root, sm.SnapOrder.items))
    assert [item.id for item in items] == [11]
    with pytest.raises(UnloadedRelationshipError, match="statuses"):
        view(root, sm.SnapOrder.statuses)


def test_a_to_many_path_fans_out_into_one_flat_tuple_in_traversal_order() -> None:
    fixture = PageFixture(
        _ORDERS,
        "parallax.compatibility.SnapOrder.items",
        "parallax.compatibility.SnapOrderItem.statuses",
    )
    order = fixture.node("SnapOrder", _ORDER_ROW)
    first = fixture.node("SnapOrderItem", _item_row(11))
    second = fixture.node("SnapOrderItem", _item_row(12))
    fixture.attach(order, "parallax.compatibility.SnapOrder.items", (first, second))
    fixture.attach(
        first,
        "parallax.compatibility.SnapOrderItem.statuses",
        tuple(fixture.node("SnapOrderStatus", _status_row(status)) for status in (21, 22)),
    )
    fixture.attach(
        second,
        "parallax.compatibility.SnapOrderItem.statuses",
        (fixture.node("SnapOrderStatus", _status_row(23)),),
    )
    (root,) = fixture.materialize(order)
    reached = cast("tuple[Any, ...]", view(root, sm.SnapOrder.items.statuses))
    assert [status.id for status in reached] == [21, 22, 23]


def test_an_empty_to_many_branch_contributes_no_terminal_and_stays_a_tuple() -> None:
    root = _order_graph(items=())
    assert view(root, sm.SnapOrder.items.statuses) == ()
    # The uninstantiated suffix of an empty branch is vacuously loaded.
    assert is_view_loaded(root, sm.SnapOrder.items.statuses) is True


def test_an_all_to_one_path_answers_its_terminal_or_none() -> None:
    fixture = PageFixture(
        _ORDERS,
        "parallax.compatibility.SnapOrder.items",
        "parallax.compatibility.SnapOrderItem.order",
    )
    order = fixture.node("SnapOrder", _ORDER_ROW)
    item = fixture.node("SnapOrderItem", _item_row(11))
    orphan = fixture.node("SnapOrderItem", _item_row(50))
    fixture.attach(order, "parallax.compatibility.SnapOrder.items", (item,))
    fixture.attach(item, "parallax.compatibility.SnapOrderItem.order", order)
    fixture.attach(orphan, "parallax.compatibility.SnapOrderItem.order", None)
    root, lone = fixture.materialize(order, orphan)
    assert view(cast("Any", root).items[0], sm.SnapOrderItem.order) is root
    assert view(lone, sm.SnapOrderItem.order) is None


def test_an_unloaded_view_on_a_deeper_segment_is_the_one_reported() -> None:
    root = _order_graph(items=(_item_row(11),))
    assert is_view_loaded(root, sm.SnapOrder.items.statuses) is False
    with pytest.raises(UnloadedRelationshipError, match="statuses"):
        view(root, sm.SnapOrder.items.statuses)


# --------------------------------------------------------------------------- #
# Narrowed views.                                                              #
# --------------------------------------------------------------------------- #


def _narrowed_owner(view_key: str, columns: dict[str, object] | None = None) -> Any:
    fixture = PageFixture(_ANIMAL, ("parallax.compatibility.AnimalOwner.pets", view_key))
    owner = fixture.node("AnimalOwner", columns if columns is not None else _OWNER_ROW)
    dog = fixture.node("Dog", _DOG_ROW)
    fixture.attach(owner, "parallax.compatibility.AnimalOwner.pets", (dog,), narrowed=view_key)
    (root,) = fixture.materialize(owner)
    return root


def test_a_narrowed_view_is_read_by_its_own_path_and_never_marks_the_broad_one() -> None:
    root = _narrowed_owner("pets[Dog]")
    assert is_view_loaded(root, sm.AnimalOwner.pets) is False
    assert is_view_loaded(root, sm.AnimalOwner.pets.narrow(sm.Dog)) is True
    reached = cast("tuple[Any, ...]", view(root, sm.AnimalOwner.pets.narrow(sm.Dog)))
    assert [type(pet) for pet in reached] == [sm.Dog]
    with pytest.raises(UnloadedRelationshipError, match=r"pets\[Cat\]"):
        view(root, sm.AnimalOwner.pets.narrow(sm.Cat))


def test_equivalent_narrow_spellings_name_one_view() -> None:
    root = _narrowed_owner("pets[Cat,Dog]")
    assert is_view_loaded(root, sm.AnimalOwner.pets.narrow(sm.Cat, sm.Dog)) is True
    assert is_view_loaded(root, sm.AnimalOwner.pets.narrow(sm.Dog, sm.Cat)) is True


def test_an_unrequested_narrowed_view_answers_false_rather_than_raising() -> None:
    root = _narrowed_owner("pets[Dog]")
    assert is_view_loaded(root, sm.AnimalOwner.pets.narrow(sm.Cat)) is False


def test_an_abstract_narrow_reads_the_view_its_concretes_key() -> None:
    root = _narrowed_owner("pets[Cat,Dog]")
    abstract = cast("tuple[Any, ...]", view(root, sm.AnimalOwner.pets.narrow(sm.Pet)))
    assert [pet.id for pet in abstract] == [1]
    assert view(root, sm.AnimalOwner.pets.narrow(sm.Cat, sm.Dog)) == abstract
    assert is_view_loaded(root, sm.AnimalOwner.pets.narrow(sm.Pet)) is True
    assert is_view_loaded(root, sm.AnimalOwner.pets) is False


def test_an_abstract_narrow_reads_a_loaded_empty_and_a_loaded_null_view() -> None:
    pets = "parallax.compatibility.AnimalOwner.pets"
    favorite = "parallax.compatibility.AnimalOwner.favorite"
    keyed = "favorite[Cat,Dog,WildBoar]"
    fixture = PageFixture(_ANIMAL, (pets, "pets[Cat,Dog]"), (favorite, keyed))
    owner = fixture.node("AnimalOwner", _OWNER_ROW)
    fixture.attach(owner, pets, (), narrowed="pets[Cat,Dog]")
    fixture.attach(owner, favorite, None, narrowed=keyed)
    (root,) = fixture.materialize(owner)

    empty = sm.AnimalOwner.pets.narrow(sm.Pet)
    null = sm.AnimalOwner.favorite.narrow(sm.Animal)
    assert (view(root, empty), view(root, null)) == ((), None)
    assert (is_view_loaded(root, empty), is_view_loaded(root, null)) == (True, True)
    assert is_view_loaded(root, empty.name) is True


def test_a_node_holding_no_narrowed_view_reports_a_narrow_by_its_authored_spelling() -> None:
    fixture = PageFixture(_ANIMAL)
    (root,) = fixture.materialize(fixture.node("AnimalOwner", _OWNER_ROW))
    assert is_view_loaded(root, sm.AnimalOwner.pets.narrow(sm.Pet)) is False
    with pytest.raises(UnloadedRelationshipError, match=r"pets\[Pet\]"):
        view(root, sm.AnimalOwner.pets.narrow(sm.Pet))


def test_a_narrowed_to_one_view_answers_the_node_itself_or_loaded_null() -> None:
    # A to-one hop narrows exactly as a to-many one does, and its view value is
    # then a single node — or loaded-null — rather than a tuple.
    fixture = PageFixture(_ANIMAL, ("parallax.compatibility.AnimalOwner.favorite", "favorite[Dog]"))
    alice = fixture.node("AnimalOwner", {"id": 10, "name": "Alice", "favorite_id": 1})
    bob = fixture.node("AnimalOwner", {"id": 11, "name": "Bob", "favorite_id": None})
    fixture.attach(
        alice,
        "parallax.compatibility.AnimalOwner.favorite",
        fixture.node("Dog", _DOG_ROW),
        narrowed="favorite[Dog]",
    )
    fixture.attach(
        bob, "parallax.compatibility.AnimalOwner.favorite", None, narrowed="favorite[Dog]"
    )
    first, second = fixture.materialize(alice, bob)
    assert type(view(first, sm.AnimalOwner.favorite.narrow(sm.Dog))) is sm.Dog
    assert is_view_loaded(second, sm.AnimalOwner.favorite.narrow(sm.Dog)) is True
    assert view(second, sm.AnimalOwner.favorite.narrow(sm.Dog)) is None


def test_a_deeper_segment_whose_owner_does_not_apply_is_refused_mid_traversal() -> None:
    fixture = PageFixture(_ANIMAL, "parallax.compatibility.AnimalOwner.animals")
    owner = fixture.node("AnimalOwner", _OWNER_ROW)
    fixture.attach(
        owner, "parallax.compatibility.AnimalOwner.animals", (fixture.node("Dog", _DOG_ROW),)
    )
    (root,) = fixture.materialize(owner)
    # `AnimalOwner.animals` reaches a `Dog`, whose class answers no relationship
    # for a name another Entity declares.
    with pytest.raises(SnapshotInspectionError) as refusal:
        view(root, sm.AnimalOwner.animals.items)
    assert refusal.value.code == "snapshot-view-owner-mismatch"


# --------------------------------------------------------------------------- #
# Deep paths, read through each reached node's own class.                      #
# --------------------------------------------------------------------------- #
_ANIMALS = f"{deep.FAMILY_NS}.Keeper.animals"
_TOYS = f"{deep.FAMILY_NS}.Animal.playthings"
_MAKER = f"{deep.FAMILY_NS}.Toy.maker"
_DOG_GEAR = f"{deep.FAMILY_NS}.Dog.gear"


def _animal_row(animal_id: int) -> dict[str, object]:
    return {"id": animal_id, "keeper_id": 1, "vet_id": None}


def _toy_row(toy_id: int, animal_id: int, maker_id: int | None) -> dict[str, object]:
    return {"id": toy_id, "animal_id": animal_id, "maker_id": maker_id}


def _deep_keeper(*, makers_loaded: bool = True) -> Any:
    """Keeper 1: a Dog with three toys, two sharing a maker and one with none, and
    a Cat with loaded-empty toys."""
    fixture = PageFixture(deep.FAMILY, _ANIMALS, _TOYS, _MAKER)
    keeper = fixture.node("Keeper", {"id": 1})
    dog = fixture.node("Dog", _animal_row(2))
    cat = fixture.node("Cat", _animal_row(3))
    toys = tuple(
        fixture.node("Toy", _toy_row(toy, 2, maker))
        for toy, maker in ((10, 100), (11, 100), (12, None))
    )
    fixture.attach(keeper, _ANIMALS, (dog, cat))
    fixture.attach(dog, _TOYS, toys)
    fixture.attach(cat, _TOYS, ())
    if makers_loaded:
        maker = fixture.node("Maker", {"id": 100})
        fixture.attach(toys[0], _MAKER, maker)
        fixture.attach(toys[1], _MAKER, maker)
        fixture.attach(toys[2], _MAKER, None)
    (root,) = fixture.materialize(keeper)
    return root


def test_a_deep_path_reads_renamed_and_inherited_members_with_fan_out_and_null_branches() -> None:
    # `toys` is renamed and declared on the root, each reached node is a concrete
    # descendant, and the null maker and the Cat's empty toys contribute nothing
    # while the duplicate maker keeps its place in traversal order.
    root = _deep_keeper()
    reached = cast("tuple[Any, ...]", view(root, deep.Keeper.animals.toys.maker))
    assert [maker.id for maker in reached] == [100, 100]
    assert is_view_loaded(root, deep.Keeper.animals.toys.maker) is True


def test_a_deep_path_reports_its_first_unloaded_segment_by_the_relationships_own_name() -> None:
    root = _deep_keeper(makers_loaded=False)
    assert is_view_loaded(root, deep.Keeper.animals.toys.maker) is False
    with pytest.raises(UnloadedRelationshipError, match="maker"):
        view(root, deep.Keeper.animals.toys.maker)
    assert is_view_loaded(root, deep.Keeper.animals.vet) is False
    with pytest.raises(UnloadedRelationshipError, match="attendingVet"):
        view(root, deep.Keeper.animals.vet)


def test_a_deep_path_past_a_narrowed_hop_continues_through_that_view() -> None:
    fixture = PageFixture(deep.FAMILY, (_ANIMALS, "animals[Dog]"), _TOYS, _MAKER, _DOG_GEAR)
    keeper = fixture.node("Keeper", {"id": 1})
    dog = fixture.node("Dog", _animal_row(2))
    toy = fixture.node("Toy", _toy_row(10, 2, 100))
    fixture.attach(keeper, _ANIMALS, (dog,), narrowed="animals[Dog]")
    fixture.attach(dog, _TOYS, (toy,))
    fixture.attach(toy, _MAKER, fixture.node("Maker", {"id": 100}))
    fixture.attach(dog, _DOG_GEAR, (fixture.node("Collar", {"id": 5, "dog_id": 2}),))
    (root,) = fixture.materialize(keeper)

    narrowed = deep.Keeper.animals.narrow(deep.Dog)
    assert [m.id for m in cast("tuple[Any, ...]", view(root, narrowed.toys.maker))] == [100]
    assert [c.id for c in cast("tuple[Any, ...]", view(root, narrowed.gear))] == [5]
    assert is_view_loaded(root, deep.Keeper.animals.toys.maker) is False


_DOG_ONLY: Final = DomainModel(
    deep.Keeper, deep.Animal, deep.Dog, deep.Toy, deep.Maker, deep.Collar
)
_NARROWED_TO_ANIMAL: Final = deep.Keeper.animals.narrow(deep.Animal)


def _keeper_query() -> Any:
    return deep.Keeper.where(deep.Keeper.id == 1)


def _found_root(database: Any, query: Any) -> Any:
    return database.find(query).result()


def _streamed_root(database: Any, query: Any) -> Any:
    with database.stream(query, batch_size=10) as stream:
        (root,) = list(stream)
    return root


@pytest.mark.parametrize("read", [_found_root, _streamed_root], ids=["eager", "streamed"])
def test_a_deep_narrowed_path_is_inspected_as_it_was_included(read: Any) -> None:
    path = _NARROWED_TO_ANIMAL.toys.maker
    with ScriptedAdapter(*deep.family_reads()) as port:
        database = own_root(Database.connect(port, deep.FAMILY)).using_database_login()
        root = read(database, _keeper_query().include(path))

    assert [maker.id for maker in cast("tuple[Any, ...]", view(root, path))] == [100]
    assert is_view_loaded(root, path) is True
    same = deep.Keeper.animals.narrow(deep.Dog, deep.Cat).toys.maker
    assert view(root, same) == view(root, path)
    assert is_view_loaded(root, deep.Keeper.animals) is False
    assert is_view_loaded(root, deep.Keeper.animals.narrow(deep.Dog)) is False
    with pytest.raises(UnloadedRelationshipError, match=r"animals\[Dog\]"):
        view(root, deep.Keeper.animals.narrow(deep.Dog))


def test_only_a_node_with_a_narrowed_view_holds_the_edition_s_keys() -> None:
    selection = prepare_model(deep.FAMILY, edition="narrowed")
    with ScriptedAdapter(*deep.family_reads()) as port:
        database = own_root(Database.connect(port, ServingModel(selection)))
        root = _found_root(
            database.using_database_login(),
            _keeper_query().include(_NARROWED_TO_ANIMAL.toys.maker),
        )

    state = snapshot_state_of(root)
    assert state is not None and isinstance(state.views, NarrowedViews)
    assert state.views.view_keys is read_projection(selection).narrowed_view_keys
    for reached in cast("tuple[Any, ...]", view(root, _NARROWED_TO_ANIMAL)):
        reached_state = snapshot_state_of(reached)
        assert reached_state is not None
        assert not isinstance(reached_state.views, NarrowedViews)


def _animal_reads(*kinds: str) -> tuple[Read, ...]:
    return (
        Read(rows=[{"id": 1}]),
        Read(
            rows=[
                {"id": 2 + index, "kind": kind, "keeper_id": 1, "vet_id": None}
                for index, kind in enumerate(kinds)
            ]
        ),
    )


def test_a_retained_node_answers_under_the_edition_that_published_it() -> None:
    wide = prepare_model(deep.FAMILY, edition="wide")
    narrow = prepare_model(_DOG_ONLY, edition="narrow")
    serving = ServingModel(wide)
    query = _keeper_query().include(_NARROWED_TO_ANIMAL)
    with ScriptedAdapter(*_animal_reads("dog", "cat"), *_animal_reads("dog")) as port:
        database = own_root(Database.connect(port, serving)).using_database_login()
        retained = _found_root(database, query)
        serving.publish(narrow, expected=wide)
        current = _found_root(database, query)

    retained_animals = cast("tuple[Any, ...]", view(retained, _NARROWED_TO_ANIMAL))
    assert [type(animal) for animal in retained_animals] == [deep.Dog, deep.Cat]
    assert is_view_loaded(retained, _NARROWED_TO_ANIMAL) is True
    current_animals = cast("tuple[Any, ...]", view(current, _NARROWED_TO_ANIMAL))
    assert [type(animal) for animal in current_animals] == [deep.Dog]
    assert is_view_loaded(retained, deep.Keeper.animals.narrow(deep.Dog)) is False


@pytest.mark.parametrize(
    "path",
    [deep.Keeper.animals.narrow(deep.Cat), deep.Keeper.animals.narrow(deep.Cat, deep.Dog)],
    ids=["outside", "partly-outside"],
)
def test_a_selection_outside_the_model_is_an_unloaded_view(path: Any) -> None:
    with ScriptedAdapter(*_animal_reads("dog")) as port:
        database = own_root(Database.connect(port, _DOG_ONLY)).using_database_login()
        root = _found_root(database, _keeper_query().include(_NARROWED_TO_ANIMAL))

    assert is_view_loaded(root, _NARROWED_TO_ANIMAL) is True
    assert is_view_loaded(root, path) is False
    with pytest.raises(UnloadedRelationshipError, match=r"animals\[Cat"):
        view(root, path)


def _read_narrowed_under(selection: ModelSelection) -> Any:
    port = ScriptedAdapter(*_animal_reads("dog"))
    database = Database.connect(port, ServingModel(selection))
    try:
        return _found_root(
            database.using_database_login(), _keeper_query().include(_NARROWED_TO_ANIMAL)
        )
    finally:
        database.close()


def test_a_retained_narrowed_node_does_not_keep_its_model_alive() -> None:
    selection = prepare_model(_DOG_ONLY, edition="retired")
    prepared = read_projection(selection)
    root = _read_narrowed_under(selection)

    reached = {id(value) for value in reachable_objects(root)}

    assert id(prepared.narrowed_view_keys) in reached
    assert reached.isdisjoint(
        id(value)
        for value in (
            selection,
            selection.model,
            prepared,
            prepared.model,
            prepared.model.meta,
            prepared.model.layouts,
            prepared.construction,
            prepared.classes,
            prepared.wire,
        )
    )


_KENNEL_NS = "parallax.tests.kennel"
_ALPHA = f"{_KENNEL_NS}.alpha.Pack"
_BETA = f"{_KENNEL_NS}.beta.Pack"


class Kennel(Entity, table="kennel", namespace=_KENNEL_NS):
    id: Attr[int] = attr(primary_key=True)
    hounds: Rel[tuple[Hound, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "kennel_id"))


class Hound(
    Entity,
    table="hound",
    namespace=_KENNEL_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    kennel_id: Attr[int | None]


class AlphaPack(
    Hound,
    name="Pack",
    namespace=f"{_KENNEL_NS}.alpha",
    inheritance=ConcreteSubtype(tag_value="alpha"),
):
    pass


class BetaPack(
    Hound,
    name="Pack",
    namespace=f"{_KENNEL_NS}.beta",
    inheritance=ConcreteSubtype(tag_value="beta"),
):
    pass


_KENNEL: Final = DomainModel(Kennel, Hound, AlphaPack, BetaPack)


def test_a_concrete_sharing_its_local_name_is_read_by_its_qualified_key() -> None:
    alpha = Kennel.hounds.narrow(AlphaPack)
    both = Kennel.hounds.narrow(Hound)
    hound_rows = [
        {"id": 2, "kennel_id": 1, "kind": "alpha"},
        {"id": 3, "kennel_id": 1, "kind": "beta"},
    ]
    with ScriptedAdapter(
        Read(rows=[{"id": 1}]), Read(rows=hound_rows), Read(rows=hound_rows[:1])
    ) as port:
        database = own_root(Database.connect(port, _KENNEL)).using_database_login()
        root = _found_root(database, Kennel.where(Kennel.id == 1).include(alpha, both))

    assert [type(hound) for hound in cast("tuple[Any, ...]", view(root, alpha))] == [AlphaPack]
    assert [hound.id for hound in cast("tuple[Any, ...]", view(root, both))] == [2, 3]
    beta = Kennel.hounds.narrow(BetaPack)
    assert is_view_loaded(root, beta) is False
    with pytest.raises(UnloadedRelationshipError, match=rf"hounds\[{_BETA}\]"):
        view(root, beta)
    state = snapshot_state_of(root)
    assert state is not None
    assert set(state.views) == {f"hounds[{_ALPHA}]", f"hounds[{_ALPHA},{_BETA}]"}


def test_a_sibling_never_answers_a_root_segment_it_merely_shares_a_name_with() -> None:
    fixture = PageFixture(deep.FAMILY, _DOG_GEAR)
    cat, dog = fixture.materialize(
        fixture.node("Cat", _animal_row(3)), fixture.node("Dog", _animal_row(2))
    )
    assert is_view_loaded(dog, deep.Dog.gear) is False
    for operation in (view, is_view_loaded):
        with pytest.raises(SnapshotInspectionError) as refusal:
            operation(cat, deep.Dog.gear)
        assert refusal.value.code == "snapshot-view-owner-mismatch"
        assert refusal.value.entity == deep.Cat.identity


_RESPELLED_NS = "parallax.tests.respelled_root"


class Sprout(Entity, table="respelled_sprout", namespace=_RESPELLED_NS):
    id: Attr[int] = attr(primary_key=True)
    parent_id: Attr[int]


class Parent(Entity, table="respelled_parent", namespace=_RESPELLED_NS):
    id: Attr[int] = attr(primary_key=True)
    children: Rel[tuple[Sprout, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "parent_id"), name="kids"
    )


# A second declaration of the SAME Entity Identity, spelling the same relationship
# under another Python name.
class RespelledParent(Entity, table="respelled_parent", name="Parent", namespace=_RESPELLED_NS):
    id: Attr[int] = attr(primary_key=True)
    offspring: Rel[tuple[Sprout, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "parent_id"), name="kids"
    )


_RESPELLED: Final = DomainModel(RespelledParent, Sprout)


def test_a_root_segment_reads_the_relationship_a_differently_spelled_class_serves() -> None:
    query = Parent.where(Parent.id == 1)
    with ScriptedAdapter(
        Read(rows=[{"id": 1}]),
        Read(rows=[{"id": 2, "parent_id": 1}]),
        Read(rows=[{"id": 1}]),
    ) as port:
        database = own_root(Database.connect(port, _RESPELLED)).using_database_login()
        loaded = database.find(query.include(Parent.children))
        unloaded = database.find(query).result()

    root = cast("Any", loaded.result())
    assert type(root) is RespelledParent
    assert is_view_loaded(root, Parent.children) is True
    assert view(root, Parent.children) == root.offspring
    assert [sprout.id for sprout in root.offspring] == [2]
    assert loaded.wire(root.offspring[0], at=Parent.children)["id"] == 2

    assert is_view_loaded(unloaded, Parent.children) is False
    with pytest.raises(UnloadedRelationshipError):
        view(unloaded, Parent.children)


def test_a_continuation_no_reached_class_declares_is_an_owner_mismatch_at_any_depth() -> None:
    root = _deep_keeper()
    for operation in (view, is_view_loaded):
        with pytest.raises(SnapshotInspectionError) as refusal:
            operation(root, deep.Keeper.animals.toys.no_such_member)
        assert refusal.value.code == "snapshot-view-owner-mismatch"
        assert refusal.value.entity == deep.Toy.identity


# --------------------------------------------------------------------------- #
# Pin and edge.                                                                #
# --------------------------------------------------------------------------- #


_MILESTONE_PIN = Pin(tx_time=dt.datetime(2024, 6, 1, tzinfo=dt.UTC))


def _balance_row(balance_id: int, started: dt.datetime) -> dict[str, object]:
    return {
        "bal_id": balance_id,
        "acct_num": f"A-{balance_id}",
        "val": Decimal("5.00"),
        "in_z": started,
        "out_z": dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
    }


def _balance_graph() -> Any:
    """One temporal `Balance` root materialized under a finite Transaction-Time
    pin, whose own milestone started earlier than the pin selects it at."""
    fixture = PageFixture(_BALANCE)
    balance = fixture.node("Balance", _balance_row(1, dt.datetime(2024, 1, 1, tzinfo=dt.UTC)))
    (root,) = fixture.materialize(balance, pin=_MILESTONE_PIN)
    return root


def test_a_temporal_node_answers_the_whole_graph_pin_and_its_own_edge() -> None:
    root = _balance_graph()
    assert pin_of(root) is _MILESTONE_PIN
    assert edge_of(root).tx_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def test_a_non_temporal_node_reports_its_missing_pin_and_edge_by_code() -> None:
    root = _order_graph()
    with pytest.raises(SnapshotInspectionError) as no_pin:
        pin_of(root)
    assert no_pin.value.code == "snapshot-pin-unavailable"
    assert no_pin.value.entity == sm.SnapOrder.identity

    with pytest.raises(SnapshotInspectionError) as no_edge:
        edge_of(root)
    assert no_edge.value.code == "snapshot-edge-unavailable"
    assert no_edge.value.operation == "edge_of"


def test_the_inspection_code_set_is_closed_against_an_unlisted_code() -> None:
    assert {
        "snapshot-node-required",
        "snapshot-view-owner-mismatch",
        "snapshot-pin-unavailable",
        "snapshot-edge-unavailable",
        "snapshot-wire-envelope-ineligible",
        "snapshot-wire-input-edited",
        "snapshot-wire-input-incompatible",
        "snapshot-wire-at-unrequested",
        "snapshot-wire-at-concrete-mismatch",
    } == SNAPSHOT_INSPECTION_CODES
    with pytest.raises(ValueError, match="not a snapshot inspection code"):
        SnapshotInspectionError(
            code="snapshot-nosuch", message="invented", operation="is_view_loaded"
        )


# --------------------------------------------------------------------------- #
# Shared provenance. Nodes of one Page stating the same facts share one        #
# provenance; a node shares its whole state only when it has no edge to cache, #
# no narrowed view and no Read Evidence.                                       #
# --------------------------------------------------------------------------- #


def test_non_temporal_nodes_without_narrowed_views_share_one_state_per_concrete() -> None:
    root = _order_graph(items=(_item_row(11), _item_row(12)))
    first, second = root.items
    order_state, first_state, second_state = (
        snapshot_state_of(node) for node in (root, first, second)
    )
    assert order_state is not None and first_state is not None

    assert first_state is second_state
    assert order_state is not first_state
    assert not isinstance(first_state.views, NarrowedViews)
    assert order_state.provenance.entity == sm.SnapOrder.identity
    assert first_state.provenance.entity == sm.SnapOrderItem.identity
    with pytest.raises(SnapshotInspectionError) as no_pin:
        pin_of(first)
    assert no_pin.value.entity == sm.SnapOrderItem.identity


def test_temporal_nodes_share_provenance_but_each_owns_its_edge_cache() -> None:
    fixture = PageFixture(_BALANCE)
    earlier = fixture.node("Balance", _balance_row(1, dt.datetime(2024, 1, 1, tzinfo=dt.UTC)))
    later = fixture.node("Balance", _balance_row(2, dt.datetime(2024, 3, 1, tzinfo=dt.UTC)))
    first, second = fixture.materialize(earlier, later, pin=_MILESTONE_PIN)
    first_state, second_state = snapshot_state_of(first), snapshot_state_of(second)
    assert first_state is not None and second_state is not None

    assert first_state is not second_state
    assert first_state.provenance is second_state.provenance
    first_edge = edge_of(first)
    assert first_edge == _BALANCE_EDGE
    assert not isinstance(second_state.edge_cache, Edge)
    assert edge_of(second) == Edge(tx_time=dt.datetime(2024, 3, 1, tzinfo=dt.UTC))
    assert edge_of(first) is first_edge


def test_a_node_with_a_narrowed_view_owns_its_state_and_shares_its_provenance() -> None:
    fixture = PageFixture(_ANIMAL, ("parallax.compatibility.AnimalOwner.pets", "pets[Dog]"))
    alice = fixture.node("AnimalOwner", _OWNER_ROW)
    bob = fixture.node("AnimalOwner", {"id": 11, "name": "Bob", "favorite_id": None})
    for owner, dog_id in ((alice, 1), (bob, 2)):
        dog = fixture.node("Dog", {**_DOG_ROW, "id": dog_id, "owner_id": owner})
        fixture.attach(
            owner, "parallax.compatibility.AnimalOwner.pets", (dog,), narrowed="pets[Dog]"
        )
    first, second = fixture.materialize(alice, bob)
    first_state, second_state = snapshot_state_of(first), snapshot_state_of(second)
    assert first_state is not None and second_state is not None

    assert first_state is not second_state
    assert first_state.provenance is second_state.provenance
    (first_dog,) = cast("tuple[Any, ...]", view(first, sm.AnimalOwner.pets.narrow(sm.Dog)))
    (second_dog,) = cast("tuple[Any, ...]", view(second, sm.AnimalOwner.pets.narrow(sm.Dog)))
    assert (first_dog.id, second_dog.id) == (1, 2)
    assert snapshot_state_of(first_dog) is snapshot_state_of(second_dog)


# --------------------------------------------------------------------------- #
# An Edited Copy. An edit replaces declared member state and preserves         #
# everything else, so the copy carries the very `SnapshotNodeState` its source  #
# node carries: every operation here answers for it, and answers the same.      #
# The carry itself is graded in `test_edit.py`; what it means to this surface   #
# is graded here.                                                              #
# --------------------------------------------------------------------------- #


def test_an_edited_copy_answers_every_view_question_as_its_source_node_did() -> None:
    root = _order_graph(items=(_item_row(11),))
    copy = root.edit(name="renamed")
    assert copy.name == "renamed"
    assert is_view_loaded(copy, sm.SnapOrder.items) is True
    assert is_view_loaded(copy, sm.SnapOrder.statuses) is False
    assert view(copy, sm.SnapOrder.items) == view(root, sm.SnapOrder.items)
    with pytest.raises(UnloadedRelationshipError, match="statuses"):
        view(copy, sm.SnapOrder.statuses)


def test_an_edited_copys_relationships_answer_through_ordinary_attribute_access() -> None:
    # The developer's own spelling, which is the one the closed world is stated
    # over: a loaded view is the value the read paid for, and an unloaded one is
    # a steered refusal naming the include fix — never a bare missing key.
    copy = _order_graph(items=(_item_row(11),)).edit(name="renamed")
    assert [item.id for item in copy.items] == [11]
    with pytest.raises(UnloadedRelationshipError, match="statuses"):
        copy.statuses  # noqa: B018 - the access itself is the assertion


def test_an_edited_copy_of_a_temporal_node_answers_the_same_pin_and_edge() -> None:
    # The pin travels with the copy, which is what makes a mutation derived from
    # a view pinned in the Transaction-Time past refusable at the verb.
    root = _balance_graph()
    copy = root.edit(value=Decimal("9.00"))
    assert pin_of(copy) is _MILESTONE_PIN
    assert edge_of(copy) is edge_of(root)


# --------------------------------------------------------------------------- #
# Sequential inspections derive the milestone Edge once and then share it     #
# across the node and every edit of it, whichever of them asked first.        #
# --------------------------------------------------------------------------- #


_BALANCE_EDGE = Edge(tx_time=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))


@pytest.fixture
def edges_built(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Edge]]:
    """Every Edge constructed while the test runs, in construction order."""
    built: list[Edge] = []
    construct = Edge.__init__

    def recording(edge: Edge, **coordinates: Any) -> None:
        construct(edge, **coordinates)
        built.append(edge)

    monkeypatch.setattr(Edge, "__init__", recording)
    yield built


def test_publication_builds_no_edge_and_the_first_inspection_builds_one(
    edges_built: list[Edge],
) -> None:
    root = _balance_graph()
    assert edges_built == []

    edge = edge_of(root)

    assert edge == _BALANCE_EDGE
    assert len(edges_built) == 1
    assert edge_of(root) is edge
    assert len(edges_built) == 1


def test_an_edit_made_after_inspection_answers_the_edge_its_source_resolved(
    edges_built: list[Edge],
) -> None:
    root = _balance_graph()
    edge = edge_of(root)
    copy = root.edit(value=Decimal("9.00"))
    assert edge_of(copy) is edge
    assert len(edges_built) == 1


def test_inspecting_an_edit_first_resolves_the_edge_for_its_source_and_siblings(
    edges_built: list[Edge],
) -> None:
    root = _balance_graph()
    first = root.edit(value=Decimal("9.00"))
    second = root.edit(value=Decimal("8.00"))

    edge = edge_of(first)

    assert edge == _BALANCE_EDGE
    assert edge_of(root) is edge
    assert edge_of(second) is edge
    assert edge_of(first.edit(value=Decimal("7.00"))) is edge
    assert len(edges_built) == 1


def test_a_failed_first_inspection_leaves_the_edge_to_a_later_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _balance_graph()
    attempts: list[object] = []

    def failing_once(*arguments: Any) -> Edge:
        attempts.append(arguments)
        if len(attempts) == 1:
            raise TemporalReadError("the first attempt fails")
        return milestone_edge(*arguments)

    monkeypatch.setattr(_inspection, "milestone_edge", failing_once)

    with pytest.raises(TemporalReadError, match="first attempt"):
        edge_of(root)
    edge = edge_of(root)

    assert edge == _BALANCE_EDGE
    assert edge_of(root) is edge
    assert len(attempts) == 2


def test_concurrent_first_inspections_answer_equal_edges_and_later_ones_share_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Holding both callers inside the derivation until each has started makes
    # them both find the Edge unresolved, which is the race the cache permits.
    root = _balance_graph()
    copy = root.edit(value=Decimal("9.00"))
    both_deriving = threading.Barrier(2, timeout=10)

    def rendezvous(*arguments: Any) -> Edge:
        both_deriving.wait()
        return milestone_edge(*arguments)

    monkeypatch.setattr(_inspection, "milestone_edge", rendezvous)
    answers: dict[str, Edge] = {}

    def inspect(name: str, node: object) -> None:
        answers[name] = edge_of(node)

    callers = [
        threading.Thread(target=inspect, args=("root", root)),
        threading.Thread(target=inspect, args=("copy", copy)),
    ]
    for caller in callers:
        caller.start()
    for caller in callers:
        caller.join(timeout=10)

    assert answers["root"] == answers["copy"] == _BALANCE_EDGE
    settled = edge_of(root)
    assert any(settled is answer for answer in answers.values())
    assert edge_of(copy) is settled


def test_resolving_the_edge_leaves_the_node_state_equal_to_what_publication_built() -> None:
    root = _balance_graph()
    state = snapshot_state_of(root)
    assert state is not None
    published = dataclasses.replace(state)

    edge_of(root)

    assert snapshot_state_of(root) is state
    assert state == published
