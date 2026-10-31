"""Publish one node-indexed graph: allocate every instance, fill each from its
rows, then attach every lifecycle state or none.

Every instance exists before any is filled, so a relationship value names an
instance by its node index and a cycle closes on an object that already exists.
Each instance's whole declared state is assembled locally and attached in one
write after every refusal its rows can earn, so no instance is ever partly
filled. The lifecycle states are buffered and counted before the first is
attached; a refusal or a failing callback attaches none, but cannot revoke
filled instances the callback was handed and kept.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

from parallax.core.entity._construction_input import ABSENT, UNLOADED
from parallax.core.entity._entity import attach_lifecycle_state
from parallax.core.entity._errors import GraphConstructionError
from parallax.core.entity._instance_state import allocate, attach_row
from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import Multiplicity

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from pydantic import BaseModel

    from parallax.core.entity._graph_construction import IndexedGraph
    from parallax.core.entity._instance_state import PublicationPlan
    from parallax.core.metamodel import EntityIdentity, OccurrenceMetadata

__all__ = ["EntityFacts", "OccurrenceFacts", "compact_row", "publish"]

_NO_LAYOUT: Final = object()


class _InvalidOccurrence(Exception):
    """A Value Object value refused at any containment depth, raised where the
    owning node is unknown and translated once by the Entity row that holds it."""

    def __init__(self, occurrence: OccurrenceFacts, detail: str) -> None:
        super().__init__(detail)
        self.occurrence = occurrence
        self.detail = detail


class OccurrenceFacts:
    """One Value Object occurrence path, proven against the class bound at it.

    Correspondence settles the class and its publication plan once per path, so
    a record publishes against them without resolving either again. ``nested``
    is aligned to the occurrence's own nested occurrences, which its row lays
    out after its scalars.
    """

    __slots__ = (
        "attributes",
        "cls",
        "declared",
        "many",
        "nested",
        "plan",
        "template",
        "width",
    )

    def __init__(
        self,
        declared: OccurrenceMetadata,
        cls: type,
        plan: PublicationPlan,
        nested: tuple[OccurrenceFacts, ...],
    ) -> None:
        self.declared = declared
        self.cls = cls
        self.plan = plan
        self.many = declared.multiplicity is Multiplicity.MANY
        self.nested = nested
        self.template = plan.template
        self.width = len(plan.py_names)
        self.attributes = self.width - len(plan.occurrences)

    def build(self, value: object, bitmaps: dict[int, int]) -> object:
        """One occurrence's value as frozen Value Object instances.

        The declared multiplicity decides the container rather than the value
        does: a One's member row and a Many's tuple of them are both tuples. A
        Many takes an exact tuple, empty for its zero-element value, and has no
        absent state. A One arriving as ``None`` is the document's own
        not-present state — absent, stored null, or stored in the wrong kind,
        which reading a document already collapsed — rather than a nullability
        verdict to derive again.
        """
        if self.many:
            if type(value) is not tuple:
                raise _InvalidOccurrence(
                    self, "is a Many occurrence and takes an exact tuple of member rows"
                )
            return tuple([self.record(row, bitmaps) for row in cast("tuple[object, ...]", value)])
        if value is None:
            return None
        return self.record(value, bitmaps)

    def record(self, member_values: object, bitmaps: dict[int, int]) -> object:
        """One positional member row as a new frozen Value Object instance."""
        instance = allocate(cast("type[BaseModel]", self.cls))
        self.fill(instance, member_values, bitmaps)
        return instance

    def fill(self, instance: BaseModel, member_values: object, bitmaps: dict[int, int]) -> None:
        """Attach ``member_values`` to an unfilled ``instance`` in one write.

        Presence is kept per position at every depth: an ``ABSENT`` position
        reads its declared default outside ``model_fields_set``, while one
        carrying ``None`` reads the same and is inside it, which is what lets
        canonical serialization omit the first and spell the second as null.
        """
        row = cast("tuple[object, ...]", member_values)
        if type(row) is not tuple or len(row) != self.width:
            raise _InvalidOccurrence(self, _member_row_detail(row, self.width))
        attach_row(
            instance, tuple(compact_row(self.template, self.attributes, self.nested, row, bitmaps))
        )


class EntityFacts:
    """Everything one Entity's publication needs: the exact-model member layout
    its rows are written against, the Entity Class composed under that identity,
    and the publication plan that class carries.

    Correspondence binds ``layout`` and ``plan``: once it passes, layout
    position ``i`` is plan position ``i``, so a row publishes positionally
    without a per-member record pairing them. ``many`` says whether each
    direction in the layout's relationship order is to-many, and
    ``occurrences`` holds each top-level occurrence's proven facts in the
    layout's occurrence order.
    """

    __slots__ = (
        "attributes",
        "cls",
        "layout",
        "many",
        "occurrences",
        "plan",
        "tail",
        "template",
        "width",
    )

    def __init__(
        self,
        layout: EntityLayout,
        cls: type,
        plan: PublicationPlan,
        occurrences: tuple[OccurrenceFacts, ...],
    ) -> None:
        self.layout = layout
        self.cls = cls
        self.plan = plan
        self.many = tuple(direction in layout.to_many for direction in layout.relationships)
        self.occurrences = occurrences
        self.template = plan.template
        self.width = len(plan.py_names)
        self.attributes = self.width - len(plan.occurrences)
        self.tail = len(plan.relationships)

    def new_empty_instance(self) -> BaseModel:
        """One unfilled frozen instance of the class, which a relationship can
        name before it holds anything."""
        return allocate(cast("type[BaseModel]", self.cls))

    # One frame per node is the whole of this step's call cost: splitting the
    # relationship loop into a helper would add a call per node it publishes.
    def fill(  # noqa: C901
        self,
        instance: BaseModel,
        member_values: tuple[object, ...],
        relationship_values: tuple[object, ...],
        instances: tuple[object, ...],
        bitmaps: dict[int, int],
        node: int,
    ) -> None:
        """Attach one node's whole declared state to its unfilled ``instance``.

        Both rows' shapes are checked before any Value Object is built or
        relationship value resolved, and every refusal precedes the one write.
        A relationship value resolves through ``instances`` by node index.
        """
        width = self.width
        if type(member_values) is not tuple or len(member_values) != width:
            raise _row_refusal(self, member_values, width, node, kind="member")
        if type(relationship_values) is not tuple or len(relationship_values) != self.tail:
            raise _row_refusal(
                self, relationship_values, self.tail, node, kind="broad-relationship"
            )
        try:
            row = compact_row(
                self.template, self.attributes, self.occurrences, member_values, bitmaps
            )
        except _InvalidOccurrence as refusal:
            raise _occurrence_refusal(self, refusal, node) from None
        offset = width + 1
        for position, value in enumerate(relationship_values):
            if value is UNLOADED:
                continue
            if type(value) is tuple:
                if not self.many[position]:
                    raise _cardinality_refusal(self, position, node, many=False)
                row[offset + position] = _related_many(
                    self, position, cast("tuple[object, ...]", value), instances, node
                )
            elif self.many[position]:
                raise _cardinality_refusal(self, position, node, many=True)
            elif value is None:
                row[offset + position] = None
            elif type(value) is int and 0 <= value < len(instances):
                row[offset + position] = instances[value]
            else:
                raise _index_refusal(self, position, value, node)
        attach_row(instance, tuple(row))


def compact_row(
    template: tuple[object, ...],
    attributes: int,
    occurrences: tuple[OccurrenceFacts, ...],
    member_values: tuple[object, ...],
    bitmaps: dict[int, int],
) -> list[object]:
    """``template`` filled from ``member_values``: the presence bitmap at index 0,
    each carried member at its position plus one, each Value Object position
    built through its occurrence facts.

    ``bitmaps`` is one publication's memo of the presence masks its rows have
    assembled. Every row of one class in one publication comes from one read
    shape and so repeats one pattern, which the memo turns into one shared
    integer per pattern; it lives only as long as that publication.
    """
    row = list(template)
    bitmap = 0
    for position, member in enumerate(member_values):
        if member is not ABSENT:
            row[position + 1] = (
                member
                if position < attributes
                else occurrences[position - attributes].build(member, bitmaps)
            )
            bitmap |= 1 << position
    row[0] = bitmaps.setdefault(bitmap, bitmap)
    return row


def publish(
    facts: Mapping[EntityIdentity, EntityFacts],
    graph: IndexedGraph,
    lifecycle_states: Callable[[Sequence[object]], Sequence[object]],
) -> object:
    """``graph``'s root instance, published with every node of its graph.

    ``lifecycle_states`` is called once, with every filled instance in node
    order, and answers one opaque state per node. Exceptions raised by the
    graph or the callback propagate unchanged.
    """
    count = len(graph)
    if count == 0:
        raise GraphConstructionError(
            code="entity-graph-invalid-value",
            message="a graph publishes its node 0, and this graph has no nodes",
        )
    bound: list[EntityFacts] = []
    shells: list[BaseModel] = []
    last: object = _NO_LAYOUT
    entity: EntityFacts | None = None
    for node in range(count):
        layout = graph.layout(node)
        if layout is not last:
            entity = facts.get(layout.concrete) if type(layout) is EntityLayout else None
            if entity is None or (entity.layout is not layout and entity.layout != layout):
                raise _layout_refusal(layout, entity, node)
            last = layout
        bound.append(cast("EntityFacts", entity))
        shells.append(cast("EntityFacts", entity).new_empty_instance())
    instances = tuple(shells)
    bitmaps: dict[int, int] = {}
    member_values = graph.member_values
    relationship_values = graph.relationship_values
    for node, instance in enumerate(shells):
        bound[node].fill(
            instance, member_values(node), relationship_values(node), instances, bitmaps, node
        )
    states = lifecycle_states(instances)
    buffered = cast("tuple[object, ...]", states) if type(states) is tuple else tuple(states)
    if len(buffered) != count:
        raise GraphConstructionError(
            code="entity-graph-invalid-value",
            message=(
                f"lifecycle states answer one state per node; this graph has {count} "
                f"nodes and {len(buffered)} states arrived"
            ),
        )
    for instance, state in zip(shells, buffered, strict=True):
        attach_lifecycle_state(instance, state)
    return instances[0]


def _related_many(
    entity: EntityFacts,
    position: int,
    value: tuple[object, ...],
    instances: tuple[object, ...],
    node: int,
) -> tuple[object, ...]:
    """A loaded to-many value's instances, in the value's order."""
    count = len(instances)
    for target in value:
        if type(target) is not int or not 0 <= target < count:
            raise _index_refusal(entity, position, target, node)
    return tuple([instances[cast("int", target)] for target in value])


def _member_row_detail(row: object, width: int) -> str:
    if type(row) is not tuple:
        return f"takes a member row as an exact tuple, not {type(row).__name__}"
    return (
        f"lays out {width} member positions, and this row carries "
        f"{len(cast('tuple[object, ...]', row))}"
    )


def _row_refusal(
    entity: EntityFacts, row: object, width: int, node: int, *, kind: str
) -> GraphConstructionError:
    """The refusal a node's top-level row earns for being anything but an exact
    built-in tuple of the model-fixed width.

    Width is the whole membership check a positional row needs: every declared
    member has a position and a position names nothing else, so what is left to
    refuse is a row that is not the model's membership at all.
    """
    identity = entity.layout.concrete
    if type(row) is not tuple:
        message = f"a {kind} row arrives as an exact tuple, not {type(row).__name__}"
    else:
        message = (
            f"{identity.canonical} lays out {width} {kind} positions, "
            f"and this row carries {len(cast('tuple[object, ...]', row))}"
        )
    return GraphConstructionError(
        code="entity-graph-invalid-member", message=message, index=node, identity=identity
    )


def _occurrence_refusal(
    entity: EntityFacts, refusal: _InvalidOccurrence, node: int
) -> GraphConstructionError:
    """The refusal one Value Object value earns, labelled by its containment path
    and naming the node whose row holds it."""
    identity = refusal.occurrence.declared.identity
    return GraphConstructionError(
        code="entity-graph-invalid-value",
        message=f"{entity.layout.concrete.canonical}.{'.'.join(identity.path)} {refusal.detail}",
        index=node,
        identity=identity,
    )


def _cardinality_refusal(
    entity: EntityFacts, position: int, node: int, *, many: bool
) -> GraphConstructionError:
    direction = entity.layout.relationships[position]
    message = (
        f"{direction.name} is a to-many direction and takes only a tuple of node indices"
        if many
        else f"{direction.name} is a to-one direction and takes no tuple of node indices"
    )
    return GraphConstructionError(
        code="entity-graph-invalid-value", message=message, index=node, identity=direction
    )


def _index_refusal(
    entity: EntityFacts, position: int, value: object, node: int
) -> GraphConstructionError:
    direction = entity.layout.relationships[position]
    return GraphConstructionError(
        code="entity-graph-invalid-value",
        message=f"{direction.name} received {value!r}, which names no node of this graph",
        index=node,
        identity=direction,
    )


def _layout_refusal(
    layout: object, entity: EntityFacts | None, node: int
) -> GraphConstructionError:
    """The refusal a node's layout earns: an Entity this model composed no class
    for, or a layout other than the one this model lays that Entity out by."""
    if type(layout) is not EntityLayout:
        return GraphConstructionError(
            code="entity-graph-layout-mismatch",
            message=f"node {node} answers {type(layout).__name__} for its layout",
            index=node,
        )
    concrete = layout.concrete
    if entity is None:
        return GraphConstructionError(
            code="entity-graph-invalid-entity",
            message=f"{concrete.canonical} is not an Entity this Domain Model composed a class for",
            index=node,
            identity=concrete,
        )
    return GraphConstructionError(
        code="entity-graph-layout-mismatch",
        message=(
            f"node {node} lays {concrete.canonical} out other than this model lays it "
            "out, so no row of it addresses the composed class"
        ),
        index=node,
        identity=concrete,
    )
