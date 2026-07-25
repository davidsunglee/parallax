"""Entity-frontend errors — a strict leaf within the Entity implementation cluster.

Every module in the cluster may depend on this one; it depends on none of them,
imports only the standard library, and retains structured values rather than
classes, hubs, or declarations. Declaration rejections carry a stable code drawn
from the closed :data:`ENTITY_DEFINITION_CODES` set, so a caller branches on the
rule that fired rather than on a message substring.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "ENTITY_DEFINITION_CODES",
    "EntityDefinitionError",
    "FrameworkOwnedAxisError",
    "ModelCopyError",
    "ProvenanceError",
    "UnloadedRelationshipError",
]

ENTITY_DEFINITION_CODES: Final[frozenset[str]] = frozenset(
    {
        "entity-header-unknown-option",
        "entity-header-invalid-value",
        "entity-header-missing-option",
        "entity-base-invalid",
        "entity-annotation-invalid",
        "entity-member-value-invalid",
        "entity-option-invalid-value",
        "entity-option-context-invalid",
        "entity-reserved-member-name",
        "entity-canonical-name-collision",
        "entity-relationship-annotation-mismatch",
    }
)
"""The complete declaration-rejection vocabulary. Ten codes fire at a factory
call or at class creation; ``entity-relationship-annotation-mismatch`` fires in
the hub constructor's Python realization phase."""


class EntityDefinitionError(TypeError):
    """A declaration the Python grammar cannot accept.

    ``code`` is a member of :data:`ENTITY_DEFINITION_CODES`; constructing one
    with any other code is an implementation defect and raises
    :class:`ValueError`.
    """

    def __init__(self, *, code: str, message: str) -> None:
        if code not in ENTITY_DEFINITION_CODES:
            raise ValueError(f"{code!r} is not an entity definition code")
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class UnloadedRelationshipError(AttributeError):
    """A closed-world relationship (or narrowed view) was not fetched by the read
    that produced this node (spec §3): access raises, naming the path and the
    ``.include(...)`` fix rather than issuing lazy SQL."""

    def __init__(self, path: str) -> None:
        super().__init__(
            f"{path!r} was not included in this find; add `.include({path})` "
            "to fetch it (this snapshot lifecycle never lazy-loads)"
        )
        self.path = path


class ModelCopyError(TypeError):
    """A ``model_copy(update=...)`` call names an unassignable member (spec §3):
    unknown, primary-key, framework-owned, or a relationship."""


class ProvenanceError(ValueError):
    """An instance carries no Change Record (never produced via ``model_copy``)
    and cannot drive a sparse ``tx.update`` (spec §5)."""


class FrameworkOwnedAxisError(ValueError):
    """A fresh instance names an axis-governed attribute at construction.

    The temporal write path stamps every milestone bound itself — from the Clock
    Strategy and the verb's own window arguments — so a caller-supplied value is
    never a legitimate alternative and is rejected rather than silently
    discarded.
    """
