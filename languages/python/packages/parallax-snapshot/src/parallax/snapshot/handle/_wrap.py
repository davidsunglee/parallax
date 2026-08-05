"""``parallax.snapshot.handle._wrap`` — the Snapshot Graph Materializer (spec §3/§4).

Private handle implementation, never re-exported through
``parallax.snapshot.handle``'s own ``__init__.py``: ``_read`` is its only caller,
and the frozen graphs it builds reach callers as ``Snapshot`` roots.

It turns one materialized neutral graph
(:class:`~parallax.snapshot.materialize.Node`) into frozen Entity instances by
driving :meth:`~parallax.core.entity.EntityGraphConstruction.construct` — it owns
no Pydantic mechanics, no cycle-closure trick, and no private instance slot of
its own. What it owns is everything lifecycle-specific:

- **graph-local identity**, resolved here and keyed by the LOGICAL identity triple
  (:func:`~parallax.snapshot.materialize.identity_key`: family-normalized name
  plus primary key — coordinate-omitted, safe within one graph's single pin),
  never by a neutral ``Node``'s python identity. One discovery pass walks the
  whole per-view forest, groups every ``Node`` by that key, and unions each
  group's contributors first-seen-wins, so a diamond's later sibling contributes
  its own loaded relationships and attribute superset rather than losing them.
  The per-view ``Node`` dicts are never mutated;
- the **allocation order** construction is stated over: the discovery pass's
  first-encounter preorder is the order this module issues ``allocate`` calls in,
  so nothing recomputes an index that the writer already owns;
- the mapping from physical storage keys to **structured identities** — the sole
  ``wire_names_of`` importer's job, now expressed as Attribute, Value Object, and
  Relationship Identities rather than Python member names;
- the per-node :class:`~parallax.snapshot._inspection.SnapshotNodeState` built in
  the state factory, where every handle resolves to its final instance. Building
  it there is what closes a cyclic narrowed view without exposing a partial
  object.

Polymorphic children materialize as their CONCRETE classes: ``familyVariant``,
when the neutral row carries it, names the concrete entity directly; a
single-resolved-position level (no ``familyVariant`` key) uses the node's own
``~parallax.snapshot.materialize.Node.resolved_entity`` instead. The caller's
declared relationship target survives only as the last-resort default for a
defensively hand-built ``Node`` carrying no ``resolved_entity``.

Hashability is conditional, exactly per spec §3: nothing here makes a node
hashable or guards against one — a back-reference closing a cycle makes the
derived hash non-terminating, so such nodes are shareable but not hashable.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from parallax.core import inheritance, relationship
from parallax.core.entity import LOADED_NULL as _LOADED_NULL
from parallax.core.entity import UNLOADED_VIEW as _UNLOADED_VIEW
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
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    ValueObjectMetadata,
    entity_by_name,
)
from parallax.core.relationship import RelationshipMetadata
from parallax.core.temporal_read import Pin, milestone_edge
from parallax.snapshot import materialize
from parallax.snapshot._inspection import SnapshotNodeState

__all__ = ["wrap_graph"]


def wrap_graph(
    nodes: Sequence[materialize.Node],
    root_entity: str,
    model: Metamodel,
    pin: Pin,
    runtime: EntityGraphConstruction,
) -> tuple[object, ...]:
    """Wrap one materialized graph's root nodes — and, transitively, everything
    reachable through them — into frozen Entity instances, attaching the SAME
    whole-graph ``pin`` to every temporal node reached.

    Two passes over the neutral forest, then one construction: discovery groups
    every ``Node`` by logical identity and fixes the allocation order, the merge
    unions each group's contributors, and ``construct`` allocates every shell
    before populating any of them so a cycle closes on an existing object.
    """
    discovery = _Discovery(model=model)
    for node in nodes:
        discovery.walk(node, root_entity)
    graph = _Graph(
        model=model,
        pin=pin,
        order=tuple(discovery.groups),
        entities=discovery.entities,
        merged=_merged_fields(discovery.groups),
        roots=tuple(discovery.key(node, root_entity) for node in nodes),
    )
    return runtime.construct(graph.build, state_factory=graph.state)


# --------------------------------------------------------------------------- #
# Discovery: logical identity, first-encounter preorder, and the merged view.  #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _MergedNode:
    fields: Mapping[str, object]
    value_objects: Mapping[str, object]
    relationships: Mapping[str, object]


class _Discovery:
    """The one walk of the whole per-view neutral forest.

    ``groups`` is insertion-ordered by first encounter, which is exactly the
    deterministic allocation preorder: roots in result order, then each node's
    relationships in accepted declaration order, the broad view before that
    relationship's narrowed views, and children in to-many result order.
    """

    __slots__ = ("entities", "groups", "model", "visited")

    model: Metamodel
    groups: dict[object, list[materialize.Node]]
    entities: dict[object, EntityMetadata]
    visited: set[int]

    def __init__(self, model: Metamodel) -> None:
        self.model = model
        self.groups = {}
        self.entities = {}
        self.visited = set()

    def key(self, node: materialize.Node, default_entity: str) -> object:
        """``node``'s logical identity key — the family-normalized name plus
        primary key, or the node's own python identity for an Entity declaring
        no primary key (none exists in the corpus today)."""
        concrete = _concrete_entity_name(node, default_entity)
        return materialize.identity_key(self.model, concrete, node.fields) or id(node)

    def walk(self, node: materialize.Node, default_entity: str) -> None:
        """Group everything reachable from ``node`` by logical key.

        ``visited`` guards a back-reference cycle, where the assembler reuses the
        SAME ancestor object; two sibling levels reaching one row are two
        different objects and both join the group.
        """
        node_id = id(node)
        if node_id in self.visited:
            return
        self.visited.add(node_id)
        concrete = _concrete_entity_name(node, default_entity)
        key = materialize.identity_key(self.model, concrete, node.fields) or node_id
        self.groups.setdefault(key, []).append(node)
        entity = _entity(self.model, concrete)
        self.entities.setdefault(key, entity)
        for direction in _relationships(self.model, entity):
            target = direction.join.target.entity.canonical
            name = direction.identity.name
            if name in node.relationships:
                self._walk_related(node.relationships[name], target)
            prefix = f"{name}["
            for view_key, value in node.relationships.items():
                if view_key.startswith(prefix):
                    self._walk_related(value, target)

    def _walk_related(self, value: object, default_entity: str) -> None:
        if value is None:
            return
        if isinstance(value, list):
            for item in cast("list[object]", value):
                self.walk(cast("materialize.Node", item), default_entity)
            return
        self.walk(cast("materialize.Node", value), default_entity)


def _merged_fields(groups: Mapping[object, list[materialize.Node]]) -> dict[object, _MergedNode]:
    """One union view per logical key: every key present on ANY sibling ``Node``
    contributes, first-seen (discovery order) winning where more than one carries
    it, so a relationship or narrowed view loaded on two paths wires exactly once
    and an attribute superset is never lost."""
    merged: dict[object, _MergedNode] = {}
    for key, members in groups.items():
        fields: dict[str, object] = {}
        value_objects: dict[str, object] = {}
        relationships: dict[str, object] = {}
        for member in members:
            for name, value in member.fields.items():
                fields.setdefault(name, value)
            for name, value in member.value_objects.items():
                value_objects.setdefault(name, value)
            for name, value in member.relationships.items():
                relationships.setdefault(name, value)
        merged[key] = _MergedNode(fields, value_objects, relationships)
    return merged


# --------------------------------------------------------------------------- #
# The construction drive.                                                      #
# --------------------------------------------------------------------------- #


class _Graph:
    """Everything one ``construct`` call holds constant, plus the two callbacks.

    ``order`` position *is* the allocation index: this module issues the
    ``allocate`` calls in that order, and lifecycle-state factories are invoked in
    the same order, which is what lets the state callback name the node it is
    building state for without reading anything off an opaque handle.
    """

    __slots__ = (
        "entities",
        "merged",
        "model",
        "narrowed",
        "order",
        "pending",
        "pin",
        "roots",
        "slots",
    )

    model: Metamodel
    pin: Pin
    order: tuple[object, ...]
    entities: Mapping[object, EntityMetadata]
    merged: Mapping[object, _MergedNode]
    roots: tuple[object, ...]
    slots: dict[object, int]
    narrowed: dict[object, dict[str, object]]
    pending: Iterator[object]

    def __init__(
        self,
        model: Metamodel,
        pin: Pin,
        order: tuple[object, ...],
        entities: Mapping[object, EntityMetadata],
        merged: Mapping[object, _MergedNode],
        roots: tuple[object, ...],
    ) -> None:
        self.model = model
        self.pin = pin
        self.order = order
        self.entities = entities
        self.merged = merged
        self.roots = roots
        self.slots = {key: index for index, key in enumerate(order)}
        self.narrowed = {}
        self.pending = iter(order)

    def build(self, writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handles = [writer.allocate(self.entities[key].identity) for key in self.order]
        for key, handle in zip(self.order, handles, strict=True):
            entity = self.entities[key]
            merged = self.merged[key]
            writer.populate(
                handle,
                _attributes(self.model, entity, merged.fields),
                _value_objects(self.model, entity, merged.value_objects),
                self._relationships(key, entity, merged, handles),
            )
        return tuple(handles[self.slots[key]] for key in self.roots)

    def state(self, view: ResolutionView, handle: NodeHandle) -> SnapshotNodeState:
        """One node's Snapshot state, built in allocation order.

        Every handle resolves to its final instance here, so a narrowed view that
        points back at an ancestor closes without any partially built object
        having been exposed.
        """
        del handle
        key = next(self.pending)
        entity = self.entities[key]
        views = {
            view_key: _resolved(view, value)
            for view_key, value in self.narrowed.get(key, {}).items()
        }
        declaring = _declaring(self.model, entity)
        temporal = bool(declaring.declared_as_of_axes)
        return SnapshotNodeState(
            entity=entity.identity,
            views=views,
            pin=self.pin if temporal else None,
            edge=milestone_edge(declaring, self.merged[key].fields) if temporal else None,
        )

    def _relationships(
        self,
        key: object,
        entity: EntityMetadata,
        merged: _MergedNode,
        handles: Sequence[NodeHandle],
    ) -> tuple[EntityRelationshipInput, ...]:
        """One node's broad relationship arms, collecting its narrowed views aside.

        A narrowed view never marks the broad relationship loaded, so it crosses
        no construction seam at all: it is kept here as handles and resolved into
        the node's own Snapshot state once every instance is final.
        """
        entries: list[EntityRelationshipInput] = []
        views: dict[str, object] = {}
        for direction in _relationships(self.model, entity):
            name = direction.identity.name
            target = direction.join.target.entity.canonical
            many = direction.cardinality.target is Multiplicity.MANY
            if name in merged.relationships:
                entries.append(
                    EntityRelationshipInput(
                        direction.identity,
                        self._arm(merged.relationships[name], target, many, handles),
                    )
                )
            else:
                entries.append(EntityRelationshipInput(direction.identity, _UNLOADED_VIEW))
            prefix = f"{name}["
            for view_key, value in merged.relationships.items():
                if view_key.startswith(prefix):
                    views[view_key] = self._view(value, target, handles)
        if views:
            self.narrowed[key] = views
        return tuple(entries)

    def _arm(
        self, value: object, target: str, many: bool, handles: Sequence[NodeHandle]
    ) -> RelationshipInput:
        if many:
            items = cast("list[object]", value) if isinstance(value, list) else []
            return LoadedMany(tuple(self._handle(item, target, handles) for item in items))
        if value is None:
            return _LOADED_NULL
        return LoadedOne(self._handle(value, target, handles))

    def _view(
        self, value: object, target: str, handles: Sequence[NodeHandle]
    ) -> NodeHandle | tuple[NodeHandle, ...] | None:
        if value is None:
            return None
        if isinstance(value, list):
            items = cast("list[object]", value)
            return tuple(self._handle(item, target, handles) for item in items)
        return self._handle(value, target, handles)

    def _handle(self, node: object, target: str, handles: Sequence[NodeHandle]) -> NodeHandle:
        neutral = cast("materialize.Node", node)
        concrete = _concrete_entity_name(neutral, target)
        key = materialize.identity_key(self.model, concrete, neutral.fields) or id(neutral)
        return handles[self.slots[key]]


def _resolved(view: ResolutionView, value: object) -> object:
    if value is None:
        return None
    if isinstance(value, tuple):
        return tuple(view.resolve(handle) for handle in cast("tuple[NodeHandle, ...]", value))
    return view.resolve(cast("NodeHandle", value))


# --------------------------------------------------------------------------- #
# Physical keys to structured identities — the one column-to-member mapping.   #
# --------------------------------------------------------------------------- #


def _attributes(
    model: Metamodel, entity: EntityMetadata, fields: Mapping[str, object]
) -> tuple[EntityAttributeInput, ...]:
    """The row's scalar contributors as structured Attribute entries.

    Keyed by each Attribute's own physical column, so a column belonging to a
    disjoint sibling of a shared table — or the synthetic family tag — contributes
    nothing rather than landing on a member that never declared it.
    """
    return tuple(
        EntityAttributeInput(attribute.identity, fields[attribute.storage.name])
        for attribute in _family_attributes(model, entity)
        if attribute.storage.name in fields
    )


def _value_objects(
    model: Metamodel, entity: EntityMetadata, documents: Mapping[str, object]
) -> tuple[ValueObjectOccurrenceInput, ...]:
    """The row's decoded documents as structured occurrence entries.

    A storage key is never reinterpreted as member identity: the occurrence is
    found by its own Storage Location and the entry is keyed by its Value Object
    Identity, which is why a document column may share a relationship's name
    without either overwriting the other.
    """
    return tuple(
        ValueObjectOccurrenceInput(
            occurrence.identity, _occurrence(documents[occurrence.storage.name], occurrence)
        )
        for occurrence in _family_value_objects(model, entity)
        if occurrence.storage.name in documents
    )


def _occurrence(
    value: object, declared: ValueObjectMetadata | NestedValueObjectMetadata
) -> ValueObjectRecord | tuple[ValueObjectRecord, ...] | None:
    if declared.multiplicity is Multiplicity.MANY:
        items = cast("list[object]", value) if isinstance(value, list) else []
        return tuple(_record(item, declared) for item in items if item is not None)
    if value is None:
        return None
    return _record(value, declared)


def _record(
    document: object, declared: ValueObjectMetadata | NestedValueObjectMetadata
) -> ValueObjectRecord:
    """One decoded document as the immutable record algebra, keyed by structured
    identity at every depth. No raw document mapping continues past here."""
    source = cast("Mapping[str, object]", document)
    return ValueObjectRecord(
        attributes=tuple(
            ValueObjectAttributeInput(leaf.identity, source[leaf.identity.name])
            for leaf in declared.attributes
            if leaf.identity.name in source
        ),
        value_objects=tuple(
            ValueObjectOccurrenceInput(
                nested.identity, _occurrence(source[nested.identity.path[-1]], nested)
            )
            for nested in declared.value_objects
            if nested.identity.path[-1] in source
        ),
    )


# --------------------------------------------------------------------------- #
# Accepted-model lookups.                                                      #
# --------------------------------------------------------------------------- #


def _concrete_entity_name(node: materialize.Node, default_entity: str) -> str:
    """``node``'s own concrete entity name: the assembler's statically resolved
    ``resolved_entity`` when it has one, else the caller's declared relationship
    target or root, which survives only as the defensive fallback for a hand-built
    ``Node`` no assembler populated."""
    return node.resolved_entity.canonical if node.resolved_entity is not None else default_entity


def _entity(model: Metamodel, name: str) -> EntityMetadata:
    metadata = entity_by_name(model, name)
    if metadata is None:  # pragma: no cover - a materialized row's concrete is always declared
        raise LookupError(f"{name!r} names no Entity of this model")
    return metadata


def _relationships(model: Metamodel, entity: EntityMetadata) -> tuple[RelationshipMetadata, ...]:
    """``entity``'s navigable relationship directions, INHERITED ones included.

    A relationship declared on an inheritance ancestor is reached by every concrete
    descendant under the ancestor's own relationship identity (`m-inheritance`
    "Inherited members"), and a descendant never redeclares it — so the navigable
    set is the ancestry chain's directions, root first, each name taken from the
    nearest declaration. A standalone Entity is its own whole chain, which makes
    this the identity for one.
    """
    facet = relationship.view(model)
    position = inheritance.view(model).entity(entity.identity)
    chain = tuple(position.ancestry) if position is not None else (entity.identity,)
    directions: list[RelationshipMetadata] = []
    seen: set[str] = set()
    for identity in chain:
        for direction in facet.relationships(identity) or ():
            if direction.identity.name not in seen:
                seen.add(direction.identity.name)
                directions.append(direction)
    return tuple(directions)


def _family_attributes(model: Metamodel, entity: EntityMetadata) -> tuple[AttributeMetadata, ...]:
    position = inheritance.view(model).entity(entity.identity)
    return (
        tuple(entity.declared_attributes)
        if position is None
        else tuple(position.applicable_attributes)
    )


def _family_value_objects(
    model: Metamodel, entity: EntityMetadata
) -> tuple[ValueObjectMetadata, ...]:
    position = inheritance.view(model).entity(entity.identity)
    return (
        tuple(entity.declared_value_objects)
        if position is None
        else tuple(position.applicable_value_objects)
    )


def _declaring(model: Metamodel, entity: EntityMetadata) -> EntityMetadata:
    """The position declaring ``entity``'s family-wide temporal facts — its family
    root, which for a standalone Entity is itself."""
    position = inheritance.view(model).entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return entity
    root = model.entity(position.root)
    return entity if root is None else root
