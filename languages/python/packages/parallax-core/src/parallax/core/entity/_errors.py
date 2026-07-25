"""Entity-frontend errors — a strict leaf within the Entity implementation cluster.

Every module in the cluster may depend on this one; it depends on none of them,
imports only the standard library and class-free core identity values, and
retains structured values rather than classes, hubs, or declarations.
Rejections carry a stable code drawn from a closed per-family set, so a caller
branches on the rule that fired rather than on a message substring.

The four families are disjoint by the question they answer.
:class:`EntityDefinitionError` says a declaration is outside the grammar;
:class:`MetamodelDefinitionError` says a hub constructor call is malformed
before any hub exists; :class:`MetamodelStateError` says an Entity Class's
binding state forbids what was asked; and :class:`MetamodelLookupError` says a
developer-facing ``models.meta(...)`` lookup found nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

    from parallax.core.metamodel import EntityIdentity

__all__ = [
    "ENTITY_DEFINITION_CODES",
    "METAMODEL_CLASS_ALREADY_BOUND",
    "METAMODEL_CLASS_NOT_BOUND",
    "METAMODEL_DEFINITION_CODES",
    "METAMODEL_DUPLICATE_ENTITY_CLASS",
    "METAMODEL_EMPTY",
    "METAMODEL_ENTITY_NOT_FOUND",
    "METAMODEL_INVALID_ENTITY_CLASS",
    "METAMODEL_INVALID_ENTITY_REFERENCE",
    "METAMODEL_LOOKUP_CODES",
    "METAMODEL_STATE_CODES",
    "EntityDefinitionError",
    "FrameworkOwnedAxisError",
    "MetamodelDefinitionError",
    "MetamodelLookupError",
    "MetamodelStateError",
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


METAMODEL_EMPTY: Final = "metamodel-empty"
"""A hub was constructed over no source at all."""
METAMODEL_INVALID_ENTITY_CLASS: Final = "metamodel-invalid-entity-class"
"""A constructor argument is not a domain Entity Class."""
METAMODEL_DUPLICATE_ENTITY_CLASS: Final = "metamodel-duplicate-entity-class"
"""One class object was passed to the constructor more than once."""

METAMODEL_DEFINITION_CODES: Final[frozenset[str]] = frozenset(
    {METAMODEL_EMPTY, METAMODEL_INVALID_ENTITY_CLASS, METAMODEL_DUPLICATE_ENTITY_CLASS}
)
"""The complete malformed-constructor-call vocabulary."""

METAMODEL_CLASS_NOT_BOUND: Final = "metamodel-class-not-bound"
"""An Entity Class no hub has claimed was used where a model is required, or a
class outside this hub was handed to its lookup."""
METAMODEL_CLASS_ALREADY_BOUND: Final = "metamodel-class-already-bound"
"""One or more Entity Classes already belong to another sealed hub."""

METAMODEL_STATE_CODES: Final[frozenset[str]] = frozenset(
    {METAMODEL_CLASS_NOT_BOUND, METAMODEL_CLASS_ALREADY_BOUND}
)
"""The complete binding-state vocabulary. A hub exists only sealed, so there is
no unsealed, rejected, or seal-re-entry code to carry."""

METAMODEL_INVALID_ENTITY_REFERENCE: Final = "metamodel-invalid-entity-reference"
"""A lookup string is not a canonical Entity spelling."""
METAMODEL_ENTITY_NOT_FOUND: Final = "metamodel-entity-not-found"
"""A well-formed lookup key names no Entity of this model."""

METAMODEL_LOOKUP_CODES: Final[frozenset[str]] = frozenset(
    {METAMODEL_INVALID_ENTITY_REFERENCE, METAMODEL_ENTITY_NOT_FOUND, METAMODEL_CLASS_NOT_BOUND}
)
"""The complete ``models.meta(...)`` failure vocabulary. The class-free lookup
protocol returns absence instead and raises none of these."""


class MetamodelDefinitionError(TypeError):
    """A hub constructor call is malformed, before any hub exists.

    ``index`` is the zero-based position of the offending argument, and is
    absent only for :data:`METAMODEL_EMPTY`, which is about the call rather than
    about one argument. Two distinct classes declaring one Entity Identity are
    valid input here and become a whole-model issue instead.
    """

    def __init__(self, *, code: str, message: str, index: int | None = None) -> None:
        if code not in METAMODEL_DEFINITION_CODES:
            raise ValueError(f"{code!r} is not a metamodel definition code")
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.index = index


class MetamodelStateError(RuntimeError):
    """An Entity Class's binding state forbids the requested operation.

    ``entities`` carries every conflicting Entity Identity in canonical order
    for :data:`METAMODEL_CLASS_ALREADY_BOUND`, so a racing constructor reports
    the whole overlap rather than the first class it happened to reach; it is
    empty for :data:`METAMODEL_CLASS_NOT_BOUND`, where no identity is known.
    """

    def __init__(self, *, code: str, message: str, entities: Sequence[EntityIdentity] = ()) -> None:
        if code not in METAMODEL_STATE_CODES:
            raise ValueError(f"{code!r} is not a metamodel state code")
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.entities = tuple(entities)


class MetamodelLookupError(LookupError):
    """A developer-facing ``models.meta(...)`` lookup found no Entity."""

    def __init__(self, *, code: str, message: str) -> None:
        if code not in METAMODEL_LOOKUP_CODES:
            raise ValueError(f"{code!r} is not a metamodel lookup code")
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
