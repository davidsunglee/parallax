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
    Concrete,
    Entity,
    EntityConfig,
    EntityDefinitionError,
    EntityRegistry,
    FamilyRoot,
    Field,
    NameCollisionError,
    Rel,
    Relationship,
    ReservedNameError,
    meta,
)
from parallax.core.descriptor import (
    AsOfAttribute as AsOfAttributeRecord,
)
from parallax.core.descriptor import (
    Attribute as AttributeRecord,
)
from parallax.core.descriptor import (
    Entity as EntityRecord,
)
from parallax.core.descriptor import (
    Inheritance,
    Metamodel,
    canonicalize,
    deserialize,
)
from parallax.core.entity import (
    AttributeRef,
    RelationshipRef,
    ScopedMetamodel,
    camel_to_snake,
    descriptor_document,
    meta_of,
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
    path = case_format.find_repo_root() / "core" / "compatibility" / "models" / f"{stem}.yaml"
    loaded = case_format.safe_load_yaml(path.read_text(encoding="utf-8"))
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
    assert isinstance(assembled, ScopedMetamodel)
    assert assembled.registry is not None


def test_metamodel_of_no_classes_stays_unscoped() -> None:
    # S2 (COR-3 Phase 7 increment 7 round-2): no class/registry context at all
    # -- the one documented case the untagged, UNSCOPED shape legitimately
    # survives in (never a silent guess at a scope with nothing to derive it
    # from).
    assembled = metamodel([])
    assert not isinstance(assembled, ScopedMetamodel)
    assert assembled.entities == ()


def test_metamodel_rejects_a_non_entity_class() -> None:
    # R3 (COR-3 Phase 7 increment 7 round-2): `metamodel(classes)`'s own
    # entity-lookup (relocated into `entity/base.py` alongside the
    # now-private registry machinery it needs) raises the SAME shape
    # `meta(int)` raises for a non-entity class, whether or not a caller
    # ever validates the class through `meta()` first.
    with pytest.raises(TypeError, match="is not a Parallax entity class"):
        metamodel([int])


def test_attribute_descriptor_get_on_class_and_instance() -> None:
    account = mm.Account(id=1, owner="alice", balance=Decimal("9.99"), version=1)
    descriptor = mm.Account.__dict__["owner"]
    # Class access yields the expression object (the seed of a predicate); its
    # underlying reference identifies the attribute.
    assert descriptor.__get__(None, mm.Account).ref == AttributeRef("Account", "owner")
    assert descriptor.__get__(account, mm.Account) == "alice"
    # Normal instance access returns the stored value (non-data descriptor).
    assert account.owner == "alice"


def test_relationship_descriptor_get_on_class_and_instance() -> None:
    descriptor = mm.Passport.__dict__["holder"]
    # Class access yields a RelationshipPath (the include/any/none seed); its
    # `.ref` mirrors AttributeExpr's own class-access identity, and `.target`
    # is the declared relationship's own related entity.
    path = descriptor.__get__(None, mm.Passport)
    assert path.ref == RelationshipRef("Passport", "holder")
    assert path.target == "Person"
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


class FutureInferred(Entity, frozen=True):
    """Neutral-type inference under ``from __future__ import annotations`` (no ``type=``).

    This module stringizes annotations, so ``Attr[int]`` reaches the metaclass as
    the string ``"Attr[int]"``; inference must still resolve the inner type.
    """

    __parallax__ = EntityConfig(table="future_inferred", mutability="transactional")

    id: Attr[int] = Field(primary_key=True)
    name: Attr[str]
    active: Attr[bool] = Field(default=False)
    amount: Attr[Decimal] = Field(type="decimal(9,2)")


def test_future_annotations_infer_neutral_types_without_explicit_type() -> None:
    by_name = {attr.name: attr for attr in meta(FutureInferred).attributes}
    assert by_name["id"].type == "int64"
    assert by_name["name"].type == "string"
    assert by_name["active"].type == "boolean"
    assert by_name["amount"].type == "decimal(9,2)"


def test_future_annotation_explicit_type_survives_unresolvable_inner() -> None:
    # A name visible only in function scope is absent from the module globals the
    # resolver evaluates against, so the inner type stays a string; an explicit
    # `type=` means inference is never consulted and the class still compiles —
    # the fallback path that keeps forward references from breaking definitions.
    class LocalOnly:
        pass

    class WidgetWithUnresolvedInner(Entity, frozen=True):
        __parallax__ = EntityConfig(table="widget", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, type="int64")
        payload: Attr[LocalOnly] = Field(type="int64")

    assert {attr.name for attr in meta(WidgetWithUnresolvedInner).attributes} == {"id", "payload"}


def _define_invalid_neutral_type() -> type:
    class Bad(Entity, frozen=True):
        __parallax__ = EntityConfig(table="bad", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, type="widget")

    return Bad


def test_invalid_neutral_type_is_rejected_at_definition() -> None:
    with pytest.raises(EntityDefinitionError, match="not a neutral type"):
        _define_invalid_neutral_type()


def _define_out_of_range_max_length() -> type:
    class Bad(Entity, frozen=True):
        __parallax__ = EntityConfig(table="bad", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, type="int64")
        label: Attr[str] = Field(type="string", max_length=0)

    return Bad


def test_out_of_range_max_length_is_rejected_at_definition() -> None:
    with pytest.raises(EntityDefinitionError, match="maxLength"):
        _define_out_of_range_max_length()


def _define_wrong_typed_pk_generator() -> type:
    class Bad(Entity, frozen=True):
        __parallax__ = EntityConfig(table="bad", mutability="transactional")

        id: Attr[int] = Field(
            primary_key=True,
            type="int64",
            pk_generator={"strategy": "sequence", "batchSize": "not-an-int"},
        )

    return Bad


def test_wrong_typed_pk_generator_mapping_is_rejected_at_definition() -> None:
    # The malformed batchSize used to be coerced to None and the class defined
    # successfully, exporting a bare `pkGenerator: sequence`; now it is rejected.
    with pytest.raises(EntityDefinitionError, match="pk generator: `batchSize`"):
        _define_wrong_typed_pk_generator()


def _define_explicit_none_pk_generator() -> type:
    class Bad(Entity, frozen=True):
        __parallax__ = EntityConfig(table="bad", mutability="transactional")

        id: Attr[int] = Field(
            primary_key=True,
            type="int64",
            pk_generator={"strategy": "sequence", "batchSize": None},
        )

    return Bad


def test_explicit_none_pk_generator_field_is_rejected_at_definition() -> None:
    # A present optional key carrying `None` (distinct from an omitted key) is a
    # malformed declaration rejected when the class body is evaluated, naming the
    # offending NoneType — never silently normalized to a bare sequence strategy.
    with pytest.raises(EntityDefinitionError, match=r"`batchSize`.*NoneType"):
        _define_explicit_none_pk_generator()


def _define_omitted_optional_pk_generator() -> type:
    class Seq(Entity, frozen=True):
        __parallax__ = EntityConfig(table="seq_bare", mutability="transactional")

        id: Attr[int] = Field(
            primary_key=True,
            type="int64",
            pk_generator={"strategy": "sequence"},
        )

    return Seq


def test_omitted_optional_pk_generator_field_defines_and_exports() -> None:
    # Omitting every optional key (absent != None) is valid and collapses to the
    # bare sequence strategy, confirming the present-None rejection does not leak
    # into the legitimately-partial object form.
    seq = _define_omitted_optional_pk_generator()
    exported = cast("dict[str, object]", meta(seq).descriptor()["entity"])
    attributes = cast("list[dict[str, object]]", exported["attributes"])
    assert attributes[0]["pkGenerator"] == "sequence"


def test_object_form_pk_generator_defines_and_exports() -> None:
    class SeqObjectForm(Entity, frozen=True):
        __parallax__ = EntityConfig(table="seq", mutability="transactional")

        id: Attr[int] = Field(
            primary_key=True,
            type="int64",
            pk_generator={
                "strategy": "sequence",
                "sequenceName": "seq_ids",
                "batchSize": 5,
                "initialValue": 100,
                "incrementSize": 10,
            },
        )

    exported = cast("dict[str, object]", meta(SeqObjectForm).descriptor()["entity"])
    attributes = cast("list[dict[str, object]]", exported["attributes"])
    assert attributes[0]["pkGenerator"] == {
        "strategy": "sequence",
        "sequenceName": "seq_ids",
        "batchSize": 5,
        "initialValue": 100,
        "incrementSize": 10,
    }


def test_meta_of_ingested_descriptor_matches_class_derived_view() -> None:
    ingested = deserialize(_raw_model("account"))
    yaml_view = meta_of(ingested, "Account")
    class_view = meta(mm.Account)
    assert yaml_view.name == class_view.name
    assert yaml_view.table == class_view.table
    assert yaml_view.namespace == class_view.namespace
    assert yaml_view.temporal == class_view.temporal
    assert tuple((a.name, a.type) for a in yaml_view.attributes) == tuple(
        (a.name, a.type) for a in class_view.attributes
    )
    assert tuple(a.name for a in yaml_view.primary_key) == tuple(
        a.name for a in class_view.primary_key
    )
    assert yaml_view.family == class_view.family  # both None (non-inheritance)
    # Same canonical descriptor (physical indices aside — the frontend does not
    # express them), proving the ingested view is the same shape as the class one.
    assert mm.drop_indices(yaml_view.descriptor()) == class_view.descriptor()


def test_meta_of_ingested_descriptor_rejects_unknown_name() -> None:
    with pytest.raises(KeyError):
        meta_of(deserialize(_raw_model("account")), "NoSuchEntity")


def _animal_family() -> Metamodel:
    pk = AttributeRecord(name="id", type="int64", column="id", primary_key=True)
    return Metamodel(
        entities=(
            EntityRecord(
                name="Animal",
                inheritance=Inheritance(
                    role="root", strategy="table-per-hierarchy", tag_column="animal_type"
                ),
            ),
            EntityRecord(
                name="Dog",
                table="animal",
                attributes=(pk,),
                inheritance=Inheritance(role="concrete-subtype", parent="Animal", tag_value="dog"),
            ),
            EntityRecord(
                name="Cat",
                table="animal",
                attributes=(pk,),
                inheritance=Inheritance(role="concrete-subtype", parent="Animal", tag_value="cat"),
            ),
        )
    )


def test_family_view_resolves_root_strategy_and_subtypes_from_ingested_descriptor() -> None:
    family = _animal_family()
    cat = meta_of(family, "Cat").family
    assert cat is not None
    assert cat.role == "concrete-subtype"
    assert cat.root == "Animal"
    assert cat.strategy == "table-per-hierarchy"
    assert cat.tag_column == "animal_type"  # resolved from the root, not the local block
    assert cat.tag_value == "cat"
    assert cat.subtypes == ("Cat",)  # a concrete subtype resolves to itself

    root = meta_of(family, "Animal").family
    assert root is not None
    assert root.root == "Animal"
    assert root.strategy == "table-per-hierarchy"
    # The abstract position resolves to its effective concrete-subtype set.
    assert root.subtypes == ("Cat", "Dog")


def test_family_view_tolerates_unresolved_root() -> None:
    # A malformed ingested family (a parent that names a non-participant, or one
    # absent from the descriptor) resolves to no root rather than raising.
    pk = AttributeRecord(name="id", type="int64", column="id", primary_key=True)
    plain = EntityRecord(name="Plain", table="plain", attributes=(pk,))
    broken = EntityRecord(
        name="Broken",
        table="broken",
        attributes=(pk,),
        inheritance=Inheritance(role="concrete-subtype", parent="Plain", tag_value="b"),
    )
    orphan = EntityRecord(
        name="Orphan",
        table="orphan",
        attributes=(pk,),
        inheritance=Inheritance(role="concrete-subtype", parent="Ghost", tag_value="o"),
    )
    descriptor = Metamodel(entities=(plain, broken, orphan))

    broken_family = meta_of(descriptor, "Broken").family  # parent is a non-participant
    assert broken_family is not None
    assert broken_family.root is None
    assert broken_family.strategy is None
    assert broken_family.tag_column is None

    orphan_family = meta_of(descriptor, "Orphan").family  # parent absent from the descriptor
    assert orphan_family is not None
    assert orphan_family.root is None


def test_meta_of_a_scoped_class_resolves_family_siblings_from_its_own_registry() -> None:
    # S2 (COR-3 Phase 7 increment 7 round-2): `meta(Class)` must derive its
    # sibling/resolution context from THAT class's own registry, never the
    # process default -- pre-fix, `meta`'s context came from `entity_records()`
    # (the process default registry's own records), which never contains a
    # class declared in a SCOPED (non-default) registry at all, so a scoped
    # family's own root resolved to NO concrete subtypes whatsoever.
    registry = EntityRegistry()

    class ScopedFamilyRoot(Entity, frozen=True, registry=registry):
        __parallax__ = EntityConfig(
            table="scoped_family_root",
            mutability="transactional",
            inheritance=FamilyRoot(strategy="table-per-hierarchy", tag="kind"),
        )

        id: Attr[int] = Field(primary_key=True, pk_generator="none")

    class ScopedFamilyLeaf(ScopedFamilyRoot, frozen=True):
        __parallax__ = EntityConfig(
            mutability="transactional", inheritance=Concrete(tag_value="leaf")
        )

    family = meta(ScopedFamilyRoot).family
    assert family is not None
    assert family.subtypes == (ScopedFamilyLeaf.__name__,)


def test_meta_temporal_is_the_family_effective_classification() -> None:
    # ADR 0026 / review remediation (Spec 1, consequence (a)): a temporal-family
    # CONCRETE descendant declares NO `asOfAttributes` of its own (only the
    # root does) — `meta(DepositRate).temporal` must still report the family's
    # EFFECTIVE classification ("bitemporal"), never the entity's own local,
    # non-flattening "non-temporal" (the entity/meta.py bug this proves fixed).
    pk = AttributeRecord(name="id", type="int64", column="id", primary_key=True)
    root = EntityRecord(
        name="Rate",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(pk,),
        as_of_attributes=(
            AsOfAttributeRecord(
                name="businessDate", from_column="from_z", to_column="thru_z", axis="business"
            ),
            AsOfAttributeRecord(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
            ),
        ),
    )
    concrete = EntityRecord(
        name="DepositRate",
        table="deposit_rate",
        attributes=(pk,),
        inheritance=Inheritance(role="concrete-subtype", parent="Rate"),
    )
    family = Metamodel(entities=(root, concrete))

    assert meta_of(family, "DepositRate").temporal == "bitemporal"
    assert meta_of(family, "Rate").temporal == "bitemporal"
    # The LOCAL structural view (`.as_of`) stays empty for the descendant —
    # deliberately NOT flattened (`m-descriptor`'s own documented exception).
    assert meta_of(family, "DepositRate").as_of == ()
    # The EXPORTED descriptor document stays LOCAL too (never the family-
    # effective `.temporal`): it is the structural, round-trippable form
    # (`serialize(deserialize(d)) == d` MUST hold, m-descriptor "Metamodel
    # serde"). Propagating the effective classification into the export would
    # produce an internally-inconsistent document — a `temporal: bitemporal`
    # label with no `asOfAttributes` children — that `deserialize` itself
    # would then reject as disagreeing with the (empty) local axes.
    exported = meta_of(family, "DepositRate").descriptor()["entity"]
    assert "temporal" not in cast("dict[str, object]", exported)


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


def test_entity_config_declares_as_of_dimensions() -> None:
    # The D-7 temporal class spelling: `EntityConfig.as_of` declares the axes in
    # the descriptor's own vocabulary; the effective temporal classification is
    # derived from them exactly as for an ingested descriptor, and the typed
    # statement surface accepts the declared axis.
    import datetime as dt

    from mirrored_models import Balance
    from parallax.core.entity import entity_records

    record = entity_records()["Balance"]
    assert record.temporal == "unitemporal-processing"
    (axis,) = record.as_of_attributes
    assert (axis.name, axis.from_column, axis.to_column) == ("processingDate", "in_z", "out_z")
    pinned = Balance.where().as_of(processing=dt.datetime(2024, 4, 1, tzinfo=dt.UTC))
    assert "asOf" in pinned.serialize()
