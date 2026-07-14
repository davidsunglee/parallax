"""The pg-full run sweep (m-conformance-adapter `run`, real Postgres).

Every exercised reachable read case is compiled, executed against a freshly reset
real database (``DROP SCHEMA … CASCADE`` → descriptor DDL → fixtures), and its
observed rows compared to the case's ``then.rows`` (order-insensitive, wire
space); its emitted SQL and binds equal the ``postgres`` golden. This is the
tracer path proven end to end — compile to canonical SQL/binds, then run against a
reset database. Docker-gated; a skip is reported, never silent (spec §6).
"""

from __future__ import annotations

from typing import Any, Final, cast

import jsonschema
import pytest
from test_compile_sweep import (
    COMPILE_EXERCISED,
    WRITE_EXERCISED,
    golden,
    wire_binds,
    write_golden_statements,
)

from conftest import adapter_schema, case_document, case_fixtures, compare_rows
from parallax.conformance import adapter, case_format, engine

pytestmark = pytest.mark.conformance

# The instance-form value-object graph reads are compile-exercised (their slot-4
# document projection matches golden), but a *run* verifies the case's asserted
# observation, and an instance-form read asserts a materialized `then.graph`. Graph
# assembly lands with the snapshot branch (COR-3 Phase 7), so these are run-deferred:
# executing only their SQL would yield a row-form observation for an instance-form
# case, verifying nothing the compile sweep does not already pin. The temporal value-
# object reads (028-031) are the same instance-form deferral, one milestone deeper.
_INSTANCE_FORM_GRAPH_READS: Final[frozenset[str]] = frozenset(
    {"m-value-object-023", "m-value-object-024"}
    | {f"m-value-object-{n:03d}" for n in (28, 29, 30, 31)}
)
# The reachable read cases whose fixtures + `then.rows` this phase runs end-to-end.
RUN_EXERCISED = frozenset(COMPILE_EXERCISED) - _INSTANCE_FORM_GRAPH_READS


def _reachable_run_cases() -> list[case_format.Case]:
    from parallax.conformance import sweep

    return [c for c in sweep.reachable_cases() if c.case_id in RUN_EXERCISED]


_CASES = _reachable_run_cases()
_SCHEMA = adapter_schema()


@pytest.mark.parametrize("case", _CASES, ids=[c.case_id for c in _CASES])
def test_run_sweep(case: case_format.Case, provisioner: Any) -> None:
    meta = engine.load_case_metamodel(case)
    from parallax.conformance import provision

    provisioner.reset(meta, provision.load_fixtures(str(case_document(case)["model"])))

    envelope = adapter.run_case(case.path, "postgres", provisioner.port)
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok", envelope

    golden_sql, golden_binds = golden(case)
    assert envelope["emissions"][0]["sql"] == golden_sql
    assert envelope["emissions"][0]["binds"] == golden_binds
    assert envelope["observations"]["roundTrips"] == 1

    expected = case_document(case).get("then", {}).get("rows")
    if expected is not None:
        compare_rows(envelope["observations"]["rows"], expected)


def _reachable_write_cases() -> list[case_format.Case]:
    from parallax.conformance import sweep

    return [c for c in sweep.reachable_cases() if c.case_id in WRITE_EXERCISED]


_WRITE_CASES = _reachable_write_cases()


class _ReadCapturePort:
    """A pass-through ``m-db-port`` decorator capturing each row-returning read.

    A scenario's per-step find rows are not adapter-envelope observations
    (m-conformance-adapter: scenario cases report ``identityChecks`` /
    ``roundTrips``), but design 22 grades every find step's wire rows against its
    ``expectRows``. Capturing at the injected port seam observes them from the
    SAME single execution the envelope reports — a scenario's finds are exactly
    its ``execute`` calls, in step order (writes go through ``execute_write`` /
    ``transaction``).
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.reads: list[list[dict[str, Any]]] = []

    def execute(self, sql: str, binds: Any) -> list[dict[str, Any]]:
        rows = self._inner.execute(sql, binds)
        self.reads.append(rows)
        return rows

    def execute_write(self, sql: str, binds: Any) -> int:
        return self._inner.execute_write(sql, binds)

    def transaction(self, body: Any) -> Any:
        return self._inner.transaction(body)


def _scenario_expect_rows(case: case_format.Case) -> list[list[dict[str, Any]] | None]:
    """Each FIND step's declared ``expectRows`` in step order (None asserts nothing)."""
    steps = cast("list[dict[str, Any]]", case_document(case)["when"]["scenario"])
    return [step.get("expectRows") for step in steps if "find" in step]


@pytest.mark.parametrize("case", _WRITE_CASES, ids=[c.case_id for c in _WRITE_CASES])
def test_write_run_sweep(case: case_format.Case, provisioner: Any) -> None:
    """Run each keyed unit-of-work write case end-to-end against a reset database.

    A scenario's writes commit (or, `rollback: true`, abort) as separate units of work
    and its finds read committed state; a writeSequence executes the whole FK-ordered
    sequence in one transaction. Grading: the envelope's per-step emissions equal the
    golden DML and its total round trips the case's `then.roundTrips`; every scenario
    find step's observed wire rows equal its `expectRows` (captured at the port seam
    from the same execution); a writeSequence's committed `tableState` observation
    equals `then.tableState`, table for table.
    """
    meta = engine.load_case_metamodel(case)
    provisioner.reset(meta, case_fixtures(case))

    port = _ReadCapturePort(provisioner.port)
    envelope = adapter.run_case(case.path, "postgres", port)
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok", envelope

    golden_statements = write_golden_statements(case)
    emissions = envelope["emissions"]
    assert len(emissions) == len(golden_statements), (case.case_id, emissions, golden_statements)
    for emission, (golden_sql, golden_binds) in zip(emissions, golden_statements, strict=True):
        assert emission["sql"] == golden_sql, (case.case_id, emission)
        assert wire_binds(emission["binds"]) == wire_binds(golden_binds), (case.case_id, emission)
    assert envelope["observations"]["roundTrips"] == case_document(case)["then"]["roundTrips"]

    if case.shape == "scenario":
        expected_per_find = _scenario_expect_rows(case)
        assert len(port.reads) == len(expected_per_find), (case.case_id, port.reads)
        for observed, expected in zip(port.reads, expected_per_find, strict=True):
            if expected is not None:
                compare_rows([engine.wire_row(row) for row in observed], expected)
    else:
        expected_state = cast(
            "dict[str, list[dict[str, Any]]]", case_document(case)["then"]["tableState"]
        )
        observed_state = envelope["observations"]["tableState"]
        assert set(observed_state) >= set(expected_state), (case.case_id, observed_state)
        for table, expected_rows in expected_state.items():
            compare_rows(observed_state[table], expected_rows)


def _reachable_error_cases() -> list[case_format.Case]:
    """The single-connection error-shape cases (statement trigger, no choreography)."""
    from parallax.conformance import sweep

    return [
        c
        for c in sweep.reachable_cases()
        if c.shape == "error" and "concurrency" not in (case_document(c).get("when") or {})
    ]


_ERROR_CASES = _reachable_error_cases()


@pytest.mark.parametrize("case", _ERROR_CASES, ids=[c.case_id for c in _ERROR_CASES])
def test_error_run_sweep(case: case_format.Case, provisioner: Any) -> None:
    """Run each single-connection m-db-error case against a reset real database.

    The authored trigger DML executes in order; the final statement raises a real
    database error at the port boundary, and the envelope's classification
    (`errorClass` / `nativeCode`) must equal the case's `then.errorClass` and
    per-dialect `then.nativeCode`. Fixtures load only when the case declares
    `given.fixtures` (the unique-violation cases self-seed via their own trigger).
    """
    meta = engine.load_case_metamodel(case)
    from parallax.conformance import provision

    doc = case_document(case)
    given = cast("dict[str, Any]", doc.get("given") or {})
    fixtures = provision.load_fixtures(str(doc["model"])) if given.get("fixtures") else {}
    provisioner.reset(meta, fixtures)

    envelope = adapter.run_case(case.path, "postgres", provisioner.port)
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok", envelope

    then = doc["then"]
    assert envelope["observations"]["errorClass"] == then["errorClass"]
    assert envelope["observations"]["nativeCode"] == then["nativeCode"]["postgres"]
    assert envelope["observations"]["roundTrips"] == len(then["statements"])
    golden_trigger = [
        (
            entry["sql"]["postgres"] if isinstance(entry["sql"], dict) else entry["sql"],
            entry.get("binds", []),
        )
        for entry in then["statements"]
    ]
    for emission, (golden_sql, golden_binds) in zip(
        envelope["emissions"], golden_trigger, strict=True
    ):
        assert emission["sql"] == golden_sql, (case.case_id, emission)
        assert emission["binds"] == golden_binds, (case.case_id, emission)
