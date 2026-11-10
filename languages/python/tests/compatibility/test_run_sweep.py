"""The pg-full run sweep (m-conformance-adapter `run`, real Postgres).

Every exercised reachable read case is compiled, executed against a freshly reset
real database (``DROP SCHEMA … CASCADE`` → descriptor DDL → fixtures), and its
observation (``then.rows`` / ``then.graph`` / ``then.graphs``, order-insensitive
where the case format says so, wire space) compared against the golden; its
emitted SQL and binds equal the golden keyed by the profile's own dialect, root
and every deep-fetch child level alike. This is the tracer path proven end to end — compile (where
eligible) to canonical SQL/binds, then run against a reset database. Docker-
gated; a skip is reported, never silent.
"""

from __future__ import annotations

import contextlib
import json
import re
from collections import Counter
from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, Final, cast

import pytest

from parallax.conformance import adapter, case_format, concurrency_runner, engine, models
from parallax.conformance.profile import Profile
from parallax.core import storage_layout
from parallax.core.db_error import Category, DatabaseError
from parallax.core.metamodel import Metamodel
from tests._support.bind_positions import assert_zero_signs, statement_bind_positions
from tests._support.case_corpus import reachable_cases
from tests._support.corpus import (
    CollectionKinds,
    case_document,
    case_fixtures,
    compare_graph,
    compare_rows,
    compare_rows_in_order,
    compare_stored_data_issues,
    wire_value_deep,
)
from tests._support.driver_writes import (
    RecordingCaseDatabase,
    assert_driver_write_document_nulls,
    assert_driver_write_zero_signs,
)
from tests._support.repo import validate_adapter_envelope
from tests._support.sweep_goldens import (
    COMPILE_EXERCISED,
    WRITE_EXERCISED,
    assert_wire_binds,
    assert_write_emissions_equal_goldens,
    wire_binds,
    write_golden_statements,
)
from tests.compatibility._float_zero_support import (
    project_float_zero_negative,
    spell_float_zero_negative,
)

# The reachable read cases whose fixtures + observation this file runs end-to-
# end: every compile-exercised read (including the instance-form-graph reads
# m-value-object-023/-024/-028..-031, the multi-concrete polymorphic
# m-inheritance-106/-107/-108/-109, and the milestone-set
# m-snapshot-read-013/-014, which materialize
# and grade their `then.graph` / `then.graphs` here) PLUS every case DECLARED
# `compileEligibility: run-only` (the query-result-dependent deep-fetch tail:
# `compile` can never emit their query-result-dependent child binds, so `run` is
# the ONLY lane that ever grades them — derived from the corpus declaration at
# collection time, never a hard-coded id list, m-conformance-adapter).
RUN_EXERCISED = frozenset(COMPILE_EXERCISED)


def _reachable_run_cases() -> list[case_format.Case]:

    reachable = reachable_cases()
    return [
        c
        for c in reachable
        if c.shape == "read" and (c.case_id in RUN_EXERCISED or engine.eligibility(c) is not None)
    ]


_CASES = _reachable_run_cases()


def _read_golden_statements(
    case: case_format.Case, dialect_name: str
) -> list[tuple[str, list[Any]]]:
    """A read case's ordered golden statements (root, then every deep-fetch
    child level) — the same per-entry `{sql, binds}` extraction
    `write_golden_statements` uses for a write case, applied to a read's own
    `then.statements`."""
    statements = case_document(case)["then"]["statements"]
    out: list[tuple[str, list[Any]]] = []
    for entry in cast("list[dict[str, Any]]", statements):
        sql = entry["sql"]
        text = cast("dict[str, str]", sql)[dialect_name] if isinstance(sql, dict) else sql
        binds = entry.get("binds", [])
        if isinstance(binds, dict):
            binds = cast("dict[str, list[object]]", binds)[dialect_name]
        out.append((cast("str", text), list(cast("list[object]", binds))))
    return out


def _grade_execution_lifecycle(then: dict[str, Any], observations: dict[str, Any]) -> None:
    """The delivered stream against `then.executionLifecycle`, where a case authors it.

    The adapter reports the observation for exactly the cases that author the
    oracle (`m-conformance-adapter`), so an authoring case whose envelope omits
    it is an adapter that installed no Provider rather than a case that asserted
    nothing — which is why the absence is asserted rather than skipped past.

    The stream is compared WHOLE and exactly, unlike every other oracle this
    sweep grades: an event stream is not a projection to normalize but the
    delivery itself, and the two facts that matter most about it — that nothing
    extra was delivered and that nothing was delivered out of order — are
    exactly what a per-field comparison would give up. The adapter has already
    reduced its side to the portable shape, so the only difference two
    conforming implementations can have here is one the case means to state.
    """
    expected = then.get("executionLifecycle")
    if expected is None:
        assert "executionLifecycle" not in observations
        return
    observed = observations["executionLifecycle"]
    assert observed == expected, (
        f"execution lifecycle mismatch:\n  observed: {observed!r}\n  expected: {expected!r}"
    )


def _is_streamed(case: case_format.Case) -> bool:
    when = case_document(case).get("when", {})
    return isinstance(when, dict) and "stream" in when


# A page's root statement carries the page's own bound; a child level inside one
# never does, a page size bounding root positions and never the rows a level
# gathers (`m-snapshot-read`).
_PAGE_BOUND: Final = re.compile(r"\blimit \?(?: for share of t0| lock in share mode)?$")


def _stated_roots(then: dict[str, Any]) -> int:
    """How many roots a read case states its result carries.

    One number from either result member: a single-instant read states one
    graph, and a milestone-set read one per milestone, whose roots together are
    the delivery's own. The delivery's page arithmetic is the same over both,
    because a page counts root positions and never milestones.
    """
    graphs = cast("list[dict[str, Any]]", then.get("graphs", []))
    graph_bodies = [cast("dict[str, list[Any]]", entry["graph"]) for entry in graphs] or [
        cast("dict[str, list[Any]]", then["graph"])
    ]
    return sum(len(nodes) for body in graph_bodies for nodes in body.values())


def _stream_root_positions(case: case_format.Case, statements: Sequence[str]) -> set[int]:
    """Where each page's ROOT statement sits in a streamed case's flat list.

    `m-case-format` makes ``then.statements`` the pages' own `1 + L` groups
    concatenated, and a page executes a child level only where the level above it
    GATHERED parent keys — so a page's group is one root statement followed by as
    many levels as that page's own rows reached, which no count of the query's
    include paths recovers. What every page's root statement carries and no child
    level of one ever does is the page's own bound, so that is what a root is
    recognized by. How MANY pages there are is the delivery's own arithmetic — a
    page asks for its batch plus the one LOOKAHEAD root that proves another page
    follows, and ends the delivery as soon as one comes back short of that, while
    a declared limit caps the final page and reads no lookahead root at all — and
    a delivery that ran a different number of them fails here rather than being
    graded against the wrong statements.
    """
    if not statements:
        # A position with no concrete subtype ends its delivery with no page
        # statement at all (m-case-format *Structurally empty reads*).
        return set()
    doc = case_document(case)
    query = cast("dict[str, Any]", doc["when"]["objectQuery"])
    size = cast("int", cast("dict[str, Any]", doc["when"]["stream"])["batchSize"])
    limit = cast("int | None", query.get("limit"))
    roots = _stated_roots(cast("dict[str, Any]", doc["then"]))
    pages = 0
    delivered = 0
    while True:
        remaining = None if limit is None else limit - delivered
        lookahead = remaining is None or remaining > size
        requested = size + 1 if remaining is None or lookahead else remaining
        returned = min(requested, roots - delivered)
        pages += 1
        delivered += returned - 1 if lookahead and returned == requested else returned
        if not lookahead or returned < requested:
            break
    positions = {index for index, sql in enumerate(statements) if _PAGE_BOUND.search(sql)}
    assert positions and min(positions) == 0, (case.case_id, sorted(positions))
    assert len(positions) == pages, (case.case_id, sorted(positions), pages)
    return positions


def _unordered_key_sets(binds: list[object]) -> list[object]:
    return [
        Counter(cast("list[object]", bind)) if isinstance(bind, list) else bind for bind in binds
    ]


def _grade_read_emissions(
    case: case_format.Case,
    profile: Profile,
    model: Metamodel,
    emissions: Sequence[dict[str, Any]],
) -> None:
    """A read's emissions against its golden statements, in order."""
    golden_statements = _read_golden_statements(case, profile.dialect.name)
    assert len(emissions) == len(golden_statements), (case.case_id, emissions, golden_statements)
    # Which emissions carry user-authored binds: an eager read's is its one root
    # statement, and a streamed delivery's is every page's, each of which binds
    # its predicate, the coordinates it continues from, and the size it asked
    # for. A page's own child levels stay gathered, exactly as an eager read's
    # are.
    roots = (
        _stream_root_positions(case, [sql for sql, _binds in golden_statements])
        if _is_streamed(case)
        else {0}
    )
    for index, (emission, (golden_sql, golden_binds)) in enumerate(
        zip(emissions, golden_statements, strict=True)
    ):
        assert emission["sql"] == golden_sql, (case.case_id, emission)
        observed_binds = wire_binds(emission["binds"])
        expected_binds = wire_binds(golden_binds)
        if index in roots:
            # The root statement's binds are user-authored (never gathered), so
            # their order is defined and exact.
            assert observed_binds == expected_binds, (case.case_id, emission)
            assert_zero_signs(
                observed_binds,
                expected_binds,
                statement_bind_positions(model, golden_sql, golden_binds),
            )
        else:
            # A deep-fetch child level's key-set binds are the distinct keys
            # GATHERED from the parent level's own returned rows — an unordered
            # set (m-case-format fifth assertion layer): the gathered order
            # depends on the parent query's own row order (itself possibly a
            # declared, non-id `orderBy`), so each key set compares as a MULTISET,
            # never by position. A `union all` level binds one key set per branch,
            # and any propagated as-of suffix follows at its own position.
            assert _unordered_key_sets(observed_binds) == _unordered_key_sets(expected_binds), (
                case.case_id,
                emission,
            )


@pytest.mark.parametrize(
    "case",
    _CASES,
    ids=[c.path.stem if "coordinate" in c.path.stem else c.case_id for c in _CASES],
)
def test_run_sweep(case: case_format.Case, profile: Profile, profile_run: Any) -> None:
    model = engine.load_case_metamodel(case)
    from parallax.conformance import provision

    profile_run.reset(
        engine.load_case_setup_metamodel(case),
        provision.load_fixtures(engine.case_setup_model_ref(case)),
    )

    envelope = adapter.run_case(case.path, profile_run)
    validate_adapter_envelope(envelope)
    assert envelope["status"] == "ok", envelope
    assert json.loads(json.dumps(envelope)) == envelope
    # The envelope names the profile this lane declares and reports the dialect the
    # container's own adapter executed in — the same key the goldens below resolve.
    assert envelope["profile"] == profile.name
    assert envelope["dialect"] == profile.dialect.name

    doc = case_document(case)
    then = doc.get("then", {})
    _grade_read_emissions(case, profile, model, envelope["emissions"])

    observations = envelope["observations"]
    assert observations["databaseCalls"] == then.get("databaseCalls", 1), case.case_id
    _grade_execution_lifecycle(then, observations)

    if "rows" in then:
        compare_rows(observations["rows"], then["rows"])
    elif "graph" in then:
        compare_graph(observations["graph"], then["graph"], CollectionKinds(model))
        compare_stored_data_issues(
            observations.get("storedDataIssues"), then.get("storedDataIssues")
        )
    elif "graphs" in then:
        expected_graphs = then["graphs"]
        observed_graphs = observations["graphs"]
        assert len(observed_graphs) == len(expected_graphs), case.case_id
        for observed_entry, expected_entry in zip(observed_graphs, expected_graphs, strict=True):
            assert wire_value_deep(observed_entry["pin"]) == wire_value_deep(
                expected_entry["pin"]
            ), case.case_id
            compare_graph(observed_entry["graph"], expected_entry["graph"], CollectionKinds(model))


def _reads_a_graph_with_includes(case: case_format.Case) -> bool:
    """Whether ``case`` reads one graph with includes, eager or streamed, and leaves
    its scope open. A milestone-set read states `then.graphs`, and it and a read with
    no includes never share, so rerunning them at page scope would show nothing."""
    document = case_document(case)
    when = cast("dict[str, Any]", document["when"])
    return (
        "graph" in document["then"]
        and "includes" in when["objectQuery"]
        and "sharingScope" not in when
    )


_PAGE_SCOPE_RERUNS = [case for case in _CASES if _reads_a_graph_with_includes(case)]


def _at_page_scope(case: case_format.Case) -> case_format.Case:
    when = {**cast("dict[str, Any]", case_document(case)["when"]), "sharingScope": "page"}
    return replace(case, document={**case.document, "when": when})


@pytest.mark.parametrize("case", _PAGE_SCOPE_RERUNS, ids=[c.case_id for c in _PAGE_SCOPE_RERUNS])
def test_a_graph_read_states_the_same_at_page_scope(
    case: case_format.Case, profile: Profile, profile_run: Any
) -> None:
    from parallax.conformance import provision

    model = engine.load_case_metamodel(case)
    profile_run.reset(
        engine.load_case_setup_metamodel(case),
        provision.load_fixtures(engine.case_setup_model_ref(case)),
    )

    run_case = (
        engine.run_stream_case if "stream" in case_document(case)["when"] else engine.run_graph_case
    )
    emissions, graph, database_calls, stored_data_issues = run_case(
        _at_page_scope(case), profile_run.port
    )

    then = cast("dict[str, Any]", case_document(case)["then"])
    _grade_read_emissions(case, profile, model, [emission.to_json() for emission in emissions])
    assert database_calls == then.get("databaseCalls", 1), case.case_id
    compare_graph(graph, then["graph"], CollectionKinds(model))
    compare_stored_data_issues(stored_data_issues, then.get("storedDataIssues"))


def _orders_rendered(profile_run: Any, run_case: Any, case_id: str) -> int:
    from parallax.conformance import provision

    case = next(c for c in _CASES if c.case_id == case_id)
    profile_run.reset(
        engine.load_case_setup_metamodel(case),
        provision.load_fixtures(engine.case_setup_model_ref(case)),
    )
    _, graph, _, _ = run_case(case, profile_run.port)
    return len({id(cast("dict[str, Any]", root)["order"]) for root in graph["OrderItem"]})


def test_a_case_declaring_a_scope_reads_at_that_scope(profile_run: Any) -> None:
    assert _orders_rendered(profile_run, engine.run_graph_case, "m-snapshot-read-052") == 3
    assert _orders_rendered(profile_run, engine.run_graph_case, "m-snapshot-read-053") == 2


def test_a_streamed_case_declaring_a_scope_reads_at_that_scope(profile_run: Any) -> None:
    assert _orders_rendered(profile_run, engine.run_stream_case, "m-snapshot-read-062") == 4
    assert _orders_rendered(profile_run, engine.run_stream_case, "m-snapshot-read-063") == 3


# The scenario cases that ALSO declare `compileEligibility: run-only` and ALSO use
# `uow` grouping (:func:`_case_uses_uow_grouping`) but whose groups INTERLEAVE —
# one unit of work's read, a CONCURRENT unit of work's own write-and-commit, then
# back to the first. `run_scenario_case`/`adapter.run_case` execute only CONTIGUOUS
# `uow` groups (`scenario._scenario_uow_spans`; a genuinely interleaved group needs a
# SECOND, independent connection this test's ordinary single-`DatabaseConnection` seam does not
# hold open), so every one of them stays OUT of `_WRITE_CASES`/
# `test_write_run_sweep`. Membership here is a routing exclusion alone;
# `_INTERLEAVED_RUNNER_CASES` below is the SUBSET this test drives through the
# interleaved runner, and names per case why it leaves the rest to the reference
# harness.
_INTERLEAVED_UOW_GROUP_CASES: Final[frozenset[str]] = frozenset(
    {
        "m-temporal-write-021",
        "m-inheritance-105",
        "m-concurrency-012",
        "m-temporal-read-010",
        "m-unit-work-031",
        "m-unit-work-032",
        "m-unit-work-034",
    }
)


# The interleaved cases `test_interleaved_uow_group_run_sweep` drives through
# `engine.run_interleaved_scenario_case` over its own dedicated executions:
# `m-concurrency-012`'s optimistic-lock race; the races of two temporal closes, each
# group at its own instant — `m-temporal-read-010` over a Transaction-Time-Only
# milestone, `m-temporal-write-021` over a Valid-Time-pinned bitemporal rectangle, and
# `m-inheritance-105` over a table-per-hierarchy subtype's tag-guarded milestone;
# and the two Repeatable Read proofs
# `m-unit-work-032` (a plain object find) and `m-unit-work-034` (a streamed
# delivery) — two units of work reading and writing one row, whose second read is
# graded against the first. The isolation cases are what make the level reach a HELD
# group through the shipped `db.transact` at all, so their `expectRows` is this
# lane's only grading of `scenario.CaseContext.isolation`. A streamed case belongs
# here because the turnstile hands off per authored STEP and a step's delivery is
# drained WHOLE before it does: the peer's commit lands between the two deliveries,
# exactly where the case authors it.
#
# `m-unit-work-031` is graded by the reference harness alone on both engines:
# its reader must face state its peer wrote and has not committed,
# and a unit of work BUFFERS its writes until its own flush edge, so the peer's DML
# is not on the wire when the reader's step runs — the window the case authors is
# one the harness's verbatim per-step execution has and a real unit of work does
# not, so running it here would assert nothing about any level.
_INTERLEAVED_RUNNER_CASES: Final[frozenset[str]] = frozenset(
    {
        "m-temporal-write-021",
        "m-inheritance-105",
        "m-concurrency-012",
        "m-temporal-read-010",
        "m-unit-work-032",
        "m-unit-work-034",
    }
)


def _case_uses_uow_grouping(case: case_format.Case) -> bool:
    """Whether the scenario names transaction-scoped unit-of-work groups."""
    when = cast("dict[str, Any]", case_document(case).get("when", {}))
    steps = cast("list[dict[str, Any]]", when.get("scenario", []))
    return any(isinstance(step.get("uow"), str) for step in steps)


# The snapshot-scenario cases whose own find step carries `objectQuery.includes`:
# a deep-fetch child level's `IN`-list binds are the distinct root keys gathered
# from that step's own root read, so each is `compileEligibility: run-only`
# (query-result-dependent) exactly as every deep-fetch read case is — which keeps
# them out of `WRITE_EXERCISED`, whose membership couples compile grading in and
# which a run-only case would fail. Run grades them here in full: the per-step
# emissions against the authored golden levels, the Database Calls, and the
# `stepGraphs` observation each `access` step's `expectGraph` asserts
# (`_grade_step_graphs`).
#
# `m-snapshot-read-017`/`-018` add the persisting write between the materializing
# find and the access, so their emissions span both a read level and committed
# DML. That is the composition the whole family exists to grade, and running it
# here is what makes the claim more than an argument: the write really commits
# against a real database, and the contents the access then reports are read off
# the view the find materialized rather than off the rows the write left.
# `-020`/`-021`/`-025` carry the destructive and temporal write shapes — a delete,
# a Transaction-Time terminate, and a bitemporal bounded rectangle split — and
# each closes with a read-back whose rows state what the database holds after the
# write, so running them grades the access and the re-read against each other.
# `-022`/`-023`/`-024` are the composite cases: a CHAIN of edits whose second hop
# names the copy the first derived, a write rewriting the whole Value Object
# document a loaded view carries, and a graph materialized over rows the scenario
# itself inserted. `-026` carries no write at all — it states the fanned-out
# multi-hop walk rule (`m-case-format`), which every other member exercises only
# in its single-hop degenerate form.
_SNAPSHOT_INCLUDE_SCENARIOS_EXERCISED: Final[frozenset[str]] = frozenset(
    {
        "m-snapshot-read-016",
        "m-snapshot-read-017",
        "m-snapshot-read-018",
        "m-snapshot-read-020",
        "m-snapshot-read-021",
        "m-snapshot-read-022",
        "m-snapshot-read-023",
        "m-snapshot-read-024",
        "m-snapshot-read-025",
        "m-snapshot-read-026",
    }
)


# The scenario cases a `given.apply` makes `compileEligibility: run-only`
# (single-connection), graded here in full exactly as a `WRITE_EXERCISED` scenario
# is, and kept out of that set because it couples compile grading in.
# `m-batch-write-054` stores a document key no member declares, which only
# out-of-band SQL can, to show a replacement leaves it in place.
_GIVEN_APPLY_SCENARIOS_EXERCISED: Final[frozenset[str]] = frozenset(
    {"m-batch-write-054", "m-storage-layout-024"}
)


# The writeSequence cases whose emissions read stored state: each is
# `compileEligibility: run-only` (query-result-dependent), because a fixture or an
# earlier entry left the milestone, range, or row its write reads. Graded here in
# full exactly as a `WRITE_EXERCISED` case is, and kept out of that set because it
# couples compile grading in.
_STORED_STATE_WRITES_EXERCISED: Final[frozenset[str]] = frozenset(
    {
        *(f"m-concurrency-{n:03d}" for n in (29, 40)),
        "m-execution-lifecycle-015",
        *(f"m-inheritance-{n:03d}" for n in (90, 91, 94, 95, 96, 97)),
        "m-storage-layout-011",
        *(
            f"m-temporal-write-{n:03d}"
            for n in (*range(2, 6), 10, *range(13, 19), 22, 23, 24, 35, 42, 43, 69, 84, 90, 91)
        ),
        *(f"m-unit-work-{n:03d}" for n in (43, 44)),
        *(f"m-value-object-{n:03d}" for n in (32, 33)),
    }
)


def _reachable_write_cases() -> list[case_format.Case]:

    return [
        c
        for c in reachable_cases()
        if (
            c.case_id in WRITE_EXERCISED
            or c.case_id in _SNAPSHOT_INCLUDE_SCENARIOS_EXERCISED
            or c.case_id in _GIVEN_APPLY_SCENARIOS_EXERCISED
            or c.case_id in _STORED_STATE_WRITES_EXERCISED
            or (
                c.case_id not in _INTERLEAVED_UOW_GROUP_CASES
                and engine.eligibility(c) is not None
                and _case_uses_uow_grouping(c)
            )
        )
    ]


_WRITE_CASES = _reachable_write_cases()


def test_every_stored_state_write_is_run_only_and_graded_against_its_golden() -> None:
    graded = {case.case_id: case for case in _WRITE_CASES}
    for case_id in _STORED_STATE_WRITES_EXERCISED:
        case = graded[case_id]
        assert engine.eligibility(case) is not None, case_id
        assert case.document.get("grading") != "state", case_id
        assert write_golden_statements(case), case_id


@pytest.mark.parametrize("case", _WRITE_CASES, ids=[c.case_id for c in _WRITE_CASES])
def test_write_run_sweep(case: case_format.Case, profile: Profile, profile_run: Any) -> None:
    """Run each keyed unit-of-work write case end-to-end against a reset database.

    An UNGROUPED scenario write commits (or, `rollback: true`, aborts) as its own
    separate unit of work, and an ungrouped find reads committed state — today's
    legacy semantics. A `uow`-GROUPED span of steps instead shares ONE held
    transaction: a grouped write applies on it without its own per-step commit, and
    a grouped find reads THROUGH that SAME transaction (read-your-own-writes,
    possibly uncommitted mid-transaction state), committing or rolling back only at
    the group's own last step. A writeSequence executes the whole FK-ordered
    sequence in one transaction. Grading: the envelope's per-step emissions equal the
    golden DML, each at a `casePointer` well-formed for the case's shape, and its total
    Database Calls the case's `then.databaseCalls`; every scenario
    row-observing step's `stepRows` observation equals its `expectRows`
    (:func:`_grade_step_rows`), every direct predicate-write step's
    `stepAffectedRows` observation its `expectAffectedRows`
    (:func:`_grade_step_affected_rows`), each group's fate the one `then.units` states, and
    the tables a scenario's `then.tableState` states hold its rows;
    a writeSequence's committed `tableState` observation equals `then.tableState`,
    table for table. The binds each golden write handed the driver carry the
    golden's zero sign at every declared float position
    (:func:`_grade_write_run`).
    """
    model = engine.load_case_metamodel(case)
    profile_run.reset(engine.load_case_setup_metamodel(case), case_fixtures(case))
    _grade_write_run(case, model, *_run_recording_writes(case, profile, profile_run))


def _run_recording_writes(
    case: case_format.Case, profile: Profile, profile_run: Any
) -> tuple[dict[str, Any], RecordingCaseDatabase]:
    """Run ``case`` over the fixture's database, recording each driver write."""
    port = RecordingCaseDatabase(profile_run.port)
    return adapter.run_case(case.path, profile.on_stand_in(port)), port


def _grade_write_run(
    case: case_format.Case,
    model: Metamodel,
    envelope: dict[str, Any],
    port: RecordingCaseDatabase,
) -> None:
    """Grade one write case's run: emissions, driver writes, and observations.

    The run lane reports a scalar bind re-encoded as a Wire value, which spells a
    managed ``-0.0`` as ``0.0``, so a scalar float write's sign is graded on the
    driver bind recorded before the database stored it.
    """
    validate_adapter_envelope(envelope)
    assert envelope["status"] == "ok", envelope
    if case.document.get("grading") == "state":
        _grade_state_run(case, model, envelope)
        return

    golden_statements = write_golden_statements(case)
    assert_write_emissions_equal_goldens(case, model, golden_statements, envelope["emissions"])
    assert_driver_write_zero_signs(model, port.dialect, golden_statements, port.writes)
    assert_driver_write_document_nulls(model, port.dialect, golden_statements, port.writes)
    assert envelope["observations"]["databaseCalls"] == case_document(case)["then"]["databaseCalls"]
    _grade_execution_lifecycle(case_document(case)["then"], envelope["observations"])

    if case.shape == "scenario":
        steps = cast("list[dict[str, Any]]", case_document(case)["when"]["scenario"])
        _grade_step_rows(case, model, steps, envelope)
        _grade_step_affected_rows(case, steps, envelope)
        # `expectError` steps grade through the adapter's `errors` observation
        # (`m-conformance-adapter` / `errorObservation.errorClass`): one entry
        # per declaring step, in step order — and NO entry for any other
        # scenario (the adapter omits an empty `errors` array entirely).
        expected_errors = [
            {"at": f"/scenario/{index}", "errorClass": step["expectError"]}
            for index, step in enumerate(steps)
            if "expectError" in step
        ]
        observed_errors = envelope["observations"].get("errors", [])
        assert observed_errors == expected_errors, (case.case_id, observed_errors)
        _grade_step_graphs(case, model, steps, envelope)
        _grade_units(case, envelope["observations"])
        if "tableState" in case_document(case)["then"]:
            _grade_table_state(case, model, envelope["observations"])
    else:
        _grade_table_state(case, model, envelope["observations"])


def _grade_table_state(
    case: case_format.Case, model: Metamodel, observations: dict[str, Any]
) -> None:
    """The tables the run read back hold exactly the rows `then.tableState`
    states, table for table."""
    expected_state = cast(
        "dict[str, list[dict[str, Any]]]", case_document(case)["then"]["tableState"]
    )
    observed_state = observations["tableState"]
    _assert_layout_shaped_table_state(case, model, observed_state)
    assert set(observed_state) >= set(expected_state), (case.case_id, observed_state)
    for table, expected_rows in expected_state.items():
        compare_rows(observed_state[table], expected_rows)


def _expected_units(case: case_format.Case) -> dict[str, Any]:
    """Each `uow` group's fate as the case states it, a group it states none
    for committing."""
    steps = cast("list[dict[str, Any]]", case_document(case)["when"]["scenario"])
    stated = cast("dict[str, Any]", case_document(case)["then"].get("units", {}))
    labels = dict.fromkeys(step["uow"] for step in steps if isinstance(step.get("uow"), str))
    return {label: stated.get(label, {"outcome": "committed"}) for label in labels}


def _grade_units(case: case_format.Case, observations: dict[str, Any]) -> None:
    """Each group's reported fate is the one the case states: its outcome, and
    the flush failure that ended it — where it ran, the object it reports, and
    its Shortfall or error."""
    observed = cast("dict[str, Any]", observations.get("units", {}))
    expected = _expected_units(case)
    assert set(observed) == set(expected), (case.case_id, observed)
    for label, fate in expected.items():
        reported = observed[label]
        assert reported["outcome"] == fate["outcome"], (case.case_id, label, reported)
        failure = fate.get("flushFailure")
        if failure is None:
            assert "flushFailure" not in reported, (case.case_id, label, reported)
            continue
        actual = reported["flushFailure"]
        assert actual["at"] == failure["at"], (case.case_id, label, actual)
        assert (actual.get("shortfall"), actual.get("error")) == (
            failure.get("shortfall"),
            failure.get("error"),
        ), (case.case_id, label, actual)
        assert _same_entity(actual["entity"], failure["entity"]), (case.case_id, label, actual)
        assert wire_value_deep(actual["key"]) == wire_value_deep(failure["key"]), (
            case.case_id,
            label,
            actual,
        )


def _same_entity(reported: str, stated: str) -> bool:
    """Whether a reported canonical Entity spelling is the one a case states,
    canonically or by its bare local name."""
    return reported == stated or reported.rpartition(".")[2] == stated


def _grade_state_run(case: case_format.Case, model: Metamodel, envelope: dict[str, Any]) -> None:
    """Grade a state-graded scenario on what it states: each find's published
    rows, each submission its verb refused, each group's fate, and the final
    tables. It authors no golden, so neither the statements a flush chose nor
    the Database Calls they cost are graded."""
    steps = cast("list[dict[str, Any]]", case_document(case)["when"]["scenario"])
    observations = envelope["observations"]
    assert envelope["emissions"] == [], (case.case_id, envelope["emissions"])
    _grade_step_rows(case, model, steps, envelope)
    expected_errors = [
        {"at": f"/scenario/{index}/write/{position}", "errorClass": entry["expectError"]}
        for index, step in enumerate(steps)
        for position, entry in enumerate(
            step["write"] if isinstance(step.get("write"), list) else []
        )
        if "expectError" in entry
    ]
    assert observations.get("errors", []) == expected_errors, (case.case_id, observations)
    _grade_units(case, observations)
    _grade_table_state(case, model, observations)


def _write_case(case_id: str) -> case_format.Case:
    (case,) = [c for c in _WRITE_CASES if c.case_id == case_id]
    return case


_PORT_NEVER_REACHED: Final = cast("RecordingCaseDatabase", None)


@pytest.mark.parametrize(
    ("case_id", "fault", "refusal"),
    [
        pytest.param(case_id, fault, refusal, id=case_id)
        for case_id, fault, refusal in (
            ("m-document-codec-015", spell_float_zero_negative, r"^bind 2: "),
            ("m-document-codec-016", spell_float_zero_negative, r"^bind 2: "),
            ("m-core-009", project_float_zero_negative, r"^driver bind 1: "),
            ("m-core-010", project_float_zero_negative, r"^driver bind 1: "),
        )
    ],
)
def test_write_run_grading_rejects_a_float_zero_turned_negative(
    case_id: str,
    fault: Callable[[pytest.MonkeyPatch], None],
    refusal: str,
    profile: Profile,
    profile_run: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A float zero turned negative before the database fails grading, and the
    restored run passes.

    A document leaf's fault reaches the reported Wire bind, so the emission
    refuses it. A scalar's reaches only the driver bind: the reported bind is
    re-encoded as ``0.0``, and table state compares in decimal space.
    """
    case = _write_case(case_id)
    model = engine.load_case_metamodel(case)
    profile_run.reset(engine.load_case_setup_metamodel(case), case_fixtures(case))
    fault(monkeypatch)
    envelope, port = _run_recording_writes(case, profile, profile_run)
    monkeypatch.undo()
    with pytest.raises(AssertionError, match=refusal):
        _grade_write_run(case, model, envelope, port)

    profile_run.reset(engine.load_case_setup_metamodel(case), case_fixtures(case))
    _grade_write_run(case, model, *_run_recording_writes(case, profile, profile_run))


def _run_answering_goldens(case: case_format.Case) -> dict[str, Any]:
    """The run envelope of a writeSequence whose first entry emitted its goldens."""
    return {
        "schemaVersion": adapter.SCHEMA_VERSION,
        "command": "run",
        "status": "ok",
        "adapter": {"language": "python", "name": "parallax", "version": "0"},
        "case": f"cases/{case.path.name}",
        "profile": "pg-full",
        "dialect": "postgres",
        "caseShape": case.shape,
        "emissions": [
            {"casePointer": "/writeSequence/0", "sql": sql, "binds": binds}
            for sql, binds in write_golden_statements(case)
        ],
        "observations": {"databaseCalls": len(write_golden_statements(case))},
    }


def test_write_run_grading_refuses_a_write_attributed_to_a_read() -> None:
    case = _write_case("m-temporal-write-002")
    envelope = _run_answering_goldens(case)
    envelope["emissions"][1]["casePointer"] = "/objectQuery"
    with pytest.raises(AssertionError, match=r"m-temporal-write-002.*/objectQuery"):
        _grade_write_run(case, engine.load_case_metamodel(case), envelope, _PORT_NEVER_REACHED)


def test_write_run_grading_refuses_a_decimal_bind_at_another_scale() -> None:
    case = _write_case("m-temporal-write-002")
    envelope = _run_answering_goldens(case)
    assert envelope["emissions"][0]["binds"][2] == "100.00"
    envelope["emissions"][0]["binds"][2] = "100.0"
    with pytest.raises(AssertionError, match=r"'100\.0'.*'100\.00'"):
        _grade_write_run(case, engine.load_case_metamodel(case), envelope, _PORT_NEVER_REACHED)


def _grade_step_rows(
    case: case_format.Case, model: Metamodel, steps: list[dict[str, Any]], envelope: Any
) -> None:
    """Grade every row-observing step's `expectRows` against the run's own `stepRows`
    observation.

    The values a step published are what `m-conformance-adapter`'s `stepRows`
    reports — one entry per read step the adapter drove plus each `mutate`
    declaring `expectRows`, at that step's own pointer, in step order. What is
    graded is therefore what the step HANDED OVER, not what its statements
    returned: a streamed step's entry is its whole delivery's roots, a deep-fetch
    step's is its roots alone, and a mutation's is its derived Wire mapping.

    A STREAMED step is the one row oracle compared POSITIONALLY: its `expectRows`
    are the roots the delivery published across every page IN DELIVERY ORDER
    (`m-case-format` *Streamed read steps*), and that order is the Continuation
    Order the delivery exists to hold to, so a delivery that published the right
    roots in the wrong sequence must fail. Every other step compares through the
    same order-insensitive comparator the rest of the corpus's row oracles use.

    The pointer list is asserted whole, so a lane that stopped driving a step fails
    on the list rather than passing on the steps it still answers — the same rule
    :func:`_grade_step_graphs` follows.
    """
    expected = [
        (f"/scenario/{index}", step.get("expectRows"), "stream" in step)
        for index, step in enumerate(steps)
        if "objectQuery" in step or (step.get("action") == "mutate" and "expectRows" in step)
    ]
    observed = cast("list[dict[str, Any]]", envelope["observations"].get("stepRows", []))
    assert [entry["at"] for entry in observed] == [at for at, _, _ in expected], (
        case.case_id,
        observed,
    )
    for entry, (_at, expected_rows, streamed) in zip(observed, expected, strict=True):
        if expected_rows is None:
            continue
        compare = compare_rows_in_order if streamed else compare_rows
        compare(entry["rows"], expected_rows)


def _grade_step_affected_rows(
    case: case_format.Case, steps: list[dict[str, Any]], envelope: Any
) -> None:
    """Grade every direct predicate-write step's `expectAffectedRows` against the
    run's own `stepAffectedRows` observation: the count its public verb returned,
    at that step's own pointer, in step order. The whole ordered list is
    asserted, so a run that dropped or invented a count fails on it, and a run
    reporting none for a case stating none reports the empty list."""
    expected = [
        {"at": f"/scenario/{index}", "affectedRows": step["expectAffectedRows"]}
        for index, step in enumerate(steps)
        if "expectAffectedRows" in step
    ]
    observed = envelope["observations"].get("stepAffectedRows", [])
    assert observed == expected, (case.case_id, observed)


# The `stepRows` oracle's own directional proof, run without a database: an
# implementation that published the wrong values, stopped answering a step, or
# published a delivery's roots out of the order it delivered them must be
# refused rather than accepted.
#
# `m-unit-work-030` carries the ORDER property: its two streamed steps each
# publish three roots across two pages, so a swap inside one entry leaves the
# multiset intact and only a positional comparison catches it.
_STEP_ROWS_ORACLE_CASE: Final[str] = "m-unit-work-030"


def _step_rows_envelope(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """A conforming `stepRows` envelope for ``steps``: every read step the adapter
    drives, answering exactly the rows that step's own `expectRows` states.

    Each entry carries its OWN copy of those rows, so damaging one states what an
    implementation published rather than editing the case it is graded against.
    """
    return {
        "observations": {
            "stepRows": [
                {"at": f"/scenario/{index}", "rows": deepcopy(step["expectRows"])}
                for index, step in enumerate(steps)
                if "objectQuery" in step
            ]
        }
    }


def _step_rows_oracle_case() -> tuple[case_format.Case, Metamodel, list[dict[str, Any]]]:
    case = next(c for c in _WRITE_CASES if c.case_id == _STEP_ROWS_ORACLE_CASE)
    model = engine.load_case_metamodel(case)
    return case, model, cast("list[dict[str, Any]]", case_document(case)["when"]["scenario"])


def test_grade_step_rows_refuses_a_run_that_published_the_wrong_values() -> None:
    case, model, steps = _step_rows_oracle_case()
    envelope = _step_rows_envelope(steps)
    del envelope["observations"]["stepRows"][0]["rows"][0]

    with pytest.raises(AssertionError):
        _grade_step_rows(case, model, steps, envelope)


def test_grade_step_rows_refuses_a_run_that_left_a_step_unanswered() -> None:
    case, model, steps = _step_rows_oracle_case()
    envelope = _step_rows_envelope(steps)
    del envelope["observations"]["stepRows"][-1]

    with pytest.raises(AssertionError):
        _grade_step_rows(case, model, steps, envelope)


def test_grade_step_rows_accepts_a_delivery_that_published_its_roots_in_order() -> None:
    case, model, steps = _step_rows_oracle_case()
    envelope = _step_rows_envelope(steps)

    assert [entry["at"] for entry in envelope["observations"]["stepRows"]] == [
        "/scenario/0",
        "/scenario/2",
    ]
    _grade_step_rows(case, model, steps, envelope)


def test_grade_step_rows_refuses_a_delivery_that_published_its_roots_reordered() -> None:
    # The roots are the SAME three; only the sequence the delivery handed them over
    # in changed, which the Continuation Order fixes (`m-case-format` *Streamed read
    # steps*). A multiset comparison accepts this run.
    case, model, steps = _step_rows_oracle_case()
    envelope = _step_rows_envelope(steps)
    rows = envelope["observations"]["stepRows"][0]["rows"]
    rows[0], rows[-1] = rows[-1], rows[0]

    with pytest.raises(AssertionError):
        _grade_step_rows(case, model, steps, envelope)


def test_grade_step_rows_accepts_an_eager_step_whose_rows_arrived_reordered() -> None:
    # The positional rule is the STREAM's, not the channel's: an eager step states a
    # result set, whose order no case fixes, so it keeps the corpus-wide multiset
    # comparison.
    case, model, steps = _step_rows_oracle_case()
    eager = deepcopy(steps)
    for step in eager:
        step.pop("stream", None)
    envelope = _step_rows_envelope(eager)
    rows = envelope["observations"]["stepRows"][0]["rows"]
    rows[0], rows[-1] = rows[-1], rows[0]

    _grade_step_rows(case, model, eager, envelope)


def _grade_step_graphs(
    case: case_format.Case,
    model: Metamodel,
    steps: list[dict[str, Any]],
    envelope: Any,
) -> None:
    """Grade every `expectGraph` step against the run's own `stepGraphs` observation.

    The relationship contents a step observes are what
    `m-conformance-adapter`'s `stepGraphs` reports — one entry per declaring step,
    at that step's own pointer, in step order — compared through the SAME
    model-driven graph comparator `then.graph` is graded by, so an entity
    collection is a multiset and a `multiplicity: many` Value Object positional.
    A declaring step with no entry is an unanswered oracle rather than a pass,
    which is what makes this generic over the observable's two placements: an
    `access` step's retained view and a find step's own materialized graph are
    both reported here, and a lane that answered only one of them fails on the
    pointer list rather than passing on the half it did answer.
    """
    expected = [
        (f"/scenario/{index}", cast("dict[str, Any]", step["expectGraph"]))
        for index, step in enumerate(steps)
        if "expectGraph" in step
    ]
    observed = cast("list[dict[str, Any]]", envelope["observations"].get("stepGraphs", []))
    assert [entry["at"] for entry in observed] == [at for at, _ in expected], (
        case.case_id,
        observed,
    )
    kinds = CollectionKinds(model)
    for entry, (_at, expected_graph) in zip(observed, expected, strict=True):
        compare_graph(entry["graph"], expected_graph, kinds)


def _assert_layout_shaped_table_state(
    case: case_format.Case, model: Metamodel, observed_state: dict[str, list[dict[str, Any]]]
) -> None:
    """Every compiled Table Layout is observed once, whole, and in canonical order.

    A shared table-per-hierarchy table therefore reports a sibling-only column as
    ``null`` instead of omitting it, and no observation carries a column the layout
    does not place or an order the layout does not fix.
    """
    layouts = {
        layout.table.name: [slot.column.name for slot in layout.columns]
        for layout in storage_layout.storage_layout_facet_of(model).tables
    }
    assert set(observed_state) == set(layouts), (case.case_id, sorted(observed_state))
    for table, rows in observed_state.items():
        for row in rows:
            assert list(row) == layouts[table], (case.case_id, table, list(row))


def _reachable_interleaved_uow_group_cases() -> list[case_format.Case]:

    return [c for c in reachable_cases() if c.case_id in _INTERLEAVED_RUNNER_CASES]


_INTERLEAVED_CASES = _reachable_interleaved_uow_group_cases()


@pytest.mark.parametrize("case", _INTERLEAVED_CASES, ids=[c.case_id for c in _INTERLEAVED_CASES])
def test_interleaved_uow_group_run_sweep(case: case_format.Case, profile_run: Any) -> None:
    """The two-connection interleaved-group entry point: two units of work held
    open at once, each over a dedicated session this run opened for it
    (`engine.run_interleaved_scenario_case`), never through `adapter.run_case`
    (which cannot hold a second session open).

    Grades the layers `test_write_run_sweep` grades for an ordinary scenario —
    the ordered per-step golden DML (flattened across both interleaved groups
    plus the trailing ungrouped verify find, in AUTHORED step order),
    `then.databaseCalls`, every find step's `stepRows` against its authored
    `expectRows` (the grouped observing finds AND the trailing ungrouped verify,
    through the same :func:`_grade_step_rows` every scenario lane's rows go
    through), each group's fate (`then.units`): the conflict a group's flush
    reported, and a commit for every group that states none — and, where the
    case states it, `then.tableState`.

    The `expectRows` grade is each case's own teeth, and what it catches
    differs per case. For `m-concurrency-012` a broken abort that left the doomed
    group's buffered insert durable would still emit well-formed DML and report
    the conflict, and its trailing verify find would observe account
    9. For the temporal races (`m-temporal-read-010`, `m-temporal-write-021`,
    `m-inheritance-105`) the losing close's emission is well-formed whether or
    not the race happened, so its fate and the table it leaves — the winner's
    successor current, the loser's close changing nothing — are what show the
    stale gate met the database. For the Repeatable Read cases
    `m-unit-work-032` and `-034` the emissions
    and the fates are identical whatever level the groups opened at, and the
    reader's SECOND read is the ONLY thing that differs: at the connection's own
    default it answers the peer's committed 999.00 rather than the 250.00 it
    read first — for `-034` on the second DELIVERY, every page of which is
    issued after the peer committed, so nothing narrower than the transaction
    can hold the roots fixed.
    """
    model = engine.load_case_metamodel(case)
    profile_run.reset(engine.load_case_setup_metamodel(case), case_fixtures(case))

    run = engine.run_interleaved_scenario_case(
        case, profile_run.port, profile_run.interleaved_execution
    )

    assert_write_emissions_equal_goldens(
        case,
        model,
        write_golden_statements(case),
        [emission.to_json() for emission in run.emissions],
    )

    then = case_document(case)["then"]
    assert run.database_calls == then["databaseCalls"], case.case_id
    observations: dict[str, Any] = {
        "stepRows": run.step_rows,
        "units": run.units,
        "tableState": run.table_state,
    }
    steps = cast("list[dict[str, Any]]", case_document(case)["when"]["scenario"])
    _grade_step_rows(case, model, steps, {"observations": observations})
    _grade_units(case, observations)
    if "tableState" in then:
        _grade_table_state(case, model, observations)


# The Wire `mutate` whole-occurrence replacement cases: a find, then edits whose
# `expectRows` state the copy each derives. Python ships no Wire edit verb, so the
# engine's own derivation is what this grades. Their find statement is not graded:
# its golden omits the `marks` presence probe the other top-level `many`
# goldens carry.
_EDIT_OCCURRENCE_CASES: Final[tuple[str, ...]] = ("m-edit-010", "m-edit-011")


@pytest.mark.parametrize("case_id", _EDIT_OCCURRENCE_CASES)
def test_edit_occurrence_run_grades_each_derived_copy(
    case_id: str, profile: Profile, profile_run: Any
) -> None:

    (case,) = [c for c in reachable_cases() if c.case_id == case_id]
    model = engine.load_case_metamodel(case)
    profile_run.reset(engine.load_case_setup_metamodel(case), case_fixtures(case))

    envelope = adapter.run_case(case.path, profile_run)

    validate_adapter_envelope(envelope)
    assert envelope["status"] == "ok", envelope
    assert envelope["observations"]["databaseCalls"] == case_document(case)["then"]["databaseCalls"]
    steps = cast("list[dict[str, Any]]", case_document(case)["when"]["scenario"])
    _grade_step_rows(case, model, steps, envelope)


def _reachable_error_cases() -> list[case_format.Case]:
    """The single-connection error-shape cases (statement trigger, no choreography)."""

    return [
        c
        for c in reachable_cases()
        if c.shape == "error" and "concurrency" not in (case_document(c).get("when") or {})
    ]


_ERROR_CASES = _reachable_error_cases()


@pytest.mark.parametrize("case", _ERROR_CASES, ids=[c.case_id for c in _ERROR_CASES])
def test_error_run_sweep(case: case_format.Case, profile: Profile, profile_run: Any) -> None:
    """Run each single-connection m-db-error case against a reset real database.

    The authored trigger DML executes in order; the final statement raises a real
    database error at the port boundary, and the envelope's classification
    (`errorClass` / `nativeCode`) must equal the case's `then.errorClass` and
    per-dialect `then.nativeCode`. Fixtures load only when the case declares
    `given.fixtures` (the unique-violation cases self-seed via their own trigger).
    """
    from parallax.conformance import provision

    doc = case_document(case)
    given = cast("dict[str, Any]", doc.get("given") or {})
    fixtures = (
        provision.load_fixtures(engine.case_setup_model_ref(case)) if given.get("fixtures") else {}
    )
    profile_run.reset(engine.load_case_setup_metamodel(case), fixtures)

    envelope = adapter.run_case(case.path, profile_run)
    validate_adapter_envelope(envelope)
    assert envelope["status"] == "ok", envelope

    then = doc["then"]
    assert envelope["observations"]["errorClass"] == then["errorClass"]
    assert envelope["observations"]["nativeCode"] == then["nativeCode"][profile.dialect.name]
    assert envelope["observations"]["databaseCalls"] == len(then["statements"])
    golden_trigger = [
        (
            entry["sql"][profile.dialect.name] if isinstance(entry["sql"], dict) else entry["sql"],
            entry.get("binds", []),
        )
        for entry in then["statements"]
    ]
    for index, (emission, (golden_sql, golden_binds)) in enumerate(
        zip(envelope["emissions"], golden_trigger, strict=True)
    ):
        assert emission["casePointer"] == f"/then/statements/{index}", (case.case_id, emission)
        assert emission["sql"] == golden_sql, (case.case_id, emission)
        assert emission["binds"] == golden_binds, (case.case_id, emission)


# --------------------------------------------------------------------------- #
# Conflict — the optimistic-lock run lane (m-concurrency). Every reachable       #
# conflict case declares `compileEligibility: run-only` (single-connection    #
# concurrency intent), so `run` is the ONLY lane that ever grades it —        #
# mirroring the pk-gen `sequence` run-only set below, neither joins           #
# `WRITE_EXERCISED` (that set couples compile AND run grading; a run-only     #
# case would fail `test_compile_sweep`'s `status == "ok"` assert). A          #
# `when.attempts` sequence (`m-concurrency-009`) is production's own replay of   #
# one invocation, each authored attempt one physical attempt of it. Every     #
# non-temporal conflict case here settles against a state a REAL read of this #
# lane observed, so the concurrent writer commits between that read and the   #
# write it invalidates. The zero-row shapes whose interference no correct     #
# client can reach — a Locking-mode target whose row a concurrent writer      #
# deleted while the required participating read held its shared lock — are    #
# absent from this lane for that reason, and the classification they would    #
# carry is pinned without a database by                                       #
# `tests/unit/test_zero_row_write_classification.py`.                         #
# --------------------------------------------------------------------------- #
_CONFLICT_CASES_EXERCISED: Final[frozenset[str]] = frozenset(
    {
        "m-concurrency-005",
        "m-concurrency-006",
        "m-concurrency-009",
        "m-concurrency-013",
        "m-value-object-046",
    }
)


def _reachable_conflict_cases() -> list[case_format.Case]:

    return [c for c in reachable_cases() if c.case_id in _CONFLICT_CASES_EXERCISED]


_CONFLICT_CASES = _reachable_conflict_cases()


def _conflict_golden_statements(
    then: dict[str, Any], dialect_name: str
) -> list[tuple[str, list[Any]]]:
    out: list[tuple[str, list[Any]]] = []
    for entry in cast("list[dict[str, Any]]", then.get("statements", [])):
        sql = entry["sql"]
        text = cast("dict[str, str]", sql)[dialect_name] if isinstance(sql, dict) else sql
        out.append((cast("str", text), list(cast("list[Any]", entry.get("binds", [])))))
    return out


@pytest.mark.parametrize("case", _CONFLICT_CASES, ids=[c.case_id for c in _CONFLICT_CASES])
def test_conflict_run_sweep(case: case_format.Case, profile: Profile, profile_run: Any) -> None:
    """Run each `conflict`-shape case against a reset real database.

    The single-attempt form (`m-concurrency-005/006/013`) grades the golden write's
    emissions, each at `/when/write`, and `then.affectedRows` — the count the
    write's own target expects, or the count a refused write reached instead. The
    `when.attempts` replay form (`m-concurrency-009`) grades each attempt's own
    statements flattened in order, each at its attempt's `write` (proving the
    `0`-then-`1` transition through each attempt's own distinct gate bind), and
    the FINAL affected-row count. A case authoring `then.databaseCalls`
    grades the calls that reached the database across every attempt — its
    resolving reads among them — and a case authoring
    `then.executionLifecycle` grades the delivered stream those calls came from,
    where that read is the Root Execution naming no golden statement. Every case
    that authors `then.tableState` grades the committed table contents; a case
    whose write is refused authors none, since the unit of work rolls back.
    """
    model = engine.load_case_metamodel(case)
    profile_run.reset(engine.load_case_setup_metamodel(case), case_fixtures(case))

    envelope = adapter.run_case(case.path, profile_run)
    validate_adapter_envelope(envelope)
    assert envelope["status"] == "ok", envelope

    doc = case_document(case)
    then = cast("dict[str, Any]", doc.get("then", {}))
    observations = envelope["observations"]
    emissions = envelope["emissions"]

    if "affectedRows" in then:
        golden_statements = [
            ("/when/write", sql, binds)
            for sql, binds in _conflict_golden_statements(then, profile.dialect.name)
        ]
        final_affected_rows = then["affectedRows"]
    else:
        attempts = cast("list[dict[str, Any]]", doc["when"]["attempts"])
        golden_statements = [
            (f"/when/attempts/{index}/write", sql, binds)
            for index, attempt in enumerate(attempts)
            for sql, binds in _conflict_golden_statements(attempt, profile.dialect.name)
        ]
        final_affected_rows = attempts[-1]["affectedRows"]
    assert len(emissions) == len(golden_statements), (case.case_id, emissions)
    for emission, (pointer, golden_sql, golden_binds) in zip(
        emissions, golden_statements, strict=True
    ):
        assert emission["casePointer"] == pointer, (case.case_id, emission)
        assert emission["sql"] == golden_sql, (case.case_id, emission)
        assert_wire_binds(model, golden_sql, golden_binds, emission["binds"])
    assert observations["affectedRows"] == final_affected_rows, case.case_id

    # `then.databaseCalls` where the case authors it: the calls that actually
    # reached the database, summed across every attempt and counting each
    # attempt's own resolving read, which is a different number from the emission
    # count whenever a call ran no authored golden.
    if "databaseCalls" in then:
        assert observations["databaseCalls"] == then["databaseCalls"], case.case_id

    _grade_execution_lifecycle(then, observations)

    if "tableState" in then:
        expected_state = cast("dict[str, list[dict[str, Any]]]", then["tableState"])
        observed_state = observations.get("tableState")
        assert observed_state is not None, case.case_id
        assert set(observed_state) >= set(expected_state), (case.case_id, observed_state)
        for table, expected_rows in expected_state.items():
            compare_rows(observed_state[table], expected_rows)


# --------------------------------------------------------------------------- #
# The pk-gen `sequence`-strategy writeSequence cases (m-pk-gen): declared      #
# `compileEligibility: run-only` (query-result-                               #
# dependent — the registry-read-derived allocated ids), so `run` is the ONLY  #
# lane that ever grades them, same reasoning as the conflict cases above.     #
# `m-pk-gen-014` (a sequence-strategy registry advance composed                #
# with a temporal audit-only insert in ONE writeSequence, two transactions)    #
# joins for the same query-result-dependent reason —                          #
# NOT `m-pk-gen-013` (already compile-eligible, `test_compile_sweep`'s own     #
# `_OPT_LOCK_AND_PK_GEN_WRITE_SEQUENCES`).                                     #
# --------------------------------------------------------------------------- #
_RUN_ONLY_WRITE_SEQUENCES_EXERCISED: Final[frozenset[str]] = frozenset(
    {
        *(f"m-pk-gen-{n:03d}" for n in range(4, 13)),
        "m-pk-gen-014",
        "m-temporal-write-011",
        "m-temporal-write-012",
    }
)


def _reachable_run_only_write_sequence_cases() -> list[case_format.Case]:

    return [c for c in reachable_cases() if c.case_id in _RUN_ONLY_WRITE_SEQUENCES_EXERCISED]


_RUN_ONLY_WRITE_SEQUENCE_CASES = _reachable_run_only_write_sequence_cases()


@pytest.mark.parametrize(
    "case", _RUN_ONLY_WRITE_SEQUENCE_CASES, ids=[c.case_id for c in _RUN_ONLY_WRITE_SEQUENCE_CASES]
)
def test_run_only_write_sequence_run_sweep(
    case: case_format.Case, profile: Profile, profile_run: Any
) -> None:
    """Run each run-only pk-gen `sequence`-strategy writeSequence case end to end
    against a reset real database — the SAME grading `test_write_run_sweep` applies
    to a compile-eligible writeSequence case, parametrized separately because a
    run-only case's compile envelope answers `status: "run-only"`, never `"ok"`
    (`test_write_run_sweep`'s `WRITE_EXERCISED` set couples compile-time grading in
    too, which a run-only member would fail)."""
    model = engine.load_case_metamodel(case)
    profile_run.reset(engine.load_case_setup_metamodel(case), case_fixtures(case))

    envelope = adapter.run_case(case.path, profile_run)
    validate_adapter_envelope(envelope)
    assert envelope["status"] == "ok", envelope

    assert_write_emissions_equal_goldens(
        case, model, write_golden_statements(case), envelope["emissions"]
    )
    assert envelope["observations"]["databaseCalls"] == case_document(case)["then"]["databaseCalls"]

    expected_state = cast(
        "dict[str, list[dict[str, Any]]]", case_document(case)["then"]["tableState"]
    )
    observed_state = envelope["observations"]["tableState"]
    assert set(observed_state) >= set(expected_state), (case.case_id, observed_state)
    for table, expected_rows in expected_state.items():
        compare_rows(observed_state[table], expected_rows)


# --------------------------------------------------------------------------- #
# The `when.concurrency` rounds runner: every two-session choreography the    #
# corpus states, whatever module owns it — the m-concurrency behavioral matrix, #
# `m-db-error`'s two-session error cases, and the isolation witnesses. Two    #
# barrier-synchronized peer sessions run verbatim statements; the error shape #
# classifies its one raised error, the success shape grades each read and    #
# write, and either grades any stated table state. Each case's own           #
# `when.uow.isolation` is what the sessions open at, read at ingress like     #
# every other declared option.                                               #
# --------------------------------------------------------------------------- #
def _reachable_concurrency_rounds_cases() -> list[case_format.Case]:

    return [
        c
        for c in reachable_cases()
        if c.shape in ("error", "concurrencySuccess")
        and "concurrency" in (case_document(c).get("when") or {})
    ]


_CONCURRENCY_CASES = _reachable_concurrency_rounds_cases()


@pytest.mark.parametrize("case", _CONCURRENCY_CASES, ids=[c.case_id for c in _CONCURRENCY_CASES])
def test_concurrency_rounds(case: case_format.Case, profile: Profile, profile_run: Any) -> None:
    """Run one `when.concurrency` case's rounds over two independently-held
    peer sessions and grade its own shape's assertion.

    An `error`-shape case asserts EXACTLY one raised, classified
    `DatabaseError` across the whole choreography (`errorClass` /
    `nativeCode`, the `m-db-error` vocabulary) and that every OTHER present
    step succeeded — the contention round's own well-formedness guard. A
    `concurrencySuccess`-shape case asserts NO node ever raised, grades each
    `kind: "read"` step's observed rows against its own `expectRows`
    (order-insensitive, `compare_rows`), and each `kind: "write"` step's
    per-statement counts against any `affectedRows` it states. Every blocking
    step must have been seen waiting on a lock, and a stated `tableState` is
    read back once both sessions closed.
    """
    from parallax.conformance import provision

    profile_run.reset(
        engine.load_case_setup_metamodel(case),
        provision.load_fixtures(engine.case_setup_model_ref(case)),
    )

    rounds = concurrency_runner.parse_rounds(case, profile.dialect.name)
    # Two raw held sessions stand in for the transactions a Database would open,
    # so each opens at the level the case resolves for itself — the authored
    # request over the configured root — rather than at the driver's default; no
    # Database is composed here, so there is no root for production to resolve
    # it against.
    with contextlib.closing(profile_run.control(autocommit=True)) as observer:
        run = concurrency_runner.run_rounds(
            rounds,
            lambda: profile_run.control(autocommit=False),
            isolation=case_format.effective_options(case).isolation,
            lock_waits=concurrency_runner.lock_waits_on(observer),
        )
    for round_spec, round_outcomes in zip(rounds, run.rounds, strict=True):
        for node, step in round_spec.items():
            if step.blocks:
                assert round_outcomes[node].waited, (case.case_id, node, "never waited")
    if case.shape == "error":
        _grade_error_rounds(case, profile, run)
    else:
        assert case.shape == "concurrencySuccess"
        _grade_success_rounds(case, rounds, run)
    then = cast("dict[str, Any]", case_document(case).get("then") or {})
    expected_state = cast("dict[str, list[dict[str, Any]]] | None", then.get("tableState"))
    if expected_state is not None:
        observed_state = engine.read_table_state(
            profile_run.port, models.load_models()[Path(case.model).stem]
        )
        for table, expected_rows in expected_state.items():
            compare_rows(cast("list[dict[str, Any]]", observed_state[table]), expected_rows)


def _grade_error_rounds(
    case: case_format.Case, profile: Profile, run: concurrency_runner.RoundsRun
) -> None:
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
    assert exc.native_code == then["nativeCode"][profile.dialect.name], (case.case_id, exc)
    for index, round_outcomes in enumerate(run.rounds):
        for node, outcome in round_outcomes.items():
            if (index, node) != (raised_index, raised_node):
                assert outcome.error is None, (case.case_id, index, node, outcome.error)


def _grade_success_rounds(
    case: case_format.Case,
    rounds: Sequence[dict[str, concurrency_runner.ConcurrencyStep]],
    run: concurrency_runner.RoundsRun,
) -> None:
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
            if step.affected_rows is not None:
                assert outcome.affected == step.affected_rows, (case.case_id, node)


def _counted_case() -> tuple[case_format.Case, list[dict[str, Any]]]:
    case = next(c for c in _WRITE_CASES if c.case_id == "m-execution-lifecycle-011")
    return case, cast("list[dict[str, Any]]", case_document(case)["when"]["scenario"])


def _counted_envelope(counts: list[tuple[int, int]]) -> dict[str, Any]:
    return {
        "observations": {
            "stepAffectedRows": [
                {"at": f"/scenario/{index}", "affectedRows": count} for index, count in counts
            ]
        }
    }


def test_grade_step_affected_rows_accepts_the_counts_each_predicate_step_states() -> None:
    case, steps = _counted_case()
    _grade_step_affected_rows(case, steps, _counted_envelope([(1, 3), (2, 0), (3, 0)]))


@pytest.mark.parametrize(
    "counts",
    [
        [(1, 2), (2, 0), (3, 0)],
        [(1, 3), (2, 0)],
        [(0, 1), (1, 3), (2, 0), (3, 0)],
        [],
    ],
    ids=["a-changed-count", "a-missing-step", "an-invented-step", "no-counts"],
)
def test_grade_step_affected_rows_refuses_any_other_report(counts: list[tuple[int, int]]) -> None:
    case, steps = _counted_case()
    with pytest.raises(AssertionError):
        _grade_step_affected_rows(case, steps, _counted_envelope(counts))


# The sweep graders' own directional proofs, run without a database: each states
# a conforming observation, then the damage a grader must refuse.
type _Damage = Callable[[dict[str, Any]], object]

_LIFECYCLE_STREAM: Final[list[dict[str, str]]] = [{"kind": "first"}, {"kind": "second"}]


def test_grade_execution_lifecycle_accepts_the_stream_the_case_states() -> None:
    _grade_execution_lifecycle(
        {"executionLifecycle": _LIFECYCLE_STREAM}, {"executionLifecycle": list(_LIFECYCLE_STREAM)}
    )
    _grade_execution_lifecycle({}, {})


@pytest.mark.parametrize(
    "observed",
    [_LIFECYCLE_STREAM[::-1], _LIFECYCLE_STREAM[:1], [*_LIFECYCLE_STREAM, {"kind": "third"}]],
    ids=["reordered", "a-lost-event", "an-invented-event"],
)
def test_grade_execution_lifecycle_refuses_any_other_stream(observed: list[dict[str, str]]) -> None:
    with pytest.raises(AssertionError, match="execution lifecycle mismatch"):
        _grade_execution_lifecycle(
            {"executionLifecycle": _LIFECYCLE_STREAM}, {"executionLifecycle": observed}
        )


def test_grade_execution_lifecycle_refuses_a_stream_the_case_does_not_author() -> None:
    with pytest.raises(AssertionError):
        _grade_execution_lifecycle({}, {"executionLifecycle": _LIFECYCLE_STREAM})


def test_grade_execution_lifecycle_refuses_an_envelope_omitting_the_stated_stream() -> None:
    with pytest.raises(KeyError):
        _grade_execution_lifecycle({"executionLifecycle": _LIFECYCLE_STREAM}, {})


def _two_page_stream() -> tuple[case_format.Case, list[str]]:
    case = next(c for c in _CASES if c.case_id == "m-snapshot-read-028")
    return case, [sql for sql, _binds in _read_golden_statements(case, "postgres")]


def test_stream_root_positions_finds_each_page_root() -> None:
    case, statements = _two_page_stream()
    assert _stream_root_positions(case, statements) == {0, 2}
    assert _stream_root_positions(case, []) == set()


def test_stream_root_positions_refuses_a_delivery_of_another_page_count() -> None:
    case, statements = _two_page_stream()
    with pytest.raises(AssertionError):
        _stream_root_positions(case, statements[:2])
    with pytest.raises(AssertionError):
        _stream_root_positions(case, [*statements, statements[2]])


def test_stream_root_positions_refuses_a_delivery_not_opening_on_a_page_root() -> None:
    case, statements = _two_page_stream()
    with pytest.raises(AssertionError):
        _stream_root_positions(case, ["select 1", *statements])


def _stated_balance_table() -> tuple[case_format.Case, Metamodel, dict[str, Any]]:
    case = _write_case("m-temporal-write-002")
    state = cast("dict[str, Any]", deepcopy(case_document(case)["then"]["tableState"]))
    return case, engine.load_case_metamodel(case), state


def _reorder_a_row(state: dict[str, Any]) -> None:
    rows = state["balance"]
    rows[0] = dict(reversed(rows[0].items()))


def test_grade_table_state_accepts_the_tables_the_case_states() -> None:
    case, model, state = _stated_balance_table()
    _grade_table_state(case, model, {"tableState": state})


_TABLE_DAMAGE: Final[dict[str, _Damage]] = {
    "a-lost-row": lambda state: state["balance"].pop(),
    "a-changed-value": lambda state: state["balance"][0].update(val="1.00"),
    "an-invented-row": lambda state: state["balance"].append(dict(state["balance"][0])),
    "a-row-off-the-layout-order": _reorder_a_row,
}


@pytest.mark.parametrize("damage", _TABLE_DAMAGE.values(), ids=_TABLE_DAMAGE.keys())
def test_grade_table_state_refuses_any_other_table(damage: _Damage) -> None:
    case, model, state = _stated_balance_table()
    damage(state)
    with pytest.raises(AssertionError):
        _grade_table_state(case, model, {"tableState": state})


_LAYOUT_DAMAGE: Final[dict[str, _Damage]] = {
    "a-lost-table": lambda state: state.pop("balance"),
    "an-invented-table": lambda state: state.update(invented=[]),
    "a-lost-column": lambda state: state["balance"][0].pop("val"),
    "an-invented-column": lambda state: state["balance"][0].update(invented=None),
    "columns-reordered": _reorder_a_row,
}


@pytest.mark.parametrize("damage", _LAYOUT_DAMAGE.values(), ids=_LAYOUT_DAMAGE.keys())
def test_layout_shaped_table_state_refuses_any_other_shape(damage: _Damage) -> None:
    case, model, state = _stated_balance_table()
    _assert_layout_shaped_table_state(case, model, state)
    damage(state)
    with pytest.raises(AssertionError):
        _assert_layout_shaped_table_state(case, model, state)


_FLUSH_FAILURE_CASE: Final[str] = "m-concurrency-030"


def _flush_failure_case() -> tuple[case_format.Case, Metamodel, list[dict[str, Any]]]:
    case = next(c for c in reachable_cases() if c.case_id == _FLUSH_FAILURE_CASE)
    steps = cast("list[dict[str, Any]]", case_document(case)["when"]["scenario"])
    return case, engine.load_case_metamodel(case), steps


def _stated_units(case: case_format.Case) -> dict[str, Any]:
    return deepcopy(_expected_units(case))


def test_grade_units_accepts_the_fates_the_case_states() -> None:
    case, _model, _steps = _flush_failure_case()
    _grade_units(case, {"units": _stated_units(case)})


def test_a_reported_entity_matches_a_statement_of_its_bare_name_alone() -> None:
    assert _same_entity("parallax.compatibility.SequenceSpan", "SequenceSpan")
    assert not _same_entity("parallax.compatibility.SequenceSpan", "Other")


_UNIT_DAMAGE: Final[dict[str, _Damage]] = {
    "a-changed-outcome": lambda units: units["control"].update(outcome="rolledBack"),
    "a-lost-group": lambda units: units.pop("control"),
    "an-invented-group": lambda units: units.update(invented={"outcome": "committed"}),
    "an-invented-flush-failure": lambda units: units["control"].update(
        flushFailure=units["stale"]["flushFailure"]
    ),
    "another-flush-site": lambda units: units["stale"]["flushFailure"].update(at="flush"),
    "another-shortfall": lambda units: units["stale"]["flushFailure"].update(shortfall="zeroRows"),
    "an-invented-error": lambda units: units["stale"]["flushFailure"].update(error="invented"),
    "another-entity": lambda units: units["stale"]["flushFailure"].update(
        entity="parallax.compatibility.Other"
    ),
    "another-key": lambda units: units["stale"]["flushFailure"].update(key={"id": 99}),
}


@pytest.mark.parametrize("damage", _UNIT_DAMAGE.values(), ids=_UNIT_DAMAGE.keys())
def test_grade_units_refuses_any_other_fate(damage: _Damage) -> None:
    case, _model, _steps = _flush_failure_case()
    units = _stated_units(case)
    damage(units)
    with pytest.raises(AssertionError):
        _grade_units(case, {"units": units})


def test_grade_units_refuses_a_fate_omitting_its_flush_failure() -> None:
    case, _model, _steps = _flush_failure_case()
    units = _stated_units(case)
    del units["stale"]["flushFailure"]
    with pytest.raises(KeyError):
        _grade_units(case, {"units": units})


def _state_run_envelope(
    case: case_format.Case, model: Metamodel, steps: list[dict[str, Any]]
) -> dict[str, Any]:
    """A conforming run of the state-graded case: every table in layout order."""
    stated = cast("dict[str, list[dict[str, Any]]]", case_document(case)["then"]["tableState"])
    return {
        "emissions": [],
        "observations": {
            **_step_rows_envelope(steps)["observations"],
            "errors": [
                {"at": "/scenario/2/write/1", "errorClass": "write-evidence-already-claimed"}
            ],
            "units": _stated_units(case),
            "tableState": {
                layout.table.name: [
                    {slot.column.name: row[slot.column.name] for slot in layout.columns}
                    for row in stated.get(layout.table.name, [])
                ]
                for layout in storage_layout.storage_layout_facet_of(model).tables
            },
        },
    }


def test_grade_state_run_accepts_what_the_case_states() -> None:
    case, model, steps = _flush_failure_case()
    _grade_state_run(case, model, _state_run_envelope(case, model, steps))


_STATE_RUN_DAMAGE: Final[dict[str, _Damage]] = {
    "an-invented-emission": lambda run: run["emissions"].append({"sql": "update"}),
    "a-lost-step-row": lambda run: run["observations"]["stepRows"][0]["rows"].pop(),
    "a-lost-refusal": lambda run: run["observations"]["errors"].pop(),
    "an-invented-refusal": lambda run: run["observations"]["errors"].append(
        {"at": "/scenario/0/write/0"}
    ),
    "a-changed-fate": lambda run: run["observations"]["units"]["control"].update(
        outcome="rolledBack"
    ),
    "a-lost-table-row": lambda run: run["observations"]["tableState"]["sequence_span"].pop(),
}


@pytest.mark.parametrize("damage", _STATE_RUN_DAMAGE.values(), ids=_STATE_RUN_DAMAGE.keys())
def test_grade_state_run_refuses_any_other_run(damage: _Damage) -> None:
    case, model, steps = _flush_failure_case()
    envelope = _state_run_envelope(case, model, steps)
    damage(envelope)
    with pytest.raises(AssertionError):
        _grade_state_run(case, model, envelope)


def _step_graph_case() -> tuple[
    case_format.Case, Metamodel, list[dict[str, Any]], list[dict[str, Any]]
]:
    case = _write_case("m-snapshot-read-016")
    steps = cast("list[dict[str, Any]]", case_document(case)["when"]["scenario"])
    entries = [{"at": "/scenario/2", "graph": deepcopy(steps[2]["expectGraph"])}]
    return case, engine.load_case_metamodel(case), steps, entries


def test_grade_step_graphs_accepts_the_graph_each_step_states() -> None:
    case, model, steps, entries = _step_graph_case()
    _grade_step_graphs(case, model, steps, {"observations": {"stepGraphs": entries}})


_STEP_GRAPH_DAMAGE: Final[dict[str, Callable[[list[dict[str, Any]]], object]]] = {
    "an-unanswered-step": lambda entries: entries.clear(),
    "another-step": lambda entries: entries[0].update(at="/scenario/1"),
    "a-changed-leaf": lambda entries: entries[0]["graph"]["OrderItem"][0].update(sku="WRONG"),
}


@pytest.mark.parametrize("damage", _STEP_GRAPH_DAMAGE.values(), ids=_STEP_GRAPH_DAMAGE.keys())
def test_grade_step_graphs_refuses_any_other_graph(
    damage: Callable[[list[dict[str, Any]]], object],
) -> None:
    case, model, steps, entries = _step_graph_case()
    damage(entries)
    with pytest.raises(AssertionError):
        _grade_step_graphs(case, model, steps, {"observations": {"stepGraphs": entries}})


def _concurrency_case(case_id: str) -> case_format.Case:
    return next(c for c in _CONCURRENCY_CASES if c.case_id == case_id)


def _raised(category: Category | None = "deadlock", native_code: str = "40001") -> DatabaseError:
    return DatabaseError(category=category, native_code=native_code, message="refused")


def _rounds_raising(*errors: DatabaseError) -> concurrency_runner.RoundsRun:
    return concurrency_runner.RoundsRun(
        (
            {"A": concurrency_runner.NodeOutcome()},
            *({"B": concurrency_runner.NodeOutcome(error=error)} for error in errors),
        )
    )


def test_grade_error_rounds_accepts_the_one_classified_error_the_case_states(
    profile: Profile,
) -> None:
    _grade_error_rounds(_concurrency_case("m-concurrency-035"), profile, _rounds_raising(_raised()))


@pytest.mark.parametrize(
    "errors",
    [
        (),
        (_raised(), _raised()),
        (_raised(category="lockWaitTimeout"),),
        (_raised(native_code="40P01"),),
    ],
    ids=["no-error", "two-errors", "another-category", "another-native-code"],
)
def test_grade_error_rounds_refuses_any_other_error(
    errors: tuple[DatabaseError, ...], profile: Profile
) -> None:
    with pytest.raises(AssertionError):
        _grade_error_rounds(
            _concurrency_case("m-concurrency-035"), profile, _rounds_raising(*errors)
        )


def _answered_rounds() -> tuple[
    case_format.Case,
    tuple[dict[str, concurrency_runner.ConcurrencyStep], ...],
    list[dict[str, concurrency_runner.NodeOutcome]],
]:
    case = _concurrency_case("m-concurrency-034")
    rounds = concurrency_runner.parse_rounds(case, "postgres")
    answered = [
        {
            node: concurrency_runner.NodeOutcome(
                rows=step.expect_rows or (), affected=step.affected_rows or ()
            )
            for node, step in round_spec.items()
        }
        for round_spec in rounds
    ]
    return case, rounds, answered


def test_grade_success_rounds_accepts_what_each_step_states() -> None:
    case, rounds, answered = _answered_rounds()
    _grade_success_rounds(case, rounds, concurrency_runner.RoundsRun(tuple(answered)))


@pytest.mark.parametrize(
    ("index", "node", "outcome"),
    [
        (2, "B", concurrency_runner.NodeOutcome(error=_raised(), affected=(1,))),
        (0, "A", concurrency_runner.NodeOutcome()),
        (2, "B", concurrency_runner.NodeOutcome(affected=(0,))),
    ],
    ids=["a-raised-step", "a-read-of-other-rows", "another-affected-count"],
)
def test_grade_success_rounds_refuses_any_other_outcome(
    index: int, node: str, outcome: concurrency_runner.NodeOutcome
) -> None:
    case, rounds, answered = _answered_rounds()
    answered[index][node] = outcome
    with pytest.raises(AssertionError):
        _grade_success_rounds(case, rounds, concurrency_runner.RoundsRun(tuple(answered)))


def test_grade_success_rounds_refuses_a_read_step_stating_no_rows() -> None:
    case, rounds, answered = _answered_rounds()
    unstated = ({"A": replace(rounds[0]["A"], expect_rows=None)}, *rounds[1:])
    with pytest.raises(AssertionError):
        _grade_success_rounds(case, unstated, concurrency_runner.RoundsRun(tuple(answered)))
