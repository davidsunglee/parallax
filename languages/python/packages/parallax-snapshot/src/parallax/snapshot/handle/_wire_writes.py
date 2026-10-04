from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from typing import cast

from parallax.core import predicate as predicate_algebra
from parallax.core.execution_lifecycle._activity import refuse_reentry
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
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
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedPredicateWrite,
)
from parallax.core.unit_work.retain import InsertionIdentity
from parallax.snapshot.handle._keyed_writes import (
    KeyedWriteContext,
    PreparedSourceWrite,
    ResolvedKeyedInsert,
    ResolvedKeyedWriteSource,
    keyed_insert,
    keyed_instruction,
    keyed_write,
    retained,
)
from parallax.snapshot.handle._predicate_writes import (
    PredicateWriteContext,
    buffer_predicate_instruction,
    buffer_target_instruction,
)
from parallax.snapshot.materialize import WireEntity, opened_wire_entity
from parallax.snapshot.materialize._wire import authoring_of, read_origin_of

__all__ = [
    "WireChanges",
    "WirePredicateTarget",
    "wire_insert",
    "wire_keyed_write",
    "wire_predicate_write",
    "wire_target_write",
]

type WireChanges = Mapping[str, object]
"""A Wire write's authored assignments: declared member names to accepted wire
values. Identity, version, temporal-axis, computed, read-only, and relationship
members are refused rather than assigned, except that a caller-addressed patch's
primary-key entries name the object it writes. Required wherever a verb's signature
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


def wire_insert(
    ctx: KeyedWriteContext,
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
    one. A value this store already published is refused too, whether a read
    published it or an earlier insert did — it names a row this store already
    holds, and ``tx.wire.update`` is the verb for that — under the Identity the
    resolved Entity spelling supplies. So is a fresh payload naming an object
    whose insertion in this transaction still stands, the same payload twice
    included: the provenance rule has nothing to say about a document, and the
    unit of work refuses it once its row is prepared, under the same code,
    advising the update verb of whichever interface OPENED the row — the node
    this verb answered where a Wire insert did, and the instance the caller
    still holds where a Typed one did, which is the only carrier that exists in
    each case.

    The returned node is what closes the one Typed/Wire parity gap on the write
    surface: ``tx.insert(a)`` leaves the Typed caller holding ``a``, so a pure
    Wire caller must be handed something too or it can never revise the row it
    just opened. What it publishes is the buffered ROW rather than the payload —
    a ``many`` the payload left out is answered as the empty collection that row
    stores. It carries the insertion's authority and no Read Origin, since no
    read published it: the writes off it are licensed by that authority, before
    and after a flush, and compose with the insert while it is pending.
    """
    opened = keyed_insert(
        ctx,
        WireKeyedInsertSource(entity_name, data),
        mutation,
        valid_from=valid_from,
        until=until,
    )
    return opened_wire_entity(ctx.model, opened.identity, opened.row, opened.authority)


def wire_keyed_write(
    ctx: KeyedWriteContext,
    mutation: KeyedMutation,
    observed: object,
    changes: WireChanges | None = None,
    *,
    until: dt.datetime | None = None,
) -> None:
    """Buffer a Wire keyed write against the state ``observed`` came from.

    ``observed`` is a frozen Entity mapping Parallax published for the row, from
    a read or from the insert that opened it. A read's private Read Origin
    supplies the concrete Entity, the object the write addresses, the pin the
    source stands at — which is also where a Bitemporal write starts — and the
    evidence the target Entity's Effective Concurrency Strategy weighs. The node
    an insert answered carries that insertion's authority instead, which names
    the object and licenses the write, starting at the insertion's own anchor,
    while it stands. ``changes`` is the authored
    assignment document for the update family and absent for the destructive
    and close verbs, which key off the source alone.

    The order is the Keyed Write Validation Order, which this verb enters rather
    than states: the change document's own shape, then the source and its pin,
    then preparation — the verb's applicability to the target and the window,
    and only then every named member's legality and value — all before the
    strategy is derived or any evidence resolved. A change document naming no
    member is the empty set, dropped before the evidence question is asked at
    all; every member it does name is assigned, whatever value the source
    published for it.
    """
    keyed_write(ctx, WireKeyedWriteSource(observed, changes), mutation, until=until)


def wire_predicate_write(
    ctx: PredicateWriteContext,
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
    about the Entity, the window, or the assignments beside it. The predicate
    parsed there is the one the instruction carries, and each change is an
    assignment owned by the target's own spelling; preparation then judges the
    target, the window, the predicate, and each assignment in authored order.
    """
    refuse_reentry(ctx.keyed.lifecycle)
    selection = _selection_shape(
        _authored_document(target, "a predicate-selected write's canonical target")
    )
    authored = _authored_changes(mutation, changes)
    instruction = PredicateWrite(
        mutation,
        selection,
        tuple(
            WriteAssignment(f"{selection.entity}.{member}", value)
            for member, value in authored.items()
        ),
        valid_from,
        until,
    )
    prepared = instructions.prepare_wire_write(instruction, ctx.keyed.model.meta)
    assert isinstance(prepared, PreparedPredicateWrite)
    buffer_predicate_instruction(ctx, prepared)


def wire_target_write(
    ctx: PredicateWriteContext,
    mutation: TargetMutation,
    entity_name: str,
    document: object,
    *,
    valid_from: dt.datetime | None,
    until: dt.datetime | None,
    if_version: int | None,
    if_tx_start: dt.datetime | None,
) -> None:
    """Buffer a Wire caller-addressed write of the ``entity_name`` object
    ``document`` names by its primary key.

    ``document`` is a patch's change set or a replacement's complete data, in
    accepted wire spellings, and its own shape is judged first. Its primary-key
    entries name the object and are no assignment; every other entry is
    assigned, a framework-owned one refused. The caller's revision arguments are
    its whole condition: nothing ``document`` carries, and no read's evidence,
    stands in for them.
    """
    refuse_reentry(ctx.keyed.lifecycle)
    described = (
        f"a Wire target `{mutation}`'s {'change set' if mutation in UPDATE_MUTATIONS else 'data'}"
    )
    row = _authored_document(document, described)
    instruction = TargetWrite(
        mutation, entity_name, row, if_version, if_tx_start, valid_from, until
    )
    meta = ctx.keyed.model.meta
    buffer_target_instruction(
        ctx, instructions.prepare_wire_write(instruction, meta, authored_members=row.keys())
    )


@dataclass(frozen=True, slots=True)
class _WireKeyedSource:
    """A published row narrowed to a keyed source, beside the facts it answers.

    ``node`` and ``object_key`` are what the adapter still needs after the
    ingress has the answers: the published identity spelling and the object the
    write settles against.
    """

    node: WireEntity
    object_key: ObjectKey
    resolved: ResolvedKeyedWriteSource


def _resolved_wire_source(
    meta: Metamodel, mutation: KeyedMutation, observed: object
) -> _WireKeyedSource:
    """``observed`` as a keyed source, refusing the value that is none.

    Shared by both Wire keyed adapters, because what a Wire keyed write is stated
    OVER is one thing whether its assignments arrive as a document to prepare or
    as a product already prepared from one.

    Provenance is ``"this"`` for a node a read published. The node a Wire
    insert answered was published by no read, so its provenance is
    ``"none"``, which the insertion's standing authority lifts exactly as it
    does for the instance a Typed insert took. Anything else is refused as no
    source at all before the question is asked, so the foreign-lifecycle
    refusal a Typed value can earn has no Wire spelling.
    """
    node, hint, authoring = _keyed_source(mutation, observed)
    key = hint.object_key if hint is not None else authoring.object_key
    record = _concrete_entity(meta, key.entity)
    return _WireKeyedSource(
        node,
        key,
        ResolvedKeyedWriteSource(
            entity=record,
            pin=None if hint is None else hint.pin,
            hint=hint,
            provenance="none" if hint is None else "this",
            representation="wire",
            authoring=authoring if hint is None else None,
        ),
    )


def _prepared_wire_write(
    meta: Metamodel,
    mutation: KeyedMutation,
    entity: EntityMetadata,
    row: Mapping[str, object],
    authored: Set[str],
    *,
    valid_from: dt.datetime | None,
    until: dt.datetime | None,
) -> PreparedKeyedWrite:
    """One authored single-row keyed instruction, decoded and judged by Unit
    Work's sole Wire judgment.

    ``authored`` names the members the caller explicitly wrote — an opening
    payload's keys, judged as insert authoring, or a change document's keys,
    judged as assignments — never the source identity an update's row carries
    beside them.
    """
    prepared = instructions.prepare_wire_write(
        keyed_instruction(mutation, entity.identity, row, valid_from=valid_from, until=until),
        meta,
        authored_members=authored,
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


def _published_identity(source: _WireKeyedSource) -> dict[str, object]:
    """The object the source names, in the spelling the source published it in.

    The source's own key names it in MANAGED values; the row an instruction is
    built from is authored, so its identity members are read back off the
    published node under those same names.
    """
    return {name: source.node[name] for name, _value in source.object_key.primary_key}


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
        self,
        resolved: ResolvedKeyedWriteSource,
        /,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> PreparedSourceWrite:
        """The instruction this document authors: the source's identity plus
        every key the change document states.

        The stated keys are the literal assignment set, whatever the source
        published under them, and only the authored side is judged, because
        every rule preparation applies is a rule about what the CALLER wrote.
        """
        meta, mutation, source = self._retained()
        assigned = self._authored.keys()
        row = {**_published_identity(source), **self._authored}
        instruction = _prepared_wire_write(
            meta, mutation, resolved.entity, row, assigned, valid_from=valid_from, until=until
        )
        return PreparedSourceWrite(
            instruction=instruction,
            object_key=source.object_key,
            assigned=frozenset(assigned),
        )

    def _retained(self) -> tuple[Metamodel, KeyedMutation, _WireKeyedSource]:
        return retained(self._meta), retained(self._mutation), retained(self._source)


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

    Provenance here has two answers rather than three: a node a read published,
    or the node an insert answered, is one this store published, and anything
    else is a document a caller built. A value another framework-managed
    lifecycle produced carries nothing THIS lifecycle recognizes, so it arrives
    as the plain document it is. Whether a plain document names an object whose
    insertion still stands is not a provenance answer at all — its key members
    are canonical only once :meth:`prepare` has run — so the ingress asks the
    unit of work after preparation, and a payload repeated is refused there.
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
        data = self._data
        published = read_origin_of(data) if isinstance(data, WireEntity) else None
        opened = authoring_of(data) if isinstance(data, WireEntity) else None
        return ResolvedKeyedInsert(
            entity=instructions.resolve_target(model, self._entity_name),
            pin=None if published is None else published.pin,
            provenance="none" if published is None and opened is None else "this",
            representation="wire",
        )

    def prepare(
        self,
        resolved: ResolvedKeyedInsert,
        /,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> PreparedKeyedWrite:
        """The row this payload opens, with every payload key judged as the
        caller's authoring: a framework-owned member is refused, because the
        interval bounds are stamped at flush from the Clock Strategy and the
        version is derived."""
        meta, mutation = self._retained()
        return _prepared_wire_write(
            meta,
            mutation,
            resolved.entity,
            self._payload,
            self._payload.keys(),
            valid_from=valid_from,
            until=until,
        )

    def _retained(self) -> tuple[Metamodel, KeyedMutation]:
        return retained(self._meta), retained(self._mutation)


def _keyed_source(
    mutation: KeyedMutation, observed: object
) -> tuple[WireEntity, ReadOrigin | None, InsertionIdentity]:
    """``observed`` with its own Read Origin, or with the insertion authority
    the node a Wire insert answered carries, or refuse the value as a keyed
    source.

    One refusal covers every non-source a caller can reach for — an ordinary
    mapping, ``dict(node)``, a JSON or pickle round trip, an
    :class:`~parallax.snapshot.materialize.InvalidData` wrapper, and every node
    published as diagnostic data under an invalid root. They differ only in how
    the provenance is absent; none can authorize a keyed write.
    """
    hint = read_origin_of(observed) if isinstance(observed, WireEntity) else None
    authoring = authoring_of(observed) if isinstance(observed, WireEntity) else None
    if hint is None and authoring is None:
        raise instructions.WriteInstructionError(
            f"a keyed `{mutation}` on `tx.wire` takes a frozen Entity mapping Parallax "
            f"published — a `tx.wire.find` result, or the node `tx.wire.insert` answered — and "
            f"{type(observed).__name__} carries no such provenance: an ordinary mapping, a "
            "`dict(...)` conversion, and a serialized round trip all lose the identity a "
            "keyed write is addressed by and the evidence or buffered insert that licenses "
            "it; read the row through `tx.wire.find` and write what it returned"
        )
    assert isinstance(observed, WireEntity)  # provenance rides an Entity node alone
    return observed, hint, cast("InsertionIdentity", authoring)


def _concrete_entity(meta: Metamodel, entity: EntityIdentity) -> EntityMetadata:
    """The accepted Metadata for the concrete Entity the source names.

    A source names the row's OWN Entity — the per-row answer under
    table-per-hierarchy — so a write off a polymorphic level's node addresses the
    concrete type that row is, never the position the query targeted.
    """
    record = meta.entity(entity)
    if record is None:  # pragma: no cover - a source is filed under THIS model
        raise instructions.WriteInstructionError(
            f"{entity.canonical}: the source was published by another model"
        )
    return record


def _selection_shape(target: Mapping[str, object]) -> PredicateSelection:
    """The selection ``target`` states, refusing anything but the canonical
    selection shape.

    Judged whole before the model is consulted: a selection that states no
    well-formed predicate has stated no target, and answering it with an
    unknown-Entity, inadmissible-bound, or illegal-assignment verdict would
    report the defect the fixed order places later. The node is `m-predicate`'s
    to judge, so a malformed one carries that module's
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
    return PredicateSelection(
        name, predicate_algebra.deserialize(cast("Mapping[str, object]", node))
    )


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
