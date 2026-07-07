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
  ``m-op-algebra`` (the nested-predicate resolver) or the ``m-value-object``
  materialization/navigation contract. The schema pins the SAME vocabulary in the
  ``then.rejectedRule`` enum; the two MUST agree.
* The **member resolvers** — resolve a dotted nested path / value-object-terminated
  path / element-relative path against an entity's *declared* recursive value-object
  structure, raising :class:`RejectionError` on the first undeclared segment, plus
  the typed-literal check.

These are non-normative grading machinery: they let the reference harness make the
reference implementation actually reject what the ``rejected`` cases pin, exactly as
each language implementation must.
"""

from __future__ import annotations

from typing import Any

from .case import Entity

# --- rule vocabulary --------------------------------------------------------
#
# The closed set of `then.rejectedRule` identifiers. Kept in lockstep with the
# `then.rejectedRule` enum in compatibility-case.schema.json (m-case-format).

# Operation rules (m-op-algebra nested-predicate resolver MUSTs + m-value-object
# materialization/navigation contract clauses 4/5).
NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT = "nested-path-first-segment-not-value-object"
NESTED_PATH_UNKNOWN_MEMBER = "nested-path-unknown-member"
NESTED_LITERAL_TYPE_MISMATCH = "nested-literal-type-mismatch"
DEEP_FETCH_VALUE_OBJECT_SEGMENT = "deep-fetch-value-object-segment"
NAVIGATE_VALUE_OBJECT_TARGET = "navigate-value-object-target"
FIND_ROOT_VALUE_OBJECT = "find-root-value-object"

# Write rules (m-value-object write validation).
WRITE_REQUIRED_ATTRIBUTE_MISSING = "write-required-attribute-missing"
WRITE_REQUIRED_VALUE_OBJECT_MISSING = "write-required-value-object-missing"
WRITE_VALUE_TYPE_MISMATCH = "write-value-type-mismatch"

REJECTED_RULES: frozenset[str] = frozenset(
    {
        NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT,
        NESTED_PATH_UNKNOWN_MEMBER,
        NESTED_LITERAL_TYPE_MISMATCH,
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

_STRING_TYPES = frozenset({"string", "text", "char", "varchar", "uuid"})
_TEMPORAL_TYPES = frozenset({"timestamp", "date", "time", "datetime"})
_INT_TYPES = frozenset({"int8", "int16", "int32", "int64", "int", "integer"})
_FLOAT_TYPES = frozenset({"float32", "float64", "float", "double", "decimal", "numeric"})
_BOOL_TYPES = frozenset({"boolean", "bool"})


def literal_matches_type(value: Any, neutral_type: str | None) -> bool:
    """Whether a literal / document value is compatible with a declared neutral type.

    Used both for a nested comparison's literal (`m-op-algebra` typed-literal MUST)
    and a write document field's value (`m-value-object` write validation). A
    ``null`` is always type-acceptable — nullability is a SEPARATE check (required
    vs optional), never a type mismatch. An UNKNOWN neutral type is accepted rather
    than guessed, so the validator never false-rejects a type it does not model.
    """
    if value is None:
        return True
    kind = (neutral_type or "").lower()
    if kind in _STRING_TYPES or kind in _TEMPORAL_TYPES:
        return isinstance(value, str)
    if kind in _INT_TYPES:
        return isinstance(value, int) and not isinstance(value, bool)
    if kind in _FLOAT_TYPES:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind in _BOOL_TYPES:
        return isinstance(value, bool)
    return True


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
