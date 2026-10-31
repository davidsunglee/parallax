from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from parallax.core._execution._unit_work.retain import ReadEvidence
from parallax.core.entity import UNLOADED, GraphConstructionError
from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    MemberIdentity,
    RelationshipIdentity,
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
    entity_state,
    exact_stored_equal,
    layout_order_key,
    reach_into,
    same_stored_values,
    stored_order_key,
)
from parallax.core.temporal_read import Pin
from parallax.core.write_plan import ObjectKey

__all__ = ["RootView", "SnapshotConsistencyError"]

SNAPSHOT_FETCHED_ROW_CONFLICT = "snapshot-fetched-row-conflict"


class SnapshotConsistencyError(RuntimeError):
    """Two fetched rows one root reached under one row key hold unequal stored values."""

    __slots__ = ("code", "coordinates", "fetched_rows", "members", "object_key")

    def __init__(
        self,
        *,
        object_key: ObjectKey,
        coordinates: tuple[object, ...],
        members: tuple[MemberIdentity, ...],
        fetched_rows: tuple[tuple[int, int], tuple[int, int]],
    ) -> None:
        super().__init__(
            f"{object_key.entity.canonical}: fetched rows disagree "
            f"({SNAPSHOT_FETCHED_ROW_CONFLICT})"
        )
        self.code = SNAPSHOT_FETCHED_ROW_CONFLICT
        self.object_key = object_key
        self.coordinates = coordinates
        self.members = members
        self.fetched_rows = fetched_rows


class RootView:
    """One result root's borrowed reach over a sealed Page: its nodes, their
    Page-owned states, their carried relationship views, and their Read Evidence.

    A publication pass forms one and re-points it at each root in turn, so it is
    valid only inside the ``publish_root`` call that received it: kept beyond
    that call, it answers for whichever root the pass resolved last. Node 0 is
    the root, and the nodes are the finalized publication segment, which
    excludes an issue-bearing allocation the root's carried views never reach.

    A fetched row of a level the Page's schema proves records each row key at
    most once is its own logical row, judged when it was recorded, so its state
    is read where the Page holds it. A Page every level of which is proved
    allocates one node per reached fetched row without comparing anything.
    """

    __slots__ = (
        "_defers_states",
        "_every_level_proved",
        "_has_issues",
        "_invalid_root",
        "_layouts",
        "_pin",
        "_proved_levels",
        "_reached",
        "_read_evidence",
        "_read_evidence_values",
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
        read_evidence: Mapping[int, ReadEvidence],
    ) -> None:
        self._rows = rows
        self._defers_states = schedule.defers_states
        schema = rows.schema
        self._proved_levels = tuple(
            not schema.may_repeat_rows(level) for level in range(schema.level_count)
        )
        self._every_level_proved = all(self._proved_levels)
        self._read_evidence = read_evidence
        self._pin = rows.pin
        self._winner: list[int] = []
        self._resolved: dict[int, int] = {}
        self._layouts: list[EntityLayout] = []
        self._states: list[EntityState] = []
        self._view_layouts: list[RootViewLayout] = []
        self._view_rows: list[list[object] | tuple[()]] = []
        self._reached: list[int] = []
        self._read_evidence_values: Sequence[ReadEvidence | None] = ()
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
        """Every Page fetched row the root reached, including a relationship value
        its carried views discard: what releasing the Page storage it finished
        with reads."""
        return self._reached

    def layout(self, node: int) -> EntityLayout:
        """The member layout ``node``'s state is read against — the canonical
        fetched row's own, and therefore its resolved concrete Entity's."""
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

    def relationship_values(self, node: int) -> tuple[object, ...]:
        """``node``'s broad relationship values in its layout's relationship
        order: ``UNLOADED`` where no fetched row loaded the direction, otherwise
        the carried view value :meth:`view` answers.

        A narrowed view presents a direction the broad view already carries, so
        only broad slots reach a position here. A view schema may lay out a slot
        for a direction this concrete does not declare — an unguarded level
        attaches its slot to every concrete it can reach — so laying one out is
        tolerated, and carrying a value in one is refused, since dropping it
        would lose a view the read loaded.
        """
        layout = self._layouts[node]
        width = len(layout.relationships)
        view_layout = self._view_layouts[node]
        broad = view_layout.broad_positions
        if not broad:
            return _unloaded(width)
        carried = self._view_rows[node]
        values: list[object] = [UNLOADED] * width
        for slot, position in broad:
            value = carried[slot]
            if value is ABSENT:
                continue
            if position is None:
                raise _undeclared_direction(
                    layout.concrete, view_layout.slots[slot].relationship, node
                )
            values[position] = value
        return tuple(values)

    def view(self, node: int, slot: int) -> object:
        """``node``'s value at ``slot``: ``ABSENT`` for a view no fetched row
        loaded, ``None`` for loaded-null, a node for a loaded to-one, and a
        tuple of them for a loaded to-many. A back-reference is a to-one: this
        root's reached node it names, or ``None`` when it names none this root
        reached among its targets.

        Resolved into nodes once, when the root was resolved, so every consumer
        reading one slot twice is answered the identical value rather than two
        equal translations of it.
        """
        return self._view_rows[node][slot]

    def read_evidence(self, node: int) -> ReadEvidence | None:
        """The Read Evidence ``node``'s canonical fetched row carries, captured
        only for a root publishing no finding."""
        values = self._read_evidence_values
        return values[node] if values else None

    def _resolve_root(self, position: int, pin: Pin) -> None:
        """Re-point this view at the root at ``position``, published at ``pin``.

        The stored values of every fetched row of one logical row the root
        reaches are compared before any of its deferred states is judged, so a
        fetched row conflict raises first, including one in a relationship value
        its carried views discard. Read Evidence is read while the Page rows are
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
        self._read_evidence_values = ()
        self._invalid_root = None
        reached = self._reached
        if rows.keys[root] is None and any(
            issue.code.startswith("stored-data-primary-key-") for issue in rows.issues[root]
        ):
            reached.clear()
            _notify(rows.observer, "fetched_rows_reached", 0)
            self._invalid_root = InvalidRootInput(position, entity_state(rows, root).findings)
            self._has_issues = True
            return
        reach_into(rows, root, reached)
        judging = not self._defers_states
        logical_rows = rows.logical_rows
        if (
            self._every_level_proved
            or len(reached) == 1
            or len({logical_rows[fetched_row] for fetched_row in reached}) == len(reached)
        ):
            self._allocate_per_fetched_row(rows, reached, judging)
        else:
            self._allocate_merged(rows, reached, judging)
        _notify(rows.observer, "fetched_rows_reached", len(reached))
        states = self._states
        if not judging:
            states.extend([self._state(rows, winner) for winner in self._winner])
        for state in states:
            if state.findings:
                if len(states) > 1:
                    self._realize()
                self._has_issues = any(published.findings for published in states)
                break
        else:
            self._has_issues = False
        if not self._has_issues:
            evidence = self._read_evidence
            self._read_evidence_values = [evidence.get(winner) for winner in self._winner]

    def _state(self, rows: PageRows, fetched_row: int) -> EntityState:
        """``fetched_row``'s Entity State: the one recording judged on a proved
        level, read where the Page holds it, otherwise its shared judgment."""
        if self._proved_levels[rows.sources[fetched_row]]:
            recorded = rows.judged_states.by_logical_row[rows.logical_rows[fetched_row]]
            if type(recorded) is EntityState:
                return recorded
        return entity_state(rows, fetched_row)

    def _allocate_per_fetched_row(
        self, rows: PageRows, reached: Sequence[int], judging: bool
    ) -> None:
        """Allocate one node per reached fetched row, each the only one of its
        logical row this root reaches, and then carry its view values into that
        node."""
        resolved = self._resolved
        winner = self._winner
        states = self._states
        proved = self._proved_levels
        sources = rows.sources
        logical_rows = rows.logical_rows
        recorded = rows.judged_states.by_logical_row
        for fetched_row in reached:
            if judging:
                state = (
                    recorded[logical_rows[fetched_row]] if proved[sources[fetched_row]] else None
                )
                states.append(
                    state if type(state) is EntityState else entity_state(rows, fetched_row)
                )
            resolved[fetched_row] = len(winner)
            winner.append(fetched_row)
            self._allocated(rows, fetched_row)
        view_rows = self._view_rows
        for fetched_row in reached:
            index = resolved[fetched_row]
            carried_views = view_rows[index]
            if not carried_views:
                continue
            view_layout = self._view_layouts[index]
            level = sources[fetched_row]
            to_root_view = view_layout.to_root_view[level]
            targets = view_layout.targets[level]
            for slot, value in enumerate(rows.view_rows[fetched_row]):
                root_view_slot = to_root_view[slot]
                if value is not ABSENT and carried_views[root_view_slot] is ABSENT:
                    carried_views[root_view_slot] = self._allocation(value, targets[slot], None)

    # Called once per root by the pass's per-root resolution, which the Snapshot
    # materialization instruments measure; every split, including sharing the
    # view-carry loop with `_allocate_per_fetched_row`, adds a call to that loop.
    def _allocate_merged(  # noqa: C901
        self, rows: PageRows, reached: Sequence[int], judging: bool
    ) -> None:
        """Allocate one node per logical row the reached fetched rows belong to,
        won by its canonical fetched row. Once every reached fetched row
        resolves to its node, carry each one's view values into that node."""
        local_rows: dict[int, int | list[int]] = {}
        for fetched_row in reached:
            logical = rows.logical_rows[fetched_row]
            merged = local_rows.get(logical)
            if merged is None:
                local_rows[logical] = fetched_row
                continue
            if isinstance(merged, int):
                local_rows[logical] = [merged, fetched_row]
            else:
                merged.append(fetched_row)
        # Every stored-values comparison precedes any deferred state judgment, so a
        # conflict raises before this root decodes a state.
        for logical, merged in local_rows.items():
            if not isinstance(merged, int):
                local_rows[logical] = self._canonical(merged)
        table: dict[int, int] = {}
        for logical, canonical in local_rows.items():
            winner = cast("int", canonical)
            if judging:
                self._states.append(self._state(rows, winner))
            table[logical] = len(self._winner)
            self._winner.append(winner)
            self._allocated(rows, winner)
        resolved = self._resolved
        for fetched_row in reached:
            resolved[fetched_row] = table[rows.logical_rows[fetched_row]]
        view_rows = self._view_rows
        for fetched_row in reached:
            index = resolved[fetched_row]
            carried_views = view_rows[index]
            if not carried_views:
                continue
            view_layout = self._view_layouts[index]
            level = rows.sources[fetched_row]
            to_root_view = view_layout.to_root_view[level]
            targets = view_layout.targets[level]
            for slot, value in enumerate(rows.view_rows[fetched_row]):
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

        An overwritten relationship value or a merged fetched row's losing slot
        extends Page reach without being carried, so it is judged and compared but published
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

    def _canonical(self, fetched_rows: Sequence[int]) -> int:
        rows = self._rows
        if len(fetched_rows) == 2 and same_stored_values(rows, fetched_rows[0], fetched_rows[1]):
            _notify(rows.observer, "stored_values_compared", 1)
            rows.decoders.settle(fetched_rows[1])
            return fetched_rows[0]
        first, *remaining = fetched_rows
        if all(same_stored_values(rows, first, candidate) for candidate in remaining):
            _notify(rows.observer, "stored_values_compared", len(remaining))
            for candidate in remaining:
                rows.decoders.settle(candidate)
            return first
        canonical, *candidates = sorted(
            fetched_rows,
            key=lambda fetched_row: (
                layout_order_key(rows.layouts[fetched_row]),
                stored_order_key(rows.stored_values[fetched_row]),
                rows.sources[fetched_row],
                rows.source_ordinals[fetched_row],
            ),
        )
        if candidates:
            _notify(rows.observer, "stored_values_compared", len(candidates))
        for candidate in candidates:
            if not same_stored_values(rows, canonical, candidate):
                raise self._conflict(canonical, candidate)
        raise AssertionError(
            "canonical stored-values ordering retained no disagreement"
        )  # pragma: no cover

    def _conflict(self, left: int, right: int) -> SnapshotConsistencyError:
        rows = self._rows
        left_layout = rows.layouts[left]
        right_layout = rows.layouts[right]
        left_values = cast("tuple[object, ...]", rows.stored_values[left])
        right_values = cast("tuple[object, ...]", rows.stored_values[right])
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
        row_key = rows.keys[left]
        primary_key = None if row_key is None else row_key.primary_key
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
            coordinates=() if row_key is None else row_key.coordinates,
            members=differing,
            fetched_rows=cast("tuple[tuple[int, int], tuple[int, int]]", positions),
        )

    def _allocation(
        self,
        value: object,
        targets: frozenset[EntityIdentity] | None,
        table: Mapping[int, int] | None,
    ) -> object:
        """Translate one view value against only this root's allocations:
        fetched rows when ``targets`` is ``None``, otherwise a back-reference's
        logical rows, the first of which this root reached as one of
        ``targets`` wins. ``table`` is the merged allocator's logical-to-node
        allocation, and ``None`` from the per-fetched-row allocator."""
        if value is None:
            return None
        if targets is None:
            resolved = self._resolved
            if isinstance(value, tuple):
                return tuple(resolved[child] for child in cast("tuple[int, ...]", value))
            return resolved[cast("int", value)]
        if not isinstance(value, tuple):
            return self._admitted(self._logical_row_node(cast("int", value), table), targets)
        for logical in cast("tuple[int, ...]", value):
            node = self._admitted(self._logical_row_node(logical, table), targets)
            if node is not None:
                return node
        return None

    def _logical_row_node(self, logical: int, table: Mapping[int, int] | None) -> int | None:
        """The node this root allocated for ``logical``, if it reached any
        fetched row of it.

        Without ``table`` the root's resolved fetched rows are exactly its
        reach. A released logical row's fetched rows and their logical rows
        read ``0``, so a fetched row only counts while its logical row still
        names ``logical``.
        """
        if table is not None:
            return table.get(logical)
        rows = self._rows
        resolved = self._resolved
        fetched = rows.fetched_rows_by_logical_row[logical]
        if isinstance(fetched, int):
            node = resolved.get(fetched)
            return node if node is not None and rows.logical_rows[fetched] == logical else None
        for fetched_row in fetched:
            node = resolved.get(fetched_row)
            if node is not None and rows.logical_rows[fetched_row] == logical:
                return node
        return None

    def _admitted(self, node: int | None, targets: frozenset[EntityIdentity]) -> int | None:
        return node if node is not None and self._layouts[node].concrete in targets else None


_UNLOADED_ROWS: dict[int, tuple[object, ...]] = {}


def _unloaded(width: int) -> tuple[object, ...]:
    """The all-unloaded relationship row of ``width`` positions, built once."""
    row = _UNLOADED_ROWS.get(width)
    if row is None:
        row = _UNLOADED_ROWS.setdefault(width, (UNLOADED,) * width)
    return row


def _undeclared_direction(
    entity: EntityIdentity, relationship: RelationshipIdentity, node: int
) -> GraphConstructionError:
    """The refusal for a loaded view naming a direction ``entity`` does not declare,
    in Entity Graph Construction's vocabulary because it is that graph's
    relationship row being refused."""
    return GraphConstructionError(
        code="entity-graph-invalid-member",
        message=(
            f"{entity.canonical} declares no relationship {relationship!r}, "
            "and a loaded view carries one"
        ),
        index=node,
        identity=relationship,
    )


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
