from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal

from parallax.core.internal.base import UsageError
from parallax.core.internal.metamodel import (
    WRITE_ASSIGNMENT_FRAMEWORK_OWNED,
    WRITE_ASSIGNMENT_PRIMARY_KEY,
    WRITE_ASSIGNMENT_READ_ONLY,
    WRITE_ASSIGNMENT_VALUE_TYPE_MISMATCH,
    canonical_location_key,
)

if TYPE_CHECKING:
    from parallax.core.internal.metamodel import ModelLocation, ModelLocationKey

__all__ = [
    "EDIT_CODES",
    "EDIT_CODE_BY_RULE",
    "ENTITY_ANNOTATION_INVALID",
    "ENTITY_BASE_INVALID",
    "ENTITY_CANONICAL_NAME_COLLISION",
    "ENTITY_GRAPH_INVALID_ENTITY",
    "ENTITY_GRAPH_INVALID_MEMBER",
    "ENTITY_GRAPH_INVALID_VALUE",
    "ENTITY_GRAPH_LAYOUT_MISMATCH",
    "ENTITY_HEADER_INVALID_VALUE",
    "ENTITY_HEADER_MISSING_OPTION",
    "ENTITY_HEADER_UNKNOWN_OPTION",
    "ENTITY_MEMBER_VALUE_INVALID",
    "ENTITY_OPTION_CONTEXT_INVALID",
    "ENTITY_OPTION_INVALID_VALUE",
    "ENTITY_RELATIONSHIP_ANNOTATION_MISMATCH",
    "ENTITY_RESERVED_MEMBER_NAME",
    "ENTITY_ROW_MALFORMED_PROVENANCE",
    "ENTITY_ROW_MEMBER_MISSING",
    "METAMODEL_DUPLICATE_ENTITY_CLASS",
    "METAMODEL_EMPTY",
    "METAMODEL_ENTITY_NOT_FOUND",
    "METAMODEL_INVALID_ENTITY_CLASS",
    "METAMODEL_INVALID_ENTITY_REFERENCE",
    "EditError",
    "EditViolation",
    "EntityDefinitionCode",
    "EntityRowCode",
    "GraphConstructionCode",
    "MetamodelDefinitionCode",
    "MetamodelLookupCode",
    "UnloadedRelationshipError",
]

type EntityDefinitionCode = Literal[
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
]
"""The declaration refusals the Python grammar raises as a
:class:`~parallax.core.internal.base.UsageError`. Ten fire at a factory call or at class
creation; ``entity-relationship-annotation-mismatch`` fires in the Domain Model
constructor's Python realization phase."""

ENTITY_HEADER_UNKNOWN_OPTION: Final = "entity-header-unknown-option"
ENTITY_HEADER_INVALID_VALUE: Final = "entity-header-invalid-value"
ENTITY_HEADER_MISSING_OPTION: Final = "entity-header-missing-option"
ENTITY_BASE_INVALID: Final = "entity-base-invalid"
ENTITY_ANNOTATION_INVALID: Final = "entity-annotation-invalid"
ENTITY_MEMBER_VALUE_INVALID: Final = "entity-member-value-invalid"
ENTITY_OPTION_INVALID_VALUE: Final = "entity-option-invalid-value"
ENTITY_OPTION_CONTEXT_INVALID: Final = "entity-option-context-invalid"
ENTITY_RESERVED_MEMBER_NAME: Final = "entity-reserved-member-name"
ENTITY_CANONICAL_NAME_COLLISION: Final = "entity-canonical-name-collision"
ENTITY_RELATIONSHIP_ANNOTATION_MISMATCH: Final = "entity-relationship-annotation-mismatch"

type MetamodelDefinitionCode = Literal[
    "metamodel-empty", "metamodel-invalid-entity-class", "metamodel-duplicate-entity-class"
]
"""The malformed Domain Model constructor calls, refused as a
:class:`~parallax.core.internal.base.UsageError` before any model exists. Two distinct
classes declaring one Entity Identity are valid input here and become a
whole-model issue instead."""

METAMODEL_EMPTY: Final = "metamodel-empty"
"""A Domain Model was constructed over no source at all."""
METAMODEL_INVALID_ENTITY_CLASS: Final = "metamodel-invalid-entity-class"
"""A constructor argument is not a domain Entity Class."""
METAMODEL_DUPLICATE_ENTITY_CLASS: Final = "metamodel-duplicate-entity-class"
"""One class object was passed to the constructor more than once."""

type MetamodelLookupCode = Literal[
    "metamodel-invalid-entity-reference", "metamodel-entity-not-found"
]
"""The ``models.entity(...)`` lookups that find no Entity, refused as a
:class:`~parallax.core.internal.base.UsageError`. The class-free lookup protocol returns
absence instead."""

METAMODEL_INVALID_ENTITY_REFERENCE: Final = "metamodel-invalid-entity-reference"
"""A lookup string is not a canonical Entity spelling."""
METAMODEL_ENTITY_NOT_FOUND: Final = "metamodel-entity-not-found"
"""A well-formed lookup key names no Entity of this model."""

type GraphConstructionCode = Literal[
    "entity-graph-invalid-entity",
    "entity-graph-invalid-member",
    "entity-graph-invalid-value",
    "entity-graph-layout-mismatch",
]
"""The ways the advanced Entity Graph Construction collaboration is driven
outside its contract, each an :class:`~parallax.core.internal.base.InternalError`
naming the node and the identity at fault in its message. The collaboration
checks every one itself, so no misuse of it surfaces as an assertion, a
:class:`LookupError`, or a partially built graph."""

ENTITY_GRAPH_INVALID_ENTITY: Final = "entity-graph-invalid-entity"
ENTITY_GRAPH_INVALID_MEMBER: Final = "entity-graph-invalid-member"
ENTITY_GRAPH_INVALID_VALUE: Final = "entity-graph-invalid-value"
ENTITY_GRAPH_LAYOUT_MISMATCH: Final = "entity-graph-layout-mismatch"

type EntityRowCode = Literal["entity-row-member-missing", "entity-row-malformed-provenance"]
"""The values a Typed write cannot read as the row it resolved. Every code names
a value its write could not read, so no misuse surfaces as an
:class:`AttributeError`, a :class:`KeyError`, or a partially keyed row."""

ENTITY_ROW_MEMBER_MISSING: Final = "entity-row-member-missing"
"""An operation selected a member it cannot emit: either the resolved identity
does not declare it, or the value's class carries no attribute for one it does.
A :class:`~parallax.core.internal.base.UsageError`, because a caller reaches it by
handing a write an instance of another model's class."""
ENTITY_ROW_MALFORMED_PROVENANCE: Final = "entity-row-malformed-provenance"
"""The private Change Record slot holds something that is not a Change Record.
An :class:`~parallax.core.internal.base.InternalError`, because only first-party code
writes that slot."""


class UnloadedRelationshipError(UsageError, AttributeError):
    """A relationship the read did not load was accessed; add it with `.include(...)`.

    Also an :class:`AttributeError`, so ``hasattr`` and ``getattr`` with a
    default treat an unloaded relationship as absent.
    """

    def __init__(self, path: str) -> None:
        super().__init__(
            "relationship-unloaded",
            f"{path!r} was not included in this find; add `.include({path})` "
            "to fetch it (this snapshot lifecycle never lazy-loads)",
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
        WRITE_ASSIGNMENT_PRIMARY_KEY: "edit-primary-key",
        WRITE_ASSIGNMENT_READ_ONLY: "edit-read-only",
        WRITE_ASSIGNMENT_FRAMEWORK_OWNED: "edit-framework-owned",
        WRITE_ASSIGNMENT_VALUE_TYPE_MISMATCH: "edit-value-mismatch",
    }
)
"""The edit code reporting each code the shared assignment judgement raises.
Every surface translates through this one mapping, so the judgement owns the
rule and the edit surface owns only its own spelling of it."""


@dataclass(frozen=True, slots=True)
class EditViolation:
    """One refused assignment, located in the model's own vocabulary.

    ``code`` is a member of :data:`EDIT_CODES`. ``location`` is the resolved
    member's own — Attribute, Relationship, Value Object occurrence, or a scalar
    inside one — or the :class:`~parallax.core.internal.metamodel.EntityLocation` of the
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


class EditError(UsageError):
    """An edit broke assignment rules; `violations` lists every one.

    Every assignment rule the authored edit breaks, in one report.

    One class covers both authoring surfaces — ``Entity.edit(**changes)`` and a
    predicate write's ``Attr.set(...)`` — because the assignment rules are one
    set with one home. ``.set(...)`` names one target and therefore always
    carries exactly one violation; an edit names as many as the caller wrote and
    reports each member's own first verdict, so correcting an edit takes one
    round trip rather than one per mistake.

    ``violations`` is nonempty and canonically ordered by location, then code,
    then member name with an unset name first, so a report never depends on
    caller keyword order. ``code`` is always ``edit-rejected``: selecting one
    violation's code to expose would misreport the others, which is what
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
        super().__init__("edit-rejected", f"{len(reported)} edit violation(s): {summary}{detail}")


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
