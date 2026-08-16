"""The wire materializer: one merged graph into a finite tree of frozen values.

A PEER of :mod:`parallax.snapshot.handle._materializer`, not a wrapper of it.
Both consume the same :class:`~parallax.snapshot.materialize.GraphMerge` and the
same root classification; neither calls the other, and a typed read constructs
nothing defined here. What differs is only what a merged node becomes: a frozen
Entity instance there, and here the :class:`WireEntity` mapping a caller with no
compiled Entity Class can still read.

Two rules give the result its shape.

**Declared names, canonical values.** Every key is the model's own declared member
name — never a physical column — and every leaf is its canonical Wire Value
(`m-wire`), the same spelling the document codec stores. A Value Object occurrence
publishes the members its carrier HELD: the walk follows the declared member lists,
which is what fixes key order and decodes each position by its declared type, but a
member the carrier does not hold contributes no key. So a consumer reads presence
off the published node rather than assuming every declared name is a key, and the
node and the hydrated Entity value observe one document — a leaf or a nullable
``one`` the stored document omitted is absent from both, while one stored as JSON
null is ``None`` in both.

Two positions carry a member the document did not hold, and neither is a fill
(`m-snapshot-read`). A ``many`` always publishes: the codec gives it no absent
state at all (`m-document-codec`), so an omitted key, JSON null, and ``[]`` are one
stored zero value and the carrier holds the empty collection for all three. A
**non-nullable** ``one`` the document omits publishes null, because that omission
is the required-member-absent state whose collapse the hydration table admits as a
value, and its root is classified.

**The include tree bounds the walk, not the identity graph.** A merged node keeps
every view any level loaded onto it, so following a node's own views would revisit
an ancestor forever. The unwind instead descends an :class:`UnwindTree` — the
requested Include Paths, realized as the views to follow — which strictly shrinks
with depth, so a back-reference renders its target once, in full, and terminates.
That is what replaces a primary-key stub: the tree, not a cycle detector, is what
makes the value finite.

Aliasing is preserved rather than copied: the unwind memoizes on
``(node, subtree)``, so every position reaching one merged node under one subtree
answers the identical frozen object. The cache lives for one materialization pass
and dies with it, so its scope IS the materialization unit.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Self, SupportsIndex, cast

from parallax.core.base import INFINITY_LITERAL, TemporalBound
from parallax.core.entity._graph_input import ValueObjectRecord
from parallax.core.inheritance import family_variant_name
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.core.unit_work import SourceHint
from parallax.core.wire import encode_wire
from parallax.snapshot.materialize._classify import ClassifiedRoot, classify_roots
from parallax.snapshot.materialize._input import RelationshipViewKey
from parallax.snapshot.materialize._invalid import InvalidData
from parallax.snapshot.materialize._merge import GraphMerge, MergedNode

__all__ = [
    "EMPTY_UNWIND",
    "FAMILY_VARIANT_KEY",
    "UnwindTree",
    "WireEntity",
    "WireValue",
    "opened_wire_entity",
    "source_hint_of",
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
    as an Entity. It is also the only node that can carry a Source Hint, and the
    slot is why: a nested Value Object mapping has no slot to put one in.

    The hint rides a slot rather than a mapping entry, so it is not a key, not
    iterated, not compared, not serialized, and not carried by ``dict(value)`` —
    a plain conversion of a Wire node is ordinary domain data with no keyed-source
    status, which is exactly what it is.
    """

    __slots__ = ("_source",)

    _source: SourceHint | None


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


def source_hint_of(entity: WireEntity) -> SourceHint | None:
    """The private Source Hint ``entity`` carries, or ``None`` for a mapping no
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
    look. A node's children are keyed exactly as a merged node keys its views, so
    following the tree and reading the merge need no translation between them.
    """

    children: Mapping[RelationshipViewKey, UnwindTree]


EMPTY_UNWIND = UnwindTree(MappingProxyType({}))
"""The tree of a read that requested no Include Path: every node renders its own
members and no relationship at all."""


def wire_roots(
    merge: GraphMerge,
    model: Metamodel,
    includes: UnwindTree = EMPTY_UNWIND,
    *,
    ordinal_offset: int = 0,
    sources: Mapping[int, SourceHint] = MappingProxyType({}),
) -> tuple[WireEntity | InvalidData[WireEntity], ...]:
    """``merge``'s roots as Wire values, in result order.

    Classification runs first and exactly once, so this materializer publishes
    the same verdicts the typed one does: a conforming root answers as itself, a
    hydratable one as its record carrying the unwound value, and a non-hydrating
    one as its record carrying nothing. ``ordinal_offset`` is where this graph's
    roots start in the ordered result, nonzero only for a milestone-set read.

    ``sources`` is the Source Hint the read retained per allocation index, which
    each published Entity node carries privately — the same evidence the typed
    materializer attaches to the node of the same row, so the two representations
    license exactly the same writes.
    """
    classification = classify_roots(merge, model, ordinal_offset=ordinal_offset)
    unwind = _Unwind(merge, model, sources)
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
    one merged node under one subtree share the merged node in the typed lane
    too, and a value that refuses mutation through the instance is safely
    shared. It dies when the pass returns.
    """

    __slots__ = ("_cache", "_merge", "_model", "_sources")

    def __init__(
        self, merge: GraphMerge, model: Metamodel, sources: Mapping[int, SourceHint]
    ) -> None:
        self._merge = merge
        self._model = model
        self._sources = sources
        self._cache: dict[tuple[int, int], _WireEntityNode] = {}

    def node(self, index: int, subtree: UnwindTree) -> _WireEntityNode:
        key = (index, id(subtree))
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        entity = self._build(self._merge.node(index), subtree)
        # Two positions reaching one merged node under one subtree answer the
        # identical object and therefore the identical claim, exactly as two
        # positions reaching one Entity instance do in the typed lane.
        object.__setattr__(entity, "_source", self._sources.get(index))
        self._cache[key] = entity
        return entity

    def _build(self, merged: MergedNode, subtree: UnwindTree) -> _WireEntityNode:
        entity = merged.concrete_entity
        rendered: dict[str, WireValue] = {}
        declared_attributes = _declared_attributes(self._model, entity)
        for entry in merged.attributes:
            attribute = declared_attributes.get(entry.identity)
            if attribute is None:  # pragma: no cover - a projection names a declared member
                continue
            _put(rendered, entry.identity.name, _leaf(attribute, entry.value))
        variant = _family_variant(self._model, entity)
        if variant is not None:
            _put(rendered, FAMILY_VARIANT_KEY, variant)
        declared_occurrences = _declared_value_objects(self._model, entity)
        for entry in merged.value_objects:
            occurrence = declared_occurrences.get(entry.identity)
            if occurrence is None:  # pragma: no cover - conversion walks the same declaration
                continue
            _put(rendered, entry.identity.path[-1], _occurrence(entry.value, occurrence, _STORED))
        loaded = {entry.view: entry.value for entry in merged.views}
        for view, child in subtree.children.items():
            # A view the node never received is a level a path-root guard excluded
            # this parent from: its key is absent, which is what unloaded means.
            if view not in loaded:
                continue
            key = view.narrowed_view or view.relationship.name
            _put(rendered, key, self._related(loaded[view], child))
        return _frozen_mapping(_WireEntityNode, rendered)

    def _related(self, value: object, subtree: UnwindTree) -> WireValue:
        """One loaded view's arm resolved against the graph's own nodes.

        The arm travels in the value's SHAPE (`_merge`): a tuple is loaded-many,
        ``None`` is loaded-null, and a lone allocation index is loaded-one.
        """
        if isinstance(value, tuple):
            return _frozen_sequence(
                self.node(index, subtree) for index in cast("tuple[int, ...]", value)
            )
        if value is None:
            return None
        return self.node(cast("int", value), subtree)


def _put(rendered: dict[str, WireValue], key: str, value: WireValue) -> None:
    """Add one published field, refusing an impossible collision."""
    if key in rendered:  # pragma: no cover - Model Formation rejects this defensively
        raise ValueError(f"wire field key {key!r} has more than one contributor")
    rendered[key] = value


def _leaf(attribute: AttributeMetadata, value: object) -> WireValue:
    """One Attribute value as its canonical Wire Value.

    Null and the open temporal bound are the two positions no value space covers:
    a null member publishes JSON null, and a temporal end's open bound publishes
    `m-core`'s own canonical ``infinity`` literal.
    """
    return _wire_scalar(attribute.type, value)


def _wire_scalar(neutral_type: object, value: object) -> WireValue:
    if value is None:
        return None
    if isinstance(value, TemporalBound):
        return INFINITY_LITERAL
    return cast("WireValue", encode_wire(cast("Any", neutral_type), value))


@dataclass(frozen=True, slots=True)
class _Carrier:
    """How one kind of occurrence carrier answers the two questions publication
    asks of it: what a ``many`` value's elements are, and which members one record
    holds, under their declared names.

    A stored :class:`ValueObjectRecord` and an authored write document hold the
    same value differently — identity-keyed entries against a plain mapping — and
    nothing else about publication differs, so the walk is shared and only the
    lookup varies. That is what keeps the node a Wire insert answers and the node
    a read publishes describing one row the same way.
    """

    elements: Callable[[object], Sequence[object]]
    entries: Callable[[object], Mapping[str, object]]


def _stored_elements(value: object) -> Sequence[object]:
    return cast("Sequence[object]", value) if isinstance(value, tuple) else ()


def _stored_entries(record: object) -> Mapping[str, object]:
    """One stored record's members by declared name — empty for anything that is
    not a record, which holds no member of any name."""
    return (
        {
            **{entry.identity.name: entry.value for entry in record.attributes},
            **{entry.identity.path[-1]: entry.value for entry in record.value_objects},
        }
        if isinstance(record, ValueObjectRecord)
        else {}
    )


def _authored_elements(value: object) -> Sequence[object]:
    return cast("Sequence[object]", value) if isinstance(value, list | tuple) else ()


def _authored_entries(document: object) -> Mapping[str, object]:
    return cast("Mapping[str, object]", document) if isinstance(document, Mapping) else {}


_STORED: Final = _Carrier(elements=_stored_elements, entries=_stored_entries)
_AUTHORED: Final = _Carrier(elements=_authored_elements, entries=_authored_entries)


def _occurrence(value: object, declared: _VoContainer, carrier: _Carrier) -> WireValue:
    """One occurrence entry as the Wire value its carrier holds."""
    if declared.multiplicity is Multiplicity.MANY:
        return _frozen_sequence(
            _held_members(record, declared, carrier) for record in carrier.elements(value)
        )
    return None if value is None else _held_members(value, declared, carrier)


def _held_members(record: object, declared: _VoContainer, carrier: _Carrier) -> WireValue:
    """One occurrence record as the members its carrier HELD, in declared order.

    The declared member lists supply the order and the per-position decoding, and
    the carrier decides which of those positions become keys: a member it does not
    hold is absent from the published mapping rather than filled with a value the
    document never carried. Absence is therefore something a consumer reads, and
    re-serializing an occurrence published from a CONFORMING document stores what
    was stored, apart from the two carried positions below. Stored state the
    hydration rules collapse — a wrong-kind ``one`` or ``many``, an undecodable
    leaf — reserializes as its collapse instead, with its root classified.

    Presence is the carrier's whole answer, so nothing here re-derives it — which
    is also why the two positions `m-snapshot-read` carries regardless of the
    document need no branch here. A stored record already carries the codec's
    verdicts: a leaf or a nullable ``one`` the document omitted contributes no
    entry, one stored as JSON null contributes ``None``, a ``many`` contributes its
    ordered elements whichever of the three zero spellings the document used, and a
    non-nullable ``one`` the document omitted contributes the null its collapse
    answers with.
    """
    held = carrier.entries(record)
    published: dict[str, WireValue] = {}
    for leaf in declared.attributes:
        name = leaf.identity.name
        if name in held:
            published[name] = _wire_scalar(leaf.type, held[name])
    for occurrence in declared.value_objects:
        name = occurrence.identity.path[-1]
        if name in held:
            published[name] = _occurrence(held[name], occurrence, carrier)
    return _frozen_mapping(_FrozenMapping, published)


def opened_wire_entity(
    model: Metamodel, entity: EntityIdentity, row: Mapping[str, object], hint: SourceHint
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
    declared_attributes = {
        attribute.identity.name: attribute
        for attribute in _declared_attributes(model, entity).values()
    }
    declared_occurrences = {
        occurrence.identity.path[-1]: occurrence
        for occurrence in _declared_value_objects(model, entity).values()
    }
    rendered: dict[str, WireValue] = {}
    for name, value in row.items():
        attribute = declared_attributes.get(name)
        if attribute is not None:
            _put(rendered, name, _wire_scalar(attribute.type, value))
            continue
        occurrence = declared_occurrences.get(name)
        if occurrence is not None:  # pragma: no branch - the payload names declared members only
            _put(rendered, name, _occurrence(value, occurrence, _AUTHORED))
    variant = _family_variant(model, entity)
    if variant is not None:
        _put(rendered, FAMILY_VARIANT_KEY, variant)
    node = _frozen_mapping(_WireEntityNode, rendered)
    object.__setattr__(node, "_source", hint)
    return node


def _declared_attributes(
    model: Metamodel, entity: EntityIdentity
) -> Mapping[AttributeIdentity, AttributeMetadata]:
    position = inheritance_view(model).entity(entity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return {}
    return {attribute.identity: attribute for attribute in position.applicable_attributes}


def _declared_value_objects(
    model: Metamodel, entity: EntityIdentity
) -> Mapping[ValueObjectIdentity, ValueObjectMetadata]:
    position = inheritance_view(model).entity(entity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return {}
    return {occurrence.identity: occurrence for occurrence in position.applicable_value_objects}


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
        target[view] = UnwindTree(MappingProxyType(children[index]))
    return UnwindTree(MappingProxyType(root))
