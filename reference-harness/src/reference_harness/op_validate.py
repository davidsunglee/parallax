"""Model-aware OPERATION validation for the ``rejected`` case shape (m-op-algebra).

An operation `rejected` case (m-case-format, resolved Q7) carries a SCHEMA-VALID
`m-op-algebra` node that a model-aware resolver MUST refuse **before any SQL is
emitted**. This module walks the operation tree — mostly against the queried
entity's declared value-object structure — and raises
:class:`~reference_harness.value_object_resolve.RejectionError` naming the violated
normative rule:

* a **range** predicate whose `lower` bound is strictly greater than its `upper`,
  comparing same-kind literals only (m-op-algebra bound ordering); this one needs no
  model, since the two authored literals carry everything the rule compares;
* a nested-predicate **path** whose first segment is not a declared value object,
  or whose intermediate / leaf segment is undeclared (m-op-algebra resolver MUST);
* a nested-comparison / membership **literal** whose type mismatches the leaf
  attribute's declared neutral type (m-op-algebra typed-literal MUST);
* a **`deepFetch`** path segment or a **relationship navigation** (`navigate` /
  `exists` / `notExists`) aimed at a value object — value objects are reached only
  by value through their owner, never navigated to (m-value-object contract 4,
  m-deep-fetch / m-navigate);
* a **find() rooted at a value object** — a value object is not a queryable root
  entity (m-value-object contract 5), surfaced here as an attribute reference whose
  class segment names a declared value object rather than the entity, or as a
  ``deepFetch`` path-ROOT narrow whose `entity` / `to` names one: the root position
  a guard resolves at is the queried position itself.

The reference harness (a non-normative oracle) runs this so the reference
implementation actually rejects what the `rejected` cases pin — the same refusal
each language implementation must make.

Scope — value-object rules are enforced at ANY depth within the queried entity's
own operation tree. :func:`validate_operation` descends through the SAME-entity
boolean combinators (``and`` / ``or`` / ``not`` / ``group``) and the result-directive
wrappers (``orderBy`` / ``limit`` / ``distinct`` / ``asOf`` …), so a nested-predicate
violation (an undeclared path segment, a mistyped literal, a value-object misuse) is
rejected wherever the offending node appears — buried inside an ``and`` just as at
the top level. The combinators do not change the root entity, so resolution stays
against the same declared value-object structure throughout.

Tracked scope limitation (future extension): value-object rules inside a
RELATED-entity sub-operation — a navigation's inner operation (``navigationFilter.op``
/ the ``op`` a ``navigate`` / ``exists`` / ``notExists`` carries, which resolves
against a DIFFERENT entity) — are NOT enforced here. That would require cross-entity
model resolution (following the relationship to its target entity's declared
structure); no corpus case exercises it, and value objects are never navigation
targets (they have no identity to correlate), so :func:`validate_operation` refuses a
value-object-TARGETED navigation but does not recurse INTO a related entity's
sub-operation. Enforcing nested value-object rules across a relationship boundary is
a documented future extension.
"""

from __future__ import annotations

from typing import Any

from .case import Entity
from .operation_references import ATTRIBUTE_REFERENCE_TAGS
from .value_object_resolve import (
    BETWEEN_BOUNDS_INVERTED,
    DEEP_FETCH_VALUE_OBJECT_SEGMENT,
    FIND_ROOT_VALUE_OBJECT,
    NAVIGATE_VALUE_OBJECT_TARGET,
    NESTED_LITERAL_TYPE_MISMATCH,
    RejectionError,
    bounds_inverted,
    find_top_value_object,
    literal_matches_type,
    resolve_element_ref,
    resolve_nested_ref,
    resolve_value_object_ref,
)

# The flat nested comparison family (single-key nodes wrapping a {path, value} body).
_NESTED_COMPARISON_TAGS = frozenset(
    {"nestedEq", "nestedNotEq", "nestedGt", "nestedGte", "nestedLt", "nestedLte"}
)


def validate_operation(entity: Entity, operation: Any) -> None:
    """Reject *operation* pre-SQL if it misuses a value object; else return.

    Raises :class:`RejectionError` (``.rule`` one of the operation rules) on the
    first violation. An operation with no value-object misuse returns quietly — this
    is used ONLY for ``rejected`` cases, so it need not fully validate every valid
    operation, only reject the specific negative inputs the corpus pins.

    The walk descends through the SAME-entity boolean combinators
    (``and`` / ``or`` / ``not`` / ``group``) and the directive / temporal wrappers, so
    a violation is caught at ANY depth in the queried entity's operation tree, not
    only at the top level. It does NOT recurse into a related-entity sub-operation
    (a navigation's inner op) — a tracked scope limitation (see the module docstring).
    """
    _walk(entity, operation)


def _walk(entity: Entity, node: Any) -> None:
    if not isinstance(node, dict) or len(node) != 1:
        return
    tag, body = next(iter(node.items()))
    if tag in _NESTED_COMPARISON_TAGS:
        _check_nested_comparison(entity, body)
    elif tag == "nestedIn":
        _check_nested_membership(entity, body)
    elif tag in ("nestedIsNull", "nestedIsNotNull"):
        resolve_nested_ref(entity, body["path"])
    elif tag in ("nestedExists", "nestedNotExists"):
        _check_nested_exists(entity, body)
    elif tag == "between":
        _check_between(entity, body)
    elif tag in ("navigate", "exists", "notExists"):
        _check_navigation(entity, body)
    elif tag == "deepFetch":
        _check_deep_fetch(entity, body)
        _walk(entity, body.get("operand"))
    elif tag in ATTRIBUTE_REFERENCE_TAGS:
        _check_find_root(entity, body.get("attr"))
    elif tag in ("and", "or"):
        for operand in body.get("operands", []):
            _walk(entity, operand)
    elif tag in ("not", "group", "distinct"):
        _walk(entity, body.get("operand"))
    elif tag == "orderBy":
        _walk(entity, body.get("operand"))
        for key in body.get("keys", []):
            if isinstance(key, dict):
                _check_find_root(entity, key.get("attr"))
    elif tag == "limit":
        _walk(entity, body.get("operand"))
    elif tag in ("asOf", "asOfRange", "history"):
        _walk(entity, body.get("operand"))
    # all / none / aggregation nodes carry no value-object reference to validate.


def _check_between(entity: Entity, body: dict[str, Any]) -> None:
    """A range predicate's own two checks: its subject, then its bound ordering."""
    _check_find_root(entity, body.get("attr"))
    _check_bound_ordering(body.get("attr"), body.get("lower"), body.get("upper"))


def _check_bound_ordering(subject: Any, lower: Any, upper: Any) -> None:
    """Reject a range whose bounds are inverted (m-op-algebra bound ordering)."""
    if bounds_inverted(lower, upper):
        raise RejectionError(
            BETWEEN_BOUNDS_INVERTED,
            f"{subject!r}: lower bound {lower!r} is greater than upper bound {upper!r}, "
            f"so the range is empty and no row can satisfy it",
        )


def _check_nested_comparison(entity: Entity, body: dict[str, Any]) -> None:
    attribute = resolve_nested_ref(entity, body["path"])
    value = body.get("value")
    if not literal_matches_type(value, attribute.get("type")):
        raise RejectionError(
            NESTED_LITERAL_TYPE_MISMATCH,
            f"{body['path']!r}: literal {value!r} does not match declared type "
            f"{attribute.get('type')!r}",
        )


def _check_nested_membership(entity: Entity, body: dict[str, Any]) -> None:
    attribute = resolve_nested_ref(entity, body["path"])
    for value in body.get("values", []):
        if not literal_matches_type(value, attribute.get("type")):
            raise RejectionError(
                NESTED_LITERAL_TYPE_MISMATCH,
                f"{body['path']!r}: list literal {value!r} does not match declared type "
                f"{attribute.get('type')!r}",
            )


def _check_nested_exists(entity: Entity, body: dict[str, Any]) -> None:
    value_object = resolve_value_object_ref(entity, body["path"])
    where = body.get("where")
    if where is not None:
        _walk_element(value_object, where)


def _walk_element(value_object: dict[str, Any], node: Any) -> None:
    """Validate a scoped `where` sub-predicate against one array element's structure."""
    if not isinstance(node, dict) or len(node) != 1:
        return
    tag, body = next(iter(node.items()))
    if tag in _NESTED_COMPARISON_TAGS:
        attribute = resolve_element_ref(value_object, body["path"])
        if not literal_matches_type(body.get("value"), attribute.get("type")):
            raise RejectionError(
                NESTED_LITERAL_TYPE_MISMATCH,
                f"element {body['path']!r}: literal {body.get('value')!r} does not match "
                f"declared type {attribute.get('type')!r}",
            )
    elif tag == "nestedIn":
        attribute = resolve_element_ref(value_object, body["path"])
        for value in body.get("values", []):
            if not literal_matches_type(value, attribute.get("type")):
                raise RejectionError(
                    NESTED_LITERAL_TYPE_MISMATCH,
                    f"element {body['path']!r}: list literal {value!r} does not match "
                    f"declared type {attribute.get('type')!r}",
                )
    elif tag in ("nestedIsNull", "nestedIsNotNull"):
        resolve_element_ref(value_object, body["path"])
    elif tag in ("and", "or"):
        for operand in body.get("operands", []):
            _walk_element(value_object, operand)
    elif tag in ("not", "group"):
        _walk_element(value_object, body.get("operand"))


def _check_navigation(entity: Entity, body: dict[str, Any]) -> None:
    rel = body.get("rel", "")
    cls, _, member = rel.partition(".")
    if cls == entity.name and find_top_value_object(entity, member) is not None:
        raise RejectionError(
            NAVIGATE_VALUE_OBJECT_TARGET,
            f"relationship navigation targets value object {member!r} on {entity.name} — "
            f"a value object has no identity to correlate and is never a navigation target",
        )


def _check_deep_fetch(entity: Entity, body: dict[str, Any]) -> None:
    for path in body.get("paths", []):
        _check_path_root_narrow(entity, path.get("narrow"))
        for segment in path.get("segments", []):
            # A path segment is a closed object ``{rel, narrow?}`` (m-op-algebra);
            # the value-object misuse rule is about the traversed relationship ref.
            rel = segment["rel"] if isinstance(segment, dict) else segment
            cls, _, member = rel.partition(".")
            if cls == entity.name and find_top_value_object(entity, member) is not None:
                raise RejectionError(
                    DEEP_FETCH_VALUE_OBJECT_SEGMENT,
                    f"deepFetch path segment {rel!r} names value object {member!r} — "
                    f"a value-object segment is invalid in a deep-fetch path",
                )


def _check_path_root_narrow(entity: Entity, narrow: Any) -> None:
    """Reject a deep-fetch path-root guard aimed at a value object.

    A path-root ``{entity, to}`` guard resolves at the QUERIED position, so both
    members name Entities: `entity` the polymorphic position and each `to` entry a
    subtype of it. The subtype-position rules themselves (the clamp, the empty and
    outside-position rejections) belong to the inheritance walk; what belongs here
    is the value-object rule the queried root already carries — a value object has
    no identity, no position, and no concrete subtypes, so it is no more guardable
    than it is queryable.
    """
    if not isinstance(narrow, dict):
        return
    to = narrow.get("to")
    names = [narrow.get("entity"), *(to if isinstance(to, list) else [])]
    for name in names:
        if isinstance(name, str) and find_top_value_object(entity, name) is not None:
            raise RejectionError(
                FIND_ROOT_VALUE_OBJECT,
                f"deepFetch path-root narrow names value object {name!r} on "
                f"{entity.name} — a value object is not a queryable root position and "
                f"has no concrete subtypes to guard",
            )


def _check_find_root(entity: Entity, attr: Any) -> None:
    if not isinstance(attr, str):
        return
    cls = attr.partition(".")[0]
    if find_top_value_object(entity, cls) is not None:
        raise RejectionError(
            FIND_ROOT_VALUE_OBJECT,
            f"attribute reference {attr!r} roots the query at value object {cls!r} — "
            f"a value object is not a queryable root entity; query it through its owner",
        )
