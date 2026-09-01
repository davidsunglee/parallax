"""Declared-type normalization for compatibility-format literal carriers."""

from __future__ import annotations

import datetime as dt
import decimal
from typing import cast

from parallax.core.base import TIMESTAMP, ManagedValue, NeutralType, matches_neutral_type
from parallax.core.base import Decimal as DecimalType
from parallax.core.wire import encode_wire
from parallax.core.wire._json import authored_token


def normalize_case_literal(neutral_type: NeutralType, value: object | None) -> object | None:
    """Normalize only case-format carrier differences into canonical Wire."""
    if value is None:
        return None
    if matches_neutral_type(value, neutral_type):
        return encode_wire(neutral_type, cast("ManagedValue", value))
    if neutral_type == TIMESTAMP and isinstance(value, str):
        try:
            instant = dt.datetime.fromisoformat(value)
        except ValueError:
            return value
        if matches_neutral_type(instant, TIMESTAMP):
            return encode_wire(TIMESTAMP, instant)
        return value
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
