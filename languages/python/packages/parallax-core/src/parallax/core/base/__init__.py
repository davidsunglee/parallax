"""``parallax.core.base`` enforcement scope (m-core).

The normative primitives the whole spine rests on: the neutral data-type
vocabulary, global UTC / microsecond normalization for ``timestamp`` instants,
the native-infinity temporal upper bound, and the ``json`` value-object
document column type. ``m-core`` depends on nothing.
"""

from __future__ import annotations

import datetime as dt
import enum
import re
from typing import Final

__all__ = [
    "DOCUMENT_TYPE",
    "INFINITY",
    "INFINITY_LITERAL",
    "NEUTRAL_TYPES",
    "InstantError",
    "TemporalBound",
    "is_neutral_type",
    "normalize_instant",
]

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
