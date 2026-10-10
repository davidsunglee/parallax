from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from parallax.core.base import ManagedValue, NeutralType, matches_neutral_type
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    OccurrenceMetadata,
    RelationshipIdentity,
    ValueObjectAttributeMetadata,
)
from parallax.core.predicate._nodes import (
    ComparisonOp,
    MembershipOp,
    NullOp,
    QuantifierKind,
    StringOp,
)

type ResolvedPredicateMember = AttributeMetadata | ValueObjectAttributeMetadata
"""A scalar member read from an object position.

An Attribute is read from an Entity position; a Value Object leaf is read from
an Entity position through single occurrences, or from the element an enclosing
quantifier binds. A scalar collection member is read whole only by its
quantifier; an operation over one of its elements names it with the element
position.
"""


@dataclass(frozen=True, slots=True)
class DeferredKeySet:
    """A child-read membership whose values arrive when its parent rows do."""

    neutral_type: NeutralType


@dataclass(frozen=True, slots=True)
class CurrentObject:
    """The object the enclosing scope is at: the queried Entity, a bound
    element, or a narrowed target."""


CURRENT: Final = CurrentObject()


@dataclass(frozen=True, slots=True)
class ResolvedRelationship:
    """One relationship direction reached from an object position.

    ``source`` and ``related`` are its join endpoints at the source position
    and at ``target``. ``visibility`` holds the generated temporal terms its
    candidates are visible under; it is empty until a read propagates them.
    """

    identity: RelationshipIdentity
    target: EntityMetadata
    source: AttributeMetadata
    related: AttributeMetadata
    visibility: tuple[ResolvedPredicate, ...] = ()


@dataclass(frozen=True, slots=True)
class RelatedObject:
    """The single Entity ``relationship`` reaches from ``source``."""

    source: ObjectPosition
    relationship: ResolvedRelationship


type ObjectPosition = CurrentObject | RelatedObject


@dataclass(frozen=True, slots=True)
class ScalarElement:
    """The scalar an enclosing scalar-collection quantifier binds."""


ELEMENT: Final = ScalarElement()

type SubjectPosition = ObjectPosition | ScalarElement


@dataclass(frozen=True, slots=True)
class ResolvedConstant:
    truth: bool


@dataclass(frozen=True, slots=True)
class ResolvedComparison:
    """``value`` is managed, or a framework sentinel bound as is when ``framework``."""

    op: ComparisonOp
    member: ResolvedPredicateMember
    value: object
    framework: bool = False
    position: SubjectPosition = CURRENT


@dataclass(frozen=True, slots=True)
class ResolvedRange:
    member: ResolvedPredicateMember
    lower: ManagedValue
    upper: ManagedValue
    position: SubjectPosition = CURRENT


@dataclass(frozen=True, slots=True)
class ResolvedMembership:
    op: MembershipOp
    member: ResolvedPredicateMember
    values: tuple[ManagedValue, ...] | DeferredKeySet
    position: SubjectPosition = CURRENT


@dataclass(frozen=True, slots=True)
class ResolvedStringMatch:
    op: StringOp
    member: ResolvedPredicateMember
    pattern: str
    case_insensitive: bool
    position: SubjectPosition = CURRENT


@dataclass(frozen=True, slots=True)
class ResolvedNullCheck:
    op: NullOp
    member: ResolvedPredicateMember
    position: ObjectPosition = CURRENT


@dataclass(frozen=True, slots=True)
class ResolvedAnd:
    operands: tuple[ResolvedPredicate, ...]


@dataclass(frozen=True, slots=True)
class ResolvedOr:
    operands: tuple[ResolvedPredicate, ...]


@dataclass(frozen=True, slots=True)
class ResolvedNot:
    operand: ResolvedPredicate


@dataclass(frozen=True, slots=True)
class ResolvedGroup:
    operand: ResolvedPredicate


@dataclass(frozen=True, slots=True)
class ResolvedNarrow:
    """Whether the Entity at ``target`` belongs to ``selection`` and, when an
    ``operand`` is present, makes it true there; a selected target keeps the
    operand's unknown, while an absent or unselected one is false."""

    selection: tuple[EntityIdentity, ...]
    operand: ResolvedPredicate | None = None
    target: ObjectPosition = CURRENT


@dataclass(frozen=True, slots=True)
class ScalarCollection:
    """A scalar collection member, quantified element by element."""

    member: ResolvedPredicateMember


type ResolvedCollection = ScalarCollection | OccurrenceMetadata | ResolvedRelationship
"""What a quantifier ranges over: a scalar collection, a ``many`` Value Object
occurrence, or a to-many relationship's related Entities."""


@dataclass(frozen=True, slots=True)
class ResolvedQuantifier:
    """Whether some (``any``), every (``all``), or no (``none``) element of
    ``collection`` at ``position`` makes ``where`` true.

    Without ``where``, ``any`` and ``none`` test whether the collection holds an
    element. ``all`` always carries ``where`` and fails on a false or unknown
    element. An absent collection holds no element.
    """

    kind: QuantifierKind
    collection: ResolvedCollection
    where: ResolvedPredicate | None = None
    position: ObjectPosition = CURRENT


@dataclass(frozen=True, slots=True)
class ResolvedPresence:
    """Whether the single object ``target`` names at ``position`` is present,
    complemented when ``negated``: a ``one`` Value Object occurrence, or the
    Entity a to-one relationship reaches."""

    negated: bool
    target: OccurrenceMetadata | ResolvedRelationship
    position: ObjectPosition = CURRENT


type ResolvedPredicate = (
    ResolvedConstant
    | ResolvedComparison
    | ResolvedRange
    | ResolvedMembership
    | ResolvedStringMatch
    | ResolvedNullCheck
    | ResolvedAnd
    | ResolvedOr
    | ResolvedNot
    | ResolvedGroup
    | ResolvedNarrow
    | ResolvedQuantifier
    | ResolvedPresence
)


def managed_comparison(
    *, op: ComparisonOp, member: AttributeMetadata, value: ManagedValue
) -> ResolvedComparison:
    """Adopt an already-managed generated comparison operand."""
    if not matches_neutral_type(value, member.type):
        raise ValueError(f"{member.identity}: generated value is outside {member.type!r}")
    return ResolvedComparison(op, member, value)


def framework_comparison(
    *, op: ComparisonOp, member: AttributeMetadata, value: object
) -> ResolvedComparison:
    """Compare against a framework sentinel that is not a typed literal."""
    return ResolvedComparison(op, member, value, framework=True)


def deferred_membership(*, member: AttributeMetadata) -> ResolvedMembership:
    """A generated membership whose key sequence is bound after compilation."""
    return ResolvedMembership("in", member, DeferredKeySet(member.type))


def disjunctive(predicate: ResolvedPredicate) -> bool:
    """Whether ``predicate`` lowers with a top-level `or`, which an `and` beside
    it would re-associate unless the predicate is grouped."""
    if isinstance(predicate, ResolvedOr):
        return True
    if isinstance(predicate, ResolvedAnd):
        return any(disjunctive(operand) for operand in predicate.operands)
    return False


def conjunction(*terms: ResolvedPredicate) -> ResolvedPredicate:
    """Compose resolved terms without resolving any of them again."""
    flattened: list[ResolvedPredicate] = []
    for term in terms:
        if isinstance(term, ResolvedConstant) and term.truth:
            continue
        if disjunctive(term):
            flattened.append(ResolvedGroup(term))
        elif isinstance(term, ResolvedAnd):
            flattened.extend(term.operands)
        else:
            flattened.append(term)
    if not flattened:
        raise ValueError("a resolved conjunction requires at least one term")
    if len(flattened) == 1:
        return flattened[0]
    return ResolvedAnd(tuple(flattened))


def disjunction(first: ResolvedPredicate, *rest: ResolvedPredicate) -> ResolvedPredicate:
    """Compose resolved alternatives, each conjunction among them grouped
    whole; a lone alternative is answered itself."""
    if not rest:
        return first
    return ResolvedOr(
        tuple(
            ResolvedGroup(term) if isinstance(term, ResolvedAnd) else term
            for term in (first, *rest)
        )
    )
