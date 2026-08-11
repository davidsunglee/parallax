"""Canonical, format-agnostic serde for operations AND the metamodel.

The canonical model is plain JSON-compatible data (dicts / lists / scalars) — the
same in-memory shape an implementation's operation algebra and metamodel
serialize to. This module provides pluggable format writers (JSON + YAML),
mirroring Reladomo's ``SerialWriter`` seam, and the round-trip property the m-case-format
harness asserts:

    serialize(deserialize(x)) == x

for BOTH the operation encoding and the model descriptor, in BOTH formats.

The deserializer is the inverse of the serializer for the JSON/YAML data model.
Because the canonical model is already JSON-compatible, round-trip fidelity is
about formatting determinism: a node must serialize the same way after a
serialize -> deserialize cycle. We canonicalize by sorting object keys and by
normalizing the one order-insensitive list, ``deepFetch.paths``.
"""

from __future__ import annotations

import json
from typing import Any

import yaml

from .portable_literal import AuthoredNumber

JSON = "json"
YAML = "yaml"
FORMATS = (JSON, YAML)


def _canonicalize(value: Any) -> Any:
    """Return a deterministically-ordered, JSON-compatible copy of *value*.

    Object keys are sorted. Lists keep their order because it is significant in
    the algebra and in attribute/row sequences, except ``deepFetch.paths``, which
    is a canonicalized set. Scalars pass through unchanged, except an
    :class:`~reference_harness.portable_literal.AuthoredNumber`, whose authored
    digits are decode context rather than document content: the document holds
    the number, which is what re-reading the written form answers, so keeping the
    carrier would break the round-trip property this module asserts.
    """
    if isinstance(value, dict):
        canonical = {key: _canonicalize(value[key]) for key in sorted(value)}
        deep_fetch = canonical.get("deepFetch")
        if len(canonical) == 1 and isinstance(deep_fetch, dict):
            paths = deep_fetch.get("paths")
            if isinstance(paths, list):
                deep_fetch["paths"] = _canonical_include_paths(paths)
        return canonical
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, AuthoredNumber):
        return float(value)
    return value


def _relationship_key(spelling: str) -> tuple[str, str, str]:
    *owner, relationship = spelling.split(".")
    *namespace, entity = owner
    return ".".join(namespace), entity, relationship


def _narrow_key(value: object) -> tuple[int, tuple[object, ...]]:
    if value is None:
        return (0, ())
    if not isinstance(value, dict) or not isinstance(value.get("to"), list):
        raise TypeError
    return (1, tuple(value["to"]))


def _include_path_key(
    path: dict[str, Any],
) -> tuple[object, ...]:
    segments = path["segments"]
    if not isinstance(segments, list):
        raise TypeError
    segment_keys = tuple(
        (_relationship_key(segment["rel"]), _narrow_key(segment.get("narrow")))
        for segment in segments
        if isinstance(segment, dict) and isinstance(segment.get("rel"), str)
    )
    if len(segment_keys) != len(segments):
        raise TypeError
    return segment_keys, _narrow_key(path.get("narrow"))


def _include_path_shape(path: dict[str, Any]) -> tuple[object, tuple[object, ...]]:
    segments = path["segments"]
    if not isinstance(segments, list):
        raise TypeError
    return _freeze(path.get("narrow")), tuple(_freeze(segment) for segment in segments)


def _freeze(value: Any) -> object:
    if isinstance(value, dict):
        return tuple((key, _freeze(item)) for key, item in sorted(value.items()))
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _canonical_include_paths(paths: list[Any]) -> list[Any]:
    if not all(isinstance(path, dict) and "segments" in path for path in paths):
        return paths
    try:
        unique = {_freeze(path): path for path in paths}
        candidates = [(path, _include_path_shape(path)) for path in unique.values()]
        maximal = [
            path
            for path, shape in candidates
            if not any(
                shape[0] == extension_shape[0]
                and len(shape[1]) < len(extension_shape[1])
                and extension_shape[1][: len(shape[1])] == shape[1]
                for _, extension_shape in candidates
            )
        ]
        return sorted(maximal, key=_include_path_key)
    except (KeyError, TypeError, ValueError):
        return paths


# --- format writers (the pluggable seam) ----------------------------------


def _write(value: Any, fmt: str) -> str:
    canonical = _canonicalize(value)
    if fmt == JSON:
        return json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    if fmt == YAML:
        return yaml.safe_dump(canonical, sort_keys=True, default_flow_style=False)
    raise ValueError(f"unknown serde format: {fmt!r}")


def _read(text: str, fmt: str) -> Any:
    if fmt == JSON:
        return json.loads(text)
    if fmt == YAML:
        return yaml.safe_load(text)
    raise ValueError(f"unknown serde format: {fmt!r}")


# --- public API ------------------------------------------------------------


def canonical(value: Any) -> Any:
    """Return the deterministic, JSON-compatible canonical form of *value*.

    This is the public canonicalization used to decide node *identity*: two
    authored encodings that canonicalize to the same value (object keys sorted;
    list order preserved wherever the algebra makes it significant; include paths
    normalized as a set) denote the same operation. The group-precedence fixtures
    rely on this: a prefix surface and a fluent surface are illustrative DX only,
    and both MUST canonicalize to the single mandated ``group`` node.
    """
    return _canonicalize(value)


def serialize(value: Any, fmt: str = JSON) -> str:
    """Serialize a canonical node to the given format."""
    return _write(value, fmt)


def deserialize(text: str, fmt: str = JSON) -> Any:
    """Deserialize a node from the given format back into the canonical model."""
    return _read(text, fmt)


def roundtrip(value: Any, fmt: str) -> Any:
    """serialize -> deserialize for a single format, returning the parsed node."""
    return deserialize(serialize(value, fmt), fmt)


def assert_roundtrip(value: Any) -> None:
    """Assert ``serialize(deserialize(x)) == x`` for both JSON and YAML.

    Concretely: serializing the canonicalized value, parsing it back, and
    re-serializing must yield byte-identical text in each format. This is the
    fixed-point property an implementation's serde module must also satisfy.
    """
    canonical = _canonicalize(value)
    for fmt in FORMATS:
        first = serialize(canonical, fmt)
        parsed = deserialize(first, fmt)
        second = serialize(parsed, fmt)
        if first != second:
            raise AssertionError(
                f"serde round-trip is not a fixed point for format {fmt!r}:\n"
                f"  first:  {first!r}\n  second: {second!r}"
            )
        if _canonicalize(parsed) != canonical:
            raise AssertionError(
                f"serde round-trip changed the value for format {fmt!r}:\n"
                f"  before: {canonical!r}\n  after:  {_canonicalize(parsed)!r}"
            )
