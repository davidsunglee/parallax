"""Storage Layout's Candidate Metamodel collision Rule Set."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from parallax.core.inheritance import InheritanceTableGroup, project_table_groups
from parallax.core.metamodel import (
    CandidateMetamodel,
    Column,
    IssueCode,
    MetamodelIssue,
    ModelLocation,
    Table,
)
from parallax.core.model_formation import ModuleIdentity

__all__ = [
    "COLUMN_COLLISION",
    "ISSUE_CODES",
    "RULE_SET",
    "STORAGE_LAYOUT_MODULE",
    "TABLE_MAPPING_COLLISION",
    "StorageLayoutRuleSet",
    "validate_storage_layout",
]

STORAGE_LAYOUT_MODULE: Final[ModuleIdentity] = "m-storage-layout"
"""The module identity owning physical Table composition and collisions."""

TABLE_MAPPING_COLLISION: Final[IssueCode] = "storage-layout-table-mapping-collision"
"""A later independent mapping owner names an already-owned structural Table."""

COLUMN_COLLISION: Final[IssueCode] = "storage-layout-column-collision"
"""Two distinct contributors in one uniquely owned Table claim one Column."""

ISSUE_CODES: Final[frozenset[IssueCode]] = frozenset({TABLE_MAPPING_COLLISION, COLUMN_COLLISION})
"""The complete Issue Code set owned by Storage Layout."""


def _column_issues(group: InheritanceTableGroup) -> list[MetamodelIssue]:
    claimed: dict[Column, ModelLocation] = {}
    issues: list[MetamodelIssue] = []
    for contributor in group.declaration_contributors:
        existing = claimed.get(contributor.column)
        if existing is None:
            claimed[contributor.column] = contributor.location
            continue
        issues.append(
            MetamodelIssue(
                COLUMN_COLLISION,
                contributor.location,
                (existing,),
                message=(
                    f"physical Column {contributor.column.name!r} is already claimed "
                    f"in Table {group.table.name!r}"
                ),
            )
        )
    return issues


def validate_storage_layout(candidate: CandidateMetamodel) -> tuple[MetamodelIssue, ...]:
    """Report deterministic independent-owner and physical-Column collisions.

    Mapping owners are visited in canonical Entity Identity order. Every later
    owner of one Table relates to the first owner, and a multiply owned Table is
    excluded from Column validation so no secondary diagnostic obscures its
    invalid physical boundary. The complete mapping pass finishes before any
    uniquely owned Table enters Column validation.
    """
    groups = project_table_groups(candidate)
    first_owners: dict[Table, InheritanceTableGroup] = {}
    multiply_owned: set[Table] = set()
    issues: list[MetamodelIssue] = []
    for group in groups:
        first = first_owners.get(group.table)
        if first is None:
            first_owners[group.table] = group
            continue
        multiply_owned.add(group.table)
        issues.append(
            MetamodelIssue(
                TABLE_MAPPING_COLLISION,
                group.mapping_provenance,
                (first.mapping_provenance,),
                message=(
                    f"Table {group.table.name!r} is already mapped by independent owner "
                    f"{first.mapping_owner.canonical!r}"
                ),
            )
        )
    for group in groups:
        if group.table not in multiply_owned:
            issues.extend(_column_issues(group))
    return tuple(issues)


class StorageLayoutRuleSet:
    """The Storage Layout Model Formation Rule Set."""

    __slots__ = ()

    @property
    def owner(self) -> ModuleIdentity:
        """The catalog identity owning this Rule Set."""
        return STORAGE_LAYOUT_MODULE

    @property
    def issue_codes(self) -> frozenset[IssueCode]:
        """The complete code set every emission is held to."""
        return ISSUE_CODES

    def validate(self, candidate: CandidateMetamodel) -> Sequence[MetamodelIssue]:
        """Validate ``candidate`` without consuming any compiled facet."""
        return validate_storage_layout(candidate)


RULE_SET: Final[StorageLayoutRuleSet] = StorageLayoutRuleSet()
"""The stateless Rule Set instance supplied by the built-in profile."""
