"""Operation-algebra nodes (m-op-algebra).

Frozen ``slots`` dataclasses for the operation tree the query surface builds and
the corpus serializes. Every node is immutable and shareable; construction is
value-only (metamodel binding is validated by the serde/statement layers, not in
``__init__``). The union :data:`Operation` is the exhaustive read-path algebra
this phase lowers; ``m-sql`` dispatches over it with ``match`` and
``assert_never``. Aggregation (``groupBy``) and the write side are out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

__all__ = [
    "All",
    "And",
    "AsOf",
    "AsOfRange",
    "Between",
    "Comparison",
    "ComparisonOp",
    "DeepFetch",
    "Distinct",
    "Exists",
    "Group",
    "History",
    "Limit",
    "Membership",
    "MembershipOp",
    "Narrow",
    "Navigate",
    "NestedComparison",
    "NestedComparisonOp",
    "NestedExists",
    "NestedMembership",
    "NestedNotExists",
    "NestedNullCheck",
    "NestedNullOp",
    "NoneOp",
    "Not",
    "NotExists",
    "NullCheck",
    "NullOp",
    "Operation",
    "Or",
    "OrderBy",
    "OrderKey",
    "PathSegment",
    "Scalar",
    "StringMatch",
    "StringOp",
]

# A scalar literal usable as a bind (json/yaml primitive).
Scalar = str | int | float | bool | None

ComparisonOp = Literal[
    "eq", "notEq", "greaterThan", "greaterThanEquals", "lessThan", "lessThanEquals"
]
NullOp = Literal["isNull", "isNotNull"]
StringOp = Literal["like", "notLike", "startsWith", "endsWith", "contains"]
MembershipOp = Literal["in", "notIn"]
NestedComparisonOp = Literal[
    "nestedEq", "nestedNotEq", "nestedGt", "nestedGte", "nestedLt", "nestedLte"
]
NestedNullOp = Literal["nestedIsNull", "nestedIsNotNull"]


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


@dataclass(frozen=True, slots=True)
class Between:
    """``attr between lower and upper`` (two ordered binds)."""

    attr: str
    lower: Scalar
    upper: Scalar


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


@dataclass(frozen=True, slots=True)
class Membership:
    """``attr in (…)`` / ``not attr in (…)`` over a non-empty value list."""

    op: MembershipOp
    attr: str
    values: tuple[Scalar, ...]


@dataclass(frozen=True, slots=True)
class And:
    """N-ary conjunction; operand order is significant (drives bind order)."""

    operands: tuple[Operation, ...]


@dataclass(frozen=True, slots=True)
class Or:
    """N-ary disjunction; operand order is significant."""

    operands: tuple[Operation, ...]


@dataclass(frozen=True, slots=True)
class Not:
    """Logical negation of one operand."""

    operand: Operation


@dataclass(frozen=True, slots=True)
class Group:
    """An explicit precedence-nesting node (`( … )`)."""

    operand: Operation


@dataclass(frozen=True, slots=True)
class OrderKey:
    """One ordering term of an ``orderBy`` directive.

    ``direction`` is ``None`` when the authored key omitted it (the schema's
    optional ``direction`` defaults to ``asc``). Serde round-trips that absence
    faithfully — an omitted ``direction`` serializes back omitted — while SQL
    lowering treats the absent direction as the ``asc`` default.
    """

    attr: str
    direction: Literal["asc", "desc"] | None = None


@dataclass(frozen=True, slots=True)
class OrderBy:
    """Order an inner query's rows by one or more keys."""

    operand: Operation
    keys: tuple[OrderKey, ...]


@dataclass(frozen=True, slots=True)
class Limit:
    """Cap an inner query's row count."""

    operand: Operation
    count: int


@dataclass(frozen=True, slots=True)
class Distinct:
    """Deduplicate an inner query's rows."""

    operand: Operation


@dataclass(frozen=True, slots=True)
class Narrow:
    """Constrain a polymorphic position to a subset of its subtypes."""

    entity: str
    to: tuple[str, ...]
    operand: Operation


@dataclass(frozen=True, slots=True)
class NestedComparison:
    """A value-object inner-attribute comparison against a typed literal."""

    op: NestedComparisonOp
    path: str
    value: Scalar


@dataclass(frozen=True, slots=True)
class NestedMembership:
    """A value-object inner-attribute membership test over typed literals."""

    path: str
    values: tuple[Scalar, ...]


@dataclass(frozen=True, slots=True)
class NestedNullCheck:
    """A value-object inner-attribute presence test (absence-collapse rule)."""

    op: NestedNullOp
    path: str


@dataclass(frozen=True, slots=True)
class NestedExists:
    """The value object at ``path`` is present / non-empty; optional element ``where``."""

    path: str
    where: Operation | None = None


@dataclass(frozen=True, slots=True)
class NestedNotExists:
    """The complement of :class:`NestedExists`."""

    path: str
    where: Operation | None = None


@dataclass(frozen=True, slots=True)
class Navigate:
    """Filter the queried entity by traversing a relationship (correlated EXISTS)."""

    rel: str
    op: Operation | None = None


@dataclass(frozen=True, slots=True)
class Exists:
    """The queried entity has >=1 related row (optionally matching ``op``)."""

    rel: str
    op: Operation | None = None


@dataclass(frozen=True, slots=True)
class NotExists:
    """The queried entity has no related row (optionally matching ``op``)."""

    rel: str
    op: Operation | None = None


@dataclass(frozen=True, slots=True)
class PathSegment:
    """One hop of a deep-fetch path: a relationship, optionally subtype-narrowed."""

    rel: str
    narrow: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DeepFetch:
    """Resolve ``operand`` then eager-fetch each navigation path."""

    operand: Operation
    paths: tuple[tuple[PathSegment, ...], ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class AsOf:
    """Pin one temporal dimension to a single instant."""

    operand: Operation
    as_of_attr: str
    date: str


@dataclass(frozen=True, slots=True)
class AsOfRange:
    """Scan a temporal dimension across a half-open ``[from, to)`` window."""

    operand: Operation
    as_of_attr: str
    from_: str
    to: str


@dataclass(frozen=True, slots=True)
class History:
    """Return the full milestone set on one axis (no as-of predicate)."""

    operand: Operation
    as_of_attr: str


# The exhaustive read-path operation union (m-op-algebra); m-sql lowers over it.
Operation = (
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
    | OrderBy
    | Limit
    | Distinct
    | Narrow
    | NestedComparison
    | NestedMembership
    | NestedNullCheck
    | NestedExists
    | NestedNotExists
    | Navigate
    | Exists
    | NotExists
    | DeepFetch
    | AsOf
    | AsOfRange
    | History
)
