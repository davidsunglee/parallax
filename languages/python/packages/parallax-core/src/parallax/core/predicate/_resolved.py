from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from parallax.core.base import ManagedValue, NeutralType, matches_neutral_type
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    OccurrenceMetadata,
    RelationshipIdentity,
    ValueObjectAttributeMetadata,
)
from parallax.core.predicate._nodes import ComparisonOp, MembershipOp, NullOp, StringOp

type ResolvedPredicateMember = AttributeMetadata | ValueObjectAttributeMetadata
"""A scalar member read from the operation's current object position.

An Attribute is read from the current Entity position; a Value Object leaf is
read from the current Entity position through single occurrences, or from the
element an enclosing quantifier binds.
"""


@dataclass(frozen=True, slots=True)
class DeferredKeySet:
    """A child-read membership whose values arrive when its parent rows do."""

    neutral_type: NeutralType


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


@dataclass(frozen=True, slots=True)
class ResolvedRange:
    member: ResolvedPredicateMember
    lower: ManagedValue
    upper: ManagedValue


@dataclass(frozen=True, slots=True)
class ResolvedMembership:
    op: MembershipOp
    member: ResolvedPredicateMember
    values: tuple[ManagedValue, ...] | DeferredKeySet


@dataclass(frozen=True, slots=True)
class ResolvedStringMatch:
    op: StringOp
    member: ResolvedPredicateMember
    pattern: str
    case_insensitive: bool


@dataclass(frozen=True, slots=True)
class ResolvedNullCheck:
    op: NullOp
    member: ResolvedPredicateMember


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
    """``operand`` holds at the current Entity position narrowed to ``position``."""

    position: tuple[EntityIdentity, ...]
    operand: ResolvedPredicate


@dataclass(frozen=True, slots=True)
class ResolvedQuantifier:
    """Whether some element of ``occurrence`` (``any``) or none (``none``) makes
    ``where`` true; without ``where``, whether it holds an element at all.

    ``where`` is read from the bound element. A single occurrence holds at most
    one element.
    """

    kind: Literal["any", "none"]
    occurrence: OccurrenceMetadata
    where: ResolvedPredicate | None = None


@dataclass(frozen=True, slots=True)
class ResolvedSemiJoin:
    """Whether some Entity ``relationship`` reaches from the current position
    makes ``where`` true, complemented when ``negated``.

    ``source`` and ``related`` are the join endpoints at the current position
    and at ``target``; ``where`` is read from the reached Entity.
    """

    relationship: RelationshipIdentity
    target: EntityMetadata
    source: AttributeMetadata
    related: AttributeMetadata
    negated: bool
    where: ResolvedPredicate | None = None


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
    | ResolvedSemiJoin
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


def conjunction(*terms: ResolvedPredicate) -> ResolvedPredicate:
    """Compose resolved terms without resolving any of them again."""
    flattened: list[ResolvedPredicate] = []
    for term in terms:
        if isinstance(term, ResolvedConstant) and term.truth:
            continue
        if isinstance(term, ResolvedAnd):
            flattened.extend(term.operands)
        elif isinstance(term, ResolvedOr):
            flattened.append(ResolvedGroup(term))
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
