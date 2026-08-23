"""The shared sealed-graph fixture the graph suites drive.

A read driver composes a graph by converting rows into a graph builder and
writing each level's views as that level lands. These suites need the same
composition without a database, so this builds one the same way — through
``convert_row`` and ``GraphBuilder`` — rather than hand-assembling rows that no
driver would produce.

``materialize`` then runs the production materializer over it, which is what makes
these suites cover the real seam: merge, allocate, populate, and the per-node state
factory, with no stand-in anywhere.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from parallax.core import DomainModel
from parallax.core.entity import graph_construction_of
from parallax.core.entity._layout import EntityLayout, LayoutCatalog
from parallax.core.entity._model import class_index, model_of
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    EntityIdentity,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    RelationshipIdentity,
    ValueObjectMetadata,
    entity_by_name,
)
from parallax.core.temporal_read import Pin
from parallax.snapshot.handle._materializer import materialize_graph
from parallax.snapshot.materialize import (
    InvalidData,
    RelationshipViewKey,
    SnapshotGraph,
)
from parallax.snapshot.materialize._convert import LevelContext, convert_row
from parallax.snapshot.materialize._graph import ABSENT, GraphBuilder
from parallax.snapshot.materialize._views import ROOT_LEVEL, ViewSchema

__all__ = [
    "GraphFixture",
    "documents_of",
    "identity_of",
    "invalid_record",
    "layout_of",
    "rendered_members",
    "rendered_occurrence",
]

_VoContainer = ValueObjectMetadata | NestedValueObjectMetadata

_NO_PIN = Pin()


def invalid_record(published: object) -> InvalidData[object]:
    """The classified record ``published`` is, narrowed for the assertions on it.

    A published root is typed as widely as the roots it may hold, so narrowing it
    by ``isinstance`` alone leaves the record's own element type unknown under
    pyright strict. Naming the narrowing once keeps every assertion site reading
    as a claim about the record rather than about the type checker.
    """
    assert isinstance(published, InvalidData), published
    return cast("InvalidData[object]", published)


def identity_of(model: Metamodel, name: str) -> EntityIdentity:
    """``name``'s accepted Entity Identity within ``model``."""
    metadata = entity_by_name(model, name)
    assert metadata is not None, name
    return metadata.identity


def documents_of(model: Metamodel, identity: EntityIdentity) -> tuple[ValueObjectMetadata, ...]:
    """The document contributors an instance-form read of ``identity`` projects."""
    position = inheritance_view(model).entity(identity)
    assert position is not None, identity
    return tuple(position.applicable_value_objects)


def layout_of(model: Metamodel, identity: EntityIdentity) -> EntityLayout:
    """``identity``'s member layout under ``model``, for a suite converting rows
    without a connection to reach that model's own catalog through."""
    return LayoutCatalog(model).entity(identity)


def rendered_members(layout: EntityLayout, values: tuple[object, ...]) -> dict[str, object]:
    """One member row by declared member name, ``ABSENT`` positions omitted.

    The rendering IS the positional walk every consumer of a row makes, so a name
    absent from it is a position the row holds ``ABSENT`` at — which is what lets
    an assertion state what a read carried without spelling an index.
    """
    rendered: dict[str, object] = {
        attribute.identity.name: values[position]
        for position, attribute in enumerate(layout.attributes)
        if values[position] is not ABSENT
    }
    rendered.update(
        {
            occurrence.identity.path[-1]: rendered_occurrence(values[position], occurrence)
            for position, occurrence in enumerate(layout.occurrences, start=layout.attribute_count)
            if values[position] is not ABSENT
        }
    )
    return rendered


def rendered_occurrence(value: object, declared: _VoContainer) -> object:
    """One occurrence slot by declared member name at every depth: ``None`` for a
    collapsed One, a tuple of mappings for a Many, a mapping otherwise."""
    if declared.multiplicity is Multiplicity.MANY:
        rows = cast("tuple[object, ...]", value) if isinstance(value, tuple) else ()
        return tuple(_occurrence_row(cast("tuple[object, ...]", row), declared) for row in rows)
    return None if value is None else _occurrence_row(cast("tuple[object, ...]", value), declared)


def _occurrence_row(row: tuple[object, ...], declared: _VoContainer) -> dict[str, object]:
    rendered: dict[str, object] = {
        leaf.identity.name: row[position]
        for position, leaf in enumerate(declared.attributes)
        if row[position] is not ABSENT
    }
    rendered.update(
        {
            nested.identity.path[-1]: rendered_occurrence(row[position], nested)
            for position, nested in enumerate(
                declared.value_objects, start=len(declared.attributes)
            )
            if row[position] is not ABSENT
        }
    )
    return rendered


class GraphFixture:
    """One graph under construction, plus the materialization over it.

    ``views`` are the relationship views this graph attaches, declared up front
    because a projection's view row is sized when the row is added and a fan-back
    only names a slot the plan already fixed. A broad view is its relationship's
    own spelling; a narrowed one is that spelling paired with the derived view
    key. They all sit on one unguarded source level, which is the shape
    :meth:`ViewSchema.of` exists for: it lets a suite state a graph with no plan,
    no executor, and no database, at the cost of every projection carrying every
    declared slot rather than only its own level's.

    ``model`` overrides the accepted model conversion and merging read without
    changing the classes construction resolves, which is how a suite exercises a
    model and its classes disagreeing — a member the model calls a Value Object
    while the composed class maps it as a scalar. Only a test can reach that
    state: the composition root always takes both facts off one Domain Model.

    Named apart from the production ``GraphBuilder`` it drives, so a suite that
    holds both reads which one it is talking to.
    """

    __slots__ = ("_builder", "_domain", "_layouts", "_model", "_sealed")

    def __init__(
        self,
        domain: DomainModel,
        *views: str | tuple[str, str],
        model: Metamodel | None = None,
    ) -> None:
        assert class_index(domain) is not None, "the graph suites compose class-backed models"
        self._domain = domain
        self._model = model if model is not None else model_of(domain)
        self._layouts = LayoutCatalog(self._model)
        self._builder = GraphBuilder(ViewSchema.of(*map(self._declared, views)))
        self._sealed: tuple[tuple[tuple[int, ...], Pin], SnapshotGraph] | None = None

    def _declared(self, view: str | tuple[str, str]) -> RelationshipViewKey:
        """One declared view: a broad one is a spelling, a narrowed one a pair."""
        if isinstance(view, str):
            return self.view_key(view)
        relationship, narrowed = view
        return self.view_key(relationship, narrowed=narrowed)

    @property
    def builder(self) -> GraphBuilder:
        """The production builder this fixture accumulates into."""
        return self._builder

    def node(self, entity: str, columns: Mapping[str, object]) -> int:
        """Convert one row of ``entity`` exactly as a level of a read would."""
        identity = identity_of(self._model, entity)
        context = LevelContext(self._layouts.entity(identity), documents_of(self._model, identity))
        return convert_row(dict(columns), context, self._builder, source=ROOT_LEVEL)

    def layout_for(self, entity: str) -> EntityLayout:
        """``entity``'s member layout under this fixture's own accepted model."""
        return self._layouts.entity(identity_of(self._model, entity))

    def view_key(self, relationship: str, *, narrowed: str | None = None) -> RelationshipViewKey:
        """One view key, spelled ``Owner.name`` at its declaring position, with
        ``narrowed`` naming the derived view key of a narrowed hop."""
        owner, _, name = relationship.rpartition(".")
        return RelationshipViewKey(
            RelationshipIdentity(identity_of(self._model, owner), name), narrowed
        )

    def attach(
        self,
        parent: int,
        relationship: str,
        value: int | tuple[int, ...] | None,
        *,
        narrowed: str | None = None,
    ) -> None:
        """Write one relationship view onto an already-converted projection."""
        self._builder.write_view(parent, self.view_key(relationship, narrowed=narrowed), value)

    def graph(self, *roots: int, pin: Pin = _NO_PIN) -> SnapshotGraph:
        """The whole sealed graph, roots in the order given.

        Sealing invalidates the builder, so a fixture seals ONCE and answers the
        graph it sealed thereafter — which is what lets a test read a merge and
        then materialize the same graph. A suite wanting a second graph builds a
        second fixture, the same discipline a read executor keeps.
        """
        asked = (roots, pin)
        if self._sealed is None:
            self._sealed = (asked, self._builder.seal(roots, pin))
        assert self._sealed[0] == asked, "one fixture seals one graph; build a second fixture"
        return self._sealed[1]

    def materialize(
        self, *roots: int, pin: Pin = _NO_PIN
    ) -> tuple[object | InvalidData[object], ...]:
        """Merge, classify, and publish this graph's roots.

        A conforming root is its frozen Entity instance; one some stored state
        contradicted is its :class:`InvalidData` record instead.
        """
        return materialize_graph(
            self.graph(*roots, pin=pin), self._model, graph_construction_of(self._domain)
        )
