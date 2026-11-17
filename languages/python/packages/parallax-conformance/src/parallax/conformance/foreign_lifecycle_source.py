from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from parallax.core import ObjectQuery
from parallax.core._execution._publication import read_projection
from parallax.core._execution._read_query import resolve_read_query
from parallax.core.execution_lifecycle._activity import INERT
from parallax.core.internal.db_port import DatabaseConnection
from parallax.core.internal.entity import lifecycle_state_of
from parallax.core.internal.entity._authored_resolver import object_query_node
from parallax.core.internal.execution import ModelSelection
from parallax.core.internal.read_delivery._page import Page
from parallax.core.internal.read_delivery._page_reader import PageReadContext, read_page
from parallax.core.internal.read_delivery._read_plan import ReadPlanCache
from parallax.snapshot._publication._graph_view import GraphView
from parallax.snapshot._publication._root_publication import publish_roots, require_publishable

__all__ = ["ForeignLifecycleSource"]


@dataclass(frozen=True, slots=True)
class _ForeignLifecycleState:
    """The per-node state one :class:`ForeignLifecycleSource` attaches to every
    value it materializes.

    It carries the source itself, which is how that source later recognizes its
    own. The production classifier reads none of that — it reads only that the
    lifecycle slot holds state this Snapshot did not attach — so the reference is
    the SECOND lifecycle's own machinery rather than anything the rule under test
    consults.
    """

    source: ForeignLifecycleSource


class ForeignLifecycleSource:
    """One managed value lifecycle over a store, distinct from the Snapshot's.

    Construct one per store and reuse it: the values it answers are recognized by
    the instance that materialized them, exactly as a lifecycle recognizes its
    own.
    """

    __slots__ = ("_construction", "_domain_model", "_model", "_port")

    def __init__(self, selection: ModelSelection, port: DatabaseConnection) -> None:
        selected = read_projection(selection)
        if selected.construction is None:
            raise ValueError(
                "this source materializes Entity Class instances, so it takes a selection "
                "prepared from a class-backed Domain Model"
            )
        self._domain_model = selection.model
        self._model = selected.model
        self._construction = selected.construction
        self._port = port

    def find[S](self, query: ObjectQuery[Any, S]) -> tuple[S, ...]:
        """Every root ``query`` matches, materialized by THIS source.

        A real read: the canonical Object Query is planned and read through the
        same Page reader the developer surface runs, so what comes back is rows
        this source read and instances this source built from them. It
        publishes no write evidence, so the Page retains no origin.

        An eager fetch is refused here, before any I/O: this source populates no
        relationship view, so reading a query's levels and then dropping them
        would answer a result missing the relationships the caller asked for.
        """
        node = object_query_node(query, self._domain_model)
        if node.includes:
            raise ValueError(
                "this source materializes root-only Pages, and the query includes "
                "a relationship level"
            )
        validated = resolve_read_query(node, model=self._model.meta)
        plan = ReadPlanCache(0).plan(
            edition="",
            model=self._model,
            dialect=self._port.dialect,
            query=validated,
            preference=None,
        )
        result = read_page(plan, PageReadContext(self._port, INERT))
        return cast("tuple[S, ...]", self._materialize(result.page))

    def materialized(self, value: object) -> bool:
        """Whether THIS source materialized ``value``.

        State another source attached — or no managed state at all — answers
        ``False``, which is what makes recognition a source's own question rather
        than a test for managed-ness in general.
        """
        state = lifecycle_state_of(value)
        return isinstance(state, _ForeignLifecycleState) and state.source is self

    def _materialize(self, page: Page) -> tuple[object, ...]:
        """Publish Page roots through the shared seam using this source's state.

        The Root View is the graph handed over: a root-only Page carries no
        relationship view, so every relationship of every node publishes
        unloaded.
        """
        construction = self._construction
        state = _ForeignLifecycleState(self)

        def lifecycle_states(instances: Sequence[object]) -> tuple[object, ...]:
            return (state,) * len(instances)

        def publish(root: GraphView, _ordinal: int) -> tuple[object, ...]:
            require_publishable(root)
            return (construction.publish(root, lifecycle_states),)

        return tuple(publish_roots(page, publish, self._model.meta))
