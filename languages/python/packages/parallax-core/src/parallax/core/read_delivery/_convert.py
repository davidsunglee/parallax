from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import InitVar, dataclass, field
from operator import itemgetter
from typing import Final, cast

from parallax.core.base import (
    SQL_NULL,
    DocumentValue,
    PresentDocument,
    SqlNull,
    UnknownFamilyTag,
    check_stored_scalar,
)
from parallax.core.deep_fetch import ResolvedReadProjection
from parallax.core.document_codec import (
    UNAVAILABLE,
    DecodeOutput,
    DocumentFinding,
    DocumentFindingCode,
    DocumentPathSegment,
    MemberDecodePlan,
    MemberShape,
    located_occurrence,
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
)
from parallax.core.read_delivery._evidence import freeze_evidence
from parallax.core.read_delivery._page import (
    ABSENT,
    StoredDataIssueCode,
    StoredDataIssueInput,
)
from parallax.core.wire import WireDecodingError, WireValue, decode_canonical_wire

__all__ = [
    "POSITIONAL_OUTPUT",
    "EntityReadMapping",
    "judge_positions",
    "occurrence_completion",
]

type _Classifier = Callable[[object], tuple[object, tuple[DocumentFinding, ...]]]


def _positional_object(_shape: MemberShape, values: list[object]) -> tuple[object, ...]:
    return tuple(values)


POSITIONAL_OUTPUT: Final = DecodeOutput(
    _positional_object, tuple, missing=ABSENT, unavailable=ABSENT
)
"""Each Value Object a declaration-ordered member row, ``ABSENT`` where it holds
no value, and each Many a tuple of them."""


@dataclass(frozen=True, slots=True, eq=False)
class EntityReadMapping:
    """What every row a compiled read resolves to one exact Entity converts under.

    ``layout`` is that Entity's model-owned member layout, and every member
    source aligns with ``layout.members``: the folded driver-row cell a member
    is read from, its prepared document classifier, and its member name in the
    row's unwrapped shared document. A member with neither a cell nor a
    document location is not carried. ``encoded_positions`` marks, one bit per
    position, the Attributes whose cell arrives in its canonical Wire spelling.

    Only encoded result cells and temporal ends are host-checked: their storage
    contract does not itself establish the managed value. Native scalar Columns
    are accepted exactly as the provider normalized them, and document members
    are classified by their document codec rather than admitted.

    The judgment selections are fixed here, once per bound read. A reduced row's
    host-checked identity positions, then its host-checked non-identity
    correlation positions, are judged when the row is recorded, so its row key
    and routing values are ready for page assembly. ``payload_positions`` are
    processed when the row is recorded on a level that records each row key at
    most once, and otherwise only when a Root View needs the row's state; the
    correlations among them reuse the verdict formed for routing rather than
    being judged again. Correlations and payload positions are both in attribute
    order, which is what places each captured correlation finding at its own
    payload position without a lookup. ``judges_scalars_only`` marks a mapping
    whose payload is host-checked scalars alone, with no document member to
    classify and no requested occurrence.

    Everything a row's judgment consults per position is fixed here too: each
    Attribute by position, the temporal ends one bit each, the positions
    holding a classifier, and the decode plan of each requested occurrence,
    which judges an occurrence its classifier did not already classify.
    """

    layout: EntityLayout
    projection: InitVar[ResolvedReadProjection]
    result_ordinals: tuple[int | None, ...]
    classifiers: tuple[Callable[[object], tuple[object, tuple[DocumentFinding, ...]]] | None, ...]
    document_member_names: tuple[str | None, ...]
    encoded_positions: int
    correlation_members: InitVar[tuple[MemberIdentity, ...]]
    concrete_entity: EntityIdentity = field(init=False)
    classifies: bool = field(init=False)
    projected_by_position: tuple[bool, ...] = field(init=False)
    direct_row: Callable[[tuple[object, ...]], object] | None = field(init=False)
    every_member_present: int = field(init=False)
    temporal_start_values: Callable[[tuple[object, ...]], tuple[object, ...]] = field(init=False)
    eager_identity_positions: tuple[int, ...] = field(init=False)
    eager_correlation_positions: tuple[int, ...] = field(init=False)
    payload_positions: tuple[int, ...] = field(init=False)
    requires_state_reduction: bool = field(init=False)
    judges_scalars_only: bool = field(init=False)
    attribute_positions: int = field(init=False)
    attributes: tuple[AttributeMetadata, ...] = field(init=False)
    temporal_end_positions: int = field(init=False)
    classifier_positions: tuple[tuple[int, _Classifier], ...] = field(init=False)
    occurrence_plans: tuple[MemberDecodePlan | None, ...] = field(init=False)
    projected_occurrences: int = field(init=False)

    def __post_init__(
        self,
        projection: ResolvedReadProjection,
        correlation_members: tuple[MemberIdentity, ...],
    ) -> None:
        layout = self.layout
        member_count = len(layout.members)
        if (  # pragma: no cover - bind derives every member source from one source tuple
            len(self.result_ordinals) != member_count
            or len(self.classifiers) != member_count
            or len(self.document_member_names) != member_count
        ):
            raise ValueError("an entity read mapping's member sources must align with its members")
        object.__setattr__(self, "concrete_entity", layout.concrete)
        classifies = any(classifier is not None for classifier in self.classifiers)
        object.__setattr__(self, "classifies", classifies)
        projected_by_position = tuple(
            projection.includes_value_object(occurrence.identity)
            for occurrence in layout.occurrences
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
            if self.encoded_positions >> position & 1 or attribute.identity in layout.temporal_ends
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
            classifies or bool(payload) or bool(eager_identity) or any(projected_by_position),
        )
        object.__setattr__(
            self, "judges_scalars_only", not classifies and not any(projected_by_position)
        )
        object.__setattr__(self, "attribute_positions", (1 << layout.attribute_count) - 1)
        # The member bindings themselves, which the Attributes open: read only at
        # Attribute positions, they cost a mapping no copy.
        object.__setattr__(
            self,
            "attributes",
            cast("tuple[AttributeMetadata, ...]", layout.member_selection.bindings),
        )
        object.__setattr__(
            self,
            "temporal_end_positions",
            sum(
                1 << position
                for position, attribute in enumerate(layout.attributes)
                if attribute.identity in layout.temporal_ends
            ),
        )
        object.__setattr__(
            self,
            "classifier_positions",
            tuple(
                (position, classifier)
                for position, classifier in enumerate(self.classifiers)
                if classifier is not None
            ),
        )
        object.__setattr__(
            self,
            "occurrence_plans",
            tuple(
                _occurrence_plan(occurrence) if projected else None
                for occurrence, projected in zip(
                    layout.occurrences, projected_by_position, strict=True
                )
            ),
        )
        object.__setattr__(
            self,
            "projected_occurrences",
            sum(
                1 << position
                for position, projected in enumerate(
                    projected_by_position, start=layout.attribute_count
                )
                if projected
            ),
        )

    def decode_payload(
        self,
        stored_values: tuple[object, ...],
        routed_values: tuple[object, ...],
        classifiable: int | None,
        correlation_findings: tuple[StoredDataIssueInput, ...],
        unknown_family_tag: UnknownFamilyTag | None,
        *,
        occurrences: bool = True,
    ) -> tuple[tuple[object, ...], tuple[StoredDataIssueInput, ...]]:
        """Judge the payload of one reduced row recorded under this mapping, from
        the inputs its Page retained for it, answering its member row and findings.

        Without ``occurrences`` only the row's Attributes are judged: each Value
        Object occurrence the row carried keeps the input its classification
        takes, which an :func:`occurrence_completion` judges later."""
        carried = self.every_member_present if classifiable is None else classifiable
        if not occurrences:
            carried &= self.attribute_positions
        members: list[object] | None = None
        for position in self.eager_identity_positions:
            if routed_values[position] is not stored_values[position]:
                if members is None:
                    members = list(stored_values)
                members[position] = routed_values[position]
        members, issues, classified = _classified(self, stored_values, carried, members)
        values = stored_values if members is None else members
        if unknown_family_tag is not None:
            issues = [
                *(() if issues is None else issues),
                StoredDataIssueInput(
                    "stored-data-family-tag-unknown",
                    self.concrete_entity,
                    stored_value=freeze_evidence(unknown_family_tag.stored_value),
                ),
            ]
        members, issues = judge_positions(
            self.payload_positions,
            values,
            self,
            members,
            issues,
            routed_values=routed_values,
            captured=correlation_findings,
            classified=classified,
        )
        if not occurrences:
            members = _pending_occurrences(values, self, members)
        elif self.projected_occurrences & ~classified:
            members, issues = _decode_occurrences(values, self, classified, members, issues)
        return (
            stored_values if members is None else tuple(members),
            () if issues is None else tuple(issues),
        )


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


def _classified(
    mapping: EntityReadMapping,
    stored_values: tuple[object, ...],
    carried: int,
    members: list[object] | None,
) -> tuple[list[object] | None, list[StoredDataIssueInput] | None, int]:
    """Classify each document member a row carried: ``members``, copied from
    ``stored_values`` if still ``None``, with each classified value written
    in, the codec's findings as issues, and the classified positions, one bit
    each."""
    issues: list[StoredDataIssueInput] | None = None
    classified = 0
    for position, classifier in mapping.classifier_positions:
        raw = stored_values[position]
        if raw is ABSENT or not carried >> position & 1:
            continue
        if members is None:
            members = list(stored_values)
        members[position], findings = classifier(raw)
        if findings:
            if issues is None:
                issues = []
            issues.extend([_translate_finding(finding, mapping) for finding in findings])
        classified |= 1 << position
    return members, issues, classified


def _occurrence_plan(declared: OccurrenceMetadata) -> MemberDecodePlan:
    """The plan judging ``declared``'s stored value, building positional member
    rows and locating findings relative to the occurrence."""
    return MemberDecodePlan(declared.definition, POSITIONAL_OUTPUT)


def _decode_occurrences(
    values: tuple[object, ...] | list[object],
    mapping: EntityReadMapping,
    classified: int,
    members: list[object] | None,
    issues: list[StoredDataIssueInput] | None,
) -> tuple[list[object] | None, list[StoredDataIssueInput] | None]:
    layout = mapping.layout
    for position, plan in enumerate(mapping.occurrence_plans, start=layout.attribute_count):
        if plan is None or classified >> position & 1 or (raw := values[position]) is ABSENT:
            continue
        value, occurrence_findings = _occurrence(raw, plan)
        if occurrence_findings:
            if issues is None:
                issues = []
            occurrence = layout.occurrences[position - layout.attribute_count]
            issues.extend(
                _occurrence_issue(finding, occurrence, mapping.concrete_entity)
                for finding in occurrence_findings
            )
        if value is not raw:
            if members is None:
                members = list(values)
            members[position] = value
    return members, issues


# One branch per verdict source. It runs per selected cell per row, so the branches
# stay inline rather than behind a per-cell call.
def judge_positions(  # noqa: C901
    selection: tuple[int, ...],
    values: tuple[object, ...] | list[object],
    mapping: EntityReadMapping,
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

    Given ``routed_values``, the mapping's eager correlation positions reuse the
    value their recording routed and the finding it ``captured``, in attribute order;
    a ``classified`` position takes its document codec's verdict; every other
    position is a host-checked stored scalar, decoded and admitted here.
    """
    attributes = mapping.attributes
    encoded = mapping.encoded_positions
    temporal_ends = mapping.temporal_end_positions
    reused = mapping.eager_correlation_positions if routed_values else ()
    next_reused = 0
    next_captured = 0
    for position in selection:
        attribute = attributes[position]
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
            value = raw
            if raw is not None and encoded >> position & 1:
                try:
                    value = decode_canonical_wire(attribute.type, cast("WireValue", raw))
                except WireDecodingError:
                    value = raw
            verdict = check_stored_scalar(
                value,
                attribute.type,
                nullable=attribute.nullable,
                temporal_end=bool(temporal_ends >> position & 1),
            )
            if not verdict.accepted:
                if issues is None:
                    issues = []
                issues.append(
                    _attribute_issue(attribute, verdict.rejected_value, mapping.concrete_entity)
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


def _pending_occurrences(
    values: tuple[object, ...] | list[object],
    mapping: EntityReadMapping,
    members: list[object] | None,
) -> list[object] | None:
    """Each Value Object occurrence of a whole read's row an Attribute-only
    judgment leaves, as the input its own classification takes, SQL null and a
    present JSON null kept apart and the contents unexamined: its location in
    the shared Structured Column tagged as the codec tags it, or the Document
    Read its own Column already is."""
    for position in range(mapping.layout.attribute_count, len(values)):
        raw = values[position]
        pending = (
            _occurrence_input(raw)
            if mapping.document_member_names[position] is None
            else located_occurrence(raw)
        )
        if pending is raw:
            continue
        if members is None:
            members = list(values)
        members[position] = pending
    return members


def occurrence_completion(
    layout: EntityLayout,
) -> Callable[[tuple[object, ...]], tuple[tuple[object, ...], tuple[StoredDataIssueInput, ...]]]:
    """Judge the Value Object occurrences an Attribute-only judgment left
    pending in a row of ``layout``'s Entity (:meth:`EntityReadMapping.decode_payload`),
    answering the completed member row and the occurrences' findings in member
    order.

    Each occurrence takes the classification an ordinary read gives it, so the
    completed row and its findings are the ones an ordinary read judges from
    the same stored state; the Attribute prefix is not judged again."""
    occurrences = tuple(
        (position, declared, _occurrence_plan(declared))
        for position, declared in enumerate(layout.occurrences, start=layout.attribute_count)
    )
    entity = layout.concrete

    def complete(
        row: tuple[object, ...],
    ) -> tuple[tuple[object, ...], tuple[StoredDataIssueInput, ...]]:
        members = list(row)
        issues: list[StoredDataIssueInput] = []
        for position, declared, plan in occurrences:
            members[position], findings = _occurrence(row[position], plan)
            issues.extend(_occurrence_issue(finding, declared, entity) for finding in findings)
        return tuple(members), tuple(issues)

    return complete


def _occurrence_input(raw: object) -> SqlNull | PresentDocument:
    """The input an occurrence stored in a Column of its own is classified
    from: the driver's ``None`` is SQL null."""
    return (
        raw
        if isinstance(raw, (SqlNull, PresentDocument))
        else SQL_NULL
        if raw is None
        else PresentDocument(cast("DocumentValue", raw))
    )


def _occurrence(raw: object, plan: MemberDecodePlan) -> tuple[object, tuple[DocumentFinding, ...]]:
    """One top-level occurrence built as positional member rows, its findings
    relative to the occurrence."""
    return plan.value(_occurrence_input(raw))


def _translate_finding(
    finding: DocumentFinding, mapping: EntityReadMapping
) -> StoredDataIssueInput:
    """One Entity-document finding as the issue it publishes.

    A finding that resolves to a single-valued Entity Attribute publishes the
    empty path its own column would, and one inside a scalar collection keeps
    the collection's own logical path, element index included: public
    translation is fixed by the logical Entity member rather than by the carrier
    the member was placed in.
    """
    path = _logical_path(finding.path)
    occurrence = next(
        (
            declared
            for declared in mapping.layout.occurrences
            if path and declared.identity.path[-1] == path[0]
        ),
        None,
    )
    attribute = next(
        (
            declared
            for declared in mapping.layout.attributes
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
        mapping.concrete_entity,
        member,
        ()
        if attribute is not None and attribute.multiplicity is Multiplicity.ONE
        else finding.path,
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
"""The `m-read-delivery` issue code each codec-local finding is published as.

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
