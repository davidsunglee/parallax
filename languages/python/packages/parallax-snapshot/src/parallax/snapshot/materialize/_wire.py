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
(`m-wire`), the same spelling the document codec stores. Value Object occurrences
are **declared-member filled**: the projection walks the declared member lists
rather than the stored carrier's keys, writing ``None`` for an absent leaf or
``one`` and ``()`` for an absent ``many``, because a consumer renders what it is
handed and owns no projection rule of its own.

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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Self, SupportsIndex, cast

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
    "WireRoot",
    "WireValue",
    "unwind_tree",
    "wire_roots",
]

type WireValue = bool | int | float | str | list[WireValue] | dict[str, WireValue] | None
"""One position in a Wire result: a canonical Wire Value, a nested Value Object
mapping, an included Entity node, or an ordered collection of either.

Structural rather than nominal, deliberately: a runtime Wire value is a frozen
built-in subclass, so it satisfies this alias while remaining directly
JSON-serializable and structurally equal to the plain value it mirrors. Deep
immutability is a runtime guarantee, not a static one — adding public frozen
list and mapping types solely to spell it would make every ordinary mapping
statically unusable as Parallax input."""

_VoContainer = ValueObjectMetadata | NestedValueObjectMetadata

FAMILY_VARIANT_KEY = "familyVariant"
"""The key an inheritance participant's stable variant spelling is published
under. It names no declared member, which is why it is fixed here rather than
resolved from the model."""

_FROZEN = "a Wire read result is immutable"


class WireEntity(Mapping[str, "WireValue"]):
    """A frozen Entity node returned by a Wire read.

    Names every returned Entity mapping — a result root and an included node
    alike — so a caller and a static checker can both say "this came from a
    Parallax Wire read" without a second type for the root position. It is
    read-only and non-constructible: the runtime value is a private frozen
    ``dict`` subclass, so ordinary indexing, iteration, ``get``, ``items``, and
    the rest of the mapping protocol work while ``isinstance(value, dict)``
    stays true and mutation raises :class:`TypeError`.

    Nominal identity states provenance, never authority. It cannot prove which
    concurrency evidence a write may use, so a keyed verb still resolves that
    dynamically; and it is deliberately absent from insert data, changes,
    predicates, and Object Query input, which continue to accept ordinary
    structural mappings.
    """

    __slots__ = ()


class _FrozenMapping(dict[str, Any]):
    """A ``dict`` that refuses every mutation.

    Subclassing ``dict`` rather than wrapping one is what keeps a Wire value
    directly JSON-serializable and structurally equal to the plain mapping it
    mirrors: a serializer's ``isinstance(value, dict)`` test still passes, while
    ``type(value) is dict`` is false for a caller that means to ask whether this
    value came from Parallax. Inherited equality and the inherited ``__hash__``
    of ``None`` are both correct as they stand, so neither is restated.

    Copying answers the same object. The value is immutable, so a copy could
    differ from it in identity alone — and identity is exactly what a later
    phase's private source hint rides on, so preserving it costs nothing and
    keeps a copied source usable.
    """

    __slots__ = ()

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
    """A ``list`` that refuses every mutation, for the same reasons as
    :class:`_FrozenMapping`: an ordered Wire collection stays JSON-serializable,
    structurally equal to the plain list it mirrors, and unhashable."""

    __slots__ = ()

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

    Separate from :class:`_FrozenMapping` because only an ENTITY node may later
    carry a private source hint: the slot lives on this class, so a nested Value
    Object mapping structurally cannot hold one and no mapping entry ever exposes
    it.
    """

    __slots__ = ()


type WireRoot = WireEntity | InvalidData[WireEntity]
"""One published Wire result position: the Entity node, or the record a root
whose stored state contradicted the model publishes in its place."""


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
) -> tuple[WireRoot, ...]:
    """``merge``'s roots as Wire values, in result order.

    Classification runs first and exactly once, so this materializer publishes
    the same verdicts the typed one does: a conforming root answers as itself, a
    hydratable one as its record carrying the unwound value, and a non-hydrating
    one as its record carrying nothing. ``ordinal_offset`` is where this graph's
    roots start in the ordered result, nonzero only for a milestone-set read.
    """
    classification = classify_roots(merge, model, ordinal_offset=ordinal_offset)
    unwind = _Unwind(merge, model)
    published: list[WireRoot] = []
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
    too, and an immutable value is safely shared. It dies when the pass returns.
    """

    __slots__ = ("_cache", "_merge", "_model")

    def __init__(self, merge: GraphMerge, model: Metamodel) -> None:
        self._merge = merge
        self._model = model
        self._cache: dict[tuple[int, int], _WireEntityNode] = {}

    def node(self, index: int, subtree: UnwindTree) -> _WireEntityNode:
        key = (index, id(subtree))
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        entity = self._build(self._merge.node(index), subtree)
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
            _put(rendered, entry.identity.path[-1], _occurrence(entry.value, occurrence))
        loaded = {entry.view: entry.value for entry in merged.views}
        for view, child in subtree.children.items():
            # A view the node never received is a level a path-root guard excluded
            # this parent from: its key is absent, which is what unloaded means.
            if view not in loaded:
                continue
            key = view.narrowed_view or view.relationship.name
            _put(rendered, key, self._related(loaded[view], child))
        return _WireEntityNode(rendered)

    def _related(self, value: object, subtree: UnwindTree) -> WireValue:
        """One loaded view's arm resolved against the graph's own nodes.

        The arm travels in the value's SHAPE (`_merge`): a tuple is loaded-many,
        ``None`` is loaded-null, and a lone allocation index is loaded-one.
        """
        if isinstance(value, tuple):
            return _FrozenSequence(
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


def _occurrence(
    value: ValueObjectRecord | tuple[ValueObjectRecord, ...] | None, declared: _VoContainer
) -> WireValue:
    """One occurrence entry as its declared-member-filled Wire value."""
    if declared.multiplicity is Multiplicity.MANY:
        records = value if isinstance(value, tuple) else ()
        return _FrozenSequence(_members(record, declared) for record in records)
    return None if value is None else _members(value, declared)


def _members(record: ValueObjectRecord | object, declared: _VoContainer) -> WireValue:
    """One occurrence record as every DECLARED member, absence filled.

    The walk is over the declared member lists rather than the record's own
    entries, which is the whole difference between the getter surface and the
    carrier: a leaf the stored document omitted reads ``None`` here, an absent
    ``one`` occurrence reads ``None``, and an absent ``many`` reads ``[]`` —
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
    filled: dict[str, WireValue] = {}
    for leaf in declared.attributes:
        filled[leaf.identity.name] = _wire_scalar(leaf.type, leaves.get(leaf.identity))
    for occurrence in declared.value_objects:
        filled[occurrence.identity.path[-1]] = _occurrence(
            nested.get(occurrence.identity), occurrence
        )
    return _FrozenMapping(filled)


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
