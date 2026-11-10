"""Strict read routing across every public read shape, Typed and Wire alike.

A database declaring a reader defaults every NEW read to it — an eager graph, a
row read, each standalone stream page, and an outer read-only transaction — and
keeps writable transactions on the writer. A preferred read that fell back keeps
the rest of its operation on the writer. Work inside a transaction acquires
nothing and so requests nothing, whichever context it runs in. The routing
rules themselves are core's; these pin that the facades reach them the same way.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any, Final

import pytest

from parallax.conformance.scripted_clock import FixedClock
from parallax.conformance.story_models import ORDERS_MODEL, Order
from parallax.core.internal.db_port import Route, RouteCapabilities, RoutePolicy, RouteSelection
from parallax.snapshot import Database, ReadOnlyTxnContext, ScopedDatabase, TxnContext, connect
from tests._support.db_port import Read, ScriptedAdapter, Transact
from tests._support.root_ownership import own_root
from tests.unit._stream_page_support import paged_reads
from tests.unit._transact_support import FIXED

_STANDBY: Final[Mapping[Route, RouteCapabilities]] = {
    "writer": RouteCapabilities.every_level(),
    "reader": RouteCapabilities(frozenset({"read_committed", "repeatable_read"})),
}


def _order_row(order_id: int) -> dict[str, object]:
    return {
        "id": order_id,
        "name": f"order-{order_id}",
        "sku": "A-100",
        "qty": 5,
        "price": Decimal("10.50"),
        "active": True,
        "ordered_on": dt.date(2024, 1, 5),
    }


_ROWS: Final = [_order_row(index) for index in (1, 2, 3)]


def _query() -> Any:
    return Order.where(Order.active == True)  # noqa: E712 - the query algebra's own equality


def _scope(adapter: ScriptedAdapter, read_policy: RoutePolicy | None = None) -> ScopedDatabase:
    database: Database[Any] = own_root(
        connect(adapter, ORDERS_MODEL, clock=FixedClock(FIXED), read_policy=read_policy)
    )
    return database.using_database_login()


def _typed_stream(db: ScopedDatabase) -> list[object]:
    with db.stream(_query(), batch_size=2) as roots:
        return [order.id for order in roots]


def _wire_stream(db: ScopedDatabase) -> list[object]:
    with db.wire.stream(_query(), batch_size=2) as roots:
        return list(roots)


_SHAPES: Final[dict[str, tuple[Callable[[ScopedDatabase], object], list[Read], int]]] = {
    "typed-eager": (lambda db: db.find(_query()).results(), [Read(rows=_ROWS)], 1),
    "wire-eager": (lambda db: db.wire.find(_query()).results(), [Read(rows=_ROWS)], 1),
    "typed-stream": (_typed_stream, paged_reads(_ROWS, size=2), 2),
    "wire-stream": (_wire_stream, paged_reads(_ROWS, size=2), 2),
}


@pytest.mark.parametrize("shape", list(_SHAPES))
def test_every_standalone_read_shape_requests_the_reader_by_default(shape: str) -> None:
    read, script, acquisitions = _SHAPES[shape]
    adapter = ScriptedAdapter(*script, routes=_STANDBY)

    read(_scope(adapter))

    assert adapter.requested_policies == ["reader_only"] * acquisitions


@pytest.mark.parametrize("shape", list(_SHAPES))
def test_every_standalone_read_shape_honors_a_writer_only_scope(shape: str) -> None:
    read, script, acquisitions = _SHAPES[shape]
    adapter = ScriptedAdapter(*script, routes=_STANDBY)

    read(_scope(adapter).with_routing(read_policy="writer_only"))

    assert adapter.requested_policies == ["writer_only"] * acquisitions


def test_a_read_only_transaction_requests_the_reader_once_for_everything_inside_it() -> None:
    adapter = ScriptedAdapter(
        Transact(Read(rows=_ROWS), *paged_reads(_ROWS, size=2), Read(rows=_ROWS)),
        routes=_STANDBY,
    )

    def body(tx: ReadOnlyTxnContext) -> None:
        tx.find(_query()).results()
        with tx.stream(_query(), batch_size=2) as roots:
            assert [order.id for order in roots] == [1, 2, 3]
        tx.wire.find(_query()).results()

    _scope(adapter).read_only(body, isolation="repeatable_read")

    assert adapter.requested_policies == ["reader_only"]


def test_a_writable_transaction_stays_on_the_writer_beside_a_standalone_reader_read() -> None:
    # A scope-level read inside the callback is standalone and requests its own
    # scope's policy; the transaction's own read participates and requests nothing.
    adapter = ScriptedAdapter(Transact(Read(rows=_ROWS), Read(rows=_ROWS)), routes=_STANDBY)
    db = _scope(adapter)

    def body(tx: TxnContext) -> None:
        tx.find(_query()).results()
        db.find(_query()).results()

    db.transact(body)

    assert adapter.requested_policies == ["writer_only", "reader_only"]


def test_a_read_only_level_the_reader_cannot_begin_is_refused_before_acquiring() -> None:
    adapter = ScriptedAdapter(Transact(), routes=_STANDBY)
    db = _scope(adapter)

    with pytest.raises(ValueError, match=r"with_routing\(read_policy='writer_only'\)"):
        db.read_only(lambda _tx: None, isolation="serializable")
    db.with_routing(read_policy="writer_only").read_only(lambda _tx: None, isolation="serializable")

    assert adapter.requested_policies == ["writer_only"]


_FELL_BACK: Final = RouteSelection("writer", "unavailable")


@pytest.mark.parametrize("shape", list(_SHAPES))
def test_every_preferred_read_shape_stays_on_the_writer_once_it_fell_back(shape: str) -> None:
    # An eager read is one acquisition; a stream that fell back on its first
    # page requests the writer for every later page, Typed and Wire alike.
    read, script, acquisitions = _SHAPES[shape]
    adapter = ScriptedAdapter(*script, selections=[_FELL_BACK], routes=_STANDBY)

    read(_scope(adapter, "reader_preferred"))

    assert adapter.requested_policies == ["reader_preferred"] + ["writer_only"] * (acquisitions - 1)


def test_a_preferred_read_only_level_the_reader_cannot_begin_requests_the_writer() -> None:
    adapter = ScriptedAdapter(Transact(Read(rows=_ROWS)), Transact(), routes=_STANDBY)
    db = _scope(adapter, "reader_preferred")

    db.read_only(lambda tx: tx.wire.find(_query()).results(), isolation="serializable")
    db.read_only(lambda _tx: None, isolation="repeatable_read")

    assert adapter.requested_policies == ["writer_only", "reader_preferred"]


def test_a_preferred_read_only_transaction_that_moved_at_begin_runs_its_reads_once() -> None:
    adapter = ScriptedAdapter(
        Transact(Read(rows=_ROWS), rerouted=RouteSelection("writer", "connection_lost")),
        Read(rows=_ROWS),
        routes=_STANDBY,
    )
    db = _scope(adapter, "reader_preferred")

    found = db.read_only(lambda tx: [order.id for order in tx.find(_query()).results()])
    # A new operation starts afresh from the scope's own policy.
    db.find(_query()).results()

    assert found == [1, 2, 3]
    assert adapter.requested_policies == ["reader_preferred", "reader_preferred"]
