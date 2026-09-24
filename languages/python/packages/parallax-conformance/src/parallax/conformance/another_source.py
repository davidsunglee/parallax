from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, cast

from parallax.core.db_port import DatabaseConnection
from parallax.core.entity import (
    UNLOADED,
    EntityGraphWriter,
    NodeHandle,
    lifecycle_state_of,
)
from parallax.core.object_query._fluent import ObjectQuery, object_query_node
from parallax.snapshot.handle import ModelSelection
from parallax.snapshot.handle import find as execute_read
from parallax.snapshot.handle._materialization import Materializer
from parallax.snapshot.handle._preflight import preflight
from parallax.snapshot.handle._publication import read_projection
from parallax.snapshot.materialize import (
    Page,
    RootView,
    require_publishable,
)

__all__ = ["AnotherSource"]


@dataclass(frozen=True, slots=True)
class _AnotherSourceState:
    """The per-node state one :class:`AnotherSource` attaches to every value it
    materializes.

    It carries the source itself, which is how that source later recognizes its
    own. The production classifier reads none of that — it reads only that the
    lifecycle slot holds state this Snapshot did not attach — so the reference is
    the SECOND lifecycle's own machinery rather than anything the rule under test
    consults.
    """

    source: AnotherSource


class AnotherSource:
    """One managed value lifecycle over a store, distinct from the Snapshot's.

    Construct one per store and reuse it: the values it answers are recognized by
    the instance that materialized them, exactly as a lifecycle recognizes its
    own.
    """

    __slots__ = ("_construction", "_model", "_port")

    def __init__(self, selection: ModelSelection, port: DatabaseConnection) -> None:
        selected = read_projection(selection)
        if selected.construction is None:
            raise ValueError(
                "this source materializes Entity Class instances, so it takes a selection "
                "prepared from a class-backed Domain Model"
            )
        self._model = selected.model
        self._construction = selected.construction
        self._port = port

    def find[S](self, query: ObjectQuery[Any, S]) -> tuple[S, ...]:
        """Every root ``query`` matches, materialized by THIS source.

        A real read: the canonical Object Query runs through the same find
        executor the developer surface runs, so what comes back is rows this
        source read and instances this source built from them.

        An eager fetch is refused here, before any I/O: this source populates no
        relationship view, so reading a query's levels and then dropping them
        would answer a result missing the relationships the caller asked for.
        """
        node = object_query_node(query)
        if node.includes:
            raise ValueError(
                "this source materializes root-only Pages, and the query includes "
                "a relationship level"
            )
        validated = preflight(node, model=self._model.meta, form="graph")
        result = execute_read(validated, self._model, self._port)
        return cast("tuple[S, ...]", self._materialize(result.page))

    def produced(self, value: object) -> bool:
        """Whether THIS source materialized ``value``.

        State another source attached — or no managed state at all — answers
        ``False``, which is what makes recognition a source's own question rather
        than a test for managed-ness in general.
        """
        state = lifecycle_state_of(value)
        return isinstance(state, _AnotherSourceState) and state.source is self

    def _materialize(self, page: Page) -> tuple[object, ...]:
        """Publish Page roots through the shared seam using this source state."""

        def publish(root: RootView, _position: int) -> Iterator[object]:
            require_publishable(root)

            def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
                handles = [writer.allocate(identity) for identity in root.order]
                for index, handle in enumerate(handles):
                    writer.populate(
                        handle,
                        root.member_values(index),
                        (UNLOADED,) * len(root.layout(index).relationships),
                    )
                return tuple(handles[index] for index in root.roots if index is not None)

            yield from self._construction.construct(
                build, state_factory=lambda _view, _handle: _AnotherSourceState(self)
            )

        return tuple(Materializer().roots(page, publish))
