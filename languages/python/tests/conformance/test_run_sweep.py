"""The pg-full run sweep (m-conformance-adapter `run`, real Postgres).

Every exercised reachable read case is compiled, executed against a freshly reset
real database (``DROP SCHEMA … CASCADE`` → descriptor DDL → fixtures), and its
observed rows compared to the case's ``then.rows`` (order-insensitive, wire
space); its emitted SQL and binds equal the ``postgres`` golden. This is the
tracer path proven end to end — compile to canonical SQL/binds, then run against a
reset database. Docker-gated; a skip is reported, never silent (spec §6).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
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

from conftest import adapter_schema, case_document
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


def _wire_row(row: dict[str, Any]) -> dict[str, Any]:
    # Observed rows arrive already wire-rendered; the authored `then.rows` are
    # normalized through the same m-db-port boundary so dates / uuids / bytes are
    # compared in one canonical form.
    return {key: engine.wire_value(value) for key, value in row.items()}


def _to_decimal(value: object) -> object:
    """Coerce a numeric (or a wire-rendered numeric string) to an exact ``Decimal``.

    The corpus grades numerics as exact Decimals (m-case-format), so a ``decimal``
    money column matches to the cent regardless of scale. A wire-rendered decimal
    arrives as a numeric *string* — its canonical wire form is the exact string, not
    a float — so a numeric-looking string is parsed too; a non-numeric string / date
    / uuid raises and passes through for exact ``==``.
    """
    if isinstance(value, (int, float, str)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return value
    return value


def _scalar_equal(observed: object, expected: object) -> bool:
    """Exact wire equality, with an exact-Decimal fallback for numerics.

    Exact ``==`` decides every string / date / uuid / bytes / bool value (so this
    never loosens a comparison that already holds); only a residual numeric
    difference — the wire-rendered ``decimal`` string ``"99.99"`` against the
    authored number ``99.99`` — reconciles in Decimal space. ``bool`` is never
    numeric (``True`` never equals ``1``).
    """
    if observed == expected:
        return True
    if isinstance(observed, bool) or isinstance(expected, bool):
        return False
    left, right = _to_decimal(observed), _to_decimal(expected)
    return isinstance(left, Decimal) and isinstance(right, Decimal) and left == right


def _row_equal(observed: dict[str, Any], expected: dict[str, Any]) -> bool:
    return observed.keys() == expected.keys() and all(
        _scalar_equal(observed[key], expected[key]) for key in observed
    )


def _compare_rows(observed: list[dict[str, Any]], expected: list[dict[str, Any]]) -> None:
    """Order-insensitive multiset comparison (greedy — result sets are tiny)."""
    obs = [_wire_row(row) for row in observed]
    remaining = [_wire_row(row) for row in expected]
    assert len(obs) == len(remaining), f"row count: observed {obs!r} != expected {remaining!r}"
    for row in obs:
        for index, candidate in enumerate(remaining):
            if _row_equal(row, candidate):
                del remaining[index]
                break
        else:
            raise AssertionError(f"observed row unmatched: {row!r}\n  expected pool: {remaining!r}")
    assert not remaining, f"expected rows unmatched: {remaining!r}"


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
        _compare_rows(envelope["observations"]["rows"], expected)


def _reachable_write_cases() -> list[case_format.Case]:
    from parallax.conformance import sweep

    return [c for c in sweep.reachable_cases() if c.case_id in WRITE_EXERCISED]


_WRITE_CASES = _reachable_write_cases()


@pytest.mark.parametrize("case", _WRITE_CASES, ids=[c.case_id for c in _WRITE_CASES])
def test_write_run_sweep(case: case_format.Case, provisioner: Any) -> None:
    """Run each keyed unit-of-work write case end-to-end against a reset database.

    A scenario's writes commit (or, `rollback: true`, abort) as separate units of work
    and its finds read committed state; a writeSequence executes the whole FK-ordered
    sequence in one transaction. The envelope's per-step emissions must equal the golden
    DML and its total round trips the case's `then.roundTrips`. Per-step rows are not on
    the wire (`additionalProperties: false`), so row correctness is the oracle-test gate.
    """
    meta = engine.load_case_metamodel(case)
    from parallax.conformance import provision

    provisioner.reset(meta, provision.load_fixtures(str(case_document(case)["model"])))

    envelope = adapter.run_case(case.path, "postgres", provisioner.port)
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok", envelope

    golden_statements = write_golden_statements(case)
    emissions = envelope["emissions"]
    assert len(emissions) == len(golden_statements), (case.case_id, emissions, golden_statements)
    for emission, (golden_sql, golden_binds) in zip(emissions, golden_statements, strict=True):
        assert emission["sql"] == golden_sql, (case.case_id, emission)
        assert wire_binds(emission["binds"]) == wire_binds(golden_binds), (case.case_id, emission)
    assert envelope["observations"]["roundTrips"] == case_document(case)["then"]["roundTrips"]


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
