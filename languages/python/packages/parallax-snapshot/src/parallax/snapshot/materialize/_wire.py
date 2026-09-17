"""The wire materializer: one Root View into a finite tree of frozen values.

A peer of :mod:`parallax.snapshot.materialize._typed`, not a wrapper of it.
Both consume the same :class:`~parallax.snapshot.materialize.RootView` and the
same root classification; neither calls the other, and a typed read constructs
nothing defined here. What differs is only what a Root View node becomes: a frozen
Entity instance there, and here the :class:`WireEntity` mapping a caller with no
compiled Entity Class can still read.

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
an ancestor forever. The unwind instead descends an :class:`UnwindTree` — the
requested Include Paths, realized as the views to follow — which strictly shrinks
with depth, so a back-reference renders its target once, in full, and terminates.
That is what replaces a primary-key stub: the tree, not a cycle detector, is what
makes the value finite.

Aliasing is preserved rather than copied: the unwind memoizes on
``(node, subtree)``, so every position reaching one Root View node under one subtree
answers the identical frozen object. The cache lives for one materialization pass
and dies with it, so its scope IS the materialization unit.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Self, SupportsIndex, cast

from parallax.core.base import INFINITY_LITERAL, ManagedValue, NeutralType, TemporalBound
from parallax.core.inheritance import family_variant_name
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    ValueObjectMetadata,
)
from parallax.core.unit_work import ReadOrigin
from parallax.core.wire import encode_wire
from parallax.core.wire._codec import encode_managed_wire
from parallax.snapshot.materialize._classify import ClassifiedRoot, classify_roots
from parallax.snapshot.materialize._invalid import InvalidData
from parallax.snapshot.materialize._page import ABSENT, RelationshipViewKey
from parallax.snapshot.materialize._root import RootView

__all__ = [
    "EMPTY_UNWIND",
    "FAMILY_VARIANT_KEY",
    "UnwindTree",
    "WireEntity",
    "WireValue",
    "opened_wire_entity",
    "read_origin_of",
    "shared_wire_encoder",
    "unwind_tree",
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


def _frozen_mapping[T: _FrozenMapping](cls: type[T], entries: Mapping[str, WireValue]) -> T:
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


@dataclass(frozen=True, slots=True, eq=False)
class UnwindTree:
    """The requested Include Paths, as the relationship views an unwind follows.

    Identity-compared on purpose: it is the second half of the unwind's memo key,
    and two positions in one tree are two positions however alike their subtrees
    look. A node's children are keyed exactly as a Root View node keys its views, so
    following the tree and reading the Root View need no translation between them.
    """

    children: Mapping[RelationshipViewKey, UnwindTree]


EMPTY_UNWIND = UnwindTree(MappingProxyType({}))
"""The tree of a read that requested no Include Path: every node renders its own
members and no relationship at all."""


def wire_roots(
    root_view: RootView,
    model: Metamodel,
    includes: UnwindTree = EMPTY_UNWIND,
    *,
    ordinal_offset: int = 0,
    sources: Mapping[int, ReadOrigin] = MappingProxyType({}),
    encode: _Encoder = encode_managed_wire,
    variants: dict[EntityIdentity, str | None] | None = None,
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
    unwind = _Unwind(root_view, model, retained, encode, variants)
    published: list[_WireRoot] = []
    for verdict in classification.roots:
        if not isinstance(verdict, ClassifiedRoot):
            published.append(unwind.node(verdict.node, includes))
            continue
        data = None if verdict.node is None else unwind.node(verdict.node, includes)
        published.append(cast("InvalidData[WireEntity]", verdict.published(data)))
    return tuple(published)


class _Unwind:
    """One materialization pass's walk, and the memo it shares across roots.

    The memo is per pass rather than per root deliberately: two roots reaching
    one Root View node under one subtree share the same node in the typed lane
    too, and a value that refuses mutation through the instance is safely
    shared. It dies when the pass returns.
    """

    __slots__ = (
        "_cache",
        "_encode",
        "_leaf_cache",
        "_model",
        "_root",
        "_sources",
        "_trusted",
        "_variants",
    )

    def __init__(
        self,
        root: RootView,
        model: Metamodel,
        sources: Mapping[int, ReadOrigin],
        encode: _Encoder,
        variants: dict[EntityIdentity, str | None] | None,
    ) -> None:
        self._root = root
        self._model = model
        self._sources = sources
        self._encode = encode
        self._trusted = encode is encode_managed_wire or isinstance(encode, _SharedWireEncoder)
        self._cache: dict[tuple[int, int], _WireEntityNode] = {}
        self._leaf_cache: dict[int, _WireEntityNode] = {}
        self._variants = {} if variants is None else variants

    def node(self, index: int, subtree: UnwindTree) -> _WireEntityNode:
        leaf = subtree is EMPTY_UNWIND
        key: int | tuple[int, int] = index if leaf else (index, id(subtree))
        cache: dict[Any, _WireEntityNode] = self._leaf_cache if leaf else self._cache
        cached = cache.get(key)
        if cached is not None:
            return cached
        entity = self._build(index, subtree)
        # Two positions reaching one Root View node under one subtree answer the
        # identical object and therefore the identical claim, exactly as two
        # positions reaching one Entity instance do in the typed lane.
        object.__setattr__(entity, "_source", self._root.projection_value(index, self._sources))
        cache[key] = entity
        return entity

    def _build(self, node: int, subtree: UnwindTree) -> _WireEntityNode:
        layout = self._root.layout(node)
        values = self._root.member_values(node)
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
        variant = self._variants.get(layout.concrete, ABSENT)
        if variant is ABSENT:
            variant = _family_variant(self._model, layout.concrete)
            self._variants[layout.concrete] = variant
        if variant is not None:
            rendered[FAMILY_VARIANT_KEY] = cast("str", variant)
        for occurrence, value in zip(
            layout.occurrences, values[layout.attribute_count :], strict=True
        ):
            if value is not ABSENT:
                rendered[occurrence.identity.path[-1]] = _occurrence(
                    value, occurrence, _STORED, self._encode, trusted=self._trusted
                )
        view_layout = self._root.view_layout(node)
        for view, child in subtree.children.items():
            # A Root View row is the union of the source rows its own concrete can
            # carry, so a node whose concrete a path-root guard excluded from the
            # level attaching this view holds NO SLOT for it, and renders none.
            # The union's other unloaded state — a slot present and holding
            # ABSENT, left wherever a level could have reached the node but did
            # not — cannot arise at a view this walk names: reaching the node here
            # meant following the arm that view's own level wrote, and a level
            # writes every parent it gathers. So the skip below is the union's
            # width showing through, and the one under it is unreachable.
            slot = view_layout.index_of.get(view)
            if slot is None:
                continue
            value = self._root.view(node, slot)
            if value is ABSENT:  # pragma: no cover - see above: a slot this walk names is written
                continue
            key = view.narrowed_view or view.relationship.name
            rendered[key] = self._related(value, child)
        return _frozen_mapping(_WireEntityNode, rendered)

    def _related(self, value: object, subtree: UnwindTree) -> WireValue:
        """One loaded view's arm resolved against the Root View's own nodes.

        The arm travels in the value's SHAPE: a tuple is loaded-many,
        ``None`` is loaded-null, and a lone allocation index is loaded-one.
        """
        if isinstance(value, tuple):
            sequence = list.__new__(_FrozenSequence)
            for index in cast("tuple[int, ...]", value):
                list[Any].append(sequence, self.node(index, subtree))
            return sequence
        if value is None:
            return None
        return self.node(cast("int", value), subtree)


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


@dataclass(frozen=True, slots=True)
class _Carrier:
    """How one kind of occurrence carrier answers the two questions publication
    asks of it: what a ``many`` value's elements are, and which members one record
    holds, under their declared names.

    A stored member row and an authored write document hold the same value
    differently — a positional row against a plain mapping — and nothing else
    about publication differs, so the walk is shared and only the lookup varies.
    That is what keeps the node a Wire insert answers and the node a read
    publishes describing one row the same way.
    """

    elements: Callable[[object], Sequence[object]]
    entries: Callable[[object, _VoContainer], Mapping[str, object]]


def _stored_elements(value: object) -> Sequence[object]:
    return cast("Sequence[object]", value) if isinstance(value, tuple) else ()


def _stored_entries(record: object, declared: _VoContainer) -> Mapping[str, object]:
    """One stored member row's members by declared name.

    The row is positional against ``declared``'s own leaves and then its nested
    occurrences, so a name is read off the declaration at the position it sits
    at. An absent position contributes no name, which is what makes a member the
    stored document did not carry absent from the published mapping too.
    """
    if not isinstance(record, tuple):  # pragma: no cover - a One slot is a row or null
        return {}
    row = cast("tuple[object, ...]", record)
    held: dict[str, object] = {}
    for position, leaf in enumerate(declared.attributes):
        if row[position] is not ABSENT:
            held[leaf.identity.name] = row[position]
    for position, nested in enumerate(declared.value_objects, start=len(declared.attributes)):
        if row[position] is not ABSENT:
            held[nested.identity.path[-1]] = row[position]
    return held


def _authored_elements(value: object) -> Sequence[object]:
    return cast("Sequence[object]", value) if isinstance(value, list | tuple) else ()


def _authored_entries(document: object, declared: _VoContainer) -> Mapping[str, object]:
    del declared
    return cast("Mapping[str, object]", document) if isinstance(document, Mapping) else {}


_STORED: Final = _Carrier(elements=_stored_elements, entries=_stored_entries)
_AUTHORED: Final = _Carrier(elements=_authored_elements, entries=_authored_entries)


def _occurrence(
    value: object,
    declared: _VoContainer,
    carrier: _Carrier,
    encode: _Encoder = encode_managed_wire,
    *,
    trusted: bool = False,
) -> WireValue:
    """One occurrence entry as the Wire value its carrier holds."""
    if declared.multiplicity is Multiplicity.MANY:
        return _frozen_sequence(
            _held_members(record, declared, carrier, encode, trusted)
            for record in carrier.elements(value)
        )
    return None if value is None else _held_members(value, declared, carrier, encode, trusted)


def _held_members(
    record: object,
    declared: _VoContainer,
    carrier: _Carrier,
    encode: _Encoder,
    trusted: bool,
) -> WireValue:
    """One occurrence record as the members its carrier HOLDS, in declared order.

    The declared member lists supply the order and the per-position decoding, and
    the carrier decides which of those positions become keys: a member it does not
    hold is absent from the published mapping rather than filled with a value the
    document never carried. Absence is therefore something a consumer reads.

    Presence is the carrier's whole answer, so nothing here re-derives it and no
    position needs a branch. A read's carrier is the record the read reduction
    already built, so it states which members the value carries — including each
    position where that differs from what the stored document held, which
    `m-snapshot-read` *What a materialized value carries* fixes and this walk only
    renders. An insert's carrier is its own opening row, complete by the rule
    :func:`opened_wire_entity` states.
    """
    if carrier is _STORED and isinstance(record, tuple):
        row = cast("tuple[object, ...]", record)
        published: dict[str, WireValue] = {}
        for leaf, value in zip(declared.attributes, row, strict=False):
            if value is not ABSENT:
                published[leaf.identity.name] = (
                    cast("WireValue", value)
                    if trusted and type(value) in (bool, int, str)
                    else _trusted_wire_scalar(leaf.type, value, encode)
                    if trusted
                    else _wire_scalar(leaf.type, value, encode)
                )
        for occurrence, value in zip(
            declared.value_objects, row[len(declared.attributes) :], strict=True
        ):
            if value is not ABSENT:
                published[occurrence.identity.path[-1]] = _occurrence(
                    value, occurrence, carrier, encode, trusted=trusted
                )
        return _frozen_mapping(_FrozenMapping, published)
    held = carrier.entries(record, declared)
    published: dict[str, WireValue] = {}
    for leaf in declared.attributes:
        name = leaf.identity.name
        if name in held:
            published[name] = _wire_scalar(leaf.type, held[name], encode)
    for occurrence in declared.value_objects:
        name = occurrence.identity.path[-1]
        if name in held:
            published[name] = _occurrence(held[name], occurrence, carrier, encode, trusted=trusted)
    return _frozen_mapping(_FrozenMapping, published)


def opened_wire_entity(
    model: Metamodel, entity: EntityIdentity, row: Mapping[str, object], hint: ReadOrigin
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
    """
    position = inheritance_view(model).entity(entity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.canonical}: no Inheritance Facet view")
    rendered: dict[str, WireValue] = {}
    for name, value in row.items():
        binding = position.member_selection.binding(name)
        if isinstance(binding, AttributeMetadata):
            _put(rendered, name, _wire_scalar(binding.type, value))
            continue
        if binding is not None:  # pragma: no branch - the payload names declared members only
            _put(
                rendered,
                name,
                _occurrence(value, binding, _AUTHORED, encode_wire),
            )
    variant = _family_variant(model, entity)
    if variant is not None:
        _put(rendered, FAMILY_VARIANT_KEY, variant)
    node = _frozen_mapping(_WireEntityNode, rendered)
    object.__setattr__(node, "_source", hint)
    return node


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


def unwind_tree(
    levels: Sequence[tuple[RelationshipViewKey, int | None]],
) -> UnwindTree:
    """The include tree for ``levels``, each a view key plus its parent's index.

    ``None`` names the root as a level's parent. A level's parent is always an
    EARLIER level (`m-deep-fetch` plans in trie order), so building from the last
    level backwards fills each node's children before that node is frozen.
    """
    children: list[dict[RelationshipViewKey, UnwindTree]] = [{} for _ in levels]
    root: dict[RelationshipViewKey, UnwindTree] = {}
    for index in reversed(range(len(levels))):
        view, parent = levels[index]
        target = root if parent is None else children[parent]
        target[view] = (
            UnwindTree(MappingProxyType(children[index])) if children[index] else EMPTY_UNWIND
        )
    return UnwindTree(MappingProxyType(root))
