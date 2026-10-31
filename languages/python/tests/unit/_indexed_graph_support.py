"""A node-indexed graph spelled node by node, and its publication.

Entity Graph Construction publishes any :class:`~parallax.core.entity.IndexedGraph`;
production hands it a Root View. A suite grading construction itself, or needing
a value some lifecycle materialized without a read, spells the graph as literal
rows instead, so the alignment between the rows and the layout is something the
suite can be wrong about.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from parallax.core.entity import DomainModel, EntityGraphConstruction
from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import EntityIdentity
from tests._support.model_capabilities import graph_construction_for

__all__ = ["LiteralGraph", "Node", "literal_graph", "published", "published_nodes"]

type Node = tuple[EntityIdentity, object, object]
"""One node: its concrete Entity, its member row, and its relationship row."""


@dataclass(frozen=True, slots=True)
class LiteralGraph:
    """An indexed graph whose every answer is a literal held per node."""

    layouts: tuple[EntityLayout, ...]
    members: tuple[object, ...]
    relationships: tuple[object, ...]

    def __len__(self) -> int:
        return len(self.layouts)

    def layout(self, node: int) -> EntityLayout:
        return self.layouts[node]

    def member_values(self, node: int) -> Any:
        return self.members[node]

    def relationship_values(self, node: int) -> Any:
        return self.relationships[node]


def literal_graph(construction: EntityGraphConstruction, *nodes: Node) -> LiteralGraph:
    """``nodes`` laid out against ``construction``'s own model layouts."""
    layouts = construction.cataloged.layouts
    return LiteralGraph(
        layouts=tuple(layouts.entity(entity) for entity, _, _ in nodes),
        members=tuple(members for _, members, _ in nodes),
        relationships=tuple(relationships for _, _, relationships in nodes),
    )


def published_nodes(
    model: DomainModel | EntityGraphConstruction,
    *nodes: Node,
    state: Callable[[object], object] | None = None,
) -> tuple[object, ...]:
    """Every instance one publication of ``nodes`` made, in node order.

    ``state`` answers each node's lifecycle state from its instance; without it
    every node is attached ``None``, which reads as no state at all.
    """
    construction = (
        model if isinstance(model, EntityGraphConstruction) else graph_construction_for(model)
    )
    seen: list[object] = []

    def lifecycle_states(instances: Sequence[object]) -> list[object]:
        seen.extend(instances)
        return [None if state is None else state(instance) for instance in instances]

    root = construction.publish(literal_graph(construction, *nodes), lifecycle_states)
    assert root is seen[0]
    return tuple(seen)


def published(
    model: DomainModel | EntityGraphConstruction,
    *nodes: Node,
    state: Callable[[object], object] | None = None,
) -> Any:
    """The root instance, node 0, of one publication of ``nodes``."""
    return published_nodes(model, *nodes, state=state)[0]
