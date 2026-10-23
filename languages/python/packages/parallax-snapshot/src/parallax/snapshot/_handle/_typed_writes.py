from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from parallax.core._execution._family import family_view
from parallax.core._execution._keyed_writes import (
    ResolvedKeyedInsert,
    ResolvedKeyedWriteSource,
    keyed_instruction,
)
from parallax.core._execution._publication import SelectedWriteModel
from parallax.core._execution._transaction._attempt import TargetWriteInput
from parallax.core._execution._unit_work import instructions
from parallax.core._execution._unit_work.instructions import (
    ASSIGNMENT_MUTATIONS,
    REPLACE_MUTATIONS,
    KeyedMutation,
    PredicateMutation,
    PredicateSelection,
    PredicateWriteInstruction,
    PreparedKeyedInstruction,
    PreparedPredicateInstruction,
    TargetMutation,
    WriteAssignment,
)
from parallax.core.entity import AttributeAssignment, EntityRowCodec
from parallax.core.entity import Entity as EntityBase
from parallax.core.entity._authored_resolver import typed_interpretation
from parallax.core.entity._declaration import declaration_of
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.object_query._fluent import ObjectQuery, mutation_selection

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores, which under pyright strict would make every intra-package
# import a reportPrivateUsage error.
from parallax.snapshot._handle._sources import (
    resolve_keyed_insert,
    resolve_keyed_write_source,
)

__all__ = [
    "TypedInstanceTargetWriteAdapter",
    "TypedKeyTargetWriteAdapter",
    "TypedKeyedInsertSource",
    "TypedKeyedWriteSource",
    "TypedPredicateWriteAdapter",
    "typed_selection",
]


def metadata_of_instance(meta: Metamodel, instance: EntityBase) -> EntityMetadata:
    """``instance``'s accepted Entity Metadata within ``meta``, or a loud
    ``TypeError`` when the connected model declares no such Entity.

    Membership is decided by the Entity Identity the instance's class declares:
    one class participates in any number of models, so belonging is a question
    about this model rather than about the class. What a shared identity cannot
    settle — whether a foreign class's MEMBERS are this model's — is settled one
    layer down and unchanged: the row acquisition and typed preparation every
    keyed write runs against the connected model reject a foreign instance's
    row.
    """
    cls = type(instance)
    metadata = meta.entity(declaration_of(cls).identity)
    if metadata is None:
        raise TypeError(f"{cls.__name__} is not an Entity Class of this model")
    return metadata


def prepared_typed_write(
    meta: Metamodel,
    mutation: KeyedMutation,
    entity: EntityMetadata,
    row: Mapping[str, object],
    *,
    valid_from: dt.datetime | None,
    until: dt.datetime | None,
    members: Callable[[], Mapping[str, object]] | None = None,
) -> PreparedKeyedInstruction:
    """One authored single-row keyed instruction, judged by Unit Work's sole
    typed preparation — target and window, then member names, values, and
    assignment legality, each of ``members`` judged as an assignment.

    The bounds ride the instruction's dimension-explicit fields rather than the
    row (ADR 0010/0013): an As-Of Axis endpoint is framework-owned, so a
    Valid-Time bound is never a member a caller could author.
    """
    prepared = instructions.prepare_typed_write(
        keyed_instruction(mutation, entity.identity, row, valid_from=valid_from, until=until),
        meta,
        members=members,
    )
    return prepared


def typed_selection(
    query: ObjectQuery[Any, Any], write_model: SelectedWriteModel
) -> PredicateSelection:
    """``query`` as the selection a predicate write states, refused as no write
    target unless it is mutation-compatible.

    The authored predicate is captured, never encoded: the selection carries
    the Typed interpretation of it, bound lazily against ``write_model``.
    """
    selection = mutation_selection(query)
    return PredicateSelection(
        selection.target.canonical,
        typed_interpretation(selection.predicate, write_model.model.meta, write_model.classes),
    )


def write_assignments(
    assignments: Sequence[AttributeAssignment[Any]],
) -> tuple[WriteAssignment, ...]:
    """``Attr.set(...)`` assignments as the canonical write assignments, each
    keeping the qualified reference its owner is judged by."""
    return tuple(
        WriteAssignment(str(assignment.attr), assignment.value) for assignment in assignments
    )


class TypedKeyedWriteSource:
    """The Typed Keyed Write Source: what an Entity value and its Change Record
    answer the keyed write ingress.

    Inert when constructed and private to one verb call, so nothing it can refuse
    runs before the ingress refuses re-entry. A Typed value's shape is fixed by
    its class, and ``edit()`` has already judged every assignment its Change
    Record holds, which is why the authoring refusals the Wire lane raises at its
    own capture reach a Typed caller before a verb ever receives a value.
    :meth:`capture` judges the one authoring fact a Typed amendment can still
    get wrong: explicit ``assignments`` beside a value whose edit chain already
    authored history, which would give one write two authors.
    """

    __slots__ = ("_assignments", "_codec", "_value")

    def __init__(
        self,
        value: EntityBase,
        codec: EntityRowCodec,
        assignments: Sequence[AttributeAssignment[Any]] = (),
    ) -> None:
        self._value = value
        self._codec = codec
        self._assignments = assignments

    def capture(self, mutation: KeyedMutation, /) -> None:
        if self._assignments and self._codec.has_edit_history(self._value):
            raise instructions.WriteInstructionError(
                f"`{mutation}` was handed explicit assignments beside a value whose edit chain "
                "already authored changes, and one write has one author: pass the edited value "
                "alone, or a value with no edit history and the complete list of assignments"
            )

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedWriteSource:
        """The facts this value states about the state the write revises."""
        return resolve_keyed_write_source(metadata_of_instance(model, self._value), self._value)

    def prepare(
        self,
        model: Metamodel,
        mutation: KeyedMutation,
        resolved: ResolvedKeyedWriteSource,
        /,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> PreparedKeyedInstruction:
        """The instruction this value authors.

        An amendment authors the value's identity plus every member its edit
        chain touched, at the value each now holds, or plus exactly the explicit
        assignments it was handed instead. The touched set is cumulative across
        the chain and literal: a member set back to the value the source
        published is still assigned, because the caller expressed it. A
        replacement authors the value's complete writable state, whatever its
        chain touched. A destructive or close verb names no member at all and
        authors its identity row alone, and so does an amendment off a value
        whose chain touched nothing — the empty write the ingress drops.
        """
        row, explicit = self._authored(model, mutation, resolved.entity)
        return prepared_typed_write(
            model,
            mutation,
            resolved.entity,
            row,
            valid_from=valid_from,
            until=until,
            members=explicit,
        )

    def _authored(
        self, meta: Metamodel, mutation: KeyedMutation, entity: EntityMetadata
    ) -> tuple[Mapping[str, object], Callable[[], Mapping[str, object]] | None]:
        """The row this value authors, and the explicit assignments preparation
        judges into that row once the target and window admit the write."""
        value, codec = self._value, self._codec
        if mutation in REPLACE_MUTATIONS:
            return codec.writable_row(value), None
        if mutation not in ASSIGNMENT_MUTATIONS:
            return codec.identity_row(value), None
        if self._assignments:
            assignments = write_assignments(self._assignments)
            return (
                codec.identity_row(value),
                lambda: instructions.assigned_members(meta, entity, assignments),
            )
        authored = codec.authored_row(value)
        if authored is None:
            return codec.identity_row(value), None
        return authored.row, None


class TypedKeyedInsertSource:
    """The Typed Keyed Insert Source: what a fresh Entity instance answers the
    ingress's insert door.

    Narrower than its peer by exactly what an opening row has no answer for: no
    hint, no identity row named ahead of the instruction, and no originals. What
    it authors is the Create Payload — every member the instance actually SET —
    rather than a change set, because there is no prior state for a change to be
    against.
    """

    __slots__ = ("_codec", "_instance")

    def __init__(self, instance: EntityBase, codec: EntityRowCodec) -> None:
        self._instance = instance
        self._codec = codec

    def capture(self, mutation: KeyedMutation, /) -> None:
        return None

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedInsert:
        return resolve_keyed_insert(metadata_of_instance(model, self._instance), self._instance)

    def prepare(
        self,
        model: Metamodel,
        mutation: KeyedMutation,
        resolved: ResolvedKeyedInsert,
        /,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> PreparedKeyedInstruction:
        return prepared_typed_write(
            model,
            mutation,
            resolved.entity,
            self._codec.full_row(self._instance),
            valid_from=valid_from,
            until=until,
        )


class TypedPredicateWriteAdapter:
    """The Typed predicate-selected write: a mutation-compatible
    :class:`~parallax.core.object_query.ObjectQuery` plus ``Attr.set(...)``
    assignments, or the instance whose writable state a replacement states,
    stated as the :class:`~parallax.core.unit_work.PredicateWriteInstruction`
    every ingress prepares.

    Inert when constructed and private to one verb call. The query's own form is
    its one representation judgment, made once :meth:`prepare` is asked
    (:func:`typed_selection`): a query carrying a result-shaping, temporal,
    narrowing, or deep-fetch clause is no write target, and no instruction has
    a spelling for such a clause. A replacement's instance is then used only as
    data, as a caller-conditioned replacement's is, and must be one of the
    queried Entity. Everything the instruction states is judged by
    :func:`~parallax.core._execution._unit_work.instructions.prepare_typed_write`.
    """

    __slots__ = ("_payload", "_query")

    def __init__(
        self,
        query: ObjectQuery[Any, Any],
        payload: Sequence[AttributeAssignment[Any]] | EntityBase,
    ) -> None:
        self._query = query
        self._payload = payload

    def prepare(
        self, write_model: SelectedWriteModel, mutation: PredicateMutation
    ) -> PreparedPredicateInstruction:
        selection = typed_selection(self._query, write_model)
        payload = self._payload
        if mutation in REPLACE_MUTATIONS:
            row = _replacement_row(write_model, selection, cast("EntityBase", payload))
            instruction = PredicateWriteInstruction(mutation, selection, row=row)
        else:
            assignments = cast("Sequence[AttributeAssignment[Any]]", payload)
            instruction = PredicateWriteInstruction(
                mutation, selection, write_assignments(assignments)
            )
        return instructions.prepare_typed_write(instruction, write_model.model.meta)


def _replacement_row(
    write_model: SelectedWriteModel, selection: PredicateSelection, payload: EntityBase
) -> Mapping[str, object]:
    """The writable state ``payload`` holds, once it is judged an instance of
    the Entity ``selection`` writes."""
    entity = metadata_of_instance(write_model.model.meta, payload)
    if entity.identity.canonical != selection.entity:
        raise instructions.WriteInstructionError(
            f"`replace_where` over {selection.entity} states a whole state of that Entity, and "
            f"this payload is a {entity.identity.canonical}"
        )
    return write_model.codec.writable_row(payload)


class TypedInstanceTargetWriteAdapter:
    """The Typed caller-conditioned replacement: ``instance``'s every populated
    writable member as the row a :class:`~parallax.core.unit_work.TargetWriteInstruction`
    states, beside the caller's own revision.

    Inert when constructed and private to one verb call. What produced the
    instance is not asked: the write addresses the object its key names, under
    the revision its caller states, so neither a read's evidence nor an
    insertion's authority the instance carries is consulted — which is what
    lets a historical observation supply a replacement's state. The row comes
    through the codec of the write projection the attempt lends.
    """

    __slots__ = ("_instance",)

    def __init__(self, instance: EntityBase) -> None:
        self._instance = instance

    def write_input(
        self, write_model: SelectedWriteModel, mutation: TargetMutation
    ) -> TargetWriteInput:
        entity = metadata_of_instance(write_model.model.meta, self._instance)
        return TargetWriteInput(
            entity.identity.canonical, write_model.codec.writable_row(self._instance), "typed"
        )


class TypedKeyTargetWriteAdapter:
    """The Typed caller-conditioned amendment, deletion, or termination of the
    object of concrete ``entity_class`` its scalar ``key`` names:
    ``assignments`` for an amendment, none for a destructive verb, under the
    caller's own revision, with no instance, read, or source consulted.

    Inert when constructed and private to one verb call. ``key`` addresses the
    family's one primary-key Attribute whatever its declared name; a mapping or
    tuple is no key here. The key and assignments are the write's payload,
    judged only once its verb, window, and revision admit it. Each assignment's
    reference is judged against the class's own ancestry before any is
    flattened into the row, so an inherited member applies and a foreign one is
    refused.
    """

    __slots__ = ("_assignments", "_entity_class", "_key")

    def __init__(
        self,
        entity_class: type[EntityBase],
        assignments: Sequence[AttributeAssignment[Any]],
        key: object,
    ) -> None:
        self._entity_class = entity_class
        self._assignments = assignments
        self._key = key

    def write_input(
        self, write_model: SelectedWriteModel, mutation: TargetMutation
    ) -> TargetWriteInput:
        meta = write_model.model.meta
        entity = metadata_of_class(meta, self._entity_class)
        key, assignments = self._key, self._assignments

        def members() -> Mapping[str, object]:
            if isinstance(key, Mapping | tuple | list | set | frozenset):
                kind = type(cast("object", key)).__name__
                raise instructions.WriteInstructionError(
                    f"{entity.identity.name}: key is the object's one scalar primary-key value, "
                    f"and a {kind} is no such value"
                )
            return instructions.assigned_members(meta, entity, write_assignments(assignments))

        key_name = family_view(meta, entity).primary_key.identity.name
        return TargetWriteInput(
            entity.identity.canonical, {key_name: key}, "typed", members=members
        )


def metadata_of_class(meta: Metamodel, entity_class: object) -> EntityMetadata:
    """The accepted Entity Metadata ``entity_class`` declares within ``meta``,
    or a loud ``TypeError`` for anything else."""
    if not isinstance(entity_class, type) or not issubclass(entity_class, EntityBase):
        raise TypeError(f"{entity_class!r} is not an Entity Class")
    metadata = meta.entity(declaration_of(entity_class).identity)
    if metadata is None:
        raise TypeError(f"{entity_class.__name__} is not an Entity Class of this model")
    return metadata
