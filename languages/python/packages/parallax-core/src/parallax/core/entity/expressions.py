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

Class-level ``Rel[T]`` access yields a :class:`RelationshipPath` (COR-3 Phase 7
increment 6a): the seed of the deep-fetch ``.include(...)`` spelling
(``Order.items.statuses``, deeper hops resolved dynamically via metamodel lookup),
the hop-level narrowed-view request (``.narrow(*subtypes)``), and the single-hop
relationship quantifiers (``.any(*predicates)`` / ``.none(*predicates)``,
serializing to ``exists`` / ``notExists``). ``ElementAttributeExpr`` is the
value-object CLASS-level access carrier (``Phone.type``): always builds
element-relative ``nested*`` nodes (no leading entity prefix), for use inside a
relationship or value-object quantifier's ``where=`` scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast, overload

from parallax.core.entity._relationship_scope import register_scope
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

    from parallax.core.entity.base import EntityRegistry

__all__ = [
    "UNLOADED",
    "Attr",
    "AttributeAssignment",
    "AttributeExpr",
    "AttributeRef",
    "ElementAttr",
    "ElementAttributeExpr",
    "Predicate",
    "Rel",
    "RelationshipPath",
    "RelationshipRef",
    "UnloadedRelationshipError",
    "and_terms",
    "conjoin",
]


class UnloadedRelationshipError(AttributeError):
    """A closed-world relationship (or narrowed view) was not fetched by the read
    that produced this node (spec §3): access raises, naming the path and the
    ``.include(...)`` fix rather than issuing lazy SQL."""

    def __init__(self, path: str) -> None:
        super().__init__(
            f"{path!r} was not included in this find; add `.include({path})` "
            "to fetch it (this snapshot lifecycle never lazy-loads)"
        )
        self.path = path


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
    """One typed ``_where``-verb assignment (``Attr.set(value)``, python.md §5):
    the entity-scoped spelling of a predicate-write assignment — the ``.set(...)``
    counterpart of ``model_copy(update={...})``'s dict-keyed spelling, built on
    the SAME attribute-expression surface a predicate is built on.

    This scope stays ``parallax.core.unit_work``-free (the
    ``parallax.core.entity ↛ parallax.core.unit_work`` import contract), so
    ``Transaction.update_where`` / ``.update_until_where``
    (``parallax.snapshot.handle``, already cleared to import both) translate
    this to the canonical ``~parallax.core.unit_work.WriteAssignment`` at the
    write boundary — never carried past this module as anything but a plain,
    ``Class.member``-addressed value pair.
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
    scope (relationship ``.any()``/``.none()``, value-object ``.any()``/
    ``.none()``, the whole-statement ``where(*predicates)``): a bare presence/
    absence test carries no interior ``where`` at all, one predicate needs no
    wrapper, and two or more flatten into one ``And`` exactly like
    ``build_statement``'s own combination — so the two conjunction sites can
    never drift."""
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

    __slots__ = ("_entity", "_head", "_path", "_registry")

    def __init__(
        self,
        entity: str,
        head: str,
        path: tuple[str, ...] = (),
        registry: EntityRegistry | None = None,
    ) -> None:
        self._entity = entity
        self._head = head
        self._path = path
        self._registry = registry

    @property
    def ref(self) -> AttributeRef:
        """The scalar attribute reference (only for a non-nested attribute)."""
        return AttributeRef(self._entity, self._head)

    def __getattr__(self, name: str) -> AttributeExpr:
        # A deeper value-object hop: Customer.address.city / .geo.country.
        if name.startswith("_"):
            raise AttributeError(name)
        return AttributeExpr(self._entity, self._head, (*self._path, name), self._registry)

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
        VALUE-OBJECT-TERMINATED path. Zero arguments emit the bare presence
        test; the interior predicates are built from the value object's own
        class-level (element-scoped) attributes, never re-prefixed."""
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
        """A set-based ``_where``-verb assignment (``Account.balance.set(0)``,
        python.md §5): only a TOP-LEVEL scalar attribute or value-object member
        is assignable — mirroring ``model_copy``'s own ``assignable_py``
        allow-list, never a NESTED value-object path (a value object always
        binds its WHOLE document, `m-value-object`; there is no sparse write
        below its boundary).

        A ``ValueObject`` instance (or a tuple of them, a ``many`` member) is
        serialized to its canonical document FIRST — the SAME translation
        ``full_row`` / ``canonical_row`` apply to every other write input —
        so this BUILD-TIME call then applies the SAME shared check the engine/
        serialized path applies to a case-authored predicate-write assignment
        (`~parallax.core.inheritance.validate_write_assignment`, the "one
        validator, two callers" pattern `python.md:667-676` / `m-case-
        format.md:700` require) to the IDENTICAL document-shaped value either
        caller ever sees: a primary-key or framework-owned (version) target is
        rejected — the SAME classification ``model_copy``'s own assignability
        guard uses (`~parallax.core.entity.base._validate_copy_keys`) — a
        scalar attribute's value must conform to its declared neutral type,
        and a value-object member's value must be a well-formed document
        against its declared composite (COR-3 Phase 8 confirmation-pass
        residual P3) — a non-document value (e.g. ``Customer.address.set(42)``)
        is rejected with the same wording style, never silently bound.
        """
        if self._path:
            raise TypeError(
                f"{self._dotted()}: only a top-level attribute or value-object member is "
                "assignable via .set(...) — a value object binds its whole document, never "
                "a nested path (m-value-object)"
            )
        from parallax.core import inheritance
        from parallax.core.entity.base import ModelCopyError, default_registry

        registry = self._registry if self._registry is not None else default_registry()
        meta = registry.metamodel()
        serialized = _serialize_assignment_value(value)
        try:
            inheritance.validate_write_assignment(
                meta, meta.entity(self._entity), self._head, serialized
            )
        except inheritance.WriteAssignmentError as exc:
            raise ModelCopyError(str(exc)) from exc
        return AttributeAssignment(attr=self.ref, value=serialized)

    def __bool__(self) -> bool:
        raise TypeError(_BOOL_HINT)

    def __hash__(self) -> int:  # pragma: no cover - expressions are not dict keys
        return hash((self._entity, self._head, self._path))


def _as_scalar(value: object) -> Scalar:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"expected a scalar literal, got {type(value).__name__}")


def _serialize_assignment_value(value: object) -> object:
    """A ``.set(...)`` assignment's write-serialized value: a ``ValueObject``
    instance becomes its canonical document, a tuple of them a list of
    documents (``cardinality: many``), everything else passes through
    unchanged — the SAME translation ``parallax.core.entity.base._serialize_member``
    applies to every other write input (a deferred import: ``entity.value_object``
    has no reverse edge onto this module, so this stays a plain sibling import)."""
    from parallax.core.entity.value_object import ValueObject, to_document

    if isinstance(value, ValueObject):
        return to_document(value)
    if isinstance(value, tuple):
        items = cast("tuple[object, ...]", value)
        return [to_document(item) if isinstance(item, ValueObject) else item for item in items]
    return value


class Attr[T]:
    """Typed attribute descriptor: class access → ``AttributeExpr``, instance → ``T``."""

    __slots__ = ("_py_name", "_ref", "_registry")

    def __init__(
        self, ref: AttributeRef, py_name: str, registry: EntityRegistry | None = None
    ) -> None:
        self._ref = ref
        self._py_name = py_name
        self._registry = registry

    @overload
    def __get__(self, obj: None, _owner: type, /) -> AttributeExpr: ...
    @overload
    def __get__(self, obj: object, _owner: type | None = None, /) -> T: ...
    def __get__(self, obj: object | None, _owner: type | None = None) -> AttributeExpr | T:
        if obj is None:
            return AttributeExpr(self._ref.entity, self._ref.attribute, registry=self._registry)
        value: T = obj.__dict__[self._py_name]
        return value


class ElementAttributeExpr:
    """A value-object CLASS-level attribute expression (``Phone.type``).

    Always builds ELEMENT-RELATIVE ``nested*`` nodes (no leading entity prefix,
    per python.md §2's value-object quantifier scope) — the class-level access
    carrier for a ``ValueObject`` subclass's own ``Attr[T]`` fields, used inside
    a relationship or value-object quantifier's ``where=``/interior predicates
    (``Phone.type == "home"`` inside ``.any(...)``). Deeper hops resolve
    dynamically via ``__getattr__`` (``Address.geo.country``), mirroring
    :class:`AttributeExpr`'s own dynamic value-object hop.
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


class ElementAttr[T]:
    """Typed value-object-class attribute descriptor: class access →
    ``ElementAttributeExpr``, instance → ``T`` (the ``ValueObject`` frontend's
    own field carrier — python.md §2's element-scoped expression surface)."""

    __slots__ = ("_canonical", "_py_name")

    def __init__(self, canonical: str, py_name: str) -> None:
        self._canonical = canonical
        self._py_name = py_name

    @overload
    def __get__(self, obj: None, _owner: type, /) -> ElementAttributeExpr: ...
    @overload
    def __get__(self, obj: object, _owner: type | None = None, /) -> T: ...
    def __get__(self, obj: object | None, _owner: type | None = None) -> ElementAttributeExpr | T:
        if obj is None:
            return ElementAttributeExpr((self._canonical,))
        # `ElementAttr` is a NON-data descriptor (no `__set__`, unlike `Rel[T]`'s
        # own data-descriptor fix): Pydantic's own instance `__dict__` always
        # shadows this branch for an ordinary field read, so it never actually
        # runs — kept only as the documented instance-access contract (a pure
        # passthrough with no sentinel translation to protect, unlike `Rel[T]`).
        value: T = obj.__dict__[self._py_name]  # pragma: no cover - shadowed by __dict__
        return value  # pragma: no cover


def _subtype_entity_name(subtype: type) -> str:
    """A subtype class's canonical entity name (falls back to the bare class
    name for a class this process has not compiled — defensive only)."""
    from parallax.core.entity.base import entity_record_of

    record = entity_record_of(subtype)
    return record.name if record is not None else subtype.__name__


@dataclass(frozen=True, slots=True, weakref_slot=True)
class RelationshipPath:
    """A chained class-level relationship reference (``Order.items``,
    ``Order.items.statuses``) — the seed of the ``.include(...)`` deep-fetch
    spelling, the hop-level ``.narrow(*subtypes)`` narrowed-view request, and
    the single-hop relationship quantifiers ``.any()``/``.none()``.

    ``segments`` is the traversal so far, in ``m-deep-fetch``'s own
    ``PathSegment`` shape (reused directly — no separate path vocabulary).
    ``target`` is the canonical entity name the path currently points AT (the
    last hop's related entity, or the narrowed subtype when the narrow resolves
    to exactly one) — resolved eagerly via the entity registry at each dynamic
    hop, since Python attribute access has no other place to look it up. The
    first hop is statically typed via the ``Rel[T]`` descriptor overload;
    deeper hops resolve dynamically through ``__getattr__``.

    ``weakref_slot=True`` (alongside ``slots=True``) lets
    ``parallax.core.entity._relationship_scope`` hold this instance's
    registered scope in an identity-keyed, GC-safe side table — the seam
    ``parallax.core.entity.graph_state`` reads this path's own captured
    registry through (COR-3 Phase 7 increment 7 round-4, P2), since a
    class-private field can never be read from outside this class's own
    methods, regardless of file or convention.
    """

    segments: tuple[PathSegment, ...]
    target: str
    # This path's own D-20 registration scope (captured at the FIRST hop, from
    # the owning ``Rel[T]`` descriptor; never a public field, mirroring
    # ``Statement._registry``): a dynamic hop and ``.narrow(...)`` both resolve
    # within it, never the process-global registry — and it is this SAME
    # captured scope (never ``type(node)``'s own, round-4 P2) that
    # ``graph_state``'s narrowed-view key derivation resolves a ``.narrow(...)``
    # position within, via ``_relationship_scope.register_scope`` below.
    # ``None`` only for a ``RelationshipPath`` built outside ``Rel.__get__``
    # (test-only direct construction) — falls back to the process default
    # registry.
    _registry: EntityRegistry | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        register_scope(self, self._registry)

    @property
    def ref(self) -> RelationshipRef:
        """The FIRST hop's relationship reference (mirrors ``AttributeExpr.ref``)."""
        owner, _, relationship = self.segments[0].rel.partition(".")
        return RelationshipRef(owner, relationship)

    def __getattr__(self, name: str) -> RelationshipPath:
        if name.startswith("_"):
            raise AttributeError(name)
        from parallax.core.entity.base import default_registry, snake_to_camel

        registry = self._registry if self._registry is not None else default_registry()
        canonical = snake_to_camel(name)
        record = registry.records().get(self.target)
        if record is None:
            raise AttributeError(
                f"{self.target!r} is not a registered Parallax entity class; import it "
                f"before chaining `.{name}`"
            )
        for relationship in record.relationships:
            if relationship.name == canonical:
                return RelationshipPath(
                    segments=(*self.segments, PathSegment(rel=f"{self.target}.{canonical}")),
                    target=relationship.related_entity,
                    _registry=registry,
                )
        raise AttributeError(f"{self.target!r} declares no relationship {canonical!r}")

    def narrow(self, *subtypes: type) -> RelationshipPath:
        """A hop-level narrowed-view request (``Owner.pets.narrow(Dog)``),
        continuable to a deeper hop. Requests the derived narrowed view
        (python.md §3), never marking the broad relationship loaded."""
        names = tuple(_subtype_entity_name(subtype) for subtype in subtypes)
        *head, last = self.segments
        new_last = PathSegment(rel=last.rel, narrow=names)
        new_target = names[0] if len(names) == 1 else self.target
        return RelationshipPath(
            segments=(*head, new_last), target=new_target, _registry=self._registry
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


class Rel[T]:
    """Typed relationship descriptor: class access → ``RelationshipPath``, instance → ``T``.

    ``related_entity`` is the declared relationship target (known at class-
    compile time), threaded straight onto the first hop's ``RelationshipPath``
    so a deeper dynamic hop (``.statuses``) resolves against it without a
    registry round trip for the FIRST hop.
    """

    __slots__ = ("_py_name", "_ref", "_registry", "_related_entity")

    def __init__(
        self,
        ref: RelationshipRef,
        py_name: str,
        related_entity: str,
        registry: EntityRegistry | None = None,
    ) -> None:
        self._ref = ref
        self._py_name = py_name
        self._related_entity = related_entity
        self._registry = registry

    @overload
    def __get__(self, obj: None, _owner: type, /) -> RelationshipPath: ...
    @overload
    def __get__(self, obj: object, _owner: type | None = None, /) -> T: ...
    def __get__(self, obj: object | None, _owner: type | None = None) -> RelationshipPath | T:
        if obj is None:
            return RelationshipPath(
                segments=(PathSegment(rel=str(self._ref)),),
                target=self._related_entity,
                _registry=self._registry,
            )
        value = obj.__dict__[self._py_name]
        if value is UNLOADED:
            raise UnloadedRelationshipError(self._ref.relationship)
        return value  # type: ignore[return-value]

    def __set__(self, obj: object, value: object) -> None:
        # A DATA descriptor (defines `__set__`) so instance attribute lookup
        # ALWAYS consults `__get__` — never shadowed by the instance `__dict__`
        # the way `Attr`'s non-data descriptor legitimately is. Without this,
        # the frozen-node wrapper's `UNLOADED` sentinel (set via the
        # `object.__setattr__` backdoor, which itself still honors the data-
        # descriptor protocol) would sit in `__dict__` and read back directly,
        # silently skipping the `UnloadedRelationshipError` check below.
        obj.__dict__[self._py_name] = value
