from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence, Set
from typing import cast

from parallax.core import predicate as predicate_algebra
from parallax.core._execution._family import family_view
from parallax.core._execution._keyed_writes import (
    PreparedSourceWrite,
    ResolvedKeyedInsert,
    ResolvedKeyedWriteSource,
    TargetRevisionArguments,
    keyed_instruction,
    retained,
)
from parallax.core._execution._options import OMITTED, Omitted
from parallax.core._execution._publication import SelectedWriteModel
from parallax.core._execution._transaction._attempt import TxnAttempt
from parallax.core._execution._unit_work import instructions
from parallax.core._execution._unit_work.instructions import (
    AMEND_MUTATIONS,
    REPLACE_MUTATIONS,
    KeyedMutation,
    PredicateMutation,
    PredicateSelection,
    PredicateWriteInstruction,
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedTargetWrite,
    TargetMutation,
    TargetWriteInstruction,
    WriteAssignment,
)
from parallax.core.execution_lifecycle._activity import refuse_reentry
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.wire import WireValue, decode_wire
from parallax.core.write_plan import ObjectKey
from parallax.snapshot._handle._sources import (
    object_key_from_row,
    resolve_keyed_insert,
    resolve_keyed_write_source,
)
from parallax.snapshot._publication._wire import (
    WireEntity,
    authoring_of,
    opened_wire_entity,
    stored_entity_of,
)

__all__ = [
    "WireChanges",
    "WirePredicateTarget",
    "WirePredicateWriteAdapter",
    "WireTargetWriteAdapter",
    "editable_wire_data",
    "published_entity",
    "wire_insert",
    "wire_keyed_write",
]

type WireChanges = Mapping[str, object]
"""A Wire write's authored assignments: declared member names to accepted wire
values. Version, temporal-axis, computed, read-only, and relationship members
are refused rather than assigned. A primary-key entry is addressing data, never
an assignment: a conditional write's names the object it writes, and a source
write's must name the object its source already addresses. Required wherever a
verb's signature names it — the verbs that name no member are the destructive
and close ones, which take no change set at all.

``{}`` is a stated document, never an absent argument, and what it states
differs by family for the reason the families differ. An amendment of one
object assigns exactly what it names, so naming no member is the ordinary
no-op. A predicate amendment lowers to the canonical assignment algebra, whose
list must name at least one assignment, so ``{}`` is refused there exactly as
``tx.amend_where(query)`` with no assignments is. A replacement's ``{}`` is its
complete stated state, completed like any other."""

type WirePredicateTarget = Mapping[str, object]
"""A Wire predicate write's target: exactly ``{"entity", "predicate"}``, the
canonical selection shape — never an Object Query, because ordering, the cap,
temporal selection, result narrowing, and Include Paths all shape a RESULT and a
set-based write has none to shape."""


def wire_insert(
    attempt: TxnAttempt,
    entity_name: str,
    data: Mapping[str, object],
    *,
    mutation: KeyedMutation,
    valid_from: dt.datetime | Omitted = OMITTED,
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
    holds, and ``tx.wire.amend`` is the verb for that — under the Identity the
    resolved Entity spelling supplies. So is a fresh payload naming an object
    whose insertion in this transaction still stands, the same payload twice
    included: the provenance rule has nothing to say about a document, and the
    unit of work refuses it once its row is prepared, under the same code,
    advising the amend verb of whichever interface OPENED the row — the node
    this verb answered where a Wire insert did, and the instance the caller
    still holds where a Typed one did, which is the only carrier that exists in
    each case.

    The returned node is what closes the one Typed/Wire parity gap on the write
    surface: ``tx.insert(a)`` leaves the Typed caller holding ``a``, so a pure
    Wire caller must be handed something too or it can never revise the row it
    just opened. What it publishes is the buffered ROW rather than the payload —
    a ``many`` the payload left out is answered as the empty collection that row
    stores. It carries the insertion's authority and no Read Evidence, since no
    read published it: the writes off it are licensed by that authority, before
    and after a flush, and compose with the insert while it is pending.
    """
    opened = attempt.keyed_insert(
        WireKeyedInsertSource(entity_name, data),
        mutation,
        valid_from=valid_from,
        until=until,
    )
    return opened_wire_entity(attempt.model, opened.identity, opened.row, opened.authority)


def wire_keyed_write(
    attempt: TxnAttempt,
    mutation: KeyedMutation,
    observed: object,
    changes: WireChanges | Omitted | None = None,
    *,
    until: dt.datetime | None = None,
) -> None:
    """Buffer a Wire keyed write against the state ``observed`` came from.

    ``observed`` is a frozen Entity mapping Parallax published for the row, from
    a read or from the insert that opened it. A read-published node supplies the
    concrete Entity and the pin the source stands at — which is also where a
    Bitemporal write starts — and, where a read of this writable attempt
    published it, the Read Evidence that names the object the write addresses
    and that the target Entity's Effective Concurrency Strategy weighs. The node
    an insert answered carries that insertion's authority instead, which names
    the object and licenses the write, starting at the insertion's own anchor,
    while it stands. ``changes`` is an amendment's assignment document, a
    replacement's stated state — omitted, the writable state ``observed``
    published — and absent for the destructive and close verbs, which key off
    the source alone.

    The order is the Keyed Write Validation Order, which this verb enters rather
    than states: the document's own shape, then the source and its pin, then
    preparation — the verb's applicability to the target and the window, the
    key members the document states, and only then every named member's
    legality and value — all before the strategy is derived or any evidence
    resolved. An amendment naming no member is the empty set, dropped only once
    its source is admitted, so ``{}`` never lets an ineligible source pass;
    every member it does name is assigned, whatever value the source published
    for it.
    """
    attempt.keyed_write(WireKeyedWriteSource(observed, changes), mutation, until=until)


class WirePredicateWriteAdapter:
    """The Wire predicate-selected write over ``target``.

    The Wire spelling of the ``_where`` family: the canonical ``{entity,
    predicate}`` selection plus an authored changes document, lowered to the
    SAME :class:`~parallax.core.unit_work.PredicateWriteInstruction` the Typed verbs build.
    No second set-based write semantics are introduced — this adapter only
    states the target and the assignments differently.

    Inert when constructed. Once :meth:`prepare` is asked, both caller
    documents are captured and judged for shape before anything is resolved
    from the model, the same lead the keyed verb gives them — and a selection's
    shape runs to the bottom of its predicate, so a malformed node is
    `m-predicate`'s own refusal rather than whatever the model happens to say
    about the Entity, the window, or the assignments beside it. The predicate
    parsed there is the one the instruction carries, and each change is an
    assignment owned by the target's own spelling; preparation then judges the
    target, the window, the predicate, and each assignment in authored order.
    """

    __slots__ = ("_changes", "_target")

    def __init__(self, target: WirePredicateTarget, changes: WireChanges | None = None) -> None:
        self._target = target
        self._changes = changes

    def prepare(
        self,
        write_model: SelectedWriteModel,
        mutation: PredicateMutation,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> PreparedPredicateWrite:
        selection = _selection_shape(
            _authored_document(self._target, "a predicate-selected write's canonical target")
        )
        authored = _authored_changes(mutation, self._changes)
        instruction = PredicateWriteInstruction(
            mutation,
            selection,
            tuple(
                WriteAssignment(f"{selection.entity}.{member}", value)
                for member, value in authored.items()
            ),
            valid_from,
            until,
        )
        return instructions.prepare_wire_write(instruction, write_model.model.meta)


class WireTargetWriteAdapter:
    """The Wire caller-conditioned write of the object ``document`` names by
    its primary key.

    ``target`` is an Entity spelling, or — for a replacement alone — a node
    Parallax published, whose own Entity and published writable state,
    historical or current, are the write's target and data, borrowed rather
    than copied. ``document`` is an amendment's change set, a replacement's
    complete data, or a destructive write's key, in accepted wire spellings; it
    must be omitted when a published node states the data. Its primary-key
    entries name the object and are no assignment; every other entry is
    assigned, a framework-owned one refused, and a destructive write states
    none. The revision the attempt hands :meth:`prepare` is the write's whole
    condition: nothing ``document`` or ``target`` carries, and no read's
    evidence, stands in for it.

    Inert when constructed. Once :meth:`prepare` is asked, the addressing and
    the document's own shape are judged first, and constructing the canonical
    instruction refuses a reserved observation key; preparation then judges
    the target, the window, the revision, and the payload.
    """

    __slots__ = ("_document", "_target")

    def __init__(self, target: object, document: object) -> None:
        self._target = target
        self._document = document

    def prepare(
        self,
        write_model: SelectedWriteModel,
        mutation: TargetMutation,
        revision_arguments: TargetRevisionArguments,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> PreparedTargetWrite:
        meta = write_model.model.meta
        target, document = self._target, self._document
        if isinstance(target, str):
            if isinstance(document, Omitted):
                raise instructions.WriteInstructionError(
                    f"a Wire `{mutation}` of an Entity spelling states the data it writes"
                )
            described = f"a Wire `{mutation}`'s {_target_document(mutation)}"
            entity_name = target
            row = _authored_document(document, described)
        elif isinstance(target, WireEntity) and mutation in REPLACE_MUTATIONS:
            if not isinstance(document, Omitted):
                raise instructions.WriteInstructionError(
                    f"a Wire `{mutation}` of a published node writes the state that node "
                    "published, so it takes no data beside it; to state other data, name the "
                    "Entity instead"
                )
            entity = published_entity(meta, target, f"`{mutation}`")
            entity_name = entity.identity.canonical
            row = _published_writable(meta, entity, target, copy=False)
        else:
            raise instructions.WriteInstructionError(
                f"a Wire `{mutation}` addresses an Entity spelling"
                + (" or a node Parallax published" if mutation in REPLACE_MUTATIONS else "")
                + f", and {type(target).__name__} is neither"
            )
        instruction = TargetWriteInstruction(
            mutation,
            entity_name,
            row,
            revision_arguments.if_version,
            revision_arguments.if_tx_start,
            valid_from,
            until,
            revision_arguments.stated,
        )
        return instructions.prepare_wire_write(instruction, meta, authored_members=row.keys())


def _target_document(mutation: TargetMutation) -> str:
    if mutation in AMEND_MUTATIONS:
        return "change set"
    return "data" if mutation in REPLACE_MUTATIONS else "key"


def editable_wire_data(attempt: TxnAttempt, source: object) -> dict[str, object]:
    """Independently mutable authoring data copied from a node Parallax
    published: its primary key and every writable member it published, in
    their Wire spellings, recursively copied into fresh mappings and lists.

    The model selects the members, exactly as a replacement extracts a
    published value's state, and nothing else is consulted: no query,
    serialization round trip, completion, identity generation, or hidden
    stored content. A member the node did not publish stays absent. Copying
    transfers no authority; the source remains the keyed carrier.
    """
    refuse_reentry(attempt.lifecycle)
    meta = attempt.model.meta
    entity = published_entity(meta, source, "`editable_data`")
    assert isinstance(source, WireEntity)  # published_entity accepts nothing else
    return _published_writable(meta, entity, source, copy=True)


def published_entity(meta: Metamodel, node: object, verb: str) -> EntityMetadata:
    """The concrete Entity a node Parallax published names, by the provenance
    it carries, or the refusal for anything else."""
    stored = stored_entity_of(node) if isinstance(node, WireEntity) else None
    authoring = authoring_of(node) if isinstance(node, WireEntity) else None
    entity = (
        stored
        if stored is not None
        else authoring.object_key.entity
        if authoring is not None
        else None
    )
    if entity is None:
        raise instructions.WriteInstructionError(
            f"{verb} on `tx.wire` takes a frozen Entity mapping Parallax published — a "
            "`tx.wire.find` result, or the node `tx.wire.insert` answered — and "
            f"{type(node).__name__} carries no such provenance"
        )
    return _concrete_entity(meta, entity)


def _published_writable(
    meta: Metamodel, entity: EntityMetadata, node: WireEntity, *, copy: bool
) -> dict[str, object]:
    """``node``'s primary key and published writable members, selected by the
    model: never a relationship, framework-owned revision or temporal member,
    derived variant, or read-only member other than the key."""
    view = family_view(meta, entity)
    key = view.primary_key.identity.name
    names = [
        attribute.identity.name
        for attribute in view.applicable_attributes
        if attribute.identity.name == key or not (attribute.framework_owned or attribute.read_only)
    ]
    names.extend(value_object.identity.path[-1] for value_object in view.applicable_value_objects)
    return {
        name: _mutable_copy(node[name]) if copy else node[name] for name in names if name in node
    }


def _mutable_copy(value: object) -> object:
    if isinstance(value, Mapping):
        mapping = cast("Mapping[str, object]", value)
        return {name: _mutable_copy(member) for name, member in mapping.items()}
    if isinstance(value, list):
        return [_mutable_copy(member) for member in cast("list[object]", value)]
    return value


def _source_object_key(resolved: ResolvedKeyedWriteSource) -> ObjectKey | None:
    """The object the source's Read Evidence or insertion authority names, or
    ``None`` for a node carrying neither — one a standalone, read-only, or
    milestone-set read published — whose key the prepared row states instead."""
    if resolved.read_evidence is not None:
        return resolved.read_evidence.object_key
    return None if resolved.authoring is None else resolved.authoring.object_key


def _prepared_wire_write(
    meta: Metamodel,
    mutation: KeyedMutation,
    entity: EntityMetadata,
    row: Mapping[str, object],
    authored: Set[str] | None,
    *,
    valid_from: dt.datetime | None,
    until: dt.datetime | None,
    members: Callable[[], Mapping[str, object]] | None = None,
) -> PreparedKeyedWrite:
    """One authored single-row keyed instruction, decoded and judged by Unit
    Work's sole Wire judgment.

    ``authored`` names the members the caller explicitly wrote — an opening
    payload's keys, judged as insert authoring, or a change document's keys,
    judged as assignments — never the source identity an amendment's row
    carries beside them; or ``members`` produces those assignments once the
    target and window admit the write.
    """
    prepared = instructions.prepare_wire_write(
        keyed_instruction(mutation, entity.identity, row, valid_from=valid_from, until=until),
        meta,
        authored_members=authored,
        members=members,
    )
    return prepared


def _published_identity(
    meta: Metamodel, entity: EntityMetadata, node: WireEntity
) -> dict[str, object]:
    """The object ``node`` names, in the spelling it was published in.

    The row an instruction is built from is authored, so its identity members
    are read back off the published node under the family key's own name — the
    name every Object Key of the family pairs its value with.
    """
    name = family_view(meta, entity).primary_key.identity.name
    return {name: node[name]}


def _published_address(
    meta: Metamodel, entity: EntityMetadata, node: WireEntity, object_key: ObjectKey | None
) -> tuple[tuple[str, object], ...]:
    """The key members the source's object is addressed by, as managed values.

    Read off the Object Key its evidence or authority names where it carries
    one. A node that carries neither — published by a read of no writable
    attempt, so its write is refused once prepared — names the object by its
    published key alone, decoded through the key's declared type.
    """
    if object_key is not None:
        return object_key.primary_key
    key = family_view(meta, entity).primary_key
    name = key.identity.name
    return ((name, decode_wire(key.type, cast("WireValue", node[name]))),)


class WireKeyedWriteSource:
    """The Wire Keyed Write Source: what a published row and an authored
    document answer the keyed write ingress.

    Inert when constructed and private to one verb call, so nothing it can refuse
    runs before the ingress refuses re-entry. :meth:`capture` judges the one thing
    this representation alone can be wrong about — the document's own shape,
    which needs neither a source nor the model — and it leads for that reason: a
    call stating no document hears that rather than a complaint about its other
    argument. A replacement handed no document states the writable state its
    source published, read once the model is known.
    """

    __slots__ = ("_authored", "_changes", "_meta", "_mutation", "_observed", "_source")

    def __init__(self, observed: object, changes: WireChanges | Omitted | None) -> None:
        self._observed = observed
        self._changes = changes
        self._authored: Mapping[str, object] | None = {}
        self._source: WireEntity | None = None
        self._meta: Metamodel | None = None
        self._mutation: KeyedMutation | None = None

    def capture(self, mutation: KeyedMutation, /) -> None:
        changes = self._changes
        if mutation in REPLACE_MUTATIONS and isinstance(changes, Omitted):
            self._authored = None
            return
        self._authored = _authored_changes(
            mutation, None if isinstance(changes, Omitted) else changes
        )

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedWriteSource:
        self._meta = model
        self._mutation = mutation
        node, entity = _keyed_source(mutation, self._observed)
        self._source = node
        return resolve_keyed_write_source(_concrete_entity(model, entity), node)

    def prepare(
        self,
        resolved: ResolvedKeyedWriteSource,
        /,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> PreparedSourceWrite:
        """The instruction this document authors: the source's identity plus
        every member the document states, its key members set aside once they
        are judged to name the source's own object.

        The stated members are the literal assignment set, whatever the source
        published under them, and only the authored side is judged, because
        every rule preparation applies is a rule about what the CALLER wrote. A
        replacement handed no document states the source's published writable
        state instead, which stands alone exactly as a stated document does.
        """
        meta, mutation, node = self._retained()
        entity = resolved.entity
        object_key = _source_object_key(resolved)
        authored = self._authored
        if authored is None:
            authored = _published_writable(meta, entity, node, copy=False)
        identity = _published_identity(meta, entity, node)
        if not any(name in authored for name in identity):
            instruction = _prepared_wire_write(
                meta,
                mutation,
                entity,
                {**identity, **authored},
                authored.keys(),
                valid_from=valid_from,
                until=until,
            )
            assigned = frozenset(authored)
        else:
            stated = authored
            instruction = _prepared_wire_write(
                meta,
                mutation,
                entity,
                identity,
                None,
                valid_from=valid_from,
                until=until,
                members=lambda: instructions.addressed_members(
                    meta, entity, _published_address(meta, entity, node, object_key), stated
                ),
            )
            assigned = frozenset(name for name in authored if name not in identity)
        return PreparedSourceWrite(
            instruction=instruction,
            object_key=(
                object_key
                if object_key is not None
                else object_key_from_row(entity, meta, instruction.rows[0])
            ),
            assigned=assigned,
        )

    def _retained(self) -> tuple[Metamodel, KeyedMutation, WireEntity]:
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
        return resolve_keyed_insert(
            instructions.resolve_target(model, self._entity_name), self._data
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


def _keyed_source(mutation: KeyedMutation, observed: object) -> tuple[WireEntity, EntityIdentity]:
    """``observed`` with the concrete Entity a read published it from conforming
    stored state under, or that the insertion authority of the node a Wire
    insert answered names, or refuse the value as a keyed source.

    One refusal covers every non-source a caller can reach for — an ordinary
    mapping, ``dict(node)``, a JSON or pickle round trip, an
    :class:`~parallax.core.read_delivery.InvalidData` wrapper, and every node
    published as diagnostic data under an invalid root. They differ only in how
    the provenance is absent; none can authorize a keyed write.
    """
    stored = stored_entity_of(observed) if isinstance(observed, WireEntity) else None
    authoring = authoring_of(observed) if isinstance(observed, WireEntity) else None
    entity = (
        stored
        if stored is not None
        else authoring.object_key.entity
        if authoring is not None
        else None
    )
    if entity is None:
        raise instructions.WriteInstructionError(
            f"a keyed `{mutation}` on `tx.wire` takes a frozen Entity mapping Parallax "
            f"published — a `tx.wire.find` result, or the node `tx.wire.insert` answered — and "
            f"{type(observed).__name__} carries no such provenance: an ordinary mapping, a "
            "`dict(...)` conversion, and a serialized round trip all lose the identity a "
            "keyed write is addressed by and the evidence or buffered insert that licenses "
            "it; read the row through `tx.wire.find` and write what it returned"
        )
    assert isinstance(observed, WireEntity)  # provenance rides an Entity node alone
    return observed, entity


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
    """Return a validated document, or the empty set a destructive verb states."""
    if changes is None and mutation not in AMEND_MUTATIONS and mutation not in REPLACE_MUTATIONS:
        return {}
    described = "data" if mutation in REPLACE_MUTATIONS else "change set"
    return _authored_document(changes, f"a Wire `{mutation}`'s {described}")


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
