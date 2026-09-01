"""Declared-type normalization for compatibility-format literal carriers."""

from __future__ import annotations

import datetime as dt
import decimal
import re
from typing import cast

from parallax.core.base import TIMESTAMP, ManagedValue, NeutralType, matches_neutral_type
from parallax.core.base import Decimal as DecimalType
from parallax.core.wire import encode_wire
from parallax.core.wire._json import authored_token

_CASE_TIMESTAMP = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})"
    r"(?:\.([0-9]+))?(Z|[+-][0-9]{2}:[0-9]{2})$"
)


def normalize_case_literal(neutral_type: NeutralType, value: object | None) -> object | None:
    """Normalize only case-format carrier differences into canonical Wire."""
    if value is None:
        return None
    if matches_neutral_type(value, neutral_type):
        return encode_wire(neutral_type, cast("ManagedValue", value))
    if neutral_type == TIMESTAMP and isinstance(value, str):
        instant = _case_timestamp(value)
        return value if instant is None else encode_wire(TIMESTAMP, instant)
    if (
        isinstance(neutral_type, DecimalType)
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ):
        return _case_decimal(value, neutral_type)
    return value


def normalize_case_bound(value: str | dt.datetime | None) -> str | None:
    normalized = normalize_case_literal(TIMESTAMP, value)
    return None if normalized is None else cast("str", normalized)


def _case_timestamp(value: str) -> dt.datetime | None:
    match = _CASE_TIMESTAMP.fullmatch(value)
    if match is None:
        return None
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    if fraction is not None and any(digit != "0" for digit in fraction[6:]):
        return None
    microsecond = int((fraction or "")[:6].ljust(6, "0") or "0")
    timezone = dt.UTC
    if zone != "Z":
        sign = -1 if zone.startswith("-") else 1
        zone_hour, zone_minute = (int(part) for part in zone[1:].split(":"))
        try:
            timezone = dt.timezone(sign * dt.timedelta(hours=zone_hour, minutes=zone_minute))
        except ValueError:
            return None
    try:
        instant = dt.datetime(
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            int(second),
            microsecond,
            timezone,
        )
        return instant.astimezone(dt.UTC)
    except (OverflowError, ValueError):
        return None


def _case_decimal(value: int | float, neutral_type: DecimalType) -> object:
    try:
        number = decimal.Decimal(authored_token(value) or str(value))
    except decimal.InvalidOperation:
        return value
    sign, digits, exponent = number.as_tuple()
    if not isinstance(exponent, int):
        return value
    original_exponent = exponent
    last = len(digits)
    while last and digits[last - 1] == 0:
        last -= 1
        exponent += 1
    if exponent < -neutral_type.scale:
        return value
    if number and abs(number.adjusted()) > neutral_type.precision + neutral_type.scale:
        return value
    normalized = decimal.Decimal((sign, digits, original_exponent))
    return format(normalized, f".{neutral_type.scale}f")
