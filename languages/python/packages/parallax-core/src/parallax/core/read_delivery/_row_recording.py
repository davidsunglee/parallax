from __future__ import annotations

from collections.abc import Callable
from typing import Final, cast

from parallax.core.base import SQL_NULL, DocumentValue, UnknownFamilyTag
from parallax.core.db_port import Row
from parallax.core.document_codec import locate_raw_entity_member
from parallax.core.read_delivery._convert import EntityReadMapping, judge_positions
from parallax.core.read_delivery._page import (
    ABSENT,
    EntityState,
    PageBuilder,
    RowKey,
    SourceLevel,
    StoredDataIssueInput,
    with_identity_findings,
)

__all__ = [
    "RecordRow",
    "located_stored_values",
    "record_deferred",
    "record_judged",
    "record_trusted",
    "record_trusted_singleton",
]

type RecordRow = Callable[
    [EntityReadMapping, tuple[object, ...], int, UnknownFamilyTag | None, PageBuilder, SourceLevel],
    int,
]
"""How one fetched row is recorded into a builder, chosen once per bound mapping:
from its stored values, the members it carried for classification, and its
unrecognized family tag, answering its fetched row index."""

# The named tuples recorded per row are built through ``tuple.__new__``, which skips
# their generated Python constructors.
type _StateFields = tuple[tuple[object, ...], tuple[StoredDataIssueInput, ...]]
_new_state: Final = cast(
    "Callable[[type[EntityState], _StateFields], EntityState]", vars(tuple)["__new__"]
)
_new_row_key: Final = cast(
    "Callable[[type[RowKey], tuple[object, object, tuple[object, ...]]], RowKey]",
    vars(tuple)["__new__"],
)


def located_stored_values(
    mapping: EntityReadMapping, row: Row, document: object | None
) -> tuple[tuple[object, ...], int]:
    """One row's stored values where some member is not a cell of its own,
    answering them beside the members the row carried, one bit each.

    A member located in the row's shared ``document`` is read from it, a cell
    from its ordinal, and an uncarried member stays :data:`ABSENT`. A requested
    occurrence the Entity carries no source for reads as stored SQL NULL."""
    classifiable = 0
    layout = mapping.layout
    ordinals = mapping.result_ordinals
    document_members = mapping.document_member_names
    values: list[object] = [ABSENT] * len(layout.members)
    for position in range(layout.attribute_count):
        document_member = document_members[position]
        if document_member is not None:
            values[position] = (
                SQL_NULL
                if document is None
                else locate_raw_entity_member(cast("DocumentValue", document), document_member)
            )
        elif (ordinal := ordinals[position]) is not None:
            values[position] = row[ordinal]
        else:
            continue
        classifiable |= 1 << position
    for position, projected in enumerate(
        mapping.projected_by_position, start=layout.attribute_count
    ):
        if not projected:
            continue
        document_member = document_members[position]
        if document_member is not None:
            values[position] = (
                SQL_NULL
                if document is None
                else locate_raw_entity_member(cast("DocumentValue", document), document_member)
            )
        elif (ordinal := ordinals[position]) is not None:
            values[position] = row[ordinal]
        else:
            values[position] = None
            continue
        classifiable |= 1 << position
    return tuple(values), classifiable


def record_trusted(
    mapping: EntityReadMapping,
    stored_values: tuple[object, ...],
    classifiable: int,
    unknown_family_tag: UnknownFamilyTag | None,
    builder: PageBuilder,
    source: SourceLevel,
) -> int:
    """Record a row nothing host-checks or classifies on a level that may repeat
    rows: its stored values are its member row, compared before they are shared."""
    del classifiable, unknown_family_tag
    layout = mapping.layout
    return builder.add_fetched_row(
        source,
        layout,
        _trusted_key(mapping, stored_values),
        stored_values,
        stored_values,
        (),
        None,
    )


def record_trusted_singleton(
    mapping: EntityReadMapping,
    stored_values: tuple[object, ...],
    classifiable: int,
    unknown_family_tag: UnknownFamilyTag | None,
    builder: PageBuilder,
    source: SourceLevel,
) -> int:
    """Record a row nothing host-checks or classifies on a level that records each
    row key at most once: its stored values are its member row, judged with no
    finding."""
    del classifiable, unknown_family_tag
    return builder.add_fetched_row(
        source,
        mapping.layout,
        _trusted_key(mapping, stored_values),
        stored_values,
        stored_values,
        (),
        stored_values,
    )


def record_judged(
    mapping: EntityReadMapping,
    stored_values: tuple[object, ...],
    classifiable: int,
    unknown_family_tag: UnknownFamilyTag | None,
    builder: PageBuilder,
    source: SourceLevel,
) -> int:
    """Record a row of a level that records each row key at most once, judging
    its whole requested payload now, since no other fetched row of its logical
    row exists to compare with first.

    Each position is judged once, by the rules a deferred judgment applies, and
    the Page holds the judged member row and its findings rather than the
    stored values or a decoder."""
    routed, identity_findings, correlation_findings = _judge_routing(mapping, stored_values)
    routed_values = stored_values if routed is None else tuple(routed)
    key = _routed_key(mapping, routed_values, unknown_family_tag)
    if mapping.judges_scalars_only and unknown_family_tag is None:
        members, payload = judge_positions(
            mapping.payload_positions,
            stored_values,
            mapping,
            routed,
            None,
            routed_values=routed_values,
            captured=() if correlation_findings is None else tuple(correlation_findings),
        )
        member_row = stored_values if members is None else tuple(members)
        payload_findings = () if payload is None else tuple(payload)
    else:
        member_row, payload_findings = mapping.decode_payload(
            stored_values,
            routed_values,
            None if classifiable == mapping.every_member_present else classifiable,
            () if correlation_findings is None else tuple(correlation_findings),
            unknown_family_tag,
        )
    identity = () if identity_findings is None else tuple(identity_findings)
    findings = with_identity_findings(payload_findings, identity)
    return builder.add_fetched_row(
        source,
        mapping.layout,
        key,
        None,
        member_row,
        identity,
        _new_state(EntityState, (member_row, findings)) if findings else member_row,
    )


def record_deferred(
    mapping: EntityReadMapping,
    stored_values: tuple[object, ...],
    classifiable: int,
    unknown_family_tag: UnknownFamilyTag | None,
    builder: PageBuilder,
    source: SourceLevel,
) -> int:
    """Record a row with its payload judgment deferred to the reader that needs
    its state: a row of a level that may repeat rows, whose fetched rows of one
    logical row compare first, or a row a write acquires.

    The fetched row keeps its stored values for comparing and classifying the
    payload, beside the routed values page assembly reads: the stored values
    with each judged identity and correlation cell decoded, or ``ABSENT`` where
    rejected. Identity findings join the Page's identity issues; correlation
    findings wait for the payload judgment, which places them at their own
    positions.
    """
    routed, identity_findings, correlation_findings = _judge_routing(mapping, stored_values)
    routed_values = stored_values if routed is None else tuple(routed)
    fetched_row = builder.add_fetched_row(
        source,
        mapping.layout,
        _routed_key(mapping, routed_values, unknown_family_tag),
        stored_values,
        routed_values,
        () if identity_findings is None else tuple(identity_findings),
        mapping,
    )
    partial = None if classifiable == mapping.every_member_present else classifiable
    if partial is not None or correlation_findings or unknown_family_tag is not None:
        builder.add_payload_inputs(
            fetched_row,
            partial,
            () if correlation_findings is None else tuple(correlation_findings),
            unknown_family_tag,
        )
    return fetched_row


def _judge_routing(
    mapping: EntityReadMapping, stored_values: tuple[object, ...]
) -> tuple[
    list[object] | None,
    list[StoredDataIssueInput] | None,
    list[StoredDataIssueInput] | None,
]:
    """Judge the host-checked identity cells, then the host-checked correlation
    cells, that page assembly routes by."""
    routed: list[object] | None = None
    identity_findings: list[StoredDataIssueInput] | None = None
    correlation_findings: list[StoredDataIssueInput] | None = None
    if mapping.eager_identity_positions:
        routed, identity_findings = judge_positions(
            mapping.eager_identity_positions, stored_values, mapping, None, None
        )
    if mapping.eager_correlation_positions:
        routed, correlation_findings = judge_positions(
            mapping.eager_correlation_positions, stored_values, mapping, routed, None
        )
    return routed, identity_findings, correlation_findings


def _trusted_key(mapping: EntityReadMapping, stored_values: tuple[object, ...]) -> RowKey | None:
    layout = mapping.layout
    primary_key = stored_values[layout.primary_key[0]]
    if primary_key is ABSENT:
        return None
    return _new_row_key(
        RowKey, (layout.family, primary_key, mapping.temporal_start_values(stored_values))
    )


def _routed_key(
    mapping: EntityReadMapping,
    routed_values: tuple[object, ...],
    unknown_family_tag: UnknownFamilyTag | None,
) -> RowKey | None:
    """The row key of a row whose identity was judged: none for an unrecognized
    family tag or a rejected primary key."""
    if unknown_family_tag is not None:
        return None
    layout = mapping.layout
    for position in layout.primary_key:
        if routed_values[position] is ABSENT:
            return None
    return _new_row_key(
        RowKey,
        (
            layout.family,
            routed_values[layout.primary_key[0]],
            mapping.temporal_start_values(routed_values),
        ),
    )
