"""Strict JSON loading with value-local numeric provenance."""

from __future__ import annotations

import decimal
import json
import math
import sys
from collections.abc import Callable, Mapping
from typing import Self, cast

from parallax.core.base._neutral import ManagedValueExclusion
from parallax.core.wire._types import WireValue


class _ImmutableAuthoredNumber:
    __slots__ = ()

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> Self:
        return self


class _AuthoredInt(int, _ImmutableAuthoredNumber):
    token: str

    def __new__(cls, token: str) -> int:
        if exceeds_json_int_space(token):
            return _OutOfSpaceAuthoredInt(token)
        if token == "-0":
            number = int.__new__(cls, 0)
            number.token = token
            return number
        return int(token)


class _OutOfSpaceAuthoredInt(_AuthoredInt, ManagedValueExclusion):
    def __new__(cls, token: str) -> _OutOfSpaceAuthoredInt:
        number = int.__new__(cls, 0)
        number.token = token
        return number


class _AuthoredFloat(float, _ImmutableAuthoredNumber):
    token: str

    def __new__(cls, token: str) -> float:
        value = float(token)
        if not math.isfinite(value):
            return _OutOfSpaceAuthoredFloat(token)
        if decimal.Decimal(token) == decimal.Decimal.from_float(value):
            return value
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


class _SourceState:
    __slots__ = ("name_cache", "source")

    def __init__(self, name_cache: dict[str, str] | None) -> None:
        self.name_cache = name_cache
        self.source = ""

    def reject_constant(self, token: str) -> object:
        raise json.JSONDecodeError(f"invalid JSON numeric constant {token!r}", self.source, 0)

    def unique_object(self, pairs: list[tuple[str, object]]) -> Mapping[str, object]:
        value: dict[str, object] = {}
        for name, member in pairs:
            if self.name_cache is not None:
                name = self.name_cache.setdefault(name, name)
            if name in value:
                raise json.JSONDecodeError(f"duplicate object member name {name!r}", self.source, 0)
            value[name] = member
        return value


class _PreparedLoader:
    __slots__ = ("_decoder", "_state")

    def __init__(self, name_cache: dict[str, str] | None) -> None:
        self._state = _SourceState(name_cache)
        self._decoder = json.JSONDecoder(
            parse_int=_AuthoredInt,
            parse_float=_AuthoredFloat,
            parse_constant=self._state.reject_constant,
            object_pairs_hook=self._state.unique_object,
        )

    def __call__(self, text: str | bytes) -> WireValue:
        self._state.source = _decoded_source(text)
        try:
            return cast("WireValue", self._decoder.decode(self._state.source))
        finally:
            self._state.source = ""


def prepared_loads(
    *, name_cache: dict[str, str] | None = None
) -> Callable[[str | bytes], WireValue]:
    """Prepare strict JSON decoding state for a sequence of independent values."""
    return _PreparedLoader(name_cache)


def loads(text: str | bytes, *, name_cache: dict[str, str] | None = None) -> WireValue:
    """Parse any JSON root, rejecting duplicate names and non-JSON constants."""
    return _PreparedLoader(name_cache)(text)
