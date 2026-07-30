"""Parallax common runtime (``parallax-core``).

The class-free engine spine: metamodel formation, op-algebra nodes, write
instructions, SQL lowering, the pure dialect strategy, the unit of work,
and the abstract database port.

This surface publishes the model-definition and read surface: the frozen entity
bases (``Entity`` and the temporal framework bases ``TxTemporal`` /
``Bitemporal``), the ``ValueObject`` class frontend, the ``Attr`` / ``Rel``
member annotations with the ``attr`` / ``rel`` / ``index`` / ``asc`` / ``desc``
factories, the core-algebra values those take (cardinality, persistence,
inheritance role and strategy, primary-key generation, and the two narrowable
Neutral Types), ``MetamodelHub``, the ``Statement`` query surface (predicate,
result-shaping, deep-fetch ``.include``, subtype ``.narrow``, and the axis-keyed
temporal-read clauses), the temporal as-of coordinate model (``LATEST`` /
``VALID_TIME`` / ``TX_TIME`` / ``Pin`` / ``Edge`` / ``pin_of`` / ``edge_of``),
the closed-world relationship load-state introspection (``is_loaded`` /
``narrowed``) the frozen ``Snapshot[T]`` node surface uses, and the errors all
of these raise. Read-only metadata protocols and identity values are imported
from ``parallax.core.metamodel`` rather than re-exported here, and canonical
descriptor interchange belongs to the separately installable
``parallax.descriptor``. The transaction and snapshot surfaces land with
``parallax.snapshot``.
"""

from __future__ import annotations

from parallax.core.entity import (
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
    AttributeExpr,
    Bitemporal,
    ConcreteSubtype,
    Entity,
    EntityDefinitionError,
    Float32,
    Int32,
    MetamodelDefinitionError,
    MetamodelHub,
    MetamodelLookupError,
    MetamodelStateError,
    ModelCopyError,
    Predicate,
    ProvenanceError,
    Rel,
    RelationshipPath,
    Sequence,
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
from parallax.core.op_algebra import OperationRejectedError, QueryDefinitionError
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
    "MAX",
    "ONE_TO_MANY",
    "ONE_TO_ONE",
    "READ_ONLY",
    "READ_WRITE",
    "TABLE_PER_CONCRETE_SUBTYPE",
    "TX_TIME",
    "VALID_TIME",
    "AbstractRoot",
    "AbstractSubtype",
    "Attr",
    "AttributeExpr",
    "Bitemporal",
    "ConcreteSubtype",
    "Edge",
    "Entity",
    "EntityDefinitionError",
    "Float32",
    "Int32",
    "MetamodelDefinitionError",
    "MetamodelHub",
    "MetamodelLookupError",
    "MetamodelStateError",
    "ModelCopyError",
    "OperationRejectedError",
    "Pin",
    "Predicate",
    "ProvenanceError",
    "QueryDefinitionError",
    "Rel",
    "RelationshipPath",
    "Sequence",
    "Statement",
    "TablePerHierarchy",
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
