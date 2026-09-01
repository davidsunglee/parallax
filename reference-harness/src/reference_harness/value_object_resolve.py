"""Model-aware value-object resolution + the pre-SQL rejection vocabulary.

Shared primitives for the two negative-validation validators
(:mod:`object_query_validate` for queries, :mod:`write_validate` for writes) that back
the ``rejected`` case shape (m-case-format, resolved Q7). A ``rejected`` case
asserts a model-aware validator refuses an input **before any SQL is emitted**,
naming the violated normative rule in ``then.rejectedRule``.

This module owns three things:

* :class:`RejectionError` — raised by a validator with the ``rule`` it violated.
* The closed **rule vocabulary** (:data:`REJECTED_RULES`) — the small set of
  ``then.rejectedRule`` identifiers, each naming a normative MUST from
  ``m-predicate`` (predicate bound ordering and the nested-predicate resolver) or
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

from typing import Any

from .case import Entity
from .portable_literal import PortableLiteralError, decode
from .references import split_reference

# --- rule vocabulary --------------------------------------------------------
#
# The closed set of `then.rejectedRule` identifiers. Kept in lockstep with the
# `then.rejectedRule` enum in compatibility-case.schema.json (m-case-format).

# PredicateNode rules (m-predicate bound-ordering + nested-predicate resolver MUSTs,
# m-value-object materialization/navigation contract clauses 4/5).
BETWEEN_BOUNDS_INVERTED = "between-bounds-inverted"
NULL_CHECK_NON_NULLABLE_MEMBER = "null-check-non-nullable-member"
NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT = "nested-path-first-segment-not-value-object"
NESTED_PATH_UNKNOWN_MEMBER = "nested-path-unknown-member"
NEUTRAL_LITERAL_TYPE_MISMATCH = "neutral-literal-type-mismatch"
NEUTRAL_LITERAL_NONCANONICAL = "neutral-literal-noncanonical"
NEUTRAL_LITERAL_OUT_OF_SPACE = "neutral-literal-out-of-space"
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
        NULL_CHECK_NON_NULLABLE_MEMBER,
        NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT,
        NESTED_PATH_UNKNOWN_MEMBER,
        NEUTRAL_LITERAL_TYPE_MISMATCH,
        NEUTRAL_LITERAL_NONCANONICAL,
        NEUTRAL_LITERAL_OUT_OF_SPACE,
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
# timestamp, uuid, json, and decimal(precision,scale). Membership is decided per
# type against the portable literal's own DECODE, never against a loose category: a
# category guess leaves the vocabulary open, so a `decimal(12,2)` position admits a
# truth value and a `bytes` position an array — spellings the space holds no value
# for.


def literal_matches_type(value: Any, neutral_type: str | None) -> bool:
    """Whether a literal / document value spells a member of a declared neutral type.

    Used both for a nested comparison's literal (`m-predicate` typed-literal MUST)
    and a write row's scalar leaf (`m-value-object` write validation). A ``null`` is
    always type-acceptable — nullability is a SEPARATE check (required vs optional),
    never a type mismatch.

    The domain is the PORTABLE literal, the spelling a case authors, and membership
    asks whether that literal DECODES to a value of the space (`m-core`,
    `m-document-codec`, `m-case-format` "What decides a bare write row"). Decoding is
    many-to-one where encoding is one-to-one: the document form a value is STORED in
    is its single canonical spelling, while several authored spellings name the same
    value. :mod:`portable_literal` writes out the whole admitted grammar of the
    string-carried spaces, so what is in space is a stated contract rather than
    whatever a host parser happens to take.

    A literal that decodes to no member is out of space: an integer beyond its
    declared width, a number whose magnitude the declared float width cannot hold, a
    decimal the declared precision and scale cannot hold exactly, text with no UTF-8
    encoding, and any spelling outside the portable grammar.

    A type spelling the closed vocabulary does not carry is accepted rather than
    guessed at — such a descriptor never passed schema validation, so refusing it
    here would report a write rule for what is a malformed model.
    """
    if value is None:
        return True
    if neutral_type is None:
        return True
    try:
        decode(value, neutral_type)
    except PortableLiteralError:
        return False
    return True


def decode_typed_literal(value: Any, neutral_type: str | None, subject: str) -> Any:
    """Decode a resolved typed literal or raise its stable surface rule."""
    if neutral_type is None:
        return value
    try:
        return decode(value, neutral_type)
    except PortableLiteralError as exc:
        rule = f"neutral-literal-{exc.reason}"
        if rule not in REJECTED_RULES:
            raise AssertionError(f"unknown portable literal reason {exc.reason!r}") from exc
        raise RejectionError(
            rule,
            f"{subject}: literal {value!r} is {exc.reason} for declared type {neutral_type!r}",
        ) from exc


def is_string_member(neutral_type: str | None) -> bool:
    """Whether a declared member's neutral type is m-core's ``String``.

    The `m-predicate` non-string-member rule, which the five nested string
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

    The operands have already decoded under one resolved declared type. Equal
    bounds name the single-value range and are never inverted.
    """
    try:
        return lower > upper
    except TypeError:
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
    _cls, members = split_reference(path)
    first, *rest = members
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
    _cls, members = split_reference(path)
    first, *rest = members
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
