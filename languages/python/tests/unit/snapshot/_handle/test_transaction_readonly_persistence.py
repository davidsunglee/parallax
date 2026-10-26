"""Writes to a ReadOnly family through the public verbs (scripted port).

Every write shape — keyed, target, and predicate-selected, Typed and Wire — is
refused at the verb with ``read-only-write-target`` (`m-unit-work` "Writes to a
ReadOnly family"). A caught refusal sends nothing, flushes nothing, and leaves the
transaction usable: work buffered before and after it commits. An uncaught one
reaches the caller as ``ExecutionFailure.cause`` and is not retried.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from parallax.core import READ_ONLY, Attr, DomainModel, Entity, Int32, attr
from parallax.core.execution import KeyedWriteValueError
from parallax.core.unit_work import InstructionRejectedError
from parallax.snapshot import TxnContext
from tests._support.adoption import raises_contextualized
from tests._support.db_port import (
    BeginCall,
    RollbackCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
    inserted_rows,
)
from tests.unit._transact_support import db_for

_NS = "parallax.test"
_RULE = "read-only-write-target"


class Archive(Entity, table="archive", namespace=_NS, persistence=READ_ONLY):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str] = attr(max_length=32)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


class Journal(Entity, table="journal", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    note: Attr[str] = attr(max_length=32)


_MODEL = DomainModel(Archive, Journal)

type _Refused = Callable[[TxnContext], object]

_REFUSED_WRITES: dict[str, _Refused] = {
    "typed-keyed-insert": lambda tx: tx.insert(Archive(id=1, title="t")),
    "wire-keyed-insert": lambda tx: tx.wire.insert("Archive", {"id": 1, "title": "t"}),
    "typed-target-amend": lambda tx: tx.amend_if(Archive, Archive.title.set("t"), key=1, version=3),
    "wire-target-delete": lambda tx: tx.wire.delete_if("Archive", {"id": 1}, version=3),
    "typed-predicate-amend": lambda tx: tx.amend_where(
        Archive.where(Archive.id == 1), Archive.title.set("t")
    ),
    "wire-predicate-delete": lambda tx: tx.wire.delete_where(
        {"entity": "Archive", "predicate": {"eq": {"path": "Archive.id", "value": 1}}}
    ),
}


def _journal_inserts(port: ScriptedAdapter) -> list[tuple[object, ...]]:
    return [
        row
        for call in port.calls
        if isinstance(call, WriteCall) and "journal" in call.sql
        for row in inserted_rows(call)
    ]


@pytest.mark.parametrize("refused", _REFUSED_WRITES.values(), ids=list(_REFUSED_WRITES))
def test_a_caught_refusal_keeps_pending_work_and_the_transaction_usable(
    refused: _Refused,
) -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: TxnContext) -> None:
        tx.insert(Journal(id=1, note="before"))
        seen = list(port.calls)
        with pytest.raises(InstructionRejectedError) as rejected:
            refused(tx)
        assert rejected.value.rule == _RULE
        assert "parallax.test.Archive" in str(rejected.value)
        # Nothing was sent, and the pending insert was not flushed.
        assert port.calls == seen
        tx.insert(Journal(id=2, note="after"))

    db_for(_MODEL, port).transact(fn)

    assert sorted(_journal_inserts(port)) == [(1, "before"), (2, "after")]
    assert not any(isinstance(call, WriteCall) and "archive" in call.sql for call in port.calls)


@pytest.mark.parametrize("refused", _REFUSED_WRITES.values(), ids=list(_REFUSED_WRITES))
def test_an_uncaught_refusal_fails_the_transaction_once_without_retry(refused: _Refused) -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: TxnContext) -> None:
        tx.insert(Journal(id=1, note="never"))
        refused(tx)

    with raises_contextualized(InstructionRejectedError) as failure:
        db_for(_MODEL, port).transact(fn)

    assert failure.value.rule == _RULE
    assert port.calls == [BeginCall(), RollbackCall()]


def test_an_ingress_refusal_ahead_of_preparation_keeps_its_precedence() -> None:
    # A constructed value carries no provenance a keyed amendment accepts, and
    # that is judged at the source, before the write reaches preparation.
    port = ScriptedAdapter(Transact())

    def fn(tx: TxnContext) -> None:
        with pytest.raises(KeyedWriteValueError):
            tx.amend(Archive(id=1, title="t"))

    db_for(_MODEL, port).transact(fn)
