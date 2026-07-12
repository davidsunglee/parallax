"""Parallax common runtime (``parallax-core``).

The class-free engine spine: metamodel hub, op-algebra nodes, write
instructions, SQL lowering, the pure dialect strategy, the unit of work,
and the abstract database port. Populated across COR-3 phases 2+.

This phase publishes the model-definition surface: the frozen entity base, the
``Attr`` / ``Rel`` typed-access carriers, the ``Field`` / ``Relationship``
declaration helpers, and ``meta`` introspection. The statement, transaction, and
snapshot surfaces land in later phases.
"""

from __future__ import annotations

from parallax.core.entity import (
    Attr,
    Entity,
    EntityConfig,
    EntityDefinitionError,
    Field,
    NameCollisionError,
    OrderByTerm,
    Rel,
    Relationship,
    ReservedNameError,
    meta,
)

__all__ = [
    "Attr",
    "Entity",
    "EntityConfig",
    "EntityDefinitionError",
    "Field",
    "NameCollisionError",
    "OrderByTerm",
    "Rel",
    "Relationship",
    "ReservedNameError",
    "meta",
]
