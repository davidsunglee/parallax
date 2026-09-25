"""Allocate all shells before populating any, then attach lifecycle state atomically.

Factories run only after population and root validation. Failure withholds roots
and lifecycle state, but cannot revoke populated instances retained by a factory;
already-populated rows are not rolled back."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, NamedTuple, cast

from pydantic import BaseModel

from parallax.core.entity._construction_input import NodeHandle
from parallax.core.entity._declaration import (
    LIFECYCLE_STATE_SLOT,
    WireNames,
    shape_of,
    wire_names_of,
)
from parallax.core.entity._entity import attach_lifecycle_state
from parallax.core.entity._errors import GraphConstructionError
from parallax.core.entity._instance_state import (
    PublicationPlan,
    RowShapeError,
    allocate,
    plan_of,
    publish_positional,
)
from parallax.core.entity._instance_state import relationship as relationship_state
from parallax.core.entity._layout import CatalogedModel, EntityLayout
from parallax.core.entity._model import ClassIndex
from parallax.core.metamodel import (
    EntityIdentity,
    MemberIdentity,
    Multiplicity,
    NestedValueObjectMetadata,
    RelationshipIdentity,
    ValueObjectMetadata,
)

__all__ = [
    "EntityGraphConstruction",
    "EntityGraphWriter",
    "ResolutionView",
    "lifecycle_state_of",
    "relationship_value_of",
    "require_correspondence",
]


class _OccurrenceFacts(NamedTuple):
    """One Value Object occurrence path, proven against the class bound at it.

    Correspondence settles the class and its publication plan once per path, so
    a record publishes against them without resolving either again. ``nested``
    is aligned to the occurrence's own nested occurrences, which its row lays out
    after its leaves.
    """

    declared: ValueObjectMetadata | NestedValueObjectMetadata
    cls: type
    plan: PublicationPlan
    many: bool
    nested: tuple[_OccurrenceFacts, ...]


@dataclass(frozen=True, slots=True)
class _EntityFacts:
    """Everything one Entity's construction needs: the exact-model member layout
    its rows are written against, the Entity Class composed under that identity,
    and the publication plan that class carries.

    Both deep values are held rather than restated. ``layout`` fixes the
    positional rows — the family-effective member order, the Attribute / Value
    Object boundary, the metadata each position takes, and the canonical
    broad-relationship order — and ``plan`` fixes where each of those positions
    lands on an instance. The correspondence check is what binds the two: once
    it passes, layout position ``i`` is plan position ``i``, so a row publishes
    positionally without a per-member record pairing them.

    The two tuples are answers resolved once here rather than per stored value:
    whether each direction in the layout's relationship order is to-many, and
    each top-level occurrence's proven facts in the layout's occurrence order.
    """

    layout: EntityLayout
    cls: type
    plan: PublicationPlan
    many: tuple[bool, ...]
    occurrences: tuple[_OccurrenceFacts, ...]


def _entity_facts(
    cataloged: CatalogedModel, classes: ClassIndex, identity: EntityIdentity
) -> _EntityFacts:
    cls = classes.class_of(identity)
    if cls is None:
        raise GraphConstructionError(
            code="entity-graph-invalid-entity",
            message=(
                f"{identity.canonical} is not an Entity this Domain Model composed a class for"
            ),
            identity=identity,
        )
    layout = cataloged.layouts.entity(identity)
    plan = plan_of(cls)
    return _EntityFacts(
        layout=layout,
        cls=cls,
        plan=plan,
        many=tuple(direction in layout.to_many for direction in layout.relationships),
        occurrences=_proven_occurrences(layout, wire_names_of(cls), plan),
    )


def require_correspondence(layout: EntityLayout, names: WireNames, plan: PublicationPlan) -> None:
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

    Order alone is not the agreement, because a name is local to an ancestry:
    two sides can spell one row, one tail, and one Value Object Class at every
    position and still mean two different sets of declarations. So the accepted
    declarations behind each position are compared as well as the order they sit
    in.

    Passing is what makes the plan positional afterwards: a member is read off
    ``plan.py_names`` at the layout's own position on the strength of this
    comparison, rather than through a second mapping built beside it.

    Compared once per (class, model) — this runs where the per-Entity facts are
    derived, which is the collaboration's construction — so it fires on the
    actual pair a process publishes rather than on whichever pair a fixture
    named, and no field read ever pays for the question.
    """
    _proven_occurrences(layout, names, plan)


def _proven_occurrences(
    layout: EntityLayout, names: WireNames, plan: PublicationPlan
) -> tuple[_OccurrenceFacts, ...]:
    """Every correspondence check, answering the occurrence facts the
    occurrence check proves on the way."""
    _require_member_correspondence(layout, names, plan)
    _require_relationship_correspondence(layout, names, plan)
    occurrences = [
        _proven_occurrence(
            layout.concrete,
            occurrence,
            # Not `None`: the check above refuses an occurrence position the class
            # binds no Value Object Class at, so one reaching here has one.
            cast("type", plan.occurrences.get(position + 1)),
            path=f"{layout.concrete.canonical}.{'.'.join(occurrence.identity.path)}",
        )
        for position, occurrence in enumerate(layout.value_objects, start=layout.attribute_count)
    ]
    _require_declared_member_correspondence(layout, names, plan)
    return tuple(occurrences)


def _require_member_correspondence(
    layout: EntityLayout, names: WireNames, plan: PublicationPlan
) -> None:
    """Refuse unless the class carries the model's member row in the model's order,
    each position of the kind the model gives it.

    Kind is checked as well as name because it is what a positional row lost: the
    identity-keyed algebra this door replaced named the member a carrier filled
    and so knew which kind that identity was, while a row of the right width says
    only how many positions there are. A model calling position ``i`` a Value
    Object occurrence where the composed class maps it as a scalar therefore
    reaches here rather than letting the container walk reinterpret a scalar as
    a Value Object row. Scalar admission itself belongs to the producer of the
    already-judged Entity State and is not repeated here.
    """
    row = tuple(
        (
            *(names.name_to_py.get(attribute.identity.name) for attribute in layout.attributes),
            *(
                names.name_to_py.get(occurrence.identity.path[-1])
                for occurrence in layout.occurrences
            ),
        )
    )
    if row != plan.py_names:
        raise _correspondence_refusal(
            layout.concrete,
            f"the model lays out members {row} and the class is laid out as {plan.py_names}",
        )
    for position, occurrence in enumerate(layout.occurrences, start=layout.attribute_count):
        if plan.occurrences.get(position + 1) is None:
            raise _correspondence_refusal(
                layout.concrete,
                f"the model calls member {position} ({plan.py_names[position]!r}) a Value "
                "Object occurrence, and the class holds None at that position",
                identity=occurrence.identity,
            )


def _require_declared_member_correspondence(
    layout: EntityLayout, names: WireNames, plan: PublicationPlan
) -> None:
    """Refuse unless each position's two sides are the same declared member.

    A local name addresses a member only within one ancestry. Two Entities of one
    model may each declare ``payload``, so a class composed under an identity
    whose ancestry runs through one of them and a layout derived where it runs
    through the other spell one row and mean two. Comparing the accepted metadata
    prevents already-judged state for one declaration from being installed under
    another declaration that happens to have the same local name; it compares the
    declaring identity, declared type, and occurrence subtree without re-judging
    the row's values.

    Last, because every disagreement the checks above name is a metadata
    disagreement too and each says which one in its own terms; what reaches here
    is a row that corresponds in spelling, kind, and Value Object Class and still
    means two different members.
    """
    for position, declared in enumerate((*layout.attributes, *layout.occurrences)):
        py_name = plan.py_names[position]
        carried = names.members.get(py_name)
        if carried != declared:
            raise _correspondence_refusal(
                layout.concrete,
                f"the model declares member {position} ({py_name!r}) as {declared} "
                f"and the class declares it as {carried}",
                identity=declared.identity,
            )


def _require_relationship_correspondence(
    layout: EntityLayout, names: WireNames, plan: PublicationPlan
) -> None:
    """Refuse unless the class's relationship tail is the model's canonical order,
    each position naming the direction the model declares there.

    The tail carries no presence bit and no name once a row is written, so a
    direction installed at another direction's position is a loaded arm answered
    for the wrong relationship — silently, and for the life of the graph. A local
    name is not that direction: an inherited direction keeps the identity of the
    ancestor that declared it, and two ancestries declaring one name at different
    levels spell one tail and mean two relationships, whose targets and
    cardinalities need not agree. Comparing whole identities refuses that pair
    here, at the Entity whose row it would misdirect.
    """
    tail = tuple(names.relationship_py.get(direction.name) for direction in layout.relationships)
    laid_out = tuple(
        py_name for py_name, _ in sorted(plan.relationships.items(), key=lambda pair: pair[1])
    )
    if tail != laid_out:
        raise _correspondence_refusal(
            layout.concrete,
            f"the model lays out relationships {tail} and the class is laid out as {laid_out}",
        )
    for position, direction in enumerate(layout.relationships):
        py_name = laid_out[position]
        carried = names.relationship_identities.get(py_name)
        if carried != direction:
            raise _correspondence_refusal(
                layout.concrete,
                f"the model lays out relationship {position} ({py_name!r}) as "
                f"{direction} and the class navigates {carried} there",
                identity=direction,
            )


def _proven_occurrence(
    concrete: EntityIdentity,
    declared: ValueObjectMetadata | NestedValueObjectMetadata,
    vo_class: type,
    *,
    path: str,
) -> _OccurrenceFacts:
    """Refuse unless one occurrence's own path layout is its Value Object class's
    own laid-out order, at every containment depth, and answer its facts.

    Accepted contextual bindings are keyed to a containment path and a
    publication plan to a class, so the two are checked against each other here:
    one class bound at two paths is laid out once and must correspond at both.
    """
    plan = plan_of(vo_class)
    name_to_py = shape_of(vo_class).name_to_py
    row = tuple(name_to_py.get(member.name) for member in declared.document_shape.members)
    if row != plan.py_names:
        raise _correspondence_refusal(
            concrete,
            f"{path} lays out members {row} and {vo_class.__name__} is laid out as {plan.py_names}",
            identity=declared.identity,
        )
    nested: list[_OccurrenceFacts] = []
    for position, occurrence in enumerate(declared.value_objects, start=len(declared.attributes)):
        py_name = cast("str", row[position])
        nested_class = plan.occurrences.get(position + 1)
        if nested_class is None:
            raise _correspondence_refusal(
                concrete,
                f"{path} calls member {position} ({py_name!r}) a nested occurrence, and "
                f"{vo_class.__name__} holds None there",
                identity=occurrence.identity,
            )
        nested.append(
            _proven_occurrence(concrete, occurrence, nested_class, path=f"{path}.{py_name}")
        )
    return _OccurrenceFacts(
        declared, vo_class, plan, declared.multiplicity is Multiplicity.MANY, tuple(nested)
    )


def _correspondence_refusal(
    concrete: EntityIdentity,
    detail: str,
    *,
    identity: EntityIdentity | MemberIdentity | RelationshipIdentity | None = None,
) -> GraphConstructionError:
    """The one refusal every correspondence disagreement earns, naming both sides."""
    return GraphConstructionError(
        code="entity-graph-layout-mismatch",
        message=(
            f"the class composed for {concrete.canonical} is not laid out the way this "
            f"model lays it out, so no positional row addresses it: {detail}"
        ),
        identity=concrete if identity is None else identity,
    )


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

    ``populating`` is the allocation index of the node being populated, which a
    refusal at any Value Object depth names.
    """

    __slots__ = (
        "_indices",
        "bitmaps",
        "facts",
        "handles",
        "instances",
        "populated",
        "populating",
    )

    def __init__(self) -> None:
        self.facts: list[_EntityFacts] = []
        self.handles: list[NodeHandle] = []
        self.instances: list[object] = []
        self.populated: list[bool] = []
        self.bitmaps: dict[int, int] = {}
        self.populating = -1
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
                identity=self._scope.facts[index].layout.concrete,
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
    """One class-backed model's graph-construction collaboration.

    Per model rather than per read: it is the home of the per-Entity facts
    derived once from accepted metadata and the class composed under each
    identity — the concrete class, its publication plan, each Value Object
    occurrence path's proven class, and the relationship cardinalities — and
    models are few and long-lived where reads are many. Every Entity's facts are
    derived when the collaboration is constructed, so construction is the one
    fallible point and a lookup afterwards can fail only by naming an Entity the
    model does not declare. Bound to one model at construction, ``construct(...)`` takes no
    model argument and cannot be handed a mismatched one.

    It takes its collaborators rather than reaching for them: the cataloged
    model — one accepted Metamodel and the member layouts derived from it — and
    the index of the classes composed under that model. The layouts its rows are
    written against are therefore the ones its caller reads, and a model beside a
    catalog that did not produce it is unconstructible rather than checked.
    """

    __slots__ = ("_facts",)

    def __init__(self, cataloged: CatalogedModel, classes: ClassIndex) -> None:
        """Derive every Entity's construction facts, or raise
        :class:`GraphConstructionError`."""
        self._facts: Mapping[EntityIdentity, _EntityFacts] = MappingProxyType(
            {
                entity.identity: _entity_facts(cataloged, classes, entity.identity)
                for entity in cataloged.meta.entities
            }
        )

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
        """``entity``'s construction facts, refusing an Entity this model does
        not declare."""
        facts = self._facts.get(entity)
        if facts is None:
            raise GraphConstructionError(
                code="entity-graph-invalid-entity",
                message=(
                    f"{entity.canonical} is not an Entity this Domain Model composed a class for"
                ),
                identity=entity,
            )
        return facts


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
                identity=scope.facts[index].layout.concrete,
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

    Results buffer here and attach only after the last factory succeeds, so the
    first failure discards every buffered result and leaves every node
    lifecycle-state-free — including the nodes whose own factory already
    returned. It leaves them populated, and it leaves a factory that kept what
    its view resolved holding that node; withholding the roots is the whole of
    what this discards on the caller's behalf.
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
    """Resolve both rows, then attach one node's whole state in a single write.

    Every refusal happens before attachment, so a row this collaboration rejects
    leaves its shell exactly as allocation left it: no partially populated node
    exists at any point, and a node whose relationship row fails carries none of
    the members the same call already read.
    """
    facts = scope.facts[index]
    scope.populating = index
    try:
        publish_positional(
            facts.plan,
            cast("BaseModel", scope.instances[index]),
            members,
            relationships,
            context=scope,
            node=index,
            occurrence=_entity_occurrence,
            relationship=_entity_relationship,
            bitmaps=scope.bitmaps,
        )
    except RowShapeError as refusal:
        raise _row_refusal(
            refusal,
            relationships if refusal.tail else members,
            index=index,
            identity=facts.layout.concrete,
        ) from None


def _row_refusal(
    refusal: RowShapeError, row: object, *, index: int, identity: EntityIdentity
) -> GraphConstructionError:
    """The refusal a node's row earns for being anything but an exact built-in
    tuple of the model-fixed width.

    Width is the whole membership check a positional row needs. Every declared
    member has a position and a position names nothing else, so a row of the
    model's own width names each declared member exactly once — which is why the
    two rejections the identity-keyed algebra made separately do not survive as
    checks: an undeclared member has no position to occupy, and a member named
    twice has one position to occupy. What is left is a row that is not the
    model's membership at all: too many positions, or too few.
    """
    kind = "broad-relationship" if refusal.tail else "member"
    if type(row) is not tuple:
        message = f"a {kind} row arrives as an exact tuple, not {type(row).__name__}"
    else:
        message = (
            f"{identity.canonical} lays out {refusal.width} {kind} positions, "
            f"and this row carries {len(cast('tuple[object, ...]', row))}"
        )
    return GraphConstructionError(
        code="entity-graph-invalid-member", message=message, index=index, identity=identity
    )


def _entity_relationship(scope: _CallScope, index: int, position: int, arm: object) -> object:
    """One loaded relationship position's installed value: ``None``, a related
    instance, or an exact tuple of them.

    The position's own value names its arm — ``None`` is loaded-null, an exact
    tuple is loaded-many with ``()`` its empty case, and a handle is loaded-one —
    so the declared cardinality is the only thing that decides whether that arm
    is admissible. Anything else at the position is no arm at all, which is what
    a caller-defined tuple subtype and a mutable sequence both are.
    """
    facts = scope.facts[index]
    many = facts.many[position]
    if type(arm) is tuple:
        if not many:
            raise GraphConstructionError(
                code="entity-graph-invalid-value",
                message=(
                    f"{facts.layout.relationships[position].name} is a to-one direction "
                    "and takes no loaded-many arm"
                ),
                index=index,
                identity=facts.layout.relationships[position],
            )
        return tuple(
            scope.instances[_index_of(scope, node, operation="populate")]
            for node in cast("tuple[object, ...]", arm)
        )
    if many:
        raise GraphConstructionError(
            code="entity-graph-invalid-value",
            message=(
                f"{facts.layout.relationships[position].name} is a to-many direction "
                "and takes only a loaded-many arm"
            ),
            index=index,
            identity=facts.layout.relationships[position],
        )
    if arm is None:
        return None
    if isinstance(arm, NodeHandle):
        return scope.instances[_index_of(scope, arm, operation="populate")]
    raise GraphConstructionError(
        code="entity-graph-invalid-value",
        message=(
            f"{facts.layout.relationships[position].name} received {type(arm).__name__}, "
            "which is no relationship arm"
        ),
        index=index,
        identity=facts.layout.relationships[position],
    )


def _entity_occurrence(scope: _CallScope, index: int, position: int, value: object) -> object:
    facts = scope.facts[index]
    return _build_occurrence(
        value, facts.occurrences[position - facts.layout.attribute_count], scope
    )


def _record_occurrence(
    scope: _CallScope, occurrence: _OccurrenceFacts, position: int, value: object
) -> object:
    return _build_occurrence(
        value, occurrence.nested[position - len(occurrence.declared.attributes)], scope
    )


def _build_occurrence(value: object, occurrence: _OccurrenceFacts, scope: _CallScope) -> object:
    """One Value Object occurrence as frozen instances, checked for container
    shape first.

    The declared multiplicity decides the shape rather than the value does: a One
    slot's member row and a Many slot's tuple of them are both tuples, and only
    the declaration distinguishes them. A Many occurrence has no absent state at
    all: it takes an exact tuple, empty for its zero-element value.
    """
    if occurrence.many:
        if type(value) is not tuple:
            raise _value_refusal(
                scope, occurrence, "is a Many occurrence and takes an exact tuple of member rows"
            )
        return tuple(
            _build_record(row, occurrence, scope) for row in cast("tuple[object, ...]", value)
        )
    if value is None:
        # A One occurrence absent from the document, stored as JSON null, or
        # stored in the wrong kind all arrive here as `None`: reading a document
        # applies Predicate-algebra absence collapse, so this is the whole
        # composite being not present rather than a nullability verdict to
        # re-derive against a collapse that already happened.
        return None
    return _build_record(value, occurrence, scope)


def _build_record(row: object, occurrence: _OccurrenceFacts, scope: _CallScope) -> object:
    """One positional member row as a frozen Value Object instance, at every depth.

    The row is that occurrence's own leaves in declaration order, then its nested
    occurrences in theirs, with ``ABSENT`` at a position the read carried nothing
    for. Field presence is preserved rather than flattened: an absent position
    reads as ``None`` (or ``()``) and stays outside ``model_fields_set``, while a
    position carrying ``None`` reads the same and is inside it — which is what
    keeps canonical document serialization able to omit the former and emit the
    latter as an explicit null.
    """
    record = allocate(cast("type[Any]", occurrence.cls))
    try:
        publish_positional(
            occurrence.plan,
            record,
            cast("tuple[object, ...]", row),
            (),
            context=scope,
            node=occurrence,
            occurrence=_record_occurrence,
            bitmaps=scope.bitmaps,
        )
    except RowShapeError as refusal:
        if type(row) is not tuple:
            detail = f"takes a member row as an exact tuple, not {type(row).__name__}"
        else:
            detail = (
                f"lays out {refusal.width} member positions, "
                f"and this row carries {len(cast('tuple[object, ...]', row))}"
            )
        raise _value_refusal(scope, occurrence, detail) from None
    return record


def _value_refusal(
    scope: _CallScope, occurrence: _OccurrenceFacts, detail: str
) -> GraphConstructionError:
    """The refusal one Value Object value earns, labelled by its containment path."""
    identity = occurrence.declared.identity
    entity = scope.facts[scope.populating].layout.concrete
    return GraphConstructionError(
        code="entity-graph-invalid-value",
        message=f"{entity.canonical}.{'.'.join(identity.path)} {detail}",
        index=scope.populating,
        identity=identity,
    )
