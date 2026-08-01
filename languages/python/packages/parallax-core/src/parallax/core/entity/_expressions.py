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
owner class, no declaration engine, no Domain Model, and no Metamodel. What a
node does carry is what its seeding class access handed it — for an Attribute
Expression, the member's own declared Metadata, which is exactly what an
assignment's assignability, nullability, and declared-type rules read. Every
rule that needs a whole model instead — an attribute reference's position, a
narrow's effective set, an include path's legality, and a relationship hop past
the first — is stated once at execution preflight, against the model actually
connected.

Type parameters read the same way everywhere in the frontend: ``E`` is the Entity
a value is rooted at — its position; ``S`` a subtype of that position; ``R`` the
related Entity a relationship hop reaches; ``T`` a declared Python value type;
and ``V`` a Value Object class. ``E``, ``S``, and ``R`` are always Entities and
``T`` never is, so a signature is readable without tracing where each parameter
was solved.

:class:`Predicate`, :class:`AllPredicate`, :class:`SortKey`, and
:class:`AttributeAssignment` are contravariant in ``E``, which is the inheritance
rule expressed as variance: an ancestor's member is addressable from a descendant
position, a descendant's member is not addressable from an ancestor position.
:class:`RelationshipPath` is COVARIANT in both parameters, for the opposite
reason: its source narrows which queried objects the path starts from, so any
descendant of the queried Entity is a legal include source, and its target is
what the path points at, so a narrowed hop stands wherever the broad one does.
``E`` and ``R`` appear in no field of any of these values, so each variance claim
is stated by its own checker-only phantom rather than inferred from the runtime
shape.

Recommended style, not a rule the parameters enforce: START EVERY TERM FROM THE
QUERIED ENTITY. Prefer ``Dog.where((Dog.name == n) & (Dog.bark_volume > v))``
over spelling an inherited member through the class that declares it. It costs
nothing on the wire — ``Dog.name`` and ``Animal.name`` emit the identical
operation, because the expression is built from the declaring class either way —
and it leaves every composition in one position, which is trivially well-typed.

What the parameters do NOT catch is recorded where it is decided rather than
discovered. A predicate's value is a WIRE LITERAL, not a member value: the
neutral contract spells a decimal member's comparison as the number ``600.00``,
so a value parameter narrowed to the member's declared Python type would refuse
the canonical spelling. ``__eq__`` / ``__ne__`` keep ``object`` for a second
reason on top of that one: narrowing them is a Liskov violation against
``object.__eq__``. So ``Order.total == "abc"`` is not a static rejection, and
where the neutral contract states a literal-type rule the model-aware validator
is what states it — the same mismatch one value-object hop deeper draws
``nested-literal-type-mismatch``. A value-object hop past the occurrence
(``Customer.address.city``) likewise keeps its Entity and erases its leaf type,
so the member's existence and type are runtime questions too.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

from parallax.core.entity._errors import ModelCopyError
from parallax.core.metamodel import (
    AttributeMetadata,
    ValueObjectMetadata,
    WriteAssignmentError,
    judge_assignment,
)
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

__all__ = [
    "UNLOADED",
    "AllPredicate",
    "AttributeAssignment",
    "AttributeExpr",
    "AttributeRef",
    "ElementAttributeExpr",
    "Predicate",
    "RelationshipPath",
    "RelationshipRef",
    "SortKey",
    "and_terms",
    "conjoin",
    "serialize_member",
    "snake_to_camel",
]


def snake_to_camel(name: str) -> str:
    """The canonical member name a snake_case Python spelling denotes.

    An operation reference names members canonically, so this is the rule that
    turns an authored member spelling into the one the wire carries. It lives
    beside the references it builds because a relationship hop past the first
    reaches no declaration and has only the spelling to go on.
    """
    head, *tail = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


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
class AttributeAssignment[E]:
    """One typed ``_where``-verb assignment (``Attr.set(value)``, spec §5).

    The entity-scoped spelling of a predicate-write assignment, built on the same
    attribute-expression surface a predicate is built on. This scope stays free of
    ``parallax.core.unit_work``, so the write boundary translates it to the
    canonical write assignment.

    Contravariant in ``E`` for the reason a Predicate is: an assignment written
    against an ancestor's member applies to every descendant position, and one
    written against a descendant's member applies to none of its ancestors'.
    """

    attr: AttributeRef
    value: object

    if TYPE_CHECKING:

        def _assigns_to(self, entity: E) -> None:
            """Never defined at run time and never called: the input position
            that makes ``E`` contravariant (see :class:`Predicate`)."""

    def __str__(self) -> str:
        return str(self.attr)


@dataclass(frozen=True, slots=True)
class SortKey[E]:
    """One ordering term over the Entity position ``E``.

    Wraps the canonical ``OrderKey`` rather than being one, so a sort key carries
    the position it was built from while the node it holds stays serializable and
    parameter-free. The Null Placement modifiers stay here — an Attribute
    Expression exposes neither — and delegate to the canonical node, so the
    single-shot placement rule has one implementation.

    Contravariant in ``E``: an ancestor's member orders every descendant
    position, and a descendant's member orders none of its ancestors'. That is
    the same rule the validator states of an order key's attribute reference
    against the ordered rows' active position.
    """

    key: OrderKey

    if TYPE_CHECKING:

        def _orders(self, entity: E) -> None:
            """Never defined at run time and never called: the input position
            that makes ``E`` contravariant (see :class:`Predicate`)."""

    def nulls_first(self) -> SortKey[E]:
        """This key with NULLs placed first. Single-shot (m-op-algebra)."""
        return SortKey(self.key.nulls_first())

    def nulls_last(self) -> SortKey[E]:
        """This key with NULLs placed last — the default, stated explicitly."""
        return SortKey(self.key.nulls_last())


@dataclass(frozen=True, slots=True)
class AllPredicate[E]:
    """The explicitly unfiltered query over the Entity position ``E``
    (``Entity.all``).

    A distinct type rather than a :class:`Predicate`, and deliberately without
    boolean operators: ``all`` is the whole filter or it is not the filter at
    all, so combining it with a term is neither a spelling the algebra has nor
    one a developer means. Both refusals hold on both sides — no operator to
    call at run time, and none to solve for statically.

    Contravariant in ``E`` like every other addressed value. Nothing on the wire
    distinguishes ``Dog.all`` from ``Animal.all`` — an ``all`` node names no
    position — so this parameter is the only thing that refuses an unfiltered
    query written against a position the query is not at.
    """

    op: Operation

    if TYPE_CHECKING:

        def _addresses(self, entity: E) -> None:
            """Never defined at run time and never called: the input position
            that makes ``E`` contravariant (see :class:`Predicate`)."""

    def __bool__(self) -> bool:
        raise TypeError(_BOOL_HINT)


@dataclass(frozen=True, slots=True)
class Predicate[E]:
    """A built operation predicate over the Entity position ``E``; composes with
    ``&`` / ``|`` / ``~``.

    Contravariant in ``E``: a predicate rooted at an ancestor addresses any
    descendant position, and one rooted at a descendant addresses none of its
    ancestors' positions.
    """

    op: Operation

    if TYPE_CHECKING:

        def _addresses(self, entity: E) -> None:
            """Never defined at run time and never called.

            ``E`` appears in no field, so without an input position a checker
            infers it as bivariant and both assignment directions succeed. This
            is the input position, and it is the whole mechanism.
            """

        def __rand__[F](self: Predicate[F], other: Predicate[F], /) -> Predicate[F]:
            """The reflected twin of :meth:`__and__`, for the checker alone.

            A checker solves ``F`` from the LEFT operand before it reads the
            right one, so a combination whose right operand is the NARROWER of
            the two would otherwise fail to check at all. A checker falls back
            to the right operand's reflected operator exactly then, and that
            solves ``F`` from the narrower side — which is the meet either way,
            so one composition reads identically in both operand orders.

            Never reached at run time: :meth:`__and__` is defined and accepts
            every predicate, so Python never consults this, and the operand
            order of the tree that gets built is always left to right.
            """
            ...

        def __ror__[F](self: Predicate[F], other: Predicate[F], /) -> Predicate[F]:
            """The reflected twin of :meth:`__or__` (see :meth:`__rand__`)."""
            ...

    # A combination addresses every position BOTH operands address — the MEET of
    # the two — and solving ONE parameter from both operands is how that meet is
    # spelled: `E` is contravariant, so `Predicate[X]` satisfies `Predicate[F]`
    # only where `F` is a subtype of `X`, and the only `F` both operands satisfy
    # is the narrower position. So `Animal.name == n` combined with
    # `Dog.bark_volume > v` addresses `Dog`: a `Dog` query takes it, an `Animal`
    # query is refused statically, and neither answer turns on operand order.
    def __and__[F](self: Predicate[F], other: Predicate[F], /) -> Predicate[F]:
        return Predicate(And(operands=(*and_terms(self), *and_terms(other))))

    def __or__[F](self: Predicate[F], other: Predicate[F], /) -> Predicate[F]:
        return Predicate(Or(operands=(*_or_terms(self), *_or_terms(other))))

    def __invert__(self) -> Predicate[E]:
        return Predicate(Not(operand=self.op))

    def __bool__(self) -> bool:
        raise TypeError(_BOOL_HINT)


def and_terms(pred: Predicate[Any] | AllPredicate[Any]) -> tuple[Operation, ...]:
    if isinstance(pred.op, And):
        return pred.op.operands  # flatten same-combinator nesting (order-preserving)
    if isinstance(pred.op, Or):
        return (Group(operand=pred.op),)  # an `or` under an `and` binds looser -> group
    return (pred.op,)


def _or_terms(pred: Predicate[Any]) -> tuple[Operation, ...]:
    if isinstance(pred.op, Or):
        return pred.op.operands  # flatten; an `and` under an `or` needs no group
    return (pred.op,)


def conjoin(predicates: Sequence[Predicate[Any]]) -> Operation | None:
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


class AttributeExpr[E, T]:
    """A class-level attribute/value-object expression (the seed of a predicate).

    ``E`` is the Entity the seeding class access went through — the position
    every predicate this expression builds is rooted at — and ``T`` the member's
    declared Python type.

    ``member`` is the seeding member's own declared Metadata, which the
    declaration that installed the descriptor was already holding. It is what
    ``.set(...)`` judges against, so an assignment states its whole rule with no
    model anywhere; it is absent for an expression built directly, which
    therefore states no assignment rule and leaves it to the write boundary.
    """

    __slots__ = ("_entity", "_head", "_member", "_path")

    def __init__(
        self,
        entity: str,
        head: str,
        path: tuple[str, ...] = (),
        member: AttributeMetadata | ValueObjectMetadata | None = None,
    ) -> None:
        self._entity = entity
        self._head = head
        self._path = path
        self._member = member

    @property
    def ref(self) -> AttributeRef:
        """The scalar attribute reference (only for a non-nested attribute)."""
        return AttributeRef(self._entity, self._head)

    def __getattr__(self, name: str) -> AttributeExpr[E, Any]:
        # A deeper value-object hop: Customer.address.city / .geo.country.
        if name.startswith("_"):
            raise AttributeError(name)
        return AttributeExpr(self._entity, self._head, (*self._path, name), self._member)

    def _dotted(self) -> str:
        return ".".join((self._entity, self._head, *self._path))

    def _cmp(self, kind: str, value: Scalar) -> Predicate[E]:
        if self._path:
            return Predicate(
                NestedComparison(op=_NESTED_CMP[kind], path=self._dotted(), value=value)
            )
        return Predicate(Comparison(op=_SCALAR_CMP[kind], attr=str(self.ref), value=value))

    def __eq__(self, other: object) -> Predicate[E]:  # type: ignore[override] - DSL comparison builds a Predicate, not object's bool
        return self._cmp("eq", _as_scalar(other))

    def __ne__(self, other: object) -> Predicate[E]:  # type: ignore[override] - DSL comparison builds a Predicate, not object's bool
        return self._cmp("ne", _as_scalar(other))

    def __gt__(self, other: Scalar) -> Predicate[E]:
        return self._cmp("gt", other)

    def __ge__(self, other: Scalar) -> Predicate[E]:
        return self._cmp("ge", other)

    def __lt__(self, other: Scalar) -> Predicate[E]:
        return self._cmp("lt", other)

    def __le__(self, other: Scalar) -> Predicate[E]:
        return self._cmp("le", other)

    def is_(self, value: bool) -> Predicate[E]:
        """The lint-clean boolean spelling; serializes to the identical ``eq`` node."""
        return self._cmp("eq", value)

    def in_(self, values: list[Scalar]) -> Predicate[E]:
        return self._membership("nestedIn", "in", values)

    def not_in(self, values: list[Scalar]) -> Predicate[E]:
        return self._membership("nestedNotIn", "notIn", values)

    def _membership(
        self, nested_op: NestedMembershipOp, scalar_op: MembershipOp, values: list[Scalar]
    ) -> Predicate[E]:
        if self._path:
            return Predicate(
                NestedMembership(op=nested_op, path=self._dotted(), values=tuple(values))
            )
        return Predicate(Membership(op=scalar_op, attr=str(self.ref), values=tuple(values)))

    def between(self, lower: Scalar, upper: Scalar) -> Predicate[E]:
        if self._path:
            return Predicate(NestedRange(path=self._dotted(), lower=lower, upper=upper))
        return Predicate(Between(attr=str(self.ref), lower=lower, upper=upper))

    def is_null(self) -> Predicate[E]:
        if self._path:
            return Predicate(NestedNullCheck(op="nestedIsNull", path=self._dotted()))
        return Predicate(NullCheck(op="isNull", attr=str(self.ref)))

    def is_not_null(self) -> Predicate[E]:
        if self._path:
            return Predicate(NestedNullCheck(op="nestedIsNotNull", path=self._dotted()))
        return Predicate(NullCheck(op="isNotNull", attr=str(self.ref)))

    def any(self, *predicates: Predicate[Any]) -> Predicate[E]:
        """The value-object member is present/non-empty (optionally matching
        ``predicates``, same-element composed): ``nestedExists`` over this
        value-object-terminated path. Zero arguments emit the bare presence
        test; the interior predicates are built from the value object's own
        element-scoped attributes, never re-prefixed."""
        return Predicate(NestedExists(path=self._dotted(), where=conjoin(predicates)))

    def none(self, *predicates: Predicate[Any]) -> Predicate[E]:
        """The complement of :meth:`any` — ``nestedNotExists``."""
        return Predicate(NestedNotExists(path=self._dotted(), where=conjoin(predicates)))

    def _string(self, op: StringOp, value: str, case_insensitive: bool) -> Predicate[E]:
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

    def like(self, value: str, *, case_insensitive: bool = False) -> Predicate[E]:
        return self._string("like", value, case_insensitive)

    def not_like(self, value: str, *, case_insensitive: bool = False) -> Predicate[E]:
        return self._string("notLike", value, case_insensitive)

    def starts_with(self, value: str, *, case_insensitive: bool = False) -> Predicate[E]:
        return self._string("startsWith", value, case_insensitive)

    def ends_with(self, value: str, *, case_insensitive: bool = False) -> Predicate[E]:
        return self._string("endsWith", value, case_insensitive)

    def contains(self, value: str, *, case_insensitive: bool = False) -> Predicate[E]:
        return self._string("contains", value, case_insensitive)

    def asc(self) -> SortKey[E]:
        """An ascending order-by key over this attribute.

        Only the Sort Key these converters produce carries the single-shot
        ``.nulls_first()`` / ``.nulls_last()`` placement modifiers; an Attribute
        Expression itself exposes neither, so placement is authorable exactly where
        a direction is.
        """
        return SortKey(OrderKey(attr=str(self.ref), direction="asc"))

    def desc(self) -> SortKey[E]:
        """A descending order-by key over this attribute (see :meth:`asc`)."""
        return SortKey(OrderKey(attr=str(self.ref), direction="desc"))

    def set(self, value: T) -> AttributeAssignment[E]:
        """A set-based ``_where``-verb assignment (``Account.balance.set(0)``, spec §5).

        Only a top-level scalar attribute or Value Object member is assignable: a
        Value Object always binds its whole document, so there is no sparse write
        below its boundary. A Value Object value (or a tuple of them) is rendered
        to its canonical document here, the same translation every other write
        input receives, and the rendered value is what the assignment rules then
        see — so the typed path and the serialized path judge one shape.

        The value parameter is the member's own declared type, unlike a
        comparison's: an assignment's value genuinely IS a member value rather
        than a wire literal. The rendered document a Value Object member equally
        accepts is what that narrowing costs — a spelling the rules still judge
        and the parameter no longer admits.
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
        one judgement and neither can drift: a primary-key, read-only, or
        framework-owned target is refused, a scalar value must match its declared
        neutral type, and a Value Object value must be a well-formed document —
        with ``None`` legal only where the member is nullable. The rejection is
        spelled ``ModelCopyError`` because it is that same family.

        The member the descriptor installed is the whole input, so this states
        its rule with no model: which member a name resolves to was decided by
        Python's own attribute lookup, and ``inheritance-member-shadowing``
        guarantees that resolution is unambiguous within any accepted model. An
        expression built directly carries no member and states no rule, leaving
        it to the write boundary.
        """
        if self._member is None:
            return
        try:
            judge_assignment(self._member, value)
        except WriteAssignmentError as error:
            raise ModelCopyError(f"{self._entity}.{error}") from error

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


class ElementAttributeExpr[V, T]:
    """A Value Object element-scoped attribute expression (``Phone.type``).

    ``V`` is the Value Object class the member was reached through and ``T`` its
    declared Python type, so mixing two Value Objects' members inside one
    quantifier scope is refused the same way mixing two Entities' members is.

    Always builds element-relative ``nested*`` nodes with no leading entity
    prefix, for use inside a relationship or value-object quantifier's interior
    predicates. Deeper hops resolve dynamically, mirroring
    :class:`AttributeExpr`'s own value-object hop.
    """

    __slots__ = ("_path",)

    def __init__(self, path: tuple[str, ...]) -> None:
        self._path = path

    def __getattr__(self, name: str) -> ElementAttributeExpr[V, Any]:
        if name.startswith("_"):
            raise AttributeError(name)
        return ElementAttributeExpr((*self._path, name))

    def _dotted(self) -> str:
        return ".".join(self._path)

    def _cmp(self, kind: str, value: Scalar) -> Predicate[V]:
        return Predicate(NestedComparison(op=_NESTED_CMP[kind], path=self._dotted(), value=value))

    def __eq__(self, other: object) -> Predicate[V]:  # type: ignore[override] - DSL comparison builds a Predicate, not object's bool
        return self._cmp("eq", _as_scalar(other))

    def __ne__(self, other: object) -> Predicate[V]:  # type: ignore[override] - DSL comparison builds a Predicate, not object's bool
        return self._cmp("ne", _as_scalar(other))

    def __gt__(self, other: Scalar) -> Predicate[V]:
        return self._cmp("gt", other)

    def __ge__(self, other: Scalar) -> Predicate[V]:
        return self._cmp("ge", other)

    def __lt__(self, other: Scalar) -> Predicate[V]:
        return self._cmp("lt", other)

    def __le__(self, other: Scalar) -> Predicate[V]:
        return self._cmp("le", other)

    def is_(self, value: bool) -> Predicate[V]:
        return self._cmp("eq", value)

    def in_(self, values: list[Scalar]) -> Predicate[V]:
        return Predicate(NestedMembership(op="nestedIn", path=self._dotted(), values=tuple(values)))

    def not_in(self, values: list[Scalar]) -> Predicate[V]:
        return Predicate(
            NestedMembership(op="nestedNotIn", path=self._dotted(), values=tuple(values))
        )

    def between(self, lower: Scalar, upper: Scalar) -> Predicate[V]:
        return Predicate(NestedRange(path=self._dotted(), lower=lower, upper=upper))

    def _string(self, op: StringOp, value: str, case_insensitive: bool) -> Predicate[V]:
        return Predicate(
            NestedStringMatch(
                op=_NESTED_STRINGS[op],
                path=self._dotted(),
                value=value,
                case_insensitive=True if case_insensitive else None,
            )
        )

    def like(self, value: str, *, case_insensitive: bool = False) -> Predicate[V]:
        return self._string("like", value, case_insensitive)

    def not_like(self, value: str, *, case_insensitive: bool = False) -> Predicate[V]:
        return self._string("notLike", value, case_insensitive)

    def starts_with(self, value: str, *, case_insensitive: bool = False) -> Predicate[V]:
        return self._string("startsWith", value, case_insensitive)

    def ends_with(self, value: str, *, case_insensitive: bool = False) -> Predicate[V]:
        return self._string("endsWith", value, case_insensitive)

    def contains(self, value: str, *, case_insensitive: bool = False) -> Predicate[V]:
        return self._string("contains", value, case_insensitive)

    def is_null(self) -> Predicate[V]:
        return Predicate(NestedNullCheck(op="nestedIsNull", path=self._dotted()))

    def is_not_null(self) -> Predicate[V]:
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


@dataclass(frozen=True, slots=True)
class RelationshipPath[E, R]:
    """A chained class-level relationship reference (``Order.items``,
    ``Order.items.statuses``) — the seed of the ``.include(...)`` deep-fetch
    spelling, the hop-level ``.narrow(*subtypes)`` narrowed-view request, and
    the single-hop relationship quantifiers ``.any()``/``.none()``.

    ``E`` is the Entity the seeding class access went through — where the path
    starts — and ``R`` the Entity it currently points at. Both are covariant. A
    path rooted at a descendant stands wherever one rooted at its ancestor is
    wanted, because a narrower source is a legal include source of a broader
    queried position and authors the path-root guard that says so; a path
    narrowed to a descendant target stands wherever the broad hop does, because
    everything it reaches is also reached by the broad one.

    ``R`` is ``Any`` past the first hop, where the target erases (see
    :meth:`__getattr__`), so a deeper hop's interior predicates and narrows are
    measured only at execution preflight.

    ``segments`` is the traversal so far in ``m-deep-fetch``'s own
    ``PathSegment`` shape, whose relationship references name their owner locally
    as the wire does; ``target`` is the canonical Entity spelling the path
    currently points at, namespace included, so two namespaces sharing a local
    Entity name stay distinguishable.

    ``target`` is absent once the path has continued past the hop its descriptor
    seeded: what a continued hop points at is a declaration fact of an Entity
    this module reaches no class for, and authoring reaches no model to resolve
    it in. A path with no target cannot continue, and the model states the whole
    rule for the hop it did take at execution preflight.

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
    target: str | None
    source: str | None = None

    if TYPE_CHECKING:

        def _starts_from(self) -> E:
            """Never defined at run time and never called.

            ``E`` appears in no field, so without an output position a checker
            infers it as bivariant and a sibling Entity's path would satisfy an
            include-source parameter. This is the output position, and it is the
            whole mechanism (see :class:`Predicate` for the contravariant twin).
            """
            ...

        def _reaches(self) -> R:
            """Never defined at run time and never called: the output position
            that makes ``R`` covariant (see :meth:`_starts_from`)."""
            ...

    @property
    def ref(self) -> RelationshipRef:
        """The first hop's relationship reference (mirrors ``AttributeExpr.ref``)."""
        owner, _, relationship = self.segments[0].rel.rpartition(".")
        return RelationshipRef(owner, relationship)

    def __getattr__(self, name: str) -> RelationshipPath[E, Any]:
        """The next hop, spelled from this path's target and the member's name.

        Authoring reaches no model, so the segment is composed rather than
        resolved: the target's own local Entity name, and the canonical member
        name the Python spelling denotes. Whether that names a declared
        relationship — and what it points at — is settled at execution preflight,
        which resolves every segment against the connected model.

        Three authoring facts erase here in consequence, and each is refused at
        preflight rather than accepted wrongly: a member whose declaration
        renames it, one an ancestor declares rather than the target itself, and
        what the hop points at — which caps an authored chain at two hops,
        because a third would have no owner to spell its segment from. ``R``
        cannot supply it: a type parameter is checker-only, and this is where the
        segment string is built. Spell a longer traversal through
        ``.include(...)`` on a path rooted at the Entity the deeper hop starts
        from.

        Only the hop's segment continues this path: a deeper hop is a member
        lookup on the current target and qualifies nothing about where the path
        is rooted.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        if self.target is None:
            raise AttributeError(
                f"{self.segments[-1].rel}.{name}: this path already continued past the hop "
                "its descriptor seeded, and query authoring reaches no model to resolve "
                "what that hop points at"
            )
        _, _, local = self.target.rpartition(".")
        return RelationshipPath(
            segments=(*self.segments, PathSegment(rel=f"{local}.{snake_to_camel(name)}")),
            target=None,
            source=self.source,
        )

    def narrow[N](self: RelationshipPath[Any, N], *subtypes: type[N]) -> RelationshipPath[E, N]:
        """A hop-level narrowed-view request (``Owner.pets.narrow(Dog)``),
        continuable to a deeper hop. Requests the derived narrowed view
        (spec §3), never marking the broad relationship loaded.

        Each named class must be a subtype of what the hop points at, which is
        the static half of ``narrow-outside-relationship-target``: a hop narrows
        to subtypes of its own target, never to another position. That bound is
        carried by the specialized ``self`` rather than by a type-parameter
        bound, because a bound may not itself be generic; solving one parameter
        from the receiver states the same rule. That the specialized ``self``
        spells the source as ``Any`` is deliberate: naming it ``E`` there would
        put the source in an input position and collapse it from covariant to
        invariant, and the source's covariance is what the include-source rule is
        stated with. Which concrete subtypes the named classes resolve to remains
        a per-model fact, settled at preflight, and the answered path keeps the
        hop's declared target — a hop narrow does not move where a quantifier's
        interior predicates are measured, since a quantifier reads the hop alone.
        """
        narrowed = tuple(_subtype_names(subtype) for subtype in subtypes)
        *head, last = self.segments
        new_last = PathSegment(rel=last.rel, narrow=tuple(local for local, _ in narrowed))
        new_target = self.target
        if len(narrowed) == 1:  # a hop narrowed to one subtype points at that subtype
            _, new_target = narrowed[0]
        return RelationshipPath(segments=(*head, new_last), target=new_target, source=self.source)

    def any(self, *predicates: Predicate[R]) -> Predicate[Any]:
        """The single-hop relationship quantifier: ``>= 1`` related row
        (optionally matching ``predicates``), serializing to ``exists``.

        The interior predicates address what the hop points at — the position the
        validator threads into this node — so they carry the hop's target rather
        than the path's source.

        The quantifier itself answers an unaddressed predicate rather than one at
        the path's source: a Predicate is contravariant, so answering
        ``Predicate[E]`` would put the source in an input position and collapse
        it from covariant to invariant, and the source's covariance is what the
        include-source rule is stated with. A quantifier naming another position's
        relationship keeps its preflight rejection.
        """
        return Predicate(Exists(rel=self._single_hop_ref(), op=conjoin(predicates)))

    def none(self, *predicates: Predicate[R]) -> Predicate[Any]:
        """The complement of :meth:`any` — ``notExists``."""
        return Predicate(NotExists(rel=self._single_hop_ref(), op=conjoin(predicates)))

    def _single_hop_ref(self) -> str:
        if len(self.segments) != 1:
            raise ValueError(
                ".any()/.none() quantify a single relationship hop, not a multi-hop "
                "include path (m-navigate)"
            )
        return self.segments[0].rel
