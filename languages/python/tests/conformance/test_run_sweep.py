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
    compare_binds,
    compare_graph,
    compare_rows,
    wire_value_deep,
)
from parallax.conformance import adapter, case_format, concurrency_runner, engine
from parallax.core.dialect import dialect_for

pytestmark = pytest.mark.conformance

# Multi-concrete polymorphic INSTANCE-FORM reads (COR-3 Phase 8 part C, DQ7b):
# m-inheritance-106/-107/-108/-109 compile byte-identical to their row-form
# siblings (`test_compile_sweep.py`'s own `COMPILE_EXERCISED`) and are exercised
# for real — but NOT through this file's own wire-level `_render_node`
# rendering, permanently: that rendering shares the identical `materialize.Node`
# the VALUES-lane witnesses (m-inheritance-003/-013/-015/-052, and OTHER
# already-exercised multi-concrete graph levels like `m-snapshot-read-012`'s
# own root-typed `animals` attachment) need PADDED, unnarrowed, so the SAME
# `Node` cannot satisfy both oracles through one rendering path. Per-variant
# narrowing is `parallax.snapshot.handle._wrap`'s OWN job (it resolves each column
# through the CONCRETE class's own declared members, skipping a sibling's) —
# these four are the OBJECT-lane (developer-surface `db.find`) witnesses each
# case's own comment names, graded by the API Conformance Suite instead
# (`tests/api_conformance/test_story_run.py`, `type(node)` + `instance_row`).
# A structural, PERMANENT lane split (DQ7b: both lanes of the same behavior
# are now expressed, each through its own grader), never a forward promise.
_INSTANCE_FORM_GRAPH_OBJECT_LANE_ONLY: Final[frozenset[str]] = frozenset(
    {"m-inheritance-106", "m-inheritance-107", "m-inheritance-108", "m-inheritance-109"}
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
# object-lane-only instance-form graph reads this file's own wire-level
# rendering structurally cannot grade.
RUN_EXERCISED = frozenset(COMPILE_EXERCISED) - _INSTANCE_FORM_GRAPH_OBJECT_LANE_ONLY


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
# first) — `run_scenario_case`/`adapter.run_case` execute only CONTIGUOUS `uow`
# groups (`engine._scenario_uow_spans`; a genuinely interleaved group needs a
# SECOND, independent connection this test's ordinary single-`DbPort` seam does
# not hold open). It stays OUT of `_WRITE_CASES`/`test_write_run_sweep`;
# `test_interleaved_uow_group_run_sweep` below is its own dedicated entry point
# (COR-3 Phase 8 increment 6: `engine.run_interleaved_scenario_case`, over the
# `Provisioner.peer` seam) — a routing exclusion, not a deferral, since the
# case IS run-lane exercised now, just through a different function.
_INTERLEAVED_UOW_GROUP_CASES: Final[frozenset[str]] = frozenset({"m-opt-lock-012"})


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


# COR-3 Phase 8 increment 5's materializing predicate-write run-only scenarios
# (`m-opt-lock` "Predicate-selected writes materialize when observations are
# needed", ADR 0014): each resolves through its OWN internal read
# (`Transaction._buffer_predicate_instruction`, paired with its immediately
# preceding find step in ONE transaction, `engine._run_materializing_pair`) —
# query-result-dependent (`compileEligibility: run-only`), so `compile` never
# grades them, but NONE of them declare `uow` grouping (unlike
# `m-opt-lock-012`) — `_case_uses_uow_grouping` alone would wrongly exclude
# every one of them, so this is their own explicit admission clause.
# `m-value-object-047` joins here too (a corpus amendment, not an increment-5
# landing): its trailing verify find is now an `asOf` read pinned strictly
# inside the closed window, the SAME find lane every OTHER `asOf` case already
# lowers — the case's own fourth step is not itself a materializing read, but
# it is run-only and NOT `uow`-grouped, so this explicit admission clause is
# still the only membership path that reaches it (`_reachable_write_cases`).
_MATERIALIZING_PREDICATE_WRITE_SCENARIOS_EXERCISED: Final[frozenset[str]] = frozenset(
    {
        "m-opt-lock-003",
        "m-opt-lock-004",
        "m-opt-lock-014",
        "m-opt-lock-015",
        "m-audit-write-007",
        "m-audit-write-009",
        "m-bitemp-write-010",
        "m-bitemp-write-011",
        "m-bitemp-write-012",
        "m-bitemp-write-013",
        "m-value-object-047",
    }
)


def _reachable_write_cases() -> list[case_format.Case]:
    from parallax.conformance import sweep

    return [
        c
        for c in sweep.reachable_cases()
        if (
            c.case_id in WRITE_EXERCISED
            or c.case_id in _MATERIALIZING_PREDICATE_WRITE_SCENARIOS_EXERCISED
            or (
                c.case_id not in _INTERLEAVED_UOW_GROUP_CASES
                and engine.eligibility(c) is not None
                and _case_uses_uow_grouping(c)
            )
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
        # `compare_binds` (the exact-Decimal-fallback comparison
        # `test_write_no_drift.py`'s typed-instance no-drift check already
        # uses): a materializing write's carried-forward payload value
        # (COR-3 Phase 8 increment 5) is a REAL ``decimal``-typed bind sourced
        # from the resolving read's own row (psycopg's native ``Decimal``,
        # never lossily coerced to ``float`` for SQL execution — `m-core`),
        # which a plain YAML-authored golden literal (``200.00``, a ``float``)
        # only reconciles against in Decimal space, not by bare wire equality.
        compare_binds(emission["binds"], golden_binds)
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


def _reachable_interleaved_uow_group_cases() -> list[case_format.Case]:
    from parallax.conformance import sweep

    return [c for c in sweep.reachable_cases() if c.case_id in _INTERLEAVED_UOW_GROUP_CASES]


_INTERLEAVED_CASES = _reachable_interleaved_uow_group_cases()


@pytest.mark.parametrize("case", _INTERLEAVED_CASES, ids=[c.case_id for c in _INTERLEAVED_CASES])
def test_interleaved_uow_group_run_sweep(case: case_format.Case, provisioner: Any) -> None:
    """`m-opt-lock-012`'s own dedicated entry point (COR-3 Phase 8 increment 6):
    the two-group optimistic-lock race, run over a REAL peer connection
    (`engine.run_interleaved_scenario_case`), never through `adapter.run_case`
    (which cannot hold a second session open).

    Grades the SAME FOUR layers `test_write_run_sweep` grades for an
    ordinary scenario — the ordered per-step golden DML (flattened across
    both interleaved groups plus the trailing ungrouped verify find, in
    AUTHORED step order), `then.roundTrips`, and every find step's own
    observed rows against its authored `expectRows` (review remediation
    finding 1 — grouped steps 0/1's own observing finds AND the trailing
    ungrouped verify at step 4, the SAME `compare_rows` comparator/
    canonicalization the ordinary lane uses, never a forked row-equality) —
    PLUS the scenario shape's own extra top-level assertion,
    `then.affectedRows`: the doomed group's own conflicting write's actual
    affected-row count (`0`, the stale-version gate mismatch that dooms the
    whole unit of work). The `expectRows` grade is the case's own teeth: a
    broken abort that left the doomed group's buffered insert durable would
    still emit well-formed DML and a correct `affectedRows`, but step 4's
    verify find would observe account 9 — this is what catches it.
    """
    meta = engine.load_case_metamodel(case)
    provisioner.reset(meta, case_fixtures(case))

    emissions, round_trips, conflict_actual, find_rows = engine.run_interleaved_scenario_case(
        case, "postgres", provisioner.port, lambda: provisioner.peer()
    )

    golden_statements = write_golden_statements(case)
    assert len(emissions) == len(golden_statements), (case.case_id, emissions, golden_statements)
    for emission, (golden_sql, golden_binds) in zip(emissions, golden_statements, strict=True):
        assert emission.sql == golden_sql, (case.case_id, emission)
        compare_binds(list(emission.binds), golden_binds)

    then = case_document(case)["then"]
    assert round_trips == then["roundTrips"], case.case_id
    assert conflict_actual == then["affectedRows"], case.case_id

    expected_per_find = _scenario_expect_rows(case)
    assert len(find_rows) == len(expected_per_find), (case.case_id, find_rows)
    for observed, expected in zip(find_rows, expected_per_find, strict=True):
        if expected is not None:
            compare_rows([engine.wire_row(row) for row in observed], expected)


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
# exercised). Increment 6 admits `m-opt-lock-009` (`retryOptimisticConflicts:  #
# true` + a two-attempt `0`-then-`1` choreography) — no new machinery, the     #
# SAME `when.attempts` retry lane `m-opt-lock-007` already exercises (pinned   #
# semantics #7: the attempts sequence is caller-visible choreography here,    #
# not the runtime auto-retry loop, which `m-opt-lock-011`'s boundary case      #
# proves instead).                                                             #
# --------------------------------------------------------------------------- #
_CONFLICT_CASES_EXERCISED: Final[frozenset[str]] = frozenset(
    {
        "m-opt-lock-005",
        "m-opt-lock-006",
        "m-opt-lock-007",
        "m-opt-lock-009",
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


# --------------------------------------------------------------------------- #
# The `when.concurrency` rounds runner (COR-3 Phase 8 increment 6 adds the    #
# m-read-lock behavioral matrix; the increment 7 completion round's D-28     #
# flip admits `m-db-error`'s own five two-session error cases too, case-     #
# driven through the SAME `Provisioner.peer` choreography with zero new      #
# machinery beyond the isolation-level knob below): `m-read-lock-006`        #
# (error / lockWaitTimeout), `-007`/`-008` (concurrencySuccess), and          #
# `m-db-error-004/-005/-006/-007/-009` (deadlock cycle/reverse, lock-wait     #
# timeout x2, serialization failure) — structurally identical to the         #
# m-read-lock matrix: two barrier-synchronized peer sessions, verbatim       #
# statement execution, error-shape classification (`sweep`'s own module      #
# docstring named this gap; it is closed here).                              #
# --------------------------------------------------------------------------- #
_CONCURRENCY_MODULES: Final[frozenset[str]] = frozenset({"m-read-lock", "m-db-error"})

# `m-db-error-009` (serialization-failure) needs its two peer sessions under
# genuine SERIALIZABLE isolation (Postgres SSI): the golden SIREAD-predicate-
# lock write-skew it pins never arises at the default READ COMMITTED every
# other concurrency case runs under (deadlock/lock-wait are ordinary row-lock
# contention, isolation-independent). `m-case-format` declares no isolation
# field — this is a runner-level fact about ONE case, not corpus data — so it
# is named here rather than added to the shared schema; every other case
# passes `isolation=None` (`concurrency_runner.run_rounds`'s own default,
# unchanged), preserving byte-identical behavior for the already-exercised
# m-read-lock matrix.
_SERIALIZABLE_ISOLATION_CASES: Final[frozenset[str]] = frozenset({"m-db-error-009"})


def _reachable_concurrency_rounds_cases() -> list[case_format.Case]:
    from parallax.conformance import sweep

    return [
        c
        for c in sweep.reachable_cases()
        if c.primary_module in _CONCURRENCY_MODULES
        and c.shape in ("error", "concurrencySuccess")
        and "concurrency" in (case_document(c).get("when") or {})
    ]


_CONCURRENCY_CASES = _reachable_concurrency_rounds_cases()


@pytest.mark.parametrize("case", _CONCURRENCY_CASES, ids=[c.case_id for c in _CONCURRENCY_CASES])
def test_concurrency_rounds(case: case_format.Case, provisioner: Any) -> None:
    """Run one `when.concurrency` case's rounds over two independently-held
    peer sessions and grade its own shape's assertion.

    An `error`-shape case (`m-read-lock-006`, `m-db-error-004/-005/-006/-007/
    -009`) asserts EXACTLY one raised, classified `DatabaseError` across the
    whole choreography (`errorClass` / `nativeCode`, the `m-db-error`
    vocabulary) and that every OTHER present step succeeded — the contention
    round's own well-formedness guard. A `concurrencySuccess`-shape case
    (`-007`/`-008`) asserts NO node ever raised, and grades each `kind:
    "read"` step's observed rows against its own `expectRows` (order-
    insensitive, `compare_rows`); a `kind: "write"` step asserts only that it
    reached this point at all (no block/no raise).
    """
    meta = engine.load_case_metamodel(case)
    from parallax.conformance import provision

    provisioner.reset(meta, provision.load_fixtures(str(case_document(case)["model"])))

    rounds = concurrency_runner.parse_rounds(case, "postgres")
    dialect = dialect_for("postgres")
    isolation = "serializable" if case.case_id in _SERIALIZABLE_ISOLATION_CASES else None
    run = concurrency_runner.run_rounds(
        rounds, dialect, lambda: provisioner.peer(autocommit=False), isolation=isolation
    )

    if case.shape == "error":
        raised = [
            (index, node, outcome.error)
            for index, round_outcomes in enumerate(run.rounds)
            for node, outcome in round_outcomes.items()
            if outcome.error is not None
        ]
        assert len(raised) == 1, (case.case_id, raised)
        raised_index, raised_node, exc = raised[0]
        then = case_document(case)["then"]
        assert exc is not None
        assert exc.category == then["errorClass"], (case.case_id, exc)
        assert exc.native_code == then["nativeCode"]["postgres"], (case.case_id, exc)
        for index, round_outcomes in enumerate(run.rounds):
            for node, outcome in round_outcomes.items():
                if (index, node) != (raised_index, raised_node):
                    assert outcome.error is None, (case.case_id, index, node, outcome.error)
    else:
        assert case.shape == "concurrencySuccess"
        for round_spec, round_outcomes in zip(rounds, run.rounds, strict=True):
            for node, step in round_spec.items():
                outcome = round_outcomes[node]
                assert outcome.error is None, (case.case_id, node, outcome.error)
                if step.kind == "read":
                    assert step.expect_rows is not None, (case.case_id, node)
                    compare_rows(
                        cast("list[dict[str, Any]]", list(outcome.rows)),
                        cast("list[dict[str, Any]]", list(step.expect_rows)),
                    )
