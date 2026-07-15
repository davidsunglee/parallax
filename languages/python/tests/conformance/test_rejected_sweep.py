"""Docker-free rejected-case run sweep (m-conformance-adapter `run`, m-case-format
`rejected` cases, COR-3 Phase 7 increment 1: resolved DQ3/DQ8).

A rejected case executes no SQL and touches no database (m-case-format "Rejected
cases"): grading its `run` envelope needs no provisioner, so — unlike
`test_run_sweep.py`, whose every test function threads the Testcontainers
`provisioner` fixture — this sweep runs entirely in-process. `when.operation` /
`when.model` inputs are exercised end-to-end: the classified `rejectedRule`
observation is compared against the case's own `then.rejectedRule`, and a
:class:`_RefusingPort` proves the "no database" contract structurally, the same
way the compile lane's refusing port proves query-result-independence.
`when.write` inputs are Phase-8 territory (ledger D-12, `m-value-object`
required-field/type-mismatch checks and `m-inheritance` subtype-write protocol
checks) and get a reasoned, forward-looking skip naming the deferral — never a
silent gap.

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

    if _when_kind(case) == "write":
        # Phase 8 territory (ledger D-12): the read-side rejected lane does not
        # grade `when.write` inputs yet — a reasoned, forward-looking skip.
        assert envelope["status"] == "error", envelope
        message = envelope["diagnostics"][0]["message"]
        assert "Phase 8" in message, message
        pytest.skip(f"when.write rejected case deferred to Phase 8: {message}")

    assert envelope["status"] == "ok", envelope
    assert envelope["emissions"] == []
    observations = envelope["observations"]
    assert observations["roundTrips"] == 0
    assert observations["rejectedRule"] == case_document(case)["then"]["rejectedRule"]


def test_reachable_rejected_population_is_non_empty() -> None:
    assert _REACHABLE_REJECTED, "the reachable intersection lost its rejected-shape cases"


def test_reachable_rejected_population_spans_every_when_kind() -> None:
    # `operation` / `model` inputs are exercised above; `write` inputs are the
    # reasoned Phase-8 skip. All three kinds should be present in the reachable
    # set so neither dispatch arm silently goes untested.
    kinds = {_when_kind(case) for case in _REACHABLE_REJECTED}
    assert kinds == {"operation", "model", "write"}, kinds
