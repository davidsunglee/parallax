"""Independent admitted/canonical/encode oracle over the closed type table."""

from __future__ import annotations

import datetime as dt
import decimal
import math
import uuid

import pytest

from reference_harness import portable_literal as literal


@pytest.mark.parametrize(
    ("spelling", "authored", "managed", "canonical"),
    [
        ("boolean", True, True, True),
        ("int32", 7, 7, 7),
        ("int64", 2**40, 2**40, 2**40),
        ("float32", 1.5, 1.5, 1.5),
        ("float64", 2.25, 2.25, 2.25),
        ("decimal(12,2)", "10.50", decimal.Decimal("10.50"), "10.50"),
        ("string", "Ada", "Ada", "Ada"),
        ("bytes", "0a0b", b"\x0a\x0b", "0a0b"),
        ("date", "2026-01-15", dt.date(2026, 1, 15), "2026-01-15"),
        ("time", "09:30:00", dt.time(9, 30), "09:30:00"),
        (
            "timestamp",
            "2026-01-15T11:30:00.000000Z",
            dt.datetime(2026, 1, 15, 11, 30, tzinfo=dt.UTC),
            "2026-01-15T11:30:00.000000Z",
        ),
        (
            "uuid",
            "123e4567-e89b-12d3-a456-426614174000",
            uuid.UUID("123e4567-e89b-12d3-a456-426614174000"),
            "123e4567-e89b-12d3-a456-426614174000",
        ),
        ("json", {"a": [1, True, None]}, {"a": [1, True, None]}, {"a": [1, True, None]}),
    ],
)
def test_each_type_decodes_and_encodes_independently(
    spelling: str, authored: object, managed: object, canonical: object
) -> None:
    assert literal.decode(authored, spelling) == managed
    assert literal.encode(managed, spelling) == canonical
    assert literal.canonicalize(authored, spelling) == canonical


def test_json_normalization_erases_authored_number_provenance() -> None:
    authored = {
        "integer": literal.AuthoredInteger("-0"),
        "fractional": literal.AuthoredNumber("0.10000000000000001"),
    }

    for normalized in (
        literal.decode(authored, "json"),
        literal.encode(authored, "json"),
        literal.canonicalize(authored, "json"),
    ):
        assert type(normalized["integer"]) is int
        assert type(normalized["fractional"]) is float


def test_canonical_decode_refuses_an_admitted_alternative() -> None:
    with pytest.raises(literal.PortableLiteralError, match="not canonical"):
        literal.decode_canonical("2026-01-15T09:30:00Z", "timestamp")


@pytest.mark.parametrize(
    ("spelling", "value", "reason"),
    [
        ("int64", "1", "type-mismatch"),
        ("int64", 2**63, "out-of-space"),
        ("decimal(4,2)", "-0.00", "noncanonical"),
        ("bytes", "0A1B", "noncanonical"),
        ("time", "09:30", "type-mismatch"),
        ("time", "09:30:00.1234560", "type-mismatch"),
        ("timestamp", "2026-1-1T9:30:00Z", "type-mismatch"),
        ("timestamp", "2026-01-01T09:30:00.1234560Z", "type-mismatch"),
        ("timestamp", "2026-01-15T09:30:00+00:00", "noncanonical"),
        ("uuid", "123E4567-E89B-12D3-A456-426614174000", "noncanonical"),
    ],
)
def test_public_decode_classifies_rejected_literals(
    spelling: str, value: object, reason: str
) -> None:
    with pytest.raises(literal.PortableLiteralError) as exc_info:
        literal.decode(value, spelling)
    assert exc_info.value.reason == reason


@pytest.mark.parametrize(
    "value",
    [
        "2026-W01-1T09:30:00Z",
        "20260101T093000Z",
        "2026-01-01X09:30:00Z",
        "2026-01-01T09:30:00.1234560Z",
        pytest.param("2026-01-15T11:30:00.000000+02:00\n", id="trailing-newline"),
    ],
)
def test_observed_timestamp_refuses_host_parser_extensions(value: str) -> None:
    with pytest.raises(literal.PortableLiteralError) as exc_info:
        literal.canonicalize_observed(value, "timestamp")
    assert exc_info.value.reason == "type-mismatch"


def test_observed_timestamp_accepts_a_strict_provider_offset() -> None:
    assert (
        literal.canonicalize_observed("2026-01-15T11:30:00.000000+02:00", "timestamp")
        == "2026-01-15T09:30:00.000000Z"
    )


def test_null_is_not_a_typed_literal() -> None:
    with pytest.raises(literal.PortableLiteralError, match="enclosing presence"):
        literal.decode(None, "string")


@pytest.mark.parametrize(
    "value",
    [
        1.0,
        literal.AuthoredInteger("1"),
        literal.AuthoredNumber("1.0"),
    ],
)
def test_integer_encoding_requires_a_managed_integer_carrier(value: object) -> None:
    with pytest.raises(literal.PortableLiteralError) as exc_info:
        literal.encode(value, "int32")
    assert exc_info.value.reason == "type-mismatch"


def test_declared_projection_not_host_carrier_inference_decides_equality() -> None:
    assert literal.values_equal(decimal.Decimal("10.50"), "10.50", "decimal(12,2)", None)
    assert not literal.values_equal(decimal.Decimal("10.51"), "10.50", "decimal(12,2)", None)


@pytest.mark.parametrize("spelling", ["float32", "float64"])
def test_float_negative_zero_is_admitted_as_positive_but_not_canonical(spelling: str) -> None:
    managed = literal.decode(-0.0, spelling)

    assert math.copysign(1.0, managed) == 1.0
    assert math.copysign(1.0, literal.encode(-0.0, spelling)) == 1.0
    with pytest.raises(literal.PortableLiteralError, match="not canonical"):
        literal.decode_canonical(-0.0, spelling)


def test_decimal_managed_negative_zero_encodes_as_positive_zero() -> None:
    assert literal.encode(decimal.Decimal("-0.00"), "decimal(12,2)") == "0.00"
