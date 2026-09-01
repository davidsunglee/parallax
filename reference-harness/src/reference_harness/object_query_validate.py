"""Model-aware Object Query validation for the ``rejected`` case shape.

A query `rejected` case (m-case-format, resolved Q7) carries a SCHEMA-VALID
`m-object-query` document that a model-aware resolver MUST refuse **before any
SQL is emitted**. This module walks that document — mostly against the queried
entity's declared value-object structure — and raises
:class:`~reference_harness.value_object_resolve.RejectionError` naming the violated
normative rule:

* a **range** predicate whose `lower` bound is strictly greater than its `upper`,
  comparing same-kind literals only (m-predicate bound ordering) — at the top level
  and at both nested scopes. At the top level the rule needs no model, since the two
  authored literals carry everything it compares; nested, the path and both typed
  bounds resolve FIRST, so a mistyped bound is named as a type mismatch rather than
  ordered as a raw literal;
* a nested-predicate **path** whose first segment is not a declared value object,
  or whose intermediate / leaf segment is undeclared (m-predicate resolver MUST);
* a nested-comparison / range / membership **literal** whose type mismatches the leaf
  attribute's declared neutral type (m-predicate typed-literal MUST);
* a nested **string predicate** whose resolved leaf is not a `String` member
  (m-predicate non-string-member MUST) — checked ahead of the typed-literal rule at
  both nested scopes, because the portable literal carries a `date` / `uuid` /
  `timestamp` value as a `string` and the literal rule alone would accept it;
* an **Include Path** segment or a **relationship navigation** (`navigate` /
  `exists` / `notExists`) aimed at a value object — value objects are reached only
  by value through their owner, never navigated to (m-value-object contract 4,
  m-deep-fetch / m-navigate);
* a **find() rooted at a value object** — a value object is not a queryable root
  entity (m-value-object contract 5), surfaced here as an attribute reference whose
  class segment names a declared value object rather than the entity, or as a
  Subtype Selection at the queried position naming one: the position a source
  guard resolves at is the queried position itself.

The reference harness (a non-normative oracle) runs this so the reference
implementation actually rejects what the `rejected` cases pin — the same refusal
each language implementation must make.

Scope — value-object rules are enforced at ANY depth within the queried entity's
own predicate. :func:`validate_object_query` checks every clause and descends
through the SAME-entity boolean combinators (``and`` / ``or`` / ``not`` /
``group``) and the Predicate-scoped ``narrow``, so a nested-predicate
violation (an undeclared path segment, a mistyped literal, a value-object misuse) is
rejected wherever the offending node appears — buried inside an ``and`` just as at
the top level. The combinators do not change the root entity, so resolution stays
against the same declared value-object structure throughout.

Tracked scope limitation (future extension): value-object rules inside a
RELATED-entity sub-predicate — a navigation's inner predicate (``navigationFilter.op``
/ the ``op`` a ``navigate`` / ``exists`` / ``notExists`` carries, which resolves
against a DIFFERENT entity) — are NOT enforced here. That would require cross-entity
model resolution (following the relationship to its target entity's declared
structure); no corpus case exercises it, and value objects are never navigation
targets (they have no identity to correlate), so :func:`validate_object_query` refuses a
value-object-TARGETED navigation but does not recurse INTO a related entity's
sub-predicate. Enforcing nested value-object rules across a relationship boundary is
a documented future extension.
"""

from __future__ import annotations

from typing import Any

from .case import Entity
from .query_references import ATTRIBUTE_REFERENCE_TAGS
from .value_object_resolve import (
    BETWEEN_BOUNDS_INVERTED,
    DEEP_FETCH_VALUE_OBJECT_SEGMENT,
    FIND_ROOT_VALUE_OBJECT,
    NAVIGATE_VALUE_OBJECT_TARGET,
    NESTED_STRING_PREDICATE_NON_STRING_MEMBER,
    NULL_CHECK_NON_NULLABLE_MEMBER,
    RejectionError,
    bounds_inverted,
    decode_typed_literal,
    find_top_value_object,
    is_string_member,
    resolve_element_ref,
    resolve_nested_ref,
    resolve_value_object_ref,
)

# The flat nested comparison family (single-key nodes wrapping a {path, value} body).
_NESTED_COMPARISON_TAGS = frozenset(
    {"nestedEq", "nestedNotEq", "nestedGt", "nestedGte", "nestedLt", "nestedLte"}
)
# The flat nested membership family (a {path, values} body); the negated form carries
# the same typed-literal obligation as the positive one.
_NESTED_MEMBERSHIP_TAGS = frozenset({"nestedIn", "nestedNotIn"})
# The flat nested string family (a {path, value, caseInsensitive?} body). Pattern
# grammar and case folding are lowering concerns; what validation owns is the pair of
# ordered rules below.
_NESTED_STRING_TAGS = frozenset(
    {"nestedLike", "nestedNotLike", "nestedStartsWith", "nestedEndsWith", "nestedContains"}
)
_STRING_TAGS = frozenset({"like", "notLike", "startsWith", "endsWith", "contains"})


def validate_object_query(entity: Entity, query: Any) -> None:
    """Reject *query* pre-SQL if it misuses a value object; else return.

    Raises :class:`RejectionError` (``.rule`` one of the query rules) on the first
    violation. A query with no value-object misuse returns quietly — this is used
    ONLY for ``rejected`` cases, so it need not fully validate every valid query,
    only reject the specific negative inputs the corpus pins.

    Every clause is checked: the predicate, each Sort Key's own root, each Include
    Path's source guard and hops. The predicate walk descends through the
    SAME-entity boolean combinators (``and`` / ``or`` / ``not`` / ``group``) and the
    Predicate-scoped ``narrow``, so a violation is caught at ANY depth. It does NOT
    recurse into a related-entity sub-predicate (a navigation's inner op) — a
    tracked scope limitation (see the module docstring).
    """
    if not isinstance(query, dict):
        return
    validate_predicate(entity, query.get("predicate"))
    _check_source_guard(entity, query.get("narrowTo"))
    for key in query.get("orderBy", []) or []:
        if isinstance(key, dict):
            _check_find_root(entity, key.get("attr"))
    _check_includes(entity, query.get("includes", []) or [])


def validate_predicate(entity: Entity, predicate: Any) -> None:
    """Reject *predicate* pre-SQL if it misuses a value object; else return.

    The clause-free half of :func:`validate_object_query`, and what a
    predicate-selected write's own bare predicate is judged by.
    """
    _walk(entity, predicate)


def _walk(entity: Entity, node: Any) -> None:
    if not isinstance(node, dict) or len(node) != 1:
        return
    tag, body = next(iter(node.items()))
    if tag in _NESTED_COMPARISON_TAGS:
        _check_nested_comparison(entity, body)
    elif tag == "nestedBetween":
        _check_range_predicate(
            resolve_nested_ref(entity, body["path"]),
            body,
            subject=body["path"],
        )
    elif tag in _NESTED_MEMBERSHIP_TAGS:
        _check_nested_membership(entity, body)
    elif tag in _NESTED_STRING_TAGS:
        _check_string_predicate(
            resolve_nested_ref(entity, body["path"]), body, subject=body["path"]
        )
    elif tag in ("nestedIsNull", "nestedIsNotNull"):
        _check_null_check(resolve_nested_ref(entity, body["path"]), body["path"])
    elif tag in ("nestedExists", "nestedNotExists"):
        _check_nested_exists(entity, body)
    elif tag == "between":
        _check_between(entity, body)
    elif tag in ("navigate", "exists", "notExists"):
        _check_navigation(entity, body)
    elif tag in ATTRIBUTE_REFERENCE_TAGS:
        subject = body.get("attr")
        _check_find_root(entity, subject)
        if not isinstance(subject, str):
            return
        attribute = entity.attribute_by_name(subject.rpartition(".")[2])
        if tag in ("isNull", "isNotNull"):
            _check_null_check(attribute, subject)
        elif tag in _STRING_TAGS:
            _check_string_predicate(attribute, body, subject=subject)
        elif tag in ("in", "notIn"):
            for value in body.get("values", []):
                decode_typed_literal(value, attribute.get("type"), repr(subject))
        else:
            decode_typed_literal(body.get("value"), attribute.get("type"), repr(subject))
    elif tag in ("and", "or"):
        for operand in body.get("operands", []):
            _walk(entity, operand)
    elif tag in ("not", "group", "narrow"):
        _walk(entity, body.get("operand"))


def _check_between(entity: Entity, body: dict[str, Any]) -> None:
    """A range predicate's own two checks: its subject, then its bound ordering."""
    subject = body.get("attr")
    _check_find_root(entity, subject)
    if not isinstance(subject, str):
        return
    attribute = entity.attribute_by_name(subject.rpartition(".")[2])
    _check_range_predicate(attribute, body, subject=subject)


def _check_bound_ordering(subject: Any, lower: Any, upper: Any) -> None:
    """Reject a range whose bounds are inverted (m-predicate bound ordering)."""
    if bounds_inverted(lower, upper):
        raise RejectionError(
            BETWEEN_BOUNDS_INVERTED,
            f"{subject!r}: lower bound {lower!r} is greater than upper bound {upper!r}, "
            f"so the range is empty and no row can satisfy it",
        )


def _check_nested_comparison(entity: Entity, body: dict[str, Any]) -> None:
    attribute = resolve_nested_ref(entity, body["path"])
    decode_typed_literal(body.get("value"), attribute.get("type"), repr(body["path"]))


def _check_null_check(attribute: dict[str, Any], subject: str) -> None:
    if not attribute.get("nullable", False):
        raise RejectionError(
            NULL_CHECK_NON_NULLABLE_MEMBER,
            f"{subject!r}: isNull/isNotNull is invalid for a non-nullable member",
        )


def _check_range_predicate(
    attribute: dict[str, Any], body: dict[str, Any], *, subject: str
) -> None:
    """A nested range's bound checks, in the order m-predicate fixes: both typed
    bounds, then the bound ordering — the path having already resolved ``attribute``.

    One function for both scopes, because only the resolution of ``attribute``
    differs. Ordering the bounds last is load-bearing: a mistyped bound is named as a
    type mismatch rather than ordered as a raw literal of some unrelated kind.
    """
    lower = decode_typed_literal(
        body.get("lower"), attribute.get("type"), f"{subject!r} lower bound"
    )
    upper = decode_typed_literal(
        body.get("upper"), attribute.get("type"), f"{subject!r} upper bound"
    )
    _check_bound_ordering(subject, lower, upper)


def _check_nested_membership(entity: Entity, body: dict[str, Any]) -> None:
    attribute = resolve_nested_ref(entity, body["path"])
    for value in body.get("values", []):
        decode_typed_literal(value, attribute.get("type"), repr(body["path"]))


def _check_string_predicate(
    attribute: dict[str, Any], body: dict[str, Any], *, subject: str
) -> None:
    """A nested string predicate's two rules, in the order m-predicate fixes: the
    resolved member's own type, then the literal's.

    One function for both scopes, because only the resolution of ``attribute``
    differs. Ordering the member first is load-bearing: the literal rule reads a
    `date`/`time`/`timestamp`/`uuid`/`bytes` member permissively as a string, so a
    string predicate aimed at one would otherwise be accepted rather than named.
    """
    declared = attribute.get("type")
    if not is_string_member(declared):
        raise RejectionError(
            NESTED_STRING_PREDICATE_NON_STRING_MEMBER,
            f"{subject!r}: a string predicate reads text, but the member's declared type "
            f"is {declared!r}, not 'string'",
        )
    decode_typed_literal(body.get("value"), declared, repr(subject))


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
        decode_typed_literal(body.get("value"), attribute.get("type"), f"element {body['path']!r}")
    elif tag == "nestedBetween":
        _check_range_predicate(
            resolve_element_ref(value_object, body["path"]),
            body,
            subject=f"element {body['path']}",
        )
    elif tag in _NESTED_MEMBERSHIP_TAGS:
        attribute = resolve_element_ref(value_object, body["path"])
        for value in body.get("values", []):
            decode_typed_literal(value, attribute.get("type"), f"element {body['path']!r}")
    elif tag in _NESTED_STRING_TAGS:
        _check_string_predicate(
            resolve_element_ref(value_object, body["path"]),
            body,
            subject=f"element {body['path']}",
        )
    elif tag in ("nestedIsNull", "nestedIsNotNull"):
        _check_null_check(resolve_element_ref(value_object, body["path"]), body["path"])
    elif tag in ("and", "or"):
        for operand in body.get("operands", []):
            _walk_element(value_object, operand)
    elif tag in ("not", "group"):
        _walk_element(value_object, body.get("operand"))


def _check_navigation(entity: Entity, body: dict[str, Any]) -> None:
    rel = body.get("rel", "")
    cls, _, member = rel.rpartition(".")
    if _names(entity, cls) and find_top_value_object(entity, member) is not None:
        raise RejectionError(
            NAVIGATE_VALUE_OBJECT_TARGET,
            f"relationship navigation targets value object {member!r} on {entity.name} — "
            f"a value object has no identity to correlate and is never a navigation target",
        )


def _check_includes(entity: Entity, paths: Any) -> None:
    for path in paths:
        if not isinstance(path, dict):
            continue
        _check_source_guard(entity, path.get("appliesTo"))
        for segment in path.get("segments", []):
            # An Include Segment is a closed object ``{rel, narrowTo?}``; the
            # value-object misuse rule is about the traversed relationship ref.
            rel = segment["rel"] if isinstance(segment, dict) else segment
            cls, _, member = rel.rpartition(".")
            if _names(entity, cls) and find_top_value_object(entity, member) is not None:
                raise RejectionError(
                    DEEP_FETCH_VALUE_OBJECT_SEGMENT,
                    f"include segment {rel!r} names value object {member!r} — "
                    f"a value-object segment is invalid in an Include Path",
                )


def _check_source_guard(entity: Entity, selection: Any) -> None:
    """Reject a Subtype Selection at the QUERIED position aimed at a value object.

    Whole-result narrowing and an Include Path's source guard both resolve at the
    queried position, so every alternative names an Entity. The subtype-position
    rules themselves (the empty and outside-position rejections) belong to the
    inheritance walk; what belongs here is the value-object rule the queried root
    already carries — a value object has no identity, no position, and no concrete
    subtypes, so it is no more selectable than it is queryable.
    """
    if not isinstance(selection, list):
        return
    for name in selection:
        if isinstance(name, str) and find_top_value_object(entity, name) is not None:
            raise RejectionError(
                FIND_ROOT_VALUE_OBJECT,
                f"Subtype Selection names value object {name!r} on "
                f"{entity.name} — a value object is not a queryable root position and "
                f"has no concrete subtypes to select",
            )


def _names(entity: Entity, spelling: str) -> bool:
    """Whether ``spelling`` — bare or canonical — names ``entity`` itself."""
    return spelling in (entity.name, entity.canonical_name)


def _check_find_root(entity: Entity, attr: Any) -> None:
    # An `attr` is `<Entity>.<member>`, so its root is everything before the LAST
    # dot: a value-object occurrence name reaching the root position (`address.city`)
    # lands there whole, and a canonical Entity spelling does too.
    if not isinstance(attr, str):
        return
    cls = attr.rpartition(".")[0]
    if find_top_value_object(entity, cls) is not None:
        raise RejectionError(
            FIND_ROOT_VALUE_OBJECT,
            f"attribute reference {attr!r} roots the query at value object {cls!r} — "
            f"a value object is not a queryable root entity; query it through its owner",
        )
