"""Immutable model-bound Predicate products consumed by planning and SQL."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from parallax.core.base import ManagedValue, NeutralType, matches_neutral_type
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityMetadata,
    NestedValueObjectMetadata,
    ValueObjectAttributeMetadata,
    ValueObjectMetadata,
)
from parallax.core.predicate._nodes import (
    All,
    And,
    Comparison,
    ComparisonOp,
    Group,
    Membership,
    NullCheck,
    NullOp,
    Or,
    PredicateNode,
    Scalar,
)
from parallax.core.wire import encode_wire

type ResolvedPredicateMember = AttributeMetadata | ValueObjectAttributeMetadata
type ResolvedValueObject = ValueObjectMetadata | NestedValueObjectMetadata
type BindForm = Literal["managed", "comparison-text", "framework"]


@dataclass(frozen=True, slots=True)
class ValidatedOperand:
    """One interpreted operand and the physical form SQL may choose for it."""

    value: ManagedValue | object
    neutral_type: NeutralType | None
    form: BindForm = "managed"


@dataclass(frozen=True, slots=True)
class ValidatedPredicate:
    """One authored Predicate occurrence after model-aware elaboration.

    Children are occurrence-local, so reusing the same authored node in two
    positions cannot merge their resolution. Membership values remain one tuple.
    """

    authored: PredicateNode
    children: tuple[ValidatedPredicate, ...] = ()
    operands: tuple[ValidatedOperand, ...] = ()
    member: ResolvedPredicateMember | None = None
    container: ResolvedValueObject | None = None
    relationship_target: EntityMetadata | None = None

    def only_child(self) -> ValidatedPredicate:
        if len(self.children) != 1:
            raise ValueError(f"{type(self.authored).__name__} does not have exactly one child")
        return self.children[0]


def framework_operand(value: object) -> ValidatedOperand:
    """Construct an untyped framework bind, never a serialized typed literal."""
    return ValidatedOperand(value, None, "framework")


def managed_comparison(
    *,
    op: ComparisonOp,
    attr: str,
    member: AttributeMetadata,
    value: ManagedValue,
) -> ValidatedPredicate:
    """Author once and adopt an already-managed generated comparison operand."""
    if not matches_neutral_type(value, member.type):
        raise ValueError(f"{attr}: generated value is outside {member.type!r}")
    authored = Comparison(op=op, attr=attr, value=cast("Scalar", encode_wire(member.type, value)))
    return ValidatedPredicate(
        authored,
        operands=(ValidatedOperand(value, member.type),),
        member=member,
    )


def framework_comparison(
    *, op: ComparisonOp, attr: str, member: AttributeMetadata, value: object
) -> ValidatedPredicate:
    """Build a comparison over a framework sentinel that is not a typed literal."""
    return ValidatedPredicate(
        Comparison(op=op, attr=attr, value=str(value)),
        operands=(framework_operand(value),),
        member=member,
    )


def managed_membership(
    *, attr: str, member: AttributeMetadata, values: tuple[ManagedValue, ...]
) -> ValidatedPredicate:
    """Author one generated membership and retain its managed tuple occurrence."""
    if not all(matches_neutral_type(value, member.type) for value in values):
        raise ValueError(f"{attr}: generated membership contains a value outside {member.type!r}")
    authored = Membership(
        op="in",
        attr=attr,
        values=tuple(cast("Scalar", encode_wire(member.type, value)) for value in values),
    )
    return ValidatedPredicate(
        authored,
        operands=tuple(ValidatedOperand(value, member.type) for value in values),
        member=member,
    )


def null_check(*, op: NullOp, attr: str, member: AttributeMetadata) -> ValidatedPredicate:
    """Build a generated null test over an already-resolved member."""
    return ValidatedPredicate(NullCheck(op=op, attr=attr), member=member)


def compose(authored: PredicateNode, *children: ValidatedPredicate) -> ValidatedPredicate:
    """Retain generated boolean structure around occurrence-local products."""
    return ValidatedPredicate(authored, children=children)


def conjunction(*terms: ValidatedPredicate) -> ValidatedPredicate:
    """Compose validated terms without decoding or resolving any occurrence again."""
    flattened: list[ValidatedPredicate] = []
    for term in terms:
        if isinstance(term.authored, All):
            continue
        if isinstance(term.authored, And):
            flattened.extend(term.children)
        elif isinstance(term.authored, Or):
            flattened.append(ValidatedPredicate(Group(operand=term.authored), children=(term,)))
        else:
            flattened.append(term)
    if not flattened:
        raise ValueError("a validated conjunction requires at least one term")
    if len(flattened) == 1:
        return flattened[0]
    return ValidatedPredicate(
        And(operands=tuple(term.authored for term in flattened)),
        children=tuple(flattened),
    )
