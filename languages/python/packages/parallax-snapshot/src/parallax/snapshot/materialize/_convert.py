from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import InitVar, dataclass, field
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
    AttributeMetadata,
    EntityIdentity,
    MemberIdentity,
    Multiplicity,
    OccurrenceMetadata,
    PrimaryKey,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.core.wire import WireDecodingError, WireValue, decode_canonical_wire
from parallax.snapshot.materialize._evidence import freeze_evidence
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
    "BoundLevel",
    "SnapshotDecodingError",
    "build_positional_many",
    "build_positional_object",
    "register_reduced_row",
]


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


@dataclass(frozen=True, slots=True, eq=False)
class BoundLevel:
    """What every row a prepared read resolves to one exact Entity converts under.

    ``layout`` is that Entity's model-owned member layout. ``attribute_reads``
    carries the statement's contract for each of its Attributes in
    ``layout.attributes`` order, read at the Attribute's own position, and is
    empty for an Entity the read projected no column for, whose Attributes each
    carry their own storage spelling. The remaining member sources align with
    ``layout.members``.

    Only encoded result cells and temporal ends are host-checked: their storage
    contract does not itself establish the managed value. Native scalar Columns
    are accepted exactly as the provider normalized them, and document-resident
    members are classified by their document codec rather than admitted.

    The judgment selections are fixed here, once per bound read. A reduced row's
    host-checked identity positions, then its host-checked non-identity
    correlation positions, are judged when the row is claimed, so its logical
    key and routing values are ready for page assembly. ``payload_positions``
    are processed only when a Root View needs the row's state; the correlations
    among them reuse the verdict formed at the claim rather than being judged
    again. Correlations and payload positions are both in attribute order, which
    is what places each captured correlation finding at its own payload position
    without a lookup.
    """

    layout: EntityLayout
    documents: InitVar[tuple[ValueObjectMetadata, ...]]
    attribute_reads: tuple[AttributeReadContract, ...]
    classified_members: frozenset[str]
    result_keys: tuple[str, ...]
    result_ordinals: tuple[int | None, ...]
    classifiers: tuple[Callable[[object], tuple[object, tuple[DocumentFinding, ...]]] | None, ...]
    document_member_names: tuple[str | None, ...]
    correlation_members: InitVar[tuple[MemberIdentity, ...]]
    concrete_entity: EntityIdentity = field(init=False)
    projected_by_position: tuple[bool, ...] = field(init=False)
    direct_row: Callable[[tuple[object, ...]], object] | None = field(init=False)
    every_member_present: int = field(init=False)
    temporal_start_values: Callable[[tuple[object, ...]], tuple[object, ...]] = field(init=False)
    eager_identity_positions: tuple[int, ...] = field(init=False)
    eager_correlation_positions: tuple[int, ...] = field(init=False)
    payload_positions: tuple[int, ...] = field(init=False)
    requires_state_reduction: bool = field(init=False)

    def __post_init__(
        self,
        documents: tuple[ValueObjectMetadata, ...],
        correlation_members: tuple[MemberIdentity, ...],
    ) -> None:
        layout = self.layout
        reads = self.attribute_reads
        member_count = len(layout.members)
        if (  # pragma: no cover - bind derives every member source from one key sequence
            len(self.result_keys) != member_count
            or len(self.result_ordinals) != member_count
            or len(self.classifiers) != member_count
            or len(self.document_member_names) != member_count
        ):
            raise ValueError("a bound level's member sources must align with its members")
        object.__setattr__(self, "concrete_entity", layout.concrete)
        projected = frozenset(member.storage.name for member in documents)
        projected_by_position = tuple(
            occurrence.storage.name in projected for occurrence in layout.occurrences
        )
        object.__setattr__(self, "projected_by_position", projected_by_position)
        direct_ordinals = tuple(ordinal for ordinal in self.result_ordinals if ordinal is not None)
        object.__setattr__(
            self,
            "direct_row",
            itemgetter(*direct_ordinals)
            if direct_ordinals and len(direct_ordinals) == member_count
            else None,
        )
        object.__setattr__(self, "every_member_present", (1 << member_count) - 1)
        object.__setattr__(self, "temporal_start_values", _tuple_getter(layout.temporal_starts))
        host_checked = frozenset(
            position
            for position, attribute in enumerate(layout.attributes)
            if (
                reads[position].encoded or reads[position].temporal_end
                if reads
                else attribute.identity in layout.temporal_ends
            )
        )
        identity = frozenset((*layout.primary_key, *layout.temporal_starts))
        eager_identity = tuple(
            position
            for position in dict.fromkeys((*layout.primary_key, *layout.temporal_starts))
            if position in host_checked
        )
        object.__setattr__(self, "eager_identity_positions", eager_identity)
        object.__setattr__(
            self,
            "eager_correlation_positions",
            tuple(
                sorted(
                    {
                        position
                        for member in correlation_members
                        if (position := layout.index_of.get(member)) in host_checked
                        and position not in identity
                    }
                )
            ),
        )
        payload = tuple(
            position
            for position in range(layout.attribute_count)
            if position not in identity
            and (position in host_checked or self.classifiers[position] is not None)
        )
        object.__setattr__(self, "payload_positions", payload)
        object.__setattr__(
            self,
            "requires_state_reduction",
            bool(self.classified_members)
            or bool(payload)
            or bool(eager_identity)
            or any(projected_by_position),
        )

    def decode_payload(
        self,
        witness: tuple[object, ...],
        routed_values: tuple[object, ...],
        classifiable: int | None,
        correlation_findings: tuple[StoredDataIssueInput, ...],
        unknown_family_tag: UnknownFamilyTag | None,
    ) -> tuple[tuple[object, ...], tuple[StoredDataIssueInput, ...]]:
        """Judge the payload of one reduced row claimed under this level, from the
        inputs its Page retained for it, answering its member row and findings."""
        values, findings, classified = _classify_payload(
            witness,
            self,
            self.every_member_present if classifiable is None else classifiable,
        )
        return _decode_payload(
            values,
            self,
            routed_values,
            correlation_findings,
            findings,
            unknown_family_tag,
            classified,
        )


def register_reduced_row(
    witness: tuple[object, ...],
    level: BoundLevel,
    builder: PageBuilder,
    *,
    source: SourceLevel,
    classifiable: int,
    unknown_family_tag: UnknownFamilyTag | None,
) -> int:
    """Claim one reduced row's identity now, register it in ``builder`` with its
    payload deferred to the Root View that needs it, and answer the projection
    index the builder assigned.

    ``witness`` is positional, laid out by ``level.layout``, with ``ABSENT``
    wherever the read carried no value. ``classifiable`` marks, one bit per
    position, the members the row carried for document classification.

    The claim keeps the raw witness for comparing claimants and classifying the
    payload, beside the routed values page assembly reads: the witness with
    each judged identity and correlation cell decoded, or ``ABSENT`` where
    rejected. Identity findings join the Page's identity issues; correlation
    findings wait for the payload judgment, which places them at their own
    positions.
    """
    routed, identity_findings = _judge(level.eager_identity_positions, witness, level, None, None)
    routed, correlation_findings = _judge(
        level.eager_correlation_positions, witness, level, routed, None
    )
    routed_values = witness if routed is None else tuple(routed)
    layout = level.layout
    key = (
        None
        if unknown_family_tag is not None
        or any(routed_values[position] is ABSENT for position in layout.primary_key)
        else LogicalKey(
            layout.family,
            routed_values[layout.primary_key[0]],
            level.temporal_start_values(routed_values),
        )
    )
    projection = builder.add_claim(
        source,
        layout,
        key,
        witness,
        routed_values,
        () if identity_findings is None else tuple(identity_findings),
        level,
    )
    partial = None if classifiable == level.every_member_present else classifiable
    if partial is not None or correlation_findings or unknown_family_tag is not None:
        builder.add_payload_inputs(
            projection,
            partial,
            () if correlation_findings is None else tuple(correlation_findings),
            unknown_family_tag,
        )
    return projection


def _tuple_getter(
    positions: tuple[int, ...],
) -> Callable[[tuple[object, ...]], tuple[object, ...]]:
    # `itemgetter` answers a bare value for one position and refuses none.
    if not positions:
        return _no_values
    if len(positions) == 1:
        (position,) = positions
        return lambda values: (values[position],)
    return cast("Callable[[tuple[object, ...]], tuple[object, ...]]", itemgetter(*positions))


def _no_values(_values: tuple[object, ...]) -> tuple[object, ...]:
    return ()


def _classify_payload(
    witness: tuple[object, ...],
    level: BoundLevel,
    classifiable: int,
) -> tuple[tuple[object, ...], tuple[DocumentFinding, ...], int]:
    """Classify each document member the row carried, answering the classified
    values, the codec's findings, and the classified positions, one bit each."""
    if not level.classified_members:
        return witness, (), 0
    values = list(witness)
    findings: list[DocumentFinding] = []
    classified = 0
    for position, optional_classifier in enumerate(level.classifiers):
        if optional_classifier is None:
            continue
        raw = witness[position]
        if raw is ABSENT or not classifiable & (1 << position):
            continue
        value, member_findings = optional_classifier(raw)
        values[position] = value
        findings.extend(member_findings)
        classified |= 1 << position
    return tuple(values), tuple(findings), classified


def _decode_payload(
    values: tuple[object, ...],
    level: BoundLevel,
    routed_values: tuple[object, ...],
    correlation_findings: tuple[StoredDataIssueInput, ...],
    findings: tuple[DocumentFinding, ...],
    unknown_family_tag: UnknownFamilyTag | None,
    classified: int,
) -> tuple[tuple[object, ...], tuple[StoredDataIssueInput, ...]]:
    issues: list[StoredDataIssueInput] | None = (
        [_translate_finding(finding, level) for finding in findings] if findings else None
    )
    if unknown_family_tag is not None:
        if issues is None:
            issues = []
        issues.append(
            StoredDataIssueInput(
                "stored-data-family-tag-unknown",
                level.concrete_entity,
                stored_value=freeze_evidence(unknown_family_tag.stored_value),
            )
        )
    members: list[object] | None = None
    for position in level.eager_identity_positions:
        if routed_values[position] is not values[position]:
            if members is None:
                members = list(values)
            members[position] = routed_values[position]
    members, issues = _judge(
        level.payload_positions,
        values,
        level,
        members,
        issues,
        routed_values=routed_values,
        captured=correlation_findings,
        classified=classified,
    )
    members, issues = _decode_occurrences(values, level, classified, members, issues)
    return (
        values if members is None else tuple(members),
        () if issues is None else tuple(issues),
    )


def _decode_occurrences(
    values: tuple[object, ...],
    level: BoundLevel,
    classified: int,
    members: list[object] | None,
    issues: list[StoredDataIssueInput] | None,
) -> tuple[list[object] | None, list[StoredDataIssueInput] | None]:
    layout = level.layout
    for occurrence_position, (occurrence, projected) in enumerate(
        zip(layout.occurrences, level.projected_by_position, strict=True),
        start=layout.attribute_count,
    ):
        if not projected or (raw := values[occurrence_position]) is ABSENT:
            continue
        value, occurrence_findings = _occurrence(
            raw,
            occurrence,
            outer_classified=bool(classified & (1 << occurrence_position)),
        )
        if occurrence_findings:
            if issues is None:
                issues = []
            issues.extend(
                _occurrence_issue(finding, occurrence, level.concrete_entity)
                for finding in occurrence_findings
            )
        if value is not raw:
            if members is None:
                members = list(values)
            members[occurrence_position] = value
    return members, issues


# One branch per verdict source. It runs per selected cell per row, so the branches
# stay inline rather than behind a per-cell call.
def _judge(  # noqa: C901
    selection: tuple[int, ...],
    values: tuple[object, ...],
    level: BoundLevel,
    members: list[object] | None,
    issues: list[StoredDataIssueInput] | None,
    *,
    routed_values: tuple[object, ...] = (),
    captured: tuple[StoredDataIssueInput, ...] = (),
    classified: int = 0,
) -> tuple[list[object] | None, list[StoredDataIssueInput] | None]:
    """Judge ``values`` at each ``selection`` position, answering ``members`` with
    every replaced value written into it, copied from ``values`` on the first
    replacement, and ``issues`` with each new finding appended.

    Given ``routed_values``, the level's eager correlation positions reuse the
    value their claim routed and the finding it ``captured``, in attribute order;
    a ``classified`` position takes its document codec's verdict; every other
    position is a host-checked stored scalar, decoded and admitted here.
    """
    layout = level.layout
    reads = level.attribute_reads
    reused = level.eager_correlation_positions if routed_values else ()
    next_reused = 0
    next_captured = 0
    for position in selection:
        attribute = layout.attributes[position]
        raw = values[position]
        if next_reused < len(reused) and reused[next_reused] == position:
            next_reused += 1
            value = routed_values[position]
            if (
                next_captured < len(captured)
                and captured[next_captured].member == attribute.identity
            ):
                if issues is None:
                    issues = []
                issues.append(captured[next_captured])
                next_captured += 1
        elif raw is ABSENT:
            continue
        elif classified & (1 << position):
            value = (
                ABSENT if raw is UNAVAILABLE or (raw is None and not attribute.nullable) else raw
            )
        else:
            contract = reads[position] if reads else None
            value = raw
            if raw is not None and contract is not None and contract.encoded:
                try:
                    value = decode_canonical_wire(attribute.type, cast("WireValue", raw))
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
                if issues is None:
                    issues = []
                issues.append(
                    _attribute_issue(attribute, admission.rejected, level.concrete_entity)
                )
                value = ABSENT
        if value is not raw:
            if members is None:
                members = list(values)
            members[position] = value
    return members, issues


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
    declared: OccurrenceMetadata,
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


def _translate_finding(finding: DocumentFinding, level: BoundLevel) -> StoredDataIssueInput:
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
    finding: DocumentFinding, declared: OccurrenceMetadata, entity: EntityIdentity
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
    declared: OccurrenceMetadata, path: tuple[str, ...]
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
