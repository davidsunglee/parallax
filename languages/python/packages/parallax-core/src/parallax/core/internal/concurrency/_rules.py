from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from parallax.core.internal.concurrency._facet import CONCURRENCY_MODULE
from parallax.core.internal.metamodel import (
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
from parallax.core.internal.model_formation import ModuleIdentity

__all__ = [
    "ISSUE_CODES",
    "RULE_SET",
]

MULTIPLE_VERSION_ATTRIBUTES: Final[IssueCode] = "concurrency-multiple-version-attributes"
"""A position declares more than one version Attribute, so no single value
identifies the row's version to gate on or advance."""

TEMPORAL_EXPLICIT_VERSION: Final[IssueCode] = "concurrency-temporal-explicit-version"
"""A Transaction-Time position also declares a version Attribute. Its milestone
start is already the version, so a second one would be a competing key."""

ISSUE_CODES: Final[frozenset[IssueCode]] = frozenset(
    {MULTIPLE_VERSION_ATTRIBUTES, TEMPORAL_EXPLICIT_VERSION}
)
"""This module's complete owned Issue Code set, as the Formation Manifest
declares it."""


def _version_attributes(declaration: EntityDeclaration) -> tuple[AttributeMetadata, ...]:
    """The Attributes ``declaration`` marks as its version, in declaration order."""
    return tuple(member for member in declaration.attributes if member.optimistic_locking)


def _entity_issues(declaration: EntityDeclaration) -> list[MetamodelIssue]:
    """The version-declaration defects of one declaring position."""
    versions = _version_attributes(declaration)
    if not versions:
        return []
    issues: list[MetamodelIssue] = []
    if len(versions) > 1:
        issues.append(
            MetamodelIssue(
                MULTIPLE_VERSION_ATTRIBUTES,
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
            TEMPORAL_EXPLICIT_VERSION,
            AttributeLocation(member.identity),
            related,
            message="a Transaction-Time Entity derives its version from its milestone start",
        )
        for member in versions
    )
    return issues


def validate_version_declarations(candidate: CandidateMetamodel) -> tuple[MetamodelIssue, ...]:
    """Every version-declaration defect of ``candidate``, reported rather than the first."""
    return tuple(issue for entity in candidate.entities for issue in _entity_issues(entity))


class ConcurrencyRuleSet:
    """This module's Model Formation Rule Set: issues only, never a facet."""

    __slots__ = ()

    @property
    def owner(self) -> ModuleIdentity:
        """The catalog identity that owns this Rule Set and its Issue Codes."""
        return CONCURRENCY_MODULE

    @property
    def issue_codes(self) -> frozenset[IssueCode]:
        """The complete owned code set every emission is held to."""
        return ISSUE_CODES

    def validate(self, candidate: CandidateMetamodel) -> Sequence[MetamodelIssue]:
        """Report every version-declaration defect ``candidate`` carries."""
        return validate_version_declarations(candidate)


RULE_SET: Final[ConcurrencyRuleSet] = ConcurrencyRuleSet()
"""The single Rule Set instance a composition root supplies.

It is stateless, so one instance serves every formation; the constant exists so
a profile names the Rule Set rather than constructing a second one."""
