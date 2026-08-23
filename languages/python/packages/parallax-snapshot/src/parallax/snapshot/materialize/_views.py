"""Relationship view slots, fixed once per execution.

One fetch plan yields one :class:`ViewSchema`, and every graph that execution
builds — its staging graph, each milestone graph, and every projection in any of
them — reads its slots off that one schema. A projection's relationship view row
is then a fixed-width row of positions rather than a mapping: which positions it
has is a function of the source level that produced it and the concrete Entity
it resolved to, and nothing about the row itself.

The concrete axis is degenerate everywhere but the root, and that is what makes
the schema small. A path-root guard is the only thing that filters a level's
parents, and a plan carries one only on root-parented levels, because a deeper
level descends from parents an ancestor level already guarded. So every non-root
source level has exactly one layout shared by all of its concretes, and only a
root projection can pay a narrower row.

Broad and narrowed views of one direction occupy DISTINCT slots. They can
resolve different child sets, so they share the storage machinery and nothing
else; splitting them stays the read-time concern it is today, where only the
typed materializer separates them.

Layouts are built on first reach of a ``(source level, concrete Entity)`` pair
and interned by the slot tuple they admit, so concretes that no guard splits
share one :class:`SourceViewLayout` object. Building on demand also degrades
gracefully: a projection resolving a concrete nothing enumerated is laid out for
rather than failed on. Every layout published is immutable, which is what lets
the graphs of one execution share a schema, and the memo is execution-scoped
internal state — no query shape is retained for the lifetime of a model.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import EntityIdentity, RelationshipIdentity

__all__ = [
    "ROOT_LEVEL",
    "ChildSlot",
    "MergedViewLayout",
    "RelationshipViewKey",
    "SourceLevel",
    "SourceViewLayout",
    "ViewSchema",
]


type SourceLevel = int
"""Which level of a fetch plan produced a projection: the root is 0, plan level
``i`` is ``i + 1``."""

ROOT_LEVEL: Final[SourceLevel] = 0
"""The source level of a root projection, and the only one a graph built from a
plan carrying no levels has."""


@dataclass(frozen=True, slots=True)
class RelationshipViewKey:
    """One relationship view a projection loaded.

    ``relationship`` is the declared direction. ``narrowed_view`` is the derived
    ``<rel>[<Concrete>,<Concrete>]`` key of a narrowed polymorphic hop, or
    ``None`` for the broad view — the two are distinct views of one direction and
    never merge into each other. The derived key is the plan's own canonical
    spelling of the hop's effective concrete-identity set; deriving a second one
    here would duplicate a decision deep-fetch planning already made.
    """

    relationship: RelationshipIdentity
    narrowed_view: str | None = None


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
    distinct hops that attach under the same name — share the one slot, so a
    parent both admit is written twice and retains what the later level found.
    """

    slots: tuple[RelationshipViewKey, ...]
    index_of: Mapping[RelationshipViewKey, int]


@dataclass(frozen=True, slots=True)
class MergedViewLayout:
    """One merged logical node's relationship view slots, in canonical order.

    ``slots`` is the union of every source layout the node's concrete Entity has,
    ordered by the member layout's own rule, so a walk that visits slots by index
    visits them in declaration order without sorting anything. Taking the union
    over the whole plan rather than over the levels one node happened to be
    projected at is what fixes the width before the first projection of that node
    is walked: a node reached again from a second level widens nothing.
    ``index_of`` is how a caller holding a view key finds the slot to read.

    ``to_merged`` translates a source row into this one, indexed by source level
    and then by that level's own slot: a projection's view row is positional
    against its :class:`SourceViewLayout`, and merging carries each written
    position across once, where the merged row is built, rather than at each
    read.
    """

    slots: tuple[RelationshipViewKey, ...]
    index_of: Mapping[RelationshipViewKey, int]
    to_merged: tuple[tuple[int, ...], ...]


class ViewSchema:
    """One execution's view slots, by source level and resolved concrete Entity.

    Two constructors, because guards exist on root-parented levels only.
    :meth:`of` states one unguarded source level directly, which is what lets a
    merge be exercised with no plan, no executor, and no database; the
    initializer takes the whole slot table a guarded plan derives, indexed by
    source level.
    """

    __slots__ = ("_interned", "_levels", "_merged", "_source")

    def __init__(self, levels: Sequence[tuple[ChildSlot, ...]]) -> None:
        self._levels: tuple[tuple[ChildSlot, ...], ...] = tuple(levels)
        self._interned: dict[tuple[RelationshipViewKey, ...], SourceViewLayout] = {}
        self._source: dict[tuple[SourceLevel, EntityIdentity], SourceViewLayout] = {}
        self._merged: dict[EntityIdentity, MergedViewLayout] = {}

    @classmethod
    def of(cls, *views: RelationshipViewKey) -> ViewSchema:
        """A schema of one unguarded source level carrying ``views``."""
        return cls((tuple(ChildSlot(view) for view in views),))

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

    def merged(self, layout: EntityLayout) -> MergedViewLayout:
        """The merged view row a logical node resolving to ``layout``'s Entity
        carries, with the translation of every source level's row into it."""
        cached = self._merged.get(layout.concrete)
        if cached is not None:
            return cached
        sources = tuple(self.source(level, layout) for level in range(len(self._levels)))
        slots = layout.ordered(dict.fromkeys(view for source in sources for view in source.slots))
        index_of = _index_of(slots)
        built = MergedViewLayout(
            slots,
            index_of,
            tuple(tuple(index_of[view] for view in source.slots) for source in sources),
        )
        self._merged[layout.concrete] = built
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
