"""Docker-free compile sweep (m-conformance-adapter `compile`, m-sql).

Parametrized from the corpus at runtime over the reachable intersection (active
slice ∩ implemented module tags). Every case's compile envelope is
schema-validated; the reviewed *exercised* set must emit SQL and binds equal to
the case's ``postgres`` golden after normalization, and every other reachable
case is reasoned-skipped (no silent gaps) with the Phase-5 gap that keeps it out
of the sweep. Because read compilation is pure, the refusing port never sees a
row request — the sweep's honesty is structural.

Marked ``unit`` as well as ``compile_sweep``: it is pure, Docker-free, in-process
behaviour, so it contributes to the unit-lane branch-coverage gate and also runs
under ``pytest -m compile_sweep`` in ``python-static``.
"""

from __future__ import annotations

from typing import Any, Final, cast

import jsonschema
import pytest

from conftest import adapter_schema, case_document
from parallax.conformance import adapter, case_format, engine, sweep

pytestmark = [pytest.mark.unit, pytest.mark.compile_sweep]

# The reviewed set of reachable read cases whose golden read projection equals the
# descriptor-derived default (every declared scalar attribute in column order) and
# whose predicate this phase lowers. New cases join deliberately as lowering grows.
COMPILE_EXERCISED: Final[frozenset[str]] = frozenset(
    {
        "m-core-001",
        "m-descriptor-001",
        "m-value-object-001",
        "m-value-object-002",
        "m-value-object-004",
        "m-value-object-005",
        "m-value-object-006",
        "m-value-object-007",
        "m-value-object-008",
        "m-value-object-009",
        "m-value-object-010",
        "m-value-object-011",
        "m-value-object-012",
        "m-value-object-013",
        "m-value-object-014",
    }
)

_REACHABLE = sweep.reachable_cases()
_SCHEMA = adapter_schema()


def golden(case: case_format.Case) -> tuple[str, list[object]]:
    then = cast("dict[str, Any]", case_document(case).get("then", {}))
    statements = cast("list[dict[str, Any]]", then.get("statements", []))
    assert len(statements) == 1, case.case_id
    entry = statements[0]
    sql: Any = entry["sql"]
    text: str = cast("dict[str, str]", sql)["postgres"] if isinstance(sql, dict) else sql
    binds: Any = entry.get("binds", [])
    if isinstance(binds, dict):
        binds = cast("dict[str, list[object]]", binds)["postgres"]
    return text, list(cast("list[object]", binds))


def _skip_reason(case: case_format.Case, envelope: dict[str, Any]) -> str:
    if case.shape != "read":
        return f"compile of {case.shape}-shape cases lands with the write path (COR-3 Phase 6/8)"
    status = envelope.get("status")
    if status == "error":
        message = envelope.get("diagnostics", [{}])[0].get("message", "")
        return f"read lowering not yet online: {message}"
    return (
        "golden read projection is underspecified by the operation algebra "
        "(bespoke/materialization/stale-descriptor projection); deferred ledger D-11"
    )


@pytest.mark.parametrize("case", _REACHABLE, ids=[c.case_id for c in _REACHABLE])
def test_compile_sweep(case: case_format.Case) -> None:
    envelope = adapter.compile_case(case.path, "postgres")
    jsonschema.validate(envelope, _SCHEMA)

    if case.case_id not in COMPILE_EXERCISED:
        pytest.skip(_skip_reason(case, envelope))

    assert envelope["status"] == "ok", envelope
    assert envelope["roundTrips"] == 1
    emissions = envelope["emissions"]
    assert len(emissions) == 1
    emission = emissions[0]
    assert emission["casePointer"] == "/operation"
    golden_sql, golden_binds = golden(case)
    assert emission["sql"] == golden_sql
    assert emission["binds"] == golden_binds


def test_exercised_set_is_a_subset_of_the_reachable_reads() -> None:
    reachable_reads = {c.case_id for c in _REACHABLE if c.shape == "read"}
    stale = COMPILE_EXERCISED - reachable_reads
    assert not stale, f"exercised ids outside the reachable read intersection: {sorted(stale)}"


def test_run_only_cases_are_never_compiled() -> None:
    """A compile on a run-only case returns the defined ``run-only`` answer."""
    run_only = [c for c in _REACHABLE if engine.eligibility(c) is not None]
    for case in run_only:  # empty for the Phase-5 read intersection, asserted structurally
        envelope = adapter.compile_case(case.path, "postgres")
        assert envelope["status"] == "run-only"
        assert envelope["diagnostics"][0]["code"] == "compile-run-only"
