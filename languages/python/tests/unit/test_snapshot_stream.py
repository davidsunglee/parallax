"""Snapshot Stream delivery tests: ``db.stream`` and ``db.wire.stream``.

Drives the real seam end to end against a canned `m-db-port` (no Docker) — the
page loop, the production find executor, and per-root publication through both
materializers — so what these assert is what a streamed read answers.

Four claims bound the suite. The state table IS the enforcement, so every one of
its cells is graded rather than only the reachable ones. Statement accounting is
what makes "a page is an eager read" observable: each nonempty page costs the
same `1 + L` a whole eager read costs, and a full final page costs one more root
statement returning nothing unless a declared ``limit`` was already delivered.
Identity is root-local, which is a NARROWING of what an eager read happens to do
rather than a second identity rule, so the within-root half is asserted to agree
with ``find`` and the cross-root half to diverge from it, in both namespaces.
And the one root shape that cannot supply a cursor ends the delivery from
whatever position it lands in, which is what keeps ``batch_size`` a performance
dial.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator, Mapping, Sequence
from decimal import Decimal
from typing import Any, cast

import pytest
from _transact_support import ACCOUNT, NoIoPort, RecordingPort, db_for

from parallax.conformance.story_models import ORDERS_MODEL, Order, OrderStatus
from parallax.core.db_port import Row
from parallax.core.object_query._fluent import ObjectQuery
from parallax.snapshot import (
    InvalidData,
    InvalidDataError,
    QueryTargetError,
    SnapshotStreamStateError,
    WireEntity,
)
from parallax.snapshot.handle import Database, Transaction

_UTC = dt.UTC


def _order_row(order_id: int) -> Row:
    return {
        "id": order_id,
        "name": f"order-{order_id}",
        "sku": "A-100",
        "qty": 5,
        "price": Decimal("10.50"),
        "active": True,
        "ordered_on": dt.date(2024, 1, 5),
    }


def _keyless_order_row() -> Row:
    return {**_order_row(0), "id": None}


def _item_row(item_id: int, order_id: int) -> Row:
    return {
        "id": item_id,
        "order_id": order_id,
        "sku": "SKU",
        "quantity": 1,
        "shipped_on": dt.date(2024, 2, 1),
    }


def _status_row(status_id: int, order_id: int) -> Row:
    return {"id": status_id, "order_id": order_id, "order_item_id": None, "code": "NEW"}


def _pages(*results: Sequence[Row]) -> RecordingPort:
    return RecordingPort(row_queue=[list(result) for result in results])


def _orders(port: RecordingPort) -> Database:
    return db_for(ORDERS_MODEL, port)


def _reads(port: RecordingPort) -> list[tuple[object, ...]]:
    return [op for op in port.ops if op[0] == "read"]


def _all_orders() -> ObjectQuery[Order, Order]:
    return Order.where(Order.active == True)  # noqa: E712 - the query algebra's own equality


def _ids(roots: Iterator[Any]) -> list[int]:
    return [root.id for root in roots]


def _entity(published: object) -> WireEntity:
    assert isinstance(published, WireEntity), published
    return published


# --------------------------------------------------------------------------- #
# The state table, cell by cell.                                               #
# --------------------------------------------------------------------------- #
def test_a_created_stream_answers_nothing_and_reaches_no_port() -> None:
    # Construction alone is inert: no gate, no plan, no statement. Everything a
    # stream answers is answered inside its own scope, `pin` included, so
    # "outside the scope, everything raises" is one rule rather than one rule
    # with an exception.
    stream = Database(NoIoPort(), ORDERS_MODEL).stream(_all_orders())
    with pytest.raises(SnapshotStreamStateError, match="inside its own scope"):
        _ = stream.pin
    with pytest.raises(SnapshotStreamStateError, match="single-pass"):
        iter(stream)
    with pytest.raises(SnapshotStreamStateError, match="single-pass"):
        stream.checked()


def test_entering_twice_is_refused() -> None:
    port = _pages([])
    with (
        _orders(port).stream(_all_orders()) as stream,
        pytest.raises(SnapshotStreamStateError, match="entered exactly once"),
    ):
        stream.__enter__()


def test_entering_while_draining_is_refused() -> None:
    port = _pages([_order_row(1)])
    with _orders(port).stream(_all_orders()) as stream:
        roots = iter(stream)
        next(roots)
        with pytest.raises(SnapshotStreamStateError, match="entered exactly once"):
            stream.__enter__()


def test_a_second_view_of_either_kind_is_refused() -> None:
    # Sharper than it strictly had to be, deliberately: a second pass over a
    # single-pass delivery is an error rather than a silent empty one.
    port = _pages([_order_row(1)], [])
    with _orders(port).stream(_all_orders()) as stream:
        list(stream)
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            iter(stream)
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            stream.checked()

    port = _pages([_order_row(1)], [])
    with _orders(port).stream(_all_orders()) as stream:
        list(stream.checked())
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            stream.checked()
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            iter(stream)


def test_an_exhausted_stream_answers_nothing_further() -> None:
    port = _pages([_order_row(1)])
    with _orders(port).stream(_all_orders()) as stream:
        assert _ids(iter(stream)) == [1]
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            iter(stream)
        with pytest.raises(SnapshotStreamStateError, match="inside its own scope"):
            _ = stream.pin


def test_a_closed_stream_answers_nothing_at_all() -> None:
    port = _pages([_order_row(1)])
    stream = _orders(port).stream(_all_orders())
    with stream:
        pass
    with pytest.raises(SnapshotStreamStateError, match="inside its own scope"):
        _ = stream.pin
    with pytest.raises(SnapshotStreamStateError, match="single-pass"):
        iter(stream)
    with pytest.raises(SnapshotStreamStateError, match="entered exactly once"):
        stream.__enter__()


def test_the_pin_answers_before_the_first_page_and_matches_the_eager_read() -> None:
    # A stream computes its pin from the query rather than from a result, so it
    # is available before a single row is read and no page can revise what the
    # caller was already told.
    port = _pages([_order_row(1), _order_row(2)])
    eager = _orders(_pages([_order_row(1)])).find(_all_orders())
    with _orders(port).stream(_all_orders(), batch_size=2) as stream:
        assert stream.pin == eager.pin
        assert _reads(port) == []
        roots = iter(stream)
        next(roots)
        assert stream.pin == eager.pin


def test_the_read_gate_runs_at_entry_and_before_any_io() -> None:
    # The same gate an eager read crosses, in the same position relative to I/O:
    # a target the connected model does not declare is refused at entry, by a
    # port that raises if it is touched at all.
    stream = Database(NoIoPort(), ACCOUNT).stream(_all_orders())
    with pytest.raises(QueryTargetError):
        stream.__enter__()


def test_the_repr_names_the_target_and_the_state_and_nothing_else() -> None:
    # A stream reports what it is and where it stands. Nothing about the page
    # plan, the cursor, or the port is readable off it.
    stream = Database(NoIoPort(), ORDERS_MODEL).stream(_all_orders())
    assert repr(stream) == "SnapshotStream(target='parallax.compatibility.Order', state='created')"


# --------------------------------------------------------------------------- #
# A participating stream delivers through the transaction it was opened in.    #
# --------------------------------------------------------------------------- #
def test_a_participating_stream_delivers_its_roots_inside_the_transaction() -> None:
    port = _pages([_order_row(1), _order_row(2)], [_order_row(3)])

    def body(tx: Transaction) -> list[int]:
        with tx.stream(_all_orders(), batch_size=2) as stream:
            return _ids(iter(stream))

    assert _orders(port).transact(body) == [1, 2, 3]


def test_a_participating_wire_stream_delivers_the_same_roots() -> None:
    port = _pages([_order_row(1), _order_row(2)], [_order_row(3)])

    def body(tx: Transaction) -> list[int]:
        with tx.wire.stream(_all_orders(), batch_size=2) as stream:
            return [cast("int", _entity(root)["id"]) for root in stream]

    assert _orders(port).transact(body) == [1, 2, 3]


def test_a_participating_stream_validates_its_page_size_at_the_call() -> None:
    port = _pages([])

    def body(tx: Transaction) -> None:
        with pytest.raises(ValueError, match="positive built-in int"):
            tx.stream(_all_orders(), batch_size=0)
        with pytest.raises(ValueError, match="positive built-in int"):
            tx.wire.stream(_all_orders(), batch_size=0)

    _orders(port).transact(body)
    assert _reads(port) == []


# --------------------------------------------------------------------------- #
# `batch_size` validation — `limit`'s idiom, at the call.                      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("size", [0, -1, True, 1.5, "10", None])
def test_a_batch_size_that_is_not_a_positive_int_is_refused_at_the_call(size: object) -> None:
    # An identity check, so nothing is coerced and `True` is not the page size 1.
    # The refusal lands at the call, before a plan or a page exists.
    port = _pages([])
    with pytest.raises(ValueError, match="positive built-in int"):
        _orders(port).stream(_all_orders(), batch_size=cast("int", size))
    with pytest.raises(ValueError, match="positive built-in int"):
        _orders(port).wire.stream(_all_orders(), batch_size=cast("int", size))
    assert _reads(port) == []


def test_the_default_page_size_is_one_thousand_root_positions() -> None:
    port = _pages([_order_row(1)])
    with _orders(port).stream(_all_orders()) as stream:
        list(stream)
    assert cast("tuple[object, ...]", _reads(port)[0][2])[-1] == 1000


# --------------------------------------------------------------------------- #
# Statement accounting: a page is an eager read of a bounded root query.       #
# --------------------------------------------------------------------------- #
def test_a_result_with_no_roots_costs_one_statement() -> None:
    # A page with no roots gathers no parent keys, so no child level issues SQL
    # and the short page proves exhaustion in the same breath.
    port = _pages([])
    with _orders(port).stream(_all_orders().include(Order.items), batch_size=2) as stream:
        assert list(stream) == []
    assert len(_reads(port)) == 1


def test_each_nonempty_page_costs_one_plus_l_and_a_short_page_ends_the_stream() -> None:
    port = _pages(
        [_order_row(1), _order_row(2)],
        [_item_row(10, 1), _item_row(11, 2)],
        [_order_row(3)],
        [_item_row(12, 3)],
    )
    with _orders(port).stream(_all_orders().include(Order.items), batch_size=2) as stream:
        assert _ids(iter(stream)) == [1, 2, 3]
    assert len(_reads(port)) == 4


def test_a_full_final_page_costs_one_more_empty_root_statement() -> None:
    # A full page proves nothing about what follows it, so exhaustion costs one
    # more root statement returning nothing. That empty page is still a page.
    port = _pages(
        [_order_row(1), _order_row(2)],
        [_item_row(10, 1), _item_row(11, 2)],
        [],
    )
    with _orders(port).stream(_all_orders().include(Order.items), batch_size=2) as stream:
        assert _ids(iter(stream)) == [1, 2]
    assert len(_reads(port)) == 3


def test_a_delivered_limit_ends_the_stream_without_a_further_statement() -> None:
    # A declared `limit` caps total roots and sizes the final page, so a limit
    # delivered in full is exhaustion already proved.
    port = _pages([_order_row(1), _order_row(2)], [_item_row(10, 1), _item_row(11, 2)])
    query = _all_orders().include(Order.items).limit(2)
    with _orders(port).stream(query, batch_size=2) as stream:
        assert _ids(iter(stream)) == [1, 2]
    assert len(_reads(port)) == 2


def test_a_limit_narrower_than_the_page_sizes_the_page_it_caps() -> None:
    port = _pages([_order_row(1)])
    with _orders(port).stream(_all_orders().limit(1), batch_size=100) as stream:
        assert _ids(iter(stream)) == [1]
    assert cast("tuple[object, ...]", _reads(port)[0][2])[-1] == 1


def test_a_limit_wider_than_the_result_still_ends_on_the_short_page() -> None:
    port = _pages([_order_row(1)])
    with _orders(port).stream(_all_orders().limit(50), batch_size=2) as stream:
        assert _ids(iter(stream)) == [1]
    assert len(_reads(port)) == 1


def test_leaving_the_loop_early_reads_no_further_page() -> None:
    port = _pages([_order_row(1), _order_row(2)], [_order_row(3), _order_row(4)])
    with _orders(port).stream(_all_orders(), batch_size=2) as stream:
        for root in stream:
            assert root.id == 1
            break
    assert len(_reads(port)) == 1


def test_a_later_page_seeks_past_the_last_root_of_the_page_before_it() -> None:
    # The cursor falls out of publication: the last root delivered is what the
    # next page's own predicate binds against.
    port = _pages([_order_row(1), _order_row(2)], [_order_row(5)])
    with _orders(port).stream(_all_orders(), batch_size=2) as stream:
        assert _ids(iter(stream)) == [1, 2, 5]
    first, second = _reads(port)
    assert "t0.id >" not in cast("str", first[1])
    assert "t0.id >" in cast("str", second[1])
    assert cast("tuple[object, ...]", second[2])[-2] == 2


# --------------------------------------------------------------------------- #
# `batch_size` is a performance dial and nothing else.                         #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("size", [1, 2, 3, 5])
def test_the_root_sequence_is_the_same_at_every_page_size(size: int) -> None:
    rows = [_order_row(index) for index in range(1, 4)]
    pages = [rows[start : start + size] for start in range(0, len(rows), size)]
    port = _pages(*pages)
    with _orders(port).stream(_all_orders(), batch_size=size) as stream:
        assert _ids(iter(stream)) == [1, 2, 3]


# --------------------------------------------------------------------------- #
# Identity: root-local, in both namespaces.                                    #
# --------------------------------------------------------------------------- #
def _diamond_pages() -> RecordingPort:
    return _pages(
        [_order_row(1)],
        [_item_row(10, 1)],
        [_item_row(10, 1)],
    )


def test_a_within_root_diamond_is_one_node_under_find_and_under_stream() -> None:
    # Two include paths reaching one row inside ONE root's tree collapse onto a
    # single node either way: root scoping narrows what identity spans, never
    # what it resolves within a root.
    query = _all_orders().include(Order.items, Order.items_by_ship_date)
    eager = _orders(_diamond_pages()).find(query).results()[0]
    assert eager.items[0] is eager.items_by_ship_date[0]

    with _orders(_diamond_pages()).stream(query, batch_size=2) as stream:
        streamed = next(iter(stream))
    assert streamed.items[0] is streamed.items_by_ship_date[0]


def test_a_within_root_diamond_publishes_the_same_wire_value_under_both() -> None:
    # The Wire lane bounds its walk by the requested Include Paths rather than
    # by the identity graph, so two positions of one tree are two positions
    # however alike their subtrees look — under `find` exactly as under
    # `stream`. What root scoping may not change is the VALUE either publishes.
    query = _all_orders().include(Order.items, Order.items_by_ship_date)
    eager = _entity(_orders(_diamond_pages()).wire.find(query).results()[0])
    with _orders(_diamond_pages()).wire.stream(query, batch_size=2) as stream:
        streamed = _entity(next(iter(stream)))
    assert streamed == eager
    assert (
        cast("list[object]", streamed["items"])[0]
        == (cast("list[object]", streamed["itemsByShipDate"])[0])
    )


def _back_reference_pages() -> RecordingPort:
    return _pages([_order_row(1)], [_item_row(10, 1)])


def test_a_back_reference_closes_the_cycle_under_find_and_under_stream() -> None:
    # A back-reference level issues no SQL and resolves through the merge's own
    # graph-local identity map, which a root-scoped merge still has.
    query = _all_orders().include(Order.items.order)
    eager = _orders(_back_reference_pages()).find(query).results()[0]
    assert eager.items[0].order is eager

    with _orders(_back_reference_pages()).stream(query, batch_size=2) as stream:
        streamed = next(iter(stream))
    assert streamed.items[0].order is streamed


def test_a_back_reference_publishes_the_same_wire_value_under_both() -> None:
    # A Wire back-reference unwinds finitely along the include tree rather than
    # closing a pointer cycle, and a streamed read unwinds the identical tree.
    query = _all_orders().include(Order.items.order)
    eager = _entity(_orders(_back_reference_pages()).wire.find(query).results()[0])
    with _orders(_back_reference_pages()).wire.stream(query, batch_size=2) as stream:
        streamed = _entity(next(iter(stream)))
    assert streamed == eager
    items = cast("list[Mapping[str, object]]", streamed["items"])
    assert cast("Mapping[str, object]", items[0]["order"])["id"] == 1


def _shared_to_one_pages() -> RecordingPort:
    return _pages([_status_row(1, 7), _status_row(2, 7)], [_order_row(7)])


def _shared_query() -> ObjectQuery[OrderStatus, OrderStatus]:
    return OrderStatus.where(OrderStatus.order_id == 7).include(OrderStatus.order)


def test_a_to_one_two_roots_reach_is_one_node_under_find_and_one_per_root_streamed() -> None:
    # The single divergence root-local identity introduces, stated from both
    # sides. Sharing across roots stays PERMITTED for an eager read and is not
    # PROMISED for either, so the streamed answer is the contract and the eager
    # one is what it happens to do.
    eager = _orders(_shared_to_one_pages()).find(_shared_query()).results()
    assert eager[0].order is eager[1].order

    with _orders(_shared_to_one_pages()).stream(_shared_query(), batch_size=2) as stream:
        streamed = list(stream)
    first, second = streamed[0].order, streamed[1].order
    assert first is not second
    assert first is not None
    assert second is not None
    assert first.id == second.id == 7


def test_a_to_one_two_roots_reach_diverges_the_same_way_in_the_wire_namespace() -> None:
    eager = [
        _entity(root)
        for root in _orders(_shared_to_one_pages()).wire.find(_shared_query()).results()
    ]
    assert eager[0]["order"] is eager[1]["order"]

    with _orders(_shared_to_one_pages()).wire.stream(_shared_query(), batch_size=2) as stream:
        streamed = [_entity(root) for root in stream]
    first = cast("Mapping[str, object]", streamed[0]["order"])
    second = cast("Mapping[str, object]", streamed[1]["order"])
    assert first is not second
    assert first["id"] == second["id"] == 7


# --------------------------------------------------------------------------- #
# A keyless root ends the stream from any position.                            #
# --------------------------------------------------------------------------- #
def _keyless_pages(position: int, *, size: int) -> RecordingPort:
    rows = [_order_row(1), _order_row(2), _order_row(3)]
    rows[position] = _keyless_order_row()
    return _pages(*[rows[start : start + size] for start in range(0, len(rows), size)])


@pytest.mark.parametrize("position", [0, 1, 2], ids=["first", "middle", "last"])
@pytest.mark.parametrize("size", [2, 3])
def test_the_checked_view_delivers_a_keyless_root_and_then_refuses_to_continue(
    position: int, size: int
) -> None:
    # The rule is positional-independent so `batch_size` cannot change it: the
    # same corrupt row may not be survivable at one page size and fatal at
    # another. What the caller gets is every root up to and including the
    # keyless one, and then the reason there is no more.
    delivered: list[object] = []
    with (
        _orders(_keyless_pages(position, size=size)).stream(
            _all_orders(), batch_size=size
        ) as stream,
        pytest.raises(SnapshotStreamStateError, match="keyless-root"),
    ):
        for root in stream.checked():
            delivered.append(root)
    assert len(delivered) == position + 1
    assert isinstance(delivered[-1], InvalidData)


@pytest.mark.parametrize("position", [0, 1, 2], ids=["first", "middle", "last"])
@pytest.mark.parametrize("size", [2, 3])
def test_the_default_view_raises_at_a_keyless_root_from_any_position(
    position: int, size: int
) -> None:
    delivered: list[object] = []
    with (
        _orders(_keyless_pages(position, size=size)).stream(
            _all_orders(), batch_size=size
        ) as stream,
        pytest.raises(InvalidDataError),
    ):
        for root in stream:
            delivered.append(root)
    assert len(delivered) == position


def test_a_stream_that_failed_answers_nothing_further() -> None:
    port = _keyless_pages(0, size=2)
    with _orders(port).stream(_all_orders(), batch_size=2) as stream:
        with pytest.raises(InvalidDataError):
            list(stream)
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            iter(stream)
