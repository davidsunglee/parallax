"""Snapshot Stream delivery tests: ``db.stream`` and ``db.wire.stream``.

Drives the real seam end to end against a canned `m-db-port` (no Docker) — the
delivery loop, the page reader, and per-root publication through both
materializers — so what these assert is what a streamed read answers.

Four claims bound the suite. The state table IS the enforcement, so every one of
its cells is graded rather than only the reachable ones. Statement accounting is
what makes "a page is an eager read" observable: each nonempty page costs the
same `1 + L` a whole eager read costs, and the lookahead root a page reads past
its batch is what ends the delivery without a terminal root statement, even where
the delivered roots fill the final page exactly.
Identity is root-local, which is a NARROWING of what an eager read happens to do
rather than a second identity rule, so the within-root half is asserted to agree
with ``find`` and the cross-root half to diverge from it, in both namespaces.
And invalid stored data inside the Continuation Order itself ends no checked
delivery: a delivery advances on the coordinate the database evaluated, so a root
whose sort key contradicts the model is published and the delivery continues past
it, from whatever position and page size it lands in. A direct leading Column's
NULL tail is retained by a second continuing-page arm, which is what keeps
``batch_size`` a performance dial even when storage lost a constraint.
"""

from __future__ import annotations

import datetime as dt
import gc
import weakref
from collections.abc import Callable, Iterator, Mapping
from decimal import Decimal
from typing import Any, Final, cast

import pytest

from parallax.conformance.graph_models import POLICY_MODEL, Policy
from parallax.conformance.story_models import (
    ORDERS_MODEL,
    POSITION_MODEL,
    Order,
    OrderStatus,
    Position,
)
from parallax.core.base import ManagedValue, NeutralType
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import DatabaseAdapter, MappingRow
from parallax.core.object_query import TX_TIME, VALID_TIME
from parallax.core.object_query._fluent import ObjectQuery
from parallax.core.temporal_read import Edge, Pin
from parallax.core.wire import encode_wire
from parallax.snapshot import (
    DeferredFeatureError,
    QueryTargetError,
    ServingModel,
    SnapshotStreamContinuationError,
    SnapshotStreamStateError,
    WireEntity,
    edge_of,
    pin_of,
    prepare_model,
)
from parallax.snapshot._inspection import snapshot_state_of
from parallax.snapshot.handle import (
    Database,
    ScopedDatabase,
    Transaction,
    _materialization,
    _read_plan,
)
from parallax.snapshot.materialize import _wire as wire_materialize
from parallax.snapshot.materialize import read_origin_of
from tests._support.adoption import raises_contextualized
from tests._support.db_port import (
    Read,
    ReadCall,
    RefusingAdapter,
    ScriptedAdapter,
    Transact,
)
from tests._support.root_ownership import own_root
from tests.unit._stream_page_support import paged_reads
from tests.unit._transact_support import ACCOUNT, db_for

_UTC = dt.UTC


def _order_row(order_id: int) -> MappingRow:
    return {
        "id": order_id,
        "name": f"order-{order_id}",
        "sku": "A-100",
        "qty": 5,
        "price": Decimal("10.50"),
        "active": True,
        "ordered_on": dt.date(2024, 1, 5),
    }


def _item_row(item_id: int, order_id: int) -> MappingRow:
    return {
        "id": item_id,
        "order_id": order_id,
        "sku": "SKU",
        "quantity": 1,
        "shipped_on": dt.date(2024, 2, 1),
    }


def _status_row(status_id: int, order_id: int) -> MappingRow:
    return {"id": status_id, "order_id": order_id, "order_item_id": None, "code": "NEW"}


def _orders(adapter: DatabaseAdapter) -> ScopedDatabase:
    return db_for(ORDERS_MODEL, adapter)


def _reads(port: ScriptedAdapter) -> list[ReadCall]:
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
    stream = (
        own_root(Database(RefusingAdapter(), ORDERS_MODEL))
        .using_database_login()
        .stream(_all_orders())
    )
    with pytest.raises(SnapshotStreamStateError, match="inside its own scope"):
        _ = stream.pin
    with pytest.raises(SnapshotStreamStateError, match="single-pass"):
        iter(stream)
    with pytest.raises(SnapshotStreamStateError, match="single-pass"):
        stream.checked()


def test_entering_twice_is_refused() -> None:
    port = ScriptedAdapter()
    with (
        _orders(port).stream(_all_orders()) as stream,
        pytest.raises(SnapshotStreamStateError, match="entered exactly once"),
    ):
        stream.__enter__()


def test_entering_while_draining_is_refused() -> None:
    port = ScriptedAdapter(Read(rows=[_order_row(1)]))
    with _orders(port).stream(_all_orders()) as stream:
        roots = iter(stream)
        next(roots)
        with pytest.raises(SnapshotStreamStateError, match="entered exactly once"):
            stream.__enter__()


def test_a_second_view_of_either_kind_is_refused() -> None:
    # Sharper than it strictly had to be, deliberately: a second pass over a
    # single-pass delivery is an error rather than a silent empty one.
    port = ScriptedAdapter(Read(rows=[_order_row(1)]))
    with _orders(port).stream(_all_orders()) as stream:
        list(stream)
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            iter(stream)
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            stream.checked()

    port = ScriptedAdapter(Read(rows=[_order_row(1)]))
    with _orders(port).stream(_all_orders()) as stream:
        list(stream.checked())
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            stream.checked()
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            iter(stream)


def test_an_exhausted_stream_answers_nothing_further() -> None:
    port = ScriptedAdapter(Read(rows=[_order_row(1)]))
    with _orders(port).stream(_all_orders()) as stream:
        assert _ids(iter(stream)) == [1]
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            iter(stream)
        with pytest.raises(SnapshotStreamStateError, match="inside its own scope"):
            _ = stream.pin


def test_a_closed_stream_answers_nothing_at_all() -> None:
    port = ScriptedAdapter()
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
    port = ScriptedAdapter()
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
    port = ScriptedAdapter(Read(rows=[_order_row(1)]))
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
    port = ScriptedAdapter(Read(rows=[_order_row(1), _order_row(2)]), Read(rows=[]))
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
    port = ScriptedAdapter(Read(rows=[_order_row(1)]), Read(rows=[]))
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
    port = ScriptedAdapter(Read(rows=[_order_row(1), _order_row(2)]))
    eager = _orders(ScriptedAdapter(Read(rows=[_order_row(1)]))).find(_all_orders())
    with _orders(port).stream(_all_orders(), batch_size=2) as stream:
        assert stream.pin == eager.pin
        assert stream.edition
        assert _reads(port) == []
        roots = iter(stream)
        next(roots)
        assert stream.pin == eager.pin


def test_the_read_gate_runs_at_entry_and_before_any_io() -> None:
    # The same gate an eager read crosses, in the same position relative to I/O:
    # a target the connected model does not declare is refused at entry, by a
    # port that raises if it is touched at all.
    stream = (
        own_root(Database(RefusingAdapter(), ACCOUNT)).using_database_login().stream(_all_orders())
    )
    with pytest.raises(QueryTargetError):
        stream.__enter__()


def test_the_repr_names_the_target_and_the_state_and_nothing_else() -> None:
    # A stream reports what it is and where it stands. Nothing about the page
    # plan, the cursor, or the port is readable off it.
    stream = (
        own_root(Database(RefusingAdapter(), ORDERS_MODEL))
        .using_database_login()
        .stream(_all_orders())
    )
    assert repr(stream) == "SnapshotStream(target='parallax.compatibility.Order', state='created')"


# --------------------------------------------------------------------------- #
# A participating stream delivers through the transaction it was opened in.    #
# --------------------------------------------------------------------------- #
def test_a_participating_stream_delivers_its_roots_inside_the_transaction() -> None:
    port = ScriptedAdapter(
        Transact(*paged_reads([_order_row(index) for index in (1, 2, 3)], size=2))
    )

    def body(tx: Transaction) -> list[int]:
        with tx.stream(_all_orders(), batch_size=2) as stream:
            return _ids(iter(stream))

    assert _orders(port).transact(body) == [1, 2, 3]


def test_a_participating_wire_stream_delivers_the_same_roots() -> None:
    port = ScriptedAdapter(
        Transact(*paged_reads([_order_row(index) for index in (1, 2, 3)], size=2))
    )

    def body(tx: Transaction) -> list[int]:
        with tx.wire.stream(_all_orders(), batch_size=2) as stream:
            return [cast("int", _entity(root)["id"]) for root in stream]

    assert _orders(port).transact(body) == [1, 2, 3]


def test_a_participating_stream_validates_its_page_size_at_the_call() -> None:
    port = ScriptedAdapter(Transact())

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
    port = ScriptedAdapter()
    with pytest.raises(ValueError, match="positive built-in int"):
        _orders(port).stream(_all_orders(), batch_size=cast("int", size))
    with pytest.raises(ValueError, match="positive built-in int"):
        _orders(port).wire.stream(_all_orders(), batch_size=cast("int", size))
    assert _reads(port) == []


def test_the_default_page_size_is_one_thousand_root_positions() -> None:
    # The default counts ROOT POSITIONS a page delivers, and the statement asks
    # for one more than that: the extra root is what proves whether a further
    # page exists, and it is never delivered.
    port = ScriptedAdapter(Read(rows=[_order_row(1)]))
    with _orders(port).stream(_all_orders()) as stream:
        list(stream)
    assert _reads(port)[0].binds[-1] == 1001


# --------------------------------------------------------------------------- #
# Statement accounting: a page is an eager read of a bounded root query.       #
# --------------------------------------------------------------------------- #
def test_a_result_with_no_roots_costs_one_statement() -> None:
    # A page with no roots gathers no parent keys, so no child level issues SQL
    # and the short page proves exhaustion in the same breath.
    port = ScriptedAdapter(Read(rows=[]))
    with _orders(port).stream(_all_orders().include(Order.items), batch_size=2) as stream:
        assert list(stream) == []
    assert len(_reads(port)) == 1


def test_each_nonempty_page_costs_one_plus_l_and_a_short_page_ends_the_stream() -> None:
    # Each page's child level gathers the keys of the roots that page KEPT, so
    # the lookahead root the first page discarded is fetched with the children of
    # the page that delivers it rather than with this one's.
    port = ScriptedAdapter(
        Read(rows=[_order_row(1), _order_row(2), _order_row(3)]),
        Read(rows=[_item_row(10, 1), _item_row(11, 2)]),
        Read(rows=[_order_row(3)]),
        Read(rows=[_item_row(12, 3)]),
    )
    with _orders(port).stream(_all_orders().include(Order.items), batch_size=2) as stream:
        assert _ids(iter(stream)) == [1, 2, 3]
    assert len(_reads(port)) == 4


def test_one_wire_encoder_reuses_equal_expensive_values_across_pages_and_not_deliveries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoded: list[object] = []
    variants: list[object] = []
    family_variant = wire_materialize._family_variant  # pyright: ignore[reportPrivateUsage]

    def counting_encode(neutral_type: NeutralType, value: ManagedValue) -> object:
        encoded.append(value)
        return encode_wire(neutral_type, value)

    def counting_variant(model: object, entity: object) -> str | None:
        variants.append(entity)
        return family_variant(model, entity)  # type: ignore[arg-type]

    monkeypatch.setattr(wire_materialize, "encode_managed_wire", counting_encode)
    monkeypatch.setattr(wire_materialize, "_family_variant", counting_variant)
    rows = [_order_row(index) for index in range(1, 4)]

    for _ in range(2):
        port = ScriptedAdapter(*paged_reads(rows, size=1))
        with _orders(port).wire.stream(_all_orders(), batch_size=1) as stream:
            assert [root["id"] for root in stream] == [1, 2, 3]

    assert encoded.count(Decimal("10.50")) == 2
    assert encoded.count(dt.date(2024, 1, 5)) == 2
    assert len(variants) == 2


def _observe_wire_encoders(
    monkeypatch: pytest.MonkeyPatch,
) -> list[weakref.ReferenceType[object]]:
    created: list[weakref.ReferenceType[object]] = []
    factory = wire_materialize.shared_wire_encoder

    class ObservedEncoder:
        def __init__(self) -> None:
            self.delegate = factory()

        def __call__(self, *args: Any) -> object:
            return self.delegate(*args)

        def begin_page(self) -> None:
            self.delegate.begin_page()

        def release(self) -> None:
            self.delegate.release()

    def observed_encoder() -> ObservedEncoder:
        encoder = ObservedEncoder()
        created.append(weakref.ref(encoder))
        return encoder

    monkeypatch.setattr(wire_materialize, "shared_wire_encoder", observed_encoder)
    return created


def test_an_exhausted_wire_stream_releases_its_encoder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = _observe_wire_encoders(monkeypatch)
    with _orders(ScriptedAdapter(Read(rows=[_order_row(1)]))).wire.stream(
        _all_orders(), batch_size=1
    ) as stream:
        assert [root["id"] for root in stream] == [1]
        gc.collect()
        assert len(created) == 1
        assert created[0]() is None


def test_a_failed_wire_stream_releases_its_encoder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = _observe_wire_encoders(monkeypatch)
    failure = DatabaseError(category=None, native_code=None, message="the later page failed")
    port = ScriptedAdapter(Read(rows=[_order_row(1), _order_row(2)]), Read(raises=failure))

    with (
        _orders(port).wire.stream(_all_orders(), batch_size=1) as stream,
        raises_contextualized(DatabaseError),
    ):
        list(stream)
    gc.collect()

    assert len(created) == 1
    assert created[0]() is None


def test_closing_a_wire_stream_early_releases_its_encoder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = _observe_wire_encoders(monkeypatch)
    stream = _orders(ScriptedAdapter(Read(rows=[_order_row(1), _order_row(2)]))).wire.stream(
        _all_orders(), batch_size=1
    )
    with stream:
        roots = iter(stream)
        assert next(roots)["id"] == 1
    gc.collect()

    assert len(created) == 1
    assert created[0]() is None


def test_a_provider_failure_on_a_later_page_preserves_the_published_prefix() -> None:
    failure = DatabaseError(category=None, native_code=None, message="the later page failed")
    port = ScriptedAdapter(
        Read(rows=[_order_row(1), _order_row(2)]),
        Read(raises=failure),
    )
    delivered: list[int] = []

    with (
        _orders(port).stream(_all_orders(), batch_size=1) as stream,
        raises_contextualized(DatabaseError) as raised,
    ):
        for root in stream:
            delivered.append(root.id)

    assert delivered == [1]
    assert raised.value is failure


def test_a_delivery_compiles_each_structural_statement_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_compiles = 0
    child_compiles = 0
    compile_root = cast("Callable[..., Any]", vars(_materialization)["compile_read"])
    prepare_root = cast("Callable[..., Any]", vars(_read_plan)["compile_read"])
    compile_child = cast("Callable[..., Any]", vars(_read_plan)["compile_template"])

    def counting_root(*args: Any, **kwargs: Any) -> Any:
        nonlocal root_compiles
        root_compiles += 1
        return compile_root(*args, **kwargs)

    def counting_prepared_root(*args: Any, **kwargs: Any) -> Any:
        nonlocal root_compiles
        root_compiles += 1
        return prepare_root(*args, **kwargs)

    def counting_child(*args: Any, **kwargs: Any) -> Any:
        nonlocal child_compiles
        child_compiles += 1
        return compile_child(*args, **kwargs)

    monkeypatch.setattr(_materialization, "compile_read", counting_root)
    monkeypatch.setattr(_read_plan, "compile_read", counting_prepared_root)
    monkeypatch.setattr(_read_plan, "compile_template", counting_child)
    port = ScriptedAdapter(
        Read(rows=[_order_row(1), _order_row(2), _order_row(3)]),
        Read(rows=[_item_row(10, 1), _item_row(11, 2)]),
        Read(rows=[_order_row(3), _order_row(4), _order_row(5)]),
        Read(rows=[_item_row(12, 3), _item_row(13, 4)]),
        Read(rows=[_order_row(5)]),
        Read(rows=[_item_row(14, 5)]),
    )

    with _orders(port).stream(_all_orders().include(Order.items), batch_size=2) as stream:
        assert _ids(iter(stream)) == [1, 2, 3, 4, 5]

    assert root_compiles == 2
    assert child_compiles == 1


def test_a_result_that_is_an_exact_multiple_of_the_page_costs_no_terminal_statement() -> None:
    # A page reads one root past its batch, so a result that fills its last page
    # exactly comes back SHORT of what that page asked for — exhaustion is proved
    # by the statement that delivered the roots rather than by an extra one
    # returning nothing.
    port = ScriptedAdapter(
        Read(rows=[_order_row(1), _order_row(2)]),
        Read(rows=[_item_row(10, 1), _item_row(11, 2)]),
    )
    with _orders(port).stream(_all_orders().include(Order.items), batch_size=2) as stream:
        assert _ids(iter(stream)) == [1, 2]
    assert len(_reads(port)) == 2


def test_a_delivered_limit_ends_the_stream_without_a_further_statement() -> None:
    # A declared `limit` caps total roots and sizes the final page, so a limit
    # delivered in full is exhaustion already proved.
    port = ScriptedAdapter(
        Read(rows=[_order_row(1), _order_row(2)]), Read(rows=[_item_row(10, 1), _item_row(11, 2)])
    )
    query = _all_orders().include(Order.items).limit(2)
    with _orders(port).stream(query, batch_size=2) as stream:
        assert _ids(iter(stream)) == [1, 2]
    assert len(_reads(port)) == 2


def test_a_limit_narrower_than_the_page_sizes_the_page_it_caps() -> None:
    port = ScriptedAdapter(Read(rows=[_order_row(1)]))
    with _orders(port).stream(_all_orders().limit(1), batch_size=100) as stream:
        assert _ids(iter(stream)) == [1]
    assert _reads(port)[0].binds[-1] == 1


def test_a_limit_wider_than_the_result_still_ends_on_the_short_page() -> None:
    port = ScriptedAdapter(Read(rows=[_order_row(1)]))
    with _orders(port).stream(_all_orders().limit(50), batch_size=2) as stream:
        assert _ids(iter(stream)) == [1]
    assert len(_reads(port)) == 1


def test_leaving_the_loop_early_reads_no_further_page() -> None:
    port = ScriptedAdapter(Read(rows=[_order_row(1), _order_row(2)]))
    with _orders(port).stream(_all_orders(), batch_size=2) as stream:
        for root in stream:
            assert root.id == 1
            break
    assert len(_reads(port)) == 1


def test_a_later_page_seeks_past_the_last_root_of_the_page_before_it() -> None:
    # The position falls out of the page rather than out of publication: what the
    # next page's seek binds is the coordinate the database evaluated for the last
    # root the page before it kept.
    port = ScriptedAdapter(*paged_reads([_order_row(index) for index in (1, 2, 5)], size=2))
    with _orders(port).stream(_all_orders(), batch_size=2) as stream:
        assert _ids(iter(stream)) == [1, 2, 5]
    first, second = _reads(port)
    assert "t0.id >" not in first.sql
    assert "t0.id >" in second.sql
    assert second.binds[1:3] == (2, 2)


# --------------------------------------------------------------------------- #
# `batch_size` is a dial alone over storage the model describes.               #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("size", [1, 2, 3, 5])
def test_the_root_sequence_is_the_same_at_every_page_size(size: int) -> None:
    rows = [_order_row(index) for index in range(1, 4)]
    port = ScriptedAdapter(*paged_reads(rows, size=size))
    with _orders(port).stream(_all_orders(), batch_size=size) as stream:
        assert _ids(iter(stream)) == [1, 2, 3]


def _leading_null_rows() -> tuple[MappingRow, ...]:
    return (
        {**_order_row(1), "active": False},
        _order_row(2),
        {**_order_row(3), "active": None},
    )


def _leading_null_query() -> ObjectQuery[Order, Order]:
    return Order.where(Order.all).order_by(Order.active.asc())


@pytest.mark.parametrize("size", [1, 2, 8], ids=lambda size: f"batch-{size}")
def test_a_leading_null_root_at_a_page_boundary_is_delivered_at_every_page_size(
    size: int,
) -> None:
    rows = _leading_null_rows()
    port = ScriptedAdapter(*paged_reads(rows, size=size))

    with _orders(port).stream(_leading_null_query(), batch_size=size) as stream:
        published = list(stream.checked())

    assert all(isinstance(root, Order) for root in published)
    typed = cast("list[Order]", published)
    assert [root.id for root in typed] == [1, 2, 3]
    assert typed[-1].active is None


def test_default_and_checked_views_deliver_the_same_leading_null_sequence() -> None:
    rows = _leading_null_rows()
    checked_port = ScriptedAdapter(*paged_reads(rows, size=1))
    with _orders(checked_port).stream(_leading_null_query(), batch_size=1) as stream:
        checked = list(stream.checked())

    throwing_port = ScriptedAdapter(*paged_reads(rows, size=1))
    with _orders(throwing_port).stream(_leading_null_query(), batch_size=1) as stream:
        delivered = list(stream)

    assert all(isinstance(root, Order) for root in checked)
    assert (
        [root.id for root in cast("list[Order]", checked)]
        == [root.id for root in delivered]
        == [1, 2, 3]
    )


# --------------------------------------------------------------------------- #
# Identity: root-local, in both namespaces.                                    #
# --------------------------------------------------------------------------- #
def _diamond_pages() -> ScriptedAdapter:
    return ScriptedAdapter(
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
    # by root-local identity, so two positions of one tree are two positions
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


def _back_reference_pages() -> ScriptedAdapter:
    return ScriptedAdapter(Read(rows=[_order_row(1)]), Read(rows=[_item_row(10, 1)]))


def test_a_back_reference_closes_the_cycle_under_find_and_under_stream() -> None:
    # A back-reference level issues no SQL and resolves through the Root View's
    # own root-local identity map.
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


def _shared_to_one_pages() -> ScriptedAdapter:
    return ScriptedAdapter(
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
    assert eager[0].order is not eager[1].order

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
    assert eager[0]["order"] is not eager[1]["order"]

    with _orders(_shared_to_one_pages()).wire.stream(_shared_query(), batch_size=2) as stream:
        streamed = [_entity(root) for root in stream]
    first = cast("Mapping[str, object]", streamed[0]["order"])
    second = cast("Mapping[str, object]", streamed[1]["order"])
    assert first is not second
    assert first["id"] == second["id"] == 7


# --------------------------------------------------------------------------- #
# Milestone streaming: the Continuation Order's third component, and the pin   #
# every published root stands at.                                              #
# --------------------------------------------------------------------------- #
def _position_row(*, value: str, valid_start: dt.datetime, tx_start: dt.datetime) -> MappingRow:
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
_MILESTONES: Final[tuple[MappingRow, ...]] = (
    _position_row(value="90.00", valid_start=_JANUARY, tx_start=_JANUARY),
    _position_row(value="100.00", valid_start=_JANUARY, tx_start=_APRIL),
    _position_row(value="200.00", valid_start=_JUNE, tx_start=_APRIL),
)


def _positions(adapter: DatabaseAdapter) -> ScopedDatabase:
    return db_for(POSITION_MODEL, adapter)


def _all_milestones() -> ObjectQuery[Position, Position]:
    return Position.where(Position.id == 1).history(TX_TIME).history(VALID_TIME)


def _milestone_pages(*, size: int) -> ScriptedAdapter:
    return ScriptedAdapter(*paged_reads(_MILESTONES, size=size))


@pytest.mark.parametrize("size", [1, 2, 3], ids=lambda size: f"batch-{size}")
def test_a_streamed_milestone_set_publishes_every_milestone_at_its_own_edge_pin(
    size: int,
) -> None:
    # A Page is shared input and a milestone page is that page plus a pin
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
    assert binds[0] == (1, 2)
    assert binds[1][:8] == (1, 1, 1, 1, _JANUARY, 1, _JANUARY, _JANUARY)
    assert binds[2][:8] == (1, 1, 1, 1, _JANUARY, 1, _JANUARY, _APRIL)
    assert binds[1][-1] == binds[2][-1] == 2


def test_a_streamed_milestone_set_delivers_what_the_whole_result_read_does() -> None:
    # `find_history` returns one flat milestone-root sequence and ranks the roots
    # Valid-Time-first; with no authored `orderBy` the Continuation Order is the
    # key then that same edge, so a single object's streamed history IS the eager
    # edge rank — same roots, same order, same pin on each, and the same absence
    # of retained write evidence, a milestone view being read-only either way.
    eager = _positions(ScriptedAdapter(Read(rows=list(_MILESTONES)))).find(_all_milestones())
    with _positions(_milestone_pages(size=1)).stream(_all_milestones(), batch_size=1) as stream:
        streamed = list(stream)
    published = eager.results()
    assert [root.value for root in streamed] == [root.value for root in published]
    assert [pin_of(root) for root in streamed] == [pin_of(root) for root in published]
    assert eager.pin == Pin()
    assert [_retained(root) for root in streamed] == [None, None, None]
    assert [_retained(root) for root in published] == [None, None, None]


def _retained(node: object) -> object:
    """One Typed node's own retained Read Origin, or ``None`` where it kept none."""
    state = snapshot_state_of(node)
    return None if state is None else state.source


def test_a_wire_streamed_milestone_root_retains_no_more_than_its_typed_peer() -> None:
    # The two namespaces answer one delivery. A Wire node keeps its whole
    # provenance — the pin included — in its Read Origin rather than in lifecycle
    # state, so a hint carrying the QUERY's coordinates would make a Wire-streamed
    # historical root writable where its Typed peer is refused.
    with _positions(_milestone_pages(size=2)).wire.stream(
        _all_milestones(), batch_size=2
    ) as stream:
        roots = [_entity(root) for root in stream]
    assert [root["value"] for root in roots] == ["90.00", "100.00", "200.00"]
    assert [read_origin_of(root) for root in roots] == [None, None, None]


def test_a_streamed_history_with_includes_is_refused_before_any_io() -> None:
    # Delivery adds no capability: history with includes is the staged
    # `snapshot-history-includes` feature, refused by the same gate at the same
    # point whichever delivery the caller asked for.
    query = (
        Policy.where(Policy.id == 1).history(TX_TIME).history(VALID_TIME).include(Policy.coverages)
    )
    with (
        pytest.raises(DeferredFeatureError, match="snapshot-history-includes"),
        own_root(Database(RefusingAdapter(), POLICY_MODEL))
        .using_database_login()
        .stream(query, batch_size=2),
    ):
        pass  # pragma: no cover - the gate refuses at scope entry


# --------------------------------------------------------------------------- #
# Two roots at one coordinate: the maximal strict prefix, then a refusal.      #
# --------------------------------------------------------------------------- #
def _tied_pages() -> ScriptedAdapter:
    """Orders 1, 2, 2 — a page of two asking for three and finding a twin.

    Storage the model does not describe: the Continuation Order here is the
    primary key, which is unique over storage that keeps the constraint it rests
    on. The scan covers the lookahead root, so the tie is found before the seek
    that would step over it is composed.
    """
    return ScriptedAdapter(Read(rows=[_order_row(1), _order_row(2), _order_row(2)]))


def test_a_tie_publishes_the_prefix_before_it_and_then_refuses() -> None:
    port = _tied_pages()
    delivered: list[object] = []
    with (
        _orders(port).stream(_all_orders(), batch_size=2) as stream,
        raises_contextualized(SnapshotStreamContinuationError) as refusal,
    ):
        delivered.extend(stream.checked())
    assert _ids(iter(delivered)) == [1]
    assert refusal.value.code == "snapshot-stream-continuation-order-not-total"
    assert refusal.value.ordinal == 1
    assert refusal.value.coordinate == (2,)
    assert [term.name for term in refusal.value.terms] == ["id"]
    assert len(_reads(port)) == 1


def test_a_tie_ends_the_throwing_view_the_same_way() -> None:
    # The two views take the same page decision and diverge only in how the page
    # is published, so a tie ends both — and neither tied root is published,
    # converted, or classified by either.
    with (
        _orders(_tied_pages()).stream(_all_orders(), batch_size=2) as stream,
        raises_contextualized(SnapshotStreamContinuationError, match="not total"),
    ):
        assert _ids(iter(stream)) == [1]


def test_a_tie_found_on_a_later_page_keeps_every_root_before_it() -> None:
    # The ordinal counts from the start of the DELIVERY rather than of the page,
    # and every root the pages before it delivered stands.
    port = ScriptedAdapter(
        Read(rows=[_order_row(1), _order_row(2), _order_row(3)]),
        Read(rows=[_order_row(3), _order_row(4), _order_row(4)]),
    )
    delivered: list[object] = []
    with (
        _orders(port).stream(_all_orders(), batch_size=2) as stream,
        raises_contextualized(SnapshotStreamContinuationError) as refusal,
    ):
        delivered.extend(stream)
    assert _ids(iter(delivered)) == [1, 2, 3]
    assert refusal.value.ordinal == 3
    assert refusal.value.coordinate == (4,)


def test_a_stream_that_ended_at_a_tie_answers_nothing_further() -> None:
    with _orders(_tied_pages()).stream(_all_orders(), batch_size=2) as stream:
        with raises_contextualized(SnapshotStreamContinuationError):
            list(stream)
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            stream.checked()


def test_the_refusal_is_frozen_and_keeps_its_coordinate_out_of_what_it_reports() -> None:
    # A coordinate is pagination state and crosses as diagnostic evidence alone:
    # reachable by attribute access, absent from the message and the default repr,
    # and on a refusal nothing may rewrite.
    with (
        _orders(_tied_pages()).stream(_all_orders(), batch_size=2) as stream,
        raises_contextualized(SnapshotStreamContinuationError) as raised,
    ):
        list(stream)
    refusal = raised.value
    assert "2" not in str(refusal).replace("result 1", "")
    assert "coordinate=" not in repr(refusal)
    with pytest.raises(AttributeError, match="frozen"):
        refusal.ordinal = 9  # pyright: ignore[reportAttributeAccessIssue] - the refusal is frozen
    with pytest.raises(AttributeError, match="frozen"):
        del refusal.args
    refusal.add_note("a note is interpreter-owned state and stays writable")
    assert refusal.__notes__ == ["a note is interpreter-owned state and stays writable"]
    del refusal.__notes__
    assert not hasattr(refusal, "__notes__")


def test_every_name_the_refusal_carries_refuses_assignment_and_deletion() -> None:
    # The freeze is the type's own `__setattr__` / `__delattr__`, so what it
    # binds is every attribute assignment and deletion — the reported names, the
    # backing fields they read, the class-level `code`, the inherited `args`, and
    # a name the class never declared — with only the five the interpreter owns
    # left writable. `object.__setattr__`, an instance-dictionary write, and a
    # subclass replacing those two methods reach past this refusal exactly as
    # they reach past `dataclass(frozen=True)`, and are outside the contract.
    with (
        _orders(_tied_pages()).stream(_all_orders(), batch_size=2) as stream,
        raises_contextualized(SnapshotStreamContinuationError) as raised,
    ):
        list(stream)
    refusal = raised.value
    carried = (
        "terms",
        "coordinate",
        "ordinal",
        "code",
        "args",
        "_terms",
        "_coordinate",
        "_ordinal",
    )
    for name in (*carried, "undeclared"):
        with pytest.raises(AttributeError, match="frozen; cannot assign"):
            setattr(refusal, name, "rewritten")
    for name in carried:
        with pytest.raises(AttributeError, match="frozen; cannot delete"):
            delattr(refusal, name)
    assert refusal.terms and refusal.coordinate == (2,) and refusal.ordinal == 1
    assert refusal.code == "snapshot-stream-continuation-order-not-total"
    refusal.__cause__ = ValueError("chaining stays interpreter-owned")
    assert isinstance(refusal.__cause__, ValueError)


def test_a_limit_leaves_a_tie_at_its_own_boundary_undetected() -> None:
    # The one boundary the guard does not cover, and deliberately: an authored
    # limit is a hard database-read boundary, so the final page reads only what is
    # left of it and never the excluded root a tie would be with. No later seek
    # exists that could skip it.
    port = ScriptedAdapter(Read(rows=[_order_row(1), _order_row(2)]))
    with _orders(port).stream(_all_orders().limit(2), batch_size=2) as stream:
        assert _ids(iter(stream)) == [1, 2]
    assert _reads(port)[0].binds[-1] == 2


# --------------------------------------------------------------------------- #
# The lookahead root: read by one page, delivered by the next.                 #
# --------------------------------------------------------------------------- #
def test_the_lookahead_root_is_never_paired_with_the_page_that_read_it() -> None:
    # A page gathers its child keys from the roots it KEPT, so the extra root it
    # read contributes no key and receives no attachment; the page that delivers
    # it re-reads it with its own root statement and fetches its children there.
    port = ScriptedAdapter(
        Read(rows=[_order_row(1), _order_row(2), _order_row(3)]),
        Read(rows=[_item_row(10, 1), _item_row(11, 2)]),
        Read(rows=[_order_row(3)]),
        Read(rows=[_item_row(12, 3)]),
    )
    with _orders(port).stream(_all_orders().include(Order.items), batch_size=2) as stream:
        assert _ids(iter(stream)) == [1, 2, 3]
    reads = _reads(port)
    assert reads[1].binds == ([1, 2],)
    assert reads[3].binds == ([3],)


# --------------------------------------------------------------------------- #
# Adoption: at entry, not at construction, and retained through every page.    #
# --------------------------------------------------------------------------- #
def _editions() -> tuple[Any, Any, ServingModel]:
    a = prepare_model(ORDERS_MODEL, edition="orders-a")
    b = prepare_model(ORDERS_MODEL, edition="orders-b")
    return a, b, ServingModel(a)


def test_an_entered_stream_reports_its_edition_and_an_unentered_one_has_none() -> None:
    # `edition` answers exactly where `pin` does: inside the scope, and never
    # before entry, because a stream that has not entered has adopted nothing.
    a, _b, serving = _editions()
    stream = (
        own_root(Database.connect(ScriptedAdapter(Read(rows=[_order_row(1)])), serving))
        .using_database_login()
        .stream(_all_orders())
    )
    with pytest.raises(SnapshotStreamStateError, match="inside its own scope"):
        _ = stream.edition
    with stream:
        assert stream.edition == "orders-a" == a.edition
        assert _ids(iter(stream)) == [1]
        with pytest.raises(SnapshotStreamStateError, match="inside its own scope"):
            _ = stream.edition
    with pytest.raises(SnapshotStreamStateError, match="inside its own scope"):
        _ = stream.edition


def test_a_stream_adopts_at_entry_rather_than_at_construction() -> None:
    # A publication landing between the call and the scope is what separates
    # the two moments: the delivery is served under what is current when its
    # scope is entered, and the call itself took nothing.
    a, b, serving = _editions()
    stream = (
        own_root(Database.connect(ScriptedAdapter(Read(rows=[_order_row(1)])), serving))
        .using_database_login()
        .stream(_all_orders())
    )
    serving.publish(b, expected=a)
    with stream:
        assert stream.edition == "orders-b"


def test_a_publication_mid_delivery_leaves_every_later_page_on_the_entered_edition() -> None:
    # Retention is per delivery: pages read after the publication are still
    # read under the selection the scope entered with, and the stamp does not
    # move. The next operation on the same handle adopts what is serving then.
    a, b, serving = _editions()
    port = ScriptedAdapter(
        *paged_reads([_order_row(index) for index in (1, 2, 3)], size=1),
        Read(rows=[_order_row(1)]),
    )
    db = own_root(Database.connect(port, serving)).using_database_login()
    delivered: list[int] = []
    with db.stream(_all_orders(), batch_size=1) as stream:
        for root in stream:
            delivered.append(root.id)
            if len(delivered) == 1:
                serving.publish(b, expected=a)
            assert stream.edition == "orders-a"
    assert delivered == [1, 2, 3]
    assert db.find(_all_orders()).edition == "orders-b"
