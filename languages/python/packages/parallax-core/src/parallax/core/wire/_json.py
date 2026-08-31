"""Strict JSON loading with value-local numeric provenance."""

from __future__ import annotations

import decimal
import json
import math
import sys
from collections.abc import Mapping
from typing import cast

from parallax.core.base._neutral import ManagedValueExclusion
from parallax.core.wire._types import WireValue


class _AuthoredInt(int):
    token: str

    def __new__(cls, token: str) -> _AuthoredInt:
        if exceeds_json_int_space(token):
            return _OutOfSpaceAuthoredInt(token)
        value = int(decimal.Decimal(token))
        number = super().__new__(cls, value)
        number.token = token
        return number


class _OutOfSpaceAuthoredInt(_AuthoredInt, ManagedValueExclusion):
    def __new__(cls, token: str) -> _OutOfSpaceAuthoredInt:
        number = int.__new__(cls, 0)
        number.token = token
        return number


class _AuthoredFloat(float):
    token: str

    def __new__(cls, token: str) -> _AuthoredFloat:
        value = float(token)
        if not math.isfinite(value):
            return _OutOfSpaceAuthoredFloat(token)
        number = super().__new__(cls, value)
        number.token = token
        return number


class _OutOfSpaceAuthoredFloat(_AuthoredFloat, ManagedValueExclusion):
    def __new__(cls, token: str) -> _OutOfSpaceAuthoredFloat:
        value = -0.0 if token.startswith("-") else 0.0
        number = float.__new__(cls, value)
        number.token = token
        return number


def authored_number(token: str) -> int | float:
    """Construct private provenance for one JSON/YAML number token."""
    if "." in token or "e" in token.lower():
        return _AuthoredFloat(token)
    return _AuthoredInt(token)


def authored_token(value: int | float) -> str | None:
    if isinstance(value, (_AuthoredInt, _AuthoredFloat)):
        return value.token
    return None


def exceeds_json_int_space(token: str) -> bool:
    limit = sys.get_int_max_str_digits()
    unsigned = token[1:] if token[:1] in ("-", "+") else token
    significant = unsigned.lstrip("0") or "0"
    return limit != 0 and len(significant) > limit


def _decoded_source(text: str | bytes) -> str:
    if isinstance(text, str):
        return text
    return text.decode(json.detect_encoding(text), errors="surrogatepass")


def loads(text: str | bytes) -> WireValue:
    """Parse any JSON root, rejecting duplicate names and non-JSON constants."""
    source = _decoded_source(text)

    def reject_constant(token: str) -> object:
        raise json.JSONDecodeError(f"invalid JSON numeric constant {token!r}", source, 0)

    def unique_object(pairs: list[tuple[str, object]]) -> Mapping[str, object]:
        value: dict[str, object] = {}
        for name, member in pairs:
            if name in value:
                raise json.JSONDecodeError(f"duplicate object member name {name!r}", source, 0)
            value[name] = member
        return value

    return cast(
        "WireValue",
        json.loads(
            text,
            parse_int=_AuthoredInt,
            parse_float=_AuthoredFloat,
            parse_constant=reject_constant,
            object_pairs_hook=unique_object,
        ),
    )
