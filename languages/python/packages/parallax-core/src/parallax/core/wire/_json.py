from __future__ import annotations

import decimal
import json
import math
import sys
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from json.encoder import encode_basestring_ascii
from typing import Final, Self, cast

from parallax.core.base import FrozenMap, frozen_map_json_backing
from parallax.core.base._neutral import ManagedValueExclusion, host_float_number
from parallax.core.wire._types import WireValue

_MAX_UNAMBIGUOUS_TOKEN_LENGTH = 16


class _ImmutableAuthoredNumber:
    __slots__ = ()
    token: str

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> Self:
        return self


class _AuthoredInt(int, _ImmutableAuthoredNumber):
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
    __slots__ = ("token",)

    def __new__(cls, token: str) -> float:
        value = float(token)
        if not math.isfinite(value):
            return _OutOfSpaceAuthoredFloat(token)
        # The digits go only when every member reads them from the bare float too: its
        # exact value, and the number `host_float_number` gives a float32 member. A float
        # token of at most _MAX_UNAMBIGUOUS_TOKEN_LENGTH characters spends one on its
        # point or exponent, leaving at most fifteen significant digits, and no two such
        # decimals name the same binary64, so an exact one is also that float32 number.
        authored = decimal.Decimal(token)
        unambiguous = len(token) <= _MAX_UNAMBIGUOUS_TOKEN_LENGTH
        if authored == decimal.Decimal.from_float(value) and (
            unambiguous or authored == host_float_number(value)
        ):
            return value
        # The same bound makes a normal float's shortest host spelling name the token's
        # own number; any other token is compared with that spelling when written.
        kind = (
            _AuthoredFloat
            if unambiguous and abs(value) >= sys.float_info.min
            else _AmbiguousAuthoredFloat
        )
        number = float.__new__(kind, value)
        number.token = token
        return number


class _AmbiguousAuthoredFloat(_AuthoredFloat):
    """A retained float whose digits leave open whether its shortest host spelling
    names the same number."""

    __slots__ = ()


class _OutOfSpaceAuthoredFloat(_AuthoredFloat, ManagedValueExclusion):
    __slots__ = ()

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


_HOST_SPELLED: Final = frozenset(
    {str, int, float, bool, type(None), FrozenMap, _AuthoredInt, _AuthoredFloat}
)
"""Member types the host encoder spells with their own meaning; a FrozenMap's
members are judged when the encoder reaches it."""
_OUT_OF_SPACE: Final = frozenset({_OutOfSpaceAuthoredFloat, _OutOfSpaceAuthoredInt})


class _HostSpellingChangesMeaning(Exception):
    pass


def _host_spelling_keeps_meaning(number: _AuthoredFloat) -> bool:
    spelled = float.__repr__(number)
    return spelled == number.token or decimal.Decimal(spelled) == decimal.Decimal(number.token)


def _require_host_spelling(members: Iterable[object]) -> None:
    if not _HOST_SPELLED.issuperset(map(type, members)):
        _require_host_spelled_members(members)


def _require_host_spelled_members(members: Iterable[object]) -> None:
    pending = [members]
    while pending:
        for member in pending.pop():
            kind = type(member)
            if kind is _AmbiguousAuthoredFloat:
                if not _host_spelling_keeps_meaning(cast("_AuthoredFloat", member)):
                    raise _HostSpellingChangesMeaning
            elif kind in _OUT_OF_SPACE:
                raise _HostSpellingChangesMeaning
            elif kind is dict or kind is list or kind is tuple:
                nested = (
                    cast("dict[object, object]", member).values()
                    if kind is dict
                    else cast("Sequence[object]", member)
                )
                if not _HOST_SPELLED.issuperset(map(type, nested)):
                    pending.append(nested)


def _judged_backing(value: object) -> object:
    if type(value) is FrozenMap:
        backing = frozen_map_json_backing(cast("FrozenMap[object, object]", value))
        members = backing.values()
        if not _HOST_SPELLED.issuperset(map(type, members)):
            _require_host_spelled_members(members)
        return backing
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


_HOST_ENCODE: Final = json.JSONEncoder(default=_judged_backing).encode
_CONTAINERS: Final = frozenset({FrozenMap, dict, list, tuple})


def _write_exactly(document: object) -> str:
    if type(document) not in _CONTAINERS:
        return _exact_scalar(document)
    parts: list[str] = []
    open_containers: list[tuple[Iterator[object], bool, int]] = []
    open_identities: set[int] = set()
    container = document
    while True:
        identity = id(container)
        if identity in open_identities:
            raise ValueError("Circular reference detected")
        open_identities.add(identity)
        kind = type(container)
        if kind is list or kind is tuple:
            parts.append("[")
            open_containers.append((iter(cast("Sequence[object]", container)), False, identity))
        else:
            backing = (
                frozen_map_json_backing(cast("FrozenMap[str, object]", container))
                if kind is FrozenMap
                else cast("dict[str, object]", container)
            )
            parts.append("{")
            open_containers.append((iter(backing.items()), True, identity))
        separator = ""
        while open_containers:
            members, is_object, identity = open_containers[-1]
            for member in members:
                parts.append(separator)
                separator = ", "
                if is_object:
                    name, member = cast("tuple[str, object]", member)
                    parts.append(encode_basestring_ascii(name))
                    parts.append(": ")
                if type(member) in _CONTAINERS:
                    container = member
                    break
                parts.append(_exact_scalar(member))
            else:
                open_containers.pop()
                open_identities.remove(identity)
                parts.append("}" if is_object else "]")
                separator = ", "
                continue
            break
        else:
            return "".join(parts)


def _exact_scalar(value: object) -> str:
    kind = type(value)
    if kind is str:
        return encode_basestring_ascii(cast("str", value))
    if kind is int or kind is _AuthoredInt:
        return int.__repr__(cast("int", value))
    if kind is _AuthoredFloat or (kind is float and math.isfinite(cast("float", value))):
        return float.__repr__(cast("float", value))
    if kind is _AmbiguousAuthoredFloat and _host_spelling_keeps_meaning(
        cast("_AuthoredFloat", value)
    ):
        return float.__repr__(cast("float", value))
    if kind is _AmbiguousAuthoredFloat or kind in _OUT_OF_SPACE:
        return str(decimal.Decimal(cast("_ImmutableAuthoredNumber", value).token))
    return _HOST_ENCODE(value)


def dump_document(document: object) -> str:
    """Serialize a structured document to JSON text for storage.

    Every number keeps the exact numeric meaning it was retained with, not its
    spelling. Immutable carriers are read in place; text is otherwise what
    ``json.dumps`` writes, including its failure for an unsupported value.
    """
    try:
        # Encoding first lets the encoder reject a cycle before the census walks
        # mutable containers it does not track; a FrozenMap retains only immutable ones.
        text = _HOST_ENCODE(document)
        _require_host_spelling((document,))
    except _HostSpellingChangesMeaning:
        return _write_exactly(document)
    return text
