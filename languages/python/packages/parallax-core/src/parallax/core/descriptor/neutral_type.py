"""Shared, error-neutral `m-descriptor` scalar-type support: neutral-type
inference, canonical-name derivation, and exact descriptor-spelling membership.

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

The module also owns exact descriptor-spelling membership: :func:`type_matches`
grades whether a value belongs to the space a resolved type spelling names,
parsing the spelling and applying the same `m-core` logical membership a keyed
write row is graded against (:func:`~parallax.core.base.matches_neutral_type`
over :func:`~parallax.core.base.decode_neutral_literal`). A predicate-write
assignment still carries the descriptor's type spelling rather than a structured
Neutral Type, so it needs this spelling-parsing entry point; its callers cannot
import each other yet each already depends on this module.
"""

from __future__ import annotations

import datetime as _dt
import decimal as _decimal
import uuid as _uuid

from parallax.core.base import decode_neutral_literal, matches_neutral_type
from parallax.core.descriptor.type_spelling import parse_type_spelling

__all__ = ["NEUTRAL_FROM_PY", "infer_neutral_type", "snake_to_camel", "type_matches"]

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


def type_matches(value: object, neutral_type: str) -> bool:
    """Whether ``value`` is a member of the space ``neutral_type`` spells, by
    EXACT `m-core` logical membership — the same contract a neutral keyed write
    row is graded against (`parallax.core.base.matches_neutral_type`), applied
    here to a `.set(...)`-built or case-authored predicate-write assignment.

    A value may still carry its portable literal spelling (an integer for a
    float space, an ISO-8601 string for a temporal one, a lowercase-hex string
    for `bytes`), so it is decoded to the space's native carrier first
    (`parallax.core.base.decode_neutral_literal`) and then checked. Decoding is
    lossless and total, so an integer no float represents exactly, a malformed
    literal, and an over-precise decimal are all non-members, exactly as they
    are for a keyed write row.

    The ONE scalar-value-policy check both `parallax.core.inheritance.
    validate_write_assignment` (the assignment's own scalar leaf, in turn
    reached by both `parallax.core.entity.expressions.AttributeExpr.set` and
    `parallax.core.unit_work.instructions.validate_instruction`) and the
    error-neutral Value Object document walk
    (`parallax.core.descriptor.vo_document`) apply — those scopes may not import
    each other (`core/spec/modules.md` §7 DAG) but each already depends on this
    module, so the check lives here once rather than staying forked. The
    `m-metamodel` interface carries a structured Neutral Type, so a keyed write
    row over accepted Metadata calls that shared membership check directly; only
    a predicate-write assignment, which still holds the descriptor's type
    spelling, needs this spelling-parsing entry point.
    """
    declared = parse_type_spelling(neutral_type)
    if declared is None:  # pragma: no cover - a resolved descriptor spells only representable types
        return False
    return matches_neutral_type(decode_neutral_literal(value, declared), declared)
