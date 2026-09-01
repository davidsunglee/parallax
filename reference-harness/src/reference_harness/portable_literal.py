"""The independent admitted and canonical Wire grammar of each Neutral Type.

The harness derives expected values from the normative m-wire matrix without
importing the production codec. Public decoding accepts only the matrix's
admitted grammar; canonical decoding additionally requires the codec's one
output spelling.

Delegating is the failure this module exists to prevent (ADR 0016): a host
parser's incidental surface — Python's ``uuid.UUID`` also taking brace-wrapped
and ``urn:uuid:`` spellings, ``datetime.fromisoformat`` also taking week dates,
basic-format runs, and any character at all as the date/time separator,
``decimal.Decimal`` also taking digit separators, a leading ``+``, surrounding
whitespace, and exponents — would become the contract a second language has to
reproduce, and no specification states it.

Authored-Wire decoding is strict: alternative spellings classified as
noncanonical are rejected rather than normalized. Provider-observed values use
a separate canonicalization boundary for the limited carrier adaptations the
compatibility contract permits. Encoding accepts managed members only and emits
the one canonical Wire spelling.

Every digit in this grammar is an ASCII digit. Python's ``\\d`` also matches every
Unicode decimal digit, so a regex written with it would decode a date spelled in
ARABIC-INDIC DIGITs and a decimal whose fraction is one as members of these
spaces — spellings no specification gives them, and ones another language's own
``\\d`` need not even agree about.
"""

from __future__ import annotations

import datetime
import decimal
import math
import re
import struct
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Literal, Never

_DATE = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})$")
_LOOSE_DATE = re.compile(r"^([0-9]{1,4})-([0-9]{1,2})-([0-9]{1,2})$")
_TIME = re.compile(r"^([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{3}|[0-9]{6}))?$")
_TIMESTAMP = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})"
    r"(?:\.([0-9]{3}|[0-9]{6}))?(Z|[+-][0-9]{2}:[0-9]{2})$"
)
_UUID_CANONICAL = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_UUID_HYPHENATED = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
_UUID_BARE = re.compile(r"^[0-9a-fA-F]{32}$")

# A `-` names a value BELOW zero, so a negative spelling carries a magnitude that
# is not zero: `-0` and `-0.0` name zero, which has the one spelling `0` / `0.0`.
_DECIMAL_NUMBER = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$")
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")

# The bit pattern of the largest finite binary32, and the magnitude at which a
# number rounds past it to an infinity: half an ulp above it, `2**128 - 2**103`.
_BINARY32_MAX_BITS = 0x7F7FFFFF
_BINARY32_OVERFLOW = Fraction(2) ** 128 - Fraction(2) ** 103
_DECIMAL_TYPE = re.compile(r"^decimal\(([0-9]+),\s*([0-9]+)\)$")


type PortableLiteralReason = Literal["type-mismatch", "noncanonical", "out-of-space"]


class PortableLiteralError(ValueError):
    """A value is not an admitted or canonical literal of its declared type."""

    def __init__(self, reason: PortableLiteralReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def _fail(reason: PortableLiteralReason, value: object, neutral_type: str) -> Never:
    raise PortableLiteralError(reason, f"{value!r} is {reason} for {neutral_type}")


def _canonical_scalar_equal(left: Any, right: Any) -> bool:
    return _same_json_scalar(left, right)


@dataclass(frozen=True, slots=True)
class _Codec:
    decode: Callable[[Any, str], Any]
    encode: Callable[[Any, str], Any]
    canonical_equal: Callable[[Any, Any], bool] = _canonical_scalar_equal


def decode(value: Any, neutral_type: str) -> Any:
    """Decode one admitted portable literal under ``neutral_type``.

    This model-free interface is the reference implementation of the m-wire
    table. It deliberately imports no production package.
    """
    if value is None:
        raise PortableLiteralError(
            "type-mismatch", "null is enclosing presence, not a typed literal"
        )
    codec = _codec(neutral_type)
    if codec is None:
        return _unknown_neutral_type(neutral_type)
    return codec.decode(value, neutral_type)


def decode_canonical(value: Any, neutral_type: str) -> Any:
    """Decode ``value`` only when it is the canonical output for its member."""
    codec = _codec(neutral_type)
    if codec is None:
        return _unknown_neutral_type(neutral_type)
    managed = codec.decode(value, neutral_type)
    canonical = codec.encode(managed, neutral_type)
    if not codec.canonical_equal(value, canonical):
        raise PortableLiteralError("noncanonical", f"{value!r} is not canonical for {neutral_type}")
    return managed


def encode(value: Any, neutral_type: str) -> Any:
    """Encode an existing managed value as the declared type's canonical literal."""
    if value is None:
        raise PortableLiteralError(
            "type-mismatch", "null is enclosing presence, not a typed literal"
        )
    codec = _codec(neutral_type)
    if codec is None:
        return _managed_type_mismatch(value, neutral_type)
    return codec.encode(value, neutral_type)


def _codec(neutral_type: str) -> _Codec | None:
    if _DECIMAL_TYPE.fullmatch(neutral_type) is not None:
        return _DECIMAL_CODEC
    return _CODECS.get(neutral_type)


def _unknown_neutral_type(neutral_type: str) -> Never:
    raise PortableLiteralError(
        "type-mismatch", f"{neutral_type!r} names no neutral type this table covers"
    )


def _decode_decimal(value: Any, neutral_type: str) -> decimal.Decimal:
    decimal_type = _DECIMAL_TYPE.fullmatch(neutral_type)
    assert decimal_type is not None
    precision, scale = (int(part) for part in decimal_type.groups())
    if not isinstance(value, str):
        _fail("type-mismatch", value, neutral_type)
    if _DECIMAL_NUMBER.fullmatch(value) is None:
        _fail("type-mismatch", value, neutral_type)
    parsed = decimal.Decimal(value)
    if not _decimal_in_space(parsed, precision, scale):
        _fail("out-of-space", value, neutral_type)
    managed = parsed.copy_abs() if parsed.is_zero() else parsed
    if _exact_decimal(managed, scale) != value:
        _fail("noncanonical", value, neutral_type)
    return managed


def _encode_decimal(value: Any, neutral_type: str) -> str:
    decimal_type = _DECIMAL_TYPE.fullmatch(neutral_type)
    assert decimal_type is not None
    precision, scale = (int(part) for part in decimal_type.groups())
    if isinstance(value, decimal.Decimal) and _decimal_in_space(value, precision, scale):
        return _exact_decimal(value.copy_abs() if value.is_zero() else value, scale)
    return _managed_type_mismatch(value, neutral_type)


def _decode_boolean(value: Any, neutral_type: str) -> bool:
    if isinstance(value, bool):
        return value
    _fail("type-mismatch", value, neutral_type)


def _encode_boolean(value: Any, neutral_type: str) -> bool:
    if isinstance(value, bool):
        return value
    return _managed_type_mismatch(value, neutral_type)


def _decode_integer(value: Any, neutral_type: str) -> int:
    bound = 2**31 if neutral_type == "int32" else 2**63
    number = _source_decimal(value)
    if number is None or not number.is_finite() or number != number.to_integral_value():
        _fail("type-mismatch", value, neutral_type)
    managed = int(number)
    if not -bound <= managed < bound:
        _fail("out-of-space", value, neutral_type)
    return managed


def _encode_integer(value: Any, neutral_type: str) -> int:
    if type(value) is int:
        return _decode_integer(value, neutral_type)
    return _managed_type_mismatch(value, neutral_type)


def _decode_float(value: Any, neutral_type: str) -> float:
    if _source_decimal(value) is None:
        _fail("type-mismatch", value, neutral_type)
    decoded = decode_number(value, binary32=neutral_type == "float32")
    if decoded is None:
        _fail("out-of-space", value, neutral_type)
    return decoded


def _encode_float(value: Any, neutral_type: str) -> float:
    if type(value) is float:
        target = decode_number(value, binary32=neutral_type == "float32")
        if target is not None and target == value:
            return _shortest_float(target, binary32=neutral_type == "float32")
    return _managed_type_mismatch(value, neutral_type)


def _canonical_number_equal(value: Any, canonical: Any) -> bool:
    return not _is_negative_zero_number(value) and _spelled_number(value) == _spelled_number(
        canonical
    )


def _decode_string(value: Any, neutral_type: str) -> str:
    if not isinstance(value, str):
        _fail("type-mismatch", value, neutral_type)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        _fail("out-of-space", value, neutral_type)
    return value


def _encode_string(value: Any, neutral_type: str) -> str:
    if isinstance(value, str):
        return _decode_string(value, neutral_type)
    return _managed_type_mismatch(value, neutral_type)


def _decode_bytes(value: Any, neutral_type: str) -> bytes:
    if not isinstance(value, str):
        _fail("type-mismatch", value, neutral_type)
    if len(value) % 2 or any(character not in _HEX_DIGITS for character in value):
        _fail("type-mismatch", value, neutral_type)
    if value != value.lower():
        _fail("noncanonical", value, neutral_type)
    return bytes.fromhex(value)


def _encode_bytes(value: Any, neutral_type: str) -> str:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return _managed_type_mismatch(value, neutral_type)


def _encode_date(value: Any, neutral_type: str) -> str:
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        return value.isoformat()
    return _managed_type_mismatch(value, neutral_type)


def _encode_time(value: Any, neutral_type: str) -> str:
    if isinstance(value, datetime.time) and value.tzinfo is None:
        return value.isoformat()
    return _managed_type_mismatch(value, neutral_type)


def _encode_timestamp(value: Any, neutral_type: str) -> str:
    if isinstance(value, datetime.datetime) and value.tzinfo is not None:
        return value.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    return _managed_type_mismatch(value, neutral_type)


def _decode_uuid(value: Any, neutral_type: str) -> uuid.UUID:
    if not isinstance(value, str):
        _fail("type-mismatch", value, neutral_type)
    if _UUID_CANONICAL.fullmatch(value) is not None:
        return uuid.UUID(value)
    if _UUID_HYPHENATED.fullmatch(value) is not None or _UUID_BARE.fullmatch(value) is not None:
        _fail("noncanonical", value, neutral_type)
    _fail("type-mismatch", value, neutral_type)


def _encode_uuid(value: Any, neutral_type: str) -> str:
    if isinstance(value, uuid.UUID):
        return str(value)
    return _managed_type_mismatch(value, neutral_type)


def _decode_json(value: Any, neutral_type: str) -> Any:
    if value is None:
        _fail("type-mismatch", value, neutral_type)
    if _json_member(value):
        return _copy_json(value)
    _fail("out-of-space" if _json_shape(value) else "type-mismatch", value, neutral_type)


def _encode_json(value: Any, neutral_type: str) -> Any:
    if _json_member(value):
        return _copy_json(value)
    return _managed_type_mismatch(value, neutral_type)


def _managed_type_mismatch(value: Any, neutral_type: str) -> Never:
    raise PortableLiteralError("type-mismatch", f"{value!r} is not a managed {neutral_type} value")


def canonicalize(value: Any, neutral_type: str) -> Any:
    """An admitted authored literal or managed value as canonical Wire."""
    try:
        return encode(value, neutral_type)
    except PortableLiteralError:
        return encode(decode(value, neutral_type), neutral_type)


def values_equal(
    left: Any, right: Any, neutral_type: str, tolerance: decimal.Decimal | None
) -> bool:
    """Compare after two independent declared-type canonical projections."""
    if type(left) is type(right) and left == right:
        return True
    decimal_type = _DECIMAL_TYPE.fullmatch(neutral_type)
    if tolerance is not None and decimal_type is not None:
        try:
            one = left if isinstance(left, decimal.Decimal) else decode(left, neutral_type)
            other = right if isinstance(right, decimal.Decimal) else decode(right, neutral_type)
        except PortableLiteralError:
            return False
        if isinstance(one, decimal.Decimal) and isinstance(other, decimal.Decimal):
            return abs(one - other) <= tolerance
    try:
        one = canonicalize_observed(left, neutral_type)
        other = canonicalize_observed(right, neutral_type)
    except PortableLiteralError:
        return False
    if tolerance is not None and neutral_type in (
        "int32",
        "int64",
        "float32",
        "float64",
    ):
        return abs(decimal.Decimal(str(one)) - decimal.Decimal(str(other))) <= tolerance
    return _same_json(one, other)


def canonicalize_observed(value: Any, neutral_type: str) -> Any:
    """Project a canonical Wire or provider-observed value to canonical Wire.

    Provider timestamp rows commonly expose an ISO offset string rather than a
    managed ``datetime``. This seam is intentionally wider than authored
    :func:`decode`; compatibility inputs still require the canonical Wire form.
    """
    try:
        return canonicalize(value, neutral_type)
    except PortableLiteralError:
        if neutral_type == "timestamp" and isinstance(value, str):
            parsed = decode_timestamp(value)
            if parsed is not None:
                if parsed.tzinfo is not None:
                    return encode(parsed, neutral_type)
        raise


def _source_decimal(value: object) -> decimal.Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, decimal.Decimal)):
        return None
    if isinstance(value, (AuthoredInteger, AuthoredNumber)):
        return decimal.Decimal(value.literal)
    if isinstance(value, decimal.Decimal):
        return value
    if isinstance(value, int):
        return decimal.Decimal(value)
    if not math.isfinite(value):
        return None
    return decimal.Decimal.from_float(value)


def _exact_decimal(value: decimal.Decimal, scale: int) -> str:
    return format(value, f".{scale}f")


def _decimal_in_space(value: decimal.Decimal, precision: int, scale: int) -> bool:
    if not value.is_finite():
        return False
    _sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):
        return False
    coefficient = int("".join(str(digit) for digit in digits))
    if coefficient == 0:
        return True
    while coefficient % 10 == 0:
        coefficient //= 10
        exponent += 1
    return exponent >= -scale and len(str(coefficient)) + exponent + scale <= precision


def _shortest_float(value: float, *, binary32: bool) -> float:
    for precision in range(1, 18):
        candidate = float(f"{value:.{precision}g}")
        if decode_number(candidate, binary32=binary32) == value:
            return candidate
    return value


def _json_member(value: Any) -> bool:
    if value is None or isinstance(value, (bool, str)):
        return True
    if isinstance(value, int) and not isinstance(value, bool):
        return -(2**63) <= value < 2**64
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_member(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(name, str) and _json_member(item) for name, item in value.items())
    return False


def _json_shape(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list):
        return all(_json_shape(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(name, str) and _json_shape(item) for name, item in value.items())
    return False


def _copy_json(value: Any) -> Any:
    if isinstance(value, list):
        return [_copy_json(item) for item in value]
    if isinstance(value, dict):
        return {name: _copy_json(item) for name, item in value.items()}
    if isinstance(value, AuthoredInteger):
        return int(value)
    if isinstance(value, AuthoredNumber):
        return float(value)
    return value


def _same_json(left: Any, right: Any) -> bool:
    if isinstance(left, dict) or isinstance(right, dict):
        return (
            isinstance(left, dict)
            and isinstance(right, dict)
            and left.keys() == right.keys()
            and all(_same_json(left[name], right[name]) for name in left)
        )
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list)
            and isinstance(right, list)
            and len(left) == len(right)
            and all(_same_json(one, other) for one, other in zip(left, right, strict=True))
        )
    return _same_json_scalar(left, right)


def _same_json_scalar(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left is right
    if isinstance(left, (int, float)) or isinstance(right, (int, float)):
        return (
            isinstance(left, (int, float))
            and not isinstance(left, bool)
            and isinstance(right, (int, float))
            and not isinstance(right, bool)
            and decimal.Decimal(str(left)) == decimal.Decimal(str(right))
        )
    return type(left) is type(right) and left == right


def _spelled_number(value: Any) -> decimal.Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, decimal.Decimal)):
        return None
    if isinstance(value, (AuthoredInteger, AuthoredNumber)):
        return decimal.Decimal(value.literal)
    return decimal.Decimal(repr(value) if isinstance(value, float) else value)


def _is_negative_zero_number(value: Any) -> bool:
    spelled = _spelled_number(value)
    return spelled is not None and spelled.is_zero() and spelled.is_signed()


class AuthoredInteger(int):
    """A JSON integer token that retains its authored sign and digits."""

    literal: str

    def __new__(cls, literal: str) -> AuthoredInteger:
        number = super().__new__(cls, literal)
        number.literal = literal
        return number


class AuthoredNumber(float):
    """A document number that remembers the digits it was written with.

    A number names the float of the DECLARED width nearest it
    (`m-document-codec`), and the declared width is unknown where a document is
    parsed. A parser that reads the number into a binary64 and leaves a later
    seam to narrow that carrier rounds twice, and two roundings are not one:
    ``1.0000000596046448`` lies just above the midpoint between binary32 ``1.0``
    and its successor, so rounding it once at binary32 names the successor, while
    binary64-then-binary32 lands exactly on that midpoint and ties to the even
    ``1.0``. Carrying the digits lets :func:`decode_number` — the seam that knows
    the width — round once, from what was written.

    The instance IS the binary64 nearest the literal, so a consumer that needs
    only a number reads it as one and nothing else has to know this type exists.
    """

    literal: str

    def __new__(cls, literal: str) -> AuthoredNumber:
        number = super().__new__(cls, literal)
        number.literal = literal
        return number


def decode_number(value: Any, *, binary32: bool) -> float | None:
    """*value* as the float of the declared width nearest it, else ``None``.

    ``None`` means the number names no member: only a magnitude that would round
    to an infinity does, so this is deliberately not an exactness test —
    ``16777217`` at a `float32` names ``16777216.0``.

    The host carrier decides nothing, because ``20`` and ``20.0`` are one number
    and so are ``16777217`` and ``16777217.0``: an ``int`` and a ``float``
    spelling the same number answer the same value. Rounding happens exactly once,
    from the authored digits when :class:`AuthoredNumber` kept them and otherwise
    from the carrier's own exact value.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, decimal.Decimal)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if not binary32:
        try:
            widened = float(value)
        except OverflowError:
            return None
        if not math.isfinite(widened):
            return None
        return 0.0 if widened == 0.0 else widened
    exact = _exact_number(value)
    if abs(exact) >= _BINARY32_OVERFLOW:
        return None
    narrowed = math.copysign(_nearest_binary32(abs(exact)), value)
    return 0.0 if narrowed == 0.0 else narrowed


def _exact_number(value: int | float | decimal.Decimal) -> Fraction:
    """The number *value* names, exactly: its authored digits, else its carrier."""
    if isinstance(value, (AuthoredInteger, AuthoredNumber)):
        return Fraction(decimal.Decimal(value.literal))
    return Fraction(value)


def _nearest_binary32(magnitude: Fraction) -> float:
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
    best_distance: Fraction | None = None
    for bits in (start - 1, start, start + 1):
        if not 0 <= bits <= _BINARY32_MAX_BITS:
            continue
        distance = abs(Fraction(_binary32_at(bits)) - magnitude)
        if best_distance is None or distance < best_distance:
            best_bits, best_distance = bits, distance
        elif distance == best_distance and bits % 2 == 0:
            best_bits = bits
    return _binary32_at(best_bits)


def _binary32_bits(magnitude: Fraction) -> int:
    """The bit pattern of a binary32 within one ulp of *magnitude*."""
    try:
        approximate = float(magnitude)
    except OverflowError:  # pragma: no cover - the overflow threshold is checked first
        return _BINARY32_MAX_BITS
    try:
        return int(struct.unpack("<I", struct.pack("<f", approximate))[0])
    except OverflowError:
        return _BINARY32_MAX_BITS


def _binary32_at(bits: int) -> float:
    return float(struct.unpack("<f", struct.pack("<I", bits))[0])


def decode_date(literal: str) -> datetime.date | None:
    """*literal* as the date it spells, else ``None``.

    The extended ``YYYY-MM-DD`` calendar form alone. An ordinal date, a week date,
    and the basic (hyphenless) form each name a day, but none is the spelling
    `m-document-codec` fixes, so none is a portable literal.
    """
    match = _DATE.match(literal)
    if match is None:
        return None
    year, month, day = (int(group) for group in match.groups())
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _decode_date_classified(value: object, neutral_type: str) -> datetime.date:
    if not isinstance(value, str):
        _fail("type-mismatch", value, neutral_type)
    strict = _DATE.fullmatch(value)
    if strict is not None:
        decoded = decode_date(value)
        if decoded is None:
            _fail("out-of-space", value, neutral_type)
        return decoded
    loose = _LOOSE_DATE.fullmatch(value)
    if loose is None:
        _fail("type-mismatch", value, neutral_type)
    try:
        datetime.date(*(int(part) for part in loose.groups()))
    except ValueError:
        _fail("out-of-space", value, neutral_type)
    _fail("noncanonical", value, neutral_type)


def decode_time(literal: str) -> datetime.time | None:
    """*literal* as the wall-clock time it spells, else ``None``.

    ``hh:mm:ss`` with no fraction or exactly three or six fractional digits. A
    `time` names a wall clock, so a UTC offset is no part of its spelling.
    """
    match = _TIME.match(literal)
    if match is None:
        return None
    hour, minute, second, fraction = match.groups()
    microsecond = _microseconds(fraction)
    try:
        return datetime.time(int(hour), int(minute), int(second or 0), microsecond)
    except ValueError:
        return None


def _decode_time_classified(value: object, neutral_type: str) -> datetime.time:
    if not isinstance(value, str):
        _fail("type-mismatch", value, neutral_type)
    if _TIME.fullmatch(value) is None:
        _fail("type-mismatch", value, neutral_type)
    decoded = decode_time(value)
    if decoded is None:
        _fail("out-of-space", value, neutral_type)
    return decoded


def decode_timestamp(literal: str) -> datetime.datetime | None:
    """*literal* as the instant it spells, else ``None``.

    ``YYYY-MM-DDThh:mm:ss`` with an optional fractional second, closed by the UTC
    designator ``Z`` or by an ``±hh:mm`` offset — a `timestamp` names an instant,
    so an offset is required. The ``T`` is the separator: a space, or any other
    character, spells no instant.
    """
    match = _TIMESTAMP.fullmatch(literal)
    if match is None:
        return None
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    microsecond = _microseconds(fraction)
    offset = _offset(zone)
    if offset is None:
        return None
    try:
        return datetime.datetime(
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            int(second),
            microsecond,
            tzinfo=offset,
        )
    except ValueError:
        return None


def _decode_timestamp_classified(value: object, neutral_type: str) -> datetime.datetime:
    if not isinstance(value, str):
        _fail("type-mismatch", value, neutral_type)
    if _TIMESTAMP.fullmatch(value) is None:
        _fail("type-mismatch", value, neutral_type)
    decoded = decode_timestamp(value)
    if decoded is None:
        _fail("out-of-space", value, neutral_type)
    if not value.endswith("Z"):
        _fail("noncanonical", value, neutral_type)
    return decoded.astimezone(datetime.UTC)


def _microseconds(fraction: str | None) -> int:
    """Convert the strict grammar's absent, three-digit, or six-digit fraction."""
    if fraction is None:
        return 0
    return int(fraction.ljust(6, "0"))


def _offset(zone: str) -> datetime.timezone | None:
    """A ``Z`` / ``±hh:mm`` UTC designator as its offset, or ``None`` when out of range."""
    if zone == "Z":
        return datetime.UTC
    sign = -1 if zone[0] == "-" else 1
    hours, minutes = (int(part) for part in zone[1:].split(":"))
    if hours > 23 or minutes > 59:
        return None
    return datetime.timezone(sign * datetime.timedelta(hours=hours, minutes=minutes))


_DECIMAL_CODEC = _Codec(_decode_decimal, _encode_decimal)
_NUMERIC_CODEC = _Codec(_decode_integer, _encode_integer, _canonical_number_equal)
_FLOAT_CODEC = _Codec(_decode_float, _encode_float, _canonical_number_equal)
_CODECS: dict[str, _Codec] = {
    "boolean": _Codec(_decode_boolean, _encode_boolean),
    "int32": _NUMERIC_CODEC,
    "int64": _NUMERIC_CODEC,
    "float32": _FLOAT_CODEC,
    "float64": _FLOAT_CODEC,
    "string": _Codec(_decode_string, _encode_string),
    "bytes": _Codec(_decode_bytes, _encode_bytes),
    "date": _Codec(_decode_date_classified, _encode_date),
    "time": _Codec(_decode_time_classified, _encode_time),
    "timestamp": _Codec(_decode_timestamp_classified, _encode_timestamp),
    "uuid": _Codec(_decode_uuid, _encode_uuid),
    "json": _Codec(_decode_json, _encode_json),
}
