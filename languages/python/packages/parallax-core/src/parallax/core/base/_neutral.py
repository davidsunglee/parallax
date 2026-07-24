"""The structured Neutral Type algebra and its value spaces (m-core).

Every typed model fact draws its type from this closed algebra: Attribute and
Value Object Attribute metadata, operation literals and assignments, and
neutral row cells. A structured value carries no serialized spelling — parsing
and formatting the ``decimal(p,s)`` family and its siblings belongs to the
interchange seams that transport them.

Value-space membership is asked of native carriers, so a seam that received a
value in its portable literal form decodes it first. The literal form is a
property of the value space rather than of any one transport — every seam that
carries a ``NeutralValue`` through the JSON data model spells it the same way —
so :func:`decode_neutral_literal` states that one inverse here instead of
leaving each seam to invent its own.
"""

from __future__ import annotations

import datetime as _dt
import decimal as _decimal
import math as _math
import struct as _struct
import uuid as _uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, TypeGuard, cast

__all__ = [
    "BOOLEAN",
    "BYTES",
    "DATE",
    "FLOAT32",
    "FLOAT64",
    "INT32",
    "INT64",
    "JSON",
    "STRING",
    "TIME",
    "TIMESTAMP",
    "UUID",
    "Boolean",
    "Bytes",
    "Date",
    "Decimal",
    "Float32",
    "Float64",
    "Int32",
    "Int64",
    "Json",
    "NeutralType",
    "String",
    "Time",
    "Timestamp",
    "Uuid",
    "decode_neutral_literal",
    "matches_neutral_type",
]


@dataclass(frozen=True, slots=True)
class Boolean:
    """The two truth values."""


@dataclass(frozen=True, slots=True)
class Int32:
    """32-bit signed integers."""


@dataclass(frozen=True, slots=True)
class Int64:
    """64-bit signed integers."""


@dataclass(frozen=True, slots=True)
class Float32:
    """Finite IEEE-754 binary32 values; NaN and the infinities are not members."""


@dataclass(frozen=True, slots=True)
class Float64:
    """Finite IEEE-754 binary64 values; NaN and the infinities are not members."""


@dataclass(frozen=True, slots=True)
class Decimal:
    """Exact fixed-point values at a declared precision and scale.

    The sole parametric variant. Both parameters are required and bounded by
    ``precision >= 1`` and ``0 <= scale <= precision``, so every constructed
    value has a serializable spelling; a violation raises :class:`ValueError`.
    """

    precision: int
    scale: int

    def __post_init__(self) -> None:
        if self.precision < 1:
            raise ValueError(f"decimal precision must be at least 1, got {self.precision}")
        if not 0 <= self.scale <= self.precision:
            raise ValueError(
                f"decimal scale must be between 0 and the precision {self.precision}, "
                f"got {self.scale}"
            )


@dataclass(frozen=True, slots=True)
class String:
    """UTF-8 encodable Unicode text compared by codepoint."""


@dataclass(frozen=True, slots=True)
class Bytes:
    """Finite octet sequences."""


@dataclass(frozen=True, slots=True)
class Date:
    """Timezone-naive proleptic-Gregorian calendar dates."""


@dataclass(frozen=True, slots=True)
class Time:
    """Timezone-naive wall-clock times of day at microsecond precision."""


@dataclass(frozen=True, slots=True)
class Timestamp:
    """Absolute UTC instants at microsecond precision."""


@dataclass(frozen=True, slots=True)
class Uuid:
    """128-bit UUID values; text case carries no information."""


@dataclass(frozen=True, slots=True)
class Json:
    """Structured content: any JSON data-model value except a bare top-level null."""


type NeutralType = (
    Boolean
    | Int32
    | Int64
    | Float32
    | Float64
    | Decimal
    | String
    | Bytes
    | Date
    | Time
    | Timestamp
    | Uuid
    | Json
)
"""The closed structured type algebra. Every typed model fact draws its type
from exactly one of these variants; no module defines a parallel vocabulary."""

# The shared instance of each nullary variant. Every variant is a frozen value
# object, so these are allocation conveniences rather than identities: a freshly
# constructed ``Int32()`` equals ``INT32`` and matches the same patterns.
BOOLEAN: Final[Boolean] = Boolean()
INT32: Final[Int32] = Int32()
INT64: Final[Int64] = Int64()
FLOAT32: Final[Float32] = Float32()
FLOAT64: Final[Float64] = Float64()
STRING: Final[String] = String()
BYTES: Final[Bytes] = Bytes()
DATE: Final[Date] = Date()
TIME: Final[Time] = Time()
TIMESTAMP: Final[Timestamp] = Timestamp()
UUID: Final[Uuid] = Uuid()
JSON: Final[Json] = Json()

# The two's-complement bounds of the integer value spaces, inclusive.
_INT32_BOUNDS: Final[tuple[int, int]] = (-(2**31), 2**31 - 1)
_INT64_BOUNDS: Final[tuple[int, int]] = (-(2**63), 2**63 - 1)


def matches_neutral_type(value: object, declared: NeutralType) -> bool:
    """Whether ``value`` is a member of ``declared``'s logical value space.

    Exact membership, not a category guess: an integer outside its declared
    width, a non-finite float, a decimal the declared precision and scale
    cannot represent exactly, text with no UTF-8 encoding, and a bare ``None``
    are all non-members. Null is a member of no space, so a nullable position
    admits it through its own contract rather than through this check.

    The domain is decoded values, one Python carrier per space —
    ``bool``/``int``/``float``/``decimal.Decimal``/``str``/``bytes``/
    ``datetime.date``/``datetime.time``/``datetime.datetime``/``uuid.UUID``,
    and the JSON data model for :class:`Json`. A wire spelling is never a
    member of the space it encodes, so a seam holding one calls
    :func:`decode_neutral_literal` before asking: the string ``"2026-01-01"``
    is not a :class:`Date` value and the integer ``2`` is not a
    :class:`Float64` value.

    ``bool`` is a Python ``int`` subclass but a distinct space, so an integer
    space rejects it and :class:`Boolean` accepts nothing else.
    """
    match declared:
        case Boolean():
            return isinstance(value, bool)
        case Int32():
            return _is_integer(value) and _INT32_BOUNDS[0] <= value <= _INT32_BOUNDS[1]
        case Int64():
            return _is_integer(value) and _INT64_BOUNDS[0] <= value <= _INT64_BOUNDS[1]
        case Float32():
            return isinstance(value, float) and _math.isfinite(value) and _fits_binary32(value)
        case Float64():
            return isinstance(value, float) and _math.isfinite(value)
        case Decimal(precision, scale):
            return isinstance(value, _decimal.Decimal) and _is_exact_decimal(
                value, precision, scale
            )
        case String():
            return isinstance(value, str) and _is_utf8_encodable(value)
        case Bytes():
            return isinstance(value, bytes)
        case Date():
            return isinstance(value, _dt.date) and not isinstance(value, _dt.datetime)
        case Time():
            return isinstance(value, _dt.time) and value.tzinfo is None
        case Timestamp():
            return isinstance(value, _dt.datetime) and value.utcoffset() is not None
        case Uuid():
            return isinstance(value, _uuid.UUID)
        case Json():
            return value is not None and _is_json_value(value)


def decode_neutral_literal(value: object, declared: NeutralType) -> object:
    """``value`` as a carrier of ``declared``'s value space, when it spells one.

    The inverse of the portable literal encoding: a JSON number spells a
    :class:`Decimal` and widens to a float space, an ISO-8601 string spells a
    :class:`Date`, :class:`Time`, or :class:`Timestamp`, a canonical UUID string
    spells a :class:`Uuid`, and a lowercase-hex string spells :class:`Bytes`.
    Every other space is already carried natively, so its literal decodes to
    itself.

    Total and nonthrowing: a value that is not a literal of ``declared`` — a
    malformed spelling, a truth value where a number belongs, or an unrelated
    object — is returned unchanged, so :func:`matches_neutral_type` alone
    decides membership and this function never classifies a defect on its own.
    """
    match declared:
        case Float32() | Float64() if _is_integer(value):
            return float(value)
        case Decimal() if _is_integer(value):
            return _decimal.Decimal(value)
        case Decimal() if isinstance(value, float):
            # Through the shortest round-tripping text, so the decoded value has
            # the digits the literal was written with rather than the binary
            # expansion of the float that carried it.
            return _decimal.Decimal(repr(value))
        case Bytes() if isinstance(value, str):
            return _decoded(bytes.fromhex, value)
        case Date() if isinstance(value, str):
            return _decoded(_dt.date.fromisoformat, value)
        case Time() if isinstance(value, str):
            return _decoded(_dt.time.fromisoformat, value)
        case Timestamp() if isinstance(value, str):
            return _decoded(_dt.datetime.fromisoformat, value)
        case Uuid() if isinstance(value, str):
            return _decoded(_uuid.UUID, value)
        case _:
            return value


def _decoded[T](decode: Callable[[str], T], literal: str) -> T | str:
    """``literal`` decoded, or the literal itself when it is not well formed."""
    try:
        return decode(literal)
    except ValueError:
        return literal


def _is_integer(value: object) -> TypeGuard[int]:
    """Whether ``value`` is an integer rather than a truth value."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_utf8_encodable(value: str) -> bool:
    """Whether text has a UTF-8 encoding; an unpaired surrogate has none."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _fits_binary32(value: float) -> bool:
    """Whether a finite binary64 value has a finite binary32 counterpart.

    Narrowing loses precision but not membership — every in-range value rounds
    to some binary32 value — so only a magnitude that overflows to infinity
    falls outside the space.
    """
    try:
        _struct.pack("<f", value)
    except OverflowError:
        return False
    return True


def _is_exact_decimal(value: _decimal.Decimal, precision: int, scale: int) -> bool:
    """Whether ``value`` is ``unscaled * 10**-scale`` within ``precision`` digits.

    Exact: a value needing more fractional digits than ``scale`` is not a
    member, because representing it would require rounding. Trailing zeros
    carry no value, so ``1.500`` and ``1.5`` are the same member.
    """
    _sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):
        return False
    coefficient = 0
    for digit in digits:
        coefficient = coefficient * 10 + digit
    if coefficient == 0:
        return True
    while coefficient % 10 == 0:
        coefficient //= 10
        exponent += 1
    if exponent < -scale:
        return False
    return len(str(coefficient)) + exponent + scale <= precision


def _is_json_value(value: object) -> bool:
    """Whether ``value`` is a JSON data-model value, ``null`` included.

    Only the top-level position excludes ``null``; nested nulls are ordinary
    structured content. A non-finite float has no JSON encoding and an object
    member name is always text.
    """
    if value is None or isinstance(value, (bool, int)):
        return True
    if isinstance(value, str):
        return _is_utf8_encodable(value)
    if isinstance(value, float):
        return _math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json_value(item) for item in cast("list[object]", value))
    if isinstance(value, dict):
        return all(
            isinstance(name, str) and _is_json_value(member)
            for name, member in cast("dict[object, object]", value).items()
        )
    return False
