"""The neutral materializer: one merged graph into class-free nodes and views.

A PEER of :mod:`parallax.snapshot.handle._materializer`, not a wrapper of it.
Both consume the same :class:`~parallax.snapshot.materialize.GraphMerge`; neither
calls the other, and a typed read constructs nothing defined here. What differs
is only what a merged node becomes: frozen Entity instances there, and here the
:class:`NeutralNodeView` a caller with no compiled Entity Class can still read.

The scope placement is the containment argument, not a filing convenience. This
module names ``m-unit-work``'s Observation Key, which the row-to-graph scope
already reaches through ``m-deep-fetch --> m-navigate``, and names no Read Trace —
so it stays inside the grant that withholds ``m-sql``, exactly as the typed
materializer does. The result that PAIRS a neutral output with its Read Trace is
:class:`~parallax.snapshot._read_result.NeutralReadResult`, in the sibling scope
that declares the provenance edge.

Value Object occurrences are **declared-member filled**: the projection walks the
declared member lists rather than the stored carrier's keys, writing ``None`` for
an absent leaf or ``one`` and ``()`` for an absent ``many``. A
:class:`NeutralNodeView` is the neutral analogue of the typed GETTER SURFACE, not
of the carrier — `m-value-object` requires a getter for every declared inner
member at every depth, while `m-document-codec`'s presence preservation governs
the carrier — so a consumer renders what it is handed and owns no projection rule
of its own.

Identity is by object, deliberately: :class:`NeutralNode` and
:class:`NeutralNodeView` compare by identity rather than by value, so a diamond or
a cycle is observable as the SAME object reached twice. Value equality would also
not terminate on a cycle, and reference identity is what a graph consumer
actually asks about.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from parallax.core.entity._graph_input import ValueObjectRecord
from parallax.core.inheritance import family_variant_name
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    PrimaryKey,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import ObjectKey, ObservationKey
from parallax.snapshot.materialize._input import RelationshipViewKey
from parallax.snapshot.materialize._merge import GraphMerge, MergedNode

__all__ = [
    "NeutralGraph",
    "NeutralGraphs",
    "NeutralNode",
    "NeutralNodeView",
    "NeutralReadOutput",
    "NeutralRelationshipView",
    "NeutralRows",
    "NeutralValue",
    "ObservationKeying",
    "neutral_graph",
    "neutral_graphs",
    "neutral_rows",
]

_VoContainer = ValueObjectMetadata | NestedValueObjectMetadata

type NeutralValue = Mapping[str, object] | tuple[Mapping[str, object], ...] | None
"""One Value Object occurrence's declared-member-filled value: a name-keyed
mapping for a ``one`` occurrence (``None`` when the whole composite is absent),
and an ordered tuple of them for a ``many`` occurrence (``()`` when absent).
Nested occurrences appear inside a mapping under the same rule, at every depth."""

type NeutralRelationshipView = NeutralNodeView | tuple[NeutralNodeView, ...] | None
"""One LOADED relationship view: ``None`` is loaded-null, a view is a loaded
to-one, and a tuple is a loaded to-many whose order is semantic and whose
emptiness is loaded-empty. Omitting the key from
:attr:`NeutralNodeView.relationships` is what means unloaded."""

type ObservationKeying = Callable[
    [ObjectKey, Mapping[AttributeIdentity, object]], ObservationKey | None
]
"""How a node learns the slot the active unit of work filed its observation
under, given the object identity this module already derived and the node's own
member values.

Supplying one *is* the decision to carry observation keys, exactly as supplying an
``ObservationCollector`` is the decision to observe: a standalone read passes
none and its nodes carry none. The POLICY — which targets are observed at all,
and whether the slot is qualified by a milestone — belongs to the unit of work and
stays with the caller that has it. The object identity travels IN rather than
being re-derived there, so a node's anchor and the slot it names can only ever be
keyed one way."""


@dataclass(frozen=True, slots=True, eq=False)
class NeutralNode:
    """One logical graph node's shared identity anchor.

    Every projection of one logical node resolves to the SAME instance, so a
    diamond and a back-reference cycle are observable as reference identity
    rather than as re-derived equality. It carries identity and nothing
    projected: the values live on the :class:`NeutralNodeView` that names it.

    ``observation_key`` is the slot the active unit of work filed this row's
    Write Observation under, and is absent for a standalone read and for a target
    the unit of work observes nothing of.
    """

    entity: EntityIdentity
    object_key: ObjectKey
    observation_key: ObservationKey | None = None


@dataclass(frozen=True, slots=True, eq=False)
class NeutralNodeView:
    """One logical node's projected state — the neutral analogue of the typed
    getter surface.

    ``attributes`` and ``value_objects`` are keyed by structured identity, like
    every other carrier in this package, so no consumer has to invert a physical
    column name back to a member. ``primary_key`` names the family-declared
    primary-key Attributes in declaration order, which is what a consumer
    truncating a cycle renders as its identity-only stub. ``family_variant`` is
    the node's stable wire spelling when it participates in an inheritance
    family, and absent otherwise.

    ``relationships`` is a live read-only view of a mapping the builder fills
    after every view of the graph exists: a cycle closes on a view that is
    already constructed, which no eagerly-populated frozen record could express.
    Consumers see an immutable mapping either way.
    """

    node: NeutralNode
    primary_key: tuple[AttributeIdentity, ...]
    family_variant: str | None
    attributes: Mapping[AttributeIdentity, object]
    value_objects: Mapping[ValueObjectIdentity, NeutralValue]
    relationships: Mapping[RelationshipViewKey, NeutralRelationshipView]


@dataclass(frozen=True, slots=True)
class NeutralRows:
    """A read's row-form output: every transformed row, in result order.

    Each row is an immutable mapping keyed as the read PROJECTED it — physical
    columns plus the synthetic ``familyVariant`` where the compiled read
    materializes one — after production's own row transform and before any wire
    rendering. Iterating the value iterates its rows.
    """

    rows: tuple[Mapping[str, object], ...]

    def __iter__(self) -> Iterator[Mapping[str, object]]:
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)


@dataclass(frozen=True, slots=True)
class NeutralGraph:
    """A read's graph-form output: the root views in result order, plus the
    whole-graph pin every node was read at."""

    roots: tuple[NeutralNodeView, ...]
    pin: Pin


@dataclass(frozen=True, slots=True)
class NeutralGraphs:
    """A milestone-set read's output: one pinned graph per milestone, in
    chronological edge order. Iterating the value iterates its graphs."""

    graphs: tuple[NeutralGraph, ...]

    def __iter__(self) -> Iterator[NeutralGraph]:
        return iter(self.graphs)

    def __len__(self) -> int:
        return len(self.graphs)


type NeutralReadOutput = NeutralRows | NeutralGraph | NeutralGraphs
"""What a neutral read answers, by the form its request selected."""


def neutral_rows(rows: Iterable[Mapping[str, object]]) -> NeutralRows:
    """``rows`` as the detached, immutable row-form output."""
    return NeutralRows(tuple(MappingProxyType(dict(row)) for row in rows))


def neutral_graph(
    merge: GraphMerge, model: Metamodel, *, observed: ObservationKeying | None = None
) -> NeutralGraph:
    """``merge``'s allocation order as one neutral graph.

    Two passes over the merge's own order, for the reason the typed materializer
    allocates before it populates: every view exists before any relationship is
    filled, so a cycle closes on a complete object and the whole graph publishes
    at once or not at all.
    """
    nodes = [merge.node(index) for index in range(len(merge.order))]
    pending: list[dict[RelationshipViewKey, NeutralRelationshipView]] = []
    views: list[NeutralNodeView] = []
    for merged in nodes:
        relationships: dict[RelationshipViewKey, NeutralRelationshipView] = {}
        pending.append(relationships)
        views.append(_view(merged, model, relationships, observed))
    for merged, relationships in zip(nodes, pending, strict=True):
        for view in merged.views:
            relationships[view.view] = _relationship(view.value, views)
    return NeutralGraph(tuple(views[index] for index in merge.roots), merge.pin)


def neutral_graphs(graphs: Iterable[NeutralGraph]) -> NeutralGraphs:
    """``graphs`` as the milestone-set output, in the order given."""
    return NeutralGraphs(tuple(graphs))


def _relationship(
    value: int | tuple[int, ...] | None, views: list[NeutralNodeView]
) -> NeutralRelationshipView:
    """One merged view's arm resolved against the graph's own views.

    The arm travels in the value's SHAPE (`_merge`): a tuple is loaded-many,
    ``None`` is loaded-null, and a lone allocation index is loaded-one.
    """
    if isinstance(value, tuple):
        return tuple(views[index] for index in value)
    if value is None:
        return None
    return views[value]


def _view(
    merged: MergedNode,
    model: Metamodel,
    relationships: Mapping[RelationshipViewKey, NeutralRelationshipView],
    observed: ObservationKeying | None,
) -> NeutralNodeView:
    entity = merged.concrete_entity
    members: dict[AttributeIdentity, object] = {
        entry.identity: entry.value for entry in merged.attributes
    }
    declared = _declared_value_objects(model, entity)
    object_key = _object_key(model, entity, members)
    return NeutralNodeView(
        node=NeutralNode(
            entity=entity,
            object_key=object_key,
            observation_key=None if observed is None else observed(object_key, members),
        ),
        primary_key=tuple(attribute.identity for attribute in _primary_key(model, entity)),
        family_variant=_family_variant(model, entity),
        attributes=MappingProxyType(members),
        value_objects=MappingProxyType(
            {
                entry.identity: _occurrence(entry.value, declared[entry.identity])
                for entry in merged.value_objects
                if entry.identity in declared
            }
        ),
        relationships=relationships,
    )


def _occurrence(
    value: ValueObjectRecord | tuple[ValueObjectRecord, ...] | None, declared: _VoContainer
) -> NeutralValue:
    """One occurrence entry as its declared-member-filled neutral value."""
    if declared.multiplicity is Multiplicity.MANY:
        records = value if isinstance(value, tuple) else ()
        return tuple(_members(record, declared) for record in records)
    return None if value is None else _members(value, declared)


def _members(record: ValueObjectRecord | object, declared: _VoContainer) -> Mapping[str, object]:
    """One occurrence record as every DECLARED member, absence filled.

    The walk is over the declared member lists rather than the record's own
    entries, which is the whole difference between the getter surface and the
    carrier: a leaf the stored document omitted reads ``None`` here, an absent
    ``one`` occurrence reads ``None``, and an absent ``many`` reads ``()`` —
    while the carrier keeps recording that it held none of them.
    """
    leaves = (
        {entry.identity: entry.value for entry in record.attributes}
        if isinstance(record, ValueObjectRecord)
        else {}
    )
    nested = (
        {entry.identity: entry.value for entry in record.value_objects}
        if isinstance(record, ValueObjectRecord)
        else {}
    )
    filled: dict[str, object] = {}
    for leaf in declared.attributes:
        filled[leaf.identity.name] = leaves.get(leaf.identity)
    for occurrence in declared.value_objects:
        filled[occurrence.identity.path[-1]] = _occurrence(
            nested.get(occurrence.identity), occurrence
        )
    return MappingProxyType(filled)


def _declared_value_objects(
    model: Metamodel, entity: EntityIdentity
) -> Mapping[ValueObjectIdentity, ValueObjectMetadata]:
    position = inheritance_view(model).entity(entity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return {}
    return {occurrence.identity: occurrence for occurrence in position.applicable_value_objects}


def _object_key(
    model: Metamodel, entity: EntityIdentity, members: Mapping[AttributeIdentity, object]
) -> ObjectKey:
    """This node's object identity, derived exactly as a keyed write derives its
    own: the row's OWN resolved concrete Entity, never family-normalized, paired
    with the family-declared primary key's ``(name, value)`` pairs in declaration
    order (`m-unit-work`)."""
    return ObjectKey(
        entity,
        tuple(
            (attribute.identity.name, members.get(attribute.identity))
            for attribute in _primary_key(model, entity)
        ),
    )


def _primary_key(model: Metamodel, entity: EntityIdentity) -> tuple[AttributeMetadata, ...]:
    """The family root's declared primary-key Attributes, in declaration order.

    Family-declared because the primary key is root-owned and inherited members
    reach a concrete descendant under their own declaring identity
    (`m-inheritance`), which is exactly how a merged node keys them.
    """
    root = _family_root(model, entity)
    if root is None:  # pragma: no cover - a family root is always accepted
        return ()
    return tuple(
        attribute
        for attribute in root.declared_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    )


def _family_root(model: Metamodel, entity: EntityIdentity) -> EntityMetadata | None:
    position = inheritance_view(model).entity(entity)
    return model.entity(entity if position is None else position.root)


def _family_variant(model: Metamodel, entity: EntityIdentity) -> str | None:
    """``entity``'s stable wire variant spelling, or absence for a standalone
    Entity.

    An inheritance participant's position carries a root-owned strategy and a
    standalone Entity's carries none, so the participation test is the strategy
    itself rather than a second enumeration of the family.
    """
    facet = inheritance_view(model)
    position = facet.entity(entity)
    if position is None or position.strategy is None:
        return None
    return family_variant_name(facet, entity)
