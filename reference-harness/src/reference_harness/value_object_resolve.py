"""Model-aware value-object resolution + the pre-SQL rejection vocabulary.

Shared primitives for the two negative-validation validators
(:mod:`op_validate` for operations, :mod:`write_validate` for writes) that back
the ``rejected`` case shape (m-case-format, resolved Q7). A ``rejected`` case
asserts a model-aware validator refuses an input **before any SQL is emitted**,
naming the violated normative rule in ``then.rejectedRule``.

This module owns three things:

* :class:`RejectionError` — raised by a validator with the ``rule`` it violated.
* The closed **rule vocabulary** (:data:`REJECTED_RULES`) — the small set of
  ``then.rejectedRule`` identifiers, each naming a normative MUST from
  ``m-op-algebra`` (predicate bound ordering and the nested-predicate resolver) or
  the ``m-value-object`` materialization/navigation contract. The schema pins the
  SAME vocabulary in the ``then.rejectedRule`` enum; the two MUST agree.
* The **member resolvers** — resolve a dotted nested path / value-object-terminated
  path / element-relative path against an entity's *declared* recursive value-object
  structure, raising :class:`RejectionError` on the first undeclared segment, plus
  the literal-level checks (declared-type match, and range-bound ordering).

These are non-normative grading machinery: they let the reference harness make the
reference implementation actually reject what the ``rejected`` cases pin, exactly as
each language implementation must.
"""

from __future__ import annotations

import datetime
import decimal
import math
import re
import uuid
from typing import Any

from .case import Entity

# --- rule vocabulary --------------------------------------------------------
#
# The closed set of `then.rejectedRule` identifiers. Kept in lockstep with the
# `then.rejectedRule` enum in compatibility-case.schema.json (m-case-format).

# Operation rules (m-op-algebra bound-ordering + nested-predicate resolver MUSTs,
# m-value-object materialization/navigation contract clauses 4/5).
BETWEEN_BOUNDS_INVERTED = "between-bounds-inverted"
NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT = "nested-path-first-segment-not-value-object"
NESTED_PATH_UNKNOWN_MEMBER = "nested-path-unknown-member"
NESTED_LITERAL_TYPE_MISMATCH = "nested-literal-type-mismatch"
NESTED_STRING_PREDICATE_NON_STRING_MEMBER = "nested-string-predicate-non-string-member"
DEEP_FETCH_VALUE_OBJECT_SEGMENT = "deep-fetch-value-object-segment"
NAVIGATE_VALUE_OBJECT_TARGET = "navigate-value-object-target"
FIND_ROOT_VALUE_OBJECT = "find-root-value-object"

# Write rules (m-value-object write validation).
WRITE_REQUIRED_ATTRIBUTE_MISSING = "write-required-attribute-missing"
WRITE_REQUIRED_VALUE_OBJECT_MISSING = "write-required-value-object-missing"
WRITE_VALUE_TYPE_MISMATCH = "write-value-type-mismatch"

REJECTED_RULES: frozenset[str] = frozenset(
    {
        BETWEEN_BOUNDS_INVERTED,
        NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT,
        NESTED_PATH_UNKNOWN_MEMBER,
        NESTED_LITERAL_TYPE_MISMATCH,
        NESTED_STRING_PREDICATE_NON_STRING_MEMBER,
        DEEP_FETCH_VALUE_OBJECT_SEGMENT,
        NAVIGATE_VALUE_OBJECT_TARGET,
        FIND_ROOT_VALUE_OBJECT,
        WRITE_REQUIRED_ATTRIBUTE_MISSING,
        WRITE_REQUIRED_VALUE_OBJECT_MISSING,
        WRITE_VALUE_TYPE_MISMATCH,
    }
)


class RejectionError(Exception):
    """A model-aware validator refused an input pre-SQL; ``rule`` names the reason.

    ``rule`` is one of :data:`REJECTED_RULES`; the runner asserts it equals the
    case's ``then.rejectedRule``.
    """

    def __init__(self, rule: str, detail: str) -> None:
        super().__init__(f"{rule}: {detail}")
        self.rule = rule
        self.detail = detail


# --- typed-literal checking -------------------------------------------------
#
# The neutral type vocabulary is CLOSED (`metamodel.schema.json` `$defs/attribute`
# `type`): boolean, int32, int64, float32, float64, string, bytes, date, time,
# timestamp, uuid, json, and decimal(precision,scale). Each admits exactly one
# portable literal form, and the check below decides membership of that form — not
# of a loose category. A category guess would leave the vocabulary open again: a
# spelling nothing here models would be accepted, which is precisely how a
# `decimal(12,2)` or a `bytes` field once admitted a truth value or an array.

_INT_BOUNDS: dict[str, tuple[int, int]] = {
    "int32": (-(2**31), 2**31 - 1),
    "int64": (-(2**63), 2**63 - 1),
}

_DECIMAL_TYPE = re.compile(r"^decimal\((\d+),(\d+)\)$")


def literal_matches_type(value: Any, neutral_type: str | None) -> bool:
    """Whether a literal / document value spells a member of a declared neutral type.

    Used both for a nested comparison's literal (`m-op-algebra` typed-literal MUST)
    and a write row's scalar leaf (`m-value-object` write validation). A ``null`` is
    always type-acceptable — nullability is a SEPARATE check (required vs optional),
    never a type mismatch.

    The domain is the PORTABLE literal, the spelling a case authors, so membership
    is decided against the wire form each space encodes to (`m-core`,
    `m-document-codec`): a JSON number for the integer and float spaces, an ISO-8601
    string for `date` / `time` / `timestamp`, a canonical UUID string, a lowercase
    hex string for `bytes`, and either a JSON number or an exact digit string for a
    `decimal`, which is the one space no JSON number can carry a scale for. An
    integer outside its declared width and a decimal the declared precision and
    scale cannot represent exactly are non-members: representing either would
    require rounding or truncation.

    A type spelling the closed vocabulary does not carry is accepted rather than
    guessed at — such a descriptor never passed schema validation, so refusing it
    here would report a write rule for what is a malformed model.
    """
    if value is None:
        return True
    kind = neutral_type or ""
    decimal_type = _DECIMAL_TYPE.match(kind)
    if decimal_type is not None:
        precision, scale = (int(group) for group in decimal_type.groups())
        return _matches_decimal(value, precision, scale)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind in _INT_BOUNDS:
        low, high = _INT_BOUNDS[kind]
        return _is_integer(value) and low <= value <= high
    if kind in ("float32", "float64"):
        return _is_number(value) and _is_finite(value)
    if kind == "string":
        return isinstance(value, str)
    if kind == "bytes":
        return isinstance(value, str) and _is_lowercase_hex(value)
    if kind in ("date", "time", "timestamp"):
        return isinstance(value, str) and _is_iso_temporal(value, kind)
    if kind == "uuid":
        return isinstance(value, str) and _parses_as_uuid(value)
    if kind == "json":
        return True
    return True


def _is_integer(value: Any) -> bool:
    """Whether *value* is an integer rather than a truth value."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_finite(value: Any) -> bool:
    return not isinstance(value, float) or math.isfinite(value)


def _matches_decimal(value: Any, precision: int, scale: int) -> bool:
    """Whether *value* spells a decimal the declared precision and scale hold exactly.

    A JSON number spells one through its shortest round-tripping text, so the digits
    tested are the digits written rather than a float's binary expansion; a string
    spells one directly, which is the form a structured document stores.
    """
    if _is_integer(value):
        spelling = str(value)
    elif isinstance(value, float):
        spelling = repr(value) if math.isfinite(value) else ""
    elif isinstance(value, str):
        spelling = value
    else:
        return False
    try:
        decimal_value = decimal.Decimal(spelling)
    except decimal.InvalidOperation:
        return False
    if not decimal_value.is_finite():
        return False
    _sign, digits, exponent = decimal_value.as_tuple()
    if not isinstance(exponent, int):
        return False
    coefficient = int("".join(str(digit) for digit in digits))
    if coefficient == 0:
        return True
    while coefficient % 10 == 0:
        coefficient //= 10
        exponent += 1
    if exponent < -scale:
        return False
    return len(str(coefficient)) + exponent + scale <= precision


def _is_lowercase_hex(value: str) -> bool:
    return len(value) % 2 == 0 and all(character in "0123456789abcdef" for character in value)


def _is_iso_temporal(value: str, kind: str) -> bool:
    """Whether *value* is a microsecond-precision ISO-8601 literal of *kind*.

    A `timestamp` carries a UTC offset (it names an instant); a `time` carries none
    (it names a wall clock). A fractional field with a non-zero digit past the sixth
    names no member of a microsecond-precision space.
    """
    if not _within_microsecond_precision(value):
        return False
    try:
        if kind == "date":
            datetime.date.fromisoformat(value)
            return True
        if kind == "time":
            return datetime.time.fromisoformat(value).tzinfo is None
        return datetime.datetime.fromisoformat(value).utcoffset() is not None
    except ValueError:
        return False


def _within_microsecond_precision(value: str) -> bool:
    """Whether no fractional field carries a non-zero digit past the sixth.

    A temporal literal may spell more than one fractional field — a fractional
    second and a fractional offset — so every ``.`` / ``,``-initiated digit run is
    inspected, not just the first.
    """
    return all(set(fraction[6:]) <= {"0"} for fraction in re.findall(r"[.,](\d+)", value))


def _parses_as_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def is_string_member(neutral_type: str | None) -> bool:
    """Whether a declared member's neutral type is m-core's ``String``.

    The `m-op-algebra` non-string-member rule, which the five nested string
    predicates are subject to in both scopes. Deliberately STRICTER than
    :func:`literal_matches_type`'s string grouping: that function answers whether a
    portable literal can carry a value of the type, and `date` / `time` /
    `timestamp` / `uuid` / `bytes` all ride a `string` literal, so reusing it would
    accept `nestedStartsWith` against a `Date` member — the exact hole this rule
    exists to close. Only the canonical `string` spelling is a string member, and an
    absent or unknown type is not one.
    """
    return neutral_type == "string"


def _is_number(value: Any) -> bool:
    """Whether *value* is a JSON ``number`` — a bool is its own kind, never one."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def bounds_inverted(lower: Any, upper: Any) -> bool:
    """Whether a range's ``lower`` bound is strictly greater than its ``upper``.

    The `m-op-algebra` bound-ordering MUST, shared by every range predicate. Bounds
    are compared by LITERAL KIND rather than by resolved attribute type: only two
    numbers or two strings are ordered against each other, and a differing pair or a
    ``null`` bound is skipped rather than guessed. Equal bounds name the single-value
    range and are never inverted.
    """
    if _is_number(lower) and _is_number(upper):
        return lower > upper
    if isinstance(lower, str) and isinstance(upper, str):
        return lower > upper
    return False


# --- declared-structure lookups --------------------------------------------


def find_top_value_object(entity: Entity, name: str) -> dict[str, Any] | None:
    """The top-level value object *name* declared on *entity*, else ``None``."""
    for value_object in entity.value_objects:
        if value_object.get("name") == name:
            return value_object
    return None


def find_nested_value_object(value_object: dict[str, Any], name: str) -> dict[str, Any] | None:
    """A nested value object *name* declared inside *value_object*, else ``None``."""
    for nested in value_object.get("valueObjects", []):
        if nested.get("name") == name:
            return nested
    return None


def find_attribute(value_object: dict[str, Any], name: str) -> dict[str, Any] | None:
    """A typed inner attribute *name* declared on *value_object*, else ``None``."""
    for attribute in value_object.get("attributes", []):
        if attribute.get("name") == name:
            return attribute
    return None


# --- path resolution --------------------------------------------------------


def resolve_nested_ref(entity: Entity, path: str) -> dict[str, Any]:
    """Resolve a ``Class.valueObject.field(.field)*`` path to its LEAF attribute.

    Raises :class:`RejectionError` on the first undeclared segment: the first
    segment must name a declared value object on *entity*
    (``nested-path-first-segment-not-value-object``), each intermediate a nested
    value object and the leaf an attribute (``nested-path-unknown-member``). The
    schema's ``nestedRef`` grammar already guarantees ≥3 dotted components, so a
    resolved path always has a value-object segment and an attribute leaf.
    """
    _cls, first, *rest = path.split(".")
    value_object = find_top_value_object(entity, first)
    if value_object is None:
        raise RejectionError(
            NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT,
            f"{path!r}: {first!r} is not a value object declared on {entity.name}",
        )
    *intermediates, leaf = rest
    current = value_object
    for segment in intermediates:
        nested = find_nested_value_object(current, segment)
        if nested is None:
            raise RejectionError(
                NESTED_PATH_UNKNOWN_MEMBER,
                f"{path!r}: {segment!r} is not a nested value object of {current['name']!r}",
            )
        current = nested
    attribute = find_attribute(current, leaf)
    if attribute is None:
        raise RejectionError(
            NESTED_PATH_UNKNOWN_MEMBER,
            f"{path!r}: {leaf!r} is not an attribute of {current['name']!r}",
        )
    return attribute


def resolve_value_object_ref(entity: Entity, path: str) -> dict[str, Any]:
    """Resolve a ``Class.valueObject(.valueObject)*`` path to its terminal value object.

    Used by ``nestedExists`` / ``nestedNotExists`` (the path ends AT a value object,
    not an attribute). Raises :class:`RejectionError` on the first undeclared segment.
    """
    _cls, first, *rest = path.split(".")
    value_object = find_top_value_object(entity, first)
    if value_object is None:
        raise RejectionError(
            NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT,
            f"{path!r}: {first!r} is not a value object declared on {entity.name}",
        )
    current = value_object
    for segment in rest:
        nested = find_nested_value_object(current, segment)
        if nested is None:
            raise RejectionError(
                NESTED_PATH_UNKNOWN_MEMBER,
                f"{path!r}: {segment!r} is not a nested value object of {current['name']!r}",
            )
        current = nested
    return current


def resolve_element_ref(value_object: dict[str, Any], path: str) -> dict[str, Any]:
    """Resolve an ELEMENT-RELATIVE path (no leading ``Class.valueObject``) to a leaf.

    The subject is one element of a ``many`` value object bound by an enclosing
    ``nestedExists`` / ``nestedNotExists`` ``where`` (same-element semantics). Each
    segment resolves against the element's declared structure; the leaf is an
    attribute. Raises :class:`RejectionError` on an undeclared segment.
    """
    *intermediates, leaf = path.split(".")
    current = value_object
    for segment in intermediates:
        nested = find_nested_value_object(current, segment)
        if nested is None:
            raise RejectionError(
                NESTED_PATH_UNKNOWN_MEMBER,
                f"element path {path!r}: {segment!r} is not a nested value object of "
                f"{current['name']!r}",
            )
        current = nested
    attribute = find_attribute(current, leaf)
    if attribute is None:
        raise RejectionError(
            NESTED_PATH_UNKNOWN_MEMBER,
            f"element path {path!r}: {leaf!r} is not an attribute of {current['name']!r}",
        )
    return attribute
