"""``parallax.snapshot._read_result`` enforcement scope (m-snapshot-read).

What a snapshot read HANDS BACK: the Snapshot Graph Input, and nothing about the
execution that produced it. A read publishes its transient Read activity through
the composition-supplied lifecycle seam while it runs (`m-execution-lifecycle`),
so a result carries no trace, no round-trip count, and no lifecycle record at
all — which is why nothing in this module names that vocabulary.

This scope alone carries the module tag's full grant, `m-execution-lifecycle`
included. The row-to-graph work sits in the separate, narrower
``parallax.snapshot.materialize`` scope, which turns driver rows into graph
inputs. The split is what keeps `m-sql` outside the closure of the grant every
consumer of the row-to-graph surface holds: a forbidden contract is the
complement of a closure, so a scope that must stay clear of SQL generation has
to be granted a scope that does not reach it.

Every lane's result sits here rather than beside the merge because a result is
what the read ANSWERS, while the row-to-graph vocabulary is what a materializer
consumes; keeping the answer in the wider scope is what leaves the narrower one
free of everything `m-execution-lifecycle` drags in, `m-sql` included.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from parallax.core.unit_work import SourceHint
from parallax.snapshot.materialize import (
    EMPTY_UNWIND,
    InvalidData,
    SnapshotGraphInput,
    UnwindTree,
)

__all__ = [
    "FindResult",
    "HistoryFindResult",
    "PublishedRow",
    "RowsResult",
]


@dataclass(frozen=True, slots=True)
class FindResult:
    """A single-graph find's Snapshot Graph Input.

    ``includes`` is the query's own Include Paths as the relationship views a
    wire unwind follows. The merged graph alone cannot supply them: it keeps
    every view any level loaded onto a node, so a back-reference would revisit
    its target forever. The executor knows the plan, so it hands the tree on.

    ``sources`` is the private Source Hint each observed projection's value will
    carry, keyed by that projection's own index in ``graph.nodes``. It travels
    with the graph input because only the executor holds the row and the
    projection at once: a materializer builds the value, but the row it came from
    is gone by then.
    """

    graph: SnapshotGraphInput
    includes: UnwindTree = EMPTY_UNWIND
    sources: Mapping[int, SourceHint] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class HistoryFindResult:
    """A milestone-set find's ordered per-milestone graph inputs.

    Each entry is a root-only graph pinned at its own milestone's from-instant
    (m-snapshot-read "The whole-graph pin"); a v1 milestone-set graph carries no
    includes (m-case-format).
    """

    graphs: tuple[SnapshotGraphInput, ...]


type PublishedRow = Mapping[str, object] | InvalidData[Mapping[str, object]]
"""One row-form result position: the transformed row itself, or the record a row
whose stored state contradicted the model publishes in its place.

The values lane's element type is the same union both public materializers
publish, one result position at a time — a row-form read has no graph, so its
own root IS the row."""


@dataclass(frozen=True, slots=True)
class RowsResult:
    """A row-form read's published rows.

    ``rows`` is every result position in result order, already eager, detached,
    and immutable, keyed as the read PROJECTED it — physical columns plus the
    synthetic ``familyVariant`` where the compiled read materializes one.
    """

    rows: tuple[PublishedRow, ...]
