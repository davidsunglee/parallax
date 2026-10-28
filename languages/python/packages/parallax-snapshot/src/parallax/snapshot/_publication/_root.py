from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from parallax.core._execution._unit_work.retain import ReadEvidence
from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    MemberIdentity,
    ValueObjectIdentity,
)
from parallax.core.read_delivery._page import (
    ABSENT,
    EntityState,
    InvalidRootInput,
    PageRows,
    PageSchedule,
    RootViewLayout,
    StoredDataIssueInput,
    exact_stored_equal,
    layout_order_key,
    reach_into,
    same_witness,
    state_for,
    stored_order_key,
)
from parallax.core.temporal_read import Pin
from parallax.core.write_plan import ObjectKey

__all__ = ["RootView", "SnapshotConsistencyError"]

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
    """One result root's borrowed reach over a sealed Page: its nodes, their
    Page-owned states, their carried relationship views, and their origins.

    A publication pass forms one and re-points it at each root in turn, so it is
    valid only inside the ``publish_root`` call that received it: kept beyond
    that call, it answers for whichever root the pass resolved last. Node 0 is
    the root, and the nodes are the finalized publication segment, which
    excludes an issue-bearing allocation the root's carried views never reach.
    """

    __slots__ = (
        "_defers_states",
        "_has_issues",
        "_invalid_root",
        "_layouts",
        "_origin_values",
        "_origins",
        "_pin",
        "_reached",
        "_resolved",
        "_rows",
        "_states",
        "_view_layouts",
        "_view_rows",
        "_winner",
    )

    def __init__(
        self,
        rows: PageRows,
        schedule: PageSchedule,
        *,
        origins: Mapping[int, ReadEvidence],
    ) -> None:
        self._rows = rows
        self._defers_states = schedule.defers_states
        self._origins = origins
        self._pin = rows.pin
        self._winner: list[int] = []
        self._resolved: dict[int, int] = {}
        self._layouts: list[EntityLayout] = []
        self._states: list[EntityState] = []
        self._view_layouts: list[RootViewLayout] = []
        self._view_rows: list[list[object] | tuple[()]] = []
        self._reached: list[int] = []
        self._origin_values: Sequence[ReadEvidence | None] = ()
        self._invalid_root: InvalidRootInput | None = None
        self._has_issues = False

    def __len__(self) -> int:
        """The nodes in this root's segment: none for an invalid root."""
        return len(self._winner)

    @property
    def invalid_root(self) -> InvalidRootInput | None:
        """The root's own findings when its stored primary key could not be read."""
        return self._invalid_root

    @property
    def has_issues(self) -> bool:
        """Whether any stored-data finding is published with this root."""
        return self._has_issues

    @property
    def pin(self) -> Pin:
        return self._pin

    @property
    def reached(self) -> Sequence[int]:
        """Every Page projection the root reached, including an arm its carried
        views discard: what releasing the Page storage it finished with reads."""
        return self._reached

    def layout(self, node: int) -> EntityLayout:
        """The member layout ``node``'s state is read against — the canonical
        occurrence's own, and therefore its resolved concrete Entity's."""
        return self._layouts[node]

    def member_values(self, node: int) -> tuple[object, ...]:
        """``node``'s Page-owned Entity State row by reference, positional
        against :meth:`layout`."""
        return self._states[node].member_row

    def issues(self, node: int) -> tuple[StoredDataIssueInput, ...]:
        """The findings from ``node``'s one Page-owned payload judgment."""
        return self._states[node].findings

    def view_layout(self, node: int) -> RootViewLayout:
        """``node``'s relationship view slots, in canonical order."""
        return self._view_layouts[node]

    def view(self, node: int, slot: int) -> object:
        """``node``'s value at ``slot``: ``ABSENT`` for a view no projection
        loaded, ``None`` for loaded-null, a node for a loaded to-one, and a
        tuple of them for a loaded to-many. A back-reference is a to-one: this
        root's reached node it names, or ``None`` when it names none this root
        reached among its targets.

        Resolved into nodes once, when the root was resolved, so every consumer
        reading one slot twice is answered the identical value rather than two
        equal translations of it.
        """
        return self._view_rows[node][slot]

    def origin(self, node: int) -> ReadEvidence | None:
        """The Read Evidence ``node``'s canonical projection carries, captured
        only for a root publishing no finding."""
        values = self._origin_values
        return values[node] if values else None

    def _resolve_root(self, position: int, pin: Pin) -> None:
        """Re-point this view at the root at ``position``, published at ``pin``.

        Every claim the root reaches is compared before any of its states is
        judged, so a projection conflict raises first, including one in an arm
        its carried views discard. Origins are read while the Page rows are
        still live, and only when the finalized segment publishes no finding.
        """
        rows = self._rows
        root = rows.roots[position]
        self._pin = pin
        self._winner.clear()
        self._resolved.clear()
        self._layouts.clear()
        self._states.clear()
        self._view_layouts.clear()
        self._view_rows.clear()
        self._origin_values = ()
        self._invalid_root = None
        reached = self._reached
        if rows.keys[root] is None and any(
            issue.code.startswith("stored-data-primary-key-") for issue in rows.issues[root]
        ):
            reached.clear()
            _notify(rows.observer, "occurrences_reached", 0)
            self._invalid_root = InvalidRootInput(position, state_for(rows, root).findings)
            self._has_issues = True
            return
        reach_into(rows, root, reached)
        judging = not self._defers_states
        logical_ids = rows.logical_ids
        if len(reached) == 1 or len({logical_ids[projection] for projection in reached}) == len(
            reached
        ):
            self._allocate_distinct(rows, reached, judging)
        else:
            self._allocate_claimed(rows, reached, judging)
        _notify(rows.observer, "occurrences_reached", len(reached))
        states = self._states
        if not judging:
            states.extend([state_for(rows, winner) for winner in self._winner])
        for state in states:
            if state.findings:
                if len(states) > 1:
                    self._realize()
                self._has_issues = any(published.findings for published in states)
                break
        else:
            self._has_issues = False
        if not self._has_issues:
            origins = self._origins
            self._origin_values = [origins.get(winner) for winner in self._winner]

    def _allocate_distinct(self, rows: PageRows, reached: Sequence[int], judging: bool) -> None:
        """Allocate one node per reached projection, each the only claimant of
        its logical occurrence, and then carry its view values into that node."""
        resolved = self._resolved
        for projection in reached:
            if judging:
                self._states.append(state_for(rows, projection))
            resolved[projection] = len(self._winner)
            self._winner.append(projection)
            self._allocated(rows, projection)
        view_rows = self._view_rows
        for projection in reached:
            index = resolved[projection]
            carried_views = view_rows[index]
            if not carried_views:
                continue
            view_layout = self._view_layouts[index]
            level = rows.sources[projection]
            to_root_view = view_layout.to_root_view[level]
            targets = view_layout.targets[level]
            for slot, value in enumerate(rows.view_rows[projection]):
                root_view_slot = to_root_view[slot]
                if value is not ABSENT and carried_views[root_view_slot] is ABSENT:
                    carried_views[root_view_slot] = self._allocation(value, targets[slot], None)

    # Called once per root by the pass's per-root resolution, which the Snapshot
    # materialization instruments measure; every split, including sharing the
    # view-carry loop with `_allocate_distinct`, adds a call to that loop.
    def _allocate_claimed(  # noqa: C901
        self, rows: PageRows, reached: Sequence[int], judging: bool
    ) -> None:
        """Allocate one node per logical occurrence the reached projections
        claim, won by its canonical claimant. Once every claimant resolves to
        its node, carry every claimant's view values into that node."""
        local_claims: dict[int, int | list[int]] = {}
        for projection in reached:
            logical = rows.logical_ids[projection]
            claimed = local_claims.get(logical)
            if claimed is None:
                local_claims[logical] = projection
                continue
            if isinstance(claimed, int):
                local_claims[logical] = [claimed, projection]
            else:
                claimed.append(projection)
        # Every witness comparison precedes any state judgment, so a conflict
        # raises before this root decodes a state.
        for logical, claimed in local_claims.items():
            if not isinstance(claimed, int):
                local_claims[logical] = self._canonical(claimed)
        table: dict[int, int] = {}
        for logical, canonical in local_claims.items():
            winner = cast("int", canonical)
            if judging:
                self._states.append(state_for(rows, winner))
            table[logical] = len(self._winner)
            self._winner.append(winner)
            self._allocated(rows, winner)
        resolved = self._resolved
        for projection in reached:
            resolved[projection] = table[rows.logical_ids[projection]]
        view_rows = self._view_rows
        for projection in reached:
            index = resolved[projection]
            carried_views = view_rows[index]
            if not carried_views:
                continue
            view_layout = self._view_layouts[index]
            level = rows.sources[projection]
            to_root_view = view_layout.to_root_view[level]
            targets = view_layout.targets[level]
            for slot, value in enumerate(rows.view_rows[projection]):
                root_view_slot = to_root_view[slot]
                if value is not ABSENT and carried_views[root_view_slot] is ABSENT:
                    carried_views[root_view_slot] = self._allocation(value, targets[slot], table)

    def _allocated(self, rows: PageRows, winner: int) -> None:
        layout = rows.layouts[winner]
        self._layouts.append(layout)
        view_layout = rows.schema.root_view_layout(layout)
        self._view_layouts.append(view_layout)
        self._view_rows.append(
            cast("list[object]", [ABSENT] * len(view_layout.slots)) if view_layout.slots else ()
        )

    def _realize(self) -> None:
        """Compact the segment to the nodes the root's carried views reach.

        An overwritten arm or a claimant's losing slot extends Page reach
        without being carried, so it is judged and compared but published
        nowhere; the realized nodes keep their allocation order, node 0 first.
        """
        view_rows = self._view_rows
        kept = _carried_reach(view_rows)
        if len(kept) == len(view_rows):
            return
        nodes = sorted(kept)
        renumbered = {node: index for index, node in enumerate(nodes)}
        self._winner[:] = [self._winner[node] for node in nodes]
        self._layouts[:] = [self._layouts[node] for node in nodes]
        self._states[:] = [self._states[node] for node in nodes]
        self._view_layouts[:] = [self._view_layouts[node] for node in nodes]
        self._view_rows[:] = [_renumbered(view_rows[node], renumbered) for node in nodes]

    def _canonical(self, occurrences: Sequence[int]) -> int:
        rows = self._rows
        if len(occurrences) == 2 and same_witness(rows, occurrences[0], occurrences[1]):
            _notify(rows.observer, "witnesses_compared", 1)
            rows.decoders.settle(occurrences[1])
            return occurrences[0]
        first, *remaining = occurrences
        if all(same_witness(rows, first, candidate) for candidate in remaining):
            _notify(rows.observer, "witnesses_compared", len(remaining))
            for candidate in remaining:
                rows.decoders.settle(candidate)
            return first
        canonical, *candidates = sorted(
            occurrences,
            key=lambda projection: (
                layout_order_key(rows.layouts[projection]),
                stored_order_key(rows.witnesses[projection]),
                rows.sources[projection],
                rows.source_ordinals[projection],
            ),
        )
        if candidates:
            _notify(rows.observer, "witnesses_compared", len(candidates))
        for candidate in candidates:
            if not same_witness(rows, canonical, candidate):
                raise self._conflict(canonical, candidate)
        raise AssertionError(
            "canonical witness ordering retained no disagreement"
        )  # pragma: no cover

    def _conflict(self, left: int, right: int) -> SnapshotConsistencyError:
        rows = self._rows
        left_layout = rows.layouts[left]
        right_layout = rows.layouts[right]
        left_values = cast("tuple[object, ...]", rows.witnesses[left])
        right_values = cast("tuple[object, ...]", rows.witnesses[right])
        left_by_member = dict(zip(left_layout.members, left_values, strict=True))
        right_by_member = dict(zip(right_layout.members, right_values, strict=True))
        differing = tuple(
            sorted(
                (
                    member
                    for member in {*left_layout.members, *right_layout.members}
                    if not exact_stored_equal(
                        left_by_member.get(member, ABSENT),
                        right_by_member.get(member, ABSENT),
                    )
                ),
                key=_member_order,
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

    def _allocation(
        self,
        value: object,
        targets: frozenset[EntityIdentity] | None,
        table: Mapping[int, int] | None,
    ) -> object:
        """Translate one view value against only this root's allocations:
        projections when ``targets`` is ``None``, otherwise a back-reference's
        logical claims, the first of which this root reached as one of
        ``targets`` wins. ``table`` is the claimed allocator's logical-to-node
        allocation, and ``None`` from the distinct allocator."""
        if value is None:
            return None
        if targets is None:
            resolved = self._resolved
            if isinstance(value, tuple):
                return tuple(resolved[child] for child in cast("tuple[int, ...]", value))
            return resolved[cast("int", value)]
        if not isinstance(value, tuple):
            return self._admitted(self._claimed_node(cast("int", value), table), targets)
        for logical in cast("tuple[int, ...]", value):
            node = self._admitted(self._claimed_node(logical, table), targets)
            if node is not None:
                return node
        return None

    def _claimed_node(self, logical: int, table: Mapping[int, int] | None) -> int | None:
        """The node this root allocated for ``logical``, if it reached any
        claimant of it.

        Without ``table`` the root's resolved projections are exactly its
        reach. A released logical's claim
        and its claimants' logical ids read ``0``, so a claimant only counts
        while its logical id still names ``logical``.
        """
        if table is not None:
            return table.get(logical)
        rows = self._rows
        resolved = self._resolved
        claim = rows.claims[logical]
        if isinstance(claim, int):
            node = resolved.get(claim)
            return node if node is not None and rows.logical_ids[claim] == logical else None
        for claimant in claim:
            node = resolved.get(claimant)
            if node is not None and rows.logical_ids[claimant] == logical:
                return node
        return None

    def _admitted(self, node: int | None, targets: frozenset[EntityIdentity]) -> int | None:
        return node if node is not None and self._layouts[node].concrete in targets else None


def _member_order(
    member: MemberIdentity,
) -> tuple[int, str, str, tuple[str, ...], str]:
    if isinstance(member, AttributeIdentity):
        return (0, *member.entity.sort_key, (member.name,), "")
    if isinstance(member, ValueObjectIdentity):
        return (1, *member.entity.sort_key, member.path, "")
    return (
        2,
        *member.value_object.entity.sort_key,
        member.value_object.path,
        member.name,
    )


def _carried_reach(view_rows: Sequence[Sequence[object]]) -> set[int]:
    """Every node node 0's carried views reach, itself included."""
    kept = {0}
    pending = [0]
    while pending:
        for value in view_rows[pending.pop()]:
            if type(value) is tuple:
                children = cast("tuple[int, ...]", value)
            elif value is None or value is ABSENT:
                continue
            else:
                children = (cast("int", value),)
            for child in children:
                if child not in kept:
                    kept.add(child)
                    pending.append(child)
    return kept


def _renumbered(row: Sequence[object], renumbered: Mapping[int, int]) -> list[object]:
    """One carried view row with every node it names renumbered."""
    return [
        tuple([renumbered[child] for child in cast("tuple[int, ...]", value)])
        if type(value) is tuple
        else value
        if value is None or value is ABSENT
        else renumbered[cast("int", value)]
        for value in row
    ]


def _notify(observer: object | None, name: str, *args: object) -> None:
    if observer is not None:
        callback = getattr(observer, name)
        callback(*args)
