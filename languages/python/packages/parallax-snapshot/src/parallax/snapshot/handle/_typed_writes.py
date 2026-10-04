from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Any

from parallax.core.entity import (
    AttributeAssignment,
    EntityRowCodec,
    lifecycle_state_of,
)
from parallax.core.entity import Entity as EntityBase
from parallax.core.entity._declaration import declaration_of
from parallax.core.execution_lifecycle._activity import refuse_reentry
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.object_query._fluent import ObjectQuery, mutation_selection
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import (
    UPDATE_MUTATIONS,
    KeyedMutation,
    ObjectKey,
    PredicateMutation,
    PredicateSelection,
    PredicateWrite,
    ReadOrigin,
    TargetMutation,
    TargetWrite,
    WriteAssignment,
    instructions,
)
from parallax.core.unit_work.instructions import PreparedKeyedWrite, PreparedPredicateWrite

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores, which under pyright strict would make every intra-package
# import a reportPrivateUsage error.
from parallax.snapshot._inspection import insertion_of, snapshot_state_of
from parallax.snapshot.handle._family import family_view
from parallax.snapshot.handle._keyed_writes import (
    PreparedSourceWrite,
    Provenance,
    ResolvedKeyedInsert,
    ResolvedKeyedWriteSource,
    keyed_instruction,
    retained,
)
from parallax.snapshot.handle._predicate_writes import (
    PredicateWriteContext,
    buffer_predicate_instruction,
    buffer_target_instruction,
)

__all__ = [
    "TypedKeyedInsertSource",
    "TypedKeyedWriteSource",
    "provenance_of",
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
    :class:`~parallax.core.unit_work.ObjectKey` a source's own Read Origins name
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
) -> PreparedKeyedWrite:
    """One authored single-row keyed instruction, judged by Unit Work's sole
    typed preparation — target and window, then member names, values, and
    assignment legality.

    The bounds ride the instruction's dimension-explicit fields rather than the
    row (ADR 0010/0013): an As-Of Axis endpoint is framework-owned, so a
    Valid-Time bound is never a member a caller could author.
    """
    prepared = instructions.prepare_typed_write(
        keyed_instruction(mutation, entity.identity, row, valid_from=valid_from, until=until),
        meta,
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


class TypedKeyedWriteSource:
    """The Typed Keyed Write Source: what an Entity value and its Change Record
    answer the keyed write ingress.

    Inert when constructed and private to one verb call, so nothing it can refuse
    runs before the ingress refuses re-entry. :meth:`capture` judges nothing at
    all — a Typed value's shape is fixed by its class, and ``edit()`` has already
    judged every assignment its Change Record holds, which is why the authoring
    refusals the Wire lane raises at its own capture reach a Typed caller before a
    verb ever receives a value.

    The mutation and the accepted Metamodel arrive at the phases the protocol
    hands them to and are retained for :meth:`prepare`, which authors the
    instruction and is handed neither.
    """

    __slots__ = ("_codec", "_meta", "_mutation", "_value")

    def __init__(self, value: EntityBase, codec: EntityRowCodec) -> None:
        self._value = value
        self._codec = codec
        self._meta: Metamodel | None = None
        self._mutation: KeyedMutation | None = None

    def capture(self, mutation: KeyedMutation, /) -> None:
        return None

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
        """The instruction this value authors: its identity plus every member
        its edit chain touched, at the value each now holds.

        The touched set is cumulative across the chain and literal: a member set
        back to the value the source published is still assigned, because the
        caller expressed it. A destructive or close verb names no member at all
        and authors its identity row alone, and so does an update off a value
        whose chain touched nothing — the empty set the ingress drops.

        The object a refusal reports comes from the source's own hint where there
        is one, and is derived from the authored row where there is not — the two
        agree by construction, because a read keys its hint by the same rule a
        written row is keyed by.
        """
        meta, mutation = self._retained()
        authored = self._codec.authored_row(self._value) if mutation in UPDATE_MUTATIONS else None
        if authored is None:
            row: Mapping[str, object] = self._codec.identity_row(self._value)
            assigned: frozenset[str] = frozenset()
        else:
            row = authored.row
            assigned = frozenset(authored.originals)
        instruction = prepared_typed_write(
            meta, mutation, resolved.entity, row, valid_from=valid_from, until=until
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
    ctx: PredicateWriteContext,
    mutation: PredicateMutation,
    query: ObjectQuery[Any, Any],
    assignments: Sequence[AttributeAssignment[Any]],
    *,
    valid_from: dt.datetime | None,
    until: dt.datetime | None = None,
) -> None:
    """The Typed entry to the predicate-write lane: a mutation-compatible
    :class:`~parallax.core.object_query.ObjectQuery` plus ``Attr.set(...)``
    assignments, stated as the canonical
    :class:`~parallax.core.unit_work.PredicateWrite` every ingress prepares.

    Only the query's own form is judged here: a query carrying a result-shaping,
    temporal, narrowing, or deep-fetch clause is no write target
    (:func:`~parallax.core.object_query.mutation_selection`,
    ``query-not-mutation-compatible``), and no instruction has a spelling for
    such a clause. Everything the instruction states — its target, verb, window,
    predicate, and assignments — is judged by
    :func:`~parallax.core.unit_work.instructions.prepare_typed_write` before
    :func:`~parallax.snapshot.handle._predicate_writes.buffer_predicate_instruction`
    dispatches the prepared product.
    """
    refuse_reentry(ctx.keyed.lifecycle)
    selection = mutation_selection(query)
    instruction = PredicateWrite(
        mutation,
        PredicateSelection(selection.target.canonical, selection.predicate),
        tuple(
            WriteAssignment(str(assignment.attr), assignment.value) for assignment in assignments
        ),
        valid_from,
        until,
    )
    prepared = instructions.prepare_typed_write(instruction, ctx.keyed.model.meta)
    assert isinstance(prepared, PreparedPredicateWrite)
    buffer_predicate_instruction(ctx, prepared)


def typed_target_write(
    ctx: PredicateWriteContext,
    mutation: TargetMutation,
    instance: EntityBase,
    codec: EntityRowCodec,
    *,
    valid_from: dt.datetime | None,
    until: dt.datetime | None,
    if_version: int | None,
    if_tx_start: dt.datetime | None,
) -> None:
    """The Typed entry to the caller-addressed write lane: ``instance``'s
    every populated writable member as the row a
    :class:`~parallax.core.unit_work.TargetWrite` states, beside the caller's own
    revision arguments.

    What produced the instance is not asked: the write addresses the object its
    key names, under the condition its caller states, so neither a read's
    evidence nor an insertion's authority the instance carries is consulted.
    """
    refuse_reentry(ctx.keyed.lifecycle)
    meta = ctx.keyed.model.meta
    entity = metadata_of_instance(meta, instance)
    instruction = TargetWrite(
        mutation,
        entity.identity.canonical,
        codec.writable_row(instance),
        if_version,
        if_tx_start,
        valid_from,
        until,
    )
    buffer_target_instruction(ctx, instructions.prepare_typed_write(instruction, meta))
