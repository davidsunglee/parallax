"""Entity Graph Construction — the advanced first-party graph-building collaboration.

Exposed from ``parallax.core.entity`` and deliberately **not** from top-level
``parallax.core``: it is the seam a lifecycle package builds a graph of frozen
Entity instances through, not developer surface.

The immutable carriers it is stated in live in the sibling
:mod:`parallax.core.entity._graph_input` scope, so a lifecycle package building
Snapshot Graph Input can be granted that algebra without being granted this
collaboration.

The collaboration owns everything about turning those carriers into Entity
and Value Object instances — concrete class selection, canonical-to-Python member
mapping, recursive Value Object construction, Pydantic's ``model_construct`` plus
the ``object.__setattr__`` backdoor, broad relationship-slot installation, the one
opaque lifecycle-state slot, and all-or-none publication. It owns nothing about
any lifecycle: it registers no callback, interprets no state value, and imports
no lifecycle package. A caller passes one build function and one optional state
factory per call, so two lifecycles coexist without either knowing the other.

Three non-overlapping phases, and the order is the contract rather than an
implementation detail:

1. **Allocate.** Every node's shell is allocated, in the caller's own
   ``allocate`` call order, which *is* the deterministic zero-based allocation
   index. Nothing recomputes that index; every node-indexed rejection reads it
   back from the writer.
2. **Populate.** The first ``populate`` closes allocation permanently. Each node
   is populated exactly once with its scalars, Value Objects, and broad
   relationship views. Allocating before populating is what lets a cycle close:
   a relationship arm names an already-allocated handle whose instance exists
   but is not yet filled.
3. **Lifecycle state.** Only after the build callback returns, every node is
   populated, and the roots validate, do the per-node state factories run — in
   allocation order, each with a fresh single-use resolution view. A factory
   therefore sees every final instance fully wired, including cycles, and sees no
   attached state and no published root.

Failure precedence follows the same fixed order. Writer-operation failures are
eager. A build-callback exception propagates unchanged and suppresses completion,
root, and factory work. After a successful callback the lowest unpopulated
allocation index fails first; only then are roots validated left to right; only
then do factories run, the first factory exception propagating unchanged and
stopping later ones. State attachment and root publication happen last and
together, so a failure anywhere publishes nothing and leaves every allocated
Entity unreachable and lifecycle-state-free.
"""

from __future__ import annotations

from collections.abc import Callable, Container, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

from parallax.core.base import INFINITY, NeutralType, Timestamp, matches_neutral_type
from parallax.core.entity._declaration import (
    LIFECYCLE_STATE_SLOT,
    ValueObjectShape,
    shape_of,
)
from parallax.core.entity._entity import wire_names_of
from parallax.core.entity._errors import GraphConstructionError
from parallax.core.entity._expressions import UNLOADED
from parallax.core.entity._graph_input import (
    UNLOADED_VIEW,
    EntityAttributeInput,
    EntityRelationshipInput,
    LoadedMany,
    LoadedNull,
    LoadedOne,
    NodeHandle,
    Unloaded,
    ValueObjectAttributeInput,
    ValueObjectOccurrenceInput,
    ValueObjectRecord,
)
from parallax.core.entity._model import ClassIndex, DomainModel, class_index, model_of
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    RelationshipIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.core.relationship import RelationshipMetadata
from parallax.core.relationship import view as relationship_view

__all__ = [
    "EntityGraphConstruction",
    "EntityGraphWriter",
    "ResolutionView",
    "graph_construction_of",
    "lifecycle_state_of",
    "relationship_value_of",
]


# --------------------------------------------------------------------------- #
# Per-Domain-Model derived facts                                               #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _EntityFacts:
    """Everything one Entity's construction needs, derived once from the accepted
    model and the Entity Class composed under it.

    Family-effective throughout: an inherited Attribute, Value Object, or
    relationship reaches a concrete subtype under its own declaring identity, so
    each map is keyed by that identity rather than by the concrete's.
    """

    identity: EntityIdentity
    cls: type
    attributes: tuple[AttributeMetadata, ...]
    attribute_py: Mapping[AttributeIdentity, str]
    attribute_meta: Mapping[AttributeIdentity, AttributeMetadata]
    open_ended: frozenset[AttributeIdentity]
    value_objects: tuple[ValueObjectMetadata, ...]
    value_object_py: Mapping[ValueObjectIdentity, str]
    value_object_class: Mapping[ValueObjectIdentity, type]
    relationship_py: Mapping[RelationshipIdentity, str]
    relationship_many: Mapping[RelationshipIdentity, bool]


def _entity_facts(model: Metamodel, classes: ClassIndex, identity: EntityIdentity) -> _EntityFacts:
    metadata = model.entity(identity)
    cls = classes.class_of(identity)
    if metadata is None or cls is None:
        raise GraphConstructionError(
            code="entity-graph-invalid-entity",
            message=(
                f"{identity.canonical} is not an Entity this Domain Model composed a class for"
            ),
            identity=identity,
        )
    position = inheritance_view(model).entity(identity)
    attributes = (
        tuple(metadata.declared_attributes)
        if position is None
        else tuple(position.applicable_attributes)
    )
    value_objects = (
        tuple(metadata.declared_value_objects)
        if position is None
        else tuple(position.applicable_value_objects)
    )
    names = wire_names_of(cls)
    attribute_py: dict[AttributeIdentity, str] = {}
    attribute_meta: dict[AttributeIdentity, AttributeMetadata] = {}
    for attribute in attributes:
        py_name = names.name_to_py.get(attribute.identity.name)
        if py_name is None:  # pragma: no cover - a composed class carries every family member
            continue
        attribute_py[attribute.identity] = py_name
        attribute_meta[attribute.identity] = attribute
    value_object_py: dict[ValueObjectIdentity, str] = {}
    value_object_class: dict[ValueObjectIdentity, type] = {}
    for occurrence in value_objects:
        py_name = names.name_to_py.get(occurrence.identity.path[-1])
        nested = None if py_name is None else names.vo_classes.get(py_name)
        if py_name is None or nested is None:  # pragma: no cover - as above
            continue
        value_object_py[occurrence.identity] = py_name
        value_object_class[occurrence.identity] = nested
    relationship_py: dict[RelationshipIdentity, str] = {}
    relationship_many: dict[RelationshipIdentity, bool] = {}
    for direction in _navigable_relationships(model, identity):
        py_name = names.relationship_py.get(direction.identity.name)
        # A sibling branch's relationship is navigable in the family namespace but
        # absent from this concrete's own MRO; it names no slot to install.
        if py_name is not None:  # pragma: no branch
            relationship_py[direction.identity] = py_name
        relationship_many[direction.identity] = direction.cardinality.target is Multiplicity.MANY
    return _EntityFacts(
        identity=identity,
        cls=cls,
        attributes=attributes,
        attribute_py=attribute_py,
        attribute_meta=attribute_meta,
        open_ended=_open_ended_attributes(model, identity),
        value_objects=value_objects,
        value_object_py=value_object_py,
        value_object_class=value_object_class,
        relationship_py=relationship_py,
        relationship_many=relationship_many,
    )


def _open_ended_attributes(
    model: Metamodel, identity: EntityIdentity
) -> frozenset[AttributeIdentity]:
    """The Attributes whose value space admits ``m-core``'s native infinity: each
    declared As-Of Axis's **end** Attribute, and nothing else.

    Infinity is the open upper bound of a temporal interval, so an axis's start
    Attribute — a finite instant like any other timestamp — is excluded even
    though both endpoints are framework-owned. The axes are family-wide metadata
    declared on the family root, reached here through the ancestry chain.
    """
    position = inheritance_view(model).entity(identity)
    chain = tuple(position.ancestry) if position is not None else (identity,)
    ends: set[AttributeIdentity] = set()
    for ancestor in chain:
        metadata = model.entity(ancestor)
        if metadata is not None:  # pragma: no branch - every ancestry member is accepted
            ends.update(axis.end_attribute for axis in metadata.declared_as_of_axes)
    return frozenset(ends)


def _navigable_relationships(
    model: Metamodel, identity: EntityIdentity
) -> tuple[RelationshipMetadata, ...]:
    """One Entity's navigable directions in accepted declaration order, ancestry
    first — the order the deterministic allocation preorder is stated over.

    A relationship declared on an inheritance ancestor is reached by every
    concrete descendant under the ancestor's own identity and is never
    redeclared, so the navigable set is the ancestry chain's directions with each
    name taken from the nearest declaration.
    """
    facet = relationship_view(model)
    position = inheritance_view(model).entity(identity)
    chain = tuple(position.ancestry) if position is not None else (identity,)
    directions: list[RelationshipMetadata] = []
    seen: set[str] = set()
    for ancestor in chain:
        for direction in facet.relationships(ancestor) or ():
            if direction.identity.name not in seen:
                seen.add(direction.identity.name)
                directions.append(direction)
    return tuple(directions)


# --------------------------------------------------------------------------- #
# Scopes and the writer                                                        #
# --------------------------------------------------------------------------- #


class _CallScope:
    """One ``construct(...)`` call's private state — the allocation-indexed arrays
    every phase reads back, and the handles naming them.

    Because a handle carries no state, belonging is a lookup here rather than a
    comparison there: a handle names a node exactly when this scope issued it,
    which is what makes a foreign handle and a value that is no handle at all one
    and the same miss.
    """

    __slots__ = ("_indices", "facts", "handles", "instances", "populated")

    def __init__(self) -> None:
        self.facts: list[_EntityFacts] = []
        self.handles: list[NodeHandle] = []
        self.instances: list[object] = []
        self.populated: list[bool] = []
        self._indices: dict[int, int] = {}

    def issue(self) -> NodeHandle:
        """A fresh handle naming the next allocation index."""
        handle = NodeHandle()
        self._indices[id(handle)] = len(self.handles)
        self.handles.append(handle)
        return handle

    def index_of(self, candidate: object) -> int | None:
        """``candidate``'s allocation index, or ``None`` when this construction
        issued no such handle. Every issued handle is retained, so no later object
        can take a dead handle's identity."""
        return self._indices.get(id(candidate))


def _index_of(scope: _CallScope, candidate: object, *, operation: str) -> int:
    """``candidate``'s allocation index in ``scope``, or the foreign-handle refusal.

    A value that is no handle at all is refused the same way a handle from
    another construction is: neither names a node this construction allocated.
    """
    index = scope.index_of(candidate)
    if index is None:
        raise GraphConstructionError(
            code="entity-graph-foreign-handle",
            message=f"{operation} accepts only a node handle this construction allocated",
        )
    return index


class EntityGraphWriter:
    """The allocate-then-populate surface one build callback drives.

    The writer closes when its build callback exits; using a retained closed
    writer raises ``entity-graph-scope-closed`` before any argument is inspected,
    so a smuggled writer cannot even report which argument was wrong.
    """

    __slots__ = ("_allocation_closed", "_construction", "_open", "_scope")

    def __init__(self, construction: EntityGraphConstruction, scope: _CallScope) -> None:
        self._construction = construction
        self._scope = scope
        self._open = True
        self._allocation_closed = False

    def allocate(self, entity: EntityIdentity) -> NodeHandle:
        """Allocate one node of ``entity`` and answer its handle.

        Call order *is* the deterministic zero-based allocation index. The shell
        exists immediately and is filled later, which is what lets a cycle close.
        """
        self._require_open()
        if self._allocation_closed:
            raise GraphConstructionError(
                code="entity-graph-allocation-closed",
                message=(
                    "allocation closed with the first populate(); every node is allocated "
                    "before any node is populated"
                ),
                index=len(self._scope.facts),
                identity=entity,
            )
        facts = self._construction.facts_for(entity)
        self._scope.facts.append(facts)
        self._scope.instances.append(_shell(facts))
        self._scope.populated.append(False)
        return self._scope.issue()

    def populate(
        self,
        handle: NodeHandle,
        attributes: tuple[EntityAttributeInput, ...],
        value_objects: tuple[ValueObjectOccurrenceInput, ...],
        relationships: tuple[EntityRelationshipInput, ...],
    ) -> None:
        """Fill one allocated node exactly once, closing allocation permanently.

        Every navigable relationship slot is installed here — a view no entry
        names becomes the private unloaded sentinel, which is what makes the
        closed world a structural fact rather than a convention.
        """
        self._require_open()
        self._allocation_closed = True
        index = _index_of(self._scope, handle, operation="populate")
        if self._scope.populated[index]:
            raise GraphConstructionError(
                code="entity-graph-node-already-populated",
                message="each allocated node is populated exactly once",
                index=index,
                identity=self._scope.facts[index].identity,
            )
        _populate(self._scope, index, attributes, value_objects, relationships)
        self._scope.populated[index] = True

    def close(self) -> None:
        """Close this writer; its build callback has returned."""
        self._open = False

    def _require_open(self) -> None:
        if not self._open:
            raise GraphConstructionError(
                code="entity-graph-scope-closed",
                message="this writer closed when its build callback returned",
            )


class ResolutionView:
    """A fresh, single-use view resolving this construction's handles to their
    final Entity instances.

    One view per state-factory invocation, closed the moment that invocation
    exits, so "a resolution view closes when its one factory invocation exits" is
    literally true rather than a rule the caller must honour.
    """

    __slots__ = ("_open", "_scope")

    def __init__(self, scope: _CallScope) -> None:
        self._scope = scope
        self._open = True

    def resolve(self, handle: NodeHandle) -> object:
        """The final Entity instance ``handle`` names."""
        if not self._open:
            raise GraphConstructionError(
                code="entity-graph-scope-closed",
                message="this resolution view closed when its factory invocation returned",
            )
        return self._scope.instances[_index_of(self._scope, handle, operation="resolve")]

    def close(self) -> None:
        """Close this view; its one factory invocation has returned."""
        self._open = False


class EntityGraphConstruction:
    """One Domain Model's graph-construction collaboration.

    Per Domain Model rather than per read: it is the home of the per-Entity facts
    derived once from accepted metadata — the concrete class, the
    identity-to-member-name mapping, and the declaration-ordered navigable
    relationships — and models are few and long-lived where reads are many.
    Because it is reached through :func:`graph_construction_of`,
    ``construct(...)`` takes no model argument and cannot be handed a mismatched
    one.
    """

    __slots__ = ("_cache", "_classes", "_model")

    def __init__(self, model: DomainModel) -> None:
        self._model = model_of(model)
        self._classes = class_index(model)
        self._cache: dict[EntityIdentity, _EntityFacts] = {}

    def construct(
        self,
        build: Callable[[EntityGraphWriter], tuple[NodeHandle, ...]],
        *,
        state_factory: Callable[[ResolutionView, NodeHandle], object] | None = None,
    ) -> tuple[object, ...]:
        """Build one graph and publish its ordered roots, or publish nothing.

        ``build`` receives a writer and answers the roots as handles. ``state_
        factory`` is invoked once per node in allocation order after the build
        callback returns; its results are buffered and attached only once every
        invocation has succeeded.

        The contract is the roots it is given plus everything reachable from
        them — never "the query result". Construction is nevertheless whole-graph
        per call: cycle closure needs every shell allocated first, and atomic
        publication needs every factory to succeed before any state attaches.
        """
        scope = _CallScope()
        writer = EntityGraphWriter(self, scope)
        try:
            roots = build(writer)
        finally:
            writer.close()
        _require_populated(scope)
        published = _validated_roots(scope, roots)
        states = _factory_results(scope, state_factory)
        for index, state in enumerate(states):
            object.__setattr__(scope.instances[index], LIFECYCLE_STATE_SLOT, state)
        return tuple(scope.instances[index] for index in published)

    def facts_for(self, entity: EntityIdentity) -> _EntityFacts:
        """``entity``'s derived construction facts, computed once per model."""
        cached = self._cache.get(entity)
        if cached is not None:
            return cached
        if self._classes is None:
            raise GraphConstructionError(
                code="entity-graph-invalid-entity",
                message=(
                    "this Domain Model composed no Entity Class, so it can construct no "
                    "Entity graph"
                ),
                identity=entity,
            )
        facts = _entity_facts(self._model, self._classes, entity)
        self._cache[entity] = facts
        return facts


def graph_construction_of(model: DomainModel) -> EntityGraphConstruction:
    """``model``'s construction collaboration — the reach seam for it.

    One per Domain Model, created on first reach and retained by the model, so
    every read of one model shares the per-Entity facts derived from it.

    Created on first reach because this module sits above ``_model`` in §7's
    import DAG: a :class:`DomainModel` cannot construct one without inverting an
    edge the generated import contracts reject, so this function is the only
    place that can build one. The guard is a dependency-direction consequence,
    not a performance hedge.
    """
    construction = model._graph_construction  # pyright: ignore[reportPrivateUsage] - first-party seam
    if not isinstance(construction, EntityGraphConstruction):
        construction = EntityGraphConstruction(model)
        model._graph_construction = construction  # pyright: ignore[reportPrivateUsage] - first-party seam
    return construction


def relationship_value_of(instance: object, relationship: RelationshipIdentity) -> object:
    """``instance``'s raw slot value for ``relationship``, unloaded sentinel included.

    The raw read the advanced seam exposes so a lifecycle package can distinguish
    unloaded from loaded-null without the raising descriptor access a developer
    gets. It is one of exactly two operations a lifecycle reads back here.
    """
    py_name = wire_names_of(type(instance)).relationship_py.get(relationship.name)
    if py_name is None:
        raise GraphConstructionError(
            code="entity-graph-invalid-member",
            message=(
                f"{type(instance).__name__} declares no relationship "
                f"{relationship.name!r} in its family"
            ),
            identity=relationship,
        )
    return instance.__dict__.get(py_name, UNLOADED)


def lifecycle_state_of(instance: object) -> object | None:
    """The opaque lifecycle state ``instance`` carries, or ``None``.

    Entity attaches whatever a state factory returned and never interprets it, so
    the value's meaning belongs entirely to the lifecycle that produced it.
    """
    return getattr(instance, LIFECYCLE_STATE_SLOT, None)


# --------------------------------------------------------------------------- #
# Phase implementations                                                        #
# --------------------------------------------------------------------------- #


def _shell(facts: _EntityFacts) -> object:
    """One unfilled frozen Entity instance.

    ``model_construct`` with no arguments skips validation entirely and fills
    every defaulted field from its default; population overwrites those and
    leaves an undefaulted field the input omits genuinely absent.
    """
    return cast("Any", facts.cls).model_construct()


def _require_populated(scope: _CallScope) -> None:
    for index, populated in enumerate(scope.populated):
        if not populated:
            raise GraphConstructionError(
                code="entity-graph-node-unpopulated",
                message="every allocated node is populated before the build callback returns",
                index=index,
                identity=scope.facts[index].identity,
            )


def _validated_roots(scope: _CallScope, roots: object) -> tuple[int, ...]:
    """The roots' allocation indices, checked left to right for value shape and
    then for the construction that issued each handle.

    Membership needs no third check: an index exists exactly for a handle this
    construction issued, and issuing one is what allocating a node does.
    """
    if type(roots) is not tuple:
        raise GraphConstructionError(
            code="entity-graph-invalid-root",
            message=(
                "a build callback answers an exact tuple of node handles, "
                f"not {type(roots).__name__}"
            ),
        )
    checked: list[int] = []
    for position, candidate in enumerate(cast("tuple[object, ...]", roots)):
        if not isinstance(candidate, NodeHandle):
            raise GraphConstructionError(
                code="entity-graph-invalid-root",
                message=(f"root {position} is a {type(candidate).__name__}, not a node handle"),
            )
        index = scope.index_of(candidate)
        if index is None:
            raise GraphConstructionError(
                code="entity-graph-foreign-handle",
                message=f"root {position} was allocated by another construction",
            )
        checked.append(index)
    return tuple(checked)


def _factory_results(
    scope: _CallScope,
    state_factory: Callable[[ResolutionView, NodeHandle], object] | None,
) -> tuple[object, ...]:
    """Every node's lifecycle state, in allocation order, or nothing at all.

    Results buffer here and attach only after the last factory succeeds: the
    first failure discards every buffered result and leaves the whole graph
    unreachable and state-free.
    """
    if state_factory is None:
        return ()
    buffered: list[object] = []
    for handle in scope.handles:
        view = ResolutionView(scope)
        try:
            buffered.append(state_factory(view, handle))
        finally:
            view.close()
    return tuple(buffered)


def _populate(
    scope: _CallScope,
    index: int,
    attributes: tuple[EntityAttributeInput, ...],
    value_objects: tuple[ValueObjectOccurrenceInput, ...],
    relationships: tuple[EntityRelationshipInput, ...],
) -> None:
    facts = scope.facts[index]
    instance = scope.instances[index]
    entries = _indexed(
        attributes,
        EntityAttributeInput,
        index=index,
        identity=facts.identity,
        kind="Attribute",
        known=facts.attribute_meta,
    )
    occurrences = _indexed(
        value_objects,
        ValueObjectOccurrenceInput,
        index=index,
        identity=facts.identity,
        kind="Value Object occurrence",
        known=facts.value_object_py,
    )
    views = _indexed(
        relationships,
        EntityRelationshipInput,
        index=index,
        identity=facts.identity,
        kind="relationship",
        known=facts.relationship_many,
    )

    for attribute in facts.attributes:
        entry = entries.get(attribute.identity)
        if entry is None:
            continue
        _check_value(
            entry.value,
            declared=attribute.type,
            nullable=attribute.nullable,
            index=index,
            identity=attribute.identity,
            label=f"{facts.identity.canonical}.{attribute.identity.name}",
            open_ended=attribute.identity in facts.open_ended,
        )
        object.__setattr__(
            instance,
            facts.attribute_py[attribute.identity],
            entry.value,
        )

    for occurrence in facts.value_objects:
        entry = occurrences.get(occurrence.identity)
        if entry is None:
            continue
        built = _build_occurrence(
            entry.value,
            declared=occurrence,
            vo_class=facts.value_object_class[occurrence.identity],
            index=index,
            entity=facts.identity,
        )
        object.__setattr__(instance, facts.value_object_py[occurrence.identity], built)

    for identity, py_name in facts.relationship_py.items():
        entry = views.get(identity)
        arm = UNLOADED_VIEW if entry is None else entry.value
        object.__setattr__(
            instance,
            py_name,
            _relationship_value(
                arm,
                scope=scope,
                many=facts.relationship_many[identity],
                index=index,
                identity=identity,
            ),
        )


class _Identified(Protocol):
    @property
    def identity(self) -> object: ...


def _indexed[T: _Identified](
    entries: tuple[T, ...],
    expected: type[T],
    *,
    index: int,
    identity: EntityIdentity,
    kind: str,
    known: Container[object],
) -> dict[object, T]:
    """``entries`` keyed by structured identity, rejecting a wrong carrier, an
    undeclared member, and a duplicate within this node."""
    if type(cast("object", entries)) is not tuple:
        raise GraphConstructionError(
            code="entity-graph-invalid-member",
            message=f"{kind} entries arrive as an exact tuple, not {type(entries).__name__}",
            index=index,
            identity=identity,
        )
    found: dict[object, T] = {}
    for entry in cast("tuple[object, ...]", entries):
        if not isinstance(entry, expected):
            raise GraphConstructionError(
                code="entity-graph-invalid-member",
                message=f"a {kind} entry is a {type(entry).__name__}, not {expected.__name__}",
                index=index,
                identity=identity,
            )
        entry_identity = entry.identity
        if entry_identity not in known:
            raise GraphConstructionError(
                code="entity-graph-invalid-member",
                message=f"{identity.canonical} declares no {kind} {entry_identity!r}",
                index=index,
                identity=cast("AttributeIdentity", entry_identity),
            )
        if entry_identity in found:
            raise GraphConstructionError(
                code="entity-graph-invalid-member",
                message=f"{identity.canonical} carries two entries for one {kind}",
                index=index,
                identity=cast("AttributeIdentity", entry_identity),
            )
        found[entry_identity] = entry
    return found


def _check_value(
    value: object,
    *,
    declared: NeutralType,
    nullable: bool,
    index: int,
    identity: AttributeIdentity | ValueObjectAttributeIdentity,
    label: str,
    open_ended: bool = False,
    collapsed: bool = False,
) -> None:
    """Reject a null where the member forbids one, and a value outside the
    declared Neutral Type's value space.

    This is where declared-type enforcement on a materialized read lives:
    construction bypasses Pydantic validation, so the writer's own Neutral Value
    check is what stands in its place.

    ``open_ended`` names a temporal interval's end Attribute, whose value space
    additionally admits ``m-core``'s native-infinity sentinel — the open upper
    bound is a temporal fact distinct from every finite instant and from ``None``,
    and it is what a current milestone's end attribute actually carries. A start
    Attribute is a finite instant and admits no sentinel.

    ``collapsed`` names a document-resident position, where ``None`` is the
    member's own NOT-PRESENT state rather than a stored null: reading a document
    applies Predicate-algebra absence collapse, so an absent leaf, a stored JSON
    null, and a wrong-kind occurrence all arrive here as ``None``. Deriving a
    nullability verdict from that would contradict the collapse the read seam
    already performed, so only the declared value space is checked.
    """
    if value is None:
        if collapsed:
            return
        if not nullable:
            raise GraphConstructionError(
                code="entity-graph-invalid-value",
                message=f"{label} is not nullable and admits no null",
                index=index,
                identity=identity,
            )
        return
    if open_ended and value is INFINITY and isinstance(declared, Timestamp):
        return
    if not matches_neutral_type(value, declared):
        raise GraphConstructionError(
            code="entity-graph-invalid-value",
            message=f"{label} received {value!r}, outside its declared type's value space",
            index=index,
            identity=identity,
        )


def _relationship_value(
    arm: object,
    *,
    scope: _CallScope,
    many: bool,
    index: int,
    identity: RelationshipIdentity,
) -> object:
    """One relationship slot's installed value: the unloaded sentinel, ``None``,
    a related instance, or an exact tuple of them."""
    if isinstance(arm, Unloaded):
        return UNLOADED
    if isinstance(arm, LoadedMany):
        if not many:
            raise GraphConstructionError(
                code="entity-graph-invalid-value",
                message=f"{identity.name} is a to-one direction and takes no loaded-many arm",
                index=index,
                identity=identity,
            )
        nodes = cast("object", arm.nodes)
        if type(nodes) is not tuple:
            raise GraphConstructionError(
                code="entity-graph-invalid-value",
                message=(
                    f"{identity.name} takes a loaded-many arm of an exact tuple of node "
                    f"handles, not {type(nodes).__name__}"
                ),
                index=index,
                identity=identity,
            )
        return tuple(
            scope.instances[_index_of(scope, node, operation="populate")]
            for node in cast("tuple[object, ...]", nodes)
        )
    if many:
        raise GraphConstructionError(
            code="entity-graph-invalid-value",
            message=f"{identity.name} is a to-many direction and takes only a loaded-many arm",
            index=index,
            identity=identity,
        )
    if isinstance(arm, LoadedNull):
        return None
    if isinstance(arm, LoadedOne):
        return scope.instances[_index_of(scope, arm.node, operation="populate")]
    raise GraphConstructionError(
        code="entity-graph-invalid-value",
        message=f"{identity.name} received {type(arm).__name__}, which is no relationship arm",
        index=index,
        identity=identity,
    )


def _build_occurrence(
    value: object,
    *,
    declared: ValueObjectMetadata | NestedValueObjectMetadata,
    vo_class: type,
    index: int,
    entity: EntityIdentity,
) -> object:
    """One Value Object occurrence as frozen instances, checked for container
    shape first.

    A Many occurrence has no absent state at all: it takes an exact tuple, empty
    for its zero-element value.
    """
    identity = declared.identity
    label = f"{entity.canonical}.{'.'.join(identity.path)}"
    if declared.multiplicity is Multiplicity.MANY:
        if type(value) is not tuple:
            raise GraphConstructionError(
                code="entity-graph-invalid-value",
                message=f"{label} is a Many occurrence and takes an exact tuple of records",
                index=index,
                identity=identity,
            )
        return tuple(
            _build_record(record, declared=declared, vo_class=vo_class, index=index, entity=entity)
            for record in cast("tuple[object, ...]", value)
        )
    if value is None:
        # A One occurrence absent from the document, stored as JSON null, or
        # stored in the wrong kind all arrive here as `None`: reading a document
        # applies Predicate-algebra absence collapse, so this is the whole
        # composite being not present rather than a nullability verdict to
        # re-derive against a collapse that already happened.
        return None
    return _build_record(value, declared=declared, vo_class=vo_class, index=index, entity=entity)


def _build_record(
    record: object,
    *,
    declared: ValueObjectMetadata | NestedValueObjectMetadata,
    vo_class: type,
    index: int,
    entity: EntityIdentity,
) -> object:
    """One :class:`ValueObjectRecord` as a frozen Value Object instance.

    Field presence is preserved rather than flattened: an omitted entry reads as
    ``None`` (or ``()``) and stays outside ``model_fields_set``, while an entry
    present as ``None`` reads the same and is inside it — which is what keeps
    canonical document serialization able to omit the former and emit the latter
    as an explicit null.
    """
    identity = declared.identity
    if not isinstance(record, ValueObjectRecord):
        raise GraphConstructionError(
            code="entity-graph-invalid-value",
            message=(
                f"{entity.canonical}.{'.'.join(identity.path)} takes a ValueObjectRecord, "
                f"not {type(record).__name__}"
            ),
            index=index,
            identity=identity,
        )
    shape = shape_of(vo_class)
    leaves = _indexed(
        record.attributes,
        ValueObjectAttributeInput,
        index=index,
        identity=entity,
        kind="Value Object Attribute",
        known={leaf.identity: leaf for leaf in declared.attributes},
    )
    nested = _indexed(
        record.value_objects,
        ValueObjectOccurrenceInput,
        index=index,
        identity=entity,
        kind="nested Value Object occurrence",
        known={occurrence.identity: occurrence for occurrence in declared.value_objects},
    )
    values: dict[str, object] = {}
    present: set[str] = set()
    for leaf in declared.attributes:
        py_name = _member_py(shape, leaf.identity.name)
        entry = leaves.get(leaf.identity)
        label = (
            f"{entity.canonical}.{'.'.join(leaf.identity.value_object.path)}.{leaf.identity.name}"
        )
        if entry is None:
            values[py_name] = None
            continue
        _check_value(
            entry.value,
            declared=leaf.type,
            nullable=leaf.nullable,
            index=index,
            identity=leaf.identity,
            label=label,
            collapsed=True,
        )
        present.add(py_name)
        values[py_name] = entry.value
    for occurrence in declared.value_objects:
        py_name = _member_py(shape, occurrence.identity.path[-1])
        many = py_name in shape.many_py
        entry = nested.get(occurrence.identity)
        if entry is None:
            values[py_name] = () if many else None
            continue
        present.add(py_name)
        values[py_name] = _build_occurrence(
            entry.value,
            declared=occurrence,
            vo_class=shape.nested_classes[py_name],
            index=index,
            entity=entity,
        )
    return cast("Any", vo_class).model_construct(present, **values)


def _member_py(shape: ValueObjectShape, canonical: str) -> str:
    py_name = shape.name_to_py.get(canonical)
    if py_name is None:  # pragma: no cover - a composed class carries every declared member
        raise GraphConstructionError(
            code="entity-graph-invalid-member",
            message=f"the bound Value Object Class declares no member {canonical!r}",
        )
    return py_name
