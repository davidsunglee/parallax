"""Immutable operation nodes built from class-level member access.

Class-level attribute access yields an :class:`AttributeExpr` (the SQLAlchemy
``Mapped[T]`` pattern): the seed of an operation predicate, strict-Pyright-clean
without a plugin. Its comparison / string / membership / null operators build
frozen ``m-op-algebra`` nodes wrapped in a :class:`Predicate`, which composes with
``&`` / ``|`` / ``~`` and native parentheses into the canonical boolean tree —
inserting a ``group`` node exactly where an ``or`` binds looser than its enclosing
``and`` so an idiomatic operation can never drift from canonical grouping.
Expressions reject ``__bool__`` (catching accidental ``and`` / ``or`` / ``not``
and chained comparisons), pointing at ``&`` / ``|`` / ``~`` and ``.between()``.

Class-level relationship access yields a :class:`RelationshipPath`: the seed of
the deep-fetch ``.include(...)`` spelling, the hop-level narrowed-view request,
and the single-hop relationship quantifiers. :class:`ElementAttributeExpr` is the
Value Object element-scoped carrier, always building element-relative ``nested*``
nodes for use inside a quantifier's ``where=`` scope.

Nodes here receive every model fact explicitly and look nothing up: this module
imports no owner class, no declaration engine, and no hub.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast, runtime_checkable

from parallax.core.op_algebra import (
    And,
    Between,
    Comparison,
    ComparisonOp,
    Exists,
    Group,
    Membership,
    NestedComparison,
    NestedComparisonOp,
    NestedExists,
    NestedMembership,
    NestedNotExists,
    NestedNullCheck,
    Not,
    NotExists,
    NullCheck,
    Operation,
    Or,
    OrderKey,
    PathSegment,
    Scalar,
    StringMatch,
    StringOp,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "UNLOADED",
    "AttributeAssignment",
    "AttributeExpr",
    "AttributeRef",
    "ElementAttributeExpr",
    "Predicate",
    "RelationshipPath",
    "RelationshipRef",
    "and_terms",
    "conjoin",
    "serialize_member",
]


@runtime_checkable
class _Documentable(Protocol):
    """A value that renders itself as a canonical nested document.

    Value Objects satisfy this. Naming the capability structurally rather than
    importing the frontend keeps this module free of an edge back into the
    declaration cluster.
    """

    def __parallax_document__(self) -> dict[str, object]: ...


class _Unloaded:
    """The private closed-world sentinel a frozen node's relationship field holds
    when its path was outside the include set (spec §3); never a public value."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "UNLOADED"


UNLOADED: _Unloaded = _Unloaded()

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
class AttributeAssignment:
    """One typed ``_where``-verb assignment (``Attr.set(value)``, spec §5).

    The entity-scoped spelling of a predicate-write assignment, built on the same
    attribute-expression surface a predicate is built on. This scope stays free of
    ``parallax.core.unit_work``, so the write boundary translates it to the
    canonical write assignment.
    """

    attr: AttributeRef
    value: object

    def __str__(self) -> str:
        return str(self.attr)


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


def conjoin(predicates: Sequence[Predicate]) -> Operation | None:
    """The big-AND of ``predicates`` (flattened, order-preserving), or ``None``
    for zero arguments — the shared builder behind every variadic predicate
    scope, so a bare presence test, a single predicate, and a conjunction can
    never drift from the whole-statement combination."""
    if not predicates:
        return None
    if len(predicates) == 1:
        return predicates[0].op
    operands: list[Operation] = []
    for predicate in predicates:
        operands.extend(and_terms(predicate))
    return And(operands=tuple(operands))


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

    def any(self, *predicates: Predicate) -> Predicate:
        """The value-object member is present/non-empty (optionally matching
        ``predicates``, same-element composed): ``nestedExists`` over this
        value-object-terminated path. Zero arguments emit the bare presence
        test; the interior predicates are built from the value object's own
        element-scoped attributes, never re-prefixed."""
        return Predicate(NestedExists(path=self._dotted(), where=conjoin(predicates)))

    def none(self, *predicates: Predicate) -> Predicate:
        """The complement of :meth:`any` — ``nestedNotExists``."""
        return Predicate(NestedNotExists(path=self._dotted(), where=conjoin(predicates)))

    def _string(self, op: StringOp, value: str, case_insensitive: bool) -> Predicate:
        # The fluent surface authors the canonical minimal form: an unset flag
        # omits `caseInsensitive` (None), a set flag emits `true`. It never
        # authors an explicit `false` — that only arises from deserializing a
        # document that spelled it out (round-trip fidelity lives in the serde).
        return Predicate(
            StringMatch(
                op=op,
                attr=str(self.ref),
                value=value,
                case_insensitive=True if case_insensitive else None,
            )
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

    def set(self, value: object) -> AttributeAssignment:
        """A set-based ``_where``-verb assignment (``Account.balance.set(0)``, spec §5).

        Only a top-level scalar attribute or Value Object member is assignable: a
        Value Object always binds its whole document, so there is no sparse write
        below its boundary. A Value Object value (or a tuple of them) is rendered
        to its canonical document here, the same translation every other write
        input receives.
        """
        if self._path:
            raise TypeError(
                f"{self._dotted()}: only a top-level attribute or value-object member is "
                "assignable via .set(...) — a value object binds its whole document, never "
                "a nested path (m-value-object)"
            )
        return AttributeAssignment(attr=self.ref, value=serialize_member(value))

    def __bool__(self) -> bool:
        raise TypeError(_BOOL_HINT)

    def __hash__(self) -> int:  # pragma: no cover - expressions are not dict keys
        return hash((self._entity, self._head, self._path))


def _as_scalar(value: object) -> Scalar:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"expected a scalar literal, got {type(value).__name__}")


def serialize_member(value: object) -> object:
    """A member's write-row value: a Value Object renders to its canonical
    document, a tuple of them to a list of documents (a Many occurrence), and
    every other value passes through unchanged."""
    if isinstance(value, _Documentable):
        return value.__parallax_document__()
    if isinstance(value, tuple):
        items = cast("tuple[object, ...]", value)
        return [
            item.__parallax_document__() if isinstance(item, _Documentable) else item
            for item in items
        ]
    return value


class ElementAttributeExpr:
    """A Value Object element-scoped attribute expression (``Phone.type``).

    Always builds element-relative ``nested*`` nodes with no leading entity
    prefix, for use inside a relationship or value-object quantifier's interior
    predicates. Deeper hops resolve dynamically, mirroring
    :class:`AttributeExpr`'s own value-object hop.
    """

    __slots__ = ("_path",)

    def __init__(self, path: tuple[str, ...]) -> None:
        self._path = path

    def __getattr__(self, name: str) -> ElementAttributeExpr:
        if name.startswith("_"):
            raise AttributeError(name)
        return ElementAttributeExpr((*self._path, name))

    def _dotted(self) -> str:
        return ".".join(self._path)

    def _cmp(self, kind: str, value: Scalar) -> Predicate:
        return Predicate(NestedComparison(op=_NESTED_CMP[kind], path=self._dotted(), value=value))

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
        return self._cmp("eq", value)

    def in_(self, values: list[Scalar]) -> Predicate:
        return Predicate(NestedMembership(path=self._dotted(), values=tuple(values)))

    def is_null(self) -> Predicate:
        return Predicate(NestedNullCheck(op="nestedIsNull", path=self._dotted()))

    def is_not_null(self) -> Predicate:
        return Predicate(NestedNullCheck(op="nestedIsNotNull", path=self._dotted()))

    def __bool__(self) -> bool:
        raise TypeError(_BOOL_HINT)

    def __hash__(self) -> int:  # pragma: no cover - expressions are not dict keys
        return hash(self._path)


def _target_entity_name(subtype: type) -> str:
    """A subtype class's canonical Entity name.

    Read off the class's own declared identity when it carries one, so this
    module resolves nothing and imports no frontend; a class that declares none
    falls back to its Python name.
    """
    identity = getattr(subtype, "identity", None)
    name = getattr(identity, "name", None)
    return name if isinstance(name, str) else subtype.__name__


@dataclass(frozen=True, slots=True)
class RelationshipPath:
    """A chained class-level relationship reference (``Order.items``,
    ``Order.items.statuses``) — the seed of the ``.include(...)`` deep-fetch
    spelling, the hop-level ``.narrow(*subtypes)`` narrowed-view request, and
    the single-hop relationship quantifiers ``.any()``/``.none()``.

    ``segments`` is the traversal so far in ``m-deep-fetch``'s own
    ``PathSegment`` shape; ``target`` is the canonical Entity name the path
    currently points at. The first hop is statically typed through the
    relationship descriptor's overload; a deeper hop resolves against the
    model, which needs the hub the path was seeded from.
    """

    segments: tuple[PathSegment, ...]
    target: str

    @property
    def ref(self) -> RelationshipRef:
        """The first hop's relationship reference (mirrors ``AttributeExpr.ref``)."""
        owner, _, relationship = self.segments[0].rel.rpartition(".")
        return RelationshipRef(owner, relationship)

    def __getattr__(self, name: str) -> RelationshipPath:
        if name.startswith("_"):
            raise AttributeError(name)
        raise AttributeError(
            f"{self.target}.{name}: a deeper relationship hop resolves against the "
            "composed model, which this path does not carry"
        )

    def narrow(self, *subtypes: type) -> RelationshipPath:
        """A hop-level narrowed-view request (``Owner.pets.narrow(Dog)``),
        continuable to a deeper hop. Requests the derived narrowed view
        (spec §3), never marking the broad relationship loaded."""
        names = tuple(_target_entity_name(subtype) for subtype in subtypes)
        *head, last = self.segments
        new_last = PathSegment(rel=last.rel, narrow=names)
        new_target = names[0] if len(names) == 1 else self.target
        return RelationshipPath(segments=(*head, new_last), target=new_target)

    def any(self, *predicates: Predicate) -> Predicate:
        """The single-hop relationship quantifier: ``>= 1`` related row
        (optionally matching ``predicates``), serializing to ``exists``."""
        return Predicate(Exists(rel=self._single_hop_ref(), op=conjoin(predicates)))

    def none(self, *predicates: Predicate) -> Predicate:
        """The complement of :meth:`any` — ``notExists``."""
        return Predicate(NotExists(rel=self._single_hop_ref(), op=conjoin(predicates)))

    def _single_hop_ref(self) -> str:
        if len(self.segments) != 1:
            raise ValueError(
                ".any()/.none() quantify a single relationship hop, not a multi-hop "
                "include path (m-navigate)"
            )
        return self.segments[0].rel
