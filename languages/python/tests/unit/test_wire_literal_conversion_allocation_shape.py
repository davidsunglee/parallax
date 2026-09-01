"""Whole-interpreter bounds for typed-bind metadata and numeric Wire conversion."""

from __future__ import annotations

import sys
import tracemalloc
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Final

from _corpus_model_support import model as corpus_model
from memory_instruments import (
    Heap,
    Seam,
    Span,
    high_water,
    in_a_child_interpreter,
    serve_one_measurement,
    whole_heap,
)

from parallax.core import inheritance, storage_layout
from parallax.core.base import FLOAT64, STRING
from parallax.core.base import Decimal as DecimalType
from parallax.core.dialect import POSTGRES
from parallax.core.sql_gen._context import StatementBuilder
from parallax.core.wire import WireDecodingError, decode_canonical_wire, loads

_MODEL: Final = corpus_model("wallet")
_SAME_TYPE_COUNTS: Final = (256, 512, 768)
_ROW_COUNTS: Final = (128, 256, 384)
_DECIMAL_DIGITS: Final = (64, 128, 192)


def _builder() -> StatementBuilder:
    return StatementBuilder(
        _MODEL,
        inheritance.view(_MODEL),
        storage_layout.view(_MODEL),
        POSTGRES,
    )


def _same_type_statement(bind_count: int) -> Seam:
    def build(sample: Callable[[], None]) -> None:
        builder = _builder()
        for _ in range(bind_count):
            builder.bind_managed("value", STRING)
        statement = builder.finish("")
        del builder
        assert len(statement.binds) == bind_count
        assert len(statement.typed_bind_spans) == 1
        sample()

    return build


def _heterogeneous_rows(row_count: int) -> Seam:
    def build(sample: Callable[[], None]) -> None:
        builder = _builder()
        rows = (("managed", "comparison"),) * row_count
        builder.bind_typed_rows(
            rows,
            ((STRING, "MANAGED"), (STRING, "COMPARISON_TEXT")),
        )
        statement = builder.finish("")
        del builder, rows
        assert len(statement.binds) == row_count * 2
        assert len(statement.typed_bind_spans) == 2
        sample()

    return build


def _equal_step_growth(readings: Sequence[Heap]) -> None:
    assert len(readings) == 3
    first, second, third = readings
    assert first.objects == second.objects == third.objects
    assert first.references == second.references == third.references
    assert second.held - first.held == third.held - second.held


@in_a_child_interpreter
def test_typed_bind_metadata_stays_structural_as_bind_counts_grow() -> None:
    same_type = whole_heap(*(_same_type_statement(count) for count in _SAME_TYPE_COUNTS))
    heterogeneous = whole_heap(*(_heterogeneous_rows(count) for count in _ROW_COUNTS))

    _equal_step_growth(same_type)
    _equal_step_growth(heterogeneous)


def _decimal_conversion(digits: int) -> Span:
    literal = "1" * digits + ".00"
    wire_value = loads(f'"{literal}"')
    declared = DecimalType(digits + 2, 2)

    def convert(opened: Callable[[], None], closed: Callable[[], None]) -> None:
        opened()
        result = decode_canonical_wire(declared, wire_value)
        closed()
        assert isinstance(result, Decimal)
        assert result.adjusted() == digits - 1

    return convert


def _extreme_number_conversion(exponent: int) -> Span:
    wire_value = loads(f"1e{exponent}")

    def convert(opened: Callable[[], None], closed: Callable[[], None]) -> None:
        opened()
        try:
            decode_canonical_wire(FLOAT64, wire_value)
        except WireDecodingError as error:
            assert error.reason == "out-of-space"
        else:
            raise AssertionError("extreme exponent unexpectedly entered Float64")
        closed()

    return convert


@in_a_child_interpreter
def test_decimal_and_number_conversion_have_bounded_allocation_shape() -> None:
    tracemalloc.start()
    try:
        decimal_peaks = tuple(high_water(_decimal_conversion(size)) for size in _DECIMAL_DIGITS)
        exponent_peaks = tuple(
            high_water(_extreme_number_conversion(exponent)) for exponent in (1_000, 5_000, 9_000)
        )
    finally:
        tracemalloc.stop()

    first_growth = decimal_peaks[1] - decimal_peaks[0]
    second_growth = decimal_peaks[2] - decimal_peaks[1]
    assert first_growth > 0
    assert second_growth <= first_growth * 2
    assert len(set(exponent_peaks)) == 1


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
