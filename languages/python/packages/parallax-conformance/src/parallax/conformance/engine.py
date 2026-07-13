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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from parallax.conformance import case_format, models
from parallax.core.db_port import DbPort, Row
from parallax.core.descriptor import Metamodel
from parallax.core.dialect import dialect_for
from parallax.core.op_algebra import OperationError, deserialize
from parallax.core.sql_gen import SqlGenError, Statement, compile_read

__all__ = [
    "Emission",
    "EngineError",
    "RunOnly",
    "compile_read_case",
    "eligibility",
    "load_case_metamodel",
    "run_read_case",
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
        return {"casePointer": self.case_pointer, "sql": self.sql, "binds": list(self.binds)}


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
        statement = compile_read(deserialize(operation_doc), meta, dialect, target)
    except (OperationError, SqlGenError, KeyError) as exc:
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
    """Execute a read case through ``port`` and record its emissions and observed rows."""
    _target, statement = _compile_statement(case, dialect_name)
    dialect = dialect_for(dialect_name)
    rows = port.execute(dialect.to_driver_sql(statement.sql), _driver_binds(statement.binds))
    emission = Emission("/operation", statement.sql, statement.binds)
    return [emission], rows, 1


def _driver_binds(binds: Sequence[object]) -> list[object]:
    return list(binds)
