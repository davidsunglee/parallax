"""Shared, error-neutral Python-scalar-type inference (m-descriptor).

The Entity class frontend (``parallax.core.entity.base``) and the ValueObject
class frontend (``parallax.core.entity.value_object``) each infer a scalar
member's `m-core` neutral type from its plain Python annotation when no
explicit ``type=`` override is given, and each derives a declared member's
default canonical (camelCase) name from its python (snake_case) field name
when no explicit ``name=`` override is given — the SAME two mechanical lookups,
independently, because ``base`` already imports ``value_object`` (to detect a
value-object-typed field), so ``value_object`` importing back from ``base``
for this would cycle. Both frontends already depend on ``m-descriptor``
directly, so the shared lookups live HERE rather than staying duplicated (the
`vo_path` module's own precedent: a shared, error-neutral resolution one layer
below the two callers that cannot import each other).

This module is **error-neutral** like `vo_path`: :func:`infer_neutral_type`
returns the resolved type name or ``None``, never raising — the unresolved-type
message text (and the decimal-needs-precision special case, whose fix-it
snippet differs, ``Field(...)`` vs ``VoField(...)``) is each caller's OWN
classification, so neither frontend's own wording changes.
"""

from __future__ import annotations

import datetime as _dt
import decimal as _decimal
import uuid as _uuid

__all__ = ["NEUTRAL_FROM_PY", "infer_neutral_type", "snake_to_camel"]

NEUTRAL_FROM_PY: dict[type, str] = {
    bool: "boolean",
    int: "int64",
    float: "float64",
    str: "string",
    bytes: "bytes",
    _dt.date: "date",
    _dt.time: "time",
    _dt.datetime: "timestamp",
    _uuid.UUID: "uuid",
    _decimal.Decimal: "decimal",
}


def infer_neutral_type(inner: object) -> str | None:
    """The bare `m-core` neutral-type name for a plain Python scalar type, or
    ``None`` when ``inner`` is not one of the recognized scalar types at all.

    Returns the literal ``"decimal"`` name uninspected — a decimal without an
    explicit precision is a caller-classified error (`Field(type=...)` /
    `VoField(type=...)`, differently worded per frontend), not this shared
    lookup's concern.
    """
    if isinstance(inner, type) and inner in NEUTRAL_FROM_PY:
        return NEUTRAL_FROM_PY[inner]
    return None


def snake_to_camel(name: str) -> str:
    """Convert a snake_case field name to its canonical camelCase identifier."""
    head, *tail = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)
