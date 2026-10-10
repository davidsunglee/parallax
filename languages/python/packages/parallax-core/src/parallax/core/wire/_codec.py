from __future__ import annotations

import datetime as dt
import decimal
import math
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, NoReturn, assert_never, cast

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
    nearest_binary32_of_spelling,
    nearest_float_at_width,
)
from parallax.core.base._neutral import (
    JsonCarrierFailure,
    ManagedValueExclusion,
    base_managed_carrier,
    exceeds_json_int_value_space,
    host_float_binary32,
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
    if isinstance(neutral_type, Boolean) and isinstance(value, bool):
        return value
    if isinstance(neutral_type, String) and isinstance(value, str):
        managed = str.__str__(value)
        if managed.isascii() or matches_neutral_type(managed, neutral_type):
            return managed
        _fail("out-of-space", value, neutral_type)
    if isinstance(neutral_type, (Int32, Int64)) and type(value) is int:
        managed_int = int.__int__(value)
        if matches_neutral_type(managed_int, neutral_type):
            return managed_int
        _fail("out-of-space", value, neutral_type)
    decoded = _decode_admitted(neutral_type, value)
    if not _is_canonical_output(neutral_type, value, decoded):
        _fail("noncanonical", value, neutral_type)
    return decoded.managed


def encode_wire(neutral_type: NeutralType, value: ManagedValue) -> WireValue:
    """Encode an existing managed member as its canonical built-in Wire value."""
    normalized = base_managed_carrier(value, neutral_type)
    if not matches_neutral_type(normalized, neutral_type):
        raise WireEncodingError(
            f"{_diagnostic(value)} is not a member of the declared value space "
            f"{_diagnostic(neutral_type)}"
        )
    return _canonical_spelling(neutral_type, normalized)


def encode_managed_wire(neutral_type: NeutralType, value: ManagedValue) -> WireValue:
    """Encode a value already admitted at a trusted managed-state boundary."""
    match neutral_type:
        case Boolean():
            return bool(value)
        case Int32() | Int64():
            return int(cast("int", value))
        case String():
            return str.__str__(cast("str", value))
        case Float64():
            float_value = float(cast("float", value))
            return 0.0 if float_value == 0.0 else float_value
        case _:
            pass
    return _canonical_spelling(neutral_type, base_managed_carrier(value, neutral_type))


type EncodedJsonKind = Literal["boolean", "number", "string"]

# The JSON primitive kind each arm of `_canonical_spelling` below spells its
# variant's values in. Json has no single kind: its values are any JSON value.
_ENCODED_JSON_KIND: Final[Mapping[type[NeutralType], EncodedJsonKind | None]] = MappingProxyType(
    {
        Boolean: "boolean",
        Int32: "number",
        Int64: "number",
        String: "string",
        Float32: "number",
        Float64: "number",
        Decimal: "string",
        Bytes: "string",
        Date: "string",
        Time: "string",
        Timestamp: "string",
        Uuid: "string",
        Json: None,
    }
)


def encoded_json_kind(neutral_type: NeutralType) -> EncodedJsonKind | None:
    """The JSON primitive kind every canonical Wire spelling of
    ``neutral_type`` takes, or ``None`` where no single kind does."""
    return _ENCODED_JSON_KIND[type(neutral_type)]


# One arm per Neutral Type variant. It runs per value on Wire encode (all of
# `encode_wire`, and `encode_managed_wire` past its scalar fast path), so the arms stay
# inline rather than behind a per-variant call.
def _canonical_spelling(neutral_type: NeutralType, managed: object) -> WireValue:  # noqa: C901
    """The canonical spelling of a value already known to be a managed member."""
    match neutral_type:
        case Boolean():
            return cast("bool", managed)
        case Int32() | Int64():
            return cast("int", managed)
        case String():
            return cast("str", managed)
        case Float32():
            float_value = cast("float", managed)
            float_value = 0.0 if float_value == 0.0 else float_value
            return _shortest_float(float_value)
        case Float64():
            float_value = cast("float", managed)
            return 0.0 if float_value == 0.0 else float_value
        case Decimal(_precision, scale):
            return _exact_decimal(cast("decimal.Decimal", managed), scale)
        case Bytes():
            return bytes.hex(cast("bytes", managed))
        case Date():
            return dt.date.isoformat(cast("dt.date", managed))
        case Time():
            return dt.time.isoformat(cast("dt.time", managed))
        case Timestamp():
            # Spelled from fields: ``strftime`` on an aware value leaves a per-call method-name
            # string in CPython's type method cache.
            instant = cast("dt.datetime", managed)
            if instant.tzinfo is not dt.UTC:
                instant = dt.datetime.astimezone(instant, dt.UTC)
            return (
                f"{instant.year:04d}-{instant.month:02d}-{instant.day:02d}"
                f"T{instant.hour:02d}:{instant.minute:02d}:{instant.second:02d}"
                f".{instant.microsecond:06d}Z"
            )
        case Uuid():
            return uuid.UUID.__str__(cast("uuid.UUID", managed))
        case Json():
            try:
                return _normalize_json(managed, top_level=True)
            except _JsonFailure as exc:
                raise WireEncodingError(str(exc)) from exc
        case _ as unreachable:
            assert_never(unreachable)


# One arm per Neutral Type variant, dispatched once per value on Wire decode (all of
# `decode_wire`, and `decode_canonical_wire` past its scalar fast path); splitting the
# dispatch would add a call to that per-value path.
def _decode_admitted(neutral_type: NeutralType, value: object) -> _DecodedWireLiteral:  # noqa: C901
    if _is_unrecognized_exclusion(value):
        _fail("type-mismatch", value, neutral_type)
    match neutral_type:
        case Boolean():
            return _decode_boolean(value, neutral_type)
        case Int32() | Int64():
            return _decode_integer(value, neutral_type)
        case Float32():
            return _decode_float32(value, neutral_type)
        case Float64():
            return _decode_float64(value, neutral_type)
        case Decimal(precision, scale):
            return _decode_decimal(value, neutral_type, precision, scale)
        case String():
            return _decode_string(value, neutral_type)
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


def _decode_boolean(value: object, neutral_type: Boolean) -> _DecodedWireLiteral:
    if not isinstance(value, bool):
        _fail("type-mismatch", value, neutral_type)
    return _DecodedWireLiteral(value)


def _decode_string(value: object, neutral_type: String) -> _DecodedWireLiteral:
    if not isinstance(value, str):
        _fail("type-mismatch", value, neutral_type)
    managed = str.__str__(value)
    if not matches_neutral_type(managed, neutral_type):
        _fail("out-of-space", value, neutral_type)
    return _DecodedWireLiteral(managed)


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


def _decode_float32(value: object, neutral_type: Float32) -> _DecodedWireLiteral:
    """Round the number ``value`` is written as once to binary32: the digits a
    parser kept, an integer's own value, or the number a bare host float names."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("type-mismatch", value, neutral_type)
    token = authored_token(value)
    if token is not None:
        managed = nearest_binary32_of_spelling(token)
        if managed is None:
            _fail("out-of-space", value, neutral_type)
        return _DecodedWireLiteral(managed, managed == 0.0 and _spells_negative_zero(token))
    if isinstance(value, int):
        return _decode_integer_to_float(value, neutral_type)
    base_value = float.__float__(value)
    managed = host_float_binary32(base_value)
    if managed is None:
        _fail("out-of-space" if math.isfinite(base_value) else "type-mismatch", value, neutral_type)
    return _DecodedWireLiteral(
        managed,
        base_value == 0.0 and math.copysign(1.0, base_value) < 0.0,
    )


def _decode_float64(value: object, neutral_type: Float64) -> _DecodedWireLiteral:
    """Round the number ``value`` is written as once to binary64: the digits a
    parser kept, an integer's own value, or a bare host float, which is already
    the binary64 that both its exact value and its shortest spelling round to."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("type-mismatch", value, neutral_type)
    token = authored_token(value)
    if token is not None:
        managed = float(token)
        if math.isinf(managed):
            _fail("out-of-space", value, neutral_type)
        if managed == 0.0:
            return _DecodedWireLiteral(0.0, _spells_negative_zero(token))
        return _DecodedWireLiteral(managed)
    if isinstance(value, int):
        return _decode_integer_to_float(value, neutral_type)
    managed = float.__float__(value)
    if not math.isfinite(managed):
        _fail("type-mismatch", value, neutral_type)
    if managed == 0.0:
        return _DecodedWireLiteral(0.0, math.copysign(1.0, managed) < 0.0)
    return _DecodedWireLiteral(managed)


def _spells_negative_zero(token: str) -> bool:
    """Whether the number ``token`` spells is zero and negative: an underflowing
    spelling such as ``-1e-400`` names a nonzero number, whatever it parses to."""
    significand = token.lower().partition("e")[0]
    return significand.startswith("-") and not significand.strip("-+0.")


def _decode_integer_to_float(value: int, neutral_type: Float32 | Float64) -> _DecodedWireLiteral:
    managed = nearest_float_at_width(int.__int__(value), neutral_type)
    if managed is None:
        _fail("out-of-space", value, neutral_type)
    return _DecodedWireLiteral(managed)


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
    """Whether ``written`` is the canonical spelling of the value it decoded to.

    Only the numeric and temporal spellings have to be derived to answer, and
    the reason is what each decoder above already established. Boolean, String
    and Json have no noncanonical spelling at all: every literal their grammar
    admits is the one this module writes for the value it names. Decimal,
    Bytes, Date and Uuid have one, and each decoder refuses it against the
    source text itself — the exact scaled spelling, the lowercase-hex grammar,
    the fixed-width date grammar, the lowercase hyphenated UUID grammar — so a
    literal that reaches here has already been held against its canonical
    spelling. What is left is the numbers, whose spelling is not the value they
    name, and the temporal fraction widths, which the grammars admit written at
    three digits, at six, and not at all.
    """
    match neutral_type:
        case Int32() | Int64():
            canonical = _canonical_spelling(neutral_type, decoded.managed)
            return _spelled_number(written) == _spelled_number(canonical)
        case Float32() | Float64():
            if decoded.source_negative_zero:
                return False
            canonical = cast("float", _canonical_spelling(neutral_type, decoded.managed))
            if type(written) is float:
                # Two floats' shortest spellings name one number exactly when they are equal.
                return written == canonical
            return _spelled_number(written) == decimal.Decimal(float.__repr__(canonical))
        case Time() | Timestamp():
            canonical = _canonical_spelling(neutral_type, decoded.managed)
            return isinstance(written, str) and canonical == str.__str__(written)
        case Boolean() | String() | Json():
            return True
        case Decimal() | Bytes() | Date() | Uuid():
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


def _shortest_float(value: float) -> float:
    """The fewest-digit number that names the binary32 ``value``.

    Only a ``float32`` has one to search for: at binary64 a number that names
    ``value`` IS ``value``, so the search would hand back what it was given, and
    a ``float64``'s canonical Wire Value is the value itself.
    """
    for precision in range(1, _MAX_FLOAT_DIGITS + 1):
        spelling = f"{value:.{precision}g}"
        if nearest_binary32_of_spelling(spelling) == value:
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


# One arm per JSON scalar kind. It runs per scalar inside every Json value on Wire encode
# and decode, so the arms stay inline rather than behind a per-kind call.
def _normalize_json_scalar(value: object) -> WireValue:  # noqa: C901
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
            return _bounded_repr(str.__str__(value), "characters")
        if isinstance(value, bytes):
            return _bounded_repr(bytes.__bytes__(value), "bytes")
        return f"<{type(value).__name__}>"
    except Exception:
        return "<unrenderable value>"


def _bounded_repr(content: str | bytes, unit: str) -> str:
    """``content``'s repr, cut at the diagnostic limit with its full length in ``unit``."""
    if len(content) <= _DIAGNOSTIC_TEXT_LIMIT:
        return repr(content)
    return f"{content[:_DIAGNOSTIC_TEXT_LIMIT]!r}… <{len(content)} {unit}>"


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


def _is_unrecognized_exclusion(value: object) -> bool:
    if not isinstance(value, ManagedValueExclusion):
        return False
    return not isinstance(value, (int, float)) or authored_token(value) is None
