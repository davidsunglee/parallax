from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from typing import Any, cast

import pytest

from parallax.core.base import INFINITY
from parallax.core.dialect import POSTGRES, Dialect
from tests._support import temporal_write_transport as transport
from tests._support.temporal_write_transport import (
    AMENDED_AT,
    AMOUNT,
    CELLS,
    REPLACED_LABEL,
    SEEDED_AT,
    Cell,
    CountingConnection,
    HistoryRow,
    PortTally,
    Realization,
    expected_history,
    expected_realization,
    milestone_start,
    seeded_history,
)


class _Inner:
    """A connection recording what reached it, with or without ordered transport."""

    def __init__(self, *, ordered: bool) -> None:
        self.dialect: Dialect = POSTGRES
        self.calls: list[object] = []
        self.ordered_write_transport = self._transport if ordered else None

    def _transport(self, statements: Sequence[object]) -> object:
        self.calls.append(("ordered", tuple(statements)))
        return ("result", len(statements))

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[object] = ()
    ) -> list[object]:
        self.calls.append(("read", sql))
        return [(1,)]

    def execute_pipeline(self, statements: Sequence[object]) -> list[list[object]]:
        self.calls.append(("pipeline", len(statements)))
        return [[] for _ in statements]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.calls.append(("write", sql))
        return 1

    def transaction(
        self,
        body: Callable[[object], object],
        *,
        isolation: object = None,
        access_mode: object = None,
    ) -> object:
        self.calls.append(("transaction", isolation))
        return body(self)


def _counting(inner: _Inner, tally: PortTally) -> CountingConnection:
    return CountingConnection(cast("Any", inner), tally)


def test_the_tally_counts_each_call_and_the_rows_each_insert_carried() -> None:
    inner = _Inner(ordered=True)
    tally = PortTally()
    connection = _counting(inner, tally)
    connection.execute("select 1", [])
    connection.execute_pipeline(cast("Any", ("a", "b")))
    connection.execute_write("update t set a = %s", [1])
    connection.execute_write("insert into t(a) values (%s)", [1])
    connection.execute_write("insert into t(a) values (%s), (%s), (%s)", [1, 2, 3])
    transport_call = cast(
        "Callable[[Sequence[object]], object]", connection.ordered_write_transport
    )
    assert transport_call(("x", "y")) == ("result", 2)
    transport_call(("z",))
    assert tally.realization() == Realization(1, 2, 3, 2, 2, 4, 3)
    assert tally.reads == 3
    assert tally.logical_writes == 8
    assert [call[0] for call in cast("list[tuple[str, object]]", inner.calls)] == [
        "read",
        "pipeline",
        "write",
        "write",
        "write",
        "ordered",
        "ordered",
    ]


def test_ordered_transport_is_forwarded_through_a_stored_callable_of_its_own() -> None:
    inner = _Inner(ordered=True)
    connection = _counting(inner, PortTally())
    forwarded = connection.ordered_write_transport
    assert forwarded is not None
    assert forwarded is connection.ordered_write_transport
    assert forwarded != inner.ordered_write_transport


def test_no_ordered_transport_is_manufactured_over_a_connection_without_one() -> None:
    assert _counting(_Inner(ordered=False), PortTally()).ordered_write_transport is None


def test_a_transaction_hands_its_body_a_connection_counting_into_the_same_tally() -> None:
    inner = _Inner(ordered=True)
    tally = PortTally()

    def body(handed: Any) -> int:
        assert isinstance(handed, CountingConnection)
        handed.execute_write("update t set a = 1", [])
        forwarded = handed.ordered_write_transport
        assert forwarded is not None
        forwarded(("x",))
        return 7

    assert _counting(inner, tally).transaction(body, isolation=cast("Any", "serializable")) == 7
    assert inner.calls[0] == ("transaction", "serializable")
    assert (tally.effects, tally.ordered) == (1, 1)


@pytest.mark.parametrize(
    ("cell", "ordered", "realized"),
    [
        (Cell("keyed-amend", 1), True, Realization(1, 0, 0, 0, 1, 3, 3)),
        (Cell("keyed-amend", 64), True, Realization(0, 1, 64, 64, 2, 66, 64)),
        (Cell("keyed-amend", 64), False, Realization(64, 0, 0, 0, 2, 66, 64)),
        (Cell("keyed-amend", 65), True, Realization(1, 1, 64, 64, 2, 67, 64)),
        (Cell("keyed-amend", 66), True, Realization(0, 2, 66, 64, 2, 68, 64)),
        (Cell("keyed-amend", 128), True, Realization(0, 2, 128, 64, 3, 130, 64)),
        (Cell("target-replace", 1), True, Realization(1, 0, 0, 0, 1, 3, 3)),
        (Cell("target-replace", 64), True, Realization(0, 1, 64, 64, 1, 3, 3)),
        (Cell("predicate-amend", 70), True, Realization(70, 0, 0, 0, 70, 210, 3)),
        (Cell("collection-amend", 64), True, Realization(0, 1, 64, 64, 2, 66, 64)),
    ],
    ids=lambda value: value.id if isinstance(value, Cell) else str(value),
)
def test_a_cells_realization_follows_from_its_closes_and_openings(
    cell: Cell, ordered: bool, realized: Realization
) -> None:
    # A lone close runs alone, as does one a capped invocation leaves behind;
    # every opening rides an insert of at most the entry cap.
    assert expected_realization(cell, ordered=ordered) == realized


def test_every_cell_is_a_workload_the_live_module_drives() -> None:
    assert len(set(CELLS)) == len(CELLS)
    assert {cell.workload for cell in CELLS} == {
        "keyed-amend",
        "target-replace",
        "predicate-amend",
        "collection-amend",
    }
    assert transport.STATEMENT_CAP == transport.ENTRY_CAP == 64


def _day(days: int) -> dt.datetime:
    return transport.EPOCH + dt.timedelta(days=days)


def test_a_one_milestone_amendment_closes_it_and_opens_head_middle_and_tail() -> None:
    (seed,) = seeded_history("keyed-amend", 1, 0)
    assert seed == HistoryRow(1, _day(0), INFINITY, SEEDED_AT, INFINITY, "k1-0", 0)
    assert expected_history("keyed-amend", 1, 0) == [
        seed._replace(tx_to=AMENDED_AT),
        HistoryRow(1, _day(0), _day(10), AMENDED_AT, INFINITY, "k1-0", 0),
        HistoryRow(1, _day(10), _day(20), AMENDED_AT, INFINITY, "k1-0", AMOUNT),
        HistoryRow(1, _day(20), INFINITY, AMENDED_AT, INFINITY, "k1-0", 0),
    ]


def test_a_wide_amendment_keeps_every_milestone_apart_and_a_replacement_merges_them() -> None:
    amended = [row for row in expected_history("keyed-amend", 64, 2) if row.tx_from == AMENDED_AT]
    assert len(amended) == 66
    assert [row.label for row in amended] == [
        "k3-0",
        *(f"k3-{index}" for index in range(64)),
        "k3-63",
    ]
    assert amended[1].valid_from == _day(10)
    assert amended[-2] == HistoryRow(
        3, milestone_start(63), _day(63 * 30 + 20), AMENDED_AT, INFINITY, "k3-63", AMOUNT
    )
    closed = [row for row in expected_history("keyed-amend", 64, 2) if row.tx_to == AMENDED_AT]
    assert len(closed) == 64
    replaced = [
        row for row in expected_history("target-replace", 64, 0) if row.tx_from == AMENDED_AT
    ]
    assert [(row.label, row.amount) for row in replaced] == [
        ("t1-0", 0),
        (REPLACED_LABEL, AMOUNT),
        ("t1-63", 63),
    ]
    assert replaced[1].valid_from == _day(10)
    assert replaced[1].valid_to == _day(63 * 30 + 20)


def test_a_predicate_group_amends_each_of_its_objects_alone() -> None:
    history = expected_history("predicate-amend", 70, 4)
    assert {row.key for row in history} == {5000 + index for index in range(70)}
    assert len(history) == 70 * 4
    assert all(
        [row.valid_from for row in history if row.key == key and row.tx_from == AMENDED_AT]
        == [_day(0), _day(10), _day(20)]
        for key in range(5000, 5070)
    )
