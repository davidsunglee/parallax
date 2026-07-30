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

Nodes here name no declaration and import no frontend: this module reaches no
owner class, no declaration engine, and no hub. What a node does carry is what
its seeding class access handed it — the Metamodel Binding of the hub that class
belongs to, and, for a Relationship Path, the class-aware resolver that answers a
deeper hop. That is how a model-stated rule fires as the node is built: an
assignment's assignability and declared-type agreement, and a deeper hop's own
resolution. A node built directly carries neither and states no such rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, cast, runtime_checkable

from parallax.core.entity._errors import ModelCopyError
from parallax.core.inheritance import WriteAssignmentError, validate_write_assignment
from parallax.core.metamodel import entity_by_name
from parallax.core.op_algebra import (
    And,
    Between,
    Comparison,
    ComparisonOp,
    Exists,
    Group,
    Membership,
    MembershipOp,
    NestedComparison,
    NestedComparisonOp,
    NestedExists,
    NestedMembership,
    NestedMembershipOp,
    NestedNotExists,
    NestedNullCheck,
    NestedRange,
    NestedStringMatch,
    NestedStringOp,
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

    from parallax.core.entity._binding import MetamodelBinding

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
# Each scalar string predicate's nested tag: one fluent method serves both, so the
# same call spells the scalar node on an Attribute and the nested one on a Value
# Object member path.
_NESTED_STRINGS: dict[StringOp, NestedStringOp] = {
    "like": "nestedLike",
    "notLike": "nestedNotLike",
    "startsWith": "nestedStartsWith",
    "endsWith": "nestedEndsWith",
    "contains": "nestedContains",
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
    """A class-level attribute/value-object expression (the seed of a predicate).

    ``binding`` is the Metamodel Binding of the hub the seeding class belongs to,
    carried so an assignment is validated against exactly that model. It is
    absent for an expression built directly and for one seeded from a class no
    hub composed.
    """

    __slots__ = ("_binding", "_entity", "_head", "_path")

    def __init__(
        self,
        entity: str,
        head: str,
        path: tuple[str, ...] = (),
        binding: MetamodelBinding | None = None,
    ) -> None:
        self._entity = entity
        self._head = head
        self._path = path
        self._binding = binding

    @property
    def ref(self) -> AttributeRef:
        """The scalar attribute reference (only for a non-nested attribute)."""
        return AttributeRef(self._entity, self._head)

    def __getattr__(self, name: str) -> AttributeExpr:
        # A deeper value-object hop: Customer.address.city / .geo.country.
        if name.startswith("_"):
            raise AttributeError(name)
        return AttributeExpr(self._entity, self._head, (*self._path, name), self._binding)

    def _dotted(self) -> str:
        return ".".join((self._entity, self._head, *self._path))

    def _cmp(self, kind: str, value: Scalar) -> Predicate:
        if self._path:
            return Predicate(
                NestedComparison(op=_NESTED_CMP[kind], path=self._dotted(), value=value)
            )
        return Predicate(Comparison(op=_SCALAR_CMP[kind], attr=str(self.ref), value=value))

    def __eq__(self, other: object) -> Predicate:  # type: ignore[override] - DSL comparison builds a Predicate, not object's bool
        return self._cmp("eq", _as_scalar(other))

    def __ne__(self, other: object) -> Predicate:  # type: ignore[override] - DSL comparison builds a Predicate, not object's bool
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
        return self._membership("nestedIn", "in", values)

    def not_in(self, values: list[Scalar]) -> Predicate:
        return self._membership("nestedNotIn", "notIn", values)

    def _membership(
        self, nested_op: NestedMembershipOp, scalar_op: MembershipOp, values: list[Scalar]
    ) -> Predicate:
        if self._path:
            return Predicate(
                NestedMembership(op=nested_op, path=self._dotted(), values=tuple(values))
            )
        return Predicate(Membership(op=scalar_op, attr=str(self.ref), values=tuple(values)))

    def between(self, lower: Scalar, upper: Scalar) -> Predicate:
        if self._path:
            return Predicate(NestedRange(path=self._dotted(), lower=lower, upper=upper))
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
        flag = True if case_insensitive else None
        if self._path:
            return Predicate(
                NestedStringMatch(
                    op=_NESTED_STRINGS[op],
                    path=self._dotted(),
                    value=value,
                    case_insensitive=flag,
                )
            )
        return Predicate(StringMatch(op=op, attr=str(self.ref), value=value, case_insensitive=flag))

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
        """An ascending order-by key over this attribute.

        Only the Sort Key these converters produce carries the single-shot
        ``.nulls_first()`` / ``.nulls_last()`` placement modifiers; an Attribute
        Expression itself exposes neither, so placement is authorable exactly where
        a direction is.
        """
        return OrderKey(attr=str(self.ref), direction="asc")

    def desc(self) -> OrderKey:
        """A descending order-by key over this attribute (see :meth:`asc`)."""
        return OrderKey(attr=str(self.ref), direction="desc")

    def set(self, value: object) -> AttributeAssignment:
        """A set-based ``_where``-verb assignment (``Account.balance.set(0)``, spec §5).

        Only a top-level scalar attribute or Value Object member is assignable: a
        Value Object always binds its whole document, so there is no sparse write
        below its boundary. A Value Object value (or a tuple of them) is rendered
        to its canonical document here, the same translation every other write
        input receives, and the rendered value is what the assignment rules then
        see — so the typed path and the serialized path judge one shape.
        """
        if self._path:
            raise TypeError(
                f"{self._dotted()}: only a top-level attribute or value-object member is "
                "assignable via .set(...) — a value object binds its whole document, never "
                "a nested path (m-value-object)"
            )
        serialized = serialize_member(value)
        self._reject_unassignable(serialized)
        return AttributeAssignment(attr=self.ref, value=serialized)

    def _reject_unassignable(self, value: object) -> None:
        """Apply the shared assignment rule family to a rendered value (spec §5).

        The rules are stated once for ``model_copy(update=...)`` (spec §3) and
        referenced by the assignment-bearing verbs, so both rejection points call
        one validator and neither can drift: a primary-key or framework-owned
        target is refused, a scalar value must match its declared neutral type,
        and a Value Object value must be a well-formed document — with ``None``
        legal only where the member is nullable. The rejection is spelled
        ``ModelCopyError`` because it is that same family.

        An expression carrying no Binding reaches no model and so states no rule.
        Neither does one whose Entity a second namespace names locally too: an
        operation reference spells its Entity locally everywhere, so such a
        reference addresses no operation at all. Both leave the rule to the write
        boundary, which states it again where the model is certain.
        """
        if self._binding is None:
            return
        entity = entity_by_name(self._binding.model, self._entity)
        if entity is None:  # pragma: no cover - an ambiguous local name states no rule
            return
        try:
            validate_write_assignment(self._binding.model, entity, self._head, value)
        except WriteAssignmentError as error:
            raise ModelCopyError(str(error)) from error

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

    def __eq__(self, other: object) -> Predicate:  # type: ignore[override] - DSL comparison builds a Predicate, not object's bool
        return self._cmp("eq", _as_scalar(other))

    def __ne__(self, other: object) -> Predicate:  # type: ignore[override] - DSL comparison builds a Predicate, not object's bool
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
        return Predicate(NestedMembership(op="nestedIn", path=self._dotted(), values=tuple(values)))

    def not_in(self, values: list[Scalar]) -> Predicate:
        return Predicate(
            NestedMembership(op="nestedNotIn", path=self._dotted(), values=tuple(values))
        )

    def between(self, lower: Scalar, upper: Scalar) -> Predicate:
        return Predicate(NestedRange(path=self._dotted(), lower=lower, upper=upper))

    def _string(self, op: StringOp, value: str, case_insensitive: bool) -> Predicate:
        return Predicate(
            NestedStringMatch(
                op=_NESTED_STRINGS[op],
                path=self._dotted(),
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

    def is_null(self) -> Predicate:
        return Predicate(NestedNullCheck(op="nestedIsNull", path=self._dotted()))

    def is_not_null(self) -> Predicate:
        return Predicate(NestedNullCheck(op="nestedIsNotNull", path=self._dotted()))

    def __bool__(self) -> bool:
        raise TypeError(_BOOL_HINT)

    def __hash__(self) -> int:  # pragma: no cover - expressions are not dict keys
        return hash(self._path)


def _subtype_names(subtype: type) -> tuple[str, str]:
    """A subtype class's ``(local Entity name, canonical spelling)``.

    Read off the class's own declared identity when it carries one, so this
    module resolves nothing and imports no frontend; a class that declares none
    falls back to its Python name for both. A hop's narrow list is the wire's own
    vocabulary and names each subtype locally, resolved against the hop target's
    namespace, while the path's target is the exact spelling.
    """
    identity = getattr(subtype, "identity", None)
    name = getattr(identity, "name", None)
    canonical = getattr(identity, "canonical", None)
    if isinstance(name, str) and isinstance(canonical, str):
        return name, canonical
    return subtype.__name__, subtype.__name__


class _HopResolver(Protocol):
    """How a Relationship Path continues past the hop it was seeded with.

    A deeper hop names a Python member of the path's current target, and only
    that Entity's own class answers which declaration that is. The class-aware
    member module supplies one of these when it seeds a path, so continuing is a
    call to what the path was handed rather than a class this module reached for:
    given the path's Binding, its canonical target spelling, and the member name,
    it answers that member's own single-hop path, or raises ``AttributeError``
    when the target or the member resolves to none.
    """

    def __call__(self, binding: MetamodelBinding, target: str, name: str) -> RelationshipPath: ...


@dataclass(frozen=True, slots=True)
class RelationshipPath:
    """A chained class-level relationship reference (``Order.items``,
    ``Order.items.statuses``) — the seed of the ``.include(...)`` deep-fetch
    spelling, the hop-level ``.narrow(*subtypes)`` narrowed-view request, and
    the single-hop relationship quantifiers ``.any()``/``.none()``.

    ``segments`` is the traversal so far in ``m-deep-fetch``'s own
    ``PathSegment`` shape, whose relationship references name their owner locally
    as the wire does; ``target`` is the canonical Entity spelling the path
    currently points at, namespace included, so two namespaces sharing a local
    Entity name stay distinguishable. The first hop is statically typed through
    the relationship descriptor's overload; a deeper hop is a declaration
    question, so it is answered by the resolver the seeding class access supplied.

    ``source`` is the Entity the seeding class access reached the first hop
    THROUGH, kept separate from that hop's own relationship identity: ``Dog.owner``
    and ``Dog.doghouse`` both name the Entity ``Dog`` there, whether ``owner`` is
    inherited from ``Animal`` or ``doghouse`` is declared on ``Dog`` itself. It is
    what a Find Query turns into the path-ROOT guard — qualifying which queried
    objects the whole path starts from — so, unlike a hop's own narrow, it lives
    beside ``segments`` rather than inside one, and a deeper hop neither adds nor
    replaces it: a deeper hop is a member lookup on the current target and says
    nothing about where the path is rooted.
    """

    segments: tuple[PathSegment, ...]
    target: str
    source: str | None = None
    # The Binding of the hub the seeding class belongs to, carried so a deeper
    # hop resolves in exactly that model. Absent only for a path built directly,
    # which cannot continue.
    binding: MetamodelBinding | None = field(default=None, repr=False, compare=False)
    # The resolver the seeding relationship descriptor handed over, absent for
    # that same directly built path.
    resolve_hop: _HopResolver | None = field(default=None, repr=False, compare=False)

    @property
    def ref(self) -> RelationshipRef:
        """The first hop's relationship reference (mirrors ``AttributeExpr.ref``)."""
        owner, _, relationship = self.segments[0].rel.rpartition(".")
        return RelationshipRef(owner, relationship)

    def __getattr__(self, name: str) -> RelationshipPath:
        """The next hop, answered by the resolver this path carries.

        The hop names a *Python* member of the current target, and only that
        Entity's own declaration knows which member that is: a member may
        override its canonical name or inherit its declaration, so a canonical
        name re-derived from the Python spelling would miss either. The resolver
        answers the whole hop — the declared member, the segment it seeds, and
        the Entity it points at — and this path only appends it, so one hop reads
        exactly as the first hop it continues.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        if self.binding is None or self.resolve_hop is None:
            raise AttributeError(
                f"{self.target}.{name}: a deeper relationship hop resolves against the "
                "composed model, which this path does not carry"
            )
        hop = self.resolve_hop(self.binding, self.target, name)
        # Only the hop's segments continue this path: a deeper hop's own seeding
        # access is a member lookup on the current target, which qualifies nothing
        # about where the path is rooted.
        return RelationshipPath(
            segments=(*self.segments, *hop.segments),
            target=hop.target,
            source=self.source,
            binding=self.binding,
            resolve_hop=self.resolve_hop,
        )

    def narrow(self, *subtypes: type) -> RelationshipPath:
        """A hop-level narrowed-view request (``Owner.pets.narrow(Dog)``),
        continuable to a deeper hop. Requests the derived narrowed view
        (spec §3), never marking the broad relationship loaded."""
        narrowed = tuple(_subtype_names(subtype) for subtype in subtypes)
        *head, last = self.segments
        new_last = PathSegment(rel=last.rel, narrow=tuple(local for local, _ in narrowed))
        new_target = self.target
        if len(narrowed) == 1:  # a hop narrowed to one subtype points at that subtype
            _, new_target = narrowed[0]
        return RelationshipPath(
            segments=(*head, new_last),
            target=new_target,
            source=self.source,
            binding=self.binding,
            resolve_hop=self.resolve_hop,
        )

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
