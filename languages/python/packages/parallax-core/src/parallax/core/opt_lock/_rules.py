"""The optimistic-locking Model Formation Rule Set (m-opt-lock).

Two things make a version undeterminable, and both are statements about one
declaring position: naming more than one version Attribute, and naming a version
Attribute on a family whose version is already the Transaction-Time milestone
start. Neither reads an ancestry, because a version Attribute and an As-Of Axis
are both root-owned facts that ``m-inheritance`` rejects on a descendant — so the
effective set of either is the declaring position's own, and checking a chain
here would report one defect once per position that inherits it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from parallax.core.metamodel import (
    AsOfAxisLocation,
    AttributeLocation,
    AttributeMetadata,
    CandidateMetamodel,
    EntityDeclaration,
    EntityLocation,
    IssueCode,
    MetamodelIssue,
    ModelLocation,
    TemporalDimension,
)
from parallax.core.model_formation import ModuleIdentity
from parallax.core.opt_lock._facet import OPT_LOCK_MODULE

__all__ = [
    "ISSUE_CODES",
    "MULTIPLE_ATTRIBUTES",
    "RULE_SET",
    "TEMPORAL_EXPLICIT_ATTRIBUTE",
    "OptimisticLockRuleSet",
    "validate_optimistic_locking",
]

MULTIPLE_ATTRIBUTES: Final[IssueCode] = "opt-lock-multiple-attributes"
"""A position declares more than one version Attribute, so no single value
identifies the row's version to gate on or advance."""

TEMPORAL_EXPLICIT_ATTRIBUTE: Final[IssueCode] = "opt-lock-temporal-explicit-attribute"
"""A Transaction-Time position also declares a version Attribute. Its milestone
start is already the version, so a second one would be a competing key."""

ISSUE_CODES: Final[frozenset[IssueCode]] = frozenset(
    {MULTIPLE_ATTRIBUTES, TEMPORAL_EXPLICIT_ATTRIBUTE}
)
"""This module's complete owned Issue Code set, as the Formation Manifest
declares it."""


def _version_attributes(declaration: EntityDeclaration) -> tuple[AttributeMetadata, ...]:
    """The Attributes ``declaration`` marks as its version, in declaration order."""
    return tuple(member for member in declaration.attributes if member.optimistic_locking)


def _entity_issues(declaration: EntityDeclaration) -> list[MetamodelIssue]:
    """The optimistic-locking defects of one declaring position."""
    versions = _version_attributes(declaration)
    if not versions:
        return []
    issues: list[MetamodelIssue] = []
    if len(versions) > 1:
        issues.append(
            MetamodelIssue(
                MULTIPLE_ATTRIBUTES,
                EntityLocation(declaration.identity),
                tuple(AttributeLocation(member.identity) for member in versions),
                message=f"{len(versions)} version Attributes are declared; at most one is allowed",
            )
        )
    transaction_time = next(
        (
            axis
            for axis in declaration.as_of_axes
            if axis.dimension is TemporalDimension.TRANSACTION_TIME
        ),
        None,
    )
    if transaction_time is None:
        return issues
    related: tuple[ModelLocation, ...] = (
        AsOfAxisLocation(declaration.identity, TemporalDimension.TRANSACTION_TIME),
    )
    issues.extend(
        MetamodelIssue(
            TEMPORAL_EXPLICIT_ATTRIBUTE,
            AttributeLocation(member.identity),
            related,
            message="a Transaction-Time Entity derives its version from its milestone start",
        )
        for member in versions
    )
    return issues


def validate_optimistic_locking(candidate: CandidateMetamodel) -> tuple[MetamodelIssue, ...]:
    """Every optimistic-locking defect of ``candidate``, reported rather than the first."""
    return tuple(issue for entity in candidate.entities for issue in _entity_issues(entity))


class OptimisticLockRuleSet:
    """This module's Model Formation Rule Set: issues only, never a facet."""

    __slots__ = ()

    @property
    def owner(self) -> ModuleIdentity:
        """The catalog identity that owns this Rule Set and its Issue Codes."""
        return OPT_LOCK_MODULE

    @property
    def issue_codes(self) -> frozenset[IssueCode]:
        """The complete owned code set every emission is held to."""
        return ISSUE_CODES

    def validate(self, candidate: CandidateMetamodel) -> Sequence[MetamodelIssue]:
        """Report every optimistic-locking defect ``candidate`` carries."""
        return validate_optimistic_locking(candidate)


RULE_SET: Final[OptimisticLockRuleSet] = OptimisticLockRuleSet()
"""The single Rule Set instance a composition root supplies.

It is stateless, so one instance serves every formation; the constant exists so
a profile names the Rule Set rather than constructing a second one."""
