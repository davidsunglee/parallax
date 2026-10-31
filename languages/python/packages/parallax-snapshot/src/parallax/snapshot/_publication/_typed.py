from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Final, cast

from parallax.core import temporal_read
from parallax.core.entity import EntityGraphConstruction
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.read_delivery._page import ABSENT, InvalidData, VersionAttributes
from parallax.core.temporal_read import Bitemporal, NonTemporal, Pin, TransactionTimeOnly
from parallax.snapshot._inspection import (
    NodeProvenance,
    PageProvenance,
    RootConformance,
    SnapshotNodeState,
    pin_for_shape,
)
from parallax.snapshot._publication._classify import ConformingRoot, classify_root
from parallax.snapshot._publication._root import RootView

__all__ = ["TypedRootPublisher"]

_NO_VIEWS: Final[Mapping[str, object]] = MappingProxyType({})


class TypedRootPublisher:
    """One Page's Typed root publisher: classify each root, then publish the
    nodes of a root that hydrates as one Entity graph.

    The Root View is the graph Entity Graph Construction publishes: node ``i``
    becomes instance ``i``, its broad relationship values name nodes, and one
    call answers every node's Snapshot state once every instance exists. The
    model's facts are bound for the Page; the Root View and the root's
    conformance are one root's, set when its call begins and released when it
    ends.

    ``versions`` names the explicit version Attribute a classified record
    publishes. Provenance and the states of nodes nothing distinguishes are
    shared across the Page's roots and released with the publisher.
    """

    __slots__ = (
        "_conformance",
        "_construction",
        "_model",
        "_provenance",
        "_root",
        "_shared_states",
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
        self._provenance = PageProvenance()
        self._shared_states: dict[NodeProvenance, SnapshotNodeState] = {}

    def __call__(self, root: RootView, ordinal: int) -> tuple[object | InvalidData[object], ...]:
        """``root`` published at result ``ordinal``: as itself when it conforms,
        and otherwise as its record, carrying its value when it hydrates."""
        # The lifecycle-states callback is bound per call rather than held: a held
        # bound method would leave this publisher reachable only through a cycle,
        # keeping the Root View and its Page rows alive past the pass.
        self._root = root
        try:
            verdict = classify_root(root, self._model, self._versions, ordinal=ordinal)
            if isinstance(verdict, ConformingRoot):
                self._conformance = RootConformance.CONFORMING
                return (self._construction.publish(root, self._lifecycle_states),)
            self._conformance = RootConformance.NONCONFORMING
            if verdict.node is None:
                return (verdict.published(None),)
            return (verdict.published(self._construction.publish(root, self._lifecycle_states)),)
        finally:
            self._root = None

    def _lifecycle_states(self, instances: Sequence[object]) -> list[SnapshotNodeState]:
        """Every node's Snapshot state, in node order.

        Every instance exists and is filled by now, so a narrowed view resolves
        to final instances by node index, including one pointing back at an
        ancestor.

        As-of axes are family-wide, so the concrete's shared Temporal Shape is
        what a temporal node retains for :func:`~parallax.snapshot.edge_of` to
        read its milestone starts against, at the family root's own Attribute
        Identities. A temporal node therefore owns its state, as does a node
        with a narrowed view or Read Evidence; any other node shares one state
        per provenance across the Page.
        """
        root = cast("RootView", self._root)
        conformance = self._conformance
        provenance_for = self._provenance.provenance_for
        shared_states = self._shared_states
        shape_of = self._temporal.shape
        root_pin = root.pin
        layout_of = root.layout
        view_layout_of = root.view_layout
        view_of = root.view
        read_evidence_of = root.read_evidence
        states: list[SnapshotNodeState] = []
        last: EntityIdentity | None = None
        provenance: NodeProvenance | None = None
        pin: Pin | None = None
        edge_cache: TransactionTimeOnly | Bitemporal | None = None
        shared: SnapshotNodeState | None = None
        for node in range(len(instances)):
            concrete = layout_of(node).concrete
            if concrete is not last:
                last = concrete
                shape = shape_of(concrete)
                pin = pin_for_shape(shape, root_pin)
                edge_cache = None if isinstance(shape, NonTemporal) else shape
                provenance = provenance_for(concrete, conformance, pin)
                shared = None
                if edge_cache is None:
                    shared = shared_states.get(provenance)
                    if shared is None:
                        shared = shared_states.setdefault(
                            provenance, SnapshotNodeState(provenance, _NO_VIEWS)
                        )
            narrowed = view_layout_of(node).narrowed_views
            views = (
                {
                    name: _resolved(instances, value)
                    for slot, name in narrowed
                    if (value := view_of(node, slot)) is not ABSENT
                }
                if narrowed
                else None
            )
            read_evidence = read_evidence_of(node)
            if read_evidence is not None:
                states.append(
                    SnapshotNodeState(
                        NodeProvenance(concrete, conformance, pin, read_evidence),
                        views or _NO_VIEWS,
                        edge_cache,
                    )
                )
            elif shared is not None and not views:
                states.append(shared)
            else:
                states.append(
                    SnapshotNodeState(
                        cast("NodeProvenance", provenance), views or _NO_VIEWS, edge_cache
                    )
                )
        return states


def _resolved(instances: Sequence[object], value: object) -> object:
    """A carried view value as the instances its nodes became: a tuple is
    loaded-many, ``None`` is loaded-null, and a lone node is loaded-one."""
    if type(value) is tuple:
        return tuple([instances[node] for node in cast("tuple[int, ...]", value)])
    if value is None:
        return None
    return instances[cast("int", value)]
