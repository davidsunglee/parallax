"""``parallax.core.entity`` enforcement scope (the Python class frontend, support).

The sole supported Python model-authoring surface: the frozen ``Entity`` and
``ValueObject`` bases and their temporal framework siblings, the ``Attr[T]`` /
``Rel[T]`` member annotations with the ``attr`` / ``rel`` / ``index`` / ``asc`` /
``desc`` factories, the core-algebra spellings those take, ``DomainModel`` and
its closed error-code sets, and the Object Query surface it re-exports from
``m-object-query``. The underscored modules
behind these names are implementation detail rather than caller seams.

It additionally exposes the **advanced Entity Graph Construction collaboration**
— ``graph_construction_of``, ``EntityGraphConstruction``, its writer, the opaque
``NodeHandle`` its positional rows name a node by, and the ``UNLOADED`` sentinel
a relationship position spells, plus the two operations a lifecycle reads back
(``relationship_value_of``, ``lifecycle_state_of``) — and the **Entity Row
Codec** a write path derives rows through, reached by ``row_codec_of``. The two
are this scope's named model-bound capability seams, and there is no composite
value over them. Top-level ``parallax.core`` re-exports neither: a first-party
lifecycle or persistence package reaches them here on purpose, and a developer
never needs either.

Entity Classes are their own formation input: the declaration engine builds each
class's ``UnresolvedEntityDeclaration`` eagerly at class creation, so this scope
imports no descriptor interchange code at all.
"""

from __future__ import annotations

from parallax.core.entity._construction_input import UNLOADED, NodeHandle
from parallax.core.entity._declaration import EntityDeclaration, shape_of, snake_to_camel
from parallax.core.entity._entity import Bitemporal, Entity, TxTemporal
from parallax.core.entity._errors import (
    EDIT_CODES,
    ENTITY_DEFINITION_CODES,
    ENTITY_ROW_CODES,
    GRAPH_CONSTRUCTION_CODES,
    METAMODEL_DEFINITION_CODES,
    METAMODEL_LOOKUP_CODES,
    EditError,
    EditViolation,
    EntityDefinitionError,
    EntityRowError,
    GraphConstructionError,
    MetamodelDefinitionError,
    MetamodelLookupError,
    UnloadedRelationshipError,
)
from parallax.core.entity._expressions import (
    AllPredicate,
    AttributeAssignment,
    AttributeExpr,
    AttributeRef,
    ElementAttributeExpr,
    Predicate,
    RelationshipPath,
    RelationshipRef,
    SortKey,
)
from parallax.core.entity._graph_construction import (
    EntityGraphConstruction,
    EntityGraphWriter,
    ResolutionView,
    graph_construction_of,
    lifecycle_state_of,
    relationship_value_of,
)
from parallax.core.entity._members import (
    MANY_TO_ONE,
    MAX,
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
    Document,
    Float32,
    IndexSpec,
    Int32,
    OrderTerm,
    Rel,
    ReverseRelSpec,
    Sequence,
    TablePerHierarchy,
    asc,
    attr,
    desc,
    index,
    rel,
)
from parallax.core.entity._model import DomainModel
from parallax.core.entity._row_codec import EntityRowCodec, row_codec_of
from parallax.core.entity._value_object import ValueObject, to_document
from parallax.core.object_query._fluent import ObjectQuery

__all__ = [
    "EDIT_CODES",
    "ENTITY_DEFINITION_CODES",
    "ENTITY_ROW_CODES",
    "GRAPH_CONSTRUCTION_CODES",
    "MANY_TO_ONE",
    "MAX",
    "METAMODEL_DEFINITION_CODES",
    "METAMODEL_LOOKUP_CODES",
    "ONE_TO_MANY",
    "ONE_TO_ONE",
    "READ_ONLY",
    "READ_WRITE",
    "TABLE_PER_CONCRETE_SUBTYPE",
    "UNLOADED",
    "AbstractRoot",
    "AbstractSubtype",
    "AllPredicate",
    "Attr",
    "AttrSpec",
    "AttributeAssignment",
    "AttributeExpr",
    "AttributeRef",
    "Bitemporal",
    "ConcreteSubtype",
    "DefiningRelSpec",
    "Document",
    "DomainModel",
    "EditError",
    "EditViolation",
    "ElementAttributeExpr",
    "Entity",
    "EntityDeclaration",
    "EntityDefinitionError",
    "EntityGraphConstruction",
    "EntityGraphWriter",
    "EntityRowCodec",
    "EntityRowError",
    "Float32",
    "GraphConstructionError",
    "IndexSpec",
    "Int32",
    "MetamodelDefinitionError",
    "MetamodelLookupError",
    "NodeHandle",
    "ObjectQuery",
    "OrderTerm",
    "Predicate",
    "Rel",
    "RelationshipPath",
    "RelationshipRef",
    "ResolutionView",
    "ReverseRelSpec",
    "Sequence",
    "SortKey",
    "TablePerHierarchy",
    "TxTemporal",
    "UnloadedRelationshipError",
    "ValueObject",
    "asc",
    "attr",
    "desc",
    "graph_construction_of",
    "index",
    "lifecycle_state_of",
    "rel",
    "relationship_value_of",
    "row_codec_of",
    "shape_of",
    "snake_to_camel",
    "to_document",
]
