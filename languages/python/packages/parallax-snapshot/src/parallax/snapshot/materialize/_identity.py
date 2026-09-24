from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import NamedTuple, Protocol, cast

from parallax.core.base import UnknownFamilyTag, admits_stored_scalar
from parallax.core.document_codec import UNAVAILABLE
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import MemberIdentity, PrimaryKey
from parallax.core.wire import WireDecodingError, WireValue, decode_canonical_wire
from parallax.snapshot.materialize._evidence import freeze_evidence
from parallax.snapshot.materialize._page import LogicalKey, StoredDataIssueInput

__all__ = ["IdentityClaim", "claim_identity"]


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

    @property
    def host_checked(self) -> tuple[int, ...]: ...

    @property
    def host_checked_set(self) -> frozenset[int]: ...

    @property
    def identity_positions(self) -> tuple[int, ...]: ...

    @property
    def identity_passthrough(self) -> frozenset[int]: ...

    def routing_positions(
        self, correlation_members: tuple[MemberIdentity, ...]
    ) -> tuple[int, ...]: ...


class IdentityClaim(NamedTuple):
    """The identity facts available before the payload is judged."""

    key: LogicalKey | None
    witness: tuple[object, ...]
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
    identity_positions = level.identity_positions
    routing_positions = level.routing_positions(correlation_members)
    host_checked = level.host_checked_set
    witness = raw_values if witness_values is None else witness_values
    if unknown_family_tag is None and host_checked.isdisjoint(routing_positions):
        identity_values = _values_at(raw_values, identity_positions)
        key = (
            None
            if any(raw_values[position] is ABSENT for position in layout.primary_key)
            else LogicalKey(
                layout.family,
                _key_value(layout, raw_values),
                _values_at(raw_values, layout.temporal_starts),
            )
        )
        return IdentityClaim(key, witness, identity_values, raw_values, raw_values)

    routing: list[object] | None = None
    findings: list[StoredDataIssueInput] = []
    for position in routing_positions:
        attribute = layout.attributes[position]
        raw = raw_values[position]
        if raw is ABSENT:
            continue
        if position in level.identity_passthrough:
            continue
        if position not in host_checked:
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
            decoded = ABSENT
        else:
            decoded = value
        if decoded is not raw:
            routing = list(raw_values) if routing is None else routing
            routing[position] = decoded

    routed: Sequence[object] = raw_values if routing is None else routing
    identity_values = _values_at(routed, identity_positions)
    routing_values = raw_values if routing is None else tuple(routing)
    common = (witness, identity_values, raw_values, routing_values, tuple(findings))
    if (
        unknown_family_tag is not None
        or any(issue.code.startswith("stored-data-primary-key-") for issue in findings)
        or any(routed[position] is ABSENT for position in layout.primary_key)
    ):
        return IdentityClaim(None, *common)
    return IdentityClaim(
        LogicalKey(
            layout.family,
            _key_value(layout, routed),
            _values_at(routed, layout.temporal_starts),
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


def _key_value(layout: EntityLayout, decoded: Sequence[object]) -> object:
    return decoded[layout.primary_key[0]]


def _values_at(values: Sequence[object], positions: tuple[int, ...]) -> tuple[object, ...]:
    if not positions:
        return ()
    if len(positions) == 1:
        return (values[positions[0]],)
    return tuple(values[position] for position in positions)
