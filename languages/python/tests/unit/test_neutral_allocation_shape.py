"""The typed path pays nothing for the second materializer.

The ticket's cost contract has two halves and this file proves the second: the
typed and neutral entry points run one executor, and the typed one constructs no
``Neutral*`` value — not per row, not per node, not once. Counted with the
constructor hook `test_planned_allocation_shape.py` established, at two dataset
sizes, with no wall-clock component.

The same query run through ``read_neutral`` is the control: it constructs neutral
values in proportion to the rows it materialized, which is what makes a zero on
the typed side evidence rather than a broken probe.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from _transact_support import RecordingPort

from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Order
from parallax.core.entity._model import model_of
from parallax.core.entity._query import lower_find_query
from parallax.snapshot import connect
from parallax.snapshot.handle import Database, NeutralReadRequest
from parallax.snapshot.materialize import (
    NeutralGraph,
    NeutralGraphs,
    NeutralNode,
    NeutralNodeView,
    NeutralRows,
)

ORDERS = MODELS["orders"]
_NEUTRAL_TYPES: tuple[type, ...] = (
    NeutralNode,
    NeutralNodeView,
    NeutralRows,
    NeutralGraph,
    NeutralGraphs,
)
"""Every published ``Neutral*`` value, so the count is total rather than a sample:
a typed find that constructed one this tuple omitted would still read as zero."""


def _count_neutral(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Count every ``Neutral*`` construction, whichever type it is."""
    constructed: list[object] = []
    for neutral in _NEUTRAL_TYPES:
        original: Callable[..., None] = neutral.__init__

        def counting(
            self: object, *args: Any, __original: Callable[..., None] = original, **kwargs: Any
        ) -> None:
            constructed.append(self)
            __original(self, *args, **kwargs)

        monkeypatch.setattr(neutral, "__init__", counting)
    return constructed


def _rows(count: int) -> list[dict[str, object]]:
    return [
        {
            "id": index,
            "name": f"Order{index}",
            "sku": "X-1",
            "qty": 1,
            "price": Decimal("9.99"),
            "active": True,
            "ordered_on": dt.date(2024, 7, 1),
        }
        for index in range(count)
    ]


def _items(count: int) -> list[dict[str, object]]:
    return [
        {"id": 1000 + index, "order_id": index, "sku": "X-1", "quantity": 1, "shipped_on": None}
        for index in range(count)
    ]


def _port(row_count: int) -> RecordingPort:
    return RecordingPort(row_queue=[_rows(row_count), _items(row_count)])


def _query() -> object:
    return Order.where(Order.all).include(Order.items)


def test_a_typed_find_constructs_no_neutral_value_at_any_row_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed = _count_neutral(monkeypatch)
    per_row_count: dict[int, int] = {}
    for row_count in (5, 800):
        constructed.clear()
        connect(_port(row_count), ORDERS).find(_query())  # pyright: ignore[reportArgumentType] - the query's own type
        per_row_count[row_count] = len(constructed)
    assert per_row_count == {5: 0, 800: 0}


def test_the_same_query_through_read_neutral_does_construct_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed = _count_neutral(monkeypatch)
    lowered = lower_find_query(_query())  # pyright: ignore[reportArgumentType] - the query's own type
    request = NeutralReadRequest.graph(target=lowered.target, operation=lowered.operation)

    per_row_count: dict[int, int] = {}
    for row_count in (5, 800):
        constructed.clear()
        result = Database(_port(row_count), model_of(ORDERS)).read_neutral(request)
        assert isinstance(result.output, NeutralGraph)
        per_row_count[row_count] = len(constructed)

    assert per_row_count[800] > per_row_count[5] > 0
