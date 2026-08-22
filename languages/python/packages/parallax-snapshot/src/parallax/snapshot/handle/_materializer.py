"""``parallax.snapshot.handle._materializer`` — a sealed Snapshot graph into frozen nodes.

Private handle implementation, never re-exported: ``_read`` is its only caller,
and the frozen graphs it builds reach callers as :class:`~parallax.snapshot.handle.Snapshot`
roots.

It owns nothing about carriers, identity, merging, or root classification —
:mod:`parallax.snapshot.materialize` settles all four before this module runs —
and nothing about Pydantic, cycle
closure, or the private lifecycle slot, which
:class:`~parallax.core.entity.EntityGraphConstruction` owns. What is left is the
thin translation between them: merge state in, ``allocate`` / ``populate`` calls
out, and one :class:`~parallax.snapshot._inspection.SnapshotNodeState` per node
built in the state factory, where every handle resolves to its final instance.
Building the state there is what closes a cyclic narrowed view without exposing a
partial object.

Construction covers the classified scope rather than the whole merge: a node no
publishable root reaches is never allocated, so atomic publication keeps meaning
*everything constructible publishes together, or nothing does*. Each root then
leaves here as itself or as its :class:`~parallax.snapshot.materialize.InvalidData`
record — the classification decided which; this module only fills a hydrated
root's ``data``.

A merged view's shape carries its own arm: a tuple is loaded-many (empty included),
``None`` is loaded-null, and a lone allocation index is loaded-one. A slot reading
``ABSENT`` names nothing, and the writer installs the private unloaded sentinel —
which is what makes the closed world structural rather than a convention this
module has to restate.

It also owns the translation into Entity Graph Construction's own carriers. The
writer takes an entry per member, so a node's Attributes, Value Object
occurrences, and broad relationship arms are synthesized from its compact row
immediately before its ``populate`` call and are dead as soon as it returns:
``populate`` folds them into local dicts and writes their values into the
instance, retaining none of them. Peak carrier cost is therefore one node's
worth whatever the graph's size, and nothing here is retained by Snapshot or the
merge.

Hashability is conditional, exactly per spec §3: nothing here makes a node hashable
or guards against one — a back-reference closing a cycle makes the derived hash
non-terminating, so such nodes are shareable but not hashable.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from types import MappingProxyType
from typing import cast

from parallax.core.entity import LOADED_NULL as _LOADED_NULL
from parallax.core.entity import (
    EntityAttributeInput,
    EntityGraphConstruction,
    EntityGraphWriter,
    EntityRelationshipInput,
    LoadedMany,
    LoadedOne,
    NodeHandle,
    RelationshipInput,
    ResolutionView,
    ValueObjectAttributeInput,
    ValueObjectOccurrenceInput,
    ValueObjectRecord,
)
from parallax.core.entity._layout import EntityLayout
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    ValueObjectMetadata,
)
from parallax.core.temporal_read import Edge, milestone_edge_of
from parallax.core.unit_work import SourceHint
from parallax.snapshot._inspection import SnapshotNodeState
from parallax.snapshot.materialize import (
    ClassifiedRoot,
    ConformingRoot,
    GraphClassification,
    GraphMerge,
    InvalidData,
    SnapshotGraph,
    classify_roots,
    merge_graph_input,
)
from parallax.snapshot.materialize._graph import ABSENT

__all__ = ["materialize_graph"]

_VoContainer = ValueObjectMetadata | NestedValueObjectMetadata


def materialize_graph(
    graph: SnapshotGraph,
    model: Metamodel,
    construction: EntityGraphConstruction,
    *,
    ordinal_offset: int = 0,
    sources: Mapping[int, SourceHint] = MappingProxyType({}),
) -> tuple[object | InvalidData[object], ...]:
    """Merge ``graph``, classify its roots, and construct the ones that hydrate.

    Every constructible node is allocated before any is populated, so a cycle
    closes on an object that already exists, and everything constructible
    publishes at once or not at all.

    ``ordinal_offset`` is where this graph's roots start in the ordered result the
    caller publishes, which is nonzero only where one Snapshot spans several
    graphs. ``sources`` is the Source Hint the executor retained per projection,
    which each node's own Snapshot state carries so a later keyed write reads its
    evidence off the value it was handed.
    """
    merge = merge_graph_input(graph)
    return _Materialization(
        merge,
        model,
        classify_roots(merge, model, ordinal_offset=ordinal_offset),
        merge.by_allocation(sources),
    ).run(construction)


class _Materialization:
    """One graph's construction drive: the merge, its classification, and the two
    callbacks over them.

    Between the two callbacks it retains the allocation handles and nothing else.
    A node's own writer carriers are synthesized from the merge at the callback
    that needs them and die with it, so no payload is accumulated into a second
    graph-sized structure beside the sealed graph and the merge itself.
    """

    __slots__ = (
        "_classification",
        "_handles",
        "_merge",
        "_model",
        "_pending",
        "_scope",
        "_sources",
    )

    def __init__(
        self,
        merge: GraphMerge,
        model: Metamodel,
        classification: GraphClassification,
        sources: Mapping[int, SourceHint],
    ) -> None:
        self._merge = merge
        self._model = model
        self._classification = classification
        self._sources = sources
        self._scope = tuple(
            index for index in range(len(merge.order)) if index not in classification.excluded
        )
        self._handles: dict[int, NodeHandle] = {}
        self._pending = iter(self._scope)

    def run(
        self, construction: EntityGraphConstruction
    ) -> tuple[object | InvalidData[object], ...]:
        return self._published(construction.construct(self.build, state_factory=self.state))

    def build(self, writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = self._merge.order
        self._handles = {index: writer.allocate(order[index]) for index in self._scope}
        for index in self._scope:
            layout = self._merge.layout(index)
            values = self._merge.member_values(index)
            writer.populate(
                self._handles[index],
                _attributes(layout, values),
                _value_objects(layout, values),
                self._broad_arms(index),
            )
        return tuple(
            self._handles[root.node] for root in self._classification.roots if root.node is not None
        )

    def _broad_arms(self, index: int) -> tuple[EntityRelationshipInput, ...]:
        """One node's loaded BROAD views as writer arms.

        A narrowed view is a read-time presentation of a direction the broad view
        already carries, so only the broad slot becomes a relationship the writer
        installs; the narrowed ones are resolved into instances in
        :meth:`state`. A slot reading ``ABSENT`` names nothing, so the writer
        installs its own unloaded sentinel there.
        """
        return tuple(
            EntityRelationshipInput(key.relationship, self._arm(value))
            for slot, key in enumerate(self._merge.view_layout(index).slots)
            if key.narrowed_view is None and (value := self._merge.view(index, slot)) is not ABSENT
        )

    def _published(
        self, constructed: tuple[object, ...]
    ) -> tuple[object | InvalidData[object], ...]:
        """Each result root as itself or as its record, in result order.

        A conforming graph hands the constructed roots over untouched, so the
        common case allocates no wrapper at all.
        """
        if self._classification.conforming:
            return constructed
        instances = iter(constructed)
        return tuple(
            next(instances) if isinstance(root, ConformingRoot) else _record(root, instances)
            for root in self._classification.roots
        )

    def state(self, view: ResolutionView, handle: NodeHandle) -> SnapshotNodeState:
        """One node's Snapshot state, built in allocation order.

        Every handle resolves to its final instance here, so a narrowed view that
        points back at an ancestor closes without any partially built object
        having been exposed.
        """
        del handle
        index = next(self._pending)
        edge = self._edge(index)
        return SnapshotNodeState(
            entity=self._merge.layout(index).concrete,
            views={
                key.narrowed_view: self._resolved(view, value)
                for slot, key in enumerate(self._merge.view_layout(index).slots)
                if key.narrowed_view is not None
                and (value := self._merge.view(index, slot)) is not ABSENT
            },
            pin=self._merge.pin if edge is not None else None,
            edge=edge,
            source=self._sources.get(index),
        )

    def _arm(self, value: object) -> RelationshipInput:
        return _by_arm(
            value,
            null=_LOADED_NULL,
            one=lambda index: LoadedOne(self._handles[index]),
            many=lambda indices: LoadedMany(tuple(self._handles[index] for index in indices)),
        )

    def _resolved(self, view: ResolutionView, value: object) -> object:
        return _by_arm(
            value,
            null=None,
            one=lambda index: view.resolve(self._handles[index]),
            many=lambda indices: tuple(view.resolve(self._handles[index]) for index in indices),
        )

    def _edge(self, index: int) -> Edge | None:
        """One node's milestone edge, or absence for a non-temporal family.

        As-of axes are family-wide metadata declared on the family root, so the
        interval members are read at the root's own Attribute Identities — the
        identities an inherited member reaches every concrete descendant under.
        """
        layout = self._merge.layout(index)
        declaring = _declaring(self._model, layout.concrete)
        if declaring is None or not declaring.declared_as_of_axes:
            return None
        values = self._merge.member_values(index)
        return milestone_edge_of(
            declaring,
            {
                attribute.identity: values[position]
                for position, attribute in enumerate(layout.attributes)
                if values[position] is not ABSENT
            },
        )


def _record(root: ClassifiedRoot, instances: Iterator[object]) -> InvalidData[object]:
    """One classified root's published record.

    A hydrating root takes the next constructed instance, in the same order its
    handle was answered; a non-hydrating one takes nothing at all, which is what
    keeps the two iterators aligned without an index.
    """
    return root.published(None if root.node is None else next(instances))


def _by_arm[T](
    value: object,
    *,
    null: T,
    one: Callable[[int], T],
    many: Callable[[tuple[int, ...]], T],
) -> T:
    """Dispatch on a merged view's arm — the one place its shape is read.

    A merged view carries its arm in its shape (`_merge`): a tuple is
    loaded-many, ``None`` is loaded-null, and a lone allocation index is
    loaded-one. Every consumer of an arm goes through here, so adding an arm is
    one cascade to change rather than one per consumer.
    """
    if isinstance(value, tuple):
        return many(cast("tuple[int, ...]", value))
    if value is None:
        return null
    return one(cast("int", value))


def _declaring(model: Metamodel, identity: EntityIdentity) -> EntityMetadata | None:
    """The position declaring ``identity``'s family-wide temporal facts — its family
    root, which for a standalone Entity is itself."""
    position = inheritance_view(model).entity(identity)
    return model.entity(identity if position is None else position.root)


# --------------------------------------------------------------------------- #
# One node's compact row as Entity Graph Construction's own carriers.          #
# --------------------------------------------------------------------------- #


def _attributes(
    layout: EntityLayout, values: tuple[object, ...]
) -> tuple[EntityAttributeInput, ...]:
    """One node's carried Attributes as writer carriers.

    An absent position contributes no entry, which is what the writer's own
    algebra means by absence — the carriers admit no sentinel value.
    """
    return tuple(
        EntityAttributeInput(attribute.identity, values[position])
        for position, attribute in enumerate(layout.attributes)
        if values[position] is not ABSENT
    )


def _value_objects(
    layout: EntityLayout, values: tuple[object, ...]
) -> tuple[ValueObjectOccurrenceInput, ...]:
    """One node's carried Value Object occurrences as writer carriers."""
    return tuple(
        ValueObjectOccurrenceInput(occurrence.identity, _occurrence(values[position], occurrence))
        for position, occurrence in enumerate(layout.occurrences, start=layout.attribute_count)
        if values[position] is not ABSENT
    )


def _occurrence(
    value: object, declared: _VoContainer
) -> ValueObjectRecord | tuple[ValueObjectRecord, ...] | None:
    """One occurrence slot as the writer's record algebra.

    The declared multiplicity decides the shape rather than the value does: a One
    slot's member row and a Many slot's tuple of them are both tuples, and only
    the declaration distinguishes them.
    """
    if declared.multiplicity is Multiplicity.MANY:
        return tuple(
            _value_object(cast("tuple[object, ...]", row), declared) for row in _rows(value)
        )
    if value is None:
        return None
    return _value_object(cast("tuple[object, ...]", value), declared)


def _rows(value: object) -> tuple[object, ...]:
    return cast("tuple[object, ...]", value) if isinstance(value, tuple) else ()


def _value_object(row: tuple[object, ...], declared: _VoContainer) -> ValueObjectRecord:
    """One positional member row as one writer record, at every depth."""
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
