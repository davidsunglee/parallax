"""The shared Snapshot Graph Input builder the graph suites drive.

A read driver composes a graph input by converting rows into a merge scope and
attaching each level's views as that level lands. These suites need the same
composition without a database, so this builds one the same way — through
``convert_row`` and ``MergeScope`` — rather than hand-assembling carriers that no
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
from parallax.core.entity._model import class_index, model_of
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    EntityIdentity,
    Metamodel,
    RelationshipIdentity,
    ValueObjectMetadata,
    entity_by_name,
)
from parallax.core.temporal_read import Pin
from parallax.snapshot.handle._materializer import materialize_graph
from parallax.snapshot.materialize import (
    InvalidData,
    LevelContext,
    MergeScope,
    RelationshipViewKey,
    SnapshotGraphInput,
    SnapshotNodeInput,
    SnapshotNodeRef,
    convert_row,
)

__all__ = ["GraphBuilder", "documents_of", "identity_of", "invalid_record"]

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


class GraphBuilder:
    """One graph input under construction, plus the materialization over it.

    ``model`` overrides the accepted model conversion and merging read without
    changing the classes construction resolves, which is how a suite exercises a
    model and its classes disagreeing — a member the model calls a Value Object
    while the composed class maps it as a scalar. Only a test can reach that
    state: the composition root always takes both facts off one Domain Model.
    """

    __slots__ = ("_domain", "_model", "_scope")

    def __init__(self, domain: DomainModel, model: Metamodel | None = None) -> None:
        assert class_index(domain) is not None, "the graph suites compose class-backed models"
        self._domain = domain
        self._model = model if model is not None else model_of(domain)
        self._scope = MergeScope(self._model)

    def node(self, entity: str, columns: Mapping[str, object]) -> SnapshotNodeRef:
        """Convert one row of ``entity`` exactly as a level of a read would."""
        identity = identity_of(self._model, entity)
        context = LevelContext(identity, documents_of(self._model, identity))
        return convert_row(dict(columns), context, self._scope)

    def input_of(self, ref: SnapshotNodeRef) -> SnapshotNodeInput:
        """The converted projection ``ref`` names."""
        return self._scope.node(ref)

    def attach(
        self,
        parent: SnapshotNodeRef,
        relationship: str,
        value: SnapshotNodeRef | tuple[SnapshotNodeRef, ...] | None,
        *,
        narrowed: str | None = None,
    ) -> None:
        """Attach one relationship view, spelled ``Owner.name`` at its declaring
        position, with ``narrowed`` naming the derived view key of a narrowed hop."""
        owner, _, name = relationship.rpartition(".")
        view = RelationshipViewKey(
            RelationshipIdentity(identity_of(self._model, owner), name), narrowed
        )
        self._scope.attach(parent, view, value)

    def graph(self, *roots: SnapshotNodeRef, pin: Pin = _NO_PIN) -> SnapshotGraphInput:
        """The whole graph input, roots in the order given."""
        return self._scope.build(roots, pin)

    def materialize(
        self, *roots: SnapshotNodeRef, pin: Pin = _NO_PIN
    ) -> tuple[object | InvalidData[object], ...]:
        """Merge, classify, and publish this graph's roots.

        A conforming root is its frozen Entity instance; one some stored state
        contradicted is its :class:`InvalidData` record instead.
        """
        return materialize_graph(
            self.graph(*roots, pin=pin), self._model, graph_construction_of(self._domain)
        )
