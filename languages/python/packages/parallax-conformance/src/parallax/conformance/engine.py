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

from parallax.conformance import case_format, models
from parallax.core import inheritance, navigate
from parallax.core.base import INFINITY_LITERAL, TemporalBound, normalize_instant
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import DbPort, JsonDocument, Row
from parallax.core.descriptor import DescriptorError, Entity, Metamodel, column_order
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
from parallax.core.unit_work import instructions, plan_flush
from parallax.core.unit_work.instructions import WriteInstruction
from parallax.snapshot import materialize
from parallax.snapshot.handle import WriteLoweringError, find, find_history, lower_write

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
# path. A **writeSequence** lowers each entry independently (no cross-entry
# coalescing — an insert-then-delete pair across two entries is two round trips, not
# a cancellation) and executes the whole sequence in one transaction.
#
# This engine-local choreography still drives ``plan_flush``/``lower_write``
# directly rather than the shipped ``db.transact`` entry points — the one-engine
# end state (design 30) re-routes it through the production developer surface;
# deferred to Phase 8's write-side re-route, ledger D-18.

# The lowering failures the write lanes convert to a neutral :class:`EngineError`,
# so the adapter reports a ``*-failed`` diagnostic rather than leaking a lower-layer
# exception type across the conformance seam.
_LOWERING_ERRORS: Final[tuple[type[Exception], ...]] = (
    instructions.WriteInstructionError,
    WriteLoweringError,
    OperationError,
    SqlGenError,
    TemporalReadError,
    KeyError,
    TypeError,
)


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


def _build_instruction(entry: Mapping[str, object], meta: Metamodel) -> WriteInstruction:
    """Build one canonical keyed write instruction from a case write entry.

    A write entry carries the instruction triple (``mutation`` / ``entity`` / ``rows``)
    beside case-authoring keys (``note`` / ``statements`` / ``roundTrips`` / ``rollback``);
    only the triple is handed to the ``m-unit-work`` deserializer, then member-name
    validated against the metamodel.
    """
    doc = {"mutation": entry["mutation"], "entity": entry["entity"], "rows": entry["rows"]}
    instruction = instructions.deserialize(doc)
    instructions.validate_instruction(instruction, meta)
    return instruction


def _lower_writes(
    entries: Sequence[Mapping[str, object]], meta: Metamodel, dialect: Dialect
) -> tuple[Statement, ...]:
    """Plan one write buffer (coalesce / FK-order / elide) and lower each survivor."""
    buffer = [_build_instruction(entry, meta) for entry in entries]
    plan = plan_flush(buffer, {}, None, meta)
    statements: list[Statement] = []
    for planned in plan.writes:
        statements.extend(lower_write(planned, meta, dialect))
    return tuple(statements)


def _lower_find(step: Mapping[str, object], meta: Metamodel, dialect: Dialect) -> Statement:
    """Compile a scenario ``find`` step through the read path with the read-lock suffix.

    A scenario find is an in-transaction object find; the reachable keyed cases run in
    the default ``locking`` unit-of-work concurrency, which renders the ``m-sql``
    shared-row-lock suffix (``for share of t0``) after every clause — matching every
    scenario golden. Deriving the suffix from an explicit ``optimistic`` step (which
    suppresses it) lands with the optimistic-lock write path (COR-3 Phase 8), when
    such a scenario first becomes reachable.
    """
    target = step.get("targetEntity")
    find_doc = step.get("find")
    if not isinstance(target, str) or find_doc is None:
        raise EngineError("scenario find step needs `targetEntity` and `find`")
    operation = _canonicalize_read(find_doc, meta.entity(target), meta)
    return compile_read(operation, meta, dialect, target, result_form="row", lock="locking")


def _scenario_lowered(case: case_format.Case, dialect_name: str) -> list[_LoweredStep]:
    """Lower every scenario step to its pointer + DML — pure (no database)."""
    meta = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    lowered: list[_LoweredStep] = []
    try:
        for index, step in enumerate(_scenario_steps(case)):
            if "write" in step:
                entries = cast("Sequence[Mapping[str, object]]", step["write"])
                statements = _lower_writes(entries, meta, dialect)
                rollback = step.get("rollback") is True
                lowered.append(_LoweredStep(f"/scenario/{index}/write", statements, True, rollback))
            else:
                statement = _lower_find(step, meta, dialect)
                lowered.append(_LoweredStep(f"/scenario/{index}/find", (statement,), False, False))
    except _LOWERING_ERRORS as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    return lowered


def _write_sequence_lowered(
    case: case_format.Case, dialect_name: str
) -> list[tuple[str, tuple[Statement, ...]]]:
    """Lower each writeSequence entry independently to ``(pointer, statements)`` — pure."""
    meta = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    try:
        return [
            (f"/writeSequence/{index}", _lower_writes([entry], meta, dialect))
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


def run_scenario_case(
    case: case_format.Case, dialect_name: str, port: DbPort
) -> tuple[list[Emission], int]:
    """Run a scenario: each write step commits (or aborts) as one unit of work, each
    find reads committed state. Reports the ordered emissions and total round trips."""
    steps = _scenario_steps(case)
    if _has_action_step(steps):
        return _run_snapshot_scenario(case, dialect_name, port, steps)
    dialect = dialect_for(dialect_name)
    lowered = _scenario_lowered(case, dialect_name)
    for step in lowered:
        if step.is_write:
            _execute_writes(port, dialect, step.statements, rollback=step.rollback)
        else:
            _execute_reads(port, dialect, step.statements)
    emissions = _emissions([(step.pointer, step.statements) for step in lowered])
    return emissions, len(emissions)


def run_write_sequence_case(
    case: case_format.Case, dialect_name: str, port: DbPort
) -> tuple[list[Emission], dict[str, list[Row]], int]:
    """Run a writeSequence: execute the whole (FK-ordered) sequence in one transaction,
    then report the ordered per-entry emissions, the committed table state, and the
    total round trips.

    The table read-back is the `m-conformance-adapter` write-sequence observation
    ("write-sequence cases report ``tableState``"): the runner grades it against
    the case's ``then.tableState``. Observation reads are not case round trips.
    """
    dialect = dialect_for(dialect_name)
    lowered = _write_sequence_lowered(case, dialect_name)
    flat = [statement for _pointer, statements in lowered for statement in statements]

    def body(tx: DbPort) -> None:
        for statement in flat:
            tx.execute_write(dialect.to_driver_sql(statement.sql), _driver_binds(statement.binds))

    port.transaction(body)
    emissions = _emissions(lowered)
    table_state = read_table_state(port, load_case_metamodel(case), dialect)
    return emissions, table_state, len(emissions)


def read_table_state(port: DbPort, meta: Metamodel, dialect: Dialect) -> dict[str, list[Row]]:
    """The committed contents of every model table, in canonical wire form.

    Each row-owning table is read back with every physical column in descriptor
    ``columnOrder`` (a shared table is read once), so the observation reports
    exactly the state ``then.tableState`` asserts — derived from the metamodel,
    never from the case's expectations.
    """
    state: dict[str, list[Row]] = {}
    for entity in meta.entities:
        if entity.table is None or entity.table in state:
            continue
        columns = ", ".join(dialect.quote(column) for column in column_order(entity))
        sql = f"select {columns} from {dialect.quote(entity.table)}"
        rows = port.execute(dialect.to_driver_sql(sql), [])
        state[entity.table] = [wire_row(row) for row in rows]
    return state


def _execute_reads(port: DbPort, dialect: Dialect, statements: Sequence[Statement]) -> None:
    for statement in statements:
        port.execute(dialect.to_driver_sql(statement.sql), _driver_binds(statement.binds))


def _execute_writes(
    port: DbPort, dialect: Dialect, statements: Sequence[Statement], *, rollback: bool
) -> None:
    """Execute a write step's DML as one transaction; ``rollback`` aborts after emitting.

    The step's coalesced DML runs inside one ``m-db-port`` transaction and commits. A
    ``rollback: true`` step raises the :class:`_RollbackStep` sentinel after the DML has
    executed (and counted its round trips), so the port rolls the transaction back — the
    write is applied then discarded, never durable (``m-unit-work`` abort).
    """

    def body(tx: DbPort) -> None:
        for statement in statements:
            tx.execute_write(dialect.to_driver_sql(statement.sql), _driver_binds(statement.binds))
        if rollback:
            raise _RollbackStep

    with contextlib.suppress(_RollbackStep):
        port.transaction(body)


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
    """The queried root a `rejected` operation case's `when` omits.

    A `rejected` case never authors `targetEntity` (m-case-format schema): the
    model-aware default `m-op-algebra` "the four-step validation rule" fixes is
    the inheritance family root when the model declares one, else the model's
    own first entity. This seeds `validate_operation`'s narrow / subtype-
    attribute position tracking only; the value-object structural rules
    resolve their own entity from each node's own `Class.member` reference and
    do not otherwise depend on it.
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
    validator unchanged. A `write` input is Phase-8 territory (ledger D-12): it
    raises a lane-honest :class:`EngineError` naming the deferral so the case
    stays reasoned-skipped rather than silently graded wrong. Raises
    :class:`EngineError` if the input is unexpectedly accepted (no rule
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
    raise EngineError(
        f"{case.path.name}: write-validation rejected cases (m-value-object "
        "required-attribute / type-mismatch checks, m-inheritance subtype-write "
        "protocol checks) are Phase 8 territory (COR-3 Phase 7; ledger D-12); the "
        "read-side rejected lane does not grade `when.write` inputs yet"
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
