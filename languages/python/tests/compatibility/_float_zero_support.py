"""Faults that turn a float zero negative at one conversion owner.

Each replaces a module attribute of the Wire codec, so every caller resolving it
at call time sees the fault. ``_canonical_spelling`` spells every reported Wire
bind, and with the managed encoder the document codec spells a stored document
leaf through, also replaced, a document leaf's driver value;
``_decode_float32`` and ``_decode_float64`` are how a decoded Wire number
reaches a float member, and the Wire lane's float converters how an authored
row's does, so their fault reaches a scalar driver bind while the reported
bind, re-encoded, still reads ``0.0``. A converter is resolved when a model's
write preparation is built, so the fault precedes the run it reaches.

Exported names carry no leading underscore: privacy is this module's.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from types import MappingProxyType
from typing import Any

import pytest

import parallax.core.document_codec._leaf as document_leaf
import parallax.core.wire._codec as wire_codec
from parallax.core.base import (
    FLOAT32,
    FLOAT64,
    Float32,
    Float64,
    ManagedValue,
    NeutralType,
    ScalarConverter,
)
from parallax.core.wire import WireValue

__all__ = ["project_float_zero_negative", "spell_float_zero_negative"]


def spell_float_zero_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    original = wire_codec._canonical_spelling  # pyright: ignore[reportPrivateUsage]

    def spelling(neutral_type: NeutralType, managed: object) -> WireValue:
        spelled = original(neutral_type, managed)
        negative = isinstance(neutral_type, (Float32, Float64)) and spelled == 0.0
        return -0.0 if negative else spelled

    monkeypatch.setattr(wire_codec, "_canonical_spelling", spelling)
    managed: Callable[[NeutralType, ManagedValue], WireValue] = vars(document_leaf)[
        "encode_managed_wire"
    ]

    def managed_spelling(neutral_type: NeutralType, value: ManagedValue) -> WireValue:
        spelled = managed(neutral_type, value)
        negative = isinstance(neutral_type, (Float32, Float64)) and spelled == 0.0
        return -0.0 if negative else spelled

    monkeypatch.setattr(document_leaf, "encode_managed_wire", managed_spelling)


def project_float_zero_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("_decode_float32", "_decode_float64"):
        monkeypatch.setattr(wire_codec, name, _negating_zero(getattr(wire_codec, name)))
    converters = dict(wire_codec._NULLARY_WIRE_CONVERTERS)  # pyright: ignore[reportPrivateUsage]
    for declared in (FLOAT32, FLOAT64):
        converters[type(declared)] = _negating_converted_zero(converters[type(declared)])
    monkeypatch.setattr(wire_codec, "_NULLARY_WIRE_CONVERTERS", MappingProxyType(converters))


def _negating_converted_zero(convert: ScalarConverter) -> ScalarConverter:
    def converted(value: object) -> object:
        managed = convert(value)
        return -0.0 if managed == 0.0 else managed

    return converted


def _negating_zero(decode: Callable[[object, NeutralType], Any]) -> Callable[..., Any]:
    def decoded(value: object, neutral_type: NeutralType) -> Any:
        literal = decode(value, neutral_type)
        return dataclasses.replace(literal, managed=-0.0) if literal.managed == 0.0 else literal

    return decoded
