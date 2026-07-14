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
# base m-sql *Read projection* the compiler emits and whose predicate this phase
# lowers. New cases join deliberately as lowering grows.
#
# Scalar round-trip + quoted-reserved-identifier reads.
_SCALAR_READS: Final[frozenset[str]] = frozenset({"m-core-001", "m-descriptor-001"})
# Value-object nested-predicate reads (row-form — the values lane; slot 4 omitted).
_VALUE_OBJECT_PREDICATE_READS: Final[frozenset[str]] = frozenset(
    f"m-value-object-{n:03d}" for n in (1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)
)
# Orders op-algebra reads. The read-projection amendment (Phase 5b) re-goldened these
# to the full declared scalar projection the default find projection already emits, so
# they now compile-match with no code change — closing ledger D-11. Includes the named
# tracer m-op-algebra-002, run end-to-end below; 028 was removed by the amendment.
_ORDERS_OP_ALGEBRA_READS: Final[frozenset[str]] = frozenset(
    f"m-op-algebra-{n:03d}" for n in (*range(1, 28), 29, 30, 31, 32, 33, 34)
)
# Value-object instance-form materialization reads (the object lane): the slot-4
# document splice projects the `address` column (m-sql *Read projection*). Their graph
# *observation* — a materialized run — lands with the snapshot branch (Phase 7), so
# they are compile-exercised here but run-deferred (see the run sweep).
_VALUE_OBJECT_MATERIALIZATION_READS: Final[frozenset[str]] = frozenset(
    {"m-value-object-023", "m-value-object-024"}
)
# Temporal reads (COR-3 Phase-6 milestone 2, m-temporal-read): the as-of predicate is
# auto-injected by m-temporal-read (default-latest on omitted axes) and m-sql projects
# each axis's interval columns (business before processing) from the re-goldened corpus.
# Audit-only + boundary (001-008) and bitemporal (013-017) are row-form — compiled and
# run below.
_TEMPORAL_READ_ROW_FORM: Final[frozenset[str]] = frozenset(
    f"m-temporal-read-{n:03d}" for n in (*range(1, 9), 13, 14, 15, 16, 17)
)
# Temporal value-object reads: the document rides the owner's milestone (m-value-object
# "Inherited temporality"). Instance-form (assert `then.graph`), so — like the non-
# temporal 023/024 — compile-exercised (slot-4 `address` + injected as-of predicate) but
# run-deferred to the snapshot branch (Phase 7).
_TEMPORAL_VALUE_OBJECT_READS: Final[frozenset[str]] = frozenset(
    f"m-value-object-{n:03d}" for n in (28, 29, 30, 31)
)
COMPILE_EXERCISED: Final[frozenset[str]] = (
    _SCALAR_READS
    | _VALUE_OBJECT_PREDICATE_READS
    | _ORDERS_OP_ALGEBRA_READS
    | _VALUE_OBJECT_MATERIALIZATION_READS
    | _TEMPORAL_READ_ROW_FORM
    | _TEMPORAL_VALUE_OBJECT_READS
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
    """The forward-looking reason a reachable case is not in the exercised set.

    The read-projection amendment (Phase 5b, ledger D-11) re-goldened every stale
    read to the projection the compiler emits, so every reachable *ok*-status read is
    now exercised (asserted by ``test_every_unexercised_reachable_read_is_refused``).
    What remains reasoned-skipped is (1) the `error`-shape `m-db-error` cases, (2) the
    other non-read shapes, whose compile lands with the write path (Phase 6/8), and
    (3) the reads the Phase-5 compiler refuses with a loud ``SqlGenError`` —
    inheritance-family reads and to-many value-object array traversal — deferred past
    the single-entity read path to the snapshot branch (ledger D-12).
    """
    if case.shape == "error":
        # m-db-error cases trigger a real DB error and assert the neutral category +
        # native code. The classification seam (categories, call-site predicates, the
        # port-boundary re-raise) is implemented and proven by the dialect contract
        # suite, the m-db-error unit tests, and the provider deadlock proof; grading
        # these cases additionally needs error/concurrency-shape `run` support — the
        # later Phase-6 conformance milestone (case-instruction translation).
        return (
            "error-shape m-db-error case: the classification seam is implemented and "
            "proven by the dialect contract suite, the m-db-error unit tests, and the "
            "provider deadlock proof; grading the case needs error/concurrency-shape "
            "`run` support (COR-3 Phase-6 case-instruction translation)"
        )
    if case.shape != "read":
        return f"compile of {case.shape}-shape cases lands with the write path (COR-3 Phase 6/8)"
    message = envelope.get("diagnostics", [{}])[0].get("message", "")
    return f"read lowering deferred past the Phase-5 read path (ledger D-12): {message}"


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


def test_every_unexercised_reachable_read_is_refused() -> None:
    """After the read-projection amendment closed D-11, the only reads left out of
    the exercised set are the ones the Phase-5 compiler refuses with an ``error``
    envelope (D-12: inheritance-family reads, to-many value-object array traversal) —
    never an ``ok``-status read whose projection silently mismatches the golden."""
    for case in _REACHABLE:
        if case.shape != "read" or case.case_id in COMPILE_EXERCISED:
            continue
        envelope = adapter.compile_case(case.path, "postgres")
        assert envelope["status"] == "error", (case.case_id, envelope)


def test_run_only_cases_are_never_compiled() -> None:
    """A compile on a run-only case returns the defined ``run-only`` answer.

    Populated in Phase-6 milestone 1: the reachable set now includes the run-only
    `m-db-error` deadlock / lock-wait cases (single-connection concurrency intent),
    so this asserts each returns ``run-only`` rather than an emitted golden.
    """
    run_only = [c for c in _REACHABLE if engine.eligibility(c) is not None]
    assert run_only, "the reachable intersection now includes run-only m-db-error cases"
    for case in run_only:
        envelope = adapter.compile_case(case.path, "postgres")
        assert envelope["status"] == "run-only"
        assert envelope["diagnostics"][0]["code"] == "compile-run-only"
