"""The Value Object Model Formation Rule Set (m-value-object).

Everything this module rejects is a statement about a declared composite shape
rather than about how it is stored: whether a shape has any member at all,
whether the reusable shape graph is acyclic, and whether an occurrence's
multiplicity and nullability can both be honored. Name collisions inside a shape
are not here — foundational resolution owns them.

The walk descends occurrence declarations rather than the shape graph alone,
because every diagnostic names the containment path a reader authored. Reuse of
one shape at several disjoint paths is legal and expands to distinct occurrence
trees, so only a shape reached twice on a single path is a cycle; descent stops
there, which is also what keeps the walk finite.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from parallax.core.metamodel import (
    CandidateMetamodel,
    EntityIdentity,
    IssueCode,
    MetamodelIssue,
    ModelLocation,
    Multiplicity,
    ValueObjectIdentity,
    ValueObjectLocation,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
)
from parallax.core.model_formation import ModuleIdentity

__all__ = [
    "CONTAINMENT_CYCLE",
    "EMPTY",
    "ISSUE_CODES",
    "MANY_NULLABLE",
    "RULE_SET",
    "VALUE_OBJECT_MODULE",
    "ValueObjectRuleSet",
    "validate_value_objects",
]

VALUE_OBJECT_MODULE: Final[ModuleIdentity] = "m-value-object"
"""The catalog identity that owns Value Object formation and its Issue Codes."""

EMPTY: Final[IssueCode] = "value-object-empty"
"""An occurrence's shape declares neither a scalar Attribute nor a nested
occurrence, so the composite has no value to carry and its containment tree
reaches no scalar leaf."""

CONTAINMENT_CYCLE: Final[IssueCode] = "value-object-containment-cycle"
"""A shape contains itself, directly or through other shapes, so the composite
it describes has no finite document form."""

MANY_NULLABLE: Final[IssueCode] = "value-object-many-nullable"
"""A Many occurrence is nullable. Many is a possibly-empty non-null collection,
so null and empty would be two spellings of one state."""

ISSUE_CODES: Final[frozenset[IssueCode]] = frozenset({EMPTY, CONTAINMENT_CYCLE, MANY_NULLABLE})
"""This module's complete owned Issue Code set, as the Formation Manifest
declares it."""

type _Enclosing = tuple[tuple[ValueObjectShapeKey, ValueObjectIdentity], ...]
"""The shapes currently being expanded, outermost first, each with the
occurrence that introduced it."""


def _cycle(key: ValueObjectShapeKey, enclosing: _Enclosing) -> tuple[ModelLocation, ...] | None:
    """The containment loop ``key`` closes over ``enclosing``, if it closes one.

    The loop runs from the outermost occurrence that already expands this shape
    down to the occurrence that contains the repeat, so the report names every
    step of the cycle rather than only the two ends.
    """
    for index, (expanding, _) in enumerate(enclosing):
        if expanding == key:
            return tuple(ValueObjectLocation(identity) for _, identity in enclosing[index:])
    return None


def _occurrence_issues(
    entity: EntityIdentity,
    path: tuple[str, ...],
    shape: ValueObjectShapeDeclaration,
    multiplicity: Multiplicity,
    nullable: bool,
    enclosing: _Enclosing,
) -> list[MetamodelIssue]:
    """The defects of the occurrence at ``path`` and of everything below it."""
    identity = ValueObjectIdentity(entity, path)
    location = ValueObjectLocation(identity)
    issues: list[MetamodelIssue] = []
    if multiplicity is Multiplicity.MANY and nullable:
        issues.append(
            MetamodelIssue(
                MANY_NULLABLE,
                location,
                message="a Many occurrence is a possibly-empty collection and is never nullable",
            )
        )
    closed = _cycle(shape.key, enclosing)
    if closed is not None:
        issues.append(
            MetamodelIssue(
                CONTAINMENT_CYCLE,
                location,
                closed,
                message="this occurrence expands a shape that already contains it",
            )
        )
        return issues
    if not shape.attributes and not shape.value_objects:
        issues.append(
            MetamodelIssue(
                EMPTY,
                location,
                message="this occurrence declares neither an Attribute nor a nested occurrence",
            )
        )
    below = (*enclosing, (shape.key, identity))
    for nested in shape.value_objects:
        issues.extend(
            _occurrence_issues(
                entity,
                (*path, nested.name),
                nested.shape,
                nested.multiplicity,
                nested.nullable,
                below,
            )
        )
    return issues


def validate_value_objects(candidate: CandidateMetamodel) -> tuple[MetamodelIssue, ...]:
    """Every Value Object defect of ``candidate``, reported rather than the first."""
    issues: list[MetamodelIssue] = []
    for entity in candidate.entities:
        for occurrence in entity.value_objects:
            issues.extend(
                _occurrence_issues(
                    entity.identity,
                    (occurrence.name,),
                    occurrence.shape,
                    occurrence.multiplicity,
                    occurrence.nullable,
                    (),
                )
            )
    return tuple(issues)


class ValueObjectRuleSet:
    """This module's Model Formation Rule Set: issues only, and no facet.

    Accepted occurrences are expanded into path-identified Metadata by the
    mandatory Metadata Compiler, so this module contributes no compiler of its
    own and holds no derived view.
    """

    __slots__ = ()

    @property
    def owner(self) -> ModuleIdentity:
        """The catalog identity that owns this Rule Set and its Issue Codes."""
        return VALUE_OBJECT_MODULE

    @property
    def issue_codes(self) -> frozenset[IssueCode]:
        """The complete owned code set every emission is held to."""
        return ISSUE_CODES

    def validate(self, candidate: CandidateMetamodel) -> Sequence[MetamodelIssue]:
        """Report every Value Object defect ``candidate`` carries."""
        return validate_value_objects(candidate)


RULE_SET: Final[ValueObjectRuleSet] = ValueObjectRuleSet()
"""The single Rule Set instance a composition root supplies.

It is stateless, so one instance serves every formation; the constant exists so
a profile names the Rule Set rather than constructing a second one."""
