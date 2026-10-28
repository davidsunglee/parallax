from __future__ import annotations

from typing import cast

from parallax.core import temporal_read
from parallax.core.entity import (
    UNLOADED,
    EntityGraphConstruction,
    EntityGraphWriter,
    GraphConstructionError,
    NodeHandle,
    ResolutionView,
)
from parallax.core.metamodel import EntityIdentity, Metamodel, RelationshipIdentity
from parallax.core.read_delivery._page import ABSENT, InvalidData, VersionAttributes
from parallax.core.temporal_read import NonTemporal
from parallax.snapshot._inspection import RootConformance, SnapshotNodeState, pin_for_shape
from parallax.snapshot._publication._classify import ConformingRoot, classify_root
from parallax.snapshot._publication._root import RootView

__all__ = ["TypedRootPublisher"]


class TypedRootPublisher:
    """One Page's Typed root publisher: classify each root, then construct the
    nodes of a root that hydrates as one Entity graph.

    Every node is allocated before any is populated, so a cycle closes on an
    object that already exists, and everything a root constructs publishes at
    once or not at all. The model's facts are bound for the Page; the Root View,
    conformance, handles, and pending node are one root's, reset when its call
    begins and the bookkeeping cleared when it ends. A node's broad-relationship
    row is built at the callback that needs it, and its member row is
    Page-owned, so no payload accumulates into a second Page-sized structure.

    ``versions`` names the explicit version Attribute a classified record
    publishes.
    """

    __slots__ = (
        "_conformance",
        "_construction",
        "_handles",
        "_model",
        "_pending",
        "_root",
        "_temporal",
        "_versions",
    )

    def __init__(
        self,
        model: Metamodel,
        construction: EntityGraphConstruction,
        versions: VersionAttributes,
    ) -> None:
        self._model = model
        self._construction = construction
        self._versions = versions
        self._temporal = temporal_read.view(model)
        self._root: RootView | None = None
        self._conformance = RootConformance.CONFORMING
        self._handles: list[NodeHandle] = []
        self._pending = 0

    def __call__(self, root: RootView, ordinal: int) -> tuple[object | InvalidData[object], ...]:
        """``root`` published at result ``ordinal``: as itself when it conforms,
        and otherwise as its record, carrying its value when it hydrates."""
        # The construction callbacks are bound per call rather than held: a held
        # bound method would leave this publisher reachable only through a cycle,
        # keeping the Root View and its Page rows alive past the pass.
        self._root = root
        self._conformance = RootConformance.CONFORMING
        self._handles.clear()
        self._pending = 0
        try:
            verdict = classify_root(root, self._model, self._versions, ordinal=ordinal)
            if isinstance(verdict, ConformingRoot):
                return self._construction.construct(self.build, state_factory=self.state)
            self._conformance = RootConformance.NONCONFORMING
            if verdict.node is None:
                return (verdict.published(None),)
            (constructed,) = self._construction.construct(self.build, state_factory=self.state)
            return (verdict.published(constructed),)
        finally:
            self._handles.clear()
            self._pending = 0

    def build(self, writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        root = cast("RootView", self._root)
        handles = self._handles
        allocate = writer.allocate
        handles.extend([allocate(root.layout(node).concrete) for node in range(len(root))])
        for node, handle in enumerate(handles):
            writer.populate(handle, root.member_values(node), self._broad_arms(root, node))
        return (handles[0],)

    def _broad_arms(self, root: RootView, node: int) -> tuple[object, ...]:
        """One node's full-width broad-relationship row.

        A narrowed view is a read-time presentation of a direction the broad view
        already carries, so only the broad slot reaches a relationship position;
        the narrowed ones are resolved into instances in :meth:`state`. A slot
        reading ``ABSENT`` names nothing, so its position keeps the unloaded
        sentinel the row starts every position at.

        Positions come from the same member layout the Root View laid the node out
        against, so the row is the model's own width by construction. A view
        schema may still lay out a slot for a direction this concrete does not
        declare — an unguarded level attaches its slot to every concrete it can
        reach, and the canonical view order ranks such a direction last rather
        than refusing it — so laying the slot out is tolerated and WRITING one is
        the disagreement, stated here in the construction vocabulary, because a
        position dropped instead would lose a view the read loaded.
        """
        layout = root.layout(node)
        row: list[object] = [UNLOADED] * len(layout.relationships)
        view_layout = root.view_layout(node)
        for slot, position in view_layout.broad_positions:
            value = root.view(node, slot)
            if value is ABSENT:
                continue
            if position is None:
                raise _undeclared_direction(
                    layout.concrete, view_layout.slots[slot].relationship, node
                )
            row[position] = self._arm(value)
        return tuple(row)

    def state(self, view: ResolutionView, handle: NodeHandle) -> SnapshotNodeState:
        """One node's Snapshot state, built in allocation order.

        Every handle resolves to its final instance here, so a narrowed view that
        points back at an ancestor closes without any partially built object
        having been exposed.

        As-of axes are family-wide, so the concrete's shared Temporal Shape is
        what a temporal node retains for :func:`~parallax.snapshot.edge_of` to
        read its milestone starts against, at the family root's own Attribute
        Identities.
        """
        del handle
        root = cast("RootView", self._root)
        node = self._pending
        self._pending = node + 1
        concrete = root.layout(node).concrete
        shape = self._temporal.shape(concrete)
        return SnapshotNodeState(
            entity=concrete,
            views={
                name: self._resolved(view, value)
                for slot, name in root.view_layout(node).narrowed_views
                if (value := root.view(node, slot)) is not ABSENT
            },
            root_conformance=self._conformance,
            pin=pin_for_shape(shape, root.pin),
            edge_cache=None if isinstance(shape, NonTemporal) else shape,
            read_evidence=root.origin(node),
        )

    def _arm(self, value: object) -> object:
        """A carried arm as handles: a tuple is loaded-many, ``None`` is
        loaded-null, and a lone node is loaded-one."""
        handles = self._handles
        if type(value) is tuple:
            return tuple([handles[node] for node in cast("tuple[int, ...]", value)])
        if value is None:
            return None
        return handles[cast("int", value)]

    def _resolved(self, view: ResolutionView, value: object) -> object:
        """A carried arm as the instances its handles resolve to."""
        handles = self._handles
        if type(value) is tuple:
            return tuple([view.resolve(handles[node]) for node in cast("tuple[int, ...]", value)])
        if value is None:
            return None
        return view.resolve(handles[cast("int", value)])


def _undeclared_direction(
    entity: EntityIdentity, relationship: RelationshipIdentity, index: int
) -> GraphConstructionError:
    """The refusal for a loaded view naming a direction ``entity`` does not declare.

    A positional row is written at declared positions, so the name a view carries
    is checked where it becomes one — and in the writer's own vocabulary, because
    what the caller sees is one graph construction failing, not two error surfaces
    depending on which side of the translation noticed.
    """
    return GraphConstructionError(
        code="entity-graph-invalid-member",
        message=(
            f"{entity.canonical} declares no relationship {relationship!r}, "
            "and a loaded view carries one"
        ),
        index=index,
        identity=relationship,
    )
