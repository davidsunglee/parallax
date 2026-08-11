"""Operation-algebra nodes (m-op-algebra).

Frozen ``slots`` dataclasses for the operation tree the query surface builds and
the corpus serializes. Every node is immutable and shareable; construction is
value-only (metamodel binding is validated by the serde/statement layers, not in
``__init__``). The union :data:`Operation` is the exhaustive read-path algebra
this phase lowers; ``m-sql`` dispatches over it with ``match`` and
``assert_never``. Aggregation (``groupBy``) and the write side are out of scope.

A node that doubles as a Python authoring surface — one a caller composes by
method call rather than by deserializing a document — rejects an illegal
composition through :class:`QueryDefinitionError`, which lives here beside the
rules that raise it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal

from parallax.core.metamodel import EntityIdentity

__all__ = [
    "QUERY_DEFINITION_CODES",
    "All",
    "And",
    "AsOf",
    "AsOfRange",
    "Between",
    "Comparison",
    "ComparisonOp",
    "DeepFetch",
    "EntityQuery",
    "Exists",
    "Group",
    "History",
    "Limit",
    "Membership",
    "MembershipOp",
    "Narrow",
    "Navigate",
    "NavigationPath",
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
    "Operation",
    "Or",
    "OrderBy",
    "OrderKey",
    "PathSegment",
    "QueryDefinitionError",
    "Scalar",
    "StringMatch",
    "StringOp",
]

# A scalar literal usable as a bind (json/yaml primitive).
Scalar = str | int | float | bool | None
TemporalDimension = Literal["valid-time", "transaction-time"]
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
    the two wire-and-model families beside it: ``OperationError`` says a
    serialized operation is malformed, and ``OperationRejectedError`` says a
    well-formed operation is illegal against a model.
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
    optional ``direction`` defaults to ``asc``), and ``nulls`` is ``None`` when it
    omitted the Null Placement (schema default ``last``). Serde round-trips both
    absences faithfully — an omitted member serializes back omitted — while SQL
    lowering treats them as the ``asc`` and ``last`` defaults.

    A Sort Key is a query-definition construct, so a rejected placement
    composition raises :class:`QueryDefinitionError`. The relationship-declaration
    ordering term (``OrderTerm``) carries the same single-shot placement rule but
    is part of a model declaration rather than of a query, so it stays outside
    that family and raises a plain :class:`ValueError`; the two spellings differ
    because the surfaces do, not by accident.
    """

    attr: str
    direction: Literal["asc", "desc"] | None = None
    nulls: Literal["first", "last"] | None = None

    def nulls_first(self) -> OrderKey:
        """This key with NULLs placed first. Single-shot (m-op-algebra)."""
        return self._with_placement("first")

    def nulls_last(self) -> OrderKey:
        """This key with NULLs placed last — the default, stated explicitly."""
        return self._with_placement("last")

    def _with_placement(self, placement: Literal["first", "last"]) -> OrderKey:
        if self.nulls is not None:
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=(
                    f"{self.attr}: null placement is single-shot and is already "
                    f"{self.nulls!r}; derive the key from the unplaced base"
                ),
            )
        return OrderKey(attr=self.attr, direction=self.direction, nulls=placement)


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
class EntityQuery:
    """The normalized query for one root or related Entity.

    Query-wide wrappers are resolved at the planning boundary. SQL compilation
    therefore receives the target and clauses directly, with temporal terms
    already injected into ``predicate``.
    """

    target: EntityIdentity
    predicate: Operation
    narrow_to: tuple[EntityIdentity, ...] | None = None
    order_by: tuple[OrderKey, ...] = ()
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class Narrow:
    """Constrain a polymorphic position to a subset of its subtypes."""

    to: SubtypeSelection
    operand: Operation

    def __post_init__(self) -> None:
        object.__setattr__(self, "to", canonical_subtype_selection(self.to))


@dataclass(frozen=True, slots=True)
class NestedComparison:
    """A value-object inner-attribute comparison against a typed literal."""

    op: NestedComparisonOp
    path: str
    value: Scalar


@dataclass(frozen=True, slots=True)
class NestedRange:
    """A value-object inner-attribute range test against two typed literal bounds.

    One canonical node, never a pair of comparisons: through a Many occurrence the
    flat family is any-element, so `>= lower` and `<= upper` as two nodes could be
    satisfied by two *different* elements, while this node requires one element to
    satisfy the whole range (`m-op-algebra`).
    """

    path: str
    lower: Scalar
    upper: Scalar


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
    narrow: SubtypeSelection = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "narrow", canonical_subtype_selection(self.narrow))


@dataclass(frozen=True, slots=True)
class NavigationPath:
    """One deep-fetch path: the ordered, non-empty hops it traverses, and the
    optional root guard restricting which queried objects it starts from.

    A path is its own node rather than a bare segment tuple, so what qualifies the
    path as a whole stays distinguishable from what qualifies one hop.
    """

    segments: tuple[PathSegment, ...]
    narrow: SubtypeSelection | None = None

    def __post_init__(self) -> None:
        if self.narrow is not None:
            object.__setattr__(self, "narrow", canonical_subtype_selection(self.narrow))


@dataclass(frozen=True, slots=True)
class DeepFetch:
    """Resolve ``operand`` then eager-fetch each navigation path."""

    operand: Operation
    paths: tuple[NavigationPath, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class AsOf:
    """Pin one temporal dimension to a single instant."""

    operand: Operation
    dimension: TemporalDimension
    coordinate: str


@dataclass(frozen=True, slots=True)
class AsOfRange:
    """Scan a temporal dimension across a half-open ``[from, to)`` window."""

    operand: Operation
    dimension: TemporalDimension
    start: str
    end: str


@dataclass(frozen=True, slots=True)
class History:
    """Return the full milestone set on one axis (no as-of predicate)."""

    operand: Operation
    dimension: TemporalDimension


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
    | DeepFetch
    | AsOf
    | AsOfRange
    | History
)
