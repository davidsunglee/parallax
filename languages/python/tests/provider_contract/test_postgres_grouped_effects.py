"""Grouped effects against a real server (`m-execution` *Flush execution*,
`m-sql` *Grouped effects*).

Each parity proof runs the same public writes twice: once as execution realizes
them, applying the updates of one member set as one grouped update, and once
over a connection reporting a dialect that binds no arrays, under which each
update runs as the statement it lowers to alone. What a scripted port cannot
establish is here: that PostgreSQL returns exactly the ordinals of the rows it
changed, so another session's committed change refuses exactly its own object's
gate; that a statement failure fails the whole grouped update; and that a unique
value handed between objects still succeeds in authored order.
"""

from __future__ import annotations

import threading
from decimal import Decimal
from typing import Any, cast

import pytest

from parallax.conformance._decoration import DecoratingAdapter
from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.core import Attr, Document, DomainModel, Entity, Int32, attr, index
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import ArrayBind
from parallax.core.entity._model import model_of
from parallax.core.execution import ExecutionFailure
from parallax.core.execution_lifecycle import DatabaseCallStarted, TransactionAttemptFinished
from parallax.core.unit_work import OptimisticLockConflictError
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


_MODEL = DomainModel(Order, Ticket, Seat)
_KEYS = tuple(range(1, 6))
type _Row = tuple[object, ...]


def _database(
    profile_run: Any, provider: RecordingLifecycleProvider, *, grouped: bool = True
) -> ScopedDatabase:
    """A root over the server, whose connections report a dialect binding no
    arrays unless ``grouped``, so every update runs alone."""
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
    return own_root(connect(port, _MODEL, lifecycle_provider=provider)).using_database_login()


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
