"""The Entity class frontend (spec §2).

An Entity Class is an implicitly frozen Pydantic model whose class statement
carries the model's mapping facts and whose body carries its members. The
metaclass is thin: it types the six header keywords, rejects every other one, and
hands the class body to the shared declaration engine.

Because the engine builds the declaration payload eagerly, an Entity Class *is*
its own ``UnresolvedEntityDeclaration``: the metaclass publishes the nine
declaration members on the class object, so a Domain Model composes classes
directly with
no adapter and no mirrored record graph.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self, cast

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
from parallax.core.entity._errors import (
    EntityDefinitionError,
    FrameworkOwnedAxisError,
    ModelCopyError,
    ProvenanceError,
)
from parallax.core.entity._expressions import AllPredicate, Predicate, serialize_member
from parallax.core.entity._members import Attr, IndexSpec, InheritanceRole
from parallax.core.entity.statement import Statement, build_statement
from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeMetadata,
    EntityIdentity,
    IndexMetadata,
    PersistenceMode,
    StorageContainer,
    TemporalDimension,
    UnresolvedInheritance,
    UnresolvedRelationshipDeclaration,
    ValueObjectMetadata,
    ValueObjectOccurrenceDeclaration,
    WriteAssignmentError,
    judge_assignment,
)
from parallax.core.op_algebra import All, Narrow, Operation

if TYPE_CHECKING:
    import datetime as _dt

    from parallax.core.entity._members import AbstractSubtype, ConcreteSubtype

__all__ = [
    "Bitemporal",
    "Entity",
    "EntityMeta",
    "TxTemporal",
    "WireNames",
    "canonical_row",
    "changed_fields",
    "effective_change_set",
    "full_row",
    "primary_key_row",
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

    The nine annotations below are the ``UnresolvedEntityDeclaration`` surface,
    published on the class object so an Entity Class needs no adapter. They
    declare types without binding values: the hidden ``__getattr__`` serves each
    read from the class's own eagerly built declaration, and instances stay
    unaffected because the members live on the metaclass. Declaring them rather
    than writing nine properties is what makes ``type[SomeEntity]`` *statically*
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
            header=EntityHeader(table, name, namespace, persistence, inheritance, indices),
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
    members: dict[str, AttributeMetadata | ValueObjectMetadata]
    """Each Python member name to the accepted Metadata that decides what may be
    written to it. Which members are assignable is not recorded here as a name
    set: that is :func:`~parallax.core.metamodel.judge_assignment`'s verdict, and
    a second spelling of it here is exactly the drift the single judgement
    exists to prevent."""
    pk_py: frozenset[str]
    framework_owned_py: frozenset[str]
    axis_governed_py: frozenset[str]
    vo_classes: dict[str, type]


def wire_names_of(cls: type) -> WireNames:
    """The MRO-merged member correspondences of an Entity Class."""
    column_to_py: dict[str, str] = {}
    name_to_py: dict[str, str] = {}
    py_to_name: dict[str, str] = {}
    relationship_py: dict[str, str] = {}
    members: dict[str, AttributeMetadata | ValueObjectMetadata] = {}
    pk_py: set[str] = set()
    framework_owned_py: set[str] = set()
    axis_governed_py: set[str] = set()
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
        members.update(names.members)
        pk_py.update(names.pk_py)
        framework_owned_py.update(names.framework_owned_py)
        axis_governed_py.update(names.axis_governed_py)
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
        members=members,
        pk_py=frozenset(pk_py),
        framework_owned_py=frozenset(framework_owned_py),
        axis_governed_py=frozenset(axis_governed_py),
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


def full_row(instance: Entity) -> dict[str, object]:
    """Every member of ``instance`` the caller actually set, keyed by canonical name.

    Filtered by Pydantic's ``model_fields_set`` rather than by the declared
    member set, so a member the caller never populated is omitted and the
    narrower insert is emitted. Raises :class:`FrameworkOwnedAxisError` when the
    caller set an axis-governed attribute, before the row is built.
    """
    names = wire_names_of(type(instance))
    fields_set = instance.model_fields_set
    supplied = sorted(names.axis_governed_py & fields_set)
    if supplied:
        py_name = supplied[0]
        raise FrameworkOwnedAxisError(
            f"{type(instance).__name__}.{py_name} ({names.py_to_name[py_name]!r}): "
            "axis-governed attributes are framework-stamped at write time — omit it at "
            "construction and let the verb stamp it"
        )
    return {
        canonical: serialize_member(getattr(instance, py_name))
        for canonical, py_name in names.name_to_py.items()
        if py_name in fields_set
    }


def primary_key_row(instance: object) -> dict[str, object]:
    """``instance``'s primary-key members, keyed by canonical name (spec §5)."""
    names = wire_names_of(type(instance))
    return {names.py_to_name[py_name]: getattr(instance, py_name) for py_name in names.pk_py}


def canonical_row(instance: object, py_row: dict[str, object]) -> dict[str, object]:
    """Translate a Python-name-keyed row to its canonical, write-serialized form."""
    names = wire_names_of(type(instance))
    return {names.py_to_name[py_name]: serialize_member(value) for py_name, value in py_row.items()}


def changed_fields(instance: object) -> dict[str, object] | None:
    """``instance``'s Change Record — each touched member to its earliest recorded
    original across the copy chain — or ``None`` when it carries none."""
    changes = (
        instance.__dict__.get("__parallax_changes__") if hasattr(instance, "__dict__") else None
    )
    if isinstance(changes, dict):
        return cast("dict[str, object]", changes)
    return None


def effective_change_set(copy: object) -> dict[str, object]:
    """The touched-and-different members of an edited copy (spec §3/§5).

    A touched member whose current value equals its recorded original drops out,
    so a net-zero copy chain is a no-op.
    """
    changes = changed_fields(copy)
    if changes is None:
        raise ProvenanceError(
            f"{type(copy).__name__} carries no Change Record; derive an edited copy via "
            "`instance.model_copy(update={...})` before passing it to `tx.update`"
        )
    return {
        py_name: getattr(copy, py_name)
        for py_name, original in changes.items()
        if getattr(copy, py_name) != original
    }


def _validate_copy_update(cls_name: str, names: WireNames, update: Mapping[str, Any]) -> None:
    """Reject an unassignable ``model_copy(update=...)`` entry (spec §3).

    The split is by what each half can know. Resolving a Python name to a member
    is a class-shaped question and is answered here: a relationship member and an
    undeclared name never reach a member at all. Everything a resolved member
    then decides — primary-key, read-only, and framework-owned targets, in that
    order, plus declared-type and nullability conformance — is
    :func:`~parallax.core.metamodel.judge_assignment`'s single verdict, the SAME
    one ``Attr.set(...)`` and the serialized write boundary reach, so an edited
    copy and a write can never disagree about what may be assigned.

    A Value Object value is rendered to its canonical document before it is
    judged, exactly as ``.set(...)`` renders it, so both paths judge one shape;
    the copy itself still merges the caller's own live value.
    """
    for py_name, value in update.items():
        if py_name in names.relationship_py.values():
            raise ModelCopyError(
                f"{cls_name}.{py_name}: relationship members are not assignable via model_copy "
                "(no cascade or association-mutation semantics to lower it to)"
            )
        member = names.members.get(py_name)
        if member is None:
            raise ModelCopyError(f"{cls_name}.{py_name}: unknown member name")
        try:
            judge_assignment(member, serialize_member(value))
        except WriteAssignmentError as error:
            raise ModelCopyError(f"{cls_name}.{error}") from error


class Entity(BaseModel, metaclass=EntityMeta, _mint=FRAMEWORK_MINT):
    """The frozen base every Parallax Entity Class extends."""

    all = _All()
    """The explicitly unfiltered query over this Entity (``Animal.all``).

    A distinct type from a Predicate, carrying no boolean operators: an
    unfiltered query is the whole filter or it is not the filter at all.
    """

    @classmethod
    def where[E: Entity](cls: type[E], *predicates: Predicate[E] | AllPredicate[E]) -> Statement:
        """Build a side-effect-free statement conjoining ``predicates`` (empty is find-all).

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
        return build_statement(cls.identity.name, predicates, as_of_axes=_family_axes(cls))

    @classmethod
    def narrow[E: Entity, S: Entity](
        cls: type[E], *subtypes: type[S], where: Predicate[S] | None = None
    ) -> Predicate[E]:
        """The scoped subtype-narrowing constructor (spec §2).

        ``to`` preserves the authored subtype list verbatim, and ``where=`` grants
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
        to = tuple(declaration_of(subtype).identity.name for subtype in subtypes)
        operand: Operation = where.op if where is not None else All()
        return Predicate(Narrow(entity=cls.identity.name, to=to, operand=operand))

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        """The validating override (spec §3).

        A copy carries a Change Record mapping each touched member to its
        earliest original across copy chains. Unlike Pydantic's own
        ``model_copy``, ``update=`` data is validated: an unknown or
        relationship member raises, every remaining entry is judged by the SAME
        assignment rules ``Attr.set(...)`` and the serialized write boundary
        apply (:func:`_validate_copy_update`), and the merged instance still
        goes back through the ordinary constructor for the §2 input policies.

        An axis-governed member this copy's ``update`` never names is carried
        forward without re-validation: a materialized current milestone's value
        there may be the framework's open-interval sentinel, which the wrapping
        construction never validated either.
        """
        if not update:
            copied = super().model_copy(update=None, deep=deep)
            carried = dict(changed_fields(self) or {})
            object.__setattr__(copied, "__parallax_changes__", carried)
            return copied
        names = wire_names_of(type(self))
        _validate_copy_update(type(self).__name__, names, update)
        declared = set(names.py_to_name)
        merged = {k: v for k, v in self.__dict__.items() if k in declared}
        merged.update(update)
        untouched_axis = names.axis_governed_py - set(update)
        carry_forward = {
            py_name: merged.pop(py_name) for py_name in untouched_axis if py_name in merged
        }
        validated = type(self)(**merged)  # re-validates the whole instance (§2 input policies)
        for py_name, value in carry_forward.items():
            object.__setattr__(validated, py_name, value)
        changes = dict(changed_fields(self) or {})
        for py_name in update:
            if py_name not in changes:
                changes[py_name] = getattr(self, py_name)
        object.__setattr__(validated, "__parallax_changes__", changes)
        return validated


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
