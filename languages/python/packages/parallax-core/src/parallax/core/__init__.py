"""Parallax common runtime (``parallax-core``).

The class-free engine spine: metamodel hub, op-algebra nodes, write
instructions, SQL lowering, the pure dialect strategy, the unit of work,
and the abstract database port.

This surface publishes the model-definition and read surface: the frozen entity
bases (``Entity`` and the temporal framework bases ``TxTemporal`` /
``Bitemporal``), the ``Attr`` / ``Rel`` typed-access carriers, the ``Field`` /
``Relationship`` declaration helpers, the ``ValueObject`` class frontend,
the inheritance-family vocabulary (``FamilyRoot`` / ``Concrete``),
the ``Statement`` query surface (predicate,
result-shaping, deep-fetch ``.include``, subtype ``.narrow``, and the
axis-keyed temporal-read clauses), the temporal as-of coordinate model
(``LATEST`` / ``VALID_TIME`` / ``TX_TIME`` / ``Pin`` / ``Edge`` / ``pin_of``
/ ``edge_of``), and the
closed-world relationship load-state introspection (``is_loaded`` /
``narrowed``) the frozen ``Snapshot[T]`` node surface uses. The transaction and
snapshot surfaces land with ``parallax.snapshot``.
"""

from __future__ import annotations

from parallax.core.descriptor import (
    AsOfAxisMetadata,
    RelationshipJoin,
    RelationshipTarget,
    TemporalDimension,
)
from parallax.core.entity import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    ONE_TO_ONE,
    READ_ONLY,
    READ_WRITE,
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    AbstractSubtype,
    Attr,
    AttributeExpr,
    Bitemporal,
    ConcreteSubtype,
    Entity,
    EntityDefinitionError,
    ModelCopyError,
    Predicate,
    ProvenanceError,
    Rel,
    RelationshipPath,
    Statement,
    TablePerHierarchy,
    TxTemporal,
    UnloadedRelationshipError,
    UnsupportedFeatureError,
    ValueObject,
    asc,
    attr,
    desc,
    index,
    is_loaded,
    narrowed,
    rel,
)
from parallax.core.op_algebra import OperationRejectedError
from parallax.core.temporal_read import (
    LATEST,
    TX_TIME,
    VALID_TIME,
    Edge,
    Pin,
    TemporalReadError,
    UndeclaredAxisError,
    edge_of,
    pin_of,
)

__all__ = [
    "LATEST",
    "MANY_TO_ONE",
    "ONE_TO_MANY",
    "ONE_TO_ONE",
    "READ_ONLY",
    "READ_WRITE",
    "TABLE_PER_CONCRETE_SUBTYPE",
    "TX_TIME",
    "VALID_TIME",
    "AbstractRoot",
    "AbstractSubtype",
    "AsOfAxisMetadata",
    "Attr",
    "AttributeExpr",
    "Bitemporal",
    "ConcreteSubtype",
    "Edge",
    "Entity",
    "EntityDefinitionError",
    "ModelCopyError",
    "OperationRejectedError",
    "Pin",
    "Predicate",
    "ProvenanceError",
    "Rel",
    "RelationshipJoin",
    "RelationshipPath",
    "RelationshipTarget",
    "Statement",
    "TablePerHierarchy",
    "TemporalDimension",
    "TemporalReadError",
    "TxTemporal",
    "UndeclaredAxisError",
    "UnloadedRelationshipError",
    "UnsupportedFeatureError",
    "ValueObject",
    "asc",
    "attr",
    "desc",
    "edge_of",
    "index",
    "is_loaded",
    "narrowed",
    "pin_of",
    "rel",
]
