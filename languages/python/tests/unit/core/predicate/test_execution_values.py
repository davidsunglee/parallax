from __future__ import annotations

from parallax.core.metamodel import TemporalDimension
from parallax.core.predicate._execution_values import ExecutionValueSource, source_order


def test_sources_order_by_category_then_position_with_valid_time_first() -> None:
    sources: list[ExecutionValueSource] = [
        ("keys",),
        ("limit",),
        ("paging", 1),
        ("temporal", TemporalDimension.TRANSACTION_TIME, "coordinate"),
        ("paging", 0),
        ("temporal", TemporalDimension.VALID_TIME, "start"),
        ("temporal", TemporalDimension.VALID_TIME, "end"),
        ("predicate", 2),
        ("predicate", 0),
    ]

    assert sorted(sources, key=source_order) == [
        ("predicate", 0),
        ("predicate", 2),
        ("temporal", TemporalDimension.VALID_TIME, "end"),
        ("temporal", TemporalDimension.VALID_TIME, "start"),
        ("temporal", TemporalDimension.TRANSACTION_TIME, "coordinate"),
        ("paging", 0),
        ("paging", 1),
        ("limit",),
        ("keys",),
    ]
