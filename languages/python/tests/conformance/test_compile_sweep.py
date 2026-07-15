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

import re
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

# The keyed, non-temporal unit-of-work write cases M4 grades byte-exact (COR-3 Phase 6
# M4, m-unit-work): scenario read-your-own-writes / rollback / mixed-op flushes, and the
# FK-ordered writeSequence cases. Each emits its per-step golden DML (a scenario find
# carries the `for share of t0` read-lock suffix). The m-batch-write coalescing witnesses
# (008/010) are unreachable under Option B; the newly-reachable m-pk-gen writeSequence
# cases (write-side id allocation) and the boundary abort case (004) are reasoned-skipped.
_WRITE_SCENARIOS: Final[frozenset[str]] = frozenset(
    f"m-unit-work-{n:03d}" for n in (1, 2, 5, 6, 9, 11, 12)
)
_WRITE_SEQUENCES: Final[frozenset[str]] = frozenset({"m-unit-work-003", "m-unit-work-007"})
WRITE_EXERCISED: Final[frozenset[str]] = _WRITE_SCENARIOS | _WRITE_SEQUENCES

_REACHABLE = sweep.reachable_cases()
_SCHEMA = adapter_schema()


def wire_binds(binds: list[object]) -> list[object]:
    """The bind list in canonical wire form (m-db-port), reconciling an authored `date`
    golden bind with the write-input date *string* the keyed lowering carries verbatim."""
    return [engine.wire_value(b) for b in binds]


def write_golden_statements(case: case_format.Case) -> list[tuple[str, list[object]]]:
    """The ordered golden DML for a write case: a writeSequence's flat `then.statements`,
    or a scenario's per-step `when.scenario[i].statements` flattened in step order."""
    doc = case_document(case)
    if case.shape == "writeSequence":
        groups = [cast("list[dict[str, Any]]", doc["then"]["statements"])]
    else:
        steps = cast("list[dict[str, Any]]", doc["when"]["scenario"])
        groups = [cast("list[dict[str, Any]]", step["statements"]) for step in steps]
    out: list[tuple[str, list[object]]] = []
    for group in groups:
        for entry in group:
            sql: Any = entry["sql"]
            text = cast("dict[str, str]", sql)["postgres"] if isinstance(sql, dict) else sql
            out.append((cast("str", text), list(cast("list[object]", entry.get("binds", [])))))
    return out


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
    """The reason a reachable case is not in the compile-exercised set.

    The read-projection amendment (Phase 5b, ledger D-11) re-goldened every stale
    read to the projection the compiler emits, so every reachable *ok*-status read is
    now exercised (asserted by ``test_every_unexercised_reachable_read_is_refused``).
    What remains reasoned-skipped is (1) the `error`-shape `m-db-error` cases — a
    permanent LANE classification, not a forward promise: the single-connection
    trigger is graded end-to-end by the error run lane, the two-connection
    choreography by the provider proof, (2) the other non-read shapes, whose compile
    lands with the write path (Phase 6/8), and (3) the reads the Phase-5 compiler
    refuses with a loud ``SqlGenError`` — inheritance-family reads and to-many
    value-object array traversal — deferred past the single-entity read path to the
    snapshot branch (ledger D-12).
    """
    if case.shape == "error":
        # An error case's trigger DML is authored, not compiled (m-case-format), so
        # neither sub-shape ever joins the compile-exercised set: this is a lane
        # classification. The single-connection statement trigger is graded by the
        # error run lane (M4 increment 4); the two-connection choreography is
        # run-only and driven by the provider contract proof's barrier-synchronized
        # sessions, which the single-connection adapter lanes cannot hold.
        if engine.eligibility(case) is not None:
            return (
                "two-connection m-db-error choreography (deadlock / lock-wait / "
                "serialization): run-only; the provider contract proof "
                "(test_provider_contract) drives the barrier-synchronized sessions, "
                "not the single-connection adapter lanes"
            )
        return (
            "error-shape trigger DML is authored, not compiled (m-case-format); graded "
            "end-to-end by the error run lane (test_run_sweep.test_error_run_sweep)"
        )
    if case.shape == "boundary":
        # The m-unit-work abort-contract case (withheld callback value on rollback) is an
        # m-api-conformance-lane assertion the wire golden SQL cannot see; the API
        # Conformance Suite verifies it, not `run`. It emits no golden DML to grade.
        return (
            "boundary abort-contract case (m-api-conformance lane): the withheld-value-"
            "on-abort contract is verified by the API Conformance Suite, not by `run`"
        )
    if case.shape in ("scenario", "writeSequence"):
        # The reachable keyed unit-of-work cases are graded above (WRITE_EXERCISED). The
        # rest are either REFUSED by the M4 lowering (inheritance-family / temporal /
        # predicate / opt-lock writes, whose forward-error diagnostic names the phase) or
        # lowerable but OUTSIDE the reviewed M4 exercised set (the m-core keyed writes, the
        # m-pk-gen write-side id allocation, the m-value-object document writes) — these
        # join the exercised set deliberately as the reviewed write corpus grows.
        if envelope.get("status") == "error":
            message = envelope.get("diagnostics", [{}])[0].get("message", "")
            return f"{case.shape} write refused by the M4 keyed-write lowering: {message}"
        return (
            f"{case.shape} `{case.primary_module}` write outside the reviewed M4 keyed "
            "unit-of-work set (the 9 account/orders cases); write-side primary-key "
            "allocation (m-pk-gen) and value-object document writes (m-value-object) land "
            "with a later write increment / phase"
        )
    if case.shape != "read":
        return f"compile of {case.shape}-shape cases lands with the write path (COR-3 Phase 6/8)"
    message = envelope.get("diagnostics", [{}])[0].get("message", "")
    return f"read lowering deferred past the Phase-5 read path (ledger D-12): {message}"


def _pointer_ok(shape: str, pointer: str) -> bool:
    """Whether an emission ``casePointer`` is well-formed for a write case's shape."""
    if shape == "writeSequence":
        return re.fullmatch(r"/writeSequence/\d+", pointer) is not None
    return re.fullmatch(r"/scenario/\d+/(write|find)", pointer) is not None


def _assert_write_emissions(case: case_format.Case, envelope: dict[str, Any]) -> None:
    """Grade a keyed unit-of-work write case: per-step emissions == the golden DML,
    round trips == ``then.roundTrips``, and every casePointer well-formed for the shape."""
    assert envelope["status"] == "ok", envelope
    golden_statements = write_golden_statements(case)
    assert envelope["roundTrips"] == case_document(case)["then"]["roundTrips"], case.case_id
    emissions = envelope["emissions"]
    assert len(emissions) == len(golden_statements), (case.case_id, emissions, golden_statements)
    for emission, (golden_sql, golden_binds) in zip(emissions, golden_statements, strict=True):
        assert emission["sql"] == golden_sql, (case.case_id, emission)
        assert wire_binds(emission["binds"]) == wire_binds(golden_binds), (case.case_id, emission)
        assert _pointer_ok(case.shape, emission["casePointer"]), (case.case_id, emission)


@pytest.mark.parametrize("case", _REACHABLE, ids=[c.case_id for c in _REACHABLE])
def test_compile_sweep(case: case_format.Case) -> None:
    envelope = adapter.compile_case(case.path, "postgres")
    jsonschema.validate(envelope, _SCHEMA)

    if case.shape == "rejected":
        # A rejected case carries no golden SQL by construction (m-case-format);
        # its run-only status is shape-intrinsic, not authored per-case
        # (m-conformance-adapter, resolved DQ3/DQ8) — every reachable rejected
        # case answers it, never a silent skip.
        assert envelope["status"] == "run-only", envelope
        assert envelope["diagnostics"][0]["code"] == "compile-run-only", envelope
        return

    if case.case_id in WRITE_EXERCISED:
        _assert_write_emissions(case, envelope)
        return
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


def test_write_exercised_set_is_reachable() -> None:
    reachable = {c.case_id for c in _REACHABLE}
    stale = WRITE_EXERCISED - reachable
    assert not stale, f"write-exercised ids outside the reachable intersection: {sorted(stale)}"


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


def test_error_and_boundary_lane_partition() -> None:
    """The error/boundary run-lane classification is exact (M4 increment 4).

    Every reachable error-shape case is EITHER a single-connection statement
    trigger (graded by the error run lane) XOR a two-connection choreography
    (corpus-declared run-only; the provider contract proof drives it) — the
    trigger marker and the run-only declaration must agree, so no error case
    can fall between the lanes. Every reachable boundary case is a declared
    api-conformance-lane case (the API Conformance Suite verifies it) with a
    run-only declaration, so neither adapter lane ever grades one.
    """
    errors = [c for c in _REACHABLE if c.shape == "error"]
    assert errors, "the reachable intersection lost its m-db-error cases"
    for case in errors:
        doc = case_document(case)
        has_choreography = "concurrency" in (doc.get("when") or {})
        declared_run_only = engine.eligibility(case) is not None
        assert has_choreography == declared_run_only, case.case_id
        if not has_choreography:
            assert doc["then"]["statements"], case.case_id
    boundaries = [c for c in _REACHABLE if c.shape == "boundary"]
    assert boundaries, "the reachable intersection lost its boundary case"
    for case in boundaries:
        assert case_document(case).get("lane") == "api-conformance", case.case_id
        assert engine.eligibility(case) is not None, case.case_id
