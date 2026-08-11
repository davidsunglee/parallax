"""The Entity class frontend (spec §2).

An Entity Class is an implicitly frozen Pydantic model whose class statement
carries the model's mapping facts and whose body carries its members. The
metaclass is thin: it types the seven header keywords, rejects every other one, and
hands the class body to the shared declaration engine.

Because the engine builds the declaration payload eagerly, an Entity Class *is*
its own ``UnresolvedEntityDeclaration``: the metaclass publishes the ten
declaration members on the class object, so a Domain Model composes classes
directly with
no adapter and no mirrored record graph.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Self, cast

from pydantic import BaseModel
from pydantic._internal._model_construction import ModelMetaclass

from parallax.core.entity._declaration import (
    DECLARATION_MEMBER_NAMES as _DECLARATION_MEMBERS,
)
from parallax.core.entity._declaration import (
    FRAMEWORK_MINT,
    DeclarationKind,
    EntityHeader,
    build_class,
    declaration_of,
    members_of,
)
from parallax.core.entity._errors import EditError, EditViolation, EntityDefinitionError
from parallax.core.entity._expressions import (
    AllPredicate,
    Predicate,
    judged_edit_violation,
    serialize_member,
)
from parallax.core.entity._members import Attr, Document, IndexSpec, InheritanceRole
from parallax.core.entity._query import FindQuery, build_find_query
from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeMetadata,
    EntityIdentity,
    EntityLocation,
    IndexMetadata,
    PersistenceMode,
    RelationshipIdentity,
    RelationshipLocation,
    StorageContainer,
    StorageLayout,
    TemporalDimension,
    UnresolvedInheritance,
    UnresolvedRelationshipDeclaration,
    ValueObjectMetadata,
    ValueObjectOccurrenceDeclaration,
)
from parallax.core.predicate import All, Narrow, PredicateNode, QueryDefinitionError
from parallax.core.predicate._nodes import canonical_subtype_selection

if TYPE_CHECKING:
    import datetime as _dt

    from parallax.core.entity._members import AbstractSubtype, ConcreteSubtype

__all__ = [
    "CHANGE_RECORD_SLOT",
    "Bitemporal",
    "Entity",
    "EntityMeta",
    "TxTemporal",
    "WireNames",
    "wire_names_of",
]


class _All:
    """The ``Entity.all`` descriptor: class access yields the explicitly
    unfiltered query over the accessing class's own position.

    It lives in ``Entity``'s class body rather than on ``EntityMeta``, and that
    placement is the whole point. A type checker resolving a member through
    ``type[...]`` reads the metaclass declaration itself and does not apply the
    descriptor protocol to it, so a metaclass spelling would answer correctly at
    a literal class reference and silently lose the Entity parameter the moment
    the class arrived through a type variable — which is exactly where a generic
    helper over Entity Classes needs it.

    Only class access is spelled: an instance is already the single row it is,
    so ``instance.all`` names nothing and the signature refuses it.
    """

    __slots__ = ()

    def __get__[E](self, obj: None, owner: type[E], /) -> AllPredicate[E]:
        return AllPredicate(All())


class EntityMeta(ModelMetaclass):
    """The Entity metaclass: typed class-header keywords over the shared engine.

    The positionals are ``cls_name``/``bases``/``ns`` and positional-only,
    because ``name=`` and ``namespace=`` are header keywords and a parameter
    cannot be spelled twice. Nothing is forwarded to Pydantic, so a Pydantic
    configuration keyword such as ``frozen=True`` is rejected as an unknown
    header option rather than silently accepted; the engine sets ``frozen=True``
    itself.

    The ten annotations below are the ``UnresolvedEntityDeclaration`` surface,
    published on the class object so an Entity Class needs no adapter. They
    declare types without binding values: the hidden ``__getattr__`` serves each
    read from the class's own eagerly built declaration, and instances stay
    unaffected because the members live on the metaclass. Declaring them rather
    than writing ten properties is what makes ``type[SomeEntity]`` *statically*
    satisfy the protocol — a type checker resolving a member through
    ``type[...]`` reads the metaclass declaration itself and does not apply the
    descriptor protocol to a metaclass ``property``.
    """

    identity: EntityIdentity
    """This Entity's canonical model-wide identity."""
    container: StorageContainer | None
    """This Entity's declared physical container, if it declares one."""
    persistence: PersistenceMode | None
    """The Persistence Mode this Entity itself declares, if any."""
    layout: StorageLayout | None
    """The Storage Layout this Entity itself declares, if any."""
    attributes: Sequence[AttributeMetadata]
    """This Entity's own scalar Attributes, in declaration order."""
    relationships: Sequence[UnresolvedRelationshipDeclaration]
    """This Entity's own relationship declarations, in declaration order."""
    value_objects: Sequence[ValueObjectOccurrenceDeclaration]
    """This Entity's own top-level Value Object occurrences."""
    as_of_axes: Sequence[AsOfAxisMetadata]
    """The temporal axes this Entity itself owns; empty below a family root."""
    inheritance: UnresolvedInheritance | None
    """This Entity's inheritance position, or ``None`` when standalone."""
    indices: Sequence[IndexMetadata]
    """This Entity's own local indices; indices are never inherited."""

    if not TYPE_CHECKING:
        # Hidden from type checkers on Pydantic's own reasoning for the same
        # construct: a visible catch-all would legalize arbitrary attribute
        # access on every Entity Class and silence real typos. A class carrying
        # no declaration — a framework root — is refused by `declaration_of`.

        def __getattr__(cls, name):
            if name in _DECLARATION_MEMBERS:
                return getattr(declaration_of(cls), name)
            return super().__getattr__(name)

    def __new__(
        mcs,
        cls_name: str,
        bases: tuple[type, ...],
        ns: dict[str, Any],
        /,
        *,
        table: str | None = None,
        name: str | None = None,
        namespace: str | None = None,
        persistence: PersistenceMode | None = None,
        layout: Document | type[Document] | None = None,
        inheritance: InheritanceRole | type[AbstractSubtype] | type[ConcreteSubtype] | None = None,
        indices: tuple[IndexSpec, ...] = (),
        _mint: object | None = None,
        _axes: tuple[TemporalDimension, ...] = (),
        **unknown: object,
    ) -> type:
        if unknown:
            raise EntityDefinitionError(
                code="entity-header-unknown-option",
                message=(
                    f"{cls_name}: unknown class-header option(s) {', '.join(sorted(unknown))}"
                ),
            )
        return build_class(
            mcs,
            cls_name,
            bases,
            cast("dict[str, object]", ns),
            kind=DeclarationKind.ENTITY,
            mint=_mint,
            axes=_axes,
            header=EntityHeader(table, name, namespace, persistence, layout, inheritance, indices),
            # `Entity.all` is a class-body descriptor, which Pydantic's own
            # namespace inspection would otherwise refuse as an unannotated
            # field the moment `Entity` itself is created.
            ignored_types=(_All,),
        )


@dataclass(frozen=True, slots=True)
class WireNames:
    """One Entity Class's family-merged Python-name correspondences.

    Built from the same declaration walk the model facts are built from, so the
    two can never drift. A family member's maps include every Parallax ancestor's
    declared members, merged base-first so a descendant's own declaration wins.
    """

    column_to_py: dict[str, str]
    name_to_py: dict[str, str]
    py_to_name: dict[str, str]
    relationship_py: dict[str, str]
    relationship_identities: dict[str, RelationshipIdentity]
    """Each Python relationship name to the Identity its own declaration built,
    so an inherited relationship keeps the declaring Entity a descendant reaches
    it through cannot supply."""
    members: dict[str, AttributeMetadata | ValueObjectMetadata]
    """Each Python member name to the accepted Metadata that decides what may be
    written to it. Which members are assignable is not recorded here as a name
    set: that is :func:`~parallax.core.metamodel.judge_assignment`'s verdict, and
    a second spelling of it here is exactly the drift the single judgement
    exists to prevent."""
    pk_py: frozenset[str]
    vo_classes: dict[str, type]

    @property
    def framework_owned_py(self) -> frozenset[str]:
        """The members whose values the framework supplies and the caller never
        authors, read off :attr:`members` rather than recorded beside it — one
        designation, projected where a Python-name question needs it."""
        return frozenset(
            py_name
            for py_name, member in self.members.items()
            if isinstance(member, AttributeMetadata) and member.framework_owned
        )


def wire_names_of(cls: type) -> WireNames:
    """The MRO-merged member correspondences of an Entity Class."""
    column_to_py: dict[str, str] = {}
    name_to_py: dict[str, str] = {}
    py_to_name: dict[str, str] = {}
    relationship_py: dict[str, str] = {}
    relationship_identities: dict[str, RelationshipIdentity] = {}
    members: dict[str, AttributeMetadata | ValueObjectMetadata] = {}
    pk_py: set[str] = set()
    vo_classes: dict[str, type] = {}
    declared = False
    for ancestor in reversed(cls.__mro__):
        if "__parallax_members__" not in ancestor.__dict__:
            continue
        declared = True
        names = members_of(ancestor)
        column_to_py.update(names.column_to_py)
        name_to_py.update(names.name_to_py)
        py_to_name.update(names.py_to_name)
        relationship_py.update(names.relationship_py)
        relationship_identities.update(
            {
                names.relationship_py[declaration.identity.name]: declaration.identity
                for declaration in declaration_of(ancestor).relationships
            }
        )
        members.update(names.members)
        pk_py.update(names.pk_py)
        vo_classes.update(names.vo_classes)
    if not declared:
        raise EntityDefinitionError(
            code="entity-base-invalid", message=f"{cls!r} is not a Parallax Entity Class"
        )
    return WireNames(
        column_to_py=column_to_py,
        name_to_py=name_to_py,
        py_to_name=py_to_name,
        relationship_py=relationship_py,
        relationship_identities=relationship_identities,
        members=members,
        pk_py=frozenset(pk_py),
        vo_classes=vo_classes,
    )


def _family_axes(cls: type) -> tuple[AsOfAxisMetadata, ...]:
    """The temporal axes governing ``cls``.

    Temporality is family-wide and root-owned, so a descendant reads its root's
    axes: the nearest ancestor that declares any.
    """
    for ancestor in cls.__mro__:
        if "__parallax_declaration__" not in ancestor.__dict__:
            continue
        axes = declaration_of(ancestor).as_of_axes
        if axes:
            return axes
    return ()


CHANGE_RECORD_SLOT: Final = "__parallax_changes__"
"""The one private instance slot an Edited Copy's Change Record lives in.

Only :meth:`Entity.edit` ever writes it, and the Entity Row Codec is its only
reader. It lives in ``__dict__`` rather than in a declared field so it stays
outside ``model_fields_set``, outside canonical serialization, and outside the
declared model — which is also why every inherited copy door that shallow-copies
that dictionary is refused."""


def _change_record(value: object) -> dict[str, object] | None:
    """``value``'s Change Record, or ``None`` when it carries none.

    The edit surface's own reader: it needs only the record it will extend, and
    an unedited value extends an empty one. Telling an absent record apart from
    an unreadable one is the Row Codec's question, not this one's.
    """
    record = value.__dict__.get(CHANGE_RECORD_SLOT)
    return cast("dict[str, object]", record) if isinstance(record, dict) else None


def _edit_violations(
    entity: EntityIdentity, cls_name: str, names: WireNames, changes: Mapping[str, object]
) -> tuple[EditViolation, ...]:
    """Every rule the authored ``changes`` break, one per named member (spec §3).

    The split is by what each half can know. Resolving a Python name to a member
    is a class-shaped question and is answered here: a relationship member and an
    undeclared name never reach a member at all, and each contributes its
    resolution violation instead of a judgement. Everything a resolved member
    then decides — primary-key, read-only, and framework-owned targets, in that
    order, plus declared-type and nullability conformance — is
    :func:`~parallax.core.metamodel.judge_assignment`'s single verdict, the SAME
    one ``Attr.set(...)`` and the serialized write boundary reach, so an edited
    value and a write can never disagree about what may be assigned.

    Every named member is examined and contributes at most one violation, so a
    caller correcting several mistakes learns all of them at once rather than one
    round trip at a time.

    A resolved member locates at the Identity its own declaration built, so an
    inherited member reports where it was declared rather than at the subtype the
    name was searched through; ``entity`` locates only the name that resolved to
    no member at all, which no declaration can name.

    A Value Object value is rendered to its canonical document before it is
    judged, exactly as ``.set(...)`` renders it, so both paths judge one shape;
    the edit itself still merges the caller's own live value.
    """
    violations: list[EditViolation] = []
    for py_name, value in changes.items():
        relationship = names.relationship_identities.get(py_name)
        if relationship is not None:
            violations.append(
                EditViolation(
                    code="edit-relationship-member",
                    location=RelationshipLocation(relationship),
                    member_name=relationship.name,
                    message=(
                        f"{cls_name}.{py_name}: relationship members are not assignable via "
                        "edit(...) (no cascade or association-mutation semantics to lower it to)"
                    ),
                )
            )
            continue
        member = names.members.get(py_name)
        if member is None:
            violations.append(
                EditViolation(
                    code="edit-unknown-member",
                    location=EntityLocation(entity),
                    member_name=py_name,
                    message=f"{cls_name}.{py_name}: unknown member name",
                )
            )
            continue
        violation = judged_edit_violation(member, serialize_member(value), owner=entity.canonical)
        if violation is not None:
            violations.append(violation)
    return tuple(violations)


_UNBOUND: Final = object()
"""Distinguishes a class that binds a name to ``None`` from one that binds it not
at all."""


def _is_derived_cache(cls: type, key: str) -> bool:
    """Whether ``cls`` declares the instance slot ``key`` a derived cache.

    A ``functools.cached_property`` memoizes an answer computed from the value it
    was read through, so the class itself declares that slot derived and the rule
    needs no registry. The first ancestor that binds the name decides, exactly as
    attribute lookup would, so a subtype that rebinds the name to something else
    is not taken to have inherited the declaration.
    """
    for ancestor in cls.__mro__:
        attribute = ancestor.__dict__.get(key, _UNBOUND)
        if attribute is not _UNBOUND:
            return isinstance(attribute, functools.cached_property)
    return False


def _partition_declared(
    value: Entity, names: WireNames
) -> tuple[dict[str, object], dict[str, object]]:
    """``value``'s declared member state and everything an edit carries, split.

    An edit replaces the first half and preserves the second unchanged, which is
    what keeps a materialized node's relationship views and lifecycle state
    readable on the copy it derives. The second half is a complement rather than
    an enumerated slot list, so a new kind of instance state travels correctly
    without either caller learning its name.

    A derived cache is the one thing that complement drops: a slot the class
    declares a ``functools.cached_property`` (:func:`_is_derived_cache`) holds an
    answer computed from declared state an edit may replace, so it is left out
    and recomputed on next access rather than carried into a copy whose own
    declared state contradicts it. That reads a declaration, so it reaches only
    names a declaration may author: the framework's own ``__parallax_`` prefix is
    reserved from every class body, which is what keeps a lifecycle's state and a
    Change Record outside anything a class can declare derived.

    Both branches of :meth:`Entity.edit` partition here, so neither can hold its
    own opinion of the boundary.
    """
    declared_names = set(names.py_to_name)
    declared_state: dict[str, object] = {}
    carried: dict[str, object] = {}
    for key, member in value.__dict__.items():
        if key in declared_names:
            declared_state[key] = member
        elif not _is_derived_cache(type(value), key):
            carried[key] = member
    return declared_state, carried


def _restate[E: Entity](
    value: E,
    declared_state: dict[str, object],
    carried: dict[str, object],
    record: dict[str, object],
) -> E:
    """A fresh value holding exactly ``value``'s state under ``record``.

    An edit that authors nothing validates nothing, so it builds through the
    validation-free construction path materialization already uses rather than
    through the constructor — which is also the only path left once every
    inherited copy door is refused.
    """
    restated = type(value).model_construct()
    object.__setattr__(restated, "__dict__", declared_state | carried)
    object.__setattr__(restated, "__pydantic_fields_set__", set(value.__pydantic_fields_set__))
    object.__setattr__(restated, CHANGE_RECORD_SLOT, record)
    return restated


def _use_edit(cls: type, door: str) -> EditError:
    """The refusal of an inherited copy path (spec §3).

    It examines no argument and names no member, so it locates at the Entity
    whose value was copied and carries no member name.
    """
    return EditError(
        [
            EditViolation(
                code="edit-use-edit",
                location=EntityLocation(declaration_of(cls).identity),
                message=(
                    f"{cls.__name__}.{door}(...) creates no value: derive an edited copy with "
                    "`value.edit(**changes)`, the one door that judges every assignment and "
                    "records what it touched"
                ),
            )
        ]
    )


class Entity(BaseModel, metaclass=EntityMeta, _mint=FRAMEWORK_MINT):
    """The frozen base every Parallax Entity Class extends."""

    all = _All()
    """The explicitly unfiltered query over this Entity (``Animal.all``).

    A distinct type from a Predicate, carrying no boolean operators: an
    unfiltered query is the whole filter or it is not the filter at all.
    """

    @classmethod
    def where[E: Entity](
        cls: type[E], first: Predicate[E] | AllPredicate[E], /, *rest: Predicate[E]
    ) -> FindQuery[E, E]:
        """Build a side-effect-free Find Query conjoining its predicates.

        At least one predicate is required, so an accidentally empty argument
        list is a mistake rather than a find-all; ``where(Entity.all)`` is the
        explicitly unfiltered spelling. The unfiltered value is the whole filter
        or none of it: only the first parameter admits it, and combining it with
        a term is refused whichever position it is written in.

        Each predicate is measured against the queried position twice. The
        parameter measures it before anything runs — a Predicate is
        contravariant, so an ancestor's predicate addresses this position and a
        descendant's does not — and the model-aware validator measures it again
        at execution preflight, which is what covers the wire path and any
        untyped caller.

        Authoring reaches no model, so a class composed into no model at all is
        as queryable as any other: the query simply has no connected model to be
        executed against yet, and a Database refuses one whose target it does not
        declare.

        An inheritance participant's temporal axes resolve through its family
        root, so a concrete subtype accepts its inherited axis spelling even
        though its own declaration carries no axis.
        """
        return build_find_query(cls.identity, (first, *rest), as_of_axes=_family_axes(cls))

    @classmethod
    def narrow[E: Entity, S: Entity](
        cls: type[E], *subtypes: type[S], where: Predicate[S] | None = None
    ) -> Predicate[E]:
        """The scoped subtype-narrowing constructor (spec §2).

        ``to`` is canonicalized as one Subtype Selection, and ``where=`` grants
        attribute scope to those subtypes' declared members inside its own operand
        alone. An ordinary predicate: it composes like any other, and inside a
        relationship quantifier it must name exactly the relationship target.

        The narrowed predicate addresses the narrowing class's own position — the
        sanctioned way to reach a descendant's member from an ancestor position —
        so the ``where=`` scope is the one place a subtype's predicate legitimately
        lands in an ancestor's query.

        ``S`` is solved from the named subtypes and is what the scoped predicate
        is measured against, so a ``where=`` addressing a position outside the
        narrowed set is refused before anything runs, while the answer stays in
        the narrowing class's own position. Whether the named classes are
        subtypes of that position at all is NOT stated here: a type parameter's
        bound may not itself be generic, so ``S`` cannot be bounded by ``E``, and
        a class outside the position keeps only its preflight rejection
        (``narrow-outside-position``) — as does the per-model question of which
        concrete subtypes the named classes resolve to.
        """
        to = tuple(declaration_of(subtype).identity.canonical for subtype in subtypes)
        if not to:
            raise QueryDefinitionError(
                code="query-path-invalid", message="narrow requires at least one subtype"
            )
        if len(set(to)) != len(to):
            raise QueryDefinitionError(
                code="query-path-invalid",
                message="narrow alternatives must not repeat the same subtype",
            )
        operand: PredicateNode = where.node if where is not None else All()
        return Predicate(Narrow(to=canonical_subtype_selection(to), operand=operand))

    def edit(self, **changes: object) -> Self:
        """The one door to an Edited Copy (spec §3).

        The result carries a Change Record mapping each touched member to its
        earliest original across edit chains. ``changes`` is validated: every
        named member is resolved and judged by the SAME assignment rules
        ``Attr.set(...)`` and the serialized write boundary apply
        (:func:`_edit_violations`), every violation is reported in one
        :class:`EditError` raised before anything is built, and the merged
        instance then goes back through the ordinary constructor for the §2 input
        policies — whose own ``ValidationError`` propagates unchanged, because a
        value the judgement accepted and the annotation refused is a judgement
        coverage defect rather than a developer-input refusal.

        An edit replaces declared member state and preserves everything it
        neither replaces nor invalidates (:func:`_partition_declared`), whichever
        branch builds the result. A materialized node's relationship views and
        its lifecycle state therefore reach the copy intact, so the copy answers
        a relationship and the lifecycle's own inspection surface exactly as the
        node did — and carries that node's as-of pin, which is what makes a view
        pinned in the Transaction-Time past read-only through an edit as well as
        directly.

        A carried view keeps describing what the read observed, which is all an
        edit can leave it describing: a relationship keyword is refused outright,
        so no edit changes a relationship member, and a view can only come from a
        read, so nothing here re-resolves one offline. A copy that authors a join
        endpoint therefore carries a view describing the pre-edit target, and a
        view of the new one is obtained by reading.

        An edit with no changes is legal and builds nothing new to validate,
        because nothing was authored: the result is this value's own state and
        its own record, whose effective change set is empty either way.

        A framework-owned member is carried forward without re-validation: its
        value was never authored, so re-running it through the constructor would
        submit stored state as a caller assignment — which that constructor
        refuses — and a materialized current milestone's endpoint there is the
        framework's open-interval sentinel, which the wrapping construction never
        validated either. ``changes`` cannot name one: the shared judgement
        refuses it before any merge.
        """
        record = dict(_change_record(self) or {})
        names = wire_names_of(type(self))
        declared_state, carried = _partition_declared(self, names)
        if not changes:
            return _restate(self, declared_state, carried, record)
        entity = declaration_of(type(self)).identity
        violations = _edit_violations(entity, type(self).__name__, names, changes)
        if violations:
            raise EditError(violations) from None
        declared_state.update(changes)
        carry_forward = {
            py_name: declared_state.pop(py_name)
            for py_name in names.framework_owned_py
            if py_name in declared_state
        }
        # re-validates the whole instance (§2 input policies)
        validated = type(self)(**declared_state)
        for py_name, value in carry_forward.items():
            object.__setattr__(validated, py_name, value)
        for py_name, member in carried.items():
            object.__setattr__(validated, py_name, member)
        for py_name in changes:
            if py_name not in record:
                record[py_name] = getattr(self, py_name)
        object.__setattr__(validated, CHANGE_RECORD_SLOT, record)
        return validated

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        """Refused: ``edit(**changes)`` is the object-copy verb (spec §3).

        Pydantic's own signature has no place to put an edit's contract —
        ``deep=True`` on a frozen value carrying a Change Record has no defined
        meaning — and the name promises Pydantic semantics this class does not
        keep. Refused with or without ``update=``, before any argument is
        examined.
        """
        del update, deep
        raise _use_edit(type(self), "model_copy") from None

    def copy(self, **kwargs: object) -> Self:
        """Refused: the deprecated Pydantic v1 shim reaches neither the
        framework's name resolution nor its judgement, so a primary key or a
        framework-owned member could be set through it (spec §3)."""
        del kwargs
        raise _use_edit(type(self), "copy") from None

    def __copy__(self) -> Self:
        """Refused: a shallow copy of the instance dictionary carries the Change
        Record living in it, so the result would claim provenance it did not earn
        and lower to a sparse row built from originals that were never its own
        (spec §3)."""
        raise _use_edit(type(self), "__copy__") from None

    def __deepcopy__(self, memo: dict[int, Any] | None = None) -> Self:
        """Refused for :meth:`__copy__`'s reason, plus deep-copied originals."""
        del memo
        raise _use_edit(type(self), "__deepcopy__") from None


class TxTemporal(Entity, _mint=FRAMEWORK_MINT, _axes=(TemporalDimension.TRANSACTION_TIME,)):
    """The Transaction-Time-only framework base.

    Extending it declares the Entity's temporal shape with no temporal
    boilerplate: the engine supplies the reserved ``tx_start``/``tx_end`` members
    over the stable ``in_z``/``out_z`` columns, plus the axis metadata. Temporal
    shape is family-wide and root-owned, so a descendant inherits it rather than
    extending this base again.
    """

    if TYPE_CHECKING:
        # The static mirror of the engine-supplied members: the runtime fields and
        # descriptors are installed on each shape owner, invisibly to a type
        # checker. Never executed, so the inert root itself declares nothing.
        tx_start: Attr[_dt.datetime]
        tx_end: Attr[_dt.datetime]


class Bitemporal(
    Entity,
    _mint=FRAMEWORK_MINT,
    _axes=(TemporalDimension.VALID_TIME, TemporalDimension.TRANSACTION_TIME),
):
    """The bitemporal framework base.

    Extending it supplies ``valid_start``/``valid_end`` (``from_z``/``thru_z``)
    and ``tx_start``/``tx_end`` (``in_z``/``out_z``), Valid Time first, plus both
    axes' metadata.
    """

    if TYPE_CHECKING:
        # The static mirror of the engine-supplied members (see `TxTemporal`).
        valid_start: Attr[_dt.datetime]
        valid_end: Attr[_dt.datetime]
        tx_start: Attr[_dt.datetime]
        tx_end: Attr[_dt.datetime]
