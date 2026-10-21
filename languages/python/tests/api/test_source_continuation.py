"""A Non-Temporal source written again after a flush its own earlier write
completed in, against real Postgres.

A read-dependency flush executes what a transaction buffered; the source a
completed write went through still authorizes the state that write produced,
without another read, while its values stay what its read returned. Each case
writes through a source, reads something else to flush, writes through the same
source again, and reads the committed row back under both storage layouts and
both strategies: what each write assigned, and the version the row advanced
to. A caller's stated revision stays literal, and a source whose object a
completed deletion removed licenses nothing, a fresh insertion at its key
included.

Standalone Docker-backed proofs, like `test_target_writes.py`: each is a
developer choreography rather than a case's authored observation.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

import pytest

from parallax.conformance.scripted_clock import FixedClock
from parallax.core import Attr, Document, DomainModel, Entity, attr
from parallax.core.entity._model import model_of
from parallax.core.unit_work import WriteEvidenceError, WritePreconditionError
from parallax.snapshot import ScopedDatabase, TxnContext, WireEntity, connect
from tests._support.adoption import raises_contextualized
from tests._support.root_ownership import own_root

_NAMESPACE = "source.continuation"
_AT = dt.datetime(2024, 6, 15, tzinfo=dt.UTC)


class ColumnsAccount(Entity, table="sc_columns_account", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None] = attr(max_length=16)
    version: Attr[int] = attr(optimistic_locking=True)


class DocumentAccount(Entity, table="sc_document_account", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None] = attr(max_length=16)
    version: Attr[int] = attr(optimistic_locking=True)


class ColumnsWallet(Entity, table="sc_columns_wallet", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None] = attr(max_length=16)


class DocumentWallet(Entity, table="sc_document_wallet", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None] = attr(max_length=16)


_MODEL = DomainModel(ColumnsAccount, DocumentAccount, ColumnsWallet, DocumentWallet)
_ACCOUNTS = (ColumnsAccount, DocumentAccount)
_ENTITIES = (ColumnsAccount, DocumentAccount, ColumnsWallet, DocumentWallet)

type _Representation = Literal["typed", "wire"]
type _Concurrency = Literal["optimistic", "locking"]

_ACCOUNT_AXES = pytest.mark.parametrize("entity", _ACCOUNTS, ids=["columns", "document"])
_ENTITY_AXES = pytest.mark.parametrize(
    "entity",
    _ENTITIES,
    ids=["versioned-columns", "versioned-document", "unversioned-columns", "unversioned-document"],
)
_STRATEGIES = pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
_REPRESENTATIONS = pytest.mark.parametrize("representation", ["typed", "wire"])
type _Source = Any


def _seeded(profile_run: Any) -> ScopedDatabase:
    profile_run.reset(model_of(_MODEL), {})
    db = own_root(connect(profile_run.port, _MODEL, clock=FixedClock(_AT))).using_database_login()

    def seed(tx: TxnContext) -> None:
        for entity in _ENTITIES:
            for key in (1, 2):
                tx.wire.insert(_name(entity), {"id": key, "label": "seed", "note": "kept"})

    db.transact(seed)
    return db


def _name(entity: type[Any]) -> str:
    return f"{_NAMESPACE}.{entity.__name__}"


def _read(
    tx: TxnContext, entity: type[Any], representation: _Representation, key: int = 1
) -> _Source:
    if representation == "typed":
        return tx.find(entity.where(entity.id == key)).result()
    return tx.wire.find(
        {
            "target": _name(entity),
            "predicate": {"eq": {"path": f"{_name(entity)}.id", "value": key}},
        }
    ).result()


def _amend(tx: TxnContext, source: _Source, **changes: object) -> None:
    if isinstance(source, WireEntity):
        tx.wire.amend(source, changes)
    else:
        tx.amend(source.edit(**changes))


def _replace(tx: TxnContext, source: _Source, **changes: object) -> None:
    if isinstance(source, WireEntity):
        tx.wire.replace(source, {**tx.wire.editable_data(source), **changes})
    else:
        tx.replace(source.edit(**changes))


def _delete(tx: TxnContext, source: _Source) -> None:
    if isinstance(source, WireEntity):
        tx.wire.delete(source)
    else:
        tx.delete(source)


def _flush(tx: TxnContext, entity: type[Any]) -> None:
    """A read of another key, which flushes everything buffered first."""
    tx.find(entity.where(entity.id == 2))


def _stored(db: ScopedDatabase, entity: type[Any]) -> tuple[object, ...] | None:
    def read(tx: TxnContext) -> tuple[object, ...] | None:
        rows = tx.find(entity.where(entity.id == 1)).results()
        if not rows:
            return None
        (row,) = rows
        return (row.label, row.note, getattr(row, "version", None))

    return db.transact(read)


def _version(entity: type[Any], version: int) -> int | None:
    return version if entity in _ACCOUNTS else None


@_ENTITY_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_a_source_amends_again_after_a_read_flushed_its_first_amendment(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, representation: _Representation
) -> None:
    db = _seeded(profile_run)

    def fn(tx: TxnContext) -> None:
        source = _read(tx, entity, representation)
        _amend(tx, source, label="first")
        _flush(tx, entity)
        _amend(tx, source, note="second")

    db.transact(fn, concurrency=concurrency)
    assert _stored(db, entity) == ("first", "second", _version(entity, 3))


@_ENTITY_AXES
@_STRATEGIES
@pytest.mark.parametrize(
    ("representation", "edited", "note"),
    [("typed", False, "kept"), ("typed", True, "seven"), ("wire", False, "kept")],
    ids=["typed-old-source", "typed-edited-source", "wire-old-source"],
)
def test_a_later_replacement_states_its_own_sources_literal_values(
    profile_run: Any,
    entity: type[Any],
    concurrency: _Concurrency,
    representation: _Representation,
    edited: bool,
    note: str,
) -> None:
    # The first write changed the note; a replacement through the value read
    # before it states that value's note, not the one the write produced, and
    # one through the edited copy states the edited note.
    db = _seeded(profile_run)

    def fn(tx: TxnContext) -> None:
        source = _read(tx, entity, representation)
        if isinstance(source, WireEntity):
            _amend(tx, source, note="seven")
            _flush(tx, entity)
            _replace(tx, source, label="new")
            return
        changed = source.edit(note="seven")
        tx.amend(changed)
        _flush(tx, entity)
        _replace(tx, changed if edited else source, label="new")

    db.transact(fn, concurrency=concurrency)
    assert _stored(db, entity) == ("new", note, _version(entity, 3))


@_ACCOUNT_AXES
@_STRATEGIES
def test_a_callers_completed_write_advances_the_source_of_the_state_it_named(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _seeded(profile_run)

    def fn(tx: TxnContext) -> None:
        source = tx.find(entity.where(entity.id == 1)).result()
        tx.amend_if(entity, entity.label.set("caller"), key=1, version=1)
        _flush(tx, entity)
        tx.amend(source.edit(note="source"))
        tx.amend_if(entity, entity.label.set("current"), key=1, version=2)

    db.transact(fn, concurrency=concurrency)
    assert _stored(db, entity) == ("current", "source", 3)


@_ACCOUNT_AXES
@_STRATEGIES
def test_a_callers_stated_revision_stays_literal_after_its_flush(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    # Locking confirms the stated revision at the call; Optimistic gates on it
    # when it executes. Either way, the version the first write left is not
    # the one the caller stated.
    db = _seeded(profile_run)

    def fn(tx: TxnContext) -> None:
        source = tx.find(entity.where(entity.id == 1)).result()
        tx.amend(source.edit(label="first"))
        _flush(tx, entity)
        tx.amend_if(entity, entity.note.set("stale"), key=1, version=1)

    with raises_contextualized(WritePreconditionError):
        db.transact(fn, concurrency=concurrency)
    assert _stored(db, entity) == ("seed", "kept", 1)


@_ACCOUNT_AXES
@_STRATEGIES
def test_an_equal_assignment_advances_the_version_and_an_empty_one_changes_nothing(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _seeded(profile_run)

    def fn(tx: TxnContext) -> None:
        source = tx.find(entity.where(entity.id == 1)).result()
        tx.amend(source.edit(label=source.label))
        _flush(tx, entity)
        tx.amend(source.edit())
        _flush(tx, entity)
        tx.amend(source.edit(note="after"))

    db.transact(fn, concurrency=concurrency)
    assert _stored(db, entity) == ("seed", "after", 3)


@_ENTITY_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_a_deleted_source_ends_and_a_reinsertion_at_its_key_revives_none_of_it(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, representation: _Representation
) -> None:
    db = _seeded(profile_run)
    refused: list[str] = []

    def fn(tx: TxnContext) -> None:
        source = _read(tx, entity, representation)
        _delete(tx, source)
        _flush(tx, entity)
        tx.wire.insert(_name(entity), {"id": 1, "label": "again", "note": "fresh"})
        for write in (lambda: _amend(tx, source, label="stale"), lambda: _delete(tx, source)):
            with pytest.raises(WriteEvidenceError) as refusal:
                write()
            refused.append(refusal.value.code)
        _flush(tx, entity)
        _amend(tx, _read(tx, entity, representation), note="reread")

    db.transact(fn, concurrency=concurrency)
    assert refused == ["write-evidence-consumed"] * 2
    assert _stored(db, entity) == ("again", "reread", _version(entity, 2))


@_ACCOUNT_AXES
@_STRATEGIES
@pytest.mark.parametrize(
    ("replaced_first", "stored"),
    [(False, ("old", "kept")), (True, ("fresh", "later"))],
    ids=["amend-then-replace", "replace-then-amend"],
)
def test_an_old_and_a_fresh_source_of_one_produced_state_write_as_one(
    profile_run: Any,
    entity: type[Any],
    concurrency: _Concurrency,
    replaced_first: bool,
    stored: tuple[str, str],
) -> None:
    # Both sources reach the version the first write produced, so their writes
    # share its claim and coalesce in authored order: a replacement overwrites
    # an earlier amendment with its own source's complete state, and an
    # amendment after a replacement overrides only what it assigns. One write
    # advances the version once.
    db = _seeded(profile_run)

    def fn(tx: TxnContext) -> None:
        old = tx.find(entity.where(entity.id == 1)).result()
        tx.amend(old.edit(note="seven"))
        fresh = tx.find(entity.where(entity.id == 1)).result()
        assert (fresh.note, fresh.version) == ("seven", 2)
        if replaced_first:
            tx.replace(fresh.edit(label="fresh"))
            tx.amend(old.edit(note="later"))
        else:
            tx.amend(fresh.edit(label="fresh"))
            tx.replace(old.edit(label="old"))

    db.transact(fn, concurrency=concurrency)
    assert _stored(db, entity) == (*stored, 3)
