"""The inheritance Model Formation Rule Set (m-inheritance).

This module rejects family invariants: whether parent links form a closed tree
under exactly one abstract root, whether the strategy's physical mapping is
declared where that strategy puts it, whether facts a family owns as a whole
stay on its root, whether a descendant's own members leave the inherited
namespace unambiguous, and whether rendered materialization keys remain
distinct. Physical Table and Column collisions belong to ``m-storage-layout``.
A family is a position's own ancestry, never the model: one model carries as
many independent families as it declares roots, and each is judged alone.
Parent resolution is not here — foundational resolution owns it, so a
candidate's parents already name existing Entities.

A position whose ancestry does not resolve is reported for that alone: the rest
of these rules are questions about a chain, and there is no chain to ask them
of.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Final

from parallax.core.inheritance._facet import INHERITANCE_MODULE
from parallax.core.inheritance._table_groups import (
    AncestryResolution,
    CyclicAncestry,
    InheritanceParticipant,
    ResolvedAncestry,
    UnrootedAncestry,
    project_topology,
)
from parallax.core.metamodel import (
    AsOfAxisLocation,
    AttributeLocation,
    CandidateMetamodel,
    ConcreteSubtype,
    EntityDeclaration,
    EntityIdentity,
    EntityLocation,
    InheritanceStrategy,
    IssueCode,
    MetamodelIssue,
    ModelLocation,
    PrimaryKey,
    RelationshipLocation,
    TablePerConcreteSubtype,
    TablePerHierarchy,
    ValueObjectIdentity,
    ValueObjectLocation,
)
from parallax.core.model_formation import ModuleIdentity

__all__ = [
    "CONCRETE_WITHOUT_ABSTRACT_ROOT",
    "CYCLE",
    "DUPLICATE_TAG_VALUE",
    "ISSUE_CODES",
    "LAYOUT_NOT_ROOT_OWNED",
    "MATERIALIZATION_KEY_COLLISION",
    "MEMBER_SHADOWING",
    "MISSING_CONCRETE_SUBTYPE",
    "MISSING_ROOT",
    "MISSING_TAG_VALUE",
    "OPTIMISTIC_LOCKING_NOT_ROOT_OWNED",
    "PERSISTENCE_NOT_ROOT_OWNED",
    "PRIMARY_KEY_MISSING",
    "PRIMARY_KEY_MULTIPLE",
    "RULE_SET",
    "STRATEGY_REDECLARED",
    "TAG_ON_CONCRETE_SUBTYPE_STRATEGY",
    "TEMPORAL_AXES_NOT_ROOT_OWNED",
    "TPCS_ABSTRACT_TABLE_FORBIDDEN",
    "TPCS_CONCRETE_TABLE_REQUIRED",
    "TPH_DESCENDANT_TABLE_FORBIDDEN",
    "TPH_ROOT_TABLE_REQUIRED",
    "InheritanceRuleSet",
]

CYCLE: Final[IssueCode] = "inheritance-cycle"
"""Parent links close on themselves, so the positions on the loop belong to no
closed tree and reach no root."""

MISSING_ROOT: Final[IssueCode] = "inheritance-missing-root"
"""An abstract position's ancestry reaches no abstract root, so its family has
none. A concrete position in the same shape is reported by its own code."""

CONCRETE_WITHOUT_ABSTRACT_ROOT: Final[IssueCode] = "inheritance-concrete-without-abstract-root"
"""A concrete subtype's ancestry reaches no abstract root. Only an abstract root
names a family and declares its strategy, so this subtype's physical mapping is
undetermined."""

MISSING_CONCRETE_SUBTYPE: Final[IssueCode] = "inheritance-missing-concrete-subtype"
"""A family contains no concrete subtype. Only concrete subtypes own rows, so
every position in such a family resolves over the empty effective concrete set:
no read selects a row, no narrow has anything to narrow to, and no write names a
target. The rule is asked of the family as composed, so composing a family's
concrete leaves partially is legal and composing none of them is not."""

STRATEGY_REDECLARED: Final[IssueCode] = "inheritance-strategy-redeclared"
"""A non-root position declares the family strategy. The accepted inheritance
algebra carries the strategy on the root variant alone, so no candidate can
represent this; the code is owned here because the rule is this module's."""

MISSING_TAG_VALUE: Final[IssueCode] = "inheritance-missing-tag-value"
"""A table-per-hierarchy concrete subtype declares no tag value, so the shared
table cannot discriminate its rows."""

DUPLICATE_TAG_VALUE: Final[IssueCode] = "inheritance-duplicate-tag-value"
"""Two concrete subtypes of one table-per-hierarchy family claim one tag value,
so a shared-table row names two variants."""

TAG_ON_CONCRETE_SUBTYPE_STRATEGY: Final[IssueCode] = "inheritance-tag-on-concrete-subtype-strategy"
"""A table-per-concrete-subtype family declares a tag value. That strategy
discriminates by which table a row is in, so there is no column to carry it."""

TPH_ROOT_TABLE_REQUIRED: Final[IssueCode] = "inheritance-tph-root-table-required"
"""A table-per-hierarchy root declares no container. The root owns the family's
one shared mapping, so without it the family maps nowhere."""

TPH_DESCENDANT_TABLE_FORBIDDEN: Final[IssueCode] = "inheritance-tph-descendant-table-forbidden"
"""A table-per-hierarchy descendant declares a container, repeating or
contradicting the one its root owns."""

TPCS_ABSTRACT_TABLE_FORBIDDEN: Final[IssueCode] = "inheritance-tpcs-abstract-table-forbidden"
"""A table-per-concrete-subtype root or abstract subtype declares a container.
Abstract positions own no rows, and reads of them lower to per-concrete
branches."""

TPCS_CONCRETE_TABLE_REQUIRED: Final[IssueCode] = "inheritance-tpcs-concrete-table-required"
"""A table-per-concrete-subtype concrete subtype declares no container of its
own, and the strategy provides no shared one."""

PRIMARY_KEY_MISSING: Final[IssueCode] = "inheritance-primary-key-missing"
"""A position's applicable ancestry chain declares no primary-key Attribute, so
rows at that position are unidentifiable."""

PRIMARY_KEY_MULTIPLE: Final[IssueCode] = "inheritance-primary-key-multiple"
"""A position's applicable ancestry chain declares more than one primary-key
Attribute. Composite keys are not part of the contract."""

TEMPORAL_AXES_NOT_ROOT_OWNED: Final[IssueCode] = "inheritance-temporal-axes-not-root-owned"
"""A descendant declares an As-Of Axis. Temporality is a whole-family coordinate
system its root owns, so a descendant may not redeclare, add, remove, override,
or shadow one — not even by repeating the root's declaration."""

OPTIMISTIC_LOCKING_NOT_ROOT_OWNED: Final[IssueCode] = (
    "inheritance-optimistic-locking-not-root-owned"
)
"""A descendant declares an optimistic-locking Attribute. The version column is
family-level metadata its root owns, whether or not the root declares one."""

PERSISTENCE_NOT_ROOT_OWNED: Final[IssueCode] = "inheritance-persistence-not-root-owned"
"""A descendant declares a Persistence Mode. The mode is uniform and root-owned,
so absence on a descendant means inherit and any declaration at all is a second
owner."""

LAYOUT_NOT_ROOT_OWNED: Final[IssueCode] = "inheritance-layout-not-root-owned"
"""A descendant declares a Storage Layout. The layout is family-wide physical
policy its root owns, so a family is entirely conventional or entirely
document-mapped and a descendant may not redeclare, repeat, or override it."""

MEMBER_SHADOWING: Final[IssueCode] = "inheritance-member-shadowing"
"""A descendant redeclares a name an ancestor already declares. One navigable
namespace runs down each ancestry, so shadowing is ambiguous across categories
too; disjoint sibling branches may still reuse a name."""

MATERIALIZATION_KEY_COLLISION: Final[IssueCode] = "inheritance-materialization-key-collision"
"""Two provenance-distinct contributors render one key on the same concrete node.

Scalar fields render by physical column, Value Objects and relationships by
canonical member name, narrowed relationships under a derived bracketed key,
and polymorphic family results under the synthetic ``familyVariant`` key.
"""

ISSUE_CODES: Final[frozenset[IssueCode]] = frozenset(
    {
        CYCLE,
        MISSING_ROOT,
        CONCRETE_WITHOUT_ABSTRACT_ROOT,
        MISSING_CONCRETE_SUBTYPE,
        STRATEGY_REDECLARED,
        MISSING_TAG_VALUE,
        DUPLICATE_TAG_VALUE,
        TAG_ON_CONCRETE_SUBTYPE_STRATEGY,
        TPH_ROOT_TABLE_REQUIRED,
        TPH_DESCENDANT_TABLE_FORBIDDEN,
        TPCS_ABSTRACT_TABLE_FORBIDDEN,
        TPCS_CONCRETE_TABLE_REQUIRED,
        PRIMARY_KEY_MISSING,
        PRIMARY_KEY_MULTIPLE,
        TEMPORAL_AXES_NOT_ROOT_OWNED,
        OPTIMISTIC_LOCKING_NOT_ROOT_OWNED,
        PERSISTENCE_NOT_ROOT_OWNED,
        LAYOUT_NOT_ROOT_OWNED,
        MEMBER_SHADOWING,
        MATERIALIZATION_KEY_COLLISION,
    }
)
"""This module's complete owned Issue Code set, as the Formation Manifest
declares it."""


def _rotated(loop: Sequence[EntityIdentity]) -> tuple[EntityIdentity, ...]:
    """``loop`` restated from its canonically first member, order preserved.

    A cycle has no inherent starting point, so the report picks one that does
    not depend on which position the walk happened to start from.
    """
    anchor = min(range(len(loop)), key=lambda index: loop[index].sort_key)
    return (*loop[anchor:], *loop[:anchor])


def _cycle_issues(
    resolutions: Mapping[EntityIdentity, AncestryResolution],
) -> list[MetamodelIssue]:
    """One issue per distinct cycle, whichever positions the walks started from.

    Every position at or below a cycle reaches the same loop, so grouping by the
    loop's members reports the defect once rather than once per position that
    trips over it.
    """
    loops: dict[frozenset[EntityIdentity], tuple[EntityIdentity, ...]] = {}
    for resolution in resolutions.values():
        if isinstance(resolution, CyclicAncestry):
            loops.setdefault(frozenset(resolution.entities), _rotated(resolution.entities))
    return [
        MetamodelIssue(
            CYCLE,
            EntityLocation(loop[0]),
            tuple(EntityLocation(member) for member in loop[1:]),
            message="inheritance parent links form a cycle",
        )
        for loop in sorted(loops.values(), key=lambda loop: loop[0].sort_key)
    ]


def _unrooted_issue(participant: InheritanceParticipant) -> MetamodelIssue:
    """The defect of a position whose ancestry reaches no abstract root."""
    location = EntityLocation(participant.declaration.identity)
    if isinstance(participant.inheritance, ConcreteSubtype):
        return MetamodelIssue(
            CONCRETE_WITHOUT_ABSTRACT_ROOT,
            location,
            message="the ancestry of this concrete subtype reaches no abstract root",
        )
    return MetamodelIssue(
        MISSING_ROOT,
        location,
        message="the ancestry of this abstract position reaches no abstract root",
    )


def _local_members(declaration: EntityDeclaration) -> Iterator[tuple[str, ModelLocation]]:
    """Every navigable local member name of ``declaration`` with its location.

    Attributes, relationships, and top-level Value Objects share one navigable
    namespace, so they are enumerated together and shadowing crosses categories.
    """
    for attribute in declaration.attributes:
        yield attribute.identity.name, AttributeLocation(attribute.identity)
    for relationship in declaration.relationships:
        yield relationship.identity.name, RelationshipLocation(relationship.identity)
    for occurrence in declaration.value_objects:
        yield (
            occurrence.name,
            ValueObjectLocation(ValueObjectIdentity(declaration.identity, (occurrence.name,))),
        )


def _materialization_key_issues(
    declarations: Sequence[EntityDeclaration], *, family_root: EntityIdentity | None
) -> list[MetamodelIssue]:
    """Rendered-node key collisions over one concrete's applicable chain.

    Value Object storage columns deliberately do not participate: decoding keeps
    their provenance and renders each document under its canonical occurrence
    name. Relationship attachment is likewise provenance-separated from row
    fields. Only the final keys that coexist in the rendered mapping are claimed
    here.
    """
    claimed: dict[str, ModelLocation] = {}
    issues: list[MetamodelIssue] = []

    def claim(key: str, location: ModelLocation) -> None:
        existing = claimed.get(key)
        if existing is None:
            claimed[key] = location
            return
        issues.append(
            MetamodelIssue(
                MATERIALIZATION_KEY_COLLISION,
                location,
                (existing,),
                message=f"materialized field key {key!r} is already claimed on this node",
            )
        )

    if family_root is not None:
        claim("familyVariant", EntityLocation(family_root))
    attributes = [attribute for declaration in declarations for attribute in declaration.attributes]
    relationships = [
        relationship for declaration in declarations for relationship in declaration.relationships
    ]
    for attribute in attributes:
        claim(attribute.storage.name, AttributeLocation(attribute.identity))
    for declaration in declarations:
        for occurrence in declaration.value_objects:
            claim(
                occurrence.name,
                ValueObjectLocation(ValueObjectIdentity(declaration.identity, (occurrence.name,))),
            )
    for relationship in relationships:
        claim(relationship.identity.name, RelationshipLocation(relationship.identity))

    for attribute in attributes:
        for relationship in relationships:
            prefix = f"{relationship.identity.name}["
            if not attribute.storage.name.startswith(prefix):
                continue
            issues.append(
                MetamodelIssue(
                    MATERIALIZATION_KEY_COLLISION,
                    AttributeLocation(attribute.identity),
                    (RelationshipLocation(relationship.identity),),
                    message=(
                        f"materialized field key {attribute.storage.name!r} occupies the "
                        f"narrowed-view namespace {prefix!r}"
                    ),
                )
            )
    return issues


def _shadowing_issues(
    declaration: EntityDeclaration,
    chain: tuple[EntityIdentity, ...],
    participants: Mapping[EntityIdentity, InheritanceParticipant],
) -> list[MetamodelIssue]:
    """The local members of ``declaration`` that an ancestor already declares.

    Ancestors are consulted nearest first, so a name declared more than once up
    the chain is reported against the declaration it actually hides.
    """
    inherited: dict[str, ModelLocation] = {}
    for ancestor in reversed(chain[:-1]):
        for name, location in _local_members(participants[ancestor].declaration):
            inherited.setdefault(name, location)
    issues: list[MetamodelIssue] = []
    for name, location in _local_members(declaration):
        shadowed = inherited.get(name)
        if shadowed is None:
            continue
        issues.append(
            MetamodelIssue(
                MEMBER_SHADOWING,
                location,
                (shadowed,),
                message=f"member {name!r} is already declared by an ancestor",
            )
        )
    return issues


def _primary_key_issues(
    declaration: EntityDeclaration,
    chain: tuple[EntityIdentity, ...],
    participants: Mapping[EntityIdentity, InheritanceParticipant],
) -> list[MetamodelIssue]:
    """The one-key rule over a position's applicable ancestry chain.

    The chain is what a read or write of this position sees, so the rule is
    asked of every position rather than of the family once: a root that cannot
    identify its own rows is as unusable as a concrete subtype that cannot.
    """
    keys = [
        attribute
        for ancestor in chain
        for attribute in participants[ancestor].declaration.attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    ]
    location = EntityLocation(declaration.identity)
    if not keys:
        return [
            MetamodelIssue(
                PRIMARY_KEY_MISSING,
                location,
                message="the applicable ancestry chain declares no primary-key Attribute",
            )
        ]
    if len(keys) > 1:
        return [
            MetamodelIssue(
                PRIMARY_KEY_MULTIPLE,
                location,
                tuple(AttributeLocation(attribute.identity) for attribute in keys),
                message=(
                    f"the applicable ancestry chain declares {len(keys)} primary-key "
                    "Attributes; exactly one is allowed"
                ),
            )
        ]
    return []


def _root_owned_issues(
    declaration: EntityDeclaration, root: EntityIdentity
) -> list[MetamodelIssue]:
    """The facts a descendant may not declare because its family root owns them."""
    if declaration.identity == root:
        return []
    related = (EntityLocation(root),)
    issues: list[MetamodelIssue] = [
        MetamodelIssue(
            TEMPORAL_AXES_NOT_ROOT_OWNED,
            AsOfAxisLocation(declaration.identity, axis.dimension),
            related,
            message="only a family root declares an As-Of Axis",
        )
        for axis in declaration.as_of_axes
    ]
    issues.extend(
        MetamodelIssue(
            OPTIMISTIC_LOCKING_NOT_ROOT_OWNED,
            AttributeLocation(attribute.identity),
            related,
            message="only a family root declares an optimistic-locking Attribute",
        )
        for attribute in declaration.attributes
        if attribute.optimistic_locking
    )
    if declaration.persistence is not None:
        issues.append(
            MetamodelIssue(
                PERSISTENCE_NOT_ROOT_OWNED,
                EntityLocation(declaration.identity),
                related,
                message="only a family root declares a Persistence Mode",
            )
        )
    if declaration.layout is not None:
        issues.append(
            MetamodelIssue(
                LAYOUT_NOT_ROOT_OWNED,
                EntityLocation(declaration.identity),
                related,
                message="only a family root declares a Storage Layout",
            )
        )
    return issues


def _hierarchy_issues(
    root: EntityIdentity, members: Sequence[InheritanceParticipant]
) -> list[MetamodelIssue]:
    """The storage and tag rules of one table-per-hierarchy family."""
    issues: list[MetamodelIssue] = []
    claimed: dict[str, EntityIdentity] = {}
    for member in members:
        identity = member.declaration.identity
        container = member.declaration.container
        if identity == root:
            if container is None:
                issues.append(
                    MetamodelIssue(
                        TPH_ROOT_TABLE_REQUIRED,
                        EntityLocation(identity),
                        message="this table-per-hierarchy root declares no shared container",
                    )
                )
        elif container is not None:
            issues.append(
                MetamodelIssue(
                    TPH_DESCENDANT_TABLE_FORBIDDEN,
                    EntityLocation(identity),
                    (EntityLocation(root),),
                    message="this descendant declares a container its family root already owns",
                )
            )
        if not isinstance(member.inheritance, ConcreteSubtype):
            continue
        tag_value = member.inheritance.tag_value
        if tag_value is None:
            issues.append(
                MetamodelIssue(
                    MISSING_TAG_VALUE,
                    EntityLocation(identity),
                    message="this table-per-hierarchy concrete subtype declares no tag value",
                )
            )
            continue
        owner = claimed.get(tag_value)
        if owner is None:
            claimed[tag_value] = identity
            continue
        issues.append(
            MetamodelIssue(
                DUPLICATE_TAG_VALUE,
                EntityLocation(identity),
                (EntityLocation(owner),),
                message=f"tag value {tag_value!r} is already claimed in this family",
            )
        )
    return issues


def _concrete_subtype_issues(
    root: EntityIdentity, members: Sequence[InheritanceParticipant]
) -> list[MetamodelIssue]:
    """The storage and tag rules of one table-per-concrete-subtype family."""
    issues: list[MetamodelIssue] = []
    for member in members:
        identity = member.declaration.identity
        container = member.declaration.container
        if not isinstance(member.inheritance, ConcreteSubtype):
            if container is not None:
                issues.append(
                    MetamodelIssue(
                        TPCS_ABSTRACT_TABLE_FORBIDDEN,
                        EntityLocation(identity),
                        message="this abstract position owns no rows, so it declares no container",
                    )
                )
            continue
        if container is None:
            issues.append(
                MetamodelIssue(
                    TPCS_CONCRETE_TABLE_REQUIRED,
                    EntityLocation(identity),
                    message="this concrete subtype declares no container and shares none",
                )
            )
        if member.inheritance.tag_value is not None:
            issues.append(
                MetamodelIssue(
                    TAG_ON_CONCRETE_SUBTYPE_STRATEGY,
                    EntityLocation(identity),
                    (EntityLocation(root),),
                    message="this family discriminates by table, so no tag value applies",
                )
            )
    return issues


def _missing_concrete_issue(
    root: EntityIdentity, members: Sequence[InheritanceParticipant]
) -> MetamodelIssue | None:
    """The defect of a family that composes no row-owning position.

    Asked before the strategy rules because it is a question about the family's
    membership rather than about how that membership maps to storage.
    """
    if any(isinstance(member.inheritance, ConcreteSubtype) for member in members):
        return None
    return MetamodelIssue(
        MISSING_CONCRETE_SUBTYPE,
        EntityLocation(root),
        message="this family contains no concrete subtype, so every position in it owns no rows",
    )


def _family_issues(
    root: EntityIdentity,
    members: Sequence[InheritanceParticipant],
    strategy: InheritanceStrategy,
) -> list[MetamodelIssue]:
    """The strategy-dependent rules of the family ``root`` names."""
    match strategy:
        case TablePerHierarchy():
            return _hierarchy_issues(root, members)
        case TablePerConcreteSubtype():
            return _concrete_subtype_issues(root, members)


def validate_inheritance(candidate: CandidateMetamodel) -> tuple[MetamodelIssue, ...]:
    """Every family or materialization-key defect, reported rather than the first."""
    materialization_issues: dict[
        tuple[ModelLocation, tuple[ModelLocation, ...]], MetamodelIssue
    ] = {}
    for declaration in candidate.entities:
        if declaration.inheritance is not None:
            continue
        for issue in _materialization_key_issues((declaration,), family_root=None):
            materialization_issues.setdefault((issue.location, issue.related), issue)

    topology = project_topology(candidate)
    participants = topology.participants
    if not participants:
        return tuple(materialization_issues.values())

    resolutions = topology.resolutions
    issues = _cycle_issues(resolutions)
    issues.extend(
        _unrooted_issue(participants[identity])
        for identity, resolution in resolutions.items()
        if isinstance(resolution, UnrootedAncestry)
    )

    for identity, resolution in resolutions.items():
        if not isinstance(resolution, ResolvedAncestry):
            continue
        participant = participants[identity]
        chain = resolution.entities
        issues.extend(_root_owned_issues(participant.declaration, chain[0]))
        issues.extend(_primary_key_issues(participant.declaration, chain, participants))
        issues.extend(_shadowing_issues(participant.declaration, chain, participants))
        if isinstance(participant.inheritance, ConcreteSubtype):
            declarations = tuple(participants[identity].declaration for identity in chain)
            for issue in _materialization_key_issues(declarations, family_root=chain[0]):
                materialization_issues.setdefault((issue.location, issue.related), issue)
    for family in topology.families:
        missing_concrete = _missing_concrete_issue(family.root, family.members)
        if missing_concrete is not None:
            issues.append(missing_concrete)
        issues.extend(_family_issues(family.root, family.members, family.strategy))
    issues.extend(materialization_issues.values())
    return tuple(issues)


class InheritanceRuleSet:
    """This module's Model Formation Rule Set: issues only, never a facet."""

    __slots__ = ()

    @property
    def owner(self) -> ModuleIdentity:
        """The catalog identity that owns this Rule Set and its Issue Codes."""
        return INHERITANCE_MODULE

    @property
    def issue_codes(self) -> frozenset[IssueCode]:
        """The complete owned code set every emission is held to."""
        return ISSUE_CODES

    def validate(self, candidate: CandidateMetamodel) -> Sequence[MetamodelIssue]:
        """Report every inheritance defect ``candidate`` carries."""
        return validate_inheritance(candidate)


RULE_SET: Final[InheritanceRuleSet] = InheritanceRuleSet()
"""The single Rule Set instance a composition root supplies.

It is stateless, so one instance serves every formation; the constant exists so
a profile names the Rule Set rather than constructing a second one."""
