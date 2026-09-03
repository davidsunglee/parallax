"""Snapshot Stream delivery tests: ``db.stream`` and ``db.wire.stream``.

Drives the real seam end to end against a canned `m-db-port` (no Docker) — the
delivery loop, the page reader, and per-root publication through both
materializers — so what these assert is what a streamed read answers.

Four claims bound the suite. The state table IS the enforcement, so every one of
its cells is graded rather than only the reachable ones. Statement accounting is
what makes "a page is an eager read" observable: each nonempty page costs the
same `1 + L` a whole eager read costs, and a full final page costs one more root
statement returning nothing unless a declared ``limit`` was already delivered.
Identity is root-local, which is a NARROWING of what an eager read happens to do
rather than a second identity rule, so the within-root half is asserted to agree
with ``find`` and the cross-root half to diverge from it, in both namespaces.
And invalid stored data inside the Continuation Order itself ends no checked
delivery: a delivery advances on the coordinate the database evaluated, so a root
whose sort key contradicts the model is published and the delivery continues past
it, from whatever position and page size it lands in — which is what keeps
``batch_size`` a performance dial over storage the model describes. A stored
``NULL`` where a non-nullable primary key belongs is storage the model does not
describe, and it is graded where a delivery is bound to reach it: a first page
carries no seek, so that root is published and the delivery exhausts past it,
while a continuing page's hoisted leading range may exclude such a root instead
of delivering it.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterator, Mapping
from decimal import Decimal
from typing import Any, Final, cast

import pytest
from _transact_support import ACCOUNT, db_for

from _support.db_port import (
    Read,
    ReadCall,
    RefusingPort,
    ScriptedPort,
    Transact,
)
from parallax.conformance.graph_models import POLICY_MODEL, Policy
from parallax.conformance.story_models import (
    ORDERS_MODEL,
    POSITION_MODEL,
    Order,
    OrderStatus,
    Position,
)
from parallax.core.db_port import DbPort, Row
from parallax.core.object_query import TX_TIME, VALID_TIME
from parallax.core.object_query._fluent import ObjectQuery
from parallax.core.temporal_read import Edge, Pin
from parallax.snapshot import (
    DeferredFeatureError,
    InvalidData,
    InvalidDataError,
    QueryTargetError,
    SnapshotStreamStateError,
    WireEntity,
    edge_of,
    pin_of,
)
from parallax.snapshot._inspection import snapshot_state_of
from parallax.snapshot.handle import Database, Transaction
from parallax.snapshot.materialize import source_hint_of

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


def _orders(port: DbPort) -> Database:
    return db_for(ORDERS_MODEL, port)


def _reads(port: ScriptedPort) -> list[ReadCall]:
    return [op for op in port.calls if isinstance(op, ReadCall)]


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
    stream = Database(RefusingPort(), ORDERS_MODEL).stream(_all_orders())
    with pytest.raises(SnapshotStreamStateError, match="inside its own scope"):
        _ = stream.pin
    with pytest.raises(SnapshotStreamStateError, match="single-pass"):
        iter(stream)
    with pytest.raises(SnapshotStreamStateError, match="single-pass"):
        stream.checked()


def test_entering_twice_is_refused() -> None:
    port = ScriptedPort()
    with (
        _orders(port).stream(_all_orders()) as stream,
        pytest.raises(SnapshotStreamStateError, match="entered exactly once"),
    ):
        stream.__enter__()


def test_entering_while_draining_is_refused() -> None:
    port = ScriptedPort(Read(rows=[_order_row(1)]))
    with _orders(port).stream(_all_orders()) as stream:
        roots = iter(stream)
        next(roots)
        with pytest.raises(SnapshotStreamStateError, match="entered exactly once"):
            stream.__enter__()


def test_a_second_view_of_either_kind_is_refused() -> None:
    # Sharper than it strictly had to be, deliberately: a second pass over a
    # single-pass delivery is an error rather than a silent empty one.
    port = ScriptedPort(Read(rows=[_order_row(1)]))
    with _orders(port).stream(_all_orders()) as stream:
        list(stream)
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            iter(stream)
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            stream.checked()

    port = ScriptedPort(Read(rows=[_order_row(1)]))
    with _orders(port).stream(_all_orders()) as stream:
        list(stream.checked())
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            stream.checked()
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            iter(stream)


def test_an_exhausted_stream_answers_nothing_further() -> None:
    port = ScriptedPort(Read(rows=[_order_row(1)]))
    with _orders(port).stream(_all_orders()) as stream:
        assert _ids(iter(stream)) == [1]
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            iter(stream)
        with pytest.raises(SnapshotStreamStateError, match="inside its own scope"):
            _ = stream.pin


def test_a_closed_stream_answers_nothing_at_all() -> None:
    port = ScriptedPort()
    stream = _orders(port).stream(_all_orders())
    with stream:
        pass
    with pytest.raises(SnapshotStreamStateError, match="inside its own scope"):
        _ = stream.pin
    with pytest.raises(SnapshotStreamStateError, match="single-pass"):
        iter(stream)
    with pytest.raises(SnapshotStreamStateError, match="entered exactly once"):
        stream.__enter__()


def test_an_iterator_retained_past_the_scope_reads_nothing_and_yields_nothing() -> None:
    # A view is taken inside the scope but consumed lazily, so every ADVANCE is
    # its own entry point: an iterator first advanced after the scope closed
    # issues no statement, publishes no root, and leaves the closed state
    # standing rather than settling an exhausted one over it.
    port = ScriptedPort()
    stream = _orders(port).stream(_all_orders(), batch_size=1)
    with stream:
        roots = iter(stream)
    assert _reads(port) == []
    with pytest.raises(SnapshotStreamStateError, match="inside its own scope"):
        next(roots)
    assert _reads(port) == []
    assert repr(stream).endswith("state='closed')")


def test_a_partly_drained_stream_does_not_resume_past_its_scope() -> None:
    # The same rule at the harder position: the delivery is under way and the
    # generator holds a live cursor, and it still reaches no page once the scope
    # that answered it has closed.
    port = ScriptedPort(Read(rows=[_order_row(1)]))
    stream = _orders(port).stream(_all_orders(), batch_size=1)
    with stream:
        roots = iter(stream)
        assert next(roots).id == 1
    drained = len(_reads(port))
    with pytest.raises(SnapshotStreamStateError, match="inside its own scope"):
        next(roots)
    assert len(_reads(port)) == drained


@pytest.mark.parametrize("view", ["default", "checked"])
def test_every_advance_past_the_scope_refuses_again_rather_than_ending(view: str) -> None:
    # Each ADVANCE is an entry point of its own, so the refusal is not spent by
    # the first one that meets it: a caller looping over a retained view sees the
    # named error every time rather than an empty iteration after the first.
    port = ScriptedPort(Read(rows=[_order_row(1), _order_row(2)]), Read(rows=[]))
    stream = _orders(port).stream(_all_orders(), batch_size=1)
    with stream:
        roots = iter(stream) if view == "default" else stream.checked()
    for _ in range(3):
        with pytest.raises(SnapshotStreamStateError, match="inside its own scope"):
            next(roots)
    assert _reads(port) == []
    assert repr(stream).endswith("state='closed')")


def test_an_exhausted_view_ends_inside_its_scope_and_refuses_outside_it() -> None:
    # Exhaustion is not a refusal: a delivery that ran out keeps answering
    # `StopIteration` while its scope stands, so the iterator protocol holds. The
    # scope rule then applies to it like everything else the stream exposes.
    port = ScriptedPort(Read(rows=[_order_row(1)]), Read(rows=[]))
    stream = _orders(port).stream(_all_orders(), batch_size=1)
    with stream:
        roots = iter(stream)
        assert [root.id for root in roots] == [1]
        with pytest.raises(StopIteration):
            next(roots)
        assert repr(stream).endswith("state='exhausted')")
    with pytest.raises(SnapshotStreamStateError, match="inside its own scope"):
        next(roots)


def test_the_pin_answers_before_the_first_page_and_matches_the_eager_read() -> None:
    # A stream computes its pin from the query rather than from a result, so it
    # is available before a single row is read and no page can revise what the
    # caller was already told.
    port = ScriptedPort(Read(rows=[_order_row(1), _order_row(2)]))
    eager = _orders(ScriptedPort(Read(rows=[_order_row(1)]))).find(_all_orders())
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
    stream = Database(RefusingPort(), ACCOUNT).stream(_all_orders())
    with pytest.raises(QueryTargetError):
        stream.__enter__()


def test_the_repr_names_the_target_and_the_state_and_nothing_else() -> None:
    # A stream reports what it is and where it stands. Nothing about the page
    # plan, the cursor, or the port is readable off it.
    stream = Database(RefusingPort(), ORDERS_MODEL).stream(_all_orders())
    assert repr(stream) == "SnapshotStream(target='parallax.compatibility.Order', state='created')"


# --------------------------------------------------------------------------- #
# A participating stream delivers through the transaction it was opened in.    #
# --------------------------------------------------------------------------- #
def test_a_participating_stream_delivers_its_roots_inside_the_transaction() -> None:
    port = ScriptedPort(
        Transact(Read(rows=[_order_row(1), _order_row(2)]), Read(rows=[_order_row(3)]))
    )

    def body(tx: Transaction) -> list[int]:
        with tx.stream(_all_orders(), batch_size=2) as stream:
            return _ids(iter(stream))

    assert _orders(port).transact(body) == [1, 2, 3]


def test_a_participating_wire_stream_delivers_the_same_roots() -> None:
    port = ScriptedPort(
        Transact(Read(rows=[_order_row(1), _order_row(2)]), Read(rows=[_order_row(3)]))
    )

    def body(tx: Transaction) -> list[int]:
        with tx.wire.stream(_all_orders(), batch_size=2) as stream:
            return [cast("int", _entity(root)["id"]) for root in stream]

    assert _orders(port).transact(body) == [1, 2, 3]


def test_a_participating_stream_validates_its_page_size_at_the_call() -> None:
    port = ScriptedPort(Transact())

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
    port = ScriptedPort()
    with pytest.raises(ValueError, match="positive built-in int"):
        _orders(port).stream(_all_orders(), batch_size=cast("int", size))
    with pytest.raises(ValueError, match="positive built-in int"):
        _orders(port).wire.stream(_all_orders(), batch_size=cast("int", size))
    assert _reads(port) == []


def test_the_default_page_size_is_one_thousand_root_positions() -> None:
    port = ScriptedPort(Read(rows=[_order_row(1)]))
    with _orders(port).stream(_all_orders()) as stream:
        list(stream)
    assert _reads(port)[0].binds[-1] == 1000


# --------------------------------------------------------------------------- #
# Statement accounting: a page is an eager read of a bounded root query.       #
# --------------------------------------------------------------------------- #
def test_a_result_with_no_roots_costs_one_statement() -> None:
    # A page with no roots gathers no parent keys, so no child level issues SQL
    # and the short page proves exhaustion in the same breath.
    port = ScriptedPort(Read(rows=[]))
    with _orders(port).stream(_all_orders().include(Order.items), batch_size=2) as stream:
        assert list(stream) == []
    assert len(_reads(port)) == 1


def test_each_nonempty_page_costs_one_plus_l_and_a_short_page_ends_the_stream() -> None:
    port = ScriptedPort(
        Read(rows=[_order_row(1), _order_row(2)]),
        Read(rows=[_item_row(10, 1), _item_row(11, 2)]),
        Read(rows=[_order_row(3)]),
        Read(rows=[_item_row(12, 3)]),
    )
    with _orders(port).stream(_all_orders().include(Order.items), batch_size=2) as stream:
        assert _ids(iter(stream)) == [1, 2, 3]
    assert len(_reads(port)) == 4


def test_a_full_final_page_costs_one_more_empty_root_statement() -> None:
    # A full page proves nothing about what follows it, so exhaustion costs one
    # more root statement returning nothing. That empty page is still a page.
    port = ScriptedPort(
        Read(rows=[_order_row(1), _order_row(2)]),
        Read(rows=[_item_row(10, 1), _item_row(11, 2)]),
        Read(rows=[]),
    )
    with _orders(port).stream(_all_orders().include(Order.items), batch_size=2) as stream:
        assert _ids(iter(stream)) == [1, 2]
    assert len(_reads(port)) == 3


def test_a_delivered_limit_ends_the_stream_without_a_further_statement() -> None:
    # A declared `limit` caps total roots and sizes the final page, so a limit
    # delivered in full is exhaustion already proved.
    port = ScriptedPort(
        Read(rows=[_order_row(1), _order_row(2)]), Read(rows=[_item_row(10, 1), _item_row(11, 2)])
    )
    query = _all_orders().include(Order.items).limit(2)
    with _orders(port).stream(query, batch_size=2) as stream:
        assert _ids(iter(stream)) == [1, 2]
    assert len(_reads(port)) == 2


def test_a_limit_narrower_than_the_page_sizes_the_page_it_caps() -> None:
    port = ScriptedPort(Read(rows=[_order_row(1)]))
    with _orders(port).stream(_all_orders().limit(1), batch_size=100) as stream:
        assert _ids(iter(stream)) == [1]
    assert _reads(port)[0].binds[-1] == 1


def test_a_limit_wider_than_the_result_still_ends_on_the_short_page() -> None:
    port = ScriptedPort(Read(rows=[_order_row(1)]))
    with _orders(port).stream(_all_orders().limit(50), batch_size=2) as stream:
        assert _ids(iter(stream)) == [1]
    assert len(_reads(port)) == 1


def test_leaving_the_loop_early_reads_no_further_page() -> None:
    port = ScriptedPort(Read(rows=[_order_row(1), _order_row(2)]))
    with _orders(port).stream(_all_orders(), batch_size=2) as stream:
        for root in stream:
            assert root.id == 1
            break
    assert len(_reads(port)) == 1


def test_a_later_page_seeks_past_the_last_root_of_the_page_before_it() -> None:
    # The position falls out of the page rather than out of publication: what the
    # next page's seek binds is the coordinate the database evaluated for the last
    # root the page before it kept.
    port = ScriptedPort(Read(rows=[_order_row(1), _order_row(2)]), Read(rows=[_order_row(5)]))
    with _orders(port).stream(_all_orders(), batch_size=2) as stream:
        assert _ids(iter(stream)) == [1, 2, 5]
    first, second = _reads(port)
    assert "t0.id >" not in first.sql
    assert "t0.id >" in second.sql
    assert second.binds[-2] == 2


# --------------------------------------------------------------------------- #
# `batch_size` is a dial alone over storage the model describes.               #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("size", [1, 2, 3, 5])
def test_the_root_sequence_is_the_same_at_every_page_size(size: int) -> None:
    rows = [_order_row(index) for index in range(1, 4)]
    pages = [rows[start : start + size] for start in range(0, len(rows), size)]
    if len(rows) % size == 0:
        pages.append([])
    port = ScriptedPort(*(Read(rows=page) for page in pages))
    with _orders(port).stream(_all_orders(), batch_size=size) as stream:
        assert _ids(iter(stream)) == [1, 2, 3]


# --------------------------------------------------------------------------- #
# Identity: root-local, in both namespaces.                                    #
# --------------------------------------------------------------------------- #
def _diamond_pages() -> ScriptedPort:
    return ScriptedPort(
        Read(rows=[_order_row(1)]),
        Read(rows=[_item_row(10, 1)]),
        Read(rows=[_item_row(10, 1)]),
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


def _back_reference_pages() -> ScriptedPort:
    return ScriptedPort(Read(rows=[_order_row(1)]), Read(rows=[_item_row(10, 1)]))


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


def _shared_to_one_pages() -> ScriptedPort:
    return ScriptedPort(
        Read(rows=[_status_row(1, 7), _status_row(2, 7)]), Read(rows=[_order_row(7)]), Read()
    )


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
# Invalid stored data inside the Continuation Order itself.                    #
# --------------------------------------------------------------------------- #
def _undecodable_qty_row() -> Row:
    return {**_order_row(0), "qty": "many"}


def _by_qty() -> ObjectQuery[Order, Order]:
    return _all_orders().order_by(Order.qty.asc())


def _corrupt_pages(row: Callable[[], Row], position: int, *, size: int) -> ScriptedPort:
    rows = [_order_row(1), _order_row(2), _order_row(3)]
    rows[position] = row()
    pages = [rows[start : start + size] for start in range(0, len(rows), size)]
    if len(rows) % size == 0:
        pages.append([])
    return ScriptedPort(*(Read(rows=page) for page in pages))


@pytest.mark.parametrize("position", [0, 1, 2], ids=["first", "middle", "last"])
@pytest.mark.parametrize("size", [2, 3])
def test_a_checked_delivery_continues_past_an_invalid_sort_key(position: int, size: int) -> None:
    # Invalid stored data ends no checked delivery, and it ends none at any
    # position or page size, so `batch_size` stays a performance dial: a root whose
    # ORDERED-BY member contradicts the model is published as its record and the
    # delivery carries on, because what the next page seeks past is the value the
    # database's own `order by` expression evaluated — which exists whatever the
    # stored value turned out to be.
    with _orders(_corrupt_pages(_undecodable_qty_row, position, size=size)).stream(
        _by_qty(), batch_size=size
    ) as stream:
        delivered = list(stream.checked())
    assert len(delivered) == 3
    assert [isinstance(root, InvalidData) for root in delivered] == [
        index == position for index in range(3)
    ]


@pytest.mark.parametrize("position", [0, 1, 2], ids=["first", "middle", "last"])
@pytest.mark.parametrize("size", [2, 3])
def test_the_default_view_still_stops_at_the_first_invalid_root(position: int, size: int) -> None:
    # The throwing view stays fail-fast: continuation is what changed, not the
    # default view's refusal, so the caller gets every root ahead of the corrupt
    # one and then the refusal.
    delivered: list[object] = []
    with (
        _orders(_corrupt_pages(_undecodable_qty_row, position, size=size)).stream(
            _by_qty(), batch_size=size
        ) as stream,
        pytest.raises(InvalidDataError),
    ):
        for root in stream:
            delivered.append(root)
    assert len(delivered) == position


def test_a_root_whose_primary_key_did_not_decode_is_delivered_and_placed_last() -> None:
    # A stored NULL where the primary key belongs is a coordinate like any
    # other, and the ordering itself says where it stands: `order by t0.id asc`
    # places a NULL last on this dialect, so nothing follows it and the seek
    # past it admits no root at all. The delivery publishes the record and then
    # exhausts on an ordinary statement that returns nothing — rather than
    # refusing to continue.
    port = ScriptedPort(Read(rows=[_order_row(1), _keyless_order_row()]), Read(rows=[]))
    with _orders(port).stream(_all_orders(), batch_size=2) as stream:
        delivered = list(stream.checked())
    assert [isinstance(root, InvalidData) for root in delivered] == [False, True]
    assert _reads(port)[1].sql.endswith(
        "where t0.active = %s and 1 = 0 order by t0.id asc limit %s"
    )


def test_a_stream_that_failed_answers_nothing_further() -> None:
    port = _corrupt_pages(_undecodable_qty_row, 0, size=2)
    with _orders(port).stream(_by_qty(), batch_size=2) as stream:
        with pytest.raises(InvalidDataError):
            list(stream)
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            iter(stream)


# --------------------------------------------------------------------------- #
# Milestone streaming: the Continuation Order's third component, and the pin   #
# every published root stands at.                                              #
# --------------------------------------------------------------------------- #
def _position_row(*, value: str, valid_start: dt.datetime, tx_start: dt.datetime) -> Row:
    return {
        "pos_id": 1,
        "acct_num": "A",
        "val": Decimal(value),
        "from_z": valid_start,
        "thru_z": _INFINITY,
        "in_z": tx_start,
        "out_z": _INFINITY,
    }


_INFINITY = dt.datetime(9999, 12, 31, tzinfo=_UTC)
_JANUARY = dt.datetime(2024, 1, 1, tzinfo=_UTC)
_APRIL = dt.datetime(2024, 4, 1, tzinfo=_UTC)
_JUNE = dt.datetime(2024, 6, 1, tzinfo=_UTC)

# `models/position.yaml`'s own rectangle history, one root per milestone: the
# original belief, the rectangle-split head, and the corrected value. The first
# two TIE on the Valid-Time start and part on the Transaction-Time one, which is
# the tie depth the edge's own lexicographic seek exists for.
_MILESTONES: Final[tuple[Row, ...]] = (
    _position_row(value="90.00", valid_start=_JANUARY, tx_start=_JANUARY),
    _position_row(value="100.00", valid_start=_JANUARY, tx_start=_APRIL),
    _position_row(value="200.00", valid_start=_JUNE, tx_start=_APRIL),
)


def _positions(port: DbPort) -> Database:
    return db_for(POSITION_MODEL, port)


def _all_milestones() -> ObjectQuery[Position, Position]:
    return Position.where(Position.id == 1).history(TX_TIME).history(VALID_TIME)


def _milestone_pages(*, size: int) -> ScriptedPort:
    pages = [list(_MILESTONES[start : start + size]) for start in range(0, len(_MILESTONES), size)]
    if len(_MILESTONES) % size == 0:
        pages.append([])
    return ScriptedPort(*(Read(rows=page) for page in pages))


@pytest.mark.parametrize("size", [1, 2, 3], ids=lambda size: f"batch-{size}")
def test_a_streamed_milestone_set_publishes_every_milestone_at_its_own_edge_pin(
    size: int,
) -> None:
    # A page graph is shared input and a milestone page is that page plus a pin
    # per root: each published root stands at its OWN milestone's from-instant on
    # both axes, never at the page's own pin and never at another milestone's —
    # at every page size, because the pin is a property of the root rather than
    # of the page it arrived in.
    with _positions(_milestone_pages(size=size)).stream(_all_milestones(), batch_size=size) as (
        stream
    ):
        assert stream.pin == Pin()
        roots = list(stream)
    assert [root.value for root in roots] == [
        Decimal("90.00"),
        Decimal("100.00"),
        Decimal("200.00"),
    ]
    assert [pin_of(root) for root in roots] == [
        Pin(valid_time=_JANUARY, tx_time=_JANUARY),
        Pin(valid_time=_JANUARY, tx_time=_APRIL),
        Pin(valid_time=_JUNE, tx_time=_APRIL),
    ]
    assert [edge_of(root) for root in roots] == [
        Edge(valid_time=_JANUARY, tx_time=_JANUARY),
        Edge(valid_time=_JANUARY, tx_time=_APRIL),
        Edge(valid_time=_JUNE, tx_time=_APRIL),
    ]


def test_a_streamed_milestone_set_seeks_past_the_edge_of_the_root_it_ended_on() -> None:
    # The page statements the delivery actually ran: the key is constant across
    # the whole result, so an order ending in it would seek `pos_id > 1` and
    # deliver ONE root. What each continuing page binds is the previous root's own
    # milestone, as the database evaluated the edge term for it and the page
    # captured it.
    port = _milestone_pages(size=1)
    with _positions(port).stream(_all_milestones(), batch_size=1) as stream:
        assert len(list(stream)) == 3
    binds = [op.binds for op in _reads(port)]
    assert binds == [
        (1, 1),
        (
            1,
            1,
            1,
            1,
            _JANUARY,
            1,
            _JANUARY,
            _JANUARY,
            1,
        ),
        (
            1,
            1,
            1,
            1,
            _JANUARY,
            1,
            _JANUARY,
            _APRIL,
            1,
        ),
        (
            1,
            1,
            1,
            1,
            _JUNE,
            1,
            _JUNE,
            _APRIL,
            1,
        ),
    ]


def test_a_streamed_milestone_set_delivers_what_the_whole_result_read_does() -> None:
    # `find_history` groups milestones into one graph each and ranks the graphs
    # Valid-Time-first; with no authored `orderBy` the Continuation Order is the
    # key then that same edge, so a single object's streamed history IS the eager
    # edge rank — same roots, same order, same pin on each, and the same absence
    # of retained write evidence, a milestone view being read-only either way.
    eager = _positions(ScriptedPort(Read(rows=list(_MILESTONES)))).find(_all_milestones())
    with _positions(_milestone_pages(size=1)).stream(_all_milestones(), batch_size=1) as stream:
        streamed = list(stream)
    published = eager.results()
    assert [root.value for root in streamed] == [root.value for root in published]
    assert [pin_of(root) for root in streamed] == [pin_of(root) for root in published]
    assert eager.pin == Pin()
    assert [_retained(root) for root in streamed] == [None, None, None]
    assert [_retained(root) for root in published] == [None, None, None]


def _retained(node: object) -> object:
    """One Typed node's own retained Source Hint, or ``None`` where it kept none."""
    state = snapshot_state_of(node)
    return None if state is None else state.source


def test_a_wire_streamed_milestone_root_retains_no_more_than_its_typed_peer() -> None:
    # The two namespaces answer one delivery. A Wire node keeps its whole
    # provenance — the pin included — in its Source Hint rather than in lifecycle
    # state, so a hint carrying the QUERY's coordinates would make a Wire-streamed
    # historical root writable where its Typed peer is refused.
    with _positions(_milestone_pages(size=2)).wire.stream(
        _all_milestones(), batch_size=2
    ) as stream:
        roots = [_entity(root) for root in stream]
    assert [root["value"] for root in roots] == ["90.00", "100.00", "200.00"]
    assert [source_hint_of(root) for root in roots] == [None, None, None]


def test_a_streamed_history_with_includes_is_refused_before_any_io() -> None:
    # Delivery adds no capability: history with includes is the staged
    # `snapshot-history-includes` feature, refused by the same gate at the same
    # point whichever delivery the caller asked for.
    query = (
        Policy.where(Policy.id == 1).history(TX_TIME).history(VALID_TIME).include(Policy.coverages)
    )
    with (
        pytest.raises(DeferredFeatureError, match="snapshot-history-includes"),
        Database(RefusingPort(), POLICY_MODEL).stream(query, batch_size=2),
    ):
        pass  # pragma: no cover - the gate refuses at scope entry


def test_a_milestone_root_whose_edge_did_not_decode_is_published_at_the_pages_pin() -> None:
    # The behavioural inversion the coordinate buys: a milestone root whose axis
    # starts did not decode has no edge of its own to be pinned at, so it is
    # published at the page's own pin — and the delivery continues past it,
    # seeking on the carriers the ordering expressions evaluated.
    broken = {**_MILESTONES[0], "in_z": None}
    port = ScriptedPort(Read(rows=[broken, _MILESTONES[1]]), Read(rows=[]))
    with _positions(port).stream(_all_milestones(), batch_size=2) as stream:
        delivered = list(stream.checked())
    assert [isinstance(root, InvalidData) for root in delivered] == [True, False]
    assert pin_of(delivered[1]) == Pin(valid_time=_JANUARY, tx_time=_APRIL)


def test_a_milestone_root_whose_key_did_not_decode_stands_at_no_edge() -> None:
    # The other half of the same rule, and the one shape that answers no member
    # at all: a root whose own primary key did not decode stands behind no
    # projection, so there is nothing to read a milestone off — and nothing about
    # that stops the delivery either.
    port = ScriptedPort(
        Read(rows=[{**_MILESTONES[0], "pos_id": None}, _MILESTONES[1]]), Read(rows=[])
    )
    with _positions(port).stream(_all_milestones(), batch_size=2) as stream:
        delivered = list(stream.checked())
    assert [isinstance(root, InvalidData) for root in delivered] == [True, False]


def _diagnoses(root: object) -> frozenset[object] | None:
    """``root``'s published diagnoses, or absence where it published as itself."""
    return (
        frozenset(cast("InvalidData[object]", root).issues)
        if isinstance(root, InvalidData)
        else None
    )


def test_an_eager_and_a_streamed_checked_read_publish_one_roots_issues_alike() -> None:
    # A page IS an eager read, so a diagnosis has to be too — down to the
    # evidence it carries. `qty` is outside this query's Continuation Order, so
    # the corrupt root is published and the delivery continues past it, which is
    # what lets the two readings be compared root for root.
    rows = [_order_row(1), {**_order_row(2), "qty": "many"}, _order_row(3)]
    eager = _orders(ScriptedPort(Read(rows=rows))).find(_all_orders()).checked().results()
    with _orders(ScriptedPort(Read(rows=rows[:2]), Read(rows=rows[2:]))).stream(
        _all_orders(), batch_size=2
    ) as stream:
        streamed = list(stream.checked())
    assert [_diagnoses(root) for root in eager] == [_diagnoses(root) for root in streamed]
    issues = _diagnoses(streamed[1])
    assert issues is not None
    (issue,) = cast("frozenset[Any]", issues)
    assert (issue.code, issue.path, issue.stored_value) == (
        "stored-data-leaf-undecodable",
        (),
        "many",
    )
