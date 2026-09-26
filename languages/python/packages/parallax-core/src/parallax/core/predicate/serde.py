from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import cast

from parallax.core.predicate._nodes import (
    All,
    And,
    Between,
    Comparison,
    ComparisonOp,
    Exists,
    Group,
    Membership,
    MembershipOp,
    Narrow,
    Navigate,
    NestedComparison,
    NestedComparisonOp,
    NestedExists,
    NestedMembership,
    NestedMembershipOp,
    NestedNotExists,
    NestedNullCheck,
    NestedNullOp,
    NestedRange,
    NestedStringMatch,
    NestedStringOp,
    NoneOp,
    Not,
    NotExists,
    NullCheck,
    NullOp,
    Or,
    PredicateNode,
    Scalar,
    StringMatch,
    StringOp,
    canonical_subtype_selection,
)

__all__ = ["CanonicalDocumentError", "deserialize", "serialize"]

_COMPARISONS: frozenset[str] = frozenset(
    {"eq", "notEq", "greaterThan", "greaterThanEquals", "lessThan", "lessThanEquals"}
)
_NULLS: frozenset[str] = frozenset({"isNull", "isNotNull"})
_STRINGS: frozenset[str] = frozenset({"like", "notLike", "startsWith", "endsWith", "contains"})
_MEMBERSHIPS: frozenset[str] = frozenset({"in", "notIn"})
_NESTED_CMP: frozenset[str] = frozenset(
    {"nestedEq", "nestedNotEq", "nestedGt", "nestedGte", "nestedLt", "nestedLte"}
)
_NESTED_RANGE: frozenset[str] = frozenset({"nestedBetween"})
_NESTED_MEMBERSHIPS: frozenset[str] = frozenset({"nestedIn", "nestedNotIn"})
_NESTED_STRINGS: frozenset[str] = frozenset(
    {"nestedLike", "nestedNotLike", "nestedStartsWith", "nestedEndsWith", "nestedContains"}
)
_NESTED_NULL: frozenset[str] = frozenset({"nestedIsNull", "nestedIsNotNull"})

# Reference-string patterns, mirroring identity.schema.json's `$defs` exactly —
# the schemas are the contract and these are this target's copy of it, so a
# reference either side accepts is accepted by both. An Entity spelling is the
# canonical `<namespace>.<Entity>` or the bare `<Entity>`, its namespace segments
# lowercase and its local name capitalized so the Entity/member boundary is
# decidable from the text alone (m-metamodel). An attribute and relationship
# reference share the `<Entity>.member` grammar; a nested reference descends >=1
# dotted member into a value object (`<Entity>.valueObject.field`); a value-object
# reference terminates AT a value object (>=1 member, `<Entity>.valueObject`); an
# element-relative reference (inside a scoped `where`) carries no Entity spelling
# at all (`type`, `geo.country`). The serde enforces the matching pattern wherever
# a reference of that kind appears, so a malformed reference is rejected rather
# than accepted.
_ENTITY = r"([a-z][a-z0-9]*(\.[a-z][a-z0-9]*)*\.)?[A-Z][A-Za-z0-9]*"
_MEMBER = r"[a-z][A-Za-z0-9_]*"
_MEMBER_REF = re.compile(rf"^{_ENTITY}\.{_MEMBER}$")
_ENTITY_NAME = re.compile(rf"^{_ENTITY}$")
_NESTED_REF = re.compile(rf"^{_ENTITY}\.{_MEMBER}(\.{_MEMBER})+$")
_VALUE_OBJECT_REF = re.compile(rf"^{_ENTITY}(\.{_MEMBER})+$")
_ELEMENT_REF = re.compile(rf"^{_MEMBER}(\.{_MEMBER})*$")

# The predicate kinds `predicate.schema.json` admits inside a nestedExists /
# nestedNotExists `where` (its `elementPredicate` oneOf): the scoped nested*
# family over element-relative paths, composed with the boolean combinators. Every
# other kind — a top-level predicate, navigation, narrowing, `all`/`none` — is
# illegal there and rejected before construction.
_ELEMENT_TAGS: frozenset[str] = (
    _NESTED_CMP
    | _NESTED_RANGE
    | _NESTED_MEMBERSHIPS
    | _NESTED_STRINGS
    | _NESTED_NULL
    | frozenset({"and", "or", "not", "group"})
)


class CanonicalDocumentError(ValueError):
    """A serialized document is not a well-formed canonical node."""


_Shape = tuple[frozenset[str], frozenset[str]]  # (required, optional)


def _shape(required: tuple[str, ...], optional: tuple[str, ...] = ()) -> _Shape:
    return frozenset(required), frozenset(optional)


def _check_shape(tag: str, shape: _Shape, body: Mapping[str, object]) -> None:
    """Reject a body carrying unexpected keys or missing a required key."""
    required, optional = shape
    extra = sorted(set(body) - required - optional)
    if extra:
        raise CanonicalDocumentError(f"{tag}: unexpected key(s) {extra}")
    missing = sorted(required - body.keys())
    if missing:
        raise CanonicalDocumentError(f"{tag}: missing required key(s) {missing}")


def _single_key(doc: object) -> tuple[str, Mapping[str, object]]:
    if not isinstance(doc, Mapping):
        raise CanonicalDocumentError(f"predicate node must be a mapping, got {type(doc).__name__}")
    node = cast("Mapping[str, object]", doc)
    if len(node) != 1:
        raise CanonicalDocumentError(
            f"predicate node must have exactly one key, got {sorted(node)}"
        )
    (tag,) = node
    body = node[tag]
    if not isinstance(body, Mapping):
        raise CanonicalDocumentError(f"predicate {tag!r} body must be a mapping")
    return tag, cast("Mapping[str, object]", body)


def _str(body: Mapping[str, object], key: str, tag: str) -> str:
    value = body.get(key)
    if not isinstance(value, str):
        raise CanonicalDocumentError(f"{tag}: `{key}` must be a string")
    return value


def _ref(
    body: Mapping[str, object], key: str, tag: str, pattern: re.Pattern[str], kind: str
) -> str:
    """Read a reference string and enforce the schema pattern for its position."""
    value = _str(body, key, tag)
    if pattern.match(value) is None:
        raise CanonicalDocumentError(f"{tag}: `{key}` {value!r} is not a valid {kind}")
    return value


def _case_insensitive(body: Mapping[str, object], tag: str) -> bool | None:
    """Read the optional ``caseInsensitive`` flag, distinguishing OMITTED (``None``)
    from an explicit boolean so serialize round-trips an authored ``false``."""
    if "caseInsensitive" not in body:
        return None
    raw = body["caseInsensitive"]
    if not isinstance(raw, bool):
        raise CanonicalDocumentError(f"{tag}: `caseInsensitive` must be a boolean")
    return raw


def _scalar(value: object, tag: str) -> Scalar:
    if isinstance(value, (str, int, float, bool)):
        return value
    raise CanonicalDocumentError(
        f"{tag}: value must be a non-null scalar literal, got {type(value).__name__}"
    )


def _values(body: Mapping[str, object], tag: str) -> tuple[Scalar, ...]:
    raw = body.get("values")
    if not isinstance(raw, list) or not raw:
        raise CanonicalDocumentError(f"{tag}: `values` must be a non-empty list")
    return tuple(_scalar(item, tag) for item in cast("list[object]", raw))


def _operand(body: Mapping[str, object], *, element_scope: bool) -> PredicateNode:
    # `operand` presence is guaranteed by the closed-shape check (every
    # operand-bearing tag lists it as required), so this only recurses. The scope
    # threads through the boolean combinators: a `not`/`group` under a scoped
    # `where` keeps its inner operand in element-predicate scope.
    return _deserialize(body["operand"], element_scope=element_scope)


def _operands(
    body: Mapping[str, object], tag: str, *, element_scope: bool
) -> tuple[PredicateNode, ...]:
    raw = body.get("operands")
    if not isinstance(raw, list):
        raise CanonicalDocumentError(f"{tag}: `operands` must have at least two entries")
    items = cast("list[object]", raw)
    if len(items) < 2:
        raise CanonicalDocumentError(f"{tag}: `operands` must have at least two entries")
    return tuple(_deserialize(item, element_scope=element_scope) for item in items)


def _to_list(body: Mapping[str, object], tag: str) -> tuple[str, ...]:
    raw = body.get("to")
    if not isinstance(raw, list) or not raw:
        raise CanonicalDocumentError(f"{tag}: `to` must be a non-empty list")
    items = cast("list[object]", raw)
    out: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise CanonicalDocumentError(f"{tag}: `to` entries must be strings")
        if _ENTITY_NAME.match(item) is None:
            raise CanonicalDocumentError(f"{tag}: `to` entry {item!r} is not a valid entity name")
        out.append(item)
    return tuple(out)


def _nested_where(body: Mapping[str, object]) -> PredicateNode | None:
    # A nestedExists/nestedNotExists `where` is an `elementPredicate` (schema):
    # the scoped nested* family over element-relative paths plus boolean
    # combinators. Recursing in element scope both restricts the legal tags and
    # switches nested paths to the element-relative pattern.
    if "where" not in body:
        return None
    return _deserialize(body["where"], element_scope=True)


def deserialize(doc: object) -> PredicateNode:
    """Parse a Predicate document and canonicalize its set-valued carriers."""
    return _deserialize(doc, element_scope=False)


def _deserialize(doc: object, *, element_scope: bool) -> PredicateNode:
    """Parse one node; ``element_scope`` restricts it to the ``elementPredicate``
    grammar (nested* family + boolean combinators, element-relative paths) the
    schema fixes inside a nestedExists/nestedNotExists ``where``."""
    tag, body = _single_key(doc)
    if element_scope and tag not in _ELEMENT_TAGS:
        raise CanonicalDocumentError(
            f"{tag}: not a legal element predicate inside a nestedExists `where`"
        )
    grammar = _GRAMMAR.get(tag)
    if grammar is None:
        raise CanonicalDocumentError(f"unknown predicate node {tag!r}")
    shape, parse = grammar
    _check_shape(tag, shape, body)
    return parse(tag, body, element_scope)


type _Parser = Callable[[str, Mapping[str, object], bool], PredicateNode]
type _Grammar = tuple[_Shape, _Parser]


def _attr(body: Mapping[str, object], tag: str) -> str:
    return _ref(body, "attr", tag, _MEMBER_REF, "attribute reference")


def _rel(body: Mapping[str, object], tag: str) -> str:
    return _ref(body, "rel", tag, _MEMBER_REF, "relationship reference")


def _nested_path(body: Mapping[str, object], tag: str, element_scope: bool) -> str:
    # A nested*-family path is a value-object inner reference at top level
    # (`Class.valueObject.field`), but an element-relative reference inside a
    # scoped `where` (`type`, `geo.country`) — the schema swaps the pattern.
    if element_scope:
        return _ref(body, "path", tag, _ELEMENT_REF, "element-relative path")
    return _ref(body, "path", tag, _NESTED_REF, "nested reference")


def _value_object_path(body: Mapping[str, object], tag: str) -> str:
    return _ref(body, "path", tag, _VALUE_OBJECT_REF, "value-object reference")


def _comparison(tag: str, body: Mapping[str, object], _scope: bool) -> PredicateNode:
    return Comparison(
        op=cast("ComparisonOp", tag),
        attr=_attr(body, tag),
        value=_scalar(body.get("value"), tag),
    )


def _between(tag: str, body: Mapping[str, object], _scope: bool) -> PredicateNode:
    return Between(
        attr=_attr(body, tag),
        lower=_scalar(body.get("lower"), tag),
        upper=_scalar(body.get("upper"), tag),
    )


def _null_check(tag: str, body: Mapping[str, object], _scope: bool) -> PredicateNode:
    return NullCheck(op=cast("NullOp", tag), attr=_attr(body, tag))


def _string_match(tag: str, body: Mapping[str, object], _scope: bool) -> PredicateNode:
    return StringMatch(
        op=cast("StringOp", tag),
        attr=_attr(body, tag),
        value=_str(body, "value", tag),
        case_insensitive=_case_insensitive(body, tag),
    )


def _membership(tag: str, body: Mapping[str, object], _scope: bool) -> PredicateNode:
    return Membership(
        op=cast("MembershipOp", tag), attr=_attr(body, tag), values=_values(body, tag)
    )


def _and(tag: str, body: Mapping[str, object], element_scope: bool) -> PredicateNode:
    return And(operands=_operands(body, tag, element_scope=element_scope))


def _or(tag: str, body: Mapping[str, object], element_scope: bool) -> PredicateNode:
    return Or(operands=_operands(body, tag, element_scope=element_scope))


def _not(_tag: str, body: Mapping[str, object], element_scope: bool) -> PredicateNode:
    return Not(operand=_operand(body, element_scope=element_scope))


def _group(_tag: str, body: Mapping[str, object], element_scope: bool) -> PredicateNode:
    return Group(operand=_operand(body, element_scope=element_scope))


def _narrow(tag: str, body: Mapping[str, object], element_scope: bool) -> PredicateNode:
    return Narrow(
        to=canonical_subtype_selection(_to_list(body, tag)),
        operand=_operand(body, element_scope=element_scope),
    )


def _nested_comparison(tag: str, body: Mapping[str, object], element_scope: bool) -> PredicateNode:
    return NestedComparison(
        op=cast("NestedComparisonOp", tag),
        path=_nested_path(body, tag, element_scope),
        value=_scalar(body.get("value"), tag),
    )


def _nested_range(tag: str, body: Mapping[str, object], element_scope: bool) -> PredicateNode:
    return NestedRange(
        path=_nested_path(body, tag, element_scope),
        lower=_scalar(body.get("lower"), tag),
        upper=_scalar(body.get("upper"), tag),
    )


def _nested_membership(tag: str, body: Mapping[str, object], element_scope: bool) -> PredicateNode:
    return NestedMembership(
        op=cast("NestedMembershipOp", tag),
        path=_nested_path(body, tag, element_scope),
        values=_values(body, tag),
    )


def _nested_string_match(
    tag: str, body: Mapping[str, object], element_scope: bool
) -> PredicateNode:
    return NestedStringMatch(
        op=cast("NestedStringOp", tag),
        path=_nested_path(body, tag, element_scope),
        value=_str(body, "value", tag),
        case_insensitive=_case_insensitive(body, tag),
    )


def _nested_null_check(tag: str, body: Mapping[str, object], element_scope: bool) -> PredicateNode:
    return NestedNullCheck(
        op=cast("NestedNullOp", tag), path=_nested_path(body, tag, element_scope)
    )


def _nested_exists(tag: str, body: Mapping[str, object], _scope: bool) -> PredicateNode:
    return NestedExists(path=_value_object_path(body, tag), where=_nested_where(body))


def _nested_not_exists(tag: str, body: Mapping[str, object], _scope: bool) -> PredicateNode:
    return NestedNotExists(path=_value_object_path(body, tag), where=_nested_where(body))


def _navigate(tag: str, body: Mapping[str, object], _scope: bool) -> PredicateNode:
    return Navigate(rel=_rel(body, tag), op=_nav_op(body))


def _exists(tag: str, body: Mapping[str, object], _scope: bool) -> PredicateNode:
    return Exists(rel=_rel(body, tag), op=_nav_op(body))


def _not_exists(tag: str, body: Mapping[str, object], _scope: bool) -> PredicateNode:
    return NotExists(rel=_rel(body, tag), op=_nav_op(body))


def _all(_tag: str, _body: Mapping[str, object], _scope: bool) -> PredicateNode:
    return All()


def _none(_tag: str, _body: Mapping[str, object], _scope: bool) -> PredicateNode:
    return NoneOp()


def _family(tags: frozenset[str], shape: _Shape, parse: _Parser) -> dict[str, _Grammar]:
    return dict.fromkeys(tags, (shape, parse))


# Each tag's closed body shape beside the parser that builds its node.
_GRAMMAR: dict[str, _Grammar] = {
    "all": (_shape(()), _all),
    "none": (_shape(()), _none),
    "between": (_shape(("attr", "lower", "upper")), _between),
    "and": (_shape(("operands",)), _and),
    "or": (_shape(("operands",)), _or),
    "not": (_shape(("operand",)), _not),
    "group": (_shape(("operand",)), _group),
    "narrow": (_shape(("to", "operand")), _narrow),
    "nestedExists": (_shape(("path",), ("where",)), _nested_exists),
    "nestedNotExists": (_shape(("path",), ("where",)), _nested_not_exists),
    "navigate": (_shape(("rel",), ("op",)), _navigate),
    "exists": (_shape(("rel",), ("op",)), _exists),
    "notExists": (_shape(("rel",), ("op",)), _not_exists),
    **_family(_COMPARISONS, _shape(("attr", "value")), _comparison),
    **_family(_NULLS, _shape(("attr",)), _null_check),
    **_family(_STRINGS, _shape(("attr", "value"), ("caseInsensitive",)), _string_match),
    **_family(_MEMBERSHIPS, _shape(("attr", "values")), _membership),
    **_family(_NESTED_CMP, _shape(("path", "value")), _nested_comparison),
    **_family(_NESTED_RANGE, _shape(("path", "lower", "upper")), _nested_range),
    **_family(_NESTED_MEMBERSHIPS, _shape(("path", "values")), _nested_membership),
    **_family(
        _NESTED_STRINGS, _shape(("path", "value"), ("caseInsensitive",)), _nested_string_match
    ),
    **_family(_NESTED_NULL, _shape(("path",)), _nested_null_check),
}


def _nav_op(body: Mapping[str, object]) -> PredicateNode | None:
    # A navigation `op` references the FULL Predicate grammar (schema), so it is
    # always deserialized in top-level (non-element) scope.
    if "op" not in body:
        return None
    return _deserialize(body["op"], element_scope=False)


def _emit_where(where: PredicateNode | None) -> dict[str, object]:
    return {"where": serialize(where)} if where is not None else {}


def _emit_nav(rel: str, op: PredicateNode | None) -> dict[str, object]:
    body: dict[str, object] = {"rel": rel}
    if op is not None:
        body["op"] = serialize(op)
    return body


def serialize(op: PredicateNode) -> dict[str, object]:
    """Emit the canonical single-key tagged document for one node.

    A ``narrow``'s Subtype Selection is canonicalized defensively so a directly
    constructed node has the same wire identity as a deserialized one.
    """
    match op:
        case All():
            return {"all": {}}
        case NoneOp():
            return {"none": {}}
        case Comparison() | Between() | NullCheck() | StringMatch() | Membership():
            return _emit_attribute_leaf(op)
        case (
            NestedComparison()
            | NestedRange()
            | NestedMembership()
            | NestedStringMatch()
            | NestedNullCheck()
        ):
            return _emit_nested_leaf(op)
        case And() | Or() | Not() | Group():
            return _emit_combinator(op)
        case Narrow(to=to, operand=operand):
            return {"narrow": {"to": list(to), "operand": serialize(operand)}}
        case NestedExists(path=path, where=where):
            return {"nestedExists": {"path": path, **_emit_where(where)}}
        case NestedNotExists(path=path, where=where):
            return {"nestedNotExists": {"path": path, **_emit_where(where)}}
        case Navigate(rel=rel, op=inner):
            return {"navigate": _emit_nav(rel, inner)}
        case Exists(rel=rel, op=inner):
            return {"exists": _emit_nav(rel, inner)}
        case NotExists(rel=rel, op=inner):
            return {"notExists": _emit_nav(rel, inner)}


def _emit_attribute_leaf(
    op: Comparison | Between | NullCheck | StringMatch | Membership,
) -> dict[str, object]:
    match op:
        case Comparison(op=tag, attr=attr, value=value):
            return {tag: {"attr": attr, "value": value}}
        case Between(attr=attr, lower=lower, upper=upper):
            return {"between": {"attr": attr, "lower": lower, "upper": upper}}
        case NullCheck(op=tag, attr=attr):
            return {tag: {"attr": attr}}
        case StringMatch(op=tag, attr=attr, value=value, case_insensitive=ci):
            return {tag: _emit_string_body({"attr": attr, "value": value}, ci)}
        case Membership(op=tag, attr=attr, values=values):
            return {tag: {"attr": attr, "values": list(values)}}


def _emit_nested_leaf(
    op: NestedComparison | NestedRange | NestedMembership | NestedStringMatch | NestedNullCheck,
) -> dict[str, object]:
    match op:
        case NestedComparison(op=tag, path=path, value=value):
            return {tag: {"path": path, "value": value}}
        case NestedRange(path=path, lower=lower, upper=upper):
            return {"nestedBetween": {"path": path, "lower": lower, "upper": upper}}
        case NestedMembership(op=tag, path=path, values=values):
            return {tag: {"path": path, "values": list(values)}}
        case NestedStringMatch(op=tag, path=path, value=value, case_insensitive=ci):
            return {tag: _emit_string_body({"path": path, "value": value}, ci)}
        case NestedNullCheck(op=tag, path=path):
            return {tag: {"path": path}}


def _emit_combinator(op: And | Or | Not | Group) -> dict[str, object]:
    match op:
        case And(operands=operands):
            return {"and": {"operands": [serialize(o) for o in operands]}}
        case Or(operands=operands):
            return {"or": {"operands": [serialize(o) for o in operands]}}
        case Not(operand=operand):
            return {"not": {"operand": serialize(operand)}}
        case Group(operand=operand):
            return {"group": {"operand": serialize(operand)}}


def _emit_string_body(body: dict[str, object], case_insensitive: bool | None) -> dict[str, object]:
    # Omit an omitted flag (None); round-trip an explicit `false`/`true`
    # verbatim (m-predicate: serialize(deserialize(op)) == op).
    if case_insensitive is not None:
        body["caseInsensitive"] = case_insensitive
    return body
