"""DB-free graph-story drivers — the checkpoint-3 R1 precedent applied to the
read-side stories.

Every ``GRAPH_STORIES`` function executes through the shipped in-process
pipeline (statement build → canonicalize → plan → compile → port →
materialize → wrap) against a canned fake ``m-db-port``, so the story bodies
contribute to the unit-lane coverage gate exactly as ``test_write_no_drift``
keeps ``stories.py`` in it (pure, Docker-free, in-process behaviour). The
golden grading — real Postgres, each case's own oracle — stays in
``test_story_run.py``; this driver pins that each story RUNS through the
public surface (an empty root level legally short-circuits every child
level), plus the mutation story's in-memory no-writeback semantics, which
need no database at all.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any

import pytest

from parallax.conformance import graph_stories, models
from parallax.core.db_port import Bind, DbPort, Row
from parallax.snapshot.handle import Database

pytestmark = [pytest.mark.unit, pytest.mark.api_conformance]

_MODELS = models.load_models()

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
    return Database.connect(_CannedPort(responses), _MODELS[story.model])


def _responses_for(run: Callable[[Database], Any]) -> list[list[Row]]:
    """The mutation story is the one whose body dereferences a result, so it
    alone needs a non-empty canned root row (twice: the find and the re-read)."""
    if run is graph_stories.mutation_has_no_writeback:
        return [[_ORDER_ROW], [_ORDER_ROW]]
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
