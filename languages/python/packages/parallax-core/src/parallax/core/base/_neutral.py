"""The structured Neutral Type algebra and its value spaces (m-core).

Every typed model fact draws its type from this closed algebra: Attribute and
Value Object Attribute metadata, predicate literals and assignments, and
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
import re as _re
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
    "AuthoredNumber",
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

_HEX_DIGITS: Final[frozenset[str]] = frozenset("0123456789abcdefABCDEF")

# The portable literal grammar of each string-carried space (`m-document-codec`
# leaf encodings, widened by the case format's own enumerated variations: either
# digit case, a UUID's optional hyphens, an omitted seconds field, any UTC
# offset). Written out because a host parser's incidental surface would otherwise
# become the cross-language contract (ADR 0016).
# Every digit below is an ASCII digit: Python's ``\d`` also matches every Unicode
# decimal digit, so a grammar written with it would decode a date spelled in
# ARABIC-INDIC DIGITs and a decimal whose fraction is one as members of these
# spaces — spellings no specification gives them, and ones another language's own
# ``\d`` need not even agree about.
_DATE_LITERAL: Final = _re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})$")
_TIME_LITERAL: Final = _re.compile(r"^([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:\.([0-9]+))?)?$")
_TIMESTAMP_LITERAL: Final = _re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})"
    r"(?:\.([0-9]+))?(Z|[+-][0-9]{2}:[0-9]{2})$"
)
_UUID_HYPHENATED: Final = _re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
_UUID_BARE: Final = _re.compile(r"^[0-9a-fA-F]{32}$")

# A ``-`` names a value BELOW zero, so a negative spelling carries a magnitude
# that is not zero: ``-0`` and ``-0.0`` name zero, whose one spelling is unsigned.
_DECIMAL_LITERAL: Final = _re.compile(
    r"^(?:(?:0|[1-9][0-9]*)(?:\.[0-9]+)?"
    r"|-(?:0\.[0-9]*[1-9][0-9]*|[1-9][0-9]*(?:\.[0-9]+)?))$"
)

# The temporal spaces hold microseconds (`m-core`).
_MICROSECOND_DIGITS: Final[int] = 6

# The bit pattern of the largest finite binary32, and the magnitude at which a
# number rounds past it to an infinity: half an ulp above it, `2**128 - 2**103`.
_BINARY32_MAX_BITS: Final[int] = 0x7F7FFFFF
_BINARY32_OVERFLOW: Final[_Fraction] = _Fraction(2) ** 128 - _Fraction(2) ** 103


class AuthoredNumber(float):
    """A wire number that remembers the digits it was written with.

    A number names the float of the DECLARED width nearest it
    (`m-document-codec`), and the declared width is unknown where a document is
    parsed. A parser that reads the number into a binary64 and leaves
    :func:`decode_neutral_literal` to narrow that carrier rounds twice, and two
    roundings are not one: ``1.0000000596046448`` lies just above the midpoint
    between binary32 ``1.0`` and its successor, so rounding it once at binary32
    names the successor, while binary64-then-binary32 lands exactly on that
    midpoint and ties to the even ``1.0``. Carrying the digits lets the seam that
    knows the width round once, from what was written.

    The instance IS the binary64 nearest the literal, so a consumer that needs
    only a number reads it as one and nothing else has to know this type exists.
    A seam that parses wire numbers constructs these; a runtime caller handing
    over a native ``float`` never does, and needs not — a caller chose that
    carrier, so the carrier is the number it meant.
    """

    literal: str

    def __new__(cls, literal: str) -> AuthoredNumber:
        number = super().__new__(cls, literal)
        number.literal = literal
        return number


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
            return isinstance(value, _dt.datetime) and utc_instant(value) is not None
        case Uuid():
            return isinstance(value, _uuid.UUID)
        case Json():
            return value is not None and _is_json_value(value)


def decode_neutral_literal(value: object, declared: NeutralType) -> object:
    """``value`` as a carrier of ``declared``'s value space, when it spells one.

    The inverse of the portable literal encoding, and MANY-TO-ONE where the
    encoding is one-to-one: a value is stored in exactly one canonical spelling,
    while every spelling that names it decodes here. A JSON number spells a
    :class:`Decimal`, and — unless its magnitude overflows the target width — a
    :class:`Float32` or :class:`Float64`; an ISO-8601 string spells a
    :class:`Date`, :class:`Time`, or :class:`Timestamp` at whatever UTC offset
    and with whatever optional fields the portable grammar admits; a UUID string
    spells a :class:`Uuid` in either digit case, hyphenated or bare; and a
    hexadecimal string spells :class:`Bytes` in either digit case, two digits per
    octet with no separator.

    That grammar is stated here, never delegated to a host parser: the spellings
    ``decimal.Decimal``, ``datetime.fromisoformat``, and ``uuid.UUID``
    additionally take are their own surface, and adopting them would make a
    second language reproduce Python instead of the neutral contract (ADR 0016).
    A :class:`Decimal` additionally spells as an exact digit STRING, which is the
    one literal a JSON number cannot carry — no JSON number declares a scale, so
    that is the form a structured document stores
    (``parallax.core.document_codec``) and this is the inverse it decodes through.
    Every other space is already carried natively, so its literal decodes to
    itself.

    A number literal is read at the **declared width**, and names the float of
    that width NEAREST it: a :class:`Float32` literal names a binary32 value,
    because a binary32's portable literal is the shortest decimal that decodes
    back to it *at that width* (``parallax.core.document_codec``), so reading
    ``1048576.2`` as a binary64 would answer a number no binary32 holds and the
    encode/decode inverse would fail for exactly the values the shortest-number
    rule pins down. The host carrier the literal arrived in decides nothing —
    ``20`` and ``20.0`` are one JSON number, and so are ``16777217`` and
    ``16777217.0`` — so an ``int`` and a ``float`` spelling the same number
    decode alike. Only a magnitude the width cannot hold names no value.

    Nearest is not exact, deliberately: a number no float of the width
    represents exactly is a literal of the space and decodes to a DIFFERENT
    number than the one written — ``16777217`` at a :class:`Float32` decodes to
    ``16777216.0``. Refusing it cannot be spelled "the literal must be exact",
    because a canonical spelling is routinely inexact (``1e30`` is the one the
    codec gives the binary32 ``1.0000000150474662e30``); the honest refusing
    rule is "exact or already canonical", which narrows :class:`Float32`
    membership itself rather than this inverse. The DEVELOPER input policy is
    the narrower one — see :func:`coerce_neutral_input`.

    Total and nonthrowing: a value that is not a literal of ``declared`` — a
    spelling outside the grammar, a truth value where a number belongs, a
    magnitude no float of the width can hold, a hexadecimal string
    carrying a separator or an odd digit count, a :class:`Time` or
    :class:`Timestamp` literal carrying non-zero sub-microsecond precision, or an
    unrelated object — is returned unchanged, so :func:`matches_neutral_type` alone decides
    membership and this function never truncates, overflows, or classifies a
    defect on its own.
    """
    match declared:
        case Float64() if _is_number(value):
            return _number_at_width(value, binary32=False)
        case Float32() if _is_number(value):
            return _number_at_width(value, binary32=True)
        case Decimal() if _is_integer(value):
            return _decimal.Decimal(value)
        case Decimal() if isinstance(value, float):
            # Through the shortest round-tripping text, so the decoded value has
            # the digits the literal was written with rather than the binary
            # expansion of the float that carried it.
            return _decimal.Decimal(repr(value))
        case Decimal() if isinstance(value, str):
            return _decoded_decimal(value)
        case Bytes() if isinstance(value, str):
            return _decoded_octets(value)
        case Date() if isinstance(value, str):
            return _decoded_date(value)
        case Time() if isinstance(value, str):
            return _decoded_time(value)
        case Timestamp() if isinstance(value, str):
            return _decoded_timestamp(value)
        case Uuid() if isinstance(value, str):
            return _decoded_uuid(value)
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
    :class:`Float32` / :class:`Float64` (lossless only, through
    :func:`_integer_as_float`'s own exactness test), and a canonical UUID
    string for :class:`Uuid`. Every other case — INCLUDING a :class:`float`
    for a :class:`Decimal`, which the input policy explicitly rejects — is
    returned unchanged. There is no ISO date/time/timestamp string decode and
    no hex-string :class:`Bytes` decode here: those are wire spellings the
    case-format / descriptor serde seam (:func:`decode_neutral_literal`)
    decodes once at ingestion, never a form the developer input policy itself
    admits at this boundary.

    The :class:`int`-for-float widening is where the two boundaries part, and
    the difference is the contract. :func:`decode_neutral_literal` reads a JSON
    NUMBER, where ``16777217`` and ``16777217.0`` are one number and the
    declared width decides the value, so it narrows to the nearest float. Here
    a caller chose the Python type, so an :class:`int` no float of the width
    carries exactly stays an :class:`int` and fails membership — the runtime
    rounds nothing a caller did not ask it to (`python.md`: "integral inputs
    must narrow exactly, while fractional inputs may round").

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
            return _canonical_uuid_input(value)
        case _:
            return value


def _canonical_uuid_input(value: str) -> object:
    """``value`` as a :class:`~uuid.UUID`, only when it is ALREADY the
    canonical lowercase-hyphenated spelling — the narrower str the input
    policy admits, as opposed to :func:`decode_neutral_literal`'s serde parse
    (the hyphenless and uppercase forms decode to the same
    :class:`~uuid.UUID` but are not this spelling). A non-canonical string is
    returned unchanged, so :func:`matches_neutral_type` rejects it.
    """
    decoded = _decoded_uuid(value)
    return decoded if isinstance(decoded, _uuid.UUID) and str(decoded) == value else value


def _number_at_width(value: int | float, *, binary32: bool) -> float | int:
    """``value`` as the float of the declared width nearest it, or ``value``
    unchanged.

    A magnitude the width cannot hold is left as it came so
    :func:`matches_neutral_type` refuses it, rather than overflowing to an
    infinity here.

    Rounding happens exactly ONCE, from the authored digits when
    :class:`AuthoredNumber` kept them and otherwise from the carrier's own exact
    value. Reading a number into a binary64 and narrowing that carrier rounds
    twice, and two roundings are not one — see :class:`AuthoredNumber`.
    """
    if not binary32:
        try:
            return float(value)
        except OverflowError:
            return value
    exact = _exact_number(value)
    if abs(exact) >= _BINARY32_OVERFLOW:
        return value
    return _math.copysign(_nearest_binary32(abs(exact)), value)


def _exact_number(value: int | float) -> _Fraction:
    """The number ``value`` names, exactly: its authored digits, else its carrier."""
    if isinstance(value, AuthoredNumber):
        return _Fraction(_decimal.Decimal(value.literal))
    return _Fraction(value)


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


def _integer_as_float(value: int, *, binary32: bool) -> float | int:
    """``value`` as the float that carries it exactly, or ``value`` unchanged.

    The DEVELOPER input policy's widening (`python.md` "Neutral scalar type
    mapping"), deliberately narrower than :func:`decode_neutral_literal`'s
    number rule: a caller hands over a value in a Python type of its own
    choosing, not a JSON number some parser typed for it, so an :class:`int`
    widens only where the width carries it exactly and is otherwise left to fail
    membership. A magnitude that overflows the width, or one whose low bits no
    mantissa of the width can hold, is returned unchanged rather than rounded to
    a nearby float or overflowed to infinity.
    """
    try:
        widened = float(value)
        if binary32:
            widened = _struct.unpack("<f", _struct.pack("<f", widened))[0]
    except OverflowError:
        return value
    return widened if widened == value else value


def _decoded_octets(literal: str) -> bytes | str:
    """A hexadecimal octet literal decoded, or the literal itself when it is not one.

    The digit set is checked before ``bytes.fromhex``, which additionally skips
    ASCII whitespace: a separator is no part of the spelling — the portable literal
    is two hexadecimal digits per octet with no prefix and no separator — so
    ``"0a 1b"`` names no octet sequence and decodes to itself for
    :func:`matches_neutral_type` to refuse. Digit CASE carries no information, so
    ``"0A1B"`` and ``"0a1b"`` decode to the same octets and encode back to the
    lowercase spelling.
    """
    if len(literal) % 2 != 0 or any(character not in _HEX_DIGITS for character in literal):
        return literal
    return bytes.fromhex(literal)


def _decoded_decimal(literal: str) -> _decimal.Decimal | str:
    """An exact decimal string decoded, or the literal itself when it is not one.

    The grammar is written out rather than delegated to :class:`decimal.Decimal`,
    which additionally takes digit separators (``1_0``), a leading ``+``,
    surrounding whitespace, an exponent, and ``nan`` / ``infinity``. None of those
    is a portable literal, and delegating would make Python's parser the contract
    a second language has to reproduce.
    """
    if _DECIMAL_LITERAL.match(literal) is None:
        return literal
    return _decimal.Decimal(literal)


def _decoded_date(literal: str) -> _dt.date | str:
    """An ISO-8601 ``YYYY-MM-DD`` literal decoded, or the literal itself.

    The extended calendar-date form alone. ``date.fromisoformat`` also takes the
    basic (hyphenless) form, week dates, and ordinal dates; each names a day, but
    none is a spelling `m-document-codec` gives the space.
    """
    match = _DATE_LITERAL.match(literal)
    if match is None:
        return literal
    year, month, day = (int(group) for group in match.groups())
    try:
        return _dt.date(year, month, day)
    except ValueError:
        return literal


def _decoded_time(literal: str) -> _dt.time | str:
    """An ISO-8601 wall-clock literal decoded, or the literal itself.

    ``hh:mm:ss`` with an optional fractional second, and — the one variation the
    case format admits — with the seconds omitted. A `Time` names a wall clock,
    so an offset is no part of the spelling, and a fractional field carrying a
    non-zero digit past the sixth names no microsecond-precision value.
    """
    match = _TIME_LITERAL.match(literal)
    if match is None:
        return literal
    hour, minute, second, fraction = match.groups()
    microsecond = _microseconds(fraction)
    if microsecond is None:
        return literal
    try:
        return _dt.time(int(hour), int(minute), int(second or 0), microsecond)
    except ValueError:
        return literal


def _decoded_timestamp(literal: str) -> _dt.datetime | str:
    """An ISO-8601 instant literal decoded, or the literal itself.

    ``YYYY-MM-DDThh:mm:ss`` with an optional fractional second, closed by ``Z`` or
    an ``±hh:mm`` offset. ``datetime.fromisoformat`` also takes basic-format runs,
    week dates, a bare date, a fractional offset, and ANY character where the
    ``T`` belongs — ``2024-01-01X00:00:00+00:00`` parses there — so the grammar is
    stated here instead.
    """
    match = _TIMESTAMP_LITERAL.match(literal)
    if match is None:
        return literal
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    microsecond = _microseconds(fraction)
    offset = _utc_offset(zone)
    if microsecond is None or offset is None:
        return literal
    try:
        return _dt.datetime(
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
        return literal


def _decoded_uuid(literal: str) -> _uuid.UUID | str:
    """A UUID literal decoded, or the literal itself.

    Thirty-two hexadecimal digits in either case, grouped 8-4-4-4-12 or written
    with no hyphens at all. ``uuid.UUID`` also takes brace-wrapped and
    ``urn:uuid:``-prefixed spellings and ignores hyphen POSITION entirely; those
    are its own surface, not the value space's.
    """
    if _UUID_HYPHENATED.match(literal) is None and _UUID_BARE.match(literal) is None:
        return literal
    return _uuid.UUID(literal.replace("-", ""))


def _microseconds(fraction: str | None) -> int | None:
    """A fractional-second field as whole microseconds, or ``None``.

    A digit past the sixth may only be zero: the temporal spaces hold
    microseconds, so a literal carrying finer precision names a value they have no
    member for, and truncating it — which the host parsers do silently — would
    answer a different instant than the one written.
    """
    if fraction is None:
        return 0
    if any(digit != "0" for digit in fraction[_MICROSECOND_DIGITS:]):
        return None
    return int(fraction[:_MICROSECOND_DIGITS].ljust(_MICROSECOND_DIGITS, "0"))


def _utc_offset(zone: str) -> _dt.timezone | None:
    """A ``Z`` / ``±hh:mm`` designator as its offset, or ``None`` when out of range."""
    if zone == "Z":
        return _dt.UTC
    sign = -1 if zone[0] == "-" else 1
    hours, minutes = (int(part) for part in zone[1:].split(":"))
    if hours > 23 or minutes > 59:
        return None
    return _dt.timezone(sign * _dt.timedelta(hours=hours, minutes=minutes))


def _is_integer(value: object) -> TypeGuard[int]:
    """Whether ``value`` is an integer rather than a truth value."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> TypeGuard[int | float]:
    """Whether ``value`` is a JSON number — a truth value is its own kind, never one."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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
