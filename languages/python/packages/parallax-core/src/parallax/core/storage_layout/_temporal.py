from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Final

from parallax.core.metamodel import AsOfAxisMetadata, Column, Table, TemporalDimension
from parallax.core.storage_layout._facet import (
    ColumnContributor,
    ColumnSlot,
    PhysicalTemporalAxis,
    TemporalHistoryConstraints,
)

__all__ = ["constraint_name", "temporal_history_constraints"]

_NAMESPACE: Final = "pxc"
_FINGERPRINT_VERSION: Final = "pxc-1"
_FINGERPRINT_HEX: Final = 32
_NAME_BYTES: Final = 63
"""The whole name's budget, PostgreSQL's identifier limit, fixed for every dialect."""
_EMPTY_PREFIX: Final = "table"

_INTERVAL_CHECK_KINDS: Final[Mapping[TemporalDimension, str]] = {
    TemporalDimension.TRANSACTION_TIME: "tx",
    TemporalDimension.VALID_TIME: "valid",
}
_LESS_THAN: Final = "lt"

_UNREADABLE: Final = re.compile(r"[^0-9A-Za-z]+")

type OperandGroup = tuple[str, tuple[Column, ...]]
"""One operand group's comparison or range semantics and its ordered Columns."""


def _readable_prefix(table: Table) -> str:
    return _UNREADABLE.sub("_", table.name).strip("_").lower() or _EMPTY_PREFIX


def _fingerprint(table: Table, kind: str, groups: Sequence[OperandGroup]) -> str:
    """The first 128 bits of SHA-256 over the definition's versioned fields.

    Every field is UTF-8 behind a four-byte big-endian length, and each operand
    group is preceded by its semantics and its operand count, so the digest
    depends on the group boundaries rather than on a joined string.
    """
    fields = [_FINGERPRINT_VERSION, table.name, kind, str(len(groups))]
    for semantics, columns in groups:
        fields.extend((semantics, str(len(columns)), *(column.name for column in columns)))
    digest = hashlib.sha256()
    for field in fields:
        encoded = field.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    return digest.hexdigest()[:_FINGERPRINT_HEX]


def constraint_name(table: Table, kind: str, groups: Sequence[OperandGroup]) -> str:
    """``pxc_<kind>_<readable-table-prefix>_<fingerprint>`` within 63 bytes.

    Only the readable prefix is shortened; the trim and fallback apply again
    after the cut so a shortened prefix never ends in a separator.
    """
    fingerprint = _fingerprint(table, kind, groups)
    budget = _NAME_BYTES - len(_NAMESPACE) - len(kind) - len(fingerprint) - 3
    kept = _readable_prefix(table)[:budget].strip("_") or _EMPTY_PREFIX
    return f"{_NAMESPACE}_{kind}_{kept}_{fingerprint}"


def _axis(
    table: Table,
    axis: AsOfAxisMetadata,
    by_contributor: Mapping[ColumnContributor, ColumnSlot],
) -> PhysicalTemporalAxis:
    start = by_contributor.get(axis.start_attribute)
    end = by_contributor.get(axis.end_attribute)
    if start is None or end is None:  # pragma: no cover - validation keeps endpoints direct
        raise RuntimeError(f"Table {table.name!r} does not carry both endpoints of an As-Of Axis")
    name = constraint_name(
        table,
        _INTERVAL_CHECK_KINDS[axis.dimension],
        ((_LESS_THAN, (start.column, end.column)),),
    )
    return PhysicalTemporalAxis(axis, start, end, name)


def temporal_history_constraints(
    table: Table,
    axes: Sequence[AsOfAxisMetadata],
    by_contributor: Mapping[ColumnContributor, ColumnSlot],
) -> TemporalHistoryConstraints | None:
    """The constraints ``table`` carries for its family root's declared ``axes``.

    Each endpoint resolves through the Table's own contributor lookup, which
    reaches a root-declared Attribute from every Table its family maps.
    """
    by_dimension = {axis.dimension: axis for axis in axes}
    transaction_axis = by_dimension.get(TemporalDimension.TRANSACTION_TIME)
    if transaction_axis is None:
        return None
    valid_axis = by_dimension.get(TemporalDimension.VALID_TIME)
    return TemporalHistoryConstraints(
        transaction_axis=_axis(table, transaction_axis, by_contributor),
        valid_axis=None if valid_axis is None else _axis(table, valid_axis, by_contributor),
    )
