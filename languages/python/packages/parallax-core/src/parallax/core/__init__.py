"""Parallax common runtime (``parallax-core``).

The class-free engine spine: metamodel hub, op-algebra nodes, write
instructions, SQL lowering, the pure dialect strategy, the unit of work,
and the abstract database port. Populated across COR-3 phases 2+.

This surface publishes the model-definition and read surface: the frozen entity
base, the ``Attr`` / ``Rel`` typed-access carriers, the ``Field`` /
``Relationship`` declaration helpers, ``meta`` introspection, the ``Statement``
query surface (predicate, result-shaping, and the axis-keyed temporal-read
clauses), and the temporal as-of coordinate model (``LATEST`` / ``Pin`` /
``Edge`` / ``pin_of`` / ``edge_of``). The transaction and snapshot surfaces land
in later phases.
"""

from __future__ import annotations

from parallax.core.entity import (
    Attr,
    AttributeExpr,
    Entity,
    EntityConfig,
    EntityDefinitionError,
    Field,
    NameCollisionError,
    OrderByTerm,
    Predicate,
    Rel,
    Relationship,
    ReservedNameError,
    Statement,
    meta,
)
from parallax.core.temporal_read import (
    LATEST,
    Edge,
    Pin,
    TemporalReadError,
    UndeclaredAxisError,
    edge_of,
    pin_of,
)

__all__ = [
    "LATEST",
    "Attr",
    "AttributeExpr",
    "Edge",
    "Entity",
    "EntityConfig",
    "EntityDefinitionError",
    "Field",
    "NameCollisionError",
    "OrderByTerm",
    "Pin",
    "Predicate",
    "Rel",
    "Relationship",
    "ReservedNameError",
    "Statement",
    "TemporalReadError",
    "UndeclaredAxisError",
    "edge_of",
    "meta",
    "pin_of",
]
