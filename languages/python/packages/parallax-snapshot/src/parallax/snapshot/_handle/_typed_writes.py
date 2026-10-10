from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from parallax.core.entity import (
    AttributeAssignment,
    EntityRowCodec,
    lifecycle_state_of,
)
from parallax.core.entity import Entity as EntityBase
from parallax.core.entity._authored_resolver import typed_interpretation
from parallax.core.entity._declaration import declaration_of
from parallax.core.execution._attempt import Attempt
from parallax.core.execution._family import family_view
from parallax.core.execution._keyed_writes import (
    PreparedSourceWrite,
    Provenance,
    ResolvedKeyedInsert,
    ResolvedKeyedWriteSource,
    TargetCondition,
    keyed_instruction,
    retained,
    stated_valid_from,
)
from parallax.core.execution._options import OMITTED, Omitted
from parallax.core.execution_lifecycle._activity import refuse_reentry
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.object_query._fluent import ObjectQuery, mutation_selection
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import (
    ASSIGNMENT_MUTATIONS,
    REPLACE_MUTATIONS,
    KeyedMutation,
    PredicateMutation,
    PredicateSelection,
    PredicateWrite,
    ReadOrigin,
    TargetMutation,
    TargetWrite,
    WriteAssignment,
    instructions,
)
from parallax.core.unit_work.instructions import PreparedKeyedWrite
from parallax.core.write_plan import ObjectKey

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores, which under pyright strict would make every intra-package
# import a reportPrivateUsage error.
from parallax.snapshot._inspection import insertion_of, snapshot_state_of

__all__ = [
    "TypedKeyedInsertSource",
    "TypedKeyedWriteSource",
    "provenance_of",
    "typed_conditional_amend",
    "typed_predicate_write",
    "typed_target_write",
]


def provenance_of(value: EntityBase) -> Provenance:
    """Which framework-managed source produced ``value``.

    Read through :func:`~parallax.snapshot._inspection.snapshot_state_of` and the
    un-narrowed :func:`~parallax.core.entity.lifecycle_state_of`, never through a
    value's private state: the narrowed answer authenticates THIS Snapshot
    lifecycle, and its Read Origin says whether that lifecycle published valid
    stored Entity State. Diagnostic data from an invalid root carries Snapshot
    state for inspection but no origin, so it is ``none`` rather than a stored
    value of this source. The un-narrowed answer distinguishes another
    framework-managed source's value from one no managed source produced at all.

    It belongs to the Typed adapter because only a Typed value carries a
    lifecycle to read: a Wire source answers the same fact from the Read Origin
    the door that published it filed, and what the keyed write judges is the
    answer rather than either carrier.

    The authority an admitted insertion bound to an instance is no read, so a
    value carrying it alone is still one no managed source published.
    """
    if lifecycle_state_of(value) is None:
        return "none"
    state = snapshot_state_of(value)
    if state is None:
        return "none" if insertion_of(value) is not None else "foreign"
    return "none" if state.source is None else "this"


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


def instance_read_origin(instance: object) -> ReadOrigin | None:
    """The private :class:`~parallax.core.unit_work.ReadOrigin` ``instance``
    carries, or ``None`` for a value Parallax never published.

    An edited copy answers the node's own hint, because an edit preserves every
    kind of instance state outside the declared members (``Entity.edit``) — which
    is what lets a developer read a row, change what they read, and write back
    against the state they read. A value another framework-managed source
    produced answers ``None`` here: its lifecycle state is that source's own, so
    this lifecycle recognizes no hint on it.
    """
    state = snapshot_state_of(instance)
    return None if state is None else state.source


def source_pin(instance: object) -> Pin | None:
    """The whole-graph as-of :class:`Pin` a materialized snapshot node carries,
    or ``None`` for anything else — a plainly constructed instance, or an edit
    of one.

    An edited copy of a NODE answers the node's own pin: an edit preserves every
    kind of instance state outside the declared members, lifecycle state among
    them (``Entity.edit``), so the write a developer derives from a pinned view
    is refused exactly as a write of the view itself is. What a value answers
    here is therefore its provenance, not its editedness."""
    state = snapshot_state_of(instance)
    return None if state is None else state.pin


def written_object_key(
    record: EntityMetadata, meta: Metamodel, row: Mapping[str, object]
) -> ObjectKey:
    """The object a WRITTEN instance addresses — the same
    :class:`~parallax.core.write_plan.ObjectKey` a source's own Read Origins name
    their objects by (the instance's OWN Entity Identity, never
    family-normalized; its one pair keyed by the family key's canonical
    attribute name) and `unit_work.object_key` computes at flush, so a
    verb-time refusal and the flush-time settle can never name the object two
    different ways.

    ``row`` is that instance's identity row as the Entity Row Codec derived it,
    passed in rather than derived here: the Inheritance Facet owns which member
    is the family key, and the codec owns what an Entity value's canonical
    primary key IS."""
    name = family_view(meta, record).primary_key.identity.name
    return ObjectKey(record.identity, ((name, row[name]),))


def prepared_typed_write(
    meta: Metamodel,
    mutation: KeyedMutation,
    entity: EntityMetadata,
    row: Mapping[str, object],
    *,
    valid_from: dt.datetime | None,
    until: dt.datetime | None,
    members: Callable[[], Mapping[str, object]] | None = None,
) -> PreparedKeyedWrite:
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

    The mutation and the accepted Metamodel arrive at the phases the protocol
    hands them to and are retained for :meth:`prepare`, which authors the
    instruction and is handed neither.
    """

    __slots__ = ("_assignments", "_codec", "_meta", "_mutation", "_value")

    def __init__(
        self,
        value: EntityBase,
        codec: EntityRowCodec,
        assignments: Sequence[AttributeAssignment[Any]] = (),
    ) -> None:
        self._value = value
        self._codec = codec
        self._assignments = assignments
        self._meta: Metamodel | None = None
        self._mutation: KeyedMutation | None = None

    def capture(self, mutation: KeyedMutation, /) -> None:
        if self._assignments and self._codec.has_edit_history(self._value):
            raise instructions.WriteInstructionError(
                f"`{mutation}` was handed explicit assignments beside a value whose edit chain "
                "already authored changes, and one write has one author: pass the edited value "
                "alone, or a value with no edit history and the complete list of assignments"
            )

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedWriteSource:
        """The facts this value states about the state the write revises."""
        self._meta = model
        self._mutation = mutation
        entity = metadata_of_instance(model, self._value)
        return ResolvedKeyedWriteSource(
            entity=entity,
            pin=source_pin(self._value),
            hint=instance_read_origin(self._value),
            provenance=provenance_of(self._value),
            representation="typed",
            authoring=insertion_of(self._value),
        )

    def prepare(
        self,
        resolved: ResolvedKeyedWriteSource,
        /,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> PreparedSourceWrite:
        """The instruction this value authors.

        An amendment authors the value's identity plus every member its edit
        chain touched, at the value each now holds, or plus exactly the explicit
        assignments it was handed instead. The touched set is cumulative across
        the chain and literal: a member set back to the value the source
        published is still assigned, because the caller expressed it. A
        replacement authors the value's complete writable state, whatever its
        chain touched. A destructive or close verb names no member at all and
        authors its identity row alone, and so does an amendment off a value
        whose chain touched nothing — the empty set the ingress drops.

        The object a refusal reports comes from the source's own hint where there
        is one, and is derived from the authored row where there is not — the two
        agree by construction, because a read keys its hint by the same rule a
        written row is keyed by.
        """
        meta, mutation = self._retained()
        row, assigned, explicit = self._authored(meta, mutation, resolved.entity)
        instruction = prepared_typed_write(
            meta,
            mutation,
            resolved.entity,
            row,
            valid_from=valid_from,
            until=until,
            members=explicit,
        )
        return PreparedSourceWrite(
            instruction=instruction,
            object_key=(
                resolved.hint.object_key
                if resolved.hint is not None
                else written_object_key(resolved.entity, meta, instruction.rows[0])
            ),
            assigned=assigned,
        )

    def _authored(
        self, meta: Metamodel, mutation: KeyedMutation, entity: EntityMetadata
    ) -> tuple[Mapping[str, object], frozenset[str], Callable[[], Mapping[str, object]] | None]:
        """The row this value authors, the members it assigns, and the explicit
        assignments preparation judges into that row once the target and
        window admit the write."""
        value, codec = self._value, self._codec
        if mutation in REPLACE_MUTATIONS:
            row = codec.writable_row(value)
            key = family_view(meta, entity).primary_key.identity.name
            return row, frozenset(name for name in row if name != key), None
        if mutation not in ASSIGNMENT_MUTATIONS:
            return codec.identity_row(value), frozenset(), None
        if self._assignments:
            assignments = write_assignments(self._assignments)
            return (
                codec.identity_row(value),
                frozenset(assignment.attr.attribute for assignment in self._assignments),
                lambda: instructions.assigned_members(meta, entity, assignments),
            )
        authored = codec.authored_row(value)
        if authored is None:
            return codec.identity_row(value), frozenset(), None
        return authored.row, frozenset(authored.originals), None

    def _retained(self) -> tuple[Metamodel, KeyedMutation]:
        return retained(self._meta), retained(self._mutation)


class TypedKeyedInsertSource:
    """The Typed Keyed Insert Source: what a fresh Entity instance answers the
    ingress's insert door.

    Narrower than its peer by exactly what an opening row has no answer for: no
    hint, no identity row named ahead of the instruction, and no originals. What
    it authors is the Create Payload — every member the instance actually SET —
    rather than a change set, because there is no prior state for a change to be
    against.
    """

    __slots__ = ("_codec", "_instance", "_meta", "_mutation")

    def __init__(self, instance: EntityBase, codec: EntityRowCodec) -> None:
        self._instance = instance
        self._codec = codec
        self._meta: Metamodel | None = None
        self._mutation: KeyedMutation | None = None

    def capture(self, mutation: KeyedMutation, /) -> None:
        return None

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedInsert:
        self._meta = model
        self._mutation = mutation
        return ResolvedKeyedInsert(
            entity=metadata_of_instance(model, self._instance),
            pin=source_pin(self._instance),
            provenance=provenance_of(self._instance),
            representation="typed",
        )

    def prepare(
        self,
        resolved: ResolvedKeyedInsert,
        /,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> PreparedKeyedWrite:
        return prepared_typed_write(
            retained(self._meta),
            retained(self._mutation),
            resolved.entity,
            self._codec.full_row(self._instance),
            valid_from=valid_from,
            until=until,
        )


def typed_predicate_write(
    attempt: Attempt,
    mutation: PredicateMutation,
    query: ObjectQuery[Any, Any],
    assignments: Sequence[AttributeAssignment[Any]],
    *,
    valid_from: dt.datetime | Omitted = OMITTED,
    until: dt.datetime | None = None,
) -> None:
    """The Typed entry to the predicate-write lane: a mutation-compatible
    :class:`~parallax.core.object_query.ObjectQuery` plus ``Attr.set(...)``
    assignments, stated as the :class:`~parallax.core.unit_work.PredicateWrite`
    every ingress prepares.

    Only the query's own form is judged here: a query carrying a result-shaping,
    temporal, narrowing, or deep-fetch clause is no write target
    (:func:`~parallax.core.object_query.mutation_selection`,
    ``query-not-mutation-compatible``), and no instruction has a spelling for
    such a clause. The authored predicate is captured, never encoded: the
    instruction carries the Typed adapter over it, borrowing the attempt's
    adopted write projection. Everything the instruction states — its target,
    verb, window, predicate, and assignments — is judged by
    :func:`~parallax.core.unit_work.instructions.prepare_typed_write` before
    the attempt dispatches the prepared product.
    """
    refuse_reentry(attempt.lifecycle)
    start = stated_valid_from(valid_from)
    selection = mutation_selection(query)
    meta = attempt.model.meta
    instruction = PredicateWrite(
        mutation,
        PredicateSelection(
            selection.target.canonical,
            typed_interpretation(selection.predicate, meta, attempt.classes),
        ),
        write_assignments(assignments),
        start,
        until,
    )
    prepared = instructions.prepare_typed_write(instruction, meta)
    attempt.predicate_write(prepared)


def typed_target_write(
    attempt: Attempt,
    mutation: TargetMutation,
    instance: EntityBase,
    codec: EntityRowCodec,
    condition: TargetCondition,
    *,
    valid_from: dt.datetime | Omitted,
    until: dt.datetime | None,
) -> None:
    """The Typed entry to caller-conditioned replacement: ``instance``'s every
    populated writable member as the row a
    :class:`~parallax.core.unit_work.TargetWrite` states, beside the caller's own
    condition.

    What produced the instance is not asked: the write addresses the object its
    key names, under the condition its caller states, so neither a read's
    evidence nor an insertion's authority the instance carries is consulted —
    which is what lets a historical observation supply a replacement's state.
    """
    refuse_reentry(attempt.lifecycle)
    start = stated_valid_from(valid_from)
    meta = attempt.model.meta
    entity = metadata_of_instance(meta, instance)
    instruction = TargetWrite(
        mutation,
        entity.identity.canonical,
        codec.writable_row(instance),
        condition.if_version,
        condition.if_tx_start,
        start,
        until,
        condition.unversioned,
        condition.stated,
    )
    attempt.target_write(instructions.prepare_typed_write(instruction, meta))


def typed_conditional_amend(
    attempt: Attempt,
    mutation: TargetMutation,
    entity_class: type[EntityBase],
    assignments: Sequence[AttributeAssignment[Any]],
    key: object,
    condition: TargetCondition,
    *,
    valid_from: dt.datetime | Omitted,
    until: dt.datetime | None,
) -> None:
    """The Typed entry to caller-conditioned amendment: ``assignments`` of the
    object of concrete ``entity_class`` its scalar ``key`` names, under the
    caller's own condition, with no instance, read, or source consulted.

    ``key`` addresses the family's one primary-key Attribute whatever its
    declared name; a mapping or tuple is no key here. The key and assignments
    are the write's payload, judged only once its window and condition admit
    it. Each assignment's reference is judged against the class's own ancestry
    before any is flattened into the row, so an inherited member applies and a
    foreign one is refused.
    """
    refuse_reentry(attempt.lifecycle)
    start = stated_valid_from(valid_from)
    meta = attempt.model.meta
    entity = metadata_of_class(meta, entity_class)

    def members() -> Mapping[str, object]:
        if isinstance(key, Mapping | tuple | list | set | frozenset):
            kind = type(cast("object", key)).__name__
            raise instructions.WriteInstructionError(
                f"{entity.identity.name}: key is the object's one scalar primary-key value, and "
                f"a {kind} is no such value"
            )
        return instructions.assigned_members(meta, entity, write_assignments(assignments))

    key_name = family_view(meta, entity).primary_key.identity.name
    instruction = TargetWrite(
        mutation,
        entity.identity.canonical,
        {key_name: key},
        condition.if_version,
        condition.if_tx_start,
        start,
        until,
        condition.unversioned,
        condition.stated,
    )
    attempt.target_write(instructions.prepare_typed_write(instruction, meta, members=members))


def metadata_of_class(meta: Metamodel, entity_class: object) -> EntityMetadata:
    """The accepted Entity Metadata ``entity_class`` declares within ``meta``,
    or a loud ``TypeError`` for anything else."""
    if not isinstance(entity_class, type) or not issubclass(entity_class, EntityBase):
        raise TypeError(f"{entity_class!r} is not an Entity Class")
    metadata = meta.entity(declaration_of(entity_class).identity)
    if metadata is None:
        raise TypeError(f"{entity_class.__name__} is not an Entity Class of this model")
    return metadata
