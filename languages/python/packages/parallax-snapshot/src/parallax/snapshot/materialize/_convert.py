from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from operator import itemgetter
from typing import Final, Protocol, cast

from parallax.core.base import (
    SQL_NULL,
    DocumentValue,
    PresentDocument,
    SqlNull,
    UnknownFamilyTag,
    admits_stored_scalar,
)
from parallax.core.document_codec import (
    UNAVAILABLE,
    DocumentFinding,
    DocumentFindingCode,
    DocumentPathSegment,
    MemberShape,
    Missing,
    Present,
    decode_occurrence_classified,
    occurrence_shape,
)
from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    MemberIdentity,
    Multiplicity,
    NestedValueObjectMetadata,
    PrimaryKey,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.core.wire import WireDecodingError, WireValue, decode_canonical_wire
from parallax.snapshot.materialize._evidence import freeze_evidence
from parallax.snapshot.materialize._identity import claim_identity
from parallax.snapshot.materialize._page import (
    ABSENT,
    LogicalKey,
    PageBuilder,
    StoredDataIssueCode,
    StoredDataIssueInput,
)
from parallax.snapshot.materialize._publication import SnapshotDecodingError
from parallax.snapshot.materialize._views import SourceLevel

__all__ = [
    "AttributeReadContract",
    "LevelContext",
    "SnapshotDecodingError",
    "build_positional_many",
    "build_positional_object",
    "convert_deferred",
]

_VoContainer = ValueObjectMetadata | NestedValueObjectMetadata


class AttributeReadContract(Protocol):
    """What one projected Attribute's compiled contract carries, read structurally
    because this scope may not import the compiler that decided it."""

    @property
    def attribute(self) -> AttributeMetadata: ...

    @property
    def result_key(self) -> str: ...

    @property
    def temporal_end(self) -> bool: ...

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
    projection's own Attribute beside the driver key and decode contract the
    statement chose for it, in ``layout.attributes`` order — the statement and
    the layout derive their Attribute sequences from one position view, so a
    contract is read at its Attribute's own position rather than looked up by
    identity — and is empty for an Entity this read projected no column for,
    whose Attributes each carry their own storage spelling. This keeps an
    encoded result such as ``payload_hex`` attached to physical ``payload``.

    ``projected_by_position`` is fixed here rather than per row and marks which
    of ``layout.occurrences`` this read carried.

    ``host_checked`` is the Attribute-position subset whose storage contract does
    not itself establish the managed value: encoded result cells and temporal
    ends. Native scalar Columns outside that subset are accepted exactly as the
    provider normalized them. Document-resident members are classified by their
    document codec before this seam and therefore do not enter this tuple.

    ``layout`` stays out of equality and hashing: ``concrete_entity`` already
    distinguishes every context it distinguishes — two layouts for one exact
    Entity are interchangeable — while comparing it would walk a whole shared
    layout tree and holding it in the hash would cost this context the
    hashability its scalar fields give it.
    """

    layout: EntityLayout = field(compare=False)
    concrete_entity: EntityIdentity = field(init=False)
    documents: tuple[ValueObjectMetadata, ...] = ()
    attribute_reads: tuple[AttributeReadContract, ...] = ()
    classified_members: frozenset[str] = field(default_factory=frozenset[str])
    result_ordinals: tuple[int | None, ...] = ()
    classifiers: tuple[
        Callable[[object], tuple[object, tuple[DocumentFinding, ...]]] | None, ...
    ] = ()
    document_member_names: tuple[str | None, ...] = ()
    direct_row: Callable[[tuple[object, ...]], object] | None = field(
        init=False, compare=False, repr=False
    )
    attribute_judgment_positions: tuple[int, ...] = field(init=False, compare=False, repr=False)
    projected_by_position: tuple[bool, ...] = field(init=False, compare=False, repr=False)
    host_checked: tuple[int, ...] = field(init=False, compare=False, repr=False)
    host_checked_set: frozenset[int] = field(init=False, compare=False, repr=False)
    identity_positions: tuple[int, ...] = field(init=False, compare=False, repr=False)
    identity_position_set: frozenset[int] = field(init=False, compare=False, repr=False)
    identity_passthrough: frozenset[int] = field(init=False, compare=False, repr=False)
    requires_state_reduction: bool = field(init=False, compare=False, repr=False)
    routing_members: tuple[MemberIdentity, ...] = field(default=(), compare=False, repr=False)
    prepared_routing_positions: tuple[int, ...] = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "concrete_entity", self.layout.concrete)
        projected = frozenset(member.storage.name for member in self.documents)
        object.__setattr__(
            self,
            "projected_by_position",
            tuple(occurrence.storage.name in projected for occurrence in self.layout.occurrences),
        )
        host_checked = tuple(
            position
            for position, attribute in enumerate(self.layout.attributes)
            if (
                self.attribute_reads
                and (
                    self.attribute_reads[position].encoded
                    or self.attribute_reads[position].temporal_end
                )
            )
            or (not self.attribute_reads and attribute.identity in self.layout.temporal_ends)
        )
        object.__setattr__(self, "host_checked", host_checked)
        object.__setattr__(self, "host_checked_set", frozenset(host_checked))
        identity_positions = tuple(
            dict.fromkeys((*self.layout.primary_key, *self.layout.temporal_starts))
        )
        object.__setattr__(self, "identity_positions", identity_positions)
        object.__setattr__(self, "identity_position_set", frozenset(identity_positions))
        correlations = tuple(
            position
            for member in self.routing_members
            if (position := self.layout.index_of.get(member)) is not None
            and position < self.layout.attribute_count
        )
        object.__setattr__(
            self,
            "prepared_routing_positions",
            tuple(dict.fromkeys((*identity_positions, *correlations))),
        )
        attribute_keys = tuple(
            attribute.storage.name
            if not self.attribute_reads
            else self.attribute_reads[position].result_key
            for position, attribute in enumerate(self.layout.attributes)
        )
        occurrence_keys = tuple(occurrence.storage.name for occurrence in self.layout.occurrences)
        if self.result_ordinals and len(self.result_ordinals) != len(
            (*attribute_keys, *occurrence_keys)
        ):
            raise ValueError("result ordinals must align with the level's members")
        if self.document_member_names and len(self.document_member_names) != len(
            (*attribute_keys, *occurrence_keys)
        ):
            raise ValueError("document member names must align with the level's members")
        direct_ordinals = tuple(ordinal for ordinal in self.result_ordinals if ordinal is not None)
        object.__setattr__(
            self,
            "direct_row",
            itemgetter(*direct_ordinals)
            if direct_ordinals and len(direct_ordinals) == len(self.result_ordinals)
            else None,
        )
        object.__setattr__(
            self,
            "identity_passthrough",
            frozenset(
                position
                for position in identity_positions
                if position not in self.host_checked_set
                and (*attribute_keys, *occurrence_keys)[position] not in self.classified_members
            ),
        )
        object.__setattr__(
            self,
            "attribute_judgment_positions",
            tuple(
                position
                for position in range(self.layout.attribute_count)
                if position not in self.identity_position_set
                and (
                    position in self.host_checked_set
                    or attribute_keys[position] in self.classified_members
                )
            ),
        )
        object.__setattr__(
            self,
            "requires_state_reduction",
            bool(self.classified_members)
            or bool(self.attribute_judgment_positions)
            or not self.identity_position_set.issubset(self.identity_passthrough)
            or any(self.projected_by_position),
        )

    def routing_positions(self, correlation_members: tuple[MemberIdentity, ...]) -> tuple[int, ...]:
        if correlation_members == self.routing_members:
            return self.prepared_routing_positions
        correlations = tuple(
            position
            for member in correlation_members
            if (position := self.layout.index_of.get(member)) is not None
            and position < self.layout.attribute_count
        )
        return tuple(dict.fromkeys((*self.identity_positions, *correlations)))


@dataclass(frozen=True, slots=True)
class _DeferredRowDecoder:
    witness: tuple[object, ...]
    level: LevelContext
    identity_values: tuple[object, ...]
    classifiable: int
    unknown_family_tag: UnknownFamilyTag | None

    def __call__(self) -> tuple[tuple[object, ...], tuple[StoredDataIssueInput, ...]]:
        values, findings, classified = _classify_payload(
            self.witness, self.level, self.classifiable
        )
        return _decode_row(
            values,
            self.level,
            self.identity_values,
            findings,
            self.unknown_family_tag,
            classified,
        )


def convert_deferred(
    witness: tuple[object, ...],
    level: LevelContext,
    builder: PageBuilder,
    *,
    source: SourceLevel,
    classifiable: int,
    unknown_family_tag: UnknownFamilyTag | None = None,
    correlation_members: tuple[AttributeIdentity, ...] = (),
) -> int:
    """Register one row's identity and exact witness in ``builder``, deferring
    payload judgment, and answer the projection index the builder assigned.

    ``witness`` is positional, laid out by ``level.layout``: every applicable
    Attribute, then every applicable top-level Value Object occurrence, with
    ``ABSENT`` wherever the read carried no value. ``source`` is the plan level
    the row was read at, a fact about where the projection lands rather than how
    the row decodes, so it travels beside ``level``. ``classifiable`` marks, one
    bit per position, the document members payload judgment classifies.
    """
    if not level.requires_state_reduction and unknown_family_tag is None:
        layout = level.layout
        primary_key = witness[layout.primary_key[0]]
        key = (
            None
            if primary_key is ABSENT
            else LogicalKey(
                layout.family,
                primary_key,
                tuple(witness[position] for position in layout.temporal_starts),
            )
        )
        return builder.add_claim(
            source,
            layout,
            key,
            witness,
            witness,
            (),
            witness,
        )
    claim = claim_identity(
        witness,
        level,
        unknown_family_tag=unknown_family_tag,
        correlation_members=correlation_members,
    )
    decoder = _DeferredRowDecoder(
        witness,
        level,
        claim.identity_values,
        classifiable,
        unknown_family_tag,
    )
    return builder.add_claim(
        source,
        level.layout,
        claim.key,
        claim.witness,
        claim.routing_values,
        claim.findings,
        decoder,
    )


def _classify_payload(
    witness: tuple[object, ...],
    level: LevelContext,
    classifiable: int,
) -> tuple[tuple[object, ...], tuple[DocumentFinding, ...], frozenset[str]]:
    if not level.classified_members:
        return witness, (), frozenset()
    values = list(witness)
    findings: list[DocumentFinding] = []
    full = classifiable == (1 << len(witness)) - 1
    classified: set[str] | None = None if full else set()
    for position, optional_classifier in enumerate(level.classifiers):
        if optional_classifier is None:
            continue
        raw = witness[position]
        if raw is ABSENT or not classifiable & (1 << position):
            continue
        value, member_findings = optional_classifier(raw)
        values[position] = value
        findings.extend(member_findings)
        if classified is not None:
            key = (
                (
                    level.layout.attributes[position].storage.name
                    if not level.attribute_reads
                    else level.attribute_reads[position].result_key
                )
                if position < level.layout.attribute_count
                else level.layout.occurrences[position - level.layout.attribute_count].storage.name
            )
            classified.add(key)
    return (
        tuple(values),
        tuple(findings),
        level.classified_members if classified is None else frozenset(classified),
    )


def _decode_row(
    raw_values: tuple[object, ...],
    level: LevelContext,
    identity_values: tuple[object, ...],
    findings: tuple[DocumentFinding, ...],
    unknown_family_tag: UnknownFamilyTag | None,
    classified_members: frozenset[str],
) -> tuple[tuple[object, ...], tuple[StoredDataIssueInput, ...]]:
    if (
        not level.requires_state_reduction
        and unknown_family_tag is None
        and not findings
        and not classified_members
    ):
        return raw_values, ()
    layout = level.layout
    issues: list[StoredDataIssueInput] = [
        _translate_finding(finding, level) for finding in findings
    ]
    if unknown_family_tag is not None:
        issues.append(
            StoredDataIssueInput(
                "stored-data-family-tag-unknown",
                level.concrete_entity,
                stored_value=freeze_evidence(unknown_family_tag.stored_value),
            )
        )
    members: list[object] | None = None
    reads = level.attribute_reads
    host_checked = level.host_checked_set
    identity_positions = level.identity_positions
    for position, value in zip(identity_positions, identity_values, strict=True):
        if value is not raw_values[position]:
            if members is None:
                members = list(raw_values)
            members[position] = value
    for position in level.attribute_judgment_positions:
        attribute = layout.attributes[position]
        contract = reads[position] if reads else None
        result_key = attribute.storage.name if contract is None else contract.result_key
        raw = raw_values[position]
        if raw is ABSENT:
            continue
        if result_key in classified_members:
            value = (
                ABSENT if raw is UNAVAILABLE or (raw is None and not attribute.nullable) else raw
            )
            if value is not raw_values[position]:
                if members is None:
                    members = list(raw_values)
                members[position] = value
            continue
        if position not in host_checked:
            continue
        try:
            value = (
                decode_canonical_wire(attribute.type, cast("WireValue", raw))
                if contract is not None and contract.encoded
                else raw
            )
        except WireDecodingError:
            value = raw
        admission = admits_stored_scalar(
            value,
            attribute.type,
            nullable=attribute.nullable,
            temporal_end=(
                attribute.identity in layout.temporal_ends
                if contract is None
                else contract.temporal_end
            ),
        )
        if not admission.admitted:
            issues.append(_attribute_issue(attribute, admission.rejected, level.concrete_entity))
        value = value if admission.admitted else ABSENT
        if value is not raw_values[position]:
            if members is None:
                members = list(raw_values)
            members[position] = value
    for occurrence_position, (occurrence, projected) in enumerate(
        zip(layout.occurrences, level.projected_by_position, strict=True),
        start=layout.attribute_count,
    ):
        if not projected:
            continue
        raw = raw_values[occurrence_position]
        if raw is ABSENT:
            continue
        value, occurrence_findings = _occurrence(
            raw,
            occurrence,
            outer_classified=occurrence.storage.name in classified_members,
        )
        issues.extend(
            _occurrence_issue(finding, occurrence, level.concrete_entity)
            for finding in occurrence_findings
        )
        if value is not raw_values[occurrence_position]:
            if members is None:
                members = list(raw_values)
            members[occurrence_position] = value
    return raw_values if members is None else tuple(members), tuple(issues)


def _attribute_issue(
    attribute: AttributeMetadata,
    value: object,
    entity: EntityIdentity,
) -> StoredDataIssueInput:
    """The classification one inadmissible stored scalar carries.

    A direct Entity Attribute is located by its identity alone under either
    Storage Layout, so the path is empty.
    """
    if value is None:
        code: StoredDataIssueCode = (
            "stored-data-primary-key-null"
            if isinstance(attribute.primary_key, PrimaryKey)
            else "stored-data-attribute-null"
        )
    else:
        code = (
            "stored-data-primary-key-undecodable"
            if isinstance(attribute.primary_key, PrimaryKey)
            else "stored-data-leaf-undecodable"
        )
    return StoredDataIssueInput(
        code, entity, attribute.identity, stored_value=freeze_evidence(value)
    )


def build_positional_object(shape: MemberShape, values: Iterable[object]) -> tuple[object, ...]:
    """Build one declaration-ordered member row from interpreted codec values."""
    return tuple(
        ABSENT if isinstance(value, Missing) or value is UNAVAILABLE else value
        for _member, value in zip(shape.members, values, strict=True)
    )


def build_positional_many(values: Iterable[object]) -> tuple[object, ...]:
    """Build one ordered Many result from completed positional elements."""
    return tuple(values)


def _occurrence(
    raw: object,
    declared: _VoContainer,
    *,
    outer_classified: bool = False,
) -> tuple[object, tuple[DocumentFinding, ...]]:
    """Build one top-level occurrence directly as positional member rows."""
    if outer_classified:
        return raw, ()
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
        build_object=build_positional_object,
        build_many=build_positional_many,
    )
    value = (
        classified.presence.value
        if isinstance(classified.presence, Present)
        else ()
        if declared.multiplicity is Multiplicity.MANY
        else None
    )
    return value, classified.findings


def _translate_finding(finding: DocumentFinding, level: LevelContext) -> StoredDataIssueInput:
    """One Entity-document finding as the issue it publishes.

    A finding that resolves to a direct Entity Attribute publishes the empty
    path its own column would: public translation is fixed by the logical Entity
    member rather than by the carrier the member was placed in.
    """
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
    return StoredDataIssueInput(
        code,
        level.concrete_entity,
        member,
        () if attribute is not None else finding.path,
        stored_value=freeze_evidence(finding.stored_value),
    )


def _occurrence_issue(
    finding: DocumentFinding, declared: _VoContainer, entity: EntityIdentity
) -> StoredDataIssueInput:
    path = _logical_path(finding.path)
    return StoredDataIssueInput(
        _stored_issue_code(finding),
        entity,
        _member_identity(declared, path),
        (declared.identity.path[-1], *finding.path),
        stored_value=freeze_evidence(finding.stored_value),
    )


_STORED_ISSUE_CODES: Final[Mapping[DocumentFindingCode, StoredDataIssueCode]] = {
    "required-member-absent": "stored-data-required-member-absent",
    "required-member-null": "stored-data-required-member-null",
    "one-wrong-kind": "stored-data-one-wrong-kind",
    "many-wrong-kind": "stored-data-many-wrong-kind",
    "leaf-undecodable": "stored-data-leaf-undecodable",
}
"""The `m-snapshot-read` issue code each codec-local finding is published as.

Both spellings are stated because only the right-hand side is core-authored:
composing one from the other would make the codec's own vocabulary load-bearing
for a corpus token it does not state (`core/spec/00-overview.md` *Representation
spelling*).
"""


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
    return _STORED_ISSUE_CODES[finding.code]


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
