"""One model's storage facts: where each stated member's cell lands, gathered
once per presence and retained within a bound."""

from __future__ import annotations

import gc
import weakref
from decimal import Decimal as PyDecimal

import pytest

from parallax.core import Attr, DomainModel, Entity, ValueObject, attr, storage_layout
from parallax.core.base import INT64, STRING, FrozenMap
from parallax.core.entity import Document
from parallax.core.entity._model import model_of
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, ValueObjectIdentity
from parallax.core.storage_layout import InheritanceDiscriminator, RelationalDocument
from parallax.core.write_payload._storage import ROW_SLOTS_PER_ENTITY, StorageCatalog
from parallax.core.write_plan import WritePlanningError
from parallax.core.write_plan.steps import NEW_LINEAGE, WriteRow
from tests._support.managed_rows import managed_row_of
from tests.unit._corpus_model_support import model as corpus_model

_NS = "storage.catalog"


class Spot(ValueObject):
    code: Attr[str]
    rank: Attr[int | None]


class Bin(Entity, table="bin", namespace=_NS):
    name: Attr[str]
    id: Attr[int] = attr(primary_key=True)
    note: Attr[str | None]
    sizes: Attr[tuple[int, ...]]
    spot: Attr[Spot | None]
    price: Attr[PyDecimal] = attr(precision=8, scale=2)


class Crate(Entity, table="crate", namespace=_NS, layout=Document):
    name: Attr[str]
    id: Attr[int] = attr(primary_key=True)
    note: Attr[str | None]
    sizes: Attr[tuple[int, ...]]
    spot: Attr[Spot | None]
    price: Attr[PyDecimal] = attr(precision=8, scale=2)


class Peg(Entity, table="peg", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    a: Attr[int | None]
    b: Attr[int | None]
    c: Attr[int | None]
    d: Attr[int | None]
    e: Attr[int | None]


_META = model_of(DomainModel(Bin, Crate, Peg))
_BIN = EntityIdentity(_NS, "Bin")
_CRATE = EntityIdentity(_NS, "Crate")
_PEG = EntityIdentity(_NS, "Peg")


def _row(entity: EntityIdentity, **members: object) -> WriteRow:
    attributes = {
        AttributeIdentity(entity, name): value for name, value in members.items() if name != "spot"
    }
    occurrences = (
        {ValueObjectIdentity(entity, ("spot",)): members["spot"]} if "spot" in members else {}
    )
    return WriteRow(
        row=managed_row_of(_META, attributes, occurrences, entity=entity), origin=NEW_LINEAGE
    )


_FULL = {
    "name": "N",
    "id": 7,
    "note": "n",
    "sizes": (1, 2),
    "spot": {"code": "A", "rank": 3},
    "price": PyDecimal("2.50"),
}


def test_slots_follow_table_order_whatever_order_the_members_are_declared_in() -> None:
    row = _row(_BIN, **_FULL)
    slots = StorageCatalog(_META).entity(_BIN).row_slots(row.row.presence)

    assert slots.columns == ("id", "name", "note", "price", "sizes", "spot")
    assert slots.types == (INT64, STRING, STRING, slots.types[3], None, None)
    assert slots.documents == (False, False, False, False, True, True)
    assert slots.shared_document is None
    assert slots.cells(row) == (
        7,
        "N",
        "n",
        PyDecimal("2.50"),
        (1, 2),
        FrozenMap({"code": "A", "rank": 3}),
    )


def test_a_document_twin_gathers_its_resident_members_into_one_document() -> None:
    row = _row(_CRATE, **_FULL)
    slots = StorageCatalog(_META).entity(_CRATE).row_slots(row.row.presence)

    assert slots.columns[0] == "id"
    assert isinstance(slots.contributors[slots.shared_document or 0], RelationalDocument)
    document = slots.cells(row)[slots.shared_document or 0]
    assert document == FrozenMap(
        {
            "name": "N",
            "note": "n",
            "sizes": (1, 2),
            "spot": FrozenMap({"code": "A", "rank": 3}),
            "price": "2.50",
        }
    )


def test_a_sparse_row_omits_an_unstated_nullable_column_and_stores_its_empty_collection() -> None:
    row = _row(_BIN, name="N", id=7, price=PyDecimal("1.00"))
    slots = StorageCatalog(_META).entity(_BIN).row_slots(row.row.presence)

    assert slots.columns == ("id", "name", "price", "sizes")
    assert slots.cells(row) == (7, "N", PyDecimal("1.00"), ())
    narrow = _row(_CRATE, name="N", id=7, price=PyDecimal("1.00"))
    document = StorageCatalog(_META).entity(_CRATE).row_slots(narrow.row.presence).cells(narrow)
    assert document[1] == FrozenMap({"name": "N", "sizes": (), "price": "1.00"})


@pytest.mark.parametrize(
    ("members", "expected"),
    [
        pytest.param({"id": 7}, (7, ()), id="one-direct-cell"),
        pytest.param({"id": 7, "name": "N"}, (7, "N", ()), id="many-direct-cells"),
    ],
)
def test_a_gather_answers_a_tuple_whatever_the_number_of_cells(
    members: dict[str, object], expected: tuple[object, ...]
) -> None:
    row = _row(_BIN, **members)
    assert StorageCatalog(_META).entity(_BIN).row_slots(row.row.presence).cells(row) == expected


@pytest.mark.parametrize(
    ("members", "expected"),
    [
        pytest.param({"id": 7}, (7,), id="one-cell"),
        pytest.param({"id": 7, "c": None, "e": 5}, (7, None, 5), id="many-cells"),
    ],
)
def test_a_row_storing_only_direct_cells_gathers_them_as_one_tuple(
    members: dict[str, object], expected: tuple[object, ...]
) -> None:
    attributes = {AttributeIdentity(_PEG, name): value for name, value in members.items()}
    row = WriteRow(row=managed_row_of(_META, attributes, entity=_PEG), origin=NEW_LINEAGE)
    storage = StorageCatalog(_META).entity(_PEG)
    assert storage.row_slots(row.row.presence).cells(row) == expected
    assert storage.row_slots(0).cells(row) == ()


def test_a_subtypes_slots_store_its_discriminator_as_a_constant() -> None:
    vehicles = corpus_model("vehicle")
    car = EntityIdentity("parallax.compatibility", "Car")
    vehicle = EntityIdentity("parallax.compatibility", "Vehicle")
    row = WriteRow(
        row=managed_row_of(
            vehicles,
            {AttributeIdentity(vehicle, "id"): 1, AttributeIdentity(car, "doors"): 2},
            entity=car,
        ),
        origin=NEW_LINEAGE,
    )
    slots = StorageCatalog(vehicles).entity(car).row_slots(row.row.presence)

    tag = next(
        index
        for index, contributor in enumerate(slots.contributors)
        if isinstance(contributor, InheritanceDiscriminator)
    )
    assert slots.cells(row)[tag] == "car"
    assert slots.types[tag] is None
    assert not slots.documents[tag]


def test_one_presence_shares_one_slots_and_the_cache_retains_a_bounded_number() -> None:
    storage = StorageCatalog(_META).entity(_PEG)
    presences = [1 | optional << 1 for optional in range(1 << 5)]
    assert len(presences) > ROW_SLOTS_PER_ENTITY
    retained = [storage.row_slots(presence) for presence in presences[:ROW_SLOTS_PER_ENTITY]]
    beyond = presences[ROW_SLOTS_PER_ENTITY]
    first, second = storage.row_slots(beyond), storage.row_slots(beyond)

    assert all(
        storage.row_slots(presence) is slots
        for presence, slots in zip(presences, retained, strict=False)
    )
    assert first is not second
    assert (
        first.columns
        == second.columns
        == ("id", "a", "b", "c", "d", "e")[:1]
        + tuple(name for bit, name in enumerate("abcde", start=1) if beyond >> bit & 1)
    )


def test_a_member_without_a_column_is_refused_and_a_tableless_entity_has_no_storage() -> None:
    catalog = StorageCatalog(_META)
    with pytest.raises(WritePlanningError, match="occupies no Column"):
        catalog.entity(_PEG).row_slots(1 << 30)
    with pytest.raises(WritePlanningError, match="no effective table"):
        catalog.entity(EntityIdentity(_NS, "Nowhere"))


def test_a_catalog_keeps_no_model_alive() -> None:
    model = model_of(DomainModel(Bin))
    catalog = StorageCatalog(model)
    catalog.entity(_BIN).row_slots(1)
    layout = weakref.ref(storage_layout.view(model))
    del model, catalog
    gc.collect()
    assert layout() is None
