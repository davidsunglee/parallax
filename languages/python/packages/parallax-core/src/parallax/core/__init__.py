"""Parallax common runtime (``parallax-core``).

The class-free engine spine: metamodel formation, Predicate nodes, write
instructions, SQL lowering, the pure dialect strategy, the unit of work,
and the abstract database port.

This surface publishes the model-definition and read surface: the frozen entity
bases (``Entity`` and the temporal framework bases ``TxTemporal`` /
``Bitemporal``), the ``ValueObject`` class frontend, the ``Attr`` / ``Rel``
member annotations with the ``attr`` / ``rel`` / ``index`` / ``asc`` / ``desc``
factories, the core-algebra values those take (cardinality, persistence,
inheritance role and strategy, primary-key generation, and the two narrowable
Neutral Types), ``DomainModel``, the ``FindQuery`` surface (predicate,
result-shaping, deep-fetch ``.include``, subtype ``.narrow``, and the axis-keyed
temporal-read clauses), the lifecycle-neutral temporal as-of coordinate model
(``LATEST`` / ``VALID_TIME`` / ``TX_TIME`` / ``Pin`` / ``Edge``), and the errors
all of these raise. Read-only metadata protocols and identity values are imported
from ``parallax.core.metamodel`` rather than re-exported here, and canonical
descriptor interchange belongs to the separately installable
``parallax.descriptor``. The transaction and snapshot surfaces land with
``parallax.snapshot``, and so does every operation that inspects a materialized
node: reading a node's loaded views, pin, or milestone edge is a question about
the lifecycle that produced it, so ``is_view_loaded`` / ``view`` / ``pin_of`` /
``edge_of`` and the ``UnloadedRelationshipError`` they raise live there, the
error class itself staying available on ``parallax.core.entity`` for the
advanced seam.
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
    AllPredicate,
    Attr,
    AttributeExpr,
    Bitemporal,
    ConcreteSubtype,
    Document,
    DomainModel,
    EditError,
    EditViolation,
    Entity,
    EntityDefinitionError,
    FindQuery,
    Float32,
    Int32,
    MetamodelDefinitionError,
    MetamodelLookupError,
    Predicate,
    Rel,
    RelationshipPath,
    Sequence,
    SortKey,
    TablePerHierarchy,
    TxTemporal,
    ValueObject,
    asc,
    attr,
    desc,
    index,
    rel,
)
from parallax.core.predicate import OperationRejectedError, QueryDefinitionError
from parallax.core.temporal_read import (
    LATEST,
    TX_TIME,
    VALID_TIME,
    Edge,
    Pin,
    TemporalReadError,
    UndeclaredAxisError,
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
    "AllPredicate",
    "Attr",
    "AttributeExpr",
    "Bitemporal",
    "ConcreteSubtype",
    "Document",
    "DomainModel",
    "Edge",
    "EditError",
    "EditViolation",
    "Entity",
    "EntityDefinitionError",
    "FindQuery",
    "Float32",
    "Int32",
    "MetamodelDefinitionError",
    "MetamodelLookupError",
    "OperationRejectedError",
    "Pin",
    "Predicate",
    "QueryDefinitionError",
    "Rel",
    "RelationshipPath",
    "Sequence",
    "SortKey",
    "TablePerHierarchy",
    "TemporalReadError",
    "TxTemporal",
    "UndeclaredAxisError",
    "ValueObject",
    "asc",
    "attr",
    "desc",
    "index",
    "rel",
]
