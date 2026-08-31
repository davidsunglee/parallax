"""The exhaustive Neutral Wire Codec implementation."""

from __future__ import annotations

import datetime as dt
import decimal
import math
import re
import uuid
from dataclasses import dataclass
from typing import Literal, NoReturn, assert_never, cast

from parallax.core.base import (
    STRING,
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
from parallax.core.base._neutral import (
    JsonCarrierFailure,
    ManagedValueExclusion,
    base_datetime_carrier,
    base_time_carrier,
    base_uuid_carrier,
    exceeds_json_int_value_space,
    normalize_json_carrier,
)
from parallax.core.wire._json import (
    authored_token,
    exceeds_json_int_space,
)
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
_MAX_FLOAT_DIGITS = 17
_DIAGNOSTIC_TEXT_LIMIT = 96
_DIAGNOSTIC_INT_BITS = 256


def decode_wire(neutral_type: NeutralType, value: WireValue) -> ManagedValue:
    """Decode one admitted public Wire literal to its managed value."""
    return _decode_admitted(neutral_type, value).managed


def decode_canonical_wire(neutral_type: NeutralType, value: WireValue) -> ManagedValue:
    """Decode one Wire literal only when it is the canonical output spelling."""
    decoded = _decode_admitted(neutral_type, value)
    if not _is_canonical_output(neutral_type, value, decoded):
        _fail("noncanonical", value, neutral_type)
    return decoded.managed


def encode_wire(neutral_type: NeutralType, value: ManagedValue) -> WireValue:
    """Encode an existing managed member as its canonical built-in Wire value."""
    normalized = _base_managed_carrier(value, neutral_type)
    if not matches_neutral_type(normalized, neutral_type):
        raise WireEncodingError(
            f"{_diagnostic(value)} is not a member of the declared value space "
            f"{_diagnostic(neutral_type)}"
        )
    match neutral_type:
        case Boolean():
            return cast("bool", normalized)
        case Int32() | Int64():
            return cast("int", normalized)
        case String():
            return cast("str", normalized)
        case Float32() | Float64():
            float_value = cast("float", normalized)
            float_value = 0.0 if float_value == 0.0 else float_value
            return _shortest_float(float_value, neutral_type)
        case Decimal(_precision, scale):
            return _exact_decimal(cast("decimal.Decimal", normalized), scale)
        case Bytes():
            return bytes.hex(cast("bytes", normalized))
        case Date():
            return dt.date.isoformat(cast("dt.date", normalized))
        case Time():
            return dt.time.isoformat(cast("dt.time", normalized))
        case Timestamp():
            instant = dt.datetime.astimezone(cast("dt.datetime", normalized), dt.UTC)
            return dt.datetime.strftime(instant, "%Y-%m-%dT%H:%M:%S.%f") + "Z"
        case Uuid():
            return uuid.UUID.__str__(cast("uuid.UUID", normalized))
        case Json():
            try:
                return _normalize_json(normalized, top_level=True)
            except _JsonFailure as exc:
                raise WireEncodingError(str(exc)) from exc
        case _ as unreachable:
            assert_never(unreachable)


def _decode_admitted(neutral_type: NeutralType, value: object) -> _DecodedWireLiteral:
    if _is_unrecognized_exclusion(value):
        _fail("type-mismatch", value, neutral_type)
    match neutral_type:
        case Boolean():
            if not isinstance(value, bool):
                _fail("type-mismatch", value, neutral_type)
            return _DecodedWireLiteral(value)
        case Int32() | Int64():
            return _decode_integer(value, neutral_type)
        case Float32() | Float64():
            return _decode_float(value, neutral_type)
        case Decimal(precision, scale):
            return _decode_decimal(value, neutral_type, precision, scale)
        case String():
            if not isinstance(value, str):
                _fail("type-mismatch", value, neutral_type)
            managed = str.__str__(value)
            if not matches_neutral_type(managed, neutral_type):
                _fail("out-of-space", value, neutral_type)
            return _DecodedWireLiteral(managed)
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
        case _ as unreachable:
            assert_never(unreachable)


def _source_decimal(value: object) -> decimal.Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    token = authored_token(value)
    if token is not None:
        return decimal.Decimal(token)
    if isinstance(value, int):
        return decimal.Decimal(int.__int__(value))
    base_value = float.__float__(value)
    if not math.isfinite(base_value):
        return None
    return decimal.Decimal.from_float(base_value)


def _decode_integer(
    value: object,
    neutral_type: Int32 | Int64,
) -> _DecodedWireLiteral:
    number = _source_decimal(value)
    if number is None or not number.is_finite():
        _fail("type-mismatch", value, neutral_type)
    integral = number.to_integral_value()
    if number != integral:
        _fail("type-mismatch", value, neutral_type)
    managed = int(integral)
    if not matches_neutral_type(managed, neutral_type):
        _fail("out-of-space", value, neutral_type)
    return _DecodedWireLiteral(managed, number.is_zero() and number.is_signed())


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
    text = str.__str__(value)
    if _DECIMAL_NUMBER.fullmatch(text) is None:
        _fail("type-mismatch", value, neutral_type)
    managed = decimal.Decimal(text)
    if not matches_neutral_type(managed, Decimal(precision, scale)):
        _fail("out-of-space", value, neutral_type)
    if _exact_decimal(managed, scale) != text:
        _fail("noncanonical", value, neutral_type)
    return _DecodedWireLiteral(managed)


def _decode_bytes(value: object, neutral_type: Bytes) -> _DecodedWireLiteral:
    if not isinstance(value, str):
        _fail("type-mismatch", value, neutral_type)
    text = str.__str__(value)
    if len(text) % 2 or _HEX.fullmatch(text) is None:
        _fail("type-mismatch", value, neutral_type)
    if _LOWER_HEX.fullmatch(text) is None:
        _fail("noncanonical", value, neutral_type)
    return _DecodedWireLiteral(bytes.fromhex(text))


def _decode_date(value: object, neutral_type: Date) -> _DecodedWireLiteral:
    if not isinstance(value, str):
        _fail("type-mismatch", value, neutral_type)
    text = str.__str__(value)
    match = _DATE.fullmatch(text)
    if match is None:
        loose = _LOOSE_DATE.fullmatch(text)
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
    match = _TIME.fullmatch(str.__str__(value))
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
    match = _TIMESTAMP.fullmatch(str.__str__(value))
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
    text = str.__str__(value)
    if _UUID_CANONICAL.fullmatch(text) is not None:
        return _DecodedWireLiteral(uuid.UUID(text))
    if _UUID_ALTERNATE.fullmatch(text) is not None:
        _fail("noncanonical", value, neutral_type)
    _fail("type-mismatch", value, neutral_type)


def _is_canonical_output(
    neutral_type: NeutralType,
    written: object,
    decoded: _DecodedWireLiteral,
) -> bool:
    canonical = encode_wire(neutral_type, decoded.managed)
    match neutral_type:
        case Int32() | Int64():
            return _spelled_number(written) == _spelled_number(canonical)
        case Float32() | Float64():
            if decoded.source_negative_zero:
                return False
            return _spelled_number(written) == _spelled_number(canonical)
        case Boolean():
            return canonical is written
        case Decimal() | String() | Bytes() | Date() | Time() | Timestamp() | Uuid():
            return isinstance(written, str) and canonical == str.__str__(written)
        case Json():
            return True
        case _ as unreachable:
            assert_never(unreachable)


def _spelled_number(value: object) -> decimal.Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    token = authored_token(value)
    if token is not None:
        return decimal.Decimal(token)
    if isinstance(value, float):
        return decimal.Decimal(float.__repr__(float.__float__(value)))
    return decimal.Decimal(int.__int__(value))


def _exact_decimal(value: decimal.Decimal, scale: int) -> str:
    sign, digits, exponent = decimal.Decimal.as_tuple(value)
    first_nonzero = next((index for index, digit in enumerate(digits) if digit), None)
    if first_nonzero is None:
        return f"0.{''.ljust(scale, '0')}" if scale else "0"
    normalized_exponent = cast("int", exponent)
    last_nonzero = len(digits)
    while digits[last_nonzero - 1] == 0:
        last_nonzero -= 1
        normalized_exponent += 1
    significant = "".join(str(digit) for digit in digits[first_nonzero:last_nonzero])
    unscaled = significant + "0" * (normalized_exponent + scale)
    padded = unscaled.rjust(scale + 1, "0")
    body = f"{padded[:-scale]}.{padded[-scale:]}" if scale else padded
    return f"-{body}" if sign else body


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


def _normalize_json(
    value: object,
    *,
    top_level: bool = False,
) -> WireValue:
    try:
        return cast(
            "WireValue",
            normalize_json_carrier(
                value,
                normalize_scalar=_normalize_json_scalar,
                top_level=top_level,
                accept_mappings=True,
            ),
        )
    except JsonCarrierFailure as exc:
        reason: WireDecodingReason = (
            "out-of-space" if exc.kind == "member-name-unicode" else "type-mismatch"
        )
        raise _JsonFailure(reason, str(exc)) from exc


def _normalize_json_scalar(value: object) -> WireValue:
    if _is_unrecognized_exclusion(value):
        raise _JsonFailure(
            "type-mismatch",
            "value is excluded from managed membership",
        )
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        token = authored_token(value)
        if token is not None:
            if exceeds_json_int_space(token):
                raise _JsonFailure(
                    "out-of-space",
                    "a Json integer is outside the ordinary host serialization space",
                )
            return int(decimal.Decimal(token))
        base_value = int.__int__(value)
        if exceeds_json_int_value_space(base_value):
            raise _JsonFailure(
                "out-of-space",
                "a Json integer is outside the ordinary host serialization space",
            )
        return base_value
    if isinstance(value, float):
        token = authored_token(value)
        number = float(decimal.Decimal(token)) if token is not None else float.__float__(value)
        if not math.isfinite(number):
            raise _JsonFailure("out-of-space", "a Json number is outside the finite host space")
        return number
    if isinstance(value, str):
        text = str.__str__(value)
        if not matches_neutral_type(text, STRING):
            raise _JsonFailure("out-of-space", "a Json string has no UTF-8 encoding")
        return text
    raise _JsonFailure("type-mismatch", f"{_diagnostic(value)} is not JSON data-model content")


def _diagnostic(value: object) -> str:
    try:
        if value is None:
            return "None"
        if isinstance(value, bool):
            return "True" if value else "False"
        if isinstance(value, int):
            bits = int.bit_length(value)
            if bits > _DIAGNOSTIC_INT_BITS:
                return f"<{type(value).__name__}: {bits}-bit integer>"
            return int.__repr__(value)
        if isinstance(value, float):
            return float.__repr__(float.__float__(value))
        if isinstance(value, str):
            text = str.__str__(value)
            if len(text) <= _DIAGNOSTIC_TEXT_LIMIT:
                return repr(text)
            prefix = text[:_DIAGNOSTIC_TEXT_LIMIT]
            return f"{prefix!r}… <{len(text)} characters>"
        if isinstance(value, bytes):
            octets = bytes.__bytes__(value)
            if len(octets) <= _DIAGNOSTIC_TEXT_LIMIT:
                return bytes.__repr__(octets)
            prefix = octets[:_DIAGNOSTIC_TEXT_LIMIT]
            return f"{prefix!r}… <{len(octets)} bytes>"
        return f"<{type(value).__name__}>"
    except Exception:
        return "<unrenderable value>"


def _fail(
    reason: WireDecodingReason,
    value: object,
    neutral_type: NeutralType,
) -> NoReturn:
    raise WireDecodingError(
        reason,
        f"{_diagnostic(value)} is {reason} for the declared value space "
        f"{_diagnostic(neutral_type)}",
    )


def _base_managed_carrier(value: object, neutral_type: NeutralType) -> object:
    if isinstance(value, ManagedValueExclusion):
        return value
    match neutral_type:
        case Int32() | Int64() if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and matches_neutral_type(value, neutral_type)
        ):
            return int.__int__(value)
        case Float32() | Float64() if isinstance(value, float) and matches_neutral_type(
            value, neutral_type
        ):
            return float.__float__(value)
        case Decimal() if isinstance(value, decimal.Decimal):
            sign, digits, exponent = decimal.Decimal.as_tuple(value)
            if isinstance(exponent, int):
                return decimal.Decimal((sign, digits, exponent))
            return value
        case String() if isinstance(value, str):
            return str.__str__(value)
        case Bytes() if isinstance(value, bytes):
            return bytes.__bytes__(value)
        case Date() if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
            return dt.date.fromordinal(dt.date.toordinal(value))
        case Time() if isinstance(value, dt.time):
            return base_time_carrier(value)
        case Timestamp() if isinstance(value, dt.datetime):
            return base_datetime_carrier(value)
        case Uuid() if isinstance(value, uuid.UUID):
            return base_uuid_carrier(value)
        case _:
            return value


def _is_unrecognized_exclusion(value: object) -> bool:
    if not isinstance(value, ManagedValueExclusion):
        return False
    return not isinstance(value, (int, float)) or authored_token(value) is None
