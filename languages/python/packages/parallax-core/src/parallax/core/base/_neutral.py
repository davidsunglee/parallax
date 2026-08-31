"""The structured Neutral Type algebra and managed value spaces (m-core)."""

from __future__ import annotations

import datetime as _dt
import decimal as _decimal
import math as _math
import struct as _struct
import sys as _sys
import types as _types
import uuid as _uuid
from collections.abc import Callable as _Callable
from collections.abc import Mapping as _Mapping
from dataclasses import dataclass
from fractions import Fraction as _Fraction
from typing import Final, Literal, TypeGuard, cast

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


class ManagedValueExclusion:
    """Token-free marker for a host carrier that is not a managed value.

    Behavioral modules may mix this marker into private ingress carriers when
    an ordinary host payload is needed for transport but must not become
    authoritative managed state. The marker carries no source text, grammar,
    failure reason, or conversion behavior.
    """

    __slots__ = ()


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
    if isinstance(value, ManagedValueExclusion):
        return None
    try:
        base_value = value if type(value) is _dt.datetime else base_datetime_carrier(value)
        if base_value.utcoffset() is None:
            return None
        return base_value.astimezone(_dt.UTC)
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
    if isinstance(value, ManagedValueExclusion):
        return False
    match declared:
        case Boolean():
            return isinstance(value, bool)
        case Int32():
            return _is_integer(value) and _INT32_BOUNDS[0] <= int.__int__(value) <= _INT32_BOUNDS[1]
        case Int64():
            return _is_integer(value) and _INT64_BOUNDS[0] <= int.__int__(value) <= _INT64_BOUNDS[1]
        case Float32():
            return (
                isinstance(value, float)
                and _math.isfinite(float.__float__(value))
                and nearest_float_at_width(float.__float__(value), declared)
                == float.__float__(value)
            )
        case Float64():
            return isinstance(value, float) and _math.isfinite(float.__float__(value))
        case Decimal(precision, scale):
            return isinstance(value, _decimal.Decimal) and _is_exact_decimal(
                value, precision, scale
            )
        case String():
            return isinstance(value, str) and _is_utf8_encodable(str.__str__(value))
        case Bytes():
            return isinstance(value, bytes)
        case Date():
            return isinstance(value, _dt.date) and not isinstance(value, _dt.datetime)
        case Time():
            return isinstance(value, _dt.time) and base_time_carrier(value).tzinfo is None
        case Timestamp():
            return isinstance(value, _dt.datetime) and utc_instant(value) is not None
        case Uuid():
            return isinstance(value, _uuid.UUID) and base_uuid_carrier(value) is not None
        case Json():
            return value is not None and _is_json_value(value)


def coerce_neutral_input(value: object, declared: NeutralType) -> object:
    """``value`` normalized by the adjacent forms the developer input policy
    admits for ``declared`` (`python.md` "Neutral scalar type mapping", the
    input-policy column), and otherwise returned unchanged.

    This is the boundary the DEVELOPER-facing write validators call — a
    runtime argument already carries a native Python value, never a wire
    literal, so only the input policy's own typed conversions apply: an
    :class:`int` for a :class:`Decimal`, a lossless :class:`int` for a float,
    and a canonical UUID string. A host float is
    projected immediately to the declared width, negative zero normalizes to
    positive zero, and an aware Timestamp normalizes to UTC.

    A caller chose an integer carrier, so an integer no float of the width
    carries exactly stays an integer and fails membership. Fractional host
    floats may round because that is the documented developer-input policy.
    """
    if isinstance(value, ManagedValueExclusion):
        return value
    match declared:
        case Decimal() if _is_integer(value):
            return _decimal.Decimal(int.__int__(value))
        case Float32() | Float64() if isinstance(value, float):
            base_value = float.__float__(value)
            projected = nearest_float_at_width(base_value, declared)
            return base_value if projected is None else projected
        case Float32() | Float64() if _is_integer(value):
            base_value = int.__int__(value)
            projected = nearest_float_at_width(base_value, declared)
            return projected if projected is not None and projected == base_value else base_value
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
    base_value = str.__str__(value)
    try:
        decoded = _uuid.UUID(base_value)
    except (AttributeError, ValueError):
        return base_value
    return decoded if str(decoded) == base_value else base_value


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
    if isinstance(value, (bool, ManagedValueExclusion)):
        return None
    if isinstance(value, float):
        base_value = float.__float__(value)
        if not _math.isfinite(base_value):
            return None
        exact = _decimal.Decimal.from_float(base_value)
    elif isinstance(value, int):
        base_value = int.__int__(value)
        magnitude_bits = abs(base_value).bit_length()
        if isinstance(declared, Float32) and magnitude_bits > 129:
            return None
        if isinstance(declared, Float64) and magnitude_bits > 1025:
            return None
        exact = _decimal.Decimal(base_value)
    else:
        sign, digits, exponent = _decimal.Decimal.as_tuple(value)
        if not isinstance(exponent, int):
            return None
        exact = _decimal.Decimal((sign, digits, exponent))

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
        str.encode(value, "utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _is_exact_decimal(value: _decimal.Decimal, precision: int, scale: int) -> bool:
    """Whether ``value`` is ``unscaled * 10**-scale`` within ``precision`` digits.

    Exact: a value needing more fractional digits than ``scale`` is not a
    member, because representing it would require rounding. Trailing zeros
    carry no value, so ``1.500`` and ``1.5`` are the same member.
    """
    _sign, digits, exponent = _decimal.Decimal.as_tuple(value)
    if not isinstance(exponent, int):
        return False
    first_nonzero = next((index for index, digit in enumerate(digits) if digit), None)
    if first_nonzero is None:
        return True
    last_nonzero = len(digits)
    while digits[last_nonzero - 1] == 0:
        last_nonzero -= 1
        exponent += 1
    if exponent < -scale:
        return False
    significant_digits = last_nonzero - first_nonzero
    return significant_digits + exponent + scale <= precision


def _is_json_value(value: object) -> bool:
    """Whether ``value`` is a JSON data-model value, ``null`` included.

    Only the top-level position excludes ``null``; nested nulls are ordinary
    structured content. A non-finite float has no JSON encoding and an object
    member name is always text.
    """
    try:
        normalize_json_carrier(
            value,
            normalize_scalar=_json_membership_scalar,
            accept_mappings=False,
        )
    except JsonCarrierFailure:
        return False
    return True


def _json_membership_scalar(value: object) -> object:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, ManagedValueExclusion):
        raise JsonCarrierFailure("invalid-scalar", "value is excluded from managed membership")
    if isinstance(value, int):
        integer = int.__int__(value)
        if not exceeds_json_int_value_space(integer):
            return integer
    if isinstance(value, str):
        text = str.__str__(value)
        if _is_utf8_encodable(text):
            return text
    elif isinstance(value, float):
        number = float.__float__(value)
        if _math.isfinite(number):
            return number
    raise JsonCarrierFailure("invalid-scalar", "value is not JSON data-model content")


def exceeds_json_int_value_space(value: int) -> bool:
    limit = _sys.get_int_max_str_digits()
    if limit == 0:
        return False
    magnitude = abs(int.__int__(value))
    magnitude_bits = magnitude.bit_length()
    if magnitude_bits <= limit * 3:
        return False
    if magnitude_bits > limit * 4:
        return True
    return _decimal.Decimal(magnitude).adjusted() >= limit


type _JsonCarrierFailureKind = Literal[
    "bare-null",
    "cycle",
    "invalid-scalar",
    "member-name-type",
    "member-name-unicode",
    "member-name-collision",
]


class JsonCarrierFailure(Exception):
    def __init__(self, kind: _JsonCarrierFailureKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


type _JsonContainer = list[object] | dict[str, object]
type _JsonLocation = int | str


@dataclass(frozen=True, slots=True)
class _JsonVisit:
    value: object
    parent: _JsonContainer
    location: _JsonLocation
    top_level: bool = False


@dataclass(frozen=True, slots=True)
class _JsonLeave:
    identity: int


type _JsonTraversal = _JsonVisit | _JsonLeave


def normalize_json_carrier(
    value: object,
    *,
    normalize_scalar: _Callable[[object], object],
    top_level: bool = False,
    accept_mappings: bool = False,
) -> object:
    """Normalize one JSON carrier through the shared iterative container walk."""
    root: list[object] = [None]
    active_containers: set[int] = set()
    pending: list[_JsonTraversal] = [_JsonVisit(value, root, 0, top_level)]
    while pending:
        task = pending.pop()
        if isinstance(task, _JsonLeave):
            active_containers.remove(task.identity)
            continue
        current = task.value
        if isinstance(current, ManagedValueExclusion) and isinstance(current, (list, _Mapping)):
            raise JsonCarrierFailure(
                "invalid-scalar",
                "a Json container is excluded from managed membership",
            )
        if current is None and task.top_level:
            raise JsonCarrierFailure("bare-null", "bare top-level null is not a Json value")
        if isinstance(current, list):
            base_current = cast("list[object]", current)
            items = base_list_carrier(base_current)
            normalized_list: list[object] = [None] * len(items)
            _assign_json_value(task.parent, task.location, normalized_list)
            _enter_json_container(base_current, active_containers, pending)
            for index in range(len(items) - 1, -1, -1):
                pending.append(_JsonVisit(items[index], normalized_list, index))
            continue
        if isinstance(current, _Mapping) and (accept_mappings or isinstance(current, dict)):
            mapping = cast("_Mapping[object, object]", current)
            items = _json_mapping_items(mapping)
            normalized_items = _normalize_json_member_names(items)
            normalized_object: dict[str, object] = {}
            _assign_json_value(task.parent, task.location, normalized_object)
            _enter_json_container(mapping, active_containers, pending)
            for name, member in reversed(normalized_items):
                pending.append(_JsonVisit(member, normalized_object, name))
            continue
        _assign_json_value(
            task.parent,
            task.location,
            normalize_scalar(cast("object", current)),
        )
    return root[0]


def _enter_json_container(
    value: object,
    active_containers: set[int],
    pending: list[_JsonTraversal],
) -> None:
    identity = id(value)
    if identity in active_containers:
        raise JsonCarrierFailure("cycle", "cyclic containers are not Json content")
    active_containers.add(identity)
    pending.append(_JsonLeave(identity))


def _json_mapping_items(value: _Mapping[object, object]) -> list[tuple[object, object]]:
    if isinstance(value, dict):
        mapping = base_dict_carrier(value)
        return list(mapping.items())
    return list(value.items())


def _normalize_json_member_names(
    items: list[tuple[object, object]],
) -> list[tuple[str, object]]:
    normalized: list[tuple[str, object]] = []
    names: set[str] = set()
    for name, member in items:
        if isinstance(name, ManagedValueExclusion):
            raise JsonCarrierFailure(
                "invalid-scalar",
                "a Json object member name is excluded from managed membership",
            )
        if not isinstance(name, str):
            raise JsonCarrierFailure("member-name-type", "a Json object member name is not text")
        normalized_name = str.__str__(name)
        if not _is_utf8_encodable(normalized_name):
            raise JsonCarrierFailure(
                "member-name-unicode",
                "a Json object member name has no UTF-8 encoding",
            )
        if normalized_name in names:
            raise JsonCarrierFailure(
                "member-name-collision",
                "Json object member names collide after normalization",
            )
        names.add(normalized_name)
        normalized.append((normalized_name, member))
    return normalized


def _assign_json_value(
    parent: _JsonContainer,
    location: _JsonLocation,
    value: object,
) -> None:
    if isinstance(parent, list):
        parent[cast("int", location)] = value
    else:
        parent[cast("str", location)] = value


def base_list_carrier(value: list[object]) -> list[object]:
    copy_list = cast("_Callable[[list[object]], list[object]]", vars(list)["copy"])
    return copy_list(value)


def base_dict_carrier(value: dict[object, object]) -> dict[object, object]:
    copy_dict = cast(
        "_Callable[[dict[object, object]], dict[object, object]]",
        vars(dict)["copy"],
    )
    return copy_dict(value)


def base_time_carrier(value: _dt.time) -> _dt.time:
    combined = _dt.datetime.combine(_dt.date.min, value)
    return _dt.datetime.timetz(combined)


def base_datetime_carrier(value: _dt.datetime) -> _dt.datetime:
    return _dt.datetime.combine(_dt.datetime.date(value), _dt.datetime.timetz(value))


def base_uuid_carrier(value: _uuid.UUID) -> _uuid.UUID | None:
    try:
        get_integer = cast(
            "_Callable[[_uuid.UUID, type[_uuid.UUID]], object]",
            vars(_uuid.UUID)["int"].__get__,
        )
        integer_value: object = get_integer(value, _uuid.UUID)
    except AttributeError:
        namespace = _base_instance_namespace(value)
        if namespace is None or "int" not in namespace:
            return None
        integer_value = namespace["int"]
    if not isinstance(integer_value, int) or isinstance(integer_value, bool):
        return None
    try:
        return _uuid.UUID(int=int.__int__(integer_value))
    except ValueError:
        return None


def _base_instance_namespace(value: object) -> dict[str, object] | None:
    type_namespace = cast("_Mapping[str, object]", vars(type))
    namespace_descriptor = type_namespace["__dict__"]
    get_descriptor = cast(
        "_Callable[[object, object, type[object]], object]",
        vars(type(namespace_descriptor))["__get__"],
    )
    for owner in type.mro(type(value)):
        owner_namespace = cast(
            "_Mapping[str, object]",
            get_descriptor(namespace_descriptor, owner, type),
        )
        descriptor = owner_namespace.get("__dict__")
        if type(descriptor) is not _types.GetSetDescriptorType:
            continue
        try:
            namespace = get_descriptor(descriptor, value, owner)
        except (AttributeError, TypeError):
            continue
        return cast("dict[str, object]", namespace) if type(namespace) is dict else None
    return None
