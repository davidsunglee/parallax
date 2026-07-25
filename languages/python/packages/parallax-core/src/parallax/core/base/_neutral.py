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
    "coerce_neutral_input",
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
    :class:`Decimal` and, when some float of the target width carries it
    exactly, a :class:`Float32` or :class:`Float64`; an ISO-8601 string spells a
    :class:`Date`, :class:`Time`, or :class:`Timestamp`, a canonical UUID string
    spells a :class:`Uuid`, and a lowercase-hex string spells :class:`Bytes`.
    Every other space is already carried natively, so its literal decodes to
    itself.

    Total and nonthrowing: a value that is not a literal of ``declared`` — a
    malformed spelling, a truth value where a number belongs, an integer no
    float of the width represents exactly, a :class:`Time` or :class:`Timestamp`
    literal carrying non-zero sub-microsecond precision, or an unrelated
    object — is returned unchanged, so :func:`matches_neutral_type` alone decides
    membership and this function never rounds, truncates, overflows, or
    classifies a defect on its own.
    """
    match declared:
        case Float64() if _is_integer(value):
            return _integer_as_float(value, binary32=False)
        case Float32() if _is_integer(value):
            return _integer_as_float(value, binary32=True)
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
            return _decoded_temporal(_dt.time.fromisoformat, value)
        case Timestamp() if isinstance(value, str):
            return _decoded_temporal(_dt.datetime.fromisoformat, value)
        case Uuid() if isinstance(value, str):
            return _decoded(_uuid.UUID, value)
        case _:
            return value


def coerce_neutral_input(value: object, declared: NeutralType) -> object:
    """``value`` widened by the exact/lossless adjacent forms the developer
    input policy admits for ``declared`` (`python.md` "Neutral scalar type
    mapping", the input-policy column), and otherwise returned unchanged.

    This is the boundary the DEVELOPER-facing write validators call — a
    runtime argument already carries a native Python value, never a wire
    literal, so only the input policy's own narrow, exact/lossless typed
    widenings apply: an :class:`int` for a :class:`Decimal` (exact — decimal
    construction from an integer never rounds), an :class:`int` for a
    :class:`Float32` / :class:`Float64` (lossless only, reusing
    :func:`_integer_as_float`'s own exactness test), and a canonical UUID
    string for :class:`Uuid`. Every other case — INCLUDING a :class:`float`
    for a :class:`Decimal`, which the input policy explicitly rejects — is
    returned unchanged. There is no ISO date/time/timestamp string decode and
    no hex-string :class:`Bytes` decode here: those are wire spellings the
    case-format / descriptor serde seam (:func:`decode_neutral_literal`)
    decodes once at ingestion, never a form the developer input policy itself
    admits at this boundary.

    Total and nonthrowing, exactly like :func:`decode_neutral_literal`: a
    value this function does not recognize as one of the three widenings
    above passes through untouched, so :func:`matches_neutral_type` alone
    decides membership.
    """
    match declared:
        case Decimal() if _is_integer(value):
            return _decimal.Decimal(value)
        case Float64() if _is_integer(value):
            return _integer_as_float(value, binary32=False)
        case Float32() if _is_integer(value):
            return _integer_as_float(value, binary32=True)
        case Uuid() if isinstance(value, str):
            return _decoded(_uuid.UUID, value)
        case _:
            return value


def _integer_as_float(value: int, *, binary32: bool) -> float | int:
    """``value`` as the float that carries it exactly, or ``value`` unchanged.

    An integer spells a float value only when a float of the target width
    represents it exactly. A magnitude that overflows the width, or one whose
    low bits no mantissa of the width can hold, is not a literal of the space:
    it decodes to itself so membership fails, never rounding to a nearby float
    or overflowing to infinity.
    """
    try:
        widened = float(value)
        if binary32:
            widened = _struct.unpack("<f", _struct.pack("<f", widened))[0]
    except OverflowError:
        return value
    return widened if widened == value else value


def _decoded[T](decode: Callable[[str], T], literal: str) -> T | str:
    """``literal`` decoded, or the literal itself when it is not well formed."""
    try:
        return decode(literal)
    except ValueError:
        return literal


def _decoded_temporal[T](decode: Callable[[str], T], literal: str) -> T | str:
    """A microsecond-precision temporal literal decoded, unless it carries
    non-zero sub-microsecond precision.

    ``datetime.fromisoformat`` / ``time.fromisoformat`` silently truncate any
    fractional field past the sixth digit, so a literal whose seventh or later
    fractional digit is non-zero — in the fractional second or in a fractional
    timezone offset — would decode to a value that is not the value written: a
    truncated fractional second, or an instant shifted by a sub-microsecond
    offset. Such a literal names no member of a microsecond-precision space and
    decodes to itself so membership fails; a literal whose extra digits are all
    trailing zeros still spells an exact microsecond value and decodes normally.
    """
    if not _within_microsecond_precision(literal):
        return literal
    return _decoded(decode, literal)


def _within_microsecond_precision(literal: str) -> bool:
    """Whether every fractional field in a temporal literal has no non-zero digit
    past the sixth.

    A temporal literal may spell more than one fractional field — a fractional
    second and a fractional timezone offset — and ``.`` also serves as an
    alternate date-time separator, so each ``.``/``,``-initiated digit run is
    inspected rather than only the first. A run of at most six digits, or one
    whose digits beyond the sixth are all zero, spells an exact microsecond
    value; any run with a non-zero digit past the sixth carries sub-microsecond
    precision and rejects the literal. A ``.`` used as the date-time separator
    introduces the two-digit hour, a short run that passes on its own.
    """
    for index, char in enumerate(literal):
        if char in ".,":
            digits = ""
            for following in literal[index + 1 :]:
                if following not in "0123456789":
                    break
                digits += following
            if len(digits) > 6 and any(digit != "0" for digit in digits[6:]):
                return False
    return True


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
