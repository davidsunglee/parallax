from __future__ import annotations

import datetime as dt
from decimal import Decimal

from _corpus_model_support import model as corpus_model

from _support.lowering_probes import lower_instruction
from parallax.core import inheritance, storage_layout
from parallax.core.base import DATE, STRING
from parallax.core.base import Decimal as DecimalType
from parallax.core.dialect import POSTGRES
from parallax.core.sql_gen._context import (
    StatementBuilder,
    _RepeatedTypedBindSpan,  # pyright: ignore[reportPrivateUsage]
    _TypedBindSpan,  # pyright: ignore[reportPrivateUsage]
)
from parallax.core.unit_work import KeyedWrite

WALLET = corpus_model("wallet")


def _builder() -> StatementBuilder:
    return StatementBuilder(
        WALLET,
        inheritance.view(WALLET),
        storage_layout.view(WALLET),
        POSTGRES,
    )


def test_statement_metadata_preserves_ranges_gaps_forms_offsets_and_overrides() -> None:
    decimal_type = DecimalType(8, 2)
    statement = _builder()
    statement.bind_managed(Decimal("1.20"), decimal_type)
    statement.bind_managed(Decimal("2.30"), decimal_type)
    statement.bind_framework("framework")
    statement.bind_comparison_text("alpha", STRING)

    fragment = _builder()
    fragment.bind_managed(dt.date(2024, 1, 2), DATE)
    fragment.bind_framework("driver-infinity", wire_value="infinity")
    statement.append_fragment(fragment.finish(""))

    lowered = statement.finish("select ?, ?, ?, ?, ?, ?")
    spans = lowered._typed_bind_spans  # pyright: ignore[reportPrivateUsage]
    assert [
        (span.start, span.stop, span.neutral_type, span.form)
        for span in spans
        if isinstance(span, _TypedBindSpan)
    ] == [
        (0, 2, decimal_type, "MANAGED"),
        (3, 4, STRING, "COMPARISON_TEXT"),
        (4, 5, DATE, "MANAGED"),
    ]
    assert [
        (override.index, override.value)
        for override in lowered._wire_bind_overrides  # pyright: ignore[reportPrivateUsage]
    ] == [(5, "infinity")]
    assert lowered.wire_binds() == (
        "1.20",
        "2.30",
        "framework",
        "alpha",
        "2024-01-02",
        "infinity",
    )
    assert isinstance(lowered.binds[0], Decimal)
    assert isinstance(lowered.binds[4], dt.date)


def test_multirow_write_uses_one_repeated_descriptor_per_typed_row_run() -> None:
    statement = lower_instruction(
        KeyedWrite(
            "insert",
            "Wallet",
            (
                {"id": 1, "owner": "A", "balance": Decimal("10.00")},
                {"id": 2, "owner": "B", "balance": Decimal("20.00")},
                {"id": 3, "owner": "C", "balance": Decimal("30.00")},
            ),
        ),
        WALLET,
        POSTGRES,
        "locking",
    )[0]

    spans = statement._typed_bind_spans  # pyright: ignore[reportPrivateUsage]
    assert len(spans) == 3
    assert [
        (span.start, span.width, span.stride, span.repetitions, span.form)
        for span in spans
        if isinstance(span, _RepeatedTypedBindSpan)
    ] == [
        (0, 1, 3, 3, "MANAGED"),
        (1, 1, 3, 3, "MANAGED"),
        (2, 1, 3, 3, "MANAGED"),
    ]
    assert statement.wire_binds() == (
        1,
        "A",
        "10.00",
        2,
        "B",
        "20.00",
        3,
        "C",
        "30.00",
    )
