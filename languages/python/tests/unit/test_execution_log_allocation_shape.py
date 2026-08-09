"""Observability costs `O(attempts + database calls)` and `O(0)` per row.

`m-execution-log` states the cost as a contract rather than a hope, and requires
it proven structurally rather than by a wall clock. Two halves, in the two styles
this repository already uses: an allocation-shape regression counting
:class:`~parallax.core.execution_log.DatabaseCall` constructions at two dataset
sizes (`test_planned_allocation_shape.py`'s constructor hook), and a retained-size
regression bounding the log against attempts and calls rather than rows
(`test_storage_layout_facet.py`'s traversal).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import sys
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from typing import Any, cast

import pytest
from _transact_support import RecordingPort, account_db, new_account

from _support import mirrored_models as mm
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Order
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import Bind
from parallax.core.execution_log import (
    CallCompletion,
    CallKind,
    DatabaseCall,
    ExecutionLog,
)
from parallax.core.sql_gen import LoweredStatement
from parallax.snapshot import connect
from parallax.snapshot.handle import Transaction


def _order_rows(count: int) -> list[dict[str, object]]:
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


def _item_rows(count: int) -> list[dict[str, object]]:
    return [
        {
            "id": 1000 + index,
            "order_id": index,
            "sku": "X-1",
            "quantity": 1,
            "shipped_on": None,
        }
        for index in range(count)
    ]


def _counting_call(constructed: list[object], monkeypatch: pytest.MonkeyPatch) -> None:
    original_init = DatabaseCall.__init__

    def counting_init(
        self: DatabaseCall,
        statement: LoweredStatement,
        kind: CallKind,
        duration_ns: int,
        completion: CallCompletion,
    ) -> None:
        constructed.append(self)
        original_init(self, statement, kind, duration_ns, completion)

    monkeypatch.setattr(DatabaseCall, "__init__", counting_init)


def test_a_deep_fetch_constructs_one_call_per_level_whatever_the_row_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # One statement per non-empty level (`m-deep-fetch`), so a root plus one
    # included level is two Database Calls — at five rows and at eight hundred.
    constructed: list[object] = []
    _counting_call(constructed, monkeypatch)

    per_row_count: dict[int, int] = {}
    for row_count in (5, 800):
        constructed.clear()
        port = RecordingPort(row_queue=[_order_rows(row_count), _item_rows(row_count)])
        db = connect(port, MODELS["orders"])
        db.find(Order.where(Order.all).include(Order.items))
        per_row_count[row_count] = len(constructed)

    levels = 1
    assert per_row_count == {5: 1 + levels, 800: 1 + levels}


def test_a_transactional_invocation_constructs_one_call_per_statement_it_ran(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The write side of the same bound: a buffered insert plus a dependent read
    # is two calls however many rows the read returns.
    constructed: list[object] = []
    _counting_call(constructed, monkeypatch)

    per_row_count: dict[int, int] = {}
    for row_count in (5, 800):
        constructed.clear()
        port = RecordingPort(rows=_account_rows(row_count))

        def body(tx: Transaction) -> None:
            tx.insert(new_account())
            tx.find(mm.Account.where(mm.Account.balance < 1_000_000.00)).results()

        account_db(port).transact(body)
        per_row_count[row_count] = len(constructed)

    assert per_row_count == {5: 2, 800: 2}


def _account_rows(count: int) -> list[dict[str, object]]:
    return [
        {"id": index, "owner": f"Owner{index}", "balance": Decimal("1.00"), "version": 1}
        for index in range(count)
    ]


class _FailingWritePort(RecordingPort):
    """A port whose writes always fail — the arrangement a multi-attempt log
    needs, with no row count of its own."""

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        raise DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")


def _log_of(*, rows: int, retries: int) -> ExecutionLog:
    port = _FailingWritePort(rows=_account_rows(rows))
    held: list[ExecutionLog] = []

    def body(tx: Transaction) -> None:
        held.append(tx.execution_log)
        tx.find(mm.Account.where(mm.Account.balance < 1_000_000.00)).results()
        tx.insert(new_account())

    with pytest.raises(DatabaseError):
        account_db(port).transact(body, retries=retries)
    return held[0]


def test_the_retained_log_grows_with_attempts_and_calls_and_not_with_rows() -> None:
    small = _log_of(rows=5, retries=0)
    wide = _log_of(rows=800, retries=0)
    retried = _log_of(rows=5, retries=1)

    # Cardinality-independent: the same two calls per attempt, 160x the rows.
    assert _retained_size(wide) == _retained_size(small)
    # Linear in attempts and calls, which is the whole of the stated bound.
    assert len(retried.attempts) == 2 * len(small.attempts)
    assert retried.round_trips == 2 * small.round_trips
    assert _retained_size(retried) < 3 * _retained_size(small)


def _retained_size(value: object) -> int:
    """The transitive in-memory footprint of ``value``, counting each object
    once (`test_storage_layout_facet.py`'s own traversal)."""
    seen: set[int] = set()

    def measure(current: object) -> int:
        if id(current) in seen:
            return 0
        seen.add(id(current))
        size = sys.getsizeof(current)
        if dataclasses.is_dataclass(current) and not isinstance(current, type):
            return size + sum(
                measure(getattr(current, field.name)) for field in dataclasses.fields(current)
            )
        if isinstance(current, Mapping):
            entries = cast("Mapping[object, object]", current)
            return size + sum(measure(key) + measure(item) for key, item in entries.items())
        if isinstance(current, (tuple, list, set, frozenset)):
            return size + sum(measure(item) for item in cast("Iterable[object]", current))
        slots = _slots(current)
        return size + sum(
            measure(getattr(current, slot)) for slot in slots if hasattr(current, slot)
        )

    return measure(value)


def _slots(current: object) -> tuple[str, ...]:
    declared: Any = getattr(type(current), "__slots__", ())
    if isinstance(declared, str):
        return (declared,)
    return tuple(name for name in cast("Iterable[Any]", declared) if isinstance(name, str))
