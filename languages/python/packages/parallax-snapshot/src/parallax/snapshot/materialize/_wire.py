"""The Wire renderer: one requested result position as frozen canonical values.

Direct Wire reads render classified :class:`~parallax.snapshot.materialize.RootView`
nodes through :class:`RootViewReader`. Typed eager and streaming reads instead
project already-published Entity nodes through :class:`EntityReader`; both use the
same :class:`WireWalk`, without reclassification or serialization. What differs is
only the representation the reader exposes to that shared walk.

Two rules give the result its shape.

**Declared names, canonical values.** Every key is the model's own declared member
name — never a physical column — and every leaf is its canonical Wire Value
(`m-wire`), the same spelling the document codec stores. A Value Object occurrence
publishes the members its carrier HOLDS: the walk follows the declared member lists,
which is what fixes key order and decodes each position by its declared type, but a
member the carrier does not hold contributes no key. Which members a read's carrier
holds — the whole of it, at every position where carried and held part — is fixed by
`m-snapshot-read` *What a materialized value carries*, and nothing here decides any
of it: the carrier is the reduced record that contract already produced, which is
why the published node and the hydrated Entity value observe one document.

**The include tree bounds the walk, not Page identity.** A Root View node keeps
every view any level loaded onto it, so following a node's own views would revisit
an ancestor forever. The unwind instead descends an :class:`IncludeTree` — the
requested Include Paths, realized as the views to follow — which strictly shrinks
with depth, so a back-reference renders its target once, in full, and terminates.
That is what replaces a primary-key stub: the tree, not a cycle detector, is what
makes the value finite.

The walk reads a node through a :class:`NodeReader`, the one seam between the
representation a node is stored in and the Wire semantics rendered over it. A
reader answers the layout a node is read against, its positional member values,
one relationship view's raw arm, and the Read Origin it carries; the walk owns
declaration order, the family variant that layout fixed, occurrence rendering,
view keys, include-tree termination, and aliasing.

Aliasing is preserved rather than copied: the walk memoizes on
``(node, subtree)``, so every position reaching one node under one subtree answers
the identical frozen object. Direct Wire publication retains that identity for one
Root View, Typed eager projection for one whole result, and Typed stream projection
for one page. Streaming clears both reader and walk at each page boundary and
terminal release.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Protocol, Self, SupportsIndex, cast

from parallax.core.base import INFINITY_LITERAL, ManagedValue, NeutralType, TemporalBound
from parallax.core.deep_fetch import IncludeTree, RelationshipViewKey, RenderToken
from parallax.core.document_codec import (
    MemberShape,
    OccurrenceCarrier,
    encode_occurrence,
    occurrence_shape,
)
from parallax.core.entity import UNLOADED, Entity
from parallax.core.entity._declaration import wire_names_of
from parallax.core.entity._entity import CHANGE_RECORD_SLOT, ChangeRecord
from parallax.core.entity._graph_construction import require_correspondence
from parallax.core.entity._instance_state import (
    ABSENT_DECLARED_VALUE,
    declared_values,
    is_published,
    named_state_value,
    plan_of,
)
from parallax.core.entity._instance_state import (
    relationship as relationship_state,
)
from parallax.core.entity._layout import CatalogedModel, EntityLayout
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    Metamodel,
    NestedValueObjectMetadata,
    ValueObjectMetadata,
)
from parallax.core.unit_work import ReadOrigin
from parallax.core.wire import encode_wire
from parallax.core.wire._codec import encode_managed_wire
from parallax.snapshot._inspection import SnapshotInspectionError, snapshot_state_of
from parallax.snapshot.materialize._classify import ClassifiedRoot, classify_roots
from parallax.snapshot.materialize._invalid import InvalidData
from parallax.snapshot.materialize._page import ABSENT
from parallax.snapshot.materialize._root import RootView
from parallax.snapshot.materialize._wire_memo import IndexMemo, WireMemo

__all__ = [
    "FAMILY_VARIANT_KEY",
    "EntityReader",
    "NodeReader",
    "RootViewReader",
    "WireEntity",
    "WireValue",
    "WireWalk",
    "opened_wire_entity",
    "projection_entity",
    "read_origin_of",
    "shared_wire_encoder",
    "wire_roots",
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

_VoContainer = ValueObjectMetadata | NestedValueObjectMetadata
type _Encoder = Callable[[NeutralType, ManagedValue], object]

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
    as an Entity. It is also the only node that can carry a Read Origin, and the
    slot is why: a nested Value Object mapping has no slot to put one in.

    The hint rides a slot rather than a mapping entry, so it is not a key, not
    iterated, not compared, not serialized, and not carried by ``dict(value)`` —
    a plain conversion of a Wire node is ordinary domain data with no keyed-source
    status, which is exactly what it is.
    """

    __slots__ = ("_source",)

    _source: ReadOrigin | None


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


def read_origin_of(entity: WireEntity) -> ReadOrigin | None:
    """The private Read Origin ``entity`` carries, or ``None`` for a mapping no
    Wire read published.

    The one reader of the slot. A hint is never authority of its own — it names
    the exact state its read observed and nothing about what may be written —
    so this answers a fact and the write side draws the conclusion.
    """
    return getattr(entity, "_source", None)


type _WireRoot = WireEntity | InvalidData[WireEntity]
"""One published Wire result position: the Entity node, or the record a root
whose stored state contradicted the model publishes in its place.

Private: every returned Entity mapping is a :class:`WireEntity`, root and
included node alike, and naming the published union would read as a second
public type for the root position where the contract has none."""


def wire_roots(
    root_view: RootView,
    model: Metamodel,
    includes: IncludeTree,
    *,
    ordinal_offset: int = 0,
    sources: Mapping[int, ReadOrigin] = MappingProxyType({}),
    encode: _Encoder = encode_managed_wire,
) -> tuple[WireEntity | InvalidData[WireEntity], ...]:
    """``root_view``'s roots as Wire values, in result order.

    Classification runs first and exactly once, so this materializer publishes
    the same verdicts the typed one does: a conforming root answers as itself, a
    hydratable one as its record carrying the unwound value, and a non-hydrating
    one as its record carrying nothing. ``ordinal_offset`` is where this Root
    View's roots start in the ordered result, including a later streamed Page.

    ``sources`` is the Read Origin the read retained per projection index, which
    each published Entity node carries privately — the same evidence the typed
    materializer attaches to the node of the same row, so the two representations
    license exactly the same writes.
    """
    classification = classify_roots(root_view, model, ordinal_offset=ordinal_offset)
    retained: Mapping[int, ReadOrigin] = (
        sources if classification.conforming else MappingProxyType({})
    )
    walk = WireWalk(RootViewReader(root_view, retained), includes, encode)
    published: list[_WireRoot] = []
    for verdict in classification.roots:
        if not isinstance(verdict, ClassifiedRoot):
            published.append(walk.position(verdict.node, includes.root))
            continue
        data = None if verdict.node is None else walk.position(verdict.node, includes.root)
        published.append(cast("InvalidData[WireEntity]", verdict.published(data)))
    return tuple(published)


class NodeReader[Node](Protocol):
    """How one representation answers what the Wire walk asks of a node.

    The walk is generic over the native reference a representation addresses a
    node by — an allocation index into a Root View — and asks a reader four
    things of one: the layout its state is read against, its positional member
    values, one requested relationship view's raw arm, and the Read Origin it
    carries. Everything about what those answers BECOME — declared-name keys,
    canonical leaves, the variant the layout fixed, occurrence rendering, finite
    descent, aliasing — belongs to the walk, so a reader exposes storage and
    renders nothing.

    ``member_values`` is consumed once, in layout order, and is never sliced or
    copied by the walk, so a Root View answers its Page-owned tuple by reference.
    ``relationship`` answers ``ABSENT`` for a view the node does not carry,
    ``None`` for loaded-null, a native reference for loaded-one, and a tuple of
    them for loaded-many: the reader's answer already travels in the shape the
    walk renders, so nothing is translated between them.
    """

    def layout(self, node: Node) -> EntityLayout: ...

    def member_values(self, node: Node) -> Iterable[object]: ...

    def relationship(self, node: Node, view: RelationshipViewKey) -> object: ...

    def origin(self, node: Node) -> ReadOrigin | None: ...

    def occurrence_carrier(self) -> OccurrenceCarrier: ...

    def admission_error(self, concrete: EntityIdentity) -> Exception: ...


class RootViewReader:
    """The :class:`NodeReader` over one Root View: a node is its allocation
    index, and every answer borrows the Root View's own indexed state.

    ``sources`` is the Read Origin the read retained per projection index,
    resolved through the Root View's canonical projection for each node; it is
    empty for a root that does not conform, so a hydrated invalid graph carries
    none.
    """

    __slots__ = ("_root", "_sources")

    def __init__(self, root: RootView, sources: Mapping[int, ReadOrigin]) -> None:
        self._root = root
        self._sources = sources

    def layout(self, node: int) -> EntityLayout:
        return self._root.layout(node)

    def member_values(self, node: int) -> tuple[object, ...]:
        return self._root.member_values(node)

    def relationship(self, node: int, view: RelationshipViewKey) -> object:
        # A Root View row is the union of the source rows its own concrete can
        # carry, so a node whose concrete a path-root guard excluded from the
        # level attaching this view holds NO SLOT for it, and answers absence.
        # The union's other unloaded state — a slot present and holding ABSENT,
        # left wherever a level could have reached the node but did not — cannot
        # arise at a view the walk names: reaching the node there meant following
        # the arm that view's own level wrote, and a level writes every parent it
        # gathers. So a missing slot is the union's width showing through, and a
        # present one is answered exactly as its level wrote it.
        slot = self._root.view_layout(node).index_of.get(view)
        return ABSENT if slot is None else self._root.view(node, slot)

    def origin(self, node: int) -> ReadOrigin | None:
        return self._root.projection_value(node, self._sources)

    def occurrence_carrier(self) -> OccurrenceCarrier:
        return _STORED

    def admission_error(  # pragma: no cover - execution admits every stored position
        self, concrete: EntityIdentity
    ) -> Exception:
        return ValueError(f"{concrete.canonical} is not admitted by the requested include position")


class EntityReader:
    """The native published-Entity adapter for the shared Wire walk."""

    __slots__ = ("_checked", "_model", "_operation")

    def __init__(self, model: CatalogedModel, *, operation: str = "Snapshot.wire") -> None:
        self._model = model
        self._operation = operation
        self._checked: set[tuple[type, EntityIdentity]] = set()

    def layout(self, node: object) -> EntityLayout:
        state = self._required(node)
        pair = (type(node), state.entity)
        try:
            layout = self._model.layouts.entity(state.entity)
            if pair not in self._checked:
                require_correspondence(
                    layout,
                    wire_names_of(type(node)),
                    plan_of(type(node)),
                )
                self._checked.add(pair)
        except Exception as error:
            raise SnapshotInspectionError(
                code="snapshot-wire-input-incompatible",
                message=(
                    f"{type(node).__name__} does not correspond to retained layout "
                    f"{state.entity.canonical}: {error}"
                ),
                operation=self._operation,
                entity=state.entity,
            ) from error
        return layout

    def member_values(self, node: object) -> Iterable[object]:
        self._required(node)
        return (
            ABSENT if value is ABSENT_DECLARED_VALUE else value
            for value in declared_values(cast("Any", node))
        )

    def relationship(self, node: object, view: RelationshipViewKey) -> object:
        state = self._required(node)
        if view.narrowed_view is not None:
            return state.views.get(view.narrowed_view, ABSENT)
        py_name = wire_names_of(type(node)).relationship_py.get(view.relationship.name)
        if py_name is None:  # pragma: no cover - correspondence checks every direction
            raise SnapshotInspectionError(
                code="snapshot-wire-input-incompatible",
                message=(
                    f"{type(node).__name__} declares no relationship position for "
                    f"{view.relationship}"
                ),
                operation=self._operation,
                entity=state.entity,
            )
        value = relationship_state(cast("Any", node), py_name)
        return ABSENT if value is UNLOADED else value

    def origin(self, node: object) -> ReadOrigin | None:
        return self._required(node).source

    def occurrence_carrier(self) -> OccurrenceCarrier:
        return _LIVE

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

    def _required(self, node: object):
        projection_entity(node, operation=self._operation)
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
            entity=None if state is None else state.entity,
        )
    published = is_published(node)
    state = snapshot_state_of(node)
    if state is None or not published:
        raise SnapshotInspectionError(
            code="snapshot-node-required",
            message="Wire projection requires a published Snapshot node",
            operation=operation,
            entity=None if state is None else state.entity,
        )
    return state.entity


class WireWalk[Node]:
    """One root-, result-, or page-scoped walk over a reader's nodes and memo.

    The memo keys the reader's native reference beside the subtree a node
    renders under, so two positions reaching one node under one subtree answer
    the identical frozen object — and therefore the identical claim — exactly
    as two positions reaching one Entity instance do in the typed lane; a value
    that refuses mutation through the instance is safely shared. The leaf
    subtree is one object shared by every position that renders members and no
    relationship, so a node reached under it is keyed by the reference alone.
    Direct publication owns one walk per Root View, eager Typed projection owns
    one for the complete result, and stream projection owns one per page. The
    owner releases that state when its scope ends.
    """

    __slots__ = ("_encode", "_includes", "_memo", "_reader", "_trusted")

    def __init__(
        self,
        reader: NodeReader[Node],
        includes: IncludeTree,
        encode: _Encoder = encode_managed_wire,
        *,
        memo: WireMemo[Node] | None = None,
    ) -> None:
        self._reader = reader
        self._includes = includes
        self._encode = encode
        self._trusted = encode is encode_managed_wire or isinstance(encode, _SharedWireEncoder)
        self._memo = cast("WireMemo[Node]", IndexMemo()) if memo is None else memo

    def node(self, node: Node, token: RenderToken) -> _WireEntityNode:
        cached = self._memo.get(node, token)
        if cached is not None:
            return cast("_WireEntityNode", cached)
        entity = self._build(node, token)
        object.__setattr__(entity, "_source", self._reader.origin(node))
        self._memo.put(node, token, entity)
        return entity

    def position(self, node: Node, position: int) -> _WireEntityNode:
        """Render ``node`` at one admitted requested position."""
        concrete = self._reader.layout(node).concrete
        token = self._includes.render_token((position,), concrete)
        if token is None:  # pragma: no cover - explicit projection checks admission first
            raise self._reader.admission_error(concrete)
        return self.node(node, token)

    def clear(self) -> None:
        self._memo.clear()

    def _build(self, node: Node, token: RenderToken) -> _WireEntityNode:
        reader = self._reader
        layout = reader.layout(node)
        values = iter(reader.member_values(node))
        rendered: dict[str, WireValue] = {}
        for attribute, value in zip(layout.attributes, values, strict=False):
            if value is not ABSENT:
                rendered[attribute.identity.name] = (
                    cast("WireValue", value)
                    if self._trusted and type(value) in (bool, int, str)
                    else _trusted_wire_scalar(attribute.type, value, self._encode)
                    if self._trusted
                    else _wire_scalar(attribute.type, value, self._encode)
                )
        if layout.family_variant is not None:
            rendered[FAMILY_VARIANT_KEY] = layout.family_variant
        for occurrence, value in zip(layout.occurrences, values, strict=True):
            if value is not ABSENT:
                rendered[occurrence.identity.path[-1]] = _occurrence(
                    value,
                    occurrence,
                    reader.occurrence_carrier(),
                    self._encode,
                    trusted=self._trusted,
                )
        for view, grouped in self._includes.child_groups(token).items():
            candidates = self._includes.admitted_children(grouped, layout.concrete)
            if not candidates:
                continue
            value = reader.relationship(node, view)
            if value is ABSENT:
                continue
            rendered[view.narrowed_view or view.relationship.name] = self._related(
                value, candidates
            )
        return _frozen_mapping(_WireEntityNode, rendered)

    def _related(self, value: object, candidates: tuple[int, ...]) -> WireValue:
        """One loaded view's arm resolved against the reader's own nodes.

        The arm travels in the value's SHAPE: a tuple is loaded-many,
        ``None`` is loaded-null, and a lone native reference is loaded-one.
        """
        if isinstance(value, tuple):
            sequence = list.__new__(_FrozenSequence)
            for element in cast("tuple[Node, ...]", value):
                list[Any].append(sequence, self._admitted_node(element, candidates))
            return sequence
        if value is None:
            return None
        return self._admitted_node(cast("Node", value), candidates)

    def _admitted_node(self, node: Node, candidates: tuple[int, ...]) -> _WireEntityNode:
        concrete = self._reader.layout(node).concrete
        token = self._includes.render_token(candidates, concrete)
        if token is None:  # pragma: no cover - fetched views hold admitted concretes
            raise self._reader.admission_error(concrete)
        return self.node(node, token)


def _put(rendered: dict[str, WireValue], key: str, value: WireValue) -> None:
    """Add one published field, refusing an impossible collision."""
    if key in rendered:  # pragma: no cover - Model Formation rejects this defensively
        raise ValueError(f"wire field key {key!r} has more than one contributor")
    rendered[key] = value


def _wire_scalar(
    neutral_type: NeutralType,
    value: object,
    encode: _Encoder = encode_managed_wire,
) -> WireValue:
    if value is None:
        return None
    if isinstance(value, TemporalBound):
        return INFINITY_LITERAL
    if type(value) in (bool, int, str) and (
        encode is encode_managed_wire or isinstance(encode, _SharedWireEncoder)
    ):
        return cast("WireValue", value)
    return cast("WireValue", encode(neutral_type, cast("ManagedValue", value)))


def _trusted_wire_scalar(neutral_type: NeutralType, value: object, encode: _Encoder) -> WireValue:
    if value is None:
        return None
    if isinstance(value, TemporalBound):
        return INFINITY_LITERAL
    return cast("WireValue", encode(neutral_type, cast("ManagedValue", value)))


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


def _authored_elements(value: object) -> Iterable[object]:
    return cast("Sequence[object]", value) if isinstance(value, list | tuple) else ()


def _stored_values(record: object, shape: MemberShape) -> Iterable[object]:
    del shape
    return cast("tuple[object, ...]", record)


_AUTHORED_ABSENT: Final = object()


def _authored_values(record: object, shape: MemberShape) -> Iterable[object]:
    document = cast("Mapping[str, object]", record)
    return (document.get(member.name, _AUTHORED_ABSENT) for member in shape.members)


def _live_values(record: object, shape: MemberShape) -> Iterable[object]:
    del shape
    return (
        ABSENT if value is ABSENT_DECLARED_VALUE else value
        for value in declared_values(cast("Any", record))
    )


_STORED: Final = OccurrenceCarrier(ABSENT, _stored_values, _tuple_elements)
_AUTHORED: Final = OccurrenceCarrier(_AUTHORED_ABSENT, _authored_values, _authored_elements)
_LIVE: Final = OccurrenceCarrier(ABSENT, _live_values, _tuple_elements)


@dataclass(frozen=True, slots=True)
class _OccurrenceLeafEncoder:
    encode: _Encoder
    trusted: bool

    def __call__(self, neutral_type: NeutralType, value: object) -> WireValue:
        return (
            cast("WireValue", value)
            if self.trusted and type(value) in (bool, int, str)
            else _trusted_wire_scalar(neutral_type, value, self.encode)
            if self.trusted
            else _wire_scalar(neutral_type, value, self.encode)
        )


def _occurrence_mapping(entries: Iterable[tuple[str, WireValue]]) -> WireValue:
    return _frozen_mapping(_FrozenMapping, entries)


def _occurrence_sequence(values: Iterable[WireValue]) -> WireValue:
    return _frozen_sequence(values)


def _occurrence(
    value: object,
    declared: _VoContainer,
    carrier: OccurrenceCarrier,
    encode: _Encoder = encode_managed_wire,
    *,
    trusted: bool = False,
) -> WireValue:
    """One occurrence entry as the Wire value its carrier holds."""
    return encode_occurrence(
        value,
        occurrence_shape(declared),
        declared.multiplicity,
        carrier,
        encode_leaf=_OccurrenceLeafEncoder(encode, trusted),
        build_object=_occurrence_mapping,
        build_array=_occurrence_sequence,
    )


def opened_wire_entity(
    model: CatalogedModel, entity: EntityIdentity, row: Mapping[str, object], hint: ReadOrigin
) -> WireEntity:
    """The frozen Wire node for a row a Wire insert has just OPENED.

    A Wire insert's caller holds nothing afterwards — the Typed peer leaves the
    caller holding the instance it passed — so the verb answers the row it
    buffered, in the one representation that can be handed straight back to a
    keyed verb. The node carries ``hint``, which is what makes it a keyed source
    at all; the values are the payload's own, rendered through the SAME
    canonical encoding a read publishes, so writing a member back is the
    restoration it would be off a read result.

    What it publishes is what this transaction STATED, not what a later read of
    the stored row will: the framework-owned members are stamped at flush and
    are absent here, and the walk is over the positions ``row`` names rather than
    the declared ones. That is exact because ``row`` is an opening row's canonical
    member set — a complete Create Payload by `m-unit-work`'s own full-document
    rule, carrying the empty collection at every ``many`` the payload omitted.

    ``model`` is the cataloged model the transaction writes under, so the
    member bindings and the family variant come off the one layout its catalog
    fixed for ``entity`` — the same layout a read of the row publishes against.
    """
    layout = model.layouts.entity(entity)
    rendered: dict[str, WireValue] = {}
    for name, value in row.items():
        binding = layout.member_selection.binding(name)
        if isinstance(binding, AttributeMetadata):
            _put(rendered, name, _wire_scalar(binding.type, value))
            continue
        if binding is not None:  # pragma: no branch - the payload names declared members only
            _put(
                rendered,
                name,
                _occurrence(value, binding, _AUTHORED, encode_wire),
            )
    if layout.family_variant is not None:
        _put(rendered, FAMILY_VARIANT_KEY, layout.family_variant)
    node = _frozen_mapping(_WireEntityNode, rendered)
    object.__setattr__(node, "_source", hint)
    return node
