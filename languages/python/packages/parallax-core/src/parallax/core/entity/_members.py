from __future__ import annotations

from collections.abc import Sequence as _Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, overload

from parallax.core.base import FLOAT32, INT32, Float32, Int32, NeutralType
from parallax.core.entity._construction_input import UNLOADED
from parallax.core.entity._errors import EntityDefinitionError, UnloadedRelationshipError
from parallax.core.entity._expressions import (
    AssignableManyScalarExpr,
    AssignableManyValueObjectExpr,
    AssignableScalarExpr,
    AssignableValueObjectExpr,
    AttributeRef,
    AuthoredPath,
    ManyRelationshipExpr,
    ManyScalarExpr,
    ManyValueObjectExpr,
    RelationshipExpr,
    RelationshipRef,
    ScalarExpr,
    ValueObjectExpr,
    ValueObjectReceiver,
    member_expression,
    relationship_hop,
)
from parallax.core.entity._instance_state import COMPACT_STATE_SLOT, plan_of
from parallax.core.metamodel import (
    APPLICATION_ASSIGNED,
    MAX,
    NOT_PRIMARY_KEY,
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    AttributeMetadata,
    AttributePrimaryKey,
    Cardinality,
    Max,
    Multiplicity,
    NullPlacement,
    PersistenceMode,
    PrimaryKey,
    Sequence,
    SortDirection,
    TablePerHierarchy,
    ValueObjectMetadata,
)

if TYPE_CHECKING:
    from parallax.core.entity._declaration import ValueObjectShape
    from parallax.core.entity._entity import Entity
    from parallax.core.entity._value_object import ValueObject

__all__ = [
    "MANY_TO_ONE",
    "MAX",
    "ONE_TO_MANY",
    "ONE_TO_ONE",
    "READ_ONLY",
    "READ_WRITE",
    "TABLE_PER_CONCRETE_SUBTYPE",
    "AbstractRoot",
    "AbstractSubtype",
    "Attr",
    "AttrSpec",
    "ConcreteSubtype",
    "DefiningRelSpec",
    "Document",
    "ElementAttr",
    "Float32",
    "IndexSpec",
    "InheritanceRole",
    "Int32",
    "Rel",
    "RelSpec",
    "ReverseRelSpec",
    "Sequence",
    "TablePerHierarchy",
    "asc",
    "attr",
    "desc",
    "index",
    "rel",
]

# The authoring spellings of the closed core algebras. A header or factory
# argument names the algebra member directly rather than a string keyword, so an
# unspellable combination is a static error before it is a runtime one. The
# payload-free variants owned elsewhere (`MAX`, `TABLE_PER_CONCRETE_SUBTYPE`),
# their payload-carrying siblings (`Sequence`, `TablePerHierarchy`,
# `AbstractRoot`), and the two narrowable Neutral Types (`Int32`, `Float32`) are
# re-exported from here for the same reason: the authoring surface is one import.
ONE_TO_ONE: Final = Cardinality.ONE_TO_ONE
MANY_TO_ONE: Final = Cardinality.MANY_TO_ONE
ONE_TO_MANY: Final = Cardinality.ONE_TO_MANY
READ_WRITE: Final = PersistenceMode.READ_WRITE
READ_ONLY: Final = PersistenceMode.READ_ONLY


@dataclass(frozen=True, slots=True)
class AbstractSubtype:
    """The rowless interior family position. Python subclassing supplies the
    parent, so the role carries nothing; ``inheritance=AbstractSubtype`` and
    ``inheritance=AbstractSubtype()`` are the same declaration."""


@dataclass(frozen=True, slots=True)
class ConcreteSubtype:
    """The row-bearing family position, tagged under a hierarchy strategy.

    Python subclassing supplies the parent. A tag value is either absent or
    nonempty, matching the accepted variant it compiles to.
    """

    tag_value: str | None = None

    def __post_init__(self) -> None:
        if self.tag_value is not None and not self.tag_value:
            raise EntityDefinitionError(
                code="entity-option-invalid-value",
                message="a concrete-subtype tag value is either absent or nonempty",
            )


type InheritanceRole = AbstractRoot | AbstractSubtype | ConcreteSubtype
"""The parent-free authoring counterpart of the core ``Inheritance`` algebra."""


DEFAULT_STRUCTURED_COLUMN: Final = "payload"
"""The Structured Column name ``layout=Document()`` supplies for an author who
names none. It is an authoring convenience: accepted metadata and the exported
descriptor always carry the resolved name."""


@dataclass(frozen=True, slots=True)
class Document:
    """Relational Document Layout, as a class header spells it.

    The column name is optional, so ``layout=Document`` and ``layout=Document()``
    are the same declaration. ``Columns`` has no counterpart here: omitting
    ``layout=`` is what selects it, and a second spelling of the default would be
    a way to say nothing.
    """

    column: str = DEFAULT_STRUCTURED_COLUMN


@dataclass(frozen=True, slots=True)
class OrderTerm:
    """One target-local ordering term: a member name, direction, and Null Placement.

    ``nulls`` is ``None`` when the term left placement unauthored, which the
    accepted model normalizes to Nulls Last — the canonical placement in either
    direction. Only a term created by :func:`asc` or :func:`desc` can carry a
    placement, because a bare member name in an ``order_by=`` tuple has nowhere
    to hang the modifier.

    This term declares part of a model, not part of a query, so a rejected
    placement composition raises a plain :class:`ValueError` and stays outside the
    query-definition error family. An Object Query Sort Key
    (``object_query.OrderKey``) carries the same single-shot rule and does belong
    to that family, so it raises ``QueryDefinitionError`` instead; the two
    spellings differ because the surfaces do, not by accident.
    """

    member: str
    direction: SortDirection = SortDirection.ASCENDING
    nulls: NullPlacement | None = None

    def nulls_first(self) -> OrderTerm:
        """This term with NULLs placed first. Single-shot (`m-relationship`)."""
        return self._with_placement(NullPlacement.NULLS_FIRST)

    def nulls_last(self) -> OrderTerm:
        """This term with NULLs placed last — the default, stated explicitly."""
        return self._with_placement(NullPlacement.NULLS_LAST)

    def _with_placement(self, placement: NullPlacement) -> OrderTerm:
        if self.nulls is not None:
            raise ValueError(
                f"{self.member}: null placement is single-shot and is already "
                f"{self.nulls.name}; derive the term from the unplaced base"
            )
        return OrderTerm(member=self.member, direction=self.direction, nulls=placement)


@dataclass(frozen=True, slots=True)
class AttrSpec:
    """One ``attr(...)`` value: the declaration facts an annotation cannot carry.

    Nullability is absent by design — the annotation alone declares it. The
    primary-key state arrives normalized, so a generation without a key is
    unrepresentable here.
    """

    primary_key: AttributePrimaryKey = NOT_PRIMARY_KEY
    column: str | None = None
    name: str | None = None
    max_length: int | None = None
    type: NeutralType | None = None
    precision: int | None = None
    scale: int | None = None
    read_only: bool = False
    optimistic_locking: bool = False


@dataclass(frozen=True, slots=True)
class DefiningRelSpec:
    """The defining branch: this direction owns the association's mapping facts."""

    cardinality: Cardinality
    join: tuple[str, str]
    dependent: bool = False
    order_by: tuple[OrderTerm, ...] = ()
    name: str | None = None


@dataclass(frozen=True, slots=True)
class ReverseRelSpec:
    """The reverse branch: it names the target's defining relationship and nothing else."""

    reverse_of: str
    order_by: tuple[OrderTerm, ...] = ()
    name: str | None = None


type RelSpec = DefiningRelSpec | ReverseRelSpec
"""The two mutually exclusive ``rel(...)`` forms."""


@dataclass(frozen=True, slots=True)
class IndexSpec:
    """One local index over a nonempty ordered sequence of Python member names."""

    name: str
    members: tuple[str, ...]
    unique: bool = False


def _invalid(message: str) -> EntityDefinitionError:
    return EntityDefinitionError(code="entity-option-invalid-value", message=message)


def _context(message: str) -> EntityDefinitionError:
    return EntityDefinitionError(code="entity-option-context-invalid", message=message)


def _optional_name(value: object, option: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise _invalid(f"{option}= takes a nonempty string, got {value!r}")
    return value


def _optional_positive(value: object, option: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise _invalid(f"{option}= takes a positive integer, got {value!r}")
    return value


def _primary_key(value: object) -> AttributePrimaryKey:
    """The normalized primary-key state a ``primary_key=`` spelling denotes.

    A generation is authored as the algebra member itself: the payload-free
    ``MAX`` constant, or a ``Sequence(...)`` instance.
    """
    if value is False:
        return NOT_PRIMARY_KEY
    if value is True:
        return PrimaryKey(APPLICATION_ASSIGNED)
    if isinstance(value, (Max, Sequence)):
        return PrimaryKey(value)
    raise _invalid(
        f"primary_key= takes False, True, MAX, or Sequence(...), got {value!r}",
    )


def _narrowed_type(value: object) -> NeutralType | None:
    """The Neutral Type a ``type=`` narrowing names.

    Only the two-variant integer and float families are narrowable, so the option
    admits exactly ``Int32`` and ``Float32``; every other Neutral Type follows
    from the annotation alone.
    """
    if value is None:
        return None
    if value is Int32 or isinstance(value, Int32):
        return INT32
    if value is Float32 or isinstance(value, Float32):
        return FLOAT32
    raise _invalid(f"type= takes Int32 or Float32, got {value!r}")


def attr(
    *,
    primary_key: object = False,
    column: str | None = None,
    name: str | None = None,
    max_length: int | None = None,
    type: object = None,
    precision: int | None = None,
    scale: int | None = None,
    read_only: bool = False,
    optimistic_locking: bool = False,
) -> Any:
    """Declare one scalar or Value Object member's non-annotation facts.

    Returns ``Any`` so the assignment slot of an ``Attr[T]`` member type-checks
    as ``T``. Every argument is validated here: an intrinsically invalid value
    raises ``entity-option-invalid-value`` and an incoherent combination raises
    ``entity-option-context-invalid``, both at this call rather than at class
    creation.
    """
    if (precision is None) != (scale is None):
        raise _context("precision= and scale= are declared together or not at all")
    return AttrSpec(
        primary_key=_primary_key(primary_key),
        column=_optional_name(column, "column"),
        name=_optional_name(name, "name"),
        max_length=_optional_positive(max_length, "max_length"),
        type=_narrowed_type(type),
        precision=_decimal_parameter(precision, "precision"),
        scale=_decimal_parameter(scale, "scale"),
        read_only=_flag(read_only, "read_only"),
        optimistic_locking=_flag(optimistic_locking, "optimistic_locking"),
    )


def _decimal_parameter(value: object, option: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _invalid(f"{option}= takes a non-negative integer, got {value!r}")
    return value


def _flag(value: object, option: str) -> bool:
    if not isinstance(value, bool):
        raise _invalid(f"{option}= takes a bool, got {value!r}")
    return value


def _order_by(terms: object) -> tuple[OrderTerm, ...]:
    """The ordering terms an ``order_by=`` tuple denotes.

    A bare string is ascending with the canonical Nulls Last placement;
    :func:`asc` and :func:`desc` spell either direction explicitly and are the
    only spellings that can then choose a placement.
    """
    if terms is None:
        return ()
    if isinstance(terms, str) or not isinstance(terms, _Sequence):
        raise _invalid(f"order_by= takes a sequence of member names, got {terms!r}")
    resolved: list[OrderTerm] = []
    for term in terms:  # pyright: ignore[reportUnknownVariableType] - order_by= elements are untyped developer input, validated per iteration below
        if isinstance(term, OrderTerm):
            resolved.append(term)
        elif isinstance(term, str) and term:
            resolved.append(OrderTerm(term))
        else:
            raise _invalid(f"order_by= takes member names or asc()/desc() terms, got {term!r}")
    return tuple(resolved)


def asc(member: str) -> OrderTerm:
    """An ascending ordering term — the explicit twin of a bare member name.

    Only the term these helpers return carries the single-shot
    ``.nulls_first()`` / ``.nulls_last()`` placement modifiers, so placement is
    authorable exactly where a direction is.
    """
    return OrderTerm(_required_name(member, "asc"), SortDirection.ASCENDING)


def desc(member: str) -> OrderTerm:
    """A descending ordering term (see :func:`asc`)."""
    return OrderTerm(_required_name(member, "desc"), SortDirection.DESCENDING)


def _required_name(value: object, option: str) -> str:
    if not isinstance(value, str) or not value:
        raise _invalid(f"{option}() takes a nonempty member name, got {value!r}")
    return value


def rel(
    *,
    cardinality: Cardinality | None = None,
    join: tuple[str, str] | None = None,
    dependent: bool = False,
    reverse_of: str | None = None,
    order_by: _Sequence[str | OrderTerm] | None = None,
    name: str | None = None,
) -> Any:
    """Declare one relationship in exactly one of the two mutually exclusive forms.

    The defining form owns cardinality, the join, dependency, and its own
    ordering; the reverse form names the target's defining relationship. Mixing
    them raises ``entity-option-context-invalid`` at this call.
    """
    defining = cardinality is not None or join is not None or dependent
    if reverse_of is not None:
        if defining:
            raise _context(
                "rel(reverse_of=...) is the reverse form; it takes no cardinality, "
                "join, or dependency"
            )
        return ReverseRelSpec(
            reverse_of=_required_name(reverse_of, "rel(reverse_of=)"),
            order_by=_order_by(order_by),
            name=_optional_name(name, "name"),
        )
    if cardinality is None or join is None:
        raise _context("rel(...) declares either cardinality= with join=, or reverse_of=")
    if not isinstance(cardinality, Cardinality):  # pyright: ignore[reportUnnecessaryIsInstance] - build-time guard against a mistyped developer value the annotation cannot enforce
        raise _invalid(
            f"cardinality= takes ONE_TO_ONE, MANY_TO_ONE, or ONE_TO_MANY, got {cardinality!r}"
        )
    if not isinstance(join, tuple) or len(join) != 2:  # pyright: ignore[reportUnnecessaryIsInstance] - build-time guard against a mistyped developer value the annotation cannot enforce
        raise _invalid(f"join= takes a (source_member, target_member) pair, got {join!r}")
    return DefiningRelSpec(
        cardinality=cardinality,
        join=(_required_name(join[0], "join source"), _required_name(join[1], "join target")),
        dependent=_flag(dependent, "dependent"),
        order_by=_order_by(order_by),
        name=_optional_name(name, "name"),
    )


def index(name: str, *members: str, unique: bool = False) -> IndexSpec:
    """Declare one local index over ``members``, in the order given.

    Components are Python member names of the declaring Entity. An empty member
    list raises ``entity-option-context-invalid`` here; an unknown, duplicate, or
    non-local component is a formation-time issue.
    """
    if not members:
        raise _context(f"index({name!r}) declares at least one member")
    return IndexSpec(
        name=_required_name(name, "index"),
        members=tuple(_required_name(member, "index member") for member in members),
        unique=_flag(unique, "unique"),
    )


class Attr[T]:
    """The scalar and Value Object member annotation, and the descriptor it installs.

    Class access through an Entity Class yields the member expression its kind
    and multiplicity select — a scalar, a scalar collection, a Value Object, or
    a ``many`` Value Object — carrying this member's own declared Metadata,
    which is every fact a whole-member assignment built from it is judged
    against. Instance access yields the member value. A non-data descriptor, so
    Pydantic's instance ``__dict__`` legitimately shadows the instance branch.

    The class-access overloads parameterize the expression by the class the
    access went THROUGH, not the one that declares the member: an inherited
    member reached from a subtype addresses the subtype's position. The wire
    keeps the DECLARING Entity either way. Tuple shapes precede the optional
    and generic single shapes, because a tuple also satisfies ``V | None`` and a
    bare ``T``; a Value Object Class's own members install
    :class:`ElementAttr` and type through the Value Object overloads.
    """

    __slots__ = ("_expression", "_index", "_member", "_ref", "_vo_shape")

    def __init__(
        self,
        ref: AttributeRef,
        index: int,
        member: AttributeMetadata | ValueObjectMetadata,
        vo_shape: ValueObjectShape | None = None,
    ) -> None:
        self._ref = ref
        self._index = index
        self._member = member
        self._vo_shape = vo_shape
        self._expression = _entity_member_expression(ref, member, vo_shape)

    def rebound(self, index: int) -> Attr[T]:
        """This member's descriptor, addressing ``index`` instead.

        A descendant declares members of its own after the ones it inherits, so a
        member's position is a fact about the exact class rather than about the
        family. Deriving the descendant's descriptor from the declaring class's
        own is what keeps the reference it hands out — which names the DECLARING
        Entity — the same one at every depth.
        """
        return Attr(self._ref, index, self._member, self._vo_shape)

    @overload
    def __get__[E: Entity, V: ValueObject](
        self: Attr[tuple[V, ...]], obj: None, owner: type[E], /
    ) -> AssignableManyValueObjectExpr[E, V]: ...
    @overload
    def __get__[E: Entity, S](
        self: Attr[tuple[S, ...]], obj: None, owner: type[E], /
    ) -> AssignableManyScalarExpr[E, S]: ...
    @overload
    def __get__[E: Entity, V: ValueObject](
        self: Attr[V | None], obj: None, owner: type[E], /
    ) -> AssignableValueObjectExpr[E, V | None]: ...
    @overload
    def __get__[E: Entity, V: ValueObject](
        self: Attr[V], obj: None, owner: type[E], /
    ) -> AssignableValueObjectExpr[E, V]: ...
    @overload
    def __get__[E: Entity](self, obj: None, owner: type[E], /) -> AssignableScalarExpr[E, T]: ...
    @overload
    def __get__[O: ValueObject, V: ValueObject](
        self: Attr[tuple[V, ...]], obj: None, owner: type[O], /
    ) -> ManyValueObjectExpr[O, V]: ...
    @overload
    def __get__[O: ValueObject, S](
        self: Attr[tuple[S, ...]], obj: None, owner: type[O], /
    ) -> ManyScalarExpr[O, S]: ...
    @overload
    def __get__[O: ValueObject, V: ValueObject](
        self: Attr[V | None], obj: None, owner: type[O], /
    ) -> ValueObjectExpr[O, V]: ...
    @overload
    def __get__[O: ValueObject, V: ValueObject](
        self: Attr[V], obj: None, owner: type[O], /
    ) -> ValueObjectExpr[O, V]: ...
    @overload
    def __get__[O: ValueObject](self, obj: None, owner: type[O], /) -> ScalarExpr[O, T]: ...
    @overload
    def __get__(self, obj: object, _owner: type | None = None, /) -> T: ...
    def __get__(self, obj: object | None, _owner: type | None = None) -> Any:
        if obj is None:
            return self._expression
        # As with `ElementAttr` below, Pydantic's own instance storage shadows
        # this branch on an ordinary value, so it answers exactly the values a
        # published one holds. The index is absolute and means nothing here: what
        # the row is laid out as belongs to the instance-state Module alone.
        # Reaching here on ordinary backing means the storage carries no such
        # member, which the empty slot reports as the missing attribute it is.
        try:
            value: T = object.__getattribute__(obj, COMPACT_STATE_SLOT)[self._index]
        except TypeError:
            raise AttributeError(_unstored(obj, self._index)) from None
        return value


def _entity_member_expression(
    ref: AttributeRef,
    member: AttributeMetadata | ValueObjectMetadata,
    vo_shape: ValueObjectShape | None,
) -> object:
    many = member.multiplicity is Multiplicity.MANY
    if isinstance(member, AttributeMetadata):
        if many:
            return AssignableManyScalarExpr[Any, Any](ref, member)
        return AssignableScalarExpr[Any, Any](ref, member)
    if vo_shape is None:  # pragma: no cover - every installed occurrence descriptor has its class
        raise ValueError(f"{ref}: a Value Object member descriptor needs its Value Object Class")
    if many:
        return AssignableManyValueObjectExpr[Any, Any](ref, member, vo_shape)
    return AssignableValueObjectExpr[Any, Any](ref, member, vo_shape)


class ElementAttr[T]:
    """A Value Object member's descriptor: class access yields a query-only
    expression relative to the element a quantifier binds, instance access
    yields the value.

    Its static type comes from the member's ``Attr`` annotation, whose Value
    Object overloads select the same expression families this answers.
    """

    __slots__ = ("_expression", "_index")

    def __init__(self, py_name: str, index: int, owner: ValueObjectShape) -> None:
        self._index = index
        self._expression = member_expression(
            AuthoredPath(ValueObjectReceiver(owner.shape), ()), owner, py_name
        )

    def __get__(self, obj: object | None, _owner: type | None = None) -> Any:
        if obj is None:
            return self._expression
        # A non-data descriptor, so Pydantic's own instance storage shadows
        # this branch on an ordinary value and it answers for a published one.
        try:
            value: T = object.__getattribute__(obj, COMPACT_STATE_SLOT)[self._index]
        except TypeError:
            raise AttributeError(_unstored(obj, self._index)) from None
        return value


class Rel[T]:
    """The relationship annotation, and the descriptor it installs.

    Class access yields a :class:`~parallax.core.entity._expressions.RelationshipExpr`
    for a single relationship and a
    :class:`~parallax.core.entity._expressions.ManyRelationshipExpr` for a
    collection; instance access yields the loaded value, or raises when the read
    that produced the node did not include it. A data descriptor, so the
    ``UNLOADED`` sentinel written through ``object.__setattr__`` still routes
    through :meth:`__get__`.

    ``target`` is the canonical spelling of the Entity this relationship points
    at, so a continuing Include hop keeps the namespace a local name would drop.

    The class-access overloads resolve the expression's target parameter to the
    relationship's ELEMENT type. Declaration order is load-bearing: overload
    resolution is first-match and a bare ``R`` unifies with anything, so the
    collection shape precedes the optional one, which precedes the catch-all.

    A subtype does not redeclare an inherited relationship, so class access
    through one reaches this same descriptor and keeps the one relationship
    identity. What the accessing class adds is the path's SOURCE — the Entity it
    was reached through — which an Object Query turns into a path-ROOT guard.
    """

    __slots__ = ("_index", "_many", "_py_name", "_ref", "_target")

    def __init__(
        self, ref: RelationshipRef, py_name: str, index: int, target: str, *, many: bool
    ) -> None:
        self._ref = ref
        self._py_name = py_name
        self._index = index
        self._target = target
        self._many = many

    def rebound(self, index: int) -> Rel[T]:
        """This relationship's descriptor, addressing ``index`` instead.

        A relationship position sits after the exact class's own member count, so
        no position survives inheritance and a descendant installs its own.
        """
        return Rel(self._ref, self._py_name, index, self._target, many=self._many)

    @overload
    def __get__[E, R](
        self: Rel[tuple[R, ...]], obj: None, owner: type[E], /
    ) -> ManyRelationshipExpr[E, R]: ...
    @overload
    def __get__[E, R](
        self: Rel[R | None], obj: None, owner: type[E], /
    ) -> RelationshipExpr[E, R]: ...
    @overload
    def __get__[E, R](self: Rel[R], obj: None, owner: type[E], /) -> RelationshipExpr[E, R]: ...
    @overload
    def __get__(self, obj: object, _owner: type | None = None, /) -> T: ...
    def __get__(self, obj: object | None, _owner: type | None = None) -> Any:
        if obj is None:
            hop = relationship_hop(
                self._ref, self._py_name, self._target, _access_source(_owner), many=self._many
            )
            if self._many:
                return ManyRelationshipExpr[Any, Any](hop)
            return RelationshipExpr[Any, Any](hop)
        try:
            value = object.__getattribute__(obj, COMPACT_STATE_SLOT)[self._index]
        except (AttributeError, TypeError):
            value = obj.__dict__.get(self._py_name, UNLOADED)
        if value is UNLOADED:
            raise UnloadedRelationshipError(self._ref.relationship)
        return value

    def __set__(self, obj: object, value: object) -> None:
        """Refused: a relationship position is written where the rest of a value's
        state is, and nowhere else.

        A published value's whole state is attached once, so a later write has
        nowhere truthful to land — the presentation it would reach is built per
        read and discarded with it, and the tail the next read consults would
        still hold the sentinel. So this is a refusal rather than a branch, and a
        caller that means to build a value builds it whole.
        """
        del value
        raise AttributeError(
            f"{type(obj).__name__}.{self._py_name}: a value's relationships are attached "
            "once, with the rest of its state"
        )


def _access_source(owner: type | None) -> str | None:
    """The canonical Entity spelling class access went THROUGH, or ``None`` for a
    bare descriptor invocation that names no class.

    The accessing class's own declared identity answers this, so this module
    resolves nothing and reaches no model: whether that Entity differs from the
    relationship's declaring one, and whether it narrows the queried position, are
    both decided later, where the query's own position is known. The spelling is
    exact because a path-root guard names a position it must resolve to one Entity.
    """
    canonical = getattr(getattr(owner, "identity", None), "canonical", None)
    return canonical if isinstance(canonical, str) else None


def _unstored(obj: object, index: int) -> str:
    """The message a member read gets when neither backing carries it.

    Reached only where ordinary storage was assigned without the member —
    validation-free construction missing a required one — because every other
    ordinary read is answered by the storage before this descriptor is consulted.
    An error path, so the member's own name is recovered from the class's plan
    rather than carried on every descriptor for the case that never happens.
    """
    name = next(
        (py_name for py_name, at in plan_of(type(obj)).indexes.items() if at == index),
        "?",
    )
    return f"{type(obj).__name__!r} object has no attribute {name!r}"
