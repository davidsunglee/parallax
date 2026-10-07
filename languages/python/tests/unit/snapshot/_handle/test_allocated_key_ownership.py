"""No public verb states a `max` allocation, so the insert is buffered on the
transaction's own unit of work, as the conformance lanes' framework writes are;
every later write goes through the public verbs.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import MAX, Attr, Bitemporal, Document, DomainModel, TxTemporal, attr
from parallax.core.entity._model import model_of
from parallax.core.unit_work import KeyedWrite
from parallax.core.unit_work.instructions import prepare_typed_write
from parallax.snapshot import ScopedDatabase, Transaction, connect
from tests._support.root_ownership import own_root

_NAMESPACE = "allocated.key"


class ColumnsLog(TxTemporal, table="allocated_columns_log", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=MAX)
    amount: Attr[int]


class DocumentLog(
    TxTemporal, table="allocated_document_log", namespace=_NAMESPACE, layout=Document()
):
    id: Attr[int] = attr(primary_key=MAX)
    amount: Attr[int]


class ColumnsSpan(Bitemporal, table="allocated_columns_span", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=MAX)
    amount: Attr[int]


class DocumentSpan(
    Bitemporal, table="allocated_document_span", namespace=_NAMESPACE, layout=Document()
):
    id: Attr[int] = attr(primary_key=MAX)
    amount: Attr[int]


_MODEL = DomainModel(ColumnsLog, DocumentLog, ColumnsSpan, DocumentSpan)
_TABLES: dict[type[Any], str] = {
    ColumnsLog: "allocated_columns_log",
    DocumentLog: "allocated_document_log",
    ColumnsSpan: "allocated_columns_span",
    DocumentSpan: "allocated_document_span",
}
_DOCUMENTS = (DocumentLog, DocumentSpan)
_T0 = dt.datetime(2024, 1, 5, tzinfo=dt.UTC)
_T = dt.datetime(2024, 1, 10, tzinfo=dt.UTC)
_JAN, _MAR, _JUN = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 6))


def _db(profile_run: Any, *instants: dt.datetime) -> ScopedDatabase:
    return own_root(
        connect(profile_run.port, _MODEL, clock=ScriptedClock(list(instants)))
    ).using_database_login()


def _amount(entity: type[Any]) -> str:
    return "payload->'amount'" if entity in _DOCUMENTS else "amount"


def _plain(row: tuple[object, ...]) -> tuple[object, ...]:
    return tuple(int(cell) if isinstance(cell, float) else cell for cell in row)


def _insert_allocated(
    tx: Transaction, entity: type[Any], valid_from: dt.datetime | None = None, **row: object
) -> None:
    instruction = KeyedWrite(
        "insert",
        entity.identity.canonical,
        ({"id": {"computed": "maxPlusOne"}, **row},),
        valid_from=valid_from,
    )
    tx._attempt.uow.buffer(prepare_typed_write(instruction, model_of(_MODEL)))


def _seed(profile_run: Any, entity: type[Any], key: int) -> None:
    """A committed row holding ``key``, so the allocation the test makes is
    the next one rather than the first."""
    profile_run.reset(model_of(_MODEL), {})
    valid_from = _JAN if issubclass(entity, Bitemporal) else None
    _db(profile_run, _T0).transact(
        lambda tx: tx.insert(entity(id=key, amount=1), valid_from=valid_from)
    )


@pytest.mark.parametrize("entity", [ColumnsLog, DocumentLog], ids=["columns", "document"])
def test_a_transaction_time_row_whose_key_the_database_allocated_is_revised_in_place(
    profile_run: Any, entity: type[Any]
) -> None:
    _seed(profile_run, entity, 7)

    def fn(tx: Transaction) -> None:
        _insert_allocated(tx, entity, amount=100)
        opened = tx.find(entity.where(entity.id == 8)).result()
        tx.update(opened.edit(amount=150))
        again = tx.find(entity.where(entity.id == 8)).result()
        tx.update(again.edit(amount=175))

    _db(profile_run, _T).transact(fn)
    rows = profile_run.port.execute(
        "select in_z, case when out_z = 'infinity' then null else out_z end, "
        f"{_amount(entity)} from {_TABLES[entity]} where id = 8 order by in_z",
        [],
    )
    assert [_plain(row) for row in rows] == [(_T, None, 175)]


@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan], ids=["columns", "document"])
def test_a_bitemporal_row_whose_key_the_database_allocated_is_split_in_place(
    profile_run: Any, entity: type[Any]
) -> None:
    _seed(profile_run, entity, 7)

    def fn(tx: Transaction) -> None:
        _insert_allocated(tx, entity, _JAN, amount=100)
        opened = tx.find(entity.where(entity.id == 8).as_of(valid_time=_MAR)).result()
        tx.update(opened.edit(amount=150), until=_JUN)

    _db(profile_run, _T).transact(fn)
    rows = profile_run.port.execute(
        "select in_z, case when out_z = 'infinity' then null else out_z end, from_z, "
        "case when thru_z = 'infinity' then null else thru_z end, "
        f"{_amount(entity)} from {_TABLES[entity]} where id = 8 order by from_z, in_z",
        [],
    )
    assert [_plain(row) for row in rows] == [
        (_T, None, _JAN, _MAR, 100),
        (_T, None, _MAR, _JUN, 150),
        (_T, None, _JUN, None, 100),
    ]
