"""Entity frontend (definition half): descriptor export, introspection, rejections."""

from __future__ import annotations

from decimal import Decimal
from typing import cast

import pytest

import frontend_probes
import mirrored_models as mm
from parallax.conformance import case_format
from parallax.core import (
    Attr,
    Entity,
    EntityConfig,
    EntityDefinitionError,
    Field,
    NameCollisionError,
    Rel,
    Relationship,
    ReservedNameError,
    meta,
)
from parallax.core.descriptor import canonicalize
from parallax.core.entity import (
    AttributeRef,
    RelationshipRef,
    camel_to_snake,
    descriptor_document,
    metamodel,
    snake_to_camel,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("stem, classes", mm.MIRRORED, ids=[stem for stem, _ in mm.MIRRORED])
def test_mirrored_class_export_matches_the_corpus_logical_model(
    stem: str, classes: list[type]
) -> None:
    corpus = mm.drop_indices(canonicalize(_raw_model(stem)))
    assert descriptor_document(classes) == corpus


def _raw_model(stem: str) -> dict[str, object]:
    import yaml

    path = case_format.find_repo_root() / "core" / "compatibility" / "models" / f"{stem}.yaml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return cast("dict[str, object]", loaded)


@pytest.mark.parametrize(
    ("snake", "camel"),
    [("id", "id"), ("order_id", "orderId"), ("person_id", "personId"), ("a_b_c", "aBC")],
)
def test_snake_to_camel_conversion(snake: str, camel: str) -> None:
    assert snake_to_camel(snake) == camel


@pytest.mark.parametrize(
    ("entity_name", "table"),
    [("Account", "account"), ("OrderItem", "order_item"), ("PkSequence", "pk_sequence")],
)
def test_camel_to_snake_default_table(entity_name: str, table: str) -> None:
    assert camel_to_snake(entity_name) == table


def test_meta_view_exposes_the_canonical_metamodel() -> None:
    view = meta(mm.Account)
    assert view.name == "Account"
    assert view.table == "account"
    assert view.namespace == "parallax.compatibility"
    assert view.temporal == "non-temporal"
    assert tuple(a.name for a in view.attributes) == ("id", "owner", "balance", "version")
    assert tuple(a.name for a in view.primary_key) == ("id",)
    assert view.relationships == ()
    assert view.value_objects == ()
    assert view.as_of == ()
    assert view.family is None
    assert view.descriptor() == descriptor_document([mm.Account])


def test_meta_by_name_and_relationship_view() -> None:
    view = meta("Person")
    assert view.name == "Person"
    assert tuple(r.name for r in view.relationships) == ("passport",)
    passport = view.relationships[0]
    assert passport.related_entity == "Passport"
    assert passport.dependent is True
    assert passport.reverse_name == "holder"


def test_meta_rejects_unknown_name_and_non_entity() -> None:
    with pytest.raises(KeyError):
        meta("NoSuchEntity")
    with pytest.raises(TypeError):
        meta(int)


def test_metamodel_assembles_related_classes() -> None:
    assembled = metamodel([mm.Person, mm.Passport])
    assert tuple(e.name for e in assembled.entities) == ("Person", "Passport")


def test_attribute_descriptor_get_on_class_and_instance() -> None:
    account = mm.Account(id=1, owner="alice", balance=Decimal("9.99"), version=1)
    descriptor = mm.Account.__dict__["owner"]
    assert descriptor.__get__(None, mm.Account) == AttributeRef("Account", "owner")
    assert descriptor.__get__(account, mm.Account) == "alice"
    # Normal instance access returns the stored value (non-data descriptor).
    assert account.owner == "alice"


def test_relationship_descriptor_get_on_class_and_instance() -> None:
    descriptor = mm.Passport.__dict__["holder"]
    assert descriptor.__get__(None, mm.Passport) == RelationshipRef("Passport", "holder")
    person = mm.Person(id=2, name="p")
    carrier = _Carrier()
    carrier.holder = person  # a materialized peer lives in the instance __dict__
    assert descriptor.__get__(carrier, mm.Passport) is person


class _Carrier:
    """A plain object whose ``__dict__`` stands in for a materialized instance."""

    holder: object


def test_attribute_ref_str_and_relationship_ref_str() -> None:
    assert str(AttributeRef("Account", "owner")) == "Account.owner"
    assert str(RelationshipRef("Person", "passport")) == "Person.passport"


class WithStringRel(Entity, frozen=True):
    """A relationship declared under ``from __future__ import annotations`` (a string)."""

    __parallax__ = EntityConfig(table="with_string_rel", mutability="transactional")

    id: Attr[int] = Field(primary_key=True, type="int64")
    peer: Rel[object] = Relationship(cardinality="many-to-one", join="x", related_entity="Peer")


def test_string_annotation_relationship_is_unwrapped() -> None:
    view = meta(WithStringRel)
    assert view.relationships[0].related_entity == "Peer"


def _define_string_plain_field() -> type:
    class Bad(Entity, frozen=True):
        __parallax__ = EntityConfig(table="bad", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, type="int64")
        qty: int = 5

    return Bad


def test_string_plain_annotation_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError, match="Attr"):
        _define_string_plain_field()


def test_field_default_becomes_the_instance_default() -> None:
    class Toggle(Entity, frozen=True):
        __parallax__ = EntityConfig(table="toggle", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, type="int64")
        active: Attr[bool] = Field(type="boolean", default=True)

    assert Toggle(id=1).active is True


def test_reserved_field_name_is_rejected() -> None:
    with pytest.raises(ReservedNameError):
        frontend_probes.define_reserved_name()


def test_canonical_name_collision_is_rejected() -> None:
    with pytest.raises(NameCollisionError):
        frontend_probes.define_name_collision()


def test_non_attr_field_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError, match="Attr"):
        frontend_probes.define_non_attr_field()


def test_entity_without_attributes_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError, match="no attributes"):
        frontend_probes.define_no_attributes()


def test_relationship_without_a_relationship_spec_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError, match="Relationship"):
        frontend_probes.define_relationship_without_spec()


def test_bad_parallax_config_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError, match="EntityConfig"):
        frontend_probes.define_bad_config()


def test_bad_mutability_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError, match="mutability"):
        frontend_probes.define_bad_mutability()


def test_decimal_without_precision_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError, match="decimal"):
        frontend_probes.define_decimal_without_type()


def test_unmapped_python_type_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError, match="neutral type"):
        frontend_probes.define_unmapped_attribute()
