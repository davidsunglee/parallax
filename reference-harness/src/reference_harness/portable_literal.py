"""The portable literal grammar of each Neutral Type, and its decode.

`m-document-codec` gives every Neutral Type exactly one document spelling, and
`m-case-format` widens that to the spellings a CASE may author: hexadecimal in
either digit case, a `uuid`'s hyphens optional, a `time` with its seconds
omitted, and a `timestamp` at any UTC offset. Those two lists are the whole
grammar, so it is written out here rather than delegated to a host parser.

Delegating is the failure this module exists to prevent (ADR 0016): a host
parser's incidental surface — Python's ``uuid.UUID`` also taking brace-wrapped
and ``urn:uuid:`` spellings, ``datetime.fromisoformat`` also taking week dates,
basic-format runs, and any character at all as the date/time separator,
``decimal.Decimal`` also taking digit separators, a leading ``+``, surrounding
whitespace, and exponents — would become the contract a second language has to
reproduce, and no specification states it.

Decoding is MANY-TO-ONE where the document encoding is one-to-one: a value is
stored in exactly one canonical spelling, while every spelling this grammar
admits names the same value and stores as that canonical one.

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
from fractions import Fraction
from typing import Any

_DATE = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})$")
_TIME = re.compile(r"^([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:\.([0-9]+))?)?$")
_TIMESTAMP = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})"
    r"(?:\.([0-9]+))?(Z|[+-][0-9]{2}:[0-9]{2})$"
)
_UUID_HYPHENATED = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
_UUID_BARE = re.compile(r"^[0-9a-fA-F]{32}$")

# A `-` names a value BELOW zero, so a negative spelling carries a magnitude that
# is not zero: `-0` and `-0.0` name zero, which has the one spelling `0` / `0.0`.
_DECIMAL = re.compile(
    r"^(?:(?:0|[1-9][0-9]*)(?:\.[0-9]+)?"
    r"|-(?:0\.[0-9]*[1-9][0-9]*|[1-9][0-9]*(?:\.[0-9]+)?))$"
)
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")

# A value beyond this many fractional digits is only in space when the extra
# digits are zeros: the temporal spaces are microsecond-precision (`m-core`).
_MICROSECOND_DIGITS = 6

# The bit pattern of the largest finite binary32, and the magnitude at which a
# number rounds past it to an infinity: half an ulp above it, `2**128 - 2**103`.
_BINARY32_MAX_BITS = 0x7F7FFFFF
_BINARY32_OVERFLOW = Fraction(2) ** 128 - Fraction(2) ** 103
_DECIMAL_TYPE = re.compile(r"^decimal\(([0-9]+),\s*([0-9]+)\)$")


class PortableLiteralError(ValueError):
    """A value is not an admitted or canonical literal of its declared type."""


def decode(value: Any, neutral_type: str) -> Any:
    """Decode one admitted portable literal under ``neutral_type``.

    This model-free interface is the reference implementation of the m-wire
    table. It deliberately imports no production package.
    """
    if value is None:
        raise PortableLiteralError("null is enclosing presence, not a typed literal")
    decimal_type = _DECIMAL_TYPE.fullmatch(neutral_type)
    if decimal_type is not None:
        precision, scale = (int(part) for part in decimal_type.groups())
        if isinstance(value, str):
            parsed = decode_decimal(value)
        elif isinstance(value, AuthoredNumber):
            parsed = decimal.Decimal(value.literal)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            parsed = decimal.Decimal(repr(value) if isinstance(value, float) else value)
        else:
            parsed = None
        if parsed is not None and _decimal_in_space(parsed, precision, scale):
            return parsed
    elif neutral_type == "boolean" and isinstance(value, bool):
        return value
    elif neutral_type in ("int32", "int64"):
        bound = 2**31 if neutral_type == "int32" else 2**63
        if isinstance(value, int) and not isinstance(value, bool) and -bound <= value < bound:
            return value
    elif neutral_type in ("float32", "float64"):
        decoded = decode_number(value, binary32=neutral_type == "float32")
        if decoded is not None:
            return decoded
    elif neutral_type == "string" and isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            pass
        else:
            return value
    elif neutral_type == "bytes":
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value)
        if isinstance(value, str):
            decoded = decode_octets(value)
            if decoded is not None:
                return decoded
    elif neutral_type == "date" and isinstance(value, str):
        decoded = decode_date(value)
        if decoded is not None:
            return decoded
    elif neutral_type == "time" and isinstance(value, str):
        decoded = decode_time(value)
        if decoded is not None:
            return decoded
    elif neutral_type == "timestamp" and isinstance(value, str):
        decoded = decode_timestamp(value)
        if decoded is not None:
            return decoded.astimezone(datetime.UTC)
    elif neutral_type == "uuid" and isinstance(value, str):
        decoded = decode_uuid(value)
        if decoded is not None:
            return decoded
    elif neutral_type == "json" and _json_member(value):
        return _copy_json(value)
    raise PortableLiteralError(f"{value!r} names no {neutral_type} value")


def decode_canonical(value: Any, neutral_type: str) -> Any:
    """Decode ``value`` only when it is the canonical output for its member."""
    managed = decode(value, neutral_type)
    canonical = encode(managed, neutral_type)
    equal = (
        _spelled_number(value) == _spelled_number(canonical)
        if neutral_type in ("int32", "int64", "float32", "float64")
        else _same_json_scalar(value, canonical)
    )
    if not equal:
        raise PortableLiteralError(f"{value!r} is not canonical for {neutral_type}")
    return managed


def encode(value: Any, neutral_type: str) -> Any:
    """Encode an existing managed value as the declared type's canonical literal."""
    if value is None:
        raise PortableLiteralError("null is enclosing presence, not a typed literal")
    decimal_type = _DECIMAL_TYPE.fullmatch(neutral_type)
    if decimal_type is not None and isinstance(value, decimal.Decimal):
        precision, scale = (int(part) for part in decimal_type.groups())
        if _decimal_in_space(value, precision, scale):
            return f"{value:.{scale}f}"
    elif neutral_type == "boolean" and isinstance(value, bool):
        return value
    elif neutral_type in ("int32", "int64"):
        return decode(value, neutral_type)
    elif neutral_type in ("float32", "float64"):
        target = decode_number(value, binary32=neutral_type == "float32")
        if target is not None:
            return _shortest_float(target, binary32=neutral_type == "float32")
    elif neutral_type == "string" and isinstance(value, str):
        return decode(value, neutral_type)
    elif neutral_type == "bytes" and isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    elif (
        neutral_type == "date"
        and isinstance(value, datetime.date)
        and not isinstance(value, datetime.datetime)
    ):
        return value.isoformat()
    elif neutral_type == "time" and isinstance(value, datetime.time) and value.tzinfo is None:
        return value.isoformat()
    elif (
        neutral_type == "timestamp"
        and isinstance(value, datetime.datetime)
        and value.tzinfo is not None
    ):
        return value.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    elif neutral_type == "uuid" and isinstance(value, uuid.UUID):
        return str(value)
    elif neutral_type == "json" and _json_member(value):
        return _copy_json(value)
    raise PortableLiteralError(f"{value!r} is not a managed {neutral_type} value")


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
    try:
        one = canonicalize(left, neutral_type)
        other = canonicalize(right, neutral_type)
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


def _copy_json(value: Any) -> Any:
    if isinstance(value, list):
        return [_copy_json(item) for item in value]
    if isinstance(value, dict):
        return {name: _copy_json(item) for name, item in value.items()}
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
    if isinstance(value, AuthoredNumber):
        return decimal.Decimal(value.literal)
    return decimal.Decimal(repr(value) if isinstance(value, float) else value)


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
        return widened if math.isfinite(widened) else None
    exact = _exact_number(value)
    if abs(exact) >= _BINARY32_OVERFLOW:
        return None
    return math.copysign(_nearest_binary32(abs(exact)), value)


def _exact_number(value: int | float | decimal.Decimal) -> Fraction:
    """The number *value* names, exactly: its authored digits, else its carrier."""
    if isinstance(value, AuthoredNumber):
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


def decode_time(literal: str) -> datetime.time | None:
    """*literal* as the wall-clock time it spells, else ``None``.

    ``hh:mm:ss`` with an optional fractional second, and — the one variation
    `m-case-format` admits — with the seconds omitted. A `time` names a wall
    clock, so a UTC offset is no part of its spelling.
    """
    match = _TIME.match(literal)
    if match is None:
        return None
    hour, minute, second, fraction = match.groups()
    microsecond = _microseconds(fraction)
    if microsecond is None:
        return None
    try:
        return datetime.time(int(hour), int(minute), int(second or 0), microsecond)
    except ValueError:
        return None


def decode_timestamp(literal: str) -> datetime.datetime | None:
    """*literal* as the instant it spells, else ``None``.

    ``YYYY-MM-DDThh:mm:ss`` with an optional fractional second, closed by the UTC
    designator ``Z`` or by an ``±hh:mm`` offset — a `timestamp` names an instant,
    so an offset is required. The ``T`` is the separator: a space, or any other
    character, spells no instant.
    """
    match = _TIMESTAMP.match(literal)
    if match is None:
        return None
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    microsecond = _microseconds(fraction)
    if microsecond is None:
        return None
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


def decode_uuid(literal: str) -> uuid.UUID | None:
    """*literal* as the 128-bit value it spells, else ``None``.

    Thirty-two hexadecimal digits in either case, grouped 8-4-4-4-12 or written
    with no hyphens at all — the two spellings `m-case-format` admits. Case
    carries no information (`m-core`), so both decode to the value the canonical
    lowercase hyphenated form stores.
    """
    if _UUID_HYPHENATED.match(literal) is None and _UUID_BARE.match(literal) is None:
        return None
    return uuid.UUID(literal.replace("-", ""))


def decode_decimal(literal: str) -> decimal.Decimal | None:
    """*literal* as the exact decimal it spells, else ``None``.

    The exact decimal spelling `m-document-codec` fixes: a ``-`` only for a value
    below zero — so ``-0`` and ``-0.0`` spell nothing, zero being neither below
    nor signed — integer digits with no leading zero, and an optional fraction.
    No exponent — a `decimal` carries a declared scale, which an exponent does
    not spell — and none of the leading ``+``, digit separator, or surrounding
    space a host parser might otherwise take.
    """
    if _DECIMAL.match(literal) is None:
        return None
    return decimal.Decimal(literal)


def decode_octets(literal: str) -> bytes | None:
    """*literal* as the octets it spells, else ``None``.

    Two hexadecimal digits per octet in either digit case, no prefix and no
    separator, so an odd digit count and an embedded space each name no octet
    sequence.
    """
    if len(literal) % 2 != 0 or any(character not in _HEX_DIGITS for character in literal):
        return None
    return bytes.fromhex(literal)


def decoded_as(value: Any, neutral_type: str | None) -> Any:
    """*value* decoded to the host carrier of *neutral_type*, or ``None``.

    ``None`` means the value spells no member, so a caller deciding membership
    reads it as a refusal. Only the string-carried spaces decode; every other
    type is carried natively in the document.
    """
    if not isinstance(value, str):
        return None
    if neutral_type == "date":
        return decode_date(value)
    if neutral_type == "time":
        return decode_time(value)
    if neutral_type == "timestamp":
        return decode_timestamp(value)
    if neutral_type == "uuid":
        return decode_uuid(value)
    if neutral_type == "bytes":
        return decode_octets(value)
    return None


def _microseconds(fraction: str | None) -> int | None:
    """A fractional-second field as whole microseconds, or ``None``.

    A digit past the sixth may only be zero: the temporal spaces hold microseconds,
    so a literal carrying finer precision names a value they have no member for and
    truncating it would answer a different instant than the one written.
    """
    if fraction is None:
        return 0
    if any(digit != "0" for digit in fraction[_MICROSECOND_DIGITS:]):
        return None
    return int(fraction[:_MICROSECOND_DIGITS].ljust(_MICROSECOND_DIGITS, "0"))


def _offset(zone: str) -> datetime.timezone | None:
    """A ``Z`` / ``±hh:mm`` UTC designator as its offset, or ``None`` when out of range."""
    if zone == "Z":
        return datetime.UTC
    sign = -1 if zone[0] == "-" else 1
    hours, minutes = (int(part) for part in zone[1:].split(":"))
    if hours > 23 or minutes > 59:
        return None
    return datetime.timezone(sign * datetime.timedelta(hours=hours, minutes=minutes))
