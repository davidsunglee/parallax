"""Canonical logical shape of one validated deep-fetch request.

The tree owns requested positions and their resolved admission facts. Execution
steps refer to positions by integer; publication consumes the same positions to
select finite continuations. Nothing here retains executable query machinery.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from parallax.core.metamodel import EntityIdentity, RelationshipIdentity
from parallax.core.object_query._validated import ValidatedIncludePath

__all__ = [
    "EMPTY_RENDER",
    "IncludePosition",
    "IncludeTree",
    "PositionId",
    "RelationshipViewKey",
    "RenderToken",
]

type PositionId = int
"""An index issued by one :class:`IncludeTree`; ``0`` is that tree's root.

The identity is meaningful only to the tree that issued it.
"""

type RenderToken = PositionId | tuple[PositionId, ...]
"""One admitted position, or issued positions whose child views render together."""

EMPTY_RENDER: Final[PositionId] = -1
"""The terminal token for a node whose requested position has no child views."""

ROOT_POSITION: Final[PositionId] = 0


@dataclass(frozen=True, slots=True)
class RelationshipViewKey:
    """One broad or narrowed relationship view."""

    relationship: RelationshipIdentity
    narrowed_view: str | None = None


@dataclass(frozen=True, slots=True)
class IncludePosition:
    """One requested logical position in an :class:`IncludeTree`."""

    parent: PositionId | None
    view: RelationshipViewKey | None
    source: tuple[EntityIdentity, ...]
    target: tuple[EntityIdentity, ...]
    to_many: bool
    children: Mapping[RelationshipViewKey, tuple[PositionId, ...]]


@dataclass(frozen=True, slots=True)
class PositionSeed:
    parent: PositionId
    view: RelationshipViewKey
    source: tuple[EntityIdentity, ...]
    target: tuple[EntityIdentity, ...]
    to_many: bool


class IncludeTree:
    """Immutable indexed positions for one validated query's finite includes."""

    __slots__ = ("_positions", "queried")

    def __init__(self, queried: EntityIdentity, positions: Sequence[IncludePosition]) -> None:
        if not positions or positions[ROOT_POSITION].parent is not None:
            raise ValueError("an IncludeTree starts with its root position")
        self._positions = tuple(positions)
        self.queried = queried

    @property
    def positions(self) -> tuple[IncludePosition, ...]:
        return self._positions

    @property
    def root(self) -> PositionId:
        return ROOT_POSITION

    def position(self, position: PositionId) -> IncludePosition:
        return self._positions[position]

    def admits(self, position: PositionId, concrete: EntityIdentity) -> bool:
        return concrete in self._positions[position].target

    def child_groups(
        self, token: RenderToken
    ) -> Mapping[RelationshipViewKey, tuple[PositionId, ...]]:
        """Children of every position denoted by ``token``, grouped by view."""
        if token == EMPTY_RENDER:
            return MappingProxyType({})
        positions = (token,) if isinstance(token, int) else token
        grouped: dict[RelationshipViewKey, list[PositionId]] = {}
        for position in positions:
            for view, children in self._positions[position].children.items():
                held = grouped.setdefault(view, [])
                for child in children:
                    if child not in held:
                        held.append(child)
        return MappingProxyType({view: tuple(children) for view, children in grouped.items()})

    def admitted_children(
        self, candidates: Iterable[PositionId], source: EntityIdentity
    ) -> tuple[PositionId, ...]:
        return tuple(
            position for position in candidates if source in self._positions[position].source
        )

    def render_token(
        self, candidates: Iterable[PositionId], concrete: EntityIdentity
    ) -> RenderToken | None:
        """The normalized continuation token admitted for one hydrated child."""
        admitted = tuple(
            position for position in candidates if concrete in self._positions[position].target
        )
        if not admitted:
            return None
        nonempty = sorted({position for position in admitted if self._positions[position].children})
        if not nonempty:
            return EMPTY_RENDER
        if len(nonempty) == 1:
            return nonempty[0]
        return tuple(nonempty)

    def requested_position(self, path: ValidatedIncludePath) -> PositionId | None:
        """The exact requested position denoted by ``path``, if one exists."""
        current = (ROOT_POSITION,)
        for index, segment in enumerate(path.segments):
            matching: list[PositionId] = []
            expected_source = path.source_position if index == 0 else None
            for parent in current:
                for candidates in self._positions[parent].children.values():
                    for position in candidates:
                        held = self._positions[position]
                        view = held.view
                        if (
                            view is not None
                            and view.relationship == segment.relationship
                            and held.target == segment.position
                            and (view.narrowed_view is not None) == segment.authored_narrow
                            and (expected_source is None or held.source == expected_source)
                        ):
                            matching.append(position)
            current = tuple(dict.fromkeys(matching))
            if not current:
                return None
        return current[0] if len(current) == 1 else None


def build_include_tree(
    *,
    queried: EntityIdentity,
    root: tuple[EntityIdentity, ...],
    positions: Sequence[PositionSeed],
) -> IncludeTree:
    """Freeze planner-owned position facts into their canonical topology."""
    child_maps: list[dict[RelationshipViewKey, list[PositionId]]] = [
        {} for _ in range(len(positions) + 1)
    ]
    for index, seed in enumerate(positions, start=1):
        child_maps[seed.parent].setdefault(seed.view, []).append(index)

    def children(position: PositionId) -> Mapping[RelationshipViewKey, tuple[PositionId, ...]]:
        return MappingProxyType(
            {view: tuple(values) for view, values in child_maps[position].items()}
        )

    frozen = [IncludePosition(None, None, root, root, False, children(ROOT_POSITION))]
    frozen.extend(
        IncludePosition(
            seed.parent,
            seed.view,
            seed.source,
            seed.target,
            seed.to_many,
            children(index),
        )
        for index, seed in enumerate(positions, start=1)
    )
    return IncludeTree(queried, frozen)
