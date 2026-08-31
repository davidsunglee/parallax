"""Predicate-algebra nodes (m-predicate).

Frozen ``slots`` dataclasses for the recursive selection tree the query surface
builds and the corpus serializes. Every node is immutable and shareable;
construction is value-only (metamodel binding is validated by the serde/statement
layers, not in ``__init__``). The union :data:`PredicateNode` is the exhaustive
selection algebra consumed by ``m-sql`` predicate lowering, whose dispatch uses
``match`` and ``assert_never``. Every query-wide value — the queried position,
result narrowing, ordering, the row cap, Temporal Selection, Includes — is a
clause of ``m-object-query`` rather than a node here; :class:`Narrow` is the
Predicate-scoped filter, which restricts the active position while evaluating
its own operand. Aggregation (``groupBy``) and the write side are out of scope.

A node that doubles as a Python authoring surface — one a caller composes by
method call rather than by deserializing a document — rejects an illegal
composition through :class:`QueryDefinitionError`, which lives here beside the
rules that raise it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from parallax.core.metamodel import EntityIdentity

__all__ = [
    "QUERY_DEFINITION_CODES",
    "All",
    "And",
    "Between",
    "Comparison",
    "ComparisonOp",
    "Exists",
    "Group",
    "Membership",
    "MembershipOp",
    "Narrow",
    "Navigate",
    "NestedComparison",
    "NestedComparisonOp",
    "NestedExists",
    "NestedMembership",
    "NestedMembershipOp",
    "NestedNotExists",
    "NestedNullCheck",
    "NestedNullOp",
    "NestedRange",
    "NestedStringMatch",
    "NestedStringOp",
    "NoneOp",
    "Not",
    "NotExists",
    "NullCheck",
    "NullOp",
    "Or",
    "PredicateNode",
    "QueryDefinitionError",
    "Scalar",
    "StringMatch",
    "StringOp",
    "SubtypeSelection",
    "canonical_subtype_selection",
]

# A non-null serialized typed literal. Null tests use dedicated nodes.
Scalar = str | int | float | bool


def _require_non_null_literal(value: object) -> None:
    if value is None:
        raise QueryDefinitionError(
            code="query-expression-invalid",
            message="None is not a Predicate literal; use .is_null() or .is_not_null()",
        )


def _require_non_null_literals(values: tuple[Scalar, ...]) -> None:
    for value in values:
        _require_non_null_literal(value)


SubtypeSelection = tuple[str, ...]


def canonical_subtype_selection(alternatives: tuple[str, ...]) -> SubtypeSelection:
    """Return alternatives in canonical Entity Identity order.

    Duplicates are preserved so schema-valid rejected inputs can reach
    model-aware validation. Python authoring surfaces reject them first.
    """

    def sort_key(spelling: str) -> tuple[str, str]:
        namespace, separator, name = spelling.rpartition(".")
        identity = EntityIdentity(namespace if separator else None, name if separator else spelling)
        return identity.sort_key

    return tuple(sorted(alternatives, key=sort_key))


ComparisonOp = Literal[
    "eq", "notEq", "greaterThan", "greaterThanEquals", "lessThan", "lessThanEquals"
]
NullOp = Literal["isNull", "isNotNull"]
StringOp = Literal["like", "notLike", "startsWith", "endsWith", "contains"]
MembershipOp = Literal["in", "notIn"]
NestedComparisonOp = Literal[
    "nestedEq", "nestedNotEq", "nestedGt", "nestedGte", "nestedLt", "nestedLte"
]
NestedMembershipOp = Literal["nestedIn", "nestedNotIn"]
NestedStringOp = Literal[
    "nestedLike", "nestedNotLike", "nestedStartsWith", "nestedEndsWith", "nestedContains"
]
NestedNullOp = Literal["nestedIsNull", "nestedIsNotNull"]


QUERY_DEFINITION_CODES: Final[frozenset[str]] = frozenset(
    {
        "query-target-mismatch",
        "query-expression-invalid",
        "query-path-invalid",
        "query-clause-invalid",
        "query-assignment-invalid",
        "query-assignment-target-mismatch",
        "query-not-mutation-compatible",
    }
)
"""The closed query-definition rejection vocabulary (Python spec §2).

That section fixes which rule draws which code; an invalid expression — a Sort
Key composition included — draws ``query-expression-invalid``. A query names no
model, so there is no model-mismatch member here: a target the connected model
does not declare is an execution refusal rather than an authoring one.
"""


class QueryDefinitionError(ValueError):
    """An invalid Python query construction, composition, or refinement.

    ``code`` is a member of :data:`QUERY_DEFINITION_CODES`; constructing one with
    any other code is an implementation defect and raises :class:`ValueError`. A
    caller therefore branches on the rule that fired rather than on a message
    substring.

    This is the query-authoring family, disjoint by the question it answers from
    the two wire-and-model families beside it: ``CanonicalDocumentError`` says a
    serialized document is malformed, and ``ModelRejectedError`` says a
    well-formed one is illegal against a model.
    """

    def __init__(self, *, code: str, message: str) -> None:
        if code not in QUERY_DEFINITION_CODES:
            raise ValueError(f"{code!r} is not a query definition code")
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class All:
    """The identity — selects every row (no ``WHERE``)."""


@dataclass(frozen=True, slots=True)
class NoneOp:
    """The absorbing element — matches nothing (``where 1 = 0``)."""


@dataclass(frozen=True, slots=True)
class Comparison:
    """A scalar comparison of one attribute against a literal."""

    op: ComparisonOp
    attr: str
    value: Scalar

    def __post_init__(self) -> None:
        _require_non_null_literal(self.value)


@dataclass(frozen=True, slots=True)
class Between:
    """``attr between lower and upper`` (two ordered binds)."""

    attr: str
    lower: Scalar
    upper: Scalar

    def __post_init__(self) -> None:
        _require_non_null_literal(self.lower)
        _require_non_null_literal(self.upper)


@dataclass(frozen=True, slots=True)
class NullCheck:
    """``attr is null`` / ``not attr is null``."""

    op: NullOp
    attr: str


@dataclass(frozen=True, slots=True)
class StringMatch:
    """A string predicate; affix forms escape wildcards, ``like`` passes through.

    ``case_insensitive`` is ``None`` when the authored node omitted the optional
    ``caseInsensitive`` flag (the schema default is ``false``). Serde round-trips
    that absence faithfully — an omitted flag serializes back omitted, an explicit
    ``false``/``true`` serializes back verbatim — while SQL lowering treats an
    absent flag as the ``false`` default (``if case_insensitive`` is falsy for
    ``None``).
    """

    op: StringOp
    attr: str
    value: str
    case_insensitive: bool | None = None

    def __post_init__(self) -> None:
        _require_non_null_literal(self.value)


@dataclass(frozen=True, slots=True)
class Membership:
    """``attr in (…)`` / ``not attr in (…)`` over a non-empty value list."""

    op: MembershipOp
    attr: str
    values: tuple[Scalar, ...]

    def __post_init__(self) -> None:
        _require_non_null_literals(self.values)


@dataclass(frozen=True, slots=True)
class And:
    """N-ary conjunction; operand order is significant (drives bind order)."""

    operands: tuple[PredicateNode, ...]


@dataclass(frozen=True, slots=True)
class Or:
    """N-ary disjunction; operand order is significant."""

    operands: tuple[PredicateNode, ...]


@dataclass(frozen=True, slots=True)
class Not:
    """Logical negation of one operand."""

    operand: PredicateNode


@dataclass(frozen=True, slots=True)
class Group:
    """An explicit precedence-nesting node (`( … )`)."""

    operand: PredicateNode


@dataclass(frozen=True, slots=True)
class Narrow:
    """Constrain a polymorphic position to a subset of its subtypes."""

    to: SubtypeSelection
    operand: PredicateNode

    def __post_init__(self) -> None:
        object.__setattr__(self, "to", canonical_subtype_selection(self.to))


@dataclass(frozen=True, slots=True)
class NestedComparison:
    """A value-object inner-attribute comparison against a typed literal."""

    op: NestedComparisonOp
    path: str
    value: Scalar

    def __post_init__(self) -> None:
        _require_non_null_literal(self.value)


@dataclass(frozen=True, slots=True)
class NestedRange:
    """A value-object inner-attribute range test against two typed literal bounds.

    One canonical node, never a pair of comparisons: through a Many occurrence the
    flat family is any-element, so `>= lower` and `<= upper` as two nodes could be
    satisfied by two *different* elements, while this node requires one element to
    satisfy the whole range (`m-predicate`).
    """

    path: str
    lower: Scalar
    upper: Scalar

    def __post_init__(self) -> None:
        _require_non_null_literal(self.lower)
        _require_non_null_literal(self.upper)


@dataclass(frozen=True, slots=True)
class NestedMembership:
    """A value-object inner-attribute membership test over typed literals.

    The negated form keeps the uniform any-element reading through a Many
    occurrence — some element's member is not in the list — which is why it is one
    node with the positive form rather than a negation of existence.
    """

    op: NestedMembershipOp
    path: str
    values: tuple[Scalar, ...]

    def __post_init__(self) -> None:
        _require_non_null_literals(self.values)


@dataclass(frozen=True, slots=True)
class NestedStringMatch:
    """A value-object inner-attribute string predicate over a ``String`` member.

    Carries :class:`StringMatch`'s semantics against a nested extraction — affix
    forms escape wildcards, ``nestedLike``/``nestedNotLike`` pass the pattern
    through, and ``case_insensitive`` follows the same omitted-versus-explicit
    round-trip rule. It is a node of its own rather than a reuse of
    :class:`StringMatch` because serialization dispatches on the node class and the
    two spell their subject differently (``path`` versus ``attr``); one class serves
    BOTH nested scopes, as every other nested node does.
    """

    op: NestedStringOp
    path: str
    value: str
    case_insensitive: bool | None = None

    def __post_init__(self) -> None:
        _require_non_null_literal(self.value)


@dataclass(frozen=True, slots=True)
class NestedNullCheck:
    """A value-object inner-attribute presence test (absence-collapse rule)."""

    op: NestedNullOp
    path: str


@dataclass(frozen=True, slots=True)
class NestedExists:
    """The value object at ``path`` is present / non-empty; optional element ``where``."""

    path: str
    where: PredicateNode | None = None


@dataclass(frozen=True, slots=True)
class NestedNotExists:
    """The complement of :class:`NestedExists`."""

    path: str
    where: PredicateNode | None = None


@dataclass(frozen=True, slots=True)
class Navigate:
    """Filter the queried entity by traversing a relationship (correlated EXISTS)."""

    rel: str
    op: PredicateNode | None = None


@dataclass(frozen=True, slots=True)
class Exists:
    """The queried entity has >=1 related row (optionally matching ``op``)."""

    rel: str
    op: PredicateNode | None = None


@dataclass(frozen=True, slots=True)
class NotExists:
    """The queried entity has no related row (optionally matching ``op``)."""

    rel: str
    op: PredicateNode | None = None


# The exhaustive read-path Predicate union (m-predicate); m-sql lowers over it.
PredicateNode = (
    All
    | NoneOp
    | Comparison
    | Between
    | NullCheck
    | StringMatch
    | Membership
    | And
    | Or
    | Not
    | Group
    | Narrow
    | NestedComparison
    | NestedRange
    | NestedMembership
    | NestedStringMatch
    | NestedNullCheck
    | NestedExists
    | NestedNotExists
    | Navigate
    | Exists
    | NotExists
)
