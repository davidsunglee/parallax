"""Entity Graph Construction: the per-model facts a node-indexed graph publishes
against, derived and proved once, and the one entry point that publishes it.

The loops that allocate, fill and attach run in
:mod:`~parallax.core.entity._row_fill`; this module keeps what is derived once
per model and the refusals a model/class disagreement earns.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import Protocol, cast

from pydantic import BaseModel

from parallax.core.entity._declaration import (
    LIFECYCLE_STATE_SLOT,
    WireNames,
    shape_of,
    wire_names_of,
)
from parallax.core.entity._errors import GraphConstructionError
from parallax.core.entity._instance_state import PublicationPlan, plan_of
from parallax.core.entity._instance_state import relationship as relationship_state
from parallax.core.entity._layout import CatalogedModel, EntityLayout
from parallax.core.entity._model import ClassIndex
from parallax.core.entity._row_fill import EntityFacts, OccurrenceFacts
from parallax.core.entity._row_fill import publish as publish_graph
from parallax.core.metamodel import (
    EntityIdentity,
    MemberIdentity,
    OccurrenceMetadata,
    RelationshipIdentity,
)

__all__ = [
    "EntityGraphConstruction",
    "IndexedGraph",
    "lifecycle_state_of",
    "relationship_value_of",
    "require_correspondence",
]


class IndexedGraph(Protocol):
    """One graph of Entity nodes addressed by index, node 0 its root.

    ``member_values`` is a node's member row in its layout's member order:
    every Attribute, then every top-level Value Object occurrence, ``ABSENT``
    where the read carried nothing, and a Value Object's own member row — or,
    for a Many occurrence, an exact tuple of them — at an occurrence position.
    ``relationship_values`` has one position per navigable direction in the
    layout's relationship order, each ``UNLOADED``, ``None`` for loaded-null, a
    node index for a loaded to-one, or an exact tuple of node indices for a
    loaded to-many, ``()`` its empty case.
    """

    def __len__(self) -> int: ...

    def layout(self, node: int) -> EntityLayout: ...

    def member_values(self, node: int) -> tuple[object, ...]: ...

    def relationship_values(self, node: int) -> tuple[object, ...]: ...


def _entity_facts(
    cataloged: CatalogedModel, classes: ClassIndex, identity: EntityIdentity
) -> EntityFacts:
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
    return EntityFacts(layout, cls, plan, _proven_occurrences(layout, wire_names_of(cls), plan))


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

    Passing is what makes the plan positional afterwards: the member at layout
    position ``i`` is installed at plan position ``i`` on the strength of this
    comparison, rather than through a second mapping built beside it.

    Compared once per (class, model) — this runs where the per-Entity facts are
    derived, which is the collaboration's construction — so it fires on the
    actual pair a process publishes rather than on whichever pair a fixture
    named, and no field read ever pays for the question.
    """
    _proven_occurrences(layout, names, plan)


def _proven_occurrences(
    layout: EntityLayout, names: WireNames, plan: PublicationPlan
) -> tuple[OccurrenceFacts, ...]:
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
    direction installed at another direction's position is a loaded relationship
    value answered for the wrong relationship — silently, and for the life of the
    graph. A local
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
    declared: OccurrenceMetadata,
    vo_class: type,
    *,
    path: str,
) -> OccurrenceFacts:
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
    nested: list[OccurrenceFacts] = []
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
    return OccurrenceFacts(declared, vo_class, plan, tuple(nested))


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


class EntityGraphConstruction:
    """One class-backed model's graph-construction collaboration.

    Per model rather than per read: it is the home of the per-Entity facts
    derived once from accepted metadata and the class composed under each
    identity — the concrete class, its publication plan, each Value Object
    occurrence path's proven class, and the relationship cardinalities — and
    models are few and long-lived where reads are many. Every Entity's facts are
    derived when the collaboration is constructed, so construction is the one
    fallible point and a lookup afterwards can fail only by naming an Entity the
    model does not declare. Bound to one model at construction, ``publish(...)``
    takes no model argument and cannot be handed a mismatched one.

    It stays a boundary between Entity and the lifecycles that publish through
    it: Entity owns class selection, allocation and filling, Value Object
    construction, and lifecycle-state attachment, while each lifecycle owns the
    graph it hands over and the state it attaches.

    It takes its collaborators rather than reaching for them: the cataloged
    model — one accepted Metamodel and the member layouts derived from it — and
    the index of the classes composed under that model. The layouts its rows are
    written against are therefore the ones its caller reads, and a model beside a
    catalog that did not produce it is unconstructible rather than checked.
    """

    __slots__ = ("_cataloged", "_facts")

    def __init__(self, cataloged: CatalogedModel, classes: ClassIndex) -> None:
        """Derive every Entity's construction facts, or raise
        :class:`GraphConstructionError`."""
        self._cataloged = cataloged
        self._facts: Mapping[EntityIdentity, EntityFacts] = MappingProxyType(
            {
                entity.identity: _entity_facts(cataloged, classes, entity.identity)
                for entity in cataloged.meta.entities
            }
        )

    def publish(
        self,
        graph: IndexedGraph,
        lifecycle_states: Callable[[Sequence[object]], Sequence[object]],
    ) -> object:
        """Publish ``graph`` and answer its root, node 0, or publish nothing.

        Every node becomes a fresh instance of the class this model composed for
        its layout's Entity. ``lifecycle_states`` is called once, after every
        instance is filled and every cycle closed, with the instances in node
        order; it answers one opaque state per node, and those states are
        attached only once all of them have arrived and been counted.

        Exceptions the graph or the callback raise propagate unchanged. A
        refusal or such an exception attaches no lifecycle state to any node,
        and cannot revoke an instance the callback was handed and kept.
        """
        return publish_graph(self._facts, graph, lifecycle_states)

    @property
    def cataloged(self) -> CatalogedModel:
        """The cataloged model whose layouts every Entity's facts were proved against."""
        return self._cataloged

    def proves(self, cls: type, entity: EntityIdentity) -> bool:
        """Whether ``cls`` is the class this model composed for ``entity``, and so
        already passed :func:`require_correspondence` against ``entity``'s layout
        in :attr:`cataloged`."""
        facts = self._facts.get(entity)
        return facts is not None and facts.cls is cls

    def facts_for(self, entity: EntityIdentity) -> EntityFacts:
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

    Entity attaches whatever a lifecycle answered and never interprets it, so
    the value's meaning belongs entirely to the lifecycle that produced it.
    """
    return getattr(instance, LIFECYCLE_STATE_SLOT, None)
