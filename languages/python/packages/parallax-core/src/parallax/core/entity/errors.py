"""Entity-frontend definition-time errors."""

from __future__ import annotations

__all__ = [
    "EntityDefinitionError",
    "NameCollisionError",
    "RegistryCollisionError",
    "ReservedNameError",
]


class EntityDefinitionError(TypeError):
    """An entity class declaration violates the frontend contract."""


class ReservedNameError(EntityDefinitionError):
    """A field reuses a name reserved for the query root or the model space."""


class NameCollisionError(EntityDefinitionError):
    """Two fields resolve to the same canonical (camelCase) identifier."""


class RegistryCollisionError(NameCollisionError):
    """Two classes register the SAME canonical entity name in ONE
    :class:`~parallax.core.entity.base.EntityRegistry` (ledger D-20): a loud,
    actionable class-definition-time error naming both classes -- the
    replacement for the historical silent last-write-wins module-dict write.
    A same-named class registered in a DIFFERENT registry is unaffected;
    coexistence across registries is the whole point of D-20."""
