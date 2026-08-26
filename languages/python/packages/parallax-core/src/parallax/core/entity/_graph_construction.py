"""Entity Graph Construction — the advanced first-party graph-building collaboration.

Exposed from ``parallax.core.entity`` and deliberately **not** from top-level
``parallax.core``: it is the seam a lifecycle package builds a graph of frozen
Entity instances through, not developer surface.

A node crosses its door as two positional rows: its full-width member row, laid
out against its exact Entity's member layout
(:mod:`parallax.core.entity._layout`), and a full-width broad-relationship row
in that layout's canonical order. The sentinels those rows spell absence and
unloadedness with, and the handle a relationship position names a node by, live
in the sibling :mod:`parallax.core.entity._construction_input` scope, so a
lifecycle package materializing Entities can be granted the vocabulary without
being granted this collaboration.

The collaboration owns everything about turning those rows into Entity
and Value Object instances — concrete class selection, canonical-to-Python member
mapping, the correspondence between the model's member layout and the class's
own, recursive Value Object construction, declared-type enforcement in Pydantic
validation's place, broad relationship-slot filling, the one opaque
lifecycle-state slot, and all-or-none publication. What it does NOT own is how a
value physically holds any of that: it hands the instance-state Module semantic
inputs and the Module attaches one row, so nothing here knows the tuple or the
bitmap. It owns nothing about
any lifecycle either: it registers no callback, interprets no state value, and
imports no lifecycle package. A caller passes one build function and one optional state
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
   attached state and no published root. What a factory returns is written
   through the lifecycle slot's own descriptor rather than assigned by name, so
   whatever the node's class binds, it lands where the two consumers that reach
   the slot directly find it: the pickle refusal (spec §3) and an edit's
   carry-forward of the state a node carries. ``lifecycle_state_of`` is not one
   of them — it resolves the slot through the class, so a class answering for
   that name blinds its own lifecycle's readers without moving what those two
   see.

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

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel

from parallax.core.base import INFINITY, NeutralType, Timestamp, matches_neutral_type
from parallax.core.entity._construction_input import ABSENT, UNLOADED, NodeHandle
from parallax.core.entity._declaration import (
    LIFECYCLE_STATE_SLOT,
    ValueObjectShape,
    shape_of,
)
from parallax.core.entity._entity import attach_lifecycle_state, wire_names_of
from parallax.core.entity._errors import GraphConstructionError
from parallax.core.entity._instance_state import (
    PublicationPlan,
    allocate,
    plan_of,
    publish,
)
from parallax.core.entity._instance_state import relationship as relationship_state
from parallax.core.entity._layout import EntityLayout, LayoutCatalog, ValueObjectLayout
from parallax.core.entity._model import (
    ClassIndex,
    DomainModel,
    cataloged_model,
    class_index,
    model_of,
)
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    MemberIdentity,
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
class _AttributeFacts:
    """One Attribute as the writer reads it at its own member-row position.

    ``open_ended`` names a temporal interval's end Attribute, resolved once here
    rather than tested against a family-wide set per stored value.
    """

    declared: AttributeMetadata
    py_name: str | None
    open_ended: bool


@dataclass(frozen=True, slots=True)
class _OccurrenceFacts:
    """One top-level Value Object occurrence at its own member-row position."""

    declared: ValueObjectMetadata
    py_name: str | None
    vo_class: type | None


@dataclass(frozen=True, slots=True)
class _RelationshipFacts:
    """One navigable direction at its own broad-relationship-row position."""

    identity: RelationshipIdentity
    py_name: str | None
    many: bool


@dataclass(frozen=True, slots=True)
class _EntityFacts:
    """Everything one Entity's construction needs, derived once from the accepted
    model and the Entity Class composed under it.

    Family-effective throughout: an inherited Attribute, Value Object, or
    relationship reaches a concrete subtype under its own declaring identity, so
    each run is stated under those declaring identities rather than the
    concrete's.

    The three runs are what a positional row is read against, each in the
    exact-model member layout's own order: applicable Attributes ancestry-first,
    then applicable top-level Value Object occurrences, and separately every
    navigable direction. Their lengths are what a row's width has to be.

    A ``py_name`` of ``None`` is a member the accepted model declares for this
    family and this concrete's own MRO does not carry: the position exists
    because the row is model-fixed, and there is no slot to install at it.
    """

    identity: EntityIdentity
    cls: type
    attributes: tuple[_AttributeFacts, ...]
    value_objects: tuple[_OccurrenceFacts, ...]
    relationships: tuple[_RelationshipFacts, ...]


def _entity_facts(
    model: Metamodel, classes: ClassIndex, layouts: LayoutCatalog, identity: EntityIdentity
) -> _EntityFacts:
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
    open_ended = _open_ended_attributes(model, identity)
    occurrence_py = [
        names.name_to_py.get(occurrence.identity.path[-1]) for occurrence in value_objects
    ]
    facts = _EntityFacts(
        identity=identity,
        cls=cls,
        attributes=tuple(
            _AttributeFacts(
                declared=attribute,
                py_name=names.name_to_py.get(attribute.identity.name),
                open_ended=attribute.identity in open_ended,
            )
            for attribute in attributes
        ),
        value_objects=tuple(
            _OccurrenceFacts(
                declared=occurrence,
                py_name=py_name,
                vo_class=None if py_name is None else names.vo_classes.get(py_name),
            )
            for occurrence, py_name in zip(value_objects, occurrence_py, strict=True)
        ),
        relationships=tuple(
            _RelationshipFacts(
                identity=direction.identity,
                py_name=names.relationship_py.get(direction.identity.name),
                many=direction.cardinality.target is Multiplicity.MANY,
            )
            for direction in _navigable_relationships(model, identity)
        ),
    )
    _require_correspondence(layouts.entity(identity), facts)
    return facts


def _require_correspondence(layout: EntityLayout, facts: _EntityFacts) -> None:
    """Refuse unless the model lays this Entity out the way its class is laid out.

    Two derivations reach one order from different material and neither is
    derived from the other. The model side walks the accepted metadata — the
    inheritance ancestry and each contributor's declared members — into an
    :class:`~parallax.core.entity._layout.EntityLayout`. The class side walks the
    Python MRO and each class body's own declarations into a publication plan,
    at class creation, knowing no model at all. A positional row is written
    against the first and read back through the second, so a disagreement
    between them installs every member after it at the wrong position, and a
    row of the right width cannot express one: width is a count.

    Compared once per (class, model) — this runs where the per-Entity facts are
    derived, and those are memoized — so it fires on the actual pair a process
    publishes rather than on whichever pair a fixture named, and no field read
    ever pays for the question. What can genuinely diverge is which contributors
    there are and what each declared, which is why factoring the shared tail into
    one rule both sides call would protect the half that cannot diverge and
    leave this half unchecked.
    """
    plan = plan_of(facts.cls)
    model_members = tuple(
        (
            *(attribute.declared.identity for attribute in facts.attributes),
            *(occurrence.declared.identity for occurrence in facts.value_objects),
        )
    )
    if layout.members != model_members or layout.relationships != tuple(
        direction.identity for direction in facts.relationships
    ):
        raise _correspondence_refusal(
            facts,
            f"the member layout lays out {layout.members} with relationships "
            f"{layout.relationships}, and this collaboration reads {model_members} with "
            f"{tuple(direction.identity for direction in facts.relationships)}",
        )
    _require_member_correspondence(facts, plan)
    _require_relationship_correspondence(facts, plan)
    for occurrence, occurrence_layout in zip(
        facts.value_objects, layout.value_objects, strict=True
    ):
        _require_occurrence_correspondence(
            facts,
            occurrence_layout,
            # Not `None`: the check above refuses an occurrence position the class
            # binds no Value Object Class at, so one reaching here has one.
            cast("type", occurrence.vo_class),
            path=f"{facts.identity.canonical}.{'.'.join(occurrence.declared.identity.path)}",
        )


def _require_member_correspondence(facts: _EntityFacts, plan: PublicationPlan) -> None:
    """Refuse unless the class carries the model's member row in the model's order,
    each position of the kind the model gives it.

    Kind is checked as well as name because it is what a positional row lost: the
    identity-keyed algebra this door replaced named the member a carrier filled
    and so knew which kind that identity was, while a row of the right width says
    only how many positions there are. A model calling position ``i`` a Value
    Object occurrence where the composed class maps it as a scalar therefore
    reaches here rather than reaching the declared type's own check further down.
    """
    row = tuple(
        (
            *(attribute.py_name for attribute in facts.attributes),
            *(occurrence.py_name for occurrence in facts.value_objects),
        )
    )
    if row != plan.py_names:
        raise _correspondence_refusal(
            facts,
            f"the model lays out members {row} and the class is laid out as {plan.py_names}",
        )
    for position, occurrence in enumerate(facts.value_objects, start=len(facts.attributes)):
        bound = plan.occurrences.get(position + 1)
        if bound is None or bound is not occurrence.vo_class:
            raise _correspondence_refusal(
                facts,
                f"the model calls member {position} ({occurrence.py_name!r}) a Value Object "
                f"occurrence, and the class holds {bound} at that position",
                identity=occurrence.declared.identity,
            )


def _require_relationship_correspondence(facts: _EntityFacts, plan: PublicationPlan) -> None:
    """Refuse unless the class's relationship tail is the model's canonical order.

    The tail carries no presence bit and no name once a row is written, so a
    direction installed at another direction's position is a loaded arm answered
    for the wrong relationship — silently, and for the life of the graph.
    """
    tail = tuple(direction.py_name for direction in facts.relationships)
    laid_out = tuple(
        py_name for py_name, _ in sorted(plan.relationships.items(), key=lambda pair: pair[1])
    )
    if tail != laid_out:
        raise _correspondence_refusal(
            facts,
            f"the model lays out relationships {tail} and the class is laid out as {laid_out}",
        )


def _require_occurrence_correspondence(
    facts: _EntityFacts,
    layout: ValueObjectLayout,
    vo_class: type,
    *,
    path: str,
) -> None:
    """Refuse unless one occurrence's own path layout is its Value Object class's
    own laid-out order, at every containment depth.

    A Value Object layout is keyed to a containment PATH and a publication plan
    to a CLASS, so the two are checked against each other here rather than
    conflated: one class bound at two paths is laid out once and must correspond
    at both.
    """
    plan = plan_of(vo_class)
    shape = shape_of(vo_class)
    row = tuple(
        shape.name_to_py.get(
            member.name if isinstance(member, ValueObjectAttributeIdentity) else member.path[-1]
        )
        for member in layout.members
    )
    if row != plan.py_names:
        raise _correspondence_refusal(
            facts,
            f"{path} lays out members {row} and {vo_class.__name__} is laid out as {plan.py_names}",
            identity=layout.identity,
        )
    for position, nested in enumerate(layout.nested):
        if nested is None:
            continue
        py_name = cast("str", row[position])
        nested_class = shape.nested_classes.get(py_name)
        if plan.occurrences.get(position + 1) is not nested_class or nested_class is None:
            raise _correspondence_refusal(
                facts,
                f"{path} calls member {position} ({py_name!r}) a nested occurrence of "
                f"{nested_class}, and {vo_class.__name__} holds "
                f"{plan.occurrences.get(position + 1)} there",
                identity=nested.identity,
            )
        _require_occurrence_correspondence(facts, nested, nested_class, path=f"{path}.{py_name}")


def _correspondence_refusal(
    facts: _EntityFacts,
    detail: str,
    *,
    identity: EntityIdentity | MemberIdentity | None = None,
) -> GraphConstructionError:
    """The one refusal every correspondence disagreement earns, naming both sides."""
    return GraphConstructionError(
        code="entity-graph-layout-mismatch",
        message=(
            f"the class composed for {facts.identity.canonical} is not laid out the way this "
            f"model lays it out, so no positional row addresses it: {detail}"
        ),
        identity=facts.identity if identity is None else identity,
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

    ``bitmaps`` is this call's own memo of the presence masks its nodes have
    assembled, and it dies with the call. Every node of one class in one
    materialization comes from one projection and so repeats one pattern, which
    the memo turns into one shared integer per distinct pattern rather than one
    per node; nothing process-wide holds it, so no mask outlives the graph.
    """

    __slots__ = ("_indices", "bitmaps", "facts", "handles", "instances", "populated")

    def __init__(self) -> None:
        self.facts: list[_EntityFacts] = []
        self.handles: list[NodeHandle] = []
        self.instances: list[object] = []
        self.populated: list[bool] = []
        self.bitmaps: dict[int, int] = {}
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
        members: tuple[object, ...],
        relationships: tuple[object, ...],
    ) -> None:
        """Fill one allocated node exactly once, closing allocation permanently.

        ``members`` is the node's full-width member row in its exact Entity's
        member layout order — every applicable Attribute, then every applicable
        top-level Value Object occurrence — with ``ABSENT`` at a position the read
        carried nothing for and a nested member row, or a tuple of them, at an
        occurrence's. ``relationships`` is one position per navigable direction in
        that layout's canonical order, each holding ``UNLOADED``, ``None``, one
        :class:`NodeHandle`, or an exact tuple of them.

        Every navigable relationship slot is installed here — a position holding
        the unloaded sentinel installs it, which is what makes the closed world a
        structural fact rather than a convention.
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
        _populate(self._scope, index, members, relationships)
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

    __slots__ = ("_cache", "_classes", "_layouts", "_model")

    def __init__(self, model: DomainModel) -> None:
        self._model = model_of(model)
        self._classes = class_index(model)
        self._layouts = cataloged_model(model).layouts
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
            attach_lifecycle_state(cast("BaseModel", scope.instances[index]), state)
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
        facts = _entity_facts(self._model, self._classes, self._layouts, entity)
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

    Where the position lives is the backing's own question — a published node
    holds every declared direction in its row's tail and an ordinary value holds
    the loaded ones in its storage — so the read goes through the backing rather
    than through a mapping this module picks.
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
    return relationship_state(cast("BaseModel", instance), py_name)


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

    Neither constructor is entered — not the validating one, and not
    ``model_construct`` — because a shell holds no declared state at all: it
    exists so a relationship can name it before it holds anything, and
    publication attaches its whole row at once. What it is given is the Pydantic
    storage no value can be missing, which is
    :func:`~parallax.core.entity._instance_state.allocate`'s own contract.
    """
    return allocate(cast("type[Any]", facts.cls))


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
    members: tuple[object, ...],
    relationships: tuple[object, ...],
) -> None:
    """Read both rows, then attach one node's whole state in a single write.

    Every refusal happens while the two mappings are still local, so a row this
    collaboration rejects leaves its shell exactly as allocation left it: no
    partially populated node exists at any point, and a node whose relationship
    row fails carries none of the members the same call already read.
    """
    facts = scope.facts[index]
    instance = cast("BaseModel", scope.instances[index])
    _require_row(
        members,
        width=len(facts.attributes) + len(facts.value_objects),
        index=index,
        identity=facts.identity,
        kind="member",
    )
    _require_row(
        relationships,
        width=len(facts.relationships),
        index=index,
        identity=facts.identity,
        kind="broad-relationship",
    )

    values: dict[str, object] = {}
    for position, attribute in enumerate(facts.attributes):
        value = members[position]
        if value is ABSENT:
            continue
        if attribute.py_name is None:  # pragma: no cover - a composed class carries its family
            raise _unbound_member(facts, attribute.declared.identity, index=index, kind="Attribute")
        declared = attribute.declared
        _check_value(
            value,
            declared=declared.type,
            nullable=declared.nullable,
            index=index,
            identity=declared.identity,
            label=f"{facts.identity.canonical}.{declared.identity.name}",
            open_ended=attribute.open_ended,
        )
        values[attribute.py_name] = value

    for position, occurrence in enumerate(facts.value_objects, start=len(facts.attributes)):
        value = members[position]
        if value is ABSENT:
            continue
        if (  # pragma: no cover - a composed class carries its family
            occurrence.py_name is None or occurrence.vo_class is None
        ):
            raise _unbound_member(
                facts, occurrence.declared.identity, index=index, kind="Value Object occurrence"
            )
        values[occurrence.py_name] = _build_occurrence(
            value,
            declared=occurrence.declared,
            vo_class=occurrence.vo_class,
            index=index,
            entity=facts.identity,
            bitmaps=scope.bitmaps,
        )

    related: dict[str, object] = {}
    for position, direction in enumerate(facts.relationships):
        if direction.py_name is None:  # pragma: no cover - a composed class carries its family
            if relationships[position] is not UNLOADED:
                raise _unbound_member(facts, direction.identity, index=index, kind="relationship")
            continue
        related[direction.py_name] = _relationship_value(
            relationships[position],
            scope=scope,
            many=direction.many,
            index=index,
            identity=direction.identity,
        )

    publish(instance, values, related, shared_bitmaps=scope.bitmaps)


def _unbound_member(  # pragma: no cover - a composed class carries its family
    facts: _EntityFacts,
    member: AttributeIdentity | ValueObjectIdentity | RelationshipIdentity,
    *,
    index: int,
    kind: str,
) -> GraphConstructionError:
    """The refusal for a position the accepted model lays out and the composed
    class carries no member for.

    A Domain Model compiles its Metamodel from the classes it composed, so the
    two never disagree about which members exist and every caller of this is
    marked unreachable. It exists rather than a skip because the alternative to
    refusing is dropping a member the row carried, silently.

    Reached only when the row carries something at the position: one the read
    left absent names nothing, so a member the class cannot hold and the row does
    not fill is no disagreement at all.
    """
    return GraphConstructionError(
        code="entity-graph-invalid-member",
        message=(
            f"the class composed for {facts.identity.canonical} declares no {kind} "
            f"{member!r}, and its row carries one"
        ),
        index=index,
        identity=member,
    )


def _require_row(
    row: object, *, width: int, index: int, identity: EntityIdentity, kind: str
) -> None:
    """Refuse anything but an exact built-in tuple of the model-fixed width.

    Width is the whole membership check a positional row needs. Every declared
    member has a position and a position names nothing else, so a row of the
    model's own width names each declared member exactly once — which is why the
    two rejections the identity-keyed algebra made separately do not survive as
    checks: an undeclared member has no position to occupy, and a member named
    twice has one position to occupy. What is left is a row that is not the
    model's membership at all: too many positions, or too few.
    """
    if type(row) is not tuple:
        raise GraphConstructionError(
            code="entity-graph-invalid-member",
            message=f"a {kind} row arrives as an exact tuple, not {type(row).__name__}",
            index=index,
            identity=identity,
        )
    if len(cast("tuple[object, ...]", row)) != width:
        raise GraphConstructionError(
            code="entity-graph-invalid-member",
            message=(
                f"{identity.canonical} lays out {width} {kind} positions, "
                f"and this row carries {len(cast('tuple[object, ...]', row))}"
            ),
            index=index,
            identity=identity,
        )


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
    a related instance, or an exact tuple of them.

    The position's own value names its arm — the sentinel is unloaded, ``None``
    is loaded-null, an exact tuple is loaded-many with ``()`` its empty case, and
    a handle is loaded-one — so the declared cardinality is the only thing that
    decides whether that arm is admissible. Anything else at the position is no
    arm at all, which is what a caller-defined tuple subtype and a mutable
    sequence both are.
    """
    if arm is UNLOADED:
        return UNLOADED
    if type(arm) is tuple:
        if not many:
            raise GraphConstructionError(
                code="entity-graph-invalid-value",
                message=f"{identity.name} is a to-one direction and takes no loaded-many arm",
                index=index,
                identity=identity,
            )
        return tuple(
            scope.instances[_index_of(scope, node, operation="populate")]
            for node in cast("tuple[object, ...]", arm)
        )
    if many:
        raise GraphConstructionError(
            code="entity-graph-invalid-value",
            message=f"{identity.name} is a to-many direction and takes only a loaded-many arm",
            index=index,
            identity=identity,
        )
    if arm is None:
        return None
    if isinstance(arm, NodeHandle):
        return scope.instances[_index_of(scope, arm, operation="populate")]
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
    bitmaps: dict[int, int],
) -> object:
    """One Value Object occurrence as frozen instances, checked for container
    shape first.

    The declared multiplicity decides the shape rather than the value does: a One
    slot's member row and a Many slot's tuple of them are both tuples, and only
    the declaration distinguishes them. A Many occurrence has no absent state at
    all: it takes an exact tuple, empty for its zero-element value.
    """
    identity = declared.identity
    label = f"{entity.canonical}.{'.'.join(identity.path)}"
    if declared.multiplicity is Multiplicity.MANY:
        if type(value) is not tuple:
            raise GraphConstructionError(
                code="entity-graph-invalid-value",
                message=f"{label} is a Many occurrence and takes an exact tuple of member rows",
                index=index,
                identity=identity,
            )
        return tuple(
            _build_record(
                row,
                declared=declared,
                vo_class=vo_class,
                index=index,
                entity=entity,
                bitmaps=bitmaps,
            )
            for row in cast("tuple[object, ...]", value)
        )
    if value is None:
        # A One occurrence absent from the document, stored as JSON null, or
        # stored in the wrong kind all arrive here as `None`: reading a document
        # applies Predicate-algebra absence collapse, so this is the whole
        # composite being not present rather than a nullability verdict to
        # re-derive against a collapse that already happened.
        return None
    return _build_record(
        value, declared=declared, vo_class=vo_class, index=index, entity=entity, bitmaps=bitmaps
    )


def _build_record(
    row: object,
    *,
    declared: ValueObjectMetadata | NestedValueObjectMetadata,
    vo_class: type,
    index: int,
    entity: EntityIdentity,
    bitmaps: dict[int, int],
) -> object:
    """One positional member row as a frozen Value Object instance, at every depth.

    The row is that occurrence's own leaves in declaration order, then its nested
    occurrences in theirs, with ``ABSENT`` at a position the read carried nothing
    for. Field presence is preserved rather than flattened: an absent position
    reads as ``None`` (or ``()``) and stays outside ``model_fields_set``, while a
    position carrying ``None`` reads the same and is inside it — which is what
    keeps canonical document serialization able to omit the former and emit the
    latter as an explicit null.
    """
    identity = declared.identity
    label = f"{entity.canonical}.{'.'.join(identity.path)}"
    leaf_count = len(declared.attributes)
    if type(row) is not tuple:
        raise GraphConstructionError(
            code="entity-graph-invalid-value",
            message=f"{label} takes a member row as an exact tuple, not {type(row).__name__}",
            index=index,
            identity=identity,
        )
    cells = cast("tuple[object, ...]", row)
    if len(cells) != leaf_count + len(declared.value_objects):
        raise GraphConstructionError(
            code="entity-graph-invalid-value",
            message=(
                f"{label} lays out {leaf_count + len(declared.value_objects)} member positions, "
                f"and this row carries {len(cells)}"
            ),
            index=index,
            identity=identity,
        )
    shape = shape_of(vo_class)
    values: dict[str, object] = {}
    for position, leaf in enumerate(declared.attributes):
        py_name = _member_py(shape, leaf.identity.name)
        value = cells[position]
        if value is ABSENT:
            continue
        _check_value(
            value,
            declared=leaf.type,
            nullable=leaf.nullable,
            index=index,
            identity=leaf.identity,
            label=(
                f"{entity.canonical}.{'.'.join(leaf.identity.value_object.path)}"
                f".{leaf.identity.name}"
            ),
            collapsed=True,
        )
        values[py_name] = value
    for position, occurrence in enumerate(declared.value_objects, start=leaf_count):
        py_name = _member_py(shape, occurrence.identity.path[-1])
        value = cells[position]
        if value is ABSENT:
            continue
        values[py_name] = _build_occurrence(
            value,
            declared=occurrence,
            vo_class=shape.nested_classes[py_name],
            index=index,
            entity=entity,
            bitmaps=bitmaps,
        )
    record = allocate(cast("type[Any]", vo_class))
    publish(record, values, shared_bitmaps=bitmaps)
    return record


def _member_py(shape: ValueObjectShape, canonical: str) -> str:
    py_name = shape.name_to_py.get(canonical)
    if py_name is None:  # pragma: no cover - a composed class carries every declared member
        raise GraphConstructionError(
            code="entity-graph-invalid-member",
            message=f"the bound Value Object Class declares no member {canonical!r}",
        )
    return py_name
