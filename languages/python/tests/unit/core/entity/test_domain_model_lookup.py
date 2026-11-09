"""``models.meta(...)`` and ``models.entities``: model-relative, read-only lookup.

The three key forms answer one object, enumeration is canonical Entity order,
local member sequences keep declaration order, and every miss carries a code.
Classes are declared at module scope because nothing here needs a per-test
declaration: one composition answers every lookup this suite asks.
"""

from __future__ import annotations

from typing import get_args

import pytest

from parallax.core import (
    MANY_TO_ONE,
    Attr,
    DomainModel,
    Entity,
    Rel,
    UsageError,
    ValueObject,
    attr,
    index,
    rel,
)
from parallax.core.entity._errors import MetamodelLookupCode
from parallax.core.metamodel import EntityIdentity
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


def test_the_three_key_forms_answer_one_object() -> None:
    by_class = MODELS.meta(Depot)
    assert MODELS.meta("ops.Depot") is by_class
    assert MODELS.meta(EntityIdentity("ops", "Depot")) is by_class


def test_a_bare_spelling_names_only_an_unnamespaced_entity() -> None:
    assert MODELS.meta("Ownerless").identity == EntityIdentity(None, "Ownerless")
    with raises_code(UsageError, "metamodel-entity-not-found"):
        MODELS.meta("Depot")


def test_entities_enumerate_in_canonical_entity_order() -> None:
    # Ownerless sorts first on the empty namespace, then `ops.Depot` before
    # `ops.Zone`.
    assert [entity.identity.canonical for entity in MODELS.entities] == [
        "Ownerless",
        "ops.Depot",
        "ops.Zone",
    ]


def test_local_member_sequences_preserve_declaration_order() -> None:
    depot = MODELS.meta(Depot)
    assert [member.identity.name for member in depot.declared_attributes] == [
        "id",
        "code",
        "zoneId",
    ]
    assert [member.identity.name for member in depot.declared_relationships] == ["zone"]
    assert [member.identity.path for member in depot.declared_value_objects] == [("address",)]
    assert [member.identity.name for member in depot.indices] == ["depot_pk", "depot_code"]


def test_lookup_is_local_and_never_exposes_an_inherited_or_foreign_member() -> None:
    depot = MODELS.meta(Depot)
    assert depot.attribute("code") is not None
    assert depot.relationship("zone") is not None
    assert depot.attribute("nope") is None
    assert depot.relationship("depots") is None


@pytest.mark.parametrize("spelling", ["", ".", ".Depot", "Depot.", "ops."])
def test_a_malformed_spelling_is_an_invalid_entity_reference(spelling: str) -> None:
    with raises_code(UsageError, "metamodel-invalid-entity-reference"):
        MODELS.meta(spelling)


def test_an_absent_identity_is_not_found() -> None:
    with raises_code(UsageError, "metamodel-entity-not-found"):
        MODELS.meta(EntityIdentity("ops", "Missing"))


def test_the_lookup_code_set_is_closed() -> None:
    assert frozenset(get_args(MetamodelLookupCode.__value__)) == _SPEC_CODES
