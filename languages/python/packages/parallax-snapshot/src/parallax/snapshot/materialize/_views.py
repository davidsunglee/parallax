from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from parallax.core.deep_fetch import RelationshipViewKey
from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import EntityIdentity

__all__ = [
    "ROOT_LEVEL",
    "ChildSlot",
    "RootViewLayout",
    "SourceLevel",
    "SourceViewLayout",
    "ViewSchema",
]


type SourceLevel = int
"""Which level of a fetch plan produced a projection: the root is 0, plan level
``i`` is ``i + 1``."""

ROOT_LEVEL: Final[SourceLevel] = 0
"""The source level of a root projection, and the only one a Page built from a
plan carrying no levels has."""


@dataclass(frozen=True, slots=True)
class ChildSlot:
    """One view a level attaches to its parents, and which parents may receive it.

    ``admits`` is the level's path-root guard as the concrete Entities it
    resolved to, or ``None`` for an unguarded level. A guard selects parents by
    their OWN resolved concrete, so two parents of one concrete are admitted or
    excluded together — which is what keeps the admitted slot set a function of
    the ``(source level, concrete)`` pair rather than of an individual row.
    """

    view: RelationshipViewKey
    admits: frozenset[EntityIdentity] | None = None


@dataclass(frozen=True, slots=True)
class SourceViewLayout:
    """The view row one source level's projections of one concrete Entity carry.

    ``slots`` is what that level's child levels attach, minus whatever a guard
    excluded this concrete from, in the member layout's own canonical order.
    Every slot is one a fan-back writes, so a position left ``ABSENT`` at sealing
    is a level that gathered no parent at all.

    Two levels sharing one view key — a guarded path and its broad sibling are
    distinct hops that attach under the same name — share the one slot. A parent
    both admit keeps the later level's delivered arm while the Page retains the
    overwritten edge until its root-local continuations have been merged.
    """

    slots: tuple[RelationshipViewKey, ...]
    index_of: Mapping[RelationshipViewKey, int]


@dataclass(frozen=True, slots=True)
class RootViewLayout:
    """One root-local logical node's relationship view slots, in canonical order.

    ``slots`` is the union of every source layout the node's concrete Entity has,
    ordered by the member layout's own rule, so a walk that visits slots by index
    visits them in declaration order without sorting anything. Taking the union
    over the whole plan rather than over the levels one node happened to be
    projected at is what fixes the width before the first projection of that node
    is walked: a node reached again from a second level widens nothing.
    ``index_of`` is how a caller holding a view key finds the slot to read.

    So a view is absent here in two distinguishable ways, and a reader must not
    read one as the other. A view this concrete carries at NO source level has no
    slot at all — a path-root guard excluded it everywhere the view is attached.
    A view it carries at some level the node was never projected at has a slot
    holding ``ABSENT``. Both are unloaded; only the second occupies a position.

    ``to_root_view`` translates a source row into this one, indexed by source level
    and then by that level's own slot: a projection's view row is positional
    against its :class:`SourceViewLayout`, and Root View assembly carries each written
    position across once, where the Root View row is built, rather than at each
    read.
    """

    slots: tuple[RelationshipViewKey, ...]
    index_of: Mapping[RelationshipViewKey, int]
    to_root_view: tuple[tuple[int, ...], ...]


class ViewSchema:
    """One execution's view slots, by source level and resolved concrete Entity.

    Two constructors, because guards exist on root-parented levels only.
    :meth:`of` states one unguarded source level directly, which is what lets a
    Root View be exercised with no plan, no executor, and no database; the
    initializer takes the whole slot table a guarded plan derives, indexed by
    source level.
    """

    __slots__ = ("_frozen", "_interned", "_levels", "_root_views", "_source")

    def __init__(self, levels: Sequence[tuple[ChildSlot, ...]]) -> None:
        self._levels: tuple[tuple[ChildSlot, ...], ...] = tuple(levels)
        self._interned: dict[tuple[RelationshipViewKey, ...], SourceViewLayout] = {}
        self._source: dict[tuple[SourceLevel, EntityIdentity], SourceViewLayout] = {}
        self._root_views: dict[EntityIdentity, RootViewLayout] = {}
        self._frozen = False

    @classmethod
    def of(cls, *views: RelationshipViewKey) -> ViewSchema:
        """A schema of one unguarded source level carrying ``views``."""
        return cls((tuple(ChildSlot(view) for view in views),))

    @classmethod
    def prepared(
        cls,
        levels: Sequence[tuple[ChildSlot, ...]],
        layouts: Iterable[EntityLayout],
    ) -> ViewSchema:
        schema = cls(levels)
        held = tuple(layouts)
        for layout in held:
            for level in range(len(schema._levels)):
                schema.source(level, layout)
            schema.root_view(layout)
        schema._interned = MappingProxyType(schema._interned)  # pyright: ignore[reportAttributeAccessIssue]
        schema._source = MappingProxyType(schema._source)  # pyright: ignore[reportAttributeAccessIssue]
        schema._root_views = MappingProxyType(schema._root_views)  # pyright: ignore[reportAttributeAccessIssue]
        schema._frozen = True
        return schema

    def source(self, level: SourceLevel, layout: EntityLayout) -> SourceViewLayout:
        """The view row a projection of ``layout``'s Entity produced by ``level``
        carries.

        Derived on the pair's first reach and answered from what that reach
        interned thereafter, so two concretes no guard splits are answered the
        identical object. Raises :class:`ValueError` for a level this schema's
        own plan never had.
        """
        memo = (level, layout.concrete)
        cached = self._source.get(memo)
        if cached is not None:
            return cached
        if self._frozen:
            raise ValueError(
                f"this prepared view schema carries no source layout for "
                f"{layout.concrete.canonical} at level {level}"
            )
        if not 0 <= level < len(self._levels):
            raise ValueError(
                f"this view schema carries {len(self._levels)} source levels, "
                f"so it lays out no row for a projection of level {level}"
            )
        built = self._interned_layout(
            layout.ordered(
                dict.fromkeys(
                    slot.view
                    for slot in self._levels[level]
                    if slot.admits is None or layout.concrete in slot.admits
                )
            )
        )
        self._source[memo] = built
        return built

    def root_view(self, layout: EntityLayout) -> RootViewLayout:
        """The Root View row a logical node resolving to ``layout``'s Entity
        carries, with the translation of every source level's row into it."""
        cached = self._root_views.get(layout.concrete)
        if cached is not None:
            return cached
        if self._frozen:
            raise ValueError(
                f"this prepared view schema carries no root layout for {layout.concrete.canonical}"
            )
        sources = tuple(self.source(level, layout) for level in range(len(self._levels)))
        slots = layout.ordered(dict.fromkeys(view for source in sources for view in source.slots))
        index_of = _index_of(slots)
        built = RootViewLayout(
            slots,
            index_of,
            tuple(tuple(index_of[view] for view in source.slots) for source in sources),
        )
        self._root_views[layout.concrete] = built
        return built

    def _interned_layout(self, slots: tuple[RelationshipViewKey, ...]) -> SourceViewLayout:
        interned = self._interned.get(slots)
        if interned is not None:
            return interned
        built = SourceViewLayout(slots, _index_of(slots))
        self._interned[slots] = built
        return built


def _index_of(slots: Iterable[RelationshipViewKey]) -> Mapping[RelationshipViewKey, int]:
    return MappingProxyType({view: slot for slot, view in enumerate(slots)})
