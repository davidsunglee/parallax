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
state — which need no database at all.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any

import pytest

from parallax.conformance import graph_stories
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Order
from parallax.core.db_port import Bind, DbPort, Row
from parallax.core.entity import UnloadedRelationshipError
from parallax.snapshot import is_view_loaded
from parallax.snapshot.handle import Database

_ORDER_ROW: Row = {
    "id": 1,
    "name": "Ada",
    "sku": "SKU-1",
    "qty": 2,
    "price": Decimal("9.99"),
    "active": True,
    "ordered_on": dt.date(2024, 1, 2),
}


class _CannedPort:
    """A fake ``m-db-port`` answering reads from a fixed queue (empty by
    default — an empty root level short-circuits every child level, which is
    all a run-through proof needs)."""

    def __init__(self, responses: Sequence[list[Row]] = ()) -> None:
        self._responses = list(responses)

    def execute(self, sql: str, binds: Sequence[Bind]) -> list[Row]:
        return self._responses.pop(0) if self._responses else []

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:  # pragma: no cover
        raise AssertionError("a graph story issues no DML")

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:  # pragma: no cover
        raise AssertionError("a graph story opens no transaction")


def _db(story: graph_stories.GraphStory, responses: Sequence[list[Row]] = ()) -> Database:
    return Database.connect(_CannedPort(responses), MODELS[story.model])


def _responses_for(run: Callable[[Database], Any]) -> list[list[Row]]:
    """The two edit stories are the ones whose bodies dereference a result, so
    they alone need a non-empty canned root row — twice for the no-writeback
    story (the find and the re-read), once for the edited-copy story."""
    if run is graph_stories.mutation_has_no_writeback:
        return [[_ORDER_ROW], [_ORDER_ROW]]
    if run is graph_stories.an_edited_copy_keeps_its_source_nodes_views:
        return [[_ORDER_ROW]]
    return []


@pytest.mark.parametrize(
    "story", graph_stories.GRAPH_STORIES, ids=[s.case_id for s in graph_stories.GRAPH_STORIES]
)
def test_every_graph_story_runs_through_the_shipped_surface(
    story: graph_stories.GraphStory,
) -> None:
    story.run(_db(story, _responses_for(story.run)))


def test_the_mutation_story_edits_in_memory_and_rereads_the_original() -> None:
    story = next(
        s for s in graph_stories.GRAPH_STORIES if s.run is graph_stories.mutation_has_no_writeback
    )
    mutated, reread = story.run(_db(story, _responses_for(story.run)))
    assert mutated.name == "Mutant"
    assert reread.result().name == "Ada"


def test_the_edited_copy_story_answers_the_source_nodes_unloaded_view() -> None:
    # The other in-memory semantic a wrap-through needs no database for: the
    # copy's view state IS the node's, so the un-included relationship reports
    # the same closed-world absence rather than a member the rebuild dropped.
    story = next(
        s
        for s in graph_stories.GRAPH_STORIES
        if s.run is graph_stories.an_edited_copy_keeps_its_source_nodes_views
    )
    snapshot, edited = story.run(_db(story, _responses_for(story.run)))
    assert (edited.name, snapshot.result().name) == ("Mutant", "Ada")
    assert is_view_loaded(edited, Order.statuses) is False
    with pytest.raises(UnloadedRelationshipError, match="statuses"):
        edited.statuses  # noqa: B018 - the access itself is the assertion


def test_the_supplemental_history_story_runs_through_the_shipped_surface() -> None:
    # SUPPLEMENTAL: `history_of_a_concrete_temporal_node_
    # distinguishes_milestones` is deliberately NOT a `GRAPH_STORIES` entry (not
    # counted toward any case's exercised status — see `graph_stories`'s own
    # module docstring), but its body still needs a Docker-free driver exactly
    # like every registered story.
    db = Database.connect(_CannedPort(), MODELS["rate"])
    graph_stories.history_of_a_concrete_temporal_node_distinguishes_milestones(db)
