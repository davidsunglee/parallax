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
import re
from collections.abc import Mapping, Sequence
from typing import Final, cast

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
    "STRING",
    "TIME",
    "TIMESTAMP",
    "UUID",
    "AuthoredNumber",
    "Boolean",
    "Bytes",
    "Date",
    "Decimal",
    "Float32",
    "Float64",
    "InstantError",
    "Int32",
    "Int64",
    "Json",
    "NeutralType",
    "String",
    "TemporalBound",
    "Time",
    "Timestamp",
    "Uuid",
    "coerce_neutral_input",
    "decode_neutral_literal",
    "detach_json_container",
    "infer_neutral_type",
    "is_neutral_type",
    "matches_neutral_type",
    "normalize_instant",
]


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
