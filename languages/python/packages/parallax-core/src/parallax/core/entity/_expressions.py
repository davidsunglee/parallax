from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal, NoReturn, cast

from parallax.core.base import (
    InvalidValueError,
    ManagedValue,
    NeutralType,
    String,
    UsageError,
    canonical_managed_member,
    coerce_neutral_input,
    matches_neutral_type,
)
from parallax.core.entity._errors import EDIT_CODE_BY_RULE, EditError, EditViolation
from parallax.core.metamodel import (
    AttributeLocation,
    AttributeMetadata,
    AuthoringViolation,
    EntityIdentity,
    MemberDefinition,
    ModelLocation,
    Multiplicity,
    RelationshipIdentity,
    ValueObjectAttributeDeclaration,
    ValueObjectLocation,
    ValueObjectMetadata,
    ValueObjectShapeDeclaration,
    judge_assignment,
)
from parallax.core.object_query import (
    OrderKey,
    subtype_spelling,
)
from parallax.core.predicate import (
    QUERY_EXPRESSION_INVALID,
    QUERY_PATH_INVALID,
    StringOp,
    SubtypeSelection,
    canonical_subtype_selection,
)
from parallax.core.predicate._interpretation import (
    BETWEEN,
    COMPARE,
    MEMBER_OF,
    NULL_TEST,
    Match,
    ScalarOperator,
)
from parallax.core.predicate._nodes import QuantifierKind

if TYPE_CHECKING:
    from collections.abc import Sequence

    from parallax.core.entity._declaration import ValueObjectShape, WireNames
    from parallax.core.object_query._nodes import (
        TemporalDimension,
        TemporalSelection,
    )

__all__ = [
    "EXPRESSION_OPERATION_NAMES",
    "AllPredicate",
    "AssignableManyScalarExpr",
    "AssignableManyValueObjectExpr",
    "AssignableScalarExpr",
    "AssignableValueObjectExpr",
    "AttributeAssignment",
    "AttributeRef",
    "AuthoredAnd",
    "AuthoredConstant",
    "AuthoredElement",
    "AuthoredGroup",
    "AuthoredIncludePath",
    "AuthoredIncludeSegment",
    "AuthoredMemberPath",
    "AuthoredNarrow",
    "AuthoredNot",
    "AuthoredOr",
    "AuthoredPredicate",
    "AuthoredPresence",
    "AuthoredQuantifier",
    "AuthoredQuery",
    "IncludePath",
    "ManyRelationshipExpr",
    "ManyScalarExpr",
    "ManyValueObjectExpr",
    "MemberValidator",
    "Predicate",
    "PreparedOperation",
    "RelationshipExpr",
    "RelationshipRef",
    "ScalarElementExpr",
    "ScalarExpr",
    "SortKey",
    "UnfinishedExpr",
    "UnfinishedOperation",
    "ValueObjectExpr",
    "ValueObjectReceiver",
    "authored_include_path",
    "conjoin",
    "judged_edit_violation",
    "managed_literal",
    "member_expression",
    "member_location",
    "require_bound_elements",
    "root_segment",
    "snake_to_camel",
    "subtype_selection",
]


def _invalid_operand(
    kind: type[UsageError],
    path: str,
    neutral_type: NeutralType | None,
    value: object,
    rule: str,
) -> UsageError:
    declared = "<unresolved>" if neutral_type is None else repr(neutral_type)
    return kind(
        QUERY_EXPRESSION_INVALID,
        f"{path}: declared NeutralType {declared}; supplied Python carrier "
        f"{type(value).__name__}; developer-input rule violated: {rule}",
    )


def managed_literal(path: str, neutral_type: NeutralType, value: object) -> ManagedValue:
    """``value`` admitted as one managed ``neutral_type`` operand under the Typed
    developer-input policy, in the canonical form a Wire literal of it decodes
    to, or a refusal naming ``path``."""
    if value is None:
        raise _invalid_operand(
            UsageError,
            path,
            neutral_type,
            value,
            "None is not a typed literal; use .is_null() or .is_not_null()",
        )
    managed = coerce_neutral_input(value, neutral_type)
    if not matches_neutral_type(managed, neutral_type):
        raise _invalid_operand(
            InvalidValueError,
            path,
            neutral_type,
            value,
            "the developer input policy does not admit this carrier for the declared type",
        )
    return cast("ManagedValue", canonical_managed_member(managed, neutral_type))


def snake_to_camel(name: str) -> str:
    """The canonical member name a snake_case Python spelling denotes by
    convention, absent an explicit ``name=``.

    A declaration applies it once and records the correspondence; authored
    paths resolve Python names through those records.
    """
    head, *tail = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


_BOOL_HINT = (
    "a Parallax expression has no truth value; combine predicates with & / | / ~ and "
    "parentheses (not and/or/not), and use .between()/.in_() instead of chained comparisons"
)


# The authored tree


@dataclass(frozen=True, slots=True)
class ValueObjectReceiver:
    """The Value Object Class a class-scoped element path was read through."""

    shape: ValueObjectShapeDeclaration


type Receiver = EntityIdentity | ValueObjectReceiver


@dataclass(frozen=True, slots=True)
class AuthoredMemberPath:
    """A member path read from ``receiver``: canonical member names where the
    declaration supplied them, or, when ``unfinished``, the Python member names
    a serving model's classes resolve.

    An Entity receiver addresses its own position, a Value Object receiver the
    element a quantifier binds; either binds only against the current scope.
    """

    receiver: Receiver
    names: tuple[str, ...]
    unfinished: bool = False

    def child(self, name: str) -> AuthoredMemberPath:
        return AuthoredMemberPath(self.receiver, (*self.names, name), self.unfinished)

    def described(self) -> str:
        receiver = self.receiver
        head = receiver.canonical if isinstance(receiver, EntityIdentity) else "<element>"
        return ".".join((head, *self.names))


@dataclass(frozen=True, slots=True)
class AuthoredElement:
    """The element of the scalar collection ``collection`` names."""

    collection: AuthoredMemberPath


type AuthoredSubject = AuthoredMemberPath | AuthoredElement


@dataclass(frozen=True, slots=True)
class PreparedOperation:
    """A scalar operation over a declaration-backed subject, its operands already
    managed under ``prepared_type``, the type that declaration states.

    A string pattern is kept as authored; every other operand is managed.
    """

    subject: AuthoredSubject
    operator: ScalarOperator
    operands: tuple[object, ...]
    prepared_type: NeutralType


@dataclass(frozen=True, slots=True)
class UnfinishedOperation:
    """A scalar operation whose subject continues by Python member names, its
    native ``operands`` awaiting the type the serving model resolves it to."""

    subject: AuthoredSubject
    operator: ScalarOperator
    operands: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class AuthoredConstant:
    truth: bool


@dataclass(frozen=True, slots=True)
class AuthoredAnd:
    operands: tuple[AuthoredPredicate, ...]


@dataclass(frozen=True, slots=True)
class AuthoredOr:
    operands: tuple[AuthoredPredicate, ...]


@dataclass(frozen=True, slots=True)
class AuthoredNot:
    operand: AuthoredPredicate


@dataclass(frozen=True, slots=True)
class AuthoredGroup:
    operand: AuthoredPredicate


type BoundElement = Literal["entity", "value-object", "scalar"]
"""What a quantifier binds: a related Entity, a Value Object element, or a
scalar collection element."""


@dataclass(frozen=True, slots=True)
class AuthoredQuantifier:
    """Whether some, every, or no element of ``collection`` makes ``where``
    true; ``where`` binds the element, and a bare form tests occupancy.
    ``binds`` is absent while a serving model has yet to resolve what the
    collection holds."""

    kind: QuantifierKind
    collection: AuthoredMemberPath
    where: AuthoredPredicate | None = None
    binds: BoundElement | None = None


@dataclass(frozen=True, slots=True)
class AuthoredPresence:
    """Whether the single object ``target`` names is present (or absent); with
    ``where``, whether its to-one target makes ``where`` true (or none does)."""

    negated: bool
    target: AuthoredMemberPath
    where: AuthoredPredicate | None = None


@dataclass(frozen=True, slots=True)
class AuthoredNarrow:
    """Whether the current Entity — read through ``receiver`` — or the to-one
    ``target`` belongs to the Subtype Selection ``to``, and makes ``operand``
    true there when one is given."""

    to: SubtypeSelection
    operand: AuthoredPredicate | None = None
    receiver: EntityIdentity | None = None
    target: AuthoredMemberPath | None = None


type AuthoredPredicate = (
    PreparedOperation
    | UnfinishedOperation
    | AuthoredConstant
    | AuthoredAnd
    | AuthoredOr
    | AuthoredNot
    | AuthoredGroup
    | AuthoredQuantifier
    | AuthoredPresence
    | AuthoredNarrow
)

_UNFILTERED: AuthoredPredicate = AuthoredConstant(truth=True)
_NO_TEMPORAL: Mapping[TemporalDimension, TemporalSelection] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class AuthoredQuery:
    """The authored state of one Typed Object Query: its target, its authored
    predicate and Include paths, and its other clauses in their canonical
    spellings.

    Model-free and immutable, so one value serves every model that accepts its
    target; nothing resolved is attached back to it.
    """

    target: EntityIdentity
    predicate: AuthoredPredicate
    narrow_to: SubtypeSelection | None = None
    temporal: Mapping[TemporalDimension, TemporalSelection] = _NO_TEMPORAL
    order_by: tuple[OrderKey, ...] = ()
    limit: int | None = None
    includes: tuple[AuthoredIncludePath, ...] = field(default_factory=tuple)

    @property
    def requests_includes(self) -> bool:
        return bool(self.includes)


def _subject_described(element: AuthoredElement) -> str:
    return f"{element.collection.described()}.element"


def _unbound_elements(authored: AuthoredPredicate) -> Iterator[AuthoredElement]:
    """The scalar elements in ``authored`` no quantifier inside it binds."""
    match authored:
        case (
            PreparedOperation(subject=AuthoredElement() as element)
            | UnfinishedOperation(subject=AuthoredElement() as element)
        ):
            yield element
        case AuthoredAnd(operands=operands) | AuthoredOr(operands=operands):
            for operand in operands:
                yield from _unbound_elements(operand)
        case AuthoredNot(operand=operand) | AuthoredGroup(operand=operand):
            yield from _unbound_elements(operand)
        case AuthoredNarrow(operand=operand) if operand is not None:
            yield from _unbound_elements(operand)
        case _:
            # A quantifier's own `where` admits only elements of its collection,
            # and a matching operand none, so nothing inside either is unbound.
            return


def require_bound_elements(authored: AuthoredPredicate, where: str) -> None:
    """Refuse a scalar element ``authored`` reads outside the quantifier over
    its own collection."""
    for element in _unbound_elements(authored):
        raise UsageError(
            QUERY_PATH_INVALID,
            f"{_subject_described(element)}: a collection element is read only inside "
            f"a quantifier over {element.collection.described()}, not {where}",
        )


# References, assignments, sort keys, and composed predicates


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


@dataclass(frozen=True, slots=True)
class AttributeAssignment[E]:
    """One typed ``_where``-verb assignment (``Attr.set(value)``).

    The entity-scoped spelling of a predicate-write assignment, built on the same
    member-expression surface a predicate is built on. This scope stays free of
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
    parameter-free. The Null Placement modifiers stay here — a member expression
    exposes neither — and delegate to the canonical node, so the single-shot
    placement rule has one implementation.

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
    distinguishes ``Dog.all`` from ``Animal.all`` — a constant names no
    position — so this parameter is the only thing that refuses an unfiltered
    query written against a position the query is not at.
    """

    authored: AuthoredPredicate = _UNFILTERED

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

    ``authored`` is the one authored tree the predicate is: no model is reached
    while it is composed, and each operation that consumes it resolves it against
    the model that operation adopted.

    Contravariant in ``E``: a predicate rooted at an ancestor addresses any
    descendant position, and one rooted at a descendant addresses none of its
    ancestors' positions.
    """

    authored: AuthoredPredicate

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
    # is the narrower position.
    def __and__[F](self: Predicate[F], other: Predicate[F], /) -> Predicate[F]:
        return Predicate(AuthoredAnd((*and_terms(self), *and_terms(other))))

    def __or__[F](self: Predicate[F], other: Predicate[F], /) -> Predicate[F]:
        return Predicate(AuthoredOr((*_or_terms(self), *_or_terms(other))))

    def __invert__(self) -> Predicate[E]:
        return Predicate(AuthoredNot(self.authored))

    def __bool__(self) -> bool:
        raise TypeError(_BOOL_HINT)


def and_terms(pred: Predicate[Any] | AllPredicate[Any]) -> tuple[AuthoredPredicate, ...]:
    authored = pred.authored
    if isinstance(authored, AuthoredAnd):
        return authored.operands  # flatten same-combinator nesting (order-preserving)
    if isinstance(authored, AuthoredOr):
        return (AuthoredGroup(authored),)  # an `or` under an `and` binds looser -> group
    return (authored,)


def _or_terms(pred: Predicate[Any]) -> tuple[AuthoredPredicate, ...]:
    authored = pred.authored
    if isinstance(authored, AuthoredOr):
        return authored.operands  # flatten; an `and` under an `or` needs no group
    return (authored,)


def conjoin(predicates: Sequence[Predicate[Any] | AllPredicate[Any]]) -> AuthoredPredicate | None:
    """The big-AND of ``predicates`` (flattened, order-preserving), or ``None``
    for zero arguments — the shared builder behind ``Entity.where``, so a single
    predicate and a conjunction can never drift from the whole-query
    combination."""
    if not predicates:
        return None
    if len(predicates) == 1:
        return predicates[0].authored
    operands: list[AuthoredPredicate] = []
    for predicate in predicates:
        operands.extend(and_terms(predicate))
    return AuthoredAnd(tuple(operands))


def _entity_identity(spelling: str) -> EntityIdentity:
    namespace, separator, name = spelling.rpartition(".")
    return EntityIdentity(namespace if separator else None, name if separator else spelling)


# Scalar authoring shared by every scalar subject


class _ScalarAuthoring[P]:
    """Comparison, Boolean, membership, range, and string authoring shared by
    every scalar subject.

    A subject supplies the type its declaration states, when it knows one, and
    the authored subject an operation names. Operands are prepared once under a
    known type and retained managed; a subject whose type the serving model
    resolves retains its native operands instead.
    """

    __slots__ = ()

    def _described(self) -> str:
        raise NotImplementedError

    def _operand_type(self) -> NeutralType | None:
        raise NotImplementedError

    def _subject(self) -> AuthoredSubject:
        raise NotImplementedError

    def _operation(self, operator: ScalarOperator, values: tuple[object, ...]) -> Predicate[P]:
        neutral_type = self._operand_type()
        if neutral_type is None:
            return Predicate(UnfinishedOperation(self._subject(), operator, values))
        described = self._described()
        operands = tuple(managed_literal(described, neutral_type, value) for value in values)
        return Predicate(PreparedOperation(self._subject(), operator, operands, neutral_type))

    def __eq__(self, other: object) -> Predicate[P]:  # type: ignore[override] - DSL comparison builds a Predicate, not object's bool
        return self._operation(COMPARE["eq"], (other,))

    def __ne__(self, other: object) -> Predicate[P]:  # type: ignore[override] - DSL comparison builds a Predicate, not object's bool
        return self._operation(COMPARE["notEq"], (other,))

    def __gt__(self, other: object) -> Predicate[P]:
        return self._operation(COMPARE["greaterThan"], (other,))

    def __ge__(self, other: object) -> Predicate[P]:
        return self._operation(COMPARE["greaterThanEquals"], (other,))

    def __lt__(self, other: object) -> Predicate[P]:
        return self._operation(COMPARE["lessThan"], (other,))

    def __le__(self, other: object) -> Predicate[P]:
        return self._operation(COMPARE["lessThanEquals"], (other,))

    def is_(self, value: bool) -> Predicate[P]:
        """The lint-clean boolean spelling of equality."""
        return self._operation(COMPARE["eq"], (value,))

    def in_(self, values: list[object]) -> Predicate[P]:
        return self._operation(MEMBER_OF["in"], tuple(values))

    def not_in(self, values: list[object]) -> Predicate[P]:
        return self._operation(MEMBER_OF["notIn"], tuple(values))

    def between(self, lower: object, upper: object) -> Predicate[P]:
        return self._operation(BETWEEN, (lower, upper))

    def _string(self, op: StringOp, value: str, case_insensitive: bool) -> Predicate[P]:
        operator = Match(op, bool(case_insensitive))
        neutral_type = self._operand_type()
        if neutral_type is not None and not isinstance(neutral_type, String):
            raise UsageError(
                QUERY_EXPRESSION_INVALID,
                f"{self._described()}: string operations require a String leaf",
            )
        if cast("object", value) is None:
            raise UsageError(
                QUERY_EXPRESSION_INVALID,
                "None is not a Predicate literal; use .is_null() or .is_not_null()",
            )
        if neutral_type is None:
            return Predicate(UnfinishedOperation(self._subject(), operator, (value,)))
        pattern = managed_literal(self._described(), neutral_type, value)
        return Predicate(PreparedOperation(self._subject(), operator, (pattern,), neutral_type))

    def like(self, value: str, *, case_insensitive: bool = False) -> Predicate[P]:
        return self._string("like", value, case_insensitive)

    def not_like(self, value: str, *, case_insensitive: bool = False) -> Predicate[P]:
        return self._string("notLike", value, case_insensitive)

    def starts_with(self, value: str, *, case_insensitive: bool = False) -> Predicate[P]:
        return self._string("startsWith", value, case_insensitive)

    def ends_with(self, value: str, *, case_insensitive: bool = False) -> Predicate[P]:
        return self._string("endsWith", value, case_insensitive)

    def contains(self, value: str, *, case_insensitive: bool = False) -> Predicate[P]:
        return self._string("contains", value, case_insensitive)

    def _null_test(self, op: Literal["isNull", "isNotNull"]) -> Predicate[P]:
        neutral_type = self._operand_type()
        if neutral_type is None:
            return Predicate(UnfinishedOperation(self._subject(), NULL_TEST[op], ()))
        return Predicate(PreparedOperation(self._subject(), NULL_TEST[op], (), neutral_type))

    def __bool__(self) -> bool:
        raise TypeError(_BOOL_HINT)


type _LeafFacts = AttributeMetadata | ValueObjectAttributeDeclaration


class ScalarExpr[E, T](_ScalarAuthoring[E]):
    """A single scalar field, read from the position ``E`` names.

    ``E`` is the Entity or Value Object Class the access went through and ``T``
    the field's declared Python type. A field reached through a Value Object is
    query-only.
    """

    __slots__ = ("_leaf", "_path")

    def __init__(self, path: AuthoredMemberPath, leaf: _LeafFacts) -> None:
        self._path = path
        self._leaf = leaf

    def _described(self) -> str:
        return self._path.described()

    def _operand_type(self) -> NeutralType:
        return self._leaf.type

    def _subject(self) -> AuthoredSubject:
        return self._path

    def is_null(self) -> Predicate[E]:
        self._require_nullable()
        return self._null_test("isNull")

    def is_not_null(self) -> Predicate[E]:
        self._require_nullable()
        return self._null_test("isNotNull")

    def _require_nullable(self) -> None:
        if self._leaf.nullable:
            return
        raise UsageError(
            QUERY_EXPRESSION_INVALID,
            f"{self._described()}: is_null()/is_not_null() is invalid for a "
            "non-nullable member (m-predicate null-check validity)",
        )

    def __hash__(self) -> int:  # pragma: no cover - expressions are not dict keys
        return hash(self._path)


class AssignableScalarExpr[E, T](ScalarExpr[E, T]):
    """A top-level Entity scalar attribute: a field that also orders results and
    takes a whole-member ``.set(...)`` assignment."""

    __slots__ = ("_member", "_ref", "_validate")

    def __init__(
        self, ref: AttributeRef, member: AttributeMetadata, validate: MemberValidator
    ) -> None:
        super().__init__(AuthoredMemberPath(_entity_identity(ref.entity), (ref.attribute,)), member)
        self._ref = ref
        self._member = member
        self._validate = validate

    def asc(self) -> SortKey[E]:
        """An ascending order-by key over this attribute.

        Only the Sort Key these converters produce carries the single-shot
        ``.nulls_first()`` / ``.nulls_last()`` placement modifiers; a member
        expression itself exposes neither, so placement is authorable exactly
        where a direction is.
        """
        return SortKey(OrderKey(attr=str(self._ref), direction="asc"))

    def desc(self) -> SortKey[E]:
        """A descending order-by key over this attribute (see :meth:`asc`)."""
        return SortKey(OrderKey(attr=str(self._ref), direction="desc"))

    def set(self, value: T) -> AttributeAssignment[E]:
        """A set-based ``_where``-verb assignment (``Account.balance.set(0)``)."""
        _reject_unassignable(self._ref, self._member, value, self._validate)
        return AttributeAssignment(attr=self._ref, value=value)

    def __hash__(self) -> int:  # pragma: no cover - expressions are not dict keys
        return hash(self._path)


class ScalarElementExpr[S, T](_ScalarAuthoring[S]):
    """The element a quantifier over a scalar collection binds.

    It is not a stored field: it has no path, no null check, no assignment, and
    no identity of its own, and it is read only inside a quantifier over the
    collection it came from.
    """

    __slots__ = ("_element", "_leaf")

    def __init__(self, element: AuthoredElement, leaf: _LeafFacts | None) -> None:
        self._element = element
        self._leaf = leaf

    def _described(self) -> str:
        return _subject_described(self._element)

    def _operand_type(self) -> NeutralType | None:
        return None if self._leaf is None else self._leaf.type

    def _subject(self) -> AuthoredSubject:
        return self._element

    def __hash__(self) -> int:  # pragma: no cover - expressions are not dict keys
        return hash(self._element)


def _quantified(
    kind: QuantifierKind,
    collection: AuthoredMemberPath,
    predicate: Predicate[Any] | None,
    *,
    binds: BoundElement | None,
) -> Predicate[Any]:
    """One quantifier over ``collection``; ``predicate`` binds its element.

    A scalar quantifier binds only elements of its own collection, an object
    quantifier none at all; a quantifier whose kind awaits the serving model
    presumes elements of its own collection are its own.
    """
    where = None if predicate is None else predicate.authored
    if where is not None:
        for element in _unbound_elements(where):
            if binds in ("entity", "value-object") or element.collection != collection:
                raise UsageError(
                    QUERY_PATH_INVALID,
                    f"{_subject_described(element)} is not an element of "
                    f"{collection.described()}, which this quantifier binds",
                )
    return Predicate(AuthoredQuantifier(kind, collection, where, binds))


def _presence(
    negated: bool, target: AuthoredMemberPath, predicate: Predicate[Any] | None
) -> Predicate[Any]:
    """The presence of ``target``, or with ``predicate`` whether its related
    Entity makes that predicate true; the operand binds that Entity, so it reads
    no collection element from outside."""
    where = None if predicate is None else predicate.authored
    if where is not None:
        for element in _unbound_elements(where):
            raise UsageError(
                QUERY_PATH_INVALID,
                f"{_subject_described(element)}: a collection element is read only inside "
                f"a quantifier over {element.collection.described()}, not inside a match "
                f"of {target.described()}",
            )
    return Predicate(AuthoredPresence(negated, target, where))


class _NotOneValue:
    """Equality refused by a member that is not one scalar value, where Python
    would otherwise answer object identity."""

    __slots__ = ()

    def _not_one_value(self) -> str:
        raise NotImplementedError  # pragma: no cover - every subclass describes itself

    def __eq__(self, other: object) -> NoReturn:
        raise UsageError(QUERY_EXPRESSION_INVALID, self._not_one_value())

    def __ne__(self, other: object) -> NoReturn:
        raise UsageError(QUERY_EXPRESSION_INVALID, self._not_one_value())

    def __hash__(self) -> int:  # pragma: no cover - expressions are not dict keys
        return object.__hash__(self)


class ManyScalarExpr[S, T](_NotOneValue):
    """A scalar collection: quantified element by element through ``element``,
    never compared, matched, ordered, or traversed whole."""

    __slots__ = ("_leaf", "_path")

    def _not_one_value(self) -> str:
        return (
            f"{self._path.described()}: a scalar collection is not one scalar value; "
            "quantify its elements with any/all/none over .element"
        )

    def __init__(self, path: AuthoredMemberPath, leaf: _LeafFacts) -> None:
        self._path = path
        self._leaf = leaf

    @property
    def element(self) -> ScalarElementExpr[S, T]:
        """The element a quantifier over this collection binds."""
        return ScalarElementExpr(AuthoredElement(self._path), self._leaf)

    def any(self, predicate: Predicate[S] | None = None) -> Predicate[S]:
        """Whether some element makes ``predicate`` true; bare, whether any exists."""
        return _quantified("any", self._path, predicate, binds="scalar")

    def all(self, predicate: Predicate[S]) -> Predicate[S]:
        """Whether every element makes ``predicate`` true; false or unknown fails."""
        return _quantified("all", self._path, predicate, binds="scalar")

    def none(self, predicate: Predicate[S] | None = None) -> Predicate[S]:
        """Whether no element makes ``predicate`` true; bare, whether it is empty."""
        return _quantified("none", self._path, predicate, binds="scalar")

    def __bool__(self) -> bool:
        raise TypeError(_BOOL_HINT)


class AssignableManyScalarExpr[E, T](ManyScalarExpr[E, T]):
    """A top-level Entity scalar collection, assignable whole."""

    __slots__ = ("_member", "_ref", "_validate")

    def __init__(
        self, ref: AttributeRef, member: AttributeMetadata, validate: MemberValidator
    ) -> None:
        super().__init__(AuthoredMemberPath(_entity_identity(ref.entity), (ref.attribute,)), member)
        self._ref = ref
        self._member = member
        self._validate = validate

    def set(self, value: tuple[T, ...]) -> AttributeAssignment[E]:
        """A whole-collection ``_where``-verb assignment; ``()`` clears it."""
        _reject_unassignable(self._ref, self._member, value, self._validate)
        return AttributeAssignment(attr=self._ref, value=value)


def member_expression(path: AuthoredMemberPath, shape: ValueObjectShape, py_name: str) -> Any:
    """The expression for ``shape``'s member ``py_name`` at ``path``."""
    canonical = shape.py_to_name.get(py_name)
    if canonical is None:
        raise AttributeError(f"{path.described()}: the Value Object declares no member {py_name!r}")
    child = path.child(canonical)
    nested = shape.nested_shapes.get(py_name)
    if nested is not None:
        if py_name in shape.many_py:
            return ManyValueObjectExpr[Any, Any](child, nested)
        return ValueObjectExpr[Any, Any](child, nested)
    leaf = next(item for item in shape.shape.attributes if item.name == canonical)
    if leaf.multiplicity is Multiplicity.MANY:
        return ManyScalarExpr[Any, Any](child, leaf)
    return ScalarExpr[Any, Any](child, leaf)


class ValueObjectExpr[E, V](_NotOneValue):
    """A single Value Object: dotted access reaches its members, and
    ``exists()`` / ``not_exists()`` test its presence."""

    __slots__ = ("_path", "_shape")

    def _not_one_value(self) -> str:
        return (
            f"{self._path.described()}: a Value Object is not one scalar value; compare its "
            "fields, or test its presence with exists()/not_exists()"
        )

    def __init__(self, path: AuthoredMemberPath, shape: ValueObjectShape) -> None:
        self._path = path
        self._shape = shape

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return member_expression(self._path, self._shape, name)

    def exists(self) -> Predicate[E]:
        """Whether this Value Object is present."""
        return Predicate(AuthoredPresence(False, self._path))

    def not_exists(self) -> Predicate[E]:
        """Whether this Value Object is absent."""
        return Predicate(AuthoredPresence(True, self._path))

    def __bool__(self) -> bool:
        raise TypeError(_BOOL_HINT)


class AssignableValueObjectExpr[E, V](ValueObjectExpr[E, V]):
    """A top-level Entity Value Object occurrence, assignable whole."""

    __slots__ = ("_member", "_ref", "_validate")

    def __init__(
        self,
        ref: AttributeRef,
        member: ValueObjectMetadata,
        shape: ValueObjectShape,
        validate: MemberValidator,
    ) -> None:
        super().__init__(AuthoredMemberPath(_entity_identity(ref.entity), (ref.attribute,)), shape)
        self._ref = ref
        self._member = member
        self._validate = validate

    def set(self, value: V) -> AttributeAssignment[E]:
        """A whole-occurrence ``_where``-verb assignment."""
        _reject_unassignable(self._ref, self._member, value, self._validate)
        return AttributeAssignment(attr=self._ref, value=value)


class ManyValueObjectExpr[E, V](_NotOneValue):
    """A ``many`` Value Object occurrence, quantified element by element with
    predicates built from the Value Object Class ``V``."""

    __slots__ = ("_path", "_shape")

    def _not_one_value(self) -> str:
        return (
            f"{self._path.described()}: a many Value Object is not one scalar value; "
            "quantify its elements with any/all/none"
        )

    def __init__(self, path: AuthoredMemberPath, shape: ValueObjectShape) -> None:
        self._path = path
        self._shape = shape

    def any(self, predicate: Predicate[V] | None = None) -> Predicate[E]:
        """Whether some element makes ``predicate`` true; bare, whether any exists."""
        return _quantified("any", self._path, predicate, binds="value-object")

    def all(self, predicate: Predicate[V]) -> Predicate[E]:
        """Whether every element makes ``predicate`` true; false or unknown fails."""
        return _quantified("all", self._path, predicate, binds="value-object")

    def none(self, predicate: Predicate[V] | None = None) -> Predicate[E]:
        """Whether no element makes ``predicate`` true; bare, whether it is empty."""
        return _quantified("none", self._path, predicate, binds="value-object")

    def __bool__(self) -> bool:
        raise TypeError(_BOOL_HINT)


class AssignableManyValueObjectExpr[E, V](ManyValueObjectExpr[E, V]):
    """A top-level Entity ``many`` Value Object occurrence, assignable whole."""

    __slots__ = ("_member", "_ref", "_validate")

    def __init__(
        self,
        ref: AttributeRef,
        member: ValueObjectMetadata,
        shape: ValueObjectShape,
        validate: MemberValidator,
    ) -> None:
        super().__init__(AuthoredMemberPath(_entity_identity(ref.entity), (ref.attribute,)), shape)
        self._ref = ref
        self._member = member
        self._validate = validate

    def set(self, value: tuple[V, ...]) -> AttributeAssignment[E]:
        """A whole-collection ``_where``-verb assignment; ``()`` clears it."""
        _reject_unassignable(self._ref, self._member, value, self._validate)
        return AttributeAssignment(attr=self._ref, value=value)


def _reject_unassignable(
    ref: AttributeRef,
    member: AttributeMetadata | ValueObjectMetadata,
    value: object,
    validate: MemberValidator,
) -> None:
    """Apply the shared assignment rule family to one whole-member value.

    The rules are one set, stated once in
    :func:`~parallax.core.metamodel.judge_assignment` and called from every
    surface that assigns, so none of them can drift. The member the descriptor
    installed is the whole input, so this states its rule with no model.
    """
    violation = judged_edit_violation(
        member, value, owner=ref.entity, location=member_location(member), validate=validate
    )
    if violation is not None:
        raise EditError([violation]) from None


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


type MemberValidator = Callable[[MemberDefinition, object], AuthoringViolation | None]
"""What authoring one non-null value as a member refuses first, or ``None``:
the validation-only judgment of the class that installed the member."""


def judged_edit_violation(
    member: AttributeMetadata | ValueObjectMetadata,
    value: object,
    *,
    owner: str,
    location: ModelLocation,
    validate: MemberValidator,
) -> EditViolation | None:
    """The shared judgement's verdict on ``value``, as a located violation.

    Every authoring surface translates the verdict here rather than re-deciding
    it or re-wording it: the judgement owns the rule and its message, this owns
    only the edit code the rule reports as and the owner prefix that says where
    the member was addressed. ``None`` means the assignment is accepted.

    ``location`` is the caller's, because where a refusal lands is a fact about
    the surface rather than about the verdict: a member of a model's Entity
    locates at :func:`member_location`, while a Value Object Class's own member
    belongs to no model position at all. ``validate`` is the value's own
    judgment, which the assignment rules consume rather than repeat.
    """
    try:
        known_violation = None if value is None else validate(member.definition, value)
        judge_assignment(
            member,
            value,
            known_violation=known_violation,
            known_value_valid=known_violation is None,
        )
    except UsageError as error:
        return EditViolation(
            code=EDIT_CODE_BY_RULE[error.code],
            location=location,
            member_name=member_canonical_name(member),
            message=f"{owner}.{error.args[1]}",
        )
    return None


# Relationships and Include paths


@dataclass(frozen=True, slots=True)
class AuthoredIncludeSegment:
    """One segment of an authored Include path, by the Python member name it was
    written with.

    ``root_relationship`` is the identity a path's first segment took from its
    descriptor; a continuation has none, because only the classes of a serving
    model or of a reached node say what its name denotes.
    """

    py_name: str
    root_relationship: RelationshipIdentity | None = None
    narrow_to: SubtypeSelection = ()

    def relationship_in(self, names: WireNames) -> RelationshipIdentity | None:
        """The relationship this segment denotes on the class ``names`` describes.

        A root segment applies wherever the class declares its identity, under
        whatever Python name that class spells it, so a sibling's identically named
        relationship is never its relationship.
        """
        root = self.root_relationship
        if root is None:
            return names.relationship_identities.get(self.py_name)
        return root if root in names.relationship_identities.values() else None

    def described(self) -> str:
        root = self.root_relationship
        return self.py_name if root is None else f"{root.source_entity.canonical}.{root.name}"


@dataclass(frozen=True, slots=True)
class AuthoredIncludePath:
    """An Include path as written: its segments, and the Entity ``access_source``
    the first was reached through, which binding measures against the queried
    position to decide the path-root guard."""

    segments: tuple[AuthoredIncludeSegment, ...]
    access_source: str | None = None

    def continued(self, name: str) -> AuthoredIncludePath:
        return replace(self, segments=(*self.segments, AuthoredIncludeSegment(name)))

    def described(self) -> str:
        return ".".join(segment.described() for segment in self.segments)


@dataclass(frozen=True, slots=True)
class _RootSegment:
    """The first relationship segment a descriptor seeded."""

    ref: RelationshipRef
    py_name: str
    source: str | None
    many: bool

    def authored_path(self, names: tuple[str, ...] = ()) -> AuthoredIncludePath:
        identity = RelationshipIdentity(_entity_identity(self.ref.entity), self.ref.relationship)
        return AuthoredIncludePath(
            (
                AuthoredIncludeSegment(self.py_name, identity),
                *(AuthoredIncludeSegment(name) for name in names),
            ),
            self.source,
        )

    def member_path(self) -> AuthoredMemberPath:
        return AuthoredMemberPath(_entity_identity(self.ref.entity), (self.ref.relationship,))


def root_segment(
    ref: RelationshipRef, py_name: str, source: str | None, *, many: bool
) -> _RootSegment:
    """The first segment a relationship descriptor seeds, reached through ``source``."""
    return _RootSegment(ref, py_name, source, many)


def authored_include_path(path: IncludePath[Any, Any]) -> AuthoredIncludePath:
    """The authored path ``path`` carries, refusing anything but an Include path —
    a Value Object or scalar member is no relationship to fetch through."""
    if not isinstance(path, IncludePath):  # pyright: ignore[reportUnnecessaryIsInstance] - untyped callers
        raise TypeError(
            f"{type(path).__name__} is not an Include path; include takes relationships"
        )
    return path._authored_path()  # pyright: ignore[reportPrivateUsage] - the carrier's own module reads its path


class IncludePath[E, R]:
    """An Include traversal (``Order.items``, ``Owner.pets.narrow(Dog)``): the
    seed of ``.include(...)`` and of a node's narrowed-view inspection.

    ``E`` is the Entity the seeding class access went through — where the path
    starts — and ``R`` the Entity it currently points at. Both are covariant. A
    path rooted at a descendant stands wherever one rooted at its ancestor is
    wanted, because a narrower source is a legal include source of a broader
    queried position and authors the path-root guard that says so; a path
    narrowed to a descendant target stands wherever the broad hop does, because
    everything it reaches is also reached by the broad one.

    It authors no predicate. Continuing it keeps the Python member name as
    written, and the serving model's Entity Classes resolve that name when an
    operation binds the path.
    """

    __slots__ = ("_authored",)

    def __init__(self, authored: AuthoredIncludePath | None) -> None:
        self._authored = authored

    if TYPE_CHECKING:

        def _starts_from(self) -> E:
            """Never defined at run time and never called: the output position
            that makes ``E`` covariant (see :class:`Predicate` for the
            contravariant twin)."""
            ...

        def _reaches(self) -> R:
            """Never defined at run time and never called: the output position
            that makes ``R`` covariant."""
            ...

    def _authored_path(self) -> AuthoredIncludePath:
        authored = self._authored
        if authored is None:  # pragma: no cover - subclasses derive their own
            raise UsageError(QUERY_PATH_INVALID, "no Include path")
        return authored

    def __getattr__(self, name: str) -> IncludePath[E, Any]:
        if name.startswith("_"):
            raise AttributeError(name)
        return IncludePath(self._authored_path().continued(name))

    def narrow[N](self: IncludePath[Any, N], *subtypes: type[N]) -> IncludePath[E, N]:
        """A hop-level narrowed-view request (``Owner.pets.narrow(Dog)``),
        continuable to a deeper hop. Requests the derived narrowed view, never
        marking the broad relationship loaded, and authors no predicate.

        Each named class must be a subtype of what the hop points at, which is
        the static half of ``narrow-outside-relationship-target``; which concrete
        subtypes the named classes resolve to remains a per-model fact, settled
        at preflight. Narrowing is single-shot per segment and needs at least one
        subtype, so a request can never silently answer the broad path.
        """
        authored = self._authored_path()
        *head, last = authored.segments
        described = authored.described()
        if last.narrow_to:
            raise UsageError(
                QUERY_PATH_INVALID,
                f"{described}: narrowing is single-shot per path segment and this hop is "
                f"already narrowed to {', '.join(last.narrow_to)}; derive the segment from "
                "the un-narrowed hop",
            )
        if not subtypes:
            raise UsageError(
                QUERY_PATH_INVALID, f"{described}: narrow requires at least one subtype"
            )
        narrowed = tuple(subtype_spelling(subtype) for subtype in subtypes)
        if len(set(narrowed)) != len(narrowed):
            raise UsageError(
                QUERY_PATH_INVALID,
                f"{described}: narrow alternatives must not repeat the same subtype",
            )
        selection = canonical_subtype_selection(narrowed)
        return IncludePath(
            replace(authored, segments=(*head, replace(last, narrow_to=selection))),
        )

    def __eq__(self, other: object) -> bool:
        if type(other) is not type(self):
            return NotImplemented
        return self._authored_path() == cast("IncludePath[Any, Any]", other)._authored_path()

    def __hash__(self) -> int:
        return hash(self._authored_path())

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._authored_path()!r})"


def subtype_selection(spellings: tuple[str, ...]) -> SubtypeSelection:
    """The Subtype Selection the Entity spellings ``spellings`` name, refused
    when empty or repeating one."""
    if not spellings:
        raise UsageError(QUERY_PATH_INVALID, "is_a requires at least one subtype")
    if len(set(spellings)) != len(spellings):
        raise UsageError(QUERY_PATH_INVALID, "is_a alternatives must not repeat the same subtype")
    return canonical_subtype_selection(spellings)


def _narrowed(
    target: AuthoredMemberPath,
    subtypes: tuple[type, ...],
    where: Predicate[Any] | None,
) -> Predicate[Any]:
    return Predicate(
        AuthoredNarrow(
            subtype_selection(tuple(subtype_spelling(subtype) for subtype in subtypes)),
            None if where is None else where.authored,
            target=target,
        )
    )


class RelationshipExpr[E, R](IncludePath[E, R]):
    """A to-one relationship: presence, a target-local subtype test, and
    dotted traversal into the Entity it reaches, besides its Include path.

    Its predicates answer an unaddressed position rather than ``E``: answering
    ``Predicate[E]`` would put the covariant include source in an input
    position.
    """

    __slots__ = ("_root",)

    def __init__(self, root: _RootSegment) -> None:
        super().__init__(root.authored_path())
        self._root = root

    def __getattr__(self, name: str) -> UnfinishedExpr[Any]:
        if name.startswith("_"):
            raise AttributeError(name)
        return UnfinishedExpr(self._root, (name,))

    def exists(self, predicate: Predicate[R] | None = None) -> Predicate[Any]:
        """Whether this relationship reaches an Entity; with ``predicate``,
        whether a reached Entity makes it true. False and unknown do not match."""
        return _presence(False, self._root.member_path(), predicate)

    def not_exists(self, predicate: Predicate[R] | None = None) -> Predicate[Any]:
        """Whether this relationship reaches no Entity; with ``predicate``,
        whether no reached Entity makes it true."""
        return _presence(True, self._root.member_path(), predicate)

    def is_a[S](self, *subtypes: type[S], where: Predicate[S] | None = None) -> Predicate[Any]:
        """Whether the reached Entity belongs to ``subtypes`` and, with
        ``where``, makes it true there. An absent or unselected target is
        false; a selected one keeps ``where``'s unknown."""
        return _narrowed(self._root.member_path(), subtypes, where)


class ManyRelationshipExpr[E, R](IncludePath[E, R]):
    """A to-many relationship: quantified over its related Entities with
    predicates built from the target Class ``R``, besides its Include path."""

    __slots__ = ("_root",)

    def __init__(self, root: _RootSegment) -> None:
        super().__init__(root.authored_path())
        self._root = root

    def __getattr__(self, name: str) -> UnfinishedExpr[Any]:
        if name.startswith("_"):
            raise AttributeError(name)
        return UnfinishedExpr(self._root, (name,))

    def any(self, predicate: Predicate[R] | None = None) -> Predicate[Any]:
        """Whether some related Entity makes ``predicate`` true; bare, whether
        any is related."""
        return _quantified("any", self._root.member_path(), predicate, binds="entity")

    def all(self, predicate: Predicate[R]) -> Predicate[Any]:
        """Whether every related Entity makes ``predicate`` true."""
        return _quantified("all", self._root.member_path(), predicate, binds="entity")

    def none(self, predicate: Predicate[R] | None = None) -> Predicate[Any]:
        """Whether no related Entity makes ``predicate`` true; bare, whether
        none is related."""
        return _quantified("none", self._root.member_path(), predicate, binds="entity")


class UnfinishedExpr[E](_ScalarAuthoring[E], IncludePath[E, Any]):
    """A dotted continuation past a relationship, whose member kind the serving
    model resolves.

    It offers every candidate operation — scalar, presence, subtype, and
    quantifier — and the serving model admits only the ones applicable to what
    the Python names resolve to, before any I/O. It is query-only: it neither
    assigns nor orders. Consumed as an Include, the same names bind as its
    segments.
    """

    __slots__ = ("_names", "_root")

    def __init__(self, root: _RootSegment, names: tuple[str, ...]) -> None:
        self._authored = None
        self._root = root
        self._names = names

    def _member_path(self) -> AuthoredMemberPath:
        receiver = _entity_identity(self._root.ref.entity)
        return AuthoredMemberPath(receiver, (self._root.py_name, *self._names), unfinished=True)

    def _authored_path(self) -> AuthoredIncludePath:
        return self._root.authored_path(self._names)

    def __getattr__(self, name: str) -> UnfinishedExpr[E]:
        if name.startswith("_"):
            raise AttributeError(name)
        return UnfinishedExpr(self._root, (*self._names, name))

    def _described(self) -> str:
        return ".".join((self._root.ref.entity, self._root.py_name, *self._names))

    def _operand_type(self) -> None:
        return None

    def _subject(self) -> AuthoredSubject:
        return self._member_path()

    def is_null(self) -> Predicate[E]:
        return self._null_test("isNull")

    def is_not_null(self) -> Predicate[E]:
        return self._null_test("isNotNull")

    @property
    def element(self) -> ScalarElementExpr[E, Any]:
        """The element a quantifier over this collection binds."""
        return ScalarElementExpr(AuthoredElement(self._member_path()), None)

    def any(self, predicate: Predicate[Any] | None = None) -> Predicate[E]:
        return _quantified("any", self._member_path(), predicate, binds=None)

    def all(self, predicate: Predicate[Any]) -> Predicate[E]:
        return _quantified("all", self._member_path(), predicate, binds=None)

    def none(self, predicate: Predicate[Any] | None = None) -> Predicate[E]:
        return _quantified("none", self._member_path(), predicate, binds=None)

    def exists(self, predicate: Predicate[Any] | None = None) -> Predicate[E]:
        return _presence(False, self._member_path(), predicate)

    def not_exists(self, predicate: Predicate[Any] | None = None) -> Predicate[E]:
        return _presence(True, self._member_path(), predicate)

    def is_a[S](self, *subtypes: type[S], where: Predicate[S] | None = None) -> Predicate[E]:
        return _narrowed(self._member_path(), subtypes, where)

    def __hash__(self) -> int:  # pragma: no cover - expressions are not dict keys
        return hash((self._root, self._names))

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._described()})"


EXPRESSION_OPERATION_NAMES: Final[frozenset[str]] = frozenset(
    name for name in dir(UnfinishedExpr) if not name.startswith("_")
)
"""Every public name a member expression's dotted access answers itself rather
than continuing to a member — the surface a member declaration may not reuse."""
