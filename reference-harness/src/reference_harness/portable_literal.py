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
"""

from __future__ import annotations

import datetime
import decimal
import re
import uuid
from typing import Any

_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_TIME = re.compile(r"^(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?$")
_TIMESTAMP = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})$"
)
_UUID_HYPHENATED = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
_UUID_BARE = re.compile(r"^[0-9a-fA-F]{32}$")
_DECIMAL = re.compile(r"^(-?)(0|[1-9]\d*)(?:\.(\d+))?$")
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")

# A value beyond this many fractional digits is only in space when the extra
# digits are zeros: the temporal spaces are microsecond-precision (`m-core`).
_MICROSECOND_DIGITS = 6


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
    below zero, integer digits with no leading zero, and an optional fraction.
    No exponent — a `decimal` carries a declared scale, which an exponent does
    not spell — and no sign, separator, or surrounding space a host parser might
    otherwise take.
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
