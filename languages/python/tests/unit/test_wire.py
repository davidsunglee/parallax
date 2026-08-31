"""Strict JSON loading and exhaustive Neutral Wire Codec laws."""

from __future__ import annotations

import datetime as dt
import decimal
import json
import math
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
)

_TOKEN = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
_INSTANT = dt.datetime(2026, 1, 15, 9, 30, tzinfo=dt.UTC)

_CANONICAL: tuple[tuple[NeutralType, ManagedValue, object], ...] = (
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


def _through_source(value: object) -> object:
    return wire.loads(json.dumps(value, separators=(",", ":")))


@pytest.mark.parametrize(
    ("neutral_type", "managed", "canonical"),
    _CANONICAL,
    ids=[str(row[0]) for row in _CANONICAL],
)
def test_every_type_obeys_the_canonical_inverse_law(
    neutral_type: NeutralType,
    managed: ManagedValue,
    canonical: object,
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
        (TIME, '"24:00:00"', "out-of-space"),
        (TIMESTAMP, "42", "type-mismatch"),
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


def test_json_accepts_structural_mappings_and_rejects_non_json_content() -> None:
    class View(Mapping[str, object]):
        def __getitem__(self, key: str) -> object:
            return {"x": 1}[key]

        def __iter__(self) -> Iterator[str]:
            return iter(("x",))

        def __len__(self) -> int:
            return 1

    assert wire.decode_wire(JSON, View()) == {"x": 1}
    with pytest.raises(wire.WireDecodingError) as exc_info:
        wire.decode_wire(JSON, cast("object", {1: "not a JSON object"}))
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
