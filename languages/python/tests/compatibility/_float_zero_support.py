"""Faults that turn a float zero negative at one conversion owner.

Each replaces a module attribute of the Wire codec, so every caller resolving it
at call time sees the fault. ``_canonical_spelling`` spells a document leaf's
driver value (through ``encode_leaf``) and every reported Wire bind alike;
``nearest_float_at_width`` is how ``_decode_float`` projects an authored Wire
number onto its declared width, and ``host_float_binary32`` how a bare float
reaches a Float32 member, so their fault reaches a scalar driver bind while the
reported bind, re-encoded, still reads ``0.0``.

Exported names carry no leading underscore: privacy is this module's.
"""

from __future__ import annotations

import decimal

import pytest

import parallax.core.wire._codec as wire_codec
from parallax.core.base import Float32, Float64, NeutralType, nearest_float_at_width
from parallax.core.base._neutral import host_float_binary32
from parallax.core.wire import WireValue

__all__ = ["project_float_zero_negative", "spell_float_zero_negative"]


def spell_float_zero_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    original = wire_codec._canonical_spelling  # pyright: ignore[reportPrivateUsage]

    def spelling(neutral_type: NeutralType, managed: object) -> WireValue:
        spelled = original(neutral_type, managed)
        negative = isinstance(neutral_type, (Float32, Float64)) and spelled == 0.0
        return -0.0 if negative else spelled

    monkeypatch.setattr(wire_codec, "_canonical_spelling", spelling)


def project_float_zero_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    def nearest(
        number: int | float | decimal.Decimal, neutral_type: Float32 | Float64
    ) -> float | None:
        projected = nearest_float_at_width(number, neutral_type)
        return -0.0 if projected == 0.0 else projected

    def binary32(value: float) -> float | None:
        projected = host_float_binary32(value)
        return -0.0 if projected == 0.0 else projected

    monkeypatch.setattr(wire_codec, "nearest_float_at_width", nearest)
    monkeypatch.setattr(wire_codec, "host_float_binary32", binary32)
