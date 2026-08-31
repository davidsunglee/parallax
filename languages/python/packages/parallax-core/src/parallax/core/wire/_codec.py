"""The exhaustive Neutral Wire Codec implementation."""

from __future__ import annotations

import datetime as dt
import decimal
import math
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, NoReturn, cast

from parallax.core.base import (
    Boolean,
    Bytes,
    Date,
    Decimal,
    Float32,
    Float64,
    Int32,
    Int64,
    Json,
    ManagedValue,
    NeutralType,
    String,
    Time,
    Timestamp,
    Uuid,
    matches_neutral_type,
    nearest_float_at_width,
)
from parallax.core.wire._json import authored_token
from parallax.core.wire._types import WireValue

type WireDecodingReason = Literal["type-mismatch", "noncanonical", "out-of-space"]


class WireDecodingError(ValueError):
    """A serialized literal cannot be decoded under its declared Neutral Type."""

    def __init__(self, reason: WireDecodingReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class WireEncodingError(Exception):
    """A value is not a managed member of its declared Neutral Type."""


@dataclass(frozen=True, slots=True)
class _DecodedWireLiteral:
    managed: ManagedValue
    source_number: decimal.Decimal | None = None
    source_negative_zero: bool = False


_HEX = re.compile(r"^[0-9a-fA-F]*$")
_LOWER_HEX = re.compile(r"^[0-9a-f]*$")
_DECIMAL_NUMBER = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$")
_DATE = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})$")
_LOOSE_DATE = re.compile(r"^([0-9]{1,4})-([0-9]{1,2})-([0-9]{1,2})$")
_TIME = re.compile(r"^([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{3}|[0-9]{6}))?$")
_TIMESTAMP = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})"
    r"(?:\.([0-9]{3}|[0-9]{6}))?(Z|[+-][0-9]{2}:[0-9]{2})$"
)
_UUID_CANONICAL = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_UUID_ALTERNATE = re.compile(
    r"^(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})$"
)
_INT32 = (-(2**31), 2**31 - 1)
_INT64 = (-(2**63), 2**63 - 1)
_MAX_FLOAT_DIGITS = 17


def decode_wire(neutral_type: NeutralType, value: object) -> ManagedValue:
    """Decode one admitted public Wire literal to its managed value."""
    return _decode_admitted(neutral_type, value).managed


def decode_canonical_wire(neutral_type: NeutralType, value: object) -> ManagedValue:
    """Decode one Wire literal only when it is the canonical output spelling."""
    decoded = _decode_admitted(neutral_type, value)
    if not _is_canonical_output(neutral_type, value, decoded):
        _fail("noncanonical", value, neutral_type)
    return decoded.managed


def encode_wire(neutral_type: NeutralType, value: object) -> WireValue:
    """Encode an existing managed member as its canonical built-in Wire value."""
    if not matches_neutral_type(value, neutral_type):
        raise WireEncodingError(
            f"{value!r} is not a member of the declared value space {neutral_type!r}"
        )
    match neutral_type:
        case Boolean() | Int32() | Int64() | String():
            return cast("WireValue", value)
        case Float32() | Float64():
            normalized = 0.0 if cast("float", value) == 0.0 else cast("float", value)
            return _shortest_float(normalized, neutral_type)
        case Decimal(_precision, scale):
            return _exact_decimal(cast("decimal.Decimal", value), scale)
        case Bytes():
            return cast("bytes", value).hex()
        case Date():
            return cast("dt.date", value).isoformat()
        case Time():
            return cast("dt.time", value).isoformat()
        case Timestamp():
            instant = cast("dt.datetime", value).astimezone(dt.UTC)
            return instant.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        case Uuid():
            return str(cast("uuid.UUID", value))
        case Json():
            try:
                return _normalize_json(value, top_level=True)
            except _JsonFailure as exc:
                raise WireEncodingError(str(exc)) from exc


def _decode_admitted(neutral_type: NeutralType, value: object) -> _DecodedWireLiteral:
    match neutral_type:
        case Boolean():
            if not isinstance(value, bool):
                _fail("type-mismatch", value, neutral_type)
            return _DecodedWireLiteral(value)
        case Int32():
            return _decode_integer(value, neutral_type, _INT32)
        case Int64():
            return _decode_integer(value, neutral_type, _INT64)
        case Float32() | Float64():
            return _decode_float(value, neutral_type)
        case Decimal(precision, scale):
            return _decode_decimal(value, neutral_type, precision, scale)
        case String():
            if not isinstance(value, str):
                _fail("type-mismatch", value, neutral_type)
            if not _utf8(value):
                _fail("out-of-space", value, neutral_type)
            return _DecodedWireLiteral(value)
        case Bytes():
            return _decode_bytes(value, neutral_type)
        case Date():
            return _decode_date(value, neutral_type)
        case Time():
            return _decode_time(value, neutral_type)
        case Timestamp():
            return _decode_timestamp(value, neutral_type)
        case Uuid():
            return _decode_uuid(value, neutral_type)
        case Json():
            try:
                managed = _normalize_json(value, top_level=True)
            except _JsonFailure as exc:
                _fail(exc.reason, value, neutral_type)
            return _DecodedWireLiteral(cast("ManagedValue", managed))


def _source_decimal(value: object) -> decimal.Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    token = authored_token(value)
    if token is not None:
        return decimal.Decimal(token)
    if isinstance(value, int):
        return decimal.Decimal(value)
    if not math.isfinite(value):
        return None
    return decimal.Decimal.from_float(value)


def _decode_integer(
    value: object,
    neutral_type: Int32 | Int64,
    bounds: tuple[int, int],
) -> _DecodedWireLiteral:
    number = _source_decimal(value)
    if number is None or not number.is_finite():
        _fail("type-mismatch", value, neutral_type)
    integral = number.to_integral_value()
    if number != integral:
        _fail("type-mismatch", value, neutral_type)
    managed = int(integral)
    if not bounds[0] <= managed <= bounds[1]:
        _fail("out-of-space", value, neutral_type)
    return _DecodedWireLiteral(managed, number, number.is_zero() and number.is_signed())


def _decode_float(
    value: object,
    neutral_type: Float32 | Float64,
) -> _DecodedWireLiteral:
    number = _source_decimal(value)
    if number is None or not number.is_finite():
        _fail("type-mismatch", value, neutral_type)
    managed = nearest_float_at_width(number, neutral_type)
    if managed is None:
        _fail("out-of-space", value, neutral_type)
    return _DecodedWireLiteral(
        managed,
        number,
        number.is_zero() and number.is_signed(),
    )


def _decode_decimal(
    value: object,
    neutral_type: Decimal,
    precision: int,
    scale: int,
) -> _DecodedWireLiteral:
    if not isinstance(value, str):
        _fail("type-mismatch", value, neutral_type)
    if _DECIMAL_NUMBER.fullmatch(value) is None:
        _fail("type-mismatch", value, neutral_type)
    managed = decimal.Decimal(value)
    if not matches_neutral_type(managed, Decimal(precision, scale)):
        _fail("out-of-space", value, neutral_type)
    if _exact_decimal(managed, scale) != value:
        _fail("noncanonical", value, neutral_type)
    return _DecodedWireLiteral(managed)


def _decode_bytes(value: object, neutral_type: Bytes) -> _DecodedWireLiteral:
    if not isinstance(value, str) or len(value) % 2 or _HEX.fullmatch(value) is None:
        _fail("type-mismatch", value, neutral_type)
    if _LOWER_HEX.fullmatch(value) is None:
        _fail("noncanonical", value, neutral_type)
    return _DecodedWireLiteral(bytes.fromhex(value))


def _decode_date(value: object, neutral_type: Date) -> _DecodedWireLiteral:
    if not isinstance(value, str):
        _fail("type-mismatch", value, neutral_type)
    match = _DATE.fullmatch(value)
    if match is None:
        loose = _LOOSE_DATE.fullmatch(value)
        if loose is not None:
            try:
                dt.date(*(int(part) for part in loose.groups()))
            except ValueError:
                _fail("out-of-space", value, neutral_type)
            _fail("noncanonical", value, neutral_type)
        _fail("type-mismatch", value, neutral_type)
    try:
        managed = dt.date(*(int(part) for part in match.groups()))
    except ValueError:
        _fail("out-of-space", value, neutral_type)
    return _DecodedWireLiteral(managed)


def _decode_time(value: object, neutral_type: Time) -> _DecodedWireLiteral:
    if not isinstance(value, str):
        _fail("type-mismatch", value, neutral_type)
    match = _TIME.fullmatch(value)
    if match is None:
        _fail("type-mismatch", value, neutral_type)
    hour, minute, second, fraction = match.groups()
    microsecond = int((fraction or "").ljust(6, "0") or "0")
    try:
        managed = dt.time(int(hour), int(minute), int(second), microsecond)
    except ValueError:
        _fail("out-of-space", value, neutral_type)
    return _DecodedWireLiteral(managed)


def _decode_timestamp(value: object, neutral_type: Timestamp) -> _DecodedWireLiteral:
    if not isinstance(value, str):
        _fail("type-mismatch", value, neutral_type)
    match = _TIMESTAMP.fullmatch(value)
    if match is None:
        _fail("type-mismatch", value, neutral_type)
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    microsecond = int((fraction or "").ljust(6, "0") or "0")
    timezone = dt.UTC
    if zone != "Z":
        sign = -1 if zone.startswith("-") else 1
        zone_hour, zone_minute = (int(part) for part in zone[1:].split(":"))
        try:
            timezone = dt.timezone(sign * dt.timedelta(hours=zone_hour, minutes=zone_minute))
        except ValueError:
            _fail("out-of-space", value, neutral_type)
    try:
        managed = dt.datetime(
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            int(second),
            microsecond,
            tzinfo=timezone,
        )
    except ValueError:
        _fail("out-of-space", value, neutral_type)
    try:
        instant = managed.astimezone(dt.UTC)
    except (OverflowError, ValueError):
        _fail("out-of-space", value, neutral_type)
    if zone != "Z":
        _fail("noncanonical", value, neutral_type)
    return _DecodedWireLiteral(instant)


def _decode_uuid(value: object, neutral_type: Uuid) -> _DecodedWireLiteral:
    if not isinstance(value, str):
        _fail("type-mismatch", value, neutral_type)
    if _UUID_CANONICAL.fullmatch(value) is not None:
        return _DecodedWireLiteral(uuid.UUID(value))
    if _UUID_ALTERNATE.fullmatch(value) is not None:
        _fail("noncanonical", value, neutral_type)
    _fail("type-mismatch", value, neutral_type)


def _is_canonical_output(
    neutral_type: NeutralType,
    written: object,
    decoded: _DecodedWireLiteral,
) -> bool:
    canonical = encode_wire(neutral_type, decoded.managed)
    if isinstance(neutral_type, Float32 | Float64):
        if decoded.source_negative_zero:
            return False
        return _spelled_number(written) == _spelled_number(canonical)
    return canonical == written


def _spelled_number(value: object) -> decimal.Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    token = authored_token(value)
    if token is not None:
        return decimal.Decimal(token)
    if isinstance(value, float):
        return decimal.Decimal(repr(value))
    return decimal.Decimal(value)


def _exact_decimal(value: decimal.Decimal, scale: int) -> str:
    sign, digits, exponent = value.as_tuple()
    unscaled = 0
    for digit in digits:
        unscaled = unscaled * 10 + digit
    unscaled *= 10 ** (cast("int", exponent) + scale)
    padded = str(unscaled).rjust(scale + 1, "0")
    body = f"{padded[:-scale]}.{padded[-scale:]}" if scale else padded
    return f"-{body}" if sign and unscaled else body


def _shortest_float(value: float, neutral_type: Float32 | Float64) -> float:
    for precision in range(1, _MAX_FLOAT_DIGITS + 1):
        spelling = f"{value:.{precision}g}"
        if nearest_float_at_width(decimal.Decimal(spelling), neutral_type) == value:
            return float(spelling)
    return value


class _JsonFailure(Exception):
    def __init__(self, reason: WireDecodingReason, message: str) -> None:
        super().__init__(message)
        self.reason: WireDecodingReason = reason


def _normalize_json(value: object, *, top_level: bool = False) -> WireValue:
    if value is None:
        if top_level:
            raise _JsonFailure("type-mismatch", "bare top-level null is not a Json value")
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        token = authored_token(value)
        return int(decimal.Decimal(token)) if token is not None else int(value)
    if isinstance(value, float):
        token = authored_token(value)
        number = float(decimal.Decimal(token)) if token is not None else float(value)
        if not math.isfinite(number):
            raise _JsonFailure("out-of-space", "a Json number is outside the finite host space")
        return number
    if isinstance(value, str):
        if not _utf8(value):
            raise _JsonFailure("out-of-space", "a Json string has no UTF-8 encoding")
        return value
    if isinstance(value, list):
        return [_normalize_json(item) for item in cast("list[object]", value)]
    if isinstance(value, Mapping):
        normalized: dict[str, WireValue] = {}
        for name, member in cast("Mapping[object, object]", value).items():
            if not isinstance(name, str):
                raise _JsonFailure("type-mismatch", "a Json object member name is not text")
            normalized[name] = _normalize_json(member)
        return normalized
    raise _JsonFailure("type-mismatch", f"{value!r} is not JSON data-model content")


def _utf8(value: str) -> bool:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _fail(
    reason: WireDecodingReason,
    value: object,
    neutral_type: NeutralType,
) -> NoReturn:
    raise WireDecodingError(
        reason,
        f"{value!r} is {reason} for the declared value space {neutral_type!r}",
    )
