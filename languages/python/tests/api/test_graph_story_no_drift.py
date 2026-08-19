"""DB-free graph-story drivers for the read-side stories.

Every ``GRAPH_STORIES`` function executes through the shipped in-process
pipeline (statement build → canonicalize → plan → compile → port →
materialize → wrap) against a canned fake ``m-db-port``, so the story bodies
contribute to the database-free coverage gate exactly as ``test_write_no_drift``
keeps ``stories.py`` in it (pure, Docker-free, in-process behaviour). The
golden grading — real Postgres, each case's own oracle — stays in
``test_story_run.py``; this driver pins that each story RUNS through the
public surface (an empty root level legally short-circuits every child
level), plus the two edit stories' in-memory semantics — that a mutation
writes nothing back, and that an edited copy keeps its source node's view
state — which need no database at all. The two SUPPLEMENTAL story functions
(not ``GRAPH_STORIES`` entries) get their own drivers here for the same
reason: a read-only-pin refusal reached before any DML, and a milestone
history run-through.

Most graph stories read only, and their canned port refuses DML outright so a
story that quietly acquired a write is caught here. The composition stories
(`m-snapshot-read-017`/`-018`/`-019`/`-020`/`-023`/`-024`/`-025`) and the
read-your-own-writes story (`m-unit-work-029`) are the exception by
construction: what they demonstrate is a materialized view standing across a
COMMITTED write, or a find inside the write's own unit of work, so they need a
port that opens a transaction and takes the DML (:class:`_WritingCannedPort`).

Running the bodies here is also what makes a scenario case's per-step finds
reachable for the Object Query no-drift guard `m-api-conformance` requires: those
queries are locals inside a story body rather than entries in
``test_object_query_no_drift.BUILDERS``, so they are canonicalized where the body
runs (:class:`_RecordingDatabase`).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any, cast

import pytest

from _support.corpus import case_document, compare_binds
from _support.document_reads import fold_mapping_rows
from _support.query_probes import canonical_document
from parallax.conformance import case_format, graph_stories
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Order, OrderStatus
from parallax.core import DomainModel, ObjectQuery
from parallax.core.base import INFINITY
from parallax.core.db_port import Bind, DbPort, Row
from parallax.core.entity import UnloadedRelationshipError
from parallax.core.unit_work import Clock, Concurrency
from parallax.snapshot import is_view_loaded
from parallax.snapshot.handle import (
    Database,
    Snapshot,
    Transaction,
    TransactionTimePinReadOnlyError,
)

_ORDER_ROW: Row = {
    "id": 1,
    "name": "Ada",
    "sku": "SKU-1",
    "qty": 2,
    "price": Decimal("9.99"),
    "active": True,
    "ordered_on": dt.date(2024, 1, 2),
}

_ORDER_ITEM_ROW: Row = {
    "id": 11,
    "order_id": 1,
    "sku": "SKU-1",
    "quantity": 2,
    "shipped_on": None,
}

# Order 3 — the fixture row the loaded-empty / unloaded pair is rooted on, which
# owns no line items until each story's own insert lands.
_ORDER_3_ROW: Row = {
    "id": 3,
    "name": "ada",
    "sku": "A-300",
    "qty": 15,
    "price": Decimal("30.25"),
    "active": False,
    "ordered_on": dt.date(2024, 3, 15),
}

_ORDER_ITEM_12_ROW: Row = {
    "id": 12,
    "order_id": 1,
    "sku": "SKU-12",
    "quantity": 1,
    "shipped_on": None,
}

# Order 1's four statuses: one ORDER-level (null `order_item_id`, the branch the
# multi-hop walk drops) beside three ITEM-level ones, two of which reach item 11.
_ORDER_1_STATUS_ROWS: list[Row] = [
    {"id": 101, "order_id": 1, "order_item_id": None, "code": "NEW"},
    {"id": 201, "order_id": 1, "order_item_id": 11, "code": "PICKED"},
    {"id": 202, "order_id": 1, "order_item_id": 11, "code": "PACKED"},
    {"id": 203, "order_id": 1, "order_item_id": 12, "code": "PICKED"},
]

# Location 100 and its owning Customer 1, both carrying an `address` document —
# the value-object composition arm. The customer's two `phones` are queued in the
# order the read decodes them, which is the order the surviving view must answer
# after the story's write rewrites the document with them swapped.
_LOCATION_100_ROW: Row = {
    "id": 100,
    "customer_id": 1,
    "label": "HQ",
    "address": {"street": "1 Harbour Way", "city": "Oslo"},
}

_CUSTOMER_1_ROW: Row = {
    "id": 1,
    "name": "Ada",
    "address": {
        "street": "1 Park Ave",
        "city": "Oslo",
        "phones": [
            {"type": "home", "number": "555-1234"},
            {"type": "work", "number": "555-9999"},
        ],
    },
}

# Order 6 and its single line item — the rows the fresh-row story's own insert
# creates and its find then materializes a graph over.
_ORDER_6_ROW: Row = {
    "id": 6,
    "name": "Hopper",
    "sku": "F-600",
    "qty": 2,
    "price": Decimal("60.00"),
    "active": True,
    "ordered_on": dt.date(2024, 7, 7),
}

_ORDER_ITEM_61_ROW: Row = {
    "id": 61,
    "order_id": 6,
    "sku": "C-610",
    "quantity": 4,
    "shipped_on": None,
}

_ORDER_ITEM_INSERT = "insert into order_item(id, order_id, sku, quantity) values (%s, %s, %s, %s)"

# Policy 2 and its single coverage at the pin the rectangle-split story takes —
# one rectangle open on both axes, which is what a bounded `updateUntil` splits
# into head / middle / tail.
_POLICY_2_ROW: Row = {
    "id": 2,
    "name": "Home",
    "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "thru_z": INFINITY,
    "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "out_z": INFINITY,
}

_COVERAGE_20_ROW: Row = {
    "id": 20,
    "policy_id": 2,
    "amount": Decimal("300.00"),
    "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "thru_z": INFINITY,
    "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "out_z": INFINITY,
}

# Balance 1's SUPERSEDED milestone — the row a finite Transaction-Time pin at
# 2024-03-01 selects, closed at 2024-06-01 by the milestone that replaced it.
_BALANCE_MILESTONE_ROW: Row = {
    "bal_id": 1,
    "acct_num": "A",
    "val": Decimal("100.00"),
    "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "out_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
}


class _CannedPort:
    """A fake ``m-db-port`` answering reads from a fixed queue (empty by
    default — an empty root level short-circuits every child level, which is
    all a run-through proof needs).

    A queued row is LOGICAL — its own members, keyed by column — and is folded
    into the adjacent presence/value projection the compiled read asked for, so
    a value-object-bearing entity can be canned here as the document it holds
    rather than as the widened cell pair its statement selects."""

    def __init__(self, responses: Sequence[list[Row]] = ()) -> None:
        self._responses = list(responses)
        self.writes: list[tuple[str, list[Bind]]] = []

    def execute(
        self, sql: str, binds: Sequence[Bind], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        return fold_mapping_rows(self._responses.pop(0), document_reads) if self._responses else []

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:  # pragma: no cover
        raise AssertionError("a read-only graph story issues no DML")

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:  # pragma: no cover
        raise AssertionError("a read-only graph story opens no transaction")


class _TransactingCannedPort(_CannedPort):
    """The read-only-pin proof is the one story here that opens a transaction —
    its refusal is a write verb's. ``execute_write`` still refuses, which is the
    guard that matters: the verb rejects the value before anything is buffered."""

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        return body(self)


class _WritingCannedPort(_TransactingCannedPort):
    """The port the composition stories need: their whole subject is a view
    standing across a write that really commits, so the DML is part of the story
    rather than a leak, and it is recorded for the caller to read."""

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        self.writes.append((sql, list(binds)))
        return 1


# The stories whose body commits DML (`m-snapshot-read-017`/`-018`/`-019`/`-020`/
# `-023`/`-024`/`-025` and `m-unit-work-029`): the composition arm, where what is
# demonstrated is the materialized view standing across a persisting write — and,
# for the read-your-own-writes story, a dependent find inside the write's own unit
# of work.
_WRITING_STORIES: frozenset[Callable[..., Any]] = frozenset(
    {
        graph_stories.a_write_keeps_a_loaded_to_one_view,
        graph_stories.a_write_keeps_a_loaded_empty_relationship_view,
        graph_stories.a_write_keeps_an_unloaded_relationship_absent,
        graph_stories.a_delete_keeps_a_loaded_relationship_view,
        graph_stories.a_write_keeps_a_loaded_value_object_document,
        graph_stories.a_write_keeps_a_view_over_freshly_inserted_rows,
        graph_stories.a_rectangle_split_keeps_a_loaded_relationship_view,
        graph_stories.a_grouped_read_observes_its_own_relationship_writes,
    }
)


_CASES = {case.case_id: case for case in case_format.load_cases()}

# Each story by the callable that IS it. A test naming the behaviour it drives
# names the run function, so this is the lookup every one of them wants, and
# keying on the function rather than the case id keeps the reference resolvable
# by the type checker.
_STORIES_BY_RUN = {story.run: story for story in graph_stories.GRAPH_STORIES}
assert len(_STORIES_BY_RUN) == len(graph_stories.GRAPH_STORIES), "one story per run function"


def _golden_write_binds(case_id: str) -> list[list[object]]:
    """The DML binds the case's own write step declares, statement for statement.

    The corpus owns the SQL text and both wire executors grade it, so what a
    story owes here is that the PUBLIC surface reached the wire with the same
    values in the same order — a write that no-opped, addressed another row, or
    chained a different rectangle fails, without this file restating a statement
    the API suite is not the grader of (`m-api-conformance` "Golden SQL text is
    out of scope").
    """
    steps = cast("list[dict[str, Any]]", case_document(_CASES[case_id])["when"]["scenario"])
    writes = [step for step in steps if "write" in step]
    assert writes, case_id
    return [
        cast("list[object]", statement.get("binds", []))
        for step in writes
        for statement in cast("list[dict[str, Any]]", step["statements"])
    ]


def _assert_wire_binds(case_id: str, port: _CannedPort) -> None:
    observed = [binds for _sql, binds in port.writes]
    expected = _golden_write_binds(case_id)
    assert len(observed) == len(expected), (case_id, port.writes)
    for emitted, golden in zip(observed, expected, strict=True):
        compare_binds(emitted, golden)


def _port_for(run: Callable[[Database], Any], responses: Sequence[list[Row]]) -> _CannedPort:
    return (_WritingCannedPort if run in _WRITING_STORIES else _CannedPort)(responses)


def _connect(story: graph_stories.GraphStory, port: _CannedPort) -> Database:
    # A story's clock is a FACTORY precisely so this consumer drives its own
    # script rather than one `test_story_run.py` already advanced.
    clock = story.clock() if story.clock is not None else None
    return Database.connect(port, MODELS[story.model], clock=clock)


def _db(story: graph_stories.GraphStory, responses: Sequence[list[Row]] = ()) -> Database:
    return _connect(story, _port_for(story.run, responses))


def _responses_for(run: Callable[[Database], Any]) -> list[list[Row]]:
    """Canned reads for the stories whose bodies dereference a result — every
    other story's empty root level legally short-circuits the rest.

    The no-writeback story reads twice (the find and the re-read); the two
    SINGLE-HOP edited-copy stories once each (their include level short-circuits
    on the empty tail), where the edit chain needs a child to carry across its
    hops and is counted with the composite stories below. The to-one composition
    story reads four times: its own root and include levels, the transaction's
    observing find, and the re-read that shows where the write IS observable.

    The loaded-empty composition story reads twice — its root level answers
    order 3 and its `items` level answers nothing, which is what makes the view
    loaded and EMPTY rather than short-circuited — and its unloaded sibling once,
    declaring no include at all.

    The destructive and rectangle-split stories read four times each: their own
    root and include levels, the transaction's observing find, and the read-back
    — which answers nothing, because the canned port is a stub rather than a
    store and only the real-database driver can say what the write left behind.

    The composite stories read for their own levels, their transaction's
    observing find, and their read-back: the edit chain twice (root and `items`,
    so the chain has a child to carry across its hops, and no write at all), the
    value-object and fresh-row stories four times each — their own levels, the
    row the write settles against, and a read-back that answers nothing here
    because the canned port is a stub rather than a store — and the multi-hop
    story three times, one per level of the `statuses.orderItem` path.

    The read-your-own-writes story reads four times, two levels for each of the
    two finds its own `uow` group issues. Its second find answers the SAME rows
    here as its first: a canned port is a stub rather than a store, so what the
    dependent find observes of the group's own writes is the real-database
    driver's to say.
    """
    if run is graph_stories.mutation_has_no_writeback:
        return [[_ORDER_ROW], [_ORDER_ROW]]
    if run is graph_stories.an_edit_chain_keeps_a_loaded_relationship_view:
        return [[_ORDER_ROW], [_ORDER_ITEM_ROW]]
    if run is graph_stories.a_write_keeps_a_loaded_value_object_document:
        return [[_LOCATION_100_ROW], [_CUSTOMER_1_ROW], [_CUSTOMER_1_ROW], []]
    if run is graph_stories.a_write_keeps_a_view_over_freshly_inserted_rows:
        return [[_ORDER_6_ROW], [_ORDER_ITEM_61_ROW], [_ORDER_ITEM_61_ROW], []]
    if run is graph_stories.a_multi_hop_access_drops_its_null_branches:
        return [[_ORDER_ROW], _ORDER_1_STATUS_ROWS, [_ORDER_ITEM_ROW, _ORDER_ITEM_12_ROW]]
    if run is graph_stories.a_write_keeps_a_loaded_to_one_view:
        return [[_ORDER_ITEM_ROW], [_ORDER_ROW], [_ORDER_ROW], [_ORDER_ROW]]
    if run is graph_stories.a_write_keeps_a_loaded_empty_relationship_view:
        return [[_ORDER_3_ROW], []]
    if run is graph_stories.a_write_keeps_an_unloaded_relationship_absent:
        return [[_ORDER_3_ROW]]
    if run is graph_stories.a_delete_keeps_a_loaded_relationship_view:
        return [[_ORDER_ROW], [_ORDER_ITEM_ROW], [_ORDER_ITEM_ROW], []]
    if run is graph_stories.a_rectangle_split_keeps_a_loaded_relationship_view:
        return [[_POLICY_2_ROW], [_COVERAGE_20_ROW], [_COVERAGE_20_ROW], []]
    if run is graph_stories.a_grouped_read_observes_its_own_relationship_writes:
        items = [_ORDER_ITEM_12_ROW, _ORDER_ITEM_ROW]
        return [[_ORDER_ROW], items, [_ORDER_ROW], items]
    if run in (
        graph_stories.an_edited_copy_keeps_its_source_nodes_views,
        graph_stories.an_edit_keeps_a_loaded_relationship_view,
    ):
        return [[_ORDER_ROW]]
    return []


@pytest.mark.parametrize(
    "story", graph_stories.GRAPH_STORIES, ids=[s.case_id for s in graph_stories.GRAPH_STORIES]
)
def test_every_graph_story_runs_through_the_shipped_surface(
    story: graph_stories.GraphStory,
) -> None:
    story.run(_db(story, _responses_for(story.run)))


def test_the_to_one_composition_story_keeps_the_view_across_the_committed_write() -> None:
    # The in-memory half of `m-snapshot-read-017`, which needs no database: the
    # write reaches the wire (recorded below) and the already-materialized
    # `order` view still answers the SAME object holding the value the read
    # produced, never the one the write buffered.
    story = _STORIES_BY_RUN[graph_stories.a_write_keeps_a_loaded_to_one_view]
    port = _WritingCannedPort(_responses_for(story.run))
    snapshot, loaded_order, _reread = story.run(Database.connect(port, MODELS[story.model]))
    assert [sql for sql, _binds in port.writes] == ["update orders set name = %s where id = %s"]
    assert snapshot.result().order is loaded_order
    assert loaded_order.name == "Ada"


def test_the_loaded_empty_composition_story_keeps_an_empty_view_across_its_insert() -> None:
    # The in-memory half of `m-snapshot-read-018`. The insert really reaches the
    # wire — recorded below, and asserted because a story whose transaction did
    # nothing would satisfy every claim about the view — and `items` still
    # answers the empty tuple the include level fetched, LOADED rather than
    # absent.
    story = _STORIES_BY_RUN[graph_stories.a_write_keeps_a_loaded_empty_relationship_view]
    port = _WritingCannedPort(_responses_for(story.run))
    snapshot = story.run(Database.connect(port, MODELS[story.model]))
    order = snapshot.result()
    assert [(sql, binds) for sql, binds in port.writes] == [
        (_ORDER_ITEM_INSERT, [31, 3, "C-300", 7])
    ]
    assert is_view_loaded(order, Order.items) is True
    assert order.items == ()


def test_the_unloaded_composition_story_keeps_an_absent_view_across_its_insert() -> None:
    # The in-memory half of `m-snapshot-read-019`, whose api-conformance lane has
    # no corpus executor at all: the SAME insert against the SAME order as its
    # loaded-empty sibling, and `items` still absent rather than empty — the two
    # halves of the distinction, differing only in the include the read declared.
    story = _STORIES_BY_RUN[graph_stories.a_write_keeps_an_unloaded_relationship_absent]
    port = _WritingCannedPort(_responses_for(story.run))
    order = story.run(Database.connect(port, MODELS[story.model])).result()
    assert [(sql, binds) for sql, binds in port.writes] == [
        (_ORDER_ITEM_INSERT, [31, 3, "C-300", 7])
    ]
    assert is_view_loaded(order, Order.items) is False
    with pytest.raises(UnloadedRelationshipError, match="items"):
        order.items  # noqa: B018 - the access itself is the assertion


def test_the_destructive_composition_story_keeps_the_destroyed_row_in_its_view() -> None:
    # The in-memory half of `m-snapshot-read-020`: the DELETE reaches the wire
    # (recorded below), and the already-materialized `items` view still answers
    # the destroyed row's own node — the SAME object, not an equal-valued
    # rebuild, which is the half a contents comparison cannot see.
    story = _STORIES_BY_RUN[graph_stories.a_delete_keeps_a_loaded_relationship_view]
    port = _WritingCannedPort(_responses_for(story.run))
    snapshot, loaded_items, _committed, _reread = story.run(_connect(story, port))
    _assert_wire_binds(story.case_id, port)
    assert [item.id for item in loaded_items] == [11]
    assert snapshot.result().items[0] is loaded_items[0]


def test_the_rectangle_split_story_keeps_the_pinned_rectangle_in_its_view() -> None:
    # The in-memory half of `m-snapshot-read-025`: the split reaches the wire as
    # the close plus the three chained rectangles the case's own goldens bind —
    # the story's scripted clock is what makes those binds reachable at all —
    # and the pinned `coverages` view still answers the rectangle its own read
    # selected, by identity.
    story = _STORIES_BY_RUN[graph_stories.a_rectangle_split_keeps_a_loaded_relationship_view]
    port = _WritingCannedPort(_responses_for(story.run))
    snapshot, loaded_coverages, _committed, _reread = story.run(_connect(story, port))
    _assert_wire_binds(story.case_id, port)
    assert [(c.id, c.amount) for c in loaded_coverages] == [(20, Decimal("300.00"))]
    assert snapshot.result().coverages[0] is loaded_coverages[0]


def test_the_edit_chain_story_keeps_the_same_children_at_every_hop() -> None:
    # The in-memory half of `m-snapshot-read-022`, which needs no database: each
    # hop of the chain derives a COPY carrying the source's own loaded children,
    # so the change-free edit of an edited copy answers the same objects the read
    # materialized — and the source keeps its own name while both copies carry
    # the authored one.
    story = _STORIES_BY_RUN[graph_stories.an_edit_chain_keeps_a_loaded_relationship_view]
    snapshot, renamed, restated = story.run(_db(story, _responses_for(story.run)))
    order = snapshot.result()
    assert (order.name, renamed.name, restated.name) == ("Ada", "Mutant", "Mutant")
    assert restated.items[0] is order.items[0]
    assert renamed.items[0] is order.items[0]


def test_the_value_object_composition_story_keeps_its_document_in_read_order() -> None:
    # The in-memory half of `m-snapshot-read-023`: the rewritten document reaches
    # the wire with the case's own binds (a changed city and the phones swapped),
    # and the already-materialized `customer` view still answers the document the
    # read decoded, ELEMENT ORDER included — the half a multiset comparison could
    # not tell apart.
    story = _STORIES_BY_RUN[graph_stories.a_write_keeps_a_loaded_value_object_document]
    port = _WritingCannedPort(_responses_for(story.run))
    snapshot, loaded_customer, _committed, _reread = story.run(_connect(story, port))
    _assert_wire_binds(story.case_id, port)
    assert loaded_customer.address.city == "Oslo"
    assert [phone.type for phone in loaded_customer.address.phones] == ["home", "work"]
    assert snapshot.result().customer is loaded_customer


def test_the_fresh_row_composition_story_keeps_the_inserted_rows_view() -> None:
    # The in-memory half of `m-snapshot-read-024`: both units of work reach the
    # wire with the case's own binds — the inserts that made the rows and the
    # update that rewrote one — and the view materialized in between still
    # answers the sku the read produced, by identity.
    story = _STORIES_BY_RUN[graph_stories.a_write_keeps_a_view_over_freshly_inserted_rows]
    port = _WritingCannedPort(_responses_for(story.run))
    _created, snapshot, loaded_items, _committed, _reread = story.run(_connect(story, port))
    _assert_wire_binds(story.case_id, port)
    assert [(item.id, item.sku) for item in loaded_items] == [(61, "C-610")]
    assert snapshot.result().items[0] is loaded_items[0]


def test_the_multi_hop_story_drops_its_null_branch_in_memory() -> None:
    # The in-memory half of `m-snapshot-read-026`, which needs no write at all:
    # every status carries a LOADED `order_item` view, the order-level one holds
    # null and contributes no terminal, and the two statuses reaching item 11
    # reach the SAME node rather than two equal ones.
    story = _STORIES_BY_RUN[graph_stories.a_multi_hop_access_drops_its_null_branches]
    order = story.run(_db(story, _responses_for(story.run))).result()
    assert all(is_view_loaded(status, OrderStatus.order_item) for status in order.statuses)
    reached = [status.order_item for status in order.statuses if status.order_item is not None]
    assert [item.id for item in reached] == [11, 11, 12]
    assert reached[0] is reached[1]


def test_the_read_your_own_writes_story_addresses_the_relationships_own_row() -> None:
    # The in-memory half of `m-unit-work-029`. What the dependent find observes of
    # the group's own writes needs a real store, so that half is
    # `test_story_run.py`'s; what needs no database is where the update's own
    # address came from — the item the RELATIONSHIP level published, never a read
    # of its own. Both writes reach the wire with the case's own binds, and the
    # `11` in the update's is that provenance stated as a value.
    story = _STORIES_BY_RUN[graph_stories.a_grouped_read_observes_its_own_relationship_writes]
    port = _WritingCannedPort(_responses_for(story.run))
    committed = story.run(_connect(story, port))
    _assert_wire_binds(story.case_id, port)
    before, _after = committed
    assert [item.id for item in before.result().items] == [12, 11]


class _RecordingTransaction:
    """A ``Transaction`` façade recording the Object Query each ``find`` receives.

    A GROUPED scenario's own find steps run inside the group's transaction, so
    the queries mirroring those steps are taken here rather than at the handle.
    Every other verb passes straight through, and a story whose case does NOT
    group its finds is never driven this way: there a ``tx.find`` is the
    resolving read a keyed write owes, counted by its write step and authored as
    no find step at all.
    """

    __slots__ = ("_queries", "_tx")

    def __init__(self, tx: Transaction, queries: list[ObjectQuery[Any, Any]]) -> None:
        self._tx = tx
        self._queries = queries

    def find[S](self, query: ObjectQuery[Any, S]) -> Snapshot[S]:
        self._queries.append(query)
        return self._tx.find(query)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._tx, name)


class _RecordingDatabase(Database):
    """The shipped handle, recording the Object Query each ``find`` receives.

    A scenario step's query is a local inside the story's own body, so reading it
    where the public surface takes it is the only way to compare it with the step
    it mirrors; a second, hand-written copy of the expression would be exactly
    the drift the comparison exists to catch. ``group_finds`` extends the same
    recording to the transaction a `uow`-grouped case's find steps run inside
    (:class:`_RecordingTransaction`); off, a ``tx.find`` stays untouched, because
    an ungrouped story's own is the framework's resolving read rather than an
    authored step.
    """

    __slots__ = ("_group_finds", "queries")

    def __init__(
        self,
        port: DbPort,
        model: DomainModel,
        *,
        clock: Clock | None = None,
        group_finds: bool = False,
    ) -> None:
        super().__init__(port, model, clock=clock)
        self.queries: list[ObjectQuery[Any, Any]] = []
        self._group_finds = group_finds

    def find[S](self, query: ObjectQuery[Any, S]) -> Snapshot[S]:
        self.queries.append(query)
        return super().find(query)

    def transact[T](
        self,
        fn: Callable[[Transaction], T],
        *,
        retries: int | None = None,
        concurrency: Concurrency | None = None,
        retry_optimistic_conflicts: bool | None = None,
    ) -> T:
        def recording(tx: Transaction) -> T:
            return fn(cast("Transaction", _RecordingTransaction(tx, self.queries)))

        body: Callable[[Transaction], T] = recording if self._group_finds else fn
        return super().transact(
            body,
            retries=retries,
            concurrency=concurrency,
            retry_optimistic_conflicts=retry_optimistic_conflicts,
        )


# The scenario stories whose case groups its own find steps, so the queries that
# mirror them are the transaction's rather than the handle's.
_GROUPED_FIND_STORIES = frozenset({"m-unit-work-029"})


def _recording_db(story: graph_stories.GraphStory) -> _RecordingDatabase:
    clock = story.clock() if story.clock is not None else None
    return _RecordingDatabase(
        _port_for(story.run, _responses_for(story.run)),
        MODELS[story.model],
        clock=clock,
        group_finds=story.case_id in _GROUPED_FIND_STORIES,
    )


def _scenario_object_queries(case_id: str) -> list[dict[str, Any]]:
    """The Object Query documents the case's own scenario finds author, in order."""
    steps = cast("list[dict[str, Any]]", case_document(_CASES[case_id])["when"]["scenario"])
    return [cast("dict[str, Any]", step["objectQuery"]) for step in steps if "objectQuery" in step]


# The scenario-shaped stories whose own `db.find` calls ARE their case's
# authored finds, one for one and in order.
_SCENARIO_FIND_STORIES = (
    "m-snapshot-read-009",
    "m-snapshot-read-010",
    "m-snapshot-read-015",
    "m-snapshot-read-016",
    "m-snapshot-read-018",
    "m-snapshot-read-019",
    "m-snapshot-read-020",
    "m-snapshot-read-022",
    "m-snapshot-read-023",
    "m-snapshot-read-024",
    "m-snapshot-read-025",
    "m-snapshot-read-026",
    "m-unit-work-029",
)

# The one scenario-shaped story whose find sequence is not its case's, and why.
_SCENARIO_FIND_EXCLUSIONS = {
    "m-snapshot-read-017": (
        "the story re-reads the written row to show where the write IS observable, and the "
        "case authors no find step for that read, so the two sequences differ by construction"
    )
}


@pytest.mark.parametrize("case_id", _SCENARIO_FIND_STORIES)
def test_a_scenario_story_builds_its_cases_object_queries(case_id: str) -> None:
    # The no-drift half `m-api-conformance` requires of a scenario's own finds:
    # each query the story builds must CANONICALIZE to the step it mirrors, not
    # merely answer the same rows at the same cost. A different predicate or a
    # different include shape over the same fixture is exactly what a row
    # comparison and a round-trip count cannot see — a read-back keyed on the
    # surviving item's own id returns the case's `expectRows` in one round trip
    # and still asks a different question from `orderId = 1`.
    story = next(s for s in graph_stories.GRAPH_STORIES if s.case_id == case_id)
    db = _recording_db(story)
    story.run(db)
    assert [canonical_document(query) for query in db.queries] == _scenario_object_queries(case_id)


def test_every_scenario_story_is_query_graded_or_reasoned() -> None:
    # A scenario case carries no top-level `when.objectQuery`, so it has no
    # `test_object_query_no_drift.BUILDERS` entry to fall back on: a story whose
    # ids reach neither side above would be silently unasserted, which is the
    # gap the partition requirement (`m-api-conformance` requirement 3) exists
    # to refuse everywhere else in this suite.
    graded, excluded = set(_SCENARIO_FIND_STORIES), set(_SCENARIO_FIND_EXCLUSIONS)
    assert graded.isdisjoint(excluded)
    assert graded | excluded == {
        story.case_id
        for story in graph_stories.GRAPH_STORIES
        if _CASES[story.case_id].shape == "scenario"
    }
    assert all(_SCENARIO_FIND_EXCLUSIONS.values())


def test_the_mutation_story_edits_in_memory_and_rereads_the_original() -> None:
    story = _STORIES_BY_RUN[graph_stories.mutation_has_no_writeback]
    mutated, reread = story.run(_db(story, _responses_for(story.run)))
    assert mutated.name == "Mutant"
    assert reread.result().name == "Ada"


def test_the_edited_copy_story_answers_the_source_nodes_unloaded_view() -> None:
    # The other in-memory semantic a wrap-through needs no database for: the
    # copy's view state IS the node's, so the un-included relationship reports
    # the same closed-world absence rather than a member the rebuild dropped.
    story = _STORIES_BY_RUN[graph_stories.an_edited_copy_keeps_its_source_nodes_views]
    snapshot, edited = story.run(_db(story, _responses_for(story.run)))
    assert (edited.name, snapshot.result().name) == ("Mutant", "Ada")
    assert is_view_loaded(edited, Order.statuses) is False
    with pytest.raises(UnloadedRelationshipError, match="statuses"):
        edited.statuses  # noqa: B018 - the access itself is the assertion


def test_the_supplemental_read_only_pin_story_refuses_at_the_verb() -> None:
    # SUPPLEMENTAL, like the history proof below: `m-identity-map-010` cannot be
    # a `GRAPH_STORIES` entry (see the story's own docstring), so its body needs
    # this Docker-free driver exactly like a registered story does. The canned
    # port's `execute_write` refuses outright, so reaching the raise at all is
    # also the proof that the verb rejects the value before buffering any DML.
    db = Database.connect(_TransactingCannedPort([[_BALANCE_MILESTONE_ROW]]), MODELS["balance"])
    with pytest.raises(TransactionTimePinReadOnlyError, match="transaction-time-pin-read-only"):
        graph_stories.a_finite_transaction_time_pinned_view_is_read_only(db)


def test_the_supplemental_history_story_runs_through_the_shipped_surface() -> None:
    # SUPPLEMENTAL: `history_of_a_concrete_temporal_node_
    # distinguishes_milestones` is deliberately NOT a `GRAPH_STORIES` entry (not
    # counted toward any case's exercised status — see `graph_stories`'s own
    # module docstring), but its body still needs a Docker-free driver exactly
    # like every registered story.
    db = Database.connect(_CannedPort(), MODELS["rate"])
    graph_stories.history_of_a_concrete_temporal_node_distinguishes_milestones(db)
