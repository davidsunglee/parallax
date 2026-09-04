"""Evolution Operations from one :class:`~._matching.Matching`, in inspection order.

A parent addition or removal suppresses every operation for the declarations it
contains, so an Entity present in one endpoint alone is one entity-level
operation and nothing else — which is also what makes the fresh-provisioning
evolution, whose every Entity is an addition, the same code path rather than a
second differ.

The generic Entity variants exclude concrete-subtype add and remove, and each
Entity's role is read from the endpoint that declares it: the later model for an
addition, the earlier one for a removal.
"""

from __future__ import annotations

from collections.abc import Iterable

from parallax.core.metamodel import ConcreteSubtype, EntityMetadata
from parallax.evolution.model_evolution._matching import Matching
from parallax.evolution.model_evolution._values import (
    ConcreteSubtypeAdded,
    ConcreteSubtypeRemoved,
    EntityAdded,
    EntityRemoved,
    EvolutionOperation,
    canonical_operation_key,
)

__all__ = ["diff"]


def diff(matching: Matching) -> tuple[EvolutionOperation, ...]:
    """Every Evolution Operation the two endpoints differ by."""
    return _ordered(
        [
            *(_added(entity) for entity in matching.entities.added.values()),
            *(_removed(entity) for entity in matching.entities.removed.values()),
        ]
    )


def _added(entity: EntityMetadata) -> EvolutionOperation:
    """The one entity-level addition for ``entity``'s role in the later endpoint."""
    if isinstance(entity.inheritance, ConcreteSubtype):
        return ConcreteSubtypeAdded(entity.identity)
    return EntityAdded(entity.identity)


def _removed(entity: EntityMetadata) -> EvolutionOperation:
    """The one entity-level removal for ``entity``'s role in the earlier endpoint."""
    if isinstance(entity.inheritance, ConcreteSubtype):
        return ConcreteSubtypeRemoved(entity.identity)
    return EntityRemoved(entity.identity)


def _ordered(operations: Iterable[EvolutionOperation]) -> tuple[EvolutionOperation, ...]:
    return tuple(sorted(operations, key=canonical_operation_key))
