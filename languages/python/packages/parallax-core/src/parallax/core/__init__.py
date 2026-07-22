"""Parallax common runtime (``parallax-core``).

The class-free engine spine: metamodel hub, op-algebra nodes, write
instructions, SQL lowering, the pure dialect strategy, the unit of work,
and the abstract database port. Populated across COR-3 phases 2+.

This surface publishes the model-definition and read surface: the frozen entity
base, the ``Attr`` / ``Rel`` typed-access carriers, the ``Field`` /
``Relationship`` declaration helpers, the ``ValueObject`` class frontend (D-7),
the inheritance-family vocabulary (``FamilyRoot`` / ``Concrete``, D-7 DQ2),
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
    Attr,
    AttributeExpr,
    Concrete,
    Entity,
    EntityConfig,
    EntityDefinitionError,
    EntityRegistry,
    FamilyRoot,
    Field,
    ModelCopyError,
    NameCollisionError,
    OrderByTerm,
    Predicate,
    ProvenanceError,
    Rel,
    Relationship,
    RelationshipPath,
    ReservedNameError,
    ReverseRelationship,
    Statement,
    UnloadedRelationshipError,
    UnsupportedFeatureError,
    ValueObject,
    VoField,
    is_loaded,
    narrowed,
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
    "TX_TIME",
    "VALID_TIME",
    "AsOfAxisMetadata",
    "Attr",
    "AttributeExpr",
    "Concrete",
    "Edge",
    "Entity",
    "EntityConfig",
    "EntityDefinitionError",
    "EntityRegistry",
    "FamilyRoot",
    "Field",
    "ModelCopyError",
    "NameCollisionError",
    "OperationRejectedError",
    "OrderByTerm",
    "Pin",
    "Predicate",
    "ProvenanceError",
    "Rel",
    "Relationship",
    "RelationshipJoin",
    "RelationshipPath",
    "RelationshipTarget",
    "ReservedNameError",
    "ReverseRelationship",
    "Statement",
    "TemporalDimension",
    "TemporalReadError",
    "UndeclaredAxisError",
    "UnloadedRelationshipError",
    "UnsupportedFeatureError",
    "ValueObject",
    "VoField",
    "edge_of",
    "is_loaded",
    "narrowed",
    "pin_of",
]
