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
serialize -> deserialize cycle. We canonicalize by sorting object keys so the
written form is deterministic regardless of authoring order.
"""

from __future__ import annotations

import json
from typing import Any

import yaml

JSON = "json"
YAML = "yaml"
FORMATS = (JSON, YAML)


def _canonicalize(value: Any) -> Any:
    """Return a deterministically-ordered, JSON-compatible copy of *value*.

    Object keys are sorted; lists keep their order (order is significant in the
    algebra and in attribute/row sequences). Scalars pass through unchanged.
    """
    if isinstance(value, dict):
        return {key: _canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    return value


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
    list order preserved, since order is significant in the algebra) denote the
    same operation. The group-precedence fixtures rely on this: a prefix surface
    and a fluent surface are illustrative DX only, and both MUST canonicalize to
    the single mandated ``group`` node.
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
