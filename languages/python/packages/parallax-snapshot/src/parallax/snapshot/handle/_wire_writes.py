"""``parallax.snapshot.handle._wire_writes`` — the Wire write ingress (spec §5).

The representation-specific half of ``tx.wire``'s write verbs, as free functions
threading the transaction state they read — the shape
:mod:`parallax.snapshot.handle._predicate_writes` established. What is
representation-specific is only how a write's TARGET and its VALUES are stated:
a Typed verb takes an Entity value whose Change Record already names the
effective change, and a Wire verb takes the frozen mapping a Wire read published
plus an explicit changes document. Everything after that — the evidence
resolver, the claim, the instruction IR, the buffer, the planner, the observed
lifecycle — is the one pipeline both share, which is why a Typed write and a
Wire write of one object coalesce.

Three rules give the ingress its shape.

**A keyed source is a Parallax Wire read result, and nothing else.** There is no
explicit-Entity ordinary-mapping overload: the concrete Entity, the object, the
participation, the as-of pin, and the observation all come from the source's own
private Source Hint, so a mapping a caller built, converted with ``dict(...)``,
or round-tripped through JSON or pickle carries none of them and is refused
before any evidence is resolved.

**Static validation precedes evidence resolution, always.** Verb and source
shape, the finite-Transaction-Time refusal, the temporal window, member names,
values, and assignment legality are all judged from the model and the input
alone; only then does the target Entity's Effective Concurrency Strategy decide
what evidence licenses the write. Within the static half, the authored
documents' own shape leads, because it needs neither a source nor the model: a
call that states no document hears that rather than a complaint about its other
argument, and a selection's shape runs all the way through the predicate node
`m-predicate`'s algebra admits. Each verb then reads its remaining argument —
the source a keyed verb was handed, the Entity spelling an insert names — and
only afterwards does anything the target Entity and the model decide run.

Malformed Wire input therefore always earns a static refusal rather than a
:class:`~parallax.snapshot.handle.WriteEvidenceError`, whichever is also true.
Which static refusal follows from whose rule was broken:
:class:`~parallax.core.unit_work.WriteInstructionError` is this ingress's own
verdict — input that states no well-formed write — while a rule another module
owns keeps that module's classification, so one input is classified one way at
every boundary that accepts it. Those are the closed pre-SQL
:class:`~parallax.core.unit_work.WriteRejectedError` vocabulary for a normative
payload rule, `m-predicate`'s
:class:`~parallax.core.predicate.CanonicalDocumentError` for a malformed
predicate node, and `m-core`'s :class:`~parallax.core.base.InstantError` for a
bound that is no instant. All are ``ValueError``s raised before the evidence
question.

**Caller-owned input is owned by preparation before the verb returns.** The ingress
first validates document shape without copying, then unit-work preparation converts
and freezes the retained product in one traversal. A keyed source is already deeply
frozen; the verb retains only its identity, resolved evidence, and explicitly changed
published values.

Wire input is stated in the accepted spellings its serde seam admits. This adapter
validates document shape and delegates source-specific decoding plus retained-value
ownership to :func:`parallax.core.unit_work.instructions.prepare_wire_write`.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from parallax.core import inheritance
from parallax.core import predicate as predicate_algebra
from parallax.core.base import TIMESTAMP, NeutralType
from parallax.core.db_port import DbPort
from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution_lifecycle._activity import (
    InstalledLifecycle,
    TransactionAttemptActivity,
    refuse_reentry,
)
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    ValueObjectMetadata,
)
from parallax.core.unit_work import (
    KeyedMutation,
    PredicateMutation,
    PredicateWrite,
    SettledEvidence,
    SourceHint,
    UnitOfWork,
    instructions,
    object_key,
)
from parallax.core.unit_work.columns import freeze_retained_value
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedPredicateWrite,
)
from parallax.core.wire import WireDecodingError, WireValue, decode_wire, encode_wire
from parallax.snapshot.handle._family import declaring as declaring_of
from parallax.snapshot.handle._predicate_writes import buffer_predicate_instruction
from parallax.snapshot.handle._write_inputs import (
    BufferedInserts,
    KeyedWriteValueError,
    admit_and_buffer,
    cancels_a_pending_assignment,
    keyed_instruction,
    resolve_write_evidence,
    validate_source_pin,
    validate_window,
    written_object_of_row,
)
from parallax.snapshot.materialize import WireEntity, opened_wire_entity, source_hint_of

__all__ = [
    "WireChanges",
    "WirePredicateTarget",
    "WireWriteLane",
    "wire_insert",
    "wire_keyed_write",
    "wire_predicate_write",
]

type WireChanges = Mapping[str, object]
"""A Wire write's authored assignments: declared member names to accepted wire
values. Identity, version, temporal-axis, computed, read-only, and relationship
members are refused rather than assigned. Required wherever a verb's signature
names it — the verbs that name no member are the destructive and close ones,
which take no change set at all.

``{}`` is a stated document, never an absent argument, and what it states
differs by family for the reason the two families differ. A keyed update
addresses one row whose values the source already published, so naming no
member is the ordinary no-op — the same one an empty Typed effective change set
is. A predicate update lowers to the canonical assignment algebra, whose list
must name at least one assignment, so ``{}`` is refused there exactly as
``tx.update_where(query)`` with no assignments is."""

type WirePredicateTarget = Mapping[str, object]
"""A Wire predicate write's target: exactly ``{"entity", "predicate"}``, the
canonical selection shape — never an Object Query, because ordering, the cap,
temporal selection, result narrowing, and Include Paths all shape a RESULT and a
set-based write has none to shape."""

_UPDATE_MUTATIONS = frozenset({"update", "updateUntil"})

_VoContainer = ValueObjectMetadata | NestedValueObjectMetadata

_DeclaredMember = AttributeMetadata | ValueObjectMetadata


@dataclass(frozen=True, slots=True)
class WireWriteLane:
    """The transaction state a Wire write verb reads, and nothing wider.

    ``inserts`` is the SAME ledger the Typed verbs record into, which is what
    makes a Typed insert followed by a Wire update of one object — and the
    reverse — one read-your-own-writes pair rather than two ingresses each with
    their own idea of what this transaction stores.

    ``model`` carries the accepted metadata every verb here resolves against and
    the layouts a materializing predicate write converts its resolved rows
    through as one value, so this lane names one model rather than two halves
    that could disagree.
    """

    model: CatalogedModel
    uow: UnitOfWork
    conn: DbPort
    attempt: TransactionAttemptActivity
    inserts: BufferedInserts
    lifecycle: InstalledLifecycle | None


def _wire_bound(value: dt.datetime | None) -> str | None:
    return None if value is None else cast("str", encode_wire(TIMESTAMP, value))


def wire_insert(
    lane: WireWriteLane,
    entity_name: str,
    data: Mapping[str, object],
    *,
    mutation: KeyedMutation,
    valid_from: dt.datetime | None = None,
    until: dt.datetime | None = None,
) -> WireEntity:
    """Buffer a Wire ``insert`` / ``insertUntil`` of ``data`` under
    ``entity_name``, and answer the frozen node it opened.

    An opening row has no source to infer a concrete Entity from, which is why
    this verb — alone among the keyed family — takes the Entity spelling: there
    is no prior observation, no hint, and nothing else that could say which
    Entity a fresh document is a document OF.

    ``data`` is the Create Payload in accepted wire spellings, and its own shape
    is the first thing judged: a payload that is no document is refused before
    the Entity spelling is resolved, so a call that states neither hears about
    the payload. A framework-owned member is refused rather than stored: the
    interval bounds are stamped at flush from the Clock Strategy and the version
    is derived, exactly as the Typed Entity constructor refuses a caller-authored
    one. A value a Wire read published is refused too — it names a row this store
    already holds, and ``tx.wire.update`` is the verb for that — under the
    Identity the resolved Entity spelling supplies.

    The returned node is what closes the one Typed/Wire parity gap on the write
    surface: ``tx.insert(a)`` leaves the Typed caller holding ``a``, so a pure
    Wire caller must be handed something too or it can never revise the row it
    just opened. What it publishes is the buffered ROW rather than the payload —
    a ``many`` the payload left out is answered as the empty collection that row
    stores — so writing a member back off it is the restoration it is off a read
    result. It carries a Source Hint naming the object and this
    transaction's participation and NO observation, which is exactly what an
    opening row has observed — the write off it is licensed by the buffered
    insert instead, through the ledger this call records into, and the two
    coalesce.
    """
    refuse_reentry(lane.lifecycle)
    payload = _authored_document(data, f"a Wire `{mutation}` payload")
    entity = instructions.resolve_target(lane.model.meta, entity_name)
    _refuse_published_source(entity, data, mutation)
    declaring = declaring_of(lane.model.meta, entity)
    valid_from_managed, until_managed = validate_window(declaring, mutation, valid_from, until)
    _refuse_framework_owned(lane.model.meta, entity, payload)
    authored = keyed_instruction(
        mutation,
        entity.identity,
        payload,
        valid_from=_wire_bound(valid_from_managed),
        until=_wire_bound(until_managed),
    )
    prepared = instructions.prepare_wire_write(authored, lane.model.meta)
    assert isinstance(prepared, PreparedKeyedWrite)
    row = prepared.rows[0]
    admit_and_buffer(lane.uow, lane.model.meta, prepared, None)
    lane.inserts.record(written_object_of_row(entity, declaring, row))
    opened = object_key(prepared, lane.model.meta)
    # A Create Payload is a complete document, so the row it buffers always
    # names its own object by the time validation has admitted it.
    assert opened is not None
    return opened_wire_entity(
        lane.model.meta,
        entity.identity,
        row,
        SourceHint(
            entity=entity.identity,
            object_key=opened,
            participation=lane.uow.participation,
            observation=None,
        ),
    )


def wire_keyed_write(
    lane: WireWriteLane,
    mutation: KeyedMutation,
    observed: object,
    changes: WireChanges | None = None,
    *,
    valid_from: dt.datetime | None = None,
    until: dt.datetime | None = None,
) -> None:
    """Buffer a Wire keyed write against the state ``observed`` came from.

    ``observed`` is a frozen Entity mapping a Parallax Wire read published; its
    private Source Hint supplies the concrete Entity, the object the write
    addresses, the pin the read stood at, and the evidence the target Entity's
    Effective Concurrency Strategy weighs. ``changes`` is the authored
    assignment document for the update family and absent for the destructive
    and close verbs, which key off the source alone.

    The fixed order is the whole contract: the change document's own shape,
    then source shape, the finite Transaction-Time refusal, the window, then
    every named member's legality and value — all before the strategy is derived
    or any evidence resolved. Shape leads because it is the one question that
    needs neither the source nor the model, so a call that states no document
    hears that rather than a provenance complaint about its other argument. A
    write whose every named member already holds the value the source published
    is the ordinary no-op, dropped before the evidence question is asked at all,
    exactly as an empty Typed effective change set is.
    """
    refuse_reentry(lane.lifecycle)
    authored = _authored_changes(mutation, changes)
    source, hint = _keyed_source(mutation, observed)
    record = _concrete_entity(lane.model.meta, hint)
    declaring = declaring_of(lane.model.meta, record)
    validate_source_pin(record.identity, hint.pin)
    valid_from_managed, until_managed = validate_window(declaring, mutation, valid_from, until)
    identity_row = dict(hint.object_key.primary_key)
    authored_identity = {name: source[name] for name in identity_row}
    raw_instruction = keyed_instruction(
        mutation,
        record.identity,
        {**authored_identity, **authored},
        valid_from=_wire_bound(valid_from_managed),
        until=_wire_bound(until_managed),
    )
    prepared = instructions.prepare_wire_write(
        raw_instruction,
        lane.model.meta,
        assigned_members=frozenset(authored),
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    buffer_prepared_keyed_write(lane, observed, prepared, frozenset(authored))


def buffer_prepared_keyed_write(
    lane: WireWriteLane,
    observed: object,
    prepared: PreparedKeyedWrite,
    assigned_members: frozenset[str],
) -> None:
    """Buffer a prepared keyed instruction against a published Wire source.

    This is the representation-neutral tail of :func:`wire_keyed_write`. The
    instruction producer has already normalized and judged the authored row;
    this seam retains production ownership of source validation, effective
    changes, evidence, claims, and buffering.
    """
    refuse_reentry(lane.lifecycle)
    mutation = prepared.mutation
    source, hint = _keyed_source(mutation, observed)
    record = _concrete_entity(lane.model.meta, hint)
    declaring = declaring_of(lane.model.meta, record)
    validate_source_pin(record.identity, hint.pin)
    identity_row = dict(hint.object_key.primary_key)
    members = _row_members(lane.model.meta, record)
    managed_assignments = {name: prepared.rows[0][name] for name in assigned_members}
    row, restorations = _authored_row(
        lane, record, hint, mutation, identity_row, members, managed_assignments, source
    )
    if row is None:
        return
    prepared = instructions.derive_keyed_write(prepared, (row,))
    written = written_object_of_row(record, declaring, identity_row)
    evidence: SettledEvidence | None = (
        None
        if lane.inserts.holds(written)
        else resolve_write_evidence(
            lane.model.meta,
            record,
            hint,
            mutation=mutation,
            object_key=hint.object_key,
            preference=lane.uow.settings.concurrency,
            participation=lane.uow.participation,
        )
    )
    admit_and_buffer(lane.uow, lane.model.meta, prepared, evidence, restorations=restorations)


def wire_predicate_write(
    lane: WireWriteLane,
    mutation: PredicateMutation,
    target: WirePredicateTarget,
    changes: WireChanges | None = None,
    *,
    valid_from: dt.datetime | None = None,
    until: dt.datetime | None = None,
) -> None:
    """Buffer a Wire predicate-selected write over ``target``.

    The Wire spelling of the ``_where`` family: the canonical ``{entity,
    predicate}`` selection plus an authored changes document, lowered to the
    SAME :class:`~parallax.core.unit_work.PredicateWrite` the Typed verbs build
    and handed to the one seam that dispatches readless or materializing. No
    second set-based write semantics are introduced — this ingress only states
    the target and the assignments differently.

    Both caller documents are captured and judged for shape before anything is
    resolved from the model, the same lead the keyed verb gives them — and a
    selection's shape runs to the bottom of its predicate, so a malformed node
    is `m-predicate`'s own refusal rather than whatever the model happens to say
    about the Entity, the window, or the assignments beside it. The Entity is
    then resolved HERE rather than left to the instruction build, because the
    temporal bounds are rendered against the target's own declaring Entity and a
    bound has to be canonical from the moment the instruction exists.
    """
    refuse_reentry(lane.lifecycle)
    selection = _authored_document(target, "a predicate-selected write's canonical target")
    entity_name = _selection_shape(selection)
    authored = _authored_changes(mutation, changes)
    entity = instructions.resolve_target(lane.model.meta, entity_name)
    declaring = declaring_of(lane.model.meta, entity)
    valid_from_managed, until_managed = validate_window(declaring, mutation, valid_from, until)
    members = _row_members(lane.model.meta, entity)
    unknown = sorted(set(authored) - set(members))
    if unknown:
        raise instructions.WriteInstructionError(
            f"{entity.identity.canonical}: assignments name undeclared members {unknown}"
        )
    doc: dict[str, object] = {
        "mutation": mutation,
        "target": selection,
    }
    if authored:
        doc["assignments"] = [
            {"attr": f"{entity.identity.canonical}.{member}", "value": value}
            for member, value in authored.items()
        ]
    if valid_from_managed is not None:
        doc["validFrom"] = _wire_bound(valid_from_managed)
    if until_managed is not None:
        doc["until"] = _wire_bound(until_managed)
    instruction = instructions.deserialize(doc)
    assert isinstance(instruction, PredicateWrite)  # a `target` document always builds this shape
    prepared = instructions.prepare_wire_write(instruction, lane.model.meta)
    assert isinstance(prepared, PreparedPredicateWrite)
    buffer_predicate_instruction(lane.uow, lane.model, lane.conn, prepared, lane.attempt)


def _authored_row(
    lane: WireWriteLane,
    record: EntityMetadata,
    hint: SourceHint,
    mutation: KeyedMutation,
    identity_row: Mapping[str, object],
    members: Mapping[str, _DeclaredMember],
    assignments: Mapping[str, object],
    observed: WireEntity,
) -> tuple[dict[str, object] | None, frozenset[str]]:
    """What this write buffers, and the members its author put back — or
    ``None`` for a write that buffers nothing at all.

    The Wire peer of the Typed lane's effective change set, computed against the
    source rather than against a Change Record: a named member whose authored
    value already equals what the source published was touched and restored, and
    the rest are the effective changes. Comparison is over DECODED values, so a
    caller writing back what a read handed it is a no-op whatever spelling it
    used — an occurrence authored short of a nested ``many`` included, because
    that member has no absent state and both sides decode to the ``[]`` the store
    holds (:func:`_decoded_document`).

    A destructive or close verb names no member and always buffers its identity
    row. An update whose effective set is empty buffers nothing — the
    zero-round-trip no-op — unless it cancels an assignment this transaction has
    already buffered at the same claim scope, where it buffers the identity row
    alone and the merged write is eliminated instead.
    """
    if mutation not in _UPDATE_MUTATIONS:
        return dict(identity_row), frozenset()
    effective: dict[str, object] = {}
    restored: set[str] = set()
    for member, value in assignments.items():
        # Every assigned member resolved: `_judged_changes` refused the rest.
        if value == freeze_retained_value(
            _decoded_member(
                members[member], observed.get(member), f"{record.identity.canonical}.{member}"
            )
        ):
            restored.add(member)
            continue
        effective[member] = value
    restorations = frozenset(restored)
    if effective:
        return {**identity_row, **effective}, restorations
    if not restorations or not cancels_a_pending_assignment(
        lane.uow, lane.model.meta, record, hint, mutation
    ):
        return None, restorations
    return dict(identity_row), restorations


def _keyed_source(mutation: KeyedMutation, observed: object) -> tuple[WireEntity, SourceHint]:
    """``observed`` and its own Source Hint, or refuse the value as a keyed source.

    One refusal covers every non-source a caller can reach for — an ordinary
    mapping, ``dict(node)``, a JSON or pickle round trip, an
    :class:`~parallax.snapshot.materialize.InvalidData` wrapper, and the ``None``
    a non-hydrating root publishes in place of data — because they differ only
    in how the provenance was lost. A hydratable invalid root's ``data`` is an
    ordinary published node and passes: classification says what contradicted
    the model, never who may write.
    """
    hint = source_hint_of(observed) if isinstance(observed, WireEntity) else None
    if hint is None:
        raise instructions.WriteInstructionError(
            f"a keyed `{mutation}` on `tx.wire` takes a frozen Entity mapping a Parallax Wire "
            f"read published, and {type(observed).__name__} carries no such provenance — an "
            "ordinary mapping, a `dict(...)` conversion, and a serialized round trip all lose "
            "the identity and evidence a keyed write is addressed and licensed by; read the row "
            "through `tx.wire.find` and write what it returned"
        )
    assert isinstance(observed, WireEntity)  # a hint rides an Entity node alone
    return observed, hint


def _concrete_entity(meta: Metamodel, hint: SourceHint) -> EntityMetadata:
    """The accepted Metadata for the concrete Entity the source's read resolved.

    A hint names the row's OWN Entity — the per-row answer under
    table-per-hierarchy — so a write off a polymorphic level's node addresses the
    concrete type that row is, never the position the query targeted.
    """
    record = meta.entity(hint.entity)
    if record is None:  # pragma: no cover - a hint is filed by a read of THIS model
        raise instructions.WriteInstructionError(
            f"{hint.entity.canonical}: the source was published by a read of another model"
        )
    return record


def _selection_shape(target: Mapping[str, object]) -> str:
    """The Entity spelling ``target`` states, refusing anything but the canonical
    selection shape.

    Judged whole before the model is consulted, which is why the predicate node
    is deserialized here and not left to the instruction build: a selection that
    states no well-formed predicate has stated no target, and answering it with
    an unknown-Entity, inadmissible-bound, or illegal-assignment verdict would
    report the defect the fixed order places later. The node is `m-predicate`'s
    to judge — the same serde the instruction build reaches for the identical
    document — so a malformed one carries that module's
    :class:`~parallax.core.predicate.CanonicalDocumentError` while the selection
    envelope around it stays this verb's own verdict.

    Reads the CAPTURED target, whose keys :func:`_authored_document` has already
    judged to be names, so the two key sets below compare and sort rather than
    raising about their own contents.
    """
    extra = sorted(set(target) - {"entity", "predicate"})
    if extra or "entity" not in target or "predicate" not in target:
        raise instructions.WriteInstructionError(
            "a predicate-selected write target carries exactly `entity` and `predicate` "
            f"(an Object Query's own clauses shape a result, and a set-based write has none); got "
            f"{sorted(target)}"
        )
    name = target["entity"]
    if not isinstance(name, str) or not name:
        raise instructions.WriteInstructionError(
            "predicate write: `target.entity` must be a non-empty entity name"
        )
    node = target["predicate"]
    if not isinstance(node, Mapping):
        raise instructions.WriteInstructionError(
            "predicate write: `target.predicate` must be a mapping"
        )
    predicate_algebra.deserialize(cast("Mapping[str, object]", node))
    return name


def _refuse_published_source(entity: EntityMetadata, data: object, mutation: KeyedMutation) -> None:
    """Refuse an insert whose payload is a value a Wire read published.

    The Wire peer of the Typed provenance refusal, under the same code: a node a
    read returned names a row this store already holds, so the verb that writes
    it is ``tx.wire.update``. It follows the payload's own shape judgement and
    the Entity spelling's resolution — shape leads because a call that states no
    document hears that first, and the Identity this verdict carries is the
    resolved one — and precedes every judgement about the payload's MEMBERS, so
    a published value is refused as one rather than measured member by member.
    """
    if isinstance(data, WireEntity) and source_hint_of(data) is not None:
        raise KeyedWriteValueError(
            code="write-value-already-stored",
            message=(
                f"{entity.identity.canonical}: {mutation!r} was handed a value this store's own "
                "read produced, so the row it names is already stored; write the change with "
                "`tx.wire.update(value, {...})`"
            ),
            identity=entity.identity,
        )


def _refuse_framework_owned(
    meta: Metamodel, entity: EntityMetadata, row: Mapping[str, object]
) -> None:
    """Refuse an insert payload naming a framework-owned member.

    The interval bounds come from the Clock Strategy at flush and the version is
    derived from the observation a later write's source retained, so neither is
    ever caller data (ADR 0010/0013). The Typed peer of this refusal is the
    Entity constructor's, which is why a Typed insert never reaches it.
    """
    members = _row_members(meta, entity)
    for member in row:
        declared = members.get(member)
        if isinstance(declared, AttributeMetadata) and declared.framework_owned:
            raise instructions.WriteInstructionError(
                f"{entity.identity.canonical}.{member}: framework-owned fields may not be "
                "assigned — the interval bounds are stamped from the Clock Strategy and the "
                "optimistic-lock version is derived"
            )


def _declared_row_members(meta: Metamodel, entity: EntityMetadata) -> Sequence[_DeclaredMember]:
    position = inheritance.view(meta).entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return ()
    return (*position.applicable_attributes, *position.applicable_value_objects)


def _row_members(meta: Metamodel, entity: EntityMetadata) -> Mapping[str, _DeclaredMember]:
    """``entity``'s family-effective row members, by the name a write spells.

    Family-effective rather than local for the reason every other write-side
    member resolution is: a family's key and version columns are declared on the
    root alone, and a concrete-subtype write names them exactly as it names its
    own. Resolved once per call and threaded, so the legality judgement, the
    effective-change comparison, and the decode all read one answer.
    """
    return {_member_name(member): member for member in _declared_row_members(meta, entity)}


def _member_name(member: _DeclaredMember) -> str:
    if isinstance(member, AttributeMetadata):
        return member.identity.name
    return member.identity.path[-1]


def _decoded_member(member: _DeclaredMember, value: object, path: str) -> object:
    if value is None:
        return None
    if isinstance(member, AttributeMetadata):
        return _decoded_leaf(member.type, value, path)
    return _decoded_occurrence(member, value, path)


def _decoded_leaf(neutral_type: NeutralType, value: object, path: str) -> object:
    try:
        return decode_wire(neutral_type, cast("WireValue", value))
    except WireDecodingError as error:
        raise instructions.InstructionRejectedError(
            f"neutral-literal-{error.reason}", f"{path}: {error}"
        ) from error


def _decoded_occurrence(occurrence: _VoContainer, value: object, path: str) -> object:
    if occurrence.multiplicity is Multiplicity.MANY:
        if not isinstance(value, Sequence) or isinstance(value, str | bytes):
            return value
        return [
            _decoded_document(occurrence, element, f"{path}[{index}]")
            for index, element in enumerate(cast("Sequence[Any]", value))
        ]
    return _decoded_document(occurrence, value, path)


def _decoded_document(container: _VoContainer, value: object, path: str) -> object:
    if not isinstance(value, Mapping):
        return value
    attributes = {attribute.identity.name: attribute for attribute in container.attributes}
    occurrences = {nested.identity.path[-1]: nested for nested in container.value_objects}
    decoded: dict[str, object] = {}
    for key, nested in cast("Mapping[str, object]", value).items():
        child_path = f"{path}.{key}"
        if (attribute := attributes.get(key)) is not None:
            decoded[key] = (
                None if nested is None else _decoded_leaf(attribute.type, nested, child_path)
            )
        elif (occurrence := occurrences.get(key)) is not None:
            decoded[key] = (
                None if nested is None else _decoded_occurrence(occurrence, nested, child_path)
            )
        else:
            decoded[key] = nested
    return _with_zero_state_occurrences(decoded, container.value_objects)


def _with_zero_state_occurrences(
    decoded: dict[str, object], occurrences: Iterable[_VoContainer]
) -> dict[str, object]:
    """``decoded`` plus the empty collection at every ``many`` it does not name.

    A ``many`` is the one occurrence a complete document may leave out, because it
    has no absent state: omission and an empty collection are the two authored
    spellings of one zero value, and ``[]`` is what a write stores for both, at
    every depth and under either Storage Layout. Naming one as an explicit null is
    refused rather than read as that zero — the model gives a ``many`` no null
    state — so a null reaching here is left as authored for the assignment
    judgement to name. The AUTHORED spellings are the two above; which spellings a
    stored document has for the same zero is the read side's question
    (`m-snapshot-read` *What a materialized value carries*), and the two sets differ
    by the JSON null the codec reads on the way out and no author may write.

    Supplying the omitted zero is what makes the decoded document the document the
    row will hold: otherwise an author who omits the member writes DML against a
    row already holding that zero, and the node an insert answers omits a key its
    own buffered row stores.
    """
    for occurrence in occurrences:
        name = occurrence.identity.path[-1]
        if occurrence.multiplicity is Multiplicity.MANY and name not in decoded:
            decoded[name] = []
    return decoded


def _authored_document(value: object, described: str) -> Mapping[str, object]:
    """Return a shape-validated Wire document without taking ownership yet."""
    if not isinstance(value, Mapping):
        raise instructions.WriteInstructionError(
            f"{described} must be a document of names to values, got {type(value).__name__}"
        )
    document = cast("Mapping[str, object]", value)
    _validate_authored(document, described, ())
    return document


def _authored_changes(mutation: KeyedMutation, changes: WireChanges | None) -> Mapping[str, object]:
    """Return validated assignments, or the empty set a destructive verb states."""
    if changes is None and mutation not in _UPDATE_MUTATIONS:
        return {}
    return _authored_document(changes, f"a Wire `{mutation}`'s change set")


def _validate_authored(value: object, described: str, enclosing: tuple[int, ...]) -> None:
    if isinstance(value, Mapping):
        mapping = cast("Mapping[str, object]", value)
        ancestry = _entered_ancestry(mapping, described, enclosing)
        for key, nested in mapping.items():
            _document_key(key, described)
            _validate_authored(nested, described, ancestry)
        return
    if isinstance(value, list | tuple):
        sequence = cast("Sequence[object]", value)
        ancestry = _entered_ancestry(sequence, described, enclosing)
        for nested in sequence:
            _validate_authored(nested, described, ancestry)


def _entered_ancestry(
    container: object, described: str, enclosing: tuple[int, ...]
) -> tuple[int, ...]:
    """``enclosing`` extended by ``container``, refusing one that already
    encloses itself. Identity-based, and sound because every container on the
    path is held alive by the caller's own value for the whole walk."""
    address = id(container)
    if address in enclosing:
        raise instructions.WriteInstructionError(
            f"{described} contains itself, so it states no finite document"
        )
    return (*enclosing, address)


def _document_key(key: object, described: str) -> str:
    if not isinstance(key, str):
        raise instructions.WriteInstructionError(
            f"{described} is keyed by names, and {key!r} is not one"
        )
    return key
