"""Entity-frontend errors — a strict leaf within the Entity implementation cluster.

Every module in the cluster may depend on this one; it depends on none of them,
imports only the standard library and class-free core identity values, and
retains structured values rather than classes, models, or declarations.
Rejections carry a stable code drawn from a closed per-family set, so a caller
branches on the rule that fired rather than on a message substring.

The four families are disjoint by the question they answer.
:class:`EntityDefinitionError` says a declaration is outside the grammar;
:class:`MetamodelDefinitionError` says a Domain Model constructor call is
malformed before any model exists; :class:`MetamodelLookupError` says a
developer-facing ``models.meta(...)`` lookup found nothing; and
:class:`GraphConstructionError` says a caller drove the advanced Entity Graph
Construction collaboration outside its contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from parallax.core.metamodel import (
        EntityIdentity,
        MemberIdentity,
        RelationshipIdentity,
    )

__all__ = [
    "ENTITY_DEFINITION_CODES",
    "GRAPH_CONSTRUCTION_CODES",
    "METAMODEL_DEFINITION_CODES",
    "METAMODEL_DUPLICATE_ENTITY_CLASS",
    "METAMODEL_EMPTY",
    "METAMODEL_ENTITY_NOT_FOUND",
    "METAMODEL_INVALID_ENTITY_CLASS",
    "METAMODEL_INVALID_ENTITY_REFERENCE",
    "METAMODEL_LOOKUP_CODES",
    "EntityDefinitionError",
    "GraphConstructionError",
    "MetamodelDefinitionError",
    "MetamodelLookupError",
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
the Domain Model constructor's Python realization phase."""


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
"""A Domain Model was constructed over no source at all."""
METAMODEL_INVALID_ENTITY_CLASS: Final = "metamodel-invalid-entity-class"
"""A constructor argument is not a domain Entity Class."""
METAMODEL_DUPLICATE_ENTITY_CLASS: Final = "metamodel-duplicate-entity-class"
"""One class object was passed to the constructor more than once."""

METAMODEL_DEFINITION_CODES: Final[frozenset[str]] = frozenset(
    {METAMODEL_EMPTY, METAMODEL_INVALID_ENTITY_CLASS, METAMODEL_DUPLICATE_ENTITY_CLASS}
)
"""The complete malformed-constructor-call vocabulary."""

METAMODEL_INVALID_ENTITY_REFERENCE: Final = "metamodel-invalid-entity-reference"
"""A lookup string is not a canonical Entity spelling."""
METAMODEL_ENTITY_NOT_FOUND: Final = "metamodel-entity-not-found"
"""A well-formed lookup key names no Entity of this model."""

METAMODEL_LOOKUP_CODES: Final[frozenset[str]] = frozenset(
    {METAMODEL_INVALID_ENTITY_REFERENCE, METAMODEL_ENTITY_NOT_FOUND}
)
"""The complete ``models.meta(...)`` failure vocabulary. The class-free lookup
protocol returns absence instead and raises none of these."""


class MetamodelDefinitionError(TypeError):
    """A Domain Model constructor call is malformed, before any model exists.

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


class MetamodelLookupError(LookupError):
    """A developer-facing ``models.meta(...)`` lookup found no Entity."""

    def __init__(self, *, code: str, message: str) -> None:
        if code not in METAMODEL_LOOKUP_CODES:
            raise ValueError(f"{code!r} is not a metamodel lookup code")
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


GRAPH_CONSTRUCTION_CODES: Final[frozenset[str]] = frozenset(
    {
        "entity-graph-invalid-entity",
        "entity-graph-invalid-member",
        "entity-graph-allocation-closed",
        "entity-graph-scope-closed",
        "entity-graph-foreign-handle",
        "entity-graph-node-already-populated",
        "entity-graph-node-unpopulated",
        "entity-graph-invalid-root",
        "entity-graph-invalid-value",
    }
)
"""The complete Entity Graph Construction misuse vocabulary. Every code names a
caller contract the collaboration checks itself, so no misuse of it surfaces as
an assertion, a :class:`LookupError`, or a partially built graph."""


class GraphConstructionError(RuntimeError):
    """The advanced Entity Graph Construction collaboration was driven outside
    its contract.

    A ``RuntimeError`` because every code describes caller misuse or an
    implementation defect rather than rejected data: the same reasoning that puts
    model-formation contract failures on ``RuntimeError`` while a stored-value
    rejection stays a ``ValueError``.

    ``index`` is the deterministic zero-based allocation index of the node the
    failure is about, absent for a failure that is about no single node.
    ``identity`` is the structured Entity, member, or Relationship Identity at
    fault, and ``cause`` the original conversion failure when one exists. Neither
    a handle, a writer, a resolution view, nor a partially built Entity is ever
    retained here.
    """

    def __init__(
        self,
        *,
        code: str,
        message: str,
        index: int | None = None,
        identity: EntityIdentity | MemberIdentity | RelationshipIdentity | None = None,
        cause: Exception | None = None,
    ) -> None:
        if code not in GRAPH_CONSTRUCTION_CODES:
            raise ValueError(f"{code!r} is not a graph construction code")
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.index = index
        self.identity = identity
        self.cause = cause


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
    """An assignment the §3 rule family refuses, whichever surface authored it.

    Two surfaces raise it, because the rules are one set: ``model_copy(update=
    ...)`` and ``Attr.set(...)``. A name that reaches no assignable member —
    unknown or a relationship — is refused by the surface itself; every other
    refusal is the shared assignment judgement's, so this class equally carries a
    primary-key, read-only, or framework-owned target, a value that does not
    match the member's declared type, and a cleared member that is not nullable.
    """


class ProvenanceError(ValueError):
    """An instance carries no Change Record (never produced via ``model_copy``)
    and cannot drive a sparse ``tx.update`` (spec §5)."""
