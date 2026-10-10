from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from parallax.core.metamodel import EntityIdentity

__all__ = [
    "CURRENT_SCALAR_ELEMENT",
    "QUERY_DEFINITION_CODES",
    "And",
    "Comparison",
    "ComparisonOp",
    "CurrentScalarElement",
    "FalseNode",
    "FieldSubject",
    "Group",
    "Membership",
    "MembershipOp",
    "Narrow",
    "Not",
    "NullCheck",
    "NullOp",
    "Or",
    "PredicateNode",
    "Presence",
    "PresenceOp",
    "Quantifier",
    "QuantifierKind",
    "QueryDefinitionError",
    "Range",
    "ScalarLiteral",
    "ScalarSubject",
    "StringMatch",
    "StringOp",
    "SubtypeSelection",
    "TrueNode",
    "canonical_subtype_selection",
]

# A non-null serialized typed literal. Null tests use dedicated nodes.
ScalarLiteral = str | int | float | bool


def _require_non_null_literal(value: object) -> None:
    if value is None:
        raise QueryDefinitionError(
            code="query-expression-invalid",
            message="None is not a Predicate literal; use .is_null() or .is_not_null()",
        )


def _require_non_null_literals(values: tuple[ScalarLiteral, ...]) -> None:
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
QuantifierKind = Literal["any", "all", "none"]
PresenceOp = Literal["exists", "notExists"]


QUERY_DEFINITION_CODES: Final[frozenset[str]] = frozenset(
    {
        "query-target-mismatch",
        "query-expression-invalid",
        "query-path-invalid",
        "query-clause-invalid",
        "query-assignment-invalid",
        "query-not-mutation-compatible",
    }
)
"""The closed query-definition rejection vocabulary.

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
class TrueNode:
    """The constant true predicate: it selects every object its query reaches."""


@dataclass(frozen=True, slots=True)
class FalseNode:
    """The constant false predicate: it selects nothing."""


@dataclass(frozen=True, slots=True)
class FieldSubject:
    """An object field named by its canonical path: Entity-qualified at the
    queried position, relative to the bound object inside a scope."""

    path: str

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("a field subject names a nonempty path")


@dataclass(frozen=True, slots=True)
class CurrentScalarElement:
    """The scalar an enclosing scalar-collection quantifier binds."""


CURRENT_SCALAR_ELEMENT: Final = CurrentScalarElement()

ScalarSubject = FieldSubject | CurrentScalarElement


@dataclass(frozen=True, slots=True)
class Comparison:
    op: ComparisonOp
    subject: ScalarSubject
    value: ScalarLiteral

    def __post_init__(self) -> None:
        _require_non_null_literal(self.value)


@dataclass(frozen=True, slots=True)
class Range:
    """An inclusive range one value must satisfy whole, lower bound first."""

    subject: ScalarSubject
    lower: ScalarLiteral
    upper: ScalarLiteral

    def __post_init__(self) -> None:
        _require_non_null_literal(self.lower)
        _require_non_null_literal(self.upper)


@dataclass(frozen=True, slots=True)
class NullCheck:
    op: NullOp
    subject: FieldSubject


@dataclass(frozen=True, slots=True)
class StringMatch:
    """A string predicate; affix forms escape wildcards, ``like`` passes through.

    ``case_insensitive`` is ``None`` when the authored node omitted the optional
    ``caseInsensitive`` flag, so serde round-trips an omitted flag omitted and an
    explicit ``false``/``true`` verbatim.
    """

    op: StringOp
    subject: ScalarSubject
    value: str
    case_insensitive: bool | None = None

    def __post_init__(self) -> None:
        _require_non_null_literal(self.value)


@dataclass(frozen=True, slots=True)
class Membership:
    op: MembershipOp
    subject: ScalarSubject
    values: tuple[ScalarLiteral, ...]

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
    operand: PredicateNode


@dataclass(frozen=True, slots=True)
class Group:
    """An explicit precedence-nesting node (`( … )`)."""

    operand: PredicateNode


@dataclass(frozen=True, slots=True)
class Quantifier:
    """Whether some (``any``), every (``all``), or no (``none``) element of the
    collection at ``path`` makes ``where`` true; bare ``any`` and ``none`` test
    occupancy alone, and ``all`` always carries ``where``."""

    kind: QuantifierKind
    path: str
    where: PredicateNode | None = None

    def __post_init__(self) -> None:
        if self.kind == "all" and self.where is None:
            raise ValueError("an `all` quantifier carries a `where` predicate")


@dataclass(frozen=True, slots=True)
class Presence:
    """Whether the single object at ``path`` is present (``exists``) or absent."""

    op: PresenceOp
    path: str


@dataclass(frozen=True, slots=True)
class Narrow:
    """``operand`` over a polymorphic position narrowed to a Subtype Selection:
    the current position, or the to-one target ``path`` reaches from it."""

    to: SubtypeSelection
    operand: PredicateNode
    path: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "to", canonical_subtype_selection(self.to))


# The exhaustive read-path Predicate union (m-predicate); m-sql lowers over it.
PredicateNode = (
    TrueNode
    | FalseNode
    | Comparison
    | Range
    | NullCheck
    | StringMatch
    | Membership
    | And
    | Or
    | Not
    | Group
    | Quantifier
    | Presence
    | Narrow
)
