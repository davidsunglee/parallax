"""m-metamodel: the Metadata Compiler and the sole accepted metadata graph."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Mapping, MutableMapping
from typing import Any, cast

import pytest
from _metamodel_support import Declaration, accepted, attribute, identity, instant, key, source

from parallax.core import base
from parallax.core.metamodel import (
    METADATA_COMPILER,
    METAMODEL_MODULE,
    AbstractRoot,
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeReference,
    Cardinality,
    Column,
    ConcreteSubtype,
    EntityIdentity,
    FacetKey,
    IndexIdentity,
    IndexMetadata,
    Multiplicity,
    NestedValueObjectOccurrenceDeclaration,
    PersistenceMode,
    RelationshipIdentity,
    RelativeEntityReference,
    Table,
    TablePerHierarchy,
    TemporalDimension,
    UnresolvedDefiningRelationshipDeclaration,
    UnresolvedRelationshipJoin,
    ValueObjectAttributeDeclaration,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
    accept_metamodel,
    compile_metadata,
)

pytestmark = pytest.mark.unit

_ORDER = identity("Order")
_ITEM = identity("Item")

_GEO = ValueObjectShapeDeclaration(
    ValueObjectShapeKey(),
    attributes=(
        ValueObjectAttributeDeclaration("lat", base.Decimal(9, 6)),
        ValueObjectAttributeDeclaration("lon", base.Decimal(9, 6), nullable=True),
    ),
)
_ADDRESS = ValueObjectShapeDeclaration(
    ValueObjectShapeKey(),
    attributes=(ValueObjectAttributeDeclaration("city", base.STRING),),
    value_objects=(NestedValueObjectOccurrenceDeclaration("geo", _GEO),),
)


def _model() -> Declaration:
    return Declaration(
        identity=_ORDER,
        container=Table("orders"),
        persistence=PersistenceMode.READ_ONLY,
        attributes=(
            key(_ORDER),
            attribute(_ORDER, "sku", type=base.STRING),
            instant(_ORDER, "tx_start"),
            instant(_ORDER, "tx_end"),
        ),
        relationships=(
            UnresolvedDefiningRelationshipDeclaration(
                identity=RelationshipIdentity(_ORDER, "items"),
                cardinality=Cardinality.ONE_TO_MANY,
                join=UnresolvedRelationshipJoin(
                    source=AttributeIdentity(_ORDER, "id"),
                    target=AttributeReference(RelativeEntityReference("Item"), "orderId"),
                ),
            ),
        ),
        value_objects=(
            ValueObjectOccurrenceDeclaration(
                "shipTo", Column("ship_to"), _ADDRESS, multiplicity=Multiplicity.MANY
            ),
            ValueObjectOccurrenceDeclaration("billTo", Column("bill_to"), _ADDRESS, nullable=True),
        ),
        as_of_axes=(
            AsOfAxisMetadata(
                TemporalDimension.TRANSACTION_TIME,
                AttributeIdentity(_ORDER, "tx_start"),
                AttributeIdentity(_ORDER, "tx_end"),
            ),
        ),
        indices=(
            IndexMetadata(
                IndexIdentity(_ORDER, "orders_pk"), (AttributeIdentity(_ORDER, "id"),), unique=True
            ),
        ),
    )


def _peer() -> Declaration:
    return Declaration(
        identity=_ITEM,
        container=Table("item"),
        attributes=(key(_ITEM), attribute(_ITEM, "orderId", column="order_id")),
        inheritance=AbstractRoot(TablePerHierarchy("kind")),
    )


def test_the_compiler_declares_its_manifest_owner() -> None:
    assert METADATA_COMPILER.owner == METAMODEL_MODULE


def test_compiled_entities_keep_canonical_order_and_total_lookup() -> None:
    metadata = METADATA_COMPILER.compile(accepted(source(_model(), _peer())))
    assert [entity.identity for entity in metadata.entities] == [_ITEM, _ORDER]
    assert metadata.entity(_ORDER) is not None
    assert metadata.entity(EntityIdentity("parallax.test", "Absent")) is None


def test_entity_metadata_exposes_only_declared_local_facts() -> None:
    metadata = compile_metadata(accepted(source(_model(), _peer())))
    order = metadata.entity(_ORDER)
    item = metadata.entity(_ITEM)
    assert order is not None and item is not None
    assert order.declared_container == Table("orders")
    assert order.declared_persistence is PersistenceMode.READ_ONLY
    assert item.declared_persistence is None
    assert order.inheritance is None
    assert item.inheritance == AbstractRoot(TablePerHierarchy("kind"))
    assert [member.identity.name for member in order.declared_attributes] == [
        "id",
        "sku",
        "tx_start",
        "tx_end",
    ]
    assert [member.identity.name for member in order.declared_relationships] == ["items"]
    assert [axis.dimension for axis in order.declared_as_of_axes] == [
        TemporalDimension.TRANSACTION_TIME
    ]
    assert [member.identity.name for member in order.indices] == ["orders_pk"]


def test_local_member_lookup_returns_absence_on_a_miss() -> None:
    metadata = compile_metadata(accepted(source(_model(), _peer())))
    order = metadata.entity(_ORDER)
    assert order is not None
    assert order.attribute("sku") is not None
    assert order.attribute("absent") is None
    assert order.relationship("items") is not None
    assert order.relationship("absent") is None
    assert order.value_object("shipTo") is not None
    assert order.value_object("absent") is None
    assert order.as_of_axis(TemporalDimension.TRANSACTION_TIME) is not None
    assert order.as_of_axis(TemporalDimension.VALID_TIME) is None
    assert order.index("orders_pk") is not None
    assert order.index("absent") is None


def test_lookup_never_exposes_an_inherited_member() -> None:
    subtype = identity("Dog")
    root = Declaration(
        identity=_ORDER,
        container=Table("orders"),
        attributes=(key(_ORDER),),
        inheritance=AbstractRoot(TablePerHierarchy("kind")),
    )
    leaf = Declaration(
        identity=subtype,
        attributes=(attribute(subtype, "barkVolume"),),
        inheritance=ConcreteSubtype(RelativeEntityReference("Order"), "dog"),
    )
    metadata = compile_metadata(accepted(source(root, leaf)))
    dog = metadata.entity(subtype)
    assert dog is not None
    assert dog.attribute("barkVolume") is not None
    assert dog.attribute("id") is None


def test_value_object_occurrences_expand_into_path_identities() -> None:
    metadata = compile_metadata(accepted(source(_model(), _peer())))
    order = metadata.entity(_ORDER)
    assert order is not None
    ship_to = order.value_object("shipTo")
    bill_to = order.value_object("billTo")
    assert ship_to is not None and bill_to is not None
    assert ship_to.identity == ValueObjectIdentity(_ORDER, ("shipTo",))
    assert ship_to.storage == Column("ship_to")
    assert ship_to.multiplicity is Multiplicity.MANY
    assert bill_to.nullable is True
    assert bill_to.identity == ValueObjectIdentity(_ORDER, ("billTo",))
    assert ship_to.attribute("city") is not None
    assert ship_to.attribute("absent") is None

    nested = ship_to.value_object("geo")
    assert nested is not None
    assert nested.identity == ValueObjectIdentity(_ORDER, ("shipTo", "geo"))
    assert nested.multiplicity is Multiplicity.ONE
    assert nested.nullable is False
    assert nested.value_object("absent") is None

    leaf = nested.attribute("lon")
    assert leaf is not None
    assert leaf.identity == ValueObjectAttributeIdentity(nested.identity, "lon")
    assert leaf.type == base.Decimal(9, 6)
    assert leaf.nullable is True
    assert nested.attribute("absent") is None


def test_one_reused_shape_expands_to_distinct_occurrence_trees() -> None:
    metadata = compile_metadata(accepted(source(_model(), _peer())))
    order = metadata.entity(_ORDER)
    assert order is not None
    ship_to = order.value_object("shipTo")
    bill_to = order.value_object("billTo")
    assert ship_to is not None and bill_to is not None
    ship_geo = ship_to.value_object("geo")
    bill_geo = bill_to.value_object("geo")
    assert ship_geo is not None and bill_geo is not None
    assert ship_geo.identity != bill_geo.identity
    assert [member.identity.name for member in ship_geo.attributes] == ["lat", "lon"]
    assert not hasattr(ship_geo, "storage")


def test_compilation_discards_every_shape_key() -> None:
    metadata = compile_metadata(accepted(source(_model(), _peer())))
    order = metadata.entity(_ORDER)
    assert order is not None
    ship_to = order.value_object("shipTo")
    assert ship_to is not None
    assert not hasattr(ship_to, "key")
    assert not hasattr(ship_to, "shape")


def test_relationship_declarations_survive_compilation_without_pairing() -> None:
    metadata = compile_metadata(accepted(source(_model(), _peer())))
    order = metadata.entity(_ORDER)
    item = metadata.entity(_ITEM)
    assert order is not None and item is not None
    declared = order.declared_relationships[0]
    assert not hasattr(declared, "reverse")
    assert item.declared_relationships == ()


def test_a_shape_graph_that_re_enters_one_key_is_a_compiler_contract_failure() -> None:
    shared = ValueObjectShapeKey()
    inner = ValueObjectShapeDeclaration(
        shared, attributes=(ValueObjectAttributeDeclaration("city", base.STRING),)
    )
    outer = ValueObjectShapeDeclaration(
        shared, value_objects=(NestedValueObjectOccurrenceDeclaration("inner", inner),)
    )
    declaration = Declaration(
        identity=_ORDER,
        attributes=(key(_ORDER),),
        value_objects=(ValueObjectOccurrenceDeclaration("address", Column("address"), outer),),
    )
    candidate = accepted(source(declaration))
    with pytest.raises(RuntimeError, match="containment cycle"):
        compile_metadata(candidate)


def test_an_accepted_metamodel_delegates_lookup_and_serves_typed_facets() -> None:
    metadata = compile_metadata(accepted(source(_model(), _peer())))
    facet_key: FacetKey[str] = FacetKey("m-test")
    model = accept_metamodel(metadata, {facet_key: "compiled"})
    assert model.entities is metadata.entities
    assert model.entity(_ORDER) is metadata.entity(_ORDER)
    assert model.entity(EntityIdentity("parallax.test", "Absent")) is None
    assert model.facet(facet_key) == "compiled"


def _mappings_within(value: object, seen: set[int]) -> Iterator[Mapping[object, object]]:
    """Every Mapping reachable from ``value`` through dataclass fields and tuples."""
    if id(value) in seen:
        return
    seen.add(id(value))
    if isinstance(value, Mapping):
        # An index's values are the same objects its owner's sequences hold, so
        # the walk stops here rather than descending twice.
        yield cast("Mapping[object, object]", value)
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        for member in dataclasses.fields(value):
            yield from _mappings_within(getattr(value, member.name), seen)
    elif isinstance(value, tuple):
        for item in cast("tuple[object, ...]", value):
            yield from _mappings_within(item, seen)


def test_every_index_backing_candidate_or_accepted_lookup_is_read_only() -> None:
    candidate = accepted(source(_model(), _peer()))
    for graph in (candidate, compile_metadata(candidate)):
        indexes = list(_mappings_within(graph, set()))
        assert indexes
        assert not [index for index in indexes if isinstance(index, MutableMapping)]


def test_an_accepted_metamodel_snapshots_the_facet_mapping_it_was_given() -> None:
    metadata = compile_metadata(accepted(source(_model(), _peer())))
    facet_key: FacetKey[str] = FacetKey("m-test")
    smuggled: FacetKey[str] = FacetKey("m-smuggled")
    supplied: dict[FacetKey[Any], object] = {facet_key: "compiled"}
    model = accept_metamodel(metadata, supplied)
    supplied[facet_key] = "replaced"
    supplied[smuggled] = "added"
    assert model.facet(facet_key) == "compiled"
    with pytest.raises(KeyError):
        model.facet(smuggled)


def test_a_facet_key_is_identified_by_its_owning_module() -> None:
    assert FacetKey("m-relationship") == FacetKey("m-relationship")
    assert FacetKey("m-relationship") != FacetKey("m-inheritance")
    assert FacetKey("m-relationship").owner == "m-relationship"
