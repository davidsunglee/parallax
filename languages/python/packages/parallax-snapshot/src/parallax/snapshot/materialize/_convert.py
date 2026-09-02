"""Per-row conversion: the one place a physical column becomes a member identity.

One SQL-materialized row's transformed values plus its level context and
classified provenance yield one compact projection row. Nothing below this
seam sees a physical column, a storage key, or a Document Path again. Any bulk
path is a thin loop over :func:`convert_row`, and the graph-local identity scope
it registers into is an explicit argument rather than a whole-result index — a
milestone-set read gives each milestone its own scope, and a future incremental
read can scope identity however it needs without a second conversion.

SQL row transforms classify and decode projected Entity-document members first,
then pass their findings, classified-member set, and transformed values here.
Conversion owns Value Object occurrence reduction after that boundary:
stored-document presence, container shape, and leaf decoding resolve into
positional member rows laid out by the exact, path-specific Value Object layout,
recursively at every depth. An undeclared stored key never contributes, and every
declared one occupies its own position — holding the value exactly where the read
contract says the value carries it, and ``ABSENT`` where the stored document held
nothing (`m-snapshot-read` *What a materialized value carries*). This is the seam
that realizes that contract, so a member present here is the same member a getter
and a published node agree the value has. No raw document mapping continues past
here.

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
    SQL_NULL,
    DocumentValue,
    NeutralType,
    PresentDocument,
    SqlNull,
    admits_stored_scalar,
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
from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    Multiplicity,
    NestedValueObjectMetadata,
    PrimaryKey,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.core.wire import WireDecodingError, WireValue, decode_canonical_wire
from parallax.snapshot.materialize._graph import (
    ABSENT,
    GraphBuilder,
    StoredDataIssueCode,
    StoredDataIssueInput,
)
from parallax.snapshot.materialize._publication import (
    SNAPSHOT_DECODING_FAILED,
    SnapshotDecodingError,
)
from parallax.snapshot.materialize._views import SourceLevel

__all__ = [
    "SNAPSHOT_DECODING_FAILED",
    "LevelContext",
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

    ``layout`` is the model-owned member layout of the exact Entity that row's
    own compiled read resolved it to, and is where the applicable member set and
    its order come from: it is fixed by the model, so a catalog derives it per
    Entity and every row of this level shares the one it was answered rather
    than re-resolving one per conversion.
    ``concrete_entity`` is read off that layout rather than supplied beside it —
    the exact Entity is a per-row fact under table-per-hierarchy, which is why it
    travels here rather than being re-derived from a synthetic tag, and taking it
    from the layout is what keeps a context from naming one Entity while laying
    out another. ``documents`` is the resolved position's own `Document` tier
    contributors, decided once where the projection was, so no level re-projects
    a family superset of its own. ``attribute_reads`` carries each compiled
    projection's logical identity, physical column, actual driver key, and decode
    contract intact. This keeps an encoded result such as ``payload_hex``
    attached to physical ``payload``.

    ``layout`` stays out of equality and hashing: ``concrete_entity`` already
    distinguishes every context it distinguishes — two layouts for one exact
    Entity are interchangeable — while comparing it would walk a whole shared
    layout tree and holding it in the hash would cost this context the
    hashability its scalar fields give it.
    """

    layout: EntityLayout = field(compare=False)
    concrete_entity: EntityIdentity = field(init=False)
    documents: tuple[ValueObjectMetadata, ...] = ()
    attribute_reads: tuple[_AttributeReadContract, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "concrete_entity", self.layout.concrete)


def convert_row(
    row: Row,
    level: LevelContext,
    builder: GraphBuilder,
    *,
    source: SourceLevel,
    findings: tuple[DocumentFinding, ...] = (),
    family_tag_unknown: bool = False,
    classified_members: frozenset[str] = frozenset(),
) -> int:
    """Convert one SQL-materialized row into ``builder``'s next projection.

    Answers the projection index the builder assigned rather than the row
    itself: the builder retains the row, and a caller that held its own copy
    would be the second place a projection lives.

    ``source`` is the plan level this row was read at, and is a fact about where
    the projection lands rather than about how the row decodes — which is why it
    travels beside the builder rather than inside ``level``, whose own identity
    distinguishes what a row converts under and nothing else.

    The row is POSITIONAL, laid out by ``level.layout``: every applicable
    Attribute occupies its declared position and every applicable top-level
    Value Object occurrence occupies its own after them, whether or not this
    read projected it. A position the read did not carry, and one whose stored
    value no conforming member could hold, both read ``ABSENT`` — beside the
    issue the latter records — which is what keeps a member the read omitted
    distinguishable from one stored null.

    ``findings``, ``family_tag_unknown``, and ``classified_members`` are the
    compiled row transform's provenance. Conversion translates those findings
    and does not re-judge members the transform already classified.

    Scalars are keyed by the compiled projection contract. A disjoint sibling's
    null-padded result — and the synthetic family tag — therefore contributes
    nothing rather than landing on a member that never declared it.
    """
    layout = level.layout
    projected = _document_columns(level)
    issues: list[StoredDataIssueInput] = [
        _translate_finding(finding, level) for finding in findings
    ]
    if family_tag_unknown:
        issues.append(StoredDataIssueInput("stored-data-family-tag-unknown", level.concrete_entity))
    members: list[object] = []
    result_keys = {contract.identity: contract for contract in level.attribute_reads}
    for attribute in layout.attributes:
        contract = result_keys.get(attribute.identity)
        result_key = attribute.storage.name if contract is None else contract.result_key
        if result_key not in row:
            members.append(ABSENT)
            continue
        raw = row[result_key]
        try:
            value = (
                decode_canonical_wire(attribute.type, cast("WireValue", raw))
                if contract is not None and contract.encoded
                else raw
            )
        except WireDecodingError:
            value = raw
        admitted = admits_stored_scalar(
            value,
            attribute.type,
            nullable=attribute.nullable,
            temporal_end=attribute.identity in layout.temporal_ends,
        )
        if not admitted and result_key not in classified_members:
            issues.append(_attribute_issue(attribute, value, level.concrete_entity))
        members.append(value if admitted else ABSENT)
    for occurrence in layout.occurrences:
        if occurrence.storage.name not in projected:
            members.append(ABSENT)
            continue
        raw = row.get(occurrence.storage.name)
        value, occurrence_findings = _occurrence(
            raw,
            occurrence,
            outer_classified=occurrence.storage.name in classified_members,
        )
        issues.extend(
            _occurrence_issue(finding, occurrence, level.concrete_entity)
            for finding in occurrence_findings
        )
        members.append(value)
    return builder.add(source, layout, tuple(members), tuple(issues))


def _attribute_issue(
    attribute: AttributeMetadata,
    value: object,
    entity: EntityIdentity,
) -> StoredDataIssueInput:
    """The classification one inadmissible stored scalar carries."""
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


def observable_columns(
    row: Row,
    level: LevelContext,
    *,
    classified_members: frozenset[str] = frozenset(),
) -> dict[str, object]:
    """One row's observable state, keyed by PHYSICAL column, documents decoded.

    What a graph-form read retains evidence from: the complete persisted row a
    Predecessor Row requires (`m-unit-work`), with each projected
    document decoded to its declared shape exactly as conversion decodes it, so a
    successor's carried-versus-changed comparison reads one spelling of a member
    rather than two.

    Deliberately outside the projection-row algebra. An observation is physical by
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
            decode_canonical_wire(contract.type, cast("WireValue", raw))
            if contract.encoded
            else raw
        )
    for occurrence in level.documents:
        raw = row.get(occurrence.storage.name)
        if isinstance(raw, (SqlNull, PresentDocument)):
            raw = unwrap_document_read(raw)
        columns[occurrence.storage.name] = _decode_document(
            raw,
            occurrence,
            outer_classified=occurrence.storage.name in classified_members,
        )[0]
    return columns


def _document_columns(level: LevelContext) -> frozenset[str]:
    return frozenset(member.storage.name for member in level.documents)


# --------------------------------------------------------------------------- #
# Document decoding.                                                           #
# --------------------------------------------------------------------------- #


def _occurrence(
    raw: object,
    declared: _VoContainer,
    *,
    outer_classified: bool = False,
) -> tuple[object, tuple[DocumentFinding, ...]]:
    """One TOP-LEVEL occurrence as the positional member rows a slot holds.

    Decoding and structuring are two passes on purpose: the codec's reduction is
    already recursive, so it runs exactly once per stored occurrence and
    :func:`_structure` then walks what it produced. Decoding a nested value a
    second time would ask the codec to read a managed value as a document
    spelling, which is a different thing entirely.
    """
    decoded, findings = _decode_document(raw, declared, outer_classified=outer_classified)
    return _structure_occurrence(decoded, declared), findings


def _structure_occurrence(decoded: object, declared: _VoContainer) -> tuple[object, ...] | None:
    """One already-reduced occurrence as member rows.

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
        else SQL_NULL
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
            element, element_findings = _decode_element(item, declared)
            decoded.append(element)
            findings.extend(
                DocumentFinding(finding.code, (index, *finding.path))
                for finding in element_findings
            )
        return decoded, tuple(findings)
    one_decoded, one_findings = _decode_element(raw, declared)
    return one_decoded, (*outer_findings, *one_findings)


def _decode_element(
    raw: object, declared: _VoContainer
) -> tuple[dict[str, object] | None, tuple[DocumentFinding, ...]]:
    """One ``one``-shaped document (or array element) reduced to the members the
    read contract carries: a non-mapping collapses to ``None`` — the whole
    composite absent — never a partial mapping, and a JSON-null leaf answers
    ``None`` while a present one decodes by its declared Neutral Type.

    Which declared members become keys is the read contract itself
    (`m-snapshot-read` *What a materialized value carries*), which is why this
    reduction takes no presence option of its own: it is the classified reduction,
    and the same one the classified row transform applies, so a document decoded
    here and one decoded there answer alike."""
    reduced, findings = reduce_declared_members_classified(occurrence_shape(declared), raw)
    return cast("dict[str, object] | None", reduced), findings


def _structure(document: Mapping[str, object], declared: _VoContainer) -> tuple[object, ...]:
    """One reduced document as its declaration-order member row: this
    occurrence's own leaves, then its nested occurrences, each at the position
    its declaration fixes.

    A member the document does not hold — and a leaf the reduction could not make
    available — reads ``ABSENT`` at its own position, which is how presence
    survives a row that cannot omit. No raw document mapping continues past here.
    """
    return (
        *(
            document[leaf.identity.name]
            if leaf.identity.name in document and document[leaf.identity.name] is not UNAVAILABLE
            else ABSENT
            for leaf in declared.attributes
        ),
        *(
            _structure_occurrence(document[nested.identity.path[-1]], nested)
            if nested.identity.path[-1] in document
            else ABSENT
            for nested in declared.value_objects
        ),
    )


def _translate_finding(finding: DocumentFinding, level: LevelContext) -> StoredDataIssueInput:
    path = _logical_path(finding.path)
    occurrence = next(
        (
            declared
            for declared in level.layout.occurrences
            if path and declared.identity.path[-1] == path[0]
        ),
        None,
    )
    attribute = next(
        (
            declared
            for declared in level.layout.attributes
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
