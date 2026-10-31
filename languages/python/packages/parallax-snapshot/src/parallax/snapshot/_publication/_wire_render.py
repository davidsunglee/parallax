from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Final, cast

from parallax.core import temporal_read
from parallax.core.base import INFINITY_LITERAL, ManagedValue, NeutralType, TemporalBound
from parallax.core.deep_fetch import IncludeTree, PositionId, RelationshipViewKey, RenderToken
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.read_delivery._page import ABSENT, InvalidData, VersionAttributes
from parallax.core.wire._codec import encode_managed_wire
from parallax.core.wire._facts import (
    ENCODE,
    OCCURRENCE,
    PASS,
    PASS_MANY,
    WireEntityFacts,
    WireModelFacts,
    WireOccurrenceFacts,
)
from parallax.snapshot._inspection import RootConformance
from parallax.snapshot._publication._classify import ConformingRoot, classify_root
from parallax.snapshot._publication._root import RootView
from parallax.snapshot._publication._wire import (
    FAMILY_VARIANT_KEY,
    NodeReader,
    RootViewReader,
    WireEntity,
    WireValue,
    _FrozenMapping,  # pyright: ignore[reportPrivateUsage] - the carriers a renderer fills
    _FrozenSequence,  # pyright: ignore[reportPrivateUsage] - the carriers a renderer fills
    _WireEntityNode,  # pyright: ignore[reportPrivateUsage] - the carriers a renderer fills
)
from parallax.snapshot._publication._wire_memo import NodeIndexMemo, WireMemo

__all__ = [
    "WireEntityPlan",
    "WireRelationshipPlan",
    "WireRenderer",
    "WireRootPublisher",
    "entity_plan",
    "requested_plan",
]

type _Encoder = Callable[[NeutralType, ManagedValue], object]
type _RecordValues = Callable[[object], Iterable[object]]

_new_dict: Final = cast("Callable[[type[_FrozenMapping]], _FrozenMapping]", dict.__new__)
_fill_dict: Final = cast(
    "Callable[[dict[str, Any], dict[str, WireValue]], None]", dict[str, Any].update
)
_new_list: Final = cast("Callable[[type[_FrozenSequence]], _FrozenSequence]", list.__new__)
_extend: Final = cast("Callable[[list[Any], Iterable[object]], None]", list[Any].extend)
_set_provenance: Final = cast("Callable[[object, str, object], None]", object.__setattr__)


class WireEntityPlan:
    """How a node of one concrete Entity renders at one render token: the
    model's facts for its members and the included relationships that token
    renders beneath it.

    Kept for the life of the compiled read's include tree, so every reader of
    that read — each direct Wire root, each stream Page, each Typed projection —
    renders through one plan per token and concrete.
    """

    __slots__ = ("facts", "relationships", "token")

    def __init__(
        self,
        token: RenderToken,
        facts: WireEntityFacts,
        relationships: tuple[WireRelationshipPlan, ...],
    ) -> None:
        self.token = token
        self.facts = facts
        self.relationships = relationships


class WireRelationshipPlan:
    """One included relationship view of a :class:`WireEntityPlan`: the field it
    renders under, the include positions it admits, and the plan of each
    concrete Entity it has reached, resolved on that Entity's first node.

    Target plans are resolved lazily, so a back-reference or a recursive include
    that returns to an earlier token and concrete closes into the plan that
    already exists rather than descending again.
    """

    __slots__ = ("_includes", "_model", "candidates", "key", "targets", "view")

    def __init__(
        self,
        key: str,
        view: RelationshipViewKey,
        candidates: tuple[PositionId, ...],
        includes: IncludeTree,
        model: WireModelFacts,
    ) -> None:
        self.key = key
        self.view = view
        self.candidates = candidates
        self.targets: dict[EntityIdentity, WireEntityPlan] = {}
        self._includes = includes
        self._model = model

    def target(self, concrete: EntityIdentity) -> WireEntityPlan | None:
        """The plan a related node of ``concrete`` renders by, or ``None`` where
        no candidate position admits it."""
        held = self.targets.get(concrete)
        if held is not None:
            return held
        token = self._includes.render_token(self.candidates, concrete)
        if token is None:
            return None
        return self.targets.setdefault(
            concrete, entity_plan(self._includes, self._model, token, concrete)
        )


def entity_plan(
    includes: IncludeTree, model: WireModelFacts, token: RenderToken, concrete: EntityIdentity
) -> WireEntityPlan:
    """The one plan ``includes`` holds for a ``concrete`` node rendered at
    ``token`` under ``model``'s facts."""
    return includes.prepared(
        (model, token, concrete), lambda: _plan(includes, model, token, concrete)
    )


_AT: Final = object()
"""Marks a requested position's own plan in the include tree's memo, apart
from the plans keyed by render token."""


def requested_plan(
    includes: IncludeTree, model: WireModelFacts, position: PositionId, concrete: EntityIdentity
) -> WireEntityPlan | None:
    """The plan a ``concrete`` node renders by at requested ``position``, or
    ``None`` where the position does not admit it."""
    return includes.prepared(
        (_AT, model, position, concrete), lambda: _requested(includes, model, position, concrete)
    )


def _requested(
    includes: IncludeTree, model: WireModelFacts, position: PositionId, concrete: EntityIdentity
) -> WireEntityPlan | None:
    token = includes.render_token((position,), concrete)
    return None if token is None else entity_plan(includes, model, token, concrete)


def _plan(
    includes: IncludeTree, model: WireModelFacts, token: RenderToken, concrete: EntityIdentity
) -> WireEntityPlan:
    relationships: list[WireRelationshipPlan] = []
    for view, grouped in includes.child_groups(token).items():
        candidates = includes.admitted_children(grouped, concrete)
        if candidates:
            relationships.append(
                WireRelationshipPlan(
                    view.narrowed_view or view.relationship.name,
                    view,
                    candidates,
                    includes,
                    model,
                )
            )
    return WireEntityPlan(token, model.entity(concrete), tuple(relationships))


class WireRenderer[Node]:
    """One root-, result-, or page-scoped renderer over a reader's nodes and memo.

    Each node renders in one pass over its prepared plan: its Attributes by
    their prepared encodings, its family variant, its Value Object occurrences
    by their prepared facts, then each included relationship. Nothing about a
    node's shape is resolved while it renders.

    The memo keys the reader's native reference beside the token a node renders
    at, so two positions reaching one node under one token answer the identical
    frozen object — exactly as two positions reaching one Entity instance do in
    the Typed lane; a value that refuses mutation through the instance is safely
    shared. Direct publication owns one renderer per publication pass and
    clears it at each root, eager Typed projection owns one for the complete
    result, and stream projection owns one per page. The owner releases that
    state when its scope ends.
    """

    __slots__ = ("_encode", "_includes", "_memo", "_model", "_reader", "_record_values")

    def __init__(
        self,
        reader: NodeReader[Node],
        includes: IncludeTree,
        model: WireModelFacts,
        encode: _Encoder = encode_managed_wire,
        *,
        memo: WireMemo[Node] | None = None,
    ) -> None:
        self._reader = reader
        self._includes = includes
        self._model = model
        self._encode = encode
        self._record_values = reader.occurrence_values
        self._memo = cast("WireMemo[Node]", NodeIndexMemo()) if memo is None else memo

    def render_at(self, node: Node, position: PositionId) -> _WireEntityNode:
        """Render ``node`` at one admitted requested position."""
        concrete = self._reader.concrete(node)
        plan = requested_plan(self._includes, self._model, position, concrete)
        if plan is None:  # pragma: no cover - explicit projection checks admission first
            raise self._reader.admission_error(concrete)
        return self.render(node, plan)

    # Runs once per rendered node, so its encoding branches stay inline rather
    # than behind per-member calls.
    def render(self, node: Node, plan: WireEntityPlan) -> _WireEntityNode:  # noqa: C901
        """Render ``node``, whose concrete ``plan`` was prepared for."""
        memo = self._memo
        token = plan.token
        cached = memo.get(node, token)
        if cached is not None:
            return cast("_WireEntityNode", cached)
        reader = self._reader
        encode = self._encode
        facts = plan.facts
        values = iter(reader.member_values(node))
        rendered: dict[str, WireValue] = {}
        for key, encoding, neutral_type, value in zip(
            facts.attribute_keys,
            facts.attribute_encodings,
            facts.attribute_types,
            values,
            strict=False,
        ):
            if value is ABSENT:
                continue
            if encoding == PASS or value is None:
                rendered[key] = cast("WireValue", value)
            elif encoding == ENCODE:
                rendered[key] = (
                    INFINITY_LITERAL
                    if type(value) is TemporalBound
                    else cast("WireValue", encode(neutral_type, cast("ManagedValue", value)))
                )
            else:
                rendered[key] = _scalars(value, neutral_type, encoding, encode)
        if facts.family_variant is not None:
            rendered[FAMILY_VARIANT_KEY] = facts.family_variant
        if facts.occurrences:
            record_values = self._record_values
            for (key, occurrence), value in zip(facts.occurrences, values, strict=True):
                if value is not ABSENT:
                    rendered[key] = _occurrence(value, occurrence, encode, record_values)
        for relationship in plan.relationships:
            value = reader.relationship(node, relationship.view)
            if value is not ABSENT:
                rendered[relationship.key] = self._render_relationship(value, relationship)
        entity = cast("_WireEntityNode", _new_dict(_WireEntityNode))
        _fill_dict(entity, rendered)
        _set_provenance(entity, "_provenance", reader.provenance(node))
        memo.put(node, token, entity)
        return entity

    def clear(self) -> None:
        self._memo.clear()

    def _render_relationship(self, value: object, relationship: WireRelationshipPlan) -> WireValue:
        """One loaded view's relationship value rendered against the reader's
        own nodes.

        The value travels in its SHAPE: a tuple is loaded-many, ``None`` is
        loaded-null, and a lone native reference is loaded-one.
        """
        if type(value) is tuple:
            return _sequence(
                [
                    self._render_admitted(element, relationship)
                    for element in cast("tuple[Node, ...]", value)
                ]
            )
        if value is None:
            return None
        return self._render_admitted(cast("Node", value), relationship)

    def _render_admitted(self, node: Node, relationship: WireRelationshipPlan) -> _WireEntityNode:
        concrete = self._reader.concrete(node)
        plan = relationship.targets.get(concrete)
        if plan is None:
            plan = relationship.target(concrete)
            if plan is None:  # pragma: no cover - fetched views hold admitted concretes
                raise self._reader.admission_error(concrete)
        return self.render(node, plan)


def _sequence(elements: Iterable[object]) -> _FrozenSequence:
    """``elements`` as one frozen Wire array, sized once from a sized input
    rather than grown element by element."""
    sequence = _new_list(_FrozenSequence)
    _extend(sequence, elements)
    return sequence


def _scalars(
    values: object, element_type: NeutralType, encoding: int, encode: _Encoder
) -> WireValue:
    """One scalar collection as the canonical immutable Wire array of its elements."""
    elements = cast("Iterable[object]", values)
    if encoding == PASS_MANY:
        return _sequence(elements)
    return _sequence(
        [
            None
            if element is None
            else INFINITY_LITERAL
            if type(element) is TemporalBound
            else encode(element_type, cast("ManagedValue", element))
            for element in elements
        ]
    )


def _occurrence(
    value: object,
    facts: WireOccurrenceFacts,
    encode: _Encoder,
    record_values: _RecordValues | None,
) -> WireValue:
    """One Value Object occurrence as its Wire mapping, or the array of them."""
    if facts.many:
        if type(value) is not tuple:
            return _new_list(_FrozenSequence)
        return _sequence(
            [
                _record(record, facts, encode, record_values)
                for record in cast("tuple[object, ...]", value)
            ]
        )
    if value is None:
        return None
    return _record(value, facts, encode, record_values)


def _record(
    record: object,
    facts: WireOccurrenceFacts,
    encode: _Encoder,
    record_values: _RecordValues | None,
) -> WireValue:
    rendered: dict[str, WireValue] = {}
    values = cast("tuple[object, ...]", record) if record_values is None else record_values(record)
    for key, encoding, detail, value in zip(
        facts.keys, facts.encodings, facts.details, values, strict=True
    ):
        if value is ABSENT:
            if encoding == OCCURRENCE:
                if cast("WireOccurrenceFacts", detail).many:
                    rendered[key] = _new_list(_FrozenSequence)
            elif encoding != PASS and encoding != ENCODE:
                rendered[key] = _new_list(_FrozenSequence)
            continue
        if encoding == PASS or value is None:
            rendered[key] = cast("WireValue", value)
        elif encoding == ENCODE:
            rendered[key] = (
                INFINITY_LITERAL
                if type(value) is TemporalBound
                else cast(
                    "WireValue", encode(cast("NeutralType", detail), cast("ManagedValue", value))
                )
            )
        elif encoding == OCCURRENCE:
            rendered[key] = _occurrence(
                value, cast("WireOccurrenceFacts", detail), encode, record_values
            )
        else:
            rendered[key] = _scalars(value, cast("NeutralType", detail), encoding, encode)
    mapping = _new_dict(_FrozenMapping)
    _fill_dict(mapping, rendered)
    return mapping


type _WireRoot = WireEntity | InvalidData[WireEntity]
"""One published Wire result position: the Entity node, or the record a root
whose stored state contradicted the model publishes in its place.

Private: every returned Entity mapping is a :class:`WireEntity`, root and
included node alike, and naming the published union would read as a second
public type for the root position where the contract has none."""


class WireRootPublisher:
    """One Page's Wire root publisher: classify each root, then render a root
    that hydrates through the include tree.

    It publishes the same verdicts the Typed publisher does: a conforming root
    answers as itself, a hydratable one as its record carrying the unwound
    value, and a non-hydrating one as its record carrying nothing. One reader
    and one renderer serve the Page, bound to the pass's Root View at the first
    root; the renderer's memo is cleared as each root's call ends, so two roots
    never share a rendered node, while the reader's provenance is shared across
    the Page's roots and released with the publisher. ``versions`` names the
    explicit version Attribute a record publishes, ``wire`` is the prepared
    model's Wire facts, and ``encode`` is the delivery's scalar encoder.
    """

    __slots__ = (
        "_encode",
        "_includes",
        "_model",
        "_reader",
        "_renderer",
        "_temporal",
        "_versions",
        "_wire",
    )

    def __init__(
        self,
        model: Metamodel,
        wire: WireModelFacts,
        versions: VersionAttributes,
        includes: IncludeTree,
        encode: _Encoder = encode_managed_wire,
    ) -> None:
        self._model = model
        self._wire = wire
        self._versions = versions
        self._includes = includes
        self._encode = encode
        self._temporal = temporal_read.view(model)
        self._reader: RootViewReader | None = None
        self._renderer: WireRenderer[int] | None = None

    def __call__(self, root: RootView, ordinal: int) -> tuple[_WireRoot, ...]:
        """``root`` published at result ``ordinal``."""
        reader = self._reader
        renderer = self._renderer
        if reader is None or renderer is None:
            reader = self._reader = RootViewReader(root, self._temporal)
            renderer = self._renderer = WireRenderer(
                reader, self._includes, self._wire, self._encode
            )
        reader.begin_root(RootConformance.CONFORMING)
        try:
            verdict = classify_root(root, self._model, self._versions, ordinal=ordinal)
            if isinstance(verdict, ConformingRoot):
                return (renderer.render_at(0, self._includes.root),)
            reader.begin_root(RootConformance.NONCONFORMING)
            if verdict.node is None:
                return (cast("InvalidData[WireEntity]", verdict.published(None)),)
            rendered = renderer.render_at(0, self._includes.root)
            return (cast("InvalidData[WireEntity]", verdict.published(rendered)),)
        finally:
            renderer.clear()
