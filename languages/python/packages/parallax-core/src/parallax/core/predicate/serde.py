from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import cast

from parallax.core.predicate._nodes import (
    CURRENT_SCALAR_ELEMENT,
    And,
    Comparison,
    ComparisonOp,
    FalseNode,
    FieldSubject,
    Group,
    Membership,
    MembershipOp,
    Narrow,
    Not,
    NullCheck,
    NullOp,
    Or,
    PredicateNode,
    Presence,
    PresenceOp,
    Quantifier,
    QuantifierKind,
    Range,
    ScalarLiteral,
    ScalarSubject,
    StringMatch,
    StringOp,
    TrueNode,
    canonical_subtype_selection,
)

__all__ = ["CanonicalDocumentError", "deserialize", "serialize"]

_COMPARISONS: frozenset[str] = frozenset(
    {"eq", "notEq", "greaterThan", "greaterThanEquals", "lessThan", "lessThanEquals"}
)
_NULLS: frozenset[str] = frozenset({"isNull", "isNotNull"})
_STRINGS: frozenset[str] = frozenset({"like", "notLike", "startsWith", "endsWith", "contains"})
_MEMBERSHIPS: frozenset[str] = frozenset({"in", "notIn"})
_QUANTIFIERS: frozenset[str] = frozenset({"any", "all", "none"})
_PRESENCE: frozenset[str] = frozenset({"exists", "notExists"})

# Reference-string patterns, mirroring identity.schema.json's `$defs` exactly. A
# predicate path is Entity-qualified (`<Entity>.member(.member)*`) or relative to
# the object a scope binds (`member(.member)*`); which one a position takes is
# a model-aware scope rule, not a structural one. A Subtype Selection alternative
# is an Entity spelling.
_ENTITY = r"([a-z][a-z0-9]*(\.[a-z][a-z0-9]*)*\.)?[A-Z][A-Za-z0-9]*"
_MEMBER = r"[a-z][A-Za-z0-9_]*"
_ENTITY_NAME = re.compile(rf"^{_ENTITY}$")
_PATH = re.compile(rf"^({_ENTITY}(\.{_MEMBER})+|{_MEMBER}(\.{_MEMBER})*)$")


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


def _path(body: Mapping[str, object], tag: str) -> str:
    value = _str(body, "path", tag)
    if _PATH.match(value) is None:
        raise CanonicalDocumentError(f"{tag}: `path` {value!r} is not a valid predicate path")
    return value


def _subject(body: Mapping[str, object], tag: str) -> ScalarSubject:
    """A field when the body carries `path`, else the current scalar element."""
    return FieldSubject(_path(body, tag)) if "path" in body else CURRENT_SCALAR_ELEMENT


def _case_insensitive(body: Mapping[str, object], tag: str) -> bool | None:
    """Read the optional ``caseInsensitive`` flag, distinguishing OMITTED (``None``)
    from an explicit boolean so serialize round-trips an authored ``false``."""
    if "caseInsensitive" not in body:
        return None
    raw = body["caseInsensitive"]
    if not isinstance(raw, bool):
        raise CanonicalDocumentError(f"{tag}: `caseInsensitive` must be a boolean")
    return raw


def _scalar(value: object, tag: str) -> ScalarLiteral:
    if isinstance(value, (str, int, float, bool)):
        return value
    raise CanonicalDocumentError(
        f"{tag}: value must be a non-null scalar literal, got {type(value).__name__}"
    )


def _values(body: Mapping[str, object], tag: str) -> tuple[ScalarLiteral, ...]:
    raw = body.get("values")
    if not isinstance(raw, list) or not raw:
        raise CanonicalDocumentError(f"{tag}: `values` must be a non-empty list")
    return tuple(_scalar(item, tag) for item in cast("list[object]", raw))


def _operands(body: Mapping[str, object], tag: str) -> tuple[PredicateNode, ...]:
    raw = body.get("operands")
    if not isinstance(raw, list):
        raise CanonicalDocumentError(f"{tag}: `operands` must have at least two entries")
    items = cast("list[object]", raw)
    if len(items) < 2:
        raise CanonicalDocumentError(f"{tag}: `operands` must have at least two entries")
    return tuple(deserialize(item) for item in items)


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


def deserialize(doc: object) -> PredicateNode:
    """Parse a Predicate document and canonicalize its set-valued carriers."""
    tag, body = _single_key(doc)
    grammar = _GRAMMAR.get(tag)
    if grammar is None:
        raise CanonicalDocumentError(f"unknown predicate node {tag!r}")
    shape, parse = grammar
    _check_shape(tag, shape, body)
    return parse(tag, body)


type _Parser = Callable[[str, Mapping[str, object]], PredicateNode]
type _Grammar = tuple[_Shape, _Parser]


def _comparison(tag: str, body: Mapping[str, object]) -> PredicateNode:
    return Comparison(
        op=cast("ComparisonOp", tag),
        subject=_subject(body, tag),
        value=_scalar(body.get("value"), tag),
    )


def _between(tag: str, body: Mapping[str, object]) -> PredicateNode:
    return Range(
        subject=_subject(body, tag),
        lower=_scalar(body.get("lower"), tag),
        upper=_scalar(body.get("upper"), tag),
    )


def _null_check(tag: str, body: Mapping[str, object]) -> PredicateNode:
    return NullCheck(op=cast("NullOp", tag), subject=FieldSubject(_path(body, tag)))


def _string_match(tag: str, body: Mapping[str, object]) -> PredicateNode:
    return StringMatch(
        op=cast("StringOp", tag),
        subject=_subject(body, tag),
        value=_str(body, "value", tag),
        case_insensitive=_case_insensitive(body, tag),
    )


def _membership(tag: str, body: Mapping[str, object]) -> PredicateNode:
    return Membership(
        op=cast("MembershipOp", tag), subject=_subject(body, tag), values=_values(body, tag)
    )


def _and(tag: str, body: Mapping[str, object]) -> PredicateNode:
    return And(operands=_operands(body, tag))


def _or(tag: str, body: Mapping[str, object]) -> PredicateNode:
    return Or(operands=_operands(body, tag))


def _not(_tag: str, body: Mapping[str, object]) -> PredicateNode:
    return Not(operand=deserialize(body["operand"]))


def _group(_tag: str, body: Mapping[str, object]) -> PredicateNode:
    return Group(operand=deserialize(body["operand"]))


def _narrow(tag: str, body: Mapping[str, object]) -> PredicateNode:
    return Narrow(
        to=canonical_subtype_selection(_to_list(body, tag)),
        operand=deserialize(body["operand"]),
        path=_path(body, tag) if "path" in body else None,
    )


def _quantifier(tag: str, body: Mapping[str, object]) -> PredicateNode:
    where = deserialize(body["where"]) if "where" in body else None
    return Quantifier(kind=cast("QuantifierKind", tag), path=_path(body, tag), where=where)


def _presence(tag: str, body: Mapping[str, object]) -> PredicateNode:
    return Presence(op=cast("PresenceOp", tag), path=_path(body, tag))


def _true(_tag: str, _body: Mapping[str, object]) -> PredicateNode:
    return TrueNode()


def _false(_tag: str, _body: Mapping[str, object]) -> PredicateNode:
    return FalseNode()


def _family(tags: frozenset[str], shape: _Shape, parse: _Parser) -> dict[str, _Grammar]:
    return dict.fromkeys(tags, (shape, parse))


_GRAMMAR: dict[str, _Grammar] = {
    "true": (_shape(()), _true),
    "false": (_shape(()), _false),
    "between": (_shape(("lower", "upper"), ("path",)), _between),
    "and": (_shape(("operands",)), _and),
    "or": (_shape(("operands",)), _or),
    "not": (_shape(("operand",)), _not),
    "group": (_shape(("operand",)), _group),
    "narrow": (_shape(("to", "operand"), ("path",)), _narrow),
    "all": (_shape(("path", "where")), _quantifier),
    **_family(_QUANTIFIERS - {"all"}, _shape(("path",), ("where",)), _quantifier),
    **_family(_PRESENCE, _shape(("path",)), _presence),
    **_family(_COMPARISONS, _shape(("value",), ("path",)), _comparison),
    **_family(_NULLS, _shape(("path",)), _null_check),
    **_family(_STRINGS, _shape(("value",), ("path", "caseInsensitive")), _string_match),
    **_family(_MEMBERSHIPS, _shape(("values",), ("path",)), _membership),
}


def serialize(op: PredicateNode) -> dict[str, object]:  # noqa: C901 - exhaustive dispatcher
    """Emit the canonical single-key tagged document for one node.

    A ``narrow``'s Subtype Selection is canonicalized defensively so a directly
    constructed node has the same wire identity as a deserialized one.
    """
    match op:
        case TrueNode():
            return {"true": {}}
        case FalseNode():
            return {"false": {}}
        case Comparison() | Range() | NullCheck() | StringMatch() | Membership():
            return _emit_operation(op)
        case And(operands=operands):
            return {"and": {"operands": [serialize(o) for o in operands]}}
        case Or(operands=operands):
            return {"or": {"operands": [serialize(o) for o in operands]}}
        case Not(operand=operand):
            return {"not": {"operand": serialize(operand)}}
        case Group(operand=operand):
            return {"group": {"operand": serialize(operand)}}
        case Quantifier(kind=kind, path=path, where=where):
            body: dict[str, object] = {"path": path}
            if where is not None:
                body["where"] = serialize(where)
            return {kind: body}
        case Presence(op=tag, path=path):
            return {tag: {"path": path}}
        case Narrow(to=to, operand=operand, path=path):
            narrow: dict[str, object] = {} if path is None else {"path": path}
            narrow.update({"to": list(to), "operand": serialize(operand)})
            return {"narrow": narrow}


def _subject_body(subject: ScalarSubject) -> dict[str, object]:
    return {"path": subject.path} if isinstance(subject, FieldSubject) else {}


def _emit_operation(
    op: Comparison | Range | NullCheck | StringMatch | Membership,
) -> dict[str, object]:
    body = _subject_body(op.subject)
    match op:
        case Comparison(op=tag, value=value):
            body["value"] = value
            return {tag: body}
        case Range(lower=lower, upper=upper):
            body.update({"lower": lower, "upper": upper})
            return {"between": body}
        case NullCheck(op=tag):
            return {tag: body}
        case StringMatch(op=tag, value=value, case_insensitive=ci):
            body["value"] = value
            if ci is not None:
                body["caseInsensitive"] = ci
            return {tag: body}
        case Membership(op=tag, values=values):
            body["values"] = list(values)
            return {tag: body}
