"""The pg-full run sweep (m-conformance-adapter `run`, real Postgres).

Every exercised reachable read case is compiled, executed against a freshly reset
real database (``DROP SCHEMA … CASCADE`` → descriptor DDL → fixtures), and its
observed rows compared to the case's ``then.rows`` (order-insensitive, wire
space); its emitted SQL and binds equal the ``postgres`` golden. This is the
tracer path proven end to end — compile to canonical SQL/binds, then run against a
reset database. Docker-gated; a skip is reported, never silent (spec §6).
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any

import jsonschema
import pytest
from test_compile_sweep import COMPILE_EXERCISED, golden

from conftest import adapter_schema, case_document
from parallax.conformance import adapter, case_format, engine

pytestmark = pytest.mark.conformance

# The reachable read cases whose fixtures + rows this phase runs end-to-end.
RUN_EXERCISED = frozenset(COMPILE_EXERCISED)


def _reachable_run_cases() -> list[case_format.Case]:
    from parallax.conformance import sweep

    return [c for c in sweep.reachable_cases() if c.case_id in RUN_EXERCISED]


_CASES = _reachable_run_cases()
_SCHEMA = adapter_schema()


def _wire(value: object) -> object:
    if isinstance(value, decimal.Decimal):
        return str(value)  # decimal space, exact
    if value is None or isinstance(value, (bool, int, str, float)):
        return value
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    return value


def _row_key(row: dict[str, Any]) -> tuple[tuple[str, object], ...]:
    return tuple(sorted((k, _wire(v)) for k, v in row.items()))


def _compare_rows(observed: list[dict[str, Any]], expected: list[dict[str, Any]]) -> None:
    assert sorted(_row_key(r) for r in observed) == sorted(_row_key(r) for r in expected)


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
