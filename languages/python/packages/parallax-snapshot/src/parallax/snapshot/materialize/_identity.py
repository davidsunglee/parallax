"""Identity-first claims and exact payload witnesses for Snapshot occurrences."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, cast

from parallax.core.base import UnknownFamilyTag, admits_stored_scalar
from parallax.core.document_codec import UNAVAILABLE
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import EntityIdentity, MemberIdentity, PrimaryKey
from parallax.core.wire import WireDecodingError, WireValue, decode_canonical_wire
from parallax.snapshot.materialize._evidence import freeze_evidence
from parallax.snapshot.materialize._page import LogicalKey, StoredDataIssueInput

__all__ = ["IdentityClaim", "PayloadWitness", "claim_identity"]


class _AttributeRead(Protocol):
    @property
    def result_key(self) -> str: ...

    @property
    def temporal_end(self) -> bool: ...

    @property
    def encoded(self) -> bool: ...


class _Level(Protocol):
    @property
    def layout(self) -> EntityLayout: ...

    @property
    def attribute_reads(self) -> tuple[_AttributeRead, ...]: ...

    @property
    def projected_by_position(self) -> tuple[bool, ...]: ...


@dataclass(frozen=True, slots=True)
class PayloadWitness:
    """One occurrence's exact pre-judgment payload in member order."""

    concrete: EntityIdentity
    members: tuple[MemberIdentity, ...]
    values: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class IdentityClaim:
    """The identity facts available before the payload is judged."""

    key: LogicalKey | None
    witness: PayloadWitness
    identity_values: tuple[object, ...]
    payload_values: tuple[object, ...]
    routing_values: tuple[object, ...]
    findings: tuple[StoredDataIssueInput, ...] = ()


def claim_identity(
    values: Mapping[str, object],
    level: _Level,
    *,
    unknown_family_tag: UnknownFamilyTag | None = None,
    classified_members: frozenset[str] = frozenset(),
    witness_values: tuple[object, ...] | None = None,
    raw_member_values: tuple[object, ...] | None = None,
    correlation_members: tuple[MemberIdentity, ...] = (),
) -> IdentityClaim:
    """Build a logical-key claim and decoded routing values without judging payload."""
    layout = level.layout
    raw_values = (
        _raw_member_values(values, level) if raw_member_values is None else raw_member_values
    )
    identity_positions = tuple(dict.fromkeys((*layout.primary_key, *layout.temporal_starts)))
    correlation_positions = tuple(
        position
        for member in correlation_members
        if (position := layout.index_of.get(member)) is not None
        and position < layout.attribute_count
    )
    routing_positions = tuple(dict.fromkeys((*identity_positions, *correlation_positions)))
    decoded: dict[int, object] = {}
    routing = list(raw_values)
    findings: list[StoredDataIssueInput] = []
    for position in routing_positions:
        attribute = layout.attributes[position]
        raw = raw_values[position]
        if raw is ABSENT:
            decoded[position] = ABSENT
            continue
        value = _identity_value(raw, position, classified_members, level)
        admission = admits_stored_scalar(
            value,
            attribute.type,
            nullable=attribute.nullable,
            temporal_end=(
                level.attribute_reads[position].temporal_end
                if level.attribute_reads
                else attribute.identity in layout.temporal_ends
            ),
        )
        if not admission.admitted:
            if position in identity_positions:
                findings.append(
                    StoredDataIssueInput(
                        "stored-data-primary-key-null"
                        if value is None and isinstance(attribute.primary_key, PrimaryKey)
                        else "stored-data-primary-key-undecodable"
                        if isinstance(attribute.primary_key, PrimaryKey)
                        else "stored-data-attribute-null"
                        if value is None
                        else "stored-data-leaf-undecodable",
                        layout.concrete,
                        attribute.identity,
                        stored_value=freeze_evidence(admission.rejected),
                    )
                )
            decoded[position] = ABSENT
        else:
            decoded[position] = value
        routing[position] = decoded[position]

    witness = PayloadWitness(
        layout.concrete,
        layout.members,
        raw_values if witness_values is None else witness_values,
    )
    identity_values = tuple(decoded[position] for position in identity_positions)
    common = (witness, identity_values, raw_values, tuple(routing), tuple(findings))
    if (
        unknown_family_tag is not None
        or any(issue.code.startswith("stored-data-primary-key-") for issue in findings)
        or any(decoded[position] is ABSENT for position in layout.primary_key)
    ):
        return IdentityClaim(None, *common)
    return IdentityClaim(
        LogicalKey(
            layout.family,
            _key_value(layout, decoded),
            tuple(decoded[position] for position in layout.temporal_starts),
        ),
        *common,
    )


def _raw_member_values(values_by_key: Mapping[str, object], level: _Level) -> tuple[object, ...]:
    layout = level.layout
    values: list[object] = []
    for position, attribute in enumerate(layout.attributes):
        contract = level.attribute_reads[position] if level.attribute_reads else None
        key = attribute.storage.name if contract is None else contract.result_key
        values.append(values_by_key.get(key, ABSENT))
    for occurrence, projected in zip(layout.occurrences, level.projected_by_position, strict=True):
        values.append(values_by_key.get(occurrence.storage.name) if projected else ABSENT)
    return tuple(values)


def _identity_value(
    raw: object,
    position: int,
    classified_members: frozenset[str],
    level: _Level,
) -> object:
    if raw is ABSENT:  # pragma: no cover - claim_identity handles absent positions before dispatch
        return raw
    attribute = level.layout.attributes[position]
    contract = level.attribute_reads[position] if level.attribute_reads else None
    key = attribute.storage.name if contract is None else contract.result_key
    if key in classified_members:
        return ABSENT if raw is UNAVAILABLE else raw
    if contract is None or not contract.encoded or raw is None:
        return raw
    try:
        return decode_canonical_wire(attribute.type, cast("WireValue", raw))
    except WireDecodingError:
        return raw


def _key_value(layout: EntityLayout, decoded: dict[int, object]) -> object:
    values = tuple(decoded[position] for position in layout.primary_key)
    return values[0] if len(values) == 1 else values
