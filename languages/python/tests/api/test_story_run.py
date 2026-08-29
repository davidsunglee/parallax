"""API-suite stories against real Postgres (m-api-conformance, spec §"API
Conformance Suite").

Every registered story — write (`parallax.conformance.stories`) or graph-read
(`parallax.conformance.graph_stories`); the same executable functions the Usage
Guide renders — executes here through the **shipped** surface:
`parallax.snapshot.connect` over the `parallax-postgres` adapter against the
real Testcontainers Postgres, inside the documented API-conformance lane
(python.md: pytest under ``tests/api/``,
"executing idiomatic public-API code through the shipped `parallax-snapshot`
extension and `parallax-postgres` adapter"; IMPLEMENTING.md "Continuous API
Conformance Lane" step 2). Docker-backed: the shared ``provisioner`` fixture
skips with a recorded reason when Docker is unavailable (never silently), and
the ``python-check-db`` CI job fails on any skip. A write story's grading is
the mirrored case's own oracle: a story returning rows must observe its final
find's `expectRows`; a writeSequence story must leave exactly `then.tableState`
behind. The one `kind == "boundary"` story (`m-unit-work-004`) is excluded from
this file's grading loop because the case-driven boundary runner
(`test_boundary_run.py`) grades it — and every other boundary-shape case —
directly against the corpus. The story remains registered for the Usage Guide
and the fake-port wire
pin (`test_write_no_drift.py`). A graph story's grading is bespoke per case
(see the section below).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from _support.corpus import (
    CollectionKinds,
    case_document,
    case_fixtures,
    compare_binds,
    compare_graph,
    compare_rows,
    instance_graph_node,
    instance_row,
)
from parallax.conformance import case_format, engine
from parallax.conformance._lifecycle_observation import LifecycleObservation
from parallax.conformance.animal_owner import Person as AnimalOwnerPerson
from parallax.conformance.class_models import MODELS
from parallax.conformance.graph_stories import (
    GRAPH_STORIES,
    a_finite_transaction_time_pinned_view_is_read_only,
    history_of_a_concrete_temporal_node_distinguishes_milestones,
)
from parallax.conformance.read_models import Animal, Cat, Dog
from parallax.conformance.read_stories import READ_STORIES, ReadStory
from parallax.conformance.stories import WRITE_STORIES, WriteStory
from parallax.conformance.story_models import Order, OrderStatus
from parallax.core import LATEST, DomainModel, ObjectQuery
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity import UnloadedRelationshipError, ValueObject, to_document
from parallax.core.entity._model import model_of
from parallax.core.unit_work import Concurrency
from parallax.snapshot import InvalidData, connect, edge_of, is_view_loaded, pin_of, view
from parallax.snapshot.handle import (
    Database,
    Snapshot,
    Transaction,
    TransactionTimePinReadOnlyError,
)

_CASES = {c.case_id: c for c in case_format.load_cases()}


def _scenario_steps(case_id: str) -> list[dict[str, Any]]:
    """The case's own ``when.scenario`` steps, in authored order."""
    return cast("list[dict[str, Any]]", case_document(_CASES[case_id])["when"]["scenario"])


def _scenario_finds(case_id: str) -> list[dict[str, Any]]:
    """The scenario's find steps, in authored order."""
    finds = [step for step in _scenario_steps(case_id) if "objectQuery" in step]
    assert finds, case_id
    return finds


def _final_find_expect_rows(case_id: str) -> list[dict[str, Any]]:
    """The last scenario find step's ``expectRows`` — the story's returned oracle."""
    return cast("list[dict[str, Any]]", _scenario_finds(case_id)[-1]["expectRows"])


def _reset_for(case_id: str, provisioner: Any) -> DomainModel:
    """Provision one case's schema and fixtures, and answer the model to connect with.

    The schema comes from the case's own corpus model and the Domain Model from
    the class family mirroring it: the two are structurally identical (the
    descriptor no-drift guard is the proof), and only the class-backed model
    carries the class index a story's own observing find needs to materialize
    typed instances.
    """
    case = _CASES[case_id]
    provisioner.reset(engine.load_case_metamodel(case), case_fixtures(case))
    return MODELS[Path(case.model).stem]


# `kind == "boundary"` (m-unit-work-004) is excluded from execution here because
# the case-driven boundary runner (`tests/api/test_boundary_run.py`)
# grades it directly
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
    # A story's scripted-clock factory supplies this consumer with a fresh
    # clock independent of `test_write_no_drift.py`.
    clock = story.clock() if story.clock is not None else None
    db = connect(provisioner.port, meta, clock=clock)

    result = story.run(db)
    if result is not None:
        # Commit and abort stories both conclude with an observing find; its
        # rows must equal the mirrored case's final `expectRows`. A scenario's
        # `expectRows` is
        # INSTANCE-form, m-case-format — physical-column-keyed, `instance_row`,
        # never the canonical camelCase `engine.wire_row` used to render).
        compare_rows([instance_row(row) for row in result], _final_find_expect_rows(story.case_id))
        return

    # A writeSequence story observes no rows; the committed table state must
    # equal the case's `then.tableState`, table for table.
    expected_state = cast(
        "dict[str, list[dict[str, Any]]]",
        case_document(_CASES[story.case_id])["then"]["tableState"],
    )
    observed_state = engine.read_table_state(provisioner.port, model_of(meta), POSTGRES)
    assert set(observed_state) >= set(expected_state), (story.case_id, observed_state)
    for table, expected_rows in expected_state.items():
        compare_rows(observed_state[table], expected_rows)


# --------------------------------------------------------------------------- #
# Graph stories (`m-snapshot-read` / `m-navigate`)                             #
# the read-side sibling of the write stories above, executed through the SAME #
# shipped `parallax.snapshot.connect` + `parallax-postgres` surface. Grading  #
# is bespoke per story (unlike the write stories' shared row/table-state      #
# comparators): each assertion mirrors its case's own `then.graph` or         #
# scenario oracle as closely as one in-process assertion                      #
# can — the developer-facing guarantees a wire grade cannot see (reference    #
# identity surviving materialization, `is_view_loaded` /                      #
# `UnloadedRelationshipError`, `pin_of`/`edge_of` on a materialized node).     #
# --------------------------------------------------------------------------- #
_GRAPH_STORIES_BY_ID = {story.case_id: story for story in GRAPH_STORIES}


class _CountingDatabase(Database):
    """A ``Database`` that records what each of its own operations put on the wire.

    A result carries no record of the execution that produced it
    (`m-execution-lifecycle`), and a Usage Guide story's code is production's —
    so the per-operation round-trip counts a scenario step's own oracle grades
    are observed here, at the one boundary where "one operation" exists as a
    thing. ``round_trips`` holds one entry per :meth:`find` and :meth:`transact`
    call, in call order, which is the same partition the case's steps draw.
    """

    def __init__(self, port: Any, model: Any, clock: Any = None) -> None:
        self.observation = LifecycleObservation()
        super().__init__(port, model, clock=clock, lifecycle_provider=self.observation.provider)
        self.round_trips: list[int] = []

    def _counted[T](self, run: Callable[[], T]) -> T:
        mark = self.observation.round_trips
        try:
            return run()
        finally:
            self.round_trips.append(self.observation.round_trips - mark)

    def find[S](self, query: ObjectQuery[Any, S]) -> Snapshot[S]:
        return self._counted(lambda: super(_CountingDatabase, self).find(query))

    def transact[T](
        self,
        fn: Callable[[Transaction], T],
        *,
        retries: int | None = None,
        concurrency: Concurrency | None = None,
        retry_optimistic_conflicts: bool | None = None,
        isolation: str | None = None,
    ) -> T:
        return self._counted(
            lambda: super(_CountingDatabase, self).transact(
                fn,
                retries=retries,
                concurrency=concurrency,
                retry_optimistic_conflicts=retry_optimistic_conflicts,
                isolation=isolation,
            )
        )


def _counting_connect(port: Any, model: Any, *, clock: Any = None) -> _CountingDatabase:
    return _CountingDatabase(port, model, clock)


def _kind_runs(db: _CountingDatabase) -> list[tuple[str, int]]:
    """The statements one handle ran, run-length encoded by port method.

    Inside a single transaction the operation boundary is gone, so the step
    partition a grouped scenario grades is recovered from the wire itself: a run
    of reads is a find, a run of writes is the flush its buffered writes reached
    the database through.
    """
    runs: list[tuple[str, int]] = []
    for call in db.observation.calls:
        if runs and runs[-1][0] == call.kind:
            runs[-1] = (call.kind, runs[-1][1] + 1)
        else:
            runs.append((call.kind, 1))
    return runs


def test_diamond_identity_shares_one_child_node(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-001"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    order = snapshot.result()
    # The diamond: both include paths reach OrderItem 12 then OrderItem 11 (id
    # desc / shipped_on asc happen to agree here) — one materialized node, not
    # two lookalike copies. Reference identity is what only this lane can show:
    # the case's own `then.graph` grades the value at both positions and cannot
    # distinguish one shared node from two equal ones.
    assert order.items[0] is order.items_by_ship_date[0]
    assert order.items[1] is order.items_by_ship_date[1]
    assert db.round_trips == [3]


def test_back_reference_cycle_resolves_to_the_root(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-011"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    order = snapshot.result()
    # The typed lane merges every projection of one row onto one node, so the
    # back-reference IS the root object rather than a lookalike re-fetch — the
    # in-memory cycle the wire lane unwinds finitely into a value tree.
    assert order.items[0].order is order
    assert order.items[1].order is order
    assert db.round_trips == [2]


def test_closed_world_unloaded_access_raises_without_sql(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-009"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    order = snapshot.result()
    assert is_view_loaded(order, Order.statuses) is False
    with pytest.raises(UnloadedRelationshipError, match="statuses"):
        order.statuses  # noqa: B018 - the access itself is the assertion
    # The access issues no SQL of its own: the materializing find is the only
    # round trip on record (m-snapshot-read-009 is this suite's official grader
    # for the closed-world absence witness, `lane: api-conformance`).
    assert db.round_trips == [1]


def test_empty_root_materializes_no_children(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-004"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    assert snapshot.results() == []
    assert db.round_trips == [1]


def test_empty_intermediate_level_short_circuits(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-005"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    order = snapshot.result()
    assert order.items == ()
    assert db.round_trips == [2]


def test_pinned_graph_at_a_past_valid_time_instant(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-navigate-013"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    policy = next(p for p in snapshot.results() if p.id == 1)
    coverage = policy.coverages[0]
    assert coverage.amount == Decimal("600.00")  # the HEAD as of 2024-03-01, not the current 700
    edge = edge_of(coverage)
    assert edge.valid_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert edge.tx_time == dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
    pin = snapshot.pin
    assert pin.valid_time == dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
    assert pin.tx_time is LATEST


def test_mutation_has_no_writeback(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-010"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    mutated, reread = story.run(db)
    assert mutated.name == "Mutant"  # the in-memory copy sees the edit
    assert reread.result().name == "Ada"  # the re-read never observes it


def test_an_edited_copy_keeps_its_source_nodes_views(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-015"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot, edited = story.run(db)
    order = snapshot.result()
    assert (edited.name, order.name) == ("Mutant", "Ada")
    # The copy is closed-world exactly as the node is, and answers the absence
    # the same way rather than failing on a member the rebuild dropped.
    assert is_view_loaded(edited, Order.statuses) is False
    with pytest.raises(UnloadedRelationshipError, match="statuses"):
        edited.statuses  # noqa: B018 - the access itself is the assertion
    # Neither the derivation nor the access issues SQL: the materializing find is
    # still the only round trip on record.
    assert db.round_trips == [1]


def test_an_edit_keeps_a_loaded_relationship_view(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-016"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot, edited = story.run(db)
    order = snapshot.result()
    assert (edited.name, order.name) == ("Mutant", "Ada")
    # What only this lane can show: the copy's items are the SAME objects, not
    # lookalike values. The case's own `expectGraph` grades the CONTENTS at both
    # positions and cannot tell one shared node from two equal ones.
    assert is_view_loaded(edited, Order.items) is True
    assert [item.id for item in edited.items] == [12, 11]
    assert edited.items[0] is order.items[0]
    assert edited.items[1] is order.items[1]
    # Neither the derivation nor the access issues SQL: the materializing find's
    # own two levels are still the only round trips on record.
    assert db.round_trips == [2]


def test_a_write_keeps_a_loaded_to_one_view(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-017"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot, loaded_order, reread = story.run(db)
    item = snapshot.result()
    # What only this lane can show: the write replaced no node — the view still
    # holds the SAME object, which the case's `expectGraph` (contents alone)
    # cannot distinguish from an equal-valued rebuild. And the value it holds is
    # the one the read paid for, while the database is where the write is
    # observable, which is what the re-read is for.
    assert item.order is loaded_order
    assert (loaded_order.name, reread.name) == ("Ada", "Rewritten")
    # The story's own first operation: the materializing read the surviving view
    # hangs off, before the write and the re-read that follow it.
    assert db.round_trips[0] == 2


def _committed_item_ids(db: Database, order_id: int) -> list[int]:
    """The line items ``order_id`` owns in the DATABASE, read after a story ran.

    The composition stories' own oracle for the half their returned snapshot
    cannot show: that the insert really committed against the very order whose
    relationship the surviving view answers for. Without it a story whose
    transaction did nothing would satisfy every assertion about that view.
    """
    reread = db.find(Order.where(Order.id == order_id).include(Order.items)).result()
    return [item.id for item in reread.items]


def test_a_write_keeps_a_loaded_empty_relationship_view(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-018"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    order = snapshot.result()
    # Loaded and EMPTY: the view answers a value rather than raising, and the
    # value is still empty though the table now holds item 31. The per-language
    # half of the distinction m-snapshot-read-019 holds from the other side.
    assert is_view_loaded(order, Order.items) is True
    assert order.items == ()
    assert db.round_trips[0] == 2
    # The write is load-bearing: order 3 really owns item 31 now, so the empty
    # tuple above is a value only the surviving view can answer.
    assert _committed_item_ids(db, 3) == [31]


def test_a_write_keeps_an_unloaded_relationship_absent(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-019"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    order = snapshot.result()
    # Unloaded, not empty — the same fixture row, relationship and write as
    # m-snapshot-read-018, differing only in the include the read declared. This
    # language surfaces the absence by raising, so an assertion that `items` is
    # `()` here would fail, which is what keeps the two apart.
    assert is_view_loaded(order, Order.items) is False
    with pytest.raises(UnloadedRelationshipError, match="items"):
        order.items  # noqa: B018 - the access itself is the assertion
    # The access issues no SQL of its own, the write's own unit of work aside:
    # the materializing find is the only round trip this snapshot ever cost.
    assert db.round_trips[0] == 1
    # This case's lane has no corpus executor at all, so the write it composes
    # across is proven here or nowhere: order 3 really owns item 31, and the
    # relationship stayed absent across a write that genuinely landed on it.
    assert _committed_item_ids(db, 3) == [31]


def _access_expect_graph(case_id: str) -> dict[str, Any]:
    """The scenario's single ``expectGraph`` — the surviving view's own oracle."""
    graphs = [step["expectGraph"] for step in _scenario_steps(case_id) if "expectGraph" in step]
    assert len(graphs) == 1, case_id
    return cast("dict[str, Any]", graphs[0])


def _serialize_value_object_members(node: dict[str, Any]) -> dict[str, Any]:
    """``node`` with every Value Object member serialized to its canonical document.

    A `then.graph` / `expectRows` leaf is the document the read published, and
    canonical serialization is presence-filtered the same way: a member the
    stored document omitted is absent from both sides, and one it stored as JSON
    null is null on both. Rendering by GETTER instead would report what an absent
    member READS as — the absence collapse `m-predicate` fixes — which is a
    different observation and the one thing this comparison must not substitute
    for the published value.
    """
    return {
        key: to_document(value) if isinstance(value, ValueObject) else value
        for key, value in node.items()
    }


def _assert_surviving_view(case_id: str, entity: str, instances: Sequence[Any]) -> None:
    """Grade a composition story's surviving relationship view against the whole
    ``expectGraph`` its access step authors, through the SAME model-driven
    comparator the wire lane grades that step by — so every leaf the case states
    is asserted here rather than the handful an assertion happens to name."""
    compare_graph(
        {
            entity: [
                _serialize_value_object_members(instance_graph_node(instance))
                for instance in instances
            ]
        },
        _access_expect_graph(case_id),
        CollectionKinds(engine.load_case_metamodel(_CASES[case_id])),
    )


def _assert_read_step_graph(
    case_id: str, index: int, entity: str, member: str, snapshot: Any
) -> None:
    """Grade one of a story's own finds against the whole ``expectGraph`` the
    scenario's step at ``index`` authors — the observable's READ placement.

    The graded value is the whole graph that find materialized: each root's own
    members, plus the ``member`` relationship its Include Path populated, read
    off the typed nodes the story holds and compared through the SAME
    model-driven comparator the wire lane grades the step by. `instance_graph_node`
    renders scalar and value-object members alone, so a loaded arm is attached
    here from the developer surface — which is what makes this the typed lane's
    answer to the same authored expectation rather than a second rendering of the
    wire's.
    """
    step = _scenario_steps(case_id)[index]
    expected = cast("dict[str, list[dict[str, Any]]]", step["expectGraph"])
    observed = {
        entity: [
            _vo_owner_row(root)
            | {member: [_vo_owner_row(child) for child in getattr(root, member)]}
            for root in snapshot.results()
        ]
    }
    compare_graph(observed, expected, CollectionKinds(engine.load_case_metamodel(_CASES[case_id])))


def _assert_find_step_rows(case_id: str, index: int, snapshot: Any) -> None:
    """Grade one of a composition story's own finds against the ``expectRows``
    the scenario's find at ``index`` states.

    Both of them: the materializing read whose root the surviving view hangs off,
    and the read-back where the write IS observable. A story that rooted on
    another row — or whose read-back reached rows the case does not state —
    fails on the step it mirrors rather than on the relationship view alone.
    """
    compare_rows(
        [
            _serialize_value_object_members(instance_row(instance))
            for instance in snapshot.results()
        ],
        cast("list[dict[str, Any]]", _scenario_finds(case_id)[index]["expectRows"]),
    )


def _assert_composition_units(case_id: str, db: _CountingDatabase) -> None:
    """A composition story's units of work each cost the round trips the scenario
    step they mirror authors, and together the case's own ``then.roundTrips``.

    ``db.round_trips`` holds the story's own ``find`` and ``transact`` calls in
    AUTHORED order, one per scenario step that touches the database — every find
    and every write, which is the same partition the case's own steps draw. A
    zero-round-trip `access` rides on the counter of the find its `on` names, so
    its declared cost is added there rather than counted on its own: a
    re-fetching access breaks that find's equality.

    Per step and in total, because the aggregate alone admits compensating
    errors: a read-back that re-read the root with an include costs one round
    trip too many, which a write that skipped its resolving read would pay for.
    """
    steps = _scenario_steps(case_id)
    expected = [
        cast("int", step["roundTrips"])
        + sum(
            cast("int", rider["roundTrips"])
            for rider in steps
            if rider.get("action") == "access" and rider.get("on") == index
        )
        for index, step in enumerate(steps)
        if "write" in step or "objectQuery" in step
    ]
    assert db.round_trips == expected, case_id
    assert sum(db.round_trips) == case_document(_CASES[case_id])["then"]["roundTrips"], case_id


def test_a_delete_keeps_a_loaded_relationship_view(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-020"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot, loaded_items, _committed, reread = story.run(db)
    _assert_find_step_rows(story.case_id, 0, snapshot)
    _assert_surviving_view(story.case_id, "OrderItem", loaded_items)
    # The multiset comparison above cannot see order; the relationship declares
    # `id desc`, and the destroyed row is still in its declared position.
    assert [item.id for item in loaded_items] == [12, 11]
    # What only this lane can show: it is the SAME object — an eviction that
    # replaced it with an equal-valued rebuild would satisfy the case's
    # `expectGraph` and fail here.
    assert snapshot.result().items[1] is loaded_items[1]
    # The delete is load-bearing: item 11 is gone from the database, so the node
    # the view still answers denotes a row no read can reach.
    _assert_find_step_rows(story.case_id, 1, reread)
    _assert_composition_units(story.case_id, db)


def test_a_rectangle_split_keeps_a_loaded_relationship_view(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-025"]
    meta = _reset_for(story.case_id, provisioner)
    # The case's own `at:` instant, so the rectangles the split chains open where
    # the case says they do and its read-back rows are gradable at all.
    clock = story.clock() if story.clock is not None else None
    db = _counting_connect(provisioner.port, meta, clock=clock)
    snapshot, loaded_coverages, _committed, reread = story.run(db)
    _assert_find_step_rows(story.case_id, 0, snapshot)
    _assert_surviving_view(story.case_id, "Coverage", loaded_coverages)
    assert snapshot.result().coverages[0] is loaded_coverages[0]
    # The re-read takes the SAME pin and answers the middle rectangle the split
    # chained, so the two disagree by construction — which is what a bitemporal
    # store is for.
    _assert_find_step_rows(story.case_id, 1, reread)
    _assert_composition_units(story.case_id, db)


def test_an_edit_chain_keeps_a_loaded_relationship_view(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-022"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot, renamed, restated = story.run(db)
    order = snapshot.result()
    _assert_find_step_rows(story.case_id, 0, snapshot)
    # The case's own access names step 0, so its `expectGraph` is the SOURCE's
    # view — graded here through the same comparator the wire lane uses.
    _assert_surviving_view(story.case_id, "OrderItem", order.items)
    # What only this lane holds: the copies themselves. Each hop of the chain
    # answers the SAME materialized children, which is what makes the chain a
    # chain of copies rather than one dict written twice — and the change-free
    # hop carries the authored one's assignment while the source keeps its own.
    _assert_surviving_view(story.case_id, "OrderItem", restated.items)
    assert (order.name, renamed.name, restated.name) == ("Ada", "Mutant", "Mutant")
    assert [copy.items[0] is order.items[0] for copy in (renamed, restated)] == [True, True]
    assert [copy.items[1] is order.items[1] for copy in (renamed, restated)] == [True, True]
    _assert_composition_units(story.case_id, db)


def test_a_write_keeps_a_loaded_value_object_document(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-023"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot, loaded_customer, _committed, reread = story.run(db)
    _assert_find_step_rows(story.case_id, 0, snapshot)
    _assert_surviving_view(story.case_id, "Customer", [loaded_customer])
    # The comparator above already grades `phones` POSITIONALLY (a
    # `multiplicity: many` Value Object); this states the order in the open, so a
    # reader can see that the surviving document and the written one are the same
    # two elements in opposite sequence.
    assert [(phone.type, phone.number) for phone in loaded_customer.address.phones] == [
        ("home", "555-1234"),
        ("work", "555-9999"),
    ]
    # What only this lane can show: the write replaced no node — the view still
    # holds the SAME object, which the case's `expectGraph` cannot distinguish
    # from an equal-valued rebuild.
    assert snapshot.result().customer is loaded_customer
    # The re-read is where the write IS observable, and it disagrees with the
    # surviving view on both the changed leaf and the element order.
    _assert_find_step_rows(story.case_id, 1, reread)
    _assert_composition_units(story.case_id, db)


def test_a_write_keeps_a_view_over_freshly_inserted_rows(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-024"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    _created, snapshot, loaded_items, _committed, reread = story.run(db)
    _assert_find_step_rows(story.case_id, 0, snapshot)
    _assert_surviving_view(story.case_id, "OrderItem", loaded_items)
    # What only this lane can show: it is the SAME object, not an equal-valued
    # rebuild the case's contents comparison would also accept.
    assert snapshot.result().items[0] is loaded_items[0]
    # The update is load-bearing: the row the view still answers for carries the
    # rewritten sku in the database, so `C-610` is a value only the surviving
    # view can produce — and the insert before it is what put the row there.
    _assert_find_step_rows(story.case_id, 1, reread)
    _assert_composition_units(story.case_id, db)


def test_a_multi_hop_access_drops_its_null_branches(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-026"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_find_step_rows(story.case_id, 0, snapshot)
    order = snapshot.result()
    # The walk the case states, performed on the developer surface: every status's
    # own `order_item` view, in traversal order, with the order-level status's
    # loaded-NULL branch dropped.
    reached = [status.order_item for status in order.statuses if status.order_item is not None]
    _assert_surviving_view(story.case_id, "OrderItem", reached)
    assert sorted(item.id for item in reached) == [11, 11, 12]
    # What only this lane can show: the two statuses reaching item 11 reach the
    # SAME node, so the repeat in the contents is one object named twice rather
    # than two equal ones — and the dropped branch is a loaded null, not an
    # unloaded view.
    assert reached[0] is reached[1]
    assert [is_view_loaded(status, OrderStatus.order_item) for status in order.statuses] == [
        True,
        True,
        True,
        True,
    ]
    _assert_composition_units(story.case_id, db)


def test_a_grouped_read_observes_its_own_relationship_writes(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-unit-work-029"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    before, after = story.run(db)
    # Both finds, against the graph each of them authors: step 0's two fixture
    # items and step 2's three, with the group's own insert and update in them.
    _assert_read_step_graph(story.case_id, 0, "Order", "items", before)
    _assert_read_step_graph(story.case_id, 2, "Order", "items", after)
    # The two reads are separate materializations of one relationship, so the
    # second answers NEW nodes rather than the first's — the half a contents
    # comparison cannot see, and the opposite of what a surviving-view story
    # asserts. The first still answers what it fetched.
    assert [item.id for item in before.result().items] == [12, 11]
    assert [item.id for item in after.result().items] == [13, 12, 11]
    assert after.result().items[2] is not before.result().items[1]
    assert before.result().items[1].sku == "A-100"
    # In total, and step by step. The group's own steps run inside ONE
    # transaction, so what separates them at the wire is which port method ran
    # each statement: two reads for the first find, two writes for the group's
    # own insert and update, two reads for the dependent find — no resolving
    # read for the write, because the group's own find already published the row
    # its update settles against.
    steps = _scenario_steps(story.case_id)
    assert db.round_trips == [case_document(_CASES[story.case_id])["then"]["roundTrips"]]
    assert _kind_runs(db) == [
        ("read", steps[0]["roundTrips"]),
        ("write", steps[1]["roundTrips"]),
        ("read", steps[2]["roundTrips"]),
    ]
    # The group really committed: a fresh read outside it observes what the
    # dependent find observed inside it.
    assert _committed_item_ids(db, 1) == [13, 12, 11]


def test_a_finite_transaction_time_pinned_view_is_read_only(provisioner: Any) -> None:
    # `m-identity-map-010` is graded here rather than through a `GraphStory`
    # because it sits outside the claimed active slice (see the story's own
    # docstring). What the corpus lane's own mutate-step grading cannot reach:
    # that refusal is derived from the step's Object Query, never from the
    # value the derivation produced, so it holds whether or not an edited copy
    # carries its source node's pin. This runs the ordinary developer sequence —
    # pinned find, edit, keyed verb — and the pin is carried on the value.
    meta = _reset_for("m-identity-map-010", provisioner)
    db = _counting_connect(provisioner.port, meta)
    before = engine.read_table_state(provisioner.port, model_of(meta), POSTGRES)
    with pytest.raises(TransactionTimePinReadOnlyError) as refused:
        a_finite_transaction_time_pinned_view_is_read_only(db)
    assert refused.value.code == "transaction-time-pin-read-only"
    # The case's own `roundTrips: 0` on the mutate step, graded as durable state:
    # the superseded milestone and the current one stand exactly as they were, so
    # nothing appended and nothing was rewritten.
    assert engine.read_table_state(provisioner.port, model_of(meta), POSTGRES) == before


def test_history_of_a_concrete_temporal_node_distinguishes_milestones(provisioner: Any) -> None:
    # This history check is not tied to any case's exercised status.
    # `m-inheritance-100`'s point read is graded by its `ReadStory`
    # below (`test_read_story_runs_through_the_shipped_surface`), through the
    # generic case-driven runner, exactly like every other read story. This
    # proves the SEPARATE milestone-HISTORY shape over the SAME fixture: a
    # concrete TPCS node (DepositRate) whose family's as-of axes are declared
    # on the root (Rate) alone still gets its own pin/edge attached, and a
    # `.history(...)` milestone-set read's closed historical correction and
    # current row remain distinct identities sharing one business key.
    meta = _reset_for("m-inheritance-100", provisioner)
    db = _counting_connect(provisioner.port, meta)
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
    assert historical_edge.valid_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert historical_edge.tx_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert current_edge.valid_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert current_edge.tx_time == dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
    # Both `pin_of` calls succeed (the root-owned axes attach a pin to a
    # concrete node exactly as they would at the abstract root or an
    # abstract-subtype position).
    pin_of(historical)
    pin_of(current)


def test_one_to_one_peer_attaches_as_a_single_object(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-007"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    by_id = {person.id: person for person in snapshot.results()}
    assert by_id[1].passport is not None
    assert by_id[1].passport.number == "P-AAA"
    assert by_id[2].passport is not None
    assert by_id[2].passport.number == "P-BBB"
    assert by_id[3].passport is None  # no passport on record -> a null peer
    assert db.round_trips == [2]


def test_animal_owner_reaches_root_and_narrowed_subtype_view(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-012"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    alice = snapshot.result()
    assert isinstance(alice, AnimalOwnerPerson)
    assert alice.name == "Alice"
    assert {pet.name for pet in alice.animals} == {"Rex", "Whiskers"}
    dogs = view(alice, AnimalOwnerPerson.pets.narrow(Dog))
    assert [dog.name for dog in cast("tuple[Any, ...]", dogs)] == ["Rex"]
    assert db.round_trips == [3]


def test_narrowed_pets_view_populates_per_owner(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-065"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    by_name = {person.name: person for person in snapshot.results()}
    alice_dogs = view(by_name["Alice"], AnimalOwnerPerson.pets.narrow(Dog))
    assert [dog.name for dog in cast("tuple[Any, ...]", alice_dogs)] == ["Rex"]
    bob_dogs = view(by_name["Bob"], AnimalOwnerPerson.pets.narrow(Dog))
    assert [dog.name for dog in cast("tuple[Any, ...]", bob_dogs)] == ["Fido"]
    carol_dogs = view(by_name["Carol"], AnimalOwnerPerson.pets.narrow(Dog))
    assert carol_dogs == ()
    assert db.round_trips == [2]


def test_equivalent_narrow_spellings_dedupe_to_one_view(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-066"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    by_name = {person.name: person for person in snapshot.results()}
    alice_view = view(by_name["Alice"], AnimalOwnerPerson.pets.narrow(Cat, Dog))
    assert {pet.name for pet in cast("tuple[Any, ...]", alice_view)} == {"Rex", "Whiskers"}
    assert db.round_trips == [2]


def test_distinct_narrowed_views_populate_independently(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-067"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    alice = next(person for person in snapshot.results() if person.name == "Alice")
    alice_dogs = view(alice, AnimalOwnerPerson.pets.narrow(Dog))
    alice_cats = view(alice, AnimalOwnerPerson.pets.narrow(Cat))
    assert [pet.name for pet in cast("tuple[Any, ...]", alice_dogs)] == ["Rex"]
    assert [pet.name for pet in cast("tuple[Any, ...]", alice_cats)] == ["Whiskers"]
    assert db.round_trips == [3]


def test_a_redundant_narrow_populates_a_view_beside_the_broad_one(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-068"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    alice = next(person for person in snapshot.results() if person.name == "Alice")
    # `view` derives its key from the AUTHORED spelling, so the story's
    # `narrow(Pet)` view is reached by the equivalent concrete spelling — the same
    # accessor route `test_equivalent_narrow_spellings_dedupe_to_one_view` takes.
    redundant = view(alice, AnimalOwnerPerson.pets.narrow(Cat, Dog))
    # The redundant narrow reaches exactly what the broad hop reaches, yet lands
    # under its own derived view key rather than merging into `pets`.
    assert sorted(pet.name for pet in alice.pets) == ["Rex", "Whiskers"]
    assert sorted(pet.name for pet in cast("tuple[Any, ...]", redundant)) == ["Rex", "Whiskers"]
    assert db.round_trips == [3]


def test_disjoint_root_guards_fill_one_owner_view(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-074"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    by_name = {animal.name: animal for animal in snapshot.results()}
    # Both guards fill the ORDINARY `owner` view, so the Dog and the Cat reach
    # their owner under the same key rather than a per-guard one.
    assert by_name["Rex"].owner.name == "Alice"
    assert by_name["Fido"].owner.name == "Bob"
    assert by_name["Whiskers"].owner.name == "Alice"
    # The WildBoar is admitted by neither guard, so its `owner` stays UNSET —
    # closed-world "never participated", not "no owner".
    assert is_view_loaded(by_name["Tusker"], Animal.owner) is False
    with pytest.raises(UnloadedRelationshipError, match="owner"):
        _ = by_name["Tusker"].owner
    assert db.round_trips == [3]


def test_a_root_guard_beside_a_broad_path_stays_its_own_hop(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-075"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    by_name = {animal.name: animal for animal in snapshot.results()}
    # The subsumed guard adds a statement and nothing else: the graph is exactly
    # the broad path's, the WildBoar included.
    assert {name: animal.owner.name for name, animal in by_name.items()} == {
        "Rex": "Alice",
        "Fido": "Bob",
        "Whiskers": "Alice",
        "Tusker": "Carol",
    }
    assert db.round_trips == [3]


def test_guarded_branches_keep_their_own_parents(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-078"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    by_name = {animal.name: animal for animal in snapshot.results()}
    # Both guarded owner hops fill the ordinary `owner` view; the Cat is admitted
    # by neither, so its whole branch of every path is absent.
    assert by_name["Rex"].owner.name == "Alice"
    assert by_name["Fido"].owner.name == "Bob"
    assert by_name["Tusker"].owner.name == "Carol"
    assert is_view_loaded(by_name["Whiskers"], Animal.owner) is False
    # `pets` continues from the DOG branch's owners alone, so the owner the
    # WildBoar branch reached carries none of it.
    assert sorted(pet.name for pet in by_name["Rex"].owner.pets) == ["Rex", "Whiskers"]
    assert [pet.name for pet in by_name["Fido"].owner.pets] == ["Fido"]
    assert is_view_loaded(by_name["Tusker"].owner, AnimalOwnerPerson.pets) is False
    assert db.round_trips == [4]


def test_a_guarded_root_continues_through_a_narrowed_hop(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-076"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    by_name = {animal.name: animal for animal in snapshot.results()}
    alice = by_name["Rex"].owner
    assert alice.name == "Alice"
    # The root guard contributed no key of its own; the segment narrow did.
    assert is_view_loaded(alice, AnimalOwnerPerson.pets) is False
    alice_dogs = view(alice, AnimalOwnerPerson.pets.narrow(Dog))
    assert [dog.name for dog in cast("tuple[Any, ...]", alice_dogs)] == ["Rex"]
    bob_dogs = view(by_name["Fido"].owner, AnimalOwnerPerson.pets.narrow(Dog))
    assert [dog.name for dog in cast("tuple[Any, ...]", bob_dogs)] == ["Fido"]
    # The Cat reaches the SAME owner object the Dog does; the guard excludes only
    # the WildBoar, whose whole branch of the path is therefore absent.
    assert by_name["Whiskers"].owner is alice
    assert is_view_loaded(by_name["Tusker"], Animal.owner) is False
    assert db.round_trips == [3]


def _vo_owner_row(instance: Any) -> dict[str, Any]:
    """A materialized VO-bearing owner's own graph node, DECLARED-member-keyed
    (``instance_graph_node``), with its value-object members serialized to their
    canonical documents (:func:`_serialize_value_object_members`) so
    ``compare_graph`` can recurse into them exactly like the wire-level engine's
    own `then.graph` grading."""
    return _serialize_value_object_members(instance_graph_node(instance))


def _assert_vo_owner_graph(case_id: str, snapshot: Any, entity_name: str, pk_member: str) -> None:
    expected_by_pk = {
        row[pk_member]: row
        for row in cast(
            "list[dict[str, Any]]", case_document(_CASES[case_id])["then"]["graph"][entity_name]
        )
    }
    kinds = CollectionKinds(engine.load_case_metamodel(_CASES[case_id]), entity_name)
    observed = [_hydrated(root) for root in snapshot.checked().results()]
    assert {instance.id for instance in observed} == set(expected_by_pk)
    for instance in observed:
        compare_graph(_vo_owner_row(instance), expected_by_pk[instance.id], kinds)


def test_transaction_time_only_vo_owner_as_of_latest(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-value-object-028"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_vo_owner_graph(story.case_id, snapshot, "Supplier", "id")
    assert db.round_trips == [1]


def test_transaction_time_only_vo_owner_as_of_a_past_instant(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-value-object-029"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_vo_owner_graph(story.case_id, snapshot, "Supplier", "id")
    assert db.round_trips == [1]


def test_bitemporal_vo_owner_as_of_latest(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-value-object-030"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_vo_owner_graph(story.case_id, snapshot, "Branch", "id")
    assert db.round_trips == [1]


def test_bitemporal_vo_owner_as_of_a_past_audit_point(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-value-object-031"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_vo_owner_graph(story.case_id, snapshot, "Branch", "id")
    assert db.round_trips == [1]


def _assert_typed_per_variant_graph(case_id: str, snapshot: Any, entity_name: str) -> None:
    """Render each instance with its concrete class's declared members.

    ``instance_graph_node`` also includes ``familyVariant`` for the
    declared-member-keyed node (spec §4 "observable as `type(node)`") — never a
    sibling's null-padded column, matching the case's own per-variant
    `then.graph` exactly (order-insensitive, `compare_rows`)."""
    expected = cast(
        "list[dict[str, Any]]", case_document(_CASES[case_id])["then"]["graph"][entity_name]
    )
    observed = [
        instance_graph_node(instance, family_variant=True) for instance in snapshot.results()
    ]
    compare_rows(observed, expected)


def test_tph_abstract_root_read_materializes_typed_per_variant_instances(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-106"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_typed_per_variant_graph(story.case_id, snapshot, "Payment")
    assert db.round_trips == [1]


def test_tph_narrow_to_abstract_subtype_materializes_typed_per_variant_instances(
    provisioner: Any,
) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-107"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_typed_per_variant_graph(story.case_id, snapshot, "Animal")
    assert db.round_trips == [1]


def test_tph_or_across_branches_materializes_typed_per_variant_instances(
    provisioner: Any,
) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-108"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_typed_per_variant_graph(story.case_id, snapshot, "Animal")
    assert db.round_trips == [1]


def test_tpcs_narrow_to_abstract_subtype_materializes_typed_per_variant_instances(
    provisioner: Any,
) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-109"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_typed_per_variant_graph(story.case_id, snapshot, "Document")
    assert db.round_trips == [1]


def _hydrated(root: Any) -> Any:
    """One published result position as the Entity a `then` oracle grades.

    The Customer fixture carries stored states that contradict the model on
    purpose, so a read over it publishes `InvalidData` records beside its
    conforming roots. The checked view is what a caller reading such a model uses;
    the classification itself is graded by the corpus (`then.storedDataIssues`),
    and what these stories grade is that the hydrated value is unchanged by it.
    """
    return cast("Any", root).data if isinstance(root, InvalidData) else root


def _assert_customer_predicate_rows(case_id: str, snapshot: Any) -> None:
    """The row-form predicate original's own ``then.rows`` oracle — id/name
    only, never the exact SQL the corpus's row-form classification would
    otherwise demand (`graph_stories`'s own module docstring explains why
    this grades here, bespoke, rather than through ``ReadStory``'s
    byte-exact generic runner)."""
    expected = cast("list[dict[str, Any]]", case_document(_CASES[case_id])["then"]["rows"])
    observed = [
        {"id": customer.id, "name": customer.name}
        for customer in map(_hydrated, snapshot.checked().results())
    ]
    compare_rows(observed, expected)


# The seven Customer nested-predicate stories share ONE execution shape
# (reset, run, `then.rows`, one round trip), so a single parametrized runner
# drives them — the READ-story generic-runner precedent below — with the
# behavior each case witnesses preserved as the parameter id.
@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param("m-value-object-001", id="nested-eq-city-selects-matching-owners"),
        pytest.param("m-value-object-002", id="deep-nested-eq-country-selects-the-matching-owner"),
        pytest.param("m-value-object-007", id="nested-is-null-collapses-every-not-present-state"),
        pytest.param("m-value-object-015", id="to-many-nested-exists-is-a-nonempty-test"),
        pytest.param(
            "m-value-object-016", id="to-many-nested-not-exists-folds-every-not-present-state"
        ),
        pytest.param("m-value-object-017", id="to-many-any-element-eq-matches-some-element"),
        pytest.param(
            "m-value-object-019", id="to-many-scoped-exists-requires-one-element-to-satisfy-both"
        ),
    ],
)
def test_customer_nested_predicate_story_selects_the_golden_owners(
    case_id: str, provisioner: Any
) -> None:
    story = _GRAPH_STORIES_BY_ID[case_id]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_customer_predicate_rows(story.case_id, snapshot)
    assert db.round_trips == [1]


@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param("m-value-object-023", id="whole-nested-composite"),
        pytest.param("m-value-object-024", id="composite-under-a-filter"),
    ],
)
def test_customer_owner_materializes_its_composite(case_id: str, provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID[case_id]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_vo_owner_graph(story.case_id, snapshot, "Customer", "id")
    assert db.round_trips == [1]


def _assert_customer_locations_graph(case_id: str, snapshot: Any) -> None:
    expected_by_id = {
        row["id"]: row
        for row in cast(
            "list[dict[str, Any]]", case_document(_CASES[case_id])["then"]["graph"]["Customer"]
        )
    }
    kinds = CollectionKinds(engine.load_case_metamodel(_CASES[case_id]), "Customer")
    observed = [_hydrated(root) for root in snapshot.checked().results()]
    assert {customer.id for customer in observed} == set(expected_by_id)
    for customer in observed:
        row = _vo_owner_row(customer)
        row["locations"] = [_vo_owner_row(location) for location in customer.locations]
        compare_graph(row, expected_by_id[customer.id], kinds)


def test_customer_locations_deep_fetch_materializes_the_child_document_too(
    provisioner: Any,
) -> None:
    story = _GRAPH_STORIES_BY_ID["m-deep-fetch-018"]
    meta = _reset_for(story.case_id, provisioner)
    db = _counting_connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_customer_locations_graph(story.case_id, snapshot)
    assert db.round_trips == [2]


def test_every_graph_story_mirrors_an_active_case_exactly_once() -> None:
    assert len(_GRAPH_STORIES_BY_ID) == len(GRAPH_STORIES)
    for story in GRAPH_STORIES:
        assert story.case_id in _CASES, story.case_id
        model_ref = str(case_document(_CASES[story.case_id])["model"])
        assert story.model == model_ref.removeprefix("models/").removesuffix(".yaml"), story.case_id


# --------------------------------------------------------------------------- #
# Read stories use one generic runner, unlike                                 #
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
# `story.concurrency` (the `m-read-lock` matrix) opts a story into the         #
# transactional half: `tx.find(build())` inside a `db.transact` of the        #
# declared Concurrency Preference, still graded against the SAME `then.rows`  #
# oracle, PLUS the statements this story's own find actually executed         #
# (`_StatementCapturePort` below) — the runtime proof that the preference and #
# the read target's own Optimistic Lock Facet together drive whether the      #
# emitted SQL carries the shared read-lock suffix (unobservable from          #
# `then.rows` alone: two stories can return identical rows while one holds a  #
# lock and the other does not).                                               #
# --------------------------------------------------------------------------- #
_READ_STORY_IDS = [story.case_id for story in READ_STORIES]


class _StatementCapturePort:
    """A pass-through ``m-db-port`` decorator capturing every SQL statement +
    binds a read story's find ACTUALLY executes: `then.rows` alone cannot
    distinguish whether a `m-read-lock` story's runtime developer path emitted
    the shared read-lock suffix; only the statement text can. ``transaction``
    nests another capture wrapper sharing this SAME ``statements`` list, because
    the underlying provider hands ``body`` ITSELF rather than this decorator, so
    a `tx.find` inside `db.transact` is captured from the SAME single execution
    as a non-transactional `db.find`.
    """

    def __init__(
        self, inner: Any, statements: list[tuple[str, tuple[object, ...]]] | None = None
    ) -> None:
        self._inner = inner
        self.statements: list[tuple[str, tuple[object, ...]]] = (
            statements if statements is not None else []
        )

    @property
    def dialect(self) -> Dialect:
        return cast("Dialect", self._inner.dialect)

    def execute(
        self, sql: str, binds: Any, document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[dict[str, Any]]:
        self.statements.append((sql, tuple(binds)))
        return self._inner.execute(sql, binds, document_reads=document_reads)

    def execute_write(self, sql: str, binds: Any) -> int:
        return self._inner.execute_write(sql, binds)

    def transaction(self, body: Any, *, isolation: str | None = None) -> Any:
        statements = self.statements

        def wrapped(conn: Any) -> Any:
            return body(_StatementCapturePort(conn, statements=statements))

        return self._inner.transaction(wrapped, isolation=isolation)


def test_statement_capture_forwards_document_read_metadata() -> None:
    class _Inner:
        def execute(
            self, sql: str, binds: Any, document_reads: Sequence[tuple[int, int]] = ()
        ) -> list[dict[str, Any]]:
            assert (sql, tuple(binds), tuple(document_reads)) == (
                "select false, payload",
                (),
                ((0, 1),),
            )
            return []

    assert _StatementCapturePort(_Inner()).execute("select false, payload", [], ((0, 1),)) == []


@pytest.mark.parametrize("story", READ_STORIES, ids=_READ_STORY_IDS)
def test_read_story_runs_through_the_shipped_surface(story: ReadStory, provisioner: Any) -> None:
    meta = _reset_for(story.case_id, provisioner)
    port = _StatementCapturePort(provisioner.port)
    db = connect(port, meta)
    if story.concurrency is not None:
        snapshot = db.transact(lambda tx: tx.find(story.build()), concurrency=story.concurrency)
    else:
        snapshot = db.find(story.build())
    then = cast("dict[str, Any]", case_document(_CASES[story.case_id])["then"])
    expected_rows = cast("list[dict[str, Any]]", then["rows"])
    expects_variant = any("familyVariant" in row for row in expected_rows)
    observed_rows = [
        instance_row(instance, family_variant=expects_variant) for instance in snapshot.results()
    ]
    compare_rows(observed_rows, expected_rows)
    expected_round_trips = then.get("roundTrips")
    if expected_round_trips is not None:
        assert len(port.statements) == expected_round_trips, story.case_id

    # Grade the statements this story's find actually executed against the
    # case's authored Postgres golden
    # dialect) — asserting the `for share of t0` lock suffix's presence
    # (`m-read-lock-002`) or absence (`m-read-lock-005`/every other read story)
    # exactly as authored, reusing the SAME driver-SQL translation and
    # exact-Decimal bind comparison every other run lane uses rather than an
    # ad hoc string match.
    golden_statements = then.get("statements")
    assert golden_statements is not None, story.case_id
    golden_statements = cast("list[dict[str, Any]]", golden_statements)
    assert len(port.statements) == len(golden_statements), (story.case_id, port.statements)
    for (sql, binds), entry in zip(port.statements, golden_statements, strict=True):
        golden_sql = entry["sql"]
        golden_text = (
            cast("dict[str, str]", golden_sql)["postgres"]
            if isinstance(golden_sql, dict)
            else golden_sql
        )
        assert sql == POSTGRES.to_driver_sql(cast("str", golden_text)), story.case_id
        compare_binds(binds, cast("list[object]", entry.get("binds", [])))


def test_every_read_story_mirrors_an_active_case_exactly_once() -> None:
    by_id = {story.case_id: story for story in READ_STORIES}
    assert len(by_id) == len(READ_STORIES)
    for story in READ_STORIES:
        assert story.case_id in _CASES, story.case_id
        assert _CASES[story.case_id].shape == "read", story.case_id
        model_ref = str(case_document(_CASES[story.case_id])["model"])
        assert story.model == model_ref.removeprefix("models/").removesuffix(".yaml"), story.case_id
