"""``parallax.core.base`` enforcement scope (m-core).

The normative primitives the whole spine rests on: the structured
:data:`~parallax.core.base.NeutralType` algebra, its value-space conformance
check, the inverse of its portable literal encoding (the serde seam's own wire
decode), the narrower developer input-policy widening the runtime write
validators apply instead, the interchange neutral-type name vocabulary, global
UTC / microsecond normalization for ``timestamp`` instants, the native-infinity
temporal upper bound, and the ``json`` value-object document column type.
``m-core`` depends on nothing.
"""

from __future__ import annotations

import datetime as dt
import enum
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, TypeGuard, cast

from parallax.core.base._inference import NEUTRAL_FROM_PYTHON, infer_neutral_type
from parallax.core.base._neutral import (
    BOOLEAN,
    BYTES,
    DATE,
    FLOAT32,
    FLOAT64,
    INT32,
    INT64,
    JSON,
    STRING,
    TIME,
    TIMESTAMP,
    UUID,
    AuthoredNumber,
    Boolean,
    Bytes,
    Date,
    Decimal,
    Float32,
    Float64,
    Int32,
    Int64,
    Json,
    NeutralType,
    String,
    Time,
    Timestamp,
    Uuid,
    coerce_neutral_input,
    decode_neutral_literal,
    matches_neutral_type,
)

__all__ = [
    "BOOLEAN",
    "BYTES",
    "DATE",
    "DOCUMENT_TYPE",
    "FLOAT32",
    "FLOAT64",
    "INFINITY",
    "INFINITY_LITERAL",
    "INT32",
    "INT64",
    "JSON",
    "NEUTRAL_FROM_PYTHON",
    "NEUTRAL_TYPES",
    "SQL_NULL",
    "STRING",
    "TIME",
    "TIMESTAMP",
    "UUID",
    "AuthoredNumber",
    "Boolean",
    "Bytes",
    "Date",
    "Decimal",
    "DocumentRead",
    "DocumentReadOrdinals",
    "DocumentValue",
    "Float32",
    "Float64",
    "InstantError",
    "Int32",
    "Int64",
    "Json",
    "NeutralType",
    "PresentDocument",
    "SqlNull",
    "String",
    "TemporalBound",
    "Time",
    "Timestamp",
    "Uuid",
    "admits_stored_scalar",
    "coerce_neutral_input",
    "decode_neutral_literal",
    "detach_json_container",
    "infer_neutral_type",
    "is_document_value",
    "is_neutral_type",
    "matches_neutral_type",
    "normalize_instant",
    "unwrap_document_read",
]


type DocumentValue = (
    bool | int | float | str | list[DocumentValue] | dict[str, DocumentValue] | None
)
"""A portable JSON data-model value, including bare JSON null."""


@dataclass(frozen=True, slots=True)
class SqlNull:
    """A structured-document result whose SQL column is NULL."""


SQL_NULL: Final[SqlNull] = SqlNull()


@dataclass(frozen=True, slots=True)
class PresentDocument:
    """A non-SQL-null structured-document result, including JSON null."""

    document: DocumentValue


type DocumentRead = SqlNull | PresentDocument
"""The provider-neutral structured-document read transport."""

type DocumentReadOrdinals = tuple[int, int]
"""Adjacent zero-based ``(presence, document)`` projection ordinals."""


def unwrap_document_read(value: DocumentRead) -> DocumentValue | None:
    """Return a document carrier's payload, mapping SQL NULL to ``None``."""
    return None if isinstance(value, SqlNull) else value.document


def is_document_value(value: object) -> TypeGuard[DocumentValue]:
    """Whether ``value`` belongs to the portable JSON data model."""
    if value is None or isinstance(value, (bool, int, str)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(is_document_value(item) for item in cast("list[object]", value))
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and is_document_value(item)
            for key, item in cast("dict[object, object]", value).items()
        )
    return False


def detach_json_container(value: object) -> object:
    """Recursively copy JSON-shaped containers into plain ``dict`` and ``list`` values.

    Mapping and sequence implementations may be immutable views owned by another
    boundary. The returned tree shares no container with ``value``; scalar values
    pass through unchanged. Strings and bytes are scalars, not JSON arrays.
    """
    if isinstance(value, Mapping):
        return {
            key: detach_json_container(item)
            for key, item in cast("Mapping[str, object]", value).items()
        }
    if isinstance(value, (list, tuple)):
        return [detach_json_container(item) for item in cast("Sequence[object]", value)]
    return value


# The closed base neutral-type vocabulary (m-core). ``decimal`` is parametric —
# a descriptor spells it ``decimal(p,s)`` — and ``is_neutral_type`` accepts that
# spelling in addition to the bare name below.
NEUTRAL_TYPES: Final[frozenset[str]] = frozenset(
    {
        "boolean",
        "int32",
        "int64",
        "float32",
        "float64",
        "decimal",
        "string",
        "bytes",
        "date",
        "time",
        "timestamp",
        "uuid",
        "json",
    }
)

# The storage type an ``m-value-object`` composite maps to: a single structured
# document column rather than column-flattened members (m-core, "json" type).
DOCUMENT_TYPE: Final[str] = "json"

# The canonical literal for the open upper bound in golden SQL and table state.
INFINITY_LITERAL: Final[str] = "infinity"

_DECIMAL = re.compile(r"^decimal\(\d+,\d+\)$")


class TemporalBound(enum.Enum):
    """The open upper bound of a temporal interval — the database's native
    infinity (m-core), distinct from every finite instant and from ``None``."""

    INFINITY = "infinity"


# The native-infinity sentinel for a temporal interval's open upper bound.
INFINITY: Final[TemporalBound] = TemporalBound.INFINITY


class InstantError(ValueError):
    """A ``timestamp`` value violates the m-core UTC / precision rules."""


def is_neutral_type(name: str) -> bool:
    """Whether ``name`` is a base neutral type or a ``decimal(p,s)`` spelling."""
    return name in NEUTRAL_TYPES or _DECIMAL.match(name) is not None


def admits_stored_scalar(
    value: object,
    declared: NeutralType,
    *,
    nullable: bool,
    temporal_end: bool,
) -> bool:
    """Whether one decoded stored scalar satisfies its logical read contract.

    SQL NULL is admitted only by a nullable Attribute, the native infinity
    sentinel only by a temporal end Attribute, and every other value must
    inhabit the Attribute's declared Neutral Type.
    """
    if value is None:
        return nullable
    if value is INFINITY:
        return temporal_end
    return matches_neutral_type(value, declared)


def normalize_instant(value: dt.datetime) -> dt.datetime:
    """Normalize a ``timestamp`` to the m-core boundary form: UTC, microsecond.

    A naive datetime carries no offset and is rejected at the boundary (§2
    input policy); an aware value is converted to UTC. ``datetime`` already
    caps precision at the microsecond, so no sub-microsecond truncation is
    possible for a ``datetime`` input.
    """
    if value.utcoffset() is None:
        raise InstantError("a naive datetime is not a valid `timestamp`; attach a tzinfo")
    return value.astimezone(dt.UTC)
