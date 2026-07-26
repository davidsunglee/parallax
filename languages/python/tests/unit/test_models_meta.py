"""``models.meta(...)`` and ``models.entities``: model-relative, read-only lookup.

The three key forms answer one object, enumeration is canonical Entity order,
local member sequences keep declaration order, and every miss carries a code.
Classes are declared at module scope here because this suite composes exactly one
hub and never competes for a claim.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from parallax.core import (
    MANY_TO_ONE,
    Attr,
    Entity,
    MetamodelHub,
    MetamodelLookupError,
    Rel,
    ValueObject,
    attr,
    index,
    rel,
)
from parallax.core.entity import METAMODEL_LOOKUP_CODES
from parallax.core.entity._hub import MetamodelHub as _Hub
from parallax.core.metamodel import EntityIdentity, UnresolvedEntityDeclaration

pytestmark = pytest.mark.unit

_SPEC_CODES = frozenset(
    {
        "metamodel-invalid-entity-reference",
        "metamodel-entity-not-found",
        "metamodel-class-not-bound",
    }
)


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


MODELS = MetamodelHub(Depot, Zone, Ownerless)


def test_the_three_key_forms_answer_one_object() -> None:
    by_class = MODELS.meta(Depot)
    assert MODELS.meta("ops.Depot") is by_class
    assert MODELS.meta(EntityIdentity("ops", "Depot")) is by_class


def test_a_bare_spelling_names_only_an_unnamespaced_entity() -> None:
    assert MODELS.meta("Ownerless").identity == EntityIdentity(None, "Ownerless")
    with pytest.raises(MetamodelLookupError) as caught:
        MODELS.meta("Depot")
    assert caught.value.code == "metamodel-entity-not-found"


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
    assert [member.identity.name for member in depot.indices] == ["depot_code"]


def test_lookup_is_local_and_never_exposes_an_inherited_or_foreign_member() -> None:
    depot = MODELS.meta(Depot)
    assert depot.attribute("code") is not None
    assert depot.relationship("zone") is not None
    assert depot.attribute("nope") is None
    assert depot.relationship("depots") is None


@pytest.mark.parametrize("spelling", ["", ".", ".Depot", "Depot.", "ops."])
def test_a_malformed_spelling_is_an_invalid_entity_reference(spelling: str) -> None:
    with pytest.raises(MetamodelLookupError) as caught:
        MODELS.meta(spelling)
    assert caught.value.code == "metamodel-invalid-entity-reference"


def test_an_absent_identity_is_not_found() -> None:
    with pytest.raises(MetamodelLookupError) as caught:
        MODELS.meta(EntityIdentity("ops", "Missing"))
    assert caught.value.code == "metamodel-entity-not-found"


def test_a_class_this_hub_did_not_claim_is_not_bound() -> None:
    class Foreign(Entity, table="foreign"):
        id: Attr[int] = attr(primary_key=True)

    with pytest.raises(MetamodelLookupError) as caught:
        MODELS.meta(Foreign)
    assert caught.value.code == "metamodel-class-not-bound"


def test_a_descriptor_backed_hub_serves_the_same_metadata_and_claims_no_class() -> None:
    fixed = _Hub._from_unresolved(_Source())  # pyright: ignore[reportPrivateUsage] - unit test drives the hub's private constructor
    assert [entity.identity.canonical for entity in fixed.entities] == ["ops.Depot", "ops.Zone"]
    assert fixed.meta("ops.Depot").identity == EntityIdentity("ops", "Depot")
    with pytest.raises(MetamodelLookupError) as caught:
        fixed.meta(Depot)
    assert caught.value.code == "metamodel-class-not-bound"


def test_the_lookup_code_set_is_closed() -> None:
    assert METAMODEL_LOOKUP_CODES == _SPEC_CODES
    with pytest.raises(ValueError, match="not a metamodel lookup code"):
        MetamodelLookupError(code="metamodel-empty", message="wrong family")


class _Source:
    """A minimal Unresolved Metamodel standing in for the Descriptor Frontend.

    It reuses the two Entity Classes as declarations, which is exactly what the
    seam accepts: a nonempty sequence of ``UnresolvedEntityDeclaration`` views
    with no Python binding input.
    """

    @property
    def entities(self) -> Sequence[UnresolvedEntityDeclaration]:
        return (Depot, Zone)
