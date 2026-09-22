"""Eager Typed Snapshot publication through the retained Wire shape."""

from __future__ import annotations

import datetime as dt
import gc
import json
import weakref
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import pytest
from pydantic import computed_field, field_serializer

from parallax.conformance import vo_models as vo
from parallax.conformance.animal_owner import ANIMAL_MODEL
from parallax.conformance.animal_owner import Person as AnimalOwnerPerson
from parallax.conformance.read_models import (
    BALANCE_MODEL,
    Animal,
    Balance,
    Cat,
    Dog,
    Pet,
    WildBoar,
)
from parallax.core import (
    TX_TIME,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    RelationshipPath,
    TablePerHierarchy,
    ValueObject,
    attr,
)
from parallax.core import (
    deep_fetch as deep_fetch_module,
)
from parallax.core.base import INFINITY
from parallax.core.object_query import IncludeSegment
from parallax.core.object_query import deserialize as deserialize_query
from parallax.snapshot import (
    InvalidData,
    Snapshot,
    SnapshotInspectionError,
    SnapshotStream,
    WireEntity,
    handle,
    view,
)
from parallax.snapshot._inspection import snapshot_state_of
from parallax.snapshot.handle import _preflight as preflight_module
from parallax.snapshot.materialize import _wire as wire_materialize
from parallax.snapshot.materialize import read_origin_of
from tests._support.db_port import Read, ScriptedAdapter


class _ForeignCustomer(
    Entity,
    name="Customer",
    table="customer",
    namespace="parallax.compatibility",
):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str]
    loyalty: Attr[int]


_FOREIGN_CUSTOMER_MODEL = DomainModel(_ForeignCustomer)


class _Bird(
    Pet,
    name="Bird",
    namespace="parallax.compatibility",
    inheritance=ConcreteSubtype(tag_value="bird"),
):
    wing_span: Attr[int | None]


_EXPANDED_ANIMAL_MODEL = DomainModel(AnimalOwnerPerson, Animal, Pet, Dog, Cat, WildBoar, _Bird)


class _ExtendedEntity(
    Entity,
    name="ExtendedEntity",
    table="extended_entity",
    namespace="parallax.compatibility",
):
    id: Attr[int] = attr(primary_key=True, column="entity_id")
    external_label: Attr[str] = attr(column="label_col")

    @computed_field
    @property
    def poisoned_computed(self) -> str:
        raise AssertionError("Wire projection invoked a computed field")

    @field_serializer("external_label")
    def _poisoned_serializer(self, value: str) -> str:
        del value
        raise AssertionError("Wire projection invoked a field serializer")


_EXTENDED_MODEL = DomainModel(_ExtendedEntity)


class _NarrowedDetails(ValueObject):
    label: Attr[str]


class _NarrowedRoot(
    Entity,
    name="NarrowedRoot",
    table="narrowed_root",
    namespace="parallax.compatibility",
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    details: Attr[_NarrowedDetails]


class _NarrowedLeft(
    _NarrowedRoot,
    name="NarrowedLeft",
    namespace="parallax.compatibility",
    inheritance=ConcreteSubtype(tag_value="left"),
):
    left_value: Attr[int | None]


class _NarrowedRight(
    _NarrowedRoot,
    name="NarrowedRight",
    namespace="parallax.compatibility",
    inheritance=ConcreteSubtype(tag_value="right"),
):
    right_value: Attr[int | None]


_NARROWED_MODEL = DomainModel(_NarrowedRoot, _NarrowedLeft, _NarrowedRight)


if TYPE_CHECKING:

    def _static_projection_contract(  # pyright: ignore[reportUnusedFunction] - static contract probe
        typed: Snapshot[vo.Customer],
        wire: Snapshot[WireEntity],
        customer: vo.Customer,
        invalid: InvalidData[vo.Customer],
        typed_stream: SnapshotStream[vo.Customer],
        wire_stream: SnapshotStream[WireEntity],
    ) -> None:
        projected: Snapshot[WireEntity] = typed.wire()
        node: WireEntity = typed.wire(customer)
        projected_invalid: InvalidData[WireEntity] = typed.wire(invalid)
        streamed_node: WireEntity = typed_stream.wire(customer)
        streamed_invalid: InvalidData[WireEntity] = typed_stream.wire(invalid)
        del projected, node, projected_invalid, streamed_node, streamed_invalid
        wire.wire()  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType] - Wire envelopes are ineligible receivers
        wire_stream.wire(customer)  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType] - Wire streams are ineligible receivers
        typed_stream.wire()  # pyright: ignore[reportCallIssue] - stream projection always takes one element
        typed.wire(at=vo.Customer.locations)  # pyright: ignore[reportCallIssue] - whole-result projection has no position override
        wrong: vo.Customer = typed.wire()  # pyright: ignore[reportAssignmentType] - projection returns the Wire envelope
        del wrong


def _customer_row(*, valid: bool = True) -> dict[str, object]:
    return {
        "id": 1,
        "name": "Ada",
        "address": (
            {"street": "1 Park Ave", "city": "Oslo", "phones": []} if valid else {"city": 7}
        ),
    }


def _database(
    *reads: Read,
) -> tuple[handle.Database[Any], handle.ScopedDatabase]:
    root = cast(
        "handle.Database[Any]",
        handle.Database.connect(ScriptedAdapter(*reads), vo.CUSTOMER_MODEL),
    )
    return root, root.using_database_login()


def test_whole_result_projection_preserves_envelope_and_origin_without_io() -> None:
    root, db = _database(Read(rows=[_customer_row()]))
    typed = db.find(vo.Customer.where(vo.Customer.id == 1))
    customer = typed.result()
    state = snapshot_state_of(customer)
    assert state is not None
    root.close()

    direct_root, direct_db = _database(Read(rows=[_customer_row()]))
    direct = direct_db.wire.find(vo.Customer.where(vo.Customer.id == 1))
    direct_root.close()

    projected = typed.wire()
    wire = projected.result()

    assert projected.result() == direct.result()
    assert wire == {
        "id": 1,
        "name": "Ada",
        "address": {"street": "1 Park Ave", "city": "Oslo", "phones": []},
    }
    assert projected.pin == typed.pin
    assert projected.edition == typed.edition
    assert read_origin_of(wire) is state.source


def test_projection_does_not_serialize_or_reclassify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, db = _database(Read(rows=[_customer_row()]))
    typed = db.find(vo.Customer.where(vo.Customer.id == 1))
    root.close()

    def forbidden(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("projection crossed a forbidden publication seam")

    original_named_state_value = cast("Any", wire_materialize).named_state_value
    named_state_reads = 0

    def observed_named_state_value(value: object, name: str, default: object = None) -> object:
        nonlocal named_state_reads
        named_state_reads += 1
        return original_named_state_value(cast("Any", value), name, default)

    monkeypatch.setattr(wire_materialize, "named_state_value", observed_named_state_value)

    monkeypatch.setattr(vo.Customer, "model_dump", forbidden)
    monkeypatch.setattr(deep_fetch_module, "plan", forbidden)
    monkeypatch.setattr(preflight_module, "preflight", forbidden)
    monkeypatch.setattr(wire_materialize, "classify_roots", forbidden)

    assert typed.wire().result()["name"] == "Ada"
    assert named_state_reads > 0


def test_projection_ignores_pydantic_extensions_and_is_directly_json_serializable() -> None:
    row = {"entity_id": 1, "label_col": "Ada"}
    root = cast(
        "handle.Database[Any]",
        handle.Database.connect(
            ScriptedAdapter(Read(rows=[row]), Read(rows=[row])), _EXTENDED_MODEL
        ),
    )
    db = root.using_database_login()
    query = _ExtendedEntity.where(_ExtendedEntity.id == 1)

    typed = db.find(query)
    projected = typed.wire()
    direct = db.wire.find(query)
    root.close()

    assert projected.results() == direct.results()
    assert json.loads(json.dumps(projected.checked().results())) == [
        {"id": 1, "externalLabel": "Ada"}
    ]


def test_whole_result_projection_preserves_root_order() -> None:
    second = {**_customer_row(), "id": 2, "name": "Grace"}
    root, db = _database(Read(rows=[_customer_row(), second]))
    typed = db.find(vo.Customer.where(vo.Customer.all))
    root.close()

    assert [value["id"] for value in typed.wire().results()] == [1, 2]


def test_element_projection_accepts_an_external_published_node_without_membership() -> None:
    root, db = _database(Read(rows=[]), Read(rows=[_customer_row()]))
    empty = db.find(vo.Customer.where(vo.Customer.id == 99).include(vo.Customer.locations))
    external = db.find(vo.Customer.where(vo.Customer.id == 1)).result()
    root.close()

    projected = empty.wire(external)

    assert projected["id"] == 1
    assert "locations" not in projected
    state = snapshot_state_of(external)
    assert state is not None
    assert read_origin_of(projected) is state.source


def test_element_projection_refuses_edited_and_unpublished_values() -> None:
    root, db = _database(Read(rows=[_customer_row()]))
    snapshot = db.find(vo.Customer.where(vo.Customer.id == 1))
    customer = snapshot.result()
    root.close()

    with pytest.raises(SnapshotInspectionError) as edited:
        snapshot.wire(customer.edit(name="Grace"), at=vo.Customer.depots)
    assert edited.value.code == "snapshot-wire-input-edited"

    with pytest.raises(SnapshotInspectionError) as unpublished:
        snapshot.wire(
            vo.Customer(id=2, name="Lin", address=None),
            at=vo.Customer.depots,
        )
    assert unpublished.value.code == "snapshot-node-required"


def test_element_projection_refuses_a_mismatched_published_layout_before_position_admission() -> (
    None
):
    # A separately accepted Customer edition adds a declared member; projection must
    # reject that published layout before considering whether its requested position
    # admits the otherwise identically named concrete.
    root, db = _database(Read(rows=[]))
    snapshot = db.find(vo.Customer.where(vo.Customer.id == 99))
    foreign_root = cast(
        "handle.Database[Any]",
        handle.Database.connect(
            ScriptedAdapter(Read(rows=[{"id": 1, "name": "Ada", "loyalty": 4}])),
            _FOREIGN_CUSTOMER_MODEL,
        ),
    )
    foreign = (
        foreign_root.using_database_login()
        .find(_ForeignCustomer.where(_ForeignCustomer.id == 1))
        .result()
    )
    root.close()
    foreign_root.close()

    with pytest.raises(SnapshotInspectionError) as refusal:
        cast("Any", snapshot).wire(foreign, at=vo.Customer.locations)
    assert refusal.value.code == "snapshot-wire-input-incompatible"


def test_projection_preserves_hydrated_and_nonhydrating_invalid_records() -> None:
    hydrating: dict[str, object] = {
        "id": 1,
        "name": "Ada",
        "address": {"city": "Oslo", "phones": []},
    }
    root, db = _database(Read(rows=[hydrating]), Read(rows=[_customer_row(valid=False)]))
    hydrated_snapshot = db.find(vo.Customer.where(vo.Customer.id == 1))
    nonhydrating_snapshot = db.find(vo.Customer.where(vo.Customer.id == 1))
    root.close()

    hydrated = cast("InvalidData[vo.Customer]", hydrated_snapshot.checked().result())
    projected_hydrated = hydrated_snapshot.wire(hydrated)
    projected_whole = hydrated_snapshot.wire().checked().result()
    assert isinstance(projected_hydrated, InvalidData)
    assert projected_whole == projected_hydrated
    assert projected_hydrated.data == {
        "id": 1,
        "name": "Ada",
        "address": {"city": "Oslo", "phones": []},
    }
    assert (
        projected_hydrated.issues,
        projected_hydrated.object_key,
        projected_hydrated.version,
        projected_hydrated.edge,
        projected_hydrated.ordinal,
    ) == (
        hydrated.issues,
        hydrated.object_key,
        hydrated.version,
        hydrated.edge,
        hydrated.ordinal,
    )

    nonhydrating = cast("InvalidData[vo.Customer]", nonhydrating_snapshot.checked().result())
    projected_nonhydrating = nonhydrating_snapshot.wire(nonhydrating)
    assert isinstance(projected_nonhydrating, InvalidData)
    assert projected_nonhydrating.data is None
    assert projected_nonhydrating == nonhydrating


def test_invalid_narrowed_view_projects_only_its_position_evidence() -> None:
    invalid_left: dict[str, object] = {
        "id": 1,
        "kind": "left",
        "details": {},
        "left_value": 7,
        "right_value": 9,
    }
    root = cast(
        "handle.Database[Any]",
        handle.Database.connect(
            ScriptedAdapter(
                Read(rows=[invalid_left]),
                Read(rows=[invalid_left]),
            ),
            _NARROWED_MODEL,
        ),
    )
    db = root.using_database_login()
    query = _NarrowedRoot.where(_NarrowedRoot.id == 1).narrow(_NarrowedLeft)

    projected = db.find(query).wire().checked()
    direct = db.wire.find(query).checked()
    root.close()

    assert projected.results() == direct.results()
    invalid = projected.result()
    assert isinstance(invalid, InvalidData)
    assert invalid.data is not None
    assert invalid.data["familyVariant"] == "NarrowedLeft"
    assert "rightValue" not in invalid.data
    direct_invalid = direct.result()
    assert isinstance(direct_invalid, InvalidData)
    assert (
        invalid.issues,
        invalid.object_key,
        invalid.version,
        invalid.edge,
        invalid.ordinal,
    ) == (
        direct_invalid.issues,
        direct_invalid.object_key,
        direct_invalid.version,
        direct_invalid.edge,
        direct_invalid.ordinal,
    )


def test_explicit_position_is_strict_and_admits_the_requested_concrete() -> None:
    location: dict[str, object] = {
        "id": 10,
        "customer_id": 1,
        "label": "Home",
        "address": {"street": "1 Park Ave", "city": "Oslo", "phones": []},
    }
    root, db = _database(Read(rows=[_customer_row()]), Read(rows=[location]))
    snapshot = db.find(vo.Customer.where(vo.Customer.id == 1).include(vo.Customer.locations))
    customer = snapshot.result()
    projected = snapshot.wire(customer.locations[0], at=vo.Customer.locations)
    assert projected["label"] == "Home"

    with pytest.raises(SnapshotInspectionError) as unrequested:
        snapshot.wire(customer.locations[0], at=vo.Customer.depots)
    assert unrequested.value.code == "snapshot-wire-at-unrequested"

    unknown = RelationshipPath[vo.Customer, Entity](
        segments=(IncludeSegment(rel="parallax.compatibility.Customer.unknown"),),
        target="parallax.compatibility.Entity",
    )
    with pytest.raises(SnapshotInspectionError) as invalid_path:
        snapshot.wire(customer, at=unknown)
    assert invalid_path.value.code == "snapshot-wire-at-unrequested"

    with pytest.raises(SnapshotInspectionError) as wrong_concrete:
        snapshot.wire(customer, at=vo.Customer.locations)
    assert wrong_concrete.value.code == "snapshot-wire-at-concrete-mismatch"
    root.close()


def test_wire_envelopes_are_ineligible_even_when_empty() -> None:
    root, db = _database(Read(rows=[]))
    wire = db.wire.find(deserialize_query({"target": "Customer", "predicate": {"all": {}}}))
    root.close()

    with pytest.raises(SnapshotInspectionError) as refusal:
        cast("Any", wire).wire()
    assert refusal.value.code == "snapshot-wire-envelope-ineligible"


def test_whole_result_projection_accepts_no_position_override() -> None:
    root, db = _database(Read(rows=[_customer_row()]))
    snapshot = db.find(vo.Customer.where(vo.Customer.id == 1))
    root.close()

    for supplied in (None, vo.Customer.locations):
        with pytest.raises(TypeError, match="accepts no at"):
            cast("Any", snapshot).wire(at=supplied)


def test_projection_uses_the_retained_model_for_equivalent_positions() -> None:
    old = handle.prepare_model(ANIMAL_MODEL, edition="old")
    current = handle.prepare_model(_EXPANDED_ANIMAL_MODEL, edition="current")
    serving = handle.ServingModel(old)
    root = cast(
        "handle.Database[Any]",
        handle.Database.connect(
            ScriptedAdapter(
                Read(rows=[{"id": 10, "name": "Alice"}]),
                Read(
                    rows=[
                        {
                            "id": 1,
                            "kind": "dog",
                            "name": "Rex",
                            "owner_id": 10,
                            "license_id": "L-100",
                            "bark_volume": 7,
                        }
                    ]
                ),
            ),
            serving,
        ),
    )
    snapshot = root.using_database_login().find(
        AnimalOwnerPerson.where(AnimalOwnerPerson.id == 10).include(
            AnimalOwnerPerson.pets.narrow(Pet)
        )
    )
    pet = cast(
        "tuple[Entity, ...]",
        view(snapshot.result(), AnimalOwnerPerson.pets.narrow(Cat, Dog)),
    )[0]

    serving.publish(current, expected=old)

    equivalent = snapshot.wire(
        pet,
        at=AnimalOwnerPerson.pets.narrow(Cat, Dog),
    )
    assert equivalent["familyVariant"] == "Dog"
    assert snapshot.edition == "old"
    with pytest.raises(SnapshotInspectionError) as subset:
        snapshot.wire(pet, at=AnimalOwnerPerson.pets.narrow(Dog))
    assert subset.value.code == "snapshot-wire-at-unrequested"
    root.close()


def test_history_projection_preserves_canonical_scalars() -> None:
    rows = [
        {
            "bal_id": 1,
            "acct_num": "A-1",
            "val": Decimal("5.00"),
            "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            "out_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
        },
        {
            "bal_id": 1,
            "acct_num": "A-1",
            "val": Decimal("9.00"),
            "in_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
            "out_z": INFINITY,
        },
    ]
    query = Balance.where(Balance.id == 1).history(TX_TIME)
    root = cast(
        "handle.Database[Any]",
        handle.Database.connect(
            ScriptedAdapter(Read(rows=rows), Read(rows=rows)),
            BALANCE_MODEL,
        ),
    )
    db = root.using_database_login()

    typed = db.find(query)
    projected = typed.wire()
    direct = db.wire.find(query)

    assert projected.results() == direct.results()
    assert [node["value"] for node in projected.results()] == ["5.00", "9.00"]
    assert projected.results()[0]["txStart"] == "2024-01-01T00:00:00.000000Z"
    assert projected.results()[1]["txEnd"] == "infinity"
    assert projected.pin == typed.pin
    root.close()


def test_projected_output_is_frozen_at_every_depth() -> None:
    root, db = _database(Read(rows=[_customer_row()]))
    projected = db.find(vo.Customer.where(vo.Customer.id == 1)).wire().result()
    root.close()

    with pytest.raises(TypeError):
        cast("Any", projected)["name"] = "Grace"
    address = cast("Any", projected["address"])
    with pytest.raises(TypeError):
        address["city"] = "Bergen"
    with pytest.raises(TypeError):
        address["phones"].append("555-0100")


def test_failed_projection_releases_successful_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    second = {**_customer_row(), "id": 2, "name": "Grace"}
    root, db = _database(Read(rows=[_customer_row(), second]))
    snapshot = db.find(vo.Customer.where(vo.Customer.all))
    first_ref = weakref.ref(snapshot.results()[0])
    original = wire_materialize.WireWalk[object].position
    calls = 0

    def fail_second(
        walk: wire_materialize.WireWalk[object],
        node: object,
        position: int,
    ) -> WireEntity:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second projection failed")
        return original(walk, node, position)

    monkeypatch.setattr(wire_materialize.WireWalk, "position", fail_second)
    with pytest.raises(RuntimeError, match="second projection failed") as failure:
        snapshot.wire()

    root.close()
    del snapshot
    gc.collect()
    assert first_ref() is None
    assert failure.value.args == ("second projection failed",)
