"""Entity-frontend errors — a strict leaf within the Entity implementation cluster.

Every module in the cluster may depend on this one; it depends on none of them,
imports only the standard library and class-free core identity, location, and
issue-ordering values, and
retains structured values rather than classes, models, or declarations.
Rejections carry a stable code drawn from a closed per-family set, so a caller
branches on the rule that fired rather than on a message substring.

The six families are disjoint by the question they answer.
:class:`EntityDefinitionError` says a declaration is outside the grammar;
:class:`MetamodelDefinitionError` says a Domain Model constructor call is
malformed before any model exists; :class:`MetamodelLookupError` says a
developer-facing ``models.meta(...)`` lookup found nothing;
:class:`GraphConstructionError` says a caller drove the advanced Entity Graph
Construction collaboration outside its contract; :class:`EntityRowError` says a
caller asked the Entity Row Codec for a row it cannot derive; and
:class:`EditError` says an authored assignment to a live value breaks the shared
assignment rules.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from parallax.core.metamodel import canonical_location_key

if TYPE_CHECKING:
    from parallax.core.metamodel import (
        EntityIdentity,
        MemberIdentity,
        ModelLocation,
        ModelLocationKey,
        RelationshipIdentity,
    )

__all__ = [
    "EDIT_CODES",
    "EDIT_CODE_BY_RULE",
    "ENTITY_DEFINITION_CODES",
    "ENTITY_ROW_CODES",
    "ENTITY_ROW_MALFORMED_PROVENANCE",
    "ENTITY_ROW_MEMBER_MISSING",
    "ENTITY_ROW_NOT_AN_ENTITY",
    "ENTITY_ROW_TARGET_NOT_IN_MODEL",
    "GRAPH_CONSTRUCTION_CODES",
    "METAMODEL_DEFINITION_CODES",
    "METAMODEL_DUPLICATE_ENTITY_CLASS",
    "METAMODEL_EMPTY",
    "METAMODEL_ENTITY_NOT_FOUND",
    "METAMODEL_INVALID_ENTITY_CLASS",
    "METAMODEL_INVALID_ENTITY_REFERENCE",
    "METAMODEL_LOOKUP_CODES",
    "EditError",
    "EditViolation",
    "EntityDefinitionError",
    "EntityRowError",
    "GraphConstructionError",
    "MetamodelDefinitionError",
    "MetamodelLookupError",
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
        "entity-graph-layout-mismatch",
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


ENTITY_ROW_NOT_AN_ENTITY: Final = "entity-row-not-an-entity"
"""A row was asked for a value that is no Entity at all."""
ENTITY_ROW_TARGET_NOT_IN_MODEL: Final = "entity-row-target-not-in-model"
"""The value's Entity Identity resolves to no Entity of the codec's model."""
ENTITY_ROW_MEMBER_MISSING: Final = "entity-row-member-missing"
"""An operation selected a member it cannot emit: either the resolved identity
does not declare it, or the value's class carries no attribute for one it does."""
ENTITY_ROW_MALFORMED_PROVENANCE: Final = "entity-row-malformed-provenance"
"""The private Change Record slot holds something that is not a Change Record."""

ENTITY_ROW_CODES: Final[frozenset[str]] = frozenset(
    {
        ENTITY_ROW_NOT_AN_ENTITY,
        ENTITY_ROW_TARGET_NOT_IN_MODEL,
        ENTITY_ROW_MEMBER_MISSING,
        ENTITY_ROW_MALFORMED_PROVENANCE,
    }
)
"""The complete Entity Row Codec refusal vocabulary. Every code names an input
the codec's own contract rejects, so no misuse of it surfaces as an
:class:`AttributeError`, a :class:`KeyError`, or a partially keyed row."""


class EntityRowError(RuntimeError):
    """The Entity Row Codec was asked for a row it cannot derive.

    A ``RuntimeError`` for :class:`GraphConstructionError`'s reason: every code
    describes first-party misuse or an implementation defect rather than rejected
    developer input. The codec knows only that it received a value its operation
    does not accept; the developer-facing steering for handing a persistence verb
    an unedited value belongs to that verb, which knows what the developer
    called.

    ``identity`` is the resolved Entity Identity the refusal is about, absent
    only when the value carried none to resolve. Neither the value, its class,
    nor any partially built row is ever retained here.
    """

    def __init__(self, *, code: str, message: str, identity: EntityIdentity | None = None) -> None:
        if code not in ENTITY_ROW_CODES:
            raise ValueError(f"{code!r} is not an entity row code")
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.identity = identity


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


EDIT_CODES: Final[frozenset[str]] = frozenset(
    {
        "edit-use-edit",
        "edit-unknown-member",
        "edit-relationship-member",
        "edit-nested-path",
        "edit-primary-key",
        "edit-read-only",
        "edit-framework-owned",
        "edit-value-mismatch",
    }
)
"""The complete edit-refusal vocabulary. Four codes classify a name a surface
resolved for itself and four classify the shared assignment judgement's own
verdicts, so a caller branches on the rule that fired rather than on wording."""

EDIT_CODE_BY_RULE: Final[Mapping[str, str]] = MappingProxyType(
    {
        "primary-key": "edit-primary-key",
        "read-only": "edit-read-only",
        "framework-owned": "edit-framework-owned",
        "value-type-mismatch": "edit-value-mismatch",
    }
)
"""The edit code reporting each classification the shared assignment judgement
raises. Every surface translates through this one mapping, so the judgement owns
the rule and the edit surface owns only its own spelling of it."""


@dataclass(frozen=True, slots=True)
class EditViolation:
    """One refused assignment, located in the model's own vocabulary.

    ``code`` is a member of :data:`EDIT_CODES`. ``location`` is the resolved
    member's own — Attribute, Relationship, Value Object occurrence, or a scalar
    inside one — or the :class:`~parallax.core.metamodel.EntityLocation` of the
    Entity whose declaration was searched when the authored name reached no
    member; a location is never absent, because a member location would have to
    name a member the model does not declare. ``member_name`` carries the
    resolved member's canonical name, the authored name when none resolved, and
    is absent for a refusal that examines no member at all.

    ``message`` is explanatory and excluded from equality, exactly as a
    Metamodel Issue's is: two surfaces refusing the same assignment at the same
    position produce one violation identity whatever each one's wording.
    """

    code: str
    location: ModelLocation
    member_name: str | None = None
    message: str = field(default="", compare=False)


class EditError(ValueError):
    """Every assignment rule the authored edit breaks, in one report.

    One class covers both authoring surfaces — ``Entity.edit(**changes)`` and a
    predicate write's ``Attr.set(...)`` — because the assignment rules are one
    set with one home. ``.set(...)`` names one target and therefore always
    carries exactly one violation; an edit names as many as the caller wrote and
    reports each member's own first verdict, so correcting an edit takes one
    round trip rather than one per mistake.

    ``violations`` is nonempty and canonically ordered by location, then code,
    then member name with an unset name first, so a report never depends on
    caller keyword order. There is deliberately no ``code`` attribute:
    selecting one violation to expose would misreport the others, which is what
    ``codes`` is for. Constructing one with no violation raises
    :class:`ValueError` — a refusal that names no rule is not a report.
    """

    violations: tuple[EditViolation, ...]
    codes: frozenset[str]

    def __init__(self, violations: Sequence[EditViolation]) -> None:
        reported = tuple(sorted(violations, key=_canonical_violation_key))
        if not reported:
            raise ValueError("an edit refusal reports at least one violation")
        self.violations = reported
        self.codes = frozenset(violation.code for violation in reported)
        summary = ", ".join(sorted(self.codes))
        detail = "".join(f"\n  {violation.code}: {violation.message}" for violation in reported)
        super().__init__(f"{len(reported)} edit violation(s): {summary}{detail}")


def _canonical_violation_key(violation: EditViolation) -> tuple[ModelLocationKey, str, bool, str]:
    """The sort key placing ``violation`` in canonical order.

    The first two terms order accumulated Metamodel Issues as well; the third and
    fourth exist because two names that reached no member share one Entity
    location and one code, and would otherwise tie into caller keyword order.
    """
    return (
        canonical_location_key(violation.location),
        violation.code,
        violation.member_name is not None,
        violation.member_name or "",
    )
