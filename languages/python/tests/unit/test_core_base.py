"""m-core (`parallax.core.base`) neutral-type and instant-normalization tests."""

from __future__ import annotations

import datetime as dt
import decimal

import pytest

from parallax.core import base


def test_neutral_type_set_matches_m_core() -> None:
    expected = {
        "boolean",
        "int32",
        "int64",
        "float32",
        "float64",
        "decimal",
        "string",
        "bytes",
        "date",
        "time",
        "timestamp",
        "uuid",
        "json",
    }
    assert expected == base.NEUTRAL_TYPES
    assert base.DOCUMENT_TYPE == "json"
    assert base.DOCUMENT_TYPE in base.NEUTRAL_TYPES


@pytest.mark.parametrize("name", ["int64", "timestamp", "json", "decimal", "decimal(18,2)"])
def test_is_neutral_type_accepts_base_and_parametric_decimal(name: str) -> None:
    assert base.is_neutral_type(name)


@pytest.mark.parametrize("name", ["Int64", "decimal()", "decimal(2)", "widget", "int"])
def test_is_neutral_type_rejects_unknown_and_malformed(name: str) -> None:
    assert not base.is_neutral_type(name)


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
    assert not base.is_document_value(float("nan"))
    assert not base.is_document_value(object())


def test_normalize_instant_converts_aware_to_utc_microsecond() -> None:
    eastern = dt.timezone(dt.timedelta(hours=-5))
    aware = dt.datetime(2026, 7, 12, 8, 30, 0, 123456, tzinfo=eastern)
    normalized = base.normalize_instant(aware)
    assert normalized.tzinfo is dt.UTC
    assert normalized == dt.datetime(2026, 7, 12, 13, 30, 0, 123456, tzinfo=dt.UTC)


def test_normalize_instant_rejects_naive() -> None:
    with pytest.raises(base.InstantError):
        base.normalize_instant(dt.datetime(2026, 7, 12, 8, 30, 0))
