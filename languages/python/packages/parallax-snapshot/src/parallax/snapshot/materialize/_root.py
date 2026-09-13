"""One root's view over page-owned occurrences and shared Entity State.

The Root View is the internal read-only INDEXED interface all three consumers read
directly. Nothing is composed per node: :meth:`RootView.layout`,
:meth:`RootView.member_values`, :meth:`RootView.issues`, and
:meth:`RootView.view_layout` each hand back a reference to something the view
or its Page already holds, and :meth:`RootView.view` reads one slot of
a row built once. The whole-view answers are frozen where the walk ends for the
same reason: :attr:`RootView.order`, :attr:`RootView.roots`, and
:attr:`RootView.invalid_roots` are tuples the view retains rather than tuples
it builds per read. That is deliberate rather than incidental: the three consumers
read genuinely different subsets — the typed materializer never reads issues,
wire never reads issues, classification never reads member values — so any
composed per-node record would over-produce for every one of them.

What it retains is the logical-node-to-allocation mapping, the projection-to-
allocation mapping, the allocation order, the canonical occurrence per logical
node, one fixed view row per logical node aligned to that node's unioned view
layout, that layout itself by reference to the schema that owns it, and the
Page-owned Entity State. It clones no member payload: every Root View borrows
the judged state.

**Every one of those is sized by what the Root View REACHES, never by the Page's own
projection array, and that is a bound rather than an economy.** A view narrowed
to one root borrows the arrays of the whole Page — narrowing them would cost the
copy the view exists to avoid — so a Root View over one root of a
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
the execution's view schema fixed both a projection's slot order and its Root
View node's before any row was converted. A walk carries each written slot
across through a precomputed translation and reads the Root View layout off the
schema.

A repeated logical node reuses its first index, and every projection is walked
exactly once, so a projection reached late still contributes its own children at
its own position.

Before payload judgment, every occurrence claiming one logical key compares its
exact Payload Witness in canonical source order. Unequal witnesses refuse the
Snapshot with ``snapshot-projection-conflict``; equal witnesses decode once into
one Page-owned Entity State reused by every Root View. Relationship views are
unioned — a view any projection loaded is loaded on the resolved node — with the
first projection to carry a given view key deciding that view's value.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, MemberIdentity
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import ObjectKey
from parallax.snapshot.materialize._page import (
    ABSENT,
    EntityState,
    InvalidRootInput,
    Page,
    PageRows,
    StoredDataIssueInput,
    dedupe_issues,
    exact_stored_equal,
    page_rows,
)
from parallax.snapshot.materialize._views import RootViewLayout

__all__ = ["SNAPSHOT_PROJECTION_CONFLICT", "RootView", "SnapshotConsistencyError"]

SNAPSHOT_PROJECTION_CONFLICT = "snapshot-projection-conflict"


class SnapshotConsistencyError(RuntimeError):
    """Two occurrences claimed one logical key with unequal payloads."""

    __slots__ = ("code", "coordinates", "members", "object_key", "occurrences")

    def __init__(
        self,
        *,
        object_key: ObjectKey,
        coordinates: tuple[object, ...],
        members: tuple[MemberIdentity, ...],
        occurrences: tuple[tuple[int, int], tuple[int, int]],
    ) -> None:
        super().__init__(
            f"{object_key.entity.canonical}: projections disagree ({SNAPSHOT_PROJECTION_CONFLICT})"
        )
        self.code = SNAPSHOT_PROJECTION_CONFLICT
        self.object_key = object_key
        self.coordinates = coordinates
        self.members = members
        self.occurrences = occurrences


class RootView:
    """One root's view over a sealed Page: allocation order, roots, and states."""

    __slots__ = (
        "_invalid_roots",
        "_issues",
        "_order",
        "_pin",
        "_resolved",
        "_roots",
        "_rows",
        "_states",
        "_view_layouts",
        "_view_rows",
        "_winner",
    )

    def __init__(
        self, page: Page, root_position: int | None = None, *, pin: Pin | None = None
    ) -> None:
        rows = page_rows(page)
        self._rows = rows
        self._pin = rows.pin if pin is None else pin
        self._winner: list[int] = []
        self._resolved: dict[int, int] = {}
        self._issues: list[tuple[StoredDataIssueInput, ...]] = []
        self._states: list[EntityState] = []
        self._view_layouts: list[RootViewLayout] = []
        invalid_roots: list[InvalidRootInput] = []
        root_indices: list[int | None] = []
        root_entries = (
            tuple(enumerate(rows.roots))
            if root_position is None
            else ((root_position, rows.roots[root_position]),)
        )
        valid_roots: list[int] = []
        for ordinal, root in root_entries:
            if rows.keys[root] is None and any(
                issue.code.startswith("stored-data-primary-key-") for issue in rows.issues[root]
            ):
                state = self._decode(root)
                invalid_roots.append(InvalidRootInput(ordinal, state.findings))
                root_indices.append(None)
            else:
                valid_roots.append(root)
                root_indices.append(root)

        winners: list[list[object]] = []
        state_nodes: dict[int, int] = {}
        reached: set[int] = set()
        for root in valid_roots:
            reachable = self._reachable([root])
            reached.update(reachable)
            occurrences: dict[int, list[int]] = {}
            for projection in reachable:
                occurrences.setdefault(rows.logical_ids[projection], []).append(projection)
            root_states = {
                logical: self._state(tuple(group)) for logical, group in occurrences.items()
            }
            for projection in reachable:
                logical = rows.logical_ids[projection]
                winner, state = root_states[logical]
                index = state_nodes.get(id(state))
                if index is None:
                    index = len(self._winner)
                    state_nodes[id(state)] = index
                    self._winner.append(winner)
                    self._states.append(state)
                    self._issues.append(state.findings)
                    root_view_layout = rows.schema.root_view(rows.layouts[winner])
                    self._view_layouts.append(root_view_layout)
                    winners.append([ABSENT] * len(root_view_layout.slots))
                self._resolved[projection] = index
                values = rows.view_rows[projection]
                carried_views = winners[index]
                to_root_view = self._view_layouts[index].to_root_view[rows.sources[projection]]
                for slot, value in enumerate(values):
                    root_view_slot = to_root_view[slot]
                    if value is not ABSENT and carried_views[root_view_slot] is ABSENT:
                        carried_views[root_view_slot] = value

        self._invalid_roots = tuple(invalid_roots)
        self._roots = tuple(None if root is None else self._resolved[root] for root in root_indices)
        self._order = tuple(rows.layouts[winner].concrete for winner in self._winner)
        self._view_rows = [tuple(self._allocation(value) for value in row) for row in winners]
        _notify(rows.observer, "occurrences_reached", len(reached))

    # ----------------------------------------------------------------------- #
    # The whole-Root-View surface.                                                  #
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
        """The Page pin every occurrence in this Root View was read at."""
        return self._pin

    def by_allocation[T](self, by_projection: Mapping[int, T]) -> Mapping[int, T]:
        """``by_projection`` re-keyed from projection index to allocation index.

        Several projections may resolve to one logical node, so the first one
        walked supplies the value after their Payload Witnesses have proved the
        projections equivalent. Only reached projections are read from the input;
        a deferred evidence mapping therefore judges nothing outside this Root
        View, and a projection no root reached contributes nothing.
        """
        resolved: dict[int, T] = {}
        for projection, index in self._resolved.items():
            try:
                value = by_projection[projection]
            except KeyError:
                continue
            resolved.setdefault(index, value)
        return resolved

    # ----------------------------------------------------------------------- #
    # The per-node indexed reads.                                               #
    # ----------------------------------------------------------------------- #

    def layout(self, node: int) -> EntityLayout:
        """The member layout ``node``'s state is read against — the canonical
        occurrence's own, and therefore its resolved concrete Entity's."""
        return self._rows.layouts[self._winner[node]]

    def member_values(self, node: int) -> tuple[object, ...]:
        """``node``'s Page-owned Entity State row by reference, positional
        against :meth:`layout`."""
        return self._states[node].member_row

    def issues(self, node: int) -> tuple[StoredDataIssueInput, ...]:
        """The findings from ``node``'s one Page-owned payload judgment."""
        return self._issues[node]

    def view_layout(self, node: int) -> RootViewLayout:
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

    def _reachable(self, roots: list[int]) -> tuple[int, ...]:
        """Projection preorder reachable from this view's roots alone."""
        order: list[int] = []
        seen: set[int] = set()

        def walk(projection: int) -> None:
            if projection in seen:
                return
            seen.add(projection)
            order.append(projection)
            for value in self._rows.view_rows[projection]:
                for child in _edges(value):
                    walk(child)

        for root in roots:
            walk(root)
        return tuple(order)

    def _decode(self, projection: int) -> EntityState:
        rows = self._rows
        member_row, findings = rows.decoders[projection]()
        findings = dedupe_issues((*findings, *rows.issues[projection]))
        _notify(rows.observer, "states_decoded")
        return EntityState(member_row, findings)

    def _state(self, occurrences: tuple[int, ...]) -> tuple[int, EntityState]:
        rows = self._rows
        canonical, *candidates = sorted(
            occurrences,
            key=lambda projection: (rows.sources[projection], rows.source_ordinals[projection]),
        )
        key = rows.keys[canonical]
        if key is None:
            return canonical, self._decode(canonical)
        if candidates:
            _notify(rows.observer, "witnesses_compared", len(candidates))
        for candidate in candidates:
            if not _same_witness(rows, canonical, candidate):
                raise self._conflict(canonical, candidate)
        for stored_projection, state in rows.judged_states.get(key, ()):
            if _same_witness(rows, canonical, stored_projection):
                _notify(rows.observer, "states_shared")
                return canonical, state
        state = self._decode(canonical)
        rows.judged_states.setdefault(key, []).append((canonical, state))
        return canonical, state

    def _conflict(self, left: int, right: int) -> SnapshotConsistencyError:
        rows = self._rows
        left_layout = rows.layouts[left]
        right_layout = rows.layouts[right]
        left_values = cast("tuple[object, ...]", rows.witnesses[left])
        right_values = cast("tuple[object, ...]", rows.witnesses[right])
        left_by_member = dict(zip(left_layout.members, left_values, strict=True))
        right_by_member = dict(zip(right_layout.members, right_values, strict=True))
        differing = tuple(
            member
            for member in dict.fromkeys((*left_layout.members, *right_layout.members))
            if not exact_stored_equal(
                left_by_member.get(member, ABSENT), right_by_member.get(member, ABSENT)
            )
        )
        logical_key = rows.keys[left]
        primary_key = None if logical_key is None else logical_key.primary_key
        primary_values = (
            cast("tuple[object, ...]", primary_key)
            if len(left_layout.primary_key) > 1
            else (primary_key,)
        )
        key_values = tuple(
            (cast("AttributeIdentity", left_layout.members[position]).name, value)
            for position, value in zip(left_layout.primary_key, primary_values, strict=True)
        )
        positions = tuple(
            sorted(
                (
                    (rows.sources[left], rows.source_ordinals[left]),
                    (rows.sources[right], rows.source_ordinals[right]),
                )
            )
        )
        return SnapshotConsistencyError(
            object_key=ObjectKey(left_layout.concrete, key_values),
            coordinates=() if logical_key is None else logical_key.coordinates,
            members=differing,
            occurrences=cast("tuple[tuple[int, int], tuple[int, int]]", positions),
        )

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


def _notify(observer: object | None, name: str, *args: object) -> None:
    if observer is not None:
        callback = getattr(observer, name)
        callback(*args)


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


def _same_witness(rows: PageRows, left: int, right: int) -> bool:
    left_layout = rows.layouts[left]
    right_layout = rows.layouts[right]
    return (
        left_layout.concrete == right_layout.concrete
        and left_layout.members == right_layout.members
        and exact_stored_equal(rows.witnesses[left], rows.witnesses[right])
    )
