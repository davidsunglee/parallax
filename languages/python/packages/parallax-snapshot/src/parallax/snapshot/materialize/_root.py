from __future__ import annotations

from array import array
from collections.abc import Mapping, Sequence
from typing import cast

from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    MemberIdentity,
    ValueObjectIdentity,
)
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import ObjectKey
from parallax.snapshot.materialize._page import (
    ABSENT,
    EntityState,
    InvalidRootInput,
    LogicalKey,
    Page,
    PageRows,
    StoredDataIssueInput,
    dedupe_issues,
    exact_stored_equal,
    judged_state,
    layout_order_key,
    page_rows,
    same_witness,
    stored_order_key,
)
from parallax.snapshot.materialize._views import RootViewLayout

__all__ = ["RootView", "SnapshotConsistencyError"]

SNAPSHOT_PROJECTION_CONFLICT = "snapshot-projection-conflict"
_UNPRIMED = object()


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
        "_layouts",
        "_order",
        "_pending_invalid",
        "_pin",
        "_primed_source",
        "_primed_values",
        "_releasable_rows",
        "_resolved",
        "_roots",
        "_rows",
        "_states",
        "_view_layouts",
        "_view_rows",
        "_winner",
    )

    def __init__(
        self,
        page: Page,
        root_position: int | None = None,
        *,
        pin: Pin | None = None,
        defer_states: bool = False,
    ) -> None:
        rows = page_rows(page)
        self._rows = rows
        self._pin = rows.pin if pin is None else pin
        self._primed_source: Mapping[int, object] | None = None
        self._primed_values: list[object] | None = None
        self._winner: list[int] = []
        self._resolved: dict[int, int] = {}
        self._layouts: list[EntityLayout] = []
        self._states: list[EntityState] = []
        self._view_layouts: list[RootViewLayout] = []
        if root_position is not None:
            root = rows.roots[root_position]
            if rows.keys[root] is None and any(
                issue.code.startswith("stored-data-primary-key-") for issue in rows.issues[root]
            ):
                invalid_entries: Sequence[tuple[int, int]] = ((root_position, root),)
                root_indices: Sequence[int | None] = (None,)
                valid_roots: Sequence[int] = ()
            else:
                invalid_entries = ()
                root_indices = (root,)
                valid_roots = (root,)
        else:
            invalid_entries = []
            root_indices = []
            valid_roots = []
            for ordinal, root in enumerate(rows.roots):
                if rows.keys[root] is None and any(
                    issue.code.startswith("stored-data-primary-key-") for issue in rows.issues[root]
                ):
                    invalid_entries.append((ordinal, root))
                    root_indices.append(None)
                else:
                    valid_roots.append(root)
                    root_indices.append(root)

        reached: set[int] | None = set() if len(valid_roots) > 1 else None
        single_reached: tuple[int, ...] = ()
        winners: list[list[object] | None] = []
        state_nodes: dict[int, int] | None = {} if len(valid_roots) > 1 else None
        for root in valid_roots:
            reachable = self._reachable([root])
            if reached is None:
                single_reached = reachable
            else:
                reached.update(reachable)
            if state_nodes is None and (
                len(reachable) == 1
                or len({rows.logical_ids[projection] for projection in reachable}) == len(reachable)
            ):
                for projection in reachable:
                    state = None if defer_states else self._state(projection)
                    index = len(self._winner)
                    self._winner.append(projection)
                    self._layouts.append(rows.layouts[projection])
                    if state is not None:
                        self._states.append(state)
                    root_view_layout = rows.schema.root_view(rows.layouts[projection])
                    self._view_layouts.append(root_view_layout)
                    carried_views: list[object] | None = (
                        [cast("object", ABSENT)] * len(root_view_layout.slots)
                        if root_view_layout.slots
                        else None
                    )
                    winners.append(carried_views)
                    self._resolved[projection] = index
                for projection in reachable:
                    index = self._resolved[projection]
                    values = rows.view_rows[projection]
                    carried_views = winners[index]
                    if carried_views is None:
                        continue
                    to_root_view = self._view_layouts[index].to_root_view[rows.sources[projection]]
                    for slot, value in enumerate(values):
                        root_view_slot = to_root_view[slot]
                        if value is not ABSENT and carried_views[root_view_slot] is ABSENT:
                            carried_views[root_view_slot] = value
                continue
            local_claims: dict[int, int | list[int]] = {}
            for projection in reachable:
                logical = rows.logical_ids[projection]
                claimed = local_claims.get(logical)
                if claimed is None:
                    local_claims[logical] = projection
                    continue
                if isinstance(claimed, int):
                    local_claims[logical] = [claimed, projection]
                else:
                    claimed.append(projection)
            canonical_by_logical = {
                logical: claimed if isinstance(claimed, int) else self._canonical(claimed)
                for logical, claimed in local_claims.items()
            }
            root_states: dict[int, tuple[int, int]] = {}
            for logical, winner in canonical_by_logical.items():
                state = None if defer_states else self._state(winner)
                index = None if state is None or state_nodes is None else state_nodes.get(id(state))
                if index is None:
                    index = len(self._winner)
                    if state is not None and state_nodes is not None:
                        state_nodes[id(state)] = index
                    self._winner.append(winner)
                    self._layouts.append(rows.layouts[winner])
                    if state is not None:
                        self._states.append(state)
                    root_view_layout = rows.schema.root_view(rows.layouts[winner])
                    self._view_layouts.append(root_view_layout)
                    carried_views = (
                        [cast("object", ABSENT)] * len(root_view_layout.slots)
                        if root_view_layout.slots
                        else None
                    )
                    winners.append(carried_views)
                root_states[logical] = winner, index
            for projection in reachable:
                logical = rows.logical_ids[projection]
                _winner, index = root_states[logical]
                self._resolved[projection] = index
                values = rows.view_rows[projection]
                carried_views = winners[index]
                if carried_views is None:
                    continue
                to_root_view = self._view_layouts[index].to_root_view[rows.sources[projection]]
                for slot, value in enumerate(values):
                    root_view_slot = to_root_view[slot]
                    if value is not ABSENT and carried_views[root_view_slot] is ABSENT:
                        carried_views[root_view_slot] = value

        self._pending_invalid = tuple(invalid_entries)
        self._invalid_roots = ()
        self._roots = tuple(None if root is None else self._resolved[root] for root in root_indices)
        self._order = tuple(layout.concrete for layout in self._layouts)
        self._view_rows = tuple(
            () if row is None else tuple(self._allocation(value) for value in row)
            for row in winners
        )
        self._winner = tuple(self._winner)  # pyright: ignore[reportAttributeAccessIssue]
        self._layouts = tuple(self._layouts)  # pyright: ignore[reportAttributeAccessIssue]
        self._states = tuple(self._states)  # pyright: ignore[reportAttributeAccessIssue]
        self._view_layouts = tuple(self._view_layouts)  # pyright: ignore[reportAttributeAccessIssue]
        self._resolved = None  # pyright: ignore[reportAttributeAccessIssue]
        reached_projections = tuple(reached) if reached is not None else single_reached
        self._releasable_rows = (
            (rows, reached_projections) if isinstance(rows.member_rows, list) else None
        )
        _notify(rows.observer, "occurrences_reached", len(reached_projections))
        if not defer_states:
            self._complete_invalid()
            self._rows = None

    @property
    def order(self) -> tuple[EntityIdentity, ...]:
        return self._order

    @property
    def roots(self) -> tuple[int | None, ...]:
        return self._roots

    @property
    def invalid_roots(self) -> tuple[InvalidRootInput, ...]:
        return self._invalid_roots

    @property
    def has_issues(self) -> bool:
        """Whether conversion classified any issue in the reachable root view."""
        return bool(self._invalid_roots) or any(state.findings for state in self._states)

    @property
    def pin(self) -> Pin:
        return self._pin

    def by_allocation[T](self, by_projection: Mapping[int, T]) -> Mapping[int, T]:
        """``by_projection`` re-keyed from projection index to allocation index.

        Several projections may resolve to one logical node, so the first one
        walked supplies the value after their Payload Witnesses have proved the
        projections equivalent. Only reached projections are read from the input;
        a deferred evidence mapping therefore judges nothing outside this Root
        View, and a projection no root reached contributes nothing.
        """
        if self._primed_source is by_projection and self._primed_values is not None:
            return cast(
                "Mapping[int, T]",
                {
                    index: value
                    for index, value in enumerate(self._primed_values)
                    if value is not _UNPRIMED
                },
            )
        resolved: dict[int, T] = {}
        for index, projection in enumerate(self._winner):
            try:
                value = by_projection[projection]
            except KeyError:
                continue
            resolved[index] = value
        return resolved

    def prime[T](self, by_projection: Mapping[int, T]) -> None:
        """Resolve canonical projection values while the borrowed Page is live."""
        if self.has_issues:
            return
        primed: list[object] = [_UNPRIMED] * len(self._winner)
        for index, projection in enumerate(self._winner):
            try:
                primed[index] = by_projection[projection]
            except KeyError:
                continue
        self._primed_source = by_projection
        self._primed_values = primed

    def projection_value[T](self, node: int, by_projection: Mapping[int, T]) -> T | None:
        """The canonical projection's value for one allocation, when present."""
        if self._primed_source is by_projection and self._primed_values is not None:
            value = self._primed_values[node]
            return None if value is _UNPRIMED else value  # pyright: ignore[reportReturnType]
        try:
            return by_projection[self._winner[node]]
        except KeyError:
            return None

    def release_raw_rows(self) -> None:
        """Release reached raw member rows after all evidence lookups are primed."""
        releasable = self._releasable_rows
        if releasable is None:
            return
        page_rows, reached = releasable
        member_rows = cast("list[tuple[object, ...]]", page_rows.member_rows)
        for projection in reached:
            member_rows[projection] = ()
        self._releasable_rows = None

    def release_finished_page_rows(
        self,
        root_position: int,
        last_uses: tuple[array[int], array[int]],
    ) -> None:
        """Release Page occurrence storage no later root can reach."""
        releasable = self._releasable_rows
        if releasable is None:
            return
        rows, reached = releasable
        projection_last, logical_last = last_uses
        member_rows = cast("list[tuple[object, ...]]", rows.member_rows)
        keys = cast("list[LogicalKey | None]", rows.keys)
        view_rows = cast("list[Sequence[object]]", rows.view_rows)
        witnesses = cast("list[object]", rows.witnesses)
        logical_ids = cast("list[int]", rows.logical_ids)
        for projection in reached:
            member_rows[projection] = ()
            if projection_last[projection] != root_position:
                continue
            logical = logical_ids[projection]
            rows.issues.release(projection)
            keys[projection] = None
            view_rows[projection] = ()
            rows.overwritten_edges.release(projection)
            witnesses[projection] = None
            rows.decoders.release(projection)
            logical_ids[projection] = 0
            if logical_last[logical] == root_position:
                rows.judged_states.release_logical(logical)
                logical_last[logical] = -1
        self._releasable_rows = None

    def complete(self) -> None:
        """Decode the already-consistent root after an atomic claim pass."""
        if self._rows is None:
            return
        self._states = tuple(  # pyright: ignore[reportAttributeAccessIssue]
            self._state(winner) for winner in self._winner
        )
        self._complete_invalid()
        self._rows = None

    def _complete_invalid(self) -> None:
        if self._pending_invalid:
            self._invalid_roots = tuple(
                InvalidRootInput(ordinal, self._decode(root).findings)
                for ordinal, root in self._pending_invalid
            )
            self._pending_invalid = ()

    def layout(self, node: int) -> EntityLayout:
        """The member layout ``node``'s state is read against — the canonical
        occurrence's own, and therefore its resolved concrete Entity's."""
        return self._layouts[node]

    def member_values(self, node: int) -> tuple[object, ...]:
        """``node``'s Page-owned Entity State row by reference, positional
        against :meth:`layout`."""
        return self._states[node].member_row

    def axis_start(self, node: int, attribute: AttributeIdentity, /) -> object:
        """``node``'s stored value at one As-Of Axis start, read at that
        Attribute's position in its member row."""
        return self._states[node].member_row[self._layouts[node].index_of[attribute]]

    def issues(self, node: int) -> tuple[StoredDataIssueInput, ...]:
        """The findings from ``node``'s one Page-owned payload judgment."""
        return self._states[node].findings

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

    def _reachable(self, roots: list[int]) -> tuple[int, ...]:
        """Projection preorder from the roots through every reached logical
        occurrence."""
        rows = self._rows
        if rows is None:  # pragma: no cover - construction owns a live Page
            raise ValueError("a completed Root View cannot rebuild reachability")
        order: list[int] = []
        seen: set[int] = set()
        pending = list(reversed(roots))
        while pending:
            projection = pending.pop()
            if projection in seen:
                continue
            seen.add(projection)
            order.append(projection)
            edges = (*rows.view_rows[projection], *rows.overwritten_edges[projection])
            for value in reversed(edges):
                if isinstance(value, tuple):
                    pending.extend(reversed(cast("tuple[int, ...]", value)))
                elif value is not None and value is not ABSENT:
                    pending.append(value)  # pyright: ignore[reportArgumentType]
        return tuple(order)

    def _decode(self, projection: int) -> EntityState:
        rows = self._rows
        if rows is None:  # pragma: no cover - completion owns a live Page
            raise ValueError("a completed Root View cannot decode another state")
        decoder = rows.decoders[projection]
        if decoder is None:  # pragma: no cover - a judged keyed projection is read from its state
            raise ValueError("a released projection decoder has no unjudged state")
        if isinstance(decoder, tuple):
            member_row, findings = cast("tuple[object, ...]", decoder), ()
        else:
            member_row, findings = decoder()
        if rows.keys[projection] is not None:
            rows.decoders[projection] = None
        identity_findings = rows.issues[projection]
        if not findings:
            findings = identity_findings
        elif identity_findings:
            findings = dedupe_issues((*findings, *identity_findings))
        _notify(rows.observer, "states_decoded")
        return EntityState(member_row, findings)

    def _canonical(self, occurrences: Sequence[int]) -> int:
        rows = self._rows
        if rows is None:  # pragma: no cover - construction owns a live Page
            raise ValueError("a completed Root View cannot compare another witness")
        if len(occurrences) == 2 and same_witness(rows, occurrences[0], occurrences[1]):
            _notify(rows.observer, "witnesses_compared", 1)
            rows.decoders[occurrences[1]] = None
            return occurrences[0]
        first, *remaining = occurrences
        if all(same_witness(rows, first, candidate) for candidate in remaining):
            _notify(rows.observer, "witnesses_compared", len(remaining))
            for candidate in remaining:
                rows.decoders[candidate] = None
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

    def _state(self, canonical: int) -> EntityState:
        rows = self._rows
        if rows is None:  # pragma: no cover - completion owns a live Page
            raise ValueError("a completed Root View cannot judge another state")
        if rows.keys[canonical] is None:
            state = self._decode(canonical)
            _release_witness(rows, canonical)
            return state
        held = judged_state(rows, canonical)
        if held is not None:
            _notify(rows.observer, "states_shared")
            return held
        state = self._decode(canonical)
        logical = rows.logical_ids[canonical]
        if isinstance(rows.claims[logical], int):
            rows.judged_states.set_singleton(logical, state)
            _release_witness(rows, canonical)
        else:
            rows.judged_states.group(logical).append((canonical, state))
        return state

    def _conflict(self, left: int, right: int) -> SnapshotConsistencyError:
        rows = cast("PageRows", self._rows)
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

    def _allocation(self, value: object) -> object:
        """One view value's projection references as allocation indices."""
        if value is None or value is ABSENT:
            return value
        if isinstance(value, tuple):
            return tuple(self._resolved[child] for child in cast("tuple[int, ...]", value))
        return self._resolved[cast("int", value)]


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


def _notify(observer: object | None, name: str, *args: object) -> None:
    if observer is not None:
        callback = getattr(observer, name)
        callback(*args)


def _release_witness(rows: PageRows, projection: int) -> None:
    if isinstance(rows.witnesses, list):
        rows.witnesses[projection] = None
