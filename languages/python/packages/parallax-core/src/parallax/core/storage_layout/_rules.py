"""Storage Layout's Candidate Metamodel collision and capability Rule Set."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from parallax.core.inheritance import (
    AttributeTableContributor,
    InheritanceTableGroup,
    TableGroupContributor,
    TopLevelValueObjectTableContributor,
    project_table_groups,
)
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeLocation,
    CandidateMetamodel,
    Column,
    Document,
    EntityDeclaration,
    EntityIdentity,
    EntityLocation,
    IndexLocation,
    IssueCode,
    MetamodelIssue,
    ModelLocation,
    Table,
)
from parallax.core.model_formation import ModuleIdentity
from parallax.core.relationship import project_join_endpoints
from parallax.core.storage_layout._roles import DirectRoles, declares_column_override

__all__ = [
    "COLUMN_COLLISION",
    "DOCUMENT_MEMBER_COLUMN_OVERRIDE",
    "INDEX_OVER_DOCUMENT_MEMBER",
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

DOCUMENT_MEMBER_COLUMN_OVERRIDE: Final[IssueCode] = "storage-layout-document-member-column-override"
"""A document-resident member carries a Column Override naming a Column it does
not occupy, so the model states two contradictory placements for one member."""

INDEX_OVER_DOCUMENT_MEMBER: Final[IssueCode] = "storage-layout-index-over-document-member"
"""An Index component names a document-resident Attribute, which has no Column to
index; this contract adds no document-path, expression, or provider-native index
form."""

ISSUE_CODES: Final[frozenset[IssueCode]] = frozenset(
    {
        TABLE_MAPPING_COLLISION,
        COLUMN_COLLISION,
        DOCUMENT_MEMBER_COLUMN_OVERRIDE,
        INDEX_OVER_DOCUMENT_MEMBER,
    }
)
"""The complete Issue Code set owned by Storage Layout."""


@dataclass(frozen=True, slots=True)
class _DocumentGroup:
    """One projected mapping group whose root selected a ``Document`` layout."""

    group: InheritanceTableGroup
    layout: Document
    roles: DirectRoles


def _temporal_designations(declaration: EntityDeclaration) -> frozenset[AttributeIdentity]:
    return frozenset(
        attribute
        for axis in declaration.as_of_axes
        for attribute in (axis.start_attribute, axis.end_attribute)
    )


def _document_groups(
    candidate: CandidateMetamodel,
    groups: Sequence[InheritanceTableGroup],
    joined: frozenset[AttributeIdentity],
) -> tuple[_DocumentGroup, ...]:
    """The projected groups governed by a root-owned ``Document`` declaration.

    Root ownership comes from the Inheritance projection: a group's root is the
    standalone Entity itself or its family root, so a descendant's own layout
    declaration is never seen here — that shape is Inheritance's
    ``inheritance-layout-not-root-owned``.
    """
    document_groups: list[_DocumentGroup] = []
    for group in groups:
        root = candidate.entity(group.root)
        if root is None or not isinstance(root.layout, Document):
            continue
        document_groups.append(
            _DocumentGroup(
                group=group,
                layout=root.layout,
                roles=DirectRoles(joined=joined, temporal=_temporal_designations(root)),
            )
        )
    return tuple(document_groups)


def _document_resident_member(contributor: TableGroupContributor, roles: DirectRoles) -> str | None:
    """``contributor``'s member name when it lives in the shared Structured Column.

    Absence covers both a member keeping a Column of its own and a framework-owned
    contributor declaring no member at all, which is one classification rather than
    two: naming and residency are decided together, so no contributor variant can
    answer one of them without answering the other.
    """
    match contributor:
        case AttributeTableContributor():
            if roles.covers(contributor.attribute):
                return None
            return contributor.attribute.identity.name
        case TopLevelValueObjectTableContributor():
            return contributor.identity.path[-1]
        case _:
            return None


def _claims(
    group: InheritanceTableGroup, document: _DocumentGroup | None
) -> tuple[tuple[Column, ModelLocation], ...]:
    """One group's physical Column claims, in diagnostic encounter order.

    Only contributors enter the registry. Under ``Document`` the Attribute and
    Value Object categories therefore contain the owner's direct-role Attributes
    alone, and the shared Structured Column is category five — always the later
    claimant, located at the layout declaration.
    """
    if document is None:
        return tuple(
            (contributor.column, contributor.location)
            for contributor in group.declaration_contributors
        )
    return (
        *(
            (contributor.column, contributor.location)
            for contributor in group.declaration_contributors
            if _document_resident_member(contributor, document.roles) is None
        ),
        (document.layout.column, EntityLocation(group.root)),
    )


def _column_issues(
    group: InheritanceTableGroup, document: _DocumentGroup | None
) -> list[MetamodelIssue]:
    claimed: dict[Column, ModelLocation] = {}
    issues: list[MetamodelIssue] = []
    for column, location in _claims(group, document):
        existing = claimed.get(column)
        if existing is None:
            claimed[column] = location
            continue
        issues.append(
            MetamodelIssue(
                COLUMN_COLLISION,
                location,
                (existing,),
                message=(
                    f"physical Column {column.name!r} is already claimed "
                    f"in Table {group.table.name!r}"
                ),
            )
        )
    return issues


def _override_issues(
    document_groups: Sequence[_DocumentGroup],
) -> list[tuple[EntityIdentity, MetamodelIssue]]:
    """The document-resident members whose Column Override contradicts the layout.

    A table-per-concrete-subtype family projects one group per concrete Table
    over one ancestry, so an ancestor's member is encountered once per branch and
    the defect is reported once.
    """
    reported: set[ModelLocation] = set()
    issues: list[tuple[EntityIdentity, MetamodelIssue]] = []
    for document in document_groups:
        owner = document.group.root
        for contributor in document.group.declaration_contributors:
            name = _document_resident_member(contributor, document.roles)
            if name is None:
                continue
            if not declares_column_override(name, contributor.column):
                continue
            if contributor.location in reported:
                continue
            reported.add(contributor.location)
            issues.append(
                (
                    owner,
                    MetamodelIssue(
                        DOCUMENT_MEMBER_COLUMN_OVERRIDE,
                        contributor.location,
                        (EntityLocation(owner),),
                        message=(
                            f"document-resident member {name!r} declares Column "
                            f"{contributor.column.name!r}, which it does not occupy"
                        ),
                    ),
                )
            )
    return issues


def _index_issues(
    candidate: CandidateMetamodel, document_groups: Sequence[_DocumentGroup]
) -> list[tuple[EntityIdentity, MetamodelIssue]]:
    """The Index components reaching into a shared Structured Column.

    Index Metadata is local and never inherited, so the model's declarations are
    walked once and each offending component is reported against the Index that
    must change.
    """
    resident: dict[AttributeIdentity, EntityIdentity] = {}
    for document in document_groups:
        for contributor in document.group.declaration_contributors:
            if not isinstance(contributor, AttributeTableContributor):
                continue
            if _document_resident_member(contributor, document.roles) is not None:
                resident.setdefault(contributor.attribute.identity, document.group.root)
    issues: list[tuple[EntityIdentity, MetamodelIssue]] = []
    for declaration in candidate.entities:
        for index in declaration.indices:
            for component in index.attributes:
                owner = resident.get(component)
                if owner is None:
                    continue
                issues.append(
                    (
                        owner,
                        MetamodelIssue(
                            INDEX_OVER_DOCUMENT_MEMBER,
                            IndexLocation(index.identity),
                            (AttributeLocation(component),),
                            message=(
                                f"Index {index.identity.name!r} names document-resident "
                                f"Attribute {component.name!r}, which has no Column"
                            ),
                        ),
                    )
                )
    return issues


def validate_storage_layout(candidate: CandidateMetamodel) -> tuple[MetamodelIssue, ...]:
    """Report independent-owner, physical-Column, and layout defects.

    Mapping owners are visited in canonical Entity Identity order. Every later
    owner of one Table relates to the first owner, and a multiply owned Table is
    excluded from Column validation so no secondary diagnostic obscures its
    invalid physical boundary. The complete mapping pass finishes before any
    uniquely owned Table enters Column validation.

    """
    groups = project_table_groups(candidate)
    document_groups = _document_groups(candidate, groups, project_join_endpoints(candidate))
    documents_by_table = {document.group.table: document for document in document_groups}
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
        if group.table in multiply_owned:
            continue
        column_issues = _column_issues(group, documents_by_table.get(group.table))
        issues.extend(column_issues)
    for _, issue in (
        *_override_issues(document_groups),
        *_index_issues(candidate, document_groups),
    ):
        issues.append(issue)
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
