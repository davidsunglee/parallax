"""Read-only Persistence Mode and read-only Attributes against real Postgres."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Final

import pytest

from parallax.core import (
    READ_ONLY,
    Attr,
    Document,
    DomainModel,
    EditError,
    Entity,
    Int32,
    ObjectQuery,
    attr,
)
from parallax.core.entity import model_of
from parallax.core.execution_lifecycle import (
    DatabaseCallStarted,
    ExecutionEvent,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    RootExecution,
)
from parallax.core.unit_work import InstructionRejectedError, WriteInstructionError
from parallax.snapshot import ScopedDatabase, TxnContext, WireEntity, connect

_NS = "readonly.persistence"
_RULE = "read-only-write-target"
_ISSUED = dt.date(2024, 1, 15)


class Archive(Entity, table="rop_archive", namespace=_NS, persistence=READ_ONLY):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str] = attr(max_length=32)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


class Catalog(Entity, table="rop_catalog", namespace=_NS, persistence=READ_ONLY, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str] = attr(max_length=32)


class Journal(Entity, table="rop_journal", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    note: Attr[str] = attr(max_length=32)


class Badge(Entity, table="rop_badge", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    holder: Attr[str] = attr(max_length=32)
    issued: Attr[dt.date] = attr(read_only=True)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


_MODEL = DomainModel(Archive, Catalog, Journal, Badge)

_FIXTURES: Final[Mapping[str, object]] = {
    f"{_NS}.Archive": [
        {"id": 1, "title": "stored", "version": 1},
        {"id": 2, "title": "kept", "version": 1},
    ],
    f"{_NS}.Catalog": [{"id": 1, "title": "stored"}, {"id": 2, "title": "kept"}],
}


class _Statements:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler:
        del execution
        return self

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        raise AssertionError(error)

    def handle(self, event: ExecutionEvent, /) -> None:
        if isinstance(event, DatabaseCallStarted):
            self.sql.append(event.statement.sql)


@contextmanager
def _database(profile_run: Any, statements: _Statements | None = None) -> Generator[ScopedDatabase]:
    profile_run.reset(model_of(_MODEL), _FIXTURES)
    with connect(profile_run.port, _MODEL, lifecycle_provider=statements) as root:
        yield root.using_database_login()


_EVERY_ARCHIVE: Final[ObjectQuery[Any, Any]] = Archive.where(Archive.all)
_EVERY_CATALOG: Final[ObjectQuery[Any, Any]] = Catalog.where(Catalog.all)


def _titles(db: ScopedDatabase, query: ObjectQuery[Any, Any]) -> dict[int, str]:
    return {row.id: row.title for row in db.find(query).results()}


def _wire_query(entity: str) -> dict[str, object]:
    return {"target": entity, "predicate": {"eq": {"path": f"{entity}.id", "value": 1}}}


def _selection(entity: str) -> dict[str, object]:
    return {"entity": entity, "predicate": {"eq": {"path": f"{entity}.id", "value": 1}}}


@dataclass(frozen=True, slots=True)
class _Write:
    """One write: reaching it may read its source first, which is why the verb
    itself is returned rather than called."""

    name: str
    reaching: Callable[[TxnContext], Callable[[], object]]


def _sourced[S](
    name: str, read: Callable[[TxnContext], S], call: Callable[[TxnContext, S], object]
) -> _Write:
    def reaching(tx: TxnContext) -> Callable[[], object]:
        source = read(tx)
        return lambda: call(tx, source)

    return _Write(name, reaching)


def _unsourced(name: str, call: Callable[[TxnContext], object]) -> _Write:
    return _Write(name, lambda tx: lambda: call(tx))


def _archive(tx: TxnContext) -> Archive:
    return tx.find(Archive.where(Archive.id == 1)).result()


def _catalog(tx: TxnContext) -> Catalog:
    return tx.find(Catalog.where(Catalog.id == 1)).result()


def _wire_archive(tx: TxnContext) -> WireEntity:
    return tx.wire.find(_wire_query("Archive")).result()


def _wire_catalog(tx: TxnContext) -> WireEntity:
    return tx.wire.find(_wire_query("Catalog")).result()


_REFUSALS: Final[tuple[_Write, ...]] = (
    _unsourced("typed-columns-insert", lambda tx: tx.insert(Archive(id=3, title="new"))),
    _unsourced(
        "wire-document-insert", lambda tx: tx.wire.insert("Catalog", {"id": 3, "title": "new"})
    ),
    _sourced("typed-columns-amend", _archive, lambda tx, read: tx.amend(read.edit(title="x"))),
    _sourced(
        "wire-document-amend", _wire_catalog, lambda tx, read: tx.wire.amend(read, {"title": "x"})
    ),
    _sourced("typed-document-replace", _catalog, lambda tx, read: tx.replace(read)),
    _sourced("wire-columns-delete", _wire_archive, lambda tx, read: tx.wire.delete(read)),
    _unsourced(
        "typed-columns-amend-if",
        lambda tx: tx.amend_if(Archive, Archive.title.set("x"), key=1, version=1),
    ),
    _unsourced(
        "wire-columns-delete-if", lambda tx: tx.wire.delete_if("Archive", {"id": 1}, version=1)
    ),
    _unsourced(
        "typed-document-amend-where",
        lambda tx: tx.amend_where(Catalog.where(Catalog.id == 1), Catalog.title.set("x")),
    ),
    _unsourced(
        "wire-document-delete-where", lambda tx: tx.wire.delete_where(_selection("Catalog"))
    ),
)


@pytest.mark.parametrize("refusal", _REFUSALS, ids=[refusal.name for refusal in _REFUSALS])
def test_a_caught_refusal_changes_no_row_and_the_transaction_commits_its_other_work(
    profile_run: Any, refusal: _Write
) -> None:
    statements = _Statements()
    with _database(profile_run, statements) as db:

        def work(tx: TxnContext) -> None:
            refuse = refusal.reaching(tx)
            tx.insert(Journal(id=1, note="before"))
            sent = len(statements.sql)
            with pytest.raises(InstructionRejectedError) as rejected:
                refuse()
            assert rejected.value.rule == _RULE
            assert len(statements.sql) == sent
            tx.insert(Journal(id=2, note="after"))

        db.transact(work)

        notes = db.find(Journal.where(Journal.all)).results()
        assert sorted((journal.id, journal.note) for journal in notes) == [
            (1, "before"),
            (2, "after"),
        ]
        assert _titles(db, _EVERY_ARCHIVE) == {1: "stored", 2: "kept"}
        assert _titles(db, _EVERY_CATALOG) == {1: "stored", 2: "kept"}
        assert db.find(Archive.where(Archive.id == 1)).result().version == 1


@pytest.mark.parametrize("query", [_EVERY_ARCHIVE, _EVERY_CATALOG], ids=["columns", "document"])
def test_reads_of_read_only_rows_are_unaffected(
    profile_run: Any, query: ObjectQuery[Any, Any]
) -> None:
    stored = [(1, "stored"), (2, "kept")]
    with _database(profile_run) as db:

        def eager_and_streamed(tx: TxnContext) -> list[list[tuple[int, str]]]:
            with tx.stream(query, batch_size=1) as typed, tx.wire.stream(query) as wire:
                return [
                    sorted((row.id, row.title) for row in tx.find(query).results()),
                    sorted((row.id, row.title) for row in typed),
                    sorted(
                        (_int(row["id"]), _str(row["title"]))
                        for row in tx.wire.find(query).results()
                    ),
                    sorted((_int(row["id"]), _str(row["title"])) for row in wire),
                ]

        with db.stream(query, batch_size=1) as typed:
            standalone_stream = sorted((row.id, row.title) for row in typed)
        with db.wire.stream(query, batch_size=1) as wire:
            standalone_wire_stream = sorted((_int(row["id"]), _str(row["title"])) for row in wire)

        assert db.transact(eager_and_streamed) == [stored] * 4
        assert sorted(_titles(db, query).items()) == stored
        assert standalone_stream == stored
        assert standalone_wire_stream == stored
        assert (
            db.read_only(
                lambda rtx: sorted((row.id, row.title) for row in rtx.find(query).results())
            )
            == stored
        )


def _int(value: object) -> int:
    assert isinstance(value, int)
    return value


def _str(value: object) -> str:
    assert isinstance(value, str)
    return value


def _badge(db: ScopedDatabase) -> Badge:
    return db.find(Badge.where(Badge.id == 1)).result()


@contextmanager
def _issued_badge(
    profile_run: Any, statements: _Statements | None = None
) -> Generator[ScopedDatabase]:
    with _database(profile_run, statements) as db:
        db.transact(lambda tx: tx.insert(Badge(id=1, holder="Ada", issued=_ISSUED)))
        yield db


def test_an_insert_authors_a_read_only_attribute(profile_run: Any) -> None:
    with _issued_badge(profile_run) as db:
        badge = _badge(db)

    assert (badge.holder, badge.issued, badge.version) == ("Ada", _ISSUED, 1)


def test_an_edit_or_an_assignment_of_a_read_only_attribute_is_refused(profile_run: Any) -> None:
    with _issued_badge(profile_run) as db:

        def amend(tx: TxnContext) -> None:
            badge = tx.find(Badge.where(Badge.id == 1)).result()
            with pytest.raises(EditError):
                badge.edit(issued=dt.date(2025, 1, 1))
            with pytest.raises(EditError):
                Badge.issued.set(dt.date(2025, 1, 1))

        db.transact(amend)

        assert _badge(db).issued == _ISSUED


_EXPLICIT_WIRE_ASSIGNMENTS: Final[tuple[_Write, ...]] = (
    _sourced(
        "amend",
        lambda tx: tx.wire.find(_wire_query("Badge")).result(),
        lambda tx, read: tx.wire.amend(read, {"issued": "2025-01-01"}),
    ),
    _unsourced(
        "amend-if",
        lambda tx: tx.wire.amend_if("Badge", {"id": 1, "issued": "2025-01-01"}, version=1),
    ),
    _sourced(
        "replace",
        lambda tx: tx.wire.find(_wire_query("Badge")).result(),
        lambda tx, read: tx.wire.replace(read, {"holder": "Bea", "issued": "2025-01-01"}),
    ),
    _unsourced(
        "replace-if",
        lambda tx: tx.wire.replace_if(
            "Badge", {"id": 1, "holder": "Bea", "issued": "2025-01-01"}, version=1
        ),
    ),
)


@pytest.mark.parametrize(
    "assignment",
    _EXPLICIT_WIRE_ASSIGNMENTS,
    ids=[assignment.name for assignment in _EXPLICIT_WIRE_ASSIGNMENTS],
)
def test_an_explicit_wire_assignment_of_a_read_only_attribute_is_refused(
    profile_run: Any, assignment: _Write
) -> None:
    with _issued_badge(profile_run) as db:

        def write(tx: TxnContext) -> None:
            refuse = assignment.reaching(tx)
            with pytest.raises(WriteInstructionError, match="read-only fields may not be assigned"):
                refuse()

        db.transact(write)

        badge = _badge(db)
        assert (badge.holder, badge.issued, badge.version) == ("Ada", _ISSUED, 1)


_DERIVED_REPLACEMENTS: Final[tuple[_Write, ...]] = (
    _sourced(
        "typed-replace",
        lambda tx: tx.find(Badge.where(Badge.id == 1)).result(),
        lambda tx, read: tx.replace(read.edit(holder="Bea")),
    ),
    _sourced(
        "typed-replace-if",
        lambda tx: tx.find(Badge.where(Badge.id == 1)).result(),
        lambda tx, read: tx.replace_if(read.edit(holder="Bea"), version=read.version),
    ),
    _sourced(
        "wire-replace-as-published",
        lambda tx: tx.wire.find(_wire_query("Badge")).result(),
        lambda tx, read: tx.wire.replace(read),
    ),
    _sourced(
        "wire-replace-if-a-published-node",
        lambda tx: tx.wire.find(_wire_query("Badge")).result(),
        lambda tx, read: tx.wire.replace_if(read, version=1),
    ),
)


@pytest.mark.parametrize(
    "replacement",
    _DERIVED_REPLACEMENTS,
    ids=[replacement.name for replacement in _DERIVED_REPLACEMENTS],
)
def test_a_replacement_derived_from_a_read_value_leaves_a_read_only_attribute_unwritten(
    profile_run: Any, replacement: _Write
) -> None:
    statements = _Statements()
    with _issued_badge(profile_run, statements) as db:
        db.transact(lambda tx: replacement.reaching(tx)())

        updates = [sql for sql in statements.sql if sql.startswith("update rop_badge")]
        assert len(updates) == 1
        assert "issued" not in updates[0]
        badge = _badge(db)
        assert (badge.issued, badge.version) == (_ISSUED, 2)
