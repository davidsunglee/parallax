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
from typing import cast

from parallax.conformance import case_format, models
from parallax.core.base import INFINITY_LITERAL, TemporalBound, normalize_instant
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import DbPort, JsonDocument, Row
from parallax.core.descriptor import Metamodel
from parallax.core.dialect import Dialect, dialect_for
from parallax.core.op_algebra import OperationError, deserialize
from parallax.core.sql_gen import ResultForm, SqlGenError, Statement, compile_read
from parallax.core.temporal_read import TemporalReadError, inject_as_of
from parallax.core.unit_work import instructions, plan_flush
from parallax.core.unit_work.instructions import WriteInstruction
from parallax.snapshot.handle import WriteLoweringError, lower_write

__all__ = [
    "Emission",
    "EngineError",
    "RunOnly",
    "compile_read_case",
    "compile_scenario_case",
    "compile_write_sequence_case",
    "eligibility",
    "load_case_metamodel",
    "run_error_case",
    "run_read_case",
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


def _compile_statement(case: case_format.Case, dialect_name: str) -> tuple[str, Statement]:
    if case.shape != "read":
        raise EngineError(
            f"{case.path.name}: only `read`-shape compile is implemented (COR-3 Phase 5 scope; "
            f"shape={case.shape})"
        )
    target, operation_doc = _read_target_and_operation(case)
    meta = load_case_metamodel(case)
    dialect = dialect_for(dialect_name)
    try:
        # Temporal reads are lowered by m-temporal-read (the auto-injected as-of
        # predicate, defaulted-latest on omitted axes) BEFORE m-sql compiles the
        # resulting plain predicate: the module DAG forbids m-sql from importing
        # m-temporal-read, so this composition site (the conformance engine, which
        # may reference both) is the canonicalize step. `inject_as_of` is a strict
        # identity for a non-temporal target.
        operation = inject_as_of(deserialize(operation_doc), meta.entity(target))
        statement = compile_read(operation, meta, dialect, target, result_form=_result_form(case))
    except (OperationError, SqlGenError, TemporalReadError, KeyError) as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    return target, statement


def compile_read_case(case: case_format.Case, dialect_name: str) -> tuple[list[Emission], int]:
    """Compile a read case to its ordered emissions and round-trip count."""
    _target, statement = _compile_statement(case, dialect_name)
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
    """
    _target, statement = _compile_statement(case, dialect_name)
    dialect = dialect_for(dialect_name)
    managed = port.execute(dialect.to_driver_sql(statement.sql), _driver_binds(statement.binds))
    emission = Emission("/operation", statement.sql, statement.binds)
    return [emission], [wire_row(row) for row in managed], 1


def _driver_binds(binds: Sequence[object]) -> list[object]:
    return list(binds)


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

# The lowering failures the write lanes convert to a neutral :class:`EngineError`,
# so the adapter reports a ``*-failed`` diagnostic rather than leaking a lower-layer
# exception type across the conformance seam.
_LOWERING_ERRORS: tuple[type[Exception], ...] = (
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
    operation = inject_as_of(deserialize(find_doc), meta.entity(target))
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


def compile_scenario_case(case: case_format.Case, dialect_name: str) -> tuple[list[Emission], int]:
    """Compile a scenario case to its ordered per-step emissions and round-trip count."""
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
) -> tuple[list[Emission], int]:
    """Run a writeSequence: execute the whole (FK-ordered) sequence in one transaction,
    then report the ordered per-entry emissions and total round trips."""
    dialect = dialect_for(dialect_name)
    lowered = _write_sequence_lowered(case, dialect_name)
    flat = [statement for _pointer, statements in lowered for statement in statements]

    def body(tx: DbPort) -> None:
        for statement in flat:
            tx.execute_write(dialect.to_driver_sql(statement.sql), _driver_binds(statement.binds))

    port.transaction(body)
    emissions = _emissions(lowered)
    return emissions, len(emissions)


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
