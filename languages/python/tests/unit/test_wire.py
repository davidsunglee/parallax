"""Strict JSON loading and exhaustive Neutral Wire Codec laws."""

from __future__ import annotations

import datetime as dt
import decimal
import json
import math
import sys
import uuid
from collections.abc import Iterator, Mapping
from typing import cast

import pytest

import parallax.core.wire as wire
from parallax.core.base import (
    BOOLEAN,
    BYTES,
    DATE,
    FLOAT32,
    FLOAT64,
    INT32,
    INT64,
    JSON,
    STRING,
    TIME,
    TIMESTAMP,
    UUID,
    Decimal,
    ManagedValue,
    NeutralType,
    matches_neutral_type,
)
from parallax.core.base._neutral import ManagedValueExclusion

_TOKEN = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
_INSTANT = dt.datetime(2026, 1, 15, 9, 30, tzinfo=dt.UTC)

_CANONICAL: tuple[tuple[NeutralType, ManagedValue, wire.WireValue], ...] = (
    (BOOLEAN, True, True),
    (INT32, -7, -7),
    (INT64, 2**40, 2**40),
    (FLOAT32, 1048576.25, 1048576.2),
    (FLOAT64, 562949953421312.25, 562949953421312.2),
    (Decimal(12, 2), decimal.Decimal("1.50"), "1.50"),
    (STRING, "alpha", "alpha"),
    (BYTES, b"\x0a\x1b", "0a1b"),
    (DATE, dt.date(2026, 1, 15), "2026-01-15"),
    (TIME, dt.time(9, 30), "09:30:00"),
    (TIMESTAMP, _INSTANT, "2026-01-15T09:30:00.000000Z"),
    (UUID, _TOKEN, "123e4567-e89b-12d3-a456-426614174000"),
    (JSON, {"free": [1, None, 1.5]}, {"free": [1, None, 1.5]}),
)


def _through_source(value: wire.WireValue) -> wire.WireValue:
    return wire.loads(json.dumps(value, separators=(",", ":")))


@pytest.mark.parametrize(
    ("neutral_type", "managed", "canonical"),
    _CANONICAL,
    ids=[str(row[0]) for row in _CANONICAL],
)
def test_every_type_obeys_the_canonical_inverse_law(
    neutral_type: NeutralType,
    managed: ManagedValue,
    canonical: wire.WireValue,
) -> None:
    assert wire.encode_wire(neutral_type, managed) == canonical
    written = _through_source(canonical)
    assert wire.decode_canonical_wire(neutral_type, written) == managed
    assert wire.decode_wire(neutral_type, written) == managed


@pytest.mark.parametrize(
    ("neutral_type", "authored", "managed", "canonical"),
    [
        (FLOAT32, "1.0000000596046448", 1.0 + 2.0**-23, 1.0000001),
        (FLOAT64, "0.10000000000000001", 0.1, 0.1),
        (TIME, '"09:30:00.000"', dt.time(9, 30), "09:30:00"),
        (TIME, '"09:30:00.123"', dt.time(9, 30, 0, 123000), "09:30:00.123000"),
        (
            TIMESTAMP,
            '"2026-01-15T09:30:00Z"',
            _INSTANT,
            "2026-01-15T09:30:00.000000Z",
        ),
        (
            TIMESTAMP,
            '"2026-01-15T09:30:00.123Z"',
            dt.datetime(2026, 1, 15, 9, 30, 0, 123000, tzinfo=dt.UTC),
            "2026-01-15T09:30:00.123000Z",
        ),
    ],
)
def test_admitted_alternatives_normalize_to_canonical_output(
    neutral_type: NeutralType,
    authored: str,
    managed: ManagedValue,
    canonical: object,
) -> None:
    written = wire.loads(authored)
    decoded = wire.decode_wire(neutral_type, written)
    assert decoded == managed
    assert wire.encode_wire(neutral_type, decoded) == canonical
    with pytest.raises(wire.WireDecodingError) as exc_info:
        wire.decode_canonical_wire(neutral_type, written)
    assert exc_info.value.reason == "noncanonical"


@pytest.mark.parametrize(
    ("neutral_type", "written", "reason"),
    [
        (BOOLEAN, '"true"', "type-mismatch"),
        (INT32, "1.5", "type-mismatch"),
        (INT32, "2147483648", "out-of-space"),
        (INT64, '"1"', "type-mismatch"),
        (INT64, "9223372036854775808", "out-of-space"),
        (FLOAT32, '"1.0"', "type-mismatch"),
        (FLOAT32, "1e39", "out-of-space"),
        (FLOAT64, '"1.0"', "type-mismatch"),
        (FLOAT64, "1e309", "out-of-space"),
        (Decimal(4, 2), "10.25", "type-mismatch"),
        (Decimal(4, 2), '"10.2"', "noncanonical"),
        (Decimal(4, 2), '"123.45"', "out-of-space"),
        (STRING, "42", "type-mismatch"),
        (BYTES, '"abc"', "type-mismatch"),
        (BYTES, '"0A1B"', "noncanonical"),
        (DATE, '"20260115"', "type-mismatch"),
        (DATE, '"2026-1-15"', "noncanonical"),
        (DATE, '"2026-02-30"', "out-of-space"),
        (TIME, "42", "type-mismatch"),
        (TIME, '"09:30"', "type-mismatch"),
        (TIME, '"09:30:00.1234560"', "type-mismatch"),
        (TIME, '"24:00:00"', "out-of-space"),
        (TIMESTAMP, "42", "type-mismatch"),
        (TIMESTAMP, '"2026-1-1T9:30:00Z"', "type-mismatch"),
        (TIMESTAMP, '"2026-01-01T09:30:00.1234560Z"', "type-mismatch"),
        (TIMESTAMP, '"2026-01-15T09:30:00+00:00"', "noncanonical"),
        (TIMESTAMP, '"2026-02-30T09:30:00Z"', "out-of-space"),
        (UUID, "42", "type-mismatch"),
        (UUID, '"123E4567-E89B-12D3-A456-426614174000"', "noncanonical"),
        (JSON, "null", "type-mismatch"),
        (JSON, "1e309", "out-of-space"),
    ],
)
def test_each_codec_failure_retains_its_classification(
    neutral_type: NeutralType,
    written: str,
    reason: wire.WireDecodingReason,
) -> None:
    with pytest.raises(wire.WireDecodingError) as exc_info:
        wire.decode_wire(neutral_type, wire.loads(written))
    assert exc_info.value.reason == reason


def test_float_zero_normalizes_positive_and_canonical_decoding_observes_source_sign() -> None:
    for neutral_type in (FLOAT32, FLOAT64):
        decoded = wire.decode_wire(neutral_type, wire.loads("-0.0"))
        assert decoded == 0.0
        assert math.copysign(1.0, cast("float", decoded)) == 1.0
        assert wire.encode_wire(neutral_type, decoded) == 0.0
        with pytest.raises(wire.WireDecodingError) as exc_info:
            wire.decode_canonical_wire(neutral_type, wire.loads("-0.0"))
        assert exc_info.value.reason == "noncanonical"


def test_integral_number_forms_decode_from_their_exact_authored_value() -> None:
    assert wire.decode_wire(INT32, wire.loads("1")) == 1
    assert wire.decode_wire(INT32, wire.loads("1.0")) == 1
    assert wire.decode_wire(INT32, wire.loads("1e0")) == 1
    assert wire.decode_wire(INT64, wire.loads("9007199254740993.0")) == 9007199254740993
    assert wire.decode_canonical_wire(INT64, wire.loads("9007199254740993.0")) == 9007199254740993


def test_out_of_space_authored_numbers_are_not_scalar_or_json_members() -> None:
    limit = sys.get_int_max_str_digits()
    if limit == 0:
        pytest.skip("the interpreter has no integer string-conversion limit")
    for source, scalar_types in (
        ("9" * (limit + 1), (INT32, INT64)),
        ("1e9999", (FLOAT32, FLOAT64)),
    ):
        loaded = wire.loads(source)
        json.loads(json.dumps(loaded))
        for neutral_type in scalar_types:
            assert matches_neutral_type(loaded, neutral_type) is False
            with pytest.raises(wire.WireDecodingError) as scalar_decoding:
                wire.decode_wire(neutral_type, loaded)
            assert scalar_decoding.value.reason == "out-of-space"
            with pytest.raises(wire.WireEncodingError):
                wire.encode_wire(neutral_type, cast("ManagedValue", loaded))
        for candidate in (loaded, [loaded], {"value": loaded}):
            assert matches_neutral_type(candidate, JSON) is False
            with pytest.raises(wire.WireDecodingError) as decoding:
                wire.decode_wire(JSON, cast("wire.WireValue", candidate))
            assert decoding.value.reason == "out-of-space"
            with pytest.raises(wire.WireEncodingError):
                wire.encode_wire(JSON, cast("ManagedValue", candidate))


def test_decimal_zero_encodes_at_declared_scale_without_rescaling_its_exponent() -> None:
    neutral_type = Decimal(4, 2)
    assert wire.encode_wire(neutral_type, decimal.Decimal("0.000")) == "0.00"
    assert wire.encode_wire(neutral_type, decimal.Decimal("0E+1000000000")) == "0.00"
    assert wire.encode_wire(neutral_type, decimal.Decimal("-0E+1000000000")) == "0.00"


def test_decimal_encoding_normalizes_trailing_coefficient_zeros_before_scaling() -> None:
    neutral_type = Decimal(4, 2)
    for managed, canonical in (
        (decimal.Decimal("1.500"), "1.50"),
        (decimal.Decimal("-1.500"), "-1.50"),
    ):
        assert wire.encode_wire(neutral_type, managed) == canonical
        assert wire.decode_canonical_wire(neutral_type, canonical) == managed


def test_decimal_encoding_does_not_cross_the_host_integer_string_limit() -> None:
    limit = sys.get_int_max_str_digits()
    if limit == 0:
        pytest.skip("the interpreter has no integer string-conversion limit")
    digits = (1,) * (limit + 1)
    managed = decimal.Decimal((0, digits, 0))
    neutral_type = Decimal(len(digits), 0)

    encoded = wire.encode_wire(neutral_type, managed)

    assert encoded == "1" * len(digits)
    assert wire.decode_canonical_wire(neutral_type, encoded) == managed


def test_extreme_exponents_classify_without_expanding_the_represented_power() -> None:
    with pytest.raises(wire.WireDecodingError) as overflow:
        wire.decode_wire(FLOAT64, wire.loads("1e1000000000"))
    assert overflow.value.reason == "out-of-space"
    assert wire.decode_wire(FLOAT64, wire.loads("1e-1000000000")) == 0.0
    with pytest.raises(wire.WireDecodingError) as nested:
        wire.decode_wire(JSON, wire.loads('{"n":1e1000000000}'))
    assert nested.value.reason == "out-of-space"


def test_json_normalization_is_fresh_recursive_and_ordinary() -> None:
    source = wire.loads('{"whole":9007199254740993,"ratio":1.25,"nested":[null,{"x":2}]}')
    managed = wire.decode_wire(JSON, source)
    assert managed == {
        "whole": 9007199254740993,
        "ratio": 1.25,
        "nested": [None, {"x": 2}],
    }
    assert type(managed) is dict
    document = cast("dict[str, object]", managed)
    assert type(document["whole"]) is int
    assert type(document["ratio"]) is float
    assert type(document["nested"]) is list
    assert json.loads(json.dumps(managed)) == managed
    assert wire.encode_wire(JSON, managed) == managed
    assert wire.encode_wire(JSON, managed) is not managed


def test_encoding_erases_private_and_programmatic_scalar_subclasses() -> None:
    class Text(str):
        pass

    authored_integer = wire.loads("1")
    encoded_integer = wire.encode_wire(INT64, cast("ManagedValue", authored_integer))
    encoded_text = wire.encode_wire(STRING, Text("value"))
    encoded_json = wire.encode_wire(JSON, {Text("key"): Text("value")})

    assert type(encoded_integer) is int
    assert type(encoded_text) is str
    assert type(encoded_json) is dict
    encoded_object = cast("dict[str, object]", encoded_json)
    [(key, member)] = encoded_object.items()
    assert type(key) is str
    assert type(member) is str


def test_encoding_reads_immutable_carrier_payloads_without_subclass_hooks() -> None:
    class Integer(int):
        def __int__(self) -> int:
            return 99

    class Text(str):
        def __str__(self) -> str:
            return "changed"

        def encode(self, *_args: object, **_kwargs: object) -> bytes:
            return b"changed"

    class BinaryFloat(float):
        def __format__(self, _format_spec: str) -> str:
            return "99"

        def __float__(self) -> float:
            return 99.0

    class FixedDecimal(decimal.Decimal):
        def as_tuple(self) -> decimal.DecimalTuple:
            return decimal.Decimal("9").as_tuple()

    class Octets(bytes):
        def hex(self, *_args: object, **_kwargs: object) -> str:
            return "changed"

    class CalendarDate(dt.date):
        def isoformat(self) -> str:
            return "changed"

    class WallTime(dt.time):
        def isoformat(self, *_args: object, **_kwargs: object) -> str:
            return "changed"

    class Instant(dt.datetime):
        def astimezone(self, tz: dt.tzinfo | None = None) -> dt.datetime:
            return dt.datetime(1999, 1, 1, tzinfo=dt.UTC)

        def strftime(self, format: str) -> str:
            return "changed"

    def uuid_int_getter(_value: uuid.UUID) -> int:
        return 1

    def uuid_int_setter(value: uuid.UUID, integer: int) -> None:
        vars(uuid.UUID)["int"].__set__(value, integer)

    def uuid_text(_value: uuid.UUID) -> str:
        return "changed"

    token_type = cast(
        "type[uuid.UUID]",
        type(
            "Token",
            (uuid.UUID,),
            {
                "__str__": uuid_text,
                "hex": property(uuid_text),
                "int": property(uuid_int_getter, uuid_int_setter),
            },
        ),
    )

    assert wire.encode_wire(INT64, Integer(1)) == 1
    assert wire.encode_wire(STRING, Text("value")) == "value"
    assert wire.encode_wire(FLOAT64, BinaryFloat(2.0)) == 2.0
    assert wire.encode_wire(Decimal(1, 0), FixedDecimal("1")) == "1"
    assert wire.encode_wire(BYTES, Octets(b"a")) == "61"
    assert wire.encode_wire(DATE, CalendarDate(2026, 1, 1)) == "2026-01-01"
    assert wire.encode_wire(TIME, WallTime(1)) == "01:00:00"
    assert (
        wire.encode_wire(TIMESTAMP, Instant(2026, 1, 1, tzinfo=dt.UTC))
        == "2026-01-01T00:00:00.000000Z"
    )
    assert wire.encode_wire(UUID, token_type(int=0)) == "00000000-0000-0000-0000-000000000000"


def test_encoding_rejects_exclusions_before_extracting_builtin_carriers() -> None:
    class ExcludedDecimal(decimal.Decimal, ManagedValueExclusion):
        pass

    class ExcludedText(str, ManagedValueExclusion):
        pass

    class ExcludedOctets(bytes, ManagedValueExclusion):
        pass

    class ExcludedDate(dt.date, ManagedValueExclusion):
        pass

    class ExcludedTime(dt.time, ManagedValueExclusion):
        pass

    class ExcludedInstant(dt.datetime, ManagedValueExclusion):
        pass

    class ExcludedUuid(uuid.UUID, ManagedValueExclusion):
        pass

    values = (
        (Decimal(2, 1), ExcludedDecimal("1.5")),
        (STRING, ExcludedText("value")),
        (BYTES, ExcludedOctets(b"a")),
        (DATE, ExcludedDate(2026, 1, 1)),
        (TIME, ExcludedTime(1)),
        (TIMESTAMP, ExcludedInstant(2026, 1, 1, tzinfo=dt.UTC)),
        (UUID, ExcludedUuid(int=0)),
    )

    for neutral_type, value in values:
        assert matches_neutral_type(value, neutral_type) is False
        with pytest.raises(wire.WireEncodingError):
            wire.encode_wire(neutral_type, cast("ManagedValue", value))


def test_decoding_rejects_unknown_exclusions_before_normalizing_their_payload() -> None:
    class ExcludedText(str, ManagedValueExclusion):
        pass

    for neutral_type, value in (
        (UUID, ExcludedText("123e4567-e89b-12d3-a456-426614174000")),
        (TIMESTAMP, ExcludedText("2026-01-01T00:00:00Z")),
    ):
        with pytest.raises(wire.WireDecodingError) as decoding:
            wire.decode_wire(neutral_type, cast("wire.WireValue", value))
        assert decoding.value.reason == "type-mismatch"


def test_uuid_subclass_nondata_descriptor_storage_remains_encodable() -> None:
    def shadowed_int(_value: uuid.UUID) -> int:
        return 1

    method_type = cast(
        "type[uuid.UUID]",
        type("Method", (uuid.UUID,), {"int": shadowed_int}),
    )
    value = method_type(int=0)

    assert matches_neutral_type(value, UUID) is True
    assert wire.encode_wire(UUID, value) == "00000000-0000-0000-0000-000000000000"


def test_uuid_subclass_data_descriptor_cannot_forge_fallback_storage() -> None:
    def shadowed_int(_value: uuid.UUID) -> int:
        return 1

    method_type = cast(
        "type[uuid.UUID]",
        type("Method", (uuid.UUID,), {"int": shadowed_int}),
    )
    token_type = cast(
        "type[uuid.UUID]",
        type(
            "Token",
            (method_type,),
            {"__dict__": property(lambda _value: {"int": 1})},
        ),
    )
    value = token_type(int=0)

    assert matches_neutral_type(value, UUID) is True
    assert wire.encode_wire(UUID, value) == "00000000-0000-0000-0000-000000000000"


def test_json_normalization_reads_builtin_container_payloads_without_subclass_hooks() -> None:
    class Text(str):
        def __str__(self) -> str:
            return "changed"

    class Items(list[object]):
        def __iter__(self) -> Iterator[object]:
            return iter(("changed",))

    class Object(dict[str, object]):
        pass

    value = Object({Text("key"): Items([Text("value")])})

    assert wire.decode_wire(JSON, cast("wire.WireValue", value)) == {"key": ["value"]}
    assert wire.encode_wire(JSON, cast("ManagedValue", value)) == {"key": ["value"]}


def test_json_rejects_excluded_scalars_containers_and_member_names() -> None:
    class ExcludedText(str, ManagedValueExclusion):
        pass

    class ExcludedList(list[object], ManagedValueExclusion):
        pass

    class ExcludedObject(dict[str, object], ManagedValueExclusion):
        pass

    candidates = (
        [ExcludedText("value")],
        [ExcludedList([1])],
        {"value": ExcludedObject({"nested": 1})},
        {ExcludedText("name"): 1},
    )

    for candidate in candidates:
        assert matches_neutral_type(candidate, JSON) is False
        with pytest.raises(wire.WireDecodingError) as decoding:
            wire.decode_wire(JSON, cast("wire.WireValue", candidate))
        assert decoding.value.reason == "type-mismatch"
        with pytest.raises(wire.WireEncodingError):
            wire.encode_wire(JSON, cast("ManagedValue", candidate))


def test_json_cycles_are_rejected_while_repeated_acyclic_containers_are_allowed() -> None:
    recursive_list: list[object] = []
    recursive_list.append(recursive_list)
    recursive_object: dict[str, object] = {}
    recursive_object["self"] = recursive_object

    for value in (recursive_list, recursive_object):
        assert matches_neutral_type(value, JSON) is False
        with pytest.raises(wire.WireDecodingError) as decoding:
            wire.decode_wire(JSON, cast("wire.WireValue", value))
        assert decoding.value.reason == "type-mismatch"
        with pytest.raises(wire.WireEncodingError):
            wire.encode_wire(JSON, cast("ManagedValue", value))

    shared = [1]
    repeated = [shared, shared]
    assert matches_neutral_type(repeated, JSON) is True
    assert wire.decode_wire(JSON, cast("wire.WireValue", repeated)) == [[1], [1]]
    assert wire.encode_wire(JSON, cast("ManagedValue", repeated)) == [[1], [1]]


@pytest.mark.parametrize("container", ["array", "object"])
def test_deep_acyclic_json_is_processed_without_python_recursion(container: str) -> None:
    depth = 1_200
    if container == "array":
        source = "[" * depth + "1" + "]" * depth
    else:
        source = '{"x":' * depth + "1" + "}" * depth
    loaded = wire.loads(source)

    assert matches_neutral_type(loaded, JSON) is True
    for normalized in (
        wire.decode_wire(JSON, loaded),
        wire.decode_canonical_wire(JSON, loaded),
        wire.encode_wire(JSON, cast("ManagedValue", loaded)),
    ):
        current: object = normalized
        for _ in range(depth):
            if container == "array":
                current = cast("list[object]", current)[0]
            else:
                current = cast("dict[str, object]", current)["x"]
        assert current == 1


def test_json_object_names_must_normalize_to_distinct_utf8_text() -> None:
    surrogate = {"\ud800": 1}
    with pytest.raises(wire.WireDecodingError) as decoding_surrogate:
        wire.decode_wire(JSON, cast("wire.WireValue", surrogate))
    assert decoding_surrogate.value.reason == "out-of-space"
    with pytest.raises(wire.WireEncodingError):
        wire.encode_wire(JSON, cast("ManagedValue", surrogate))

    class Key(str):
        __hash__ = object.__hash__

        def __eq__(self, other: object) -> bool:
            return self is other

    first = Key("x")
    second = Key("x")
    colliding = {first: 1, second: 2}
    assert len(colliding) == 2
    with pytest.raises(wire.WireDecodingError) as decoding_collision:
        wire.decode_wire(JSON, cast("wire.WireValue", colliding))
    assert decoding_collision.value.reason == "type-mismatch"
    with pytest.raises(wire.WireEncodingError):
        wire.encode_wire(JSON, cast("ManagedValue", colliding))


def test_programmatic_oversized_json_integers_are_outside_host_serialization_space() -> None:
    limit = sys.get_int_max_str_digits()
    if limit == 0:
        pytest.skip("the interpreter has no integer string-conversion limit")
    value = 10**limit

    for candidate in (value, [value], {"value": value}):
        assert matches_neutral_type(candidate, JSON) is False
        with pytest.raises(wire.WireEncodingError):
            wire.encode_wire(JSON, cast("ManagedValue", candidate))

    with pytest.raises(wire.WireDecodingError) as decoding:
        wire.decode_wire(JSON, cast("wire.WireValue", value))
    assert decoding.value.reason == "out-of-space"


def test_codec_errors_bound_large_integer_diagnostics_without_changing_exception_type() -> None:
    limit = sys.get_int_max_str_digits()
    if limit == 0:
        pytest.skip("the interpreter has no integer string-conversion limit")
    value = 10**limit

    with pytest.raises(wire.WireDecodingError) as decoding:
        wire.decode_wire(INT32, cast("wire.WireValue", value))
    assert decoding.value.reason == "out-of-space"
    assert len(str(decoding.value)) < 256
    with pytest.raises(wire.WireEncodingError) as encoding:
        wire.encode_wire(INT32, cast("ManagedValue", value))
    assert len(str(encoding.value)) < 256


def test_json_accepts_structural_mappings_and_rejects_non_json_content() -> None:
    class View(Mapping[str, wire.WireValue]):
        def __getitem__(self, key: str) -> wire.WireValue:
            return {"x": 1}[key]

        def __iter__(self) -> Iterator[str]:
            return iter(("x",))

        def __len__(self) -> int:
            return 1

    assert wire.decode_wire(JSON, View()) == {"x": 1}
    with pytest.raises(wire.WireDecodingError) as exc_info:
        wire.decode_wire(JSON, cast("wire.WireValue", {1: "not a JSON object"}))
    assert exc_info.value.reason == "type-mismatch"


@pytest.mark.parametrize("source", ["NaN", "Infinity", "-Infinity"])
def test_strict_loading_rejects_non_json_numeric_constants(source: str) -> None:
    with pytest.raises(json.JSONDecodeError, match="numeric constant"):
        wire.loads(source)


def test_strict_loading_rejects_duplicate_names_at_every_depth() -> None:
    for source in ('{"x":1,"x":2}', '{"outer":{"x":1,"x":2}}'):
        with pytest.raises(json.JSONDecodeError, match=r"duplicate.*x"):
            wire.loads(source)


@pytest.mark.parametrize(
    ("source", "expected"),
    [("null", None), ("true", True), ("42", 42), ('"x"', "x"), ("[1]", [1])],
)
def test_strict_loading_accepts_every_valid_json_root(source: str, expected: object) -> None:
    assert wire.loads(source) == expected
    assert wire.loads(source.encode()) == expected


def test_encoding_refuses_nonmembers_without_developer_coercion() -> None:
    with pytest.raises(wire.WireEncodingError):
        wire.encode_wire(FLOAT32, 1)
    with pytest.raises(wire.WireEncodingError):
        wire.encode_wire(Decimal(4, 2), 1)


def test_the_public_facade_contains_only_the_contractual_codec_surface() -> None:
    assert wire.__all__ == [
        "WireDecodingError",
        "WireDecodingReason",
        "WireEncodingError",
        "WireValue",
        "decode_canonical_wire",
        "decode_wire",
        "encode_wire",
        "loads",
    ]
