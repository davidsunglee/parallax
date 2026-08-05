"""``parallax.snapshot.handle._materializer`` — Snapshot Graph Input into frozen nodes.

Private handle implementation, never re-exported: ``_read`` is its only caller,
and the frozen graphs it builds reach callers as :class:`~parallax.snapshot.handle.Snapshot`
roots.

It owns nothing about carriers, identity, or merging — :mod:`parallax.snapshot.materialize`
settles all three before this module runs — and nothing about Pydantic, cycle
closure, or the private lifecycle slot, which
:class:`~parallax.core.entity.EntityGraphConstruction` owns. What is left is the
thin translation between them: merge state in, ``allocate`` / ``populate`` calls
out, and one :class:`~parallax.snapshot._inspection.SnapshotNodeState` per node
built in the state factory, where every handle resolves to its final instance.
Building the state there is what closes a cyclic narrowed view without exposing a
partial object.

A merged view's shape carries its own arm: a tuple is loaded-many (empty included),
``None`` is loaded-null, and a lone allocation index is loaded-one. A relationship
the merge carries no entry for is simply not named, and the writer installs the
private unloaded sentinel — which is what makes the closed world structural rather
than a convention this module has to restate.

Hashability is conditional, exactly per spec §3: nothing here makes a node hashable
or guards against one — a back-reference closing a cycle makes the derived hash
non-terminating, so such nodes are shareable but not hashable.
"""

from __future__ import annotations

from typing import cast

from parallax.core.entity import LOADED_NULL as _LOADED_NULL
from parallax.core.entity import (
    EntityGraphConstruction,
    EntityGraphWriter,
    EntityRelationshipInput,
    LoadedMany,
    LoadedOne,
    NodeHandle,
    RelationshipInput,
    ResolutionView,
)
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.temporal_read import Edge, milestone_edge_of
from parallax.snapshot._inspection import SnapshotNodeState
from parallax.snapshot.materialize import (
    GraphMerge,
    MergedNode,
    SnapshotGraphInput,
    merge_graph_input,
)

__all__ = ["materialize_graph"]


def materialize_graph(
    graph: SnapshotGraphInput, model: Metamodel, runtime: EntityGraphConstruction
) -> tuple[object, ...]:
    """Merge ``graph`` and construct its roots as frozen Entity instances.

    Every node is allocated before any is populated, so a cycle closes on an
    object that already exists, and the whole result publishes at once or not at
    all.
    """
    return _Materialization(merge_graph_input(graph, model), model).run(runtime)


class _Materialization:
    """One graph's construction drive: the merge, and the two callbacks over it."""

    __slots__ = ("_edges", "_merge", "_model", "_narrowed", "_pending")

    def __init__(self, merge: GraphMerge, model: Metamodel) -> None:
        self._merge = merge
        self._model = model
        self._narrowed: dict[int, dict[str, object]] = {}
        self._edges: list[Edge | None] = []
        self._pending = iter(range(len(merge.order)))

    def run(self, runtime: EntityGraphConstruction) -> tuple[object, ...]:
        return runtime.construct(self.build, state_factory=self.state)

    def build(self, writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handles = [writer.allocate(identity) for identity in self._merge.order]
        for index, handle in enumerate(handles):
            node = self._merge.node(index)
            views: dict[str, object] = {}
            entries: list[EntityRelationshipInput] = []
            for merged in node.views:
                key = merged.view.narrowed_view
                if key is None:
                    entries.append(
                        EntityRelationshipInput(
                            merged.view.relationship, _arm(merged.value, handles)
                        )
                    )
                else:
                    views[key] = _resolvable(merged.value, handles)
            writer.populate(handle, node.attributes, node.value_objects, tuple(entries))
            if views:
                self._narrowed[index] = views
            self._edges.append(self._edge(node))
        return tuple(handles[index] for index in self._merge.roots)

    def state(self, view: ResolutionView, handle: NodeHandle) -> SnapshotNodeState:
        """One node's Snapshot state, built in allocation order.

        Every handle resolves to its final instance here, so a narrowed view that
        points back at an ancestor closes without any partially built object
        having been exposed.
        """
        del handle
        index = next(self._pending)
        edge = self._edges[index]
        return SnapshotNodeState(
            entity=self._merge.order[index],
            views={
                key: _resolved(view, value) for key, value in self._narrowed.get(index, {}).items()
            },
            pin=self._merge.pin if edge is not None else None,
            edge=edge,
        )

    def _edge(self, node: MergedNode) -> Edge | None:
        """One node's milestone edge, or absence for a non-temporal family.

        As-of axes are family-wide metadata declared on the family root, so the
        interval members are read at the root's own Attribute Identities — the
        identities an inherited member reaches every concrete descendant under.
        """
        declaring = _declaring(self._model, node.concrete_entity)
        if declaring is None or not declaring.declared_as_of_axes:
            return None
        return milestone_edge_of(
            declaring, {entry.identity: entry.value for entry in node.attributes}
        )


def _arm(value: int | tuple[int, ...] | None, handles: list[NodeHandle]) -> RelationshipInput:
    if isinstance(value, tuple):
        return LoadedMany(tuple(handles[index] for index in value))
    if value is None:
        return _LOADED_NULL
    return LoadedOne(handles[value])


def _resolvable(
    value: int | tuple[int, ...] | None, handles: list[NodeHandle]
) -> NodeHandle | tuple[NodeHandle, ...] | None:
    if isinstance(value, tuple):
        return tuple(handles[index] for index in value)
    if value is None:
        return None
    return handles[value]


def _resolved(view: ResolutionView, value: object) -> object:
    if value is None:
        return None
    if isinstance(value, tuple):
        return tuple(view.resolve(handle) for handle in cast("tuple[NodeHandle, ...]", value))
    return view.resolve(cast("NodeHandle", value))


def _declaring(model: Metamodel, identity: EntityIdentity) -> EntityMetadata | None:
    """The position declaring ``identity``'s family-wide temporal facts — its family
    root, which for a standalone Entity is itself."""
    position = inheritance_view(model).entity(identity)
    return model.entity(identity if position is None else position.root)
