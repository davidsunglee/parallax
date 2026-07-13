"""Operation serde (m-op-algebra canonical single-key tagged encoding).

``serialize`` emits the canonical single-key tagged object for each node exactly
as ``operation.schema.json`` fixes it (defaulted keys — ``direction: asc``,
``caseInsensitive: false`` — omitted); ``deserialize`` reads that form back into
frozen nodes. The pair round-trips (``serialize(deserialize(x)) == x``) for every
node in the read algebra, in both JSON and YAML (the format is irrelevant — the
document is plain dict/list/scalar). ``deserialize`` is structural and
type-checked; metamodel binding (attribute→column, nested-path and narrow
resolution) is applied by ``m-sql`` at lowering time, which holds the metamodel.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from parallax.core.op_algebra.nodes import (
    All,
    And,
    AsOf,
    AsOfRange,
    Between,
    Comparison,
    ComparisonOp,
    DeepFetch,
    Distinct,
    Exists,
    Group,
    History,
    Limit,
    Membership,
    MembershipOp,
    Narrow,
    Navigate,
    NestedComparison,
    NestedComparisonOp,
    NestedExists,
    NestedMembership,
    NestedNotExists,
    NestedNullCheck,
    NestedNullOp,
    NoneOp,
    Not,
    NotExists,
    NullCheck,
    NullOp,
    Operation,
    Or,
    OrderBy,
    OrderKey,
    PathSegment,
    Scalar,
    StringMatch,
    StringOp,
)

__all__ = ["OperationError", "deserialize", "serialize"]

_COMPARISONS: frozenset[str] = frozenset(
    {"eq", "notEq", "greaterThan", "greaterThanEquals", "lessThan", "lessThanEquals"}
)
_NULLS: frozenset[str] = frozenset({"isNull", "isNotNull"})
_STRINGS: frozenset[str] = frozenset({"like", "notLike", "startsWith", "endsWith", "contains"})
_MEMBERSHIPS: frozenset[str] = frozenset({"in", "notIn"})
_NESTED_CMP: frozenset[str] = frozenset(
    {"nestedEq", "nestedNotEq", "nestedGt", "nestedGte", "nestedLt", "nestedLte"}
)
_NESTED_NULL: frozenset[str] = frozenset({"nestedIsNull", "nestedIsNotNull"})


class OperationError(ValueError):
    """An operation document is not a well-formed canonical operation node."""


# --------------------------------------------------------------------------- #
# Deserialize.                                                                 #
# --------------------------------------------------------------------------- #
def _single_key(doc: object) -> tuple[str, Mapping[str, object]]:
    if not isinstance(doc, Mapping):
        raise OperationError(f"operation node must be a mapping, got {type(doc).__name__}")
    node = cast("Mapping[str, object]", doc)
    if len(node) != 1:
        raise OperationError(f"operation node must have exactly one key, got {sorted(node)}")
    (tag,) = node
    body = node[tag]
    if not isinstance(body, Mapping):
        raise OperationError(f"operation {tag!r} body must be a mapping")
    return tag, cast("Mapping[str, object]", body)


def _str(body: Mapping[str, object], key: str, tag: str) -> str:
    value = body.get(key)
    if not isinstance(value, str):
        raise OperationError(f"{tag}: `{key}` must be a string")
    return value


def _scalar(value: object, tag: str) -> Scalar:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise OperationError(f"{tag}: value must be a scalar literal, got {type(value).__name__}")


def _values(body: Mapping[str, object], tag: str) -> tuple[Scalar, ...]:
    raw = body.get("values")
    if not isinstance(raw, list) or not raw:
        raise OperationError(f"{tag}: `values` must be a non-empty list")
    return tuple(_scalar(item, tag) for item in cast("list[object]", raw))


def _operand(body: Mapping[str, object], tag: str) -> Operation:
    if "operand" not in body:
        raise OperationError(f"{tag}: missing `operand`")
    return deserialize(body["operand"])


def _operands(body: Mapping[str, object], tag: str) -> tuple[Operation, ...]:
    raw = body.get("operands")
    if not isinstance(raw, list):
        raise OperationError(f"{tag}: `operands` must have at least two entries")
    items = cast("list[object]", raw)
    if len(items) < 2:
        raise OperationError(f"{tag}: `operands` must have at least two entries")
    return tuple(deserialize(item) for item in items)


def _order_keys(body: Mapping[str, object]) -> tuple[OrderKey, ...]:
    raw = body.get("keys")
    if not isinstance(raw, list) or not raw:
        raise OperationError("orderBy: `keys` must be a non-empty list")
    keys: list[OrderKey] = []
    for item in cast("list[object]", raw):
        if not isinstance(item, Mapping):
            raise OperationError("orderBy: each key must be a mapping")
        key = cast("Mapping[str, object]", item)
        direction = key.get("direction", "asc")
        if direction not in ("asc", "desc"):
            raise OperationError("orderBy: `direction` must be 'asc' or 'desc'")
        keys.append(OrderKey(attr=_str(key, "attr", "orderBy"), direction=direction))
    return tuple(keys)


def _to_list(body: Mapping[str, object], tag: str) -> tuple[str, ...]:
    raw = body.get("to")
    if not isinstance(raw, list) or not raw:
        raise OperationError(f"{tag}: `to` must be a non-empty list")
    return tuple(str(item) for item in cast("list[object]", raw))


def _paths(body: Mapping[str, object]) -> tuple[tuple[PathSegment, ...], ...]:
    raw = body.get("paths")
    if not isinstance(raw, list) or not raw:
        raise OperationError("deepFetch: `paths` must be a non-empty list")
    paths: list[tuple[PathSegment, ...]] = []
    for path in cast("list[object]", raw):
        if not isinstance(path, list) or not path:
            raise OperationError("deepFetch: each path must be a non-empty list of segments")
        segments: list[PathSegment] = []
        for seg in cast("list[object]", path):
            if not isinstance(seg, Mapping):
                raise OperationError("deepFetch: each path segment must be a mapping")
            segment = cast("Mapping[str, object]", seg)
            narrow_raw = segment.get("narrow")
            narrow: tuple[str, ...] = ()
            if isinstance(narrow_raw, Mapping):
                narrow = _to_list(cast("Mapping[str, object]", narrow_raw), "deepFetch.narrow")
            segments.append(PathSegment(rel=_str(segment, "rel", "deepFetch"), narrow=narrow))
        paths.append(tuple(segments))
    return tuple(paths)


def _nested_where(body: Mapping[str, object]) -> Operation | None:
    if "where" not in body:
        return None
    return deserialize(body["where"])


def deserialize(doc: object) -> Operation:
    """Parse a canonical operation document into a frozen node tree."""
    tag, body = _single_key(doc)
    if tag == "all":
        return All()
    if tag == "none":
        return NoneOp()
    if tag in _COMPARISONS:
        return Comparison(
            op=cast("ComparisonOp", tag),
            attr=_str(body, "attr", tag),
            value=_scalar(body.get("value"), tag),
        )
    if tag == "between":
        return Between(
            attr=_str(body, "attr", tag),
            lower=_scalar(body.get("lower"), tag),
            upper=_scalar(body.get("upper"), tag),
        )
    if tag in _NULLS:
        return NullCheck(op=cast("NullOp", tag), attr=_str(body, "attr", tag))
    if tag in _STRINGS:
        ci = body.get("caseInsensitive", False)
        if not isinstance(ci, bool):
            raise OperationError(f"{tag}: `caseInsensitive` must be a boolean")
        return StringMatch(
            op=cast("StringOp", tag),
            attr=_str(body, "attr", tag),
            value=_str(body, "value", tag),
            case_insensitive=ci,
        )
    if tag in _MEMBERSHIPS:
        return Membership(
            op=cast("MembershipOp", tag), attr=_str(body, "attr", tag), values=_values(body, tag)
        )
    if tag == "and":
        return And(operands=_operands(body, tag))
    if tag == "or":
        return Or(operands=_operands(body, tag))
    if tag == "not":
        return Not(operand=_operand(body, tag))
    if tag == "group":
        return Group(operand=_operand(body, tag))
    if tag == "orderBy":
        return OrderBy(operand=_operand(body, tag), keys=_order_keys(body))
    if tag == "limit":
        count = body.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise OperationError("limit: `count` must be a positive integer")
        return Limit(operand=_operand(body, tag), count=count)
    if tag == "distinct":
        return Distinct(operand=_operand(body, tag))
    if tag == "narrow":
        return Narrow(
            entity=_str(body, "entity", tag), to=_to_list(body, tag), operand=_operand(body, tag)
        )
    if tag in _NESTED_CMP:
        return NestedComparison(
            op=cast("NestedComparisonOp", tag),
            path=_str(body, "path", tag),
            value=_scalar(body.get("value"), tag),
        )
    if tag == "nestedIn":
        return NestedMembership(path=_str(body, "path", tag), values=_values(body, tag))
    if tag in _NESTED_NULL:
        return NestedNullCheck(op=cast("NestedNullOp", tag), path=_str(body, "path", tag))
    if tag == "nestedExists":
        return NestedExists(path=_str(body, "path", tag), where=_nested_where(body))
    if tag == "nestedNotExists":
        return NestedNotExists(path=_str(body, "path", tag), where=_nested_where(body))
    if tag == "navigate":
        return Navigate(rel=_str(body, "rel", tag), op=_nav_op(body))
    if tag == "exists":
        return Exists(rel=_str(body, "rel", tag), op=_nav_op(body))
    if tag == "notExists":
        return NotExists(rel=_str(body, "rel", tag), op=_nav_op(body))
    if tag == "deepFetch":
        return DeepFetch(operand=_operand(body, tag), paths=_paths(body))
    if tag == "asOf":
        return AsOf(
            operand=_operand(body, tag),
            as_of_attr=_str(body, "asOfAttr", tag),
            date=_str(body, "date", tag),
        )
    if tag == "asOfRange":
        return AsOfRange(
            operand=_operand(body, tag),
            as_of_attr=_str(body, "asOfAttr", tag),
            from_=_str(body, "from", tag),
            to=_str(body, "to", tag),
        )
    if tag == "history":
        return History(operand=_operand(body, tag), as_of_attr=_str(body, "asOfAttr", tag))
    raise OperationError(f"unknown operation node {tag!r}")


def _nav_op(body: Mapping[str, object]) -> Operation | None:
    if "op" not in body:
        return None
    return deserialize(body["op"])


# --------------------------------------------------------------------------- #
# Serialize (canonical minimal single-key tagged form).                       #
# --------------------------------------------------------------------------- #
def _emit_where(where: Operation | None) -> dict[str, object]:
    return {"where": serialize(where)} if where is not None else {}


def _emit_nav(rel: str, op: Operation | None) -> dict[str, object]:
    body: dict[str, object] = {"rel": rel}
    if op is not None:
        body["op"] = serialize(op)
    return body


def serialize(op: Operation) -> dict[str, object]:
    """Emit the canonical single-key tagged document for one node."""
    match op:
        case All():
            return {"all": {}}
        case NoneOp():
            return {"none": {}}
        case Comparison(op=tag, attr=attr, value=value):
            return {tag: {"attr": attr, "value": value}}
        case Between(attr=attr, lower=lower, upper=upper):
            return {"between": {"attr": attr, "lower": lower, "upper": upper}}
        case NullCheck(op=tag, attr=attr):
            return {tag: {"attr": attr}}
        case StringMatch(op=tag, attr=attr, value=value, case_insensitive=ci):
            body: dict[str, object] = {"attr": attr, "value": value}
            if ci:
                body["caseInsensitive"] = True
            return {tag: body}
        case Membership(op=tag, attr=attr, values=values):
            return {tag: {"attr": attr, "values": list(values)}}
        case And(operands=operands):
            return {"and": {"operands": [serialize(o) for o in operands]}}
        case Or(operands=operands):
            return {"or": {"operands": [serialize(o) for o in operands]}}
        case Not(operand=operand):
            return {"not": {"operand": serialize(operand)}}
        case Group(operand=operand):
            return {"group": {"operand": serialize(operand)}}
        case OrderBy(operand=operand, keys=keys):
            return {
                "orderBy": {"operand": serialize(operand), "keys": [_order_key(k) for k in keys]}
            }
        case Limit(operand=operand, count=count):
            return {"limit": {"operand": serialize(operand), "count": count}}
        case Distinct(operand=operand):
            return {"distinct": {"operand": serialize(operand)}}
        case Narrow(entity=entity, to=to, operand=operand):
            return {"narrow": {"entity": entity, "to": list(to), "operand": serialize(operand)}}
        case NestedComparison(op=tag, path=path, value=value):
            return {tag: {"path": path, "value": value}}
        case NestedMembership(path=path, values=values):
            return {"nestedIn": {"path": path, "values": list(values)}}
        case NestedNullCheck(op=tag, path=path):
            return {tag: {"path": path}}
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
        case DeepFetch(operand=operand, paths=paths):
            return {
                "deepFetch": {"operand": serialize(operand), "paths": [_path(p) for p in paths]}
            }
        case AsOf(operand=operand, as_of_attr=axis, date=date):
            return {"asOf": {"operand": serialize(operand), "asOfAttr": axis, "date": date}}
        case AsOfRange(operand=operand, as_of_attr=axis, from_=frm, to=to):
            return {
                "asOfRange": {
                    "operand": serialize(operand),
                    "asOfAttr": axis,
                    "from": frm,
                    "to": to,
                }
            }
        case History(operand=operand, as_of_attr=axis):
            return {"history": {"operand": serialize(operand), "asOfAttr": axis}}


def _order_key(key: OrderKey) -> dict[str, object]:
    # The corpus authors `direction` explicitly on every operation orderBy key
    # (both `asc` and `desc`), so serialization emits it verbatim to satisfy the
    # `serialize(deserialize(op)) == op` round-trip contract.
    return {"attr": key.attr, "direction": key.direction}


def _path(path: tuple[PathSegment, ...]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for seg in path:
        entry: dict[str, object] = {"rel": seg.rel}
        if seg.narrow:
            entry["narrow"] = {"to": list(seg.narrow)}
        out.append(entry)
    return out
