from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final, cast

from parallax.conformance import _case_ingress
from parallax.conformance._mechanism.envelope import EngineError
from parallax.conformance._mechanism.model_facts import case_entity, family_declarer
from parallax.core import inheritance, read_delivery
from parallax.core._execution._keyed_writes import validate_source_pin
from parallax.core._execution._unit_work import instructions
from parallax.core.execution import TransactionTimePinReadOnlyError
from parallax.core.metamodel import AttributeMetadata, Leaf, PrimaryKey, TemporalDimension
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.unit_work import (
    INSERT_MUTATIONS,
    KeyedWriteInstruction,
    PredicateWriteInstruction,
    TargetWriteInstruction,
    WriteEvidenceError,
)
from parallax.core.wire import WireValue, decode_wire
from parallax.core.write_plan import ObjectKey, VersionObservation
from parallax.snapshot import Snapshot, TxnContext, WireEntity
from parallax.snapshot._publication._wire import authoring_of, read_evidence_of

__all__ = [
    "Buffered",
    "Executed",
    "Outcome",
    "Refused",
    "Submission",
    "WireSubmitter",
    "read_submissions",
]

type WriteInstruction = KeyedWriteInstruction | TargetWriteInstruction | PredicateWriteInstruction


@dataclass(frozen=True, slots=True)
class Submission:
    instruction: WriteInstruction
    pointer: str
    on: object = None
    expect_error: object = None
    declared_observation: VersionObservation | None = None
    is_framework_marker: bool = False
    step: int | None = None
    predicate_target: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class Buffered:
    pass


@dataclass(frozen=True, slots=True)
class Executed:
    affected: int


@dataclass(frozen=True, slots=True)
class Refused:
    at: str
    code: str


type Outcome = Buffered | Executed | Refused


def read_submissions(
    model: AcceptedMetamodel, write: object, *, step: int | None = None
) -> tuple[Submission, ...]:
    """Parse each entry once; split rows while retaining declarations and insertion pointers."""
    entries = (
        [cast("Mapping[str, object]", write)]
        if isinstance(write, Mapping)
        else cast("Sequence[Mapping[str, object]]", write)
    )
    submissions: list[Submission] = []
    for position, entry in enumerate(entries):
        pointer = f"/scenario/{step}/write/{position}" if step is not None else f"/write/{position}"
        observations: list[VersionObservation | None] = []
        document = {
            name: value
            for name, value in entry.items()
            if name
            in {
                "mutation",
                "entity",
                "rows",
                "row",
                "target",
                "assignments",
                "ifVersion",
                "ifTxStart",
                "validFrom",
                "until",
            }
        }
        if "rows" in entry:
            entity, mutation = cast("str", entry["entity"]), cast("str", entry["mutation"])
            rows = cast("Sequence[Mapping[str, object]]", entry["rows"])
            if _is_temporal_entity(model, entity):
                _temporal_entry_row(entity, mutation, rows)
            document["rows"] = [
                _without_observation_controls(model, entity, mutation, row) for row in rows
            ]
            observations = [
                VersionObservation(observed_version=cast("int", row["observedVersion"]))
                if row.get("observedVersion") is not None
                else None
                for row in rows
            ]
        instruction = _case_ingress.normalize_case_write(instructions.deserialize(document), model)
        split = (
            tuple(replace(instruction, rows=(row,)) for row in instruction.rows)
            if isinstance(instruction, KeyedWriteInstruction)
            else (instruction,)
        )
        for index, one in enumerate(split):
            submissions.append(
                Submission(
                    one,
                    pointer,
                    entry.get("on"),
                    entry.get("expectError"),
                    observations[index] if observations else None,
                    _is_framework_write(one, model),
                    step,
                    cast("Mapping[str, object] | None", entry.get("target")),
                )
            )
    return tuple(submissions)


class WireSubmitter:
    """Submit against values held by one transaction attempt; build inside its callback.

    record_find also accepts the checked roots already delivered by a stream, which
    cannot be consumed a second time. Explicit references never fall back to another read.
    """

    __slots__ = ("_held", "_model", "_tx")

    def __init__(self, tx: TxnContext, model: AcceptedMetamodel) -> None:
        self._tx, self._model = tx, model
        self._held = _HeldValues()

    def record_find(self, step: int, snapshot: Snapshot[WireEntity] | Sequence[object]) -> None:
        roots = snapshot.checked().results() if isinstance(snapshot, Snapshot) else snapshot
        nodes = _published_from(roots)
        self._held.finds[step] = nodes
        self._held.published.extend(nodes)

    def submit(self, submission: Submission) -> Outcome:
        if submission.is_framework_marker:
            raise EngineError(
                "a DB-computed write marker is framework bookkeeping, not a Wire submission"
            )
        try:
            instruction = submission.instruction
            if isinstance(instruction, PredicateWriteInstruction):
                return Executed(
                    _execute_wire_predicate_write(
                        self._tx, instruction, submission.predicate_target
                    )
                )
            named = _source_nodes({"on": submission.on}, submission.step, self._held)
            _buffer_wire_write(
                self._tx, self._model, self._held, instruction, named, pointer=submission.pointer
            )
        except WriteEvidenceError as exc:
            if exc.code != submission.expect_error:
                raise
            return Refused(submission.pointer, exc.code)
        return Buffered()

    def submit_unit(
        self, submissions: Sequence[Submission], *, before_writes: Callable[[], None] | None = None
    ) -> tuple[Outcome, ...]:
        if any(s.is_framework_marker for s in submissions):
            raise EngineError(
                "a DB-computed write marker is framework bookkeeping, not a Wire submission"
            )
        for query in _unit_source_reads(self._model, tuple(s.instruction for s in submissions)):
            self._held.published.extend(_published_nodes(self._tx.wire.find(query)))
        if before_writes is not None:
            before_writes()
        return tuple(self.submit(s) for s in submissions)


@dataclass(frozen=True, slots=True)
class _HeldValues:
    published: list[WireEntity] = field(default_factory=list[WireEntity])
    finds: dict[int, tuple[WireEntity, ...]] = field(
        default_factory=dict[int, tuple[WireEntity, ...]]
    )
    opened: dict[ObjectKey, WireEntity] = field(default_factory=dict[ObjectKey, WireEntity])
    insertions: dict[str, list[WireEntity]] = field(default_factory=dict[str, list[WireEntity]])


_VERSION_OBSERVATION_KEY = "observedVersion"
_TEMPORAL_GATE_KEY = "observedTxStart"
_TEMPORAL_VALID_START_KEY = "observedValidStart"
_ROW_OBSERVATION_KEYS = (_VERSION_OBSERVATION_KEY, _TEMPORAL_GATE_KEY, _TEMPORAL_VALID_START_KEY)
_MARKER_KEYS: Final[frozenset[frozenset[str]]] = frozenset(
    {frozenset({"computed"}), frozenset({"increment"})}
)
_LATEST_SELECTION: Final[Mapping[TemporalDimension, str]] = {
    TemporalDimension.VALID_TIME: "valid-time",
    TemporalDimension.TRANSACTION_TIME: "transaction-time",
}


def _versioned_non_temporal_version_attribute(
    model: AcceptedMetamodel, entity_name: str
) -> AttributeMetadata | None:
    declaring = family_declarer(model, case_entity(model, entity_name))
    if declaring.declared_as_of_axes:
        return None
    return next((attr for attr in declaring.declared_attributes if attr.optimistic_locking), None)


def _is_temporal_entity(model: AcceptedMetamodel, entity_name: str) -> bool:
    return bool(family_declarer(model, case_entity(model, entity_name)).declared_as_of_axes)


def _temporal_entry_row(
    entity_name: str, mutation: str, raw_rows: Sequence[Mapping[str, object]]
) -> Mapping[str, object]:
    if len(raw_rows) != 1:
        raise EngineError(
            f"{entity_name!r} {mutation!r}: a temporal write entry carries ONE row "
            f"({len(raw_rows)} authored) — each row closes its own milestone and chains its "
            "own successors, and a temporal entity never collapses into a set-based statement "
            "(m-unit-work 'A temporal keyed instruction carries exactly one row'); author one "
            "entry per row"
        )
    return raw_rows[0]


def _observation_refusal(
    model: AcceptedMetamodel, entity_name: str, mutation: str, key: str
) -> str | None:
    if key in {_TEMPORAL_GATE_KEY, _TEMPORAL_VALID_START_KEY}:
        return (
            f"a write row authors no `{key}` (m-case-format: a writeRow reserves "
            "`observedVersion` alone and every other key names an entity member — a temporal "
            "write observes a whole predecessor milestone, which no row cell can name)"
        )
    if _is_temporal_entity(model, entity_name):
        return (
            f"a temporal row authors no `{key}` (m-unit-work: a temporal write observes a whole "
            "predecessor milestone, which no flat row cell can name — the engine resolves one "
            "from tracked case state or from the find its own step settles against)"
        )
    if mutation in INSERT_MUTATIONS:
        return (
            f"an insert row authors no `{key}` (m-unit-work: inserts have no observation — an "
            "observed version names the milestone a write against an EXISTING row observed)"
        )
    if _versioned_non_temporal_version_attribute(model, entity_name) is None:
        return (
            f"an unversioned row authors no `{key}` (m-unit-work: unversioned Non-Temporal "
            "writes have no observation — there is no observed version for it to name)"
        )
    return None


def _without_observation_controls(
    model: AcceptedMetamodel, entity_name: str, mutation: str, row: Mapping[str, object]
) -> dict[str, object]:
    for key in _ROW_OBSERVATION_KEYS:
        if key not in row:
            continue
        refusal = _observation_refusal(model, entity_name, mutation, key)
        if refusal is not None:
            raise EngineError(f"{entity_name!r} {mutation!r}: {refusal}")
    durable = dict(row)
    durable.pop(_VERSION_OBSERVATION_KEY, None)
    return durable


def _is_framework_write(instruction: WriteInstruction, model: AcceptedMetamodel) -> bool:
    if not isinstance(instruction, KeyedWriteInstruction):
        return False
    entity = instruction.entity
    position = inheritance.view(model).entity(case_entity(model, entity).identity)
    if position is None:  # pragma: no cover - accepted entities have an inheritance position
        return False
    shape = position.member_selection.shape
    return any(
        isinstance(shape.member(name), Leaf)
        and isinstance(value, Mapping)
        and frozenset(cast("Mapping[str, object]", value)) in _MARKER_KEYS
        for row in instruction.rows
        for name, value in row.items()
    )


def _unit_source_query(
    model: AcceptedMetamodel,
    entity_name: str,
    keys: Sequence[ObjectKey],
    valid_at: dt.datetime | None = None,
) -> dict[str, object]:
    """The canonical Object Query resolving every row of ``entity_name`` — a
    CANONICAL Entity spelling — one choreography unit writes against existing
    state, at the Valid-Time instant ``valid_at`` its Bitemporal writes start
    from.

    Membership over the family-declared primary key, one read per target Entity
    however many rows the unit addresses, which is what a caller holding several
    writes of one Entity does: it reads them together and writes what the read
    returned. Reading per row instead would cost the corpus a Database Call per row
    for no semantic gain, and reading between two writes would force-flush the
    first — destroying the very batch collapse the goldens pin.

    A temporal target selects ``latest`` on Transaction Time, the only milestone
    a keyed write may address: the Transaction-Time past is read-only. A
    Bitemporal target is read at the instant its writes start from, because an
    observed write starts at its source's own Valid-Time pin; one read per
    distinct start, so writes starting apart read apart.
    """
    declaring = family_declarer(model, case_entity(model, entity_name))
    pk = [
        attr for attr in declaring.declared_attributes if isinstance(attr.primary_key, PrimaryKey)
    ]
    if len(pk) != 1:  # pragma: no cover - no witnessed write target is composite-keyed
        raise EngineError(
            f"{entity_name!r}: a unit's source read selects by a single-attribute primary key, "
            f"and this Entity declares {len(pk)}"
        )
    name = pk[0].identity.name
    query: dict[str, object] = {
        "target": entity_name,
        "predicate": {
            "in": {
                "path": f"{declaring.identity.canonical}.{name}",
                "values": [dict(key.primary_key)[name] for key in keys],
            }
        },
    }
    temporal: dict[str, object] = {
        _LATEST_SELECTION[axis.dimension]: {"asOf": "latest"}
        for axis in declaring.declared_as_of_axes
    }
    if valid_at is not None:
        temporal[_LATEST_SELECTION[TemporalDimension.VALID_TIME]] = {
            "asOf": f"{valid_at:%Y-%m-%dT%H:%M:%S.%fZ}"
        }
    if temporal:
        query["temporal"] = temporal
    return query


def _unit_source_reads(
    model: AcceptedMetamodel, translated: Sequence[WriteInstruction]
) -> list[dict[str, object]]:
    """Every resolving read one choreography unit owes, in target order.

    A keyed verb is stated against a value the caller holds, so each Entity this
    unit writes against EXISTING state needs one read to hold it by — except for
    a row this same unit opened, which read-your-own-writes covers and which no
    read could return anyway, since the insert has not flushed. Insert rows are
    therefore gathered first and the reads derived from what is left.

    The membership is over OBJECTS rather than over authored rows: two entries
    writing one row — an update the delete after it supersedes — address one
    object and contribute one key. A row naming no whole object is gathered for
    no read at all, because the write it states is addressed by nothing and is
    refused where the diagnosis can name the key.

    Both the object identity and the TARGET are canonical, never the spelling the
    case authored: a bare local name and its canonical form name one Entity
    (`m-case-format`), so two entries spelling one target differently owe one
    read between them rather than one each.
    """
    opened: set[ObjectKey] = set()
    for instruction in translated:
        if not isinstance(instruction, KeyedWriteInstruction):
            continue
        if instruction.mutation in INSERT_MUTATIONS:
            key = _instruction_key(instruction, model)
            if key is not None:
                opened.add(key)
    needed: dict[tuple[str, dt.datetime | None], dict[ObjectKey, None]] = {}
    for instruction in translated:
        if not isinstance(instruction, KeyedWriteInstruction):
            continue
        if instruction.mutation in INSERT_MUTATIONS:
            continue
        key = _instruction_key(instruction, model)
        if key is None or key in opened:
            continue
        canonical = case_entity(model, instruction.entity).identity.canonical
        needed.setdefault((canonical, instruction.valid_from), {})[key] = None
    return [
        _unit_source_query(model, entity, tuple(keys), valid_at)
        for (entity, valid_at), keys in needed.items()
    ]


def _published_nodes(snapshot: Snapshot[WireEntity]) -> tuple[WireEntity, ...]:
    return _published_from(snapshot.checked().results())


def _published_from(roots: Iterable[object]) -> tuple[WireEntity, ...]:
    """Every Entity node ``roots`` carry, each once, in walk order.

    Publication is what settles ownership: a value a caller was handed is the one
    a later keyed write may be addressed by, so the walk starts at the published
    roots and descends the values they carry rather than reading the read's own
    retained sources. A frozen Wire node is a ``dict`` and therefore unhashable,
    which is why the visited set is identity-keyed over objects the caller holds
    for the walk's whole duration.

    How the roots ARRIVED is not among the things this reads: a Snapshot's whole
    result and a Snapshot Stream's delivered roots walk identically, which is the
    claim `m-unit-work-030` states in the corpus — evidence belongs to the value
    rather than to the delivery that carried it. A HYDRATABLE record's collapse
    produced legal member values, so the node in its ``data`` is an ordinary
    observed source and enters the walk unwrapped, while a NON-HYDRATING record
    carries no value to publish and contributes none — which is what leaves the
    wrapper itself unwritable.
    """
    nodes: list[WireEntity] = []
    visited: set[int] = set()
    frontier: list[object] = [
        cast("read_delivery.InvalidData[object]", root).data
        if isinstance(root, read_delivery.InvalidData)
        else root
        for root in roots
    ]
    cursor = 0
    while cursor < len(frontier):
        value = frontier[cursor]
        cursor += 1
        if isinstance(value, list):
            frontier.extend(cast("list[object]", value))
            continue
        if not isinstance(value, WireEntity) or id(value) in visited:
            continue
        visited.add(id(value))
        nodes.append(value)
        frontier.extend(cast("Mapping[str, object]", value).values())
    return tuple(nodes)


def _node_object_key(node: WireEntity) -> ObjectKey:
    hint = read_evidence_of(node)
    if hint is not None:
        return hint.object_key
    authority = authoring_of(node)
    assert authority is not None  # every node this lane holds a read or an insert published
    return authority.object_key


def _writable_source(node: WireEntity) -> bool:
    hint = read_evidence_of(node)
    assert hint is not None
    try:
        validate_source_pin(hint.entity, hint.pin)
    except TransactionTimePinReadOnlyError:
        return False
    return True


def _group_source_node(
    entity_name: str,
    key: ObjectKey | None,
    state: _HeldValues,
    named: Sequence[WireEntity] | None,
    valid_from: dt.datetime | None = None,
) -> WireEntity:
    """The published value one keyed write is addressed by, from what its own
    choreography unit produced.

    Shared by both lanes that state keyed writes: a `uow` group's steps, where
    the values come from the group's own find steps, and an ungrouped unit,
    where they come from the resolving reads that unit issued for itself
    (:func:`_unit_source_reads`).

    ``named`` is what a grouped step's own ``on`` reference resolved to, and is
    the whole answer where it is present: a versioned target holds one row per
    key but a unit of work may observe several GENERATIONS of it, and the
    reference is how a case says which. With no reference, a row this unit's own
    insert opened wins over any find — that is read-your-own-writes, and no read
    could have returned it — and otherwise the published run is scanned from the
    END, so a write settles against the latest reading rather than a stale one.

    ``valid_from`` is a Bitemporal write's start, which an observed write takes
    from the Valid-Time pin of the value it is handed rather than as an argument
    of its own: a published value read anywhere else states a different write,
    so it is never the source, and a named one is refused.
    """
    if named is not None:
        matched = [node for node in named if _node_object_key(node) == key]
        if len(matched) != 1:
            raise EngineError(
                f"{entity_name!r}: the find step this write settles against published "
                f"{len(matched)} rows of {key!r} — a keyed write settles against the ONE "
                "observed state the value it was handed came from (m-case-format 'Settling "
                "against a grouped find')"
            )
        (node,) = matched
        if read_evidence_of(node) is not None and not _pinned_at(node, valid_from):
            raise EngineError(
                f"{entity_name!r}: the write starts at {valid_from!r}, but the find it settles "
                "against was read at another Valid-Time instant — an observed write starts at "
                "its source's own pin and states no start of its own (m-case-format 'Settling "
                "against a grouped find')"
            )
        return node
    opened = None if key is None else state.opened.get(key)
    if opened is not None:
        return opened
    for node in reversed(state.published):
        if (
            _node_object_key(node) == key
            and _writable_source(node)
            and _pinned_at(node, valid_from)
        ):
            return node
    raise EngineError(
        f"{entity_name!r}: a keyed write addresses {key!r}, which no read of its own "
        "choreography unit published and no write of it opened — every keyed write here is "
        "stated through the public verb its mutation names, against a value the caller holds, "
        "and a choreography unit comes to hold one only by reading the row or by opening it "
        "with its own insert (m-case-format 'Resolving reads a write owes')"
    )


def _pinned_at(node: WireEntity, valid_from: dt.datetime | None) -> bool:
    if valid_from is None:
        return True
    hint = read_evidence_of(node)
    assert hint is not None
    pin = hint.pin
    return pin is not None and pin.valid_time == valid_from


def _source_find_nodes(
    entry: Mapping[str, object],
    index: int | None,
    group_finds: Mapping[int, tuple[WireEntity, ...]],
) -> tuple[WireEntity, ...] | None:
    source = entry.get("on")
    if source is None or isinstance(source, str):
        return None
    if not isinstance(source, int) or isinstance(source, bool):
        raise EngineError(
            f"scenario[{index}]: a write settles against ONE find step, named by its "
            f"index — {source!r} is not one (m-case-format 'Settling against a grouped find')"
        )
    published = group_finds.get(source)
    if published is None:
        raise EngineError(
            f"scenario[{index}]: settles against step {source}, which is not an EARLIER find "
            "step of its own `uow` group — the evidence a write settles against is "
            "transaction-scoped (m-case-format 'Settling against a grouped find')"
        )
    return published


def _source_nodes(
    entry: Mapping[str, object], index: int | None, state: _HeldValues
) -> Sequence[WireEntity] | None:
    source = entry.get("on")
    if isinstance(source, str):
        opened = state.insertions.get(source)
        if opened is None:
            raise EngineError(
                f"scenario[{index}]: writes through {source!r}, which opened no value "
                "in this attempt of its own `uow` group"
            )
        return opened
    return _source_find_nodes(entry, index, state.finds)


def _buffer_wire_write(
    tx: TxnContext,
    model: AcceptedMetamodel,
    state: _HeldValues,
    instruction: WriteInstruction,
    named: Sequence[WireEntity] | None,
    *,
    pointer: str | None = None,
) -> None:
    if isinstance(instruction, TargetWriteInstruction):
        _buffer_wire_target(tx, model, instruction)
        return
    assert isinstance(instruction, KeyedWriteInstruction)
    if instruction.mutation in INSERT_MUTATIONS:
        _buffer_wire_insert(tx, model, state, instruction, pointer)
        return
    _buffer_wire_keyed(
        tx,
        model,
        instruction,
        _group_source_node(
            case_entity(model, instruction.entity).identity.canonical,
            _instruction_key(instruction, model),
            state,
            named,
            instruction.valid_from,
        ),
    )


def _instruction_key(
    instruction: KeyedWriteInstruction, model: AcceptedMetamodel
) -> ObjectKey | None:
    entity = case_entity(model, instruction.entity)
    declaring = family_declarer(model, entity)
    attributes = [
        attr for attr in declaring.declared_attributes if isinstance(attr.primary_key, PrimaryKey)
    ]
    row = instruction.rows[0]
    if not attributes or any(row.get(attr.identity.name) is None for attr in attributes):
        return None
    return ObjectKey(
        entity.identity,
        tuple(
            (attr.identity.name, decode_wire(attr.type, cast("WireValue", row[attr.identity.name])))
            for attr in attributes
        ),
    )


def _buffer_wire_insert(
    tx: TxnContext,
    model: AcceptedMetamodel,
    state: _HeldValues,
    instruction: KeyedWriteInstruction,
    pointer: str | None,
) -> WireEntity:
    valid_from, until = instruction.valid_from, instruction.until
    entity = case_entity(model, instruction.entity)
    version = _versioned_non_temporal_version_attribute(model, instruction.entity)
    payload = {
        name: value
        for name, value in instruction.rows[0].items()
        if version is None or name != version.identity.name
    }
    opened = (
        tx.wire.insert(
            entity.identity.canonical,
            payload,
            valid_from=_required(valid_from),
            until=_required(until),
        )
        if instruction.mutation == "insertUntil"
        else tx.wire.insert(entity.identity.canonical, payload, **_stated_start(valid_from))
    )
    state.opened[_node_object_key(opened)] = opened
    if pointer is not None:
        state.insertions.setdefault(pointer, []).append(opened)
    return opened


def _buffer_wire_keyed(
    tx: TxnContext, model: AcceptedMetamodel, instruction: KeyedWriteInstruction, node: WireEntity
) -> None:
    key = _instruction_key(instruction, model)
    identity = dict(key.primary_key) if key is not None else {}
    changes = {name: value for name, value in instruction.rows[0].items() if name not in identity}
    until = instruction.until
    match instruction.mutation:
        case "amend":
            tx.wire.amend(node, changes)
        case "amendUntil":
            tx.wire.amend(node, changes, until=_required(until))
        case "replace" | "replaceUntil":
            tx.wire.replace(node, changes, **({} if until is None else {"until": until}))
        case "delete":
            tx.wire.delete(node)
        case "terminate":
            tx.wire.terminate(node)
        case _:
            tx.wire.terminate(node, until=_required(until))


def _buffer_wire_target(
    tx: TxnContext, model: AcceptedMetamodel, instruction: TargetWriteInstruction
) -> None:
    entity_name = case_entity(model, instruction.entity).identity.canonical
    document = dict(instruction.row)
    valid_from, until = instruction.valid_from, instruction.until
    condition: dict[str, Any] = (
        {"version": instruction.if_version}
        if instruction.if_version is not None
        else {"tx_start": instruction.if_tx_start}
    )
    bounds: dict[str, Any] = {**_stated_start(valid_from)}
    if until is not None:
        bounds["until"] = until
    match instruction.mutation:
        case "amend" | "amendUntil":
            tx.wire.amend_if(entity_name, document, **condition, **bounds)
        case "replace" | "replaceUntil":
            tx.wire.replace_if(entity_name, document, **condition, **bounds)
        case "delete":
            tx.wire.delete_if(entity_name, document, **condition)
        case _:
            tx.wire.terminate_if(entity_name, document, **condition, **bounds)


def _stated_start(valid_from: dt.datetime | None) -> dict[str, dt.datetime]:
    return {} if valid_from is None else {"valid_from": valid_from}


def _required(instant: dt.datetime | None) -> dt.datetime:
    assert instant is not None
    return instant


def _execute_wire_predicate_write(
    tx: TxnContext, authored: PredicateWriteInstruction, target: Mapping[str, object] | None
) -> int:
    assert target is not None
    match authored.mutation:
        case "amend":
            return tx.wire.amend_where(
                target,
                {
                    assignment.attr.rpartition(".")[2]: assignment.value
                    for assignment in authored.assignments
                },
            )
        case "replace":
            assert authored.row is not None
            return tx.wire.replace_where(target, authored.row)
        case "delete":
            return tx.wire.delete_where(target)
