"""Storage Layout's Candidate Metamodel collision and capability Rule Set."""

from __future__ import annotations

from collections.abc import Callable, Sequence
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
    AbstractRoot,
    AttributeIdentity,
    AttributeLocation,
    AttributeMetadata,
    CandidateMetamodel,
    Column,
    Document,
    EntityDeclaration,
    EntityIdentity,
    EntityLocation,
    IndexLocation,
    InheritanceStrategy,
    IssueCode,
    MetamodelIssue,
    ModelLocation,
    Table,
    TablePerConcreteSubtype,
    TablePerHierarchy,
    TemporalDimension,
)
from parallax.core.model_formation import ModuleIdentity
from parallax.core.relationship import project_join_endpoints
from parallax.core.storage_layout._roles import DirectRoles, declares_column_override

__all__ = [
    "CAPABILITY_SCOPE",
    "COLUMN_COLLISION",
    "DOCUMENT_CAPABILITY_UNSUPPORTED",
    "DOCUMENT_MEMBER_COLUMN_OVERRIDE",
    "INDEX_OVER_DOCUMENT_MEMBER",
    "ISSUE_CODES",
    "RULE_SET",
    "STORAGE_LAYOUT_MODULE",
    "TABLE_MAPPING_COLLISION",
    "CapabilityScopeEntry",
    "DocumentLayoutOwner",
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

DOCUMENT_CAPABILITY_UNSUPPORTED: Final[IssueCode] = "storage-layout-document-capability-unsupported"
"""A root-owned Relational Document Layout selects a shape this build cannot
execute end to end. The code exists only while :data:`CAPABILITY_SCOPE` is
non-empty; emptying the scope retires the rule and this code with it."""


@dataclass(frozen=True, slots=True)
class DocumentLayoutOwner:
    """One accepted root-owned ``Document`` declaration and the mapping it governs.

    ``strategy`` is the family's root-owned inheritance strategy, or absent for a
    standalone Entity. ``attributes`` is every Attribute contributing to the
    Tables this layout governs — one Table for a standalone Entity or a
    table-per-hierarchy family, one per concrete Entity under
    table-per-concrete-subtype — which is the set the direct-column roles are
    stated over. ``joined`` names the Attributes an accepted Relationship Join
    designates anywhere in the model.
    """

    owner: EntityDeclaration
    layout: Document
    strategy: InheritanceStrategy | None
    attributes: tuple[AttributeMetadata, ...]
    joined: frozenset[AttributeIdentity]

    @property
    def axes(self) -> frozenset[TemporalDimension]:
        """The temporal axes the layout owner declares; empty when non-temporal."""
        return frozenset(axis.dimension for axis in self.owner.as_of_axes)


def _is_standalone(owner: DocumentLayoutOwner) -> bool:
    return owner.strategy is None


def _is_table_per_hierarchy(owner: DocumentLayoutOwner) -> bool:
    return isinstance(owner.strategy, TablePerHierarchy)


def _is_table_per_concrete_subtype(owner: DocumentLayoutOwner) -> bool:
    return isinstance(owner.strategy, TablePerConcreteSubtype)


def _joins_a_relationship(owner: DocumentLayoutOwner) -> bool:
    return any(attribute.identity in owner.joined for attribute in owner.attributes)


def _locks_optimistically(owner: DocumentLayoutOwner) -> bool:
    return any(attribute.optimistic_locking for attribute in owner.attributes)


def _is_transaction_time_only(owner: DocumentLayoutOwner) -> bool:
    return owner.axes == frozenset({TemporalDimension.TRANSACTION_TIME})


def _is_bitemporal(owner: DocumentLayoutOwner) -> bool:
    return TemporalDimension.VALID_TIME in owner.axes


@dataclass(frozen=True, slots=True)
class CapabilityScopeEntry:
    """One layout shape this build declares it cannot execute end to end.

    ``shape`` names the shape in the diagnostic and ``matches`` decides it over
    an accepted root-owned declaration. An entry is deleted whole once the build
    executes that shape's reads and writes alike.
    """

    shape: str
    matches: Callable[[DocumentLayoutOwner], bool]


CAPABILITY_SCOPE: Final[tuple[CapabilityScopeEntry, ...]] = (
    CapabilityScopeEntry("a standalone Entity", _is_standalone),
    CapabilityScopeEntry("a table-per-hierarchy family", _is_table_per_hierarchy),
    CapabilityScopeEntry("a table-per-concrete-subtype family", _is_table_per_concrete_subtype),
    CapabilityScopeEntry("an Attribute named by a Relationship Join", _joins_a_relationship),
    CapabilityScopeEntry("an explicit optimistic-lock Attribute", _locks_optimistically),
    CapabilityScopeEntry("a Transaction-Time axis", _is_transaction_time_only),
    CapabilityScopeEntry("a Bitemporal axis pair", _is_bitemporal),
)
"""The closed set of layout shapes this build refuses.

Each entry is a predicate over one accepted root-owned ``Document``
declaration. The list shrinks as the runtime widens, and the last deletion takes
:data:`DOCUMENT_CAPABILITY_UNSUPPORTED` and this rule with it: an empty scope
refuses nothing and is not a supported state.
"""

ISSUE_CODES: Final[frozenset[IssueCode]] = frozenset(
    {
        TABLE_MAPPING_COLLISION,
        COLUMN_COLLISION,
        DOCUMENT_MEMBER_COLUMN_OVERRIDE,
        INDEX_OVER_DOCUMENT_MEMBER,
        DOCUMENT_CAPABILITY_UNSUPPORTED,
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


def _strategy(owner: EntityDeclaration) -> InheritanceStrategy | None:
    return owner.inheritance.strategy if isinstance(owner.inheritance, AbstractRoot) else None


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


def _member_name(contributor: TableGroupContributor) -> str | None:
    """The canonical member name ``contributor`` declares, or absence when framework-owned."""
    match contributor:
        case AttributeTableContributor():
            return contributor.attribute.identity.name
        case TopLevelValueObjectTableContributor():
            return contributor.identity.path[-1]
        case _:
            return None


def _is_document_resident(contributor: TableGroupContributor, roles: DirectRoles) -> bool:
    """Whether ``contributor``'s member lives in the shared Structured Column."""
    match contributor:
        case AttributeTableContributor():
            return not roles.covers(contributor.attribute)
        case TopLevelValueObjectTableContributor():
            return True
        case _:
            return False


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
            if not _is_document_resident(contributor, document.roles)
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
            name = _member_name(contributor)
            if name is None or not _is_document_resident(contributor, document.roles):
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
            if _is_document_resident(contributor, document.roles):
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


def _layout_owners(
    candidate: CandidateMetamodel, document_groups: Sequence[_DocumentGroup]
) -> tuple[DocumentLayoutOwner, ...]:
    """The accepted root-owned ``Document`` declarations, one per layout owner.

    A table-per-concrete-subtype family projects one group per concrete Table
    under one root, so the groups are folded back onto their owner and the gate
    fires once per layout declaration rather than once per governed Table.
    """
    governed: dict[EntityIdentity, list[AttributeMetadata]] = {}
    layouts: dict[EntityIdentity, Document] = {}
    joined: frozenset[AttributeIdentity] = frozenset()
    for document in document_groups:
        joined = document.roles.joined
        layouts[document.group.root] = document.layout
        governed.setdefault(document.group.root, []).extend(
            contributor.attribute
            for contributor in document.group.declaration_contributors
            if isinstance(contributor, AttributeTableContributor)
        )
    owners: list[DocumentLayoutOwner] = []
    for identity in sorted(layouts, key=lambda entity: entity.sort_key):
        declaration = candidate.entity(identity)
        if declaration is None:  # pragma: no cover - the group projected this root
            continue
        owners.append(
            DocumentLayoutOwner(
                owner=declaration,
                layout=layouts[identity],
                strategy=_strategy(declaration),
                attributes=tuple(governed[identity]),
                joined=joined,
            )
        )
    return tuple(owners)


def _capability_issue(owner: DocumentLayoutOwner) -> MetamodelIssue | None:
    """The gate diagnostic for ``owner``, or absence when this build executes it."""
    refused = [entry.shape for entry in CAPABILITY_SCOPE if entry.matches(owner)]
    if not refused:
        return None
    return MetamodelIssue(
        DOCUMENT_CAPABILITY_UNSUPPORTED,
        EntityLocation(owner.owner.identity),
        message=(
            f"Relational Document Layout over Structured Column "
            f"{owner.layout.column.name!r} is not executable by this build: "
            f"{', '.join(refused)}"
        ),
    )


def validate_storage_layout(candidate: CandidateMetamodel) -> tuple[MetamodelIssue, ...]:
    """Report independent-owner, physical-Column, layout, and capability defects.

    Mapping owners are visited in canonical Entity Identity order. Every later
    owner of one Table relates to the first owner, and a multiply owned Table is
    excluded from Column validation so no secondary diagnostic obscures its
    invalid physical boundary. The complete mapping pass finishes before any
    uniquely owned Table enters Column validation.

    The capability gate runs last and skips a layout owner whose own mapping
    raised anything above, so a model with a genuine layout defect reports that
    defect rather than a refusal to execute the layout it does not yet have.
    """
    groups = project_table_groups(candidate)
    document_groups = _document_groups(candidate, groups, project_join_endpoints(candidate))
    documents_by_table = {document.group.table: document for document in document_groups}
    first_owners: dict[Table, InheritanceTableGroup] = {}
    multiply_owned: set[Table] = set()
    defective: set[EntityIdentity] = set()
    issues: list[MetamodelIssue] = []
    for group in groups:
        first = first_owners.get(group.table)
        if first is None:
            first_owners[group.table] = group
            continue
        multiply_owned.add(group.table)
        defective.update((group.root, first.root))
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
        if column_issues:
            defective.add(group.root)
        issues.extend(column_issues)
    for owner, issue in (
        *_override_issues(document_groups),
        *_index_issues(candidate, document_groups),
    ):
        defective.add(owner)
        issues.append(issue)
    for owner in _layout_owners(candidate, document_groups):
        if owner.owner.identity in defective:
            continue
        capability = _capability_issue(owner)
        if capability is not None:
            issues.append(capability)
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
