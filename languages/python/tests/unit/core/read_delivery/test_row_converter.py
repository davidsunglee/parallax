"""A bound read's recording of a whole level's rows, where every row names one
Entity, and its flat-row publication."""

from __future__ import annotations

from typing import Final

import pytest

from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.read_delivery._page import ABSENT, ROOT_LEVEL, PageBuilder, ViewSchema, page_rows
from parallax.core.read_delivery._row_converter import bind
from parallax.core.temporal_read import Pin
from tests.unit._prepared_read_support import compiled_read, result_row, uncarried
from tests.unit.snapshot._encoded_page_models import ENCODED_ORDERS

_ENCODED: Final = model_of(ENCODED_ORDERS)


def test_a_fixed_read_records_a_level_carrying_no_cell_for_some_member() -> None:
    compiled = uncarried(compiled_read(_ENCODED, "EncodedOrder"), "name")
    converter = bind(CatalogedModel(_ENCODED), compiled.result_contract, compiled.projection)
    builder = PageBuilder(ViewSchema.of())
    rows = [
        result_row(compiled, {"id": order, "name": "Ada", "badge_hex": "0f", "address": None})
        for order in (1, 2)
    ]

    refs = converter.record_rows(rows, builder, ROOT_LEVEL, None)

    member_rows = page_rows(builder.finish(refs, Pin())).member_rows
    assert refs == (0, 1)
    assert [row[1] for row in member_rows] == [ABSENT, ABSENT]


def test_a_fixed_read_refuses_a_row_of_another_arity() -> None:
    compiled = compiled_read(_ENCODED, "EncodedOrder")
    converter = bind(CatalogedModel(_ENCODED), compiled.result_contract, compiled.projection)

    with pytest.raises(ValueError, match="does not match row arity 1"):
        converter.record_rows([(1,)], PageBuilder(ViewSchema.of()), ROOT_LEVEL, None)


def test_a_read_bound_without_row_operations_publishes_no_flat_row() -> None:
    compiled = compiled_read(_ENCODED, "EncodedOrder")
    converter = bind(CatalogedModel(_ENCODED), compiled.result_contract, compiled.projection)

    with pytest.raises(ValueError, match="bound without row operations"):
        converter.row_publisher()
