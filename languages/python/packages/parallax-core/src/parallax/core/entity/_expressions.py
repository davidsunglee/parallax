from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, NoReturn, assert_never, cast

from parallax.core.base import (
    ManagedValue,
    NeutralType,
    String,
    coerce_neutral_input,
    matches_neutral_type,
)
from parallax.core.document_codec._authoring import (
    BORROWED_SOURCE_ACCESS,
    validate_member_authoring,
)
from parallax.core.entity._errors import EDIT_CODE_BY_RULE, EditError, EditViolation
from parallax.core.metamodel import (
    AttributeLocation,
    AttributeMetadata,
    EntityIdentity,
    EntityLocation,
    Leaf,
    ModelLocation,
    Multiplicity,
    OccurrenceMetadata,
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
from parallax.core.object_query import (
    IncludeSegment,
    ObjectQueryNode,
    OrderKey,
    object_query,
    subtype_spelling,
)
from parallax.core.predicate import (
    All,
    And,
    Between,
    Comparison,
    ComparisonOp,
    Exists,
    Group,
    Membership,
    Narrow,
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
    NoneOp,
    Not,
    NotExists,
    NullCheck,
    Or,
    PredicateNode,
    QueryDefinitionError,
    Scalar,
    StringMatch,
    StringOp,
    SubtypeSelection,
    canonical_subtype_selection,
)
from parallax.core.predicate._interpretation import (
    BETWEEN,
    COMPARE,
    MEMBER_OF,
    NULL_TEST,
    AttributeSubject,
    Compare,
    InRange,
    Match,
    MemberOf,
    NullTest,
    OperationSubject,
    PathSubject,
    ScalarOperator,
)
from parallax.core.wire import encode_wire

if TYPE_CHECKING:
    from collections.abc import Sequence

    from parallax.core.object_query._nodes import (
        IncludePath,
        TemporalDimension,
        TemporalSelection,
    )

__all__ = [
    "AllPredicate",
    "AttributeAssignment",
    "AttributeExpr",
    "AttributeRef",
    "AuthoredAnd",
    "AuthoredConstant",
    "AuthoredGroup",
    "AuthoredNarrow",
    "AuthoredNot",
    "AuthoredOr",
    "AuthoredPredicate",
    "AuthoredQuantifier",
    "AuthoredQuery",
    "AuthoredSemiJoin",
    "ElementAttributeExpr",
    "Predicate",
    "PreparedOperation",
    "RelationshipPath",
    "RelationshipRef",
    "SortKey",
    "UnfinishedOperation",
    "canonical_predicate",
    "conjoin",
    "judged_edit_violation",
    "managed_literal",
    "member_location",
    "snake_to_camel",
    "typed_authoring_leaf",
]


def _invalid_operand(
    path: str,
    neutral_type: NeutralType | None,
    value: object,
    rule: str,
) -> QueryDefinitionError:
    declared = "<unresolved>" if neutral_type is None else repr(neutral_type)
    return QueryDefinitionError(
        code="query-expression-invalid",
        message=(
            f"{path}: declared NeutralType {declared}; supplied Python carrier "
            f"{type(value).__name__}; developer-input rule violated: {rule}"
        ),
    )


def _single_scalar[
    M: AttributeMetadata | ValueObjectAttributeMetadata | ValueObjectAttributeDeclaration
](path: str, member: M) -> M:
    """``member``, refused where it is a scalar collection: a collection is not
    one scalar value, so no scalar operation or ordering reaches its elements."""
    if member.multiplicity is Multiplicity.MANY:
        raise QueryDefinitionError(
            code="query-expression-invalid",
            message=(
                f"{path}: a scalar collection is not one scalar value and takes no comparison, "
                "membership, range, string, null-check, or ordering operation"
            ),
        )
    return member


def managed_literal(path: str, neutral_type: NeutralType, value: object) -> ManagedValue:
    """``value`` admitted as one managed ``neutral_type`` operand under the Typed
    developer-input policy, or a refusal naming ``path``."""
    if value is None:
        raise _invalid_operand(
            path,
            neutral_type,
            value,
            "None is not a typed literal; use .is_null() or .is_not_null()",
        )
    managed = coerce_neutral_input(value, neutral_type)
    if not matches_neutral_type(managed, neutral_type):
        raise _invalid_operand(
            path,
            neutral_type,
            value,
            "the developer input policy does not admit this carrier for the declared type",
        )
    return cast("ManagedValue", managed)


def snake_to_camel(name: str) -> str:
    """The canonical member name a snake_case Python spelling denotes.

    A predicate or query reference names members canonically, so this is the rule that
    turns an authored member spelling into the one the wire carries. It lives
    beside the references it builds because a relationship hop past the first
    reaches no declaration and has only the spelling to go on.
    """
    head, *tail = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


_BOOL_HINT = (
    "a Parallax expression has no truth value; combine predicates with & / | / ~ and "
    "parentheses (not and/or/not), and use .between()/.in_() instead of chained comparisons"
)

_NESTED_COMPARISONS: dict[ComparisonOp, NestedComparisonOp] = {
    "eq": "nestedEq",
    "notEq": "nestedNotEq",
    "greaterThan": "nestedGt",
    "greaterThanEquals": "nestedGte",
    "lessThan": "nestedLt",
    "lessThanEquals": "nestedLte",
}
_NESTED_MEMBERSHIPS: dict[str, NestedMembershipOp] = {"in": "nestedIn", "notIn": "nestedNotIn"}
_NESTED_STRINGS: dict[StringOp, NestedStringOp] = {
    "like": "nestedLike",
    "notLike": "nestedNotLike",
    "startsWith": "nestedStartsWith",
    "endsWith": "nestedEndsWith",
    "contains": "nestedContains",
}


@dataclass(frozen=True, slots=True)
class PreparedOperation:
    """A scalar operation over a known declared subject, its operands already
    managed under ``prepared_type``, the type that subject's declaration states.

    A string pattern is kept as authored; every other operand is managed.
    """

    subject: OperationSubject
    operator: ScalarOperator
    operands: tuple[object, ...]
    prepared_type: NeutralType


@dataclass(frozen=True, slots=True)
class UnfinishedOperation:
    """A scalar operation whose subject continues from the Entity ``anchor`` by
    Python member ``names``, its native ``operands`` awaiting the type the
    serving model resolves that subject to."""

    anchor: EntityIdentity
    names: tuple[str, ...]
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


@dataclass(frozen=True, slots=True)
class AuthoredNarrow:
    """``operand`` at the current Entity position narrowed to the Subtype Selection ``to``."""

    to: SubtypeSelection
    operand: AuthoredPredicate


@dataclass(frozen=True, slots=True)
class AuthoredQuantifier:
    """Whether some element (``any``) or no element (``none``) of the Value Object
    occurrence at the Entity-rooted ``path`` makes ``where`` true; without
    ``where``, whether one is present at all. ``where`` is element-relative."""

    kind: Literal["any", "none"]
    path: str
    where: AuthoredPredicate | None = None


@dataclass(frozen=True, slots=True)
class AuthoredSemiJoin:
    """Whether some Entity the ``Class.relationship`` reference reaches makes
    ``where`` true, complemented when ``negated``. ``where`` addresses the
    reached Entity."""

    relationship: str
    negated: bool
    where: AuthoredPredicate | None = None


type AuthoredPredicate = (
    PreparedOperation
    | UnfinishedOperation
    | AuthoredConstant
    | AuthoredAnd
    | AuthoredOr
    | AuthoredNot
    | AuthoredGroup
    | AuthoredNarrow
    | AuthoredQuantifier
    | AuthoredSemiJoin
)

_UNFILTERED: AuthoredPredicate = AuthoredConstant(truth=True)
_NO_TEMPORAL: Mapping[TemporalDimension, TemporalSelection] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class AuthoredQuery:
    """The authored state of one Typed Object Query: its target, its authored
    predicate, and its other clauses in their canonical spellings.

    Model-free and immutable, so one value serves every model that accepts its
    target; nothing resolved is attached back to it.
    """

    target: EntityIdentity
    predicate: AuthoredPredicate
    narrow_to: SubtypeSelection | None = None
    temporal: Mapping[TemporalDimension, TemporalSelection] = _NO_TEMPORAL
    order_by: tuple[OrderKey, ...] = ()
    limit: int | None = None
    includes: tuple[IncludePath, ...] = field(default_factory=tuple)

    def canonical(self) -> ObjectQueryNode:
        """The canonical Object Query this authored state exports to."""
        return object_query(
            self.target,
            canonical_predicate(self.predicate),
            narrow_to=self.narrow_to,
            temporal=self.temporal,
            order_by=self.order_by,
            limit=self.limit,
            includes=self.includes,
        )


def canonical_predicate(authored: AuthoredPredicate) -> PredicateNode:
    """The canonical predicate ``authored`` exports to, encoding its prepared
    operands; an unfinished operation has no canonical form until bound."""
    match authored:
        case PreparedOperation():
            return _canonical_operation(authored)
        case UnfinishedOperation(anchor=anchor, names=names):
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=(
                    f"{anchor.canonical}.{'.'.join(names)}: an operation over Python member names "
                    "has no canonical form until a serving model resolves them"
                ),
            )
        case AuthoredAnd(operands=operands):
            return And(tuple(canonical_predicate(operand) for operand in operands))
        case AuthoredOr(operands=operands):
            return Or(tuple(canonical_predicate(operand) for operand in operands))
        case AuthoredNot(operand=operand):
            return Not(canonical_predicate(operand))
        case AuthoredGroup(operand=operand):
            return Group(canonical_predicate(operand))
        case _:
            return _canonical_scope(authored)


def _canonical_scope(
    authored: AuthoredConstant | AuthoredNarrow | AuthoredQuantifier | AuthoredSemiJoin,
) -> PredicateNode:
    match authored:
        case AuthoredConstant(truth=truth):
            return All() if truth else NoneOp()
        case AuthoredNarrow(to=to, operand=operand):
            return Narrow(to=to, operand=canonical_predicate(operand))
        case AuthoredQuantifier(kind=kind, path=path, where=where):
            exported = None if where is None else canonical_predicate(where)
            if kind == "any":
                return NestedExists(path=path, where=exported)
            return NestedNotExists(path=path, where=exported)
        case AuthoredSemiJoin(relationship=relationship, negated=negated, where=where):
            interior = None if where is None else canonical_predicate(where)
            if negated:
                return NotExists(rel=relationship, op=interior)
            return Exists(rel=relationship, op=interior)
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(authored)


def _canonical_operation(operation: PreparedOperation) -> PredicateNode:
    operator, prepared_type = operation.operator, operation.prepared_type
    literals = tuple(
        operand if isinstance(operator, Match) else _encoded(prepared_type, operand)
        for operand in operation.operands
    )
    subject = operation.subject
    if isinstance(subject, AttributeSubject):
        return _canonical_attribute_operation(subject.reference, operator, literals)
    return _canonical_path_operation(subject.path, operator, literals)


def _encoded(neutral_type: NeutralType, value: object) -> Scalar:
    return cast("Scalar", encode_wire(neutral_type, cast("ManagedValue", value)))


def _canonical_attribute_operation(
    attr: str, operator: ScalarOperator, literals: tuple[object, ...]
) -> PredicateNode:
    match operator:
        case Compare(op=tag):
            return Comparison(op=tag, attr=attr, value=cast("Scalar", literals[0]))
        case InRange():
            lower, upper = cast("tuple[Scalar, Scalar]", literals)
            return Between(attr=attr, lower=lower, upper=upper)
        case MemberOf(op=tag):
            return Membership(op=tag, attr=attr, values=cast("tuple[Scalar, ...]", literals))
        case Match(op=tag, case_insensitive=folded):
            return StringMatch(
                op=tag, attr=attr, value=cast("str", literals[0]), case_insensitive=folded or None
            )
        case NullTest(op=tag):
            return NullCheck(op=tag, attr=attr)
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(operator)


def _canonical_path_operation(
    path: str, operator: ScalarOperator, literals: tuple[object, ...]
) -> PredicateNode:
    match operator:
        case Compare(op=tag):
            return NestedComparison(
                op=_NESTED_COMPARISONS[tag], path=path, value=cast("Scalar", literals[0])
            )
        case InRange():
            lower, upper = cast("tuple[Scalar, Scalar]", literals)
            return NestedRange(path=path, lower=lower, upper=upper)
        case MemberOf(op=tag):
            return NestedMembership(
                op=_NESTED_MEMBERSHIPS[tag],
                path=path,
                values=cast("tuple[Scalar, ...]", literals),
            )
        case Match(op=tag, case_insensitive=folded):
            return NestedStringMatch(
                op=_NESTED_STRINGS[tag],
                path=path,
                value=cast("str", literals[0]),
                case_insensitive=folded or None,
            )
        case NullTest(op=tag):
            return NestedNullCheck(
                op="nestedIsNull" if tag == "isNull" else "nestedIsNotNull", path=path
            )
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(operator)


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
    """One typed ``_where``-verb assignment (``Attr.set(value)``).

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
    # is the narrower position. So `Animal.name == n` combined with
    # `Dog.bark_volume > v` addresses `Dog`: a `Dog` query takes it, an `Animal`
    # query is refused statically, and neither answer turns on operand order.
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
    for zero arguments — the shared builder behind every variadic predicate
    scope, so a bare presence test, a single predicate, and a conjunction can
    never drift from the whole-query combination ``Entity.where`` builds. It
    accepts whatever :func:`and_terms` does, which is what lets the unfiltered
    ``Entity.all`` reach it as a sole argument."""
    if not predicates:
        return None
    if len(predicates) == 1:
        return predicates[0].authored
    operands: list[AuthoredPredicate] = []
    for predicate in predicates:
        operands.extend(and_terms(predicate))
    return AuthoredAnd(tuple(operands))


class _ScalarAuthoring[P]:
    """Comparison, Boolean, membership, range, and string authoring shared by
    every scalar subject.

    A subject supplies the type its declaration states, when it knows one, and
    the canonical subject a prepared operation names; operands are prepared once
    under that type and retained managed. A subject whose type is not known
    authors through :meth:`_unprepared`.
    """

    __slots__ = ()

    def _described(self) -> str:
        raise NotImplementedError

    def _operand_type(self) -> NeutralType | None:
        raise NotImplementedError

    def _subject(self) -> OperationSubject:
        raise NotImplementedError

    def _unprepared(self, operator: ScalarOperator, operands: tuple[object, ...]) -> NoReturn:
        """The refusal of an operation whose subject states no scalar type."""
        described = self._described()
        if isinstance(operator, Match):
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=f"{described}: literal operations require resolved scalar metadata",
            )
        raise _invalid_operand(
            described,
            None,
            operands[0] if operands else operands,
            "typed literal operations require resolved scalar metadata",
        )

    def _operation(self, operator: ScalarOperator, values: tuple[object, ...]) -> Predicate[P]:
        neutral_type = self._operand_type()
        if neutral_type is None:
            self._unprepared(operator, values)
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
        if neutral_type is None:
            self._unprepared(operator, (value,))
        if not isinstance(neutral_type, String):
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=f"{self._described()}: string operations require a String leaf",
            )
        return Predicate(PreparedOperation(self._subject(), operator, (value,), neutral_type))

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
        if neutral_type is None:  # pragma: no cover - a nullable check resolves its member first
            self._unprepared(NULL_TEST[op], ())
        return Predicate(PreparedOperation(self._subject(), NULL_TEST[op], (), neutral_type))

    def __bool__(self) -> bool:
        raise TypeError(_BOOL_HINT)


class AttributeExpr[E, T](_ScalarAuthoring[E]):
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

    def _described(self) -> str:
        return self._dotted()

    def _operand_type(self) -> NeutralType | None:
        member = self._resolved_scalar_member()
        return None if member is None else member.type

    def _subject(self) -> OperationSubject:
        if self._path:
            return PathSubject(self._dotted())
        return AttributeSubject(str(self.ref))

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
            return _single_scalar(self._dotted(), self._member) if not self._path else None
        if self._member is None or isinstance(self._member, AttributeMetadata) or not self._path:
            return None
        container: OccurrenceMetadata = self._member
        for segment in self._path[:-1]:
            nested = container.value_object(snake_to_camel(segment))
            if nested is None:
                return None
            container = nested
        leaf = container.attribute(snake_to_camel(self._path[-1]))
        return None if leaf is None else _single_scalar(self._dotted(), leaf)

    def is_null(self) -> Predicate[E]:
        self._reject_non_nullable_null_check()
        return self._null_test("isNull")

    def is_not_null(self) -> Predicate[E]:
        self._reject_non_nullable_null_check()
        return self._null_test("isNotNull")

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
        ``predicates``, same-element composed) over this value-object-terminated
        path. Zero arguments author the bare presence test; the interior
        predicates are built from the value object's own element-scoped
        attributes, never re-prefixed."""
        return Predicate(AuthoredQuantifier("any", self._dotted(), conjoin(predicates)))

    def not_exists(self, *predicates: Predicate[Any]) -> Predicate[E]:
        """The complement of :meth:`exists`."""
        return Predicate(AuthoredQuantifier("none", self._dotted(), conjoin(predicates)))

    def asc(self) -> SortKey[E]:
        """An ascending order-by key over this attribute.

        Only the Sort Key these converters produce carries the single-shot
        ``.nulls_first()`` / ``.nulls_last()`` placement modifiers; an Attribute
        Expression itself exposes neither, so placement is authorable exactly where
        a direction is.
        """
        self._resolved_scalar_member()
        return SortKey(OrderKey(attr=str(self.ref), direction="asc"))

    def desc(self) -> SortKey[E]:
        """A descending order-by key over this attribute (see :meth:`asc`)."""
        self._resolved_scalar_member()
        return SortKey(OrderKey(attr=str(self.ref), direction="desc"))

    def set(self, value: T) -> AttributeAssignment[E]:
        """A set-based ``_where``-verb assignment (``Account.balance.set(0)``).

        Only a top-level scalar attribute or Value Object member is assignable: a
        Value Object always binds its whole document, so there is no sparse write
        below its boundary. A Value Object value stays in its live frontend
        carrier until the shared authoring traversal prepares it, so typed and
        serialized writes judge one structural shape without an intermediate tree.

        The value parameter is the member's own declared type, unlike a
        comparison's: an assignment's value genuinely IS a member value rather
        than an operand the developer-input policy admits. A raw document a Value
        Object member equally accepts is what that narrowing costs — a spelling
        the rules still judge and the parameter no longer admits.
        """
        if self._path:
            raise EditError([self._nested_path_violation()]) from None
        self._reject_unassignable(value)
        return AttributeAssignment(attr=self.ref, value=value)

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
        """Apply the shared assignment rule family to a rendered value.

        The rules are one set, stated once in
        :func:`~parallax.core.metamodel.judge_assignment` and called from every
        surface that assigns: here, ``Entity.edit(...)``, and the
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
        known_violation = (
            validate_member_authoring(
                member.definition,
                value,
                source_access=BORROWED_SOURCE_ACCESS,
                normalize_leaf=typed_authoring_leaf,
                path=owner,
            )
            if value is not None
            and (
                not isinstance(member, AttributeMetadata)
                or member.multiplicity is Multiplicity.MANY
            )
            else None
        )
        judge_assignment(member, value, known_violation=known_violation)
    except WriteAssignmentError as error:
        return EditViolation(
            code=EDIT_CODE_BY_RULE[error.rule],
            location=location,
            member_name=member_canonical_name(member),
            message=f"{owner}.{error}",
        )
    return None


def typed_authoring_leaf(leaf: Leaf, value: object, _path: str) -> tuple[object, bool]:
    neutral_type = leaf.type
    managed = coerce_neutral_input(value, neutral_type)
    return managed, matches_neutral_type(managed, neutral_type)


class ElementAttributeExpr[V, T](_ScalarAuthoring[V]):
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

    def _described(self) -> str:
        return self._dotted()

    def _operand_type(self) -> NeutralType | None:
        return None if self._shape is None else self._leaf().type

    def _subject(self) -> OperationSubject:
        return PathSubject(self._dotted())

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
        return _single_scalar(self._dotted(), leaf)

    def is_null(self) -> Predicate[V]:
        self._reject_non_nullable_null_check()
        return self._null_test("isNull")

    def is_not_null(self) -> Predicate[V]:
        self._reject_non_nullable_null_check()
        return self._null_test("isNotNull")

    def _reject_non_nullable_null_check(self) -> None:
        if self._leaf().nullable:
            return
        raise QueryDefinitionError(
            code="query-expression-invalid",
            message=f"{self._dotted()}: null checks require a nullable scalar leaf",
        )

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
        , never marking the broad relationship loaded.

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
        (optionally matching ``predicates``).

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
        return Predicate(AuthoredSemiJoin(self._single_hop_ref(), False, conjoin(predicates)))

    def not_exists(self, *predicates: Predicate[R]) -> Predicate[Any]:
        """The complement of :meth:`exists`."""
        return Predicate(AuthoredSemiJoin(self._single_hop_ref(), True, conjoin(predicates)))

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
