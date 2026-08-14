"""The conformance compile/run engine — binding the corpus to the spine.

The adapter path compiles and runs a compatibility case against the class-free
production spine (no dynamic class synthesis): the case's model YAML is ingested
through the ``m-descriptor`` deserializer and its ``when.objectQuery`` through the
``m-object-query`` deserializer. ``compile`` lowers that query through ``m-sql``;
``run`` routes it through the production read seams — the public Wire read for a
graph, the values lane for rows — which own planning, compilation, execution,
conversion, classification, and row materialization before the adapter builds the
observation envelope around what they published. Compile eligibility
(``m-case-format`` ``compileEligibility``) is read from the case; the run-only
minority is never compiled.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import decimal
import os
import socket
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Final, Literal, Protocol, cast, runtime_checkable

from parallax.conformance import (
    case_format,
    models,
    provision,
    temporal_state,
)
from parallax.conformance.temporal_state import TemporalShadow
from parallax.core import batch_write, deep_fetch, inheritance, opt_lock, storage_layout
from parallax.core.base import (
    INFINITY_LITERAL,
    TemporalBound,
    decode_neutral_literal,
    normalize_instant,
)
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import DbPort, DocumentReadOrdinals, JsonDocument, Row
from parallax.core.dialect import Dialect, dialect_for
from parallax.core.execution_log import (
    DatabaseCall,
    DatabaseCallFailed,
    ExecutionLog,
    ReadCompleted,
    ReadTrace,
    TraceRecorder,
    TransactionAttempt,
    WriteBatchTrace,
    WriteCompleted,
)
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    MemberIdentity,
    Multiplicity,
    NestedValueObjectMetadata,
    TemporalDimension,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
    ValueObjectMetadata,
    entity_by_name,
)
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.model_formation import MetamodelValidationError
from parallax.core.object_query import EntityQuery, ObjectQueryNode, validate_object_query
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.predicate import (
    CanonicalDocumentError,
    ModelRejectedError,
)
from parallax.core.sql_gen import CompiledRead, LoweredStatement, SqlGenError, compile_read
from parallax.core.temporal_read import Pin, TemporalReadError, query_pin, scans_an_axis
from parallax.core.unit_work import (
    INSERT_MUTATIONS,
    CardinalityCorruptionError,
    Concurrency,
    FixedClock,
    KeyedWrite,
    MissingTargetError,
    ObjectKey,
    ObservationKey,
    ObservedKeyedWrite,
    OptimisticLockConflictError,
    PlanningRequest,
    PredicateWrite,
    StaleWriteError,
    SubjectIdentity,
    TemporalObservation,
    TransactionInstant,
    VersionObservation,
    WriteAssignment,
    WriteEffectError,
    WriteObservation,
    WritePlanningError,
    WriteRejectedError,
    buffered_write,
    enforce_affected_rows,
    instructions,
    object_key,
    validate_write,
)
from parallax.core.unit_work.instructions import WriteInstruction
from parallax.core.unit_work.write_planner import reject_readless_document_many
from parallax.descriptor import (
    DescriptorError,
    domain_model_from_document,
    validate_inheritance_families,
)
from parallax.snapshot import handle
from parallax.snapshot.handle import (
    TransactionTimePinReadOnlyError,
    WriteLoweringError,
    build_write_planner,
    stream_lowered,
    validate_source_pin,
)

__all__ = [
    "Emission",
    "EngineError",
    "RunOnly",
    "compile_read_case",
    "compile_scenario_case",
    "compile_write_sequence_case",
    "decode_write_row",
    "eligibility",
    "execution_observation",
    "load_case_metamodel",
    "read_table_state",
    "run_conflict_case",
    "run_error_case",
    "run_graph_case",
    "run_graphs_case",
    "run_interleaved_scenario_case",
    "run_read_case",
    "run_rejected_case",
    "run_scenario_case",
    "run_write_sequence_case",
    "wire_row",
    "wire_value",
]


class EngineError(ValueError):
    """The engine cannot compile or run a case (unsupported shape or bad reference)."""


_READ_ERRORS = (
    CanonicalDocumentError,
    ModelRejectedError,
    SqlGenError,
    TemporalReadError,
    handle.QueryTargetError,
    KeyError,
)


@dataclass(frozen=True, slots=True)
class Emission:
    """One compiled statement emission (an entry of the adapter ``emissions`` array)."""

    case_pointer: str
    sql: str
    binds: tuple[object, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "casePointer": self.case_pointer,
            "sql": self.sql,
            "binds": [_json_bind(bind) for bind in self.binds],
        }


def _json_bind(bind: object) -> object:
    """Render one bind to JSON-native form for the emission wire (m-conformance-adapter).

    A value-object document write binds the whole document as a :class:`JsonDocument`
    carrier (m-db-port); on the wire it is its underlying JSON document. Every other
    CASE-AUTHORED keyed bind is already JSON-native (scalars; a date rides as the
    write-input string) — but a MATERIALIZING predicate write's carried-forward bind
    (an observed gate value, or a chained row's payload
    column) is sourced from a REAL resolved row, so it may be a driver-native
    ``datetime.datetime`` / the native-infinity :class:`~parallax.core.base.
    TemporalBound` sentinel / a ``Decimal`` — exactly the shapes production code
    deliberately passes through UNCHANGED into the write pipeline (never pre-rendered
    there; that seam's own contract, `parallax.snapshot.handle`). :func:`wire_value`
    (this module's own read-side wire renderer) already covers every one of those
    shapes, so it renders the emission wire form here too, rather than a second,
    divergent conversion.
    """
    if isinstance(bind, JsonDocument):
        return bind.value
    return wire_value(bind)


@dataclass(frozen=True, slots=True)
class RunOnly:
    """A case the corpus declares compile-ineligible (`compileEligibility: run-only`)."""

    reason: str


def eligibility(case: case_format.Case) -> RunOnly | None:
    """The case's compile eligibility: ``None`` when compile-eligible, else run-only."""
    raw = case.document.get("compileEligibility")
    if not isinstance(raw, Mapping):
        return None
    declaration = cast("Mapping[str, object]", raw)
    if declaration.get("mode") != "run-only":
        return None
    reason = declaration.get("reason")
    return RunOnly(reason=str(reason) if isinstance(reason, str) else "run-only")


def _case_model_path(case: case_format.Case) -> Path:
    model_ref = case.document.get("model")
    if not isinstance(model_ref, str):
        raise EngineError(f"{case.path.name}: `model` must be a string path")
    return case_format.find_repo_root() / "core" / "compatibility" / model_ref


def load_case_metamodel(case: case_format.Case) -> AcceptedMetamodel:
    """The accepted Metamodel the case's model descriptor forms into."""
    return models.load_model(_case_model_path(case))


def case_entity(model: AcceptedMetamodel, name: str) -> EntityMetadata:
    """The accepted Metadata ``name`` denotes in ``model``.

    A case names an Entity by the spelling its own model authored — bare when
    that is unambiguous, canonical otherwise — which is exactly the QUERY
    REFERENCE rule :func:`~parallax.core.metamodel.entity_by_name` adjudicates,
    so a case's spelling resolves here the way every validator and lowering site
    resolves one.

    A miss is a ``KeyError``: it is a lookup that found nothing, and every lane
    already translates one into an :class:`EngineError` naming the case file, so
    a corpus defect reports the case rather than an engine frame.
    """
    metadata = entity_by_name(model, name)
    if metadata is None:
        raise KeyError(f"{name!r} names no entity the accepted model declares")
    return metadata


def _declaring_metadata(model: AcceptedMetamodel, name: str) -> EntityMetadata:
    """The accepted Metadata of the position that DECLARES ``name``'s family
    facts — its family root, itself for a standalone Entity.

    Temporality is family-wide and root-owned (`m-inheritance` "Inherited
    members"), so a read's pin resolves through the root rather than through a
    concrete descendant's own (locally empty) declaration.
    """
    return _family_declarer(model, case_entity(model, name))


def _read_query(case: case_format.Case) -> ObjectQueryNode:
    when = case.document.get("when")
    if not isinstance(when, Mapping):
        raise EngineError(f"{case.path.name}: read case has no `when`")
    body = cast("Mapping[str, object]", when)
    if "objectQuery" not in body:
        raise EngineError(f"{case.path.name}: read case has no `objectQuery`")
    return deserialize_query(body["objectQuery"])


def _result_form(case: case_format.Case) -> Literal["row", "instance"]:
    """The read's result form from its asserted result member (m-case-format / m-sql).

    A top-level read case declares its consumption lane by which result member it
    asserts: ``then.graph`` / ``then.graphs`` materialize instances (instance-form,
    the object lane), so the read projects the value-object document columns (slot
    4); every other read (``then.rows``) is row-form (the values lane) and omits
    them.
    """
    then = case.document.get("then")
    if isinstance(then, Mapping) and ("graph" in then or "graphs" in then):
        return "instance"
    return "row"


def _canonicalize_read(
    query: ObjectQueryNode,
    entity: EntityMetadata,
    model: AcceptedMetamodel,
    *,
    form: Literal["rows", "graph"] = "graph",
) -> EntityQuery:
    """Preflight and plan one flat root Entity Query.

    The gate is production's own (`handle.preflight`), including Deferred
    Execution Feature classification: an adapter whose compile lane accepted a
    query its own executor would refuse would claim two different supported
    surfaces. ``m-deep-fetch`` then composes temporal injection plus navigation
    canonicalization before SQL sees the result.
    """
    handle.preflight(query, model=model, form=form)
    return deep_fetch.plan(entity, query, model).root


def _family_declarer(model: AcceptedMetamodel, entity: EntityMetadata) -> EntityMetadata:
    """``entity``'s family root, which owns the family-wide declarations.

    A standalone Entity is its own root, so this is the identity there rather
    than a second code path.
    """
    view = inheritance.view(model).entity(entity.identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        raise EngineError(f"{entity.identity.canonical!r} names no entity the model declares")
    root = model.entity(view.root)
    if root is None:  # pragma: no cover - a family root is an accepted Entity
        raise EngineError(f"{view.root.canonical!r} names no entity the model declares")
    return root


def _read_case_concurrency(case: case_format.Case) -> Concurrency | None:
    """A read-shape case's own unit-of-work Concurrency Preference — the
    read-shape half of the `when.uow` threading.

    `when.uow.concurrency` when the case declares it; ``None`` otherwise, which
    is the plain, non-transactional `db.find` surface every other reachable read
    models and which takes no lock under any preference.

    Absent `when.uow` there is no participation to derive a strategy from at
    all, so this seam grants no module-scoped default: the `m-read-lock`
    witnesses whose goldens carry the shared-row-lock suffix declare the
    preference that produces it, exactly as `m-case-format` requires of any
    case whose SQL depends on the effective choice.
    """
    when = case.document.get("when")
    uow = cast("Mapping[str, object]", when).get("uow") if isinstance(when, Mapping) else None
    if isinstance(uow, Mapping):
        concurrency = cast("Mapping[str, object]", uow).get("concurrency")
        if concurrency in ("locking", "optimistic"):
            return concurrency
    return None


def _compile_statement(case: case_format.Case, dialect_name: str) -> CompiledRead:
    if case.shape != "read":
        raise EngineError(
            f"{case.path.name}: only `read`-shape compile is implemented (a write/rejected/"
            f"scenario case compiles through its own dedicated lane; shape={case.shape})"
        )
    query = _read_query(case)
    model = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    try:
        metadata = case_entity(model, query.target.canonical)
        form: Literal["rows", "graph"] = "graph" if _result_form(case) == "instance" else "rows"
        entity_query = _canonicalize_read(query, metadata, model, form=form)
        return compile_read(
            entity_query,
            model,
            dialect,
            result_form=_result_form(case),
            lock=handle.entity_read_lock(model, metadata.identity, _read_case_concurrency(case)),
        )
    except _READ_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc


def compile_read_case(case: case_format.Case, dialect_name: str) -> tuple[list[Emission], int]:
    """Compile a read case to its ordered emissions and round-trip count."""
    statement = _compile_statement(case, dialect_name).statement
    emission = Emission("/objectQuery", statement.sql, statement.binds)
    return [emission], 1


def run_read_case(
    case: case_format.Case, dialect_name: str, port: DbPort
) -> tuple[list[Emission], list[Row], int, ReadTrace]:
    """Run a row-form read case through the production values lane.

    The whole lane is ``db.read_rows`` / ``tx.read_rows``: canonicalization,
    compilation, the read-lock suffix, the Database Call, `familyVariant`
    materialization, and the round-trip count are all production's, and what is
    left here is wire rendering and the case's own routing. A row this adapter
    reports is the row production materialized, not a row this adapter
    re-derived from the query a second time.

    A case declaring a `when.uow` Concurrency Preference is RUN in a transaction
    (`m-read-lock` "an in-transaction object find that intends to write acquires
    a shared row lock"): the lock suffix is derived inside production from that
    preference and the read target's own Optimistic Lock Facet, exactly as it is
    for a developer's ``tx.find``, rather than from a lock this lane asked a
    compiler for while executing outside any boundary. Begin and commit reach the
    database but are no Database Call, so the round trips a locking case reports
    are the read's alone.

    The adapter returns **managed** Python values (``Decimal``, ``datetime``,
    ``UUID``, ``bytes``, …); the conformance harness grades in **wire space**, so
    each observed row is rendered to canonical wire form here — the grader-side
    serialization the ``m-db-port`` boundary fixes, keeping the adapter free of any
    wire/grading logic and the observation envelope JSON-serializable.

    Wire rendering FOLLOWS production's own row transform, because that transform
    may itself produce a managed value: a Relational Document Layout read projects
    one Structured Column and fans it out into members decoded by their declared
    Neutral Type (`m-sql`), so a `timestamp` member arrives here as a `datetime`
    exactly as the same member does when it is a column of its own. Rendering
    first would hand the wire that member's document spelling instead, making one
    logical value observably different under the two layouts.
    """
    query = _read_query(case)
    model = load_case_metamodel(case)
    db = handle.Database(port, model, dialect=dialect_for(dialect_name))
    concurrency = _read_case_concurrency(case)
    try:
        result = (
            db.read_rows(query)
            if concurrency is None
            else db.transact(lambda tx: tx.read_rows(query), concurrency=concurrency).value
        )
    except _READ_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    emissions = [
        Emission("/objectQuery", call.statement.sql, call.statement.binds)
        for call in result.execution.calls
    ]
    return (
        emissions,
        [wire_row(_conforming_row(case, row)) for row in result.rows],
        result.execution.round_trips,
        result.execution,
    )


def _conforming_row(case: case_format.Case, row: handle.PublishedRow) -> Mapping[str, object]:
    """One published row-form element as the row a `then.rows` case grades.

    A row whose stored state contradicted the model publishes its record instead
    of itself, and the row-form observation has no place to carry one, so this
    lane names the shape rather than grading a record as though it were a row.
    Graph-form cases grade `InvalidData` through `then.storedDataIssues`.
    """
    if isinstance(row, handle.InvalidData):
        raise EngineError(
            f"{case.path.name}: a row-form read published an InvalidData record — stored data "
            "that contradicts the model is graded through a `then.graph` case's own "
            "`storedDataIssues`, never as a row"
        )
    return row


def _driver_binds(binds: Sequence[object]) -> list[object]:
    return list(binds)


# --------------------------------------------------------------------------- #
# Graph reads (m-deep-fetch / m-snapshot-read): the lane runs the PUBLIC Wire   #
# read, so every level's compile, execute, convert, merge, classify, and unwind #
# is production's and a `then.graph` observation IS a Wire result. What is left #
# here is the envelope around it — the root key, the milestone pin, and the     #
# stored-data records a classified root publishes in place of itself.           #
# --------------------------------------------------------------------------- #
def _wire_read(
    case: case_format.Case,
    query: ObjectQueryNode,
    model: AcceptedMetamodel,
    port: DbPort,
    dialect_name: str,
) -> handle.Snapshot[handle.WireEntity]:
    """One graph-form Wire read of the case's own Object Query.

    The whole lane is ``db.wire.find``: target resolution, validation, deep-fetch
    planning, per-level compilation and execution, row conversion, projection
    merging, root classification, the finite include-tree unwind, and the
    round-trip count are production's, and a scanning read answers the
    milestone-set form from the same call, exactly as ``db.find`` does.
    """
    db = handle.Database(port, model, dialect=dialect_for(dialect_name))
    try:
        return db.wire.find(query)
    except _READ_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc


def run_graph_case(
    case: case_format.Case, dialect_name: str, port: DbPort
) -> tuple[list[Emission], dict[str, list[Row | None]], int, list[dict[str, object]] | None]:
    """Run a single-graph deep-fetch / snapshot read, reporting the Wire result
    production published as the wire `then.graph` shape (root-class-keyed) and,
    for a root whose stored state contradicted the model, the record it published
    in place of itself.
    """
    query = _read_query(case)
    model = load_case_metamodel(case)
    snapshot = _wire_read(case, query, model, port, dialect_name)
    if not _is_single_graph(query):
        raise EngineError(
            f"{case.path.name}: a `then.graph` case read a milestone SET — "
            "a milestone-set read asserts `then.graphs`"
        )
    roots = snapshot.checked().results()
    return (
        _read_emissions(snapshot.execution),
        {_graph_root_key(query.target.canonical, model): [_graph_root(root) for root in roots]},
        snapshot.execution.round_trips,
        _stored_data_records(roots),
    )


def run_graphs_case(
    case: case_format.Case, dialect_name: str, port: DbPort
) -> tuple[list[Emission], list[dict[str, object]], int]:
    """Run a milestone-set (`history` / `asOfRange`) snapshot read, reporting
    production's ordered per-milestone roots as the wire `then.graphs` shape: an
    array of `{pin, graph}` entries, each pin keyed by declared as-of dimension
    spelling.

    A milestone-set Wire Snapshot publishes every milestone's roots in ONE
    ordered result (`m-snapshot-read`), so the per-milestone partition is
    recovered from each root's own edge — the coordinate the pin states — rather
    than from a second read per milestone.
    """
    query = _read_query(case)
    model = load_case_metamodel(case)
    snapshot = _wire_read(case, query, model, port, dialect_name)
    if _is_single_graph(query):
        raise EngineError(
            f"{case.path.name}: a `then.graphs` case read a single instant — "
            "a single-instant read asserts `then.graph`"
        )
    root_key = _graph_root_key(query.target.canonical, model)
    entity = _declaring_metadata(model, query.target.canonical)
    graphs_wire: list[dict[str, object]] = [
        {"pin": _wire_pin(pin), "graph": {root_key: roots}}
        for pin, roots in _milestone_partition(entity, snapshot.checked().results())
    ]
    return _read_emissions(snapshot.execution), graphs_wire, snapshot.execution.round_trips


def _is_single_graph(query: ObjectQueryNode) -> bool:
    """Whether the read answers one graph rather than a milestone SET.

    The dispatch is the query's own — a scanned axis is what makes a read
    milestone-set (`m-temporal-read`) — read here rather than inferred from the
    result, because both forms now publish one ordered Snapshot.
    """
    return not scans_an_axis(query)


def _milestone_partition(
    entity: EntityMetadata, roots: Sequence[object]
) -> list[tuple[Pin, list[Row | None]]]:
    """One ordered milestone-set result partitioned back into its own graphs.

    Roots arrive in the executor's chronological milestone order, so a partition
    closes as soon as the edge changes: grouping by first appearance would fold
    two milestones a scan legitimately answers twice.
    """
    partitions: list[tuple[Pin, list[Row | None]]] = []
    for root in roots:
        pin = _root_pin(entity, root)
        if not partitions or partitions[-1][0] != pin:
            partitions.append((pin, []))
        partitions[-1][1].append(_graph_root(root))
    return partitions


def _root_pin(entity: EntityMetadata, root: object) -> Pin:
    """One milestone-set root's own edge pin, read off the values it published.

    A milestone-set graph is edge-pinned at its own milestone's from-instant
    (`m-snapshot-read`), and the root carries those axis starts as declared
    members, so the coordinate is the row's own rather than a second reading of
    the query.
    """
    values = _graph_root(root)
    if values is None:  # pragma: no cover - a non-hydrating milestone root pins nothing
        raise EngineError("a milestone-set root published no value to pin")
    coordinates: dict[TemporalDimension, object] = {
        axis.dimension: values.get(axis.start_attribute.name) for axis in entity.declared_as_of_axes
    }
    return Pin(
        tx_time=_pin_instant(coordinates.get(TemporalDimension.TRANSACTION_TIME)),
        valid_time=_pin_instant(coordinates.get(TemporalDimension.VALID_TIME)),
    )


def _pin_instant(value: object) -> dt.datetime | None:
    """One published axis start as the instant a :class:`Pin` carries."""
    if not isinstance(value, str):
        return None
    return normalize_instant(dt.datetime.fromisoformat(value))


def _graph_root(root: object) -> Row | None:
    """One published result position as the value `then.graph` grades.

    A conforming root IS the graph node. A classified root publishes its record
    instead, carrying the hydrated node when the collapse produced one and
    nothing when no value could be produced without inventing it — and the graph
    position then carries ``null``, because a record is graded through
    `then.storedDataIssues` rather than rendered as though it were a node.
    """
    if isinstance(root, handle.InvalidData):
        return cast("Row | None", cast("handle.InvalidData[object]", root).data)
    return cast("Row", root)


def _read_emissions(execution: ReadTrace) -> list[Emission]:
    """The read's own emissions: the statements production actually ran, in order."""
    return [
        Emission("/objectQuery", call.statement.sql, call.statement.binds)
        for call in execution.calls
    ]


# The wire spelling each pinned as-of axis is emitted under in a milestone-set
# graph's pin entry. The coordinate itself is structured everywhere above this seam.
_PIN_AXIS_NAMES: Final[tuple[tuple[str, str], ...]] = (
    ("valid-time", "valid_time"),
    ("transaction-time", "tx_time"),
)


def _wire_pin(pin: Pin) -> dict[str, object]:
    """One milestone's edge pin on the wire, keyed by dimension spelling.

    An axis the milestone's Entity does not declare carries no coordinate and is
    absent, which is what a :class:`~parallax.core.temporal_read.Pin` already
    says by holding ``None`` there.
    """
    return {
        name: wire_value(getattr(pin, field))
        for name, field in _PIN_AXIS_NAMES
        if getattr(pin, field) is not None
    }


def _graph_root_key(target: str, model: AcceptedMetamodel) -> str:
    """The `then.graph` root key the query's own ``target`` denotes.

    Result vocabulary is LOCAL where an addressing reference is exact
    (`m-case-format`), so the authored spelling is resolved and the Entity's own
    local name answers — the same key a bare spelling produced before every
    reference position became canonical.
    """
    entity = entity_by_name(model, target)
    if entity is None:  # pragma: no cover - the read already resolved this target
        raise EngineError(f"{target!r} names no entity the accepted model declares")
    return entity.identity.name


def _stored_data_records(roots: Sequence[object]) -> list[dict[str, object]] | None:
    """The `then.storedDataIssues` observation, or ``None`` for a clean read.

    One entry per INVALID result position, in result order: the position itself,
    whether hydration completed, and the closed diagnosis set the root carries.
    A conforming read reports nothing at all, so a case that authors no
    expectation is never handed an empty array to explain.
    """
    records = [
        _stored_data_record(cast("handle.InvalidData[object]", root))
        for root in roots
        if isinstance(root, handle.InvalidData)
    ]
    return records or None


def _stored_data_record(record: handle.InvalidData[object]) -> dict[str, object]:
    """One published :class:`~parallax.snapshot.InvalidData` on the wire.

    ``hydrated`` states the one thing the graph position cannot: whether the
    ``null`` at that position means "no value could be produced without inventing
    one" or is the node's own collapsed value.
    """
    return {
        "ordinal": record.ordinal,
        "hydrated": record.data is not None,
        "issues": sorted(
            (_stored_data_issue(issue) for issue in record.issues),
            key=lambda issue: (
                cast("str", issue["code"]),
                cast("str", issue.get("member") or ""),
                cast("str", issue["entity"]),
            ),
        ),
    }


def _stored_data_issue(issue: handle.StoredDataIssue) -> dict[str, object]:
    """One diagnosis as its cross-language record (`m-snapshot-read`).

    ``member`` is absent for an unresolved family tag alone — its discriminator
    names no declared member — and ``objectKey`` is absent wherever the affected
    object's own identity did not decode.
    """
    rendered: dict[str, object] = {"code": issue.code, "entity": issue.entity.canonical}
    if issue.member is not None:
        rendered["member"] = _member_path(issue.member)
    if issue.object_key is not None:
        rendered["objectKey"] = _wire_object_key(issue.object_key)
    return rendered


def _member_path(member: MemberIdentity) -> str:
    """One member identity as the dotted path the corpus addresses members by.

    The same spelling a nested predicate authors
    (``parallax.compatibility.Customer.address.geo.country``), so a diagnosis
    names a member exactly as a case already names one.
    """
    match member:
        case AttributeIdentity():
            return f"{member.entity.canonical}.{member.name}"
        case ValueObjectIdentity():
            return ".".join((member.entity.canonical, *member.path))
        case ValueObjectAttributeIdentity():
            occurrence = member.value_object
            return ".".join((occurrence.entity.canonical, *occurrence.path, member.name))


def _wire_object_key(key: ObjectKey) -> dict[str, object]:
    """One Object Key on the wire: its Entity plus its ordered primary-key values."""
    return {
        "entity": key.entity.canonical,
        "key": {name: wire_value(value) for name, value in key.primary_key},
    }


# --------------------------------------------------------------------------- #
# Scenario / writeSequence — the unit-of-work write lanes (m-unit-work).       #
# --------------------------------------------------------------------------- #
# A write step is one unit of work: its buffered keyed writes are planned by
# the SAME ``build_write_planner`` factory production uses (``m-unit-work``)
# and each surviving :class:`~parallax.core.unit_work.PlannedWrite` is lowered
# to DML by the shared ``snapshot.handle.stream_lowered`` seam — the deliberate
# ``m-sql`` write edge the conformance family may compose (the import-side DAG
# exemption). A **scenario** is a *sequence* of units of work: a write step
# commits (or, ``rollback: true``, aborts) its coalesced DML, then a ``find``
# reads committed state through the read path. A **writeSequence** lowers each
# entry independently — no cross-entry coalescing (an insert-then-delete pair
# across two entries is two round trips, not a cancellation) — and each entry
# is its OWN transaction (not "the whole sequence in one transaction").
#
# The RUN lane executes
# every write choreography unit — a writeSequence entry, a scenario write step, a
# conflict attempt — through the SHIPPED ``db.transact`` entry point (one
# transaction per unit, ``clock=FixedClock(<entry at>)``, ADR 0010), buffered
# through the neutral ``Transaction.write_neutral`` ingress + ``UnitOfWork.observe`` (never
# the typed instance verbs, which this engine's case-driven metamodel has no
# compiled classes for). The COMPILE lane still lowers PURELY (no database,
# ``build_write_planner(...).plan`` / ``stream_lowered``) — that pure lowering is
# ALSO what the RUN lane's emissions/round-trips observation grades against,
# since both are the SAME deterministic computation over the SAME
# instructions/observations/instant (`_resolve_entries` / `_lower_resolved`
# below are the shared core).

# The lowering failures the write lanes convert to a neutral :class:`EngineError`,
# so the adapter reports a ``*-failed`` diagnostic rather than leaking a lower-layer
# exception type across the conformance seam. `opt_lock.UnobservedVersionError` /
# `.CallerAuthoredVersionError` are m-opt-lock's own
# forward-error posture; `temporal_state.AmbiguousObservationError` /
# `.MilestoneEdgeError` are this engine's own (shapes no reachable case
# exercises). A deferred witness (the
# materializing / auto-retry-
# boundary forms) that reaches this engine-local write path without
# a recorded observation must degrade to a reasoned `EngineError`, never an
# uncaught crash of the sweep.
_LOWERING_ERRORS: Final[tuple[type[Exception], ...]] = (
    instructions.WriteInstructionError,
    WriteLoweringError,
    WritePlanningError,
    inheritance.InheritanceError,
    opt_lock.UnobservedVersionError,
    opt_lock.CallerAuthoredVersionError,
    temporal_state.AmbiguousObservationError,
    temporal_state.MilestoneEdgeError,
    CanonicalDocumentError,
    SqlGenError,
    TemporalReadError,
    KeyError,
    TypeError,
)

# A non-temporal writeSequence entry (e.g. a pk-gen sequence registry advance)
# names no `at` — its Clock value is inert (no temporal write consumes it this
# unit), so a fixed, deterministic instant stands in (`m-txtime-write` / ADR 0010:
# "a non-temporal entry's clock value is inert, pick something deterministic").
_INERT_CLOCK_INSTANT: Final[str] = "1970-01-01T00:00:00+00:00"

# The compile lane's own audit-neutral Subject Identity: this lane never opens
# a real Principal boundary, and a Planning Request requires one regardless
# (`m-unit-work`) — the harness proves the value is never inspected, so any
# nonempty constant serves every pure re-lowering call below identically.
_PLANNING_SUBJECT: Final[SubjectIdentity] = SubjectIdentity("conformance-compile-lane")


def _pinned_instant(tx_instant: str) -> TransactionInstant:
    """The lazy Transaction Instant a pure lowering runs at.

    The compile lane has no unit of work to own one, so it pins the entry's own
    ``at`` through the SAME ``FixedClock`` the run lane hands ``db.transact`` —
    the two lanes therefore capture the identical literal, and an entry whose
    lowering needs no Transaction-Time boundary captures nothing at all.
    """
    return TransactionInstant(FixedClock(dt.datetime.fromisoformat(tx_instant)))


class _RollbackStep(Exception):
    """Sentinel raised inside a transaction body to abort a ``rollback: true`` step."""


class _AbortingPort:
    """A pass-through ``m-db-port`` whose transaction ALWAYS aborts, after the
    unit of work inside it has finished its own work.

    Case-only choreography for a `rollback: true` step (`m-case-format`), and
    the sibling of the boundary lane's own fault injector: it arranges an
    outcome a caller cannot ask a real database for. The abort is raised once
    the body returns — after the boundary's finalization flush has already put
    the buffered DML on the wire — so the case's own contract is reproduced
    exactly (`m-unit-work` "Abort": "the forced flush is safe precisely because
    it lands inside the still-open atomic scope the abort discards"): the write's
    statements execute, count their round trips on the attempt, and are then
    erased by the provider's rollback.

    Raising HERE rather than inside the transaction callback is what makes the
    flush production's own: a callback that raises leaves the unit of work
    discarding its buffer unflushed, so the DML the case asserts would never
    reach the database at all.

    The cost of raising there is that the boundary has already entered its
    commit phase, so the attempt's own failure record names ``commit`` for a
    durability boundary that never failed, and the sentinel — outside every
    classified family — makes ``retryEligible: false`` a default rather than a
    verdict. No case reads either: what a `rollback: true` case asserts is the
    table state and the round trips, and both come from the calls, not from the
    failure record.
    """

    def __init__(self, inner: DbPort) -> None:
        self._inner = inner

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        return self._inner.execute(sql, binds, document_reads)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        return self._inner.execute_write(sql, binds)

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        def aborting(conn: DbPort) -> T:
            body(conn)
            raise _RollbackStep

        return self._inner.transaction(aborting)


def _write_port(port: DbPort, *, rollback: bool) -> DbPort:
    """``port`` itself, or the aborting decorator a `rollback: true` step needs."""
    return _AbortingPort(port) if rollback else port


@dataclass(frozen=True, slots=True)
class _LoweredStep:
    """One lowered scenario step: its emission pointer and DML, and how to run it."""

    pointer: str
    statements: tuple[LoweredStatement, ...]
    is_write: bool
    rollback: bool


def _when(case: case_format.Case) -> Mapping[str, object]:
    when = case.document.get("when")
    if not isinstance(when, Mapping):
        raise EngineError(f"{case.path.name}: case has no `when`")
    return cast("Mapping[str, object]", when)


def _scenario_steps(case: case_format.Case) -> list[Mapping[str, object]]:
    steps = _when(case).get("scenario")
    if not isinstance(steps, list):
        raise EngineError(f"{case.path.name}: scenario case has no `when.scenario` list")
    return [cast("Mapping[str, object]", step) for step in cast("list[object]", steps)]


def _write_sequence_entries(case: case_format.Case) -> list[Mapping[str, object]]:
    entries = _when(case).get("writeSequence")
    if not isinstance(entries, list):
        raise EngineError(f"{case.path.name}: writeSequence case has no `when.writeSequence` list")
    return [cast("Mapping[str, object]", entry) for entry in cast("list[object]", entries)]


def _concurrency(case: case_format.Case) -> Concurrency:
    """The case's declared unit-of-work Concurrency Preference
    (`when.uow.concurrency`; `m-unit-work` "Strategy selection"), defaulting to
    `optimistic` when the case declares none — the SAME default
    `m-unit-work.TransactionSettings` resolves and the one `m-case-format`
    states for the `when.uow` block.

    A preference is not a strategy: what each step's own Entity participates
    under is derived from this value and that Entity's Optimistic Lock Facet, so
    an unversioned Non-Temporal target still locks and still writes ungated
    under the default. A case whose golden SQL depends on that choice declares
    the preference explicitly (`m-case-format`); `when.uow` is schema-legal on
    writeSequence shape (`compatibility-case.schema.json`'s writeSequence
    `propertyNames` admits `uow` alongside `writeSequence`)."""
    when = case.document.get("when")
    if isinstance(when, Mapping):
        uow = cast("Mapping[str, object]", when).get("uow")
        if isinstance(uow, Mapping):
            value = cast("Mapping[str, object]", uow).get("concurrency")
            if value == "locking":
                return "locking"
    return "optimistic"


# The ONE reserved observation control key a case writeRow can author
# (`compatibility-case.schema.json` `$defs/writeRow`): the version the unit of
# work observed, stripped into a Version Observation before the durable
# instruction is built (the durable row forbids it, ADR 0013). Which write
# shapes are entitled to author it is `_observation_refusal`'s answer, not the
# schema's — one shared `writeRow` definition spans every shape.
_VERSION_OBSERVATION_KEY: Final[str] = "observedVersion"

# The two halves of an observed milestone's own EDGE coordinate. NEITHER is a
# write-row key in any shape: they are authored beside the write, at
# `when.observedTxStart` / `when.observedValidStart` — and, on a retry attempt,
# `observedTxStart` alone, since the edge form is single-attempt only
# (`m-case-format`) — so a row carrying one is refused rather than stripped.
_TEMPORAL_GATE_KEY: Final[str] = "observedTxStart"
_TEMPORAL_VALID_START_KEY: Final[str] = "observedValidStart"

# Every reserved observation control key a case can spell on a write row. The
# durable instruction forbids all of them (ADR 0013); which one a given write is
# entitled to author BEFORE stripping is :func:`_observation_refusal`'s answer.
_ROW_OBSERVATION_KEYS: Final[tuple[str, ...]] = (
    _VERSION_OBSERVATION_KEY,
    _TEMPORAL_GATE_KEY,
    _TEMPORAL_VALID_START_KEY,
)


# What ONE grouped find step observed, in the order production filed it. A later
# write step of the same group names that step with `on` and settles against the
# record of its OWN key (`m-case-format` "Settling against a grouped find").
ObservedNodes = tuple[handle.ObservedRecord, ...]

# Everything a `uow` group's find steps have observed so far, in step order — the
# store a grouped write with no `on` reference resolves its own evidence from.
# `_write_sequence_lowered` / `run_write_sequence_case` pass a permanently EMPTY
# sequence (a writeSequence carries no find steps at all): every keyed write's
# observation there comes solely from its own row's reserved `observedVersion`
# control key. The scenario RUN lane (`_run_uow_group`) builds one FRESH store per
# `uow` GROUP — never one spanning the whole scenario or crossing a group
# boundary; the scenario COMPILE lane (`_scenario_lowered`) never populates one at
# all, so no compile path ever consults a query result (`m-conformance-adapter`
# "Compile eligibility"). Reladomo prior art (semantics, not idioms): the
# transaction records the version at read time ("the shadow value read earlier")
# and threads it into the UPDATE bind
# (`docs/research/reladomo/09-transactions-locking.md:55-59`).
GroupObservations = list[handle.ObservedRecord]

# What a write hands `Transaction.write_neutral` as the evidence it settles
# against: the active unit of work's own Observation Key where a grouped find
# issued one, the case's own authored or tracked Write Observation otherwise.
type WriteEvidence = ObservationKey | WriteObservation | None


@dataclass(frozen=True, slots=True)
class _ResolvedWrite:
    """One case write entry's row, resolved against whatever evidence its lane
    supplies and ready for BOTH consumers of a write buffer.

    The two evidence fields are deliberately separate carriers of related facts.
    ``execution_evidence`` is what the REAL write hands
    :meth:`~parallax.snapshot.handle.Transaction.write_neutral`, which may be an
    Observation Key the active unit of work issued and which only that unit of
    work can dereference. ``oracle_observation`` is the same evidence as a value,
    for the PURE re-lowering (:func:`_lower_resolved`) that plans with no unit of
    work behind it. Neither substitutes for the other, and an entry needing no
    evidence at all carries neither.
    """

    instruction: WriteInstruction
    execution_evidence: WriteEvidence
    oracle_observation: WriteObservation | None


def _versioned_non_temporal_version_attribute(
    model: AcceptedMetamodel, entity_name: str
) -> AttributeMetadata | None:
    """``entity_name``'s own optimistic-lock version ATTRIBUTE, when it is a
    VERSIONED, NON-TEMPORAL entity (`m-opt-lock`) — ``None`` otherwise, because a
    temporal entity observes a whole MILESTONE rather than a version, which is a
    different observation shape and not this attribute's
    (:func:`_milestone_observation`; `_build_temporal_instruction`). Resolved
    through the FAMILY-declaring entity (:func:`_family_declarer`): the version
    column is family-wide metadata declared only on the root
    (`m-opt-lock` "The version column")."""
    declaring = _family_declarer(model, case_entity(model, entity_name))
    if declaring.declared_as_of_axes:
        return None
    return next((attr for attr in declaring.declared_attributes if attr.optimistic_locking), None)


def _refuse_unaccounted_document_milestone(
    model: AcceptedMetamodel,
    entity: EntityMetadata,
    row: Mapping[str, object],
    shadow: TemporalShadow,
) -> None:
    """Refuse a keyed temporal write over a Relational Document Layout target
    whose observation would be rebuilt from a tracked milestone the tracker can no
    longer account for whole.

    The peer of :func:`_refuse_document_layout_milestone` for the lanes that take
    their milestone from tracked case state rather than from a find — every
    writeSequence entry and every scenario write step not settling against a
    grouped find. Under ``Columns`` the tracked members ARE the whole stored row.
    Under ``Document`` they are the whole stored document too, but only while
    every key in it came from this case's own fixtures and authored writes: a
    fixture row is authored member by member, and a successor this engine tracked
    was built from the plan that wrote it.

    Out-of-band statements are exactly what breaks that. They exist to store what
    no authored member can produce, this tracker never re-reads, and the framework
    issues no resolving read on behalf of a keyed write — so the successor such a
    write chains would be patched onto declared members alone and drop whatever
    those statements MAY have left in the document. Whether they touched this
    milestone at all is not knowable from a naive ``sql`` string, so the doubt
    alone refuses: naming the shape is the only answer that cannot be silently
    wrong.

    Which milestone the write addresses is what decides it
    (:meth:`~parallax.conformance.temporal_state.TemporalShadow.accounts_for`),
    never merely whether the case ran such statements somewhere: a milestone this
    case's own later write opened is a whole account of its row again, so an
    insert-then-update chain over a document-mapped target stays legal beside any
    out-of-band statement (`m-case-format`: a keyed write consumes the milestone
    the case's own fixtures and earlier entries left current).
    """
    if shadow.accounts_for(model, entity, row):
        return
    entity_name = entity.identity.canonical
    column = _shared_document_column(model, entity_name)
    if column is None:
        return
    raise EngineError(
        f"a keyed temporal write on {entity_name!r} addresses a milestone this case's own "
        f"out-of-band statements may have overtaken or stored, and its document-resident members "
        f"are stored in the shared Structured Column {column!r} — this lane observes the "
        "milestone from tracked case state, which never saw what those statements stored, so "
        "the successor it chains would lose whatever else that document holds"
    )


def _refuse_materialized_case_state(
    model: AcceptedMetamodel,
    entity: EntityMetadata,
    row: Mapping[str, object],
    shadow: TemporalShadow,
) -> None:
    """Refuse a keyed temporal write whose observation would come from case state
    a materializing predicate write of this same case already moved
    (:meth:`~parallax.conformance.temporal_state.TemporalShadow.moved_by_materialization`).

    That write resolved its own rows inside production, retired the milestone it
    found for each and opened a successor, and returned neither the plan nor the
    rows — so the milestone this lane still holds current for that key is one the
    database closed. A close addressed at it matches no row.

    The composition is refused rather than executed because the two would not even
    fail the same way. A real caller could not have issued this write at all
    without a Temporal Observation, which only a read supplies; their observation
    would name the milestone the predicate write opened, and gating a close on the
    retired one is what production reports as a stale write. This lane's
    observation comes from tracked case state instead — the whole reason the
    tracker exists — and would issue a well-formed statement that quietly affects
    zero rows. Naming the shape is the only answer that cannot be silently wrong.

    Scope is the milestone, not the case: a target the predicate write never named
    keeps its tracked state, and a milestone this case's own later write opens for
    the moved key is a current account of it again.
    """
    if not shadow.moved_by_materialization(model, entity, row):
        return
    raise EngineError(
        f"a keyed temporal write on {entity.identity.canonical!r} settles against case state "
        "that this case's own materializing predicate write already moved — that write closed "
        "the tracked milestone and opened a successor inside production, whose plan this lane "
        "never sees, so the close this write would address matches no row. A real caller could "
        "reach this step only by READING the row, and would gate on the milestone the predicate "
        "write opened; gating on the retired one is a stale write, not a zero-row success. "
        "Author the materializing write and the keyed write as separate cases"
    )


def _shared_document_column(model: AcceptedMetamodel, entity_name: str) -> str | None:
    """The name of the shared Structured Column ``entity_name``'s rows carry under
    Relational Document Layout, or ``None`` under ``Columns``, which has none."""
    entity = entity_by_name(model, entity_name)
    layout = None if entity is None else storage_layout.view(model).entity(entity.identity)
    if layout is None:  # pragma: no cover - an observed node names a row-owning Entity
        return None
    return next(
        (
            slot.column.name
            for slot in layout.columns
            if isinstance(slot.contributor, storage_layout.RelationalDocument)
        ),
        None,
    )


def _entry_instant(entry: Mapping[str, object]) -> str:
    """The tx_instant an entry's OWN choreography unit (transaction) runs at
    (m-txtime-write / m-bitemp-write ``at``; ADR 0010: the Clock, never a
    per-operation override). A non-temporal entry names none — its Clock
    value is inert, so :data:`_INERT_CLOCK_INSTANT` stands in."""
    at = entry.get("at")
    return at if isinstance(at, str) else _INERT_CLOCK_INSTANT


def _is_temporal_entity(model: AcceptedMetamodel, entity_name: str) -> bool:
    return bool(_family_declarer(model, case_entity(model, entity_name)).declared_as_of_axes)


_TEMPORAL_INSERT_MUTATIONS: Final[frozenset[str]] = frozenset({"insert", "insertUntil"})


def _temporal_entry_row(
    entity_name: str, mutation: str, raw_rows: Sequence[Mapping[str, object]]
) -> Mapping[str, object]:
    """The ONE case-authored row a TEMPORAL write entry mutates.

    `m-unit-work` "A temporal keyed instruction carries exactly one row": each row
    closes its own current milestone, consumes its own Temporal Observation, and
    opens its own successors, and a temporal entity never collapses into a
    set-based statement (`m-batch-write`), so several rows under one entry denote
    several independent milestone chains rather than one wider write. That rule
    forbids reducing the entry to a first row the case did not single out, so it
    is refused HERE, where the authoring diagnosis can name the entry. It is the
    SAME rule :func:`_conflict_close_row` applies to a temporal conflict attempt's
    multi-key ``write`` array; the shared case schema cannot express either,
    because the row count it may admit depends on whether the target entity is
    temporal, which only the model knows.

    Refusing before :func:`_durable_row` is what makes "every case-authored row
    reaches the seam" true rather than approximately true: a row this function
    admits is the entry's only row, so none is left behind unrefused.
    """
    if len(raw_rows) != 1:
        raise EngineError(
            f"{entity_name!r} {mutation!r}: a temporal write entry carries ONE row "
            f"({len(raw_rows)} authored) — each row closes its own milestone and chains its "
            "own successors, and a temporal entity never collapses into a set-based statement "
            "(m-unit-work 'A temporal keyed instruction carries exactly one row'); author one "
            "entry per row"
        )
    return raw_rows[0]


def _build_temporal_instruction(
    entry: Mapping[str, object],
    model: AcceptedMetamodel,
    shadow: TemporalShadow,
    unit_inserted: set[ObjectKey],
    source: ObservedNodes | None,
) -> _ResolvedWrite:
    """One TEMPORAL writeSequence/scenario entry -> its canonical keyed
    instruction plus the observation its close/chain consumes.

    Where the observation comes from is what ``source`` decides. Absent one, it is
    the milestone ``shadow`` tracks for this key (`m-txtime-write` /
    `m-bitemp-write` "the engine supplies observed rows from case state" — never
    an implicit resolving read), which is how every writeSequence entry and every
    ungrouped scenario write resolves; a milestone a materializing predicate write
    of this case already moved (:func:`_refuse_materialized_case_state`), and one
    whose tracked members can no longer account for the whole stored row
    (:func:`_refuse_unaccounted_document_milestone`), are both refused first.
    Given one, the entry's own
    step named a find of its `uow` group with ``on``, and the evidence is the
    Observation Key the active unit of work filed that node under
    (:func:`_settled_against_source`).

    The corpus and canonical instruction share the same ``validFrom`` / ``until``
    spelling. Bounds are instruction-level fields; temporal row payloads never
    carry authoring aliases. A temporal entry carries exactly ONE row, which
    :func:`_temporal_entry_row` enforces rather than assumes.

    That row reaches the same :func:`_durable_row` seam every other producer's
    does, which entitles a temporal row to no observation control key at all —
    the observation this entry consumes is a whole predecessor milestone, never a
    cell the row carried.

    ``unit_inserted`` is the SAME choreography unit's own running set of
    (entity, pk) pairs a PRIOR entry in this SAME buffer already inserted
    (`m-unit-work` same-transaction coalescing, `m-txtime-write-008` /
    `m-bitemp-write-014`): a later entry targeting one of them is a
    same-buffer coalescing candidate whose OWN close/chain arithmetic never
    runs (the planner folds it into the pending insert before finalization
    ever sees it) — its observation is forced to `None`, and with no observation
    consumed there is no milestone for it to retire. What the ledger ends up
    holding for the key is the COALESCED row: :func:`_lower_resolved` tracks the
    surviving Planned Insert off the finished plan, so the tracked state is the
    milestone the flush actually writes rather than a stand-in for it.
    """
    mutation = cast("str", entry["mutation"])
    entity_name = cast("str", entry["entity"])
    raw_rows = cast("Sequence[Mapping[str, object]]", entry["rows"])
    row, _authored_none = _durable_row(
        model, entity_name, mutation, _temporal_entry_row(entity_name, mutation, raw_rows)
    )
    valid_from = cast("str | None", entry.get("validFrom"))
    until = cast("str | None", entry.get("until"))
    doc: dict[str, object] = {"mutation": mutation, "entity": entity_name, "rows": [row]}
    if valid_from is not None:
        doc["validFrom"] = valid_from
    if until is not None:
        doc["until"] = until
    instruction = instructions.deserialize(doc)
    instructions.validate_instruction(instruction, model)
    assert isinstance(instruction, KeyedWrite)  # a temporal entry is always keyed
    entity_metadata = case_entity(model, entity_name)
    pk_key = object_key(instruction, model)
    is_insert = mutation in _TEMPORAL_INSERT_MUTATIONS
    is_coalescing_candidate = not is_insert and pk_key is not None and pk_key in unit_inserted
    observation: TemporalObservation | None = None
    evidence: WriteEvidence = None
    if not is_insert and not is_coalescing_candidate:
        if source is None:
            _refuse_materialized_case_state(model, entity_metadata, row, shadow)
            _refuse_unaccounted_document_milestone(model, entity_metadata, row, shadow)
            observation = shadow.resolve(model, entity_metadata, row)
            evidence = observation
        else:
            settled = _settled_against_source(entity_name, pk_key, source)
            evidence, observation = settled
    if observation is not None and not is_coalescing_candidate:
        shadow.retire(model, entity_metadata, observation)
    if is_insert and pk_key is not None:
        unit_inserted.add(pk_key)
    return _ResolvedWrite(instruction, evidence, observation)


def _settled_against_source(
    entity_name: str, pk_key: ObjectKey | None, source: ObservedNodes
) -> tuple[WriteEvidence, TemporalObservation]:
    """The evidence a write settles against when its step named the find it came
    from (`m-case-format` *Settling against a grouped find*).

    The named find's own record for this key is the evidence the write was handed,
    so the slot the unit of work filed it under is the one the write settles
    against — production's own Observation Key, naming the milestone the read
    actually saw, rather than a coordinate this engine re-derived and hoped
    agreed. That is what makes a store keyed by identity alone observably wrong
    here: a key holding several current rectangles has no single answer, while the
    filed record names exactly one.

    Returns the key the real write settles by beside the observation the pure
    re-lowering oracle plans with — one record, so the two can never disagree. A
    miss returns neither and the close is refused where every unobserved close is.
    A named find that observed no row of this key — or several, which no single
    value could have come from — is an authoring defect, refused here where the
    diagnosis can name the step.
    """
    matched = [record for record in source if record.key.object_key == pk_key]
    if len(matched) != 1:
        raise EngineError(
            f"{entity_name!r}: the find step this write settles against observed "
            f"{len(matched)} rows of {pk_key!r} — a keyed write settles against the ONE "
            "milestone the value it was handed came from (m-case-format 'Settling against "
            "a grouped find')"
        )
    record = matched[0]
    # A milestone coordinate files only a Temporal Observation; a versioned row's
    # evidence has none and can never answer this lookup.
    assert isinstance(record.observation, TemporalObservation)
    return record.key, record.observation


def _is_predicate_write_step(raw_write: object) -> bool:
    """Whether a scenario write step's own ``write`` field is a single
    STRUCTURED PREDICATE-write instruction (`mutation` / `target` / optional
    `assignments` — `m-case-format`'s predicate-selected shape, e.g.
    ``m-batch-write-005``) rather than the keyed-write entry LIST
    (`m-case-format`'s buffered-keyed-write shape) this engine's keyed path
    lowers. A predicate write's `target` names its entity/predicate; a keyed
    write is a plain list of ``{mutation, entity, rows}`` entries — the SHAPE
    signal (a bare mapping vs. a list) is structural, never inferred from a
    ``KeyError``; this shape routes to the readless/materializing
    predicate-write
    translation instead — see :func:`_lower_predicate_write_step` /
    :func:`_run_materializing_pair`.
    """
    return isinstance(raw_write, Mapping)


def _write_entries(raw_write: object) -> Sequence[Mapping[str, object]]:
    """A scenario write step's own ``write`` field as its keyed-write entry
    LIST — callers check :func:`_is_predicate_write_step` FIRST; this is never
    reached for a structured predicate-write instruction."""
    return cast("Sequence[Mapping[str, object]]", raw_write)


def _canonical_predicate_doc(raw_write: Mapping[str, object]) -> dict[str, object]:
    """A scenario predicate-write step's own ``write`` field, translated to the
    canonical ``write-instruction.schema.json`` predicate shape
    (`m-case-format` "Predicate-selected write instruction"): ``at`` (the
    Clock-context Transaction-Time instant) is DROPPED — never an instruction
    field, ADR 0010. ``validFrom`` and ``until`` already use the canonical
    spelling. Every caller that hands a raw case document to
    :func:`~parallax.core.unit_work.instructions.deserialize` routes through
    this first — the canonical deserializer rejects ``at``/``until`` outright
    as unexpected keys.
    """
    doc = dict(raw_write)
    doc.pop("at", None)
    return doc


# --------------------------------------------------------------------------- #
# Case-format ingestion decode (m-case-format / m-core): a case authors a      #
# neutral write row in the SAME portable wire spellings a read golden does     #
# (a decimal or a sub-microsecond-free timestamp as a bare number/ISO string,  #
# bytes as lowercase hex, a uuid as a canonical string) — never the native     #
# carrier the developer-facing write validators now require (they moved off   #
# the full wire decode onto the narrower input-policy widening,               #
# `~parallax.core.base.coerce_neutral_input`). This is the ONE seam that      #
# lowers a case-authored row/assignment to native carriers before it ever     #
# reaches `validate_write` / `validate_write_assignment` on the developer      #
# verb's own path -- decoding a value already native, or one no branch        #
# recognizes, is a no-op (`decode_neutral_literal` is total and idempotent),  #
# so calling this twice, or on an already-native row, changes nothing.        #
# --------------------------------------------------------------------------- #
def decode_write_row(
    entity: EntityMetadata, row: Mapping[str, object], model: AcceptedMetamodel
) -> dict[str, object]:
    """One case-authored neutral write row, its wire-spelled scalar leaves
    decoded to native carriers.

    Mirrors ``write_validate.validate_write``'s own structural walk --
    ``entity``'s family-effective attributes and applicable value objects
    (`m-inheritance` "Inherited members") -- but TRANSFORMS rather than
    validates: each present, non-null scalar leaf decodes through
    :func:`~parallax.core.base.decode_neutral_literal` against its declared
    type, and a present value-object document (or each element of a `many`
    occurrence) recurses the same way over its own declared composite
    (:func:`_decoded_vo_value`). An absent field, an explicit null, a
    DB-computed write marker, and every non-attribute control key are
    returned exactly as authored.
    """
    view = inheritance.view(model).entity(entity.identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        return dict(row)
    decoded = dict(row)
    for attribute in view.applicable_attributes:
        name = attribute.identity.name
        if name in decoded and decoded[name] is not None:
            decoded[name] = decode_neutral_literal(decoded[name], attribute.type)
    for value_object in view.applicable_value_objects:
        name = value_object.identity.path[-1]
        if name in decoded and decoded[name] is not None:
            decoded[name] = _decoded_vo_value(value_object, decoded[name])
    return decoded


def _decoded_vo_value(
    container: ValueObjectMetadata | NestedValueObjectMetadata, value: object
) -> object:
    """One present Value Object occurrence's own value, decoded leaf by leaf.

    Mirrors ``parallax.core.metamodel.vo_document_violation``'s structural
    walk: a `many` occurrence decodes each element, a to-one occurrence
    decodes the one document. A value the walk cannot make sense of (not a
    list, not a mapping) is left unchanged -- that reading is what classifies
    it as a rejection; this function only ever transforms an otherwise
    well-shaped document's own scalar leaves.
    """
    if container.multiplicity is Multiplicity.MANY:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return value
        return [
            _decoded_vo_element(container, element) for element in cast("Sequence[object]", value)
        ]
    return _decoded_vo_element(container, value)


def _decoded_vo_element(
    container: ValueObjectMetadata | NestedValueObjectMetadata, value: object
) -> object:
    if not isinstance(value, Mapping):
        return value
    document = dict(cast("Mapping[str, object]", value))
    for attribute in container.attributes:
        name = attribute.identity.name
        if name in document and document[name] is not None:
            document[name] = decode_neutral_literal(document[name], attribute.type)
    for nested in container.value_objects:
        name = nested.identity.path[-1]
        if name in document and document[name] is not None:
            document[name] = _decoded_vo_value(nested, document[name])
    return document


def _decoded_assignment_value(
    entity: EntityMetadata, member: str, value: object, model: AcceptedMetamodel
) -> object:
    """One predicate-write assignment's case-authored value, decoded against
    ``member``'s declared type on ``entity`` -- :func:`decode_write_row`'s
    per-leaf decode, applied to a single named member rather than a whole
    row."""
    position = inheritance.view(model).entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return value
    for attribute in position.applicable_attributes:
        if attribute.identity.name == member:
            return decode_neutral_literal(value, attribute.type)
    for value_object in position.applicable_value_objects:
        if value_object.identity.path[-1] == member:
            return _decoded_vo_value(value_object, value)
    return value


def _decoded_predicate_write(
    instruction: PredicateWrite, model: AcceptedMetamodel
) -> PredicateWrite:
    """``instruction``'s own assignment values, decoded
    (:func:`_decoded_assignment_value`) against its target entity's declared
    member types -- the predicate-write analogue of :func:`decode_write_row`,
    one assignment at a time rather than one row.

    Building a SEPARATE decoded instruction (rather than mutating
    ``instruction`` in place) matters where a caller validates the decoded
    copy but still lowers the ORIGINAL, case-authored one (`_lower_predicate_write_step`'s
    own docstring): the compile lane's emitted bind must stay the EXACT value
    the case authored, so decoding cannot be allowed to leak into it.
    """
    if not instruction.assignments:
        return instruction
    entity = case_entity(model, instruction.target.entity)
    assignments = tuple(
        WriteAssignment(
            assignment.attr,
            _decoded_assignment_value(
                entity, assignment.attr.rpartition(".")[2], assignment.value, model
            ),
        )
        for assignment in instruction.assignments
    )
    return replace(instruction, assignments=assignments)


def _is_versioned_entity(model: AcceptedMetamodel, entity_name: str) -> bool:
    declaring = _family_declarer(model, case_entity(model, entity_name))
    return any(attr.optimistic_locking for attr in declaring.declared_attributes)


def _observation_refusal(
    model: AcceptedMetamodel, entity_name: str, mutation: str, key: str
) -> str | None:
    """Why a write row against ``entity_name`` under ``mutation`` may not author
    the reserved observation control key ``key`` — ``None`` when that pair is the
    ONE the corpus vocabulary entitles to author it.

    This is the whole licensing rule `m-unit-work`'s "Absence is structural"
    states, total over every (target, mutation) pair a case can write, so no
    producer decides any part of it locally. A VERSIONED, NON-TEMPORAL update or
    delete may author ``observedVersion``; nothing else may author anything:

    - neither half of an observed milestone's own EDGE coordinate
      (``observedTxStart`` / ``observedValidStart``) is entitled ANYWHERE. Neither
      is a write-row control key in any shape:
      `compatibility-case.schema.json`'s ``writeRow`` reserves ``observedVersion``
      alone and every other key names an entity member, while a temporal close's
      observed coordinate rides beside the write, at ``when.observedTxStart`` /
      ``when.observedValidStart`` — and, on a retry attempt, ``observedTxStart``
      alone (`m-case-format`). Stripping one from a row — or projecting the row
      past it — would silently discard the very coordinate the author meant to
      observe.
    - a TEMPORAL target's write observes a whole predecessor MILESTONE, which no
      flat row cell can name. It resolves either from tracked case state
      (:class:`~parallax.conformance.temporal_state.TemporalShadow`) or, where the
      write's own step named the find it settles against, from the observations
      that `uow` group's reads filled (:func:`_settled_against_source`); a
      standalone close's gate is authored beside the write. Which of the two
      supplies it changes nothing here: neither is a cell the row may carry.
    - an INSERT opens a row rather than writing against one, so an observed
      version names a milestone that does not yet exist.
    - an UNVERSIONED non-temporal target has no version to observe, so an
      observed version on it is evidence about nothing. Wrapping such a row would
      still exclude it from batching, splitting a collapsible run into one
      statement per key on the strength of an observation the planner then
      ignores.

    The last two restate what `compatibility-case.schema.json`'s own prose
    already says — "absent on a versioned insert and on a non-versioned write" —
    and which its single shared ``writeRow`` definition cannot express. Deciding
    them here is what makes the carrier's own guarantee complete: the carrier can
    decide "is this an insert?" from the instruction alone, but "is this target
    versioned?" and "is it temporal?" need the model, which only this translation
    holds.
    """
    if key in {_TEMPORAL_GATE_KEY, _TEMPORAL_VALID_START_KEY}:
        return (
            f"a write row authors no `{key}` (m-case-format: an observed milestone's own edge "
            "coordinate rides beside the write, at `when.observedTxStart` / "
            "`when.observedValidStart`, or an attempt's own `observedTxStart`; a writeRow "
            "reserves `observedVersion` alone and every other key names an entity member)"
        )
    if _is_temporal_entity(model, entity_name):
        return (
            f"a temporal row authors no `{key}` (m-unit-work: a temporal write observes a whole "
            "predecessor milestone, which no flat row cell can name — the engine resolves one "
            "from tracked case state or from the find its own step settles against, and a "
            "standalone close's gate rides beside the write)"
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


def _durable_row(
    model: AcceptedMetamodel, entity_name: str, mutation: str, row: Mapping[str, object]
) -> tuple[dict[str, object], VersionObservation | None]:
    """One case-authored write row as the DURABLE row a write carries, plus the
    Version Observation that row described (``None`` when it described none — an
    unobserved write, one whose observation instead comes from this SAME `uow`
    group's own prior find step (:func:`_observed_nodes`), or a temporal
    write, whose observation is a whole milestone — held by
    :class:`TemporalShadow`, or, where the step named the find it settles against,
    by that same group's observations).

    THE seam a case row becomes a durable row through — the only one. Every
    producer of a case-authored row goes through it, whatever the row's shape or
    lane: :func:`_build_instructions` for a non-temporal writeSequence/scenario
    entry, :func:`_build_temporal_instruction` for a temporal one,
    :func:`_resolve_conflict_writes` for a non-temporal conflict attempt's
    ``write``, and :func:`_run_conflict_close` for a temporal attempt's close
    row. EVERY row of each reaches it, not merely the first: the two non-temporal
    producers resolve the whole authored sequence (:func:`_durable_rows`), and the
    two temporal ones admit a single row and refuse a plural entry outright
    (:func:`_temporal_entry_row`, :func:`_conflict_close_row`) rather than
    settling one row and discarding the rest.

    Refusal (:func:`_observation_refusal`) and stripping are one
    indivisible step here precisely because they were separable before: a
    producer that copied the row itself got a perfectly usable durable row while
    silently skipping the refusal, and each new write shape rediscovered the
    hole. There is now no way to obtain a durable row without being refused.

    The durable row never carries a control key: the write-instruction schema
    forbids every one of them (ADR 0013), which `instructions.deserialize`
    enforces for the lanes that reach it and which the lanes that bypass it — a
    standalone close settles straight through
    :func:`~parallax.snapshot.handle.plan_temporal_close` — depend on this seam
    for.
    """
    for key in _ROW_OBSERVATION_KEYS:
        if key not in row:
            continue
        refusal = _observation_refusal(model, entity_name, mutation, key)
        if refusal is not None:
            raise EngineError(f"{entity_name!r} {mutation!r}: {refusal}")
    durable = dict(row)
    version = durable.pop(_VERSION_OBSERVATION_KEY, None)
    if version is None:
        return durable, None
    return durable, VersionObservation(observed_version=cast("int", version))


def _durable_rows(
    model: AcceptedMetamodel,
    entity_name: str,
    mutation: str,
    raw_rows: Sequence[Mapping[str, object]],
) -> list[tuple[dict[str, object], VersionObservation | None]]:
    """Every row of one multi-row write entry through :func:`_durable_row`,
    resolved EAGERLY so an entry is refused on any row it authors before its
    first row is planned — a partially translated entry is never observable."""
    return [_durable_row(model, entity_name, mutation, row) for row in raw_rows]


def _binds_row_observations(
    model: AcceptedMetamodel,
    entity_name: str,
    mutation: str,
    raw_rows: Sequence[Mapping[str, object]],
) -> bool:
    """Whether a non-temporal write entry's rows each carry their OWN object key
    and observation, mirroring what that many separate
    `Transaction.insert`/`.update`/`.delete` calls would buffer — rather than
    arriving as anonymous rows free to be merged back together.

    This decides OBSERVATION BINDING only, never statement count:
    :func:`_build_instructions` buffers one single-row instruction per row
    regardless, and leaves every merge to the planner's own collapse stage
    (:func:`_lower_resolved`, `parallax.snapshot.handle.Database.transact`).
    What a bound observation changes is that the planner refuses to merge that
    row at all, which is exactly the point — a merged multi-row instruction has
    nowhere to carry a per-row observed version. The question is answered with
    :func:`~parallax.core.batch_write.collapses`, the same injected
    `m-batch-write` collapse-eligibility vocabulary the planner consults, so
    binding an observation never contradicts the planner's own eligibility
    answer.

    Derived SEMANTICALLY from the instruction and model — mutation kind,
    versioned-ness, computed/allocated primary keys, and (for update) per-key
    value uniformity — never from the case's own authored ``statements`` count,
    which is a count-consistency ASSERTION only (`compatibility-case.schema.
    json`) verified separately by
    :func:`_check_statement_count_consistency`, never a semantics
    discriminator:

    - a single row always binds its own observation (nothing to merge it with,
      so nothing is given up);
    - `batch_write.insert_collapses` — an INSERT decomposes only when the
      target's primary key is pk-gen MANAGED (`m-pk-gen`'s `sequence`/`max`
      strategies, ``m-pk-gen-001``..`-012``); a VERSIONED insert still
      collapses (the initial version is a derived constant, never observed);
    - `batch_write.update_collapses` — a VERSIONED target's update always
      decomposes (the gate/advance binds a per-row observed version,
      `m-opt-lock`, ADR 0014); an unversioned target decomposes per distinct
      key only when its rows assign NON-uniform values (``m-batch-write-002``),
      collapsing into one `IN`-predicate statement when uniform
      (``m-batch-write-001``'s own update entry);
    - `batch_write.delete_collapses` — a VERSIONED target's delete always
      decomposes (``m-batch-write-004``'s versioned per-key delete
      materialize); an unversioned one collapses to one `IN`-list statement.
    """
    if len(raw_rows) == 1:
        return True
    entity = case_entity(model, entity_name)
    return not batch_write.collapses(model, entity, mutation, raw_rows)


def _check_statement_count_consistency(
    entries: Sequence[Mapping[str, object]], emitted_count: int
) -> None:
    """``statements`` is a count-CONSISTENCY assertion the schema intends
    (`compatibility-case.schema.json`), never a semantics discriminator — verify
    the authored count against the statements this buffer's flush ACTUALLY
    emitted and fail loudly on a mismatch (an authoring error), rather than
    silently trusting either number.

    ``emitted_count`` comes from the real plan (:func:`_lower_resolved`), so the
    assertion sees every stage the planner applies — coalescing, physical-shape
    collapse, and the ELISION that drops a keyed update whose effective change
    set is empty (`m-opt-lock`'s no-op write) — rather than a second,
    drift-prone reconstruction of them.

    Only a writeSequence entry authors ``statements`` (a buffered scenario write
    entry has no such key at all), and a writeSequence entry is planned ALONE,
    so the sum below spans exactly one entry in practice; summing is what
    `m-case-format` asserts either way ("the DML statement count MUST equal the
    sum of the steps' declared statement counts"). An entry that authors nothing
    grades nothing.
    """
    declared = [entry.get("statements") for entry in entries]
    if any(count is None for count in declared):
        return
    expected = sum(cast("int", count) for count in declared)
    if expected != emitted_count:
        described = ", ".join(
            f"{entry.get('entity')!r} {entry.get('mutation')!r}" for entry in entries
        )
        raise EngineError(
            f"{described}: authored `statements: {expected}` does not match the "
            f"{emitted_count} statement(s) this flush emits (m-case-format: `statements` is a "
            "count-consistency assertion, not a semantics discriminator)"
        )


def _seed_insert_version(
    model: AcceptedMetamodel, entity_name: str, mutation: str, row: Mapping[str, object]
) -> dict[str, object]:
    """A VERSIONED, non-temporal entity's INSERT row, with the derived initial
    version seeded when the case-authored row omits it
    (`opt_lock.INITIAL_VERSION`) — a no-op for every other mutation/entity/row
    shape.

    `parallax.snapshot.handle`'s own write finalization derives the INITIAL
    version at the version Attribute UNCONDITIONALLY, ignoring any row-carried
    value
    — every reachable insert witness already authors an explicit `version`
    matching this SAME constant (`m-unit-work-001`/`-008`), coincidentally
    satisfying `~parallax.core.unit_work.write_validate.validate_write`'s
    required-attribute check along the way, but a same-transaction coalescing
    pair whose insert never survives to ANY golden DML
    (`m-unit-work-010`'s insert-then-delete cancellation) has no golden bind
    to match and so may omit it. The RUN lane's own translation
    (`_execute_write_unit`, mirroring "as many separate `Transaction.insert`
    calls") buffers through `Transaction.write_neutral`, and a case's own
    authored `version` is what a required-attribute check would have wanted; since
    the framework discards whatever the row carries at lowering regardless,
    seeding the identical constant here changes no compiled emission and keeps
    the run lane's buffered row the same shape the case authored.
    """
    if mutation != "insert":
        return dict(row)
    version_attr = _versioned_non_temporal_version_attribute(model, entity_name)
    if version_attr is None or version_attr.identity.name in row:
        return dict(row)
    return {**row, version_attr.identity.name: opt_lock.INITIAL_VERSION}


def _build_instructions(
    entry: Mapping[str, object],
    model: AcceptedMetamodel,
    shadow: TemporalShadow,
    unit_inserted: set[ObjectKey],
    group_observations: GroupObservations,
    source: ObservedNodes | None,
) -> list[_ResolvedWrite]:
    """One case write entry -> one or more canonical keyed write instructions.

    A STRUCTURED PREDICATE-write entry (`target`/`predicate` shaped, no
    `entity` key at all) refuses loudly here too — defensive coverage for the
    writeSequence path, which shares this function with every scenario write
    entry (the scenario `write`-field-is-itself-a-mapping shape is caught one
    layer up, by :func:`_is_predicate_write_step`, and routed to the
    readless/materializing predicate-write translation instead — a predicate
    write is never a legal writeSequence entry shape, `m-case-format`'s
    writeSequence vocabulary is keyed-only).

    A TEMPORAL entity's entry dispatches to :func:`_build_temporal_instruction`,
    which admits exactly ONE row: its authored ``statements`` count is the DML
    STATEMENT count (a close plus zero-to-three chained opens), a DIFFERENT
    accounting from the row-decomposition below, which assumes non-temporal
    semantics and is never applied to a temporal entry's entry. Decomposition
    would answer no question there either — a temporal entity never collapses
    (`m-batch-write`), so there is no set-based statement for a decomposed row to
    be re-merged into, and several rows under one entry are several independent
    milestone chains the case must author as several entries.

    Otherwise, a write entry carries the instruction triple (``mutation`` /
    ``entity`` / ``rows``) beside case-authoring keys (``note`` / ``statements``
    / ``roundTrips`` / ``rollback``). ``rows`` MAY batch several logical
    per-object writes into one entry (the write-instruction schema's "one or
    more rows" vocabulary), and this seam ALWAYS buffers one single-row
    instruction per row, exactly as that many separate ``Transaction`` calls
    would. Nothing is ever pre-merged here: whether buffered rows share one
    statement is the planner's own collapse stage to decide.

    :func:`_durable_rows` resolves every row first, so an observation surviving
    from a row belongs to a versioned non-temporal write against an existing row
    — the only write shape `m-unit-work` gives an observation at all.

    What :func:`_binds_row_observations` derives SEMANTICALLY is whether each row
    binds its OWN object key and Version Observation (its reserved
    ``observedVersion`` stripped into one — `m-opt-lock`; ADR 0013), which in
    turn tells the planner to keep that row separately identifiable rather than
    merging it. A row that authors no observed version falls back to
    ``group_observations`` — a writeSequence's own permanently-empty sequence, or
    (the scenario RUN lane only) a `uow` GROUP's own prior find step(s)
    (:func:`_observed_nodes`, via :func:`_run_uow_group`) — by object identity
    alone, since one row per primary key needs no milestone to address it. That is
    why such a write names no source find: identity already addresses its
    evidence, so ``source`` is refused above for a NON-temporal target and reaches
    the temporal branch alone.

    An entry's authored ``statements`` count is graded later, once
    :func:`_lower_resolved` has actually planned and lowered the buffer these
    instructions join (:func:`_check_statement_count_consistency`) — nothing
    here predicts what the flush will emit.
    """
    if "entity" not in entry:
        target = entry.get("target")
        target = (
            cast("Mapping[str, object]", target).get("entity")
            if isinstance(target, Mapping)
            else None
        )
        raise EngineError(
            f"a writeSequence entry must be a keyed mutation (`entity` + `rows`) — a "
            f"structured predicate-selected instruction ({entry.get('mutation')!r} on "
            f"{target!r}) is scenario-write-only (m-case-format: the writeSequence "
            "entry vocabulary is keyed-only)"
        )
    entity_name = cast("str", entry["entity"])
    if source is not None and not _is_temporal_entity(model, entity_name):
        raise EngineError(
            f"{entity_name!r}: a write step naming the find it settles against targets a "
            "TEMPORAL entity — a versioned Non-Temporal target has one row per primary key, so "
            "identity already reaches its group's evidence and the reference names nothing the "
            "resolution does not have (m-case-format 'Settling against a grouped find')"
        )
    if _is_temporal_entity(model, entity_name):
        return [_build_temporal_instruction(entry, model, shadow, unit_inserted, source)]
    mutation = cast("str", entry["mutation"])
    raw_rows = cast("Sequence[Mapping[str, object]]", entry["rows"])
    durable = _durable_rows(model, entity_name, mutation, raw_rows)
    binds_observations = _binds_row_observations(model, entity_name, mutation, raw_rows)
    out: list[_ResolvedWrite] = []
    opens_a_row = mutation in INSERT_MUTATIONS
    for clean_row, row_observation in durable:
        observation: WriteObservation | None = row_observation
        evidence: WriteEvidence = row_observation
        clean_row = _seed_insert_version(model, entity_name, mutation, clean_row)
        instruction = instructions.deserialize(
            {"mutation": mutation, "entity": entity_name, "rows": [clean_row]}
        )
        instructions.validate_instruction(instruction, model)
        if binds_observations and not opens_a_row:
            key = object_key(instruction, model)
            if observation is None and key is not None:
                observed = _observed_for(group_observations, key)
                if observed is not None:
                    evidence, observation = observed.key, observed.observation
        else:
            evidence, observation = None, None
        out.append(_ResolvedWrite(instruction, evidence, observation))
    return out


def _observed_for(observations: GroupObservations, key: ObjectKey) -> handle.ObservedRecord | None:
    """The LATEST record this group's finds filed for ``key``, or ``None``.

    Latest rather than first: a versioned Non-Temporal target holds one row per
    primary key, so a second find of it observes the same object again and its
    evidence supersedes the earlier reading — the overwrite production's own
    observation record performs, expressed over an ordered store instead.
    """
    for record in reversed(observations):
        if record.key.object_key == key:
            return record
    return None


def _resolve_entries(
    entries: Sequence[Mapping[str, object]],
    model: AcceptedMetamodel,
    shadow: TemporalShadow,
    group_observations: GroupObservations,
    source: ObservedNodes | None = None,
) -> list[_ResolvedWrite]:
    """Every entry in one choreography unit's buffer -> its resolved
    instructions (retiring from ``shadow`` the milestone each close consumes) —
    the shared core both the PURE lowering (:func:`_lower_resolved`) and the
    RUN lane's real `db.transact` execution (:func:`_execute_write_unit`)
    consume, so a temporal write's observation is never resolved (or its
    milestone retired) twice for one unit. ``unit_inserted`` tracks this SAME
    buffer's own same-transaction coalescing candidates (see
    :func:`_build_temporal_instruction`) across the whole unit.
    ``group_observations`` is READ-ONLY here — an always-empty sequence for a
    writeSequence entry or an ungrouped scenario write step (neither ever
    consults a find-derived observation), or (the scenario RUN lane only) the
    nodes a `uow` GROUP's own find steps published (:func:`_run_uow_group`) before
    this unit ran — never a store spanning the whole scenario.

    ``source`` is what the step's own ``on`` named (`m-case-format` *Settling
    against a grouped find*): the milestones ONE earlier find of this same group
    observed, which every temporal entry of this step settles against instead of
    against tracked case state. It defaults to absence, which is every lane but a
    grouped scenario write step naming a find."""
    resolved: list[_ResolvedWrite] = []
    unit_inserted: set[ObjectKey] = set()
    for entry in entries:
        resolved.extend(
            _build_instructions(entry, model, shadow, unit_inserted, group_observations, source)
        )
    return resolved


def _buffered(
    instruction: WriteInstruction, observation: WriteObservation | None
) -> WriteInstruction | ObservedKeyedWrite:
    """One resolved entry as the buffer item a unit of work would hold for it.

    An entry whose case document (or this group's own prior find) supplied an
    observation travels with it, exactly as a developer verb's own resolution
    does; an unobserved entry stays bare, so absence is the absence of the
    wrapper here too. Whether an observation may exist at all is decided BEFORE
    this point, by :func:`_durable_row` — the one seam every producer's rows pass
    through — and by the carrier's own structural refusals; this function only
    forwards what they left.
    """
    return buffered_write(instruction, observation)


def _lower_resolved(
    resolved: Sequence[_ResolvedWrite],
    entries: Sequence[Mapping[str, object]],
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    tx_instant: str,
    shadow: TemporalShadow,
) -> tuple[LoweredStatement, ...]:
    """Plan one write buffer through the SAME ``build_write_planner`` factory
    the composition layer uses (`parallax.snapshot.handle.Database.transact`)
    and lower each survivor — PURE, no database. The planner is the ONE
    authority that merges a case entry's rows: every entry arrives as its own
    per-row instructions, and which of them share a statement is decided HERE,
    per physical shape, by the same `batch_write.collapses` eligibility answer
    production consults.

    ``entries`` are the case entries ``resolved`` was built from, carried only so
    their authored ``statements`` counts can be graded against the statements
    this ONE plan actually emits (:func:`_check_statement_count_consistency`) —
    the count is never derived from a second, reconstructed plan.

    The case-state ledger advances HERE, from THIS plan's own opened rows
    (:meth:`TemporalShadow.track_opened`) — the milestone a later choreography
    unit observes is the one this write actually plans, so there is no second
    expansion of the same topology to drift from it. The close's retirement
    happened at resolution, where the observation it consumed is known. Both
    advances belong to the boundary the caller stages them on
    (:meth:`TemporalShadow.staged`), so a doomed unit's are discarded with its
    rows.
    """
    buffer = [_buffered(write.instruction, write.oracle_observation) for write in resolved]
    instant = _pinned_instant(tx_instant)
    plan = build_write_planner(model).plan(
        PlanningRequest(
            subject_identity=_PLANNING_SUBJECT,
            transaction_instant=instant,
            concurrency=concurrency,
            buffered_writes=buffer,
        )
    )
    statements = [statement for _step, statement in stream_lowered(plan, model, dialect)]
    _check_statement_count_consistency(entries, len(statements))
    shadow.track_opened(model, plan)
    return tuple(statements)


def _lower_writes(
    entries: Sequence[Mapping[str, object]],
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    shadow: TemporalShadow,
    tx_instant: str,
    group_observations: GroupObservations,
) -> tuple[LoweredStatement, ...]:
    """Resolve and PURE-lower one write buffer — the COMPILE lane's own
    lowering, and the RUN lane's emissions/round-trips oracle (`_execute_write_unit`
    resolves its own entries via :func:`_resolve_entries` and reuses
    :func:`_lower_resolved` directly, rather than calling this a second time, so
    each consumed observation is retired once and the buffer's one plan is
    tracked once)."""
    resolved = _resolve_entries(entries, model, shadow, group_observations)
    return _lower_resolved(resolved, entries, model, dialect, concurrency, tx_instant, shadow)


def _lower_predicate_write_step(
    raw_write: Mapping[str, object],
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency,
) -> LoweredStatement:
    """Lower a READLESS scenario predicate-write step (`m-batch-write-005`/
    ``-006``) to its ONE statement — PURE, no database. Deserializes +
    validates the canonical instruction, then reuses the SAME
    ``build_write_planner`` -> ``stream_lowered`` seam every other write path
    does (batching is a structural no-op for a lone predicate write).

    Validation runs against a DECODED copy of the instruction
    (:func:`_decoded_predicate_write`) — an assignment value may carry a case
    wire spelling (`m-core-007`'s own decimal sibling) the coercion-only
    developer-facing validator would otherwise reject — but ``instruction``
    itself, the one this function actually lowers, stays exactly as authored:
    this is a compile-time PURE re-lowering whose emitted bind is graded
    byte-exact against the case's own golden, so decoding must never leak
    into the value that reaches planning.

    A MATERIALIZING predicate write never reaches here: its case carries
    ``compileEligibility: run-only``, which short-circuits at
    :func:`eligibility` before the compile lane ever calls this — reaching
    this seam with one is therefore always a caller wiring defect, surfaced as
    planning's own defensive :class:`~parallax.core.unit_work.WritePlanningError`.
    """
    instruction = instructions.deserialize(_canonical_predicate_doc(raw_write))
    assert isinstance(instruction, PredicateWrite)  # a predicate-shaped step always builds this
    instructions.validate_instruction(_decoded_predicate_write(instruction, model), model)
    # A readless predicate write declares no Transaction-Time boundary, so the
    # inert instant it carries is never captured (ADR 0010).
    instant = _pinned_instant(_INERT_CLOCK_INSTANT)
    plan = build_write_planner(model).plan(
        PlanningRequest(
            subject_identity=_PLANNING_SUBJECT,
            transaction_instant=instant,
            concurrency=concurrency,
            buffered_writes=[instruction],
        )
    )
    statements = [statement for _step, statement in stream_lowered(plan, model, dialect)]
    assert len(statements) == 1  # a readless predicate write is always exactly one statement
    return statements[0]


def _compile_find(
    step: Mapping[str, object],
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency | None,
    *,
    result_form: Literal["row", "instance"] = "instance",
) -> CompiledRead:
    """Compile a scenario ``find`` step through the read path with the read-lock
    suffix — the COMPILE lane's own oracle, which reaches no database.

    Every RUN lane instead executes the step through the public Wire read
    (:func:`_run_standalone_find`, :func:`_run_uow_group`) and reports the
    statement production actually ran, so this function answers the compile lane
    alone.

    A scenario find is an in-transaction object find; ``concurrency`` (the case's
    own ``when.uow.concurrency``) is the unit of work's Concurrency PREFERENCE,
    which resolves against the step's own target Entity into the Effective
    Concurrency Strategy that decides the ``m-sql`` shared-row-lock suffix
    (``for share of t0``) — through
    :func:`~parallax.snapshot.handle.entity_read_lock`, the same seam the
    production `Transaction.find` derives every level's lock through. The
    Locking strategy renders the suffix after every clause; the Optimistic one
    renders none (the `m-txtime-write-008` / `m-bitemp-write-014` coalescing
    witnesses exercise that branch). ``None`` ALSO renders none — a read case
    declaring no `when.uow` at all, which models the plain, non-transactional
    `db.find` surface.

    ``result_form`` defaults to ``instance`` — an ORDINARY (managed) scenario
    find mirrors production ``Transaction.find`` (`m-sql` *Read projection*,
    slot 4 included); for a value-object-free entity row-form and instance-form
    are byte-identical, so the default only matters to VO-bearing targets.
    A materializing predicate write's OWN internal resolving read is ROW-form
    (`m-value-object-047` pins its need-driven Document projection) but is compiled by
    the materializing predicate-write resolve in `parallax.snapshot.handle`
    directly, never through this function — the RUN lane reports its ACTUAL
    executed SQL off the transaction's own Execution Log
    (:func:`_run_materializing_pair`), not a separate pure re-lowering (its
    binds are query-result-dependent, so no pure oracle exists to compute them
    from).

    This composition — `compile_read` + `entity_read_lock`, mirroring
    `Transaction.find`'s own derivation — is IRREDUCIBLE adapter content, not
    a residual "mirrors production" gap to close. The case-driven engine has
    no typed Python entity classes at all (a scenario step is a raw,
    case-authored dict carrying a serialized Object Query), so
    there is no `LoweredStatement` to hand a production seam — `Transaction.find`
    itself REQUIRES one. Re-routing through a production API would mean
    inventing a new one solely to serve this untyped input, the opposite of
    engine-thinning; this function stays the adapter's own translation from
    "raw case step" to compiled read, composing production's `m-sql` /
    `m-read-lock` building blocks rather than duplicating their logic.
    """
    query = _step_query(step)
    metadata = case_entity(model, query.target.canonical)
    entity_query = _canonicalize_read(query, metadata, model)
    return compile_read(
        entity_query,
        model,
        dialect,
        result_form=result_form,
        lock=handle.entity_read_lock(model, metadata.identity, concurrency),
    )


def _step_query(step: Mapping[str, object]) -> ObjectQueryNode:
    """A scenario or coherence read step's own canonical Object Query.

    The query travels as authored. Root as-of injection and per-hop navigation
    canonicalization are `deep_fetch.plan`'s own first step on every production
    read path, so applying them here would apply them twice; the compile lane's
    :func:`_compile_find` composes them itself precisely because it reaches no
    executor.
    """
    query_doc = step.get("objectQuery")
    if query_doc is None:
        raise EngineError("a scenario read step needs `objectQuery`")
    return deserialize_query(query_doc)


def _trace_statements(snapshot: handle.Snapshot[Any]) -> tuple[LoweredStatement, ...]:
    """The statements a read actually ran, in call order — a find step's
    emission, read off its own Read Trace rather than re-lowered beside it."""
    return tuple(call.statement for call in snapshot.execution.calls)


def _run_standalone_find(
    port: DbPort,
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency | None,
    step: Mapping[str, object],
) -> handle.Snapshot[handle.WireEntity]:
    """Run one UNGROUPED scenario find step through the production Wire read.

    A step carrying its scenario's Concurrency Preference runs inside a real
    ``db.transact`` so the read participates exactly as :func:`run_read_case`
    does and exactly as a developer's ``tx.find`` would: whether it takes the
    shared row lock is then the target Entity's own Effective Concurrency
    Strategy, never a property of the preference alone or of what the scenario
    goes on to write.
    """
    query = _step_query(step)
    db = handle.Database(port, model, dialect=dialect)
    if concurrency is None:
        return db.wire.find(query)
    return db.transact(lambda tx: tx.wire.find(query), concurrency=concurrency).value


def _graph_rows(
    model: AcceptedMetamodel, entity_name: str, snapshot: handle.Snapshot[handle.WireEntity]
) -> list[Mapping[str, object]]:
    """A Wire result's roots as physically-keyed rows — the interleaved lane's
    own ``expectRows`` oracle.

    The corpus states a find step's expectation in the projection's own physical
    spelling while a Wire root is keyed by declared member name, so each member's
    value is re-keyed by the slot it occupies. It is a rendering of what
    production published, never a second traversal.
    """
    columns = _member_columns(model, entity_name)
    return [
        {
            columns[name]: value
            for name, value in (_graph_root(root) or {}).items()
            if name in columns
        }
        for root in snapshot.checked().results()
    ]


def _member_columns(model: AcceptedMetamodel, entity_name: str) -> Mapping[str, str]:
    """Each declared member name of ``entity_name`` paired with its own column."""
    position = inheritance.view(model).entity(case_entity(model, entity_name).identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return {}
    columns = {
        attribute.identity.name: attribute.storage.name
        for attribute in position.applicable_attributes
    }
    columns.update(
        {
            occurrence.identity.path[-1]: occurrence.storage.name
            for occurrence in position.applicable_value_objects
        }
    )
    return columns


def _lower_scenario_step(
    context: _GroupContext,
    step: Mapping[str, object],
    index: int,
    find_lock: Concurrency | None,
    group_observations: GroupObservations,
) -> _LoweredStep:
    """One scenario step's pointer + DML, PURE — the compile lane's own per-step
    interpreter, the peer of the run lane's :func:`_run_group_step`.

    Which boundary the step belongs to is deliberately NOT decided here: a
    doomed unit's case-state advances are staged by the caller
    (:func:`_scenario_lowered`), the one place a step's own transaction is
    known.
    """
    if "write" not in step:
        statement = _compile_find(step, context.model, context.dialect, find_lock).statement
        return _LoweredStep(f"/scenario/{index}/objectQuery", (statement,), False, False)
    raw_write = step["write"]
    rollback = step.get("rollback") is True
    if _is_predicate_write_step(raw_write):
        # Readless only (`m-batch-write-005`/`-006`) — a materializing predicate
        # write never reaches the compile lane at all (its case's
        # `compileEligibility: run-only` short-circuits before
        # `_scenario_lowered` ever runs).
        statement = _lower_predicate_write_step(
            cast("Mapping[str, object]", raw_write),
            context.model,
            context.dialect,
            context.concurrency,
        )
        return _LoweredStep(f"/scenario/{index}/write", (statement,), True, rollback)
    entries = _write_entries(raw_write)
    statements = _lower_writes(
        entries,
        context.model,
        context.dialect,
        context.concurrency,
        context.shadow,
        _entry_instant(entries[0]),
        group_observations,
    )
    return _LoweredStep(f"/scenario/{index}/write", statements, True, rollback)


def _doomed_group_spans(case_name: str, steps: Sequence[Mapping[str, object]]) -> dict[int, int]:
    """Each DOOMED `uow` group's own step span, keyed ``start -> end`` inclusive.

    Only the doomed ones: a committing group's steps need no staging, so leaving
    them out lets the caller drive them as ordinary steps. The two spans this
    lane cannot represent answer emptily — an interleaved two-group race
    (:func:`_scenario_uow_spans` returns ``None``) needs two concurrent units a
    pure lowering has no way to model, and every case carrying that shape is
    `compileEligibility: run-only` for the same reason.
    """
    spans = _scenario_uow_spans(case_name, steps)
    if spans is None:
        return {}
    return {start: end for start, end in spans.values() if _group_is_doomed(steps, start, end)}


def _scenario_lowered(case: case_format.Case, dialect_name: str) -> list[_LoweredStep]:
    """Lower every scenario step to its pointer + DML — pure (no database).

    One :class:`TemporalShadow` spans the whole scenario:
    a later write step's temporal close/chain observes an
    earlier step's own opened milestone(s), never the database. The compile
    lane consults NO find-derived observation:
    a keyed write whose version bind is the framework-owned
    advance of a version this SAME scenario's own observing find returned is
    query-result-dependent (`m-conformance-adapter` "Compile eligibility") and
    is therefore declared `compileEligibility: run-only` in the corpus, so it
    short-circuits at :func:`eligibility` before this function ever runs
    (`adapter.compile_case`). The group observation store stays permanently
    empty here — every keyed write this lane reaches resolves its observation
    from its OWN row's reserved ``observedVersion`` control key only
    (:func:`_durable_row`), exactly as a writeSequence entry does.

    A DOOMED unit's advances are staged on that unit's own outcome, exactly as
    the run lane stages them
    (:meth:`~parallax.conformance.temporal_state.TemporalShadow.staged`): a
    doomed group's own later steps observe them and the group's last step
    restores them, and an ungrouped `rollback: true` write step restores them
    after itself. Both lanes must reach the same DML for the same case, and a
    step after an abort takes its milestone from the write the database kept.
    """
    model = load_case_metamodel(case)
    concurrency = _concurrency(case)
    context = _GroupContext(model, dialect_for(dialect_name), concurrency, TemporalShadow())
    group_observations: GroupObservations = []
    lowered: list[_LoweredStep] = []
    try:
        steps = _scenario_steps(case)
        find_lock = concurrency
        doomed_spans = _doomed_group_spans(case.path.name, steps)
        index = 0
        while index < len(steps):
            end = doomed_spans.get(index)
            if end is not None:
                with context.shadow.staged(doomed=True):
                    for grouped in range(index, end + 1):
                        lowered.append(
                            _lower_scenario_step(
                                context, steps[grouped], grouped, find_lock, group_observations
                            )
                        )
                index = end + 1
                continue
            step = steps[index]
            with context.shadow.staged(doomed=step.get("rollback") is True):
                lowered.append(
                    _lower_scenario_step(context, step, index, find_lock, group_observations)
                )
            index += 1
    except _LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    return lowered


def _write_sequence_lowered(
    case: case_format.Case, dialect_name: str
) -> list[tuple[str, tuple[LoweredStatement, ...]]]:
    """Lower each writeSequence entry independently to ``(pointer, statements)`` —
    pure. One :class:`TemporalShadow` spans the whole sequence:
    a later entry's temporal close/chain observes an earlier
    entry's own opened milestone(s), never the database. A writeSequence
    carries no find steps at all (`m-case-format`), so its own
    group observation store stays permanently empty — every keyed
    write's observation still comes from its row's own ``observedVersion``
    control key."""
    model = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    concurrency = _concurrency(case)
    shadow = TemporalShadow()
    # The same seeding the RUN lane applies: a case opting into `given.fixtures`
    # starts from persisted history, and its first temporal close observes a
    # fixture milestone rather than one an earlier entry opened. Both lanes must
    # start from the same tracked state or they are not the same computation.
    _seed_shadow_from_fixtures(case, model, shadow)
    group_observations: GroupObservations = []
    try:
        return [
            (
                f"/writeSequence/{index}",
                _lower_writes(
                    [entry],
                    model,
                    dialect,
                    concurrency,
                    shadow,
                    _entry_instant(entry),
                    group_observations,
                ),
            )
            for index, entry in enumerate(_write_sequence_entries(case))
        ]
    except _LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc


def _emissions(
    pointer_statements: Sequence[tuple[str, Sequence[LoweredStatement]]],
) -> list[Emission]:
    return [
        Emission(pointer, statement.sql, statement.binds)
        for pointer, statements in pointer_statements
        for statement in statements
    ]


def _has_action_step(steps: Sequence[Mapping[str, object]]) -> bool:
    """Whether a scenario carries at least one lifecycle **action** step
    (m-case-format "Lifecycle action steps") — the snapshot-read scenario shape
    (`mutate`) this module lowers/runs through a SEPARATE path from the keyed
    unit-of-work scenarios (`write` / `find` steps only), never mixed."""
    return any("action" in step for step in steps)


def _check_action_step(case: case_format.Case, step: Mapping[str, object]) -> None:
    """Refuse an action verb this lane does not grade (only `mutate` does; an
    `action: access` case — m-snapshot-read's closed-world absence witness — is
    dispatched to the api-conformance lane before reaching here at all, per the
    adapter's own lane guard)."""
    action = step.get("action")
    if action != "mutate":
        raise EngineError(
            f"{case.path.name}: scenario action {action!r} is graded by the API "
            "Conformance Suite (api-conformance lane), not compile/run"
        )


def _compile_snapshot_scenario(
    case: case_format.Case, dialect_name: str, steps: Sequence[Mapping[str, object]]
) -> tuple[list[Emission], int]:
    """Compile a snapshot-read scenario's own find steps (instance-form,
    unlocked — a snapshot materialization is not a locking object find);
    `mutate` contributes no emissions and no round trips at all (m-snapshot-
    read: an in-memory-only change, never SQL)."""
    model = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    emissions: list[Emission] = []
    try:
        for index, step in enumerate(steps):
            if "action" in step:
                _check_action_step(case, step)
                continue
            query = _step_query(step)
            metadata = case_entity(model, query.target.canonical)
            entity_query = _canonicalize_read(query, metadata, model)
            statement = compile_read(entity_query, model, dialect, result_form="instance").statement
            emissions.append(
                Emission(f"/scenario/{index}/objectQuery", statement.sql, statement.binds)
            )
    except _READ_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    return emissions, len(emissions)


@dataclass(frozen=True, slots=True)
class _ScenarioStepResult:
    """What one snapshot-scenario step left behind for a later step to name.

    The three facts are produced together and consumed together by
    :func:`_grade_mutate_step`, so they travel as one value rather than as
    index-aligned sequences a caller could fall out of step.

    ``roots`` is the in-memory member state of each root the step materialized,
    keyed by declared member name — the plain detached value a `mutate` assigns
    into (`m-snapshot-read` closed world). Its length is what a `mutate` step's
    single-node requirement is checked against. ``pin`` and ``identity`` are the
    coordinates the production finite-pin validator is handed. An action step
    materializes nothing and carries the empty result.
    """

    roots: tuple[dict[str, object], ...]
    pin: Pin | None
    identity: EntityIdentity | None


_NO_SCENARIO_RESULT: Final[_ScenarioStepResult] = _ScenarioStepResult((), None, None)


def _run_snapshot_scenario(
    case: case_format.Case,
    dialect_name: str,
    port: DbPort,
    steps: Sequence[Mapping[str, object]],
) -> tuple[list[Emission], int, list[dict[str, object]]]:
    """Run a snapshot-read scenario: each find step reads through the SAME
    public Wire read every graph read uses (``db.wire.find``); `mutate` runs the
    production write seam's
    finite-Transaction-Time-pin refusal against the referenced find step's own
    statement pin and, when that verdict accepts, assigns the step's `set` to the
    named view's own in-memory members (:func:`_grade_mutate_step`) — zero round
    trips, nothing at the port (m-snapshot-read closed world: a snapshot node is
    never enrolled in a unit of work, so mutating it can never write back).
    Returns the ordered emissions, the total round trips, and one `errors`
    observation entry per `expectError` step whose verb raised its declared
    application-lifecycle error (`m-conformance-adapter`)."""
    model = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    # This lane resolves no milestone from case state — every node it publishes
    # comes from a real read and it buffers no keyed write — so the tracker the
    # out-of-band statements mark is its own and is never consulted.
    _apply_given_apply(case, dialect, port, TemporalShadow())
    db = handle.Database(port, model, dialect=dialect)
    emissions: list[Emission] = []
    round_trips = 0
    results: list[_ScenarioStepResult] = []
    errors: list[dict[str, object]] = []
    for index, step in enumerate(steps):
        if "action" in step:
            error_class = _grade_mutate_step(case, step, results)
            if error_class is not None:
                errors.append({"at": f"/scenario/{index}", "errorClass": error_class})
            results.append(_NO_SCENARIO_RESULT)
            continue
        query = _step_query(step)
        try:
            # The case document's own spelling is resolved HERE, where the
            # document is read, so no later step carries a spelling into a
            # production seam that takes an Entity Identity.
            identity = case_entity(model, query.target.canonical).identity
            snapshot = db.wire.find(query)
            pin = _find_step_pin(model, query)
        except _READ_ERRORS as exc:
            raise EngineError(f"{case.path.name}: {exc}") from exc
        for call in snapshot.execution.calls:
            emissions.append(
                Emission(f"/scenario/{index}/objectQuery", call.statement.sql, call.statement.binds)
            )
        round_trips += snapshot.execution.round_trips
        results.append(_ScenarioStepResult(_root_members(snapshot), pin, identity))
    return emissions, round_trips, errors


def _root_members(
    snapshot: handle.Snapshot[handle.WireEntity],
) -> tuple[dict[str, object], ...]:
    """Each root the step materialized, as its own detached member state.

    Member NAME keyed, because that is the vocabulary a case's `set` is authored
    in — the Wire result's own keying — and the values are copied out so a later
    assignment reaches nothing the frozen result still publishes.
    """
    return tuple(dict(_graph_root(root) or {}) for root in snapshot.checked().results())


def _find_step_pin(model: AcceptedMetamodel, query: ObjectQueryNode) -> Pin:
    """A scenario read step's own query pin — the whole-graph as-of coordinates
    the materialized view carries (`m-snapshot-read`), read from the SAME
    Object Query the find executor consumes. This is the pin
    :func:`_grade_mutate_step` hands the production write seam's finite-pin
    rule, resolved through the family-declaring entity exactly as the read
    path resolves it."""
    return query_pin(query, _declaring_metadata(model, query.target.canonical))


def _grade_mutate_step(
    case: case_format.Case,
    step: Mapping[str, object],
    results: Sequence[_ScenarioStepResult],
) -> str | None:
    """Grade one scenario `mutate` action step through the SAME production
    validator the keyed developer verbs run
    (:func:`~parallax.snapshot.handle.validate_source_pin`): a mutation
    through a view pinned at a finite Transaction-Time instant raises the
    neutral `transaction-time-pin-read-only` error and assigns nothing, while a
    Latest or finite-Valid-Time pin is accepted and the `set` applies in memory
    (:func:`_apply_mutate_step`). Returns the raised error's `errorClass` when
    the step's own declared `expectError` matched it, else ``None`` for an
    accepted mutation; a mismatch in either direction — an undeclared refusal,
    or a declared expectation the verb never raised — is a loud
    :class:`EngineError`, never a silently dropped observation."""
    _check_action_step(case, step)
    on = step.get("on")
    source = results[on] if isinstance(on, int) and 0 <= on < len(results) else None
    identity = None if source is None else source.identity
    if not isinstance(on, int) or source is None or identity is None:
        raise EngineError(f"{case.path.name}: `mutate` names {on!r}, which is no earlier find step")
    expected = step.get("expectError")
    try:
        validate_source_pin(identity, source.pin)
    except TransactionTimePinReadOnlyError as exc:
        if expected != exc.code:
            declared = f"expectError {expected!r}" if expected is not None else "no expectError"
            raise EngineError(
                f"{case.path.name}: the `mutate` verb raised {exc.code!r} but the step "
                f"declares {declared}"
            ) from exc
        return exc.code
    if expected is not None:
        raise EngineError(
            f"{case.path.name}: the step declares expectError {expected!r} but the "
            "mutation was accepted"
        )
    _apply_mutate_step(case, step, on, source)
    return None


def _apply_mutate_step(
    case: case_format.Case,
    step: Mapping[str, object],
    on: int,
    source: _ScenarioStepResult,
) -> None:
    """Assign an ACCEPTED mutation's `set` to the named view's own members.

    `m-case-format` defines `mutate` as assigning the attributes in `set` in
    memory, so the assignment lands on the detached member state the source step
    materialized and reaches nothing else: the immutable neutral view production
    published is untouched, no unit of work holds the view, and no DML follows.
    A `set` naming a member the materialized view does not carry is refused
    here — an assignment with nowhere to land is a case the verb cannot perform,
    not a mutation it silently drops. The refusal is decided over the WHOLE
    `set` before any member is written, so a rejected mutation leaves the member
    state exactly as the find step materialized it: `set` is an unordered
    mapping, and applying its recognized names up to the first unrecognized one
    would make the surviving state depend on authoring order.
    """
    if len(source.roots) != 1:
        raise EngineError(
            f"{case.path.name}: `mutate` targets step {on}, which materialized "
            f"{len(source.roots)} nodes (expected exactly one to mutate)"
        )
    assignments = step.get("set")
    if not isinstance(assignments, Mapping):
        raise EngineError(f"{case.path.name}: a `mutate` action needs a `set` mapping")
    members = source.roots[0]
    member_assignments = cast("Mapping[str, object]", assignments)
    unassignable = sorted(name for name in member_assignments if name not in members)
    if unassignable:
        raise EngineError(
            f"{case.path.name}: `mutate` assigns {unassignable!r}, which the view step {on} "
            "materialized carries no member of"
        )
    members.update(member_assignments)


def compile_scenario_case(case: case_format.Case, dialect_name: str) -> tuple[list[Emission], int]:
    """Compile a scenario case to its ordered per-step emissions and round-trip count."""
    steps = _scenario_steps(case)
    if _has_action_step(steps):
        return _compile_snapshot_scenario(case, dialect_name, steps)
    emissions = _emissions(
        [(step.pointer, step.statements) for step in _scenario_lowered(case, dialect_name)]
    )
    return emissions, len(emissions)


def compile_write_sequence_case(
    case: case_format.Case, dialect_name: str
) -> tuple[list[Emission], int]:
    """Compile a writeSequence case to its ordered per-entry emissions and round trips."""
    emissions = _emissions(_write_sequence_lowered(case, dialect_name))
    return emissions, len(emissions)


def _seed_shadow_from_fixtures(
    case: case_format.Case, model: AcceptedMetamodel, shadow: TemporalShadow
) -> None:
    """Seed ``shadow`` from the case's OWN fixture-loading rule (`m-case-format`):
    a writeSequence starts EMPTY unless it opts in with ``given.fixtures: true``;
    every other shape (scenario, conflict) loads the model's default fixtures —
    mirrored from ``tests/_support/corpus.py``'s ``case_fixtures`` rule, kept independent
    (production/adapter code never imports the test suite)."""
    given = case.document.get("given")
    fixtures_flag = (
        isinstance(given, Mapping) and cast("Mapping[str, object]", given).get("fixtures") is True
    )
    if case.shape == "writeSequence" and not fixtures_flag:
        return
    fixtures = provision.load_fixtures(cast("str", case.document["model"]))
    for entity_name, rows in fixtures.items():
        shadow.seed_fixtures(
            model,
            case_entity(model, entity_name),
            cast("list[Mapping[str, object]]", rows),
        )


def _buffer_execution_instruction(
    tx: handle.Transaction,
    model: AcceptedMetamodel,
    write: _ResolvedWrite,
) -> None:
    """Buffer one resolved keyed write, and the evidence resolved for it, for
    REAL execution, its row decoded to native carriers first — the
    ONE entity-lookup/decode/buffer seam
    every real-execution write path (an ungrouped unit, a `uow` group, an
    interleaved group) shares.

    Every resolved instruction is SINGLE-row (:func:`_build_instructions`
    buffers one per case row, collapse-eligible or not, and a temporal entry
    carries exactly one), and this refuses a plural one rather than buffering
    its first row and dropping the rest — a decoded copy of a plural instruction
    would silently mix rows this engine resolved separately. It enters production
    through ``Transaction.write_neutral``, the one neutral runtime write ingress,
    exactly as that many separate developer calls would — never the typed
    instance verbs, which this engine's case-driven metamodel has no compiled
    Python classes for. A case-authored wire spelling (a decimal literal spelled
    as a float, `m-core-007`) is lowered to its native carrier HERE, once, since
    the neutral ingress takes an already-decoded instruction. Any batch collapse
    then happens where production does it, in the unit of work's own planner.

    The caller's own ``instruction`` argument is left untouched: a separate
    PURE re-lowering (`_lower_resolved`) grades a golden bind against that
    ORIGINAL authored instruction, never this decoded copy, so decoding here
    cannot drift a compile-time emission.
    """
    instruction = write.instruction
    assert isinstance(instruction, KeyedWrite)  # every resolved entry this lane buffers is keyed
    if len(instruction.rows) != 1:  # pragma: no cover - every producer builds a single-row write
        raise EngineError(
            f"{instruction.entity!r} {instruction.mutation!r}: a buffered write carries one row "
            f"({len(instruction.rows)} resolved) — the unit of work's own buffer seam takes one"
        )
    entity_metadata = case_entity(model, instruction.entity)
    tx.write_neutral(
        replace(instruction, rows=(decode_write_row(entity_metadata, instruction.rows[0], model),)),
        observation=write.execution_evidence,
    )


def _execute_write_unit(
    port: DbPort,
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    resolved: Sequence[_ResolvedWrite],
    tx_instant: str,
    *,
    rollback: bool,
) -> ExecutionLog | None:
    """Execute one choreography unit's ALREADY-RESOLVED instructions through the
    production ``db.transact`` entry point — ONE transaction,
    ``clock=FixedClock(tx_instant)``
    (ADR 0010: instants come from the Clock Strategy, never a per-operation
    override). Each instruction buffers through :func:`_buffer_execution_instruction`
    — already deserialized and `validate_instruction`-ed by
    :func:`_build_instructions`, and single-row, so the flush is free to merge
    any of them that carries no observation of its own. A
    ``rollback: true`` step runs on the aborting port (`m-unit-work` abort
    contract): the boundary's own finalization flush still puts the buffered DML
    on the wire — and counts its round trips — before the provider rolls the
    transaction back.
    """
    instant = normalize_instant(dt.datetime.fromisoformat(tx_instant))
    database = handle.Database(
        _write_port(port, rollback=rollback), model, dialect=dialect, clock=FixedClock(instant)
    )

    logs: list[ExecutionLog] = []

    def body(tx: handle.Transaction) -> None:
        logs.append(tx.execution_log)
        for write in resolved:
            _buffer_execution_instruction(tx, model, write)

    with contextlib.suppress(_RollbackStep):
        database.transact(body, concurrency=concurrency)
    return logs[-1] if logs else None


def _run_readless_predicate_write(
    port: DbPort,
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    raw_write: Mapping[str, object],
    tx_instant: str,
    *,
    rollback: bool,
) -> ExecutionLog | None:
    """Execute a READLESS scenario predicate-write step (`m-batch-write-005`/
    ``-006``) through the SAME production ``db.transact`` entry point every
    other write path uses — one transaction, buffering through
    ``Transaction.write_neutral`` (the one neutral runtime write ingress, which
    a predicate-selected instruction enters exactly as a keyed one does,
    `m-case-format` "predicate-shaped case entries ... buffer through
    Transaction's own seam, materialization then happens exactly where
    production does it").

    Decodes ``raw_write``'s own assignment values to native carriers
    (:func:`_decoded_predicate_write`) once, here — this instruction is never
    separately re-lowered for a golden-bind comparison (that reporting oracle
    is `_lower_predicate_write_step`'s OWN independent parse of the same raw
    document), so the SAME decoded instruction both validates and executes.
    """
    instruction = instructions.deserialize(_canonical_predicate_doc(raw_write))
    assert isinstance(instruction, PredicateWrite)
    decoded = _decoded_predicate_write(instruction, model)
    instructions.validate_instruction(decoded, model)
    instant = normalize_instant(dt.datetime.fromisoformat(tx_instant))
    database = handle.Database(
        _write_port(port, rollback=rollback), model, dialect=dialect, clock=FixedClock(instant)
    )
    logs: list[ExecutionLog] = []

    def body(tx: handle.Transaction) -> None:
        logs.append(tx.execution_log)
        tx.write_neutral(decoded)

    with contextlib.suppress(_RollbackStep):
        database.transact(body, concurrency=concurrency)
    return logs[-1] if logs else None


def _is_materializing_write_step(
    step: Mapping[str, object] | None, model: AcceptedMetamodel
) -> PredicateWrite | None:
    """If ``step`` is a write step whose ``write`` field is a structured
    predicate instruction targeting a VERSIONED or TEMPORAL entity
    (MATERIALIZES, `m-opt-lock` "Predicate-selected writes materialize when
    observations are needed", ADR 0014), its deserialized + validated
    :class:`~parallax.core.unit_work.PredicateWrite` — ``None`` for a keyed
    write step, a READLESS predicate write, a find step, or ``None`` itself
    (no such step, e.g. the scenario's last step).

    The returned instruction's own assignment values are DECODED to native
    carriers (:func:`_decoded_predicate_write`): a materializing write has no
    separate PURE re-lowering oracle (its own golden bind is graded against
    the ACTUAL executed SQL, `_run_materializing_pair`'s own Execution Log),
    so there is nothing for a decoded value to drift away from here.
    """
    if step is None or "write" not in step:
        return None
    raw_write = step["write"]
    if not isinstance(raw_write, Mapping):
        return None
    instruction = instructions.deserialize(
        _canonical_predicate_doc(cast("Mapping[str, object]", raw_write))
    )
    if not isinstance(instruction, PredicateWrite):
        return None
    decoded = _decoded_predicate_write(instruction, model)
    instructions.validate_instruction(decoded, model)
    if _is_temporal_entity(model, instruction.target.entity) or _is_versioned_entity(
        model, instruction.target.entity
    ):
        return decoded
    return None


def _run_materializing_pair(
    port: DbPort,
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    steps: Sequence[Mapping[str, object]],
    index: int,
    shadow: TemporalShadow,
) -> tuple[list[_LoweredStep], ExecutionLog | None]:
    """Execute a MATERIALIZING predicate-write step (``index + 1``) whose
    IMMEDIATELY PRECEDING step (``index``) is the resolving find that shares
    its target entity — ONE transaction, `m-case-format` "Materializing
    cases": "a preceding scenario read resolves the same target predicate ...
    It is a real resolving read, not a cache hit". Production materialization
    (``Transaction.write_neutral``) performs its OWN internal
    resolve using the SAME predicate; with no concurrent writer between the
    two steps, that resolve observes the IDENTICAL rows the corpus's own
    preceding find step documents, so pairing them here reproduces the
    corpus's own ``1 resolve + N per-row writes`` round-trip accounting
    exactly — the resolve's round trip is charged to the FIND step's pointer
    (the corpus's own authoring convention), never double-counted against the
    write step.

    Reports the ACTUAL executed SQL, read off this transaction's own Execution
    Log (`m-execution-log`), never a separate pure re-lowering: a materializing
    write's per-row binds are QUERY-RESULT-DEPENDENT, so there is no pure oracle
    to derive them from independently of a real run. The resolve is the attempt's
    own Read Trace (materialization always resolves before it writes) and the
    ``N`` per-row keyed writes are its Write Batch Traces, in resolved-row order
    — canonical Lowered Statements, the SAME form every other emission this
    engine reports carries, so no driver-SQL round trip stands between what ran
    and what is reported.

    What this transaction did to a TEMPORAL target's milestones is recorded on
    ``shadow`` rather than tracked into it: the rows it closed and opened were
    resolved and planned inside production, so no later step can settle against
    them from case state, and one that tries is refused
    (:func:`_refuse_materialized_case_state`). The record is staged on this
    transaction's own outcome, exactly as every other unit's advances are — an
    aborted pair moved nothing.
    """
    find_step = steps[index]
    write_step = steps[index + 1]
    instruction = _is_materializing_write_step(write_step, model)
    assert instruction is not None  # the caller already established this via the same check
    find = _step_query(find_step)
    target = find.target.canonical
    if target != instruction.target.entity:
        raise EngineError(
            f"materializing predicate write at scenario step {index + 1} is not preceded by "
            f"a resolving find over the SAME target entity (find targets {target!r}, write "
            f"targets {instruction.target.entity!r} — m-case-format 'Materializing cases' "
            "requires the prior find to share the write's own target)"
        )
    # `m-case-format` "Materializing cases": for every versioned or temporal
    # target, model-aware validation MUST require that prior find to use the same
    # concrete target AND canonical predicate — same entity alone is not enough
    # (a resolving find over a DIFFERENT predicate would silently observe the
    # wrong rows). The read's own Temporal Selection is a sibling clause and the
    # write target remains the bare predicate, so the two predicates compare
    # directly; `_canonicalize_read` would additionally inject interval
    # predicates and is therefore still not the apples-to-apples form.
    if find.predicate != instruction.target.predicate:
        raise EngineError(
            f"materializing predicate write at scenario step {index + 1} is not preceded by "
            "a resolving find over the SAME canonical predicate as the write's own target "
            f"predicate (find {find.predicate!r}, write {instruction.target.predicate!r} "
            "— m-case-format 'Materializing cases' requires the prior find to use the same "
            "concrete target and canonical predicate)"
        )
    tx_instant = _entry_instant(cast("Mapping[str, object]", write_step["write"]))
    instant = normalize_instant(dt.datetime.fromisoformat(tx_instant))
    rollback = write_step.get("rollback") is True
    database = handle.Database(
        _write_port(port, rollback=rollback),
        model,
        dialect=dialect,
        clock=FixedClock(instant),
    )
    logs: list[ExecutionLog] = []

    def body(tx: handle.Transaction) -> None:
        logs.append(tx.execution_log)
        tx.write_neutral(instruction)

    with shadow.staged(doomed=rollback):
        with contextlib.suppress(_RollbackStep):
            database.transact(body, concurrency=concurrency)
        shadow.note_materialized_write(case_entity(model, instruction.target.entity))
    log = logs[-1] if logs else None
    resolve, writes = _materialized_pair_statements(log)
    if not resolve:  # pragma: no cover - zero resolved rows still resolves (1 statement)
        raise EngineError(
            f"materializing predicate write at scenario step {index + 1} executed no "
            "statements at all — even a zero-row resolve issues its own SELECT"
        )
    return [
        _LoweredStep(f"/scenario/{index}/objectQuery", resolve, False, False),
        _LoweredStep(f"/scenario/{index + 1}/write", writes, True, rollback),
    ], log


def _materialized_pair_statements(
    log: ExecutionLog | None,
) -> tuple[tuple[LoweredStatement, ...], tuple[LoweredStatement, ...]]:
    """A materializing pair's executed statements, split the way the corpus
    charges them: the internal resolve's own Read Traces against the FIND step's
    pointer, and every Write Batch Trace call against the write step's.

    The split is the trace KIND rather than a position in one flat list, so a
    resolve that issued more than one call, or a batch the planner split, still
    lands where the corpus authors it.
    """
    if log is None:  # pragma: no cover - the body always runs and retains its log
        return (), ()
    reads: list[LoweredStatement] = []
    writes: list[LoweredStatement] = []
    for attempt in log.attempts:
        for trace in attempt.traces:
            target = reads if isinstance(trace, ReadTrace) else writes
            target.extend(call.statement for call in trace.calls)
    return tuple(reads), tuple(writes)


def _scenario_group_step_indices(steps: Sequence[Mapping[str, object]]) -> dict[str, list[int]]:
    """Every declared `uow` group label's OWN step indices, in authored order
    (`m-case-format` scenario `uow` grouping) — not necessarily contiguous;
    the caller (:func:`_scenario_uow_spans` / :func:`run_interleaved_scenario_case`)
    decides how to execute them."""
    groups: dict[str, list[int]] = {}
    for index, step in enumerate(steps):
        label = step.get("uow")
        if isinstance(label, str):
            groups.setdefault(label, []).append(index)
    return groups


def _scenario_uow_spans(
    case_name: str, steps: Sequence[Mapping[str, object]]
) -> dict[str, tuple[int, int]] | None:
    """Every declared `uow` group label's step-index span ``(start, end)``
    (inclusive) in this scenario (`m-case-format` scenario `uow` grouping).

    Every group whose OWN steps are CONTIGUOUS gets its ordinary span, and
    :func:`_run_uow_group` runs each on the MAIN connection. Exactly TWO
    groups whose steps INTERLEAVE (`m-case-format`'s own "two groups MAY
    interleave" — the classic optimistic-lock race, `m-opt-lock-012`'s own
    shape) is signaled by returning ``None``: :func:`run_scenario_case`
    cannot execute that shape itself (no engine function here constructs a
    connection of its own, and an interleaved race genuinely needs a SECOND,
    peer-backed session) — the caller routes to
    :func:`run_interleaved_scenario_case` instead. Anything BEYOND that one
    witnessed shape — three or more interleaved
    groups, or a non-contiguous group that is not part of a clean two-group
    interleave — raises loudly rather than silently mis-executing it (scope
    honestly: support what `m-opt-lock-012` needs, refuse the rest)."""
    groups = _scenario_group_step_indices(steps)
    spans = {label: (indices[0], indices[-1]) for label, indices in groups.items()}
    noncontiguous = {
        label
        for label, indices in groups.items()
        if indices != list(range(spans[label][0], spans[label][1] + 1))
    }
    if not noncontiguous:
        return spans
    if len(groups) == 2:
        (label_a, label_b) = groups
        span_a, span_b = spans[label_a], spans[label_b]
        interleaved = span_a[1] >= span_b[0] and span_b[1] >= span_a[0]
        if interleaved:
            return None
    raise EngineError(
        f"{case_name}: uow group(s) {sorted(noncontiguous)} interleave beyond the one "
        "witnessed two-group optimistic-lock race shape (m-opt-lock-012, "
        "run_interleaved_scenario_case) — the engine's scenario run lane supports "
        "exactly that interleaving, not an arbitrary one"
    )


def _group_tx_instant(steps: Sequence[Mapping[str, object]], start: int, end: int) -> str:
    """The Clock instant a `uow` group's own choreography unit runs at — its
    first write entry's own instant (m-txtime-write/m-bitemp-write `at`; ADR
    0010), or the inert default when the group carries no write (or every
    write entry names none, i.e. every group this round targets a
    non-temporal entity)."""
    for i in range(start, end + 1):
        step = steps[i]
        if "write" in step:
            entries = _write_entries(step["write"])
            if entries:
                return _entry_instant(entries[0])
    return _INERT_CLOCK_INSTANT


def _group_is_doomed(steps: Sequence[Mapping[str, object]], start: int, end: int) -> bool:
    """Whether a `uow` group ROLLS BACK after its last step: at least one of
    its OWN write steps declares `rollback: true` — the WHOLE group is then
    the doomed unit of work (`m-case-format` scenario `uow` grouping), not
    just that one step."""
    return any(
        "write" in steps[i] and steps[i].get("rollback") is True for i in range(start, end + 1)
    )


def _source_find_milestones(
    step: Mapping[str, object], index: int, group_finds: Mapping[int, ObservedNodes]
) -> ObservedNodes | None:
    """What the find step this WRITE step names with ``on`` observed
    (`m-case-format` *Settling against a grouped find*) — ``None`` when it names
    no source, which is every write step but one settling against its group's own
    read.

    ``group_finds`` holds one entry per find step of THIS group that has
    already run, so a reference it cannot satisfy names a step outside the group,
    a step that is not a find, or one that has not run yet. All three are the same
    authoring defect and all three are refused here, rather than resolved to an
    empty tuple that would read as "the find observed nothing".
    """
    source = step.get("on")
    if source is None:
        return None
    if not isinstance(source, int) or isinstance(source, bool):
        raise EngineError(
            f"scenario[{index}]: a write step settles against ONE find step, named by its "
            f"index — {source!r} is not one (m-case-format 'Settling against a grouped find')"
        )
    milestones = group_finds.get(source)
    if milestones is None:
        raise EngineError(
            f"scenario[{index}]: settles against step {source}, which is not an EARLIER find "
            "step of its own `uow` group — the evidence a write consumes is transaction-scoped "
            "(m-case-format 'Settling against a grouped find')"
        )
    return milestones


@dataclass(frozen=True, slots=True)
class _GroupContext:
    """What a scenario's translation is fixed by, for every one of its steps —
    the run lane's `uow` groups (:func:`_run_group_step`) and the compile lane's
    pure lowering (:func:`_lower_scenario_step`) alike.

    The model is the case's own accepted Metamodel
    (:func:`load_case_metamodel`), and the tracker is the ONE case-spanning
    :class:`TemporalShadow` every group shares rather than a per-group copy — a
    later group's temporal close observes the milestone an earlier group's write
    opened. The record is frozen because none of the four is ever REBOUND
    mid-scenario; the tracker's own contents advance, which is exactly the state
    a shared tracker exists to carry.
    """

    model: AcceptedMetamodel
    dialect: Dialect
    concurrency: Concurrency
    shadow: TemporalShadow


def _empty_group_observations() -> GroupObservations:
    return []


def _empty_group_finds() -> dict[int, ObservedNodes]:
    return {}


@dataclass(frozen=True, slots=True)
class _GroupState:
    """What ONE `uow` group accumulates as its own steps run, and nothing wider.

    Both halves are the same evidence read two ways: ``observations`` is the flat
    run every write of the group settles against by object identity, and
    ``finds`` keys the same nodes by the step that observed them, which is what a
    write step naming a find with ``on`` addresses (`m-case-format` *Settling
    against a grouped find*). They are built fresh per group — never a
    scenario-wide store — so evidence never crosses a transaction boundary.
    """

    observations: GroupObservations = field(default_factory=_empty_group_observations)
    finds: dict[int, ObservedNodes] = field(default_factory=_empty_group_finds)


def _run_group_step(
    tx: handle.Transaction,
    context: _GroupContext,
    state: _GroupState,
    step: Mapping[str, object],
    index: int,
    tx_instant: str,
) -> tuple[_LoweredStep, handle.Snapshot[handle.WireEntity] | None]:
    """One `uow` group step, inside the group's own open transaction — the ONE
    interpreter both group runners share, contiguous span and interleaved index
    list alike.

    A WRITE step resolves its entries against this group's own observations
    (never a scenario-wide store), records the SEPARATE pure re-lowering every
    other write path uses (:func:`_lower_resolved`) BEFORE the group's flush
    executes anything, and buffers each resolved write through
    ``tx.write_neutral`` carrying the evidence production itself issued. A FIND
    step runs through ``tx.observed_read`` — the participating Wire read, which
    force-flushes any pending buffered write, takes the transaction's own read
    lock, records what a later write settles against, and brackets its own Read
    Trace, exactly as a real ``Transaction.find`` does — and publishes the records
    that recording filed into both halves of ``state``, which this function
    extends in place.

    Returns the step's lowered emission pointer, and a find step's own read
    output beside it: what a caller does with the rows it returned — grade them,
    ignore them — is the caller's affair, and is the only thing the two runners
    still do differently.
    """
    model = context.model
    if "write" in step:
        entries = _write_entries(step["write"])
        source = _source_find_milestones(step, index, state.finds)
        resolved = _resolve_entries(entries, model, context.shadow, state.observations, source)
        statements = _lower_resolved(
            resolved,
            entries,
            model,
            context.dialect,
            context.concurrency,
            tx_instant,
            context.shadow,
        )
        for write in resolved:
            _buffer_execution_instruction(tx, model, write)
        return (
            _LoweredStep(
                f"/scenario/{index}/write", statements, True, step.get("rollback") is True
            ),
            None,
        )
    read = tx.observed_read(_step_query(step))
    state.finds[index] = read.observations
    state.observations.extend(read.observations)
    return _LoweredStep(
        f"/scenario/{index}/objectQuery", _trace_statements(read.snapshot), False, False
    ), read.snapshot


def _run_uow_group(
    port: DbPort,
    context: _GroupContext,
    steps: Sequence[Mapping[str, object]],
    start: int,
    end: int,
) -> tuple[list[_LoweredStep], ExecutionLog | None]:
    """Execute one CONTIGUOUS `uow` group's steps (index *start*..*end*
    inclusive) inside ONE ``db.transact``, in step order, each through the shared
    :func:`_run_group_step` interpreter.

    What this runner owns beyond that interpreter is the group's own BOUNDARY:
    the single Transaction Instant every step in the span runs at
    (:func:`_group_tx_instant`), and the doom decision — `rollback: true` on any
    of the group's own write steps dooms the WHOLE group, which then runs on the
    aborting port, so the boundary's finalization flush still puts the buffered
    DML on the wire before the provider rolls it back (the `m-unit-work` abort
    contract applied to the group rather than to one step). The group's case-state
    advances are staged on that same outcome
    (:meth:`~parallax.conformance.temporal_state.TemporalShadow.staged`): visible
    to the group's own later steps, discarded with the rows when it aborts.

    Its own find rows are graded elsewhere, so the read output each find step
    answers is discarded here.
    """
    tx_instant = _group_tx_instant(steps, start, end)
    doomed = _group_is_doomed(steps, start, end)
    state = _GroupState()
    instant = normalize_instant(dt.datetime.fromisoformat(tx_instant))
    database = handle.Database(
        _write_port(port, rollback=doomed),
        context.model,
        dialect=context.dialect,
        clock=FixedClock(instant),
    )
    lowered: list[_LoweredStep] = []
    logs: list[ExecutionLog] = []

    def body(tx: handle.Transaction) -> None:
        logs.append(tx.execution_log)
        for index in range(start, end + 1):
            step, _output = _run_group_step(tx, context, state, steps[index], index, tx_instant)
            lowered.append(step)

    with context.shadow.staged(doomed=doomed), contextlib.suppress(_RollbackStep):
        database.transact(body, concurrency=context.concurrency)
    # The group's own Execution Log — the production record of what this ONE
    # transaction did, which is where the `execution` observation and this
    # group's round trips come from rather than from a second count this lane
    # keeps.
    return lowered, logs[-1] if logs else None


# --------------------------------------------------------------------------- #
# Interleaved `uow` groups — the two-group optimistic-lock race                #
# (`m-opt-lock-012`). `_run_uow_group` above runs                              #
# ONE contiguous group on the main connection; a genuinely interleaved case    #
# needs TWO groups held open CONCURRENTLY over TWO real sessions (the          #
# `Provisioner.peer` seam) — a DIFFERENT consumer of that seam than the        #
# `when.concurrency` rounds runner (`parallax.conformance.concurrency_runner`, #
# real `db.transact` calls, production routing, not verbatim                   #
# authored statements). :class:`_Turnstile` sequences the two groups' own      #
# steps in AUTHORED order across two worker threads — deterministic (never a   #
# genuine race at the Python level) because optimistic mode's own reads take   #
# no lock and the choreography hands off control explicitly at each step, so   #
# there is nothing to race.                                                    #
# --------------------------------------------------------------------------- #
@runtime_checkable
class _PeerConnection(DbPort, Protocol):
    """A `DbPort` peer connection (`Provisioner.peer`) with its own closeable
    lifecycle: the interleaved-group runner opens a SECOND, independent
    session for the `concurrent` group and MUST close it itself once the
    choreography finishes (successfully or not) — this module constructs no
    connection itself otherwise, so the CALLER threads the factory in
    explicitly (`run_interleaved_scenario_case`'s own `peer_factory`
    parameter)."""

    def close(self) -> None: ...


class _Turnstile:
    """A strict, shared step-index cursor two worker threads take turns
    through: a thread's own step at index ``i``
    calls :meth:`wait_for` ``(i)`` before running it (blocking until every
    EARLIER step, on EITHER thread, has finished) and :meth:`advance` after —
    so the two groups' steps interleave in EXACTLY authored order, never a
    genuine Python-level race, matching `m-case-format`'s own "steps execute
    in authored order" scenario contract even though they run on two
    independently-held connections.
    """

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._next = 0

    def wait_for(self, index: int) -> None:
        with self._condition:
            while self._next < index:
                self._condition.wait()

    def advance(self) -> None:
        with self._condition:
            self._next += 1
            self._condition.notify_all()

    def release_all(self) -> None:
        """Unstick every waiter unconditionally (a worker thread's own
        UNEXPECTED failure — never a witnessed path, defensive only): without
        this a partner thread blocked on a LATER index than one extra
        :meth:`advance` reaches would hang forever, and so would the
        orchestrator's own `thread.join()`."""
        with self._condition:
            self._next = 2**31
            self._condition.notify_all()


def _empty_group_rows() -> dict[int, list[Mapping[str, object]]]:
    return {}


@dataclass(slots=True)
class _InterleavedGroupResult:
    """One interleaved group's own report: its lowered steps (keyed by
    scenario step index), the conflict's own `actual` affected-row count
    when its LAST write step doomed the group via a genuine optimistic-lock
    conflict (`None` for a group that committed, or that never conflicts),
    any OTHER exception the worker thread raised (re-raised on the main
    thread once both join — never silently swallowed), and every OWN find
    step's own observed rows (keyed by scenario step index) — the group's own
    oracle for `expectRows`, the
    SAME grade the ordinary scenario run lane (`test_write_run_sweep`'s
    `_ReadCapturePort`) already gives every OTHER find step; without this the
    caller has no way to grade a grouped find at all, only its DML shape."""

    lowered: dict[int, _LoweredStep]
    conflict_actual: int | None = None
    failure: BaseException | None = None
    rows: dict[int, list[Mapping[str, object]]] = field(default_factory=_empty_group_rows)
    round_trips: int = 0


def _run_interleaved_group(
    database: handle.Database,
    context: _GroupContext,
    steps: Sequence[Mapping[str, object]],
    indices: Sequence[int],
    turnstile: _Turnstile,
    result: _InterleavedGroupResult,
) -> None:
    """Run one interleaved group's OWN steps (``indices``, in authored order,
    possibly non-contiguous across the WHOLE scenario) inside ONE real
    ``db.transact`` call on ``database`` — the SAME :func:`_run_group_step`
    interpreter :func:`_run_uow_group` drives over a contiguous span,
    generalized to an explicit index list and gated by ``turnstile`` at every
    step. A write step's lowering is therefore recorded BEFORE the group's own
    flush executes it, so a step that later CONFLICTS still reports its own
    well-formed golden DML (`m-opt-lock` "Conflict detection" — the SQL is
    correct, the row count is not).

    The group's own boundary flushes what its last step buffered, and that
    flush may itself raise
    :class:`~parallax.core.unit_work.OptimisticLockConflictError` (the SAME
    signal a caller-driven retry catches, `_run_conflict_write`'s own
    precedent) — caught HERE, its ``actual`` recorded, and the transaction
    aborts (never retried: `m-opt-lock-012`'s own `when.uow` sets no
    ``retryOptimisticConflicts`` opt-in, so :func:`~parallax.core.auto_retry.
    run_with_retry` surfaces it after exactly one attempt). Unlike
    :func:`_run_uow_group`'s own OWN ``doomed``/``rollback: true`` convention
    (an authored, EXPLICIT abort signal independent of any real conflict),
    this lane's ONE witness (`m-opt-lock-012`) authors ``rollback: true``
    ONLY on the step whose OWN flush already conflicts — the CONFLICT itself
    is what dooms the group, so no separate explicit-rollback trigger exists
    here; a genuinely non-conflict-driven interleaved abort is unwitnessed
    and out of scope (pinned semantics #10, "unwitnessed surfaces stay
    honest"). The turnstile only ADVANCES past the group's own last step once
    ``database.transact`` itself RETURNS (a REAL commit — the underlying
    port's transaction context manager has committed, not merely that this
    callback's own Python code finished): the OTHER group's next step must
    observe that commit for real, never a same-process illusion of one.

    ``context`` carries the SAME single :class:`TemporalShadow` every group
    shares (`_run_uow_group`'s own convention) — safe here ONLY because
    `m-opt-lock-012`'s own witnessed model is entirely NON-temporal (the
    tracker is never mutated for these instructions, so two threads never
    contend on it, and this group's own abort has nothing to discard). A
    genuinely temporal interleaved case would need its own per-group tracking
    discipline — the contiguous runner's whole-tracker staging cannot serve two
    groups advancing at once — unwitnessed and out of scope.

    Every OWN find step's observed rows land in ``result.rows`` (keyed by
    scenario step index): the caller's own
    oracle for that step's authored ``expectRows`` — without this, a grouped
    find's own DML is graded but its OBSERVATION never is, so a broken abort
    that left a doomed group's writes durable would report well-formed SQL
    and still pass. Keeping them is the one thing this runner does with a step's
    result that the contiguous runner does not.
    """
    lowered: dict[int, _LoweredStep] = {}
    state = _GroupState()
    logs: list[ExecutionLog] = []

    def body(tx: handle.Transaction) -> None:
        logs.append(tx.execution_log)
        for position, index in enumerate(indices):
            turnstile.wait_for(index)
            is_last = position == len(indices) - 1
            lowered[index], output = _run_group_step(
                tx, context, state, steps[index], index, _INERT_CLOCK_INSTANT
            )
            if output is not None:
                result.rows[index] = _graph_rows(
                    context.model, _step_query(steps[index]).target.canonical, output
                )
            if not is_last:
                turnstile.advance()

    committed = False
    try:
        database.transact(body, concurrency=context.concurrency)
        committed = True
    except OptimisticLockConflictError as exc:
        result.conflict_actual = exc.actual
    except BaseException as exc:  # re-raised on the main thread below
        result.failure = exc
        turnstile.release_all()  # never leave a partner thread hanging on this thread's own defect
    result.lowered = lowered
    result.round_trips = logs[-1].round_trips if logs else 0
    if committed:
        turnstile.advance()


# The interleaved-group choreography's own bounded join (the provider-
# contract deadlock proof's own precedent): a genuine harness defect (a
# missing `advance()` somewhere) must surface as a loud failure, never an
# indefinitely hung test session. Named so :func:`_await_interleaved_workers`
# can be exercised directly with a SHRUNK bound — a real, unstuck-by-
# `release_all` timeout path in well under a second, rather than the
# production bound actually elapsing twice.
_INTERLEAVED_GROUP_JOIN_TIMEOUT: Final[float] = 30.0


def _underlying_connection(connection: object) -> object | None:
    """The termination ladder's rung-two/rung-three shared reach target
    (:func:`_terminate_connection`): the duck-typed underlying transport
    (mirroring :attr:`~parallax.postgres.PostgresAdapter.connection`, the
    wrapped psycopg ``Connection``), or ``None`` when ``connection`` exposes
    no such escalation seam at all. Used only by
    :func:`_terminate_connection`'s own rungs two and three; preflight
    (:func:`_require_interleaved_termination_capability`) does not inspect a
    connection's shape at all."""
    return getattr(connection, "connection", None)


# ---------------------------------------------------------------------------
# The termination ladder's trust marker. A structural check — whether
# `close()` / `fileno()` are CALLABLE — cannot prove termination is
# RELIABLE: a port whose cancellation, close, underlying close, and socket
# teardown are all CALLABLE yet all RAISE at runtime would pass such a check
# (`preflight=('validated',)`) and then hang the unbounded post-ladder join
# forever (`helper_completed=False`). Runtime reliability of an arbitrary
# duck-typed object this module does not itself construct is not provable by
# inspection, so preflight REQUIRES an explicit, truthful GRANT of trust
# rather than inferring a guarantee from shape.
# ---------------------------------------------------------------------------
_TERMINATION_LADDER_TRUST_ATTR: Final[str] = "termination_ladder_trusted"
"""The trust marker's attribute name (a named boolean rather than a separate
ABC/Protocol, kept a plain duck-typed attribute so a test fake needs no
extra base class to declare
it). A connection type this module does not itself construct DECLARES the
deterministic-termination contract by setting this attribute truthy on
itself — a class attribute (inherited by every instance) is the natural
place, but an instance attribute counts identically — asserting EXACTLY
that the termination ladder's own escalation
(:func:`_terminate_connection` — outer ``close()``, then the underlying
``connection``'s own ``close()``, then real OS-level socket teardown)
deterministically unblocks whatever this connection's own I/O is doing.
Declaring the marker IS taking responsibility for it: a truthful
declaration means :func:`_await_interleaved_workers`'s own unbounded
post-ladder join can never hang past this connection; an UNTRUTHFUL
declaration is a bug in the DECLARING type, diagnosable at that exact join
line, never a defect this preflight could have caught — this module's own
contract is discharged the moment a truthful declaration exists, never by
attempting to verify one is true (a shape cannot be trusted to imply the
declaration this module needs)."""


def _validate_termination_trust(connection: object, label: str) -> list[str]:
    """The pre-start refusal check enforcing the DECLARED termination-trust
    contract: ``connection``
    passes ONLY when it grants that trust explicitly, by exactly one of —

    1. Being the KNOWN-DETERMINISTIC real type,
       :class:`~parallax.postgres.PostgresAdapter` — the concrete shape
       ``provision.py``'s own ``Provisioner.port`` AND ``Provisioner.peer()``
       both construct (the SAME class serves the caller's own connection
       and its peer alike). Trusted BY CONSTRUCTION, never inferred: its
       own ``close()`` tears down the wrapped psycopg connection, whose own
       ``close()`` tears down the underlying OS-level socket fd — an OS
       guarantee, not a hope, that any driver call blocked on that fd's I/O
       unblocks.
    2. Carrying a truthy :data:`_TERMINATION_LADDER_TRUST_ATTR` attribute —
       this module's own documented marker (see its own module-level
       docstring for exactly what declaring it promises) — by which the
       declarer takes on the SAME responsibility the real adapter carries
       by construction.

    A CALLABLE ``close()`` / ``fileno()`` — even a whole structurally
    plausible ladder of them — is NEVER sufficient on its own: a port with
    every rung callable
    and every rung RAISING at runtime is refused WITHOUT
    CALLING any of them (a pure trust check, never a behavioral probe —
    nothing here is invoked, only inspected).

    Returns every defect found (empty when ``connection`` validates) rather
    than raising itself — the caller
    (:func:`_require_interleaved_termination_capability`) combines BOTH
    connections' own defects into one loud refusal rather than stopping at
    the first one."""
    from parallax.postgres import PostgresAdapter  # local: keep the unit lane psycopg-import-light

    if isinstance(connection, PostgresAdapter):
        return []
    if getattr(connection, _TERMINATION_LADDER_TRUST_ATTR, False) is True:
        return []
    return [
        f"{label} declares no trusted termination contract — it is neither the "
        "known-deterministic PostgresAdapter shape (whose close() tears down an "
        "OS-level socket fd, an OS-level guarantee) nor does it carry a truthy "
        f"`{_TERMINATION_LADDER_TRUST_ATTR}` attribute, the documented marker "
        "promising that the termination ladder deterministically unblocks its "
        "own I/O; a callable close()/fileno() alone is never sufficient"
    ]


def _require_interleaved_termination_capability(
    main_connection: DbPort, peer_connection: _PeerConnection, case_name: str
) -> None:
    """The termination-trust preflight entry point. A merely structural check
    — that a connection's ``close()`` / ``fileno()`` are CALLABLE — is
    insufficient: a port that passes it yet whose every runtime rung RAISES
    would leave :func:`_await_interleaved_workers`'s own deliberately
    UNBOUNDED post-ladder join hanging indefinitely with no live process
    able to unstick it. So the check is TRUST, not STRUCTURE: BEFORE either
    interleaved-group worker thread
    starts, BOTH ``main_connection`` (the caller-owned port) and
    ``peer_connection`` must carry a DECLARED deterministic-termination
    contract (:func:`_validate_termination_trust`) — refusing loudly, naming
    EVERY defective connection at once (main, peer, or both; never
    first-failure-only) rather than letting a defect surface only much
    later as that indefinite hang.

    Called from :func:`run_interleaved_scenario_case` before either worker
    thread is even constructed: a refusal here leaves nothing running and
    nothing to clean up on ``main_connection`` — the caller's own port is
    inspected only, never called, exactly as untouched as if this function
    had never run at all. (The caller is responsible for ``peer_connection``,
    which it opened via its own ``peer_factory``; this function neither
    closes it nor assumes anything about it beyond the same trust check
    ``main_connection`` gets.)"""
    defects = _validate_termination_trust(
        main_connection, "main connection"
    ) + _validate_termination_trust(peer_connection, "peer connection")
    if not defects:
        return
    raise EngineError(
        f"{case_name}: the interleaved-group choreography refuses to start — {'; '.join(defects)}"
    )


def _cancel_in_flight_work(connection: object) -> None:
    """Best-effort, non-destructive interruption of whatever ``connection``
    is blocked on right now (:func:`_await_interleaved_workers`'s second
    escalation):
    a worker parked in REAL driver I/O wakes for neither
    :meth:`_Turnstile.release_all` (it is not inside ``turnstile.wait_for``)
    nor closing some OTHER session, so its OWN connection's outstanding
    operation must be cancelled directly. The concrete adapter
    (:class:`~parallax.postgres.PostgresAdapter`) is a legal
    ``parallax-conformance`` dependency (`pyproject.toml`), so a real
    Postgres connection is cancelled through psycopg's thread-safe,
    connection-preserving ``Connection.cancel_safe`` — callable from a
    thread other than the one running the blocked query, and unlike
    ``close()`` it does not itself destroy the connection: THIS rung never
    tears a session down, whether it is the peer's or the caller's own
    ``ours`` session. A survivor this rung cannot reach (cancellation fails
    or is unavailable) escalates one rung further, to
    :func:`_terminate_connection` — the GUARANTEED close ladder,
    never best-effort like this rung — which DOES close it; cancellation
    staying non-destructive only means a session that wakes here is never
    needlessly destroyed, not that it can never be destroyed at all. A fake
    port (unit lane) legally carries no psycopg connection; it instead
    exposes its OWN duck-typed ``cancel()`` capability, probed for and
    invoked when present. Neither path is a guarantee — a cancellation
    request can itself fail or time out, and a fake's ``cancel()`` is
    whatever its test author wired — so this is deliberately best-effort;
    the caller rejoins bounded afterward and reports an honest terminal
    state either way."""
    from parallax.postgres import PostgresAdapter

    # The concrete-adapter path needs a real psycopg `Connection`, which the
    # unit lane (no container/socket I/O) never constructs; exercised only
    # informally by the Docker-backed conformance lanes, none of which
    # witness a genuine join timeout (`m-opt-lock-012` itself always
    # resolves within the bound).
    if isinstance(connection, PostgresAdapter):  # pragma: no cover
        with contextlib.suppress(Exception):
            connection.connection.cancel_safe()
        return
    cancel = getattr(connection, "cancel", None)
    if callable(cancel):
        with contextlib.suppress(Exception):
            cancel()


def _terminate_underlying_socket(  # pragma: no cover - real transport only, Docker-lane exercised
    underlying: object, label: str
) -> list[str]:
    """The termination ladder's LAST rung (:func:`_terminate_connection`'s
    own final escalation, reached only once BOTH ``underlying``'s own
    ``close()`` is missing or has already raised): genuine OS-level socket
    teardown on ``underlying``'s raw connection fd (``underlying.fileno()``
    — psycopg's own documented seam for exactly this, normally used for
    ``selectors``-based readiness waiting, reused here as the escalation's
    own reach into the transport). ``shutdown(SHUT_RDWR)`` is the
    thread-safe way to force a DIFFERENT thread's blocking
    read/write/recv syscall on that SAME fd to return with an OS-level
    error — the standard "unstick a blocked peer" trick, safe to call
    concurrently with a blocking call on the same fd (unlike a bare
    ``close()`` of that fd from another thread, which POSIX leaves
    unsafe/undefined while a syscall on it is in flight elsewhere). The fd
    is unconditionally closed afterward regardless of whether
    ``shutdown()`` itself succeeded (``finally``): this connection is
    already condemned by the time this rung runs, so closing it too is
    never a new loss, and a ``shutdown()`` failure alone (e.g. the socket
    was already disconnected) must never leave the fd itself still open.
    Unreachable from any test fake — no fake in this module's unit lane
    carries a real OS fd — so this rung is exercised only informally by the
    Docker-backed conformance lanes, the SAME reasoning
    :func:`_cancel_in_flight_work`'s own ``PostgresAdapter``-only
    ``cancel_safe`` rung already carries."""
    failures: list[str] = []
    fileno = getattr(underlying, "fileno", None)
    if not callable(fileno):
        failures.append(f"{label}: underlying connection exposes no fileno() for OS-level teardown")
        return failures
    try:
        fd = cast("int", fileno())
    except Exception as exc:
        failures.append(f"{label}: underlying connection.fileno() raised {exc!r}")
        return failures
    try:
        sock = socket.socket(fileno=fd)
    except Exception as exc:  # a misbehaving fileno() must never crash this rung
        failures.append(f"{label}: OS-level socket(fileno={fd}) raised {exc!r}")
        with contextlib.suppress(Exception):
            os.close(fd)
        return failures
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except Exception as exc:
        failures.append(f"{label}: OS-level shutdown(fd={fd}) raised {exc!r}")
    finally:
        with contextlib.suppress(Exception):
            sock.close()
    return failures


def _terminate_connection(connection: object, label: str) -> list[str]:
    """Escalation rung three (:func:`_await_interleaved_workers`'s FINAL
    escalation): unlike :func:`_cancel_in_flight_work`
    (best-effort, non-destructive), this rung is GUARANTEED, never
    best-effort. A single, silently-swallowed ``close()``
    probe would assume closing always works; if BOTH ``cancel()`` and
    ``close()`` fail on the SAME survivor, a
    live worker keeps racing the caller after this rung has already run and
    :func:`_await_interleaved_workers` has already raised — which this
    ladder exists to prevent.

    This ladder, each rung attempted only once the one above it is
    missing or itself raises (never silently — every miss and every raise is
    RECORDED and returned, so the caller can attach the full trail to the
    timeout error as context rather than masking it):

    1. ``connection``'s own duck-typed ``close()`` (``main_connection`` is
       typed as the abstract ``DbPort``, with no ``close()`` in that
       protocol — mirroring :func:`_cancel_in_flight_work`'s own
       ``cancel()`` probe, this duck-types rather than assumes the
       capability; :class:`_PeerConnection`, `PostgresAdapter`, and every
       termination-rung test fake all expose one).
    2. The UNDERLYING transport, reached the SAME duck-typed way — a
       ``connection`` attribute (:attr:`~parallax.postgres.PostgresAdapter.
       connection`, the wrapped psycopg ``Connection``), closed directly.
       Unlike :func:`_cancel_in_flight_work`'s own ``cancel_safe`` rung,
       this is NOT ``isinstance``-gated to the concrete adapter: ``close()``
       is a universal enough capability name that a test fake can
       legitimately expose the SAME seam a real adapter does, so this rung
       reaches both alike. This is the documented seam a termination-rung
       test fake must expose once its own OUTER ``close()`` is made to fail.
    3. :func:`_terminate_underlying_socket` — genuine OS-level socket
       teardown on the underlying connection's raw fd, real-transport only.

    The guarantee this ladder exists to satisfy: for every connection type
    actually wired into this path today (the real ``PostgresAdapter``,
    escalating through rungs 1-3; a test fake, via whichever rung its own
    documented seam answers), the ladder's last successful rung
    deterministically unblocks a worker parked in that connection's I/O. A
    fake whose documented seam the ladder genuinely cannot reach is a
    defect in that fake, not in this function — it hangs the suite, which
    is this module's own documented contract for an unreachable fake, not a
    bug this rung papers over.

    Rungs 1 and 2 reach the underlying transport through
    :func:`_underlying_connection`. The preflight gate above this ladder does
    not infer a guarantee by inspecting these rung shapes; it requires a
    caller-visible, DECLARED trust contract instead
    (:func:`_require_interleaved_termination_capability`,
    :data:`_TERMINATION_LADDER_TRUST_ATTR`). :func:`_underlying_connection`
    is simply this ladder's own single-sourced reach for rungs two and
    three."""
    failures: list[str] = []

    def _attempt(target: object, rung: str) -> bool:
        close = getattr(target, "close", None)
        if not callable(close):
            failures.append(f"{label}: {rung} exposes no close() capability")
            return False
        try:
            close()
        except Exception as exc:  # escalate; recorded, never masks the timeout error below
            failures.append(f"{label}: {rung}.close() raised {exc!r}")
            return False
        return True

    if _attempt(connection, "connection"):
        return failures

    underlying = _underlying_connection(connection)
    if underlying is None:
        failures.append(f"{label}: connection exposes no underlying `connection` escalation seam")
        return failures
    if _attempt(underlying, "underlying connection"):
        return failures

    failures.extend(  # pragma: no cover - real transport only; Docker-lane exercised
        _terminate_underlying_socket(underlying, label)
    )
    return failures


def _await_interleaved_workers(
    thread_a: threading.Thread,
    thread_b: threading.Thread,
    turnstile: _Turnstile,
    main_connection: DbPort,
    peer_connection: _PeerConnection,
    case_name: str,
    *,
    timeout: float = _INTERLEAVED_GROUP_JOIN_TIMEOUT,
) -> None:
    """Join both interleaved-group worker threads within ``timeout``; on a
    timeout, cooperatively UNSTICK them before raising rather than raising
    while they may still be alive: wake every
    waiter parked in ``turnstile.wait_for`` (:meth:`_Turnstile.release_all` —
    the SAME defensive unstick a worker's own unexpected failure already
    uses), close ``peer_connection`` so any outstanding database work the
    peer-side worker still holds terminates, THEN rejoin both threads (bounded
    again, never a second indefinite hang).

    That first escalation cannot reach a worker blocked in REAL database I/O
    on its OWN session: ``release_all`` only wakes a thread parked in
    ``turnstile.wait_for``, and closing ``peer_connection`` touches only the
    ``concurrent`` group's session, never ``main_connection``. So any thread
    STILL alive after that rejoin gets a SECOND escalation:
    :func:`_cancel_in_flight_work` — best-effort, non-destructive, and
    ALLOWED to stay that way, because the
    guarantee below lives entirely in the rung after it — on its OWN
    connection (``main_connection`` for ``thread_a``, ``peer_connection``
    for ``thread_b``), then one more bounded rejoin of both.

    FINAL CONTRACT: this function has NO code path — return, raise, or assert
    — that runs while any started worker is alive. A bounded rejoin behind an
    assumed-guaranteed ``close()`` is not enough: if BOTH ``cancel()`` and
    ``close()`` fail on the same survivor, a live worker remains at the very
    point this function would otherwise
    raise. So any thread STILL alive after the cancel rejoin gets a THIRD
    escalation that is no longer best-effort: :func:`_terminate_connection`'s
    own GUARANTEED close ladder (duck-typed ``close()`` -> the underlying
    driver connection -> OS-level socket teardown for the real adapter
    shape; a documented underlying seam for a test fake — see that
    function) on its OWN connection, INCLUDING ``main_connection`` (the
    caller's own port) when its worker is the survivor — superseding the
    earlier "never close the caller-owned port" invariant, since a live
    worker still racing the caller on that port is strictly worse than a
    terminated port that fails loudly on next use.

    The join AFTER this rung is DELIBERATELY UNBOUNDED (``thread.join()``,
    no ``timeout=``): there is no second, narrower timeout to violate. The trade,
    made explicit: against a hypothetical FUTURE connection whose own close
    ladder is defeated all the way down (a rung this module cannot reach,
    or one that itself blocks), the failure mode is a diagnosable hang at
    THIS join — a stuck process a maintainer can inspect and attribute to
    this exact line — never a live worker racing the caller on a port the
    caller already believes is theirs. Every connection type actually wired
    into this path today (the real ``PostgresAdapter``; every
    termination-rung test fake, via its documented seam) satisfies the
    ladder's guarantee, so in practice this join returns promptly; the
    unbounded wait is insurance against a violation of that guarantee, not
    evidence one is expected. Worker exceptions the termination itself
    provokes (a close-induced driver error inside the worker) are expected
    collateral, captured on the worker's own ``_InterleavedGroupResult.
    failure`` and never consulted once this function has already raised —
    the caller only reaches that check on the ordinary, non-timeout path, so
    the timeout error below is always what a caller here actually sees.

    This unbounded join is safe only because
    :func:`run_interleaved_scenario_case` calls
    :func:`_require_interleaved_termination_capability` on BOTH
    ``main_connection`` and ``peer_connection`` before either worker thread
    even starts. A merely structural check — that a connection's ``close()``
    / ``fileno()`` are CALLABLE — is insufficient: a port with every one of
    those callable yet every one RAISING at runtime would pass it and hang
    this SAME join anyway (``preflight=('validated',)``,
    ``helper_completed=False``). So the check is TRUST, not STRUCTURE — a
    connection passes only by carrying a DECLARED deterministic-termination
    contract (:func:`_validate_termination_trust`: the known-deterministic
    ``PostgresAdapter`` shape, trusted by construction, or an explicit
    :data:`_TERMINATION_LADDER_TRUST_ATTR` marker declaring the SAME
    responsibility). Past that validation, a hang at the join below can only
    mean a connection's trust grant was UNTRUTHFUL — a lying declaration (or
    a `PostgresAdapter` whose own OS-level guarantee was somehow defeated):
    a contract violation by that connection type, diagnosable at this exact
    line, never an ordinary or expected outcome. The declaration makes the
    requirement explicit and caller-visible instead of leaving it implicit
    in an unbounded join a maintainer would otherwise have to
    reverse-engineer.

    The terminal state is always honest, never a silent leak: because the
    join above cannot return while a worker remains alive, EVERY path past
    it raises the SAME timeout error this function has always raised,
    naming whether ``main_connection`` (the caller's own port) was itself
    terminated (closed) — the caller's next use must treat it as unsafe to
    reuse either way — and now also carrying every close-ladder failure the
    termination rung recorded (a missing capability, a raised ``close()``,
    …) as `~BaseException.add_note` context: recorded, never silently
    suppressed, never masking this error. The caller's own ``finally`` still
    closes ``peer_connection`` unconditionally (idempotent,
    `parallax.postgres.PostgresAdapter.close`), so a double close here is
    harmless."""
    thread_a.join(timeout=timeout)
    thread_b.join(timeout=timeout)
    if not thread_a.is_alive() and not thread_b.is_alive():
        return

    turnstile.release_all()
    peer_connection.close()
    thread_a.join(timeout=timeout)
    thread_b.join(timeout=timeout)

    workers = ((thread_a, main_connection), (thread_b, peer_connection))
    survivors = [(thread, connection) for thread, connection in workers if thread.is_alive()]
    if survivors:
        for _thread, connection in survivors:
            _cancel_in_flight_work(connection)
        thread_a.join(timeout=timeout)
        thread_b.join(timeout=timeout)

    survivors = [(thread, connection) for thread, connection in workers if thread.is_alive()]
    terminated_caller_port = False
    termination_failures: list[str] = []
    for thread, connection in survivors:
        if connection is main_connection:
            terminated_caller_port = True
        termination_failures.extend(_terminate_connection(connection, thread.name))

    # UNBOUNDED — see docstring: a diagnosable hang here beats ever raising
    # (or returning) while a worker is still alive, so there is no separate,
    # narrower termination-join bound to violate.
    thread_a.join()
    thread_b.join()

    if terminated_caller_port:
        error = EngineError(
            f"{case_name}: the interleaved-group choreography did not "
            "finish within its bound — the caller-owned port was "
            "terminated (closed) to unstick it and must be treated as "
            "unsafe to reuse"
        )
    else:
        error = EngineError(
            f"{case_name}: the interleaved-group choreography did not "
            "finish within its bound — a turnstile hand-off is missing"
        )
    for failure in termination_failures:
        error.add_note(f"termination ladder: {failure}")
    raise error


def run_interleaved_scenario_case(
    case: case_format.Case,
    dialect_name: str,
    port: DbPort,
    peer_factory: Callable[[], _PeerConnection],
) -> tuple[list[Emission], int, int | None, list[list[Mapping[str, object]]]]:
    """Run the ONE witnessed interleaved-`uow`-group scenario shape
    (`m-opt-lock-012`'s two-group optimistic-lock race): the ``ours`` group
    on the caller's own ``port``, a
    ``concurrent`` group on a SECOND, peer-backed connection (``peer_factory``
    — this function constructs no connection itself), each a REAL
    ``db.transact`` (production routing), steps sequenced across
    the two in AUTHORED order (:class:`_Turnstile`). Any ungrouped step
    (`m-opt-lock-012`'s own trailing verify find) runs AFTER both groups have
    resolved, on the caller's ``port``.

    Reports the ordered emissions, total round trips, and — when a group's
    own last write step conflicted — the conflict's ``actual`` affected-row
    count (`then.affectedRows`, the scenario shape's own EXTRA top-level
    assertion this ONE case authors; ``None`` when no group conflicted), and
    EVERY find step's own observed rows (grouped or ungrouped, in scenario
    step order): the caller's own oracle for
    every authored `expectRows`, the SAME observable the ordinary scenario
    run lane grades for every OTHER find step. Routed to explicitly by the
    run sweep (`test_run_sweep.py`) rather than through `run_scenario_case`/
    `adapter.run_case` — this shape's own peer requirement has no seat in the
    ordinary shape-dispatched entry points, the SAME reasoning the rounds
    runner's own dispatch follows.

    Before either worker thread starts, both ``port`` and the connection
    ``peer_factory`` produces must carry a TRUSTED deterministic-termination
    contract (:func:`_require_interleaved_termination_capability`) — a
    connection with no declared trust
    refuses loudly here, rather than surfacing only much later as an
    indefinite hang at :func:`_await_interleaved_workers`'s own unbounded
    post-ladder join.
    """
    steps = _scenario_steps(case)
    model = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    concurrency = _concurrency(case)
    groups = _scenario_group_step_indices(steps)
    if len(groups) != 2:
        raise EngineError(  # pragma: no cover - defensive: only m-opt-lock-012 reaches this entry
            f"{case.path.name}: run_interleaved_scenario_case supports exactly the "
            "two-group optimistic-lock race shape (m-opt-lock-012), not "
            f"{len(groups)} uow groups"
        )
    ungrouped = [i for i in range(len(steps)) if i not in {j for js in groups.values() for j in js}]
    (label_a, indices_a), (label_b, indices_b) = groups.items()
    shadow = TemporalShadow()
    _seed_shadow_from_fixtures(case, model, shadow)
    _apply_given_apply(case, dialect, port, shadow)
    instant = normalize_instant(dt.datetime.fromisoformat(_INERT_CLOCK_INSTANT))
    main_db = handle.Database(port, model, dialect=dialect, clock=FixedClock(instant))
    peer_connection = peer_factory()
    try:
        _require_interleaved_termination_capability(port, peer_connection, case.path.name)
    except BaseException:
        # Refusing here means neither worker thread ever started, so there is
        # nothing to unstick — only the peer connection this function itself
        # opened via `peer_factory` to release. Best-effort and swallowed
        # (never let a broken `close()` on an already-refused connection mask
        # the loud refusal above): a connection that failed validation may
        # have no working `close()` at all, by definition.
        with contextlib.suppress(Exception):
            peer_connection.close()
        raise
    peer_db = handle.Database(peer_connection, model, dialect=dialect, clock=FixedClock(instant))
    turnstile = _Turnstile()
    result_a = _InterleavedGroupResult(lowered={})
    result_b = _InterleavedGroupResult(lowered={})
    context = _GroupContext(model, dialect, concurrency, shadow)
    thread_a = threading.Thread(
        target=_run_interleaved_group,
        args=(main_db, context, steps, indices_a, turnstile, result_a),
        name=f"uow-{label_a}",
    )
    thread_b = threading.Thread(
        target=_run_interleaved_group,
        args=(peer_db, context, steps, indices_b, turnstile, result_b),
        name=f"uow-{label_b}",
    )
    try:
        thread_a.start()
        thread_b.start()
        _await_interleaved_workers(
            thread_a, thread_b, turnstile, port, peer_connection, case.path.name
        )
    finally:
        peer_connection.close()
    for result in (result_a, result_b):
        if result.failure is not None:
            raise result.failure

    lowered: dict[int, _LoweredStep] = {**result_a.lowered, **result_b.lowered}
    rows_by_index: dict[int, list[Mapping[str, object]]] = {**result_a.rows, **result_b.rows}
    # Each group's own transaction counted its own calls; the trailing ungrouped
    # verify finds add theirs below.
    round_trips = sum(result.round_trips for result in (result_a, result_b))
    for index in ungrouped:
        step = steps[index]
        if "write" in step:  # pragma: no cover - no witnessed ungrouped write is doomed-adjacent
            raise EngineError(
                f"{case.path.name}: an ungrouped write step ({index}) beside an "
                "interleaved uow race is unsupported — m-opt-lock-012's own ungrouped "
                "step is a trailing verify find only"
            )
        read = _run_standalone_find(port, model, dialect, concurrency, step)
        rows_by_index[index] = _graph_rows(model, _step_query(step).target.canonical, read)
        round_trips += read.execution.round_trips
        lowered[index] = _LoweredStep(
            f"/scenario/{index}/objectQuery", _trace_statements(read), False, False
        )

    ordered = [lowered[index] for index in sorted(lowered)]
    emissions = _emissions([(step.pointer, step.statements) for step in ordered])
    conflict_actual = result_a.conflict_actual
    if conflict_actual is None:
        conflict_actual = result_b.conflict_actual
    find_rows = [rows_by_index[index] for index in sorted(rows_by_index)]
    return emissions, round_trips, conflict_actual, find_rows


def run_scenario_case(
    case: case_format.Case, dialect_name: str, port: DbPort
) -> tuple[list[Emission], int, list[dict[str, object]], ExecutionLog | None]:
    """Run a scenario: an UNGROUPED write step commits (or aborts) as its OWN
    unit of work through ``db.transact``, and an ungrouped find reads
    committed state. A `uow`-GROUPED contiguous span of steps instead runs
    inside ONE ``db.transact`` (:func:`_run_uow_group`): the observing find
    and the versioned write it licenses execute in the SAME unit of work, so
    the write's version bind is a genuine transaction-scoped observation,
    never an oracle. A MATERIALIZING predicate-write step pairs with its
    IMMEDIATELY PRECEDING find step (:func:`_run_materializing_pair`) —
    detected by a one-step LOOK-AHEAD before that find is lowered as an
    ordinary standalone step, since `m-case-format`'s own "Materializing
    cases" convention makes the preceding find the resolve. Reports the
    ordered emissions, the total round trips, and the `errors` observation
    entries (`m-conformance-adapter`) — populated only by the snapshot
    action-step lane's `expectError` grading (:func:`_run_snapshot_scenario`);
    every keyed unit-of-work scenario reports an empty list.

    The fourth element is the scenario's execution provenance
    (`m-execution-log`): the Execution Log of its ONE `uow` group, or ``None``
    when the scenario ran no group or more than one — a scenario that opened
    several transactions has no single log to report, and the observation
    describes one invocation by contract."""
    steps = _scenario_steps(case)
    if _has_action_step(steps):
        emissions, round_trips, errors = _run_snapshot_scenario(case, dialect_name, port, steps)
        return emissions, round_trips, errors, None
    model = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    concurrency = _concurrency(case)
    find_lock = concurrency
    shadow = TemporalShadow()
    spans = _scenario_uow_spans(case.path.name, steps)
    if spans is None:
        raise EngineError(
            f"{case.path.name}: interleaved uow groups (the two-group optimistic-lock "
            "race shape, m-opt-lock-012) need a second, peer-backed connection this "
            "function does not construct — call run_interleaved_scenario_case instead"
        )
    span_start_labels = {start: label for label, (start, _end) in spans.items()}
    context = _GroupContext(model, dialect, concurrency, shadow)
    lowered: list[_LoweredStep] = []
    group_logs: list[ExecutionLog | None] = []
    round_trips = 0
    try:
        _seed_shadow_from_fixtures(case, model, shadow)
        # After the fixtures and before the first step, exactly where every other
        # lane applies it (:func:`_apply_given_apply`). The tracker is deliberately
        # not re-seeded from it — it records which milestones the statements may
        # have overtaken instead. A predicate write resolves through a real read that
        # sees whatever they wrote; a keyed write's observation stays case state,
        # and where that state can no longer be the whole stored row the write is
        # refused rather than silently rebuilt
        # (:func:`_refuse_unaccounted_document_milestone`).
        _apply_given_apply(case, dialect, port, shadow)
        index = 0
        while index < len(steps):
            label = span_start_labels.get(index)
            if label is not None:
                start, end = spans[label]
                group_lowered, group_log = _run_uow_group(port, context, steps, start, end)
                lowered.extend(group_lowered)
                group_logs.append(group_log)
                round_trips += group_log.round_trips if group_log is not None else 0
                index = end + 1
                continue
            step = steps[index]
            if "write" not in step:
                next_step = steps[index + 1] if index + 1 < len(steps) else None
                pairing = _is_materializing_write_step(next_step, model)
                if (
                    pairing is not None
                    and _step_query(step).target.canonical == pairing.target.entity
                ):
                    pair_lowered, pair_log = _run_materializing_pair(
                        port, model, dialect, concurrency, steps, index, shadow
                    )
                    lowered.extend(pair_lowered)
                    round_trips += pair_log.round_trips if pair_log is not None else 0
                    index += 2
                    continue
                read = _run_standalone_find(port, model, dialect, find_lock, step)
                round_trips += read.execution.round_trips
                lowered.append(
                    _LoweredStep(
                        f"/scenario/{index}/objectQuery", _trace_statements(read), False, False
                    )
                )
                index += 1
                continue
            raw_write = step["write"]
            rollback = step.get("rollback") is True
            if _is_predicate_write_step(raw_write):
                # A materializing write reaching HERE (rather than being
                # consumed by the look-ahead pairing above) was not preceded
                # by a matching find — a malformed corpus case per
                # `m-case-format`'s own validation requirement; finalization's
                # defensive refusal surfaces it loudly rather than silently
                # mishandling it. A READLESS write needs no pairing at all.
                raw_predicate_write = cast("Mapping[str, object]", raw_write)
                tx_instant = _entry_instant(raw_predicate_write)
                statement = _lower_predicate_write_step(
                    raw_predicate_write, model, dialect, concurrency
                )
                write_log = _run_readless_predicate_write(
                    port,
                    model,
                    dialect,
                    concurrency,
                    raw_predicate_write,
                    tx_instant,
                    rollback=rollback,
                )
                round_trips += write_log.round_trips if write_log is not None else 0
                lowered.append(
                    _LoweredStep(f"/scenario/{index}/write", (statement,), True, rollback)
                )
            else:
                entries = _write_entries(raw_write)
                tx_instant = _entry_instant(entries[0])
                with shadow.staged(doomed=rollback):
                    resolved = _resolve_entries(entries, model, shadow, [])
                    statements = _lower_resolved(
                        resolved, entries, model, dialect, concurrency, tx_instant, shadow
                    )
                    write_log = _execute_write_unit(
                        port, model, dialect, concurrency, resolved, tx_instant, rollback=rollback
                    )
                round_trips += write_log.round_trips if write_log is not None else 0
                lowered.append(_LoweredStep(f"/scenario/{index}/write", statements, True, rollback))
            index += 1
    except _LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    emissions = _emissions([(step.pointer, step.statements) for step in lowered])
    log = group_logs[0] if len(group_logs) == 1 else None
    return emissions, round_trips, [], log


def run_write_sequence_case(
    case: case_format.Case, dialect_name: str, port: DbPort
) -> tuple[list[Emission], dict[str, list[Row]], int]:
    """Run a writeSequence: each entry executes as its OWN unit of work through
    ``db.transact`` (one transaction per entry, never the whole sequence in
    one), then report the ordered per-entry
    emissions, the committed table state, and the total round trips.

    The table read-back is the `m-conformance-adapter` write-sequence observation
    ("write-sequence cases report ``tableState``"): the runner grades it against
    the case's ``then.tableState``. Observation reads are not case round trips.

    ``given.apply`` is applied after the case's own fixture provisioning and
    before the first entry (`m-case-format` admits it on a writeSequence): the
    state it stands for — a row a concurrent writer removed, a stored document
    key no authored member of this model can produce — is state the FIRST entry
    already writes against, so applying it later than that would grade the
    sequence against a table the case never described.
    """
    model = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    concurrency = _concurrency(case)
    shadow = TemporalShadow()
    group_observations: GroupObservations = []
    lowered: list[tuple[str, tuple[LoweredStatement, ...]]] = []
    round_trips = 0
    try:
        _seed_shadow_from_fixtures(case, model, shadow)
        _apply_given_apply(case, dialect, port, shadow)
        for index, entry in enumerate(_write_sequence_entries(case)):
            tx_instant = _entry_instant(entry)
            resolved = _resolve_entries([entry], model, shadow, group_observations)
            statements = _lower_resolved(
                resolved, [entry], model, dialect, concurrency, tx_instant, shadow
            )
            log = _execute_write_unit(
                port, model, dialect, concurrency, resolved, tx_instant, rollback=False
            )
            round_trips += log.round_trips if log is not None else 0
            lowered.append((f"/writeSequence/{index}", statements))
    except _LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    emissions = _emissions(lowered)
    table_state = read_table_state(port, model, dialect)
    return emissions, table_state, round_trips


def read_table_state(
    port: DbPort, model: AcceptedMetamodel, dialect: Dialect
) -> dict[str, list[Row]]:
    """The committed contents of every model table, in canonical wire form.

    Every compiled Table Layout is read back exactly once, projecting its
    complete slot sequence in canonical order, so the observation reports the
    whole physical row ``then.tableState`` asserts — including a slot that only
    a sibling table-per-hierarchy variant fills (e.g. `m-inheritance-007`'s
    inserted `CardPayment` row still reports the cash-only `tendered` column as
    `null`).
    """
    state: dict[str, list[Row]] = {}
    for layout in storage_layout.view(model).tables:
        columns = ", ".join(dialect.quote(slot.column.name) for slot in layout.columns)
        sql = f"select {columns} from {dialect.quote(layout.table.name)}"
        rows = port.execute(dialect.to_driver_sql(sql), [])
        state[layout.table.name] = [wire_row(row) for row in rows]
    return state


# --------------------------------------------------------------------------- #
# Conflict — the write-effect run lane (m-opt-lock / m-unit-work).             #
# Single-attempt (`when.write`) and retry                                      #
# (`when.attempts`) forms both drive ONE `db.transact` call per attempt.       #
# A non-temporal attempt (a keyed UPDATE or DELETE over one row or the         #
# multi-key array) buffers through the neutral `Transaction.write_neutral`     #
# exactly like any other keyed write; a TEMPORAL attempt (`m-txtime-write` /   #
# `m-bitemp-write`) composes `handle.plan_temporal_close` directly — a         #
# conflict case tests ONLY the close, under an address and a gate the case     #
# names EXPLICITLY rather than derives from an observation.                    #
# --------------------------------------------------------------------------- #
def _apply_given_apply(
    case: case_format.Case, dialect: Dialect, port: DbPort, shadow: TemporalShadow
) -> None:
    """Apply a case's out-of-band ``given.apply`` naive statements VERBATIM,
    immediately (never inside our own transaction), and tell ``shadow`` they ran.

    They stand for a writer this unit of work is not: a CONCURRENT transaction
    that already committed, so its effect must survive our own eventual rollback
    (a stale-version conflict), or a newer application version that stored state
    no authored member of this model could produce (a Structured Column key the
    model declares nowhere).

    Marking the tracker here rather than at each lane is what makes the mark
    unforgettable: every executor of a shape ``given.apply`` is admitted on —
    conflict, writeSequence, and each of the three scenario executors — runs the
    statements through this one function, so no lane can leave a tracker claiming
    a whole account of a row one of them may since have overtaken."""
    given = case.document.get("given")
    if not isinstance(given, Mapping):
        return
    entries = cast("Mapping[str, object]", given).get("apply")
    if not isinstance(entries, list):
        return
    shadow.note_out_of_band_write()
    for entry in cast("list[Mapping[str, object]]", entries):
        sql = cast("str", entry["sql"])
        binds = cast("list[object]", entry.get("binds", []))
        port.execute_write(dialect.to_driver_sql(sql), _driver_binds(binds))


def _default_family_root(model: AcceptedMetamodel) -> EntityMetadata | None:
    """The family root the default-target conventions resolve through.

    ``None`` when the model declares no inheritance family at all, so a caller
    falls back to the model document's own first entity
    (:func:`_first_declared_entity`). A model declaring SEVERAL families
    has no single root to name, and picking one of them would silently target an
    entity the case never asked for, so it is refused: the conventions below all
    say "the family root", singular, and a case over such a model must name its
    target explicitly.

    A family is read off the Inheritance Facet: every participant's view carries
    the root's own strategy, and a standalone Entity carries none, so the
    strategy-bearing views' distinct roots ARE the model's families.
    """
    facet = inheritance.view(model)
    roots = {
        entity.identity: view.root
        for entity in model.entities
        if (view := facet.entity(entity.identity)) is not None and view.strategy is not None
    }
    distinct = set(roots.values())
    if not distinct:
        return None
    if len(distinct) > 1:
        raise EngineError(
            "the case's model declares no single inheritance family root; a case whose "
            "`when` names no explicit target has no default to resolve against a model "
            "carrying several families"
        )
    root = model.entity(next(iter(distinct)))
    if root is None:  # pragma: no cover - a family root is an accepted Entity
        raise EngineError("the case's model names a family root it does not declare")
    return root


def _first_declared_entity(case: case_format.Case) -> str:
    """The canonical spelling of the Entity a case's model document declares
    FIRST.

    `m-case-format` fixes the default target of a case naming none as the
    family root, "else — when it declares no family at all — its own first
    entity". That is the DOCUMENT's order: the accepted model enumerates its
    Entities canonically, so the authored order survives nowhere else. Of the
    cases that reach this convention, one resolves to a different Entity under
    each reading — ``m-predicate-048`` over ``shared-local-name`` — and it is
    refused by the same rule either way, so no case grades the difference.

    The ORDER is the document's; the SPELLING is canonical
    (:func:`~parallax.conformance.models.declared_entity_spellings`), because a
    convention resolving a target the case never named must land on the Entity
    it selected rather than re-enter the bare-name rule that adjudicates an
    AUTHORED reference.
    """
    spellings = models.declared_entity_spellings(models.read_document(_case_model_path(case)))
    if not spellings:  # pragma: no cover - a formed model declares at least one entity
        raise EngineError(f"{case.path.name}: the case's model declares no entity")
    return spellings[0]


def _conflict_target(case: case_format.Case, model: AcceptedMetamodel) -> str:
    """The entity a conflict case's write targets, when ``when.write`` carries no
    explicit reference (`m-case-format`: a conflict case's write names no
    entity of its own). For a plain model this is its SOLE entity — the same
    convention :func:`_rejected_target` uses. For an inheritance family
    (`m-inheritance-105`'s TPH composed conflict) writes are concrete-subtype
    only (`m-inheritance` "Concrete-subtype writes"), never the abstract root
    :func:`_rejected_target` resolves to for the REJECTED lane's DIFFERENT
    default-target convention — this resolves to the family's SOLE concrete
    subtype (every reachable temporal-inheritance conflict model declares
    exactly one).

    Reported by CANONICAL spelling, like every default this lane resolves: the
    subtype is selected by Identity here, so reducing it to a bare local name
    would hand a resolved selection back to the ambiguity rule that adjudicates
    an authored reference."""
    root = _default_family_root(model)
    if root is None:
        return _first_declared_entity(case)
    view = inheritance.view(model).entity(root.identity)
    concretes = sorted(
        identity.canonical for identity in (() if view is None else view.concrete_subtypes)
    )
    if len(concretes) != 1:
        raise EngineError(  # pragma: no cover - no witnessed conflict model is ambiguous
            f"a conflict case's model declares {len(concretes)} concrete subtypes "
            f"{concretes!r}; the target is ambiguous without an explicit reference"
        )
    return concretes[0]


def _conflict_mutation(when: Mapping[str, object]) -> Literal["update", "delete"]:
    """A NON-TEMPORAL conflict case's written verb (`m-case-format`
    ``when.mutation``), defaulting to ``update``. A temporal target ignores it:
    its conflict write is always the milestone close."""
    return "delete" if when.get("mutation") == "delete" else "update"


@dataclass(frozen=True, slots=True)
class _ConflictWrite:
    """One row of a NON-TEMPORAL conflict attempt's ``write``, resolved once for
    both the pure re-lowering and the real execution: the durable row, the
    single-row instruction a unit of work buffers for it, that instruction's
    coalescing identity, and the Version Observation the row's reserved
    ``observedVersion`` described."""

    row: dict[str, object]
    instruction: WriteInstruction
    key: ObjectKey | None
    observation: VersionObservation | None

    @property
    def resolved(self) -> _ResolvedWrite:
        """This row as the buffer item both write consumers take. Its Version
        Observation is evidence the case authored and this lane holds directly,
        so the real write and the pure oracle settle against the same value and
        no Observation Key stands between them."""
        return _ResolvedWrite(self.instruction, self.observation, self.observation)


def _resolve_conflict_writes(
    model: AcceptedMetamodel,
    target: str,
    mutation: Literal["update", "delete"],
    write_rows: Sequence[Mapping[str, object]],
) -> tuple[_ConflictWrite, ...]:
    """Resolve a NON-TEMPORAL conflict attempt's ``write`` rows: strip each row's
    reserved ``observedVersion`` into a Version Observation (`m-opt-lock`;
    ADR 0013) and validate the durable instruction it leaves. ``mutation`` is the
    case's own ``when.mutation`` verb — a keyed UPDATE or DELETE, the two
    non-temporal shapes whose gate the concurrency mode decides uniformly; a
    temporal close's own conflict form (`handle.plan_temporal_close`) is a
    distinct shape.

    A conflict attempt authors its rows in the SAME ``writeRow`` vocabulary a
    writeSequence entry does, so they become durable rows through the SAME
    :func:`_durable_row` seam: an unversioned conflict target — a supported
    surface (``m-unit-work-013`` / ``-014``, ``m-batch-write-008``) — has no
    version to observe, and wrapping its rows anyway would exclude them from the
    collapse this lane exists to exercise.

    Every row becomes its OWN single-row instruction, exactly as a unit of work
    buffers it. Which of them end up sharing a statement is the planner's
    decision alone, so the MULTI-KEY ``write`` array reaches the collapse rule
    rather than a pre-merged instruction this function invented.
    """
    resolved: list[_ConflictWrite] = []
    for clean_row, observation in _durable_rows(model, target, mutation, write_rows):
        instruction = instructions.deserialize(
            {"mutation": mutation, "entity": target, "rows": [clean_row]}
        )
        instructions.validate_instruction(instruction, model)
        resolved.append(
            _ConflictWrite(clean_row, instruction, object_key(instruction, model), observation)
        )
    return tuple(resolved)


def _landed_conflict_rows(resolved: Sequence[_ConflictWrite]) -> int:
    """The aggregate row count a conflict attempt affects when its write LANDS:
    one per DISTINCT addressed key, since same-key rows coalesce into a single
    addressed row before any target is built. A row whose identity does not
    resolve coalesces with nothing and stands for itself."""
    keyed = {write.key for write in resolved if write.key is not None}
    return len(keyed) + sum(1 for write in resolved if write.key is None)


def _lower_conflict_write(
    model: AcceptedMetamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    resolved: Sequence[_ConflictWrite],
) -> tuple[LoweredStatement, ...]:
    """PURE-lower one NON-TEMPORAL conflict attempt's resolved ``write`` rows:
    plan the whole buffer through the SAME ``build_write_planner`` factory the
    composition layer uses (`parallax.snapshot.handle.Database.transact`) and
    lower every survivor, so a MULTI-KEY attempt reports the ONE set-based
    statement its real execution emits rather than the per-row statements an
    uncollapsed plan would have rendered.
    """
    instant = _pinned_instant(_INERT_CLOCK_INSTANT)
    plan = build_write_planner(model).plan(
        PlanningRequest(
            subject_identity=_PLANNING_SUBJECT,
            transaction_instant=instant,
            concurrency=concurrency,
            buffered_writes=[_buffered(write.instruction, write.observation) for write in resolved],
        )
    )
    return tuple(statement for _step, statement in stream_lowered(plan, model, dialect))


def _implied_shortfall_error(
    observation_requiring: bool,
    concurrency: Concurrency,
    model: AcceptedMetamodel,
    target: str,
) -> type[WriteEffectError]:
    """The ONE shortfall class a conflict case's declared facts imply.

    Derived from the case, never from the plan the implementation settled, so a
    write whose policy was settled wrongly cannot also move the expectation it is
    graded against. An OBSERVATION-REQUIRING write — a versioned keyed UPDATE or
    DELETE, or a temporal close — classifies by its gate, which the target's own
    Effective Concurrency Strategy decides: a GATED (Optimistic) shortfall is the
    retriable optimistic-lock conflict, an UNGATED (Locking) one the
    non-retriable stale write. Anything else is an observation-free keyed write,
    whose shortfall means the addressed rows are simply not there.
    """
    if not observation_requiring:
        return MissingTargetError
    strategy = opt_lock.effective_strategy(
        concurrency, opt_lock.view(model).key(case_entity(model, target).identity)
    )
    return OptimisticLockConflictError if strategy == "optimistic" else StaleWriteError


def _conflict_attempt_affected(
    database: handle.Database,
    concurrency: Concurrency,
    implied: type[WriteEffectError],
    body: Callable[[handle.Transaction], int],
) -> tuple[int, ExecutionLog | None]:
    """One conflict attempt's affected-row observation: what ``body`` reports when
    the write lands, or the ``actual`` count carried by the ONE Write Effect Error
    the case's own declared facts admit.

    Both conflict lanes — the non-temporal keyed write and the temporal close —
    make this exact guard, so it lives here once rather than beside each ``body``.
    Every member of the family renders the same ``actual`` count, so a lane that
    caught the whole family would report an identical ``affectedRows`` observation
    whichever class the write raised, and the case would then assert nothing about
    the classification. Admitting only the implied class lets every other one
    propagate and fail the case instead.

    An EXCESS is invariant: whatever a shortfall would have classified as, more
    rows than the target addresses is always Cardinality Corruption, so the
    direction the raised error itself reports — not the declared mode — selects
    that arm.
    """
    logs: list[ExecutionLog] = []

    def observed(tx: handle.Transaction) -> int:
        # Retained before the body runs: a shortfall aborts the transaction, so
        # the result never arrives and the live log the Transaction carries is
        # the only way to read what the failed attempt did (`m-execution-log`).
        logs.append(tx.execution_log)
        return body(tx)

    log = None
    try:
        result = database.transact(observed, concurrency=concurrency)
    except WriteEffectError as exc:
        admitted = CardinalityCorruptionError if exc.actual > exc.expected else implied
        if type(exc) is not admitted:
            raise
        if logs:
            log = logs[-1]
        return exc.actual, log
    return result.value, result.execution_log


def _admitted_affected(implied: type[WriteEffectError], run: Callable[[], int]) -> int:
    """``run``'s own affected-row count, or the ``actual`` the ONE admitted Write
    Effect Error carries — :func:`_conflict_attempt_affected`'s guard, for the
    close lane, which opens no ``db.transact`` to read a log from."""
    try:
        return run()
    except WriteEffectError as exc:
        admitted = CardinalityCorruptionError if exc.actual > exc.expected else implied
        if type(exc) is not admitted:
            raise
        return exc.actual


def _run_conflict_write(
    port: DbPort,
    dialect: Dialect,
    model: AcceptedMetamodel,
    target: str,
    concurrency: Concurrency,
    write_rows: Sequence[Mapping[str, object]],
    mutation: Literal["update", "delete"],
) -> tuple[tuple[LoweredStatement, ...], int, ExecutionLog | None, int]:
    """Lower and execute one NON-TEMPORAL conflict attempt's write through
    ``db.transact`` — ONE
    transaction, an inert Clock (never consumed by a non-temporal write).
    Buffers EVERY row through the neutral ``Transaction.write_neutral`` ingress, each
    carrying the observation its own row authored, so a MULTI-KEY attempt
    reaches the flush the same way
    a unit of work's own buffered writes do and the batching rule — not this
    function — decides how many statements they become; the PRODUCTION flush
    executor's OWN affected-row enforcer raises on a violation, and this lane
    admits only the class the case's own declared facts imply
    (:func:`_implied_shortfall_error`), rendering it as the ``affectedRows``
    observation the case asserts. A failure classified any other way — an ungated
    locking-mode versioned DELETE surfacing as an optimistic conflict, or an
    unversioned keyed UPDATE against a missing row surfacing as anything but a
    missing target — propagates and fails the case.

    ``statements`` (the reported golden-comparable emission) is
    :func:`_lower_conflict_write`'s own SEPARATE, PURE re-lowering of the
    ORIGINAL, undecoded rows — the rows this function actually
    buffers are decoded to native carriers (:func:`decode_write_row`) only for
    THIS real execution, so a case-authored wire spelling (`m-opt-lock-013`'s
    own decimal `balance`) validates at the coercion-only developer boundary
    without the reported emission's bind ever drifting from the case-authored
    literal.
    """
    resolved = _resolve_conflict_writes(model, target, mutation, write_rows)
    statements = _lower_conflict_write(model, dialect, concurrency, resolved)
    instant = normalize_instant(dt.datetime.fromisoformat(_INERT_CLOCK_INSTANT))
    database = handle.Database(port, model, dialect=dialect, clock=FixedClock(instant))
    landed = _landed_conflict_rows(resolved)

    def body(tx: handle.Transaction) -> int:
        for write in resolved:
            _buffer_execution_instruction(tx, model, write.resolved)
        return landed  # the expectation machinery already verified this on success

    observation_requiring = _versioned_non_temporal_version_attribute(model, target) is not None
    implied = _implied_shortfall_error(observation_requiring, concurrency, model, target)
    affected, log = _conflict_attempt_affected(database, concurrency, implied, body)
    return statements, affected, log, log.round_trips if log is not None else 0


# A temporal conflict attempt's verb. The case names none (`when.mutation` is
# the NON-temporal lane's keyed UPDATE/DELETE) because a temporal target's
# conflict write is always the milestone close — so the close names itself, for
# the row diagnostics that report which write refused an authored key.
_CLOSE_MUTATION: Final[str] = "close"


def _run_conflict_close(
    port: DbPort,
    dialect: Dialect,
    model: AcceptedMetamodel,
    target: str,
    concurrency: Concurrency,
    write_row: Mapping[str, object],
    at: str,
    observed_tx_start: str | None,
    observed_valid_start: str | None,
    shadow: TemporalShadow,
) -> tuple[tuple[LoweredStatement, ...], int, ExecutionLog | None, int]:
    """Lower and execute one TEMPORAL conflict attempt's close — ONE
    transaction opened on the port itself, ``clock=FixedClock(at)``. Composes the SAME two halves
    production does — :func:`~parallax.snapshot.handle.plan_temporal_close`
    settles the step, :func:`~parallax.snapshot.handle.lower_step` renders it —
    for a conflict case's own close-only probe, never a REAL chaining mutation,
    and executes it on the port's own transaction; a standalone close has
    nothing to coalesce or FK-order with, so it bypasses the buffer/flush
    pipeline entirely.

    A case names its close's coordinates one of two ways, and never both:

    * the ADDRESS directly — the write row's own ``validEnd`` completes a
      bitemporal close's address and ``observed_tx_start`` supplies its gate
      candidate, both the case's EXPLICIT authored fields
      (`when.write.validEnd` / `when.observedTxStart`). This is how a case tests
      a KNOWN stale-or-fresh gate, whose whole point is that it matches no
      milestone;
    * the OBSERVED MILESTONE — ``observed_valid_start`` with
      ``observed_tx_start`` is that milestone's own edge coordinate
      (`when.observedValidStart` / `when.observedTxStart`), which resolves
      against the case's tracked state and supplies BOTH the address's
      Valid-Time end and the gate from the ONE milestone it names. A key holding
      several disjoint current rectangles is then addressable, and the address
      and the gate provably come from one observation rather than from two
      independently authored coordinates.

    Its ``write_row`` is a case-authored row like any other, so it becomes a
    durable row through :func:`_durable_row`, which entitles a temporal row to no
    observation control key: the coordinates this close binds are the SEPARATE
    arguments, and a row that spelled its own would otherwise be projected away
    to the address's primary-key cells and the author's coordinate silently
    replaced by the one beside the write.

    A zero-row close is caught only as the class the case's own mode implies
    (:func:`_implied_shortfall_error`); every other class propagates, so the
    ``affectedRows`` observation can never absorb a misclassified failure.
    """
    row, _authored_none = _durable_row(model, target, _CLOSE_MUTATION, write_row)
    observed_valid_end = cast("str | None", row.pop("validEnd", None))
    if observed_valid_start is not None:
        observed_valid_end, observed_tx_start = _observed_milestone_coordinates(
            model, target, row, observed_valid_end, observed_valid_start, observed_tx_start, shadow
        )
    # The standalone close is settled outside any unit of work, so it is handed
    # its own Transaction Instant over the SAME clock the transaction below runs
    # on — the two can never derive different instants from one `at`.
    clock = FixedClock(normalize_instant(dt.datetime.fromisoformat(at)))
    step = handle.plan_temporal_close(
        row,
        target,
        model,
        concurrency,
        TransactionInstant(clock),
        observed_tx_start,
        observed_valid_end,
    )
    statement = handle.lower_step(step, model, dialect)
    # A standalone close is no keyed mutation and no unit of work buffers it, so
    # it runs on the port's own transaction — public `m-db-port`, the same
    # boundary ``db.transact`` opens — and brackets production's own Database
    # Call recorder, which is what makes its round trip countable in the one
    # vocabulary every other lane reports in.
    #
    # A Bitemporal close is unreachable through a keyed verb: every
    # closure-bearing entry in `bitemp_write._TOPOLOGIES` chains at least the
    # head rectangle, and the goldens author the close alone. A
    # Transaction-Time-Only `terminate` does close without chaining
    # (`txtime_write.MILESTONE_CHAIN.topology`), but it derives its address and
    # gate from the milestone its observation names, while a conflict case
    # authors both directly — including the deliberately stale gate whose whole
    # point is that it matches no milestone.
    calls = TraceRecorder()

    def run_close(conn: DbPort) -> int:
        started = time.perf_counter_ns()
        try:
            affected = conn.execute_write(
                dialect.to_driver_sql(statement.sql), list(statement.binds)
            )
        except DatabaseError as exc:
            calls.failed(statement, "write", time.perf_counter_ns() - started, exc)
            raise
        calls.completed(
            statement, "write", time.perf_counter_ns() - started, WriteCompleted(affected)
        )
        # The SAME authoritative interpreter `parallax.snapshot.handle`'s own
        # flush executor asks, so the two callers can never disagree on what a
        # count means.
        with calls.enforcing():
            enforce_affected_rows(step, affected)
        return affected

    implied = _implied_shortfall_error(True, concurrency, model, target)
    affected = _admitted_affected(implied, lambda: port.transaction(run_close))
    # No Execution Log describes this lane: it opened no transaction through
    # `db.transact`, so there is no attempt graph to report and no case authors
    # the oracle for one.
    return (statement,), affected, None, calls.write_batch_trace("finalization").round_trips


def _observed_milestone_coordinates(
    model: AcceptedMetamodel,
    target: str,
    row: Mapping[str, object],
    authored_valid_end: str | None,
    observed_valid_start: str,
    observed_tx_start: str | None,
    shadow: TemporalShadow,
) -> tuple[str | None, str | None]:
    """The close coordinates the ONE milestone a case named the edge of supplies:
    that milestone's own Valid-Time end (the address's exclusive upper bound) and
    its own Transaction-Time start (the gate candidate).

    Both come from one resolved observation, so an implementation that resolved
    the observation by primary key alone — picking whichever of a key's current
    rectangles it happened to hold — cannot render the address this returns.
    That is the whole reason a case names an edge instead of an address.

    An authored ``validEnd`` alongside is refused rather than cross-checked: the
    two spellings answer the same question, and a case that agrees with itself
    proves nothing the derivation does not already, while a case that disagrees
    would have to pick a winner.
    """
    if authored_valid_end is not None:
        raise EngineError(
            f"{target!r} {_CLOSE_MUTATION!r}: a close names its observed milestone's edge "
            "(`observedValidStart`) or its address (`write.validEnd`), never both — the "
            "address of an edge-named close is DERIVED from the milestone the edge selects"
        )
    entity_metadata = case_entity(model, target)
    edge = temporal_state.observed_edge(
        model, entity_metadata, valid_start=observed_valid_start, tx_start=observed_tx_start
    )
    observation = shadow.resolve(model, entity_metadata, row, edge)
    if observation is None:
        raise EngineError(
            f"{target!r} {_CLOSE_MUTATION!r}: no current milestone of this key carries the "
            f"observed edge {edge!r} — a close observes a milestone the case's own state holds"
        )
    valid_end, tx_start = temporal_state.observed_close_coordinates(
        model, entity_metadata, observation
    )
    return cast("str | None", valid_end), cast("str | None", tx_start)


def _conflict_write_rows(attempt: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    """One conflict attempt's authored ``write`` as the ordered row sequence both
    forms denote: a lone object is the one-element case of the multi-key array
    (`m-case-format`), so the single seam here spares every lane downstream from
    knowing which spelling the case chose."""
    raw = attempt["write"]
    if isinstance(raw, list):
        return tuple(cast("list[Mapping[str, object]]", raw))
    return (cast("Mapping[str, object]", raw),)


def _conflict_close_row(
    case: case_format.Case, attempt: Mapping[str, object]
) -> Mapping[str, object]:
    """The ONE milestone row a temporal conflict attempt closes.

    The multi-key ``write`` array is a keyed, NON-temporal form — a temporal
    target's write expands into a close plus its successors per key and never
    collapses into one set-based statement — so an array reaching a close is
    refused rather than silently reduced to a row the case did not single out.
    """
    raw = attempt["write"]
    if isinstance(raw, list):
        raise EngineError(
            f"{case.path.name}: a temporal conflict attempt closes one milestone row, and "
            "the multi-key `write` array form is keyed and non-temporal"
        )
    return cast("Mapping[str, object]", raw)


# The observed milestone's own edge, authored beside a temporal conflict write.
_MILESTONE_EDGE_KEYS: Final[frozenset[str]] = frozenset({"observedTxStart", "observedValidStart"})


def _refuse_unentitled_observed_edge(
    case: case_format.Case, when: Mapping[str, object], *, is_temporal: bool
) -> None:
    """Refuse an observation coordinate the conflict target, mode, or attempt
    form cannot consume.

    Four entitlements, all decided here because all are properties of the CASE
    rather than of any one attempt's arithmetic (`m-case-format`, *Naming the
    observed milestone*):

    * a NON-temporal target has no milestones and no edge to name one with, so
      the coordinates would be read by nothing — the versioned conflict path
      never looks at them. That holds wherever they are spelled, so the root
      ``when`` and every attempt are checked alike;
    * a RETRY attempt re-reads state the concurrent writer left behind, while an
      edge selects among the milestones the case's own loaded fixtures hold. The
      two cannot be reconciled without a resolving read no lane performs, so the
      OBSERVATION form is single-attempt only and a retry names its address
      directly;
    * a retry sequence reads each attempt's own coordinates and never the root
      ``when``'s, so a root coordinate beside ``attempts`` is consumed by nothing.
      The two authoring locations are alternatives, not a default and an
      override;
    * ``observedTxStart`` standing ALONE is the address form's gate candidate,
      and a ``locking`` close renders no gate, so it is entitled only under
      ``optimistic``. Beside ``observedValidStart`` it is instead the edge's
      Transaction-Time half, which selects the milestone in either mode. Locking
      is the default, so an unstated mode is refused with an explicit one.

    The Transaction-Time-Only arm of the first entitlement lives where the edge
    is built (:func:`temporal_state.observed_edge`), which refuses a coordinate
    on an axis the target does not declare.
    """
    raw_attempts = when.get("attempts")
    attempts = (
        cast("list[Mapping[str, object]]", raw_attempts) if isinstance(raw_attempts, list) else []
    )
    if not is_temporal:
        for pointer, source in [
            ("`when`", when),
            *((f"attempt {index}", attempt) for index, attempt in enumerate(attempts)),
        ]:
            if any(key in source for key in _MILESTONE_EDGE_KEYS):
                raise EngineError(
                    f"{case.path.name}: a NON-temporal conflict target has no milestone to "
                    f"observe, so it may author neither of {sorted(_MILESTONE_EDGE_KEYS)} "
                    f"({pointer})"
                )
    for index, attempt in enumerate(attempts):
        if "observedValidStart" in attempt:
            raise EngineError(
                f"{case.path.name}: attempt {index} names its observed milestone's edge "
                "(`observedValidStart`), which selects among the case's own fixtures — a "
                "retry re-reads what the concurrent writer left, so a retry attempt names "
                "its address (`write.validEnd`) directly"
            )
    if raw_attempts is not None:
        for key in sorted(_MILESTONE_EDGE_KEYS):
            if key in when:
                raise EngineError(
                    f"{case.path.name}: the root `when` authors {key!r} beside `attempts` — "
                    "a retry sequence reads each attempt's own coordinates, so a root one is "
                    "consumed by no attempt"
                )
    if _concurrency(case) == "optimistic":
        return
    for pointer, source in [
        ("`when`", when),
        *((f"attempt {index}", attempt) for index, attempt in enumerate(attempts)),
    ]:
        if "observedTxStart" in source and "observedValidStart" not in source:
            raise EngineError(
                f"{case.path.name}: `locking` mode renders no gate, so a lone "
                f"`observedTxStart` is consumed by nothing ({pointer}) — it is entitled "
                "under `optimistic`, or beside `observedValidStart` as the observed "
                "milestone's edge"
            )


def run_conflict_case(
    case: case_format.Case, dialect_name: str, port: DbPort
) -> tuple[list[Emission], int, dict[str, list[Row]] | None, ExecutionLog | None, int]:
    """Run a `conflict` case (`m-opt-lock` / `m-txtime-write` / `m-bitemp-write`):
    the single-attempt form (`when.write`), or the `when.attempts` retry
    sequence — each attempt its OWN `db.transact` unit,
    in order, each with its own statements /
    affected-row count (the case's own `0`-then-`1` retry-contract witness). A
    NON-temporal target (a keyed UPDATE or DELETE, named by `when.mutation`)
    buffers every row of its `write` — one row, or the multi-key array whose
    rows the batching rule may collapse into a single set-based statement —
    through the neutral `Transaction.write_neutral` ingress; a TEMPORAL target composes
    `handle.plan_temporal_close` directly, one milestone row at a time.

    Loads no fixtures itself (the caller's own lifecycle does, per
    `m-case-format`'s conflict-shape default); applies `given.apply` verbatim
    and out-of-band FIRST (the concurrent writer, `_apply_given_apply`).
    Returns the ordered emissions, the FINAL (single-attempt or last-retry)
    affected-row count — the schema's one `affectedRows` slot,
    `m-conformance-adapter` — and the resulting table state when the case
    authors `then.tableState`.
    """
    model = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    when = _when(case)
    concurrency = _concurrency(case)
    target = _conflict_target(case, model)
    mutation = _conflict_mutation(when)
    is_temporal = _is_temporal_entity(model, target)
    # The state an edge-named close resolves its observed milestone against — the
    # case's own loaded fixtures, which are exactly the milestones its address
    # can select. Seeded before `given.apply`, whose out-of-band writer is a
    # CONCURRENT transaction this one never observed.
    shadow = TemporalShadow()
    _refuse_unentitled_observed_edge(case, when, is_temporal=is_temporal)
    if is_temporal:
        _seed_shadow_from_fixtures(case, model, shadow)
    emissions: list[Emission] = []
    affected = 0
    round_trips = 0
    logs: list[ExecutionLog | None] = []
    try:
        _apply_given_apply(case, dialect, port, shadow)
        raw_attempts = when.get("attempts")
        attempts: list[tuple[str, Mapping[str, object]]] = (
            [
                (f"/when/attempts/{index}/write", attempt)
                for index, attempt in enumerate(cast("list[Mapping[str, object]]", raw_attempts))
            ]
            if isinstance(raw_attempts, list)
            else [("/when/write", when)]
        )
        for pointer, attempt in attempts:
            if is_temporal:
                statements, affected, log, attempt_trips = _run_conflict_close(
                    port,
                    dialect,
                    model,
                    target,
                    concurrency,
                    _conflict_close_row(case, attempt),
                    cast("str", attempt["at"]),
                    cast("str | None", attempt.get("observedTxStart")),
                    cast("str | None", attempt.get("observedValidStart")),
                    shadow,
                )
            else:
                statements, affected, log, attempt_trips = _run_conflict_write(
                    port,
                    dialect,
                    model,
                    target,
                    concurrency,
                    _conflict_write_rows(attempt),
                    mutation,
                )
            emissions.extend(Emission(pointer, s.sql, s.binds) for s in statements)
            logs.append(log)
            round_trips += attempt_trips
    except _LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    then = case.document.get("then")
    table_state = (
        read_table_state(port, model, dialect)
        if isinstance(then, Mapping) and "tableState" in then
        else None
    )
    # A `when.attempts` sequence drives one transaction PER attempt, so the lane
    # holds one log per attempt and no single invocation to report; only the
    # single-attempt form has one. The round trips are every attempt's, summed —
    # a retry sequence's own cost is what it did across all of them.
    return (
        emissions,
        affected,
        table_state,
        logs[0] if len(logs) == 1 else None,
        round_trips,
    )


# --------------------------------------------------------------------------- #
# Error — the m-db-error single-connection classification lane.                #
# --------------------------------------------------------------------------- #
def _error_trigger(
    case: case_format.Case, dialect_name: str
) -> list[tuple[str, tuple[object, ...]]]:
    """The authored single-connection trigger DML (`then.statements`) for ``dialect``."""
    then_raw = case.document.get("then")
    then: Mapping[str, object] = (
        cast("Mapping[str, object]", then_raw) if isinstance(then_raw, Mapping) else {}
    )
    raw = then.get("statements")
    if not isinstance(raw, list) or not raw:
        raise EngineError(f"{case.path.name}: error case has no `then.statements` trigger")
    trigger: list[tuple[str, tuple[object, ...]]] = []
    for entry in cast("list[Mapping[str, object]]", raw):
        sql = entry["sql"]
        text = cast("Mapping[str, str]", sql)[dialect_name] if isinstance(sql, Mapping) else sql
        binds = entry.get("binds", [])
        trigger.append((cast("str", text), tuple(cast("list[object]", binds))))
    return trigger


def run_error_case(
    case: case_format.Case, dialect_name: str, port: DbPort
) -> tuple[list[Emission], str, str | int, int]:
    """Run an error-shape case and report the raised failure's classification.

    The single-connection trigger IS the authored ``then.statements`` — ordered
    DML whose final statement raises (m-case-format); there is no neutral
    instruction to translate, so executing it verbatim is the case contract, not
    golden reverse-engineering. Every statement before the last must succeed;
    the last must raise a classified :class:`DatabaseError`, whose neutral
    category and preserved native code are the observations
    (``errorClass`` / ``nativeCode``). Each call is recorded on production's own
    Database Call recorder — completed or failed, the failing one included — and
    the round trips are that trace's, so this lane reports the same provenance
    every other run lane does rather than a count of what it meant to emit. A
    ``when.concurrency`` trigger needs
    two barrier-synchronized sessions this single-connection lane cannot drive
    at all — it is refused here UNCONDITIONALLY, never dispatched to from a
    caller that owns two sessions (
    ``m-read-lock-006`` is graded by the CASE-DRIVEN two-session rounds
    runner instead, ``parallax.conformance.concurrency_runner`` — this
    module's own dispatcher (`tests/compatibility/test_run_sweep.py`) routes it
    there and never reaches this function for that case at all; the
    provider-contract deadlock proof remains the OTHER two-session witness,
    hand-authored rather than case-driven). The ``m-db-error`` two-connection
    choreography (deadlock / lock-wait) stays covered by the provider-contract
    proof alone this increment (see the module's own extensibility note).
    """
    when = case.document.get("when")
    if isinstance(when, Mapping) and "concurrency" in when:
        raise EngineError(
            f"{case.path.name}: two-connection when.concurrency choreography needs two "
            "barrier-synchronized sessions this single-connection lane cannot drive — "
            "the case-driven rounds runner (parallax.conformance.concurrency_runner) or "
            "the provider contract proof grades it instead, never this function"
        )
    trigger = _error_trigger(case, dialect_name)
    dialect = dialect_for(dialect_name)
    emissions: list[Emission] = []
    calls = TraceRecorder()
    final = len(trigger) - 1
    for index, (sql, binds) in enumerate(trigger):
        emissions.append(Emission(f"/then/statements/{index}", sql, binds))
        statement = LoweredStatement(sql, binds)
        started = time.perf_counter_ns()
        try:
            affected = port.execute_write(dialect.to_driver_sql(sql), _driver_binds(binds))
        except DatabaseError as exc:
            calls.failed(statement, "write", time.perf_counter_ns() - started, exc)
            if index != final:
                raise EngineError(
                    f"{case.path.name}: trigger statement {index} raised before the final "
                    f"statement: {exc}"
                ) from exc
            if exc.category is None or exc.native_code is None:
                raise EngineError(
                    f"{case.path.name}: the trigger raised an unclassified database error: {exc}"
                ) from exc
            return (
                emissions,
                exc.category,
                exc.native_code,
                calls.write_batch_trace("finalization").round_trips,
            )
        calls.completed(
            statement, "write", time.perf_counter_ns() - started, WriteCompleted(affected)
        )
    raise EngineError(f"{case.path.name}: the final trigger statement did not raise")


# --------------------------------------------------------------------------- #
# Rejected — the pre-SQL model-aware validation lane (m-case-format).          #
# --------------------------------------------------------------------------- #
def _rejected_target(case: case_format.Case, model: AcceptedMetamodel) -> str:
    """The queried/written root a `rejected` case's `when` omits.

    A `rejected` case's `when.write` input carries no explicit handle: the
    model-aware default `m-predicate` "the four-step validation rule" fixes is
    the inheritance family root when the model declares one, else the model's own
    first entity. It is the entity `validate_write` checks the payload against. A
    `when.objectQuery` case names its own queried position and reaches none of
    this.

    Reported by CANONICAL spelling: the root arrives here as accepted Metadata,
    so its Identity is already resolved, and spelling it bare would put a
    selection the case never authored back through the ambiguity rule that
    adjudicates an authored one — where a local name two namespaces share
    resolves to nothing and a local name an ownerless sibling also carries
    resolves to that sibling.
    """
    root = _default_family_root(model)
    if root is not None:
        return root.identity.canonical
    return _first_declared_entity(case)


# The `rejected` shape's schema `oneOf`: exactly one of these keys, never zero
# or more than one (m-case-format).
_REJECTED_WHEN_KINDS: Final[tuple[str, ...]] = ("objectQuery", "model", "write")


def _rejected_when_kind(case: case_format.Case, when: Mapping[str, object]) -> str:
    """The `rejected` case's single recognized `when` input, enforcing the
    schema's `oneOf` (m-case-format): a caller that reaches the engine without
    schema validation (or a hand-built two-input synthetic case) must not
    silently dispatch on the first recognized key — zero or more than one
    recognized input is a loud, named refusal, mirroring the harness's own
    mirror guard for this rule.
    """
    present = [kind for kind in _REJECTED_WHEN_KINDS if kind in when]
    if len(present) != 1:
        raise EngineError(
            f"{case.path.name}: a `rejected` case must carry EXACTLY ONE of "
            f"`when.objectQuery` / `when.model` / `when.write` (m-case-format schema "
            f"`oneOf`); found {present!r}"
        )
    return present[0]


def run_rejected_case(case: case_format.Case) -> str:
    """Grade a `rejected` case's pre-SQL refusal, returning the classified rule.

    A `rejected` case carries EXACTLY ONE of `when.objectQuery` / `when.model` /
    `when.write` (m-case-format schema `oneOf`) — enforced by
    :func:`_rejected_when_kind` before dispatch, since the schema `oneOf` cannot
    protect a caller that reaches this engine without schema validation. An
    `objectQuery` input is deserialized through the same `m-object-query` serde
    every read uses, then checked by the shared query validation
    (`m-predicate` / `m-navigate` / `m-value-object`) — the same rules the read
    preflight seam applies, so the two paths cannot drift. A `model` input first
    passes the descriptor frontend's own pre-formation family validator
    (:func:`~parallax.descriptor.validate_inheritance_families`) for descriptor
    spellings the accepted algebra cannot represent, then goes through the same
    public :func:`~parallax.descriptor.domain_model_from_document` door every
    reusable corpus model does. **That order is load-bearing, not incidental**:
    the document door gates on the canonical schema FIRST, and four inline
    `rejected` models violate that schema on purpose, so forming first would
    report each as a `DescriptorSchemaError` instead of the family rule the case
    authored. The family validator parses shape only and has no schema phase,
    which is exactly why it can answer for a document expected never to form.

    A `write` input is one of three, dispatched on the members the input itself
    carries (`m-case-format` Rejected cases) — never on the case's tags or
    filename. A `target` names a predicate-selected instruction; `rows` names a
    keyed instruction, which brings its own `entity` handle
    (:func:`_rejected_keyed_write`); anything else is the bare neutral write row
    (①), which names no handle at all and is therefore resolved against the
    model's default entity (`_rejected_target`'s own convention, reused here —
    the family root when the model declares one, else the model's single
    entity), DECODED to native carriers (:func:`decode_write_row` — the case
    authors this row in the SAME wire spellings a read golden uses, never the
    native form the developer-facing validator now requires), and checked by the
    shared `validate_write` (`m-value-object` write validation x `m-inheritance`
    concrete-subtype write protocol) — the SAME validator the developer
    transaction verbs call at buffer time, so the two
    paths cannot drift.

    Membership can decide the form only because `target` and `rows` are RESERVED
    from a bare row at this position (`compatibility-case.schema.json`
    `$defs/bareWriteRow`): neither is a domain member name here, so no row can be
    re-read as an instruction and no instruction as a row. It can decide it only
    for an OBJECT at all, so the multi-key ARRAY the shared `when.write`
    vocabulary carries for the conflict lane is refused here by shape, before any
    member is asked for.

    Raises :class:`EngineError` if the input is unexpectedly accepted (no rule
    violation detected) — the caller compares the returned rule against the
    case's `then.rejectedRule`.
    """
    when = _when(case)
    kind = _rejected_when_kind(case, when)
    model = load_case_metamodel(case)
    if kind == "objectQuery":
        try:
            query = deserialize_query(when["objectQuery"])
        except CanonicalDocumentError as exc:
            raise EngineError(f"{case.path.name}: {exc}") from exc
        root = case_entity(model, query.target.canonical)
        try:
            validate_object_query(root, query, model)
        except ModelRejectedError as exc:
            return exc.rule
        raise EngineError(
            f"{case.path.name}: the model-aware validator accepted an Object Query the case "
            "expects rejected pre-SQL"
        )
    if kind == "model":
        inline_model = cast("Mapping[str, object]", when["model"])
        try:
            validate_inheritance_families(inline_model)
        except inheritance.InheritanceError as exc:
            return exc.rule
        except DescriptorError as exc:
            raise EngineError(f"{case.path.name}: {exc}") from exc
        try:
            domain_model_from_document(inline_model)
        except DescriptorError as exc:
            raise EngineError(f"{case.path.name}: {exc}") from exc
        except (
            MetamodelValidationError
        ) as exc:  # pragma: no cover - formation tests own diagnostics
            codes = tuple(issue.code for issue in exc.issues)
            if len(codes) != 1:
                raise EngineError(
                    f"{case.path.name}: inline model produced {len(codes)} formation issues "
                    f"{codes!r}; a rejected case must isolate exactly one rule"
                ) from exc
            return codes[0]
        raise EngineError(
            f"{case.path.name}: the model-aware validator accepted an inline model the case "
            "expects rejected pre-SQL"
        )
    raw_write = when["write"]
    if not isinstance(raw_write, Mapping):
        raise EngineError(
            f"{case.path.name}: a rejected `when.write` is a predicate-selected instruction, a "
            f"keyed instruction, or a bare neutral write row — all objects, and the members "
            f"decide which. {type(raw_write).__name__} is the conflict lane's multi-key form, "
            f"which asserts an aggregate affected-row count no rejected case emits SQL to "
            f"produce (m-case-format Rejected cases)"
        )
    row = cast("Mapping[str, object]", raw_write)
    if "target" in row:
        try:
            instruction = instructions.deserialize(_canonical_predicate_doc(row))
        except (
            WritePlanningError
        ) as exc:  # pragma: no cover - schema validation owns malformed writes
            raise EngineError(f"{case.path.name}: {exc}") from exc
        if not isinstance(
            instruction, PredicateWrite
        ):  # pragma: no cover - target implies predicate
            raise EngineError(f"{case.path.name}: rejected predicate write decoded as keyed")
        decoded = _decoded_predicate_write(instruction, model)
        try:
            instructions.validate_instruction(decoded, model)
            target = case_entity(model, decoded.target.entity)
            reject_readless_document_many(target, decoded)
        except WriteRejectedError as exc:
            return exc.rule
        raise EngineError(  # pragma: no cover - rejected cases must classify
            f"{case.path.name}: the model-aware validator accepted a predicate write the "
            "case expects rejected pre-SQL"
        )
    if "rows" in row:
        return _rejected_keyed_write(case, row, model)
    target = case_entity(model, _rejected_target(case, model))
    try:
        inheritance.validate_subtype_write(model, target, row)
    except inheritance.InheritanceError as exc:
        return exc.rule
    _reject_undeclared_bare_row_members(case, target, row, model)
    try:
        validate_write(target, decode_write_row(target, row, model), model)
    except WriteRejectedError as exc:
        return exc.rule
    raise EngineError(
        f"{case.path.name}: the model-aware validator accepted a write the case expects "
        "rejected pre-SQL"
    )


# The framework control key a case-format write row may carry beside its members
# (`compatibility-case.schema.json` `$defs/writeRow`): flush-time observation
# context, never a declared member. The canonical durable instruction forbids it, so
# a row that may not carry one is already refused at schema validation.
_ROW_CONTROL_KEYS: Final[frozenset[str]] = frozenset({"observedVersion"})


def _reject_undeclared_bare_row_members(
    case: case_format.Case,
    target: EntityMetadata,
    row: Mapping[str, object],
    model: AcceptedMetamodel,
) -> None:
    """Refuse a bare `when.write` row naming members ``target`` does not declare.

    Member honesty is a case-authoring judgement, not a violated normative MUST: an
    undeclared name resolves to no declared position, so no rule of the closed
    `then.rejectedRule` vocabulary is about it, and grading the row anyway reports
    whichever rule some OTHER member happens to violate — a case that passes while
    testing something it never claimed. The keyed instruction lane refuses the same
    way (`instructions.validate_instruction`), so one neutral write row is judged one
    way whichever form carries it.

    Asked AFTER the concrete-subtype protocol (run just above, which is why this lane
    calls it explicitly rather than leaving it to `validate_write`'s own first pass):
    `m-inheritance` orders those rules first, and they own the family-specific names
    a row may not carry — the tag column and the `tag` / `tagValue` / `familyVariant`
    handles as `subtype-write-metadata-field`, a sibling branch's attribute as
    `subtype-write-sibling-attribute` — which are classified rules rather than
    authoring defects. It is asked BEFORE the declared-member walk so that a row
    carrying both an undeclared name and a real defect is refused rather than graded
    on the defect.
    """
    view = inheritance.view(model).entity(target.identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        return
    declared = {attribute.identity.name for attribute in view.applicable_attributes}
    declared.update(vo.identity.path[-1] for vo in view.applicable_value_objects)
    unknown = sorted(key for key in row if key not in declared and key not in _ROW_CONTROL_KEYS)
    if unknown:
        raise EngineError(
            f"{case.path.name}: the bare write row names {unknown}, which are not "
            f"attributes or value objects of {target.identity.name}"
        )


def _rejected_keyed_write(
    case: case_format.Case, authored: Mapping[str, object], model: AcceptedMetamodel
) -> str:
    """Grade a rejected `when.write` that is a KEYED INSTRUCTION, returning the rule.

    A keyed instruction names its own `entity`, so unlike the bare neutral write
    row beside it this input needs no default-target convention: the handle it is
    validated against is the one it authored. The canonical document is rebuilt
    from the instruction members alone, exactly as the writeSequence/scenario
    producer rebuilds it — the case format's `at` is harness Clock context and
    never an instruction field (`m-unit-work`), so it is not carried across.

    The refusal is the shared build-time
    :func:`~parallax.core.unit_work.instructions.validate_instruction`'s — the
    SAME validator every keyed developer verb runs before it buffers anything — and it
    runs in the same PLACE, after the concrete-subtype payload-shape rules
    (`m-inheritance` "Concrete-subtype writes"). Those rules classify a
    framework-owned metadata key and a sibling-branch member more specifically
    than the generic member-name-honesty gate ever could, so a keyed update of
    `CardPayment` carrying `CashPayment`'s own attribute is
    `subtype-write-sibling-attribute` rather than an undeclared-member authoring
    failure. Asking them here and in that order is what makes the keyed rejected
    lane, the bare-row lane, and the developer transaction one classification.
    """
    doc: dict[str, object] = {
        key: authored[key]
        for key in ("mutation", "entity", "rows", "validFrom", "until")
        if key in authored
    }
    try:
        instruction = instructions.deserialize(doc)
    except (
        instructions.WriteInstructionError
    ) as exc:  # pragma: no cover - schema validation owns malformed writes
        raise EngineError(f"{case.path.name}: {exc}") from exc
    keyed_target = (
        entity_by_name(model, instruction.entity) if isinstance(instruction, KeyedWrite) else None
    )
    if isinstance(instruction, KeyedWrite) and keyed_target is not None:
        for keyed_row in instruction.rows:
            try:
                inheritance.validate_subtype_write(model, keyed_target, keyed_row)
            except inheritance.InheritanceError as exc:
                return exc.rule
    try:
        instructions.validate_instruction(instruction, model)
    except instructions.InstructionRejectedError as exc:
        return exc.rule
    raise EngineError(
        f"{case.path.name}: the model-aware validator accepted a keyed write instruction the "
        "case expects rejected pre-SQL"
    )


def wire_value(value: object) -> object:
    """Render one managed scalar to its canonical wire form (m-db-port / m-core).

    JSON-native scalars pass through; a ``Decimal`` renders as its exact decimal
    string. A ``datetime`` is a ``timestamp`` INSTANT: it is normalized through the
    m-core boundary form (aware → UTC/µs, a naive value rejected loudly) BEFORE
    ISO-rendering, so a non-UTC offset is canonicalized rather than graded as-is. A
    ``date`` / ``time`` is not an instant and renders ISO-8601 as-is; a ``UUID``
    renders as its canonical string, and a byte buffer as lowercase hex. Anything
    already wire (or an unrecognized carrier) is returned unchanged.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, TemporalBound):
        # A temporal interval's open upper bound (the m-core infinity sentinel the
        # port returns for native `timestamptz` infinity) renders as the canonical
        # `infinity` literal — the same literal the golden binds and `then.rows` use.
        return INFINITY_LITERAL
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, dt.datetime):
        # `datetime` subclasses `date`, so this instant branch MUST precede the
        # `date`/`time` branch below.
        return normalize_instant(value).isoformat()
    if isinstance(value, (dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return value.hex()
    return value


# --------------------------------------------------------------------------- #
# Execution provenance (m-execution-log) — the `execution` observation.        #
# The adapter REPORTS what production recorded; it never re-derives a trace    #
# from the case's own golden (m-conformance-adapter "Execution provenance").   #
# --------------------------------------------------------------------------- #
type CaseProvenance = ReadTrace | ExecutionLog


class _StatementIndexer:
    """Hands each Database Call, in execution order, its index into the
    envelope's own ``emissions``, and VALIDATES that the index names the
    statement the call ran.

    The correspondence is positional — the k-th call ran the k-th emission — but
    it is not assumed. On the grouped-scenario and conflict lanes the two sides
    are built independently: the emissions are a pure re-lowering of the
    case-authored rows, per step, while execution buffers the whole group and
    flushes it as one plan, so foreign-key reordering inside that plan or any
    drift between the two lowerings would leave position *k* naming a different
    statement while the case still graded green. Comparing the SQL text closes
    every mechanism that changes it. A disagreement is an adapter defect rather
    than a case failure, so it is raised here instead of reported, exactly as a
    count mismatch is.

    Binds are deliberately NOT compared. The two sides differ in representation
    on purpose: the emission stays on the undecoded, case-authored wire spelling
    (an authored ``250.00``) while execution binds the native carrier a decode
    produced (``Decimal("250.00")``), which is what keeps the golden-bind
    comparison from drifting. The residual is therefore two statements with
    identical SQL and different binds, which a swap would leave undetected — one
    known gap in one place, rather than an unchecked assumption spread across
    three lanes.
    """

    __slots__ = ("_emissions", "_position")

    def __init__(self, emissions: Sequence[Emission]) -> None:
        self._emissions = emissions
        self._position = 0

    def take(self, call: DatabaseCall) -> int | None:
        """``call``'s statement index, or ``None`` on a lane whose envelope
        reports no emission at all (`api-conformance`)."""
        if not self._emissions:
            return None
        index = self._position
        self._position += 1
        if index >= len(self._emissions):
            raise EngineError(
                f"execution provenance recorded {index + 1} database call(s) but the "
                f"envelope reports only {len(self._emissions)} emission(s): the observation's "
                "statement index would name nothing (m-conformance-adapter)"
            )
        emitted = self._emissions[index].sql
        if call.statement.sql != emitted:
            raise EngineError(
                f"execution provenance's database call {index} ran {call.statement.sql!r}, "
                f"but the envelope's emission {index} reports {emitted!r}: the observation's "
                "statement index would name a different statement (m-conformance-adapter)"
            )
        return index


def execution_observation(
    provenance: CaseProvenance, emissions: Sequence[Emission]
) -> dict[str, object]:
    """One run's `execution` observation, in the closed union the case oracle
    authors: a bare ``readTrace`` for a standalone read, or the whole
    ``transactionLog`` for a transactional run."""
    indexer = _StatementIndexer(emissions)
    if isinstance(provenance, ReadTrace):
        return {"readTrace": _wire_read_trace(provenance, indexer)}
    return {"transactionLog": _wire_transaction_log(provenance, indexer)}


def _wire_transaction_log(log: ExecutionLog, indexer: _StatementIndexer) -> dict[str, object]:
    return {
        "concurrency": log.concurrency,
        "retryPolicy": {
            "maxRetries": log.retry_policy.max_retries,
            "retryOptimisticConflicts": log.retry_policy.retry_optimistic_conflicts,
        },
        "attempts": [_wire_attempt(attempt, indexer) for attempt in log.attempts],
        "roundTrips": log.round_trips,
    }


_ATTEMPT_STATUS_WIRE: Final[dict[str, str]] = {
    "committed": "committed",
    "rolled_back": "rolled-back",
}

_TRIGGER_WIRE: Final[dict[str, str]] = {
    "read_dependency": "read-dependency",
    "finalization": "finalization",
}


def _wire_attempt(attempt: TransactionAttempt, indexer: _StatementIndexer) -> dict[str, object]:
    status = _ATTEMPT_STATUS_WIRE.get(attempt.status)
    if status is None:
        raise EngineError(
            f"execution provenance reports an {attempt.status!r} attempt after the run "
            "finished; a terminal Execution Log has already transitioned every attempt "
            "(m-execution-log)"
        )
    calls = list(attempt.calls)
    wire: dict[str, object] = {
        "status": status,
        "traces": [_wire_trace(trace, indexer) for trace in attempt.traces],
        "roundTrips": attempt.round_trips,
    }
    failure = attempt.failure
    if failure is not None:
        entry: dict[str, object] = {"phase": failure.phase, "retryEligible": failure.retry_eligible}
        if failure.code is not None:
            entry["code"] = failure.code
        if failure.database_call is not None:
            entry["databaseCall"] = _call_position(calls, failure.database_call)
        wire["failure"] = entry
    return wire


def _call_position(calls: Sequence[DatabaseCall], call: DatabaseCall) -> int:
    """Where ``call`` sits in an attempt's flattened calls, by IDENTITY.

    A failure references the one call OBJECT the attempt already recorded
    (`m-execution-log`), so the index is that object's position. Equality would
    answer the position of the first call that merely LOOKS the same — two runs
    of one statement whose durations happened to tie — and name the wrong
    statement while staying in range.
    """
    for position, candidate in enumerate(calls):
        if candidate is call:
            return position
    raise EngineError(
        "execution provenance reports an attempt failure referencing a Database Call "
        "the attempt does not hold, so the observation's `databaseCall` index would "
        "name nothing (m-conformance-adapter)"
    )


def _wire_trace(
    trace: ReadTrace | WriteBatchTrace, indexer: _StatementIndexer
) -> dict[str, object]:
    if isinstance(trace, ReadTrace):
        return {"readTrace": _wire_read_trace(trace, indexer)}
    return {
        "writeBatch": {
            "trigger": _TRIGGER_WIRE[trace.trigger],
            "calls": [_wire_call(call, indexer) for call in trace.calls],
            "roundTrips": trace.round_trips,
        }
    }


def _wire_read_trace(trace: ReadTrace, indexer: _StatementIndexer) -> dict[str, object]:
    return {
        "calls": [_wire_call(call, indexer) for call in trace.calls],
        "roundTrips": trace.round_trips,
    }


def _wire_call(call: DatabaseCall, indexer: _StatementIndexer) -> dict[str, object]:
    wire: dict[str, object] = {"kind": call.kind, "completion": _wire_completion(call.completion)}
    index = indexer.take(call)
    if index is not None:
        wire["statement"] = index
    return wire


def _wire_completion(
    completion: ReadCompleted | WriteCompleted | DatabaseCallFailed,
) -> dict[str, object]:
    if isinstance(completion, ReadCompleted):
        return {"readCompleted": {"returnedRows": completion.returned_rows}}
    if isinstance(completion, WriteCompleted):
        return {"writeCompleted": {"affectedRows": completion.affected_rows}}
    return {"failed": {"category": completion.category}}


def wire_row(row: Mapping[str, object]) -> Row:
    """Render every managed value of one observed row to canonical wire form.

    Takes any mapping, because the two sources differ in kind: a table-state read
    hands over the driver's own row, and the values lane hands over the immutable
    one production published.
    """
    return {key: wire_value(value) for key, value in row.items()}
