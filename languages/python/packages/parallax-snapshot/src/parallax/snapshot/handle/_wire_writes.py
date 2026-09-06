"""``parallax.snapshot.handle._wire_writes`` — the Wire write representation (spec §5).

What ``tx.wire``'s write verbs state differently from their Typed peers, and
nothing else. What a keyed verb here OWNS is one source and one call: the order
every keyed write runs — re-entry, source, pin, window, preparation, effective
changes, the buffered-insert exemption, evidence, claim, and buffer — belongs to
:mod:`parallax.snapshot.handle._keyed_writes`, and what this module supplies is
the Wire Keyed Write Source and Keyed Insert Source, plus the one the conformance
conflict lane enters through. The predicate-selected verb keeps a composition of
its own, because a materializing set-based write runs a resolving read no keyed
write does.

What is representation-specific is only how a write's TARGET and its VALUES are
stated: a Typed verb takes an Entity value whose Change Record already names the
effective change, and a Wire verb takes the frozen mapping Parallax published
for the row plus an explicit changes document. Everything after that — the evidence
resolver, the claim, the instruction IR, the buffer, the planner, the observed
lifecycle — is the one pipeline both share, which is why a Typed write and a
Wire write of one object coalesce.

Three rules give the Wire sources their shape.

**A keyed source is a hinted node Parallax published, and nothing else.** Two
doors publish one, and they differ in the evidence their node carries: a Wire
read, whose node carries the observation of the state it saw, and a Wire insert,
whose node carries none because the row it opened had observed nothing — the
buffered insert licenses the write that follows instead. There is no
explicit-Entity ordinary-mapping overload: the concrete Entity, the object, the
participation, the as-of pin, and the observation all come from the source's own
private Source Hint, so a mapping a caller built, converted with ``dict(...)``,
or round-tripped through JSON or pickle carries none of them and is refused
before any evidence is resolved. That refusal is why a Wire keyed write's
provenance answer is always ``"this"``: the values a source could be refused for
having come from never reach the question.

**An authored document's own shape is judged at capture, before anything it is
stated beside.** It needs neither a source nor the model, so it leads: a call
that states no document hears that rather than a complaint about its other
argument, and a selection's shape runs all the way through the predicate node
`m-predicate`'s algebra admits. Every judgement about a MEMBER waits for the
window, as the Keyed Write Validation Order places it.

Malformed Wire input therefore always earns a static refusal rather than a
:class:`~parallax.snapshot.handle.WriteEvidenceError`, whichever is also true.
Which static refusal follows from whose rule was broken:
:class:`~parallax.core.unit_work.WriteInstructionError` is this representation's
own verdict — input that states no well-formed write — while a rule another
module owns keeps that module's classification, so one input is classified one
way at every boundary that accepts it. Those are the closed pre-SQL
:class:`~parallax.core.unit_work.WriteRejectedError` vocabulary for a normative
payload rule, `m-predicate`'s
:class:`~parallax.core.predicate.CanonicalDocumentError` for a malformed
predicate node, and `m-core`'s :class:`~parallax.core.base.InstantError` for a
bound that is no instant. All are ``ValueError``s raised before the evidence
question.

**Both sides of a restoration pass through one decode, and only one is judged.**
What a caller authored and what the source published under those same names are
converted by the one Wire decode, so the ingress weighs effectiveness over one
carrier per value and no source decides its own. Judgement is asked of the
authored side alone, because every rule preparation applies is a rule about what
the caller states in THIS call, and the published side states nothing in it: it
is the state the write is addressed against, admitted already at the door that
published it. The two doors admit on different terms — a read owes the accepted
model nothing, which is why the correction of a row it published as a hydratable
classified record has to reach the buffer, while an insert judged its payload in
full before answering the node it opened — and re-judging either here would
refuse a write for the state that write revises. Caller-owned input is owned by preparation before
the verb returns: shape is validated without copying, and preparation converts
and freezes the retained product in one traversal. A keyed source is already
deeply frozen; the write retains only its identity, resolved evidence, and
explicitly changed published values.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from parallax.core import inheritance
from parallax.core import predicate as predicate_algebra
from parallax.core.base import TIMESTAMP
from parallax.core.db_port import DbPort
from parallax.core.execution_lifecycle._activity import (
    TransactionAttemptActivity,
    refuse_reentry,
)
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
    ValueObjectMetadata,
)
from parallax.core.unit_work import (
    KeyedMutation,
    PredicateMutation,
    PredicateWrite,
    SourceHint,
    instructions,
)
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedTemporalBounds,
)
from parallax.core.wire import encode_wire
from parallax.snapshot.handle._family import declaring as declaring_of
from parallax.snapshot.handle._keyed_writes import (
    KeyedWriteContext,
    PreparedSourceWrite,
    ResolvedKeyedInsert,
    ResolvedKeyedWriteSource,
    keyed_insert,
    keyed_write,
    retained,
)
from parallax.snapshot.handle._predicate_writes import buffer_predicate_instruction
from parallax.snapshot.handle._write_inputs import (
    UPDATE_MUTATIONS,
    keyed_instruction,
    reject_temporal_delete,
    validate_window,
)
from parallax.snapshot.materialize import WireEntity, opened_wire_entity, source_hint_of

__all__ = [
    "PreparedWireKeyedWriteSource",
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

_DeclaredMember = AttributeMetadata | ValueObjectMetadata


@dataclass(frozen=True, slots=True)
class WireWriteLane:
    """The transaction state a Wire write verb reads, and nothing wider.

    ``keyed`` is the SAME ``KeyedWriteContext`` this transaction's Typed verbs
    read — one accepted model, one unit of work, one buffered-insert ledger, one
    installed lifecycle. That the ledger is one is what makes a Typed insert
    followed by a Wire update of one object, and the reverse, one
    read-your-own-writes pair rather than two ingresses each with their own idea
    of what this transaction stores; that the model is one is what stops a lane
    resolving metadata against a model its Typed peer does not use. The
    predicate verb here reads three of the four for the same reason, so the four
    are stated once rather than restated per lane.

    The connection and the attempt sit beside that record rather than inside it
    because only the predicate-selected lane reads either: a materializing
    set-based write runs a resolving read of its own, and no keyed write reads at
    all.
    """

    keyed: KeyedWriteContext
    conn: DbPort
    attempt: TransactionAttemptActivity


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
    A value this store already published is refused too, whether a read published
    it or an earlier insert did — it names a row this store already holds, and
    ``tx.wire.update`` is the verb for that — under the Identity the resolved
    Entity spelling supplies.

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
    opened = keyed_insert(
        lane.keyed,
        WireKeyedInsertSource(entity_name, data),
        mutation,
        valid_from=valid_from,
        until=until,
    )
    return opened_wire_entity(lane.keyed.model.meta, opened.identity, opened.row, opened.hint)


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

    ``observed`` is a frozen Entity mapping Parallax published for the row, from
    a read or from the insert that opened it; its private Source Hint supplies
    the concrete Entity, the object the write addresses, the pin the source
    stands at, and the evidence the target Entity's Effective Concurrency
    Strategy weighs. ``changes`` is the authored
    assignment document for the update family and absent for the destructive
    and close verbs, which key off the source alone.

    The order is the Keyed Write Validation Order, which this verb enters rather
    than states: the change document's own shape, then the source, its pin, the
    verb's applicability to a target that milestones its rows, the window, and
    only then every named member's legality and value — all before the strategy
    is derived or any evidence resolved. A write whose every named member already
    holds the value the source published is the ordinary no-op, dropped before the
    evidence question is asked at all, exactly as an empty Typed effective change
    set is.
    """
    keyed_write(
        lane.keyed,
        WireKeyedWriteSource(observed, changes),
        mutation,
        valid_from=valid_from,
        until=until,
    )


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
    bound has to be canonical from the moment the instruction exists — and
    ``delete_where``, which offers no bound to render, hears the target's
    verdict on the VERB before the window gate is reached at all, exactly as the
    Typed ``_where`` lane does.
    """
    refuse_reentry(lane.keyed.lifecycle)
    selection = _authored_document(target, "a predicate-selected write's canonical target")
    entity_name = _selection_shape(selection)
    authored = _authored_changes(mutation, changes)
    entity = instructions.resolve_target(lane.keyed.model.meta, entity_name)
    declaring = declaring_of(lane.keyed.model.meta, entity)
    reject_temporal_delete(entity, declaring, mutation, surface="predicate")
    valid_from_managed, until_managed = validate_window(declaring, mutation, valid_from, until)
    members = _row_members(lane.keyed.model.meta, entity)
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
    prepared = instructions.prepare_wire_write(instruction, lane.keyed.model.meta)
    assert isinstance(prepared, PreparedPredicateWrite)
    buffer_predicate_instruction(
        lane.keyed.uow, lane.keyed.model, lane.conn, prepared, lane.attempt
    )


@dataclass(frozen=True, slots=True)
class _WireKeyedSource:
    """A published row narrowed to a keyed source, beside the facts it answers.

    ``node`` and ``hint`` are what the adapter still needs after the ingress has
    the answers: the published values a restoration is measured against, and the
    object the write settles against.
    """

    node: WireEntity
    hint: SourceHint
    resolved: ResolvedKeyedWriteSource


def _resolved_wire_source(
    meta: Metamodel, mutation: KeyedMutation, observed: object
) -> _WireKeyedSource:
    """``observed`` as a keyed source, refusing the value that is none.

    Shared by both Wire keyed adapters, because what a Wire keyed write is stated
    OVER is one thing whether its assignments arrive as a document to prepare or
    as a product already prepared from one.

    Provenance is ``"this"`` and can be nothing else: a hintless argument is
    refused as no source at all, before the question is asked, so every source
    that reaches it is a node this store published — by a read, or by the insert
    that opened the row. The two refusals a Typed value can earn for its
    provenance have no Wire spelling for the same reason.
    """
    node, hint = _keyed_source(mutation, observed)
    record = _concrete_entity(meta, hint)
    return _WireKeyedSource(
        node,
        hint,
        ResolvedKeyedWriteSource(
            entity=record,
            pin=hint.pin,
            hint=hint,
            identity_row=dict(hint.object_key.primary_key),
            provenance="this",
            representation="wire",
        ),
    )


def _prepared_wire_write(
    meta: Metamodel,
    mutation: KeyedMutation,
    entity: EntityMetadata,
    row: Mapping[str, object],
    bounds: PreparedTemporalBounds,
    assigned: frozenset[str] | None,
) -> PreparedKeyedWrite:
    """One authored single-row keyed instruction, decoded and judged by Unit
    Work's sole Wire judgment.

    ``assigned`` names the members whose ASSIGNMENT is judged, and is absent for
    an opening payload, whose members are the row itself rather than assignments
    against one this store already holds.

    The bounds ride the instruction's dimension-explicit fields in the canonical
    spelling the Wire decoder reads, never the row: an As-Of Axis
    endpoint is framework-owned, so a Valid-Time bound is never a member a caller
    could author.
    """
    prepared = instructions.prepare_wire_write(
        keyed_instruction(
            mutation,
            entity.identity,
            row,
            valid_from=_wire_bound(bounds.valid_from),
            until=_wire_bound(bounds.until),
        ),
        meta,
        assigned_members=assigned,
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


def _published_identity(source: _WireKeyedSource) -> dict[str, object]:
    """The object the source names, in the spelling the source published it in.

    The hint's own key names it in MANAGED values, which is what the ledger is
    asked about; the row an instruction is built from is authored, so its identity
    members are read back off the published node under those same names.
    """
    return {name: source.node[name] for name, _value in source.hint.object_key.primary_key}


def _published_originals(
    meta: Metamodel, entity: EntityMetadata, source: _WireKeyedSource, members: frozenset[str]
) -> dict[str, object]:
    """What the source published under ``members``, in the carriers a prepared
    authored row states the same members in.

    A member the published row omits is stated as the null it published nothing
    for, which is exactly the original a restoration of such a member is measured
    against — and is what the row would state back.

    Decoded and judged by nothing: these are the state the write is addressed
    against rather than anything its caller stated in the call, and the door that
    published them settled what admits them. A read owes the accepted model
    nothing, so the row it published as a hydratable classified record is a keyed
    source whose correction has to reach the buffer; an insert judged its payload
    in full before answering the node it opened. Judging either here would refuse
    the write that revises the member.
    """
    published = {
        **_published_identity(source),
        **{name: source.node.get(name) for name in members},
    }
    decoded = instructions.decode_wire_row(published, meta, entity)
    return {name: decoded[name] for name in members}


class WireKeyedWriteSource:
    """The Wire Keyed Write Source: what a published row and an authored change
    document answer the keyed write ingress.

    Inert when constructed and private to one verb call, so nothing it can refuse
    runs before the ingress refuses re-entry. :meth:`capture` judges the one thing
    this representation alone can be wrong about — the change document's own
    shape, which needs neither a source nor the model — and it leads for that
    reason: a call stating no document hears that rather than a complaint about
    its other argument.
    """

    __slots__ = ("_authored", "_changes", "_meta", "_mutation", "_observed", "_source")

    def __init__(self, observed: object, changes: WireChanges | None) -> None:
        self._observed = observed
        self._changes = changes
        self._authored: Mapping[str, object] = {}
        self._source: _WireKeyedSource | None = None
        self._meta: Metamodel | None = None
        self._mutation: KeyedMutation | None = None

    def capture(self, mutation: KeyedMutation, /) -> None:
        self._authored = _authored_changes(mutation, self._changes)

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedWriteSource:
        self._meta = model
        self._mutation = mutation
        self._source = _resolved_wire_source(model, mutation, self._observed)
        return self._source.resolved

    def prepare(
        self, resolved: ResolvedKeyedWriteSource, bounds: PreparedTemporalBounds, /
    ) -> PreparedSourceWrite:
        """The instruction this document authors, beside the source's own originals.

        Both sides run through the SAME decode over the SAME member list — the
        values the caller authored, and the values the source published under
        those same names — so the ingress weighs effectiveness over one carrier
        per value rather than over a decoded document on one side and a managed
        one on the other.

        Only the authored side is judged, because every rule preparation applies
        is a rule about what the CALLER wrote.
        """
        meta, mutation, source = self._retained()
        assigned = frozenset(self._authored)
        authored = {**_published_identity(source), **self._authored}
        instruction = _prepared_wire_write(
            meta, mutation, resolved.entity, authored, bounds, assigned
        )
        return PreparedSourceWrite(
            instruction=instruction,
            object_key=source.hint.object_key,
            originals=_published_originals(meta, resolved.entity, source, assigned),
        )

    def _retained(self) -> tuple[Metamodel, KeyedMutation, _WireKeyedSource]:
        return retained(self._meta), retained(self._mutation), retained(self._source)


class PreparedWireKeyedWriteSource:
    """The conformance bridge's Keyed Write Source: a product already prepared,
    stated over a published row.

    Preparation is an INPUT capability here rather than a stage this adapter
    runs, which is the whole of what makes the conflict lane a source rather than
    a second front door: every other stage — re-entry, the source, its pin, the
    window, the effective change set, the buffered-insert exemption, evidence,
    the claim, and the buffer — runs for it exactly as for a verb a developer
    called.

    :meth:`capture` judges nothing: there is no raw document, only members a
    producer already decoded and named.
    """

    __slots__ = ("_assigned", "_meta", "_observed", "_prepared", "_source")

    def __init__(
        self, observed: object, prepared: PreparedKeyedWrite, assigned: frozenset[str]
    ) -> None:
        self._observed = observed
        self._prepared = prepared
        self._assigned = assigned
        self._source: _WireKeyedSource | None = None
        self._meta: Metamodel | None = None

    def capture(self, mutation: KeyedMutation, /) -> None:
        return None

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedWriteSource:
        self._meta = model
        self._source = _resolved_wire_source(model, mutation, self._observed)
        return self._source.resolved

    def prepare(
        self, resolved: ResolvedKeyedWriteSource, bounds: PreparedTemporalBounds, /
    ) -> PreparedSourceWrite:
        """The product this adapter holds, beside the source's own originals.

        The originals go through the decode that built the product, over the
        members it names as assigned, so the effective change set is the same
        comparison of like with like a verb's own document reaches.
        """
        meta, source = self._retained()
        return PreparedSourceWrite(
            instruction=self._prepared,
            object_key=source.hint.object_key,
            originals=_published_originals(meta, resolved.entity, source, self._assigned),
        )

    def _retained(self) -> tuple[Metamodel, _WireKeyedSource]:
        return retained(self._meta), retained(self._source)


class WireKeyedInsertSource:
    """The Wire Keyed Insert Source: what an Entity spelling and a Create Payload
    answer the ingress's insert door.

    An opening row has no source to infer a concrete Entity from, which is why
    this door alone takes the spelling: there is no prior observation, no hint,
    and nothing else that could say which Entity a fresh document is a document
    OF.

    A payload that is itself a published node answers the view that node carries,
    exactly as its Typed peer answers a pinned instance's. Such a payload has two
    refusals coming at once, and the pin is the one the door states: it names the
    fact that makes the call wrong whatever else is true of the value, where the
    provenance answer names only which verb this particular one belongs to.

    Provenance here has two answers rather than three: a hinted node is one this
    store published, by a read or by an insert this transaction already buffered,
    and anything else is a document a caller built. A value another
    framework-managed lifecycle produced carries no hint THIS lifecycle
    recognizes, so it arrives as the plain document it is.
    """

    __slots__ = ("_data", "_entity_name", "_meta", "_mutation", "_payload")

    def __init__(self, entity_name: str, data: Mapping[str, object]) -> None:
        self._entity_name = entity_name
        self._data = data
        self._payload: Mapping[str, object] = {}
        self._meta: Metamodel | None = None
        self._mutation: KeyedMutation | None = None

    def capture(self, mutation: KeyedMutation, /) -> None:
        self._payload = _authored_document(self._data, f"a Wire `{mutation}` payload")

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedInsert:
        self._meta = model
        self._mutation = mutation
        published = source_hint_of(self._data) if isinstance(self._data, WireEntity) else None
        return ResolvedKeyedInsert(
            entity=instructions.resolve_target(model, self._entity_name),
            pin=None if published is None else published.pin,
            provenance="none" if published is None else "this",
            representation="wire",
        )

    def prepare(
        self, resolved: ResolvedKeyedInsert, bounds: PreparedTemporalBounds, /
    ) -> PreparedKeyedWrite:
        """The row this payload opens.

        The framework-owned refusal leads it: the interval bounds are stamped at
        flush from the Clock Strategy and the version is derived, so neither is
        ever caller data, and a payload naming one is refused as the authoring it
        is rather than measured member by member.
        """
        meta, mutation = self._retained()
        _refuse_framework_owned(meta, resolved.entity, self._payload)
        return _prepared_wire_write(meta, mutation, resolved.entity, self._payload, bounds, None)

    def _retained(self) -> tuple[Metamodel, KeyedMutation]:
        return retained(self._meta), retained(self._mutation)


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
            f"a keyed `{mutation}` on `tx.wire` takes a frozen Entity mapping Parallax "
            f"published — a `tx.wire.find` result, or the node `tx.wire.insert` answered — and "
            f"{type(observed).__name__} carries no such provenance: an ordinary mapping, a "
            "`dict(...)` conversion, and a serialized round trip all lose the identity and "
            "evidence a keyed write is addressed and licensed by; read the row through "
            "`tx.wire.find` and write what it returned"
        )
    assert isinstance(observed, WireEntity)  # a hint rides an Entity node alone
    return observed, hint


def _concrete_entity(meta: Metamodel, hint: SourceHint) -> EntityMetadata:
    """The accepted Metadata for the concrete Entity the source's own hint names.

    A hint names the row's OWN Entity — the per-row answer under
    table-per-hierarchy — so a write off a polymorphic level's node addresses the
    concrete type that row is, never the position the query targeted.
    """
    record = meta.entity(hint.entity)
    if record is None:  # pragma: no cover - a hint is filed under THIS model
        raise instructions.WriteInstructionError(
            f"{hint.entity.canonical}: the source was published by another model"
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
    if changes is None and mutation not in UPDATE_MUTATIONS:
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
