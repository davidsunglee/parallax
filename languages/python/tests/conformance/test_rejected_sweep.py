"""Docker-free rejected-case run sweep (m-conformance-adapter `run`, m-case-format
`rejected` cases, COR-3 Phase 7 increment 1: resolved DQ3/DQ8).

A rejected case executes no SQL and touches no database (m-case-format "Rejected
cases"): grading its `run` envelope needs no provisioner, so — unlike
`test_run_sweep.py`, whose every test function threads the Testcontainers
`provisioner` fixture — this sweep runs entirely in-process. `when.operation` /
`when.model` / `when.write` inputs are all exercised end-to-end (COR-3 Phase 8
increment 2 landed the `when.write` half, `validate_write`): the classified
`rejectedRule` observation is compared against the case's own
`then.rejectedRule`, and a :class:`_RefusingPort` proves the "no database"
contract structurally, the same way the compile lane's refusing port proves
query-result-independence.

Marked `unit` as well as `conformance` (the `tests/api_conformance/
test_write_no_drift.py` dual-marking precedent): it is pure, Docker-free,
in-process behaviour, so it contributes to the unit-lane branch-coverage gate
and also runs under `pytest -m conformance`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, cast

import jsonschema
import pytest

from conftest import adapter_schema, case_document
from parallax.conformance import adapter, case_format, sweep
from parallax.core.db_port import DbPort, Row

pytestmark = [pytest.mark.unit, pytest.mark.conformance]

_SCHEMA = adapter_schema()
_REACHABLE_REJECTED = [c for c in sweep.reachable_cases() if c.shape == "rejected"]


class _RefusingPort:
    """An `m-db-port` that fails loudly if the rejected lane ever touches it."""

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:
        raise AssertionError(f"a rejected-case run must not execute SQL: {sql!r}")

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        raise AssertionError(f"a rejected-case run must not execute SQL: {sql!r}")

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        raise AssertionError("a rejected-case run must not open a transaction")


def _when_kind(case: case_format.Case) -> str:
    when = cast("dict[str, Any]", case_document(case).get("when") or {})
    for kind in ("operation", "model", "write"):
        if kind in when:
            return kind
    raise AssertionError(
        f"{case.case_id}: rejected case carries none of operation/model/write"
    )  # pragma: no cover


@pytest.mark.parametrize("case", _REACHABLE_REJECTED, ids=[c.case_id for c in _REACHABLE_REJECTED])
def test_rejected_sweep(case: case_format.Case) -> None:
    envelope = adapter.run_case(case.path, "postgres", _RefusingPort())
    jsonschema.validate(envelope, _SCHEMA)

    assert envelope["status"] == "ok", envelope
    assert envelope["emissions"] == []
    observations = envelope["observations"]
    assert observations["roundTrips"] == 0
    assert observations["rejectedRule"] == case_document(case)["then"]["rejectedRule"]


def test_reachable_rejected_population_is_non_empty() -> None:
    assert _REACHABLE_REJECTED, "the reachable intersection lost its rejected-shape cases"


def test_reachable_rejected_population_spans_every_when_kind() -> None:
    # `operation` / `model` / `write` inputs are all exercised above. All three
    # kinds should be present in the reachable set so no dispatch arm silently
    # goes untested.
    kinds = {_when_kind(case) for case in _REACHABLE_REJECTED}
    assert kinds == {"operation", "model", "write"}, kinds
