"""``parallax.snapshot.handle._wire_writes`` — the Wire write ingress (spec §5).

The representation-specific half of ``tx.wire``'s write verbs, as free functions
threading the transaction state they read — the shape
:mod:`parallax.snapshot.handle._predicate_writes` established. What is
representation-specific is only how a write's TARGET and its VALUES are stated:
a Typed verb takes an Entity value whose Change Record already names the
effective change, and a Wire verb takes the frozen mapping a Wire read published
plus an explicit changes document. Everything after that — the evidence
resolver, the claim, the instruction IR, the buffer, the planner, the Execution
Log — is the one pipeline both share, which is why a Typed write and a Wire
write of one object coalesce.

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

**Caller-owned input is snapshotted before the verb returns.** Inserted data,
changes, the predicate target, and the temporal bounds are copied recursively at
the call, so later mutation of any nested list or mapping cannot alter buffered
intent. A keyed source is not copied: it is already deeply frozen, and what the
verb retains of it is its identity, its resolved evidence, and — only for the
members the caller explicitly changed — the value it published. Capture is also
where a document's own shape is judged (:func:`_authored_document`), because the
copy is the traversal that would otherwise fail on it.

Wire input is stated in the ACCEPTED wire spellings its serde seam admits
(`m-wire`: one canonical output spelling per Neutral Type, accepted input
spellings as specified at each seam), so every value crosses
:func:`~parallax.core.base.decode_neutral_literal` once here and reaches the
instruction IR as the native carrier every other ingress hands it.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any, cast

from parallax.core import inheritance
from parallax.core import predicate as predicate_algebra
from parallax.core.base import NeutralType, decode_neutral_literal
from parallax.core.db_port import DbPort
from parallax.core.dialect import Dialect
from parallax.core.execution_log import AttemptRecorder
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
from parallax.snapshot.handle._family import declaring as declaring_of
from parallax.snapshot.handle._predicate_writes import buffer_predicate_instruction
from parallax.snapshot.handle._write_inputs import (
    BufferedInserts,
    KeyedWriteValueError,
    admit_and_buffer,
    cancels_a_pending_assignment,
    keyed_instruction,
    resolve_write_evidence,
    validate_keyed_instruction,
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
    """

    meta: Metamodel
    uow: UnitOfWork
    conn: DbPort
    dialect: Dialect
    attempt: AttemptRecorder
    inserts: BufferedInserts


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
    just opened. It carries a Source Hint naming the object and this
    transaction's participation and NO observation, which is exactly what an
    opening row has observed — the write off it is licensed by the buffered
    insert instead, through the ledger this call records into, and the two
    coalesce.
    """
    payload = _authored_document(data, f"a Wire `{mutation}` payload")
    entity = instructions.resolve_target(lane.meta, entity_name)
    _refuse_published_source(entity, data, mutation)
    declaring = declaring_of(lane.meta, entity)
    valid_from_literal, until_literal = validate_window(declaring, mutation, valid_from, until)
    row = _decoded_row(lane.meta, entity, payload)
    _refuse_framework_owned(lane.meta, entity, row)
    instruction = keyed_instruction(
        mutation, entity.identity, row, valid_from=valid_from_literal, until=until_literal
    )
    validate_keyed_instruction(lane.meta, instruction)
    admit_and_buffer(lane.uow, lane.meta, instruction, None)
    lane.inserts.record(written_object_of_row(entity, declaring, row))
    opened = object_key(instruction, lane.meta)
    # A Create Payload is a complete document, so the row it buffers always
    # names its own object by the time validation has admitted it.
    assert opened is not None
    return opened_wire_entity(
        lane.meta,
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
    authored = _authored_changes(mutation, changes)
    source, hint = _keyed_source(mutation, observed)
    record = _concrete_entity(lane.meta, hint)
    declaring = declaring_of(lane.meta, record)
    validate_source_pin(record.identity, hint.pin)
    valid_from_literal, until_literal = validate_window(declaring, mutation, valid_from, until)
    identity_row = dict(hint.object_key.primary_key)
    members = _row_members(lane.meta, record)
    assignments = _judged_changes(lane.meta, record, members, authored)
    row, restorations = _authored_row(
        lane, record, hint, mutation, identity_row, members, assignments, source
    )
    if row is None:
        return
    instruction = keyed_instruction(
        mutation, record.identity, row, valid_from=valid_from_literal, until=until_literal
    )
    validate_keyed_instruction(lane.meta, instruction)
    written = written_object_of_row(record, declaring, identity_row)
    evidence: SettledEvidence | None = (
        None
        if lane.inserts.holds(written)
        else resolve_write_evidence(
            lane.meta,
            record,
            hint,
            mutation=mutation,
            object_key=hint.object_key,
            preference=lane.uow.settings.concurrency,
            participation=lane.uow.participation,
        )
    )
    admit_and_buffer(lane.uow, lane.meta, instruction, evidence, restorations=restorations)


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
    selection = _authored_document(target, "a predicate-selected write's canonical target")
    entity_name = _selection_shape(selection)
    authored = _authored_changes(mutation, changes)
    entity = instructions.resolve_target(lane.meta, entity_name)
    declaring = declaring_of(lane.meta, entity)
    valid_from_literal, until_literal = validate_window(declaring, mutation, valid_from, until)
    assignments = _judged_changes(lane.meta, entity, _row_members(lane.meta, entity), authored)
    doc: dict[str, object] = {
        "mutation": mutation,
        "target": selection,
    }
    if assignments:
        doc["assignments"] = [
            {"attr": f"{entity.identity.canonical}.{member}", "value": value}
            for member, value in assignments.items()
        ]
    if valid_from_literal is not None:
        doc["validFrom"] = valid_from_literal
    if until_literal is not None:
        doc["until"] = until_literal
    instruction = instructions.deserialize(doc)
    assert isinstance(instruction, PredicateWrite)  # a `target` document always builds this shape
    instructions.validate_instruction(instruction, lane.meta)
    buffer_predicate_instruction(
        lane.uow, lane.meta, lane.conn, lane.dialect, instruction, lane.attempt
    )


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
        if value == _decoded_member(members[member], observed.get(member)):
            restored.add(member)
            continue
        effective[member] = value
    restorations = frozenset(restored)
    if effective:
        return {**identity_row, **effective}, restorations
    if not restorations or not cancels_a_pending_assignment(
        lane.uow, lane.meta, record, hint, mutation
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


def _judged_changes(
    meta: Metamodel,
    entity: EntityMetadata,
    members: Mapping[str, _DeclaredMember],
    changes: Mapping[str, object],
) -> dict[str, object]:
    """``changes`` decoded to native carriers, every named member judged.

    Both halves run before anything about concurrency is asked, and both run for
    EVERY named member rather than only the ones that turn out to be effective:
    a caller assigning a primary key or the framework-owned version its exact
    current value has still named a member no write may assign, and answering
    that with silence would make legality depend on the stored state.

    The verdict is
    :func:`~parallax.core.inheritance.validate_write_assignment`'s — the one
    judgement the typed ``.set(...)`` path, ``Entity.edit(**changes)``, and the
    canonical predicate assignment all reach — so a Wire assignment is refused
    for exactly the reasons its Typed peer is.

    Returning only the accepted names is what lets everything downstream index
    ``members`` directly: a change that survives this has a declaration.
    """
    judged: dict[str, object] = {}
    for member, value in changes.items():
        declared = members.get(member)
        if declared is None:
            raise instructions.WriteInstructionError(
                f"{entity.identity.name}: {member!r} does not name a declared member of this "
                "Entity, so no write can assign it"
            )
        decoded = _decoded_member(declared, value)
        try:
            inheritance.validate_write_assignment(meta, entity, member, decoded)
        except inheritance.WriteAssignmentError as exc:
            raise instructions.WriteInstructionError(str(exc)) from exc
        judged[member] = decoded
    return judged


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


def _decoded_row(
    meta: Metamodel, entity: EntityMetadata, data: Mapping[str, object]
) -> dict[str, object]:
    """One authored Wire document as a canonical write row.

    The walk is over the AUTHORED keys rather than the declared members, so a key
    the model declares no member for passes through untouched and the member-name
    honesty gate — rather than a decoding failure — is what names it.
    """
    members = _row_members(meta, entity)
    return {key: _decoded_member(members.get(key), value) for key, value in data.items()}


def _decoded_member(member: _DeclaredMember | None, value: object) -> object:
    """``value`` in ``member``'s declared native carrier.

    Total and nonthrowing, exactly like the seam it delegates to: an absent
    member, a null value, and a value no declared decoding recognizes all pass
    through unchanged, so the judgement that follows is what refuses them and a
    decoding failure never stands in for a type verdict.
    """
    return _decoded(_position_decoder(member), value)


type _Decoder = Callable[[object], object]
"""What one authored position's value crosses, resolved from the model once and
applied to whatever the caller wrote there."""


def _decoded(decoder: _Decoder | None, value: object) -> object:
    """``value`` through ``decoder``, or as authored where there is nothing to
    apply — an absent declaration or a null, neither of which a serde seam has
    anything to say about."""
    return value if value is None or decoder is None else decoder(value)


def _position_decoder(member: _DeclaredMember | None) -> _Decoder | None:
    if member is None:
        return None
    if isinstance(member, AttributeMetadata):
        return partial(_decoded_leaf, member.type)
    return partial(_decoded_occurrence, member)


def _decoded_leaf(neutral_type: NeutralType, value: object) -> object:
    return decode_neutral_literal(value, neutral_type)


def _decoded_occurrence(occurrence: _VoContainer, value: object) -> object:
    """One present occurrence value: a `many`'s whole ordered replacement, or a
    `one`'s single document."""
    if occurrence.multiplicity is Multiplicity.MANY:
        if not isinstance(value, Sequence) or isinstance(value, str | bytes):
            return value
        return [_decoded_document(occurrence, element) for element in cast("Sequence[Any]", value)]
    return _decoded_document(occurrence, value)


def _decoded_document(container: _VoContainer, value: object) -> object:
    """One occurrence document, decoded over the keys it actually carries.

    Authored-key-driven for :func:`_decoded_row`'s reason, which also makes
    absence structural here: a member the document omits is not a member this
    walk decodes, and an undeclared key inside the document is left exactly as
    authored for the composite judgement to name. A leaf inside an occurrence
    carries its own metadata type rather than an Entity Attribute's, so what the
    two levels share is the resolved decoder rather than the member.

    A nested ``many`` is the one position the authored keys do not decide, because
    it has no absent state: an omitted key, a null, and ``[]`` are three spellings
    of one zero value, and the document this assignment stores carries ``[]`` at
    that position whichever was authored. Decoding it to the empty collection is
    what makes the value compared here the value that will be stored — otherwise
    an author who omits it writes DML against a row already holding that zero, and
    the node an insert answers omits a key its own buffered row stores.
    """
    if not isinstance(value, Mapping):
        return value
    decoders: Mapping[str, _Decoder] = {
        **{
            attribute.identity.name: partial(_decoded_leaf, attribute.type)
            for attribute in container.attributes
        },
        **{
            nested.identity.path[-1]: partial(_decoded_occurrence, nested)
            for nested in container.value_objects
        },
    }
    decoded: dict[str, object] = {
        key: _decoded(decoders.get(key), nested)
        for key, nested in cast("Mapping[str, object]", value).items()
    }
    for nested in container.value_objects:
        name = nested.identity.path[-1]
        if nested.multiplicity is Multiplicity.MANY and name not in decoded:
            decoded[name] = []
    return decoded


def _authored_document(value: object, described: str) -> dict[str, object]:
    """``value`` as one caller-owned Wire document: judged for shape, and copied.

    A Wire document is a mapping of names to values at every depth — the shape
    `m-wire` transports and the shape the instruction IR reads — so the three
    ways a Python value can fail to be one are refused HERE, as
    :class:`~parallax.core.unit_work.WriteInstructionError`, before any member is
    resolved and long before the evidence question: a non-mapping, a key that is
    not a name, and a container that contains itself. Left to the walks
    downstream they would surface as ``AttributeError``, ``TypeError`` from a
    key sort, and ``RecursionError`` — none of which is a verdict on the write.

    Shape and capture are one pass because they are one traversal, and neither
    is a judgement about the model: what this answers is whether a document was
    stated at all, which is the question every judgement after it presupposes.
    """
    if not isinstance(value, Mapping):
        raise instructions.WriteInstructionError(
            f"{described} must be a document of names to values, got {type(value).__name__}"
        )
    return _captured_mapping(cast("Mapping[str, object]", value), described, ())


def _authored_changes(mutation: KeyedMutation, changes: WireChanges | None) -> dict[str, object]:
    """A write's authored assignments, captured — or the empty set a destructive
    or close verb states by naming no member at all.

    Which verb was called is what decides whether ``None`` means anything: a
    ``delete`` / ``terminate`` / ``terminateUntil`` passes no change set and its
    ``None`` is that absence, while the update family's signature requires the
    document, so a ``None`` there is a caller that stated none. Neither an empty
    document nor a falsy value of another type says "no changes": ``{}`` is a
    document that names no member — whose meaning :data:`WireChanges` states,
    and which the two families answer differently — and everything else is a
    document the caller failed to state, which reading as absence would answer
    with a silent no-op instead of a refusal.
    """
    if changes is None and mutation not in _UPDATE_MUTATIONS:
        return {}
    return _authored_document(changes, f"a Wire `{mutation}`'s change set")


def _captured[T](value: T, described: str, enclosing: tuple[int, ...]) -> T:
    """``value`` with every mapping and sequence in it copied, keys judged.

    A verb's captured intent is its own from the moment it returns, so a caller
    that keeps and mutates the document it passed changes nothing about the
    write. Ordinary containers rather than frozen ones, because what leaves here
    is write input the pipeline reads exactly as an instruction document's own
    rows are read; the cost is proportional to authored input alone, and a
    keyed source — already frozen, and never copied — is not among it.

    Copying preserves each container's authored TYPE. Rewriting a tuple as a
    list would be a spelling translation rather than a copy, and it would make
    this the one boundary that admits an array `m-predicate`'s own serde
    refuses: the captured target reaches that serde verbatim, and a laundered
    tuple would be accepted here and rejected for the identical document
    elsewhere.

    ``enclosing`` is the identity of every container on the path to this one,
    which is what makes the walk total over caller-owned input: a container
    reachable from itself is refused rather than descended into. Two siblings
    referencing one document are not a cycle and are copied twice, exactly as a
    caller sharing a subdocument between two members would expect.
    """
    if isinstance(value, Mapping):
        mapping = cast("Mapping[str, object]", value)
        return cast("T", _captured_mapping(mapping, described, enclosing))
    if isinstance(value, list | tuple):
        sequence = cast("Sequence[object]", value)
        ancestry = _entered_ancestry(sequence, described, enclosing)
        elements = [_captured(nested, described, ancestry) for nested in sequence]
        return cast("T", tuple(elements) if isinstance(value, tuple) else elements)
    return value


def _captured_mapping(
    mapping: Mapping[str, object], described: str, enclosing: tuple[int, ...]
) -> dict[str, object]:
    ancestry = _entered_ancestry(mapping, described, enclosing)
    return {
        _document_key(key, described): _captured(nested, described, ancestry)
        for key, nested in mapping.items()
    }


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
