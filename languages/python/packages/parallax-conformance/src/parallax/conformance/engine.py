"""The conformance compile/run engine — binding the corpus to the spine.

The adapter path compiles and runs a compatibility case directly against the
class-free engine spine (no dynamic class synthesis): the case's model YAML is
ingested through the ``m-descriptor`` deserializer, its ``when.operation`` through
the ``m-op-algebra`` deserializer, and the tree is lowered by ``m-sql``
``compile_read`` to one canonical ``Statement``. ``compile`` emits that statement;
``run`` executes it through the injected ``m-db-port`` and records the observed
rows. Compile eligibility (``m-case-format`` ``compileEligibility``) is read from
the case; the run-only minority is never compiled.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import decimal
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

from parallax.conformance import case_format, models, provision, temporal_state
from parallax.conformance.temporal_state import TemporalShadow
from parallax.core import inheritance, navigate, opt_lock
from parallax.core.base import INFINITY_LITERAL, TemporalBound, normalize_instant
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import DbPort, JsonDocument, Row
from parallax.core.descriptor import Attribute, DescriptorError, Entity, Metamodel, column_order
from parallax.core.descriptor import deserialize as deserialize_metamodel
from parallax.core.dialect import Dialect, dialect_for
from parallax.core.op_algebra import Operation, OperationError, OperationRejectedError, deserialize
from parallax.core.op_algebra import validate_operation as validate_op_algebra_operation
from parallax.core.sql_gen import (
    ResultForm,
    SqlGenError,
    Statement,
    apply_family_variant,
    compile_read,
    family_variant_plan,
)
from parallax.core.temporal_read import TemporalReadError, inject_as_of, resolve_pinned_instants
from parallax.core.unit_work import (
    Concurrency,
    FixedClock,
    KeyedWrite,
    ObjectKey,
    Observation,
    WriteRejectedError,
    instructions,
    object_key,
    plan_flush,
    validate_write,
)
from parallax.core.unit_work.instructions import WriteInstruction
from parallax.snapshot import handle, materialize
from parallax.snapshot.handle import (
    WriteLoweringError,
    find,
    find_history,
    lower_write,
    predicate_write_refusal,
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
    carrier (m-db-port); on the wire it is its underlying JSON document. Every other keyed
    bind is already JSON-native (scalars; a date rides as the write-input string).
    """
    if isinstance(bind, JsonDocument):
        return bind.value
    return bind


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


def _result_form(case: case_format.Case) -> ResultForm:
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


def _compile_statement(
    case: case_format.Case, dialect_name: str
) -> tuple[str, Statement, Metamodel, Operation]:
    if case.shape != "read":
        raise EngineError(
            f"{case.path.name}: only `read`-shape compile is implemented (COR-3 Phase 5 scope; "
            f"shape={case.shape})"
        )
    target, operation_doc = _read_target_and_operation(case)
    meta = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    try:
        operation = _canonicalize_read(operation_doc, meta.entity(target), meta)
        statement = compile_read(operation, meta, dialect, target, result_form=_result_form(case))
    except (OperationError, SqlGenError, TemporalReadError, KeyError) as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    return target, statement, meta, operation


def compile_read_case(case: case_format.Case, dialect_name: str) -> tuple[list[Emission], int]:
    """Compile a read case to its ordered emissions and round-trip count."""
    _target, statement, _meta, _operation = _compile_statement(case, dialect_name)
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
    additionally materializes `familyVariant` into each wire row from the read's
    `~parallax.core.sql_gen.family_variant_plan`: a table-per-hierarchy read
    derives it from the projected raw tag column via the tag-metadata map (the
    tag column itself is popped, never left on the wire row); a table-per-
    concrete-subtype read renames its projected `family_variant` literal column.
    A concrete-target (or single-resolved-position TPCS) read carries neither.
    """
    target, statement, meta, operation = _compile_statement(case, dialect_name)
    dialect = dialect_for(dialect_name)
    managed = port.execute(dialect.to_driver_sql(statement.sql), _driver_binds(statement.binds))
    emission = Emission("/operation", statement.sql, statement.binds)
    plan = family_variant_plan(meta, target, operation)
    rows = [apply_family_variant(wire_row(row), plan) for row in managed]
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
# unit), so a fixed, deterministic instant stands in (`m-audit-write` / ADR 0010:
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


def _strip_observation(row: Mapping[str, object]) -> tuple[dict[str, object], Observation | None]:
    """Strip a case writeRow's reserved ``observedVersion`` / ``observedInZ``
    control keys (`m-opt-lock`; ADR 0013), returning the DURABLE row (never
    carrying them — the write-instruction schema forbids both,
    `instructions.deserialize` enforces it) and the :class:`Observation` they
    describe (``None`` when the row carries neither — an unobserved write, or
    one whose observation instead comes from this SAME `uow` group's own
    prior find step, consulted separately via :data:`ScenarioObservations`)."""
    clean = dict(row)
    version = clean.pop("observedVersion", None)
    in_z = clean.pop("observedInZ", None)
    if version is None and in_z is None:
        return clean, None
    return clean, Observation(
        version=cast("int", version) if version is not None else None,
        in_z=cast("str", in_z) if in_z is not None else None,
    )


# An object-key -> Observation map (m-opt-lock; ADR 0013) — the same neutral
# shape a REAL `Transaction.find` populates on the production path
# (`parallax.snapshot.handle._record_observations` -> `uow.observe`).
# `_write_sequence_lowered` / `run_write_sequence_case` pass a permanently
# EMPTY instance (a writeSequence carries no find steps at all): every keyed
# write's observation there comes solely from its own row's reserved
# `observedVersion`/`observedInZ` control keys. The scenario RUN lane
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
    `parallax.snapshot.handle._record_observations` reads via
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
    builds, `parallax.snapshot.handle._record_observations` -> `uow.observe`)
    (COR-3 Phase 8 amendment-review remediation), so a later keyed write of
    the SAME object in this SAME group derives its version bind from a
    genuine transaction-scoped observation — never an oracle, never a
    scenario-wide map. Rows are always COLUMN-named here (the real
    ``port.execute`` row shape — the SAME convention
    `parallax.snapshot.handle._record_observations` reads via
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
    (m-audit-write / m-bitemp-write ``at``; ADR 0010: the Clock, never a
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
    (`m-audit-write` / `m-bitemp-write` "the engine supplies observed rows
    from case state" — never an implicit resolving read).

    Hoists the corpus's OWN axis-bound authoring convention to the canonical
    instruction-level fields (`write-instruction.schema.json`) — the case
    format authors business bounds in TWO DIFFERENT places depending on shape
    (`m-case-format` schema, ``keyedWrite`` vs the writeSequence step): a
    SCENARIO buffered write's ``businessFrom`` / ``businessTo`` are ENTRY-level
    (sibling of ``mutation`` / ``entity`` / ``rows`` — the canonical
    ``keyedWriteInstruction`` shape directly), while a WRITESEQUENCE step's
    ``businessFrom`` is ROW-embedded and its ``businessTo`` alias is the
    entry-level ``until`` (there is no entry-level ``businessFrom`` slot in
    that step schema at all). This checks entry-level first, then row-embedded,
    so it handles BOTH conventions uniformly without needing to know the
    caller's shape. A plain (unbounded) writeSequence mutation's seed row MAY
    additionally carry a literal ``businessTo: infinity`` (its own fully-open
    upper bound) — dropped, never hoisted (the schema forbids ``businessTo`` on
    an unbounded mutation; infinity IS its implicit default). Every temporal
    entry this increment reaches is single-row.

    ``unit_inserted`` is the SAME choreography unit's own running set of
    (entity, pk) pairs a PRIOR entry in this SAME buffer already inserted
    (`m-unit-work` same-transaction coalescing, `m-audit-write-008` /
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
    business_from = cast("str | None", entry.get("businessFrom"))
    if business_from is None:
        business_from = cast("str | None", row.pop("businessFrom", None))
    else:
        row.pop("businessFrom", None)  # defensive: never double-carried
    business_to_row = row.pop("businessTo", None)
    if business_to_row is not None and business_to_row != INFINITY_LITERAL:
        raise EngineError(  # pragma: no cover - no witnessed case authors this
            f"{entity_name}: an unbounded mutation's row carries a finite businessTo "
            f"{business_to_row!r}; only the literal `infinity` default is recognized"
        )
    business_to = cast("str | None", entry.get("businessTo"))
    if business_to is None:
        business_to = cast("str | None", entry.get("until"))
    doc: dict[str, object] = {"mutation": mutation, "entity": entity_name, "rows": [row]}
    if business_from is not None:
        doc["businessFrom"] = business_from
    if business_to is not None:
        doc["businessTo"] = business_to
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


_OBSERVATION_CONTROL_KEYS: Final[frozenset[str]] = frozenset({"observedVersion", "observedInZ"})


def _refuse_predicate_write_shape(entry: Mapping[str, object]) -> None:
    """Refuse a STRUCTURED PREDICATE-write instruction (`mutation` / `target` /
    optional `assignments` — `m-case-format`'s predicate-selected shape,
    e.g. ``m-batch-write-005``/``-006``) reaching the keyed-write engine seam
    — loudly, before any row indexing, deferring to `lower_write`'s own
    predicate-write refusal wording
    (`parallax.snapshot.handle.predicate_write_refusal` — the single shared
    source of truth both this pre-check and `lower_write` raise through, the
    same move as `opt_lock.classify_mismatch`). A predicate write's `target`
    names its entity/predicate; a keyed write never carries that key at all
    (`entity` + `rows` instead), so `target`'s presence (or `entity`'s
    absence) is the SHAPE signal — never inferred from a `KeyError`.
    """
    target = entry.get("target")
    entity_name = (
        cast("Mapping[str, object]", target).get("entity") if isinstance(target, Mapping) else None
    )
    raise predicate_write_refusal(entity_name)


def _write_entries(raw_write: object) -> Sequence[Mapping[str, object]]:
    """A scenario write step's own ``write`` field, normalized to its entry
    LIST — refusing loudly (:func:`_refuse_predicate_write_shape`), before any
    row indexing, when it is a single STRUCTURED PREDICATE-write instruction
    (a bare mapping, `m-case-format`'s ``target``/``predicate`` shape) rather
    than the keyed-write entry list this engine lowers. Never a bare
    ``KeyError`` from indexing a mapping as if it were a sequence — the
    reachability gap the Phase-8 mid-phase review's finding E closed
    (``m-batch-write-005``/``-006``, previously the bare ``": 0"`` skip text).
    """
    if isinstance(raw_write, Mapping):
        _refuse_predicate_write_shape(cast("Mapping[str, object]", raw_write))
    return cast("Sequence[Mapping[str, object]]", raw_write)


def _is_versioned_entity(meta: Metamodel, entity_name: str) -> bool:
    declaring = inheritance.declaring_entity(meta, meta.entity(entity_name))
    return any(attr.optimistic_locking for attr in declaring.attributes)


def _is_pk_gen_managed(meta: Metamodel, entity_name: str) -> bool:
    """Whether ``entity_name``'s (family-effective) primary key is allocated by
    a `pkGenerator` strategy other than ``none`` (`m-pk-gen`).

    A row targeting such an entity decomposes per row regardless of ITS OWN
    shape — a literal, already-resolved id from a prior registry read (the
    `sequence` strategy's own `batchSize > 1` block reservation,
    `m-pk-gen-008`..`-012`, whose rows carry plain integers, never a
    `{computed: ...}` marker) or an actual `{computed: ...}` marker (the `max`
    strategy) — because each row's own key allocation is independent and this
    seam lowers single-row keyed writes only.
    """
    entity = meta.entity(entity_name)
    pk_attrs = inheritance.family_primary_key(meta, entity)
    return any(
        attr.pk_generator is not None and attr.pk_generator.strategy != "none" for attr in pk_attrs
    )


def _rows_carry_observation_keys(raw_rows: Sequence[Mapping[str, object]]) -> bool:
    return any(_OBSERVATION_CONTROL_KEYS & row.keys() for row in raw_rows)


def _uniform_update_values(
    pk_names: frozenset[str], raw_rows: Sequence[Mapping[str, object]]
) -> bool:
    """Whether every row assigns the IDENTICAL values to its non-key columns
    (`m-batch-write` "Set-based flush": "executed once per distinct key, or as
    a single statement with an IN predicate when the new value is uniform
    across the keys") — the uniform update entry of ``m-batch-write-001``
    collapses; the non-uniform, per-distinct-key form of ``m-batch-write-002``
    decomposes (see :func:`_decomposes_per_row`).
    """
    excluded = pk_names | _OBSERVATION_CONTROL_KEYS
    assigned = [{k: v for k, v in row.items() if k not in excluded} for row in raw_rows]
    first = assigned[0]
    return all(candidate == first for candidate in assigned[1:])


def _decomposes_per_row(
    meta: Metamodel, entity_name: str, mutation: str, raw_rows: Sequence[Mapping[str, object]]
) -> bool:
    """Whether a non-temporal write entry's rows decompose into independent
    single-row instructions (mirroring what that many separate
    `Transaction.insert`/`.update`/`.delete` calls would buffer) rather than
    collapsing into ONE multi-row instruction (`m-batch-write`'s set-based
    flush collapse — the set-based lowering itself lands with a later write
    increment, so a collapsed entry reaches `lower_write`'s own multi-row
    refusal, the honest increment-5 deferral).

    Derived SEMANTICALLY from the instruction and model — mutation kind,
    versioned-ness, presence of per-row observations, and computed/allocated
    primary keys — never from the case's own authored ``statements`` count,
    which is a count-consistency ASSERTION only (`compatibility-case.schema.
    json`), never a semantics discriminator (the review finding this closes):

    - a single row is always its own instruction (no ambiguity);
    - a VERSIONED target's row carries per-row framework concerns (the
      version gate/advance) no single collapsed statement can express — every
      mutation kind decomposes (``m-batch-write-004``'s versioned per-key
      delete materialize);
    - any row authoring a reserved ``observedVersion``/``observedInZ`` control
      key is an explicit per-row-observation signal (`m-opt-lock`; ADR 0013);
    - a pk-gen-MANAGED target's INSERT decomposes — each row's own key
      allocation is independent (`m-pk-gen`'s `sequence`/`max` strategies,
      ``m-pk-gen-001``..`-012`);
    - an UPDATE whose rows assign NON-uniform values per key decomposes into
      one UPDATE per distinct key (``m-batch-write-002``); uniform values
      collapse into one `IN`-predicate statement instead
      (``m-batch-write-001``'s own update entry).

    Every other shape (unversioned, non-pk-gen-managed, no per-row observation
    keys, and — for update — uniform values) stays ONE multi-row instruction
    (``m-batch-write-001``/``-003``, ``m-value-object-045``).
    """
    if len(raw_rows) == 1:
        return True
    if _is_versioned_entity(meta, entity_name):
        return True
    if _rows_carry_observation_keys(raw_rows):
        return True
    if mutation == "insert":
        return _is_pk_gen_managed(meta, entity_name)
    if mutation == "update":
        entity = meta.entity(entity_name)
        pk_names = frozenset(attr.name for attr in inheritance.family_primary_key(meta, entity))
        return not _uniform_update_values(pk_names, raw_rows)
    return False  # delete / terminate: an unversioned target collapses to one IN-list statement


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
    `entity` key at all) refuses loudly here too
    (:func:`_refuse_predicate_write_shape`) — defensive coverage for the
    writeSequence path, which shares this function with every scenario write
    entry (the scenario `write`-field-is-itself-a-mapping shape is caught one
    layer up, by :func:`_write_entries`).

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
        _refuse_predicate_write_shape(entry)
    entity_name = cast("str", entry["entity"])
    if _is_temporal_entity(meta, entity_name):
        return [_build_temporal_instruction(entry, meta, shadow, tx_instant, unit_inserted)]
    mutation = cast("str", entry["mutation"])
    raw_rows = cast("Sequence[Mapping[str, object]]", entry["rows"])
    if not _decomposes_per_row(meta, entity_name, mutation, raw_rows):
        _check_statement_count_consistency(entry, 1)
        clean_rows = [_strip_observation(raw_row)[0] for raw_row in raw_rows]
        instruction = instructions.deserialize(
            {"mutation": mutation, "entity": entity_name, "rows": clean_rows}
        )
        instructions.validate_instruction(instruction, meta)
        return [(instruction, None, None)]
    _check_statement_count_consistency(entry, len(raw_rows))
    out: list[tuple[WriteInstruction, ObjectKey | None, Observation | None]] = []
    for raw_row in raw_rows:
        clean_row, observation = _strip_observation(raw_row)
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
    """Plan one write buffer (coalesce / FK-order / elide) and lower each
    survivor — PURE, no database."""
    buffer = [instruction for instruction, _key, _observation in resolved]
    observations: dict[ObjectKey, Observation] = {
        key: observation
        for _instruction, key, observation in resolved
        if key is not None and observation is not None
    }
    plan = plan_flush(buffer, observations, tx_instant, meta)
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


def _lower_find(
    step: Mapping[str, object], meta: Metamodel, dialect: Dialect, concurrency: Concurrency
) -> Statement:
    """Compile a scenario ``find`` step through the read path with the read-lock suffix.

    A scenario find is an in-transaction object find; ``concurrency`` (the case's
    own ``when.uow.concurrency``, unchanged since increment 3's non-temporal
    conflict lane) decides the ``m-sql`` shared-row-lock suffix (``for share of
    t0``) exactly as the production `Transaction.find` derives it from
    ``self._uow.settings.concurrency``: ``locking`` renders it after every clause;
    ``optimistic`` renders none (an optimistic-mode read takes no lock, COR-3
    Phase 8 increment 4 — the audit-write-008 / bitemp-write-014 coalescing
    witnesses are the first reachable OPTIMISTIC scenarios).
    """
    target = step.get("targetEntity")
    find_doc = step.get("find")
    if not isinstance(target, str) or find_doc is None:
        raise EngineError("scenario find step needs `targetEntity` and `find`")
    operation = _canonicalize_read(find_doc, meta.entity(target), meta)
    return compile_read(operation, meta, dialect, target, result_form="row", lock=concurrency)


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
    from its OWN row's reserved ``observedVersion``/``observedInZ`` control
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
        for index, step in enumerate(_scenario_steps(case)):
            if "write" in step:
                entries = _write_entries(step["write"])
                tx_instant = _entry_instant(entries[0])
                statements = _lower_writes(
                    entries, meta, dialect, concurrency, shadow, tx_instant, scenario_observations
                )
                rollback = step.get("rollback") is True
                lowered.append(_LoweredStep(f"/scenario/{index}/write", statements, True, rollback))
            else:
                statement = _lower_find(step, meta, dialect, concurrency)
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
    ``observedInZ`` control keys."""
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
            statement = compile_read(operation, meta, dialect, target, result_form="instance")
            emissions.append(Emission(f"/scenario/{index}/find", statement.sql, statement.binds))
    except (OperationError, SqlGenError, TemporalReadError, KeyError) as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    return emissions, len(emissions)


def _run_snapshot_scenario(
    case: case_format.Case,
    dialect_name: str,
    port: DbPort,
    steps: Sequence[Mapping[str, object]],
) -> tuple[list[Emission], int]:
    """Run a snapshot-read scenario: each find step materializes fresh neutral
    nodes through the SAME production find executor every graph read uses (no
    engine-local level loop); `mutate` applies its `set` directly to the
    referenced step's own materialized node — a plain in-memory field update,
    zero round trips, nothing at the port (m-snapshot-read closed world: a
    snapshot node is never enrolled in a unit of work, so mutating it can never
    write back)."""
    meta = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    emissions: list[Emission] = []
    round_trips = 0
    results: list[list[materialize.Node]] = []
    for index, step in enumerate(steps):
        if "action" in step:
            _apply_mutate_step(case, step, results)
            results.append([])
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
        except (OperationError, SqlGenError, TemporalReadError, KeyError) as exc:
            raise EngineError(f"{case.path.name}: {exc}") from exc
        for statement in result.execution.statements:
            emissions.append(Emission(f"/scenario/{index}/find", statement.sql, statement.binds))
        round_trips += result.execution.round_trips
        results.append(list(result.nodes))
    return emissions, round_trips


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
    override). Buffering goes through the neutral ``Transaction._buffer`` route
    + ``UnitOfWork.observe`` — never the typed instance verbs (`insert` /
    `update` / `delete`), which this engine's case-driven metamodel has no
    compiled Python classes for. A ``rollback: true`` step raises inside the
    callback (rollback-only, `m-unit-work` abort contract): the buffered DML
    still executes — and counts its round trips — before the provider rolls the
    transaction back.
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
            tx._buffer(  # pyright: ignore[reportPrivateUsage]
                instruction.mutation,
                instruction.entity,
                dict(instruction.rows[0]),
                business_from=instruction.business_from,
                business_to=instruction.business_to,
            )
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


def _scenario_uow_spans(
    case_name: str, steps: Sequence[Mapping[str, object]]
) -> dict[str, tuple[int, int]]:
    """Every declared `uow` group label's CONTIGUOUS step-index span
    ``(start, end)`` (inclusive) in this scenario (`m-case-format` scenario
    `uow` grouping). The Python run lane executes only CONTIGUOUS groups —
    every group it reaches this round is (`m-unit-work-002/005/006/009/012`);
    a genuinely INTERLEAVED group (the optimistic-lock race shape,
    `m-opt-lock-012`) stays reference-harness-only until the engine gains its
    own multi-connection seam (a later increment), so this raises loudly
    rather than silently mis-executing one."""
    labels = [step.get("uow") if isinstance(step.get("uow"), str) else None for step in steps]
    spans: dict[str, tuple[int, int]] = {}
    for label in {cast("str", entry) for entry in labels if entry is not None}:
        indices = [i for i, entry in enumerate(labels) if entry == label]
        start, end = indices[0], indices[-1]
        if indices != list(range(start, end + 1)):
            raise EngineError(
                f"{case_name}: uow group {label!r} is not contiguous — the engine's "
                "scenario run lane executes only contiguous groups (an interleaved "
                "group, the optimistic-lock race shape, is reference-harness-only "
                "today)"
            )
        spans[label] = (start, end)
    return spans


def _group_tx_instant(steps: Sequence[Mapping[str, object]], start: int, end: int) -> str:
    """The Clock instant a `uow` group's own choreography unit runs at — its
    first write entry's own instant (m-audit-write/m-bitemp-write `at`; ADR
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
                        business_from=instruction.business_from,
                        business_to=instruction.business_to,
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


def run_scenario_case(
    case: case_format.Case, dialect_name: str, port: DbPort
) -> tuple[list[Emission], int]:
    """Run a scenario: an UNGROUPED write step commits (or aborts) as its OWN
    unit of work through ``db.transact`` (COR-3 Phase 8 increment 4, DQ4
    re-route) and an ungrouped find reads committed state, exactly as before.
    A `uow`-GROUPED contiguous span of steps instead runs inside ONE
    ``db.transact`` (COR-3 Phase 8 amendment-review remediation,
    :func:`_run_uow_group`): the observing find and the versioned write it
    licenses execute in the SAME unit of work, so the write's version bind is
    a genuine transaction-scoped observation, never an oracle. Reports the
    ordered emissions and total round trips."""
    steps = _scenario_steps(case)
    if _has_action_step(steps):
        return _run_snapshot_scenario(case, dialect_name, port, steps)
    meta = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    concurrency = _concurrency(case)
    shadow = TemporalShadow()
    spans = _scenario_uow_spans(case.path.name, steps)
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
            if "write" in step:
                entries = _write_entries(step["write"])
                tx_instant = _entry_instant(entries[0])
                resolved = _resolve_entries(entries, meta, shadow, tx_instant, {})
                statements = _lower_resolved(resolved, meta, dialect, concurrency, tx_instant)
                rollback = step.get("rollback") is True
                _execute_write_unit(
                    port, meta, dialect, concurrency, resolved, tx_instant, rollback=rollback
                )
                lowered.append(_LoweredStep(f"/scenario/{index}/write", statements, True, rollback))
            else:
                statement = _lower_find(step, meta, dialect, concurrency)
                _execute_reads(port, dialect, (statement,))
                lowered.append(_LoweredStep(f"/scenario/{index}/find", (statement,), False, False))
            index += 1
    except _LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    emissions = _emissions([(step.pointer, step.statements) for step in lowered])
    return emissions, len(emissions)


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
        if entity.table is None or entity.table in state:
            continue
        table = entity.table
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
    members = sorted(
        (e for e in meta.entities if e.inheritance is not None and e.table == table),
        key=lambda e: e.name,
    )
    root = inheritance.family_root(meta, entity)
    assert root.inheritance is not None  # a resolved family root always carries one
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
            if vo.column in seen_docs:  # declares a value object yet (defensive dedup)
                continue
            seen_docs.add(vo.column)
            document_columns.append(vo.column)
    return [*pk_columns, *tag_columns, *rest_columns, *document_columns]


def _execute_reads(port: DbPort, dialect: Dialect, statements: Sequence[Statement]) -> list[Row]:
    """Execute every statement and return the LAST one's rows — a scenario find
    step is always single-statement (:func:`_lower_find`), so ``statements`` is
    always a one-tuple in practice; the raw, COLUMN-keyed rows are a GROUPED
    find's own source for :func:`_observe_group_find` (mirroring the
    production ``Transaction.find`` -> ``uow.observe`` seam, `parallax.
    snapshot.handle._record_observations`) when called on the transaction's
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
# like any other keyed write; a TEMPORAL attempt (`m-audit-write` /            #
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
    observed_in_z: str | None,
) -> tuple[tuple[Statement, ...], int]:
    """Lower and execute one TEMPORAL conflict attempt's close through
    ``db.transact`` (COR-3 Phase 8 increment 4, DQ4 re-route) — ONE
    transaction, ``clock=FixedClock(at)``. Composes
    :func:`~parallax.snapshot.handle.lower_temporal_close` directly (a
    conflict case's own close-only probe, never a REAL chaining mutation) and
    executes it on the transaction's own connection — a standalone close has
    nothing to coalesce or FK-order with, so it bypasses the buffer/flush
    pipeline entirely. ``observed_in_z`` / the write row's own ``businessFrom``
    (the bitemporal business discriminator) are the case's EXPLICIT authored
    fields (`when.observedInZ` / `when.write.businessFrom`) — never a
    shadow-tracker lookup, a conflict case tests a KNOWN stale-or-fresh value.
    """
    row = dict(write_row)
    business_from = cast("str | None", row.pop("businessFrom", None))
    lowered = handle.lower_temporal_close(
        row, target, meta, dialect, concurrency, at, observed_in_z, business_from
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
    """Run a `conflict` case (`m-opt-lock` / `m-audit-write` / `m-bitemp-write`):
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
                    observed_in_z = cast("str | None", attempt.get("observedInZ"))
                    statements, affected = _run_conflict_close(
                        port, dialect, meta, target, concurrency, write_row, at, observed_in_z
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
                observed_in_z = cast("str | None", when.get("observedInZ"))
                statements, affected = _run_conflict_close(
                    port, dialect, meta, target, concurrency, write_row, at, observed_in_z
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
    two barrier-synchronized sessions the single-connection adapter run cannot
    drive — the harness's provider choreography (and this target's provider
    deadlock proof) covers that sub-shape.
    """
    when = case.document.get("when")
    if isinstance(when, Mapping) and "concurrency" in when:
        raise EngineError(
            f"{case.path.name}: two-connection m-db-error choreography (when.concurrency) is "
            "driven by the provider contract proof, not the single-connection adapter run"
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
