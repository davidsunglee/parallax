"""Projection merging: many per-row projections into one deterministic allocation order.

The merge retains a transient logical-identity index, the allocation index each
input projection resolved to, and **slot-level winner references** — a
``(node index, entry index)`` pair naming where in the input a member's winning
entry lives. It clones no payload: :meth:`GraphMerge.node` composes one node's
populate inputs on demand, out of the input's own frozen carrier records, and the
caller drops the result as soon as that node is populated. No merged second graph
is retained.

Two passes over one order. Pass 1 walks roots in first-encounter preorder,
assigning each logical node its zero-based allocation index and recording the
first projection to carry each member and view. Pass 2 is the caller's own
allocate/populate loop over the same order.

The preorder is fixed: roots in result order; each projection's relationship views
in accepted metadata declaration order; the broad view before that relationship's
narrowed views; narrowed views by their canonical derived key; children in
to-many result order. A repeated logical node reuses its first index, and every
projection is walked exactly once, so a projection reached late still contributes
its own children at its own position.

Scalars, Value Objects, and the resolved concrete Entity are first-projection-wins
with **no value comparison**: duplicate projections of one logical node are
value-identical by construction, because they resolve the same row at the same
pin. Relationship views are unioned — a view any projection loaded is loaded on
the merged node — with the first projection to carry a given view key deciding
that view's value.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from parallax.core.entity._graph_input import (
    EntityAttributeInput,
    ValueObjectOccurrenceInput,
)
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.relationship import view as relationship_view
from parallax.core.temporal_read import Pin
from parallax.snapshot.materialize._input import (
    LogicalKey,
    RelationshipViewKey,
    SnapshotGraphInput,
    SnapshotNodeInput,
    SnapshotNodeRef,
    SnapshotRelationshipViewInput,
    logical_key,
    validate_graph_input,
    view_refs,
)

__all__ = ["GraphMerge", "MergedNode", "MergedRelationshipView", "merge_graph_input"]

_UNREACHED = -1


@dataclass(frozen=True, slots=True)
class MergedRelationshipView:
    """One merged relationship view: ``None`` is loaded-null, an allocation index
    is a loaded to-one, and a tuple of them is a loaded to-many. A view no
    projection carried is absent, which is what unloaded means."""

    view: RelationshipViewKey
    value: int | tuple[int, ...] | None


@dataclass(frozen=True, slots=True)
class MergedNode:
    """One logical node's populate inputs, composed on demand and owned by the
    caller for exactly as long as it takes to populate that node."""

    concrete_entity: EntityIdentity
    attributes: tuple[EntityAttributeInput, ...]
    value_objects: tuple[ValueObjectOccurrenceInput, ...]
    views: tuple[MergedRelationshipView, ...]


type _Winner = tuple[int, int]


class GraphMerge:
    """One graph input's merge state: allocation order, roots, and winners.

    ``order`` position *is* the allocation index the caller allocates in, so
    nothing recomputes an index the writer already owns.
    """

    __slots__ = (
        "_attributes",
        "_graph",
        "_logical",
        "_model",
        "_order",
        "_ranks",
        "_resolved",
        "_roots",
        "_value_objects",
        "_views",
    )

    def __init__(self, graph: SnapshotGraphInput, model: Metamodel) -> None:
        validate_graph_input(graph)
        self._graph = graph
        self._model = model
        self._order: list[EntityIdentity] = []
        self._logical: dict[LogicalKey | int, int] = {}
        self._ranks: dict[EntityIdentity, Mapping[str, int]] = {}
        self._resolved = [_UNREACHED] * len(graph.nodes)
        self._attributes: list[dict[object, _Winner]] = []
        self._value_objects: list[dict[object, _Winner]] = []
        self._views: list[dict[RelationshipViewKey, _Winner]] = []
        for root in graph.roots:
            self._walk(root)
        self._roots = tuple(self._resolved[root.node_index] for root in graph.roots)

    @property
    def order(self) -> tuple[EntityIdentity, ...]:
        """Each allocation index's own concrete Entity, in allocation order."""
        return tuple(self._order)

    @property
    def roots(self) -> tuple[int, ...]:
        """The allocation indices of this graph's roots, in result order."""
        return self._roots

    @property
    def pin(self) -> Pin:
        """The whole-graph pin every node of this graph was read at."""
        return self._graph.pin

    def node(self, index: int) -> MergedNode:
        """One allocation index's merged populate inputs.

        Freshly composed per call out of the winning entries' own records, so the
        merge itself holds integers and nothing else.
        """
        nodes = self._graph.nodes
        return MergedNode(
            concrete_entity=self._order[index],
            attributes=tuple(
                nodes[node].attributes[entry] for node, entry in self._attributes[index].values()
            ),
            value_objects=tuple(
                nodes[node].value_objects[entry]
                for node, entry in self._value_objects[index].values()
            ),
            views=tuple(
                MergedRelationshipView(view, self._allocation(nodes[node], entry))
                for view, (node, entry) in self._ordered_winners(index)
            ),
        )

    # ----------------------------------------------------------------------- #
    # Pass 1                                                                    #
    # ----------------------------------------------------------------------- #

    def _walk(self, ref: SnapshotNodeRef) -> None:
        if self._resolved[ref.node_index] != _UNREACHED:
            return
        node = self._graph.nodes[ref.node_index]
        key = logical_key(self._model, node)
        index = self._logical.get(ref.node_index if key is None else key)
        if index is None:
            index = len(self._order)
            self._logical[ref.node_index if key is None else key] = index
            self._order.append(node.concrete_entity)
            self._attributes.append({})
            self._value_objects.append({})
            self._views.append({})
        self._resolved[ref.node_index] = index
        for position, entry in enumerate(node.attributes):
            self._attributes[index].setdefault(entry.identity, (ref.node_index, position))
        for position, entry in enumerate(node.value_objects):
            self._value_objects[index].setdefault(entry.identity, (ref.node_index, position))
        for position, entry in enumerate(node.relationship_views):
            self._views[index].setdefault(entry.view, (ref.node_index, position))
        for entry in self._ordered_views(node):
            for child in view_refs(entry.value):
                self._walk(child)

    # ----------------------------------------------------------------------- #
    # Deterministic view order                                                  #
    # ----------------------------------------------------------------------- #

    def _ordered_views(self, node: SnapshotNodeInput) -> list[SnapshotRelationshipViewInput]:
        declared = self._declared(node.concrete_entity)
        return sorted(node.relationship_views, key=lambda entry: _rank(declared, entry.view))

    def _ordered_winners(self, index: int) -> list[tuple[RelationshipViewKey, _Winner]]:
        declared = self._declared(self._order[index])
        return sorted(self._views[index].items(), key=lambda item: _rank(declared, item[0]))

    def _declared(self, entity: EntityIdentity) -> Mapping[str, int]:
        cached = self._ranks.get(entity)
        if cached is None:
            cached = _navigable_relationships(self._model, entity)
            self._ranks[entity] = cached
        return cached

    def _allocation(self, node: SnapshotNodeInput, entry: int) -> int | tuple[int, ...] | None:
        value = node.relationship_views[entry].value
        if value is None:
            return None
        if isinstance(value, tuple):
            return tuple(self._resolved[ref.node_index] for ref in value)
        return self._resolved[value.node_index]


def merge_graph_input(graph: SnapshotGraphInput, model: Metamodel) -> GraphMerge:
    """``graph``'s merge state — validated, walked, and ready to allocate from."""
    return GraphMerge(graph, model)


def _rank(declared: Mapping[str, int], view: RelationshipViewKey) -> tuple[int, int, str]:
    """One view's position in the deterministic preorder: its relationship's own
    declaration position, the broad view before that relationship's narrowed ones,
    and narrowed views by their canonical derived key."""
    position = declared.get(view.relationship.name, len(declared))
    return position, int(view.narrowed_view is not None), view.narrowed_view or ""


def _navigable_relationships(model: Metamodel, entity: EntityIdentity) -> Mapping[str, int]:
    """Each navigable relationship name's position in accepted declaration order,
    ancestry first.

    A relationship declared on an inheritance ancestor is reached by every
    concrete descendant under the ancestor's own identity and is never
    redeclared, so the navigable set is the ancestry chain's directions with each
    name taken from the nearest declaration.
    """
    facet = relationship_view(model)
    position = inheritance_view(model).entity(entity)
    chain = tuple(position.ancestry) if position is not None else (entity,)
    order: dict[str, int] = {}
    for ancestor in chain:
        for direction in facet.relationships(ancestor) or ():
            order.setdefault(direction.identity.name, len(order))
    return order
