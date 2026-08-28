"""Projection merging: many per-row projections into one deterministic allocation order.

The merge is the internal read-only INDEXED interface all three consumers read
directly. Nothing is composed per node: :meth:`GraphMerge.layout`,
:meth:`GraphMerge.member_values`, :meth:`GraphMerge.issues`, and
:meth:`GraphMerge.view_layout` each hand back a reference to something the merge
or its sealed graph already holds, and :meth:`GraphMerge.view` reads one slot of
a row built once. The whole-graph answers are frozen where the walk ends for the
same reason: :attr:`GraphMerge.order`, :attr:`GraphMerge.roots`, and
:attr:`GraphMerge.invalid_roots` are tuples the merge retains rather than tuples
it builds per read. That is deliberate rather than incidental: the three consumers
read genuinely different subsets — the typed materializer never reads issues,
wire never reads issues, classification never reads member values — so any
composed per-node record would over-produce for every one of them.

What it retains is the logical-node-to-allocation mapping, the projection-to-
allocation mapping, the allocation order, the winning projection per logical
node, one fixed view row per logical node aligned to that node's merged view
layout, that layout itself by reference to the schema that owns it, and the
accumulated issues. It clones no member payload: a merged node's member row IS
the winning projection's row.

**Every one of those is sized by what the merge REACHES, never by the graph's own
projection array, and that is a bound rather than an economy.** A graph narrowed
to one root shares the arrays of the whole graph it was cut from — narrowing them
would cost the copy the narrowing exists to avoid — so a merge over one root of a
page is handed a projection index space as wide as the page. Anything here
allocated against that width would carry the page into a per-root cost, which is
exactly what `m-snapshot-read` gives to the page's own layer and to no other. The
projection-to-allocation mapping is therefore keyed rather than indexed, and a
projection nothing reached has no entry.

Two passes over one order. Pass 1 walks roots in first-encounter preorder,
assigning each logical node its zero-based allocation index and recording the
first projection to carry each view. Pass 2 is the caller's own
allocate/populate loop over the same order.

The preorder is fixed: roots in result order; each projection's relationship
views in accepted metadata declaration order; the broad view before that
relationship's narrowed views; narrowed views by their canonical derived key;
children in to-many result order. Nothing here sorts or unions to achieve it —
the execution's view schema fixed both a projection's slot order and its merged
node's before any row was converted, so a walk carries each written slot across
through a precomputed translation and reads the merged layout off the schema.

A repeated logical node reuses its first index, and every projection is walked
exactly once, so a projection reached late still contributes its own children at
its own position.

The whole member row and the resolved concrete Entity are first-projection-wins
with **no value comparison**: duplicate projections of one logical node are
value-identical by construction, because they resolve the same row at the same
pin. Relationship views are unioned — a view any projection loaded is loaded on
the merged node — with the first projection to carry a given view key deciding
that view's value. Issues are the one exception: every walked projection's are
accumulated, undeduplicated.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import EntityIdentity
from parallax.core.temporal_read import Pin
from parallax.snapshot.materialize._graph import (
    ABSENT,
    InvalidRootInput,
    SnapshotGraph,
    StoredDataIssueInput,
    graph_rows,
)
from parallax.snapshot.materialize._views import MergedViewLayout

__all__ = ["GraphMerge", "merge_graph_input"]


class GraphMerge:
    """One sealed graph's merge state: allocation order, roots, and winners.

    ``order`` position *is* the allocation index the caller allocates in, so
    nothing recomputes an index the writer already owns.
    """

    __slots__ = (
        "_invalid_roots",
        "_issues",
        "_logical",
        "_order",
        "_resolved",
        "_roots",
        "_rows",
        "_view_layouts",
        "_view_rows",
        "_winner",
    )

    def __init__(self, graph: SnapshotGraph) -> None:
        rows = graph_rows(graph)
        self._rows = rows
        self._winner: list[int] = []
        self._logical: dict[int, int] = {}
        self._resolved: dict[int, int] = {}
        self._issues: list[tuple[StoredDataIssueInput, ...]] = []
        self._view_layouts: list[MergedViewLayout] = []
        invalid_roots: list[InvalidRootInput] = []
        winners: list[list[object]] = []
        root_indices: list[int | None] = []
        for root in rows.roots:
            if isinstance(root, InvalidRootInput):
                invalid_roots.append(root)
                root_indices.append(None)
            else:
                self._walk(root, winners)
                root_indices.append(self._resolved[root])
        self._invalid_roots = tuple(invalid_roots)
        self._roots = tuple(root_indices)
        self._order = tuple(rows.layouts[winner].concrete for winner in self._winner)
        self._view_rows = [tuple(self._allocation(value) for value in row) for row in winners]

    # ----------------------------------------------------------------------- #
    # The whole-graph surface.                                                  #
    # ----------------------------------------------------------------------- #

    @property
    def order(self) -> tuple[EntityIdentity, ...]:
        """Each allocation index's own concrete Entity, in allocation order."""
        return self._order

    @property
    def roots(self) -> tuple[int | None, ...]:
        """Constructible allocation indices and invalid-root holes, in result order."""
        return self._roots

    @property
    def invalid_roots(self) -> tuple[InvalidRootInput, ...]:
        """Non-hydrating roots in result order."""
        return self._invalid_roots

    @property
    def has_issues(self) -> bool:
        """Whether conversion classified any issue in the reachable graph."""
        return bool(self._invalid_roots) or any(self._issues)

    @property
    def pin(self) -> Pin:
        """The whole-graph pin every projection of this graph was read at."""
        return self._rows.pin

    def by_allocation[T](self, by_projection: Mapping[int, T]) -> Mapping[int, T]:
        """``by_projection`` re-keyed from projection index to allocation index.

        Several projections may resolve to one logical node, so the first one
        walked wins — the same first-projection-wins rule the merged member row
        already follows, and sound for the same reason: duplicate projections of
        one logical node resolve the same row at the same pin. A projection no
        root reached contributes nothing, because nothing allocates it.
        """
        resolved: dict[int, T] = {}
        for projection, value in by_projection.items():
            index = self._resolved.get(projection)
            if index is not None:
                resolved.setdefault(index, value)
        return resolved

    # ----------------------------------------------------------------------- #
    # The per-node indexed reads.                                               #
    # ----------------------------------------------------------------------- #

    def layout(self, node: int) -> EntityLayout:
        """The member layout ``node``'s row is read against — the winning
        projection's own, and therefore its resolved concrete Entity's."""
        return self._rows.layouts[self._winner[node]]

    def member_values(self, node: int) -> tuple[object, ...]:
        """``node``'s merged member row, BY REFERENCE: the winning projection's
        own row, positional against :meth:`layout`."""
        return self._rows.member_rows[self._winner[node]]

    def issues(self, node: int) -> tuple[StoredDataIssueInput, ...]:
        """Every issue every projection of ``node`` carried, in walk order and
        without deduplication."""
        return self._issues[node]

    def view_layout(self, node: int) -> MergedViewLayout:
        """``node``'s relationship view slots, in canonical order."""
        return self._view_layouts[node]

    def view(self, node: int, slot: int) -> object:
        """``node``'s value at ``slot``: ``ABSENT`` for a view no projection
        loaded, ``None`` for loaded-null, an allocation index for a loaded
        to-one, and a tuple of them for a loaded to-many.

        Resolved into allocation indices once, when the row was built, so every
        consumer reading one slot twice is answered the identical value rather
        than two equal translations of it.
        """
        return self._view_rows[node][slot]

    # ----------------------------------------------------------------------- #
    # Pass 1.                                                                   #
    # ----------------------------------------------------------------------- #

    def _walk(self, projection: int, winners: list[list[object]]) -> None:
        if projection in self._resolved:
            return
        rows = self._rows
        logical = rows.logical_ids[projection]
        index = self._logical.get(logical)
        if index is None:
            index = len(self._winner)
            self._logical[logical] = index
            self._winner.append(projection)
            self._issues.append(rows.issues[projection])
            merged = rows.schema.merged(rows.layouts[projection])
            self._view_layouts.append(merged)
            winners.append([ABSENT] * len(merged.slots))
        else:
            carried = rows.issues[projection]
            if carried:
                self._issues[index] = (*self._issues[index], *carried)
        self._resolved[projection] = index
        values = rows.view_rows[projection]
        carried_views = winners[index]
        to_merged = self._view_layouts[index].to_merged[rows.sources[projection]]
        for slot, value in enumerate(values):
            merged_slot = to_merged[slot]
            if value is not ABSENT and carried_views[merged_slot] is ABSENT:
                carried_views[merged_slot] = value
        for value in values:
            for child in _edges(value):
                self._walk(child, winners)

    # ----------------------------------------------------------------------- #
    # Pass 1's epilogue: a walked projection's edges as allocation indices.     #
    # ----------------------------------------------------------------------- #

    def _allocation(self, value: object) -> object:
        """One view value's projection references as allocation indices."""
        if value is None or value is ABSENT:
            return value
        if isinstance(value, tuple):
            return tuple(self._resolved[child] for child in cast("tuple[int, ...]", value))
        return self._resolved[cast("int", value)]


def merge_graph_input(graph: SnapshotGraph) -> GraphMerge:
    """``graph``'s merge state — walked, and ready to allocate from.

    A SEALED graph only: a builder still accumulating has published no arrays to
    read, and merging one would answer questions about a graph that does not yet
    exist.
    """
    if type(graph) is not SnapshotGraph:
        raise TypeError(
            "a merge reads a sealed SnapshotGraph; an unsealed builder publishes no graph to read"
        )
    return GraphMerge(graph)


def _edges(value: object) -> tuple[int, ...]:
    """The projection indexes one relationship view value reaches, in order.

    The graph boundary already settled that every one is an exact in-range
    ``int``, so the shape is read rather than re-judged. An unloaded slot and a
    loaded null both reach nothing.
    """
    if value is None or value is ABSENT:
        return ()
    if isinstance(value, tuple):
        return cast("tuple[int, ...]", value)
    return (cast("int", value),)
