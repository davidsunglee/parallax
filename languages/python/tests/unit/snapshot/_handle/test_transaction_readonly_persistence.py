"""Writes to a ReadOnly family through the public verbs (scripted port)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

import pytest

from parallax.conformance.read_models import Magazine, Periodical, Publication
from parallax.core import (
    READ_ONLY,
    Attr,
    Bitemporal,
    Document,
    DomainModel,
    Entity,
    Int32,
    TemporalBound,
    attr,
)
from parallax.core.base import PresentDocument
from parallax.core.execution import KeyedWriteValueError
from parallax.core.unit_work import InstructionRejectedError
from parallax.snapshot import TxnContext, WireEntity
from tests._support.adoption import raises_contextualized
from tests._support.db_port import (
    BeginCall,
    Read,
    ReadCall,
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

_RECORDED = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_VALID_FROM = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
_UNTIL = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)


class Archive(Entity, table="archive", namespace=_NS, persistence=READ_ONLY):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str] = attr(max_length=32)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


class Register(Entity, table="register", namespace=_NS, persistence=READ_ONLY):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=32)


class Catalog(Entity, table="catalog", namespace=_NS, persistence=READ_ONLY, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str] = attr(max_length=32)


class Ledger(Bitemporal, table="ledger", namespace=_NS, persistence=READ_ONLY):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[Decimal] = attr(precision=12, scale=2)


class Journal(Entity, table="journal", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    note: Attr[str] = attr(max_length=32)


_MODEL = DomainModel(Archive, Register, Catalog, Ledger, Journal, Publication, Periodical, Magazine)

_ARCHIVE_ROW: Final[Mapping[str, object]] = {"id": 1, "title": "stored", "version": 1}
_CATALOG_ROW: Final[Mapping[str, object]] = {
    "id": 1,
    "payload": PresentDocument({"title": "stored"}),
}
_LEDGER_ROW: Final[Mapping[str, object]] = {
    "id": 1,
    "amount": Decimal("5.00"),
    "from_z": _RECORDED,
    "thru_z": TemporalBound.INFINITY,
    "in_z": _RECORDED,
    "out_z": TemporalBound.INFINITY,
}

_AT_VALID_FROM: Final[Mapping[str, object]] = {
    "transaction-time": {"asOf": "latest"},
    "valid-time": {"asOf": "2024-07-01T00:00:00.000000Z"},
}


def _selection(entity: str) -> dict[str, object]:
    return {"entity": entity, "predicate": {"eq": {"path": f"{entity}.id", "value": 1}}}


def _wire_query(entity: str, temporal: Mapping[str, object] | None = None) -> dict[str, object]:
    query: dict[str, object] = {
        "target": entity,
        "predicate": {"eq": {"path": f"{entity}.id", "value": 1}},
    }
    if temporal is not None:
        query["temporal"] = temporal
    return query


def _archive(tx: TxnContext) -> Archive:
    return tx.find(Archive.where(Archive.id == 1)).result()


def _catalog(tx: TxnContext) -> Catalog:
    return tx.find(Catalog.where(Catalog.id == 1)).result()


def _ledger(tx: TxnContext) -> Ledger:
    return tx.find(Ledger.where(Ledger.id == 1).as_of(valid_time=_VALID_FROM)).result()


def _wire_archive(tx: TxnContext) -> WireEntity:
    return tx.wire.find(_wire_query("Archive")).result()


def _wire_catalog(tx: TxnContext) -> WireEntity:
    return tx.wire.find(_wire_query("Catalog")).result()


def _wire_ledger(tx: TxnContext) -> WireEntity:
    return tx.wire.find(_wire_query("Ledger", _AT_VALID_FROM)).result()


@dataclass(frozen=True, slots=True)
class _Refusal:
    name: str
    reaching: Callable[[TxnContext], Callable[[], object]]
    source_rows: tuple[Mapping[str, object], ...] = ()


def _unsourced(name: str, call: Callable[[TxnContext], object]) -> _Refusal:
    return _Refusal(name, lambda tx: lambda: call(tx))


def _sourced[S](
    name: str,
    read: Callable[[TxnContext], S],
    call: Callable[[TxnContext, S], object],
    row: Mapping[str, object],
) -> _Refusal:
    def reaching(tx: TxnContext) -> Callable[[], object]:
        source = read(tx)
        return lambda: call(tx, source)

    return _Refusal(name, reaching, (row,))


_KEYED: Final[tuple[_Refusal, ...]] = (
    _unsourced("typed-insert", lambda tx: tx.insert(Archive(id=2, title="new"))),
    _unsourced("wire-insert", lambda tx: tx.wire.insert("Archive", {"id": 2, "title": "new"})),
    _sourced(
        "typed-amend",
        _archive,
        lambda tx, read: tx.amend(read.edit(title="changed")),
        _ARCHIVE_ROW,
    ),
    _sourced(
        "typed-amend-by-assignment",
        _archive,
        lambda tx, read: tx.amend(read, Archive.title.set("changed")),
        _ARCHIVE_ROW,
    ),
    _sourced(
        "wire-amend",
        _wire_archive,
        lambda tx, read: tx.wire.amend(read, {"title": "changed"}),
        _ARCHIVE_ROW,
    ),
    _sourced("typed-empty-amend", _archive, lambda tx, read: tx.amend(read), _ARCHIVE_ROW),
    _sourced(
        "wire-empty-amend", _wire_archive, lambda tx, read: tx.wire.amend(read, {}), _ARCHIVE_ROW
    ),
    _sourced(
        "typed-replace",
        _archive,
        lambda tx, read: tx.replace(read.edit(title="changed")),
        _ARCHIVE_ROW,
    ),
    _sourced(
        "wire-replace",
        _wire_archive,
        lambda tx, read: tx.wire.replace(read, {"title": "changed"}),
        _ARCHIVE_ROW,
    ),
    _sourced(
        "wire-replace-as-published",
        _wire_archive,
        lambda tx, read: tx.wire.replace(read),
        _ARCHIVE_ROW,
    ),
    _sourced("typed-delete", _archive, lambda tx, read: tx.delete(read), _ARCHIVE_ROW),
    _sourced("wire-delete", _wire_archive, lambda tx, read: tx.wire.delete(read), _ARCHIVE_ROW),
    _sourced("typed-terminate", _ledger, lambda tx, read: tx.terminate(read), _LEDGER_ROW),
    _sourced("wire-terminate", _wire_ledger, lambda tx, read: tx.wire.terminate(read), _LEDGER_ROW),
)

_BOUNDED_KEYED: Final[tuple[_Refusal, ...]] = (
    _unsourced(
        "typed-insert-within-a-window",
        lambda tx: tx.insert(
            Ledger(id=2, amount=Decimal("1.00")), valid_from=_VALID_FROM, until=_UNTIL
        ),
    ),
    _unsourced(
        "wire-insert-within-a-window",
        lambda tx: tx.wire.insert(
            "Ledger", {"id": 2, "amount": "1.00"}, valid_from=_VALID_FROM, until=_UNTIL
        ),
    ),
    _sourced(
        "typed-amend-until",
        _ledger,
        lambda tx, read: tx.amend(read.edit(amount=Decimal("7.00")), until=_UNTIL),
        _LEDGER_ROW,
    ),
    _sourced(
        "wire-amend-until",
        _wire_ledger,
        lambda tx, read: tx.wire.amend(read, {"amount": "7.00"}, until=_UNTIL),
        _LEDGER_ROW,
    ),
    _sourced(
        "typed-replace-until",
        _ledger,
        lambda tx, read: tx.replace(read, until=_UNTIL),
        _LEDGER_ROW,
    ),
    _sourced(
        "wire-replace-until",
        _wire_ledger,
        lambda tx, read: tx.wire.replace(read, {"amount": "7.00"}, until=_UNTIL),
        _LEDGER_ROW,
    ),
    _sourced(
        "typed-terminate-until",
        _ledger,
        lambda tx, read: tx.terminate(read, until=_UNTIL),
        _LEDGER_ROW,
    ),
    _sourced(
        "wire-terminate-until",
        _wire_ledger,
        lambda tx, read: tx.wire.terminate(read, until=_UNTIL),
        _LEDGER_ROW,
    ),
)

_TARGET: Final[tuple[_Refusal, ...]] = (
    _unsourced(
        "typed-amend-if",
        lambda tx: tx.amend_if(Archive, Archive.title.set("changed"), key=1, version=1),
    ),
    _unsourced(
        "wire-amend-if",
        lambda tx: tx.wire.amend_if("Archive", {"id": 1, "title": "changed"}, version=1),
    ),
    _unsourced("typed-empty-amend-if", lambda tx: tx.amend_if(Archive, key=1, version=1)),
    _unsourced("wire-empty-amend-if", lambda tx: tx.wire.amend_if("Archive", {"id": 1}, version=1)),
    _unsourced(
        "typed-replace-if",
        lambda tx: tx.replace_if(Archive(id=1, title="changed"), version=1),
    ),
    _unsourced(
        "wire-replace-if",
        lambda tx: tx.wire.replace_if("Archive", {"id": 1, "title": "changed"}, version=1),
    ),
    _sourced(
        "wire-replace-if-a-published-node",
        _wire_archive,
        lambda tx, read: tx.wire.replace_if(read, version=1),
        _ARCHIVE_ROW,
    ),
    _unsourced("typed-delete-if", lambda tx: tx.delete_if(Archive, key=1, version=1)),
    _unsourced("wire-delete-if", lambda tx: tx.wire.delete_if("Archive", {"id": 1}, version=1)),
    _unsourced(
        "typed-terminate-if",
        lambda tx: tx.terminate_if(Ledger, key=1, tx_start=_RECORDED, valid_from=_VALID_FROM),
    ),
    _unsourced(
        "wire-terminate-if",
        lambda tx: tx.wire.terminate_if(
            "Ledger", {"id": 1}, tx_start=_RECORDED, valid_from=_VALID_FROM
        ),
    ),
)

_BOUNDED_TARGET: Final[tuple[_Refusal, ...]] = (
    _unsourced(
        "typed-amend-if-within-a-window",
        lambda tx: tx.amend_if(
            Ledger,
            Ledger.amount.set(Decimal("7.00")),
            key=1,
            tx_start=_RECORDED,
            valid_from=_VALID_FROM,
            until=_UNTIL,
        ),
    ),
    _unsourced(
        "wire-amend-if-within-a-window",
        lambda tx: tx.wire.amend_if(
            "Ledger",
            {"id": 1, "amount": "7.00"},
            tx_start=_RECORDED,
            valid_from=_VALID_FROM,
            until=_UNTIL,
        ),
    ),
    _unsourced(
        "typed-replace-if-within-a-window",
        lambda tx: tx.replace_if(
            Ledger(id=1, amount=Decimal("7.00")),
            tx_start=_RECORDED,
            valid_from=_VALID_FROM,
            until=_UNTIL,
        ),
    ),
    _unsourced(
        "wire-replace-if-within-a-window",
        lambda tx: tx.wire.replace_if(
            "Ledger",
            {"id": 1, "amount": "7.00"},
            tx_start=_RECORDED,
            valid_from=_VALID_FROM,
            until=_UNTIL,
        ),
    ),
    _unsourced(
        "typed-terminate-if-within-a-window",
        lambda tx: tx.terminate_if(
            Ledger, key=1, tx_start=_RECORDED, valid_from=_VALID_FROM, until=_UNTIL
        ),
    ),
    _unsourced(
        "wire-terminate-if-within-a-window",
        lambda tx: tx.wire.terminate_if(
            "Ledger", {"id": 1}, tx_start=_RECORDED, valid_from=_VALID_FROM, until=_UNTIL
        ),
    ),
)

_PREDICATE: Final[tuple[_Refusal, ...]] = (
    _unsourced(
        "typed-amend-where",
        lambda tx: tx.amend_where(Register.where(Register.id == 1), Register.label.set("changed")),
    ),
    _unsourced(
        "wire-amend-where",
        lambda tx: tx.wire.amend_where(_selection("Register"), {"label": "changed"}),
    ),
    _unsourced(
        "typed-empty-amend-where", lambda tx: tx.amend_where(Register.where(Register.id == 1))
    ),
    _unsourced(
        "wire-empty-amend-where", lambda tx: tx.wire.amend_where(_selection("Register"), {})
    ),
    _unsourced(
        "typed-replace-where",
        lambda tx: tx.replace_where(
            Register.where(Register.id == 1), Register(id=1, label="changed")
        ),
    ),
    _unsourced(
        "wire-replace-where",
        lambda tx: tx.wire.replace_where(_selection("Register"), {"label": "changed"}),
    ),
    _unsourced("typed-delete-where", lambda tx: tx.delete_where(Register.where(Register.id == 1))),
    _unsourced("wire-delete-where", lambda tx: tx.wire.delete_where(_selection("Register"))),
)

_LAYOUT_AND_FAMILY: Final[tuple[_Refusal, ...]] = (
    _unsourced("typed-document-insert", lambda tx: tx.insert(Catalog(id=2, title="new"))),
    _sourced(
        "typed-document-amend",
        _catalog,
        lambda tx, read: tx.amend(read.edit(title="changed")),
        _CATALOG_ROW,
    ),
    _sourced(
        "wire-document-amend",
        _wire_catalog,
        lambda tx, read: tx.wire.amend(read, {"title": "changed"}),
        _CATALOG_ROW,
    ),
    _unsourced(
        "wire-document-delete-where", lambda tx: tx.wire.delete_where(_selection("Catalog"))
    ),
    _unsourced(
        "typed-concrete-subtype-insert", lambda tx: tx.insert(Magazine(id=2, title="Monthly"))
    ),
    _unsourced(
        "wire-concrete-subtype-amend-if",
        lambda tx: tx.wire.amend_if("Magazine", {"id": 1, "title": "changed"}, version=1),
    ),
    _unsourced(
        "typed-abstract-subtype-amend-where",
        lambda tx: tx.amend_where(
            Periodical.where(Periodical.id == 1), Periodical.frequency.set("weekly")
        ),
    ),
    _unsourced(
        "typed-abstract-root-delete-where",
        lambda tx: tx.delete_where(Publication.where(Publication.id == 1)),
    ),
)

_REFUSALS: Final[tuple[_Refusal, ...]] = (
    *_KEYED,
    *_BOUNDED_KEYED,
    *_TARGET,
    *_BOUNDED_TARGET,
    *_PREDICATE,
    *_LAYOUT_AND_FAMILY,
)


def _journal_inserts(port: ScriptedAdapter) -> list[tuple[object, ...]]:
    return [
        row
        for call in port.calls
        if isinstance(call, WriteCall) and "journal" in call.sql
        for row in inserted_rows(call)
    ]


@pytest.mark.parametrize("refusal", _REFUSALS, ids=[refusal.name for refusal in _REFUSALS])
def test_a_caught_refusal_keeps_pending_work_and_the_transaction_usable(
    refusal: _Refusal,
) -> None:
    port = ScriptedAdapter(Transact(*(Read(rows=[row]) for row in refusal.source_rows), Write()))

    def fn(tx: TxnContext) -> None:
        refuse = refusal.reaching(tx)
        tx.insert(Journal(id=1, note="before"))
        seen = list(port.calls)
        with pytest.raises(InstructionRejectedError) as rejected:
            refuse()
        assert rejected.value.rule == _RULE
        assert port.calls == seen
        tx.insert(Journal(id=2, note="after"))

    db_for(_MODEL, port).transact(fn)

    assert sorted(_journal_inserts(port)) == [(1, "before"), (2, "after")]
    assert all("journal" in call.sql for call in port.calls if isinstance(call, WriteCall))


@pytest.mark.parametrize("refusal", _REFUSALS, ids=[refusal.name for refusal in _REFUSALS])
def test_an_uncaught_refusal_fails_the_transaction_once_without_retry(refusal: _Refusal) -> None:
    port = ScriptedAdapter(Transact(*(Read(rows=[row]) for row in refusal.source_rows)))

    def fn(tx: TxnContext) -> None:
        refuse = refusal.reaching(tx)
        tx.insert(Journal(id=1, note="never"))
        refuse()

    with raises_contextualized(InstructionRejectedError) as failure:
        db_for(_MODEL, port).transact(fn)

    assert failure.value.rule == _RULE
    assert [type(call) for call in port.calls] == [
        BeginCall,
        *(ReadCall for _ in refusal.source_rows),
        RollbackCall,
    ]


def test_the_refusal_names_the_target_it_refused() -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: TxnContext) -> None:
        with pytest.raises(InstructionRejectedError) as rejected:
            tx.insert(Magazine(id=2, title="Monthly"))
        assert "parallax.compatibility.Magazine" in str(rejected.value)

    db_for(_MODEL, port).transact(fn)


def test_an_ingress_refusal_ahead_of_preparation_keeps_its_precedence() -> None:
    # A constructed value carries no provenance a keyed amendment accepts, and
    # that is judged at the source, before the write reaches preparation.
    port = ScriptedAdapter(Transact())

    def fn(tx: TxnContext) -> None:
        with pytest.raises(KeyedWriteValueError):
            tx.amend(Archive(id=1, title="t"))

    db_for(_MODEL, port).transact(fn)
