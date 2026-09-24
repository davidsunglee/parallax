"""Retained and transient bounds for typed-bind metadata and numeric Wire
conversion (`cost` class)."""

from __future__ import annotations

import sys
import tracemalloc
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Final

from parallax.core import inheritance, predicate, storage_layout
from parallax.core.base import FLOAT64, STRING
from parallax.core.base import Decimal as DecimalType
from parallax.core.dialect import POSTGRES
from parallax.core.sql_gen._context import (
    LoweredStatement,
    StatementBuilder,
    _TypedBindSpan,  # pyright: ignore[reportPrivateUsage]
)
from parallax.core.wire import WireDecodingError, decode_canonical_wire, loads
from tests._support.sql import compile_read
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._corpus_model_support import target
from tests.unit.memory_instruments import (
    Seam,
    Span,
    high_water,
    in_a_child_interpreter,
    retained,
    serve_one_measurement,
)

_MODEL: Final = corpus_model("wallet")
_WALLET: Final = target(_MODEL, "Wallet")
# Every count is past CPython's small-integer cache, so the span bound each one
# ends at is an integer the statement allocates at every count rather than at
# some.
_SAME_TYPE_COUNTS: Final = (300, 600, 900)
_ROW_COUNTS: Final = (300, 600, 900)
_DECIMAL_DIGITS: Final = (64, 128, 192)


def _builder() -> StatementBuilder:
    return StatementBuilder(
        _MODEL,
        inheritance.view(_MODEL),
        storage_layout.view(_MODEL),
        POSTGRES,
    )


def _same_type_statement(bind_count: int) -> Callable[[], LoweredStatement]:
    def build() -> LoweredStatement:
        membership = predicate.Membership(
            op="in",
            attr="Wallet.owner",
            values=("value",) * bind_count,
        )
        statement = compile_read(membership, _MODEL, POSTGRES, _WALLET).statement
        assert len(statement.binds) == bind_count
        assert statement.sql.endswith(
            f"where t0.owner in ({', '.join('?' for _ in range(bind_count))})"
        )
        assert statement.typed_bind_spans == (_TypedBindSpan(0, bind_count, STRING, "MANAGED"),)
        return statement

    return build


def _heterogeneous_rows(row_count: int) -> Callable[[], LoweredStatement]:
    def build() -> LoweredStatement:
        builder = _builder()
        rows = (("managed", "comparison"),) * row_count
        builder.bind_typed_rows(
            rows,
            ((STRING, "MANAGED"), (STRING, "COMPARISON_TEXT")),
        )
        statement = builder.finish("")
        assert len(statement.binds) == row_count * 2
        assert len(statement.typed_bind_spans) == 2
        return statement

    return build


def _holding(
    build: Callable[[], LoweredStatement], kept: Callable[[LoweredStatement], object]
) -> Seam:
    """``build``'s statement, of which only what ``kept`` answers is still held at
    the sample point."""

    def seam(sample: Callable[[], None]) -> None:
        held = kept(build())
        sample()
        assert held is not None

    return seam


def _whole(statement: LoweredStatement) -> object:
    return statement


def _binds_and_sql(statement: LoweredStatement) -> object:
    return statement.binds, statement.sql


def _metadata_is_fixed(builds: Sequence[Callable[[], LoweredStatement]]) -> None:
    """That what a statement holds beyond its binds and its SQL is the same number
    of bytes at every bind count.

    The binds and the SQL are what grows with the count, so each is read as its
    own control: the statement against those two alone, built the same way. A
    span, override, or slot kept per bind rather than per run is what would make
    the difference grow."""
    beyond = [
        retained(_holding(build, _whole)) - retained(_holding(build, _binds_and_sql))
        for build in builds
    ]
    assert beyond[0] > 0, beyond
    assert len(set(beyond)) == 1, beyond


@in_a_child_interpreter
def test_typed_bind_metadata_stays_structural_as_bind_counts_grow() -> None:
    tracemalloc.start()
    try:
        _metadata_is_fixed([_same_type_statement(count) for count in _SAME_TYPE_COUNTS])
        _metadata_is_fixed([_heterogeneous_rows(count) for count in _ROW_COUNTS])
    finally:
        tracemalloc.stop()


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
