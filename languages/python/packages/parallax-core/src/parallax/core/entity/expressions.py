"""Typed class-level access carriers and the predicate expression surface.

Class-level attribute access yields an :class:`AttributeExpr` (the SQLAlchemy
``Mapped[T]`` pattern): the seed of an operation predicate, strict-Pyright-clean
without a plugin. Its comparison / string / membership / null operators build
frozen ``m-op-algebra`` nodes wrapped in a :class:`Predicate`, which composes with
``&`` / ``|`` / ``~`` and native parentheses into the canonical boolean tree —
inserting a ``group`` node exactly where an ``or`` binds looser than its enclosing
``and`` so an idiomatic operation can never drift from canonical grouping.
Expressions reject ``__bool__`` (catching accidental ``and`` / ``or`` / ``not``
and chained comparisons), pointing at ``&`` / ``|`` / ``~`` and ``.between()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import overload

from parallax.core.op_algebra import (
    And,
    Between,
    Comparison,
    ComparisonOp,
    Group,
    Membership,
    NestedComparison,
    NestedComparisonOp,
    NestedMembership,
    NestedNullCheck,
    Not,
    NullCheck,
    Operation,
    Or,
    OrderKey,
    Scalar,
    StringMatch,
    StringOp,
)

__all__ = [
    "Attr",
    "AttributeExpr",
    "AttributeRef",
    "Predicate",
    "Rel",
    "RelationshipRef",
    "and_terms",
]

_BOOL_HINT = (
    "a Parallax expression has no truth value; combine predicates with & / | / ~ and "
    "parentheses (not and/or/not), and use .between()/.in_() instead of chained comparisons"
)

_SCALAR_CMP: dict[str, ComparisonOp] = {
    "eq": "eq",
    "ne": "notEq",
    "gt": "greaterThan",
    "ge": "greaterThanEquals",
    "lt": "lessThan",
    "le": "lessThanEquals",
}
_NESTED_CMP: dict[str, NestedComparisonOp] = {
    "eq": "nestedEq",
    "ne": "nestedNotEq",
    "gt": "nestedGt",
    "ge": "nestedGte",
    "lt": "nestedLt",
    "le": "nestedLte",
}


@dataclass(frozen=True, slots=True)
class AttributeRef:
    """A class-level reference to an entity attribute (``Entity.attribute``)."""

    entity: str
    attribute: str

    def __str__(self) -> str:
        return f"{self.entity}.{self.attribute}"


@dataclass(frozen=True, slots=True)
class RelationshipRef:
    """A class-level reference to an entity relationship (``Entity.relationship``)."""

    entity: str
    relationship: str

    def __str__(self) -> str:
        return f"{self.entity}.{self.relationship}"


@dataclass(frozen=True, slots=True)
class Predicate:
    """A built operation predicate; composes with ``&`` / ``|`` / ``~``."""

    op: Operation

    def __and__(self, other: Predicate) -> Predicate:
        return Predicate(And(operands=(*and_terms(self), *and_terms(other))))

    def __or__(self, other: Predicate) -> Predicate:
        return Predicate(Or(operands=(*_or_terms(self), *_or_terms(other))))

    def __invert__(self) -> Predicate:
        return Predicate(Not(operand=self.op))

    def __bool__(self) -> bool:
        raise TypeError(_BOOL_HINT)


def and_terms(pred: Predicate) -> tuple[Operation, ...]:
    if isinstance(pred.op, And):
        return pred.op.operands  # flatten same-combinator nesting (order-preserving)
    if isinstance(pred.op, Or):
        return (Group(operand=pred.op),)  # an `or` under an `and` binds looser -> group
    return (pred.op,)


def _or_terms(pred: Predicate) -> tuple[Operation, ...]:
    if isinstance(pred.op, Or):
        return pred.op.operands  # flatten; an `and` under an `or` needs no group
    return (pred.op,)


class AttributeExpr:
    """A class-level attribute/value-object expression (the seed of a predicate)."""

    __slots__ = ("_entity", "_head", "_path")

    def __init__(self, entity: str, head: str, path: tuple[str, ...] = ()) -> None:
        self._entity = entity
        self._head = head
        self._path = path

    @property
    def ref(self) -> AttributeRef:
        """The scalar attribute reference (only for a non-nested attribute)."""
        return AttributeRef(self._entity, self._head)

    def __getattr__(self, name: str) -> AttributeExpr:
        # A deeper value-object hop: Customer.address.city / .geo.country.
        if name.startswith("_"):
            raise AttributeError(name)
        return AttributeExpr(self._entity, self._head, (*self._path, name))

    def _dotted(self) -> str:
        return ".".join((self._entity, self._head, *self._path))

    def _cmp(self, kind: str, value: Scalar) -> Predicate:
        if self._path:
            return Predicate(
                NestedComparison(op=_NESTED_CMP[kind], path=self._dotted(), value=value)
            )
        return Predicate(Comparison(op=_SCALAR_CMP[kind], attr=str(self.ref), value=value))

    def __eq__(self, other: object) -> Predicate:  # type: ignore[override]
        return self._cmp("eq", _as_scalar(other))

    def __ne__(self, other: object) -> Predicate:  # type: ignore[override]
        return self._cmp("ne", _as_scalar(other))

    def __gt__(self, other: Scalar) -> Predicate:
        return self._cmp("gt", other)

    def __ge__(self, other: Scalar) -> Predicate:
        return self._cmp("ge", other)

    def __lt__(self, other: Scalar) -> Predicate:
        return self._cmp("lt", other)

    def __le__(self, other: Scalar) -> Predicate:
        return self._cmp("le", other)

    def is_(self, value: bool) -> Predicate:
        """The lint-clean boolean spelling; serializes to the identical ``eq`` node."""
        return self._cmp("eq", value)

    def in_(self, values: list[Scalar]) -> Predicate:
        if self._path:
            return Predicate(NestedMembership(path=self._dotted(), values=tuple(values)))
        return Predicate(Membership(op="in", attr=str(self.ref), values=tuple(values)))

    def not_in(self, values: list[Scalar]) -> Predicate:
        return Predicate(Membership(op="notIn", attr=str(self.ref), values=tuple(values)))

    def between(self, lower: Scalar, upper: Scalar) -> Predicate:
        return Predicate(Between(attr=str(self.ref), lower=lower, upper=upper))

    def is_null(self) -> Predicate:
        if self._path:
            return Predicate(NestedNullCheck(op="nestedIsNull", path=self._dotted()))
        return Predicate(NullCheck(op="isNull", attr=str(self.ref)))

    def is_not_null(self) -> Predicate:
        if self._path:
            return Predicate(NestedNullCheck(op="nestedIsNotNull", path=self._dotted()))
        return Predicate(NullCheck(op="isNotNull", attr=str(self.ref)))

    def _string(self, op: StringOp, value: str, case_insensitive: bool) -> Predicate:
        return Predicate(
            StringMatch(op=op, attr=str(self.ref), value=value, case_insensitive=case_insensitive)
        )

    def like(self, value: str, *, case_insensitive: bool = False) -> Predicate:
        return self._string("like", value, case_insensitive)

    def not_like(self, value: str, *, case_insensitive: bool = False) -> Predicate:
        return self._string("notLike", value, case_insensitive)

    def starts_with(self, value: str, *, case_insensitive: bool = False) -> Predicate:
        return self._string("startsWith", value, case_insensitive)

    def ends_with(self, value: str, *, case_insensitive: bool = False) -> Predicate:
        return self._string("endsWith", value, case_insensitive)

    def contains(self, value: str, *, case_insensitive: bool = False) -> Predicate:
        return self._string("contains", value, case_insensitive)

    def asc(self) -> OrderKey:
        """An ascending order-by key over this attribute."""
        return OrderKey(attr=str(self.ref), direction="asc")

    def desc(self) -> OrderKey:
        """A descending order-by key over this attribute."""
        return OrderKey(attr=str(self.ref), direction="desc")

    def __bool__(self) -> bool:
        raise TypeError(_BOOL_HINT)

    def __hash__(self) -> int:  # pragma: no cover - expressions are not dict keys
        return hash((self._entity, self._head, self._path))


def _as_scalar(value: object) -> Scalar:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"expected a scalar literal, got {type(value).__name__}")


class Attr[T]:
    """Typed attribute descriptor: class access → ``AttributeExpr``, instance → ``T``."""

    __slots__ = ("_py_name", "_ref")

    def __init__(self, ref: AttributeRef, py_name: str) -> None:
        self._ref = ref
        self._py_name = py_name

    @overload
    def __get__(self, obj: None, _owner: type, /) -> AttributeExpr: ...
    @overload
    def __get__(self, obj: object, _owner: type | None = None, /) -> T: ...
    def __get__(self, obj: object | None, _owner: type | None = None) -> AttributeExpr | T:
        if obj is None:
            return AttributeExpr(self._ref.entity, self._ref.attribute)
        value: T = obj.__dict__[self._py_name]
        return value


class Rel[T]:
    """Typed relationship descriptor: class access → ``RelationshipRef``, instance → ``T``."""

    __slots__ = ("_py_name", "_ref")

    def __init__(self, ref: RelationshipRef, py_name: str) -> None:
        self._ref = ref
        self._py_name = py_name

    @overload
    def __get__(self, obj: None, _owner: type, /) -> RelationshipRef: ...
    @overload
    def __get__(self, obj: object, _owner: type | None = None, /) -> T: ...
    def __get__(self, obj: object | None, _owner: type | None = None) -> RelationshipRef | T:
        if obj is None:
            return self._ref
        value: T = obj.__dict__[self._py_name]
        return value
