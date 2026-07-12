"""Entity-frontend definition-time errors."""

from __future__ import annotations

__all__ = ["EntityDefinitionError", "NameCollisionError", "ReservedNameError"]


class EntityDefinitionError(TypeError):
    """An entity class declaration violates the frontend contract."""


class ReservedNameError(EntityDefinitionError):
    """A field reuses a name reserved for the query root or the model space."""


class NameCollisionError(EntityDefinitionError):
    """Two fields resolve to the same canonical (camelCase) identifier."""
