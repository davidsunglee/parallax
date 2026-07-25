"""``parallax.core.entity`` enforcement scope (the Python class frontend, support).

The sole supported Python model-authoring surface: the frozen ``Entity`` and
``ValueObject`` bases and their temporal framework siblings, the ``Attr[T]`` /
``Rel[T]`` member annotations with the ``attr`` / ``rel`` / ``index`` / ``asc`` /
``desc`` factories, the closed ``EntityDefinitionError`` code set, the statement
surface, and the closed-world relationship load-state vocabulary. The underscored
modules behind these names are implementation detail rather than caller seams.

Entity Classes are their own formation input: the declaration engine builds each
class's ``UnresolvedEntityDeclaration`` eagerly at class creation, so this scope
imports no descriptor interchange code at all.
"""

from __future__ import annotations

from parallax.core.entity._declaration import EntityDeclaration, snake_to_camel
from parallax.core.entity._entity import (
    Bitemporal,
    Entity,
    EntityMeta,
    TxTemporal,
    WireNames,
    canonical_row,
    changed_fields,
    effective_change_set,
    full_row,
    primary_key_row,
    wire_names_of,
)
from parallax.core.entity._errors import (
    ENTITY_DEFINITION_CODES,
    EntityDefinitionError,
    FrameworkOwnedAxisError,
    ModelCopyError,
    ProvenanceError,
    UnloadedRelationshipError,
)
from parallax.core.entity._expressions import (
    UNLOADED,
    AttributeExpr,
    AttributeRef,
    ElementAttributeExpr,
    Predicate,
    RelationshipPath,
    RelationshipRef,
)
from parallax.core.entity._members import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    ONE_TO_ONE,
    READ_ONLY,
    READ_WRITE,
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    AbstractSubtype,
    Attr,
    AttrSpec,
    ConcreteSubtype,
    DefiningRelSpec,
    IndexSpec,
    OrderTerm,
    Rel,
    ReverseRelSpec,
    TablePerHierarchy,
    asc,
    attr,
    desc,
    index,
    rel,
)
from parallax.core.entity._value_object import ValueObject, ValueObjectMeta, to_document
from parallax.core.entity.graph_state import is_loaded, narrowed
from parallax.core.entity.statement import Statement, UnsupportedFeatureError

__all__ = [
    "ENTITY_DEFINITION_CODES",
    "MANY_TO_ONE",
    "ONE_TO_MANY",
    "ONE_TO_ONE",
    "READ_ONLY",
    "READ_WRITE",
    "TABLE_PER_CONCRETE_SUBTYPE",
    "UNLOADED",
    "AbstractRoot",
    "AbstractSubtype",
    "Attr",
    "AttrSpec",
    "AttributeExpr",
    "AttributeRef",
    "Bitemporal",
    "ConcreteSubtype",
    "DefiningRelSpec",
    "ElementAttributeExpr",
    "Entity",
    "EntityDeclaration",
    "EntityDefinitionError",
    "EntityMeta",
    "FrameworkOwnedAxisError",
    "IndexSpec",
    "ModelCopyError",
    "OrderTerm",
    "Predicate",
    "ProvenanceError",
    "Rel",
    "RelationshipPath",
    "RelationshipRef",
    "ReverseRelSpec",
    "Statement",
    "TablePerHierarchy",
    "TxTemporal",
    "UnloadedRelationshipError",
    "UnsupportedFeatureError",
    "ValueObject",
    "ValueObjectMeta",
    "WireNames",
    "asc",
    "attr",
    "canonical_row",
    "changed_fields",
    "desc",
    "effective_change_set",
    "full_row",
    "index",
    "is_loaded",
    "narrowed",
    "primary_key_row",
    "rel",
    "snake_to_camel",
    "to_document",
    "wire_names_of",
]
