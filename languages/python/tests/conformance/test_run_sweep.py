"""The pg-full run sweep (m-conformance-adapter `run`, real Postgres).

Every exercised reachable read case is compiled, executed against a freshly reset
real database (``DROP SCHEMA … CASCADE`` → descriptor DDL → fixtures), and its
observation (``then.rows`` / ``then.graph`` / ``then.graphs``, order-insensitive
where the case format says so, wire space) compared against the golden; its
emitted SQL and binds equal the ``postgres`` golden, root and every deep-fetch
child level alike. This is the tracer path proven end to end — compile (where
eligible) to canonical SQL/binds, then run against a reset database. Docker-
gated; a skip is reported, never silent (spec §6).
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Final, cast

import jsonschema
import pytest
from test_compile_sweep import (
    COMPILE_EXERCISED,
    WRITE_EXERCISED,
    wire_binds,
    write_golden_statements,
)

from conftest import (
    adapter_schema,
    case_document,
    case_fixtures,
    compare_graph,
    compare_rows,
    wire_value_deep,
)
from parallax.conformance import adapter, case_format, engine

pytestmark = pytest.mark.conformance

# Multi-concrete polymorphic instance-form reads (COR-3 Phase 8 part C, DQ7b):
# m-inheritance-106/-107/-108 compile byte-identical to their row-form siblings
# (`test_compile_sweep.py` adds them to `COMPILE_EXERCISED`), but the per-variant
# `then.graph` narrowing they pin is NOT yet implemented by the find executor
# (`parallax.snapshot.materialize.decode_row` passes every projected column
# through unchanged — the same padded-superset shape a row-form read carries,
# never narrowed to the variant's own declared columns). COR-3 Phase 8
# increment 7 (ledger D-22) implements the narrowing and joins these to
# `RUN_EXERCISED`; carving them out here (rather than compiling them) keeps
# this sweep from running them against a materialization the golden `then.graph`
# does not yet match, honestly deferring the RUN half while COMPILE stays green.
_INSTANCE_FORM_GRAPH_RUN_DEFERRED: Final[frozenset[str]] = frozenset(
    {"m-inheritance-106", "m-inheritance-107", "m-inheritance-108"}
)

# The reachable read cases whose fixtures + observation this phase runs end-to-
# end: every compile-exercised read (COR-3 Phase 7 increment 5 closes the
# instance-form-graph run deferral this set once carried — m-value-object-023/
# -024/-028..-031 and the milestone-set m-snapshot-read-013/-014 now materialize
# and grade their `then.graph` / `then.graphs` here) PLUS every case DECLARED
# `compileEligibility: run-only` (D-10's query-result-dependent deep-fetch tail:
# `compile` can never emit their query-result-dependent child binds, so `run` is
# the ONLY lane that ever grades them — derived from the corpus declaration at
# collection time, never a hard-coded id list, m-conformance-adapter), MINUS the
# instance-form graph reads whose RUN half is still increment 7 territory.
RUN_EXERCISED = frozenset(COMPILE_EXERCISED) - _INSTANCE_FORM_GRAPH_RUN_DEFERRED


def _reachable_run_cases() -> list[case_format.Case]:
    from parallax.conformance import sweep

    reachable = sweep.reachable_cases()
    return [
        c
        for c in reachable
        if c.shape == "read" and (c.case_id in RUN_EXERCISED or engine.eligibility(c) is not None)
    ]


_CASES = _reachable_run_cases()
_SCHEMA = adapter_schema()


def _read_golden_statements(case: case_format.Case) -> list[tuple[str, list[Any]]]:
    """A read case's ordered golden statements (root, then every deep-fetch
    child level) — the same per-entry `{sql, binds}` extraction
    `write_golden_statements` uses for a write case, applied to a read's own
    `then.statements`."""
    statements = case_document(case)["then"]["statements"]
    out: list[tuple[str, list[Any]]] = []
    for entry in cast("list[dict[str, Any]]", statements):
        sql = entry["sql"]
        text = cast("dict[str, str]", sql)["postgres"] if isinstance(sql, dict) else sql
        binds = entry.get("binds", [])
        if isinstance(binds, dict):
            binds = cast("dict[str, list[object]]", binds)["postgres"]
        out.append((cast("str", text), list(cast("list[object]", binds))))
    return out


@pytest.mark.parametrize("case", _CASES, ids=[c.case_id for c in _CASES])
def test_run_sweep(case: case_format.Case, provisioner: Any) -> None:
    meta = engine.load_case_metamodel(case)
    from parallax.conformance import provision

    provisioner.reset(meta, provision.load_fixtures(str(case_document(case)["model"])))

    envelope = adapter.run_case(case.path, "postgres", provisioner.port)
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok", envelope

    doc = case_document(case)
    then = doc.get("then", {})
    golden_statements = _read_golden_statements(case)
    emissions = envelope["emissions"]
    assert len(emissions) == len(golden_statements), (case.case_id, emissions, golden_statements)
    for index, (emission, (golden_sql, golden_binds)) in enumerate(
        zip(emissions, golden_statements, strict=True)
    ):
        assert emission["sql"] == golden_sql, (case.case_id, emission)
        observed_binds = wire_binds(emission["binds"])
        expected_binds = wire_binds(golden_binds)
        if index == 0:
            # The root statement's binds are user-authored (never gathered), so
            # their order is defined and exact.
            assert observed_binds == expected_binds, (case.case_id, emission)
        else:
            # A deep-fetch child level's `IN`-list binds are the distinct keys
            # GATHERED from the parent level's own returned rows — an unordered
            # set (m-case-format fifth assertion layer): the gathered order
            # depends on the parent query's own row order (itself possibly a
            # declared, non-id `orderBy`), so only the MULTISET of bind values —
            # the gathered keys together with any propagated as-of suffix — is
            # asserted, never positional order.
            assert Counter(observed_binds) == Counter(expected_binds), (case.case_id, emission)

    observations = envelope["observations"]
    assert observations["roundTrips"] == then.get("roundTrips", 1), case.case_id

    if "rows" in then:
        compare_rows(observations["rows"], then["rows"])
    elif "graph" in then:
        compare_graph(observations["graph"], then["graph"])
        if "identityChecks" in then:
            assert observations.get("identityChecks") == then["identityChecks"], case.case_id
    elif "graphs" in then:
        expected_graphs = then["graphs"]
        observed_graphs = observations["graphs"]
        assert len(observed_graphs) == len(expected_graphs), case.case_id
        for observed_entry, expected_entry in zip(observed_graphs, expected_graphs, strict=True):
            assert wire_value_deep(observed_entry["pin"]) == wire_value_deep(
                expected_entry["pin"]
            ), case.case_id
            compare_graph(observed_entry["graph"], expected_entry["graph"])


# `m-opt-lock-012`'s scenario ALSO declares `compileEligibility: run-only` and
# ALSO uses `uow` grouping (:func:`_case_uses_uow_grouping`), but its two groups
# INTERLEAVE (the classic optimistic-lock race — one unit of work's observing
# find, a CONCURRENT unit of work's own observe-and-commit, then back to the
# first) — the engine's `run_scenario_case` executes only CONTIGUOUS `uow`
# groups (`engine._scenario_uow_spans`; a genuinely interleaved group needs a
# SECOND, independent connection the engine's single-`DbPort` seam does not
# expose yet). It stays OUT of this sweep; the reference harness (`just
# oracle-test`, real Postgres/MariaDB, two independently held sessions) is its
# green gate until a later increment gives the engine its own multi-connection
# seam.
_UOW_GROUPED_RUN_DEFERRED: Final[frozenset[str]] = frozenset({"m-opt-lock-012"})


def _case_uses_uow_grouping(case: case_format.Case) -> bool:
    """Whether a scenario case's own steps declare the `uow` grouping key
    (`m-case-format`) — the amendment-review remediation's discriminator
    between "this run-only case's observation is transaction-scoped, and the
    engine's `uow`-grouping seam (`engine._run_uow_group`) is what makes it
    runnable" and every OTHER run-only reason a scenario/writeSequence case
    carries (single-connection materializing predicate writes, deep-fetch
    deferred loads, pk-gen sequence batch reservations — none of which the
    run lane is ready to grade yet, exactly like before this remediation)."""
    when = cast("dict[str, Any]", case_document(case).get("when", {}))
    steps = cast("list[dict[str, Any]]", when.get("scenario", []))
    return any(isinstance(step.get("uow"), str) for step in steps)


def _reachable_write_cases() -> list[case_format.Case]:
    from parallax.conformance import sweep

    return [
        c
        for c in sweep.reachable_cases()
        if c.case_id in WRITE_EXERCISED
        or (
            c.case_id not in _UOW_GROUPED_RUN_DEFERRED
            and engine.eligibility(c) is not None
            and _case_uses_uow_grouping(c)
        )
    ]


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

    A `uow`-GROUPED find (amendment-review remediation) runs on the
    transaction's OWN connection (``tx._conn``, ``engine._run_uow_group``) —
    the object ``database.transact``'s closure receives as its argument, which
    a bare pass-through ``transaction(body)`` would hand ``body`` UNWRAPPED
    (the underlying provider's ``PostgresAdapter.transaction`` passes ITSELF,
    not this decorator). ``transaction`` therefore wraps that inner connection
    in a NESTED ``_ReadCapturePort`` sharing this SAME ``reads`` list, so a
    grouped find is captured from the SAME single execution as an ungrouped
    one, in the SAME step order.
    """

    def __init__(self, inner: Any, reads: list[list[dict[str, Any]]] | None = None) -> None:
        self._inner = inner
        self.reads: list[list[dict[str, Any]]] = reads if reads is not None else []

    def execute(self, sql: str, binds: Any) -> list[dict[str, Any]]:
        rows = self._inner.execute(sql, binds)
        self.reads.append(rows)
        return rows

    def execute_write(self, sql: str, binds: Any) -> int:
        return self._inner.execute_write(sql, binds)

    def transaction(self, body: Any) -> Any:
        reads = self.reads

        def wrapped(conn: Any) -> Any:
            return body(_ReadCapturePort(conn, reads=reads))

        return self._inner.transaction(wrapped)


def _scenario_expect_rows(case: case_format.Case) -> list[list[dict[str, Any]] | None]:
    """Each FIND step's declared ``expectRows`` in step order (None asserts nothing)."""
    steps = cast("list[dict[str, Any]]", case_document(case)["when"]["scenario"])
    return [step.get("expectRows") for step in steps if "find" in step]


@pytest.mark.parametrize("case", _WRITE_CASES, ids=[c.case_id for c in _WRITE_CASES])
def test_write_run_sweep(case: case_format.Case, provisioner: Any) -> None:
    """Run each keyed unit-of-work write case end-to-end against a reset database.

    An UNGROUPED scenario write commits (or, `rollback: true`, aborts) as its own
    separate unit of work, and an ungrouped find reads committed state — today's
    legacy semantics. A `uow`-GROUPED span of steps instead shares ONE held
    transaction: a grouped write applies on it without its own per-step commit, and
    a grouped find reads THROUGH that SAME transaction (read-your-own-writes,
    possibly uncommitted mid-transaction state), committing or rolling back only at
    the group's own last step. A writeSequence executes the whole FK-ordered
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


# --------------------------------------------------------------------------- #
# Conflict — the optimistic-lock run lane (m-opt-lock / m-audit-write /        #
# m-bitemp-write, COR-3 Phase 8 increments 3-4). Every reachable conflict      #
# case declares `compileEligibility: run-only` (single-connection concurrency  #
# intent), so `run` is the ONLY lane that ever grades it — mirroring the       #
# pk-gen `sequence` run-only set below, neither joins `WRITE_EXERCISED` (that  #
# set couples compile AND run grading; a run-only case would fail             #
# `test_compile_sweep`'s `status == "ok"` assert). Increment 4 adds the        #
# temporal close-only conflict witnesses: the non-inheritance audit-only and   #
# bitemporal gate/success/conflict pairs, the locking-mode zero-row-close      #
# (StaleWriteError) case, the TPH composed conflict, and the non-temporal      #
# value-object write under an optimistic gate (already tag-reachable, now      #
# exercised).                                                                  #
# --------------------------------------------------------------------------- #
_CONFLICT_CASES_EXERCISED: Final[frozenset[str]] = frozenset(
    {
        "m-opt-lock-005",
        "m-opt-lock-006",
        "m-opt-lock-007",
        "m-opt-lock-013",
        "m-temporal-read-009",
        "m-temporal-read-010",
        "m-temporal-read-011",
        "m-temporal-read-012",
        "m-audit-write-006",
        "m-bitemp-write-004",
        "m-bitemp-write-005",
        "m-inheritance-105",
        "m-value-object-046",
    }
)


def _reachable_conflict_cases() -> list[case_format.Case]:
    from parallax.conformance import sweep

    return [c for c in sweep.reachable_cases() if c.case_id in _CONFLICT_CASES_EXERCISED]


_CONFLICT_CASES = _reachable_conflict_cases()


def _conflict_golden_statements(then: dict[str, Any]) -> list[tuple[str, list[Any]]]:
    out: list[tuple[str, list[Any]]] = []
    for entry in cast("list[dict[str, Any]]", then.get("statements", [])):
        sql = entry["sql"]
        text = cast("dict[str, str]", sql)["postgres"] if isinstance(sql, dict) else sql
        out.append((cast("str", text), list(cast("list[Any]", entry.get("binds", [])))))
    return out


@pytest.mark.parametrize("case", _CONFLICT_CASES, ids=[c.case_id for c in _CONFLICT_CASES])
def test_conflict_run_sweep(case: case_format.Case, provisioner: Any) -> None:
    """Run each `conflict`-shape case (m-opt-lock) against a reset real database.

    The single-attempt form (`m-opt-lock-005/006/013`) grades the golden UPDATE's
    emissions and `then.affectedRows` — `0` for the stale-version conflict, `1` for
    a fresh gate. The `when.attempts` retry form (`m-opt-lock-007`) grades each
    attempt's own statements flattened in order (proving the `0`-then-`1` transition
    through each attempt's own distinct gate bind) and the FINAL affected-row count.
    Every case that authors `then.tableState` grades the committed table contents.
    """
    meta = engine.load_case_metamodel(case)
    provisioner.reset(meta, case_fixtures(case))

    envelope = adapter.run_case(case.path, "postgres", provisioner.port)
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok", envelope

    doc = case_document(case)
    then = cast("dict[str, Any]", doc.get("then", {}))
    observations = envelope["observations"]
    emissions = envelope["emissions"]

    if "affectedRows" in then:
        golden_statements = _conflict_golden_statements(then)
        assert len(emissions) == len(golden_statements), (case.case_id, emissions)
        for emission, (golden_sql, golden_binds) in zip(emissions, golden_statements, strict=True):
            assert emission["sql"] == golden_sql, (case.case_id, emission)
            assert wire_binds(emission["binds"]) == wire_binds(golden_binds), (
                case.case_id,
                emission,
            )
        assert observations["affectedRows"] == then["affectedRows"], case.case_id
    else:
        attempts = cast("list[dict[str, Any]]", doc["when"]["attempts"])
        golden_statements = [
            entry for attempt in attempts for entry in _conflict_golden_statements(attempt)
        ]
        assert len(emissions) == len(golden_statements), (case.case_id, emissions)
        for emission, (golden_sql, golden_binds) in zip(emissions, golden_statements, strict=True):
            assert emission["sql"] == golden_sql, (case.case_id, emission)
            assert wire_binds(emission["binds"]) == wire_binds(golden_binds), (
                case.case_id,
                emission,
            )
        assert observations["affectedRows"] == attempts[-1]["affectedRows"], case.case_id

    if "tableState" in then:
        expected_state = cast("dict[str, list[dict[str, Any]]]", then["tableState"])
        observed_state = observations.get("tableState")
        assert observed_state is not None, case.case_id
        assert set(observed_state) >= set(expected_state), (case.case_id, observed_state)
        for table, expected_rows in expected_state.items():
            compare_rows(observed_state[table], expected_rows)


# --------------------------------------------------------------------------- #
# The pk-gen `sequence`-strategy writeSequence cases (m-pk-gen, COR-3 Phase 8  #
# increment 3): declared `compileEligibility: run-only` (query-result-        #
# dependent — the registry-read-derived allocated ids), so `run` is the ONLY  #
# lane that ever grades them, same reasoning as the conflict cases above.     #
# `m-pk-gen-014` (increment 4: a sequence-strategy registry advance composed   #
# with a temporal audit-only insert in ONE writeSequence, two transactions     #
# post the DQ4 re-route) joins for the same query-result-dependent reason —    #
# NOT `m-pk-gen-013` (already compile-eligible, `test_compile_sweep`'s own     #
# `_OPT_LOCK_AND_PK_GEN_WRITE_SEQUENCES`).                                     #
# --------------------------------------------------------------------------- #
_RUN_ONLY_WRITE_SEQUENCES_EXERCISED: Final[frozenset[str]] = frozenset(
    {*(f"m-pk-gen-{n:03d}" for n in range(4, 13)), "m-pk-gen-014"}
)


def _reachable_run_only_write_sequence_cases() -> list[case_format.Case]:
    from parallax.conformance import sweep

    return [c for c in sweep.reachable_cases() if c.case_id in _RUN_ONLY_WRITE_SEQUENCES_EXERCISED]


_RUN_ONLY_WRITE_SEQUENCE_CASES = _reachable_run_only_write_sequence_cases()


@pytest.mark.parametrize(
    "case", _RUN_ONLY_WRITE_SEQUENCE_CASES, ids=[c.case_id for c in _RUN_ONLY_WRITE_SEQUENCE_CASES]
)
def test_run_only_write_sequence_run_sweep(case: case_format.Case, provisioner: Any) -> None:
    """Run each run-only pk-gen `sequence`-strategy writeSequence case end to end
    against a reset real database — the SAME grading `test_write_run_sweep` applies
    to a compile-eligible writeSequence case, parametrized separately because a
    run-only case's compile envelope answers `status: "run-only"`, never `"ok"`
    (`test_write_run_sweep`'s `WRITE_EXERCISED` set couples compile-time grading in
    too, which a run-only member would fail)."""
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

    expected_state = cast(
        "dict[str, list[dict[str, Any]]]", case_document(case)["then"]["tableState"]
    )
    observed_state = envelope["observations"]["tableState"]
    assert set(observed_state) >= set(expected_state), (case.case_id, observed_state)
    for table, expected_rows in expected_state.items():
        compare_rows(observed_state[table], expected_rows)
