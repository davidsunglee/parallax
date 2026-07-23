"""The inheritance Model Formation Rule Set (m-inheritance).

Everything this module rejects is a statement about a family rather than about
one Entity: whether the parent links form a closed tree under exactly one
abstract root, whether the strategy's physical mapping is declared where that
strategy puts it, whether the facts a family owns as a whole stay on its root,
and whether a descendant's own members leave the inherited namespace
unambiguous. Parent resolution is not here — foundational resolution owns it, so
a candidate's parents already name existing Entities.

A position whose ancestry does not resolve is reported for that alone: the rest
of these rules are questions about a chain, and there is no chain to ask them
of.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from parallax.core.inheritance._facet import INHERITANCE_MODULE
from parallax.core.metamodel import (
    MODEL_ROOT,
    AbstractRoot,
    AbstractSubtype,
    AsOfAxisLocation,
    AttributeLocation,
    CandidateMetamodel,
    ConcreteSubtype,
    EntityDeclaration,
    EntityIdentity,
    EntityLocation,
    InheritanceMetadata,
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
    "MEMBER_SHADOWING",
    "MISSING_ROOT",
    "MISSING_TAG_VALUE",
    "MULTIPLE_ROOTS",
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

MULTIPLE_ROOTS: Final[IssueCode] = "inheritance-multiple-roots"
"""A model's inheritance participants declare more than one abstract root. The
rule is model-wide rather than per-ancestry: a root has no parent, so two roots
never share an ancestry and a per-ancestry reading could never fire."""

CONCRETE_WITHOUT_ABSTRACT_ROOT: Final[IssueCode] = "inheritance-concrete-without-abstract-root"
"""A concrete subtype's ancestry reaches no abstract root. Only an abstract root
names a family and declares its strategy, so this subtype's physical mapping is
undetermined."""

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

MEMBER_SHADOWING: Final[IssueCode] = "inheritance-member-shadowing"
"""A descendant redeclares a name an ancestor already declares. One navigable
namespace runs down each ancestry, so shadowing is ambiguous across categories
too; disjoint sibling branches may still reuse a name."""

ISSUE_CODES: Final[frozenset[IssueCode]] = frozenset(
    {
        CYCLE,
        MISSING_ROOT,
        MULTIPLE_ROOTS,
        CONCRETE_WITHOUT_ABSTRACT_ROOT,
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
        MEMBER_SHADOWING,
    }
)
"""This module's complete owned Issue Code set, as the Formation Manifest
declares it."""


@dataclass(frozen=True, slots=True)
class _Chain:
    """The position's ancestry resolves: ``entities`` runs root first.

    The root's strategy travels with the chain because reaching a root is what
    established it: a family whose strategy is still in question is one of the
    other two outcomes.
    """

    entities: tuple[EntityIdentity, ...]
    strategy: InheritanceStrategy


@dataclass(frozen=True, slots=True)
class _Cycle:
    """The walk revisited a position; ``entities`` is the loop it closed on."""

    entities: tuple[EntityIdentity, ...]


@dataclass(frozen=True, slots=True)
class _Unrooted:
    """The walk ended somewhere that is not an abstract root."""


type _Resolution = _Chain | _Cycle | _Unrooted


@dataclass(frozen=True, slots=True)
class _Participant:
    """One Entity that declares inheritance, paired with what it declares.

    Participation is carried as a type rather than rechecked: every walk below
    reads a position's role directly instead of asking again whether it has one.
    """

    declaration: EntityDeclaration
    inheritance: InheritanceMetadata


def _resolution(
    participant: _Participant, participants: Mapping[EntityIdentity, _Participant]
) -> _Resolution:
    """Where ``participant``'s ancestry leads.

    Each position has at most one parent, so the walk either closes on a loop,
    leaves the participants — a parent that declares no inheritance of its own —
    or reaches the abstract root that establishes the family and its strategy.
    """
    path: list[EntityIdentity] = []
    depth: dict[EntityIdentity, int] = {}
    position = participant
    while True:
        identity = position.declaration.identity
        if identity in depth:
            return _Cycle(tuple(path[depth[identity] :]))
        depth[identity] = len(path)
        path.append(identity)
        match position.inheritance:
            case AbstractRoot(strategy):
                return _Chain(tuple(reversed(path)), strategy)
            case AbstractSubtype(parent) | ConcreteSubtype(parent, _):
                ancestor = participants.get(parent)
                if ancestor is None:
                    return _Unrooted()
                position = ancestor


def _rotated(loop: Sequence[EntityIdentity]) -> tuple[EntityIdentity, ...]:
    """``loop`` restated from its canonically first member, order preserved.

    A cycle has no inherent starting point, so the report picks one that does
    not depend on which position the walk happened to start from.
    """
    anchor = min(range(len(loop)), key=lambda index: loop[index].sort_key)
    return (*loop[anchor:], *loop[:anchor])


def _cycle_issues(resolutions: Mapping[EntityIdentity, _Resolution]) -> list[MetamodelIssue]:
    """One issue per distinct cycle, whichever positions the walks started from.

    Every position at or below a cycle reaches the same loop, so grouping by the
    loop's members reports the defect once rather than once per position that
    trips over it.
    """
    loops: dict[frozenset[EntityIdentity], tuple[EntityIdentity, ...]] = {}
    for resolution in resolutions.values():
        if isinstance(resolution, _Cycle):
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


def _unrooted_issue(participant: _Participant) -> MetamodelIssue:
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


def _multiple_root_issues(roots: Sequence[EntityIdentity]) -> list[MetamodelIssue]:
    """The model-wide single-root rule.

    Every other rule below is asked of one family, resolved from a position's
    own ancestry. This one is asked of the model: its participants resolve to
    one family identity, so a second root is a second family the contract does
    not admit.
    """
    if len(roots) < 2:
        return []
    return [
        MetamodelIssue(
            MULTIPLE_ROOTS,
            MODEL_ROOT,
            tuple(EntityLocation(root) for root in roots),
            message=f"{len(roots)} inheritance roots are declared; exactly one is allowed",
        )
    ]


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


def _shadowing_issues(
    declaration: EntityDeclaration,
    chain: tuple[EntityIdentity, ...],
    participants: Mapping[EntityIdentity, _Participant],
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
    participants: Mapping[EntityIdentity, _Participant],
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
    return issues


def _hierarchy_issues(
    root: EntityIdentity, members: Sequence[_Participant]
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
    root: EntityIdentity, members: Sequence[_Participant]
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


def _family_issues(
    root: EntityIdentity, members: Sequence[_Participant], strategy: InheritanceStrategy
) -> list[MetamodelIssue]:
    """The strategy-dependent rules of the family ``root`` names."""
    match strategy:
        case TablePerHierarchy():
            return _hierarchy_issues(root, members)
        case TablePerConcreteSubtype():
            return _concrete_subtype_issues(root, members)


def validate_inheritance(candidate: CandidateMetamodel) -> tuple[MetamodelIssue, ...]:
    """Every inheritance defect of ``candidate``, reported rather than the first."""
    participants = {
        declaration.identity: _Participant(declaration, declaration.inheritance)
        for declaration in candidate.entities
        if declaration.inheritance is not None
    }
    if not participants:
        return ()

    resolutions = {
        identity: _resolution(participant, participants)
        for identity, participant in participants.items()
    }
    roots = [
        identity
        for identity, participant in participants.items()
        if isinstance(participant.inheritance, AbstractRoot)
    ]
    issues = _cycle_issues(resolutions)
    issues.extend(
        _unrooted_issue(participants[identity])
        for identity, resolution in resolutions.items()
        if isinstance(resolution, _Unrooted)
    )
    issues.extend(_multiple_root_issues(roots))

    families: dict[EntityIdentity, tuple[InheritanceStrategy, list[_Participant]]] = {}
    for identity, resolution in resolutions.items():
        if not isinstance(resolution, _Chain):
            continue
        participant = participants[identity]
        chain = resolution.entities
        _, members = families.setdefault(chain[0], (resolution.strategy, []))
        members.append(participant)
        issues.extend(_root_owned_issues(participant.declaration, chain[0]))
        issues.extend(_primary_key_issues(participant.declaration, chain, participants))
        issues.extend(_shadowing_issues(participant.declaration, chain, participants))
    for root, (strategy, members) in families.items():
        issues.extend(_family_issues(root, members, strategy))
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
