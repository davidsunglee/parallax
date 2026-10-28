"""m-core (`parallax.core.base`) neutral-type and instant-normalization tests."""

from __future__ import annotations

import datetime as dt
import decimal
import math
import random
import struct
import uuid
from collections.abc import Callable, Iterator, Mapping
from fractions import Fraction
from types import MappingProxyType
from typing import Any, cast

import pytest

from parallax.core import base
from parallax.core.base._neutral import (
    ManagedValueExclusion,
    host_float_binary32,
    host_float_number,
    is_decimal_member,
    is_integer_member,
    is_string_member,
    utc_instant,
)
from tests._support.binary32 import rounded_once, rounding_witnesses


class _MutableTuple(tuple[object, ...]):
    items: list[object]

    def __new__(cls, values: tuple[object, ...]) -> _MutableTuple:
        value = super().__new__(cls, values)
        value.items = list(values)
        return value

    def __iter__(self) -> Iterator[object]:
        return iter(self.items)


def test_a_native_carrier_infers_the_widest_neutral_type_of_its_exact_type() -> None:
    assert base.infer_neutral_type(int) == base.Int64()
    assert base.infer_neutral_type(dt.date) == base.Date()
    # A `datetime` is a `date` subclass but a distinct value space, so the
    # mapping is read by exact type rather than by subclass.
    assert base.infer_neutral_type(dt.datetime) == base.Timestamp()


@pytest.mark.parametrize(
    "annotation",
    [decimal.Decimal, dict[str, int], tuple[int, ...], "int", None],
    ids=["decimal", "generic-mapping", "generic-tuple", "text", "none"],
)
def test_inference_answers_absence_for_anything_outside_the_carrier_mapping(
    annotation: object,
) -> None:
    # Error-neutral by design, whether the argument is an unmapped type
    # (`Decimal`, whose parameters are a declaration fact) or no type at all: a
    # parameterized generic is not a `type`, and neither is a name or `None`.
    assert base.infer_neutral_type(annotation) is None


def test_infinity_is_the_native_upper_bound_sentinel() -> None:
    assert base.INFINITY is base.TemporalBound.INFINITY
    assert base.INFINITY.value == base.INFINITY_LITERAL == "infinity"


def test_document_values_are_finite_portable_json_trees() -> None:
    assert base.is_document_value({"ratio": 1.5, "items": [True, None]})
    assert base.is_document_value(base.FrozenMap({"ratio": 1.5, "items": (True, None)}))
    assert not base.is_document_value(float("nan"))
    assert not base.is_document_value(MappingProxyType({"ratio": 1.5}))
    assert not base.is_document_value(object())


def test_document_membership_rejects_container_subclasses() -> None:
    assert not base.is_document_value(type("DictSubclass", (dict,), {})({"value": 1}))
    assert not base.is_document_value(type("ListSubclass", (list,), {})([1]))
    assert not base.is_document_value(_MutableTuple((1,)))


def test_document_retention_owns_mutable_descendants_and_reuses_safe_subtrees() -> None:
    safe = base.FrozenMap({"city": "Oslo"})
    nested = {"safe": safe, "items": ({"name": "Ada"},)}
    retained = cast("base.FrozenMap[str, object]", base.retain_document_value(nested))

    cast("dict[str, object]", cast("tuple[object, ...]", nested["items"])[0])["name"] = "Bo"

    assert retained == {"safe": {"city": "Oslo"}, "items": ({"name": "Ada"},)}
    assert retained["safe"] is safe
    assert base.retain_document_value(safe) is safe
    with pytest.raises(TypeError):
        cast("dict[str, object]", retained)["safe"] = {}
    with pytest.raises(TypeError):
        cast("dict[str, object]", cast("tuple[object, ...]", retained["items"])[0])["name"] = "Bo"


def test_document_retention_copies_a_tuple_subclass_even_when_its_descendants_are_safe() -> None:
    source = _MutableTuple((base.FrozenMap({"city": "Oslo"}),))

    retained = base.retain_document_value(source)
    source.items[0] = base.FrozenMap({"city": "Bergen"})

    assert type(retained) is tuple
    assert retained == ({"city": "Oslo"},)


def test_a_proxy_is_retained_as_owned_storage_not_trusted_by_its_wrapper() -> None:
    backing = {"nested": {"city": "Oslo"}}
    proxy = MappingProxyType(backing)
    retained = base.retain_document_value(proxy)

    cast("dict[str, object]", backing["nested"])["city"] = "Bergen"

    assert retained == {"nested": {"city": "Oslo"}}
    assert retained is not proxy


def test_frozen_map_is_the_exact_owned_mapping_type() -> None:
    frozen = base.FrozenMap({"city": "Oslo"})
    name = "city"

    assert repr(frozen) == "FrozenMap({'city': 'Oslo'})"
    with pytest.raises(TypeError, match="immutable"):
        setattr(frozen, name, "Bergen")
    with pytest.raises(TypeError, match="immutable"):
        delattr(frozen, name)
    with pytest.raises(TypeError, match="does not support subclassing"):
        type("ExtendedFrozenMap", (base.FrozenMap,), {})
    with pytest.raises(TypeError, match="only the core FrozenMap"):
        base.frozen_map_json_backing(cast("base.FrozenMap[str, object]", object()))


def test_frozen_map_compares_unequal_to_a_non_mapping_without_recursing() -> None:
    assert base.FrozenMap({"city": "Oslo"}) != object()
    assert base.FrozenMap({"items": ()}) != {"items": object()}


def test_frozen_map_does_not_execute_arbitrary_mapping_equality() -> None:
    class MappingSubclass(dict[str, object]):
        def items(self):
            raise AssertionError("arbitrary mapping behavior was executed")

    assert base.FrozenMap({"city": "Oslo"}) != MappingSubclass(city="Oslo")


_MAPPING_MIXIN = Mapping[object, object]

_FROZEN_LOOKUP_SOURCE: dict[object, object] = {
    "city": "Oslo",
    "note": None,
    "terms": {"days": 30},
    None: "null-key",
    (1, 2): "tuple-key",
}


@pytest.mark.parametrize(
    "key",
    ["city", "note", "terms", None, (1, 2), "street", 3],
    ids=["hit", "null-value", "nested", "none-key", "tuple-key", "miss", "unknown-int"],
)
def test_frozen_map_lookup_answers_exactly_what_the_mapping_mixin_answers(key: object) -> None:
    frozen = base.FrozenMap(_FROZEN_LOOKUP_SOURCE)
    default = object()

    assert (key in frozen) is _MAPPING_MIXIN.__contains__(frozen, key)
    assert frozen.get(key) is _MAPPING_MIXIN.get(frozen, key)
    assert frozen.get(key, default) is _MAPPING_MIXIN.get(frozen, key, default)
    assert frozen.get(key, None) is _MAPPING_MIXIN.get(frozen, key, None)
    if key in _FROZEN_LOOKUP_SOURCE:
        assert key in frozen
        assert frozen.get(key, default) is frozen[key]
    else:
        assert key not in frozen
        assert frozen.get(key) is None
        assert frozen.get(key, default) is default


def test_frozen_map_lookup_keeps_a_stored_null_apart_from_a_missing_key() -> None:
    frozen = base.FrozenMap({"note": None})
    default = object()

    assert "note" in frozen
    assert frozen.get("note", default) is None
    assert "street" not in frozen
    assert frozen.get("street", default) is default


def test_frozen_map_lookup_refuses_an_unhashable_key_as_the_mixin_does() -> None:
    frozen = cast("base.FrozenMap[object, object]", base.FrozenMap({"city": "Oslo"}))
    unhashable: object = ["city"]

    with pytest.raises(TypeError, match="unhashable"):
        _MAPPING_MIXIN.get(frozen, unhashable)
    with pytest.raises(TypeError, match="unhashable"):
        frozen.get(unhashable)
    with pytest.raises(TypeError, match="unhashable"):
        _MAPPING_MIXIN.__contains__(frozen, unhashable)
    with pytest.raises(TypeError, match="unhashable"):
        frozen.__contains__(unhashable)


class _HashRaisesKeyError:
    def __hash__(self) -> int:
        raise KeyError("hash")


class _EqRaisesKeyError:
    def __hash__(self) -> int:
        return hash("city")

    def __eq__(self, other: object) -> bool:
        raise KeyError("eq")


class _HashRaisesValueError:
    def __hash__(self) -> int:
        raise ValueError("hash")


@pytest.mark.parametrize(
    "key",
    [_HashRaisesKeyError(), _EqRaisesKeyError()],
    ids=["hash-raises-key-error", "colliding-eq-raises-key-error"],
)
def test_frozen_map_lookup_swallows_a_key_error_from_the_key_as_the_mixin_does(
    key: object,
) -> None:
    frozen = cast("base.FrozenMap[object, object]", base.FrozenMap({"city": "Oslo"}))
    default = object()

    assert _MAPPING_MIXIN.__contains__(frozen, key) is False
    assert (key in frozen) is False
    assert _MAPPING_MIXIN.get(frozen, key) is None
    assert frozen.get(key) is None
    assert _MAPPING_MIXIN.get(frozen, key, default) is default
    assert frozen.get(key, default) is default


def test_frozen_map_lookup_propagates_other_key_exceptions_as_the_mixin_does() -> None:
    frozen = cast("base.FrozenMap[object, object]", base.FrozenMap({"city": "Oslo"}))
    key = _HashRaisesValueError()

    with pytest.raises(ValueError, match="hash"):
        _MAPPING_MIXIN.get(frozen, key)
    with pytest.raises(ValueError, match="hash"):
        frozen.get(key)
    with pytest.raises(ValueError, match="hash"):
        _MAPPING_MIXIN.__contains__(frozen, key)
    with pytest.raises(ValueError, match="hash"):
        frozen.__contains__(key)


def test_frozen_map_equality_stays_unequal_when_a_colliding_key_raises_key_error() -> None:
    left = cast("base.FrozenMap[object, object]", base.FrozenMap({_EqRaisesKeyError(): 1}))
    right = cast("base.FrozenMap[object, object]", base.FrozenMap({"city": 1}))

    assert (left == right) is False
    assert (left != right) is True


def test_frozen_map_lookup_is_its_own_and_never_dispatches_through_getitem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = base.FrozenMap({"city": "Oslo"})
    retained = cast(
        "base.FrozenMap[str, object]", base.retain_document_value({"nested": {"city": "Oslo"}})
    )
    nested = retained["nested"]

    own = vars(base.FrozenMap)
    assert own["get"] is not _MAPPING_MIXIN.get
    assert own["__contains__"] is not _MAPPING_MIXIN.__contains__

    def refuse_indexing(self: object, key: object) -> object:
        raise AssertionError(f"lookup indexed the map for {key!r}")

    monkeypatch.setattr(base.FrozenMap, "__getitem__", refuse_indexing)

    assert "city" in frozen
    assert "street" not in frozen
    assert frozen.get("city") == "Oslo"
    assert frozen.get("street", "fallback") == "fallback"
    assert "nested" in retained
    assert retained.get("nested") is nested


def test_normalize_instant_converts_aware_to_utc_microsecond() -> None:
    eastern = dt.timezone(dt.timedelta(hours=-5))
    aware = dt.datetime(2026, 7, 12, 8, 30, 0, 123456, tzinfo=eastern)
    normalized = base.normalize_instant(aware)
    assert normalized.tzinfo is dt.UTC
    assert normalized == dt.datetime(2026, 7, 12, 13, 30, 0, 123456, tzinfo=dt.UTC)


def test_utc_instant_answers_a_utc_datetime_with_itself() -> None:
    instant = dt.datetime(2026, 7, 12, 13, 30, 0, 123456, tzinfo=dt.UTC)
    assert utc_instant(instant) is instant


class _InstantSubclass(dt.datetime):
    pass


@pytest.mark.parametrize(
    "aware",
    [
        dt.datetime(2026, 7, 12, 8, 30, 0, 123456, tzinfo=dt.timezone(dt.timedelta(hours=-5))),
        dt.datetime(2026, 7, 12, 13, 30, 0, 123456, tzinfo=dt.timezone(dt.timedelta(0), "UTC")),
        _InstantSubclass(2026, 7, 12, 13, 30, 0, 123456, tzinfo=dt.UTC),
    ],
    ids=["offset", "named-utc-zone", "subclass"],
)
def test_utc_instant_converts_any_other_aware_datetime_to_a_base_utc_value(
    aware: dt.datetime,
) -> None:
    instant = utc_instant(aware)
    assert type(instant) is dt.datetime
    assert instant.tzinfo is dt.UTC
    assert instant == dt.datetime(2026, 7, 12, 13, 30, 0, 123456, tzinfo=dt.UTC)


def test_normalize_instant_rejects_naive() -> None:
    with pytest.raises(base.InstantError):
        base.normalize_instant(dt.datetime(2026, 7, 12, 8, 30, 0))


class _UnusableOffset(dt.tzinfo):
    """A ``tzinfo`` answering an offset `datetime` arithmetic refuses.

    Constructible and attachable — the constructor asks a ``tzinfo`` for
    nothing — so a value carrying one reaches the boundary like any other.
    """

    def utcoffset(self, dt_: dt.datetime | None) -> dt.timedelta:
        return dt.timedelta(hours=25)

    def dst(self, dt_: dt.datetime | None) -> dt.timedelta | None:
        return None


@pytest.mark.parametrize(
    "unusable",
    [
        dt.datetime.min.replace(tzinfo=dt.timezone(dt.timedelta(hours=14))),
        dt.datetime.max.replace(tzinfo=dt.timezone(dt.timedelta(hours=-14))),
        dt.datetime(2026, 7, 12, tzinfo=_UnusableOffset()),
    ],
    ids=["min-east-of-utc", "max-west-of-utc", "offset-beyond-a-day"],
)
def test_normalize_instant_rejects_a_datetime_naming_no_instant(unusable: dt.datetime) -> None:
    # Each of these is a `datetime` that answers no UTC instant, and each fails
    # in its own primitive: the two edges overflow the conversion, while an
    # offset beyond a day is refused by the offset accessor before any
    # conversion runs. The boundary is total over `datetime`, so all three are
    # `timestamp` verdicts rather than arithmetic accidents reaching the caller.
    with pytest.raises(base.InstantError):
        base.normalize_instant(unusable)


def _binary32_at(bits: int) -> float:
    (value,) = struct.unpack("<f", struct.pack("<I", bits))
    return value


def _around_binary32_midpoints() -> list[float]:
    midpoints = [
        (_binary32_at(bits) + _binary32_at(bits + 1)) / 2
        for bits in (0x00000000, 0x00000002, 0x007FFFFF, 0x15AE43FD, 0x3F7FFFFF, 0x3F800000)
    ]
    midpoints.append(2.0**128 - 2.0**103)
    around: list[float] = []
    for midpoint in midpoints:
        below = above = midpoint
        for _ in range(2):
            below = math.nextafter(below, -math.inf)
            above = math.nextafter(above, math.inf)
            around += [below, above]
        around.append(midpoint)
    return around + [-value for value in around]


@pytest.mark.parametrize(
    "value",
    [
        7.038531e-26,
        -7.038531e-26,
        1.0000000596046448,
        1.000000059604644775390625,
        0.0,
        -0.0,
        3.4028234663852886e38,
        -3.4028234663852886e38,
        3.4028235677973366e38,
        1.7976931348623157e308,
        -1.7976931348623157e308,
        *_around_binary32_midpoints(),
    ],
)
def test_a_bare_float_names_at_float32_its_spelled_number_rounded_once(value: float) -> None:
    rounded_once = base.nearest_float_at_width(host_float_number(value), base.FLOAT32)
    assert repr(host_float_binary32(value)) == repr(rounded_once)


_BINARY32_OVERFLOW = 2**128 - 2**103
_LARGEST_BINARY32 = 3.4028234663852886e38


def _is_positive_zero_or_nonzero(value: float) -> bool:
    return value != 0.0 or math.copysign(1.0, value) == 1.0


def test_a_spelling_names_the_binary32_its_exact_decimal_rounds_to_once() -> None:
    witnesses = rounding_witnesses()
    named = [base.nearest_binary32_of_spelling(spelling) for spelling in witnesses]

    assert named == [rounded_once(spelling) for spelling in witnesses]
    assert all(value is not None and _is_positive_zero_or_nonzero(value) for value in named)


@pytest.mark.parametrize(
    ("spelling", "expected"),
    [
        (str(_BINARY32_OVERFLOW - 1), _LARGEST_BINARY32),
        (f"-{_BINARY32_OVERFLOW - 1}", -_LARGEST_BINARY32),
        (str(_BINARY32_OVERFLOW), None),
        (f"-{_BINARY32_OVERFLOW}", None),
        ("3.4028236e38", None),
        ("1e39", None),
        ("1e400", None),
        ("-1e400", None),
        ("inf", None),
        ("-Infinity", None),
        ("nan", None),
    ],
)
def test_a_spelling_past_the_largest_binary32_or_not_finite_names_none(
    spelling: str, expected: float | None
) -> None:
    assert base.nearest_binary32_of_spelling(spelling) == expected


@pytest.mark.parametrize("spelling", ["0", "-0", "-0.0", "-1e-46", "-1e-50", "-1e-400", "1e-400"])
def test_a_spelling_naming_a_binary32_zero_names_positive_zero(spelling: str) -> None:
    assert repr(base.nearest_binary32_of_spelling(spelling)) == "0.0"


def _binary64_at(bits: int) -> float:
    (value,) = struct.unpack("<d", struct.pack("<Q", bits))
    return value


def _float_rounding_witnesses() -> list[float]:
    generator = random.Random(188)
    # Binary64 exponents from below the binary32 subnormals to past its overflow.
    near_binary32 = [
        _binary64_at(
            generator.getrandbits(1) << 63
            | (872 + generator.randrange(310)) << 52
            | generator.getrandbits(52)
        )
        for _ in range(1_000)
    ]
    anywhere = [_binary64_at(generator.getrandbits(64)) for _ in range(200)]
    corpus = [float(spelling) for spelling in rounding_witnesses()]
    return [
        *corpus,
        *near_binary32,
        *(value for value in anywhere if math.isfinite(value)),
        *_around_binary32_midpoints(),
    ]


def _exactly_rounded(value: float) -> float | None:
    if abs(Fraction(value)) >= _BINARY32_OVERFLOW:
        return None
    return rounded_once(str(decimal.Decimal(value)))


def test_a_host_float_rounds_once_to_the_nearest_binary32() -> None:
    values = _float_rounding_witnesses()
    rounded = [base.nearest_float_at_width(value, base.FLOAT32) for value in values]

    assert rounded == [_exactly_rounded(value) for value in values]
    assert all(value is None or _is_positive_zero_or_nonzero(value) for value in rounded)


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_a_nonfinite_host_float_has_no_nearest_binary32(value: float) -> None:
    assert base.nearest_float_at_width(value, base.FLOAT32) is None


def test_an_excluded_host_float_has_no_nearest_float() -> None:
    class ExcludedFloat(float, ManagedValueExclusion):
        pass

    for declared in (base.FLOAT32, base.FLOAT64):
        assert base.nearest_float_at_width(ExcludedFloat(1.5), declared) is None


def test_float32_membership_admits_exactly_the_finite_binary32_values() -> None:
    members = [rounded_once(spelling) for spelling in rounding_witnesses()]
    neighbours = [
        math.nextafter(member, direction)
        for member in members
        for direction in (-math.inf, math.inf)
    ]

    assert all(base.matches_neutral_type(member, base.FLOAT32) for member in members)
    assert not any(base.matches_neutral_type(value, base.FLOAT32) for value in neighbours)


@pytest.mark.parametrize(
    ("value", "member"),
    [
        (-0.0, True),
        (_LARGEST_BINARY32, True),
        (-_LARGEST_BINARY32, True),
        (float(_BINARY32_OVERFLOW), False),
        (-float(_BINARY32_OVERFLOW), False),
        (1e39, False),
        (1.7976931348623157e308, False),
        (math.inf, False),
        (-math.inf, False),
        (math.nan, False),
    ],
)
def test_float32_membership_refuses_every_value_past_the_finite_binary32_range(
    value: float, member: bool
) -> None:
    assert base.matches_neutral_type(value, base.FLOAT32) is member


def test_a_typed_float32_input_names_its_spelled_number_rounded_once() -> None:
    hosts = [float(spelling) for spelling in rounding_witnesses()]
    coerced = [base.coerce_neutral_input(host, base.FLOAT32) for host in hosts]

    assert coerced == [rounded_once(repr(host)) for host in hosts]
    assert all(base.matches_neutral_type(value, base.FLOAT32) for value in coerced)
    assert all(_is_positive_zero_or_nonzero(cast("float", value)) for value in coerced)


class _Count(int):
    pass


class _Instant(dt.datetime):
    pass


class _ExcludedCount(int, ManagedValueExclusion):
    pass


class _ExcludedText(str, ManagedValueExclusion):
    pass


_EVERY_TYPE: tuple[base.NeutralType, ...] = (
    base.BOOLEAN,
    base.INT32,
    base.INT64,
    base.FLOAT32,
    base.FLOAT64,
    base.Decimal(6, 2),
    base.STRING,
    base.BYTES,
    base.DATE,
    base.TIME,
    base.TIMESTAMP,
    base.UUID,
    base.JSON,
)
_UUID_TEXT = "123e4567-e89b-12d3-a456-426614174000"
_CANDIDATES: tuple[object, ...] = (
    None,
    True,
    0,
    1,
    -(2**31) - 1,
    2**31,
    2**40,
    2**53 + 1,
    2**63,
    2**24 + 1,
    _Count(7),
    1.5,
    0.1,
    -0.0,
    1e39,
    math.inf,
    math.nan,
    decimal.Decimal("1.50"),
    decimal.Decimal("1.234"),
    decimal.Decimal("12345.6"),
    decimal.Decimal("NaN"),
    "text",
    "\ud800",
    "1.50",
    _UUID_TEXT,
    _UUID_TEXT.upper(),
    b"raw",
    dt.date(2026, 1, 1),
    dt.datetime(2026, 1, 1),
    dt.datetime(2026, 1, 1, tzinfo=dt.timezone(dt.timedelta(hours=2))),
    _Instant(2026, 1, 1, tzinfo=dt.UTC),
    dt.time(12, 0),
    dt.time(12, 0, tzinfo=dt.UTC),
    uuid.UUID(_UUID_TEXT),
    {"a": [1, None]},
    [math.nan],
    _ExcludedCount(1),
    _ExcludedText(_UUID_TEXT),
)


@pytest.mark.parametrize("declared", _EVERY_TYPE, ids=repr)
def test_every_admissible_typed_input_is_a_carrier(declared: base.NeutralType) -> None:
    admitted = [
        candidate
        for candidate in _CANDIDATES
        if base.matches_neutral_type(base.coerce_neutral_input(candidate, declared), declared)
    ]

    assert admitted
    assert all(base.matches_typed_carrier(candidate, declared) for candidate in admitted)


@pytest.mark.parametrize(
    ("value", "declared", "carrier", "member"),
    [
        (2**40, base.INT32, True, False),
        (_Count(7), base.INT64, True, True),
        (True, base.INT64, False, False),
        (1.0, base.INT64, False, False),
        (1, base.BOOLEAN, False, False),
        (decimal.Decimal("1.234"), base.Decimal(6, 2), True, False),
        (decimal.Decimal("12345.6"), base.Decimal(6, 2), True, False),
        (decimal.Decimal("NaN"), base.Decimal(6, 2), True, False),
        (10**5, base.Decimal(6, 2), True, False),
        (1.5, base.Decimal(6, 2), False, False),
        ("1.50", base.Decimal(6, 2), False, False),
        (1e39, base.FLOAT32, True, False),
        (math.inf, base.FLOAT64, True, False),
        (2**24, base.FLOAT32, True, True),
        (2**24 + 1, base.FLOAT32, False, False),
        (2**53 + 1, base.FLOAT64, False, False),
        (2**2000, base.FLOAT64, False, False),
        ("1.5", base.FLOAT64, False, False),
        ("\ud800", base.STRING, True, False),
        (b"raw", base.STRING, False, False),
        ("raw", base.BYTES, False, False),
        (dt.datetime(2026, 1, 1), base.DATE, False, False),
        ("2026-01-01", base.DATE, False, False),
        (dt.time(12, 0, tzinfo=dt.UTC), base.TIME, True, False),
        (dt.datetime(2026, 1, 1), base.TIMESTAMP, True, False),
        (_Instant(2026, 1, 1, tzinfo=dt.UTC), base.TIMESTAMP, True, True),
        (dt.date(2026, 1, 1), base.TIMESTAMP, False, False),
        ("2026-01-01T00:00:00Z", base.TIMESTAMP, False, False),
        (_UUID_TEXT, base.UUID, True, True),
        (_UUID_TEXT.upper(), base.UUID, False, False),
        (_UUID_TEXT.replace("-", ""), base.UUID, False, False),
        (uuid.UUID(_UUID_TEXT).int, base.UUID, False, False),
        ([math.nan], base.JSON, True, False),
        (None, base.JSON, False, False),
        (None, base.INT64, False, False),
        (_ExcludedCount(1), base.INT64, False, False),
        (_ExcludedText(_UUID_TEXT), base.UUID, False, False),
        (_ExcludedText("text"), base.STRING, False, False),
    ],
)
def test_the_carrier_policy_refuses_only_what_pydantic_would_convert(
    value: object, declared: base.NeutralType, carrier: bool, member: bool
) -> None:
    coerced = base.coerce_neutral_input(value, declared)

    assert base.matches_typed_carrier(value, declared) is carrier
    assert base.matches_neutral_type(coerced, declared) is member


def test_an_unknown_variant_has_no_carrier_member_or_input_form() -> None:
    unknown = cast("base.NeutralType", object())

    assert base.matches_typed_carrier(1, unknown) is False
    assert base.matches_neutral_type(1, unknown) is False
    assert base.coerce_neutral_input(1, unknown) == 1


@pytest.mark.parametrize(
    ("rule", "declared"),
    [
        (is_integer_member, base.INT32),
        (is_integer_member, base.INT64),
        (is_decimal_member, base.Decimal(6, 2)),
        (is_decimal_member, base.Decimal(1, 0)),
        (is_string_member, base.STRING),
    ],
    ids=["int32", "int64", "decimal-6-2", "decimal-1-0", "string"],
)
def test_a_shared_membership_rule_is_the_judgment_membership_applies(
    rule: Callable[[object, Any], bool], declared: base.NeutralType
) -> None:
    ordinary = [
        candidate for candidate in _CANDIDATES if not isinstance(candidate, ManagedValueExclusion)
    ]

    assert [rule(candidate, declared) for candidate in ordinary] == [
        base.matches_neutral_type(candidate, declared) for candidate in ordinary
    ]


def _general_typed_conversion(value: object, declared: base.NeutralType) -> tuple[bool, object]:
    managed = base.coerce_neutral_input(value, declared)
    return base.matches_neutral_type(managed, declared), base.retain_document_value(managed)


@pytest.mark.parametrize("declared", _EVERY_TYPE, ids=repr)
def test_a_typed_converter_answers_coercion_then_membership_as_one_call(
    declared: base.NeutralType,
) -> None:
    convert = base.typed_converter(declared)
    for candidate in (*_CANDIDATES, _Instant(2026, 1, 1, tzinfo=dt.timezone.min)):
        member, managed = _general_typed_conversion(candidate, declared)
        if member:
            converted = convert(candidate)
            assert converted == managed
            # Owned Json content keeps each scalar in its built-in carrier.
            assert type(converted) is type(managed) or declared == base.JSON
        else:
            with pytest.raises(base.NeutralTypeMismatch) as refused:
                convert(candidate)
            assert refused.value.declared == declared
            assert repr(refused.value.managed) == repr(managed)


def test_a_typed_float32_converter_names_the_spelled_number_rounded_once() -> None:
    convert = base.typed_converter(base.FLOAT32)
    hosts = [float(spelling) for spelling in rounding_witnesses()]

    assert [convert(host) for host in hosts] == [rounded_once(repr(host)) for host in hosts]


def test_a_typed_timestamp_converter_finds_the_utc_instant_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from parallax.core.base import _neutral

    calls: list[dt.datetime] = []

    def counted(value: dt.datetime) -> dt.datetime | None:
        calls.append(value)
        return utc_instant(value)

    monkeypatch.setattr(_neutral, "utc_instant", counted)
    east = dt.datetime(2026, 1, 1, 2, tzinfo=dt.timezone(dt.timedelta(hours=2)))

    assert base.typed_converter(base.TIMESTAMP)(east) == dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    assert calls == [east]


def test_a_typed_json_converter_owns_its_containers_in_the_judging_walk() -> None:
    source: dict[str, object] = {"a": [1, {"b": None}], "c": "text"}

    converted = base.typed_converter(base.JSON)(source)

    assert converted == base.retain_document_value(source)
    assert type(converted) is base.FrozenMap
    owned = cast("Mapping[str, object]", converted)
    assert type(owned["a"]) is tuple
    assert type(cast("tuple[object, ...]", owned["a"])[1]) is base.FrozenMap
    cast("list[object]", source["a"]).append(2)
    assert owned["a"] == (1, base.FrozenMap({"b": None}))
