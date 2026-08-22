"""``parallax.conformance.another_source`` — a second framework-managed source.

`m-unit-work` *Write value provenance* defines a framework-managed source as one
managed value lifecycle: the machinery that materializes values from reads and
attaches to each the state by which it later recognizes its own. The Snapshot
runtime is exactly one such lifecycle (ADR 0010), so no read it performs answers
a value some OTHER source produced — which is the provenance a case states as
`anotherSource` (`m-case-format` *Keyed write action steps*).

This module is the second source, supplied by the adapter rather than shipped:
:class:`AnotherSource` runs its own query through the shared find executor and
then materializes what that read returned ITSELF — its own merge over the
the sealed graph a read answered, its own Entity Graph Construction drive, and
per-node state, which the Snapshot never attached and therefore never claims.
:meth:`AnotherSource.produced` is the definition's other half: a source
recognizes its own. So a value arranged here is a value a managed read of a
second source produced, which is the antecedent the ForeignLifecycle rule states
rather than a stand-in for it.

It shares its Database Port with the source under test deliberately. A
connection is not a source, and any number of them over one lifecycle are one
source (`m-unit-work`); what separates two sources is which one materialized the
value and whose state it carries, so a second connection would witness nothing a
shared one does not.

Materialization covers flat graphs — attributes and Value Objects, no
relationship views — which is the whole of what the write-value corpus reads. A
deep fetch is refused at the query, before any I/O, rather than read and then
materialized without the levels it asked for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from parallax.core.db_port import DbPort
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity import (
    DomainModel,
    EntityAttributeInput,
    EntityGraphWriter,
    NodeHandle,
    ValueObjectAttributeInput,
    ValueObjectOccurrenceInput,
    ValueObjectRecord,
    graph_construction_of,
    lifecycle_state_of,
)
from parallax.core.entity._model import cataloged_model
from parallax.core.metamodel import (
    Multiplicity,
    NestedValueObjectMetadata,
    ValueObjectMetadata,
)
from parallax.core.object_query._fluent import ObjectQuery, object_query_node
from parallax.snapshot.handle import find as execute_read
from parallax.snapshot.materialize import (
    GraphMerge,
    SnapshotGraph,
    merge_graph_input,
    require_publishable,
)
from parallax.snapshot.materialize._graph import ABSENT

__all__ = ["AnotherSource"]

_VoContainer = ValueObjectMetadata | NestedValueObjectMetadata


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

    __slots__ = ("_dialect", "_domain", "_model", "_port")

    def __init__(self, model: DomainModel, port: DbPort, *, dialect: Dialect = POSTGRES) -> None:
        self._domain = model
        self._model = cataloged_model(model)
        self._port = port
        self._dialect = dialect

    def find[S](self, query: ObjectQuery[Any, S]) -> tuple[S, ...]:
        """Every root ``query`` matches, materialized by THIS source.

        A real read: the canonical Object Query runs through the same find
        executor the developer surface runs, so what comes back is rows this
        source read and instances this source built from them.

        An eager fetch is refused here, before any I/O: this source populates no
        relationship view, so reading a query's levels and then dropping them
        would answer a graph the caller did not ask for.
        """
        node = object_query_node(query)
        if node.includes:
            raise ValueError(
                "this source materializes flat graphs only, and the query includes "
                "a relationship level"
            )
        result = execute_read(node, self._model, self._dialect, self._port)
        return cast("tuple[S, ...]", self._materialize(result.graph))

    def produced(self, value: object) -> bool:
        """Whether THIS source materialized ``value``.

        State another source attached — or no managed state at all — answers
        ``False``, which is what makes recognition a source's own question rather
        than a test for managed-ness in general.
        """
        state = lifecycle_state_of(value)
        return isinstance(state, _AnotherSourceState) and state.source is self

    def _materialize(self, graph: SnapshotGraph) -> tuple[object, ...]:
        """``graph``'s roots as instances carrying this source's own state.

        Every relationship slot is left to the writer's unloaded sentinel: a
        level-free read carries no merged view to install, which :meth:`find`
        guarantees by refusing a deep fetch.

        The translation from the merge's compact rows into the writer's carriers
        is this source's OWN, deliberately: what makes a second source second is
        that it merges, translates, and constructs for itself rather than
        borrowing the Snapshot materializer's private drive. Both translations
        die together when the writer takes compact rows directly.
        """
        merge = merge_graph_input(graph)
        require_publishable(merge)

        def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
            handles = [writer.allocate(identity) for identity in merge.order]
            for index, handle in enumerate(handles):
                writer.populate(handle, *_carriers(merge, index), ())
            return tuple(handles[index] for index in merge.roots if index is not None)

        return graph_construction_of(self._domain).construct(
            build, state_factory=lambda _view, _handle: _AnotherSourceState(self)
        )


def _carriers(
    merge: GraphMerge, node: int
) -> tuple[tuple[EntityAttributeInput, ...], tuple[ValueObjectOccurrenceInput, ...]]:
    """One merged node's member row as the writer's Attribute and Value Object
    carriers. A position no read carried contributes no entry, which is what the
    carrier algebra means by absence."""
    layout = merge.layout(node)
    values = merge.member_values(node)
    attributes = tuple(
        EntityAttributeInput(attribute.identity, values[position])
        for position, attribute in enumerate(layout.attributes)
        if values[position] is not ABSENT
    )
    occurrences = tuple(
        ValueObjectOccurrenceInput(occurrence.identity, _occurrence(values[position], occurrence))
        for position, occurrence in enumerate(layout.occurrences, start=layout.attribute_count)
        if values[position] is not ABSENT
    )
    return attributes, occurrences


def _occurrence(
    value: object, declared: _VoContainer
) -> ValueObjectRecord | tuple[ValueObjectRecord, ...] | None:
    if declared.multiplicity is Multiplicity.MANY:
        rows = cast("tuple[object, ...]", value) if isinstance(value, tuple) else ()
        return tuple(_record(cast("tuple[object, ...]", row), declared) for row in rows)
    if value is None:
        return None
    return _record(cast("tuple[object, ...]", value), declared)


def _record(row: tuple[object, ...], declared: _VoContainer) -> ValueObjectRecord:
    return ValueObjectRecord(
        attributes=tuple(
            ValueObjectAttributeInput(leaf.identity, row[position])
            for position, leaf in enumerate(declared.attributes)
            if row[position] is not ABSENT
        ),
        value_objects=tuple(
            ValueObjectOccurrenceInput(nested.identity, _occurrence(row[position], nested))
            for position, nested in enumerate(
                declared.value_objects, start=len(declared.attributes)
            )
            if row[position] is not ABSENT
        ),
    )
