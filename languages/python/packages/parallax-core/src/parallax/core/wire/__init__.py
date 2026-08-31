"""Strict JSON loading and the exhaustive Neutral Wire Codec (m-wire)."""

from __future__ import annotations

from parallax.core.wire._codec import (
    WireDecodingError,
    WireDecodingReason,
    WireEncodingError,
    decode_canonical_wire,
    decode_wire,
    encode_wire,
)
from parallax.core.wire._json import loads
from parallax.core.wire._types import WireValue

__all__ = [
    "WireDecodingError",
    "WireDecodingReason",
    "WireEncodingError",
    "WireValue",
    "decode_canonical_wire",
    "decode_wire",
    "encode_wire",
    "loads",
]
