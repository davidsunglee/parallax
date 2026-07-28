"""Validation-time inheritance topology and physical Table-group projection.

The projection is deliberately earlier than the Inheritance Facet. It accepts
only a Candidate Metamodel, emits no issues, and returns groups only where the
family root, strategy, ancestry, and intended Table are unambiguous. The
Inheritance Rule Set and dependent Storage Layout Rule Set share the same
cycle-guarded topology walk without depending on Rule Set invocation order.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    AttributeLocation,
    AttributeMetadata,
    CandidateMetamodel,
    Column,
    ConcreteSubtype,
    EntityDeclaration,
    EntityIdentity,
    EntityLocation,
    InheritanceMetadata,
    InheritanceStrategy,
    ModelLocation,
    PrimaryKey,
    Table,
    TablePerHierarchy,
    ValueObjectIdentity,
    ValueObjectLocation,
    ValueObjectOccurrenceDeclaration,
)

__all__ = [
    "AncestryResolution",
    "AttributeTableContributor",
    "CyclicAncestry",
    "InheritanceFamily",
    "InheritanceParticipant",
    "InheritanceTableGroup",
    "InheritanceTopology",
    "ResolvedAncestry",
    "TableGroupContributor",
    "TablePerHierarchyTagContributor",
    "TopLevelValueObjectTableContributor",
    "UnrootedAncestry",
    "project_table_groups",
    "project_topology",
]


@dataclass(frozen=True, slots=True)
class InheritanceParticipant:
    """One inheritance declaration paired with its resolved role value."""

    declaration: EntityDeclaration
    inheritance: InheritanceMetadata


@dataclass(frozen=True, slots=True)
class ResolvedAncestry:
    """A position's root-first ancestry and root-owned strategy."""

    entities: tuple[EntityIdentity, ...]
    strategy: InheritanceStrategy


@dataclass(frozen=True, slots=True)
class CyclicAncestry:
    """The parent-link loop reached by a topology walk."""

    entities: tuple[EntityIdentity, ...]


@dataclass(frozen=True, slots=True)
class UnrootedAncestry:
    """A topology walk that ended without reaching an abstract root."""


type AncestryResolution = ResolvedAncestry | CyclicAncestry | UnrootedAncestry


@dataclass(frozen=True, slots=True)
class InheritanceFamily:
    """One unambiguous rooted family in canonical participant order."""

    root: EntityIdentity
    strategy: InheritanceStrategy
    members: tuple[InheritanceParticipant, ...]


@dataclass(frozen=True, slots=True)
class InheritanceTopology:
    """The shared total result of walking every inheritance participant."""

    participants: Mapping[EntityIdentity, InheritanceParticipant]
    resolutions: Mapping[EntityIdentity, AncestryResolution]
    families: tuple[InheritanceFamily, ...]


@dataclass(frozen=True, slots=True)
class AttributeTableContributor:
    """One declared scalar Attribute in a Table group's diagnostic stream."""

    attribute: AttributeMetadata

    @property
    def column(self) -> Column:
        """The physical Column claimed by the Attribute."""
        return self.attribute.storage

    @property
    def location(self) -> ModelLocation:
        """The declaration provenance used by a physical collision issue."""
        return AttributeLocation(self.attribute.identity)


@dataclass(frozen=True, slots=True)
class TopLevelValueObjectTableContributor:
    """One top-level Value Object document declaration in a Table group."""

    identity: ValueObjectIdentity
    declaration: ValueObjectOccurrenceDeclaration

    @property
    def column(self) -> Column:
        """The one document Column claimed by the occurrence."""
        return self.declaration.storage

    @property
    def location(self) -> ModelLocation:
        """The declaration provenance used by a physical collision issue."""
        return ValueObjectLocation(self.identity)


@dataclass(frozen=True, slots=True)
class TablePerHierarchyTagContributor:
    """The framework-owned discriminator declaration of one TPH root."""

    root: EntityIdentity
    column: Column

    @property
    def location(self) -> ModelLocation:
        """The root provenance available for its tag declaration."""
        return EntityLocation(self.root)


type TableGroupContributor = (
    AttributeTableContributor
    | TopLevelValueObjectTableContributor
    | TablePerHierarchyTagContributor
)
"""The closed identity-bearing physical-claim projection algebra.

``AttributeTableContributor`` carries an accepted Attribute declaration,
``TopLevelValueObjectTableContributor`` carries a top-level Value Object
identity and declaration, and ``TablePerHierarchyTagContributor`` carries the
Entity Identity and Column of a TPH root discriminator.
"""


@dataclass(frozen=True, slots=True)
class InheritanceTableGroup:
    """One independent physical mapping owner projected for Storage Layout.

    ``declaration_contributors`` is in the explicit diagnostic category order:
    primary-key Attributes, optional TPH tag, remaining Attributes, then
    top-level Value Objects. It is not the accepted physical column order.
    """

    table: Table
    mapping_owner: EntityIdentity
    mapping_provenance: EntityLocation
    row_owners: tuple[EntityIdentity, ...]
    declaration_contributors: tuple[TableGroupContributor, ...]


def _resolution(
    participant: InheritanceParticipant,
    participants: Mapping[EntityIdentity, InheritanceParticipant],
) -> AncestryResolution:
    path: list[EntityIdentity] = []
    depth: dict[EntityIdentity, int] = {}
    position = participant
    while True:
        identity = position.declaration.identity
        if identity in depth:
            return CyclicAncestry(tuple(path[depth[identity] :]))
        depth[identity] = len(path)
        path.append(identity)
        match position.inheritance:
            case AbstractRoot(strategy):
                return ResolvedAncestry(tuple(reversed(path)), strategy)
            case AbstractSubtype(parent) | ConcreteSubtype(parent, _):
                ancestor = participants.get(parent)
                if ancestor is None:
                    return UnrootedAncestry()
                position = ancestor


def project_topology(candidate: CandidateMetamodel) -> InheritanceTopology:
    """Walk ``candidate`` once into the topology shared by validation modules.

    The operation is pure and total. Malformed positions retain a cycle or
    unrooted result instead of raising, while only resolved positions enter the
    rooted-family sequence.
    """
    participant_index = {
        declaration.identity: InheritanceParticipant(declaration, declaration.inheritance)
        for declaration in candidate.entities
        if declaration.inheritance is not None
    }
    resolutions = {
        identity: _resolution(participant, participant_index)
        for identity, participant in participant_index.items()
    }
    grouped: dict[EntityIdentity, tuple[InheritanceStrategy, list[InheritanceParticipant]]] = {}
    for identity, resolution in resolutions.items():
        if not isinstance(resolution, ResolvedAncestry):
            continue
        strategy, members = grouped.setdefault(resolution.entities[0], (resolution.strategy, []))
        if strategy != resolution.strategy:
            continue
        members.append(participant_index[identity])
    families = tuple(
        InheritanceFamily(
            root=root,
            strategy=strategy,
            members=tuple(sorted(members, key=lambda item: item.declaration.identity.sort_key)),
        )
        for root, (strategy, members) in sorted(grouped.items(), key=lambda item: item[0].sort_key)
    )
    return InheritanceTopology(
        participants=MappingProxyType(participant_index),
        resolutions=MappingProxyType(resolutions),
        families=families,
    )


def _contributor_declarations(
    topology: InheritanceTopology,
    family: InheritanceFamily,
    row_owners: Sequence[EntityIdentity],
) -> tuple[EntityDeclaration, ...]:
    """The family declaration sequence behind one shared Table group."""
    effective = set(row_owners)
    encountered = set(effective)
    contributors: list[EntityIdentity] = []
    for concrete in row_owners:
        resolution = topology.resolutions[concrete]
        if not isinstance(resolution, ResolvedAncestry):
            continue
        for ancestor in resolution.entities[:-1]:
            if ancestor in encountered:
                continue
            encountered.add(ancestor)
            contributors.append(ancestor)
    contributors.extend(row_owners)
    for member in sorted(
        family.members,
        key=lambda item: (
            item.declaration.identity != family.root,
            item.declaration.identity.sort_key,
        ),
    ):
        identity = member.declaration.identity
        if identity in encountered:
            continue
        encountered.add(identity)
        contributors.append(identity)
    return tuple(topology.participants[identity].declaration for identity in contributors)


def _declaration_contributors(
    declarations: Sequence[EntityDeclaration],
    *,
    tag: TablePerHierarchyTagContributor | None = None,
) -> tuple[TableGroupContributor, ...]:
    keys = tuple(
        AttributeTableContributor(attribute)
        for declaration in declarations
        for attribute in declaration.attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    )
    rest = tuple(
        AttributeTableContributor(attribute)
        for declaration in declarations
        for attribute in declaration.attributes
        if not isinstance(attribute.primary_key, PrimaryKey)
    )
    documents = tuple(
        TopLevelValueObjectTableContributor(
            ValueObjectIdentity(declaration.identity, (occurrence.name,)), occurrence
        )
        for declaration in declarations
        for occurrence in declaration.value_objects
    )
    discriminator: tuple[TableGroupContributor, ...] = () if tag is None else (tag,)
    return (*keys, *discriminator, *rest, *documents)


def project_table_groups(candidate: CandidateMetamodel) -> tuple[InheritanceTableGroup, ...]:
    """Project every unambiguous independent physical mapping owner.

    Standalone Entities, complete TPH families, and individual TPCS concrete
    mappings remain separate even when their structural Table values compare
    equal. Missing or topology-ambiguous mappings are omitted for their owning
    Inheritance rules to diagnose.
    """
    topology = project_topology(candidate)
    groups: list[InheritanceTableGroup] = []
    for declaration in candidate.entities:
        if declaration.inheritance is not None or declaration.container is None:
            continue
        groups.append(
            InheritanceTableGroup(
                table=declaration.container,
                mapping_owner=declaration.identity,
                mapping_provenance=EntityLocation(declaration.identity),
                row_owners=(declaration.identity,),
                declaration_contributors=_declaration_contributors((declaration,)),
            )
        )

    for family in topology.families:
        root = topology.participants[family.root].declaration
        if isinstance(family.strategy, TablePerHierarchy):
            if root.container is None:
                continue
            row_owners = tuple(
                sorted(
                    (
                        member.declaration.identity
                        for member in family.members
                        if isinstance(member.inheritance, ConcreteSubtype)
                    ),
                    key=lambda identity: identity.sort_key,
                )
            )
            declarations = _contributor_declarations(topology, family, row_owners)
            groups.append(
                InheritanceTableGroup(
                    table=root.container,
                    mapping_owner=family.root,
                    mapping_provenance=EntityLocation(family.root),
                    row_owners=row_owners,
                    declaration_contributors=_declaration_contributors(
                        declarations,
                        tag=TablePerHierarchyTagContributor(
                            family.root, Column(family.strategy.tag_column)
                        ),
                    ),
                )
            )
            continue
        for member in family.members:
            declaration = member.declaration
            if not isinstance(member.inheritance, ConcreteSubtype):
                continue
            if declaration.container is None:
                continue
            resolution = topology.resolutions[declaration.identity]
            if not isinstance(resolution, ResolvedAncestry):
                continue
            declarations = tuple(
                topology.participants[identity].declaration for identity in resolution.entities
            )
            groups.append(
                InheritanceTableGroup(
                    table=declaration.container,
                    mapping_owner=declaration.identity,
                    mapping_provenance=EntityLocation(declaration.identity),
                    row_owners=(declaration.identity,),
                    declaration_contributors=_declaration_contributors(declarations),
                )
            )
    return tuple(sorted(groups, key=lambda group: group.mapping_owner.sort_key))
