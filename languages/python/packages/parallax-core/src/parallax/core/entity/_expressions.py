"""Immutable query and write values built from class-level member access.

Class-level attribute access yields an :class:`AttributeExpr` (the SQLAlchemy
``Mapped[T]`` pattern): the seed of a Predicate, strict-Pyright-clean
without a plugin. Its comparison / string / membership / null operators build
frozen ``m-predicate`` nodes wrapped in a :class:`Predicate`, which composes with
``&`` / ``|`` / ``~`` and native parentheses into the canonical boolean tree —
inserting a ``group`` node exactly where an ``or`` binds looser than its enclosing
``and`` so an idiomatic predicate can never drift from canonical grouping.
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
predicate, because the expression is built from the declaring class either way —
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

from parallax.core.base import ManagedValue, String, coerce_neutral_input, matches_neutral_type
from parallax.core.entity._errors import EDIT_CODE_BY_RULE, EditError, EditViolation
from parallax.core.metamodel import (
    AttributeLocation,
    AttributeMetadata,
    EntityIdentity,
    EntityLocation,
    ModelLocation,
    NestedValueObjectMetadata,
    ValueObjectAttributeDeclaration,
    ValueObjectAttributeIdentity,
    ValueObjectAttributeLocation,
    ValueObjectAttributeMetadata,
    ValueObjectIdentity,
    ValueObjectLocation,
    ValueObjectMetadata,
    ValueObjectShapeDeclaration,
    WriteAssignmentError,
    judge_assignment,
)
from parallax.core.object_query import IncludeSegment, OrderKey, subtype_spelling
from parallax.core.predicate import (
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
    Or,
    PredicateNode,
    QueryDefinitionError,
    Scalar,
    StringMatch,
    StringOp,
    canonical_subtype_selection,
)
from parallax.core.wire import WireEncodingError, encode_wire

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
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
    "judged_edit_violation",
    "member_canonical_name",
    "member_location",
    "serialize_member",
    "snake_to_camel",
]


def snake_to_camel(name: str) -> str:
    """The canonical member name a snake_case Python spelling denotes.

    A predicate or query reference names members canonically, so this is the rule that
    turns an authored member spelling into the one the wire carries. It lives
    beside the references it builds because a relationship hop past the first
    reaches no declaration and has only the spelling to go on.
    """
    head, *tail = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


@runtime_checkable
class _Documentable(Protocol):
    """A value that renders itself as a managed nested document.

    Value Objects satisfy this. Naming the capability structurally rather than
    importing the frontend keeps this module free of an edge back into the
    declaration cluster.
    """

    def __parallax_document__(self) -> dict[str, object]: ...


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
        """This key with NULLs placed first. Single-shot (m-object-query)."""
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

    node: PredicateNode

    if TYPE_CHECKING:

        def _addresses(self, entity: E) -> None:
            """Never defined at run time and never called: the input position
            that makes ``E`` contravariant (see :class:`Predicate`)."""

    def __bool__(self) -> bool:
        raise TypeError(_BOOL_HINT)


@dataclass(frozen=True, slots=True)
class Predicate[E]:
    """A built Predicate over the Entity position ``E``; composes with
    ``&`` / ``|`` / ``~``.

    Contravariant in ``E``: a predicate rooted at an ancestor addresses any
    descendant position, and one rooted at a descendant addresses none of its
    ancestors' positions.
    """

    node: PredicateNode

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
        return Predicate(Not(operand=self.node))

    def __bool__(self) -> bool:
        raise TypeError(_BOOL_HINT)


def and_terms(pred: Predicate[Any] | AllPredicate[Any]) -> tuple[PredicateNode, ...]:
    if isinstance(pred.node, And):
        return pred.node.operands  # flatten same-combinator nesting (order-preserving)
    if isinstance(pred.node, Or):
        return (Group(operand=pred.node),)  # an `or` under an `and` binds looser -> group
    return (pred.node,)


def _or_terms(pred: Predicate[Any]) -> tuple[PredicateNode, ...]:
    if isinstance(pred.node, Or):
        return pred.node.operands  # flatten; an `and` under an `or` needs no group
    return (pred.node,)


def conjoin(predicates: Sequence[Predicate[Any] | AllPredicate[Any]]) -> PredicateNode | None:
    """The big-AND of ``predicates`` (flattened, order-preserving), or ``None``
    for zero arguments — the shared builder behind every variadic predicate
    scope, so a bare presence test, a single predicate, and a conjunction can
    never drift from the whole-query combination ``Entity.where`` builds. It
    accepts whatever :func:`and_terms` does, which is what lets the unfiltered
    ``Entity.all`` reach it as a sole argument."""
    if not predicates:
        return None
    if len(predicates) == 1:
        return predicates[0].node
    operands: list[PredicateNode] = []
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

    def _cmp(self, kind: str, value: object) -> Predicate[E]:
        literal = self._literal(value)
        if self._path:
            return Predicate(
                NestedComparison(op=_NESTED_CMP[kind], path=self._dotted(), value=literal)
            )
        return Predicate(Comparison(op=_SCALAR_CMP[kind], attr=str(self.ref), value=literal))

    def __eq__(self, other: object) -> Predicate[E]:  # type: ignore[override] - DSL comparison builds a Predicate, not object's bool
        return self._cmp("eq", other)

    def __ne__(self, other: object) -> Predicate[E]:  # type: ignore[override] - DSL comparison builds a Predicate, not object's bool
        return self._cmp("ne", other)

    def __gt__(self, other: object) -> Predicate[E]:
        return self._cmp("gt", other)

    def __ge__(self, other: object) -> Predicate[E]:
        return self._cmp("ge", other)

    def __lt__(self, other: object) -> Predicate[E]:
        return self._cmp("lt", other)

    def __le__(self, other: object) -> Predicate[E]:
        return self._cmp("le", other)

    def is_(self, value: bool) -> Predicate[E]:
        """The lint-clean boolean spelling; serializes to the identical ``eq`` node."""
        return self._cmp("eq", value)

    def in_(self, values: list[object]) -> Predicate[E]:
        return self._membership("nestedIn", "in", values)

    def not_in(self, values: list[object]) -> Predicate[E]:
        return self._membership("nestedNotIn", "notIn", values)

    def _membership(
        self, nested_op: NestedMembershipOp, scalar_op: MembershipOp, values: list[object]
    ) -> Predicate[E]:
        literals = tuple(self._literal(value) for value in values)
        if self._path:
            return Predicate(NestedMembership(op=nested_op, path=self._dotted(), values=literals))
        return Predicate(Membership(op=scalar_op, attr=str(self.ref), values=literals))

    def between(self, lower: object, upper: object) -> Predicate[E]:
        lower_literal = self._literal(lower)
        upper_literal = self._literal(upper)
        if self._path:
            return Predicate(
                NestedRange(path=self._dotted(), lower=lower_literal, upper=upper_literal)
            )
        return Predicate(Between(attr=str(self.ref), lower=lower_literal, upper=upper_literal))

    def _literal(self, value: object) -> Scalar:
        if value is None:
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=f"{self._dotted()}: use .is_null() or .is_not_null() for None",
            )
        member = self._require_scalar_member()
        managed = coerce_neutral_input(value, member.type)
        if not matches_neutral_type(managed, member.type):
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=f"{self._dotted()}: {value!r} is not admitted by {member.type!r}",
            )
        try:
            return cast("Scalar", encode_wire(member.type, cast("ManagedValue", managed)))
        except WireEncodingError as error:  # pragma: no cover - membership above proves encoding
            raise QueryDefinitionError(
                code="query-expression-invalid", message=f"{self._dotted()}: {error}"
            ) from error

    def _require_scalar_member(self) -> AttributeMetadata | ValueObjectAttributeMetadata:
        member = self._resolved_scalar_member()
        if member is None:
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=f"{self._dotted()}: literal operations require resolved scalar metadata",
            )
        return member

    def _resolved_scalar_member(self) -> AttributeMetadata | ValueObjectAttributeMetadata | None:
        if isinstance(self._member, AttributeMetadata):
            return self._member if not self._path else None
        if self._member is None or isinstance(self._member, AttributeMetadata) or not self._path:
            return None
        container: ValueObjectMetadata | NestedValueObjectMetadata = self._member
        for segment in self._path[:-1]:
            nested = container.value_object(snake_to_camel(segment))
            if nested is None:
                return None
            container = nested
        return container.attribute(snake_to_camel(self._path[-1]))

    def is_null(self) -> Predicate[E]:
        self._reject_non_nullable_null_check()
        if self._path:
            return Predicate(NestedNullCheck(op="nestedIsNull", path=self._dotted()))
        return Predicate(NullCheck(op="isNull", attr=str(self.ref)))

    def is_not_null(self) -> Predicate[E]:
        self._reject_non_nullable_null_check()
        if self._path:
            return Predicate(NestedNullCheck(op="nestedIsNotNull", path=self._dotted()))
        return Predicate(NullCheck(op="isNotNull", attr=str(self.ref)))

    def _reject_non_nullable_null_check(self) -> None:
        member = self._require_scalar_member()
        if member.nullable:
            return
        raise QueryDefinitionError(
            code="query-expression-invalid",
            message=(
                f"{self._dotted()}: is_null()/is_not_null() is invalid for a "
                "non-nullable member (m-predicate null-check validity)"
            ),
        )

    def exists(self, *predicates: Predicate[Any]) -> Predicate[E]:
        """The value-object member is present/non-empty (optionally matching
        ``predicates``, same-element composed): ``nestedExists`` over this
        value-object-terminated path. Zero arguments emit the bare presence
        test; the interior predicates are built from the value object's own
        element-scoped attributes, never re-prefixed."""
        return Predicate(NestedExists(path=self._dotted(), where=conjoin(predicates)))

    def not_exists(self, *predicates: Predicate[Any]) -> Predicate[E]:
        """The complement of :meth:`exists` — ``nestedNotExists``."""
        return Predicate(NestedNotExists(path=self._dotted(), where=conjoin(predicates)))

    def _string(self, op: StringOp, value: str, case_insensitive: bool) -> Predicate[E]:
        # The fluent surface authors the canonical minimal form: an unset flag
        # omits `caseInsensitive` (None), a set flag emits `true`. It never
        # authors an explicit `false` — that only arises from deserializing a
        # document that spelled it out (round-trip fidelity lives in the serde).
        member = self._require_scalar_member()
        if not isinstance(member.type, String):
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=f"{self._dotted()}: string operations require a String leaf",
            )
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
            raise EditError([self._nested_path_violation()]) from None
        serialized = serialize_member(value)
        self._reject_unassignable(serialized)
        return AttributeAssignment(attr=self.ref, value=serialized)

    def _nested_path_violation(self) -> EditViolation:
        """The refusal of an assignment below a Value Object boundary.

        The location is the scalar the path names inside the occurrence the head
        member declares, which is the one member position this surface can reach
        that no other authoring surface can: a keyword edit cannot spell a path.
        An expression built directly carries no member, so the Entity it names is
        only the bare string it was constructed with, and the violation locates
        at that ownerless Entity.
        """
        member = self._member
        location: ModelLocation
        if isinstance(member, AttributeMetadata):
            location = AttributeLocation(member.identity)
        elif member is not None:
            location = ValueObjectAttributeLocation(
                ValueObjectAttributeIdentity(
                    ValueObjectIdentity(
                        member.identity.entity, (*member.identity.path, *self._path[:-1])
                    ),
                    self._path[-1],
                )
            )
        else:
            location = EntityLocation(EntityIdentity(None, self._entity))
        return EditViolation(
            code="edit-nested-path",
            location=location,
            member_name=".".join((self._head, *self._path)),
            message=(
                f"{self._dotted()}: only a top-level attribute or value-object member is "
                "assignable via .set(...) — a value object binds its whole document, never "
                "a nested path (m-value-object)"
            ),
        )

    def _reject_unassignable(self, value: object) -> None:
        """Apply the shared assignment rule family to a rendered value (spec §5).

        The rules are one set, stated once in
        :func:`~parallax.core.metamodel.judge_assignment` and called from every
        surface that assigns: here, ``Entity.edit(...)`` (spec §3), and the
        serialized write boundary. A primary-key, read-only, or framework-owned
        target is refused, a scalar value must match its declared neutral type,
        and a Value Object value must be a well-formed document — with ``None``
        legal only where the member is nullable. Only the resolution in front of
        the judgement differs between the three, so none of them can drift. The
        rejection is spelled :class:`EditError` because it is that same family;
        one call names one target, so it carries exactly one violation and there
        is nothing to aggregate.

        The member the descriptor installed is the whole input, so this states
        its rule with no model: which member a name resolves to was decided by
        Python's own attribute lookup, and ``inheritance-member-shadowing``
        guarantees that resolution is unambiguous within any accepted model. An
        expression built directly carries no member and states no rule, leaving
        it to the write boundary.
        """
        if self._member is None:
            return
        violation = judged_edit_violation(
            self._member, value, owner=self._entity, location=member_location(self._member)
        )
        if violation is not None:
            raise EditError([violation]) from None

    def __bool__(self) -> bool:
        raise TypeError(_BOOL_HINT)

    def __hash__(self) -> int:  # pragma: no cover - expressions are not dict keys
        return hash((self._entity, self._head, self._path))


def member_location(member: AttributeMetadata | ValueObjectMetadata) -> ModelLocation:
    """Where a resolved member's own refusal is located.

    The member's accepted Metadata already carries the identity, so every
    authoring surface locates one resolved member identically without holding a
    model — which is what lets ``.set(...)`` and ``edit(...)`` report the same
    violation for the same mistake.
    """
    if isinstance(member, AttributeMetadata):
        return AttributeLocation(member.identity)
    return ValueObjectLocation(member.identity)


def member_canonical_name(member: AttributeMetadata | ValueObjectMetadata) -> str:
    """A resolved member's canonical name, whichever kind of member it is."""
    if isinstance(member, AttributeMetadata):
        return member.identity.name
    return member.identity.path[-1]


def judged_edit_violation(
    member: AttributeMetadata | ValueObjectMetadata,
    value: object,
    *,
    owner: str,
    location: ModelLocation,
) -> EditViolation | None:
    """The shared judgement's verdict on ``value``, as a located violation.

    Every authoring surface translates the verdict here rather than re-deciding
    it or re-wording it: the judgement owns the rule and its message, this owns
    only the edit code the rule reports as and the owner prefix that says where
    the member was addressed. ``None`` means the assignment is accepted.

    ``location`` is the caller's, because where a refusal lands is a fact about
    the surface rather than about the verdict: a member of a model's Entity
    locates at :func:`member_location`, while a Value Object Class's own member
    belongs to no model position at all.
    """
    try:
        judge_assignment(member, value)
    except WriteAssignmentError as error:
        return EditViolation(
            code=EDIT_CODE_BY_RULE[error.rule],
            location=location,
            member_name=member_canonical_name(member),
            message=f"{owner}.{error}",
        )
    return None


def serialize_member(value: object) -> object:
    """Render Value Objects as managed typed-write documents."""
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
    """A Value Object element-scoped attribute expression with resolved leaf facts."""

    __slots__ = ("_path", "_shape")

    def __init__(
        self,
        path: tuple[str, ...],
        shape: ValueObjectShapeDeclaration | None = None,
    ) -> None:
        self._path = path
        self._shape = shape

    def __getattr__(self, name: str) -> ElementAttributeExpr[V, Any]:
        if name.startswith("_"):
            raise AttributeError(name)
        return ElementAttributeExpr((*self._path, name), self._shape)

    def _dotted(self) -> str:
        return ".".join(self._path)

    def _leaf(self) -> ValueObjectAttributeDeclaration:
        container = self._shape
        if container is None:
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=f"{self._dotted()}: literal operations require resolved scalar metadata",
            )
        for segment in self._path[:-1]:
            canonical = snake_to_camel(segment)
            occurrence = next(
                (item for item in container.value_objects if item.name == canonical),
                None,
            )
            if occurrence is None:
                raise QueryDefinitionError(
                    code="query-expression-invalid",
                    message=f"{self._dotted()}: {canonical!r} is not a nested Value Object",
                )
            container = occurrence.shape
        name = snake_to_camel(self._path[-1])
        leaf = next((item for item in container.attributes if item.name == name), None)
        if leaf is None:
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=f"{self._dotted()}: {name!r} is not a scalar leaf",
            )
        return leaf

    def _literal(self, value: object) -> Scalar:
        if value is None:
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=f"{self._dotted()}: use .is_null() or .is_not_null() for None",
            )
        leaf = self._leaf()
        managed = coerce_neutral_input(value, leaf.type)
        if not matches_neutral_type(managed, leaf.type):
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=f"{self._dotted()}: {value!r} is not admitted by {leaf.type!r}",
            )
        try:
            return cast("Scalar", encode_wire(leaf.type, cast("ManagedValue", managed)))
        except WireEncodingError as error:
            raise QueryDefinitionError(
                code="query-expression-invalid", message=f"{self._dotted()}: {error}"
            ) from error

    def _cmp(self, kind: str, value: object) -> Predicate[V]:
        return Predicate(
            NestedComparison(op=_NESTED_CMP[kind], path=self._dotted(), value=self._literal(value))
        )

    def __eq__(self, other: object) -> Predicate[V]:  # type: ignore[override]
        return self._cmp("eq", other)

    def __ne__(self, other: object) -> Predicate[V]:  # type: ignore[override]
        return self._cmp("ne", other)

    def __gt__(self, other: object) -> Predicate[V]:
        return self._cmp("gt", other)

    def __ge__(self, other: object) -> Predicate[V]:
        return self._cmp("ge", other)

    def __lt__(self, other: object) -> Predicate[V]:
        return self._cmp("lt", other)

    def __le__(self, other: object) -> Predicate[V]:
        return self._cmp("le", other)

    def is_(self, value: bool) -> Predicate[V]:
        return self._cmp("eq", value)

    def in_(self, values: list[object]) -> Predicate[V]:
        return Predicate(
            NestedMembership(
                op="nestedIn",
                path=self._dotted(),
                values=tuple(self._literal(value) for value in values),
            )
        )

    def not_in(self, values: list[object]) -> Predicate[V]:
        return Predicate(
            NestedMembership(
                op="nestedNotIn",
                path=self._dotted(),
                values=tuple(self._literal(value) for value in values),
            )
        )

    def between(self, lower: object, upper: object) -> Predicate[V]:
        return Predicate(
            NestedRange(
                path=self._dotted(),
                lower=self._literal(lower),
                upper=self._literal(upper),
            )
        )

    def _string(self, op: StringOp, value: str, case_insensitive: bool) -> Predicate[V]:
        if not isinstance(self._leaf().type, String):
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=f"{self._dotted()}: string operations require a String leaf",
            )
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
        self._reject_non_nullable_null_check()
        return Predicate(NestedNullCheck(op="nestedIsNull", path=self._dotted()))

    def is_not_null(self) -> Predicate[V]:
        self._reject_non_nullable_null_check()
        return Predicate(NestedNullCheck(op="nestedIsNotNull", path=self._dotted()))

    def _reject_non_nullable_null_check(self) -> None:
        if self._leaf().nullable:
            return
        raise QueryDefinitionError(
            code="query-expression-invalid",
            message=f"{self._dotted()}: null checks require a nullable scalar leaf",
        )

    def __bool__(self) -> bool:
        raise TypeError(_BOOL_HINT)

    def __hash__(self) -> int:
        return hash((self._path, self._shape))


@dataclass(frozen=True, slots=True)
class RelationshipPath[E, R]:
    """A chained class-level relationship reference (``Order.items``,
    ``Order.items.statuses``) — the seed of the ``.include(...)`` deep-fetch
    spelling, the hop-level ``.narrow(*subtypes)`` narrowed-view request, and
    the single-hop relationship quantifiers ``.exists()``/``.not_exists()``.

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
    ``IncludeSegment`` shape, whose relationship references name their owner locally
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
    what an Object Query turns into the path-ROOT guard — qualifying which queried
    objects the whole path starts from — so, unlike a hop's own narrow, it lives
    beside ``segments`` rather than inside one, and a deeper hop neither adds nor
    replaces it: a deeper hop is a member lookup on the current target and says
    nothing about where the path is rooted.
    """

    segments: tuple[IncludeSegment, ...]
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
        resolved: the target's own canonical Entity spelling, and the canonical
        member name the Python spelling denotes. Whether that names a declared
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
                f"what that hop points at — root the deeper traversal at the Entity {name!r} "
                "is declared on and add it as its own `.include(...)` path"
            )
        return RelationshipPath(
            segments=(*self.segments, IncludeSegment(rel=f"{self.target}.{snake_to_camel(name)}")),
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

        Narrowing is single-shot per segment: a segment carries one alternative
        list, so a second narrow on the same hop could only intersect or replace
        the first, and both silently answer something other than what either call
        asked for. Continuing to another relationship starts a fresh segment,
        which narrows its own target independently.

        At least one subtype is required, like every other narrowing form. A
        segment records "no narrow" as an empty alternative list, so accepting a
        narrow to nothing would answer the broad path itself — the request would
        vanish rather than be refused, and the deep fetch would mark the broad
        relationship loaded. The sibling forms are refused at preflight
        (``narrow-empty-effective-set``); this one has no such refusal to fall
        back on, because it lowers to no node of its own.
        """
        *head, last = self.segments
        if last.narrow_to:
            raise QueryDefinitionError(
                code="query-path-invalid",
                message=(
                    f"{last.rel}: narrowing is single-shot per path segment and this hop is "
                    f"already narrowed to {', '.join(last.narrow_to)}; derive the segment from "
                    "the un-narrowed hop"
                ),
            )
        if not subtypes:
            raise QueryDefinitionError(
                code="query-path-invalid",
                message=f"{last.rel}: narrow requires at least one subtype",
            )
        narrowed = tuple(subtype_spelling(subtype) for subtype in subtypes)
        if len(set(narrowed)) != len(narrowed):
            raise QueryDefinitionError(
                code="query-path-invalid",
                message=f"{last.rel}: narrow alternatives must not repeat the same subtype",
            )
        narrowed = canonical_subtype_selection(narrowed)
        new_last = IncludeSegment(rel=last.rel, narrow_to=narrowed)
        new_target = self.target
        if len(narrowed) == 1:  # a hop narrowed to one subtype points at that subtype
            new_target = narrowed[0]
        return RelationshipPath(segments=(*head, new_last), target=new_target, source=self.source)

    def exists(self, *predicates: Predicate[R]) -> Predicate[Any]:
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

    def not_exists(self, *predicates: Predicate[R]) -> Predicate[Any]:
        """The complement of :meth:`exists` — ``notExists``."""
        return Predicate(NotExists(rel=self._single_hop_ref(), op=conjoin(predicates)))

    def _single_hop_ref(self) -> str:
        if len(self.segments) != 1:
            raise QueryDefinitionError(
                code="query-path-invalid",
                message=(
                    ".exists()/.not_exists() quantify a single relationship hop, not a multi-hop "
                    "include path (m-navigate)"
                ),
            )
        return self.segments[0].rel
