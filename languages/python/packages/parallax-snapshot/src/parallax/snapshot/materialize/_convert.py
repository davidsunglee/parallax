"""Per-row conversion: the one place a physical column becomes a member identity.

One SQL-materialized row's transformed values plus its level context and
classified provenance yield one :class:`SnapshotNodeInput`. Nothing below this
seam sees a physical column, a storage key, or a Document Path again. Any bulk
path is a thin loop over :func:`convert_row`, and the graph-local identity scope
it registers into is an explicit argument rather than a whole-result index — a
milestone-set read gives each milestone its own scope, and a future incremental
read can scope identity however it needs without a second conversion.

SQL row transforms classify and decode projected Entity-document members first,
then pass their findings, classified-member set, and transformed values here.
Conversion owns Value Object occurrence reduction after that boundary:
stored-document presence, container shape, and leaf decoding resolve into
:class:`~parallax.core.entity._graph_input.ValueObjectOccurrenceInput` /
:class:`~parallax.core.entity._graph_input.ValueObjectAttributeInput` keyed by
structured identity. An undeclared stored key never contributes; a member the
stored document omits contributes no input at all, while one stored as JSON null
contributes ``None`` — the presence distinction the carriers reconstruct; no raw
document mapping continues past here.

:func:`observable_columns` is the deliberate exception, and it is not below the
seam: an observation is a physical record by contract (`m-unit-work`'s Predecessor
Row is keyed by column), so the write side is served by its own explicitly
physical function rather than by leaking a column-keyed mapping out of conversion.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, cast

from parallax.core.base import (
    DocumentValue,
    NeutralType,
    PresentDocument,
    SqlNull,
    admits_stored_scalar,
    decode_neutral_literal,
    unwrap_document_read,
)
from parallax.core.db_port import Row
from parallax.core.document_codec import (
    UNAVAILABLE,
    DocumentFinding,
    DocumentPathSegment,
    Present,
    decode_occurrence_classified,
    occurrence_shape,
    reduce_declared_members_classified,
)
from parallax.core.entity._graph_input import (
    EntityAttributeInput,
    ValueObjectAttributeInput,
    ValueObjectOccurrenceInput,
    ValueObjectRecord,
)
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    PrimaryKey,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.core.temporal_read import Pin
from parallax.snapshot.materialize._input import (
    InvalidRootInput,
    LogicalKey,
    RelationshipViewKey,
    SnapshotGraphInput,
    SnapshotNodeInput,
    SnapshotNodeRef,
    SnapshotRelationshipViewInput,
    StoredDataIssueCode,
    StoredDataIssueInput,
    has_invalid_key,
    logical_key,
)
from parallax.snapshot.materialize._publication import (
    SNAPSHOT_DECODING_FAILED,
    SnapshotDecodingError,
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


class _AttributeReadContract(Protocol):
    @property
    def identity(self) -> AttributeIdentity: ...

    @property
    def column(self) -> str: ...

    @property
    def result_key(self) -> str: ...

    @property
    def type(self) -> NeutralType: ...

    @property
    def encoded(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class LevelContext:
    """What one row of one level converts under.

    ``concrete_entity`` is the exact Entity that row's own compiled read resolved
    it to — a per-row fact under table-per-hierarchy, which is why it travels
    here rather than being re-derived from a synthetic tag. ``documents`` is the
    resolved position's own `Document` tier contributors, decided once where the
    projection was, so no level re-projects a family superset of its own.
    ``attribute_reads`` carries each compiled projection's logical identity,
    physical column, actual driver key, and decode contract intact. This keeps an
    encoded result such as ``payload_hex`` attached to physical ``payload``.
    """

    concrete_entity: EntityIdentity
    documents: tuple[ValueObjectMetadata, ...] = ()
    attribute_reads: tuple[_AttributeReadContract, ...] = ()


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
        key = None if has_invalid_key(node) else logical_key(self.model, node)
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
                issues=node.issues,
            )
            for node, views in zip(self._nodes, self._views, strict=True)
        )
        result_roots = tuple(
            InvalidRootInput(ordinal, nodes[ref.node_index].issues)
            if has_invalid_key(nodes[ref.node_index])
            else ref
            for ordinal, ref in enumerate(roots)
        )
        return SnapshotGraphInput(
            nodes=nodes,
            roots=result_roots,
            pin=pin,
            has_issues=any(node.issues for node in nodes),
        )


def convert_row(
    row: Row,
    level: LevelContext,
    scope: MergeScope,
    *,
    findings: tuple[DocumentFinding, ...] = (),
    family_tag_unknown: bool = False,
    classified_members: frozenset[str] = frozenset(),
) -> SnapshotNodeRef:
    """Convert one SQL-materialized row into ``scope``'s next
    :class:`SnapshotNodeInput`.

    Answers the reference the scope assigned rather than the record itself: the
    scope retains the record, and a caller that held its own copy would be the
    second place a projection lives.

    ``findings``, ``family_tag_unknown``, and ``classified_members`` are the
    compiled row transform's provenance. Conversion translates those findings
    and does not re-judge members the transform already classified.

    Scalars are keyed by the compiled projection contract. A disjoint sibling's
    null-padded result — and the synthetic family tag — therefore contributes
    nothing rather than landing on a member that never declared it.
    """
    projected = _document_columns(level)
    issues: list[StoredDataIssueInput] = [
        _translate_finding(finding, level, scope.model) for finding in findings
    ]
    if family_tag_unknown:
        issues.append(StoredDataIssueInput("stored-data-family-tag-unknown", level.concrete_entity))
    attributes: list[EntityAttributeInput] = []
    result_keys = {contract.identity: contract for contract in level.attribute_reads}
    for attribute in _applicable_attributes(scope.model, level.concrete_entity):
        contract = result_keys.get(attribute.identity)
        result_key = attribute.storage.name if contract is None else contract.result_key
        if result_key not in row:
            continue
        raw = row[result_key]
        value = (
            decode_neutral_literal(raw, attribute.type)
            if contract is not None and contract.encoded
            else raw
        )
        issue = (
            None
            if result_key in classified_members
            else _attribute_issue(attribute, value, level.concrete_entity, scope.model)
        )
        if issue is not None:
            issues.append(issue)
        if admits_stored_scalar(
            value,
            attribute.type,
            nullable=attribute.nullable,
            temporal_end=_is_temporal_end(attribute, level.concrete_entity, scope.model),
        ):
            attributes.append(EntityAttributeInput(attribute.identity, value))
    value_objects: list[ValueObjectOccurrenceInput] = []
    for occurrence in _applicable_value_objects(scope.model, level.concrete_entity):
        if occurrence.storage.name not in projected:
            continue
        raw = row.get(occurrence.storage.name)
        value, occurrence_findings = _occurrence(
            raw,
            occurrence,
            level.concrete_entity,
            outer_classified=occurrence.storage.name in classified_members,
        )
        issues.extend(
            _occurrence_issue(finding, occurrence, level.concrete_entity)
            for finding in occurrence_findings
        )
        value_objects.append(ValueObjectOccurrenceInput(occurrence.identity, value))
    return scope.add(
        SnapshotNodeInput(
            concrete_entity=level.concrete_entity,
            attributes=tuple(attributes),
            value_objects=tuple(value_objects),
            issues=tuple(issues),
        )
    )


def _attribute_issue(
    attribute: AttributeMetadata,
    value: object,
    entity: EntityIdentity,
    model: Metamodel,
) -> StoredDataIssueInput | None:
    temporal_end = _is_temporal_end(attribute, entity, model)
    if admits_stored_scalar(
        value,
        attribute.type,
        nullable=attribute.nullable,
        temporal_end=temporal_end,
    ):
        return None
    if value is None:
        code: StoredDataIssueCode = (
            "stored-data-primary-key-null"
            if isinstance(attribute.primary_key, PrimaryKey)
            else "stored-data-attribute-null"
        )
        return StoredDataIssueInput(code, entity, attribute.identity)
    code = (
        "stored-data-primary-key-undecodable"
        if isinstance(attribute.primary_key, PrimaryKey)
        else "stored-data-leaf-undecodable"
    )
    return StoredDataIssueInput(code, entity, attribute.identity)


def _is_temporal_end(
    attribute: AttributeMetadata, entity: EntityIdentity, model: Metamodel
) -> bool:
    position = inheritance_view(model).entity(entity)
    if position is None:  # pragma: no cover - accepted entities have a view
        return False
    root = model.entity(position.root)
    return root is not None and any(
        axis.end_attribute == attribute.identity for axis in root.declared_as_of_axes
    )


def observable_columns(
    row: Row,
    level: LevelContext,
    *,
    classified_members: frozenset[str] = frozenset(),
) -> dict[str, object]:
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
    attribute_keys = frozenset(contract.result_key for contract in level.attribute_reads)
    columns = {key: value for key, value in row.items() if key not in projected | attribute_keys}
    for contract in level.attribute_reads:
        if contract.result_key not in row:
            continue
        raw = row[contract.result_key]
        columns[contract.column] = (
            decode_neutral_literal(raw, contract.type) if contract.encoded else raw
        )
    for occurrence in level.documents:
        raw = row.get(occurrence.storage.name)
        if isinstance(raw, (SqlNull, PresentDocument)):
            raw = unwrap_document_read(raw)
        columns[occurrence.storage.name] = _decode_document(
            raw,
            occurrence,
            level.concrete_entity,
            outer_classified=occurrence.storage.name in classified_members,
        )[0]
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
    raw: object,
    declared: _VoContainer,
    entity: EntityIdentity,
    *,
    outer_classified: bool = False,
) -> tuple[ValueObjectRecord | tuple[ValueObjectRecord, ...] | None, tuple[DocumentFinding, ...]]:
    """One TOP-LEVEL occurrence as the immutable record algebra.

    Decoding and structuring are two passes on purpose: the codec's reduction is
    already recursive, so it runs exactly once per stored occurrence and
    :func:`_structure` then walks what it produced. Decoding a nested value a
    second time would ask the codec to read a managed value as a document
    spelling, which is a different thing entirely.
    """
    decoded, findings = _decode_document(raw, declared, entity, outer_classified=outer_classified)
    return _structure_occurrence(decoded, declared), findings


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


def _decode_document(
    raw: object,
    declared: _VoContainer,
    entity: EntityIdentity,
    *,
    outer_classified: bool = False,
) -> tuple[object, tuple[DocumentFinding, ...]]:
    """One occurrence reduced to its declared members, as the plain document shape
    an observation retains."""
    if outer_classified:
        return raw, ()
    outer_findings: tuple[DocumentFinding, ...] = ()
    carrier = (
        raw
        if isinstance(raw, (SqlNull, PresentDocument))
        else SqlNull()
        if raw is None
        else PresentDocument(cast("DocumentValue", raw))
    )
    classified = decode_occurrence_classified(
        occurrence_shape(declared),
        carrier,
        multiplicity=declared.multiplicity,
        nullable=declared.nullable,
    )
    outer_findings = classified.findings
    raw = classified.presence.value if isinstance(classified.presence, Present) else None
    if declared.multiplicity is Multiplicity.MANY:
        items = cast("list[object]", raw) if isinstance(raw, list) else []
        decoded: list[object] = []
        findings: list[DocumentFinding] = list(outer_findings)
        for index, item in enumerate(items):
            element, element_findings = _decode_element(item, declared, entity)
            decoded.append(element)
            findings.extend(
                DocumentFinding(finding.code, (index, *finding.path))
                for finding in element_findings
            )
        return decoded, tuple(findings)
    one_decoded, one_findings = _decode_element(raw, declared, entity)
    return one_decoded, (*outer_findings, *one_findings)


def _decode_element(
    raw: object, declared: _VoContainer, entity: EntityIdentity
) -> tuple[dict[str, object] | None, tuple[DocumentFinding, ...]]:
    """One ``one``-shaped document (or array element) reduced to the DECLARED
    members the stored document holds: a non-mapping collapses to ``None`` — the
    whole composite absent — never a partial mapping, and a JSON-null leaf answers
    ``None`` while a present one decodes by its declared Neutral Type.

    A member the stored document omits contributes no key, at every containment
    depth, so what a read carries forward is the document's own presence rather
    than the declared member list. That is what lets a materialized occurrence be
    re-serialized without inventing a key storage never held. The presence option
    is not the authored-member mask mutation comparison supplies: this source
    answers for itself which members it holds, so no mask is passed."""
    reduced, findings = reduce_declared_members_classified(
        occurrence_shape(declared), raw, preserve_presence=True
    )
    return cast("dict[str, object] | None", reduced), findings


def _structure(document: Mapping[str, object], declared: _VoContainer) -> ValueObjectRecord:
    """One reduced document as the immutable record algebra, keyed by structured
    identity at every depth. No raw document mapping continues past here."""
    return ValueObjectRecord(
        attributes=tuple(
            ValueObjectAttributeInput(leaf.identity, document[leaf.identity.name])
            for leaf in declared.attributes
            if leaf.identity.name in document and document[leaf.identity.name] is not UNAVAILABLE
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


def _translate_finding(
    finding: DocumentFinding, level: LevelContext, model: Metamodel
) -> StoredDataIssueInput:
    path = _logical_path(finding.path)
    occurrence = next(
        (
            declared
            for declared in _applicable_value_objects(model, level.concrete_entity)
            if path and declared.identity.path[-1] == path[0]
        ),
        None,
    )
    attribute = next(
        (
            declared
            for declared in _applicable_attributes(model, level.concrete_entity)
            if path and declared.identity.name == path[0]
        ),
        None,
    )
    member = (
        attribute.identity
        if attribute is not None
        else None
        if occurrence is None
        else _member_identity(occurrence, path[1:])
    )
    code = _stored_issue_code(
        finding,
        entity_attribute=attribute is not None,
        primary_key=attribute is not None and isinstance(attribute.primary_key, PrimaryKey),
    )
    return StoredDataIssueInput(code, level.concrete_entity, member, finding.path)


def _occurrence_issue(
    finding: DocumentFinding, declared: _VoContainer, entity: EntityIdentity
) -> StoredDataIssueInput:
    path = _logical_path(finding.path)
    return StoredDataIssueInput(
        _stored_issue_code(finding),
        entity,
        _member_identity(declared, path),
        (declared.identity.path[-1], *finding.path),
    )


def _stored_issue_code(
    finding: DocumentFinding,
    *,
    entity_attribute: bool = False,
    primary_key: bool = False,
) -> StoredDataIssueCode:
    if primary_key and finding.code == "leaf-undecodable":
        return "stored-data-primary-key-undecodable"
    if entity_attribute and finding.code in {
        "required-member-absent",
        "required-member-null",
    }:
        return "stored-data-attribute-null"
    return cast("StoredDataIssueCode", f"stored-data-{finding.code}")


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


def _logical_path(path: tuple[DocumentPathSegment, ...]) -> tuple[str, ...]:
    return tuple(part for part in path if isinstance(part, str))
