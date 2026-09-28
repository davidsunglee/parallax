"""Faults that turn a float zero negative at one conversion owner.

Each replaces a module attribute of the Wire codec, so every caller resolving it
at call time sees the fault. ``_canonical_spelling`` spells a document leaf's
driver value (through ``encode_leaf``) and every reported Wire bind alike;
``_decode_float32`` and ``_decode_float64`` are how a Wire number reaches a
float member, so their fault reaches a scalar driver bind while the reported
bind, re-encoded, still reads ``0.0``.

Exported names carry no leading underscore: privacy is this module's.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

import pytest

import parallax.core.wire._codec as wire_codec
from parallax.core.base import Float32, Float64, NeutralType
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
    for name in ("_decode_float32", "_decode_float64"):
        monkeypatch.setattr(wire_codec, name, _negating_zero(getattr(wire_codec, name)))


def _negating_zero(decode: Callable[[object, NeutralType], Any]) -> Callable[..., Any]:
    def decoded(value: object, neutral_type: NeutralType) -> Any:
        literal = decode(value, neutral_type)
        return dataclasses.replace(literal, managed=-0.0) if literal.managed == 0.0 else literal

    return decoded
