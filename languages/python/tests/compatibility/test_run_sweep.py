"""The pg-full run sweep (m-conformance-adapter `run`, real Postgres).

Every exercised reachable read case is compiled, executed against a freshly reset
real database (``DROP SCHEMA … CASCADE`` → descriptor DDL → fixtures), and its
observation (``then.rows`` / ``then.graph`` / ``then.graphs``, order-insensitive
where the case format says so, wire space) compared against the golden; its
emitted SQL and binds equal the golden keyed by the profile's own dialect, root
and every deep-fetch child level alike. This is the tracer path proven end to end — compile (where
eligible) to canonical SQL/binds, then run against a reset database. Docker-
gated; a skip is reported, never silent (spec §6).
"""

from __future__ import annotations

import dataclasses
import re
from collections import Counter
from collections.abc import Sequence
from copy import deepcopy
from typing import Any, Final, cast

import jsonschema
import pytest

from _support.corpus import (
    CollectionKinds,
    case_document,
    case_fixtures,
    compare_binds,
    compare_graph,
    compare_rows,
    compare_rows_in_order,
    compare_stored_data_issues,
    wire_value_deep,
)
from _support.repo import adapter_schema
from _support.sweep_goldens import (
    COMPILE_EXERCISED,
    WRITE_EXERCISED,
    wire_binds,
    write_golden_statements,
)
from parallax.conformance import adapter, case_format, concurrency_runner, engine
from parallax.conformance.profile import Profile
from parallax.core import inheritance, storage_layout
from parallax.core.metamodel import Metamodel, entity_by_name

# Deep-fetch / snapshot CHILD-LEVEL graph shape: these cases author a child
# level's nodes PER PROJECTION — the unnarrowed concrete superset with a sibling
# branch's null padding, `familyVariant` present or absent by the VIEW that
# reached the node, and one logical row rendered twice with different values when
# two views reach it. Production materializes one MERGED, per-variant-narrowed
# node per logical row, which is what `then.graph` now grades through, so these
# eleven disagree with it structurally rather than by any defect on either side.
#
# `m-case-format` *Read targeting* states the gap itself: the per-variant node
# shape "is scoped, for now, to a read case's own top-level `then.graph` leaves",
# and "a deep-fetch or snapshot CHILD level's graph node shape
# (`m-snapshot-read-012`'s narrowed-vs-broad diamond, for example) is a distinct,
# already-established convention this decision does not touch; reconciling the
# two … is left open for a follow-up." Reconciling it moves the corpus AND the
# reference harness's own deep-fetch grader, so it is a core-specification
# decision rather than an adapter one.
#
# Everything else these cases assert still runs here — every level's SQL and
# binds (the N+1-elimination proof they exist for) and the round-trip count. Only
# the `then.graph` comparison is withheld, and what it withholds is the WIRE
# rendering rather than the graph: nine of the eleven carry a graph story
# (`parallax.conformance.graph_stories`), whose `tests/api/test_story_run.py`
# case walks the SAME merged graph through the typed developer surface against a
# real database. `m-inheritance-073` and `-077` carry no story and cannot: each
# needs a path-root guard resolving to two or more concrete subtypes, which the
# idiomatic surface can only author by reaching a relationship through ONE
# subtype class — the same permanent non-fit
# `parallax.conformance.api_suite.CASE_SKIP_REASONS` already records for both
# ids. So for those two nothing in this target grades the graph at all.
_CHILD_LEVEL_GRAPH_SHAPE_DEFERRED: Final[frozenset[str]] = frozenset(
    {
        "m-inheritance-065",
        "m-inheritance-066",
        "m-inheritance-067",
        "m-inheritance-068",
        "m-inheritance-073",
        "m-inheritance-074",
        "m-inheritance-075",
        "m-inheritance-076",
        "m-inheritance-077",
        "m-inheritance-078",
        "m-snapshot-read-012",
    }
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
    from parallax.conformance import sweep

    reachable = sweep.reachable_cases()
    return [
        c
        for c in reachable
        if c.shape == "read" and (c.case_id in RUN_EXERCISED or engine.eligibility(c) is not None)
    ]


_CASES = _reachable_run_cases()
_SCHEMA = adapter_schema()


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
_PAGE_BOUND: Final = re.compile(r"\blimit \?$")


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
    page delivers the size it asked for until one falls short, and a declared
    limit ends it early — and a delivery that ran a different number of them
    fails here rather than being graded against the wrong statements.
    """
    doc = case_document(case)
    query = cast("dict[str, Any]", doc["when"]["objectQuery"])
    size = cast("int", cast("dict[str, Any]", doc["when"]["stream"])["batchSize"])
    limit = cast("int | None", query.get("limit"))
    roots = _stated_roots(cast("dict[str, Any]", doc["then"]))
    pages = 0
    delivered = 0
    while True:
        requested = size if limit is None else min(size, limit - delivered)
        page = min(requested, roots - delivered)
        pages += 1
        delivered += page
        if page < requested or (limit is not None and delivered >= limit):
            break
    positions = {index for index, sql in enumerate(statements) if _PAGE_BOUND.search(sql)}
    assert positions and min(positions) == 0, (case.case_id, sorted(positions))
    assert len(positions) == pages, (case.case_id, sorted(positions), pages)
    return positions


@pytest.mark.parametrize("case", _CASES, ids=[c.case_id for c in _CASES])
def test_run_sweep(case: case_format.Case, profile: Profile, provisioner: Any) -> None:
    model = engine.load_case_metamodel(case)
    from parallax.conformance import provision

    provisioner.reset(model, provision.load_fixtures(str(case_document(case)["model"])))

    envelope = adapter.run_case(case.path, profile, provisioner.port)
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok", envelope
    # The envelope names the profile this lane declares and reports the dialect the
    # container's own adapter executed in — the same key the goldens below resolve.
    assert envelope["profile"] == profile.name
    assert envelope["dialect"] == profile.dialect.name

    doc = case_document(case)
    then = doc.get("then", {})
    golden_statements = _read_golden_statements(case, profile.dialect.name)
    emissions = envelope["emissions"]
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
    _grade_execution_lifecycle(then, observations)

    if "rows" in then:
        compare_rows(observations["rows"], then["rows"])
    elif "graph" in then and case.case_id not in _CHILD_LEVEL_GRAPH_SHAPE_DEFERRED:
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


# `m-opt-lock-012`'s scenario ALSO declares `compileEligibility: run-only` and
# ALSO uses `uow` grouping (:func:`_case_uses_uow_grouping`), but its two groups
# INTERLEAVE (the classic optimistic-lock race — one unit of work's observing
# find, a CONCURRENT unit of work's own observe-and-commit, then back to the
# first) — `run_scenario_case`/`adapter.run_case` execute only CONTIGUOUS `uow`
# groups (`engine._scenario_uow_spans`; a genuinely interleaved group needs a
# SECOND, independent connection this test's ordinary single-`DbPort` seam does
# not hold open). It stays OUT of `_WRITE_CASES`/`test_write_run_sweep`;
# `test_interleaved_uow_group_run_sweep` below is its own dedicated entry point
# (`engine.run_interleaved_scenario_case`, over the
# `Provisioner.peer` seam) — a routing exclusion, not a deferral, since the
# case IS run-lane exercised now, just through a different function.
_INTERLEAVED_UOW_GROUP_CASES: Final[frozenset[str]] = frozenset({"m-opt-lock-012"})


def _case_uses_uow_grouping(case: case_format.Case) -> bool:
    """Whether a scenario case's own steps declare the `uow` grouping key
    (`m-case-format`) — the discriminator
    between "this run-only case's observation is transaction-scoped, and the
    engine's `uow`-grouping seam (`engine._run_uow_group`) is what makes it
    runnable" and every OTHER run-only reason a scenario/writeSequence case
    carries (single-connection materializing predicate writes, deep-fetch
    deferred loads, pk-gen sequence batch reservations — none of which the
    run lane is ready to grade yet, exactly like before this remediation)."""
    when = cast("dict[str, Any]", case_document(case).get("when", {}))
    steps = cast("list[dict[str, Any]]", when.get("scenario", []))
    return any(isinstance(step.get("uow"), str) for step in steps)


# The materializing predicate-write run-only scenarios
# (`m-opt-lock` "Predicate-selected writes materialize when observations are
# needed", ADR 0014): each resolves through its OWN internal read
# (`tx.wire.update_where` and its family, paired with the immediately
# preceding find step in ONE transaction, `engine._run_materializing_pair`) —
# query-result-dependent (`compileEligibility: run-only`), so `compile` never
# grades them, but NONE of them declare `uow` grouping (unlike
# `m-opt-lock-012`) — `_case_uses_uow_grouping` alone would wrongly exclude
# every one of them, so this is their own explicit admission clause.
# `m-value-object-047` joins here too (a corpus amendment): its trailing
# verify find is an `asOf` read pinned strictly
# inside the closed window, the SAME find lane every OTHER `asOf` case already
# lowers — the case's own fourth step is not itself a materializing read, but
# it is run-only and NOT `uow`-grouped, so this explicit admission clause is
# still the only membership path that reaches it (`_reachable_write_cases`).
# `m-value-object-066` is its versioned counterpart and reaches membership the
# same way. Both are graded here precisely BECAUSE this lane compares each
# emitted statement against its authored golden: the Document slot each
# resolving read projects is observable nowhere else.
# `m-opt-lock-019` is the Relational Document Layout member of that same family:
# its resolving read must decode a Document Path out of the Structured Column
# before the per-row no-op comparison, and only running it proves the comparison
# saw the member's value rather than an absent column.
# `m-bitemp-write-020` is the member-free member of it: no member its resolve asks
# for lives inside the Structured Column, so only the emitted select list proves
# the observation projected it anyway, and only the emitted insert binds prove the
# rectangles it chains were built from the document that read retained. It is
# `single-connection` run-only rather than query-result-dependent (its `given.apply`
# writes the key no authored member could), which changes nothing here: this set is
# the admission clause for every run-only materializing pair whatever its reason.
_MATERIALIZING_PREDICATE_WRITE_SCENARIOS_EXERCISED: Final[frozenset[str]] = frozenset(
    {
        "m-opt-lock-003",
        "m-opt-lock-004",
        "m-opt-lock-014",
        "m-opt-lock-015",
        "m-opt-lock-019",
        "m-txtime-write-007",
        "m-txtime-write-009",
        "m-bitemp-write-010",
        "m-bitemp-write-011",
        "m-bitemp-write-012",
        "m-bitemp-write-013",
        "m-bitemp-write-020",
        "m-value-object-047",
        "m-value-object-066",
    }
)


# The snapshot-scenario cases whose own find step carries `objectQuery.includes`:
# a deep-fetch child level's `IN`-list binds are the distinct root keys gathered
# from that step's own root read, so each is `compileEligibility: run-only`
# (query-result-dependent) exactly as every deep-fetch read case is — which keeps
# them out of `WRITE_EXERCISED`, whose membership couples compile grading in and
# which a run-only case would fail. Run grades them here in full: the per-step
# emissions against the authored golden levels, the round trips, and the
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
# `-022`/`-023`/`-024` are the composite arms: a CHAIN of edits whose second hop
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


def _reachable_write_cases() -> list[case_format.Case]:
    from parallax.conformance import sweep

    return [
        c
        for c in sweep.reachable_cases()
        if (
            c.case_id in WRITE_EXERCISED
            or c.case_id in _MATERIALIZING_PREDICATE_WRITE_SCENARIOS_EXERCISED
            or c.case_id in _SNAPSHOT_INCLUDE_SCENARIOS_EXERCISED
            or (
                c.case_id not in _INTERLEAVED_UOW_GROUP_CASES
                and engine.eligibility(c) is not None
                and _case_uses_uow_grouping(c)
            )
        )
    ]


_WRITE_CASES = _reachable_write_cases()


def _scenario_expect_rows(case: case_format.Case) -> list[list[dict[str, Any]] | None]:
    """Each FIND step's declared ``expectRows`` in step order (None asserts nothing).

    For the interleaved lane, which reports one row list per find step rather than
    the pointer-addressed ``stepRows`` entries the envelope carries.
    """
    steps = cast("list[dict[str, Any]]", case_document(case)["when"]["scenario"])
    return [step.get("expectRows") for step in steps if "objectQuery" in step]


@pytest.mark.parametrize("case", _WRITE_CASES, ids=[c.case_id for c in _WRITE_CASES])
def test_write_run_sweep(case: case_format.Case, profile: Profile, provisioner: Any) -> None:
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
    read step's `stepRows` observation equals its `expectRows` (:func:`_grade_step_rows`);
    a writeSequence's committed `tableState` observation equals `then.tableState`,
    table for table.
    """
    model = engine.load_case_metamodel(case)
    provisioner.reset(model, case_fixtures(case))

    envelope = adapter.run_case(case.path, profile, provisioner.port)
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
        # is a REAL ``decimal``-typed bind sourced
        # from the resolving read's own row (psycopg's native ``Decimal``,
        # never lossily coerced to ``float`` for SQL execution — `m-core`),
        # which a plain YAML-authored golden literal (``200.00``, a ``float``)
        # only reconciles against in Decimal space, not by bare wire equality.
        compare_binds(emission["binds"], golden_binds)
    assert envelope["observations"]["roundTrips"] == case_document(case)["then"]["roundTrips"]
    _grade_execution_lifecycle(case_document(case)["then"], envelope["observations"])

    if case.shape == "scenario":
        steps = cast("list[dict[str, Any]]", case_document(case)["when"]["scenario"])
        _grade_step_rows(case, model, steps, envelope)
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
    else:
        expected_state = cast(
            "dict[str, list[dict[str, Any]]]", case_document(case)["then"]["tableState"]
        )
        observed_state = envelope["observations"]["tableState"]
        _assert_layout_shaped_table_state(case, model, observed_state)
        assert set(observed_state) >= set(expected_state), (case.case_id, observed_state)
        for table, expected_rows in expected_state.items():
            compare_rows(observed_state[table], expected_rows)


def _resolves_a_materializing_write(
    model: Metamodel, steps: list[dict[str, Any]], index: int
) -> bool:
    """Whether the read step at ``index`` is a materializing predicate write's own
    resolving read (`m-case-format` *Materializing cases*).

    Such a write is authored immediately after the find that resolves it and over
    that find's own target, in the predicate-selected object form rather than the
    keyed buffer a list spells — and its target MATERIALIZES
    (:func:`_materializes_when_written`). Adjacency and target alone would exclude
    too much: a READLESS predicate write resolves nothing, so an ordinary find
    before one publishes its rows like any other read and owns its entry.

    "That find's own target" is decided by MODEL IDENTITY, because a case spells
    an Entity either way it may (`m-case-format` *How a case spells an Entity*):
    a read naming `Subscriber` and a write naming
    `parallax.compatibility.Subscriber` are one target, and comparing the raw
    spellings would expect an entry for a resolve that publishes nothing.
    """
    following = steps[index + 1] if index + 1 < len(steps) else None
    write = None if following is None else following.get("write")
    if not isinstance(write, dict):
        return False
    target = cast("dict[str, Any]", write).get("target")
    if not isinstance(target, dict):
        return False
    entity = cast("dict[str, Any]", target).get("entity")
    if not _names_one_entity(model, entity, steps[index]["objectQuery"]["target"]):
        return False
    return _materializes_when_written(model, cast("str", entity))


def _materializes_when_written(model: Metamodel, entity_name: str) -> bool:
    """Whether a predicate write against ``entity_name`` must resolve its rows
    before it writes them.

    A VERSIONED or TEMPORAL target materializes; an unversioned, non-temporal
    `update` or `delete` is the sole readless exception (`m-case-format`
    *Materializing cases*). Both profiles are owned by the family ROOT, so a
    subtype spelling is answered from its root rather than from local declarations
    that carry neither.
    """
    entity = entity_by_name(model, entity_name)
    if entity is None:
        return False
    position = inheritance.view(model).entity(entity.identity)
    root = None if position is None else model.entity(position.root)
    if root is None:
        return False
    return bool(root.declared_as_of_axes) or any(
        attribute.optimistic_locking for attribute in root.declared_attributes
    )


def _names_one_entity(model: Metamodel, left: object, right: object) -> bool:
    """Whether two authored Entity spellings resolve to one declared Entity."""
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    resolved, other = entity_by_name(model, left), entity_by_name(model, right)
    return resolved is not None and other is not None and resolved.identity == other.identity


def _grade_step_rows(
    case: case_format.Case, model: Metamodel, steps: list[dict[str, Any]], envelope: Any
) -> None:
    """Grade every read step's `expectRows` against the run's own `stepRows`
    observation.

    The values a step published are what `m-conformance-adapter`'s `stepRows`
    reports — one entry per read step the adapter drove, at that step's own
    pointer, in step order. What is graded is therefore what the step HANDED OVER,
    not what its statements returned: a streamed step's entry is its whole
    delivery's roots, and a deep-fetch step's is its roots alone, with no per-lane
    arithmetic over result sets in between.

    A STREAMED step is the one row oracle compared POSITIONALLY: its `expectRows`
    are the roots the delivery published across every page IN DELIVERY ORDER
    (`m-case-format` *Streamed read steps*), and that order is the Continuation
    Order the delivery exists to hold to, so a delivery that published the right
    roots in the wrong sequence must fail. Every other step compares through the
    same order-insensitive comparator the rest of the corpus's row oracles use.

    The pointer list is asserted whole, so a lane that stopped driving a step fails
    on the list rather than passing on the steps it still answers — the same rule
    :func:`_grade_step_graphs` follows. The one read step that owns no entry is a
    materializing predicate write's resolving read, identified from the case
    (:func:`_resolves_a_materializing_write`) rather than from the engine's own
    pairing, so the two disagreeing is a failure rather than a silent skip.
    """
    expected = [
        (f"/scenario/{index}", step.get("expectRows"), "stream" in step)
        for index, step in enumerate(steps)
        if "objectQuery" in step and not _resolves_a_materializing_write(model, steps, index)
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


# The `stepRows` oracle's own directional proof, run without a database: an
# implementation that published the wrong values, stopped answering a step,
# answered the ONE step that owns no entry, or published a delivery's roots out of
# the order it delivered them must be refused rather than accepted.
#
# `m-value-object-066` carries the pointer-list properties: its four steps are a
# read, a materializing predicate write's resolving read, that write, and a verify
# read — so its expected pointer list is a strict subset of its read steps, which
# is the property a grader could silently get wrong. `m-unit-work-030` carries the
# ORDER property: its two streamed steps each publish three roots across two pages,
# so a swap inside one entry leaves the multiset intact and only a positional
# comparison catches it.
# `m-batch-write-005` carries the READLESS profile: Wallet is Account without the
# optimistic-lock version and without a temporal axis, so its predicate delete
# resolves nothing. The case authors the write before its verifying find, which
# is the adjacency the exclusion keys on read backwards; reversing the two steps
# builds the adjacency the corpus never authors, where the profile is the only
# thing separating a published read from a write's internal resolve.
_STEP_ROWS_ORACLE_CASE: Final[str] = "m-value-object-066"
_STREAMED_STEP_ROWS_ORACLE_CASE: Final[str] = "m-unit-work-030"
_READLESS_WRITE_ORACLE_CASE: Final[str] = "m-batch-write-005"


def _step_rows_envelope(model: Metamodel, steps: list[dict[str, Any]]) -> dict[str, Any]:
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
                and not _resolves_a_materializing_write(model, steps, index)
            ]
        }
    }


def _step_rows_oracle_case(
    case_id: str = _STEP_ROWS_ORACLE_CASE,
) -> tuple[case_format.Case, Metamodel, list[dict[str, Any]]]:
    case = next(c for c in _WRITE_CASES if c.case_id == case_id)
    model = engine.load_case_metamodel(case)
    return case, model, cast("list[dict[str, Any]]", case_document(case)["when"]["scenario"])


def test_grade_step_rows_accepts_a_run_that_published_what_every_step_states() -> None:
    case, model, steps = _step_rows_oracle_case()
    envelope = _step_rows_envelope(model, steps)

    # Pinned as a literal rather than derived, so the exclusion this case exists to
    # exercise is stated independently of the rule that computes it.
    assert [entry["at"] for entry in envelope["observations"]["stepRows"]] == [
        "/scenario/0",
        "/scenario/3",
    ]
    _grade_step_rows(case, model, steps, envelope)


def test_grade_step_rows_refuses_a_run_that_published_the_wrong_values() -> None:
    case, model, steps = _step_rows_oracle_case()
    envelope = _step_rows_envelope(model, steps)
    envelope["observations"]["stepRows"][0]["rows"] = [{"id": 2, "version": 1, "address": None}]

    with pytest.raises(AssertionError):
        _grade_step_rows(case, model, steps, envelope)


def test_grade_step_rows_refuses_a_run_that_left_a_step_unanswered() -> None:
    case, model, steps = _step_rows_oracle_case()
    envelope = _step_rows_envelope(model, steps)
    del envelope["observations"]["stepRows"][-1]

    with pytest.raises(AssertionError):
        _grade_step_rows(case, model, steps, envelope)


def test_grade_step_rows_refuses_an_entry_for_a_materializing_writes_own_resolve() -> None:
    # The resolving read of a materializing predicate write hands its rows to no
    # caller, so an adapter reporting one for it is reporting something it did not
    # publish — captured at a port, or re-read.
    case, model, steps = _step_rows_oracle_case()
    envelope = _step_rows_envelope(model, steps)
    envelope["observations"]["stepRows"].insert(
        1, {"at": "/scenario/1", "rows": steps[1]["expectRows"]}
    )

    with pytest.raises(AssertionError):
        _grade_step_rows(case, model, steps, envelope)


def test_grade_step_rows_pairs_a_materializing_write_by_entity_rather_than_spelling() -> None:
    # `m-case-format` admits the bare local name wherever it names exactly one
    # declared Entity, so a resolving find spelled `Subscriber` and its write spelled
    # `parallax.compatibility.Subscriber` are ONE materializing operation. A lexical
    # pairing reads them as two and expects an entry for the internal resolve.
    case, model, steps = _step_rows_oracle_case()
    respelled = deepcopy(steps)
    canonical = respelled[1]["objectQuery"]["target"]
    respelled[1]["objectQuery"]["target"] = canonical.rpartition(".")[2]
    assert respelled[1]["objectQuery"]["target"] != canonical

    _grade_step_rows(case, model, respelled, _step_rows_envelope(model, steps))


def test_grade_step_rows_expects_an_entry_for_a_find_before_a_readless_write() -> None:
    # Adjacency alone does not make a read a write's internal resolve: an
    # unversioned, non-temporal `update`/`delete` is readless (`m-case-format`
    # *Materializing cases*), so a find before one is an ordinary read that
    # publishes its rows and owns a `stepRows` entry like every other. Production
    # runs that find on its own and reports it; a grader excluding it would reject
    # a conforming run on the pointer list.
    case, model, steps = _step_rows_oracle_case(_READLESS_WRITE_ORACLE_CASE)
    write, find = steps
    adjacent = [deepcopy(find), deepcopy(write)]
    envelope = {
        "observations": {"stepRows": [{"at": "/scenario/0", "rows": deepcopy(find["expectRows"])}]}
    }

    _grade_step_rows(case, model, adjacent, envelope)


def test_grade_step_rows_accepts_a_delivery_that_published_its_roots_in_order() -> None:
    case, model, steps = _step_rows_oracle_case(_STREAMED_STEP_ROWS_ORACLE_CASE)
    envelope = _step_rows_envelope(model, steps)

    assert [entry["at"] for entry in envelope["observations"]["stepRows"]] == [
        "/scenario/0",
        "/scenario/2",
    ]
    _grade_step_rows(case, model, steps, envelope)


def test_grade_step_rows_refuses_a_delivery_that_published_its_roots_reordered() -> None:
    # The roots are the SAME three; only the sequence the delivery handed them over
    # in changed, which the Continuation Order fixes (`m-case-format` *Streamed read
    # steps*). A multiset comparison accepts this run.
    case, model, steps = _step_rows_oracle_case(_STREAMED_STEP_ROWS_ORACLE_CASE)
    envelope = _step_rows_envelope(model, steps)
    rows = envelope["observations"]["stepRows"][0]["rows"]
    rows[0], rows[-1] = rows[-1], rows[0]

    with pytest.raises(AssertionError):
        _grade_step_rows(case, model, steps, envelope)


def test_grade_step_rows_accepts_an_eager_step_whose_rows_arrived_reordered() -> None:
    # The positional rule is the STREAM's, not the channel's: an eager step states a
    # result set, whose order no case fixes, so it keeps the corpus-wide multiset
    # comparison.
    case, model, steps = _step_rows_oracle_case(_STREAMED_STEP_ROWS_ORACLE_CASE)
    eager = deepcopy(steps)
    for step in eager:
        step.pop("stream", None)
    envelope = _step_rows_envelope(model, eager)
    rows = envelope["observations"]["stepRows"][0]["rows"]
    rows[0], rows[-1] = rows[-1], rows[0]

    _grade_step_rows(case, model, eager, envelope)


def test_run_scenario_case_pairs_a_materializing_write_spelled_bare(provisioner: Any) -> None:
    """Production pairs a materializing predicate write with its resolving find by
    ENTITY, not by spelling.

    `m-case-format` admits the bare local name wherever it names exactly one
    declared Entity, so respelling `m-value-object-066`'s resolving find bare
    leaves the same case: one transaction, the resolve plus its per-row keyed
    write, and no `stepRows` entry for the read that hands its rows to no caller.
    A lexical pairing runs that find on its own and lets the write resolve a
    second time, which the round-trip count and the pointer list both state.
    """
    case = next(c for c in _WRITE_CASES if c.case_id == _STEP_ROWS_ORACLE_CASE)
    model = engine.load_case_metamodel(case)
    provisioner.reset(model, case_fixtures(case))
    document = deepcopy(dict(case.document))
    steps = cast("list[dict[str, Any]]", cast("dict[str, Any]", document["when"])["scenario"])
    canonical = cast("str", steps[1]["objectQuery"]["target"])
    steps[1]["objectQuery"]["target"] = canonical.rpartition(".")[2]
    assert steps[1]["objectQuery"]["target"] != canonical

    run = engine.run_scenario_case(dataclasses.replace(case, document=document), provisioner.port)

    assert run.round_trips == case_document(case)["then"]["roundTrips"]
    assert [entry["at"] for entry in run.step_rows] == ["/scenario/0", "/scenario/3"]


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
        for layout in storage_layout.view(model).tables
    }
    assert set(observed_state) == set(layouts), (case.case_id, sorted(observed_state))
    for table, rows in observed_state.items():
        for row in rows:
            assert list(row) == layouts[table], (case.case_id, table, list(row))


def _reachable_interleaved_uow_group_cases() -> list[case_format.Case]:
    from parallax.conformance import sweep

    return [c for c in sweep.reachable_cases() if c.case_id in _INTERLEAVED_UOW_GROUP_CASES]


_INTERLEAVED_CASES = _reachable_interleaved_uow_group_cases()


@pytest.mark.parametrize("case", _INTERLEAVED_CASES, ids=[c.case_id for c in _INTERLEAVED_CASES])
def test_interleaved_uow_group_run_sweep(case: case_format.Case, provisioner: Any) -> None:
    """`m-opt-lock-012`'s own dedicated entry point:
    the two-group optimistic-lock race, run over a REAL peer connection
    (`engine.run_interleaved_scenario_case`), never through `adapter.run_case`
    (which cannot hold a second session open).

    Grades the SAME FOUR layers `test_write_run_sweep` grades for an
    ordinary scenario — the ordered per-step golden DML (flattened across
    both interleaved groups plus the trailing ungrouped verify find, in
    AUTHORED step order), `then.roundTrips`, and every find step's own
    observed rows against its authored `expectRows` (grouped steps 0/1's own
    observing finds AND the trailing
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
    model = engine.load_case_metamodel(case)
    provisioner.reset(model, case_fixtures(case))

    emissions, round_trips, conflict_actual, find_rows = engine.run_interleaved_scenario_case(
        case, provisioner.port, lambda: provisioner.peer()
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
def test_error_run_sweep(case: case_format.Case, profile: Profile, provisioner: Any) -> None:
    """Run each single-connection m-db-error case against a reset real database.

    The authored trigger DML executes in order; the final statement raises a real
    database error at the port boundary, and the envelope's classification
    (`errorClass` / `nativeCode`) must equal the case's `then.errorClass` and
    per-dialect `then.nativeCode`. Fixtures load only when the case declares
    `given.fixtures` (the unique-violation cases self-seed via their own trigger).
    """
    model = engine.load_case_metamodel(case)
    from parallax.conformance import provision

    doc = case_document(case)
    given = cast("dict[str, Any]", doc.get("given") or {})
    fixtures = provision.load_fixtures(str(doc["model"])) if given.get("fixtures") else {}
    provisioner.reset(model, fixtures)

    envelope = adapter.run_case(case.path, profile, provisioner.port)
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok", envelope

    then = doc["then"]
    assert envelope["observations"]["errorClass"] == then["errorClass"]
    assert envelope["observations"]["nativeCode"] == then["nativeCode"][profile.dialect.name]
    assert envelope["observations"]["roundTrips"] == len(then["statements"])
    golden_trigger = [
        (
            entry["sql"][profile.dialect.name] if isinstance(entry["sql"], dict) else entry["sql"],
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
# Conflict — the optimistic-lock run lane (m-opt-lock / m-txtime-write /        #
# m-bitemp-write). Every reachable conflict                                    #
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
# proves instead). Every non-temporal conflict case here settles against a     #
# state a REAL read of this lane observed, so the concurrent writer commits    #
# between that read and the write it invalidates. The zero-row shapes whose    #
# interference no correct client can reach — a Locking-mode target whose row   #
# a concurrent writer deleted while the required participating read held its   #
# shared lock — are absent from this lane for that reason, and the             #
# classification they would carry is pinned without a database by              #
# `tests/unit/test_zero_row_write_classification.py`.                          #
# `m-bitemp-write-017`/`-018` close the BOUNDED current rectangle whose        #
# Valid-Time end is finite, in each concurrency mode: only a real execution    #
# distinguishes an address that binds the observed rectangle's own `thru_z`    #
# from one that would match both current rectangles of the key, and the        #
# distinguishing observable is the affected-row count.                         #
# `m-bitemp-write-021`/`-022` are the EDGE-NAMED pair over one key holding     #
# two current rectangles: each derives its `thru_z` from the milestone its     #
# edge selects, and only the pair rules out resolving by primary key and       #
# always picking the same rectangle. Neither grades where the gate came from   #
# — both rectangles share `in_z`, and that `in_z` is the authored edge's own   #
# Transaction-Time half — which each header states as a bare negative.         #
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
        "m-txtime-write-006",
        "m-bitemp-write-004",
        "m-bitemp-write-005",
        "m-bitemp-write-017",
        "m-bitemp-write-018",
        "m-bitemp-write-021",
        "m-bitemp-write-022",
        "m-inheritance-105",
        "m-value-object-046",
    }
)


def _reachable_conflict_cases() -> list[case_format.Case]:
    from parallax.conformance import sweep

    return [c for c in sweep.reachable_cases() if c.case_id in _CONFLICT_CASES_EXERCISED]


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
def test_conflict_run_sweep(case: case_format.Case, profile: Profile, provisioner: Any) -> None:
    """Run each `conflict`-shape case against a reset real database.

    The single-attempt form (`m-opt-lock-005/006/013`) grades the golden write's
    emissions and `then.affectedRows` — the count the write's own target expects,
    or the count a refused write reached instead. The `when.attempts` retry form
    (`m-opt-lock-007`) grades each attempt's own statements flattened in order
    (proving the `0`-then-`1` transition through each attempt's own distinct gate
    bind) and the FINAL affected-row count. A case authoring `then.roundTrips`
    grades the calls that reached the database across every attempt — its
    resolving reads among them, which is the one shape where such a read stands
    outside the transaction it licenses — and a case authoring
    `then.executionLifecycle` grades the delivered stream those calls came from,
    where that read is the Root Execution naming no golden statement. Every case
    that authors `then.tableState` grades the committed table contents; a case
    whose write is refused authors none, since the unit of work rolls back.
    """
    model = engine.load_case_metamodel(case)
    provisioner.reset(model, case_fixtures(case))

    envelope = adapter.run_case(case.path, profile, provisioner.port)
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "ok", envelope

    doc = case_document(case)
    then = cast("dict[str, Any]", doc.get("then", {}))
    observations = envelope["observations"]
    emissions = envelope["emissions"]

    if "affectedRows" in then:
        golden_statements = _conflict_golden_statements(then, profile.dialect.name)
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
            entry
            for attempt in attempts
            for entry in _conflict_golden_statements(attempt, profile.dialect.name)
        ]
        assert len(emissions) == len(golden_statements), (case.case_id, emissions)
        for emission, (golden_sql, golden_binds) in zip(emissions, golden_statements, strict=True):
            assert emission["sql"] == golden_sql, (case.case_id, emission)
            assert wire_binds(emission["binds"]) == wire_binds(golden_binds), (
                case.case_id,
                emission,
            )
        assert observations["affectedRows"] == attempts[-1]["affectedRows"], case.case_id

    # `then.roundTrips` where the case authors it: the calls that actually
    # reached the database, summed across every attempt and counting each
    # attempt's own resolving read, which is a different number from the emission
    # count whenever a call ran no authored golden.
    if "roundTrips" in then:
        assert observations["roundTrips"] == then["roundTrips"], case.case_id

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
    {*(f"m-pk-gen-{n:03d}" for n in range(4, 13)), "m-pk-gen-014"}
)


def _reachable_run_only_write_sequence_cases() -> list[case_format.Case]:
    from parallax.conformance import sweep

    return [c for c in sweep.reachable_cases() if c.case_id in _RUN_ONLY_WRITE_SEQUENCES_EXERCISED]


_RUN_ONLY_WRITE_SEQUENCE_CASES = _reachable_run_only_write_sequence_cases()


@pytest.mark.parametrize(
    "case", _RUN_ONLY_WRITE_SEQUENCE_CASES, ids=[c.case_id for c in _RUN_ONLY_WRITE_SEQUENCE_CASES]
)
def test_run_only_write_sequence_run_sweep(
    case: case_format.Case, profile: Profile, provisioner: Any
) -> None:
    """Run each run-only pk-gen `sequence`-strategy writeSequence case end to end
    against a reset real database — the SAME grading `test_write_run_sweep` applies
    to a compile-eligible writeSequence case, parametrized separately because a
    run-only case's compile envelope answers `status: "run-only"`, never `"ok"`
    (`test_write_run_sweep`'s `WRITE_EXERCISED` set couples compile-time grading in
    too, which a run-only member would fail)."""
    model = engine.load_case_metamodel(case)
    provisioner.reset(model, case_fixtures(case))

    envelope = adapter.run_case(case.path, profile, provisioner.port)
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
# The `when.concurrency` rounds runner (the m-read-lock behavioral matrix,   #
# joined by `m-db-error`'s own five two-session error cases too, case-       #
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
def test_concurrency_rounds(case: case_format.Case, profile: Profile, provisioner: Any) -> None:
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
    model = engine.load_case_metamodel(case)
    from parallax.conformance import provision

    provisioner.reset(model, provision.load_fixtures(str(case_document(case)["model"])))

    rounds = concurrency_runner.parse_rounds(case, profile.dialect.name)
    isolation = "serializable" if case.case_id in _SERIALIZABLE_ISOLATION_CASES else None
    run = concurrency_runner.run_rounds(
        rounds, lambda: provisioner.peer(autocommit=False), isolation=isolation
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
        assert exc.native_code == then["nativeCode"][profile.dialect.name], (case.case_id, exc)
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
