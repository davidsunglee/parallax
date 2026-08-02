"""Storage Layout's Candidate Metamodel collision and capability Rule Set."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

from parallax.core.inheritance import (
    AttributeTableContributor,
    InheritanceTableGroup,
    project_table_groups,
)
from parallax.core.metamodel import (
    AbstractRoot,
    AttributeIdentity,
    AttributeMetadata,
    CandidateMetamodel,
    Column,
    DefiningRelationshipDeclaration,
    Document,
    EntityDeclaration,
    EntityIdentity,
    EntityLocation,
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

__all__ = [
    "CAPABILITY_SCOPE",
    "COLUMN_COLLISION",
    "DOCUMENT_CAPABILITY_UNSUPPORTED",
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
    {TABLE_MAPPING_COLLISION, COLUMN_COLLISION, DOCUMENT_CAPABILITY_UNSUPPORTED}
)
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


def _joined_attributes(candidate: CandidateMetamodel) -> frozenset[AttributeIdentity]:
    """Every Attribute an accepted Relationship Join designates.

    Both endpoints of a defining declaration are read, because both stay direct
    Columns under Relational Document Layout; a reverse declaration introduces no
    Attribute its defining peer does not already name.
    """
    return frozenset(
        endpoint
        for declaration in candidate.entities
        for relationship in declaration.relationships
        if isinstance(relationship, DefiningRelationshipDeclaration)
        for endpoint in (relationship.join.source, relationship.join.target)
    )


def _strategy(owner: EntityDeclaration) -> InheritanceStrategy | None:
    return owner.inheritance.strategy if isinstance(owner.inheritance, AbstractRoot) else None


def _layout_owners(
    candidate: CandidateMetamodel, groups: Sequence[InheritanceTableGroup]
) -> tuple[DocumentLayoutOwner, ...]:
    """The accepted root-owned ``Document`` declarations of ``candidate``.

    Root ownership comes from the Inheritance projection: a group's root is the
    standalone Entity itself or its family root, so a descendant's own layout
    declaration is never seen here — that shape is Inheritance's
    ``inheritance-layout-not-root-owned``.
    """
    joined = _joined_attributes(candidate)
    governed: dict[EntityIdentity, list[AttributeMetadata]] = {}
    for group in groups:
        governed.setdefault(group.root, []).extend(
            contributor.attribute
            for contributor in group.declaration_contributors
            if isinstance(contributor, AttributeTableContributor)
        )
    owners: list[DocumentLayoutOwner] = []
    for identity, attributes in governed.items():
        declaration = candidate.entity(identity)
        if declaration is None or not isinstance(declaration.layout, Document):
            continue
        owners.append(
            DocumentLayoutOwner(
                owner=declaration,
                layout=declaration.layout,
                strategy=_strategy(declaration),
                attributes=tuple(attributes),
                joined=joined,
            )
        )
    owners.sort(key=lambda owner: owner.owner.identity.sort_key)
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
    """Report independent-owner, physical-Column, and layout-capability defects.

    Mapping owners are visited in canonical Entity Identity order. Every later
    owner of one Table relates to the first owner, and a multiply owned Table is
    excluded from Column validation so no secondary diagnostic obscures its
    invalid physical boundary. The complete mapping pass finishes before any
    uniquely owned Table enters Column validation.

    The capability gate runs last and skips a layout owner whose own Tables
    raised anything above, so a model with a genuine physical defect reports that
    defect rather than a refusal to execute the layout it does not yet have.
    """
    groups = project_table_groups(candidate)
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
        column_issues = _column_issues(group)
        if column_issues:
            defective.add(group.root)
        issues.extend(column_issues)
    for owner in _layout_owners(candidate, groups):
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
