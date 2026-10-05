"""Inserts whose key the database allocates for a temporal row: the key the
statement answers, and the row it then names (scripted port)."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import datetime as dt

import pytest

from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.core import MAX, Attr, DomainModel, Entity, TxTemporal, attr
from parallax.core.entity._model import model_of
from parallax.core.execution_lifecycle import (
    DatabaseCallFinished,
    DatabaseCallStarted,
    DatabaseWriteCompleted,
    DatabaseWriteRowsCompleted,
)
from parallax.core.unit_work import KeyedWrite, WriteResultError
from parallax.core.unit_work.instructions import prepare_typed_write
from parallax.snapshot.handle import Transaction
from tests._support.adoption import raises_contextualized
from tests._support.db_port import (
    Read,
    ReadCall,
    RollbackCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests.unit._transact_support import FIXED, INFINITY_INSTANT, db_for

_T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)


class Ledger(TxTemporal, table="ledger", namespace="allocated.scripted"):
    id: Attr[int] = attr(primary_key=MAX)
    amount: Attr[int]


class Tally(Entity, table="tally", namespace="allocated.scripted"):
    id: Attr[int] = attr(primary_key=MAX)
    amount: Attr[int]


_MODEL = DomainModel(Ledger, Tally)
_INSERT = (
    "insert into ledger(id, amount, in_z, out_z) "
    "select coalesce(max(t0.id), %s) + %s, %s, %s, %s from ledger t0 returning id"
)


def _insert_allocated(tx: Transaction, entity: type[Entity], amount: int) -> None:
    instruction = KeyedWrite(
        "insert", entity.identity.canonical, ({"id": {"computed": "maxPlusOne"}, "amount": amount},)
    )
    tx._uow.buffer(prepare_typed_write(instruction, model_of(_MODEL)))


def _ledger_row(key: int, amount: int) -> dict[str, object]:
    return {"id": key, "amount": amount, "in_z": FIXED, "out_z": INFINITY_INSTANT}


def test_an_allocated_temporal_key_is_answered_and_the_row_revised_in_place() -> None:
    recorder = RecordingLifecycleProvider()
    port = ScriptedAdapter(
        Transact(Read(rows=[{"id": 8}]), Read(rows=[_ledger_row(8, 100)]), Write())
    )

    def fn(tx: Transaction) -> None:
        _insert_allocated(tx, Ledger, 100)
        opened = tx.find(Ledger.where(Ledger.id == 8)).result()
        tx.update(opened.edit(amount=150))

    db_for(_MODEL, port, lifecycle_provider=recorder).transact(fn)
    insert, _find, revision = (
        call for call in port.calls if isinstance(call, ReadCall | WriteCall)
    )
    assert insert == ReadCall(_INSERT, (0, 1, 100, FIXED, "infinity"))
    # The attempt opened that row, so it is revised at its address, never closed.
    assert isinstance(revision, WriteCall)
    assert revision.sql == (
        "update ledger set amount = %s where id = %s and out_z = %s and in_z = %s"
    )
    events = recorder.roots[-1].events
    (started,) = (
        event
        for event in events
        if isinstance(event, DatabaseCallStarted) and event.statement.sql.startswith("insert")
    )
    assert started.kind == "write"
    outcomes = [event.outcome for event in events if isinstance(event, DatabaseCallFinished)]
    assert DatabaseWriteRowsCompleted(1) in outcomes
    assert DatabaseWriteCompleted(1) in outcomes


def test_a_non_temporal_allocated_key_is_not_answered() -> None:
    port = ScriptedAdapter(Transact(Write()))
    db_for(_MODEL, port).transact(lambda tx: _insert_allocated(tx, Tally, 5))
    (insert,) = port.calls[1:-1]
    assert isinstance(insert, WriteCall)
    assert insert.sql == (
        "insert into tally(id, amount) select coalesce(max(t0.id), %s) + %s, %s from tally t0"
    )


@pytest.mark.parametrize(
    "answered",
    [[], [{"id": 8}, {"id": 9}], [{"id": "8"}]],
    ids=["missing", "excess", "mistyped"],
)
def test_an_answer_the_insert_cannot_produce_fails_the_write_and_rolls_it_back(
    answered: list[dict[str, object]],
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=answered)))
    with raises_contextualized(WriteResultError):
        db_for(_MODEL, port).transact(lambda tx: _insert_allocated(tx, Ledger, 100))
    assert isinstance(port.calls[-1], RollbackCall)
