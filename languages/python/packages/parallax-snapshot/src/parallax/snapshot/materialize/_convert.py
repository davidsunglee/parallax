"""Per-row conversion: the one place a physical column becomes a member identity.

One driver row plus its level context yields one :class:`SnapshotNodeInput`, and
nothing below this seam sees a physical column, a storage key, or a Document Path
again. Any bulk path is a thin loop over :func:`convert_row`, and the graph-local
identity scope it registers into is an explicit argument rather than a
whole-result index — a milestone-set read gives each milestone its own scope, and
a future incremental read can scope identity however it needs without a second
conversion.

Conversion owns document-resident occurrences end to end: stored-document
presence, container shape, and leaf decoding resolve here into
:class:`~parallax.core.entity._graph_input.ValueObjectOccurrenceInput` /
:class:`~parallax.core.entity._graph_input.ValueObjectAttributeInput` keyed by
structured identity. An undeclared stored key never contributes; a missing member
and a stored JSON null both read as ``None``; no raw document mapping continues
past here.

:func:`observable_columns` is the deliberate exception, and it is not below the
seam: an observation is a physical record by contract (`m-unit-work`'s Predecessor
Row is keyed by column), so the write side is served by its own explicitly
physical function rather than by leaking a column-keyed mapping out of conversion.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, cast

from parallax.core.db_port import Row
from parallax.core.document_codec import (
    LeafEncodingError,
    occurrence_shape,
    reduce_declared_members,
)
from parallax.core.entity._graph_input import (
    EntityAttributeInput,
    ValueObjectAttributeInput,
    ValueObjectOccurrenceInput,
    ValueObjectRecord,
)
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.core.temporal_read import Pin
from parallax.snapshot.materialize._input import (
    LogicalKey,
    RelationshipViewKey,
    SnapshotGraphInput,
    SnapshotNodeInput,
    SnapshotNodeRef,
    SnapshotRelationshipViewInput,
    logical_key,
)

__all__ = [
    "SNAPSHOT_DECODING_FAILED",
    "LevelContext",
    "MergeScope",
    "SnapshotDecodingError",
    "convert_row",
    "observable_columns",
]

_VoContainer = ValueObjectMetadata | NestedValueObjectMetadata

SNAPSHOT_DECODING_FAILED: Final[str] = "snapshot-decoding-failed"
"""The one code conversion refuses under."""


class SnapshotDecodingError(ValueError):
    """Stored data a read cannot convert into the graph-input algebra.

    Raised where a stored document contradicts its declared shape — a leaf that is
    not the one document spelling its Neutral Type gives some value of its space,
    or an occurrence stored in a kind its multiplicity does not admit. It carries
    the concrete Entity the row resolved to and the member identity at fault, and
    it deliberately exposes **no** raw database value: the value that provoked it
    survives on the chained ``cause`` for a first-party diagnosis, not in the
    message a caller sees.

    A decoding failure is never wrapped as
    :class:`~parallax.snapshot.handle.SnapshotMaterializationError`: no Entity
    graph was being built when it happened.
    """

    code: Final[str] = SNAPSHOT_DECODING_FAILED

    def __init__(
        self,
        message: str,
        *,
        entity: EntityIdentity,
        member: ValueObjectIdentity | ValueObjectAttributeIdentity,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(f"{SNAPSHOT_DECODING_FAILED}: {message}")
        self.message = message
        self.entity = entity
        self.member = member
        self.cause = cause


@dataclass(frozen=True, slots=True)
class LevelContext:
    """What one row of one level converts under.

    ``concrete_entity`` is the exact Entity that row's own compiled read resolved
    it to — a per-row fact under table-per-hierarchy, which is why it travels
    here rather than being re-derived from a synthetic tag. ``documents`` is the
    resolved position's own `Document` tier contributors, decided once where the
    projection was, so no level re-projects a family superset of its own.
    """

    concrete_entity: EntityIdentity
    documents: tuple[ValueObjectMetadata, ...] = ()


def _new_nodes() -> list[SnapshotNodeInput]:
    return []


def _new_views() -> list[dict[RelationshipViewKey, SnapshotRelationshipViewInput]]:
    return []


def _new_identity() -> dict[LogicalKey, SnapshotNodeRef]:
    return {}


@dataclass(slots=True)
class MergeScope:
    """One materialization's graph-local identity scope and node accumulator.

    Graph-local identity resolution promises node reuse within one scope and never
    beyond it, so the scope is the unit a caller chooses: a `find` gives its whole
    result one, and a milestone-set read gives each milestone its own. The FIRST
    projection registered for a logical key is the one a later back-reference
    resolves to.

    Relationship views accumulate separately from the node records because a
    parent's views are only known once its child level lands, and the raw parent
    row is long gone by then. :meth:`build` composes the immutable graph input
    once, reusing every member tuple by reference rather than copying one.
    """

    model: Metamodel
    _nodes: list[SnapshotNodeInput] = field(default_factory=_new_nodes)
    _views: list[dict[RelationshipViewKey, SnapshotRelationshipViewInput]] = field(
        default_factory=_new_views
    )
    _identity: dict[LogicalKey, SnapshotNodeRef] = field(default_factory=_new_identity)

    def add(self, node: SnapshotNodeInput) -> SnapshotNodeRef:
        """Register one converted projection and answer the reference naming it."""
        ref = SnapshotNodeRef(len(self._nodes))
        self._nodes.append(node)
        self._views.append({})
        key = logical_key(self.model, node)
        if key is not None:  # pragma: no branch - every accepted Entity keys
            self._identity.setdefault(key, ref)
        return ref

    def node(self, ref: SnapshotNodeRef) -> SnapshotNodeInput:
        """The projection ``ref`` names."""
        return self._nodes[ref.node_index]

    def resolve(self, family: EntityIdentity, key: tuple[object, ...]) -> SnapshotNodeRef | None:
        """The first projection registered under ``(family, key)``, if any — how a
        back-reference level reaches an ancestor it issues no query for."""
        return self._identity.get((family, key))

    def attach(
        self,
        ref: SnapshotNodeRef,
        view: RelationshipViewKey,
        value: SnapshotNodeRef | tuple[SnapshotNodeRef, ...] | None,
    ) -> None:
        """Record one relationship view on an already-converted projection.

        Keyed rather than appended, because two levels may legitimately attach one
        view: a guarded path and its broad sibling are distinct hops with the same
        view key, and a parent both admit is attached twice. A guard filters
        parents rather than children, so the two attachments carry the same value,
        and one entry per view is what the graph input is stated to hold.
        """
        self._views[ref.node_index][view] = SnapshotRelationshipViewInput(view, value)

    def build(self, roots: tuple[SnapshotNodeRef, ...], pin: Pin) -> SnapshotGraphInput:
        """This scope's whole graph input, roots in result order."""
        nodes = tuple(
            node
            if not views
            else SnapshotNodeInput(
                concrete_entity=node.concrete_entity,
                attributes=node.attributes,
                value_objects=node.value_objects,
                relationship_views=tuple(views.values()),
            )
            for node, views in zip(self._nodes, self._views, strict=True)
        )
        return SnapshotGraphInput(nodes=nodes, roots=roots, pin=pin)


def convert_row(row: Row, level: LevelContext, scope: MergeScope) -> SnapshotNodeRef:
    """Convert one driver row into ``scope``'s next :class:`SnapshotNodeInput`.

    Answers the reference the scope assigned rather than the record itself: the
    scope retains the record, and a caller that held its own copy would be the
    second place a projection lives.

    Scalars are keyed by each Attribute's own physical column, so a disjoint
    sibling's null-padded column — and the synthetic family tag — contributes
    nothing rather than landing on a member that never declared it.
    """
    projected = _document_columns(level)
    attributes = tuple(
        EntityAttributeInput(attribute.identity, row[attribute.storage.name])
        for attribute in _applicable_attributes(scope.model, level.concrete_entity)
        if attribute.storage.name in row
    )
    value_objects = tuple(
        ValueObjectOccurrenceInput(
            occurrence.identity,
            _occurrence(row.get(occurrence.storage.name), occurrence, level.concrete_entity),
        )
        for occurrence in _applicable_value_objects(scope.model, level.concrete_entity)
        if occurrence.storage.name in projected
    )
    return scope.add(
        SnapshotNodeInput(
            concrete_entity=level.concrete_entity,
            attributes=attributes,
            value_objects=value_objects,
        )
    )


def observable_columns(row: Row, level: LevelContext) -> dict[str, object]:
    """One row's observable state, keyed by PHYSICAL column, documents decoded.

    What a participating read hands its observation collector: the complete
    persisted row a Predecessor Row requires (`m-unit-work`), with each projected
    document decoded to its declared shape exactly as conversion decodes it, so a
    successor's carried-versus-changed comparison reads one spelling of a member
    rather than two.

    Deliberately outside the graph-input algebra. An observation is physical by
    contract, and keeping it a separate function is what stops a column-keyed
    mapping riding along inside a converted node.
    """
    projected = _document_columns(level)
    columns = {key: value for key, value in row.items() if key not in projected}
    for occurrence in level.documents:
        columns[occurrence.storage.name] = _decode_document(
            row.get(occurrence.storage.name), occurrence, level.concrete_entity
        )
    return columns


def _document_columns(level: LevelContext) -> frozenset[str]:
    return frozenset(member.storage.name for member in level.documents)


def _applicable_attributes(
    model: Metamodel, identity: EntityIdentity
) -> tuple[AttributeMetadata, ...]:
    """``identity``'s family-effective Attributes — inherited ones under their own
    declaring identity, which is how an ancestor's member reaches a concrete."""
    position = inheritance_view(model).entity(identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return ()
    return tuple(position.applicable_attributes)


def _applicable_value_objects(
    model: Metamodel, identity: EntityIdentity
) -> tuple[ValueObjectMetadata, ...]:
    position = inheritance_view(model).entity(identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return ()
    return tuple(position.applicable_value_objects)


# --------------------------------------------------------------------------- #
# Document decoding.                                                           #
# --------------------------------------------------------------------------- #


def _occurrence(
    raw: object, declared: _VoContainer, entity: EntityIdentity
) -> ValueObjectRecord | tuple[ValueObjectRecord, ...] | None:
    """One TOP-LEVEL occurrence as the immutable record algebra.

    Decoding and structuring are two passes on purpose: the codec's reduction is
    already recursive, so it runs exactly once per stored occurrence and
    :func:`_structure` then walks what it produced. Decoding a nested value a
    second time would ask the codec to read a managed value as a document
    spelling, which is a different thing entirely.
    """
    return _structure_occurrence(_decode_document(raw, declared, entity), declared)


def _structure_occurrence(
    decoded: object, declared: _VoContainer
) -> ValueObjectRecord | tuple[ValueObjectRecord, ...] | None:
    """One already-reduced occurrence as records.

    A Many occurrence has no absent state: its zero-element value is the empty
    tuple, and an element the reduction collapsed contributes none. A One
    occurrence is ``None`` exactly where the reduction collapsed the whole
    composite.
    """
    if declared.multiplicity is Multiplicity.MANY:
        items = cast("list[object]", decoded) if isinstance(decoded, list) else []
        return tuple(
            _structure(cast("Mapping[str, object]", item), declared)
            for item in items
            if item is not None
        )
    if decoded is None:
        return None
    return _structure(cast("Mapping[str, object]", decoded), declared)


def _decode_document(raw: object, declared: _VoContainer, entity: EntityIdentity) -> object:
    """One occurrence reduced to its declared members, as the plain document shape
    an observation retains."""
    if declared.multiplicity is Multiplicity.MANY:
        items = cast("list[object]", raw) if isinstance(raw, list) else []
        return [_decode_element(item, declared, entity) for item in items]
    return _decode_element(raw, declared, entity)


def _decode_element(
    raw: object, declared: _VoContainer, entity: EntityIdentity
) -> dict[str, object] | None:
    """One ``one``-shaped document (or array element) reduced to its DECLARED
    members: a non-mapping collapses to ``None`` — the whole composite absent —
    never a partial mapping, and an absent or JSON-null leaf answers ``None``
    while a present one decodes by its declared Neutral Type."""
    try:
        reduced = reduce_declared_members(
            occurrence_shape(declared), raw, collapse_invalid_occurrences=True
        )
    except LeafEncodingError as exc:
        raise _decoding_error(exc, declared, entity) from exc
    return cast("dict[str, object] | None", reduced)


def _structure(document: Mapping[str, object], declared: _VoContainer) -> ValueObjectRecord:
    """One reduced document as the immutable record algebra, keyed by structured
    identity at every depth. No raw document mapping continues past here."""
    return ValueObjectRecord(
        attributes=tuple(
            ValueObjectAttributeInput(leaf.identity, document[leaf.identity.name])
            for leaf in declared.attributes
            if leaf.identity.name in document
        ),
        value_objects=tuple(
            ValueObjectOccurrenceInput(
                nested.identity,
                _structure_occurrence(document[nested.identity.path[-1]], nested),
            )
            for nested in declared.value_objects
            if nested.identity.path[-1] in document
        ),
    )


def _decoding_error(
    exc: LeafEncodingError, declared: _VoContainer, entity: EntityIdentity
) -> SnapshotDecodingError:
    """The refusal one codec failure becomes, resolved to the member at fault.

    The codec names the failing member as a SEQUENCE of declared names relative to
    the occurrence being reduced, and its detail may quote the stored value. Only
    the names reach the message; the detail stays on the chained cause, so nothing
    a caller sees exposes stored data.
    """
    occurrence = ".".join(declared.identity.path)
    spelled = ".".join((occurrence, *exc.path))
    return SnapshotDecodingError(
        f"{entity.canonical}.{spelled} holds data its declared shape does not admit",
        entity=entity,
        member=_member_identity(declared, exc.path),
        cause=exc,
    )


def _member_identity(
    declared: _VoContainer, path: tuple[str, ...]
) -> ValueObjectIdentity | ValueObjectAttributeIdentity:
    """The declared member ``path`` names inside ``declared``, descending through
    the nested occurrences on the way, or the occurrence itself where the codec
    reported no path — a whole document stored in a kind it cannot be read as.

    Each step matches one declared name exactly. Resolving a rendered path
    instead could not be exact: a member name is any nonempty string
    (`m-metamodel` "Canonical identities and order"), so a leaf named ``a.b`` and
    a leaf ``b`` inside an occurrence ``a`` spell one dotted path between them.
    """
    container = declared
    for name in path:
        leaf = next((one for one in container.attributes if one.identity.name == name), None)
        if leaf is not None:
            return leaf.identity
        nested = next(
            (one for one in container.value_objects if one.identity.path[-1] == name), None
        )
        if nested is None:  # pragma: no cover - the codec reports declared members only
            break
        container = nested
    return container.identity
