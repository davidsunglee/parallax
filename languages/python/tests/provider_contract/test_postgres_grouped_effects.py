"""Grouped effects against a real server (`m-execution` *Flush execution*,
`m-sql` *Grouped effects*, `m-temporal-write`).

Each parity proof runs the same public writes twice: once as execution realizes
them, applying the effects of one shape as one grouped effect, and once over a
connection reporting a dialect that binds no arrays, under which each effect
runs as the statement it lowers to alone. What a scripted port cannot establish
is here: that PostgreSQL returns exactly the ordinals of the rows it changed or
removed, so another session's committed change refuses exactly its own object's
gate or milestone; that grouped closes, revisions, and removals store the
history their lone statements store under the generated interval checks and
exclusion; that a statement failure fails the whole grouped effect, an exclusion
refusal recognized as the recoverable conflict it is; and that a unique value
handed between objects still succeeds in authored order.
"""

from __future__ import annotations

import datetime as dt
import threading
from collections.abc import Callable
from decimal import Decimal
from typing import Any, Literal, cast

import pytest

from parallax.conformance._decoration import DecoratingAdapter
from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import (
    Attr,
    Bitemporal,
    Document,
    DomainModel,
    Entity,
    Int32,
    TxTemporal,
    attr,
    index,
)
from parallax.core.base import INFINITY
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import ArrayBind
from parallax.core.entity._model import model_of
from parallax.core.execution import ExecutionFailure
from parallax.core.execution_lifecycle import (
    AttemptRolledBack,
    DatabaseCallStarted,
    TransactionAttemptFinished,
)
from parallax.core.storage_layout import view as storage_layout_view
from parallax.core.unit_work import OptimisticLockConflictError
from parallax.core.write_plan.steps import MilestoneTarget
from parallax.snapshot import ScopedDatabase, TxnContext, connect
from tests._support.root_ownership import own_root
from tests._support.temporal_write_transport import CountingConnection, PortTally

_NAMESPACE = "grouped.effects"


class Order(Entity, table="grp_order", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)
    total: Attr[Decimal] = attr(precision=18, scale=2)
    note: Attr[str | None] = attr(max_length=16)


class Ticket(Entity, table="grp_ticket", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)
    total: Attr[Decimal] = attr(precision=18, scale=2)
    note: Attr[str | None] = attr(max_length=16)


class Seat(
    Entity,
    table="grp_seat",
    namespace=_NAMESPACE,
    indices=(index("grp_seat_holder", "holder", unique=True),),
):
    id: Attr[int] = attr(primary_key=True)
    holder: Attr[str | None] = attr(max_length=16)
    seat_no: Attr[int]


class Book(TxTemporal, table="grp_book", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]


class Span(Bitemporal, table="grp_span", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]


class DocumentSpan(Bitemporal, table="grp_document_span", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    note: Attr[str | None] = attr(max_length=16)


_MODEL = DomainModel(Order, Ticket, Seat, Book, Span, DocumentSpan)
_KEYS = tuple(range(1, 6))
type _Row = tuple[object, ...]
type _Concurrency = Literal["optimistic", "locking"]

_JAN, _FEB, _JUN, _SEP = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 2, 6, 9))
_INSTANTS = tuple(dt.datetime(2023, 12, day, tzinfo=dt.UTC) for day in range(1, 29))
"""One Transaction Instant per attempt, alike in every run of one proof, so the
history each run stores compares whole."""


def _database(
    profile_run: Any,
    provider: RecordingLifecycleProvider,
    *,
    grouped: bool = True,
    reset: bool = True,
    instants: tuple[dt.datetime, ...] = _INSTANTS,
) -> ScopedDatabase:
    """A root over the server, whose connections report a dialect binding no
    arrays unless ``grouped``, so every effect runs alone, its Tables reset
    first where ``reset``."""
    if reset:
        profile_run.reset(model_of(_MODEL), {})
    port = (
        profile_run.port
        if grouped
        else DecoratingAdapter(
            profile_run.port,
            lambda connection: cast(
                "Any", CountingConnection(connection, PortTally(), "expanding")
            ),
        )
    )
    return own_root(
        connect(port, _MODEL, clock=ScriptedClock(instants), lifecycle_provider=provider)
    ).using_database_login()


def _seed(db: ScopedDatabase) -> None:
    def seed(tx: TxnContext) -> None:
        for key in _KEYS:
            tx.insert(Order(id=key, total=Decimal(key), note=None))
            tx.insert(Ticket(id=key, total=Decimal(key), note="n"))
            tx.insert(Seat(id=key, holder=f"h{key}", seat_no=key))

    db.transact(seed)


def _rows(profile_run: Any, table: str) -> list[_Row]:
    return [
        tuple(row) for row in profile_run.port.execute(f"select * from {table} order by id", [])
    ]


def _writes(provider: RecordingLifecycleProvider) -> list[DatabaseCallStarted]:
    return [
        event
        for event in provider.roots[-1].events
        if isinstance(event, DatabaseCallStarted) and event.kind == "write"
    ]


def _amend_all(entity: type[Any]) -> Any:
    def amend(tx: TxnContext) -> None:
        for source in tx.find(entity.where(entity.id >= 1)).results():
            note = None if source.id % 2 else f"n{source.id}"
            tx.amend(source.edit(total=source.total * 10, note=note))

    return amend


@pytest.mark.parametrize(("entity", "table"), [(Order, "grp_order"), (Ticket, "grp_ticket")])
def test_one_grouped_update_stores_what_each_update_alone_stores(
    profile_run: Any, entity: type[Any], table: str
) -> None:
    stored: list[list[_Row]] = []
    writes: list[list[DatabaseCallStarted]] = []
    for grouped in (False, True):
        provider = RecordingLifecycleProvider()
        db = _database(profile_run, provider, grouped=grouped)
        _seed(db)
        db.transact(_amend_all(entity))
        stored.append(_rows(profile_run, table))
        writes.append(_writes(provider))
    alone, grouped_writes = writes
    assert stored[0] == stored[1]
    assert len(alone) == len(_KEYS)
    (statement,) = grouped_writes
    assert " from unnest(" in statement.statement.sql
    assert statement.statement.sql.endswith(" returning v.ord")
    first = statement.statement.binds[-1]
    assert isinstance(first, ArrayBind)
    assert len(first.values) == len(_KEYS)


def _another_writer_advances(db: ScopedDatabase, key: int) -> None:
    def write(tx: TxnContext) -> None:
        order = tx.find(Order.where(Order.id == key)).result()
        tx.amend(order.edit(note="other"))

    writer = threading.Thread(target=db.transact, args=(write,))
    writer.start()
    writer.join()


def test_another_sessions_change_refuses_exactly_its_objects_gate_then_replays(
    profile_run: Any,
) -> None:
    provider = RecordingLifecycleProvider()
    db = _database(profile_run, provider)
    _seed(db)
    attempts: list[list[int]] = []
    conflicts: list[BaseException] = []

    def amend(tx: TxnContext) -> None:
        orders = sorted(tx.find(Order.where(Order.id >= 1)).results(), key=lambda order: order.id)
        attempts.append([order.version for order in orders])
        if len(attempts) == 1:
            _another_writer_advances(db, 3)
        for order in orders:
            tx.amend(order.edit(total=order.total + 1))
        try:
            tx.find(Order.where(Order.id == 1)).result()
        except OptimisticLockConflictError as conflict:
            conflicts.append(conflict)
            raise

    db.transact(amend, max_retries=1)
    (conflict,) = conflicts
    assert isinstance(conflict, OptimisticLockConflictError)
    assert conflict.target.key_values == ((3,),)
    assert attempts == [[1] * 5, [1, 1, 2, 1, 1]]
    rows = _rows(profile_run, "grp_order")
    assert [(row[0], row[1], row[2]) for row in rows] == [
        (1, 2, Decimal("2.00")),
        (2, 2, Decimal("3.00")),
        (3, 3, Decimal("4.00")),
        (4, 2, Decimal("5.00")),
        (5, 2, Decimal("6.00")),
    ]
    finished = [
        event for event in provider.roots[1].events if isinstance(event, TransactionAttemptFinished)
    ]
    assert len(finished) == 2


def test_a_check_violation_fails_the_whole_grouped_update_and_rolls_it_back(
    profile_run: Any,
) -> None:
    provider = RecordingLifecycleProvider()
    db = _database(profile_run, provider)
    _seed(db)
    control = profile_run.control()
    try:
        control.execute_write(
            "alter table grp_order add constraint grp_order_total check (total <> 30) not valid",
            [],
        )
    finally:
        control.close()
    before = _rows(profile_run, "grp_order")
    with pytest.raises(ExecutionFailure) as escaped:
        db.transact(_amend_all(Order), max_retries=2)
    cause = escaped.value.cause
    assert isinstance(cause, DatabaseError)
    assert (cause.category, cause.native_code) == ("constraintViolation", "23514")
    assert len(_writes(provider)) == 1
    assert _rows(profile_run, "grp_order") == before


def test_a_unique_value_handed_between_objects_succeeds_in_authored_order(
    profile_run: Any,
) -> None:
    provider = RecordingLifecycleProvider()
    db = _database(profile_run, provider)
    _seed(db)

    def hand_over(tx: TxnContext) -> None:
        seats = {seat.id: seat for seat in tx.find(Seat.where(Seat.id >= 1)).results()}
        tx.amend(seats[4].edit(seat_no=40))
        tx.amend(seats[5].edit(seat_no=50))
        tx.amend(seats[1].edit(holder=None, seat_no=10))
        tx.amend(seats[2].edit(holder="h1", seat_no=20))

    db.transact(hand_over)
    rows = _rows(profile_run, "grp_seat")
    assert [(row[0], row[1]) for row in rows] == [
        (1, None),
        (2, "h1"),
        (3, "h3"),
        (4, "h4"),
        (5, "h5"),
    ]
    # The release and the take each run alone, in authored order, while the two
    # updates assigning no unique member share one grouped update.
    sql = [event.statement.sql for event in _writes(provider)]
    assert len(sql) == 3
    assert sql[0].startswith("update grp_seat t set seat_no = v.c2 from unnest(")
    assert sql[1:] == ["update grp_seat set holder = ?, seat_no = ? where id = ?"] * 2


def test_a_unique_violation_fails_the_whole_grouped_update_naming_no_row(
    profile_run: Any,
) -> None:
    # The index is out of the model's sight, so the two seats' swap still
    # groups, and PostgreSQL refuses the statement whichever row it visits
    # first.
    provider = RecordingLifecycleProvider()
    db = _database(profile_run, provider)
    _seed(db)
    control = profile_run.control()
    try:
        control.execute_write("create unique index grp_seat_no on grp_seat (seat_no)", [])
    finally:
        control.close()
    before = _rows(profile_run, "grp_seat")

    def collide(tx: TxnContext) -> None:
        for seat in tx.find(Seat.where(Seat.id >= 4)).results():
            tx.amend(seat.edit(seat_no=9 - seat.id))

    with pytest.raises(ExecutionFailure) as escaped:
        db.transact(collide, max_retries=2)
    cause = escaped.value.cause
    assert isinstance(cause, DatabaseError)
    assert (cause.category, cause.native_code) == ("uniqueViolation", "23505")
    assert cause.constraint_name == "grp_seat_no"
    (statement,) = _writes(provider)
    assert statement.statement.sql.startswith("update grp_seat t set seat_no = v.c2 from unnest(")
    assert _rows(profile_run, "grp_seat") == before


# --------------------------------------------------------------------------- #
# Deletes and temporal effects.                                                #
# --------------------------------------------------------------------------- #
_HISTORY_ORDER = {"grp_order": "id", "grp_book": "id, in_z, out_z"}


def _history(profile_run: Any, table: str) -> list[_Row]:
    """Every row ``table`` stores, in one order whatever order wrote them."""
    order = _HISTORY_ORDER.get(table, "id, in_z, out_z, from_z")
    return [
        tuple(row)
        for row in profile_run.port.execute(f"select * from {table} order by {order}", [])
    ]


def _realized(
    profile_run: Any,
    table: str,
    seed: Callable[[TxnContext], None],
    edits: Callable[[TxnContext], None],
    *,
    grouped: bool,
    concurrency: _Concurrency = "optimistic",
    prepare: Callable[[TxnContext], None] | None = None,
) -> tuple[list[_Row], list[str]]:
    """What ``edits`` leave stored in ``table`` after ``seed`` and ``prepare``
    committed, and the DML its transaction ran, grouped or each effect alone.

    The seed and preparation run grouped, each at its own earlier instant, so
    every run of one proof starts from the same stored history."""
    seeding = _database(profile_run, RecordingLifecycleProvider(), instants=_INSTANTS[:2])
    seeding.transact(seed)
    if prepare is not None:
        seeding.transact(prepare)
    provider = RecordingLifecycleProvider()
    db = _database(profile_run, provider, grouped=grouped, reset=False, instants=_INSTANTS[2:])
    db.transact(edits, concurrency=concurrency)
    return _history(profile_run, table), [event.statement.sql for event in _writes(provider)]


def _seed_orders(tx: TxnContext) -> None:
    for key in _KEYS:
        tx.insert(Order(id=key, total=Decimal(key), note=None))


@pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
def test_grouped_deletes_remove_what_each_delete_alone_removes(
    profile_run: Any, concurrency: _Concurrency
) -> None:
    def remove(tx: TxnContext) -> None:
        for order in tx.find(Order.where(Order.id >= 2)).results():
            tx.delete(order)

    alone, alone_writes = _realized(
        profile_run, "grp_order", _seed_orders, remove, grouped=False, concurrency=concurrency
    )
    grouped, grouped_writes = _realized(
        profile_run, "grp_order", _seed_orders, remove, grouped=True, concurrency=concurrency
    )
    assert grouped == alone
    assert [row[0] for row in grouped] == [1]
    assert len(alone_writes) == 4
    (statement,) = grouped_writes
    assert statement.startswith("delete from grp_order t using unnest(")


def _seed_books(tx: TxnContext) -> None:
    for key in _KEYS:
        tx.insert(Book(id=key, amount=100))


def _amend_books(tx: TxnContext) -> None:
    for book in tx.find(Book.where(Book.id >= 1)).results():
        tx.amend(book.edit(amount=book.amount + book.id))


@pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
def test_grouped_transaction_time_closes_store_the_history_each_close_stores(
    profile_run: Any, concurrency: _Concurrency
) -> None:
    alone, alone_writes = _realized(
        profile_run, "grp_book", _seed_books, _amend_books, grouped=False, concurrency=concurrency
    )
    grouped, grouped_writes = _realized(
        profile_run, "grp_book", _seed_books, _amend_books, grouped=True, concurrency=concurrency
    )
    assert grouped == alone
    assert len(grouped) == 2 * len(_KEYS)
    assert len(alone_writes) == 2 * len(_KEYS)
    close, insert = grouped_writes
    assert close.startswith("update grp_book t set out_z = v.c")
    assert (" and t.in_z = v.c" in close) is (concurrency == "optimistic")
    assert insert.startswith("insert into grp_book(")


def test_grouped_guards_match_every_unchanged_milestone_and_change_nothing(
    profile_run: Any,
) -> None:
    # Each amendment assigns the amount the book already holds, so under the
    # optimistic strategy its milestone is proven unchanged by a guard that
    # assigns its Transaction-Time start to itself: every row matches, none
    # changes, and nothing opens.
    def restate(tx: TxnContext) -> None:
        for book in tx.find(Book.where(Book.id >= 1)).results():
            tx.amend(book.edit(amount=book.amount))

    runs = [
        _realized(profile_run, "grp_book", _seed_books, restate, grouped=grouped)
        for grouped in (False, True)
    ]
    (alone, alone_writes), (grouped, grouped_writes) = runs
    assert grouped == alone
    assert len(grouped) == len(_KEYS)
    assert len(alone_writes) == len(_KEYS)
    (guard,) = grouped_writes
    assert guard.startswith("update grp_book t set in_z = t.in_z from unnest(")


def _seed_spans(entity: type[Any]) -> Callable[[TxnContext], None]:
    def seed(tx: TxnContext) -> None:
        for key in _KEYS:
            tx.insert(entity(id=key, amount=100), valid_from=_JAN)

    return seed


def _split_spans(entity: type[Any]) -> Callable[[TxnContext], None]:
    """Amend every span from February until September: one close each, then a
    head, a changed middle, and a tail."""

    def split(tx: TxnContext) -> None:
        for span in tx.find(entity.where(entity.id >= 1).as_of(valid_time=_FEB)).results():
            tx.amend(span.edit(amount=span.amount + span.id), until=_SEP)

    return split


@pytest.mark.parametrize("entity", [Span, DocumentSpan], ids=["columns", "document"])
@pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
def test_grouped_bitemporal_interior_splits_store_the_history_each_alone_stores(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    table = "grp_span" if entity is Span else "grp_document_span"
    runs = [
        _realized(
            profile_run,
            table,
            _seed_spans(entity),
            _split_spans(entity),
            grouped=grouped,
            concurrency=concurrency,
        )
        for grouped in (False, True)
    ]
    (alone, alone_writes), (grouped, grouped_writes) = runs
    assert grouped == alone
    assert len(grouped) == 4 * len(_KEYS)
    assert len(alone_writes) == len(_KEYS) + 3 * len(_KEYS)
    close, insert = grouped_writes
    assert close.startswith(f"update {table} t set out_z = v.c")
    assert insert.startswith(f"insert into {table}(")


def _two_rectangles(tx: TxnContext) -> None:
    """Each span's amount changes from June on, leaving it two current
    rectangles: January to June and June onward."""
    for span in tx.find(Span.where(Span.id >= 1).as_of(valid_time=_JUN)).results():
        tx.amend(span.edit(amount=200))


def test_grouped_closes_of_deferred_ranges_reach_every_rectangle_each_write_acquired(
    profile_run: Any,
) -> None:
    # A find at February observes only each span's first rectangle, so each
    # amendment until September acquires its June rectangle with the shared
    # coverage read, and closes both of its own rectangles in one statement
    # beside every other span's.
    runs = [
        _realized(
            profile_run,
            "grp_span",
            _seed_spans(Span),
            _split_spans(Span),
            grouped=grouped,
            prepare=_two_rectangles,
        )
        for grouped in (False, True)
    ]
    (alone, alone_writes), (grouped, grouped_writes) = runs
    assert grouped == alone
    closes = [sql for sql in alone_writes if sql.startswith("update")]
    assert len(closes) == 2 * len(_KEYS)
    close, insert = grouped_writes
    assert close.startswith("update grp_span t set out_z = v.c")
    assert insert.startswith("insert into grp_span(")


def _revise_and_remove(tx: TxnContext) -> None:
    """Amend every span from February until September, then once the flush has
    run, amend the even spans' opened middles again, which revises them in
    place, and terminate the odd spans' opened middles, which removes them."""
    _split_spans(Span)(tx)
    middles = tx.find(Span.where(Span.id >= 1).as_of(valid_time=_FEB)).results()
    for span in middles:
        if span.id % 2:
            tx.terminate(span, until=_SEP)
        else:
            tx.amend(span.edit(amount=span.amount * 10), until=_SEP)


def test_grouped_same_attempt_revisions_and_removals_store_what_each_alone_stores(
    profile_run: Any,
) -> None:
    runs = [
        _realized(profile_run, "grp_span", _seed_spans(Span), _revise_and_remove, grouped=grouped)
        for grouped in (False, True)
    ]
    (alone, _alone_writes), (grouped, grouped_writes) = runs
    assert grouped == alone
    later = grouped_writes[2:]
    assert any(sql.startswith("update grp_span t set ") for sql in later)
    assert any(sql.startswith("delete from grp_span t using unnest(") for sql in later)


def _advance_book(db: ScopedDatabase, key: int) -> None:
    def write(tx: TxnContext) -> None:
        book = tx.find(Book.where(Book.id == key)).result()
        tx.amend(book.edit(amount=-1))

    writer = threading.Thread(target=db.transact, args=(write,))
    writer.start()
    writer.join()


def test_another_sessions_change_refuses_exactly_its_milestone_and_rolls_back_the_rest(
    profile_run: Any,
) -> None:
    provider = RecordingLifecycleProvider()
    db = _database(profile_run, provider)
    db.transact(_seed_books)
    conflicts: list[OptimisticLockConflictError] = []
    attempts: list[list[int]] = []
    stored: list[list[_Row]] = []

    def amend(tx: TxnContext) -> None:
        books = sorted(tx.find(Book.where(Book.id >= 1)).results(), key=lambda book: book.id)
        attempts.append([book.amount for book in books])
        if len(attempts) == 1:
            _advance_book(db, 3)
        for book in books:
            tx.amend(book.edit(amount=book.amount + 1))
        try:
            tx.find(Book.where(Book.id == 1)).result()
        except OptimisticLockConflictError as conflict:
            conflicts.append(conflict)
            stored.append(_history(profile_run, "grp_book"))
            raise

    db.transact(amend, max_retries=1)
    (conflict,) = conflicts
    target = conflict.target
    assert isinstance(target, MilestoneTarget)
    assert target.key_values == (3,)
    assert attempts == [[100] * 5, [100, 100, -1, 100, 100]]
    # Read from another session while the losing attempt was open, the history
    # held only the seed and the other session's close and successor: the
    # grouped close of every other book was never committed.
    (losing,) = stored
    assert len(losing) == len(_KEYS) + 1
    rows = _history(profile_run, "grp_book")
    assert len(rows) == len(losing) + len(_KEYS)
    current = sorted((row[0], row[1]) for row in rows if row[-1] is INFINITY)
    assert current == [(1, 101), (2, 101), (3, 0), (4, 101), (5, 101)]
    finished = [
        event for event in provider.roots[1].events if isinstance(event, TransactionAttemptFinished)
    ]
    assert len(finished) == 2
    assert isinstance(finished[0].outcome, AttemptRolledBack)


def test_an_exclusion_refusal_fails_the_whole_grouped_close_as_a_recoverable_conflict(
    profile_run: Any,
) -> None:
    # The Table's own exclusion is replaced, under its own name, by one no two
    # rows closed at one instant satisfy, so the grouped close refuses it
    # whichever row it visits second, while no ordinal falls short.
    provider = RecordingLifecycleProvider()
    db = _database(profile_run, provider)
    db.transact(_seed_books)
    view = storage_layout_view(model_of(_MODEL)).entity(Book.identity)
    assert view is not None and view.layout.temporal_constraints is not None
    name = view.layout.temporal_constraints.exclusion_name
    control = profile_run.control()
    try:
        control.execute_write(f"alter table grp_book drop constraint {name}", [])
        control.execute_write(
            f"alter table grp_book add constraint {name} exclude using btree (out_z with =) "
            "where (out_z <> 'infinity')",
            [],
        )
    finally:
        control.close()
    before = _history(profile_run, "grp_book")
    with pytest.raises(ExecutionFailure) as escaped:
        db.transact(_amend_books, max_retries=1)
    cause = escaped.value.cause
    assert isinstance(cause, DatabaseError)
    assert (cause.native_code, cause.constraint_name) == ("23P01", name)
    finished = [
        event
        for event in provider.roots[-1].events
        if isinstance(event, TransactionAttemptFinished)
    ]
    # Recognized as a recoverable conflict, the refusal is replayed once.
    assert len(finished) == 2
    first, last = (attempt.outcome for attempt in finished)
    assert isinstance(first, AttemptRolledBack) and isinstance(last, AttemptRolledBack)
    assert first.failure.retry_eligible is True
    grouped = [event for event in _writes(provider) if " t set out_z = v.c" in event.statement.sql]
    assert len(grouped) == 2
    assert _history(profile_run, "grp_book") == before
