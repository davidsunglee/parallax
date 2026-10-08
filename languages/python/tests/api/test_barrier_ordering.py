"""Writes on either side of a readless predicate write, against real Postgres."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

import pytest

from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import (
    Attr,
    Bitemporal,
    Document,
    DomainModel,
    Entity,
    TxTemporal,
    ValueObject,
    attr,
)
from parallax.core.entity._model import model_of
from parallax.core.execution import KeyedWriteValueError
from parallax.snapshot import ScopedDatabase, Transaction, connect
from tests._support.root_ownership import own_root

_NAMESPACE = "barrier.ordering"


class Spec(ValueObject):
    title: Attr[str | None]


class ColumnsStock(Entity, table="bo_columns_stock", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    quantity: Attr[int]
    label: Attr[str] = attr(max_length=16)
    spec: Attr[Spec | None]


class DocumentStock(Entity, table="bo_document_stock", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    quantity: Attr[int]
    label: Attr[str] = attr(max_length=16)
    spec: Attr[Spec | None]


class ColumnsLedger(Entity, table="bo_columns_ledger", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    balance: Attr[int]
    spec: Attr[Spec | None]
    version: Attr[int] = attr(optimistic_locking=True)


class DocumentLedger(Entity, table="bo_document_ledger", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    balance: Attr[int]
    spec: Attr[Spec | None]
    version: Attr[int] = attr(optimistic_locking=True)


class ColumnsSpan(Bitemporal, table="bo_columns_span", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    spec: Attr[Spec | None]


class DocumentSpan(Bitemporal, table="bo_document_span", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    spec: Attr[Spec | None]


class ColumnsLog(TxTemporal, table="bo_columns_log", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    spec: Attr[Spec | None]


class DocumentLog(TxTemporal, table="bo_document_log", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    spec: Attr[Spec | None]


class Tag(Entity, table="bo_tag", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


_MODEL = DomainModel(
    ColumnsStock,
    DocumentStock,
    ColumnsLedger,
    DocumentLedger,
    ColumnsSpan,
    DocumentSpan,
    ColumnsLog,
    DocumentLog,
    Tag,
)

type _Concurrency = Literal["optimistic", "locking"]

_STRATEGIES = pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
_STOCKS = pytest.mark.parametrize(
    "stock", [ColumnsStock, DocumentStock], ids=["columns", "document"]
)
_LEDGERS = pytest.mark.parametrize(
    "ledger", [ColumnsLedger, DocumentLedger], ids=["columns", "document"]
)
_SPANS = pytest.mark.parametrize("span", [ColumnsSpan, DocumentSpan], ids=["columns", "document"])
_LOGS = pytest.mark.parametrize("log", [ColumnsLog, DocumentLog], ids=["columns", "document"])

_TA = dt.datetime(2024, 1, 10, tzinfo=dt.UTC)
_JAN, _APR = dt.datetime(2024, 1, 1, tzinfo=dt.UTC), dt.datetime(2024, 4, 1, tzinfo=dt.UTC)


def _db(profile_run: Any, *instants: dt.datetime) -> ScopedDatabase:
    profile_run.reset(model_of(_MODEL), {})
    return own_root(
        connect(profile_run.port, _MODEL, clock=ScriptedClock(list(instants) or [_TA]))
    ).using_database_login()


def _low(tx: Transaction, stock: type[Any]) -> None:
    """The barrier: label every stock row whose quantity is below two."""
    tx.amend_where(stock.where(stock.quantity < 2), stock.label.set("low"))


_DOCUMENT = (DocumentStock, DocumentLedger, DocumentSpan, DocumentLog)
_TABLES: dict[type[Any], str] = {
    ColumnsStock: "bo_columns_stock",
    DocumentStock: "bo_document_stock",
    ColumnsLedger: "bo_columns_ledger",
    DocumentLedger: "bo_document_ledger",
    ColumnsSpan: "bo_columns_span",
    DocumentSpan: "bo_document_span",
    ColumnsLog: "bo_columns_log",
    DocumentLog: "bo_document_log",
}


def _member(entity: type[Any], member: str) -> str:
    return f"payload->'{member}'" if entity in _DOCUMENT else member


def _stock_rows(profile_run: Any, stock: type[Any]) -> list[tuple[object, ...]]:
    members = ", ".join(_member(stock, name) for name in ("quantity", "label"))
    sql = f"select id, {members} from {_TABLES[stock]} order by id"
    return [tuple(row) for row in profile_run.port.execute(sql, [])]


def _ledger_rows(profile_run: Any, ledger: type[Any]) -> list[tuple[object, ...]]:
    members = ", ".join(_member(ledger, name) for name in ("balance", "spec"))
    sql = f"select id, {members}, version from {_TABLES[ledger]}"
    return [tuple(row) for row in profile_run.port.execute(sql, [])]


@_STOCKS
@pytest.mark.parametrize("representation", ["typed", "wire"])
def test_a_predicate_observes_the_write_of_a_state_buffered_before_it(
    profile_run: Any, stock: type[Any], representation: str
) -> None:
    db = _db(profile_run)
    db.transact(lambda tx: tx.insert(stock(id=1, quantity=5, label="a")))

    def fn(tx: Transaction) -> None:
        if representation == "typed":
            source = tx.find(stock.where(stock.id == 1)).result()
            tx.amend(source.edit(quantity=1))
            _low(tx, stock)
            tx.amend(source.edit(quantity=7))
        else:
            (node,) = tx.wire.find(stock.where(stock.id == 1)).results()
            tx.wire.amend(node, {"quantity": 1})
            _low(tx, stock)
            tx.wire.amend(node, {"quantity": 7})

    db.transact(fn)
    # The barrier saw quantity 1 and labelled the row; the later write then ran.
    assert _stock_rows(profile_run, stock) == [(1, 7, "low")]


@_STOCKS
def test_a_predicate_observes_an_insert_buffered_before_it_and_not_the_edit_after(
    profile_run: Any, stock: type[Any]
) -> None:
    db = _db(profile_run)

    def fn(tx: Transaction) -> None:
        inserted = stock(id=9, quantity=1, label="new")
        tx.insert(inserted)
        _low(tx, stock)
        tx.amend(inserted.edit(quantity=7))

    db.transact(fn)
    assert _stock_rows(profile_run, stock) == [(9, 7, "low")]


@_STOCKS
def test_an_insert_removed_after_a_barrier_is_observed_and_admits_its_reinsertion(
    profile_run: Any, stock: type[Any]
) -> None:
    db = _db(profile_run)
    db.transact(lambda tx: tx.insert(Tag(id=1, label="t")))

    def fn(tx: Transaction) -> None:
        inserted = stock(id=9, quantity=1, label="new")
        tx.insert(inserted)
        _low(tx, stock)
        tx.delete(inserted)
        tx.insert(stock(id=9, quantity=4, label="again"))

    db.transact(fn)
    assert _stock_rows(profile_run, stock) == [(9, 4, "again")]


@_LEDGERS
@_STRATEGIES
def test_a_versioned_write_after_a_barrier_advances_the_version_the_earlier_one_left(
    profile_run: Any, ledger: type[Any], concurrency: _Concurrency
) -> None:
    db = _db(profile_run)
    db.transact(lambda tx: tx.insert(ledger(id=1, balance=10)))
    db.transact(lambda tx: tx.insert(ColumnsStock(id=1, quantity=5, label="a")))

    def fn(tx: Transaction) -> None:
        source = tx.find(ledger.where(ledger.id == 1)).result()
        tx.amend(source.edit(balance=20))
        _low(tx, ColumnsStock)
        tx.amend(source.edit(spec=Spec(title="after")))

    db.transact(fn, concurrency=concurrency)
    assert _ledger_rows(profile_run, ledger) == [(1, 20, {"title": "after"}, 3)]


@_LEDGERS
def test_a_versioned_insert_is_revised_after_a_barrier_from_the_version_it_opened_at(
    profile_run: Any, ledger: type[Any]
) -> None:
    db = _db(profile_run)

    def fn(tx: Transaction) -> None:
        inserted = ledger(id=1, balance=10)
        tx.insert(inserted)
        _low(tx, ColumnsStock)
        tx.amend(inserted.edit(balance=30))

    db.transact(fn)
    assert _ledger_rows(profile_run, ledger) == [(1, 30, None, 2)]


@_SPANS
@_STRATEGIES
def test_an_opening_edited_after_a_barrier_is_revised_at_one_instant(
    profile_run: Any, span: type[Any], concurrency: _Concurrency
) -> None:
    db = _db(profile_run, _TA)
    db.transact(lambda tx: tx.insert(Tag(id=1, label="t")))
    table = _TABLES[span]
    control = profile_run.control()
    try:
        control.execute_write("create table bo_audit (current_rows int not null)", [])
        control.execute_write("grant select on bo_audit to public", [])
        control.execute_write(
            "create function bo_on_tag() returns trigger language plpgsql security definer "
            "as $body$ begin insert into bo_audit (current_rows) select count(*) "
            f"from {table} where id = 1 and out_z = 'infinity'; return new; end $body$",
            [],
        )
        control.execute_write(
            "create trigger bo_tag_updated after update on bo_tag "
            "for each row execute function bo_on_tag()",
            [],
        )
    finally:
        control.close()

    def fn(tx: Transaction) -> None:
        inserted = span(id=1, amount=100)
        tx.insert(inserted, valid_from=_JAN)
        tx.amend_where(Tag.where(Tag.id == 1), Tag.label.set("q"))
        tx.amend(inserted.edit(amount=150), until=_APR)

    db.transact(fn, concurrency=concurrency)
    # When the barrier ran the opening stood alone; the edit then split it.
    assert list(profile_run.port.execute("select current_rows from bo_audit", [])) == [(1,)]
    rows = profile_run.port.execute(
        f"select in_z, case when out_z = 'infinity' then null else out_z end, from_z, "
        f"case when thru_z = 'infinity' then null else thru_z end, {_member(span, 'amount')} "
        f"from {table} order by from_z",
        [],
    )
    assert [tuple(row) for row in rows] == [
        (_TA, None, _JAN, _APR, 150),
        (_TA, None, _APR, None, 100),
    ]


def _span_rows(profile_run: Any, span: type[Any]) -> list[tuple[object, ...]]:
    rows = profile_run.port.execute(
        f"select in_z, case when out_z = 'infinity' then null else out_z end, from_z, "
        f"case when thru_z = 'infinity' then null else thru_z end, {_member(span, 'amount')} "
        f"from {_TABLES[span]} order by from_z",
        [],
    )
    return [tuple(row) for row in rows]


@_SPANS
@_STRATEGIES
@pytest.mark.parametrize("opening", ["unbounded", "bounded"])
def test_an_opening_removed_whole_after_a_barrier_admits_its_reinsertion(
    profile_run: Any, span: type[Any], concurrency: _Concurrency, opening: str
) -> None:
    db = _db(profile_run, _TA)
    db.transact(lambda tx: tx.insert(Tag(id=1, label="t")))

    def fn(tx: Transaction) -> None:
        first = span(id=1, amount=100)
        if opening == "bounded":
            tx.insert(first, valid_from=_JAN, until=_APR)
        else:
            tx.insert(first, valid_from=_JAN)
        tx.amend_where(Tag.where(Tag.id == 1), Tag.label.set("q"))
        tx.terminate(first)
        tx.insert(span(id=1, amount=200), valid_from=_JAN)
        with pytest.raises(KeyedWriteValueError) as refused:
            tx.amend(first.edit(amount=1))
        assert refused.value.code == "write-value-not-stored"

    db.transact(fn, concurrency=concurrency)
    # The first opening ran before the barrier and was removed after it; only
    # the reinsertion's row stands, at the attempt's one instant.
    assert _span_rows(profile_run, span) == [(_TA, None, _JAN, None, 200)]


@_SPANS
def test_an_opening_removed_in_part_after_a_barrier_still_refuses_a_reinsertion(
    profile_run: Any, span: type[Any]
) -> None:
    db = _db(profile_run, _TA)
    db.transact(lambda tx: tx.insert(Tag(id=1, label="t")))

    def fn(tx: Transaction) -> None:
        first = span(id=1, amount=100)
        tx.insert(first, valid_from=_JAN)
        tx.amend_where(Tag.where(Tag.id == 1), Tag.label.set("q"))
        tx.terminate(first, until=_APR)
        with pytest.raises(KeyedWriteValueError) as refused:
            tx.insert(span(id=1, amount=200), valid_from=_JAN)
        assert refused.value.code == "write-value-already-stored"

    db.transact(fn)
    assert _span_rows(profile_run, span) == [(_TA, None, _APR, None, 100)]


@_LOGS
@_STRATEGIES
def test_a_transaction_time_insert_edited_after_a_barrier_is_revised_in_place(
    profile_run: Any, log: type[Any], concurrency: _Concurrency
) -> None:
    db = _db(profile_run, _TA)

    def fn(tx: Transaction) -> None:
        inserted = log(id=1, label="seed")
        tx.insert(inserted)
        tx.amend_where(Tag.where(Tag.id == 1), Tag.label.set("q"))
        tx.amend(inserted.edit(label="after"))

    db.transact(fn, concurrency=concurrency)
    rows = profile_run.port.execute(
        "select in_z, case when out_z = 'infinity' then null else out_z end, "
        f"{_member(log, 'label')} from {_TABLES[log]}",
        [],
    )
    assert [tuple(row) for row in rows] == [(_TA, None, "after")]


@_LOGS
def test_a_transaction_time_insert_removed_after_a_barrier_admits_its_reinsertion(
    profile_run: Any, log: type[Any]
) -> None:
    db = _db(profile_run, _TA)

    def fn(tx: Transaction) -> None:
        inserted = log(id=1, label="seed")
        tx.insert(inserted)
        tx.amend_where(Tag.where(Tag.id == 1), Tag.label.set("q"))
        tx.terminate(inserted)
        tx.insert(log(id=1, label="again"))

    db.transact(fn)
    rows = profile_run.port.execute(
        "select in_z, case when out_z = 'infinity' then null else out_z end, "
        f"{_member(log, 'label')} from {_TABLES[log]}",
        [],
    )
    assert [tuple(row) for row in rows] == [(_TA, None, "again")]
