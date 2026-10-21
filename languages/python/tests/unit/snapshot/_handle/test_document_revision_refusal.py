"""A temporal revision patches a row's shared Structured Column only where the
row it revises was read holding an object there (`m-temporal-write` *Ownership
disposal*), through the public verbs over a scripted port.

Every case revises rows the attempt itself opened, so each revision is the
in-place update of a row stored earlier in the same attempt; the scripted
coverage read is what tells expansion what that row holds.
"""

from __future__ import annotations

import pytest

from parallax.core import Attr, Document, DomainModel, TxTemporal, attr
from parallax.core.base import SQL_NULL, PresentDocument
from parallax.core.sql_gen import SqlGenError
from parallax.core.unit_work import RollbackOnlyError
from parallax.snapshot import TxnContext
from tests._support.adoption import raises_contextualized
from tests._support.db_port import (
    BeginCall,
    PortCall,
    Read,
    ReadCall,
    RollbackCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests.unit._transact_support import FIXED, INFINITY_INSTANT, db_for


class RevisedLog(TxTemporal, table="revised_log", namespace="document.revision", layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int | None] = attr()
    label: Attr[str | None] = attr(max_length=16)


class ColumnsLog(TxTemporal, table="columns_log", namespace="document.revision"):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int | None] = attr()


_MODEL = DomainModel(RevisedLog, ColumnsLog)

_NON_OBJECT_DOCUMENTS = {
    "json-null": PresentDocument(None),
    "sql-null": SQL_NULL,
    "array": PresentDocument(["legacy", "old"]),
    "scalar": PresentDocument("legacy"),
}


def _row(key: int, payload: object) -> dict[str, object]:
    return {"id": key, "in_z": FIXED, "out_z": INFINITY_INSTANT, "payload": payload}


def _stored(key: int) -> dict[str, object]:
    return _row(key, PresentDocument({"amount": 1, "label": "a"}))


def _kinds(calls: list[PortCall]) -> list[str]:
    kinds: list[str] = []
    for call in calls:
        if isinstance(call, WriteCall):
            kinds.append(call.sql.split(" ", 1)[0])
        elif isinstance(call, ReadCall):
            kinds.append("read")
        elif isinstance(call, BeginCall):
            kinds.append("begin")
        elif isinstance(call, RollbackCall):
            kinds.append("rollback")
        else:
            kinds.append(type(call).__name__)
    return kinds


@pytest.mark.parametrize("document", _NON_OBJECT_DOCUMENTS.values(), ids=_NON_OBJECT_DOCUMENTS)
def test_a_revision_patching_a_row_not_read_as_an_object_is_refused_before_its_sql(
    document: object,
) -> None:
    # The first object's revision runs and completes in its own group before
    # the second object's group is refused at its own payload demand; nothing
    # judges the later group ahead of its turn.
    port = ScriptedAdapter(
        Transact(
            Write(),
            Read(rows=[_stored(8)]),
            Read(rows=[_stored(8)]),
            Write(),
            Read(rows=[_row(9, document)]),
        )
    )
    reached: list[str] = []

    def fn(tx: TxnContext) -> None:
        first = RevisedLog(id=8, amount=1, label="a")
        second = RevisedLog(id=9, amount=1, label="a")
        tx.insert(first)
        tx.insert(second)
        tx.find(RevisedLog.where(RevisedLog.id == 8)).result()
        tx.amend(first.edit(amount=2))
        tx.amend(second.edit(amount=3))
        reached.append("buffered")

    with raises_contextualized(SqlGenError, match="not known to be an object"):
        db_for(_MODEL, port).transact(fn)

    assert reached == ["buffered"]
    assert _kinds(port.calls) == [
        "begin",
        "insert",
        "read",
        "read",
        "update",
        "read",
        "rollback",
    ]
    (revision,) = (
        call for call in port.calls if isinstance(call, WriteCall) and call.sql.startswith("update")
    )
    assert revision.binds[-3:] == (8, "infinity", FIXED)


@pytest.mark.parametrize("document", _NON_OBJECT_DOCUMENTS.values(), ids=_NON_OBJECT_DOCUMENTS)
def test_a_refused_revision_dooms_the_attempt_where_a_later_read_flushes_it(
    document: object,
) -> None:
    port = ScriptedAdapter(
        Transact(Write(), Read(rows=[_stored(9)]), Read(rows=[_row(9, document)]))
    )
    refused: list[SqlGenError] = []

    def fn(tx: TxnContext) -> None:
        opened = RevisedLog(id=9, amount=1, label="a")
        tx.insert(opened)
        tx.find(RevisedLog.where(RevisedLog.id == 9)).result()
        tx.amend(opened.edit(amount=2))
        try:
            tx.find(RevisedLog.where(RevisedLog.id == 9)).result()
        except SqlGenError as error:
            refused.append(error)
        tx.find(RevisedLog.where(RevisedLog.id == 9)).result()

    with raises_contextualized(RollbackOnlyError):
        db_for(_MODEL, port).transact(fn)

    assert len(refused) == 1
    assert _kinds(port.calls) == ["begin", "insert", "read", "read", "rollback"]


def test_a_revision_assigning_only_columns_proceeds_whatever_its_row_holds() -> None:
    port = ScriptedAdapter(
        Transact(
            Write(),
            Read(rows=[{"id": 9, "amount": 1, "in_z": FIXED, "out_z": INFINITY_INSTANT}]),
            Read(rows=[{"id": 9, "amount": 1, "in_z": FIXED, "out_z": INFINITY_INSTANT}]),
            Write(),
        )
    )

    def fn(tx: TxnContext) -> None:
        opened = ColumnsLog(id=9, amount=1)
        tx.insert(opened)
        tx.find(ColumnsLog.where(ColumnsLog.id == 9)).result()
        tx.amend(opened.edit(amount=2))

    db_for(_MODEL, port).transact(fn)
    assert _kinds(port.calls)[-2:] == ["update", "CommitCall"]
