"""``models.entity(...)`` and ``models.entities``: model-relative, resolved,
read-only lookup.

The three key forms answer one object, enumeration is canonical Entity order,
and every miss carries a code. Each Entity answers a declared profile — what it
declares itself — and an effective profile — what is in force on it — whose
members are the declared profiles' own objects. Classes are declared at module
scope because one composition per model answers every lookup asked of it.
"""

from __future__ import annotations

import dataclasses
from collections.abc import MutableSequence, Sequence
from decimal import Decimal
from typing import Protocol, get_args

import pytest

from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    READ_ONLY,
    READ_WRITE,
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    AbstractSubtype,
    ApplicationAssigned,
    Attr,
    Columns,
    ConcreteSubtype,
    Document,
    DomainModel,
    Entity,
    Int32,
    Numeric,
    Rel,
    TablePerHierarchy,
    TxTemporal,
    UsageError,
    ValueObject,
    attr,
    index,
    rel,
)
from parallax.core.entity._errors import MetamodelLookupCode
from parallax.core.introspection import EntityIdentity, PrimaryKey, Table, TemporalDimension
from tests._support.errors import raises_code

_SPEC_CODES = frozenset({"metamodel-invalid-entity-reference", "metamodel-entity-not-found"})


class Address(ValueObject):
    city: Attr[str]


class Zone(Entity, table="zone", namespace="ops"):
    id: Attr[int] = attr(primary_key=True)
    depots: Rel[tuple[Depot, ...]] = rel(reverse_of="zone")


class Depot(
    Entity,
    table="depot",
    namespace="ops",
    indices=(index("depot_code", "code"),),
):
    id: Attr[int] = attr(primary_key=True)
    code: Attr[str]
    zone_id: Attr[int]
    address: Attr[Address | None]
    zone: Rel[Zone] = rel(cardinality=MANY_TO_ONE, join=("zone_id", "id"))


class Ownerless(Entity, table="ownerless"):
    id: Attr[int] = attr(primary_key=True)


MODELS = DomainModel(Depot, Zone, Ownerless)


class Payment(
    Entity,
    table="payment",
    namespace="ops",
    layout=Document(column="body"),
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    zone_id: Attr[int]
    zone: Rel[Zone] = rel(cardinality=MANY_TO_ONE, join=("zone_id", "id"))


class Card(Payment, namespace="ops", inheritance=ConcreteSubtype(tag_value="card")):
    number: Attr[str]
    depot_id: Attr[int]
    depot: Rel[Depot] = rel(cardinality=MANY_TO_ONE, join=("depot_id", "id"))


class Deferred(Payment, namespace="ops", inheritance=AbstractSubtype):
    due: Attr[int]


class Invoice(Deferred, namespace="ops", inheritance=ConcreteSubtype(tag_value="invoice")):
    reference: Attr[str]


class Voucher(Payment, namespace="ops", inheritance=AbstractSubtype()):
    code: Attr[str]


class Craft(Entity, namespace="ops", inheritance=AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE)):
    id: Attr[int] = attr(primary_key=True)


class Sloop(Craft, table="sloop", namespace="ops", inheritance=ConcreteSubtype()):
    masts: Attr[int]


class Meter(
    TxTemporal,
    table="meter",
    namespace="ops",
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)


class Gauge(Meter, namespace="ops", inheritance=ConcreteSubtype(tag_value="gauge")):
    reading: Attr[int]


class Archive(Entity, table="archive", namespace="ops", persistence=READ_ONLY):
    id: Attr[int] = attr(primary_key=True)


FAMILIES = DomainModel(
    Zone,
    Depot,
    Ownerless,
    Payment,
    Card,
    Deferred,
    Invoice,
    Voucher,
    Craft,
    Sloop,
    Meter,
    Gauge,
    Archive,
)


class _Name(Protocol):
    @property
    def name(self) -> str: ...


class _Named(Protocol):
    @property
    def identity(self) -> _Name: ...


def _names(members: Sequence[_Named]) -> list[str]:
    return [member.identity.name for member in members]


def _contains_each(outer: Sequence[object], inner: Sequence[object]) -> bool:
    return all(any(candidate is member for candidate in outer) for member in inner)


def test_the_three_key_forms_answer_one_object() -> None:
    by_class = MODELS.entity(Depot)
    assert MODELS.entity("ops.Depot") is by_class
    assert MODELS.entity(EntityIdentity("ops", "Depot")) is by_class


def test_a_bare_spelling_names_only_an_unnamespaced_entity() -> None:
    assert MODELS.entity("Ownerless").identity == EntityIdentity(None, "Ownerless")
    with raises_code(UsageError, "metamodel-entity-not-found"):
        MODELS.entity("Depot")


def test_entities_enumerate_in_canonical_entity_order_as_the_lookup_objects() -> None:
    # Ownerless sorts first on the empty namespace, then `ops.Depot` before
    # `ops.Zone`.
    assert [entity.identity.canonical for entity in MODELS.entities] == [
        "Ownerless",
        "ops.Depot",
        "ops.Zone",
    ]
    for entity in MODELS.entities:
        assert MODELS.entity(entity.identity) is entity


def test_local_member_sequences_preserve_declaration_order() -> None:
    depot = MODELS.entity(Depot)
    assert _names(depot.declared.attributes) == ["id", "code", "zoneId"]
    assert _names(depot.declared.relationships) == ["zone"]
    assert [member.identity.path for member in depot.declared.value_objects] == [("address",)]
    assert _names(depot.indices) == ["depot_pk", "depot_code"]


def test_declared_lookup_is_local_and_never_exposes_a_foreign_member() -> None:
    depot = MODELS.entity(Depot).declared
    assert depot.attribute("code") is depot.attributes[1]
    assert depot.relationship("zone") is depot.relationships[0]
    assert depot.value_object("address") is depot.value_objects[0]
    assert depot.attribute("nope") is None
    assert depot.relationship("depots") is None
    assert depot.value_object("nope") is None


def test_relationships_answer_resolved_paired_directions() -> None:
    zone = MODELS.entity(Zone).declared.relationship("depots")
    depot = MODELS.entity(Depot).declared.relationship("zone")
    assert zone is not None
    assert depot is not None
    assert (depot.cardinality, depot.reverse) == (MANY_TO_ONE, "depots")
    # The reverse direction is resolved through its peer: its cardinality and
    # join are stated from its own side.
    assert (zone.cardinality, zone.reverse) == (ONE_TO_MANY, "zone")
    assert zone.join.target.entity == EntityIdentity("ops", "Depot")


def test_a_standalone_entity_is_its_own_effective_scope() -> None:
    depot = MODELS.entity(Depot)
    assert depot.inheritance is None
    assert depot.parent is None
    assert depot.effective.attributes == depot.declared.attributes
    assert depot.effective.relationships is depot.declared.relationships
    assert depot.effective.value_objects == depot.declared.value_objects
    assert depot.effective.primary_key is depot.declared.primary_key
    assert depot.declared.primary_key is depot.declared.attribute("id")
    assert depot.effective.relationship("zone") is depot.declared.relationship("zone")
    assert depot.declared.container == depot.effective.container == Table("depot")


def test_an_omitted_layout_and_persistence_are_absent_declared_and_defaulted_effective() -> None:
    zone = MODELS.entity(Zone)
    assert (zone.declared.layout, zone.declared.persistence) == (None, None)
    assert zone.effective.layout == Columns()
    assert zone.effective.persistence is READ_WRITE
    archive = FAMILIES.entity(Archive)
    assert archive.declared.persistence is archive.effective.persistence is READ_ONLY


def test_reading_back_answers_the_classes_the_author_wrote() -> None:
    payment = FAMILIES.entity(Payment)
    assert payment.inheritance == AbstractRoot(TablePerHierarchy(tag_column="kind"))
    assert payment.declared.layout == payment.effective.layout == Document(column="body")
    card = FAMILIES.entity(Card)
    assert type(card.inheritance) is ConcreteSubtype
    assert card.inheritance == ConcreteSubtype(tag_value="card")
    assert card.parent == payment.identity
    deferred = FAMILIES.entity(Deferred)
    assert deferred.inheritance == AbstractSubtype()
    assert deferred.inheritance is FAMILIES.entity(Voucher).inheritance
    assert FAMILIES.entity(Invoice).parent == deferred.identity
    assert FAMILIES.entity(Sloop).inheritance == ConcreteSubtype()


class Ledger(Entity, table="ledger", namespace="ops", layout=Columns()):
    id: Attr[int] = attr(primary_key=True)
    total: Attr[Decimal] = attr(precision=12, scale=2)
    entries: Attr[int] = attr(type=Int32)


def test_written_column_types_layout_and_key_generation_read_back_as_the_root_classes() -> None:
    ledger = DomainModel(Ledger).entity(Ledger)
    total = ledger.declared.attribute("total")
    entries = ledger.declared.attribute("entries")
    assert total is not None and entries is not None
    assert total.type == Numeric(precision=12, scale=2)
    assert type(entries.type) is Int32
    assert ledger.declared.layout is None
    assert ledger.effective.layout == Columns()
    key = ledger.effective.primary_key
    assert key is not None and isinstance(key.primary_key, PrimaryKey)
    assert isinstance(key.primary_key.generation, ApplicationAssigned)


def test_a_subtype_declares_none_of_the_root_owned_facts() -> None:
    card = FAMILIES.entity(Card)
    payment = FAMILIES.entity(Payment)
    declared = card.declared
    assert (declared.container, declared.persistence, declared.layout) == (None, None, None)
    assert declared.primary_key is None
    assert card.effective.container == payment.declared.container == Table("payment")
    assert card.effective.layout is payment.effective.layout
    assert card.effective.persistence is READ_WRITE
    assert card.effective.primary_key is payment.declared.primary_key
    assert card.indices == ()


def test_effective_members_run_root_first_and_contain_each_declared_member() -> None:
    invoice = FAMILIES.entity(Invoice)
    assert _names(invoice.effective.attributes) == ["id", "amount", "zoneId", "due", "reference"]
    for position in (Payment, Deferred, Invoice):
        declared = FAMILIES.entity(position).declared
        assert _contains_each(invoice.effective.attributes, declared.attributes)
    assert invoice.effective.attribute("due") is FAMILIES.entity(Deferred).declared.attribute("due")
    assert invoice.declared.attribute("due") is None


def test_effective_relationships_follow_the_ancestry_without_sibling_leakage() -> None:
    card = FAMILIES.entity(Card)
    zone = FAMILIES.entity(Payment).declared.relationship("zone")
    assert _names(card.declared.relationships) == ["depot"]
    assert _names(card.effective.relationships) == ["zone", "depot"]
    assert card.effective.relationship("zone") is zone
    assert card.declared.relationship("zone") is None
    assert card.effective.relationship("depot") is card.declared.relationship("depot")
    invoice = FAMILIES.entity(Invoice)
    assert _names(invoice.effective.relationships) == ["zone"]
    assert invoice.effective.relationship("depot") is None


def test_a_dormant_branch_and_an_abstract_root_still_resolve_their_scopes() -> None:
    voucher = FAMILIES.entity(Voucher)
    assert _names(voucher.effective.attributes) == ["id", "amount", "zoneId", "code"]
    assert voucher.effective.container == Table("payment")
    craft = FAMILIES.entity(Craft)
    sloop = FAMILIES.entity(Sloop)
    # Table per concrete subtype: each concrete position owns its container and
    # the abstract root owns none.
    assert craft.effective.container is None
    assert sloop.declared.container == sloop.effective.container == Table("sloop")
    assert sloop.effective.primary_key is craft.declared.primary_key


def test_effective_axes_are_the_root_owned_axes() -> None:
    meter = FAMILIES.entity(Meter)
    gauge = FAMILIES.entity(Gauge)
    (axis,) = meter.declared.as_of_axes
    assert axis.dimension is TemporalDimension.TRANSACTION_TIME
    assert gauge.declared.as_of_axes == ()
    assert gauge.declared.as_of_axis(TemporalDimension.TRANSACTION_TIME) is None
    (effective,) = gauge.effective.as_of_axes
    assert effective is axis
    assert gauge.effective.as_of_axis(TemporalDimension.TRANSACTION_TIME) is axis
    assert gauge.effective.as_of_axis(TemporalDimension.VALID_TIME) is None
    assert tuple(meter.effective.as_of_axes) == (axis,)
    assert FAMILIES.entity(Archive).effective.as_of_axes == ()


def test_resolved_metadata_is_read_only() -> None:
    depot = MODELS.entity(Depot)
    for collection in (
        depot.indices,
        depot.declared.attributes,
        depot.declared.relationships,
        depot.effective.attributes,
        depot.effective.value_objects,
        MODELS.entities,
    ):
        assert not isinstance(collection, MutableSequence)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(depot, "parent", None)  # noqa: B010 - the refusal under test
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(depot.effective, "layout", None)  # noqa: B010 - the refusal under test


@pytest.mark.parametrize("spelling", ["", ".", ".Depot", "Depot.", "ops."])
def test_a_malformed_spelling_is_an_invalid_entity_reference(spelling: str) -> None:
    with raises_code(UsageError, "metamodel-invalid-entity-reference"):
        MODELS.entity(spelling)


def test_an_absent_identity_is_not_found() -> None:
    with raises_code(UsageError, "metamodel-entity-not-found"):
        MODELS.entity(EntityIdentity("ops", "Missing"))


def test_the_lookup_code_set_is_closed() -> None:
    assert frozenset(get_args(MetamodelLookupCode.__value__)) == _SPEC_CODES
