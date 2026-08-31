"""The structured Neutral Type algebra and managed value spaces (m-core)."""

from __future__ import annotations

import datetime as _dt
import decimal as _decimal
import math as _math
import struct as _struct
import uuid as _uuid
from dataclasses import dataclass
from fractions import Fraction as _Fraction
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
    "ManagedValue",
    "NeutralType",
    "String",
    "Time",
    "Timestamp",
    "Uuid",
    "coerce_neutral_input",
    "matches_neutral_type",
    "nearest_float_at_width",
    "utc_instant",
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

type ManagedValue = (
    bool
    | int
    | float
    | _decimal.Decimal
    | str
    | bytes
    | _dt.date
    | _dt.time
    | _dt.datetime
    | _uuid.UUID
    | list["ManagedValue | None"]
    | dict[str, "ManagedValue | None"]
)
"""A host carrier belonging to a declared Neutral Type's managed value space."""

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

# The bit pattern of the largest finite binary32, and the magnitude at which a
# number rounds past it to an infinity: half an ulp above it, `2**128 - 2**103`.
_BINARY32_MAX_BITS: Final[int] = 0x7F7FFFFF
_BINARY32_OVERFLOW: Final[_Fraction] = _Fraction(2) ** 128 - _Fraction(2) ** 103


def utc_instant(value: _dt.datetime) -> _dt.datetime | None:
    """``value`` as the UTC ``datetime`` naming the same instant, or ``None``
    when it names no instant the ``timestamp`` space holds.

    Two constructible ``datetime``s name none, and neither is recoverable here.
    One states no usable UTC offset — a naive value, and equally a ``tzinfo``
    answering ``None`` or an offset outside the day ``datetime`` arithmetic
    admits — so it is not on a timeline at all. The other states one that
    carries it past the ends of the range: ``datetime.min`` east of UTC and
    ``datetime.max`` west of it name instants no UTC ``datetime`` holds, and
    that `m-wire`'s four-digit-year UTC spelling therefore cannot write.

    Answering rather than raising is what lets membership stay a predicate, and
    the ``timestamp`` value space is exactly the instants answered for here:
    admitting one this function has no answer for would leave a member with no
    Wire Value, which `m-wire` gives every value of a declared type.
    """
    try:
        if value.utcoffset() is None:
            return None
        return value.astimezone(_dt.UTC)
    except (OverflowError, TypeError, ValueError):
        return None


def matches_neutral_type(value: object, declared: NeutralType) -> bool:
    """Whether ``value`` is a member of ``declared``'s logical value space.

    Exact membership, not a category guess: an integer outside its declared
    width, a non-finite float, a decimal the declared precision and scale
    cannot represent exactly, text with no UTF-8 encoding, an instant no UTC
    ``datetime`` holds, and a bare ``None`` are all non-members. Null is a
    member of no space, so a nullable position admits it through its own
    contract rather than through this check.

    The domain is managed values, one Python carrier per space —
    ``bool``/``int``/``float``/``decimal.Decimal``/``str``/``bytes``/
    ``datetime.date``/``datetime.time``/``datetime.datetime``/``uuid.UUID``,
    and the JSON data model for :class:`Json`. A serialized spelling is never a
    member of the space it encodes.

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
            return (
                isinstance(value, float)
                and _math.isfinite(value)
                and nearest_float_at_width(value, declared) == value
            )
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
            return isinstance(value, _dt.datetime) and utc_instant(value) is not None
        case Uuid():
            return isinstance(value, _uuid.UUID)
        case Json():
            return value is not None and _is_json_value(value)


def coerce_neutral_input(value: object, declared: NeutralType) -> object:
    """``value`` widened by the exact/lossless adjacent forms the developer
    input policy admits for ``declared`` (`python.md` "Neutral scalar type
    mapping", the input-policy column), and otherwise returned unchanged.

    This is the boundary the DEVELOPER-facing write validators call — a
    runtime argument already carries a native Python value, never a wire
    literal, so only the input policy's own narrow, exact/lossless typed
    widenings apply: an :class:`int` for a :class:`Decimal`, a lossless
    :class:`int` for a float, and a canonical UUID string. A host float is
    projected immediately to the declared width, negative zero normalizes to
    positive zero, and an aware Timestamp normalizes to UTC.

    A caller chose an integer carrier, so an integer no float of the width
    carries exactly stays an integer and fails membership. Fractional host
    floats may round because that is the documented developer-input policy.
    """
    match declared:
        case Decimal() if _is_integer(value):
            return _decimal.Decimal(value)
        case Float32() | Float64() if isinstance(value, float):
            projected = nearest_float_at_width(value, declared)
            return value if projected is None else projected
        case Float32() | Float64() if _is_integer(value):
            projected = nearest_float_at_width(value, declared)
            return projected if projected is not None and projected == value else value
        case Timestamp() if isinstance(value, _dt.datetime):
            return utc_instant(value) or value
        case Uuid() if isinstance(value, str):
            return _canonical_uuid_input(value)
        case _:
            return value


def _canonical_uuid_input(value: str) -> object:
    """``value`` as a :class:`~uuid.UUID`, only when it is ALREADY the
    canonical lowercase-hyphenated spelling — the narrower str the input
    policy admits. A non-canonical string is returned unchanged, so
    :func:`matches_neutral_type` rejects it.
    """
    try:
        decoded = _uuid.UUID(value)
    except (AttributeError, ValueError):
        return value
    return decoded if str(decoded) == value else value


def nearest_float_at_width(
    value: int | float | _decimal.Decimal,
    declared: Float32 | Float64,
) -> float | None:
    """Project an exact number to the nearest value of ``declared``.

    Rounding is IEEE round-to-nearest-even. Overflow returns ``None``;
    underflow and either signed zero return positive zero. Magnitudes that are
    plainly outside the target neighborhood are classified before constructing
    a ratio, so represented exponent size cannot drive allocation.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        if not _math.isfinite(value):
            return None
        exact = _decimal.Decimal.from_float(value)
    elif isinstance(value, int):
        magnitude_bits = abs(value).bit_length()
        if isinstance(declared, Float32) and magnitude_bits > 129:
            return None
        if isinstance(declared, Float64) and magnitude_bits > 1025:
            return None
        exact = _decimal.Decimal(value)
    else:
        if not value.is_finite():
            return None
        exact = value

    if exact.is_zero():
        return 0.0
    negative = exact.is_signed()
    magnitude = exact.copy_abs()

    if isinstance(declared, Float64):
        adjusted = magnitude.adjusted()
        if adjusted > 308:
            return None
        if adjusted < -324:
            return 0.0
        projected = float(magnitude)
        if not _math.isfinite(projected):
            return None
        return -projected if negative else projected

    adjusted = magnitude.adjusted()
    if adjusted > 38:
        return None
    if adjusted < -46:
        return 0.0
    ratio = _Fraction(magnitude)
    if ratio >= _BINARY32_OVERFLOW:
        return None
    projected = _nearest_binary32(ratio)
    if projected == 0.0:
        return 0.0
    return -projected if negative else projected


def _nearest_binary32(magnitude: _Fraction) -> float:
    """A non-negative magnitude below the overflow threshold as the binary32
    nearest it, ties to the even mantissa.

    The search starts from the binary64 the magnitude rounds to, narrowed — which
    is the answer or one of its two neighbours, since each rounding moves by less
    than half an ulp of the wider format — and then compares the three candidates
    exactly, so the double rounding that produced the start point cannot survive
    into the result.
    """
    start = _binary32_bits(magnitude)
    best_bits = 0
    best_distance: _Fraction | None = None
    for bits in (start - 1, start, start + 1):
        if not 0 <= bits <= _BINARY32_MAX_BITS:
            continue
        distance = abs(_Fraction(_binary32_at(bits)) - magnitude)
        if best_distance is None or distance < best_distance:
            best_bits, best_distance = bits, distance
        elif distance == best_distance and bits % 2 == 0:
            best_bits = bits
    return _binary32_at(best_bits)


def _binary32_bits(magnitude: _Fraction) -> int:
    """The bit pattern of a binary32 within one ulp of ``magnitude``."""
    try:
        approximate = float(magnitude)
    except OverflowError:  # pragma: no cover - the overflow threshold is checked first
        return _BINARY32_MAX_BITS
    try:
        return int(cast("int", _struct.unpack("<I", _struct.pack("<f", approximate))[0]))
    except OverflowError:
        return _BINARY32_MAX_BITS


def _binary32_at(bits: int) -> float:
    return float(cast("float", _struct.unpack("<f", _struct.pack("<I", bits))[0]))


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
