"""API-suite stories against real Postgres (m-api-conformance, spec §"API
Conformance Suite").

Every registered story — write (`parallax.conformance.stories`) or graph-read
(`parallax.conformance.graph_stories`); the same executable functions the Usage
Guide renders — executes here through the **shipped** surface:
`parallax.snapshot.connect` over the `parallax-postgres` adapter against the
real Testcontainers Postgres, inside the documented API-conformance lane
(python.md: pytest ``-m api_conformance`` under ``tests/api_conformance/``,
"executing idiomatic public-API code through the shipped `parallax-snapshot`
extension and `parallax-postgres` adapter"; IMPLEMENTING.md "Continuous API
Conformance Lane" step 2). Docker-backed: the shared ``provisioner`` fixture
skips with a recorded reason when Docker is unavailable (never silently), and
the ``python-database`` CI job fails on any skip. A write story's grading is
the mirrored case's own oracle: a story returning rows must observe its final
find's `expectRows`; a writeSequence story must leave exactly `then.tableState`
behind. The one `kind == "boundary"` story (`m-unit-work-004`) is EXCLUDED from
this file's own grading loop (COR-3 Phase 8 increment 6, DQ5): the D-17
case-driven boundary runner (`test_boundary_run.py`) grades it — and every
other boundary-shape case — directly against the corpus now, so the story
function survives registered only for the Usage Guide and the fake-port wire
pin (`test_write_no_drift.py`). A graph story's grading is bespoke per case
(see the section below).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, cast

import pytest

from conftest import case_document, case_fixtures, compare_rows, instance_row
from parallax.conformance import case_format, engine
from parallax.conformance.graph_stories import (
    GRAPH_STORIES,
    history_of_a_concrete_temporal_node_distinguishes_milestones,
)
from parallax.conformance.read_stories import READ_STORIES, ReadStory
from parallax.conformance.stories import WRITE_STORIES, WriteStory
from parallax.core import LATEST, edge_of, is_loaded, pin_of
from parallax.core.dialect import POSTGRES
from parallax.core.entity.expressions import UnloadedRelationshipError
from parallax.snapshot import connect

pytestmark = pytest.mark.api_conformance

_CASES = {c.case_id: c for c in case_format.load_cases()}


def _final_find_expect_rows(case_id: str) -> list[dict[str, Any]]:
    """The last scenario find step's ``expectRows`` — the story's returned oracle."""
    steps = cast("list[dict[str, Any]]", case_document(_CASES[case_id])["when"]["scenario"])
    finds = [step for step in steps if "find" in step]
    assert finds, case_id
    return cast("list[dict[str, Any]]", finds[-1]["expectRows"])


def _reset_for(case_id: str, provisioner: Any) -> Any:
    case = _CASES[case_id]
    meta = engine.load_case_metamodel(case)
    provisioner.reset(meta, case_fixtures(case))
    return meta


# `kind == "boundary"` (m-unit-work-004) is EXCLUDED from execution here (COR-3
# Phase 8 increment 6, DQ5): the D-17 case-driven boundary runner
# (`tests/api_conformance/test_boundary_run.py`) now grades it directly
# against the corpus, case-driven like every other boundary case — the hand
# story's function stays registered (`stories.WRITE_STORIES`) ONLY so the
# Usage Guide keeps rendering it (`api_suite.EXAMPLES`) and the fake-port
# wire pin (`test_write_no_drift.test_boundary_story_withholds_the_callback_
# value`) keeps proving its own DML shape — this hand-mirrored REAL-DATABASE
# grading is what retires.
_EXECUTED_STORIES = [story for story in WRITE_STORIES if story.kind != "boundary"]
_STORY_IDS = [story.case_id for story in _EXECUTED_STORIES]


@pytest.mark.parametrize("story", _EXECUTED_STORIES, ids=_STORY_IDS)
def test_story_runs_through_the_shipped_surface(story: WriteStory, provisioner: Any) -> None:
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)

    result = story.run(db)
    if result is not None:
        # Commit and abort stories both conclude with an observing find; its
        # rows must equal the mirrored case's final `expectRows`.
        compare_rows(
            [engine.wire_row(row) for row in result], _final_find_expect_rows(story.case_id)
        )
        return

    # A writeSequence story observes no rows; the committed table state must
    # equal the case's `then.tableState`, table for table.
    expected_state = cast(
        "dict[str, list[dict[str, Any]]]",
        case_document(_CASES[story.case_id])["then"]["tableState"],
    )
    observed_state = engine.read_table_state(provisioner.port, meta, POSTGRES)
    assert set(observed_state) >= set(expected_state), (story.case_id, observed_state)
    for table, expected_rows in expected_state.items():
        compare_rows(observed_state[table], expected_rows)


# --------------------------------------------------------------------------- #
# Graph stories (m-snapshot-read / m-navigate, COR-3 Phase 7 increment 6b):    #
# the read-side sibling of the write stories above, executed through the SAME #
# shipped `parallax.snapshot.connect` + `parallax-postgres` surface. Grading  #
# is bespoke per story (unlike the write stories' shared row/table-state      #
# comparators): each assertion mirrors its case's own `then.graph`/           #
# `identityChecks`/scenario oracle as closely as one in-process assertion     #
# can — the developer-facing guarantees a wire grade cannot see (reference    #
# identity surviving the frozen-node wrap, `is_loaded` /                      #
# `UnloadedRelationshipError`, `pin_of`/`edge_of` on a materialized node).     #
# --------------------------------------------------------------------------- #
_GRAPH_STORIES_BY_ID = {story.case_id: story for story in GRAPH_STORIES}


def test_diamond_identity_shares_one_child_node(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-001"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    order = snapshot.result()
    # The diamond: both include paths reach OrderItem 12 then OrderItem 11 (id
    # desc / shipped_on asc happen to agree here) — one materialized node, not
    # two lookalike copies, exactly the reference identity `then.identityChecks`
    # would grade at the wire level for the graph half of this case.
    assert order.items[0] is order.items_by_ship_date[0]
    assert order.items[1] is order.items_by_ship_date[1]
    assert snapshot.execution.round_trips == 3


def test_back_reference_cycle_resolves_to_the_root(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-011"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    order = snapshot.result()
    # `then.identityChecks` graded as Python reference identity: the back-
    # reference IS the root node, never a lookalike re-fetch.
    assert order.items[0].order is order
    assert order.items[1].order is order
    assert snapshot.execution.round_trips == 2


def test_closed_world_unloaded_access_raises_without_sql(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-009"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    order = snapshot.result()
    assert is_loaded(order, "statuses") is False
    with pytest.raises(UnloadedRelationshipError, match="statuses"):
        order.statuses  # noqa: B018 - the access itself is the assertion
    # The access issues no SQL of its own: the materializing find is the only
    # round trip on record (m-snapshot-read-009 is this suite's official grader
    # for the closed-world absence witness, `lane: api-conformance`).
    assert snapshot.execution.round_trips == 1


def test_empty_root_materializes_no_children(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-004"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    assert snapshot.results() == []
    assert snapshot.execution.round_trips == 1


def test_empty_intermediate_level_short_circuits(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-005"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    order = snapshot.result()
    assert order.items == ()
    assert snapshot.execution.round_trips == 2


def test_pinned_graph_at_a_past_business_instant(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-navigate-013"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    policy = next(p for p in snapshot.results() if p.id == 1)
    coverage = policy.coverages[0]
    assert coverage.amount == Decimal("600.00")  # the HEAD as of 2024-03-01, not the current 700
    edge = edge_of(coverage)
    assert edge.business == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert edge.processing == dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
    pin = snapshot.pin
    assert pin.business == dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
    assert pin.processing is LATEST


def test_mutation_has_no_writeback(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-010"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    mutated, reread = story.run(db)
    assert mutated.name == "Mutant"  # the in-memory copy sees the edit
    assert reread.result().name == "Ada"  # the re-read never observes it


def test_history_of_a_concrete_temporal_node_distinguishes_milestones(provisioner: Any) -> None:
    # SUPPLEMENTAL (Spec-2 remediation) — NOT tied to any case's exercised
    # status: `m-inheritance-100`'s own point read is graded by its `ReadStory`
    # below (`test_read_story_runs_through_the_shipped_surface`), through the
    # generic case-driven runner, exactly like every other read story. This
    # proves the SEPARATE milestone-HISTORY shape over the SAME fixture: a
    # concrete TPCS node (DepositRate) whose family's as-of axes are declared
    # on the root (Rate) alone still gets its own pin/edge attached, and a
    # `.history(...)` milestone-set read's closed historical correction and
    # current row remain distinct identities sharing one business key.
    meta = _reset_for("m-inheritance-100", provisioner)
    db = connect(provisioner.port, meta)
    snapshot = history_of_a_concrete_temporal_node_distinguishes_milestones(db)
    nodes = snapshot.results()
    assert len(nodes) == 2
    by_amount = {node.amount: node for node in nodes}
    historical = by_amount[Decimal("2.25")]
    current = by_amount[Decimal("2.50")]
    assert historical is not current  # distinct identities per milestone
    assert historical.grade == "B"
    assert current.grade == "A"
    historical_edge = edge_of(historical)
    current_edge = edge_of(current)
    assert historical_edge.business == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert historical_edge.processing == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert current_edge.business == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert current_edge.processing == dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
    # Both `pin_of` calls succeed (the root-owned axes attach a pin to a
    # concrete node exactly as they would at the abstract root or an
    # abstract-subtype position).
    pin_of(historical)
    pin_of(current)


def test_every_graph_story_mirrors_an_active_case_exactly_once() -> None:
    assert len(_GRAPH_STORIES_BY_ID) == len(GRAPH_STORIES)
    for story in GRAPH_STORIES:
        assert story.case_id in _CASES, story.case_id
        model_ref = str(case_document(_CASES[story.case_id])["model"])
        assert story.model == model_ref.removeprefix("models/").removesuffix(".yaml"), story.case_id


# --------------------------------------------------------------------------- #
# Read stories (m-api-conformance S1 remediation): a GENERIC runner, unlike    #
# the write/graph stories above — every read-only example's execution shape   #
# is identical (reset, `db.find(build())`, compare), so ONE parametrized test #
# drives every `read_stories.READ_STORIES` entry instead of a hand-rolled     #
# per-case function. Grading is the case's own `then.rows` (order-insensitive,#
# exact-typed, physical-column-keyed — `instance_row`, never the canonical    #
# camelCase `orderedOn` spelling `then.rows` never uses) plus `then.roundTrips`#
# when the case declares it. `familyVariant` is reported only for a case whose #
# own oracle rows declare it (an abstract-root inheritance read) — the        #
# API-suite's own polymorphism observation (`python.md` §4: "observable as    #
# `type(node)`"), not a field the developer surface itself exposes.           #
#                                                                              #
# `story.concurrency` (COR-3 Phase 8 increment 6, the `m-read-lock` matrix)   #
# opts a story into the TRANSACTIONAL half instead: `tx.find(build())` inside #
# a `db.transact` of the declared participation mode, still graded against    #
# the SAME `then.rows` oracle — the runtime proof that the mode actually      #
# drives whether the emitted SQL carries the shared read-lock suffix          #
# (unobservable from `then.rows` alone; the compile/run sweeps prove the      #
# emitted SQL byte-exact, this proves the SAME mode reaches the SAME public   #
# surface a developer drives).                                                #
# --------------------------------------------------------------------------- #
_READ_STORY_IDS = [story.case_id for story in READ_STORIES]


@pytest.mark.parametrize("story", READ_STORIES, ids=_READ_STORY_IDS)
def test_read_story_runs_through_the_shipped_surface(story: ReadStory, provisioner: Any) -> None:
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    if story.concurrency is not None:
        snapshot = db.transact(lambda tx: tx.find(story.build()), concurrency=story.concurrency)
    else:
        snapshot = db.find(story.build())
    expected_rows = cast(
        "list[dict[str, Any]]", case_document(_CASES[story.case_id])["then"]["rows"]
    )
    expects_variant = any("familyVariant" in row for row in expected_rows)
    observed_rows = [
        instance_row(instance, family_variant=expects_variant) for instance in snapshot.results()
    ]
    compare_rows(observed_rows, expected_rows)
    expected_round_trips = case_document(_CASES[story.case_id])["then"].get("roundTrips")
    if expected_round_trips is not None:
        assert snapshot.execution.round_trips == expected_round_trips, story.case_id


def test_every_read_story_mirrors_an_active_case_exactly_once() -> None:
    by_id = {story.case_id: story for story in READ_STORIES}
    assert len(by_id) == len(READ_STORIES)
    for story in READ_STORIES:
        assert story.case_id in _CASES, story.case_id
        assert _CASES[story.case_id].shape == "read", story.case_id
        model_ref = str(case_document(_CASES[story.case_id])["model"])
        assert story.model == model_ref.removeprefix("models/").removesuffix(".yaml"), story.case_id
