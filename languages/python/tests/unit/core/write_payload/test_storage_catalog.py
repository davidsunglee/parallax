"""One model's storage facts: where each stated member's cell lands, gathered
once per presence and retained within a bound."""

from __future__ import annotations

import datetime as dt
import gc
import weakref
from decimal import Decimal as PyDecimal

import pytest

from parallax.core import Attr, DomainModel, Entity, ValueObject, attr, storage_layout
from parallax.core.base import INT32, INT64, JSON, STRING, FrozenMap
from parallax.core.entity import Document
from parallax.core.entity._model import model_of
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, ValueObjectIdentity
from parallax.core.storage_layout import InheritanceDiscriminator, RelationalDocument
from parallax.core.write_payload._storage import ROW_SLOTS_PER_ENTITY, EffectShape, StorageCatalog
from parallax.core.write_plan import WritePlanningError
from parallax.core.write_plan.steps import (
    INFINITY,
    MISSING_TARGET,
    NEW_LINEAGE,
    STALE_WRITE,
    SUPERSEDED,
    UNGATED,
    UNVERSIONED,
    ExactCount,
    KeyTarget,
    MilestoneTarget,
    PlannedAssignments,
    PlannedClose,
    PlannedTemporalRevision,
    PlannedUpdate,
    WriteRow,
)
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


def test_each_slot_names_the_one_element_type_every_cell_it_stores_shares() -> None:
    row = _row(_BIN, **_FULL)
    bin_slots = StorageCatalog(_META).entity(_BIN).row_slots(row.row.presence)
    crate_slots = StorageCatalog(_META).entity(_CRATE).row_slots(row.row.presence)

    assert bin_slots.element_types == (INT64, STRING, STRING, bin_slots.types[3], JSON, JSON)
    assert crate_slots.element_types == (INT64, JSON)
    vehicles = corpus_model("vehicle")
    car = EntityIdentity("parallax.compatibility", "Car")
    vehicle = EntityIdentity("parallax.compatibility", "Vehicle")
    car_row = managed_row_of(
        vehicles,
        {AttributeIdentity(vehicle, "id"): 1, AttributeIdentity(car, "doors"): 2},
        entity=car,
    )
    car_slots = StorageCatalog(vehicles).entity(car).row_slots(car_row.presence)
    assert [
        element_type
        for contributor, element_type in zip(
            car_slots.contributors, car_slots.element_types, strict=True
        )
        if isinstance(contributor, InheritanceDiscriminator)
    ] == [STRING]


def test_column_cells_answer_one_new_list_per_slot_in_row_order() -> None:
    storage = StorageCatalog(_META).entity(_BIN)
    rows = [
        _row(_BIN, name="N", id=7, price=PyDecimal("1.00"), sizes=()),
        _row(_BIN, name="M", id=8, price=PyDecimal("2.00"), sizes=(4,)),
    ]
    slots = storage.row_slots(rows[0].row.presence)
    gathered = [slots.cells(row) for row in rows]

    columns = slots.column_cells(gathered)

    assert columns == (
        [7, 8],
        ["N", "M"],
        [PyDecimal("1.00"), PyDecimal("2.00")],
        [(), (4,)],
    )
    assert all(type(column) is list for column in columns)
    assert columns[3][1] is gathered[1][3]
    assert slots.column_cells([]) == ([], [], [], [])


def test_a_column_the_slot_fixes_repeats_its_value_for_every_row() -> None:
    vehicles = corpus_model("vehicle")
    car = EntityIdentity("parallax.compatibility", "Car")
    vehicle = EntityIdentity("parallax.compatibility", "Vehicle")
    rows = [
        WriteRow(
            row=managed_row_of(
                vehicles,
                {AttributeIdentity(vehicle, "id"): key, AttributeIdentity(car, "doors"): 2},
                entity=car,
            ),
            origin=NEW_LINEAGE,
        )
        for key in (1, 2, 3)
    ]
    slots = StorageCatalog(vehicles).entity(car).row_slots(rows[0].row.presence)
    tag = next(
        index
        for index, contributor in enumerate(slots.contributors)
        if isinstance(contributor, InheritanceDiscriminator)
    )
    assert slots.column_cells([slots.cells(row) for row in rows])[tag] == ["car"] * 3


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


def test_one_effect_shape_shares_one_effect_slots_and_the_cache_retains_a_bounded_number() -> None:
    storage = StorageCatalog(_META).entity(_PEG)
    key = (AttributeIdentity(_PEG, "id"),)
    shapes = [
        EffectShape(PlannedUpdate, _PEG, key, optional << 1, None) for optional in range(1, 1 << 5)
    ]
    assert len(shapes) > ROW_SLOTS_PER_ENTITY
    retained = [storage.effect_slots(shape) for shape in shapes[:ROW_SLOTS_PER_ENTITY]]
    beyond = shapes[ROW_SLOTS_PER_ENTITY]
    first, second = storage.effect_slots(beyond), storage.effect_slots(beyond)

    assert all(
        storage.effect_slots(shape) is slots for shape, slots in zip(shapes, retained, strict=False)
    )
    assert first is not second
    assert first.element_types == second.element_types
    assert first.key_sources == (0,)
    assert first.gate_source is None
    assert first.assignment_sources == tuple(range(1, beyond.presence.bit_count() + 1))


def test_only_a_non_primary_unique_key_member_makes_an_update_ungroupable() -> None:
    passport = corpus_model("person")
    storage = StorageCatalog(passport).entity(EntityIdentity("parallax.compatibility", "Passport"))

    def update(member: str) -> PlannedUpdate:
        identity = AttributeIdentity(storage.entity, member)
        return PlannedUpdate(
            entity=storage.entity,
            target=KeyTarget(
                key_attributes=(AttributeIdentity(storage.entity, "id"),), key_values=((1,),)
            ),
            assignments=PlannedAssignments(
                attributes={identity: 7 if member == "personId" else "N"}
            ),
            concurrency=UNVERSIONED,
            affected_rows=ExactCount(1, MISSING_TARGET),
        )

    assert storage.effect_shape(update("personId")) is None
    assert storage.effect_shape(update("number")) is not None


@pytest.mark.parametrize(
    ("name", "ends"),
    [("Handle", ("txEnd",)), ("Assignment", ("validEnd", "txEnd"))],
    ids=["transaction-time", "bitemporal"],
)
def test_a_temporal_unique_keys_axis_ends_never_make_a_milestone_effect_ungroupable(
    name: str, ends: tuple[str, ...]
) -> None:
    storage = StorageCatalog(corpus_model("temporal-authored-index")).entity(
        EntityIdentity("parallax.compatibility", name)
    )
    entity = storage.entity
    end_attributes = tuple(AttributeIdentity(entity, end) for end in ends)
    (code,) = storage.view.layout.unique_keys[1:]
    assert code.column_attributes == (AttributeIdentity(entity, "code"), *end_attributes)
    target = MilestoneTarget(
        key_attributes=(AttributeIdentity(entity, "id"),),
        key_values=(1,),
        end_attributes=end_attributes,
        end_values=(INFINITY,) * len(ends),
    )
    closed_at = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    close = PlannedClose(
        entity=entity,
        target=target,
        assignments=PlannedAssignments({AttributeIdentity(entity, "txEnd"): closed_at}),
        cause=SUPERSEDED,
        concurrency=UNGATED,
        affected_rows=ExactCount(1, STALE_WRITE),
    )

    def revision(member: str, value: str) -> PlannedTemporalRevision:
        return PlannedTemporalRevision(
            entity=entity,
            target=target,
            assignments=PlannedAssignments({AttributeIdentity(entity, member): value}),
            concurrency=UNGATED,
            affected_rows=ExactCount(1, STALE_WRITE),
            predecessor_document_is_object=True,
        )

    assert storage.effect_shape(close) is not None
    assert storage.effect_shape(revision("label", "b")) is not None
    assert storage.effect_shape(revision("code", "Z")) is None


def test_effect_slots_of_a_document_twin_skip_a_shared_document_no_path_of_which_is_assigned() -> (
    None
):
    meta = corpus_model("scalar-collection-lifecycle-layout-twin-document")
    entity = EntityIdentity("parallax.compatibility", "TagLedger")
    storage = StorageCatalog(meta).entity(entity)
    version = AttributeIdentity(entity, "version")
    position = storage.view.member_selection.index[version]
    slots = storage.effect_slots(
        EffectShape(PlannedUpdate, entity, (AttributeIdentity(entity, "id"),), 1 << position, None)
    )
    assert slots.assignment_sources == (1,)
    assert slots.element_types == (INT64, INT32)
    assert slots.parameter_count == 2
