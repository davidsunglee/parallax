from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from parallax.core.base import ManagedValue
from parallax.core.predicate._nodes import ComparisonOp, MembershipOp, NullOp, StringOp
from parallax.core.predicate._resolved import ResolvedPredicate, ResolvedPredicateMember

if TYPE_CHECKING:
    from parallax.core.metamodel import EntityMetadata
    from parallax.core.predicate.validate import PositionScope

__all__ = [
    "BETWEEN",
    "COMPARE",
    "MEMBER_OF",
    "NULL_TEST",
    "Compare",
    "InRange",
    "Match",
    "MemberOf",
    "NullTest",
    "OperandAdmission",
    "PredicateInterpretation",
    "ScalarOperator",
]


@dataclass(frozen=True, slots=True)
class Compare:
    op: ComparisonOp


@dataclass(frozen=True, slots=True)
class InRange:
    """An inclusive range test taking a lower and an upper operand."""


@dataclass(frozen=True, slots=True)
class MemberOf:
    op: MembershipOp


@dataclass(frozen=True, slots=True)
class Match:
    """A string predicate; its one operand is the pattern, which is never admitted."""

    op: StringOp
    case_insensitive: bool


@dataclass(frozen=True, slots=True)
class NullTest:
    op: NullOp


type ScalarOperator = Compare | InRange | MemberOf | Match | NullTest

COMPARE: Final[dict[ComparisonOp, Compare]] = {
    op: Compare(op)
    for op in ("eq", "notEq", "greaterThan", "greaterThanEquals", "lessThan", "lessThanEquals")
}
BETWEEN: Final = InRange()
MEMBER_OF: Final[dict[MembershipOp, MemberOf]] = {op: MemberOf(op) for op in ("in", "notIn")}
NULL_TEST: Final[dict[NullOp, NullTest]] = {op: NullTest(op) for op in ("isNull", "isNotNull")}

type OperandAdmission = Callable[
    [str, ResolvedPredicateMember, tuple[object, ...]], tuple[ManagedValue, ...]
]
"""How one ingress turns an operation's operands into managed values of the
resolved member's scalar type, given the subject spelling its refusals name."""


class PredicateInterpretation(Protocol):
    """One captured predicate input, resolved at the checked position it applies to.

    An adapter captures its input and borrows the model the operation adopted,
    so the call carries only portable position facts: ``root`` is the Entity the
    predicate selects within and ``position`` the active concrete set there.
    """

    def __call__(self, root: EntityMetadata, position: PositionScope, /) -> ResolvedPredicate: ...
