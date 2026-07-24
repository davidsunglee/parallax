"""The Entity frontend's native Unresolved Metamodel adaptation error paths.

``native_metamodel`` adapts a compiled record graph into the frontend's own
Unresolved Metamodel view. A record that survives class-definition time but
carries a value the accepted model contract cannot represent surfaces here as a
:class:`DescriptorError`, so a class-authored model that cannot form fails at
assembly rather than silently. These exercise those rejections directly, since a
well-formed class body never reaches them.
"""

from __future__ import annotations

import pytest

from parallax.core.descriptor import records
from parallax.core.descriptor.errors import DescriptorError
from parallax.core.entity._declaration import native_metamodel
from parallax.core.metamodel import (
    EntityIdentity,
    ExactEntityReference,
    UnresolvedDefiningRelationshipDeclaration,
)

pytestmark = pytest.mark.unit


def _one(entity: records.Entity) -> records.Metamodel:
    return records.Metamodel(entities=(entity,))


_ID_PK = records.Attribute(name="id", type="int64", column="id", primary_key=True)


def test_an_empty_assembly_is_rejected() -> None:
    with pytest.raises(DescriptorError, match="no entity"):
        native_metamodel(records.Metamodel(entities=()))


def test_a_model_value_refusal_is_reported_as_a_named_descriptor_error() -> None:
    # An empty namespace is a value the identity type refuses to construct; the
    # raw refusal leaves this seam naming the offending Entity.
    entity = records.Entity(name="Ghost", namespace="", attributes=(_ID_PK,))
    with pytest.raises(DescriptorError, match="Entity namespace"):
        native_metamodel(_one(entity))


def test_an_unrepresentable_type_spelling_is_rejected() -> None:
    entity = records.Entity(
        name="Widget",
        table="widget",
        attributes=(records.Attribute(name="kind", type="gizmo", column="kind"),),
    )
    with pytest.raises(DescriptorError, match="not a neutral type spelling"):
        native_metamodel(_one(entity))


def test_a_table_per_hierarchy_root_without_a_tag_column_is_rejected() -> None:
    entity = records.Entity(
        name="Root",
        table="root",
        attributes=(_ID_PK,),
        inheritance=records.Inheritance(role="root", strategy="table-per-hierarchy"),
    )
    with pytest.raises(DescriptorError, match="tag column"):
        native_metamodel(_one(entity))


def test_an_inheritance_root_without_a_strategy_is_rejected() -> None:
    entity = records.Entity(
        name="Root",
        table="root",
        attributes=(_ID_PK,),
        inheritance=records.Inheritance(role="root", strategy=None),
    )
    with pytest.raises(DescriptorError, match="declares a strategy"):
        native_metamodel(_one(entity))


def test_an_inheritance_descendant_without_a_parent_is_rejected() -> None:
    entity = records.Entity(
        name="Sub",
        attributes=(_ID_PK,),
        inheritance=records.Inheritance(role="abstract-subtype", parent=None),
    )
    with pytest.raises(DescriptorError, match="names its parent"):
        native_metamodel(_one(entity))


def test_a_qualified_relationship_target_resolves_to_an_exact_reference() -> None:
    # A dot-qualified Entity spelling is exact regardless of the declaring
    # Entity's own namespace — the same authoring rule the descriptor-backed
    # adapter honors for a compiled class record (`m-descriptor` "relationship").
    source = records.Entity(
        name="Order",
        namespace="shop",
        table="order",
        attributes=(
            _ID_PK,
            records.Attribute(name="warehouseId", type="int64", column="warehouse_id"),
        ),
        relationships=(
            records.DefiningRelationship(
                name="warehouse",
                cardinality="many-to-one",
                join=records.RelationshipJoin(
                    source="warehouseId",
                    target=records.RelationshipTarget(entity="ops.Warehouse", attribute="id"),
                ),
            ),
        ),
    )
    (declaration,) = native_metamodel(_one(source)).entities
    (relationship,) = declaration.relationships
    assert isinstance(relationship, UnresolvedDefiningRelationshipDeclaration)
    assert relationship.join.target.entity == ExactEntityReference(
        EntityIdentity("ops", "Warehouse")
    )
    assert relationship.join.target.name == "id"
