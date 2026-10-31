from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Final, Protocol, Self, SupportsIndex, cast

from parallax.core._execution._unit_work.retain import InsertionIdentity, ReadEvidence
from parallax.core.base import (
    INFINITY_LITERAL,
    TIMESTAMP,
    ManagedValue,
    NeutralType,
    TemporalBound,
)
from parallax.core.deep_fetch import RelationshipViewKey
from parallax.core.document_codec import (
    MemberShape,
    OccurrenceCarrier,
    encode_occurrence,
    occurrence_shape,
)
from parallax.core.entity import UNLOADED, Entity, EntityGraphConstruction
from parallax.core.entity._declaration import wire_names_of
from parallax.core.entity._entity import CHANGE_RECORD_SLOT, ChangeRecord
from parallax.core.entity._graph_construction import require_correspondence
from parallax.core.entity._instance_state import (
    declared_values,
    is_published,
    named_state_value,
    plan_of,
)
from parallax.core.entity._instance_state import (
    relationship as relationship_state,
)
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    Multiplicity,
    OccurrenceMetadata,
    TemporalDimension,
)
from parallax.core.metamodel._temporal_structure import TEMPORAL_MEMBERS
from parallax.core.read_delivery._page import ABSENT
from parallax.core.temporal_read import Edge, Pin, TemporalFacet
from parallax.core.wire import decode_canonical_wire
from parallax.core.wire._codec import encode_managed_wire
from parallax.snapshot._inspection import (
    NodeProvenance,
    PageProvenance,
    RootConformance,
    SnapshotInspectionError,
    SnapshotNodeState,
    pin_for_shape,
    snapshot_state_of,
)
from parallax.snapshot._publication._root import RootView

__all__ = [
    "FAMILY_VARIANT_KEY",
    "InstanceReader",
    "NodeReader",
    "RootViewReader",
    "WireEntity",
    "WireValue",
    "authoring_of",
    "opened_wire_entity",
    "projection_entity",
    "read_evidence_of",
    "shared_wire_encoder",
    "stored_entity_of",
    "wire_edge_of",
    "wire_pin_of",
]

type WireValue = bool | int | float | str | list[WireValue] | dict[str, WireValue] | None
"""One position in a Wire result: a canonical Wire Value, a nested Value Object
mapping, an included Entity node, or an ordered collection of either.

Structural rather than nominal, deliberately: a runtime Wire value is a frozen
built-in subclass, so it satisfies this alias while remaining directly
JSON-serializable and structurally equal to the plain value it mirrors. That
freezing is a runtime property rather than a static one, and it holds at every
depth against every mutation reaching a value through the instance; the base
descriptors a caller can reach around the instance for
(``dict.__setitem__(value, ...)``, ``list.append(value, ...)``) stay open, for
the reason :class:`WireEntity` gives. Spelling immutability statically instead,
through public frozen list and mapping types, would make every ordinary mapping
statically unusable as Parallax input."""

FAMILY_VARIANT_KEY = "familyVariant"
"""The key an inheritance participant's stable variant spelling is published
under. It names no declared member, which is why it is fixed here rather than
resolved from the model."""

_FROZEN = "a Wire read result refuses mutation through the instance"


class WireEntity(Mapping[str, "WireValue"]):
    """A frozen Entity node returned by a Wire read.

    Names every returned Entity mapping — a result root and an included node
    alike — so a caller and a static checker can both say "this came from a
    Parallax Wire read" without a second type for the root position. It is
    read-only and non-constructible: the runtime value is a private frozen
    ``dict`` subclass, so ordinary indexing, iteration, ``get``, ``items``, and
    the rest of the mapping protocol work while ``isinstance(value, dict)``
    stays true and every mutation reaching the value — each named mutator, the
    operators, and ``value.__init__(...)`` — raises :class:`TypeError`. Being a
    ``dict`` is the bound on that: a caller going around the instance to the
    base descriptor (``dict.__setitem__(value, ...)``) reaches the layout that
    makes the value a ``dict`` at all, and no ``dict`` subclass in the language
    refuses it.

    Nominal identity states provenance, never authority. It cannot prove which
    concurrency evidence a write may use, so a keyed verb still resolves that
    dynamically; and it is deliberately absent from insert data, changes,
    predicates, and Object Query input, which continue to accept ordinary
    structural mappings.
    """

    __slots__ = ()


class _FrozenMapping(dict[str, Any]):
    """A ``dict`` that refuses every mutation reaching it through the instance.

    Subclassing ``dict`` rather than wrapping one is what keeps a Wire value
    directly JSON-serializable and structurally equal to the plain mapping it
    mirrors: a serializer's ``isinstance(value, dict)`` test still passes, while
    ``type(value) is dict`` is false for a caller that means to ask whether this
    value came from Parallax. Inherited equality and the inherited ``__hash__``
    of ``None`` are both correct as they stand, so neither is restated.

    ``__init__`` is a mutator too — ``dict.__init__`` repopulates an existing
    mapping — so it refuses like the rest, and :func:`_frozen_mapping` builds an
    instance without it. What the refusals cannot reach is a caller that goes
    around the instance to the base descriptor itself
    (``dict.__setitem__(value, ...)``): that route exists for every ``dict``
    subclass in the language and closing it means not being a ``dict``, which is
    the property this value is chosen for.

    Copying answers the same object. A copy could differ from this value in
    identity alone, so allocating one buys a caller nothing and costs it the
    identity two positions of one read share.
    """

    __slots__ = ()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(_FROZEN)

    def __setitem__(self, key: str, value: Any) -> None:
        raise TypeError(_FROZEN)

    def __delitem__(self, key: str) -> None:
        raise TypeError(_FROZEN)

    def clear(self) -> None:
        raise TypeError(_FROZEN)

    def pop(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError(_FROZEN)

    def popitem(self) -> tuple[str, Any]:
        raise TypeError(_FROZEN)

    def setdefault(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError(_FROZEN)

    def update(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(_FROZEN)

    def __ior__(self, other: Any) -> Self:
        raise TypeError(_FROZEN)

    def copy(self) -> Self:
        return self

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> Self:
        return self

    def __reduce__(self) -> tuple[Any, ...]:
        """Serialize as ordinary domain data.

        A pickled Wire value crosses a boundary the source claim cannot: what
        comes back is a plain mapping with no provenance, which is exactly what
        it is. Reconstructing the frozen subclass would hand a caller a value
        that looks like a Parallax read result and carries none of its evidence.
        """
        return (dict, (dict(self),))


class _FrozenSequence(list[Any]):
    """A ``list`` that refuses every mutation reaching it through the instance,
    for the same reasons as :class:`_FrozenMapping`: an ordered Wire collection
    stays JSON-serializable, structurally equal to the plain list it mirrors, and
    unhashable — and refuses the repopulating ``__init__`` with the rest, while
    the base descriptor a caller reaches around the instance for
    (``list.append(value, ...)``) stays open to exactly the same limit."""

    __slots__ = ()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(_FROZEN)

    def __setitem__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(_FROZEN)

    def __delitem__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(_FROZEN)

    def append(self, value: Any) -> None:
        raise TypeError(_FROZEN)

    def extend(self, values: Any) -> None:
        raise TypeError(_FROZEN)

    def insert(self, index: SupportsIndex, value: Any) -> None:
        raise TypeError(_FROZEN)

    def remove(self, value: Any) -> None:
        raise TypeError(_FROZEN)

    def pop(self, index: SupportsIndex = -1) -> Any:
        raise TypeError(_FROZEN)

    def clear(self) -> None:
        raise TypeError(_FROZEN)

    def sort(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(_FROZEN)

    def reverse(self) -> None:
        raise TypeError(_FROZEN)

    def __iadd__(self, other: Any) -> Self:
        raise TypeError(_FROZEN)

    def __imul__(self, other: Any) -> Self:
        raise TypeError(_FROZEN)

    def copy(self) -> Self:
        return self

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> Self:
        return self

    def __reduce__(self) -> tuple[Any, ...]:
        return (list, (list(self),))


class _WireEntityNode(_FrozenMapping, WireEntity):
    """The one runtime realization of :class:`WireEntity`.

    Separate from :class:`_FrozenMapping` because the nominal type belongs to an
    ENTITY node alone: a nested Value Object mapping is structurally identical
    and must answer ``isinstance(value, WireEntity)`` with false, which is what
    lets a caller ask of any mapping in the result whether the read published it
    as an Entity. It is also the only node that carries provenance, and its
    slots are why: a nested Value Object mapping has none to put it in.

    Its :class:`~parallax.snapshot._inspection.NodeProvenance` is the one a
    Typed node's Snapshot state holds for the same facts, and its root
    conformance is absent only on the node an insert answered.

    Provenance rides a slot rather than a mapping entry, so it is not a key, not
    iterated, not compared, not serialized, and not carried by ``dict(value)`` —
    a plain conversion of a Wire node is ordinary domain data with no keyed-source
    status, which is exactly what it is.
    """

    __slots__ = ("_provenance",)

    _provenance: NodeProvenance


class _WireAuthoringNode(_WireEntityNode):
    """The node a Wire insert answers: no read published it, so its provenance
    states no pin, Read Evidence, or conformance, and the authority the
    insertion's admission granted rides a slot of its own.

    The authority is private exactly as Read Evidence is — not a key, not
    iterated, not compared, not serialized, and not carried by ``dict(value)``
    — and a subclass carries it, so a node a read publishes pays nothing for a
    slot it could never fill.
    """

    __slots__ = ("_authoring",)

    _authoring: InsertionIdentity


def _frozen_mapping[T: _FrozenMapping](
    cls: type[T], entries: Mapping[str, WireValue] | Iterable[tuple[str, WireValue]]
) -> T:
    """One frozen mapping of ``cls``, populated through ``dict``'s own writer.

    Construction cannot run through ``cls(entries)``: the refusing ``__init__``
    that closes ``value.__init__({...})`` closes ordinary construction with it,
    so the instance is allocated and filled directly.
    """
    value = dict.__new__(cls)
    dict[str, Any].update(value, entries)
    return value


def _frozen_sequence(values: Iterable[WireValue]) -> _FrozenSequence:
    """One frozen sequence, populated through ``list``'s own writer
    (:func:`_frozen_mapping`'s reason)."""
    value = list.__new__(_FrozenSequence)
    list[Any].extend(value, values)
    return value


def authoring_of(entity: WireEntity) -> InsertionIdentity | None:
    """The insertion authority ``entity`` carries, or ``None`` for any node but
    one a Wire insert answered."""
    return getattr(entity, "_authoring", None)


def read_evidence_of(entity: WireEntity) -> ReadEvidence | None:
    """The private Read Evidence ``entity`` carries, or ``None`` for a mapping no
    writable attempt's Wire read published.

    The one reader of the slot. A hint is never authority of its own — it names
    the exact state its read observed and nothing about what may be written —
    so this answers a fact and the write side draws the conclusion.
    """
    provenance: NodeProvenance | None = getattr(entity, "_provenance", None)
    return None if provenance is None else provenance.read_evidence


def stored_entity_of(entity: WireEntity) -> EntityIdentity | None:
    """The concrete Entity of a node a read published from conforming stored
    state, or ``None`` for any other mapping — diagnostic data under a
    classified root, the node an insert answered, or one Parallax never
    published.

    A fact about provenance alone, with or without Read Evidence beside it.
    """
    provenance: NodeProvenance | None = getattr(entity, "_provenance", None)
    if provenance is None or provenance.root_conformance is not RootConformance.CONFORMING:
        return None
    return provenance.entity


def wire_pin_of(entity: WireEntity) -> Pin | None:
    """The as-of coordinates a read-published node was read at, or ``None``
    where its family declares no As-Of Axis or no read published it."""
    provenance: NodeProvenance | None = getattr(entity, "_provenance", None)
    return None if provenance is None else provenance.pin


_TX_START: Final = TEMPORAL_MEMBERS[TemporalDimension.TRANSACTION_TIME][0].name
_VALID_START: Final = TEMPORAL_MEMBERS[TemporalDimension.VALID_TIME][0].name


def wire_edge_of(node: object) -> Edge:
    """The milestone :class:`~parallax.core.temporal_read.Edge` of a node a
    Wire read published, conforming or diagnostic, decoded from its own
    published milestone starts on every call.

    Only the read-published carrier answers; matching keys on any other mapping
    never do. The Pin decides whether the node is temporal at all, never where
    its milestone starts. Every Entity reserves the framework endpoint names in
    its top-level members, so a published ``validStart`` is the Valid-Time
    start and only a Bitemporal node publishes one.
    """
    if type(node) is not _WireEntityNode:
        raise _not_read_published(node)
    provenance = node._provenance  # pyright: ignore[reportPrivateUsage] - the carrier's own slot
    if provenance.pin is None:
        entity = provenance.entity
        raise SnapshotInspectionError(
            code="snapshot-edge-unavailable",
            message=f"{entity.canonical} is not temporal, so it stands on no milestone",
            operation="edge_of",
            entity=entity,
        )
    valid_start = node.get(_VALID_START)
    return Edge(
        tx_time=cast("dt.datetime", decode_canonical_wire(TIMESTAMP, node[_TX_START])),
        valid_time=None
        if valid_start is None
        else cast("dt.datetime", decode_canonical_wire(TIMESTAMP, valid_start)),
    )


def _not_read_published(node: object) -> SnapshotInspectionError:
    provenance: NodeProvenance | None = (
        getattr(node, "_provenance", None) if isinstance(node, _WireEntityNode) else None
    )
    entity = None if provenance is None else provenance.entity
    held = (
        f"{type(node).__name__} carries no read publication"
        if entity is None or getattr(node, "_authoring", None) is None
        else f"the {entity.canonical} node an insert answered stands on no read milestone"
    )
    return SnapshotInspectionError(
        code="snapshot-node-required",
        message=f"edge_of inspects a node a Snapshot read published; {held}",
        operation="edge_of",
        entity=entity,
    )


class NodeReader[Node](Protocol):
    """How one representation answers what the Wire renderer asks of a node.

    The renderer is generic over the native reference a representation
    addresses a node by — a node of a Root View, or a published instance — and
    asks a reader for a node's concrete Entity, its positional member values,
    one requested relationship view's raw value, and its provenance, which the
    renderer installs on the node as it stands. Everything about what those
    answers BECOME — declared-name keys, canonical scalars, the family variant,
    occurrence rendering, finite descent, aliasing — belongs to the renderer and
    the model's prepared facts, so a reader exposes storage and renders nothing.

    :meth:`concrete` is asked of every node before anything else about it, so a
    reader validates a node there once. ``member_values`` is consumed once, in
    layout order, and is never sliced or copied, so a Root View answers its
    Page-owned tuple by reference. ``relationship`` answers ``ABSENT`` for a
    view the node does not carry, ``None`` for loaded-null, a native reference
    for loaded-one, and a tuple of them for loaded-many: the answer already
    travels in the shape the renderer renders, so nothing is translated.

    ``occurrence_values`` describes the representation rather than any node:
    how a Value Object record answers its positional member values, or
    ``None`` where a record already is them.
    """

    @property
    def occurrence_values(self) -> Callable[[object], Iterable[object]] | None: ...

    def concrete(self, node: Node) -> EntityIdentity: ...

    def member_values(self, node: Node) -> Iterable[object]: ...

    def relationship(self, node: Node, view: RelationshipViewKey) -> object: ...

    def provenance(self, node: Node) -> NodeProvenance: ...

    def admission_error(self, concrete: EntityIdentity) -> Exception: ...


class RootViewReader:
    """The :class:`NodeReader` over a publication pass's Root View: a node is
    a Root View node, and every answer borrows the Root View's own state for
    the root it currently names.

    :meth:`begin_root` sets the verdict every node of the root being published
    carries, and ``temporal`` answers which nodes stand at the Root View's pin.
    A node's Read Evidence is what the Root View captured for it, which is none
    for a root publishing a finding; a node carrying none shares its Page's
    provenance for its concrete, conformance and pin.
    """

    __slots__ = ("_by_concrete", "_conformance", "_page", "_root", "_temporal")

    def __init__(self, root: RootView, temporal: TemporalFacet) -> None:
        self._root = root
        self._temporal = temporal
        self._conformance = RootConformance.CONFORMING
        self._page = PageProvenance()
        self._by_concrete: dict[EntityIdentity, NodeProvenance] = {}

    def begin_root(self, conformance: RootConformance) -> None:
        """Answer every later node with ``conformance`` at the Root View's
        current pin."""
        self._conformance = conformance
        self._by_concrete.clear()

    @property
    def occurrence_values(self) -> None:
        return None

    def concrete(self, node: int) -> EntityIdentity:
        return self._root.layout(node).concrete

    def member_values(self, node: int) -> tuple[object, ...]:
        return self._root.member_values(node)

    def relationship(self, node: int, view: RelationshipViewKey) -> object:
        # A Root View row is the union of the source rows its own concrete can
        # carry, so a node whose concrete a path-root guard excluded from the
        # level attaching this view holds NO SLOT for it, and answers absence.
        # The union's other unloaded state — a slot present and holding ABSENT,
        # left wherever a level could have reached the node but did not — cannot
        # arise at a view the renderer names: reaching the node there meant
        # following the relationship value that view's own level wrote, and a
        # level writes every parent it gathers. So a missing slot is the union's
        # width showing through, and a present one is answered exactly as its
        # level wrote it.
        slot = self._root.view_layout(node).index_of.get(view)
        return ABSENT if slot is None else self._root.view(node, slot)

    def provenance(self, node: int) -> NodeProvenance:
        root = self._root
        concrete = root.layout(node).concrete
        read_evidence = root.read_evidence(node)
        if read_evidence is not None:
            return NodeProvenance(
                concrete,
                self._conformance,
                pin_for_shape(self._temporal.shape(concrete), root.pin),
                read_evidence,
            )
        held = self._by_concrete.get(concrete)
        if held is None:
            held = self._by_concrete[concrete] = self._page.provenance_for(
                concrete,
                self._conformance,
                pin_for_shape(self._temporal.shape(concrete), root.pin),
            )
        return held

    def admission_error(  # pragma: no cover - execution admits every stored position
        self, concrete: EntityIdentity
    ) -> Exception:
        return ValueError(f"{concrete.canonical} is not admitted by the requested include position")


class InstanceReader:
    """The :class:`NodeReader` over published Typed instances, for projecting a
    Typed result as Wire.

    A node of the class ``construction`` composed for its Entity was proved
    against that Entity's layout when the construction was built, so only
    another class pays the correspondence check, once per pair per reader.
    Every node is required to be a published, unedited Snapshot node once,
    when its concrete is asked.
    """

    __slots__ = ("_checked", "_construction", "_operation", "model")

    def __init__(
        self,
        construction: EntityGraphConstruction,
        *,
        operation: str = "Snapshot.wire",
    ) -> None:
        self.model = construction.cataloged
        self._construction = construction
        self._operation = operation
        self._checked: set[tuple[type, EntityIdentity]] = set()

    @property
    def occurrence_values(self) -> Callable[[object], Iterable[object]]:
        return _record_values

    def concrete(self, node: object) -> EntityIdentity:
        entity = _required(node, self._operation).provenance.entity
        cls = type(node)
        pair = (cls, entity)
        if pair in self._checked:
            return entity
        try:
            layout = self.model.layouts.entity(entity)
            if not self._construction.proves(cls, entity):
                require_correspondence(layout, wire_names_of(cls), plan_of(cls))
        except Exception as error:
            raise SnapshotInspectionError(
                code="snapshot-wire-input-incompatible",
                message=(
                    f"{type(node).__name__} does not correspond to retained layout "
                    f"{entity.canonical}: {error}"
                ),
                operation=self._operation,
                entity=entity,
            ) from error
        self._checked.add(pair)
        return entity

    def member_values(self, node: object) -> Iterable[object]:
        return declared_values(cast("Any", node))

    def relationship(self, node: object, view: RelationshipViewKey) -> object:
        if view.narrowed_view is not None:
            return _state(node).views.get(view.narrowed_view, ABSENT)
        py_name = wire_names_of(type(node)).relationship_py.get(view.relationship.name)
        if py_name is None:  # pragma: no cover - correspondence checks every direction
            raise SnapshotInspectionError(
                code="snapshot-wire-input-incompatible",
                message=(
                    f"{type(node).__name__} declares no relationship position for "
                    f"{view.relationship}"
                ),
                operation=self._operation,
                entity=_state(node).provenance.entity,
            )
        value = relationship_state(cast("Any", node), py_name)
        return ABSENT if value is UNLOADED else value

    def provenance(self, node: object) -> NodeProvenance:
        return _state(node).provenance

    def clear(self) -> None:
        self._checked.clear()

    def admission_error(  # pragma: no cover - explicit callers check admission first
        self, concrete: EntityIdentity
    ) -> Exception:
        return SnapshotInspectionError(
            code="snapshot-wire-at-concrete-mismatch",
            message=f"{concrete.canonical} is not admitted by the requested include position",
            operation=self._operation,
            entity=concrete,
        )


def _record_values(record: object) -> Iterable[object]:
    return declared_values(cast("Any", record))


def _required(node: object, operation: str) -> SnapshotNodeState:
    projection_entity(node, operation=operation)
    return _state(node)


def _state(node: object) -> SnapshotNodeState:
    state = snapshot_state_of(node)
    assert state is not None
    return state


def projection_entity(node: object, *, operation: str = "Snapshot.wire") -> EntityIdentity:
    """Require one eligible published Snapshot Entity and answer its concrete."""
    if isinstance(node, Entity) and isinstance(
        named_state_value(node, CHANGE_RECORD_SLOT), ChangeRecord
    ):
        state = snapshot_state_of(node)
        raise SnapshotInspectionError(
            code="snapshot-wire-input-edited",
            message="an edited Entity cannot be projected as read Wire state",
            operation=operation,
            entity=None if state is None else state.provenance.entity,
        )
    published = is_published(node)
    state = snapshot_state_of(node)
    if state is None or not published:
        raise SnapshotInspectionError(
            code="snapshot-node-required",
            message="Wire projection requires a published Snapshot node",
            operation=operation,
            entity=None if state is None else state.provenance.entity,
        )
    return state.provenance.entity


def _put(rendered: dict[str, WireValue], key: str, value: WireValue) -> None:
    """Add one published field, refusing an impossible collision."""
    if key in rendered:  # pragma: no cover - Model Formation rejects this defensively
        raise ValueError(f"wire field key {key!r} has more than one contributor")
    rendered[key] = value


def _wire_scalar(neutral_type: NeutralType, value: object) -> WireValue:
    """One scalar a write states, in its canonical Wire spelling."""
    if value is None:
        return None
    if isinstance(value, TemporalBound):
        return INFINITY_LITERAL
    if type(value) in (bool, int, str):
        return cast("WireValue", value)
    return cast("WireValue", encode_managed_wire(neutral_type, cast("ManagedValue", value)))


def _wire_collection(element_type: NeutralType, value: object) -> WireValue:
    """One scalar collection as the canonical immutable Wire array of its elements."""
    return _frozen_sequence(
        _wire_scalar(element_type, element) for element in cast("Iterable[object]", value)
    )


class _SharedWireEncoder:
    """A delivery encoder retaining at most the current and preceding Page.

    Advancing a Page drops everything older than its predecessor. Equal values
    repeated across a boundary still reuse their encoded object, while values
    visited only once cannot accumulate with the delivery position.
    """

    __slots__ = ("_current", "_previous")

    def __init__(self) -> None:
        self._current: dict[tuple[NeutralType, ManagedValue], object] = {}
        self._previous: dict[tuple[NeutralType, ManagedValue], object] = {}

    def begin_page(self) -> None:
        self._previous = self._current
        self._current = {}

    def __call__(self, neutral_type: NeutralType, value: ManagedValue) -> object:
        try:
            key = (neutral_type, value)
            held = self._current.get(key, ABSENT)
            if held is ABSENT:
                held = self._previous.pop(key, ABSENT)
        except TypeError:
            return encode_managed_wire(neutral_type, value)
        if held is ABSENT:
            held = encode_managed_wire(neutral_type, value)
        self._current[key] = held
        return held

    def release(self) -> None:
        self._current.clear()
        self._previous.clear()


def shared_wire_encoder() -> _SharedWireEncoder:
    """A trusted encoder whose bounded reuse lasts for one delivery."""
    return _SharedWireEncoder()


def _tuple_elements(value: object) -> Iterable[object]:
    return cast("tuple[object, ...]", value) if isinstance(value, tuple) else ()


def _stored_values(record: object, shape: MemberShape) -> Iterable[object]:
    del shape
    return cast("tuple[object, ...]", record)


_STORED: Final = OccurrenceCarrier(ABSENT, _stored_values, _tuple_elements)


def _occurrence_mapping(entries: Iterable[tuple[str, WireValue]]) -> WireValue:
    return _frozen_mapping(_FrozenMapping, entries)


def _occurrence(
    value: object, declared: OccurrenceMetadata, carrier: OccurrenceCarrier
) -> WireValue:
    """One occurrence a write states, as the Wire value its carrier holds."""
    return encode_occurrence(
        value,
        occurrence_shape(declared),
        declared.multiplicity,
        carrier,
        encode_leaf=_wire_scalar,
        build_object=_occurrence_mapping,
        build_array=_frozen_sequence,
    )


def opened_wire_entity(
    model: CatalogedModel,
    entity: EntityIdentity,
    stated: Iterable[tuple[int, object]],
    absent: object,
    authority: InsertionIdentity,
) -> WireEntity:
    """The frozen Wire node for a row a Wire insert has just OPENED.

    A Wire insert's caller holds nothing afterwards — the Typed peer leaves the
    caller holding the instance it passed — so the verb answers the row it
    buffered, in the one representation that can be handed straight back to a
    keyed verb. The node carries the insertion's ``authority``, which is what
    makes it a keyed source at all, and no Read Evidence, since no read published
    it; the values are the payload's own, rendered through the SAME canonical
    encoding a read publishes.

    What it publishes is what this transaction STATED, not what a later read of
    the stored row will: the framework-owned members are stamped at flush and
    are absent here, and the walk is over the members the row states rather
    than the declared ones. That is exact because the row is an opening row's
    canonical member set — a complete Create Payload by `m-unit-work`'s own
    full-document rule, carrying the empty collection at every ``many`` the
    payload omitted. ``stated`` is each stated member's position beside its
    managed cell, a Value Object's in its positional form marking an omitted
    nested member ``absent``.

    ``model`` is the cataloged model the transaction writes under, so the
    member bindings and the family variant come off the one layout its catalog
    fixed for ``entity`` — the same layout a read of the row publishes against.
    """
    layout = model.layouts.entity(entity)
    selection = layout.member_selection
    bindings = selection.bindings
    names = selection.shape.members
    occurrences = (
        _STORED if absent is ABSENT else OccurrenceCarrier(absent, _stored_values, _tuple_elements)
    )
    rendered: dict[str, WireValue] = {}
    for position, value in stated:
        binding = bindings[position]
        name = names[position].name
        if isinstance(binding, AttributeMetadata):
            _put(
                rendered,
                name,
                _wire_collection(binding.type, value)
                if binding.multiplicity is Multiplicity.MANY
                else _wire_scalar(binding.type, value),
            )
            continue
        _put(rendered, name, _occurrence(value, binding, occurrences))
    if layout.family_variant is not None:
        _put(rendered, FAMILY_VARIANT_KEY, layout.family_variant)
    node = _frozen_mapping(_WireAuthoringNode, rendered)
    object.__setattr__(node, "_provenance", NodeProvenance(entity, None))
    object.__setattr__(node, "_authoring", authority)
    return node
