"""Docker-free compile sweep (m-conformance-adapter `compile`, m-sql).

Parametrized from the corpus at runtime over the reachable intersection of the
active slice and implemented module tags. Every case's compile envelope is
schema-validated; the exercised set must emit SQL and binds equal to the case's
``postgres`` golden after normalization, and every other reachable case has an
explicit skip reason. Because read compilation is pure, the refusing port never
sees a row request.

Pure, Docker-free, in-process behaviour, so it classifies ``dbfree`` and
contributes to the database-free branch-coverage gate. ``compile_sweep`` is its
orthogonal focused selector, not a class.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Any, cast

import jsonschema
import pytest

from _support.corpus import case_document
from _support.repo import adapter_schema
from _support.sweep_goldens import (
    COMPILE_EXERCISED,
    WRITE_EXERCISED,
    wire_binds,
    write_golden_statements,
)
from parallax.conformance import adapter, case_format, engine, sweep
from parallax.conformance.profile import profile_for
from parallax.core.db_port import DbPort, Row, TransactionOutcome
from parallax.core.dialect import POSTGRES, Dialect

pytestmark = pytest.mark.compile_sweep

_REACHABLE = sweep.reachable_cases()
_SCHEMA = adapter_schema()
# The declared profile the lane-dispatch check below names its `run` request under,
# resolved out of the one roster; nothing here provisions it, because the case is
# refused before a database is needed.
_PROFILE = profile_for("pg-full")


class _RefusingPort:
    """An `m-db-port` that fails loudly if a lane-dispatched `run` ever touches it."""

    dialect: Dialect = POSTGRES

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        raise AssertionError(f"a lane-dispatched run must not execute SQL: {sql!r}")

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        raise AssertionError(f"a lane-dispatched run must not execute SQL: {sql!r}")

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        raise AssertionError("a lane-dispatched run must not open a transaction")


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

    Run-only cases are classified first, independent of shape. Error cases are
    divided between the single-connection run lane and the provider's
    two-connection proof. Remaining non-read shapes receive their write-path
    classification, while unsupported reads report the compiler diagnostic.
    """
    if envelope.get("status") == "run-only":
        # Declared `compileEligibility: run-only` covers query-result-dependent
        # reads, pk-gen sequence reservations, and materializing predicate writes:
        # m-txtime-write-007/009, m-bitemp-write-010..-013, m-opt-lock-014/015,
        # m-value-object-047/066): `run` (never `compile`) is the ONLY lane that ever
        # grades these — the m-conformance-adapter envelope already answers
        # `run-only` without attempting any lowering at all, so this is classified
        # first, shape-agnostically, before any shape-specific fallback text.
        # `test_run_only_cases_are_never_compiled` asserts the envelope.
        reason = envelope.get("diagnostics", [{}])[0].get("message", "")
        return (
            f"declared compile-run-only ({reason}); graded by run instead (m-conformance-adapter)"
        )
    if case.shape == "error":
        # An error case's trigger DML is authored, not compiled (m-case-format), so
        # neither sub-shape ever joins the compile-exercised set: this is a lane
        # classification. The single-connection statement trigger is graded by the
        # error run lane; the two-connection choreography is
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
        # Every boundary case (m-auto-retry / m-opt-lock bounded automatic
        # retry — an injected-fault or loop-configuration loop-mechanics
        # branch) is a
        # declared `api-conformance`-lane assertion the wire golden SQL
        # cannot see (it carries no golden DML at all, m-case-format); the
        # API Conformance Suite verifies it, not `run`.
        return (
            "boundary loop-mechanics case (m-auto-retry/m-opt-lock, api-conformance lane): "
            "verified by the API Conformance Suite's case-driven boundary runner, not by `run`"
        )
    if case.shape in ("scenario", "writeSequence"):
        # The reachable keyed unit-of-work cases are graded above (WRITE_EXERCISED);
        # every run-only case is classified above too. The rest are either REFUSED
        # by the keyed-write lowering (inheritance-family / temporal / opt-lock-
        # unobserved writes, whose forward-error diagnostic names its own deferral
        # or corpus conflict) or lowerable but outside the exercised set.
        if envelope.get("status") == "error":
            message = envelope.get("diagnostics", [{}])[0].get("message", "")
            return f"{case.shape} write refused by the keyed-write lowering: {message}"
        return (
            f"{case.shape} `{case.primary_module}` write outside the reviewed keyed "
            "unit-of-work set (the 9 account/orders cases plus the batch/predicate-write "
            "flips); not yet a reviewed exercised case"
        )
    if case.shape != "read":
        return f"compile of {case.shape}-shape cases lands with the write path"
    message = envelope.get("diagnostics", [{}])[0].get("message", "")
    return f"read lowering deferred past the read path: {message}"


def _pointer_ok(shape: str, pointer: str) -> bool:
    """Whether an emission ``casePointer`` is well-formed for a write case's shape."""
    if shape == "writeSequence":
        return re.fullmatch(r"/writeSequence/\d+", pointer) is not None
    return re.fullmatch(r"/scenario/\d+/(write|objectQuery)", pointer) is not None


def _assert_write_emissions(case: case_format.Case, envelope: dict[str, Any]) -> None:
    """Grade a keyed unit-of-work write case: per-step emissions == the golden DML,
    round trips == the DML statement count, and every casePointer well-formed for
    the shape.

    The compile lane lowers a write buffer and issues nothing, so what it can
    report is the DML it emitted. `then.roundTrips` counts the RESOLVING READS a
    keyed write verb's source requires beside that DML (`m-case-format`
    *Resolving reads a write owes*), which only the run lane performs — so the
    two numbers coincide for a case whose writes open rows and differ by exactly
    those reads for a case whose writes address existing ones.
    """
    assert envelope["status"] == "ok", envelope
    golden_statements = write_golden_statements(case)
    assert envelope["roundTrips"] == len(golden_statements), case.case_id
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
        # (`m-conformance-adapter`) — every reachable rejected
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
    assert emission["casePointer"] == "/objectQuery"
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
    """Every compile-eligible read outside the exercised set is refused.

    A declared run-only read is exempt: its envelope is the defined ``run-only``
    answer, not ``error`` — asserted instead by
    `test_run_only_cases_are_never_compiled`, which every such case must join.
    """
    for case in _REACHABLE:
        if case.shape != "read" or case.case_id in COMPILE_EXERCISED:
            continue
        if engine.eligibility(case) is not None:
            continue
        envelope = adapter.compile_case(case.path, "postgres")
        assert envelope["status"] == "error", (case.case_id, envelope)


def test_run_only_cases_are_never_compiled() -> None:
    """A compile on a run-only case returns the defined ``run-only`` answer.

    The reachable set includes run-only `m-db-error` deadlock and lock-wait
    cases, each of which returns ``run-only`` rather than an emitted golden.
    """
    run_only = [c for c in _REACHABLE if engine.eligibility(c) is not None]
    assert run_only, "the reachable intersection now includes run-only m-db-error cases"
    for case in run_only:
        envelope = adapter.compile_case(case.path, "postgres")
        assert envelope["status"] == "run-only"
        assert envelope["diagnostics"][0]["code"] == "compile-run-only"


def test_error_and_boundary_lane_partition() -> None:
    """The error and boundary run-lane classification is exact.

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


def _actions_all_mutate(case: case_format.Case) -> bool:
    steps = cast("list[dict[str, Any]]", case_document(case).get("when", {}).get("scenario", []))
    actions = [step["action"] for step in steps if "action" in step]
    return bool(actions) and all(action == "mutate" for action in actions)


def test_scenario_lane_dispatch_is_honest() -> None:
    """Every reachable scenario-shape case whose top-level `lane` is
    `api-conformance` and is NOT a mutate-action-only scenario
    (m-snapshot-read-009's `action: access` closed-world witness) answers a
    lane-honest `error` from
    `compile` — the SAME `_boundary_lane_error` precedent, extended to a second
    shape (m-case-format "Case lanes"). It carries NO `compileEligibility`
    declaration (neither closed reason — `single-connection` /
    `query-result-dependent` — honestly describes why; the lane dispatch alone
    is the compile-time refusal), unlike a boundary case's mechanical
    run-only backstop. A MUTATE-action-only one is the exception: the engine
    grades the mutate verb itself — including an `expectError` step through
    the `errors` observation (`m-conformance-adapter`) — so it stays in the
    compile/run lanes as a member of `WRITE_EXERCISED`
    (`_PIN_CONTRAST_SCENARIOS`), graded like every other exercised scenario
    rather than refused.
    """
    lane_dispatched = [
        c
        for c in _REACHABLE
        if c.shape == "scenario" and case_document(c).get("lane") == "api-conformance"
    ]
    refused = [c for c in lane_dispatched if not _actions_all_mutate(c)]
    engine_graded = [c for c in lane_dispatched if _actions_all_mutate(c)]
    assert refused, "the reachable intersection lost its scenario api-conformance-lane case"
    assert engine_graded, "the reachable intersection lost its finite-pin contrast pair"
    for case in refused:
        assert engine.eligibility(case) is None, case.case_id
        envelope = adapter.compile_case(case.path, "postgres")
        assert envelope["status"] == "error", (case.case_id, envelope)
        # `run` answers the SAME lane-honest error, never executing SQL: the port
        # it is handed answers only the dialect the case would have been classified
        # and run under, and raises on any attempt to use it.
        run_envelope = adapter.run_case(case.path, _PROFILE, _RefusingPort())
        assert run_envelope["status"] == "error", (case.case_id, run_envelope)
    for case in engine_graded:
        assert case.case_id in WRITE_EXERCISED, case.case_id


def _skip_text(case_id: str) -> str:
    (case,) = [c for c in _REACHABLE if c.case_id == case_id]
    envelope = adapter.compile_case(case.path, "postgres")
    return _skip_reason(case, envelope)


def test_displayed_skip_text_stays_honest_for_a_representative_set() -> None:
    """Pin displayed skip text for representative classification cases.

    This catches vague forward promises and bare diagnostic fragments.
    """
    # `m-batch-write-005` and `-006` compile successfully and belong to
    # `WRITE_EXERCISED` (graded by `_assert_write_emissions` in the
    # main sweep, never by `_skip_text` — a case's exercised-status membership
    # is asserted directly there, not re-derived from skip text here).
    assert {"m-batch-write-005", "m-batch-write-006"} <= WRITE_EXERCISED
    # A materializing predicate-write scenario (query-result-dependent,
    # run-only) is classified BEFORE the shape fallback — never the stale
    # generic scheduling promise.
    materializing_text = _skip_text("m-txtime-write-007")
    assert materializing_text.startswith("declared compile-run-only"), materializing_text
    assert "graded by run instead" in materializing_text, materializing_text
    assert "land with a later write increment" not in materializing_text, materializing_text
    # A write that lowers successfully but sits outside the keyed set names its
    # current classification and does not mention unrelated pk-gen behavior.
    bucket_text = _skip_text("m-core-002")
    assert "outside the reviewed keyed" in bucket_text, bucket_text
    assert "m-pk-gen" not in bucket_text, bucket_text
    assert "land with a later write increment" not in bucket_text, bucket_text


def test_m_opt_lock_001_is_query_result_dependent_run_only() -> None:
    """`m-opt-lock-001` is a query-result-dependent run-only scenario.

    Its observing find, no-op versioned update, and dependent find share one
    unit of work and lock lifetime. The update's license comes from the query
    result, so compile returns the declared run-only envelope and the run lane
    grades the scenario.
    """
    (case,) = [c for c in _REACHABLE if c.case_id == "m-opt-lock-001"]
    assert case.case_id not in WRITE_EXERCISED
    assert engine.eligibility(case) is not None
    envelope = adapter.compile_case(case.path, "postgres")
    assert envelope["status"] == "run-only", envelope
    assert envelope["diagnostics"][0]["code"] == "compile-run-only", envelope
