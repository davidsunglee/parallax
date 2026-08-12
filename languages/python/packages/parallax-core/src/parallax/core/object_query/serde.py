"""Object Query serde (m-object-query canonical flat encoding).

``serialize`` emits the canonical document exactly as
``object-query.schema.json`` fixes it: an omitted optional clause stays omitted,
an omitted optional Sort Key member (``direction`` / ``nulls``) stays omitted,
and the Temporal Selection map is emitted in canonical dimension order.
``deserialize`` reads that form into the frozen
:class:`~parallax.core.object_query.ObjectQueryNode` and canonicalizes the
order-insensitive carriers — Subtype Selections and the Include Path set — so a
document and the query a caller authored have the same canonical identity.

The predicate clause delegates to ``m-predicate``'s own serde unchanged: the
recursion belongs there, and this module never re-implements it. Metamodel
binding (attribute→column, narrow resolution, temporal dimension declaration) is
applied by preflight and lowering, which hold the metamodel.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal, cast

from parallax.core.metamodel import EntityIdentity
from parallax.core.object_query._canonical import object_query
from parallax.core.object_query._nodes import (
    AsOf,
    AsOfRange,
    History,
    IncludePath,
    IncludeSegment,
    ObjectQueryNode,
    OrderKey,
    TemporalDimension,
    TemporalSelection,
)
from parallax.core.predicate import CanonicalDocumentError, canonical_subtype_selection
from parallax.core.predicate import deserialize as deserialize_predicate
from parallax.core.predicate import serialize as serialize_predicate

__all__ = ["ObjectQueryError", "deserialize", "serialize"]


class ObjectQueryError(CanonicalDocumentError):
    """An Object Query document is not a well-formed canonical query.

    A subclass of the Predicate serde's own malformed-document error, because a
    query carries a predicate and a caller catching "this document is malformed"
    means both.
    """


# Reference-string patterns, mirroring identity.schema.json's `$defs` exactly.
_ENTITY = r"([a-z][a-z0-9]*(\.[a-z][a-z0-9]*)*\.)?[A-Z][A-Za-z0-9]*"
_MEMBER = r"[a-z][A-Za-z0-9_]*"
_ENTITY_NAME = re.compile(rf"^{_ENTITY}$")
_MEMBER_REF = re.compile(rf"^{_ENTITY}\.{_MEMBER}$")

_CLAUSES: frozenset[str] = frozenset(
    {"target", "predicate", "narrowTo", "temporal", "orderBy", "limit", "includes"}
)
_DIMENSIONS: tuple[TemporalDimension, ...] = ("transaction-time", "valid-time")


def _mapping(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ObjectQueryError(f"{where} must be a mapping, got {type(value).__name__}")
    return cast("Mapping[str, object]", value)


def _closed(node: Mapping[str, object], allowed: frozenset[str], where: str) -> None:
    extra = sorted(set(node) - allowed)
    if extra:
        raise ObjectQueryError(f"{where}: unexpected key(s) {extra}")


def _entity_name(value: object, where: str) -> str:
    if not isinstance(value, str) or _ENTITY_NAME.match(value) is None:
        raise ObjectQueryError(f"{where}: {value!r} is not a valid entity name")
    return value


def _selection(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ObjectQueryError(f"{where} must be a non-empty list")
    return canonical_subtype_selection(
        tuple(_entity_name(item, where) for item in cast("list[object]", value))
    )


def _instant(value: object, where: str, *, finite: bool) -> str:
    """Read a temporal coordinate and enforce the schema's own constraints.

    ``latest`` is canonical only for an ``asOf`` coordinate. Range bounds must be
    finite, and ``now`` is never a serialized coordinate: callers obtain a finite
    current-clock instant before construction.
    """
    if not isinstance(value, str) or not value:
        raise ObjectQueryError(f"{where} must be a non-empty temporal value")
    if value == "now" or (finite and value == "latest"):
        qualifier = "finite " if finite else ""
        raise ObjectQueryError(f"{where} must be a {qualifier}canonical coordinate")
    return value


def _temporal_selection(doc: object, dimension: str) -> TemporalSelection:
    node = _mapping(doc, f"temporal.{dimension}")
    if len(node) != 1:
        raise ObjectQueryError(
            f"temporal.{dimension}: a Temporal Selection has exactly one key, got {sorted(node)}"
        )
    (tag,) = node
    body = node[tag]
    if tag == "asOf":
        return AsOf(coordinate=_instant(body, f"temporal.{dimension}.asOf", finite=False))
    if tag == "asOfRange":
        window = _mapping(body, f"temporal.{dimension}.asOfRange")
        _closed(window, frozenset({"start", "end"}), f"temporal.{dimension}.asOfRange")
        return AsOfRange(
            start=_instant(window.get("start"), f"temporal.{dimension}.start", finite=True),
            end=_instant(window.get("end"), f"temporal.{dimension}.end", finite=True),
        )
    if tag == "history":
        _closed(_mapping(body, f"temporal.{dimension}.history"), frozenset(), "history")
        return History()
    raise ObjectQueryError(f"temporal.{dimension}: unknown Temporal Selection {tag!r}")


def _temporal(doc: object) -> dict[TemporalDimension, TemporalSelection]:
    node = _mapping(doc, "temporal")
    _closed(node, frozenset(_DIMENSIONS), "temporal")
    if not node:
        raise ObjectQueryError("temporal: a present map names at least one dimension")
    return {
        dimension: _temporal_selection(node[dimension], dimension)
        for dimension in _DIMENSIONS
        if dimension in node
    }


def _order_by(doc: object) -> tuple[OrderKey, ...]:
    if not isinstance(doc, list) or not doc:
        raise ObjectQueryError("orderBy must be a non-empty list")
    keys: list[OrderKey] = []
    for item in cast("list[object]", doc):
        key = _mapping(item, "orderBy key")
        _closed(key, frozenset({"attr", "direction", "nulls"}), "orderBy key")
        attr = key.get("attr")
        if not isinstance(attr, str) or _MEMBER_REF.match(attr) is None:
            raise ObjectQueryError(f"orderBy: `attr` {attr!r} is not a valid attribute reference")
        # `direction` and `nulls` are optional (schema defaults `asc` and `last`); a
        # key that omits one deserializes to `None` so serialization can omit it
        # back (round-trip).
        direction: Literal["asc", "desc"] | None = None
        if "direction" in key:
            raw = key["direction"]
            if raw not in ("asc", "desc"):
                raise ObjectQueryError("orderBy: `direction` must be 'asc' or 'desc'")
            direction = raw
        nulls: Literal["first", "last"] | None = None
        if "nulls" in key:
            raw_nulls = key["nulls"]
            if raw_nulls not in ("first", "last"):
                raise ObjectQueryError("orderBy: `nulls` must be 'first' or 'last'")
            nulls = raw_nulls
        keys.append(OrderKey(attr=attr, direction=direction, nulls=nulls))
    return tuple(keys)


def _includes(doc: object) -> tuple[IncludePath, ...]:
    if not isinstance(doc, list) or not doc:
        raise ObjectQueryError("includes must be a non-empty list")
    paths: list[IncludePath] = []
    for entry in cast("list[object]", doc):
        path = _mapping(entry, "include path")
        _closed(path, frozenset({"appliesTo", "segments"}), "include path")
        applies_to = (
            _selection(path["appliesTo"], "include path appliesTo") if "appliesTo" in path else None
        )
        raw_segments = path.get("segments")
        if not isinstance(raw_segments, list) or not raw_segments:
            raise ObjectQueryError("include path `segments` must be a non-empty list")
        segments: list[IncludeSegment] = []
        for item in cast("list[object]", raw_segments):
            segment = _mapping(item, "include segment")
            _closed(segment, frozenset({"rel", "narrowTo"}), "include segment")
            rel = segment.get("rel")
            if not isinstance(rel, str) or _MEMBER_REF.match(rel) is None:
                raise ObjectQueryError(
                    f"include segment: `rel` {rel!r} is not a valid relationship reference"
                )
            narrow_to = (
                _selection(segment["narrowTo"], "include segment narrowTo")
                if "narrowTo" in segment
                else ()
            )
            segments.append(IncludeSegment(rel=rel, narrow_to=narrow_to))
        paths.append(IncludePath(segments=tuple(segments), applies_to=applies_to))
    return tuple(paths)


def _target(value: object) -> EntityIdentity:
    """The queried position an authored ``target`` spelling names.

    Split structurally rather than resolved: an Object Query names no model, so
    the canonical spelling round-trips exactly and preflight decides whether the
    connected model declares it.
    """
    spelling = _entity_name(value, "target")
    namespace, separator, name = spelling.rpartition(".")
    return EntityIdentity(namespace if separator else None, name if separator else spelling)


def deserialize(doc: object) -> ObjectQueryNode:
    """Parse an Object Query document and canonicalize its set-valued clauses."""
    node = _mapping(doc, "objectQuery")
    _closed(node, _CLAUSES, "objectQuery")
    for required in ("target", "predicate"):
        if required not in node:
            raise ObjectQueryError(f"objectQuery: missing required clause `{required}`")
    limit = node.get("limit")
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
        raise ObjectQueryError("limit must be a positive integer")
    return object_query(
        _target(node["target"]),
        deserialize_predicate(node["predicate"]),
        narrow_to=_selection(node["narrowTo"], "narrowTo") if "narrowTo" in node else None,
        temporal=_temporal(node["temporal"]) if "temporal" in node else None,
        order_by=_order_by(node["orderBy"]) if "orderBy" in node else (),
        limit=limit,
        includes=_includes(node["includes"]) if "includes" in node else (),
    )


def _order_key(key: OrderKey) -> dict[str, object]:
    # `direction` and `nulls` are optional in the schema (defaults `asc` and
    # `last`); each is emitted only when it was authored, so a key that omitted one
    # round-trips omitted and a key that authored it round-trips verbatim —
    # including an explicit `last`, which is distinguishable from omission.
    entry: dict[str, object] = {"attr": key.attr}
    if key.direction is not None:
        entry["direction"] = key.direction
    if key.nulls is not None:
        entry["nulls"] = key.nulls
    return entry


def _serialize_selection(selection: TemporalSelection) -> dict[str, object]:
    match selection:
        case AsOf(coordinate=coordinate):
            return {"asOf": coordinate}
        case AsOfRange(start=start, end=end):
            return {"asOfRange": {"start": start, "end": end}}
        case History():
            return {"history": {}}


def _serialize_path(path: IncludePath) -> dict[str, object]:
    segments: list[dict[str, object]] = []
    for segment in path.segments:
        entry: dict[str, object] = {"rel": segment.rel}
        if segment.narrow_to:
            entry["narrowTo"] = list(segment.narrow_to)
        segments.append(entry)
    # The source guard is optional, so an unguarded path round-trips without an
    # `appliesTo` key rather than with an empty one.
    if path.applies_to is None:
        return {"segments": segments}
    return {"appliesTo": list(path.applies_to), "segments": segments}


def serialize(query: ObjectQueryNode) -> dict[str, object]:
    """Emit the canonical document for one Object Query.

    Set-valued clauses are canonicalized defensively so a directly constructed
    query has the same wire identity as a deserialized one.
    """
    canonical = object_query(
        query.target,
        query.predicate,
        narrow_to=query.narrow_to,
        temporal=query.temporal,
        order_by=query.order_by,
        limit=query.limit,
        includes=query.includes,
    )
    doc: dict[str, object] = {
        "target": canonical.target.canonical,
        "predicate": serialize_predicate(canonical.predicate),
    }
    if canonical.narrow_to is not None:
        doc["narrowTo"] = list(canonical.narrow_to)
    if canonical.temporal:
        doc["temporal"] = {
            dimension: _serialize_selection(canonical.temporal[dimension])
            for dimension in _DIMENSIONS
            if dimension in canonical.temporal
        }
    if canonical.order_by:
        doc["orderBy"] = [_order_key(key) for key in canonical.order_by]
    if canonical.limit is not None:
        doc["limit"] = canonical.limit
    if canonical.includes:
        doc["includes"] = [_serialize_path(path) for path in canonical.includes]
    return doc
