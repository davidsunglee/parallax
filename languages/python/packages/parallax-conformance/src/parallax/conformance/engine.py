"""The conformance compile/run engine — binding the corpus to the spine.

The adapter path compiles and runs a compatibility case directly against the
class-free engine spine (no dynamic class synthesis): the case's model YAML is
ingested through the ``m-descriptor`` deserializer, its ``when.operation`` through
the ``m-op-algebra`` deserializer, and the tree is lowered by ``m-sql``
``compile_read`` to one ``CompiledRead`` — its canonical ``Statement`` together
with the row transform that statement's own resolved position decided.
``compile`` emits that statement; ``run`` executes it through the injected
``m-db-port``, renders each observed row to wire form, and passes it through the
compiled read's own ``transform_row``. Compile eligibility (``m-case-format``
``compileEligibility``) is read from the case; the run-only minority is never
compiled.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import decimal
import os
import socket
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, Protocol, cast, runtime_checkable

from parallax.conformance import case_format, models, provision, temporal_state
from parallax.conformance.temporal_state import TemporalShadow
from parallax.core import batch_write, inheritance, navigate, opt_lock, read_lock
from parallax.core.base import INFINITY_LITERAL, TemporalBound, normalize_instant
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import DbPort, JsonDocument, Row
from parallax.core.descriptor import Attribute, DescriptorError, Entity, Metamodel, column_order
from parallax.core.descriptor import deserialize as deserialize_metamodel
from parallax.core.dialect import Dialect, dialect_for
from parallax.core.op_algebra import Operation, OperationError, OperationRejectedError, deserialize
from parallax.core.op_algebra import validate_operation as validate_op_algebra_operation
from parallax.core.sql_gen import CompiledRead, SqlGenError, Statement, compile_read
from parallax.core.temporal_read import (
    Pin,
    TemporalReadError,
    inject_as_of,
    resolve_pinned_instants,
    statement_pin,
)
from parallax.core.unit_work import (
    Concurrency,
    FixedClock,
    KeyedWrite,
    ObjectKey,
    Observation,
    PredicateWrite,
    WriteRejectedError,
    instructions,
    object_key,
    plan_flush,
    validate_write,
)
from parallax.core.unit_work.instructions import WriteInstruction
from parallax.snapshot import handle, materialize
from parallax.snapshot.handle import (
    TransactionTimePinReadOnlyError,
    WriteLoweringError,
    find,
    find_history,
    lower_write,
    validate_source_pin,
)

__all__ = [
    "Emission",
    "EngineError",
    "RunOnly",
    "compile_read_case",
    "compile_scenario_case",
    "compile_write_sequence_case",
    "eligibility",
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
    (COR-3 Phase 8 increment 5: an observed gate value, or a chained row's payload
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


def load_case_metamodel(case: case_format.Case) -> Metamodel:
    """Ingest the case's model descriptor into a :class:`Metamodel`."""
    model_ref = case.document.get("model")
    if not isinstance(model_ref, str):
        raise EngineError(f"{case.path.name}: `model` must be a string path")
    root = case_format.find_repo_root()
    model_path = root / "core" / "compatibility" / model_ref
    return models.load_model(model_path)


def _read_target_and_operation(case: case_format.Case) -> tuple[str, object]:
    when = case.document.get("when")
    if not isinstance(when, Mapping):
        raise EngineError(f"{case.path.name}: read case has no `when`")
    body = cast("Mapping[str, object]", when)
    target = body.get("targetEntity")
    if not isinstance(target, str):
        raise EngineError(f"{case.path.name}: read case has no `targetEntity`")
    if "operation" not in body:
        raise EngineError(f"{case.path.name}: read case has no `operation`")
    return target, body["operation"]


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


def _canonicalize_read(operation_doc: object, entity: Entity, meta: Metamodel) -> Operation:
    """Deserialize + canonicalize one read: root as-of injection, then per-hop
    navigation canonicalization — the composition-at-the-engine order every read
    compile site shares (M2 precedent, restated for navigation, COR-3 Phase 7
    increment 3).

    Temporal reads are lowered by ``m-temporal-read`` (the auto-injected as-of
    predicate, defaulted-latest on omitted axes) BEFORE ``m-sql`` compiles the
    resulting plain predicate: the module DAG forbids ``m-sql`` from importing
    ``m-temporal-read``, so this composition site (the conformance engine, which
    may reference both) is the canonicalize step. ``inject_as_of`` is a strict
    identity for a non-temporal target. ``entity`` resolves through
    `inheritance.declaring_entity` first: an inheritance participant's as-of
    axes are declared on the family root alone (`m-inheritance`), so a
    concrete- or abstract-subtype-target read's own record carries none of its
    own — the root's axes are what ``inject_as_of`` must see.
    ``parallax.core.navigate.canonicalize`` runs immediately after: it resolves
    the root's own pinned per-axis instant (``resolve_pinned_instants``, read
    from the SAME raw operation) and injects the matching per-hop as-of
    predicate into every ``navigate`` / ``exists`` / ``notExists`` node the
    operation carries, however deeply nested — a strict identity when the
    operation carries no navigation node at all.
    """
    raw_op = deserialize(operation_doc)
    temporal_entity = inheritance.declaring_entity(meta, entity)
    root_pins = resolve_pinned_instants(raw_op, temporal_entity)
    injected = inject_as_of(raw_op, temporal_entity)
    return navigate.canonicalize(injected, meta, root_pins)


def _read_case_concurrency(case: case_format.Case) -> Concurrency | None:
    """A read-shape case's own unit-of-work participation mode — the
    read-shape half of the `when.uow` threading COR-3 Phase 8 increment 6
    adds (no previously reachable read case ever carried it, so no other read
    case's derivation changes).

    `when.uow.concurrency` when the case declares it (the read-lock matrix's
    -002/-003/-005, `api-conformance`-lane; any future transactional read
    case that self-describes its mode the same way). The `m-read-lock`
    corpus family's OWN harness-lane witnesses (-001/-009) declare no
    `when.uow` at all — their corpus prose is explicit that the read is "an
    in-transaction object find" under the module's own DEFAULT mode
    (`m-read-lock.md` "Automatic read-lock correctness": "the default
    (`locking`) in-transaction object find acquires a shared row lock") — so
    a read case whose PRIMARY module is `m-read-lock` defaults to `locking`
    absent an explicit `when.uow`, the one module-scoped default this seam
    grants (no other read case's primary module carries this default:
    every other reachable read models the plain, non-transactional
    `db.find` surface, `None`).
    """
    when = case.document.get("when")
    uow = cast("Mapping[str, object]", when).get("uow") if isinstance(when, Mapping) else None
    if isinstance(uow, Mapping):
        concurrency = cast("Mapping[str, object]", uow).get("concurrency")
        if concurrency in ("locking", "optimistic"):
            return concurrency
    if case.primary_module == "m-read-lock":
        return "locking"
    return None


def _compile_statement(case: case_format.Case, dialect_name: str) -> CompiledRead:
    if case.shape != "read":
        raise EngineError(
            f"{case.path.name}: only `read`-shape compile is implemented (a write/rejected/"
            f"scenario case compiles through its own dedicated lane; shape={case.shape})"
        )
    target, operation_doc = _read_target_and_operation(case)
    meta = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    lock = read_lock.mode_for(_read_case_concurrency(case))
    try:
        operation = _canonicalize_read(operation_doc, meta.entity(target), meta)
        return compile_read(
            operation, meta, dialect, target, result_form=_result_form(case), lock=lock
        )
    except (OperationError, SqlGenError, TemporalReadError, KeyError) as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc


def compile_read_case(case: case_format.Case, dialect_name: str) -> tuple[list[Emission], int]:
    """Compile a read case to its ordered emissions and round-trip count."""
    statement = _compile_statement(case, dialect_name).statement
    emission = Emission("/operation", statement.sql, statement.binds)
    return [emission], 1


def run_read_case(
    case: case_format.Case, dialect_name: str, port: DbPort
) -> tuple[list[Emission], list[Row], int]:
    """Execute a read case through ``port`` and record its emissions and observed rows.

    The adapter returns **managed** Python values (``Decimal``, ``datetime``,
    ``UUID``, ``bytes``, …); the conformance harness grades in **wire space**, so
    each observed row is rendered to canonical wire form here — the grader-side
    serialization the ``m-db-port`` boundary fixes, keeping the adapter free of any
    wire/grading logic and the observation envelope JSON-serializable.

    An **abstract-target** inheritance read (m-case-format / m-sql resolved Q6)
    additionally materializes `familyVariant` into each wire row through the
    compiled read's own `~parallax.core.sql_gen.CompiledRead.transform_row`: a
    table-per-hierarchy read derives it from the projected raw tag column via
    the tag-metadata map (the tag column itself is popped, never left on the
    wire row); a table-per-concrete-subtype read renames its projected
    `family_variant` literal column. A concrete-target (or
    single-resolved-position TPCS) read carries neither and transforms by
    identity. The lane is therefore exactly compile -> execute -> transform:
    `m-sql` decided at COMPILE time what each row needs, so this adapter never
    re-derives it from the operation.
    """
    compiled = _compile_statement(case, dialect_name)
    statement = compiled.statement
    dialect = dialect_for(dialect_name)
    managed = port.execute(dialect.to_driver_sql(statement.sql), _driver_binds(statement.binds))
    emission = Emission("/operation", statement.sql, statement.binds)
    rows = [compiled.transform_row(wire_row(row)) for row in managed]
    return [emission], rows, 1


def _driver_binds(binds: Sequence[object]) -> list[object]:
    return list(binds)


# --------------------------------------------------------------------------- #
# Graph reads (m-deep-fetch / m-snapshot-read, COR-3 Phase 7 increment 5): the #
# production find executor (`parallax.snapshot.handle`) does EVERY level's own #
# compile/execute/materialize — no engine-local level loop. This lane only     #
# deserializes the case's operation, calls the shared executor, and renders    #
# its neutral `materialize.Node`s to the wire `graph` / `graphs` observation.  #
# --------------------------------------------------------------------------- #
def run_graph_case(
    case: case_format.Case, dialect_name: str, port: DbPort
) -> tuple[list[Emission], dict[str, list[Row]], int, list[dict[str, object]] | None]:
    """Run a single-graph deep-fetch / snapshot read, rendering its assembled
    neutral nodes to the wire `then.graph` shape (root-class-keyed) and, for a
    case declaring `then.identityChecks`, evaluating each declared reference-
    identity assertion over the ASSEMBLED (pre-truncation) graph.
    """
    target, operation_doc = _read_target_and_operation(case)
    meta = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    try:
        raw_op = deserialize(operation_doc)
        result = find(raw_op, meta, dialect, target, port)
    except (
        OperationError,
        SqlGenError,
        TemporalReadError,
        materialize.MaterializeError,
        KeyError,
    ) as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    emissions = [
        Emission("/operation", statement.sql, statement.binds)
        for statement in result.execution.statements
    ]
    graph_wire = _render_graph(target, result.nodes)
    identity_checks = _evaluate_identity_checks(case, target, result.nodes)
    return emissions, graph_wire, result.execution.round_trips, identity_checks


def run_graphs_case(
    case: case_format.Case, dialect_name: str, port: DbPort
) -> tuple[list[Emission], list[dict[str, object]], int]:
    """Run a milestone-set (`history` / `asOfRange`) snapshot read, rendering the
    executor's ordered per-milestone graphs to the wire `then.graphs` shape:
    an array of `{pin, graph}` entries, each pin keyed by declared as-of
    attribute name."""
    target, operation_doc = _read_target_and_operation(case)
    meta = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    try:
        raw_op = deserialize(operation_doc)
        result = find_history(raw_op, meta, dialect, target, port)
    except (OperationError, SqlGenError, TemporalReadError, KeyError) as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    emissions = [
        Emission("/operation", statement.sql, statement.binds)
        for statement in result.execution.statements
    ]
    graphs_wire: list[dict[str, object]] = [
        {
            "pin": {name: wire_value(instant) for name, instant in graph.pin.items()},
            "graph": _render_graph(target, graph.nodes),
        }
        for graph in result.graphs
    ]
    return emissions, graphs_wire, result.execution.round_trips


def _render_graph(target: str, nodes: Sequence[materialize.Node]) -> dict[str, list[Row]]:
    """The wire `then.graph` shape: root-class-keyed, each root row rendered
    through :func:`_render_node` (back-reference cycles truncate to a PK-only
    stub; a diamond at a non-cyclic position keeps its full value)."""
    return {target: [_render_node(node, frozenset()) for node in nodes]}


def _render_node(node: materialize.Node, visiting: frozenset[int]) -> Row:
    """Render one assembled node to wire JSON: a node whose identity is ALREADY
    on the current recursion path (a true back-reference cycle, m-case-format
    "Back-reference cycles") truncates to a PK-only stub instead of recursing
    again; every other position — including a diamond reached a second time
    from a DIFFERENT, non-ancestor position — renders its full value.
    """
    node_id = id(node)
    if node_id in visiting:
        return {column: wire_value(node.fields[column]) for column in node.pk_columns}
    nested = visiting | {node_id}
    return {key: _render_value(value, nested) for key, value in node.fields.items()}


def _render_value(value: object, visiting: frozenset[int]) -> object:
    if isinstance(value, materialize.Node):
        return _render_node(value, visiting)
    if isinstance(value, list):
        return [_render_value(item, visiting) for item in cast("list[object]", value)]
    if isinstance(value, Mapping):
        mapping = cast("Mapping[str, object]", value)
        return {key: _render_value(v, visiting) for key, v in mapping.items()}
    return wire_value(value)


def _evaluate_identity_checks(
    case: case_format.Case, target: str, nodes: Sequence[materialize.Node]
) -> list[dict[str, object]] | None:
    """The case's declared `then.identityChecks` (m-case-format / m-conformance-
    adapter), each evaluated as Python reference identity (`is`) over the
    ASSEMBLED graph — resolved by walking the SAME JSON-Pointer path the case
    declares, against the neutral nodes directly (never the truncated wire
    JSON, so a stubbed cycle position still resolves to its real referent).
    Returns ``None`` when the case declares no identityChecks at all.
    """
    then = case.document.get("then")
    declared = (
        cast("Mapping[str, object]", then).get("identityChecks")
        if isinstance(then, Mapping)
        else None
    )
    if not declared:
        return None
    root_map = {target: nodes}
    results: list[dict[str, object]] = []
    for check in cast("list[Mapping[str, object]]", declared):
        left = _resolve_graph_pointer(case, root_map, cast("str", check["left"]))
        right = _resolve_graph_pointer(case, root_map, cast("str", check["right"]))
        results.append({"left": check["left"], "right": check["right"], "same": left is right})
    return results


def _resolve_graph_pointer(
    case: case_format.Case, root_map: Mapping[str, Sequence[materialize.Node]], pointer: str
) -> materialize.Node:
    """Resolve a `/then/graph/<RootClass>/<index>/<key>/<index>/...` JSON Pointer
    against the assembled (pre-truncation) graph, alternating list-index and
    relationship-key navigation exactly as the pointer's own segments do."""
    parts = pointer.lstrip("/").split("/")
    if len(parts) < 4 or parts[0] != "then" or parts[1] != "graph":
        raise EngineError(f"{case.path.name}: identityChecks pointer {pointer!r} is malformed")
    current: object = root_map[parts[2]][int(parts[3])]
    for part in parts[4:]:
        if isinstance(current, materialize.Node):
            current = current.fields[part]
        elif isinstance(current, list):
            current = cast("list[object]", current)[int(part)]
        else:
            raise EngineError(
                f"{case.path.name}: identityChecks pointer {pointer!r} does not resolve "
                "against the assembled graph"
            )
    if not isinstance(current, materialize.Node):
        raise EngineError(
            f"{case.path.name}: identityChecks pointer {pointer!r} does not name a graph node"
        )
    return current


# --------------------------------------------------------------------------- #
# Scenario / writeSequence — the unit-of-work write lanes (m-unit-work).       #
# --------------------------------------------------------------------------- #
# A write step is one unit of work: its buffered keyed writes are planned
# (coalesce -> FK-order -> elide, ``m-unit-work``) and each surviving
# :class:`PlannedWrite` is lowered to DML by the shared
# ``snapshot.handle.lower_write`` seam — the deliberate ``m-sql`` write edge the
# conformance family may compose (the import-side DAG exemption). A **scenario** is
# a *sequence* of units of work: a write step commits (or, ``rollback: true``,
# aborts) its coalesced DML, then a ``find`` reads committed state through the read
# path. A **writeSequence** lowers each entry independently — no cross-entry
# coalescing (an insert-then-delete pair across two entries is two round trips, not
# a cancellation) — and, post the DQ4 re-route below, each entry is its OWN
# transaction (COR-3 Phase 8 increment 4 changes this from "the whole sequence in
# one transaction").
#
# COR-3 Phase 8 increment 4 (DQ4 re-route, ledger D-18): the RUN lane now executes
# every write choreography unit — a writeSequence entry, a scenario write step, a
# conflict attempt — through the SHIPPED ``db.transact`` entry point (one
# transaction per unit, ``clock=FixedClock(<entry at>)``, ADR 0010), buffered
# through the neutral ``Transaction._buffer`` route + ``UnitOfWork.observe`` (never
# the typed instance verbs, which this engine's case-driven metamodel has no
# compiled classes for). The COMPILE lane still lowers PURELY (no database,
# ``plan_flush`` / ``lower_write``) — that pure lowering is ALSO what the RUN
# lane's emissions/round-trips observation grades against, since both are the
# SAME deterministic computation over the SAME instructions/observations/instant
# (`_resolve_entries` / `_lower_resolved` below are the shared core).

# The lowering failures the write lanes convert to a neutral :class:`EngineError`,
# so the adapter reports a ``*-failed`` diagnostic rather than leaking a lower-layer
# exception type across the conformance seam. `opt_lock.UnobservedVersionError` /
# `.HistoricalObservationError` / `.CallerAuthoredVersionError` are m-opt-lock's own
# forward-error posture (COR-3 Phase 8 increment 3; the core amendment bundle adds
# the last one once the M4-era literal-version passthrough retires);
# `temporal_state.AmbiguousObservationError` is this increment's own (a shape no
# reachable case exercises). A deferred witness (the materializing / auto-retry-
# boundary forms, increments 5/6) that reaches this engine-local write path without
# a recorded observation must degrade to a reasoned `EngineError`, never an
# uncaught crash of the sweep.
_LOWERING_ERRORS: Final[tuple[type[Exception], ...]] = (
    instructions.WriteInstructionError,
    WriteLoweringError,
    inheritance.InheritanceError,
    opt_lock.UnobservedVersionError,
    opt_lock.HistoricalObservationError,
    opt_lock.CallerAuthoredVersionError,
    temporal_state.AmbiguousObservationError,
    OperationError,
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


class _RollbackStep(Exception):
    """Sentinel raised inside a transaction body to abort a ``rollback: true`` step."""


@dataclass(frozen=True, slots=True)
class _LoweredStep:
    """One lowered scenario step: its emission pointer and DML, and how to run it."""

    pointer: str
    statements: tuple[Statement, ...]
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
    """The case's declared unit-of-work participation mode (`when.uow.concurrency`;
    `m-opt-lock`), defaulting to `locking` when the case declares none — the SAME
    default `m-unit-work.TransactionSettings` resolves. Every writeSequence case
    needing a non-default mode (m-bitemp-write-008 included, since the core
    amendment bundle) self-describes via `when.uow.concurrency` — `when.uow` is
    schema-legal on writeSequence shape (`compatibility-case.schema.json`'s
    writeSequence `propertyNames` admits `uow` alongside `writeSequence`)."""
    when = case.document.get("when")
    if isinstance(when, Mapping):
        uow = cast("Mapping[str, object]", when).get("uow")
        if isinstance(uow, Mapping):
            value = cast("Mapping[str, object]", uow).get("concurrency")
            if value == "optimistic":
                return "optimistic"
    return "locking"


def _scenario_needs_lock(steps: Sequence[Mapping[str, object]], meta: Metamodel) -> bool:
    """Whether a scenario's ORDINARY (non-materializing-paired) find steps
    carry the case's declared read-lock suffix at all (`m-read-lock`: "an
    in-transaction object find that INTENDS TO WRITE acquires a shared row
    lock" — the lock protects an observation a SUBSEQUENT keyed write depends
    on). ``True`` unless EVERY write step in the scenario is a READLESS
    predicate write (`m-batch-write-005`/`-006`'s own witness, COR-3 Phase 8
    increment 5): a readless write establishes no transaction-scoped
    observation at all, so there is nothing for a lock to protect and the
    scenario's find steps are plain, non-participating verification reads. A
    scenario with no write step at all (a pure read narrative) keeps the
    lock — unaffected, since it never reaches a readless predicate write.
    """
    write_steps = [step for step in steps if "write" in step]
    if not write_steps:
        return True
    for step in write_steps:
        if not _is_predicate_write_step(step["write"]) or _is_materializing_write_step(step, meta):
            return True
    return False


def _strip_observation(row: Mapping[str, object]) -> tuple[dict[str, object], Observation | None]:
    """Strip a case writeRow's reserved ``observedVersion`` / ``observedTxStart``
    control keys (`m-opt-lock`; ADR 0013), returning the DURABLE row (never
    carrying them — the write-instruction schema forbids both,
    `instructions.deserialize` enforces it) and the :class:`Observation` they
    describe (``None`` when the row carries neither — an unobserved write, or
    one whose observation instead comes from this SAME `uow` group's own
    prior find step, consulted separately via :data:`ScenarioObservations`)."""
    clean = dict(row)
    version = clean.pop("observedVersion", None)
    tx_start = clean.pop("observedTxStart", None)
    if version is None and tx_start is None:
        return clean, None
    return clean, Observation(
        version=cast("int", version) if version is not None else None,
        tx_start=cast("str", tx_start) if tx_start is not None else None,
    )


# An object-key -> Observation map (m-opt-lock; ADR 0013) — the same neutral
# shape a REAL `Transaction.find` populates on the production path
# (`parallax.snapshot.handle` records observations into `uow.observe`).
# `_write_sequence_lowered` / `run_write_sequence_case` pass a permanently
# EMPTY instance (a writeSequence carries no find steps at all): every keyed
# write's observation there comes solely from its own row's reserved
# `observedVersion`/`observedTxStart` control keys. The scenario RUN lane
# (`_run_uow_group`) builds one FRESH instance per `uow` GROUP — never one
# spanning the whole scenario or crossing a group boundary (COR-3 Phase 8
# amendment-review remediation retires the prior scenario-wide map); the
# scenario COMPILE lane (`_scenario_lowered`) never populates one at all, so
# no compile path ever consults a query result (`m-conformance-adapter`
# "Compile eligibility"). Reladomo prior art (semantics, not idioms): the
# transaction records the version at read time ("the shadow value read
# earlier") and threads it into the UPDATE bind
# (`docs/research/reladomo/09-transactions-locking.md:55-59`).
ScenarioObservations = dict[ObjectKey, Observation]


def _versioned_non_temporal_version_attribute(
    meta: Metamodel, entity_name: str
) -> Attribute | None:
    """``entity_name``'s own optimistic-lock version ATTRIBUTE, when it is a
    VERSIONED, NON-TEMPORAL entity (`m-opt-lock`) — ``None`` otherwise (a
    temporal entity's observation flows through :class:`TemporalShadow`
    instead, never this map; `_build_temporal_instruction`). Resolved through
    the FAMILY-declaring entity (`inheritance.declaring_entity`): the version
    column is family-wide metadata declared only on the root
    (`m-opt-lock` "The version column")."""
    declaring = inheritance.declaring_entity(meta, meta.entity(entity_name))
    if declaring.is_temporal:
        return None
    return next((attr for attr in declaring.attributes if attr.optimistic_locking), None)


def _row_object_key(
    meta: Metamodel, entity_name: str, row: Mapping[str, object], *, by_column: bool
) -> ObjectKey | None:
    """The SAME identity :func:`~parallax.core.unit_work.object_key` computes for
    a keyed write, derived from a raw FOUND row instead (a scenario find
    step's own ``expectRows`` entry, or a real ``port.execute`` row) — so a
    later write's own key lookup against :data:`ScenarioObservations` matches.

    ``by_column`` selects the row's own field-naming convention: the compile
    lane's authored ``expectRows`` are ATTRIBUTE-named (`m-case-format`'s flat
    attribute-named row vocabulary); the run lane's real ``port.execute`` rows
    are COLUMN-named (the raw driver row — the SAME convention
    `parallax.snapshot.handle`'s own observation recording reads via
    ``node.fields[attr.column]``). ``None`` when the (family-effective)
    primary key is absent from ``row`` — never reachable for a well-formed
    corpus find, but this seam takes no data on faith."""
    entity = meta.entity(entity_name)
    pk_attrs = inheritance.family_primary_key(meta, entity)
    if not pk_attrs:  # pragma: no cover - defends a malformed model
        return None
    pairs: list[tuple[str, object]] = []
    for attr in pk_attrs:
        field = attr.column if by_column else attr.name
        if field not in row:  # pragma: no cover - defends a malformed row/projection
            return None
        pairs.append((attr.name, row[field]))
    return (entity_name, tuple(pairs))


def _observe_group_find(
    tx: handle.Transaction,
    observations: ScenarioObservations,
    meta: Metamodel,
    entity_name: str,
    rows: Sequence[Mapping[str, object]],
) -> None:
    """Record a `uow` GROUP's own OBSERVED version for every row a grouped
    find step returns, when its target is a VERSIONED NON-TEMPORAL entity —
    into BOTH the group-local :data:`ScenarioObservations` map (this SAME
    group's own pure re-lowering oracle, :func:`_lower_resolved` via
    :func:`_run_uow_group`) and the REAL transaction's own unit of work
    (``tx._uow.observe`` — the same neutral seam :func:`_execute_write_unit`
    pokes at, mirroring the production path a real ``Transaction.find``
    builds, where `parallax.snapshot.handle` records observations into
    `uow.observe`) (COR-3 Phase 8 amendment-review remediation), so a later
    keyed write of the SAME object in this SAME group derives its version
    bind from a genuine transaction-scoped observation — never an oracle,
    never a scenario-wide map. Rows are always COLUMN-named here (the real
    ``port.execute`` row shape — the SAME convention
    `parallax.snapshot.handle`'s own observation recording reads via
    ``node.fields[attr.column]``); the scenario compile lane never calls this
    at all. A no-op for a temporal or unversioned target
    (:func:`_versioned_non_temporal_version_attribute` returns ``None``) and
    for any row missing its primary key or version field — never reachable
    for a well-formed corpus find, but this seam takes no data on faith."""
    version_attr = _versioned_non_temporal_version_attribute(meta, entity_name)
    if version_attr is None:
        return
    for row in rows:
        key = _row_object_key(meta, entity_name, row, by_column=True)
        if key is None or version_attr.column not in row:
            continue
        observation = Observation(version=cast("int", row[version_attr.column]))
        observations[key] = observation
        tx._uow.observe(key, observation)  # pyright: ignore[reportPrivateUsage]


def _entry_instant(entry: Mapping[str, object]) -> str:
    """The tx_instant an entry's OWN choreography unit (transaction) runs at
    (m-txtime-write / m-bitemp-write ``at``; ADR 0010: the Clock, never a
    per-operation override). A non-temporal entry names none — its Clock
    value is inert, so :data:`_INERT_CLOCK_INSTANT` stands in."""
    at = entry.get("at")
    return at if isinstance(at, str) else _INERT_CLOCK_INSTANT


def _is_temporal_entity(meta: Metamodel, entity_name: str) -> bool:
    return inheritance.declaring_entity(meta, meta.entity(entity_name)).is_temporal


_TEMPORAL_INSERT_MUTATIONS: Final[frozenset[str]] = frozenset({"insert", "insertUntil"})


def _build_temporal_instruction(
    entry: Mapping[str, object],
    meta: Metamodel,
    shadow: TemporalShadow,
    tx_instant: str,
    unit_inserted: set[ObjectKey],
) -> tuple[WriteInstruction, ObjectKey | None, Observation | None]:
    """One TEMPORAL writeSequence/scenario entry -> its canonical keyed
    instruction plus the shadow-tracked observation its close/chain consumes
    (`m-txtime-write` / `m-bitemp-write` "the engine supplies observed rows
    from case state" — never an implicit resolving read).

    The corpus and canonical instruction share the same ``validFrom`` / ``until``
    spelling. Bounds are instruction-level fields; temporal row payloads never
    carry authoring aliases. Every temporal entry this increment reaches is
    single-row.

    ``unit_inserted`` is the SAME choreography unit's own running set of
    (entity, pk) pairs a PRIOR entry in this SAME buffer already inserted
    (`m-unit-work` same-transaction coalescing, `m-txtime-write-008` /
    `m-bitemp-write-014`): a later entry targeting one of them is a
    same-buffer coalescing candidate whose OWN close/chain arithmetic never
    runs (the planner folds it into the pending insert before `lower_write`
    ever sees it) — its observation is forced to `None` and the shadow tracker
    is left untouched (advanced once, by the insert, which is what the
    eventual coalesced write's tracked state approximates; no reachable case
    observes this pk again within the same unit after coalescing).
    """
    mutation = cast("str", entry["mutation"])
    entity_name = cast("str", entry["entity"])
    raw_rows = cast("Sequence[Mapping[str, object]]", entry["rows"])
    row = dict(raw_rows[0])
    valid_from = cast("str | None", entry.get("validFrom"))
    until = cast("str | None", entry.get("until"))
    doc: dict[str, object] = {"mutation": mutation, "entity": entity_name, "rows": [row]}
    if valid_from is not None:
        doc["validFrom"] = valid_from
    if until is not None:
        doc["until"] = until
    instruction = instructions.deserialize(doc)
    instructions.validate_instruction(instruction, meta)
    assert isinstance(instruction, KeyedWrite)  # a temporal entry is always keyed
    pk_key = object_key(instruction, meta)
    is_insert = mutation in _TEMPORAL_INSERT_MUTATIONS
    is_coalescing_candidate = not is_insert and pk_key is not None and pk_key in unit_inserted
    observation: Observation | None = None
    if not is_insert and not is_coalescing_candidate:
        observation = shadow.resolve(meta, entity_name, row)
    key = pk_key if observation is not None else None
    if is_insert or (observation is not None and not is_coalescing_candidate):
        shadow.advance(meta, entity_name, instruction, tx_instant, observation)
    if is_insert and pk_key is not None:
        unit_inserted.add(pk_key)
    return instruction, key, observation


_OBSERVATION_CONTROL_KEYS: Final[frozenset[str]] = frozenset({"observedVersion", "observedTxStart"})


def _is_predicate_write_step(raw_write: object) -> bool:
    """Whether a scenario write step's own ``write`` field is a single
    STRUCTURED PREDICATE-write instruction (`mutation` / `target` / optional
    `assignments` — `m-case-format`'s predicate-selected shape, e.g.
    ``m-batch-write-005``) rather than the keyed-write entry LIST
    (`m-case-format`'s buffered-keyed-write shape) this engine's keyed path
    lowers. A predicate write's `target` names its entity/predicate; a keyed
    write is a plain list of ``{mutation, entity, rows}`` entries — the SHAPE
    signal (a bare mapping vs. a list) is structural, never inferred from a
    ``KeyError`` (the reachability gap the Phase-8 mid-phase review's finding
    E first closed; COR-3 Phase 8 increment 5 retires the refusal it left
    behind and routes this shape to the readless/materializing predicate-write
    translation instead — see :func:`_lower_predicate_write_step` /
    :func:`_run_materializing_pair`).
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


def _is_versioned_entity(meta: Metamodel, entity_name: str) -> bool:
    declaring = inheritance.declaring_entity(meta, meta.entity(entity_name))
    return any(attr.optimistic_locking for attr in declaring.attributes)


def _rows_carry_observation_keys(raw_rows: Sequence[Mapping[str, object]]) -> bool:
    return any(_OBSERVATION_CONTROL_KEYS & row.keys() for row in raw_rows)


def _decomposes_per_row(
    meta: Metamodel, entity_name: str, mutation: str, raw_rows: Sequence[Mapping[str, object]]
) -> bool:
    """Whether a non-temporal write entry's rows decompose into independent
    single-row instructions (mirroring what that many separate
    `Transaction.insert`/`.update`/`.delete` calls would buffer) rather than
    collapsing into ONE multi-row instruction — the INVERSE of
    :func:`~parallax.core.batch_write.collapses`, the injected `m-batch-write`
    collapse-eligibility vocabulary (COR-3 Phase 8 increment 5) both this
    engine and the composition layer's own planner collapse stage
    (:func:`_lower_resolved`, `parallax.snapshot.handle.Database.transact`)
    consult identically, so the engine's PRE-collapsed multi-row instruction
    construction below and the PLANNER's own collapse stage can never
    disagree on eligibility.

    Derived SEMANTICALLY from the instruction and model — mutation kind,
    versioned-ness, presence of per-row observations, and computed/allocated
    primary keys — never from the case's own authored ``statements`` count,
    which is a count-consistency ASSERTION only (`compatibility-case.schema.
    json`), never a semantics discriminator (a prior review finding closed
    this; ``_check_statement_count_consistency`` stays the assertion-only
    verifier):

    - a single row is always its own instruction (no ambiguity);
    - any row authoring a reserved ``observedVersion``/``observedTxStart`` control
      key is an explicit per-row-observation signal (`m-opt-lock`; ADR 0013) —
      an ENGINE-specific pre-check `batch_write.collapses` itself does not
      make (it has no case-authoring concept), covering insert/delete too
      (`batch_write.update_collapses` already makes the SAME check for update);
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
    if _rows_carry_observation_keys(raw_rows):
        return True
    return not batch_write.collapses(meta, entity_name, mutation, raw_rows)


def _check_statement_count_consistency(entry: Mapping[str, object], decomposed_count: int) -> None:
    """``statements`` is a count-CONSISTENCY assertion the schema intends
    (`compatibility-case.schema.json`), never a semantics discriminator — verify
    the entry's OWN authored count against this seam's independently DERIVED
    instruction count and fail loudly on a mismatch (an authoring error),
    rather than silently trusting either number.
    """
    declared = entry.get("statements")
    if declared is not None and declared != decomposed_count:
        raise EngineError(
            f"{entry.get('entity')!r} {entry.get('mutation')!r}: authored `statements: "
            f"{declared!r}` does not match the {decomposed_count} instruction(s) this entry "
            "decomposes into (m-case-format: `statements` is a count-consistency assertion, "
            "not a semantics discriminator)"
        )


def _seed_insert_version(
    meta: Metamodel, entity_name: str, mutation: str, row: Mapping[str, object]
) -> dict[str, object]:
    """A VERSIONED, non-temporal entity's INSERT row, with the derived initial
    version seeded when the case-authored row omits it
    (`opt_lock.INITIAL_VERSION`) — a no-op for every other mutation/entity/row
    shape.

    `parallax.snapshot.handle`'s `lower_insert` / `lower_multi_insert`, the
    keyed builders `lower_write` dispatches to, derive the
    INITIAL version at the version column's own columnOrder position
    UNCONDITIONALLY, "ignoring any row-carried value" (their own docstrings)
    — every reachable insert witness already authors an explicit `version`
    matching this SAME constant (`m-unit-work-001`/`-008`), coincidentally
    satisfying `~parallax.core.unit_work.write_validate.validate_write`'s
    required-attribute check along the way, but a same-transaction coalescing
    pair whose insert never survives to ANY golden DML
    (`m-unit-work-010`'s insert-then-delete cancellation) has no golden bind
    to match and so may omit it. The RUN lane's own translation
    (`_execute_write_unit`, mirroring "as many separate `Transaction.insert`
    calls") buffers through `Transaction._buffer`, which DOES run
    `validate_write` (the COMPILE lane's `_lower_resolved` never does) — so
    only the run lane needs this seed; since the framework discards whatever
    the row carries at lowering regardless, seeding the identical constant
    here changes no compiled emission.
    """
    if mutation != "insert":
        return dict(row)
    version_attr = _versioned_non_temporal_version_attribute(meta, entity_name)
    if version_attr is None or version_attr.name in row:
        return dict(row)
    return {**row, version_attr.name: opt_lock.INITIAL_VERSION}


def _build_instructions(
    entry: Mapping[str, object],
    meta: Metamodel,
    shadow: TemporalShadow,
    tx_instant: str,
    unit_inserted: set[ObjectKey],
    scenario_observations: ScenarioObservations,
) -> list[tuple[WriteInstruction, ObjectKey | None, Observation | None]]:
    """One case write entry -> one or more canonical keyed write instructions.

    A STRUCTURED PREDICATE-write entry (`target`/`predicate` shaped, no
    `entity` key at all) refuses loudly here too — defensive coverage for the
    writeSequence path, which shares this function with every scenario write
    entry (the scenario `write`-field-is-itself-a-mapping shape is caught one
    layer up, by :func:`_is_predicate_write_step`, and routed to the
    readless/materializing predicate-write translation instead — a predicate
    write is never a legal writeSequence entry shape, `m-case-format`'s
    writeSequence vocabulary is keyed-only).

    A TEMPORAL entity's entry dispatches to :func:`_build_temporal_instruction`
    (COR-3 Phase 8 increment 4): its authored ``statements`` count is the DML
    STATEMENT count (a close plus zero-to-three chained opens), a DIFFERENT
    accounting from the row-decomposition below, which assumes non-temporal
    semantics and is never applied to a temporal entry's entry.

    Otherwise, a write entry carries the instruction triple (``mutation`` /
    ``entity`` / ``rows``) beside case-authoring keys (``note`` / ``statements``
    / ``roundTrips`` / ``rollback``). ``rows`` MAY batch several logical
    per-object writes into one entry (the write-instruction schema's "one or
    more rows" vocabulary); :func:`_decomposes_per_row` derives SEMANTICALLY
    whether they decompose into N independent single-row instructions (each
    stripping its own reserved observation control keys into an
    :class:`Observation`, keyed by that row's OWN object key — `m-opt-lock`;
    ADR 0013) or stay ONE multi-row instruction (reaching `lower_write`'s own
    multi-row refusal, the honest increment-5 collapse deferral). A row whose
    own control keys yield NO observation falls back to
    ``scenario_observations`` — a writeSequence's own permanently-empty
    instance, or (the scenario RUN lane only) a `uow` GROUP's own prior find
    step(s) (:func:`_observe_group_find`, via :func:`_run_uow_group`), keyed
    consistently with :func:`~parallax.core.unit_work.object_key` — mirroring
    how a temporal entry falls back to :meth:`TemporalShadow.resolve` above.
    :func:`_check_statement_count_consistency` then verifies the entry's own
    authored ``statements`` count agrees, independently of that decision.
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
    if _is_temporal_entity(meta, entity_name):
        return [_build_temporal_instruction(entry, meta, shadow, tx_instant, unit_inserted)]
    mutation = cast("str", entry["mutation"])
    raw_rows = cast("Sequence[Mapping[str, object]]", entry["rows"])
    if not _decomposes_per_row(meta, entity_name, mutation, raw_rows):
        _check_statement_count_consistency(entry, 1)
        clean_rows = [
            _seed_insert_version(meta, entity_name, mutation, _strip_observation(raw_row)[0])
            for raw_row in raw_rows
        ]
        instruction = instructions.deserialize(
            {"mutation": mutation, "entity": entity_name, "rows": clean_rows}
        )
        instructions.validate_instruction(instruction, meta)
        return [(instruction, None, None)]
    _check_statement_count_consistency(entry, len(raw_rows))
    out: list[tuple[WriteInstruction, ObjectKey | None, Observation | None]] = []
    for raw_row in raw_rows:
        clean_row, observation = _strip_observation(raw_row)
        clean_row = _seed_insert_version(meta, entity_name, mutation, clean_row)
        instruction = instructions.deserialize(
            {"mutation": mutation, "entity": entity_name, "rows": [clean_row]}
        )
        instructions.validate_instruction(instruction, meta)
        key = object_key(instruction, meta)
        if observation is None and key is not None:
            observation = scenario_observations.get(key)
        if observation is None:
            key = None
        out.append((instruction, key, observation))
    return out


def _resolve_entries(
    entries: Sequence[Mapping[str, object]],
    meta: Metamodel,
    shadow: TemporalShadow,
    tx_instant: str,
    scenario_observations: ScenarioObservations,
) -> list[tuple[WriteInstruction, ObjectKey | None, Observation | None]]:
    """Every entry in one choreography unit's buffer -> its resolved
    instructions (advancing ``shadow`` exactly once per temporal instruction) —
    the shared core both the PURE lowering (:func:`_lower_resolved`) and the
    RUN lane's real `db.transact` execution (:func:`_execute_write_unit`)
    consume, so a temporal write's observation is never resolved (or the
    tracker advanced) twice for one unit. ``unit_inserted`` tracks this SAME
    buffer's own same-transaction coalescing candidates (see
    :func:`_build_temporal_instruction`) across the whole unit.
    ``scenario_observations`` is READ-ONLY here — an always-empty map for a
    writeSequence entry or an ungrouped scenario write step (neither ever
    consults a find-derived observation), or (the scenario RUN lane only) a
    `uow` GROUP's own find-derived map (:func:`_run_uow_group`), populated by
    that SAME group's find steps that ran before this unit — never one
    spanning the whole scenario."""
    resolved: list[tuple[WriteInstruction, ObjectKey | None, Observation | None]] = []
    unit_inserted: set[ObjectKey] = set()
    for entry in entries:
        resolved.extend(
            _build_instructions(
                entry, meta, shadow, tx_instant, unit_inserted, scenario_observations
            )
        )
    return resolved


def _lower_resolved(
    resolved: Sequence[tuple[WriteInstruction, ObjectKey | None, Observation | None]],
    meta: Metamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    tx_instant: str,
) -> tuple[Statement, ...]:
    """Plan one write buffer (coalesce / collapse / FK-order / elide) and lower
    each survivor — PURE, no database. ``collapse=batch_write.collapses`` is
    injected identically to the composition layer's own production wiring
    (`parallax.snapshot.handle.Database.transact`, COR-3 Phase 8 increment 5) —
    a case's own PRE-collapsed multi-row entry (`_decomposes_per_row`'s "not
    decomposes" branch) reaches the planner already merged, so the collapse
    stage is a no-op for it; a case entry the engine decomposed per row instead
    (`m-batch-write-002`'s non-uniform shape) never re-collapses either, since
    `batch_write.collapses` answers the SAME eligibility question either way.
    """
    buffer = [instruction for instruction, _key, _observation in resolved]
    observations: dict[ObjectKey, Observation] = {
        key: observation
        for _instruction, key, observation in resolved
        if key is not None and observation is not None
    }
    plan = plan_flush(buffer, observations, tx_instant, meta, collapse=batch_write.collapses)
    statements: list[Statement] = []
    for planned in plan.writes:
        statements.extend(
            lowered.statement
            for lowered in lower_write(planned, meta, dialect, concurrency, tx_instant)
        )
    return tuple(statements)


def _lower_writes(
    entries: Sequence[Mapping[str, object]],
    meta: Metamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    shadow: TemporalShadow,
    tx_instant: str,
    scenario_observations: ScenarioObservations,
) -> tuple[Statement, ...]:
    """Resolve and PURE-lower one write buffer — the COMPILE lane's own
    lowering, and the RUN lane's emissions/round-trips oracle (`_execute_write_unit`
    resolves its own entries via :func:`_resolve_entries` and reuses
    :func:`_lower_resolved` directly, rather than calling this a second time, so
    the shadow tracker advances exactly once per entry)."""
    resolved = _resolve_entries(entries, meta, shadow, tx_instant, scenario_observations)
    return _lower_resolved(resolved, meta, dialect, concurrency, tx_instant)


def _lower_predicate_write_step(
    raw_write: Mapping[str, object], meta: Metamodel, dialect: Dialect, concurrency: Concurrency
) -> Statement:
    """Lower a READLESS scenario predicate-write step (`m-batch-write-005`/
    ``-006``) to its ONE statement — PURE, no database. Deserializes +
    validates the canonical instruction, then reuses the SAME
    ``plan_flush`` -> ``lower_write`` seam every other write path does
    (`collapse=batch_write.collapses` injected identically, though the
    collapse stage is a structural no-op for a lone predicate write).

    A MATERIALIZING predicate write never reaches here: its case carries
    ``compileEligibility: run-only``, which short-circuits at
    :func:`eligibility` before the compile lane ever calls this — reaching
    ``lower_write`` with one is therefore always a caller wiring defect,
    surfaced as ``lower_write``'s own defensive :class:`WriteLoweringError`.
    """
    instruction = instructions.deserialize(_canonical_predicate_doc(raw_write))
    assert isinstance(instruction, PredicateWrite)  # a predicate-shaped step always builds this
    instructions.validate_instruction(instruction, meta)
    plan = plan_flush([instruction], {}, None, meta, collapse=batch_write.collapses)
    statements = [
        lowered.statement
        for planned in plan.writes
        for lowered in lower_write(planned, meta, dialect, concurrency, None)
    ]
    assert len(statements) == 1  # a readless predicate write is always exactly one statement
    return statements[0]


def _lower_find(
    step: Mapping[str, object],
    meta: Metamodel,
    dialect: Dialect,
    concurrency: Concurrency | None,
    *,
    result_form: Literal["row", "instance"] = "instance",
) -> Statement:
    """Compile a scenario ``find`` step through the read path with the read-lock suffix.

    A scenario find is an in-transaction object find; ``concurrency`` (the case's
    own ``when.uow.concurrency``) decides the ``m-sql`` shared-row-lock suffix
    (``for share of t0``) exactly as the production `Transaction.find` derives it
    from ``self._uow.settings.concurrency``: ``locking`` renders it after every
    clause; ``optimistic`` renders none (an optimistic-mode read takes no lock —
    the `m-txtime-write-008` / `m-bitemp-write-014` coalescing witnesses exercise
    this OPTIMISTIC branch). ``None`` ALSO renders none — the caller's own
    :func:`_scenario_needs_lock` gate: a scenario whose write steps are ALL
    readless predicate writes (`m-batch-write-005`/`-006`) establishes no
    transaction-scoped observation at all (`m-read-lock` "an in-transaction
    object find that intends to write acquires a shared row lock" — a readless
    write intends nothing an observation could ever protect), so its find
    steps are plain, non-participating verification reads.

    ``result_form`` defaults to ``instance`` — an ORDINARY (managed) scenario
    find mirrors production ``Transaction.find`` (`m-sql` *Read projection*,
    slot 4 included); for a value-object-free entity row-form and instance-form
    are byte-identical, so the default only matters to VO-bearing targets.
    A materializing predicate write's OWN internal resolving read is ROW-form
    (`m-value-object-047` pins the VO-omission contrast) but is compiled by
    the materializing predicate-write resolve in `parallax.snapshot.handle`
    directly, never through this function — the RUN lane reports its ACTUAL
    executed SQL via a capturing port
    (:func:`_run_materializing_pair`), not a separate pure re-lowering (its
    binds are query-result-dependent, so no pure oracle exists to compute them
    from).

    This composition — `compile_read` + `read_lock.mode_for`, mirroring
    `Transaction.find`'s own derivation — is IRREDUCIBLE adapter content, not
    a residual "mirrors production" gap to close. The case-driven engine has
    no typed Python entity classes at all (a scenario step is a raw,
    case-authored dict naming `targetEntity` + a serialized operation), so
    there is no `Statement` to hand a production seam — `Transaction.find`
    itself REQUIRES one. Re-routing through a production API would mean
    inventing a new one solely to serve this untyped input, the opposite of
    engine-thinning; this function stays the adapter's own translation from
    "raw case step" to "compiled Statement", composing production's `m-sql` /
    `m-read-lock` building blocks rather than duplicating their logic.
    """
    target = step.get("targetEntity")
    find_doc = step.get("find")
    if not isinstance(target, str) or find_doc is None:
        raise EngineError("scenario find step needs `targetEntity` and `find`")
    operation = _canonicalize_read(find_doc, meta.entity(target), meta)
    lock = read_lock.mode_for(concurrency)
    # A scenario find's emission is graded on SQL text and binds alone — the
    # compiled read's row transform belongs to whoever consumes the rows, and a
    # scenario find step's rows are consumed by the production find executor.
    return compile_read(
        operation, meta, dialect, target, result_form=result_form, lock=lock
    ).statement


def _scenario_lowered(case: case_format.Case, dialect_name: str) -> list[_LoweredStep]:
    """Lower every scenario step to its pointer + DML — pure (no database).

    One :class:`TemporalShadow` spans the whole scenario (COR-3 Phase 8
    increment 4): a later write step's temporal close/chain observes an
    earlier step's own opened milestone(s), never the database. The compile
    lane consults NO find-derived observation (COR-3 Phase 8 amendment-review
    remediation): a keyed write whose version bind is the framework-owned
    advance of a version this SAME scenario's own observing find returned is
    query-result-dependent (`m-conformance-adapter` "Compile eligibility") and
    is therefore declared `compileEligibility: run-only` in the corpus, so it
    short-circuits at :func:`eligibility` before this function ever runs
    (`adapter.compile_case`). :data:`ScenarioObservations` stays permanently
    empty here — every keyed write this lane reaches resolves its observation
    from its OWN row's reserved ``observedVersion``/``observedTxStart`` control
    keys only (:func:`_strip_observation`), exactly as a writeSequence entry
    does.
    """
    meta = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    concurrency = _concurrency(case)
    shadow = TemporalShadow()
    scenario_observations: ScenarioObservations = {}
    lowered: list[_LoweredStep] = []
    try:
        steps = _scenario_steps(case)
        find_lock = concurrency if _scenario_needs_lock(steps, meta) else None
        for index, step in enumerate(steps):
            if "write" in step:
                raw_write = step["write"]
                rollback = step.get("rollback") is True
                if _is_predicate_write_step(raw_write):
                    # Readless only (`m-batch-write-005`/`-006`) — a
                    # materializing predicate write never reaches the compile
                    # lane at all (its case's `compileEligibility: run-only`
                    # short-circuits before `_scenario_lowered` ever runs).
                    statement = _lower_predicate_write_step(
                        cast("Mapping[str, object]", raw_write), meta, dialect, concurrency
                    )
                    lowered.append(
                        _LoweredStep(f"/scenario/{index}/write", (statement,), True, rollback)
                    )
                else:
                    entries = _write_entries(raw_write)
                    tx_instant = _entry_instant(entries[0])
                    statements = _lower_writes(
                        entries,
                        meta,
                        dialect,
                        concurrency,
                        shadow,
                        tx_instant,
                        scenario_observations,
                    )
                    lowered.append(
                        _LoweredStep(f"/scenario/{index}/write", statements, True, rollback)
                    )
            else:
                statement = _lower_find(step, meta, dialect, find_lock)
                lowered.append(_LoweredStep(f"/scenario/{index}/find", (statement,), False, False))
    except _LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    return lowered


def _write_sequence_lowered(
    case: case_format.Case, dialect_name: str
) -> list[tuple[str, tuple[Statement, ...]]]:
    """Lower each writeSequence entry independently to ``(pointer, statements)`` —
    pure. One :class:`TemporalShadow` spans the whole sequence (COR-3 Phase 8
    increment 4): a later entry's temporal close/chain observes an earlier
    entry's own opened milestone(s), never the database. A writeSequence
    carries no find steps at all (`m-case-format`), so its own
    :data:`ScenarioObservations` map stays permanently empty — every keyed
    write's observation still comes from its row's own ``observedVersion`` /
    ``observedTxStart`` control keys."""
    meta = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    concurrency = _concurrency(case)
    shadow = TemporalShadow()
    scenario_observations: ScenarioObservations = {}
    try:
        return [
            (
                f"/writeSequence/{index}",
                _lower_writes(
                    [entry],
                    meta,
                    dialect,
                    concurrency,
                    shadow,
                    _entry_instant(entry),
                    scenario_observations,
                ),
            )
            for index, entry in enumerate(_write_sequence_entries(case))
        ]
    except _LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc


def _emissions(pointer_statements: Sequence[tuple[str, Sequence[Statement]]]) -> list[Emission]:
    return [
        Emission(pointer, statement.sql, statement.binds)
        for pointer, statements in pointer_statements
        for statement in statements
    ]


def _has_action_step(steps: Sequence[Mapping[str, object]]) -> bool:
    """Whether a scenario carries at least one lifecycle **action** step
    (m-case-format "Lifecycle action steps") — the snapshot-read scenario shape
    (`mutate`) this module lowers/runs through a SEPARATE path from the keyed
    unit-of-work M4 scenarios (`write` / `find` steps only), never mixed."""
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
    meta = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    emissions: list[Emission] = []
    try:
        for index, step in enumerate(steps):
            if "action" in step:
                _check_action_step(case, step)
                continue
            target = step.get("targetEntity")
            find_doc = step.get("find")
            if not isinstance(target, str) or find_doc is None:
                raise EngineError(
                    f"{case.path.name}: scenario find step needs `targetEntity` and `find`"
                )
            operation = _canonicalize_read(find_doc, meta.entity(target), meta)
            statement = compile_read(
                operation, meta, dialect, target, result_form="instance"
            ).statement
            emissions.append(Emission(f"/scenario/{index}/find", statement.sql, statement.binds))
    except (OperationError, SqlGenError, TemporalReadError, KeyError) as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    return emissions, len(emissions)


def _run_snapshot_scenario(
    case: case_format.Case,
    dialect_name: str,
    port: DbPort,
    steps: Sequence[Mapping[str, object]],
) -> tuple[list[Emission], int, list[dict[str, object]]]:
    """Run a snapshot-read scenario: each find step materializes fresh neutral
    nodes through the SAME production find executor every graph read uses (no
    engine-local level loop); `mutate` runs the production write seam's
    finite-Transaction-Time-pin refusal against the referenced find step's own
    statement pin (:func:`_grade_mutate_step`) and, when accepted, applies its
    `set` directly to that step's own materialized node — a plain in-memory
    field update, zero round trips, nothing at the port (m-snapshot-read
    closed world: a snapshot node is never enrolled in a unit of work, so
    mutating it can never write back). Returns the ordered emissions, the
    total round trips, and one `errors` observation entry per `expectError`
    step whose verb raised its declared application-lifecycle error
    (`m-conformance-adapter`)."""
    meta = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    emissions: list[Emission] = []
    round_trips = 0
    results: list[list[materialize.Node]] = []
    pins: list[Pin | None] = []
    errors: list[dict[str, object]] = []
    for index, step in enumerate(steps):
        if "action" in step:
            error_class = _grade_mutate_step(case, step, steps, results, pins)
            if error_class is not None:
                errors.append({"at": f"/scenario/{index}", "errorClass": error_class})
            results.append([])
            pins.append(None)
            continue
        target = step.get("targetEntity")
        find_doc = step.get("find")
        if not isinstance(target, str) or find_doc is None:
            raise EngineError(
                f"{case.path.name}: scenario find step needs `targetEntity` and `find`"
            )
        try:
            raw_op = deserialize(find_doc)
            result = find(raw_op, meta, dialect, target, port)
            pin = _find_step_pin(meta, target, raw_op)
        except (OperationError, SqlGenError, TemporalReadError, KeyError) as exc:
            raise EngineError(f"{case.path.name}: {exc}") from exc
        for statement in result.execution.statements:
            emissions.append(Emission(f"/scenario/{index}/find", statement.sql, statement.binds))
        round_trips += result.execution.round_trips
        results.append(list(result.nodes))
        pins.append(pin)
    return emissions, round_trips, errors


def _find_step_pin(meta: Metamodel, target: str, raw_op: Operation) -> Pin:
    """A scenario find step's own statement pin — the whole-graph as-of
    coordinates the materialized view carries (`m-snapshot-read`), read from
    the SAME raw operation the find executor consumes. This is the pin
    :func:`_grade_mutate_step` hands the production write seam's finite-pin
    rule, resolved through the family-declaring entity exactly as the read
    path resolves it."""
    declaring = inheritance.declaring_entity(meta, meta.entity(target))
    return statement_pin(raw_op, declaring)


def _grade_mutate_step(
    case: case_format.Case,
    step: Mapping[str, object],
    steps: Sequence[Mapping[str, object]],
    results: Sequence[list[materialize.Node]],
    pins: Sequence[Pin | None],
) -> str | None:
    """Grade one scenario `mutate` action step through the SAME production
    validator the keyed developer verbs run
    (:func:`~parallax.snapshot.handle.validate_source_pin`): a mutation
    through a view pinned at a finite Transaction-Time instant raises the
    neutral `transaction-time-pin-read-only` error and applies nothing, while
    a Latest or finite-Valid-Time pin is accepted and the `set` applies
    in-memory (:func:`_apply_mutate_step`). Returns the raised error's
    `errorClass` when the step's own declared `expectError` matched it, else
    ``None`` for an accepted mutation; a mismatch in either direction — an
    undeclared refusal, or a declared expectation the verb never raised — is
    a loud :class:`EngineError`, never a silently dropped observation."""
    _check_action_step(case, step)
    on = step.get("on")
    if not isinstance(on, int) or not (0 <= on < len(results)):
        raise EngineError(f"{case.path.name}: `mutate` names an invalid `on` step index {on!r}")
    target = steps[on].get("targetEntity")
    expected = step.get("expectError")
    try:
        validate_source_pin(str(target), pins[on])
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
    _apply_mutate_step(case, step, results)
    return None


def _apply_mutate_step(
    case: case_format.Case, step: Mapping[str, object], results: Sequence[list[materialize.Node]]
) -> None:
    _check_action_step(case, step)
    on = step.get("on")
    if not isinstance(on, int) or not (0 <= on < len(results)):
        raise EngineError(f"{case.path.name}: `mutate` names an invalid `on` step index {on!r}")
    nodes = results[on]
    if len(nodes) != 1:
        raise EngineError(
            f"{case.path.name}: `mutate` targets step {on}, which materialized "
            f"{len(nodes)} nodes (expected exactly one to mutate)"
        )
    set_values = step.get("set")
    if not isinstance(set_values, Mapping):
        raise EngineError(f"{case.path.name}: a `mutate` action needs a `set` mapping")
    nodes[0].fields.update(cast("Mapping[str, object]", set_values))


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
    case: case_format.Case, meta: Metamodel, shadow: TemporalShadow
) -> None:
    """Seed ``shadow`` from the case's OWN fixture-loading rule (`m-case-format`):
    a writeSequence starts EMPTY unless it opts in with ``given.fixtures: true``;
    every other shape (scenario, conflict) loads the model's default fixtures —
    mirrored from ``tests/conftest.case_fixtures``'s own rule, kept independent
    (production/adapter code never imports the test suite)."""
    given = case.document.get("given")
    fixtures_flag = (
        isinstance(given, Mapping) and cast("Mapping[str, object]", given).get("fixtures") is True
    )
    if case.shape == "writeSequence" and not fixtures_flag:
        return
    fixtures = provision.load_fixtures(cast("str", case.document["model"]))
    for entity_name, rows in fixtures.items():
        shadow.seed_fixtures(meta, entity_name, cast("list[Mapping[str, object]]", rows))


def _execute_write_unit(
    port: DbPort,
    meta: Metamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    resolved: Sequence[tuple[WriteInstruction, ObjectKey | None, Observation | None]],
    tx_instant: str,
    *,
    rollback: bool,
) -> None:
    """Execute one choreography unit's ALREADY-RESOLVED instructions through the
    production ``db.transact`` entry point (COR-3 Phase 8 increment 4, DQ4
    re-route, ledger D-18) — ONE transaction, ``clock=FixedClock(tx_instant)``
    (ADR 0010: instants come from the Clock Strategy, never a per-operation
    override). A single-row instruction buffers through the neutral
    ``Transaction._buffer`` route + ``UnitOfWork.observe`` — never the typed
    instance verbs (`insert` / `update` / `delete`), which this engine's
    case-driven metamodel has no compiled Python classes for. A COLLAPSED
    multi-row instruction (COR-3 Phase 8 increment 5, `m-batch-write`) buffers
    directly on the unit of work instead (:func:`_build_instructions`'s "not
    decomposes" branch already deserialized + `validate_instruction`-ed it, and
    it carries no per-row observation by construction — `Transaction._buffer`'s
    own single-row document route cannot carry more than one row). A
    ``rollback: true`` step raises inside the callback (rollback-only,
    `m-unit-work` abort contract): the buffered DML still executes — and counts
    its round trips — before the provider rolls the transaction back.
    """
    instant = normalize_instant(dt.datetime.fromisoformat(tx_instant))
    database = handle.Database(port, meta, dialect=dialect, clock=FixedClock(instant))

    def body(tx: handle.Transaction) -> None:
        for instruction, key, observation in resolved:
            assert isinstance(
                instruction, KeyedWrite
            )  # every resolved entry this lane buffers is keyed
            if key is not None and observation is not None:
                # The documented neutral seam (Transaction._buffer route + uow.observe).
                tx._uow.observe(key, observation)  # pyright: ignore[reportPrivateUsage]
            rows = instruction.rows
            if len(rows) == 1:
                tx._buffer(  # pyright: ignore[reportPrivateUsage]
                    instruction.mutation,
                    instruction.entity,
                    dict(rows[0]),
                    valid_from=instruction.valid_from,
                    until=instruction.until,
                )
            else:
                tx._uow.buffer(instruction)  # pyright: ignore[reportPrivateUsage]
        if rollback:
            # Force the buffered DML to execute (and count its round trips)
            # INSIDE the still-open atomic scope before the intentional abort —
            # `db.transact`'s own post-body flush never runs once `body` raises
            # (`UnitOfWork.run_outermost` discards the buffer unflushed on any
            # exception), so this scope must flush itself first (`m-unit-work`
            # abort contract: "the forced flush is safe precisely because it
            # lands inside the still-open atomic scope the abort discards").
            tx._uow.flush()  # pyright: ignore[reportPrivateUsage]
            raise _RollbackStep

    with contextlib.suppress(_RollbackStep):
        database.transact(body, concurrency=concurrency)


def _run_readless_predicate_write(
    port: DbPort,
    meta: Metamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    raw_write: Mapping[str, object],
    tx_instant: str,
    *,
    rollback: bool,
) -> None:
    """Execute a READLESS scenario predicate-write step (`m-batch-write-005`/
    ``-006``) through the SAME production ``db.transact`` entry point every
    other write path uses — one transaction, buffering through
    ``Transaction._buffer_predicate_instruction`` (the neutral seam the typed
    ``_where`` verbs and this engine translation share, `m-case-format`
    "predicate-shaped case entries ... buffer through Transaction's own seam,
    materialization then happens exactly where production does it")."""
    instruction = instructions.deserialize(_canonical_predicate_doc(raw_write))
    assert isinstance(instruction, PredicateWrite)
    instructions.validate_instruction(instruction, meta)
    instant = normalize_instant(dt.datetime.fromisoformat(tx_instant))
    database = handle.Database(port, meta, dialect=dialect, clock=FixedClock(instant))

    def body(tx: handle.Transaction) -> None:
        tx._buffer_predicate_instruction(instruction)  # pyright: ignore[reportPrivateUsage]
        if rollback:
            tx._uow.flush()  # pyright: ignore[reportPrivateUsage]
            raise _RollbackStep

    with contextlib.suppress(_RollbackStep):
        database.transact(body, concurrency=concurrency)


class _CapturingPort:
    """A pass-through ``m-db-port`` capturing every executed statement (read
    or write, SQL + binds, in call order) — a MATERIALIZING predicate write's
    own reporting seam (COR-3 Phase 8 increment 5): its per-row binds are
    QUERY-RESULT-DEPENDENT, so there is no pure oracle to derive ``emissions``
    from independently of a real run; :func:`_run_materializing_pair` instead
    reports exactly what executed. Nested ``transaction()`` wrapping shares
    the SAME ``captured`` list across the outer port and the inner connection
    the provider's own ``transaction()`` hands the callback (mirroring
    ``tests/conformance/test_run_sweep.py``'s ``_ReadCapturePort`` precedent),
    so a grouped or nested call captures into one single ordered list.
    """

    def __init__(
        self, inner: DbPort, captured: list[tuple[str, tuple[object, ...]]] | None = None
    ) -> None:
        self._inner = inner
        self.captured: list[tuple[str, tuple[object, ...]]] = (
            captured if captured is not None else []
        )

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:
        self.captured.append((sql, tuple(binds)))
        return self._inner.execute(sql, binds)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.captured.append((sql, tuple(binds)))
        return self._inner.execute_write(sql, binds)

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        captured = self.captured

        def wrapped(conn: DbPort) -> T:
            return body(_CapturingPort(conn, captured=captured))

        return self._inner.transaction(wrapped)


def _is_materializing_write_step(
    step: Mapping[str, object] | None, meta: Metamodel
) -> PredicateWrite | None:
    """If ``step`` is a write step whose ``write`` field is a structured
    predicate instruction targeting a VERSIONED or TEMPORAL entity
    (MATERIALIZES, `m-opt-lock` "Predicate-selected writes materialize when
    observations are needed", ADR 0014), its deserialized + validated
    :class:`~parallax.core.unit_work.PredicateWrite` — ``None`` for a keyed
    write step, a READLESS predicate write, a find step, or ``None`` itself
    (no such step, e.g. the scenario's last step)."""
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
    instructions.validate_instruction(instruction, meta)
    entity = meta.entity(instruction.target.entity)
    declaring = inheritance.declaring_entity(meta, entity)
    if declaring.is_temporal or _is_versioned_entity(meta, instruction.target.entity):
        return instruction
    return None


def _run_materializing_pair(
    port: DbPort,
    meta: Metamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    steps: Sequence[Mapping[str, object]],
    index: int,
) -> list[_LoweredStep]:
    """Execute a MATERIALIZING predicate-write step (``index + 1``) whose
    IMMEDIATELY PRECEDING step (``index``) is the resolving find that shares
    its target entity — ONE transaction, `m-case-format` "Materializing
    cases": "a preceding scenario read resolves the same target predicate ...
    It is a real resolving read, not a cache hit". Production materialization
    (``Transaction._buffer_predicate_instruction``) performs its OWN internal
    resolve using the SAME predicate; with no concurrent writer between the
    two steps, that resolve observes the IDENTICAL rows the corpus's own
    preceding find step documents, so pairing them here reproduces the
    corpus's own ``1 resolve + N per-row writes`` round-trip accounting
    exactly — the resolve's round trip is charged to the FIND step's pointer
    (the corpus's own authoring convention), never double-counted against the
    write step.

    Reports the ACTUAL executed SQL (:class:`_CapturingPort`), never a
    separate pure re-lowering: the resolve is this pair's first captured
    statement (materialization always resolves before it writes), and every
    statement after it is one of the ``N`` per-row keyed writes, in
    resolved-row order.
    """
    find_step = steps[index]
    write_step = steps[index + 1]
    instruction = _is_materializing_write_step(write_step, meta)
    assert instruction is not None  # the caller already established this via the same check
    target = find_step.get("targetEntity")
    if target != instruction.target.entity:
        raise EngineError(
            f"materializing predicate write at scenario step {index + 1} is not preceded by "
            f"a resolving find over the SAME target entity (find targets {target!r}, write "
            f"targets {instruction.target.entity!r} — m-case-format 'Materializing cases' "
            "requires the prior find to share the write's own target)"
        )
    # `m-case-format.md:719`: "For every versioned or temporal target, model-
    # aware validation MUST require that prior find to use the same concrete
    # `targetEntity` AND CANONICAL OPERATION" — same entity alone is not
    # enough (a resolving find over a DIFFERENT predicate would silently
    # observe the wrong rows). Compared BARE (`deserialize`, no as-of
    # injection / navigate canonicalization): `instruction.target.predicate`
    # is itself the write's own UN-injected bare predicate
    # (`instructions.deserialize`), so the find step's own raw operation is
    # the one apples-to-apples comparison — `_canonicalize_read`'s temporal
    # as-of injection would make even a genuinely matching pair compare
    # unequal.
    find_doc = find_step.get("find")
    find_operation = deserialize(find_doc) if find_doc is not None else None
    if find_operation != instruction.target.predicate:
        raise EngineError(
            f"materializing predicate write at scenario step {index + 1} is not preceded by "
            "a resolving find over the SAME canonical operation as the write's own target "
            f"predicate (find {find_operation!r}, write {instruction.target.predicate!r} — "
            "m-case-format 'Materializing cases' requires the prior find to use the same "
            "concrete targetEntity and canonical operation)"
        )
    tx_instant = _entry_instant(cast("Mapping[str, object]", write_step["write"]))
    instant = normalize_instant(dt.datetime.fromisoformat(tx_instant))
    capture = _CapturingPort(port)
    database = handle.Database(capture, meta, dialect=dialect, clock=FixedClock(instant))
    rollback = write_step.get("rollback") is True

    def body(tx: handle.Transaction) -> None:
        tx._buffer_predicate_instruction(instruction)  # pyright: ignore[reportPrivateUsage]
        if rollback:
            tx._uow.flush()  # pyright: ignore[reportPrivateUsage]
            raise _RollbackStep

    with contextlib.suppress(_RollbackStep):
        database.transact(body, concurrency=concurrency)
    if not capture.captured:  # pragma: no cover - zero resolved rows still resolves (1 statement)
        raise EngineError(
            f"materializing predicate write at scenario step {index + 1} executed no "
            "statements at all — even a zero-row resolve issues its own SELECT"
        )
    # `capture.captured` holds the ACTUAL DRIVER SQL (each statement already
    # translated by `dialect.to_driver_sql` before it ever reached the port) —
    # every OTHER emission this engine reports is canonical `?`-placeholder text
    # (a pure re-lowering that never touches a driver), so each captured
    # statement's SQL must round-trip back through `dialect.from_driver_sql`
    # before joining them; the binds themselves need no translation (the
    # framework's own pre-adapter values, the same shape a pure re-lowering's
    # `Statement.binds` already carries).
    resolve_sql, resolve_binds = capture.captured[0]
    write_statements = tuple(
        Statement(dialect.from_driver_sql(sql), binds) for sql, binds in capture.captured[1:]
    )
    return [
        _LoweredStep(
            f"/scenario/{index}/find",
            (Statement(dialect.from_driver_sql(resolve_sql), resolve_binds),),
            False,
            False,
        ),
        _LoweredStep(f"/scenario/{index + 1}/write", write_statements, True, rollback),
    ]


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
    :func:`run_interleaved_scenario_case` instead (COR-3 Phase 8 increment
    6). Anything BEYOND that one witnessed shape — three or more interleaved
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


def _run_uow_group(
    port: DbPort,
    meta: Metamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    shadow: TemporalShadow,
    steps: Sequence[Mapping[str, object]],
    start: int,
    end: int,
) -> list[_LoweredStep]:
    """Execute one CONTIGUOUS `uow` group's steps (index *start*..*end*
    inclusive) inside ONE ``db.transact`` (COR-3 Phase 8 amendment-review
    remediation): in step order, a grouped FIND reads THROUGH the
    transaction's own connection (``tx._conn`` — force-flushing any pending
    buffered write first, ``tx._uow.read``, exactly as a real
    ``Transaction.find`` does) and records its own observation on the
    transaction's unit of work (:func:`_observe_group_find`); a grouped WRITE
    resolves against this SAME group's own observations (never a scenario-
    wide map) and buffers via ``tx._buffer``, so the eventual ``flush()``
    derives every version bind from ``self._observations`` alone — the SAME
    neutral seam :func:`_execute_write_unit` uses for one step, generalized
    here to a whole group. Emissions/round-trips still come from the SAME
    pure re-lowering every other write path uses (:func:`_lower_resolved`),
    fed this group's own observations — the oracle stays a pure function of
    (instructions, observations, instant), only now the observations
    themselves come from a REAL find this SAME call already executed, not an
    authored value. `rollback: true` on any of the group's own write steps
    dooms the WHOLE group: after its last step, the buffer is force-flushed
    (a no-op if a trailing find already forced it via read-your-own-writes)
    and the closure raises — the `m-unit-work` abort contract applied to the
    group rather than one step.
    """
    tx_instant = _group_tx_instant(steps, start, end)
    doomed = _group_is_doomed(steps, start, end)
    group_observations: ScenarioObservations = {}
    instant = normalize_instant(dt.datetime.fromisoformat(tx_instant))
    database = handle.Database(port, meta, dialect=dialect, clock=FixedClock(instant))
    lowered: list[_LoweredStep] = []

    def body(tx: handle.Transaction) -> None:
        for index in range(start, end + 1):
            step = steps[index]
            if "write" in step:
                entries = _write_entries(step["write"])
                resolved = _resolve_entries(entries, meta, shadow, tx_instant, group_observations)
                statements = _lower_resolved(resolved, meta, dialect, concurrency, tx_instant)
                for instruction, key, observation in resolved:
                    assert isinstance(
                        instruction, KeyedWrite
                    )  # every resolved entry this lane buffers is keyed
                    if key is not None and observation is not None:
                        tx._uow.observe(key, observation)  # pyright: ignore[reportPrivateUsage]
                    tx._buffer(  # pyright: ignore[reportPrivateUsage]
                        instruction.mutation,
                        instruction.entity,
                        dict(instruction.rows[0]),
                        valid_from=instruction.valid_from,
                        until=instruction.until,
                    )
                lowered.append(
                    _LoweredStep(
                        f"/scenario/{index}/write", statements, True, step.get("rollback") is True
                    )
                )
            else:
                statement = _lower_find(step, meta, dialect, concurrency)
                target = cast("str", step["targetEntity"])
                conn = tx._conn  # pyright: ignore[reportPrivateUsage]
                rows = tx._uow.read(  # pyright: ignore[reportPrivateUsage]
                    lambda st=statement, c=conn: _execute_reads(c, dialect, (st,))
                )
                _observe_group_find(tx, group_observations, meta, target, rows)
                lowered.append(_LoweredStep(f"/scenario/{index}/find", (statement,), False, False))
        if doomed:
            # Force any still-buffered DML onto the wire (and count its round
            # trips) INSIDE the still-open atomic scope before the deliberate
            # abort — a no-op when a trailing grouped find already forced the
            # flush via read-your-own-writes (`m-unit-work-012`'s doomed group);
            # otherwise (the group's last step is itself the doomed write, no
            # find after it) this is what puts the DML on the wire at all
            # (`m-unit-work` abort contract, mirroring `_execute_write_unit`).
            tx._uow.flush()  # pyright: ignore[reportPrivateUsage]
            raise _RollbackStep

    with contextlib.suppress(_RollbackStep):
        database.transact(body, concurrency=concurrency)
    return lowered


# --------------------------------------------------------------------------- #
# Interleaved `uow` groups — the two-group optimistic-lock race                #
# (`m-opt-lock-012`, COR-3 Phase 8 increment 6). `_run_uow_group` above runs   #
# ONE contiguous group on the main connection; a genuinely interleaved case    #
# needs TWO groups held open CONCURRENTLY over TWO real sessions (the          #
# `Provisioner.peer` seam) — a DIFFERENT consumer of that seam than the        #
# `when.concurrency` rounds runner (`parallax.conformance.concurrency_runner`, #
# real `db.transact` calls, production routing per D-18/DQ4, not verbatim      #
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
    through (COR-3 Phase 8 increment 6): a thread's own step at index ``i``
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


def _empty_group_rows() -> dict[int, list[Row]]:
    return {}


@dataclass(slots=True)
class _InterleavedGroupResult:
    """One interleaved group's own report: its lowered steps (keyed by
    scenario step index), the conflict's own `actual` affected-row count
    when its LAST write step doomed the group via a genuine optimistic-lock
    conflict (`None` for a group that committed, or that never conflicts),
    any OTHER exception the worker thread raised (re-raised on the main
    thread once both join — never silently swallowed), and every OWN find
    step's own observed rows (keyed by scenario step index, review
    remediation finding 1) — the group's own oracle for `expectRows`, the
    SAME grade the ordinary scenario run lane (`test_write_run_sweep`'s
    `_ReadCapturePort`) already gives every OTHER find step; without this the
    caller has no way to grade a grouped find at all, only its DML shape."""

    lowered: dict[int, _LoweredStep]
    conflict_actual: int | None = None
    failure: BaseException | None = None
    rows: dict[int, list[Row]] = field(default_factory=_empty_group_rows)


def _run_interleaved_group(
    database: handle.Database,
    meta: Metamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    shadow: TemporalShadow,
    steps: Sequence[Mapping[str, object]],
    indices: Sequence[int],
    turnstile: _Turnstile,
    result: _InterleavedGroupResult,
) -> None:
    """Run one interleaved group's OWN steps (``indices``, in authored order,
    possibly non-contiguous across the WHOLE scenario) inside ONE real
    ``db.transact`` call on ``database`` — the SAME buffer/observe/flush
    machinery :func:`_run_uow_group` uses for a contiguous span, generalized
    to an explicit index list and gated by ``turnstile`` at every step. A
    write step's lowering is the SAME pure re-lowering every other write path
    uses (:func:`_lower_resolved`), recorded BEFORE the group's own flush
    executes it, so a step that later CONFLICTS still reports its own
    well-formed golden DML (`m-opt-lock` "Conflict detection" — the SQL is
    correct, the row count is not).

    The group's OWN LAST step forces an explicit flush (never deferred to
    end-of-scope auto-flush): a WRITE step's flush may itself raise
    :class:`~parallax.core.opt_lock.OptimisticLockConflictError` (the SAME
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

    ``shadow`` is the SAME single :class:`TemporalShadow` every group shares
    (`_run_uow_group`'s own convention) — safe here ONLY because
    `m-opt-lock-012`'s own witnessed model is entirely NON-temporal (the
    tracker is never mutated for these instructions, so two threads never
    contend on it); a genuinely temporal interleaved case would need its own
    per-group tracking discipline, unwitnessed and out of scope.

    Every OWN find step's observed rows land in ``result.rows`` (keyed by
    scenario step index, review remediation finding 1): the caller's own
    oracle for that step's authored ``expectRows`` — without this, a grouped
    find's own DML is graded but its OBSERVATION never is, so a broken abort
    that left a doomed group's writes durable would report well-formed SQL
    and still pass.
    """
    lowered: dict[int, _LoweredStep] = {}
    group_observations: ScenarioObservations = {}

    def body(tx: handle.Transaction) -> None:
        for position, index in enumerate(indices):
            turnstile.wait_for(index)
            step = steps[index]
            is_last = position == len(indices) - 1
            if "write" in step:
                entries = _write_entries(step["write"])
                resolved = _resolve_entries(
                    entries, meta, shadow, _INERT_CLOCK_INSTANT, group_observations
                )
                statements = _lower_resolved(
                    resolved, meta, dialect, concurrency, _INERT_CLOCK_INSTANT
                )
                for instruction, key, observation in resolved:
                    assert isinstance(
                        instruction, KeyedWrite
                    )  # every resolved entry this lane buffers is keyed
                    if key is not None and observation is not None:
                        tx._uow.observe(key, observation)  # pyright: ignore[reportPrivateUsage]
                    tx._buffer(  # pyright: ignore[reportPrivateUsage]
                        instruction.mutation,
                        instruction.entity,
                        dict(instruction.rows[0]),
                        valid_from=instruction.valid_from,
                        until=instruction.until,
                    )
                lowered[index] = _LoweredStep(
                    f"/scenario/{index}/write", statements, True, step.get("rollback") is True
                )
                if is_last:
                    tx._uow.flush()  # pyright: ignore[reportPrivateUsage]
            else:
                statement = _lower_find(step, meta, dialect, concurrency)
                target = cast("str", step["targetEntity"])
                conn = tx._conn  # pyright: ignore[reportPrivateUsage]
                rows = tx._uow.read(  # pyright: ignore[reportPrivateUsage]
                    lambda st=statement, c=conn: _execute_reads(c, dialect, (st,))
                )
                _observe_group_find(tx, group_observations, meta, target, rows)
                result.rows[index] = rows
                lowered[index] = _LoweredStep(f"/scenario/{index}/find", (statement,), False, False)
            if not is_last:
                turnstile.advance()

    committed = False
    try:
        database.transact(body, concurrency=concurrency)
        committed = True
    except opt_lock.OptimisticLockConflictError as exc:
        result.conflict_actual = exc.actual
    except BaseException as exc:  # re-raised on the main thread below
        result.failure = exc
        turnstile.release_all()  # never leave a partner thread hanging on this thread's own defect
    result.lowered = lowered
    if committed:
        turnstile.advance()


# The interleaved-group choreography's own bounded join (the provider-
# contract deadlock proof's own precedent): a genuine harness defect (a
# missing `advance()` somewhere) must surface as a loud failure, never an
# indefinitely hung test session. Named so :func:`_await_interleaved_workers`
# can be exercised directly with a SHRUNK bound (review remediation finding
# 4) — a real, unstuck-by-`release_all` timeout path in well under a second,
# rather than the production bound actually elapsing twice.
_INTERLEAVED_GROUP_JOIN_TIMEOUT: Final[float] = 30.0


def _underlying_connection(connection: object) -> object | None:
    """The termination ladder's rung-two/rung-three shared reach target
    (:func:`_terminate_connection`): the duck-typed underlying transport
    (mirroring :attr:`~parallax.postgres.PostgresAdapter.connection`, the
    wrapped psycopg ``Connection``), or ``None`` when ``connection`` exposes
    no such escalation seam at all. Round 4 single-sourced this helper with
    a since-retired pre-start SHAPE validator too; round 5 (the corrected
    contract on the interleaved-uow join-timeout residual) narrows that
    scope back to the ladder alone — preflight
    (:func:`_require_interleaved_termination_capability`) no longer inspects
    a connection's shape at all, so this function's "single source" promise
    is exactly what :func:`_terminate_connection`'s own rungs two and three
    need and nothing more."""
    return getattr(connection, "connection", None)


# ---------------------------------------------------------------------------
# The round-5 corrected contract's own trust marker (the interleaved-uow
# join-timeout residual, FIFTH confirmation pass on the same helper block).
# Round 4 deepened the original best-effort design into a pre-start
# preflight, but validated STRUCTURE only — whether `close()` / `fileno()`
# were CALLABLE — never whether termination was RELIABLE. The reviewer
# reproduced exactly the gap that leaves open: a port whose cancellation,
# close, underlying close, and socket teardown are all CALLABLE yet all
# RAISE at runtime passed round 4's structural check
# (`preflight=('validated',)`) and then hung the unbounded post-ladder join
# forever (`helper_completed=False`). Runtime reliability of an arbitrary
# duck-typed object this module does not itself construct is not provable
# by inspection — round 4's own reproduction is the proof — so preflight
# stops inferring a guarantee from shape and starts REQUIRING an explicit,
# truthful GRANT of trust instead.
# ---------------------------------------------------------------------------
_TERMINATION_LADDER_TRUST_ATTR: Final[str] = "termination_ladder_trusted"
"""The documented trust marker's attribute name (round 5's own design
choice: a named boolean rather than a separate ABC/Protocol, kept a plain
duck-typed attribute so a test fake needs no extra base class to declare
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
attempting to verify one is true (verifying it is exactly round 4's own
retired mistake: a declaration this module never actually asked for, only
a shape it hoped implied one)."""


def _validate_termination_trust(connection: object, label: str) -> list[str]:
    """Round 5's own pre-start refusal check (the corrected contract on the
    interleaved-uow join-timeout residual, deepening round 4's own
    structural-only check into a TRUSTED, DECLARED contract): ``connection``
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
    plausible ladder of them — is NEVER sufficient on its own: the
    reviewer's own reproduction is exactly a port with every rung callable
    and every rung RAISING at runtime, which this check refuses WITHOUT
    CALLING any of them (a pure trust check, never a behavioral probe —
    nothing here is invoked, only inspected, exactly as round 4's own
    structural check never invoked anything either).

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
    """The corrected contract's own entry point (round 5, the FIFTH
    confirmation pass on the interleaved-uow join-timeout residual). Round 4
    validated only that a connection's ``close()`` / ``fileno()`` were
    CALLABLE — the reviewer reproduced a port that passes that structural
    check yet whose every runtime rung RAISES, leaving
    :func:`_await_interleaved_workers`'s own deliberately UNBOUNDED
    post-ladder join (round 3's design) hanging indefinitely with no live
    process able to unstick it. So this pass deepens the check from
    STRUCTURE to TRUST: BEFORE either interleaved-group worker thread
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
    escalation, a later confirmation pass on review remediation finding 4):
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
    :func:`_terminate_connection` — round 3's own GUARANTEED close ladder,
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
    escalation) — a round-3 confirmation pass's own correction on review
    remediation finding 4: unlike :func:`_cancel_in_flight_work`
    (best-effort, non-destructive), this rung is GUARANTEED, never
    best-effort. Round 2 shipped a single, silently-swallowed ``close()``
    probe on the assumption that closing always works; the round-3 pass
    forced BOTH ``cancel()`` and ``close()`` to fail on the SAME survivor
    and reproduced exactly the failure that assumption was covering for — a
    live worker still racing the caller after this rung had already run and
    :func:`_await_interleaved_workers` had already raised.

    The corrected ladder, each rung attempted only once the one above it is
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
       test fake must expose once its own OUTER ``close()`` is made to fail
       — the round-3 confirmation pass's own adversarial pin proves the
       escalation reaches it.
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

    Round 4 single-sourced rungs 1 and 2's own reach — the underlying
    transport below is fetched through :func:`_underlying_connection` — with
    a pre-start SHAPE validator that round 5 (the corrected contract on the
    interleaved-uow join-timeout residual) has since retired: this ladder's
    OWN mechanics are untouched by that correction (the round-3 guaranteed
    escalation below stays exactly as it was), only the GATE above it
    changed, from re-deriving a guarantee by inspecting this ladder's own
    rung shapes to requiring a caller-visible, DECLARED trust contract
    instead (:func:`_require_interleaved_termination_capability`,
    :data:`_TERMINATION_LADDER_TRUST_ATTR`) — this function no longer has a
    validator counterpart walking the SAME reach helper for the SAME
    reason; it is simply this ladder's own single-sourced reach for rungs
    two and three."""
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
    while they may still be alive (review remediation finding 4): wake every
    waiter parked in ``turnstile.wait_for`` (:meth:`_Turnstile.release_all` —
    the SAME defensive unstick a worker's own unexpected failure already
    uses), close ``peer_connection`` so any outstanding database work the
    peer-side worker still holds terminates, THEN rejoin both threads (bounded
    again, never a second indefinite hang).

    That first escalation cannot reach a worker blocked in REAL database I/O
    on its OWN session (a later confirmation pass's own residual on this same
    finding): ``release_all`` only wakes a thread parked in
    ``turnstile.wait_for``, and closing ``peer_connection`` touches only the
    ``concurrent`` group's session, never ``main_connection``. So any thread
    STILL alive after that rejoin gets a SECOND escalation:
    :func:`_cancel_in_flight_work` — best-effort, non-destructive, and
    (round 3's own explicit call) ALLOWED to stay that way, because the
    guarantee below lives entirely in the rung after it — on its OWN
    connection (``main_connection`` for ``thread_a``, ``peer_connection``
    for ``thread_b``), then one more bounded rejoin of both.

    ROUND-3 CORRECTED, FINAL CONTRACT (supersedes rounds 1-2's own terminal
    designs): this function has NO code path — return, raise, or assert —
    that runs while any started worker is alive. Round 1 raised a loud
    "could not stop" error with a worker potentially still running; round 2
    replaced that with a bounded rejoin behind an assumed-guaranteed
    ``close()`` and an internal ``AssertionError`` safety net for when that
    assumption failed — and a round-3 confirmation pass reproduced exactly
    that failure: BOTH ``cancel()`` and ``close()`` forced to fail on the
    same survivor, a live worker at the very point this function used to
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
    no ``timeout=``): this retires round 2's own separate, fixed
    termination-join bound and its ``AssertionError`` safety net entirely —
    there is no longer a second, narrower timeout to violate. The trade,
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

    Round 4 (a confirmation pass on this SAME join-timeout residual)
    strengthened that trade from implicit to EXPLICIT: the reviewer
    reproduced every rung above failing on every worker, leaving this join
    hanging indefinitely with no live process able to unstick it, so
    :func:`run_interleaved_scenario_case` was made to call
    :func:`_require_interleaved_termination_capability` on BOTH
    ``main_connection`` and ``peer_connection`` before either worker thread
    even starts. Round 4's OWN check validated only that a connection's
    ``close()`` / ``fileno()`` were CALLABLE — and the reviewer reproduced
    exactly the gap that leaves: a port with every one of those callable,
    passing that structural check, and every one RAISING at runtime, hanging
    this SAME join anyway (round 5, the fifth confirmation pass on this
    block: ``preflight=('validated',)``, ``helper_completed=False``). So
    round 5 deepened the check from STRUCTURE to TRUST — a connection now
    passes only by carrying a DECLARED deterministic-termination contract
    (:func:`_validate_termination_trust`: the known-deterministic
    ``PostgresAdapter`` shape, trusted by construction, or an explicit
    :data:`_TERMINATION_LADDER_TRUST_ATTR` marker declaring the SAME
    responsibility). Past that validation, a hang at the join below can only
    mean a connection's trust grant was UNTRUTHFUL — a lying declaration (or
    a `PostgresAdapter` whose own OS-level guarantee was somehow defeated):
    a contract violation by that connection type, diagnosable at this exact
    line, never an ordinary or expected outcome. The requirement was always
    real; the declaration only makes it explicit and caller-visible instead
    of leaving it implicit in an unbounded join a maintainer would otherwise
    have to reverse-engineer.

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
    # (or returning) while a worker is still alive; this retires round 2's
    # own separate, fixed termination-join bound and its `AssertionError`
    # safety net.
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
) -> tuple[list[Emission], int, int | None, list[list[Row]]]:
    """Run the ONE witnessed interleaved-`uow`-group scenario shape
    (`m-opt-lock-012`'s two-group optimistic-lock race, COR-3 Phase 8
    increment 6): the ``ours`` group on the caller's own ``port``, a
    ``concurrent`` group on a SECOND, peer-backed connection (``peer_factory``
    — this function constructs no connection itself), each a REAL
    ``db.transact`` (production routing, D-18/DQ4), steps sequenced across
    the two in AUTHORED order (:class:`_Turnstile`). Any ungrouped step
    (`m-opt-lock-012`'s own trailing verify find) runs AFTER both groups have
    resolved, on the caller's ``port``.

    Reports the ordered emissions, total round trips, and — when a group's
    own last write step conflicted — the conflict's ``actual`` affected-row
    count (`then.affectedRows`, the scenario shape's own EXTRA top-level
    assertion this ONE case authors; ``None`` when no group conflicted), and
    EVERY find step's own observed rows (grouped or ungrouped, in scenario
    step order — review remediation finding 1): the caller's own oracle for
    every authored `expectRows`, the SAME observable the ordinary scenario
    run lane grades for every OTHER find step. Routed to explicitly by the
    run sweep (`test_run_sweep.py`) rather than through `run_scenario_case`/
    `adapter.run_case` — this shape's own peer requirement has no seat in the
    ordinary shape-dispatched entry points, the SAME reasoning the rounds
    runner's own dispatch follows.

    Before either worker thread starts, both ``port`` and the connection
    ``peer_factory`` produces must carry a TRUSTED deterministic-termination
    contract (:func:`_require_interleaved_termination_capability`, round 5
    on the join-timeout residual) — a connection with no declared trust
    refuses loudly here, rather than surfacing only much later as an
    indefinite hang at :func:`_await_interleaved_workers`'s own unbounded
    post-ladder join.
    """
    steps = _scenario_steps(case)
    meta = load_case_metamodel(case)
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
    _seed_shadow_from_fixtures(case, meta, shadow)
    instant = normalize_instant(dt.datetime.fromisoformat(_INERT_CLOCK_INSTANT))
    main_db = handle.Database(port, meta, dialect=dialect, clock=FixedClock(instant))
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
    peer_db = handle.Database(peer_connection, meta, dialect=dialect, clock=FixedClock(instant))
    turnstile = _Turnstile()
    result_a = _InterleavedGroupResult(lowered={})
    result_b = _InterleavedGroupResult(lowered={})
    thread_a = threading.Thread(
        target=_run_interleaved_group,
        args=(main_db, meta, dialect, concurrency, shadow, steps, indices_a, turnstile, result_a),
        name=f"uow-{label_a}",
    )
    thread_b = threading.Thread(
        target=_run_interleaved_group,
        args=(peer_db, meta, dialect, concurrency, shadow, steps, indices_b, turnstile, result_b),
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
    rows_by_index: dict[int, list[Row]] = {**result_a.rows, **result_b.rows}
    for index in ungrouped:
        step = steps[index]
        if "write" in step:  # pragma: no cover - no witnessed ungrouped write is doomed-adjacent
            raise EngineError(
                f"{case.path.name}: an ungrouped write step ({index}) beside an "
                "interleaved uow race is unsupported — m-opt-lock-012's own ungrouped "
                "step is a trailing verify find only"
            )
        statement = _lower_find(step, meta, dialect, concurrency)
        rows_by_index[index] = _execute_reads(port, dialect, (statement,))
        lowered[index] = _LoweredStep(f"/scenario/{index}/find", (statement,), False, False)

    ordered = [lowered[index] for index in sorted(lowered)]
    emissions = _emissions([(step.pointer, step.statements) for step in ordered])
    conflict_actual = result_a.conflict_actual
    if conflict_actual is None:
        conflict_actual = result_b.conflict_actual
    find_rows = [rows_by_index[index] for index in sorted(rows_by_index)]
    return emissions, len(emissions), conflict_actual, find_rows


def run_scenario_case(
    case: case_format.Case, dialect_name: str, port: DbPort
) -> tuple[list[Emission], int, list[dict[str, object]]]:
    """Run a scenario: an UNGROUPED write step commits (or aborts) as its OWN
    unit of work through ``db.transact`` (COR-3 Phase 8 increment 4, DQ4
    re-route) and an ungrouped find reads committed state, exactly as before.
    A `uow`-GROUPED contiguous span of steps instead runs inside ONE
    ``db.transact`` (COR-3 Phase 8 amendment-review remediation,
    :func:`_run_uow_group`): the observing find and the versioned write it
    licenses execute in the SAME unit of work, so the write's version bind is
    a genuine transaction-scoped observation, never an oracle. A MATERIALIZING
    predicate-write step (COR-3 Phase 8 increment 5) pairs with its
    IMMEDIATELY PRECEDING find step (:func:`_run_materializing_pair`) —
    detected by a one-step LOOK-AHEAD before that find is lowered as an
    ordinary standalone step, since `m-case-format`'s own "Materializing
    cases" convention makes the preceding find the resolve. Reports the
    ordered emissions, the total round trips, and the `errors` observation
    entries (`m-conformance-adapter`) — populated only by the snapshot
    action-step lane's `expectError` grading (:func:`_run_snapshot_scenario`);
    every keyed unit-of-work scenario reports an empty list."""
    steps = _scenario_steps(case)
    if _has_action_step(steps):
        return _run_snapshot_scenario(case, dialect_name, port, steps)
    meta = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    concurrency = _concurrency(case)
    find_lock = concurrency if _scenario_needs_lock(steps, meta) else None
    shadow = TemporalShadow()
    spans = _scenario_uow_spans(case.path.name, steps)
    if spans is None:
        raise EngineError(
            f"{case.path.name}: interleaved uow groups (the two-group optimistic-lock "
            "race shape, m-opt-lock-012) need a second, peer-backed connection this "
            "function does not construct — call run_interleaved_scenario_case instead"
        )
    span_start_labels = {start: label for label, (start, _end) in spans.items()}
    lowered: list[_LoweredStep] = []
    try:
        _seed_shadow_from_fixtures(case, meta, shadow)
        index = 0
        while index < len(steps):
            label = span_start_labels.get(index)
            if label is not None:
                start, end = spans[label]
                lowered.extend(
                    _run_uow_group(port, meta, dialect, concurrency, shadow, steps, start, end)
                )
                index = end + 1
                continue
            step = steps[index]
            if "write" not in step:
                next_step = steps[index + 1] if index + 1 < len(steps) else None
                pairing = _is_materializing_write_step(next_step, meta)
                if pairing is not None and step.get("targetEntity") == pairing.target.entity:
                    lowered.extend(
                        _run_materializing_pair(port, meta, dialect, concurrency, steps, index)
                    )
                    index += 2
                    continue
                statement = _lower_find(step, meta, dialect, find_lock)
                _execute_reads(port, dialect, (statement,))
                lowered.append(_LoweredStep(f"/scenario/{index}/find", (statement,), False, False))
                index += 1
                continue
            raw_write = step["write"]
            rollback = step.get("rollback") is True
            if _is_predicate_write_step(raw_write):
                # A materializing write reaching HERE (rather than being
                # consumed by the look-ahead pairing above) was not preceded
                # by a matching find — a malformed corpus case per
                # `m-case-format`'s own validation requirement; `lower_write`'s
                # defensive refusal surfaces it loudly rather than silently
                # mishandling it. A READLESS write needs no pairing at all.
                raw_predicate_write = cast("Mapping[str, object]", raw_write)
                tx_instant = _entry_instant(raw_predicate_write)
                statement = _lower_predicate_write_step(
                    raw_predicate_write, meta, dialect, concurrency
                )
                _run_readless_predicate_write(
                    port,
                    meta,
                    dialect,
                    concurrency,
                    raw_predicate_write,
                    tx_instant,
                    rollback=rollback,
                )
                lowered.append(
                    _LoweredStep(f"/scenario/{index}/write", (statement,), True, rollback)
                )
            else:
                entries = _write_entries(raw_write)
                tx_instant = _entry_instant(entries[0])
                resolved = _resolve_entries(entries, meta, shadow, tx_instant, {})
                statements = _lower_resolved(resolved, meta, dialect, concurrency, tx_instant)
                _execute_write_unit(
                    port, meta, dialect, concurrency, resolved, tx_instant, rollback=rollback
                )
                lowered.append(_LoweredStep(f"/scenario/{index}/write", statements, True, rollback))
            index += 1
    except _LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    emissions = _emissions([(step.pointer, step.statements) for step in lowered])
    return emissions, len(emissions), []


def run_write_sequence_case(
    case: case_format.Case, dialect_name: str, port: DbPort
) -> tuple[list[Emission], dict[str, list[Row]], int]:
    """Run a writeSequence: each entry executes as its OWN unit of work through
    ``db.transact`` (COR-3 Phase 8 increment 4, DQ4 re-route — "the whole
    sequence in one transaction" retires), then report the ordered per-entry
    emissions, the committed table state, and the total round trips.

    The table read-back is the `m-conformance-adapter` write-sequence observation
    ("write-sequence cases report ``tableState``"): the runner grades it against
    the case's ``then.tableState``. Observation reads are not case round trips.
    """
    meta = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    concurrency = _concurrency(case)
    shadow = TemporalShadow()
    scenario_observations: ScenarioObservations = {}
    lowered: list[tuple[str, tuple[Statement, ...]]] = []
    try:
        _seed_shadow_from_fixtures(case, meta, shadow)
        for index, entry in enumerate(_write_sequence_entries(case)):
            tx_instant = _entry_instant(entry)
            resolved = _resolve_entries([entry], meta, shadow, tx_instant, scenario_observations)
            statements = _lower_resolved(resolved, meta, dialect, concurrency, tx_instant)
            _execute_write_unit(
                port, meta, dialect, concurrency, resolved, tx_instant, rollback=False
            )
            lowered.append((f"/writeSequence/{index}", statements))
    except _LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    emissions = _emissions(lowered)
    table_state = read_table_state(port, meta, dialect)
    return emissions, table_state, len(emissions)


def read_table_state(port: DbPort, meta: Metamodel, dialect: Dialect) -> dict[str, list[Row]]:
    """The committed contents of every model table, in canonical wire form.

    Each row-owning table is read back with every physical column in FAMILY
    columnOrder (`_table_column_order` — a shared table is read once), so the
    observation reports exactly the state ``then.tableState`` asserts — derived
    from the metamodel, never from the case's expectations.
    """
    state: dict[str, list[Row]] = {}
    for entity in meta.entities:
        table = inheritance.effective_table(meta, entity)
        if table is None or table in state:
            continue
        columns = ", ".join(
            dialect.quote(column) for column in _table_column_order(meta, entity, table)
        )
        sql = f"select {columns} from {dialect.quote(table)}"
        rows = port.execute(dialect.to_driver_sql(sql), [])
        state[table] = [wire_row(row) for row in rows]
    return state


def _table_column_order(meta: Metamodel, entity: Entity, table: str) -> list[str]:
    """``table``'s FULL physical columns in canonical order (m-sql
    ``column_order``'s own rule — primary key first, then the inheritance tag,
    then the remaining scalars, then value-object documents).

    For a plain entity this is its own bare view (`column_order`). For an
    inheritance-family table it is EVERY entity mapped to it, unioned
    family-wide: a table-per-hierarchy shared table carries every sibling
    concrete's own columns (`then.tableState` asserts the WHOLE row, e.g.
    `m-inheritance-007`'s inserted `CardPayment` row still reports the
    cash-only `tendered` column as `null`), and a table-per-concrete-subtype
    table is one concrete's own ancestry chain. `column_order`'s own docstring
    defers exactly this "full inherited chain" resolution to "above this
    per-entity view" — the read-back analogue of
    `parallax.snapshot.handle`'s write-emission `_family_column_order`
    (a sibling resolution, not reused directly: write emission touches only
    ONE participant's own columns, this touches every participant SHARING
    the physical table).
    """
    if entity.inheritance is None:
        return list(column_order(entity))
    root = inheritance.family_root(meta, entity)
    assert root.inheritance is not None  # a resolved family root always carries one
    if root.inheritance.strategy == "table-per-hierarchy":
        members = sorted(
            (
                candidate
                for candidate in meta.entities
                if candidate.inheritance is not None
                and inheritance.family_root(meta, candidate) is root
            ),
            key=lambda candidate: candidate.name,
        )
    else:
        members = [entity]
    pk_columns = [attr.column for attr in root.attributes if attr.primary_key]
    tag_columns = [root.inheritance.tag_column] if root.inheritance.tag_column is not None else []
    chain = (*inheritance.ancestor_chain(meta, tuple(member.name for member in members)), *members)
    rest_columns: list[str] = []
    document_columns: list[str] = []
    seen_rest: set[str] = set()
    seen_docs: set[str] = set()
    for member in chain:
        for attribute in member.attributes:
            if attribute.primary_key or attribute.column in seen_rest:
                continue
            seen_rest.add(attribute.column)
            rest_columns.append(attribute.column)
        for vo in member.value_objects:  # pragma: no cover - no reachable family model
            if vo.storage_column in seen_docs:  # declares a value object yet (defensive dedup)
                continue
            seen_docs.add(vo.storage_column)
            document_columns.append(vo.storage_column)
    return [*pk_columns, *tag_columns, *rest_columns, *document_columns]


def _execute_reads(port: DbPort, dialect: Dialect, statements: Sequence[Statement]) -> list[Row]:
    """Execute every statement and return the LAST one's rows — a scenario find
    step is always single-statement (:func:`_lower_find`), so ``statements`` is
    always a one-tuple in practice; the raw, COLUMN-keyed rows are a GROUPED
    find's own source for :func:`_observe_group_find` (mirroring the
    production ``Transaction.find`` -> ``uow.observe`` seam that
    `parallax.snapshot.handle` owns) when called on the transaction's
    own connection (``tx._conn``, :func:`_run_uow_group`), and an ungrouped
    find's plain read when called on the top-level ``port``."""
    rows: list[Row] = []
    for statement in statements:
        rows = port.execute(dialect.to_driver_sql(statement.sql), _driver_binds(statement.binds))
    return rows


# --------------------------------------------------------------------------- #
# Conflict — the optimistic-lock run lane (m-opt-lock; COR-3 Phase 8           #
# increment 4, DQ4 re-route). Single-attempt (`when.write`) and retry          #
# (`when.attempts`) forms both drive ONE `db.transact` call per attempt        #
# (ledger D-18). A non-temporal attempt (the increment-3 versioned keyed       #
# UPDATE) buffers through the neutral `Transaction._buffer` route, exactly     #
# like any other keyed write; a TEMPORAL attempt (`m-txtime-write` /            #
# `m-bitemp-write`) composes `handle.lower_temporal_close` directly — a        #
# conflict case tests ONLY the close, never a chain, a shape no REAL temporal  #
# mutation verb produces on its own.                                          #
# --------------------------------------------------------------------------- #
def _apply_given_apply(case: case_format.Case, dialect: Dialect, port: DbPort) -> None:
    """Apply a conflict case's out-of-band ``given.apply`` naive statements
    VERBATIM, immediately (never inside our own transaction) — they simulate a
    CONCURRENT transaction that already committed, so they must survive our
    own unit of work's eventual rollback (a stale-version conflict)."""
    given = case.document.get("given")
    if not isinstance(given, Mapping):
        return
    entries = cast("Mapping[str, object]", given).get("apply")
    if not isinstance(entries, list):
        return
    for entry in cast("list[Mapping[str, object]]", entries):
        sql = cast("str", entry["sql"])
        binds = cast("list[object]", entry.get("binds", []))
        port.execute_write(dialect.to_driver_sql(sql), _driver_binds(binds))


def _conflict_target(meta: Metamodel) -> str:
    """The entity a conflict case's write targets, when ``when.write`` carries no
    explicit reference (`m-case-format`: a conflict case's write names no
    entity of its own). For a plain model this is its SOLE entity — the same
    convention :func:`_rejected_target` uses. For an inheritance family
    (`m-inheritance-105`'s TPH composed conflict) writes are concrete-subtype
    only (`m-inheritance` "Concrete-subtype writes"), never the abstract root
    :func:`_rejected_target` resolves to for the REJECTED lane's DIFFERENT
    default-target convention — this resolves to the family's SOLE concrete
    subtype (every reachable temporal-inheritance conflict model declares
    exactly one)."""
    family = inheritance.family_of(meta)
    if family.root is None:
        return meta.entities[0].name
    concretes = sorted(
        entity.name
        for entity in family.participants
        if entity.inheritance is not None and entity.inheritance.role == "concrete-subtype"
    )
    if len(concretes) != 1:
        raise EngineError(  # pragma: no cover - no witnessed conflict model is ambiguous
            f"a conflict case's model declares {len(concretes)} concrete subtypes "
            f"{concretes!r}; the target is ambiguous without an explicit reference"
        )
    return concretes[0]


def _identity_key(
    meta: Metamodel, entity_name: str, row: Mapping[str, object]
) -> tuple[tuple[str, object], ...]:
    pk_names = [
        attr.name for attr in inheritance.family_primary_key(meta, meta.entity(entity_name))
    ]
    return tuple((name, row[name]) for name in pk_names)


def _lower_conflict_write(
    meta: Metamodel,
    dialect: Dialect,
    target: str,
    concurrency: Concurrency,
    write_row: Mapping[str, object],
) -> tuple[Statement, ...]:
    """PURE-lower one NON-TEMPORAL conflict attempt's ``write`` row: strip its
    reserved ``observedVersion`` into an :class:`Observation` (`m-opt-lock`;
    ADR 0013), plan the single-instruction buffer, and lower it. A
    non-temporal conflict's write is always a versioned keyed UPDATE
    (`m-case-format`: "an optimistic-lock UPDATE") — a temporal close's own
    conflict form (`handle.lower_temporal_close`) is a distinct shape."""
    clean_row, observation = _strip_observation(write_row)
    instruction = instructions.deserialize(
        {"mutation": "update", "entity": target, "rows": [clean_row]}
    )
    instructions.validate_instruction(instruction, meta)
    observations: dict[ObjectKey, Observation] = {}
    if observation is not None:
        key = object_key(instruction, meta)
        if key is not None:
            observations[key] = observation
    plan = plan_flush([instruction], observations, _INERT_CLOCK_INSTANT, meta)
    statements: list[Statement] = []
    for planned in plan.writes:
        statements.extend(
            lowered.statement
            for lowered in lower_write(planned, meta, dialect, concurrency, _INERT_CLOCK_INSTANT)
        )
    return tuple(statements)


def _run_conflict_write(
    port: DbPort,
    dialect: Dialect,
    meta: Metamodel,
    target: str,
    concurrency: Concurrency,
    write_row: Mapping[str, object],
) -> tuple[tuple[Statement, ...], int]:
    """Lower and execute one NON-TEMPORAL conflict attempt's write through
    ``db.transact`` (COR-3 Phase 8 increment 4, DQ4 re-route) — ONE
    transaction, an inert Clock (never consumed by a non-temporal write).
    Buffers through the neutral ``Transaction._buffer`` route +
    ``UnitOfWork.observe``; the PRODUCTION flush executor's OWN
    ``expected_affected`` check raises :class:`~parallax.core.opt_lock.
    OptimisticLockConflictError` on a mismatch (unchanged from increment 3),
    which this lane catches and renders as the ``0`` ``affectedRows``
    observation."""
    statements = _lower_conflict_write(meta, dialect, target, concurrency, write_row)
    clean_row, observation = _strip_observation(write_row)
    instant = normalize_instant(dt.datetime.fromisoformat(_INERT_CLOCK_INSTANT))
    database = handle.Database(port, meta, dialect=dialect, clock=FixedClock(instant))

    def body(tx: handle.Transaction) -> int:
        instruction = instructions.deserialize(
            {"mutation": "update", "entity": target, "rows": [clean_row]}
        )
        if observation is not None:
            key = object_key(instruction, meta)
            if key is not None:
                # The documented neutral seam (Transaction._buffer route + uow.observe).
                tx._uow.observe(key, observation)  # pyright: ignore[reportPrivateUsage]
        tx._buffer("update", target, clean_row)  # pyright: ignore[reportPrivateUsage]
        return 1  # the expectation machinery already verified this on success (m-opt-lock)

    try:
        affected = database.transact(body, concurrency=concurrency)
    except opt_lock.OptimisticLockConflictError as exc:
        affected = exc.actual
    return statements, affected


def _run_conflict_close(
    port: DbPort,
    dialect: Dialect,
    meta: Metamodel,
    target: str,
    concurrency: Concurrency,
    write_row: Mapping[str, object],
    at: str,
    observed_tx_start: str | None,
) -> tuple[tuple[Statement, ...], int]:
    """Lower and execute one TEMPORAL conflict attempt's close through
    ``db.transact`` (COR-3 Phase 8 increment 4, DQ4 re-route) — ONE
    transaction, ``clock=FixedClock(at)``. Composes
    :func:`~parallax.snapshot.handle.lower_temporal_close` directly (a
    conflict case's own close-only probe, never a REAL chaining mutation) and
    executes it on the transaction's own connection — a standalone close has
    nothing to coalesce or FK-order with, so it bypasses the buffer/flush
    pipeline entirely. ``observed_tx_start`` / the write row's own ``valid_start``
    (the bitemporal Valid-Time discriminator) are the case's EXPLICIT authored
    fields (`when.observedTxStart` / `when.write.valid_start`) — never a
    shadow-tracker lookup, a conflict case tests a KNOWN stale-or-fresh value.
    """
    row = dict(write_row)
    observed_valid_start = cast("str | None", row.pop("valid_start", None))
    lowered = handle.lower_temporal_close(
        row, target, meta, dialect, concurrency, at, observed_tx_start, observed_valid_start
    )
    instant = normalize_instant(dt.datetime.fromisoformat(at))
    database = handle.Database(port, meta, dialect=dialect, clock=FixedClock(instant))

    def body(tx: handle.Transaction) -> int:
        # The neutral connection seam.
        affected = tx._conn.execute_write(  # pyright: ignore[reportPrivateUsage]
            dialect.to_driver_sql(lowered.statement.sql), list(lowered.statement.binds)
        )
        if lowered.expected_affected is not None and affected != lowered.expected_affected:
            # Shared classification (`parallax.core.opt_lock.classify_mismatch`):
            # the SAME gate/mode-driven decision `parallax.snapshot.handle`'s own
            # flush executor applies, so the two callers can never disagree on
            # which error class a mismatch raises.
            raise opt_lock.classify_mismatch(
                target,
                _identity_key(meta, target, row),
                lowered.expected_affected,
                affected,
                stale_error=lowered.stale_error,
            )
        return affected

    try:
        affected = database.transact(body, concurrency=concurrency)
    except (opt_lock.OptimisticLockConflictError, opt_lock.StaleWriteError) as exc:
        affected = exc.actual
    return (lowered.statement,), affected


def run_conflict_case(
    case: case_format.Case, dialect_name: str, port: DbPort
) -> tuple[list[Emission], int, dict[str, list[Row]] | None]:
    """Run a `conflict` case (`m-opt-lock` / `m-txtime-write` / `m-bitemp-write`):
    the single-attempt form (`when.write`), or the `when.attempts` retry
    sequence — each attempt its OWN `db.transact` unit (COR-3 Phase 8
    increment 4, DQ4 re-route), in order, each with its own statements /
    affected-row count (the case's own `0`-then-`1` retry-contract witness). A
    NON-temporal target (`m-opt-lock`'s own versioned keyed UPDATE, unchanged
    from increment 3) buffers through the neutral `Transaction._buffer` route;
    a TEMPORAL target composes `handle.lower_temporal_close` directly.

    Loads no fixtures itself (the caller's own lifecycle does, per
    `m-case-format`'s conflict-shape default); applies `given.apply` verbatim
    and out-of-band FIRST (the concurrent writer, `_apply_given_apply`).
    Returns the ordered emissions, the FINAL (single-attempt or last-retry)
    affected-row count — the schema's one `affectedRows` slot,
    `m-conformance-adapter` — and the resulting table state when the case
    authors `then.tableState`.
    """
    meta = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    when = _when(case)
    concurrency = _concurrency(case)
    target = _conflict_target(meta)
    is_temporal = _is_temporal_entity(meta, target)
    emissions: list[Emission] = []
    affected = 0
    try:
        _apply_given_apply(case, dialect, port)
        attempts = when.get("attempts")
        if isinstance(attempts, list):
            for index, attempt in enumerate(cast("list[Mapping[str, object]]", attempts)):
                write_row = cast("Mapping[str, object]", attempt["write"])
                if is_temporal:
                    at = cast("str", attempt["at"])
                    observed_tx_start = cast("str | None", attempt.get("observedTxStart"))
                    statements, affected = _run_conflict_close(
                        port, dialect, meta, target, concurrency, write_row, at, observed_tx_start
                    )
                else:
                    statements, affected = _run_conflict_write(
                        port, dialect, meta, target, concurrency, write_row
                    )
                emissions.extend(
                    Emission(f"/when/attempts/{index}/write", s.sql, s.binds) for s in statements
                )
        else:
            write_row = cast("Mapping[str, object]", when["write"])
            if is_temporal:
                at = cast("str", when["at"])
                observed_tx_start = cast("str | None", when.get("observedTxStart"))
                statements, affected = _run_conflict_close(
                    port, dialect, meta, target, concurrency, write_row, at, observed_tx_start
                )
            else:
                statements, affected = _run_conflict_write(
                    port, dialect, meta, target, concurrency, write_row
                )
            emissions.extend(Emission("/when/write", s.sql, s.binds) for s in statements)
    except _LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    then = case.document.get("then")
    table_state = (
        read_table_state(port, meta, dialect)
        if isinstance(then, Mapping) and "tableState" in then
        else None
    )
    return emissions, affected, table_state


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
    (``errorClass`` / ``nativeCode``). Round trips count every executed trigger
    statement, including the raising one. A ``when.concurrency`` trigger needs
    two barrier-synchronized sessions this single-connection lane cannot drive
    at all — it is refused here UNCONDITIONALLY, never dispatched to from a
    caller that owns two sessions (COR-3 Phase 8 increment 6:
    ``m-read-lock-006`` is graded by the CASE-DRIVEN two-session rounds
    runner instead, ``parallax.conformance.concurrency_runner`` — this
    module's own dispatcher (`tests/conformance/test_run_sweep.py`) routes it
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
    final = len(trigger) - 1
    for index, (sql, binds) in enumerate(trigger):
        emissions.append(Emission(f"/then/statements/{index}", sql, binds))
        try:
            port.execute_write(dialect.to_driver_sql(sql), _driver_binds(binds))
        except DatabaseError as exc:
            if index != final:
                raise EngineError(
                    f"{case.path.name}: trigger statement {index} raised before the final "
                    f"statement: {exc}"
                ) from exc
            if exc.category is None or exc.native_code is None:
                raise EngineError(
                    f"{case.path.name}: the trigger raised an unclassified database error: {exc}"
                ) from exc
            return emissions, exc.category, exc.native_code, len(trigger)
    raise EngineError(f"{case.path.name}: the final trigger statement did not raise")


# --------------------------------------------------------------------------- #
# Rejected — the pre-SQL model-aware validation lane (m-case-format, COR-3     #
# Phase 7 increment 1: resolved DQ3/DQ8).                                      #
# --------------------------------------------------------------------------- #
def _rejected_target(meta: Metamodel) -> str:
    """The queried/written root a `rejected` case's `when` omits.

    A `rejected` case never authors `targetEntity` (m-case-format schema), and a
    `when.write` input carries no explicit handle either: the model-aware
    default `m-op-algebra` "the four-step validation rule" fixes is the
    inheritance family root when the model declares one, else the model's own
    first entity. For a `when.operation` case this seeds `validate_operation`'s
    narrow / subtype-attribute position tracking only (the value-object
    structural rules resolve their own entity from each node's own
    `Class.member` reference and do not otherwise depend on it); for a
    `when.write` case it is the entity `validate_write` checks the payload
    against — the same "no explicit handle, so resolve the model's default
    write/read root" convention, reused rather than restated (COR-3 Phase 8
    increment 2).
    """
    root = inheritance.family_of(meta).root
    if root is not None:
        return root.name
    return meta.entities[0].name


# The `rejected` shape's schema `oneOf`: exactly one of these keys, never zero
# or more than one (m-case-format).
_REJECTED_WHEN_KINDS: Final[tuple[str, ...]] = ("operation", "model", "write")


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
            f"`when.operation` / `when.model` / `when.write` (m-case-format schema "
            f"`oneOf`); found {present!r}"
        )
    return present[0]


def run_rejected_case(case: case_format.Case) -> str:
    """Grade a `rejected` case's pre-SQL refusal, returning the classified rule.

    A `rejected` case carries EXACTLY ONE of `when.operation` / `when.model` /
    `when.write` (m-case-format schema `oneOf`) — enforced by
    :func:`_rejected_when_kind` before dispatch, since the schema `oneOf` cannot
    protect a caller that reaches this engine without schema validation. An
    `operation` input is deserialized through the same `m-op-algebra` serde
    every read uses, then checked by the shared `validate_operation`
    (`m-op-algebra` / `m-navigate` / `m-value-object`) — the same validator an
    idiomatic statement frontend calls at build time, so the two paths cannot
    drift. A `model` input reuses the Phase-3 `m-inheritance` family-invariant
    validator unchanged. A `write` input (COR-3 Phase 8 increment 2) is
    resolved against the model's default entity (`_rejected_target`'s own
    convention, reused here — the family root when the model declares one,
    else the model's single entity, since a rejected `when.write` carries no
    explicit handle) and checked by the shared `validate_write`
    (`m-value-object` write validation x `m-inheritance` concrete-subtype
    write protocol) — the SAME validator the developer transaction verbs call
    at buffer time (`Transaction._buffer`), so the two paths cannot drift.
    Raises :class:`EngineError` if the input is unexpectedly accepted (no rule
    violation detected) — the caller compares the returned rule against the
    case's `then.rejectedRule`.
    """
    when = _when(case)
    kind = _rejected_when_kind(case, when)
    meta = load_case_metamodel(case)
    if kind == "operation":
        try:
            operation = deserialize(when["operation"])
        except OperationError as exc:
            raise EngineError(f"{case.path.name}: {exc}") from exc
        target = _rejected_target(meta)
        try:
            validate_op_algebra_operation(target, operation, meta)
        except OperationRejectedError as exc:
            return exc.rule
        raise EngineError(
            f"{case.path.name}: the model-aware validator accepted an operation the case "
            "expects rejected pre-SQL"
        )
    if kind == "model":
        inline_model = cast("Mapping[str, object]", when["model"])
        try:
            inline_meta = deserialize_metamodel(inline_model)
        except DescriptorError as exc:
            raise EngineError(f"{case.path.name}: {exc}") from exc
        try:
            inheritance.validate(inline_meta)
        except inheritance.InheritanceError as exc:
            return exc.rule
        raise EngineError(
            f"{case.path.name}: the model-aware validator accepted an inline inheritance "
            "family the case expects rejected pre-SQL"
        )
    row = cast("Mapping[str, object]", when["write"])
    target = meta.entity(_rejected_target(meta))
    try:
        validate_write(target, row, meta)
    except WriteRejectedError as exc:
        return exc.rule
    raise EngineError(
        f"{case.path.name}: the model-aware validator accepted a write the case expects "
        "rejected pre-SQL"
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


def wire_row(row: Row) -> Row:
    """Render every managed value of one observed row to canonical wire form."""
    return {key: wire_value(value) for key, value in row.items()}
