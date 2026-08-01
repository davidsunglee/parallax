"""The member authoring vocabulary and the installed class/instance descriptors.

``Attr[T]`` and ``Rel[T]`` are the only two member annotations; the assignment
slot optionally holds one ``attr(...)`` or exactly one ``rel(...)`` value.
``index(...)``, ``asc(...)``, and ``desc(...)`` complete the surface. Each
factory rejects an intrinsically invalid argument at the call itself, so a
malformed option never reaches class creation.

The same two names double as the installed descriptors: class access yields an
operation-node seed and instance access yields the member value. This is the
only module in the Entity cluster whose runtime behavior touches owner classes.
"""

from __future__ import annotations

from collections.abc import Sequence as _Sequence
from dataclasses import dataclass
from typing import Any, Final, overload

from parallax.core.base import FLOAT32, INT32, Float32, Int32, NeutralType
from parallax.core.entity._errors import EntityDefinitionError, UnloadedRelationshipError
from parallax.core.entity._expressions import (
    UNLOADED,
    AttributeExpr,
    AttributeRef,
    ElementAttributeExpr,
    RelationshipPath,
    RelationshipRef,
)
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
    NullPlacement,
    PersistenceMode,
    PrimaryKey,
    Sequence,
    SortDirection,
    TablePerHierarchy,
    ValueObjectMetadata,
)
from parallax.core.op_algebra import PathSegment

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
    "ElementAttr",
    "Float32",
    "IndexSpec",
    "InheritanceRole",
    "Int32",
    "OrderTerm",
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
    query-definition error family. An operation Sort Key
    (``op_algebra.OrderKey``) carries the same single-shot rule and does belong to
    that family, so it raises ``QueryDefinitionError`` instead; the two spellings
    differ because the surfaces do, not by accident.
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

    Class access yields an :class:`~parallax.core.entity._expressions.AttributeExpr`
    predicate seed carrying this member's own declared Metadata, which is every
    fact an assignment built from it is judged against; instance access yields
    the member value. A non-data descriptor, so Pydantic's instance ``__dict__``
    legitimately shadows the instance branch.

    The class-access overload parameterizes the expression by the class the
    access went THROUGH, not the one that declares the member: an inherited
    member reached from a subtype addresses the subtype's position, which is what
    makes an ancestor's member usable from a descendant position and a
    descendant's member unusable from an ancestor's. The wire keeps the DECLARING
    Entity either way, so a subtype spelling of an inherited member is the one
    composition the parameter refuses where the model would have accepted it —
    spell such a member through the class that declares it.
    """

    __slots__ = ("_member", "_py_name", "_ref")

    def __init__(
        self, ref: AttributeRef, py_name: str, member: AttributeMetadata | ValueObjectMetadata
    ) -> None:
        self._ref = ref
        self._py_name = py_name
        self._member = member

    @overload
    def __get__[E](self, obj: None, owner: type[E], /) -> AttributeExpr[E, T]: ...
    @overload
    def __get__(self, obj: object, _owner: type | None = None, /) -> T: ...
    def __get__(self, obj: object | None, _owner: type | None = None) -> AttributeExpr[Any, T] | T:
        if obj is None:
            return AttributeExpr(self._ref.entity, self._ref.attribute, member=self._member)
        # As with `ElementAttr` below, Pydantic's own instance `__dict__`
        # shadows this branch under ordinary attribute access; it is reached only
        # by invoking the descriptor directly, the documented instance-access
        # contract.
        value: T = obj.__dict__[self._py_name]
        return value


class ElementAttr[T]:
    """A Value Object member's descriptor: class access yields an element-scoped
    expression carrying no entity prefix, instance access yields the value.

    The class-access overload parameterizes the expression by the Value Object
    class the access went through, so an element predicate names the Value Object
    it addresses rather than an Entity.
    """

    __slots__ = ("_canonical", "_py_name")

    def __init__(self, canonical: str, py_name: str) -> None:
        self._canonical = canonical
        self._py_name = py_name

    @overload
    def __get__[V](self, obj: None, owner: type[V], /) -> ElementAttributeExpr[V, T]: ...
    @overload
    def __get__(self, obj: object, _owner: type | None = None, /) -> T: ...
    def __get__(
        self, obj: object | None, _owner: type | None = None
    ) -> ElementAttributeExpr[Any, T] | T:
        if obj is None:
            return ElementAttributeExpr((self._canonical,))
        # A non-data descriptor, so Pydantic's own instance `__dict__` shadows
        # this branch under ordinary attribute access; it is reached only by
        # invoking the descriptor directly.
        value: T = obj.__dict__[self._py_name]
        return value


class Rel[T]:
    """The relationship annotation, and the descriptor it installs.

    Class access yields a :class:`~parallax.core.entity._expressions.RelationshipPath`;
    instance access yields the loaded value, or raises when the read that
    produced the node did not include it. A data descriptor, so the ``UNLOADED``
    sentinel written through ``object.__setattr__`` still routes through
    :meth:`__get__`.

    ``target`` is the canonical spelling of the Entity this relationship points
    at, so a continuing hop keeps the namespace a local name would drop.

    A subtype does not redeclare an inherited relationship, so class access
    through one (``Dog.owner`` where ``Animal`` declares ``owner``) reaches this
    same descriptor and keeps the one relationship identity ``Animal.owner``. What
    the accessing class adds is the path's SOURCE — the Entity it was reached
    through — which a Find Query turns into a path-ROOT guard. The source is
    recorded for every access, including one through the declaring class itself
    (``Dog.doghouse``, declared on ``Dog``), because whether it guards anything is a
    question about the QUERIED position, which only the Find Query knows.
    """

    __slots__ = ("_py_name", "_ref", "_target")

    def __init__(self, ref: RelationshipRef, py_name: str, target: str) -> None:
        self._ref = ref
        self._py_name = py_name
        self._target = target

    @overload
    def __get__(self, obj: None, _owner: type, /) -> RelationshipPath: ...
    @overload
    def __get__(self, obj: object, _owner: type | None = None, /) -> T: ...
    def __get__(self, obj: object | None, _owner: type | None = None) -> RelationshipPath | T:
        if obj is None:
            return RelationshipPath(
                segments=(PathSegment(rel=str(self._ref)),),
                target=self._target,
                source=_access_source(_owner),
            )
        value = obj.__dict__[self._py_name]
        if value is UNLOADED:
            raise UnloadedRelationshipError(self._ref.relationship)
        return value

    def __set__(self, obj: object, value: object) -> None:
        obj.__dict__[self._py_name] = value


def _access_source(owner: type | None) -> str | None:
    """The declared Entity name class access went THROUGH, or ``None`` for a bare
    descriptor invocation that names no class.

    The accessing class's own declared identity answers this, so this module
    resolves nothing and reaches no model: whether that Entity differs from the
    relationship's declaring one, and whether it narrows the queried position, are
    both decided later, where the query's own position is known.
    """
    name = getattr(getattr(owner, "identity", None), "name", None)
    return name if isinstance(name, str) else None
