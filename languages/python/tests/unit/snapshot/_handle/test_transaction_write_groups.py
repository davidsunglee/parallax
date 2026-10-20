"""Keyed loops over distinct objects, through the public verbs over a scripted
port: what each Write Group costs in calls (`m-unit-work` *Write Group
formation*, `m-execution` *Flush execution*)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Final

import pytest

from parallax.core import Attr, Bitemporal, DomainModel, Entity, Int32, TxTemporal, attr
from parallax.core.base import INFINITY
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import MappingRow, OrderedWriteResultComplete
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.execution_lifecycle import (
    DatabaseCallStarted,
    ExecutionEvent,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    FlushStarted,
    RootExecution,
)
from parallax.core.unit_work import OptimisticLockConflictError
from parallax.core.write_plan.steps import MilestoneTarget
from parallax.snapshot import TxnContext
from tests._support.adoption import raises_contextualized
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    Ordered,
    OrderedCall,
    PortCall,
    Read,
    ReadCall,
    RollbackCall,
    ScriptedAdapter,
    ScriptEntry,
    Transact,
    Write,
    WriteCall,
    inserted_rows,
)
from tests.unit._transact_support import db_for

_NS: Final = "write.groups.handle"
_SEEDED: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_START: Final = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_BOOK: Final = 1


class SpanRow(Bitemporal, table="wgh_span", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    book: Attr[int]
    amount: Attr[int]


class AuditedRow(TxTemporal, table="wgh_audited", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    book: Attr[int]
    amount: Attr[int]


class PlainRow(Entity, table="wgh_plain", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    book: Attr[int]
    amount: Attr[int]
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


class Card(Entity, table="wgh_card", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    note: Attr[str | None] = attr(max_length=16)


_MODEL: Final = DomainModel(SpanRow, AuditedRow, PlainRow, Card)


def _rows(kind: str, objects: int) -> list[MappingRow]:
    rows: list[MappingRow] = []
    for key in range(1, objects + 1):
        row: dict[str, object] = {"id": key, "book": _BOOK, "amount": -key}
        if kind == "bitemporal":
            row |= {"from_z": _SEEDED, "thru_z": INFINITY, "in_z": _SEEDED, "out_z": INFINITY}
        elif kind == "transaction-time":
            row |= {"in_z": _SEEDED, "out_z": INFINITY}
        else:
            row |= {"version": 1}
        rows.append(row)
    return rows


def _sources(tx: TxnContext, kind: str) -> list[SpanRow] | list[AuditedRow] | list[PlainRow]:
    if kind == "bitemporal":
        query = SpanRow.where(SpanRow.book == _BOOK).as_of(valid_time=_START)
        return list(tx.find(query).results())
    if kind == "transaction-time":
        return list(tx.find(AuditedRow.where(AuditedRow.book == _BOOK)).results())
    return list(tx.find(PlainRow.where(PlainRow.book == _BOOK)).results())


def _loop(kind: str, *, delete: bool = False) -> Callable[[TxnContext], None]:
    def body(tx: TxnContext) -> None:
        for source in _sources(tx, kind):
            if delete:
                tx.delete(source)
            else:
                tx.amend(source.edit(amount=999))

    return body


def _run(
    kind: str,
    objects: int,
    script: Sequence[ScriptEntry],
    *,
    ordered: bool = True,
    dialect: Dialect = POSTGRES,
    delete: bool = False,
    lifecycle: _Calls | None = None,
) -> ScriptedAdapter:
    port = ScriptedAdapter(
        Transact(Read(rows=_rows(kind, objects)), *script), ordered=ordered, dialect=dialect
    )
    db_for(_MODEL, port, lifecycle_provider=lifecycle).transact(
        _loop(kind, delete=delete), concurrency="optimistic"
    )
    return port


def _shapes(calls: Sequence[PortCall]) -> list[tuple[str, int]]:
    """Each DML call as its shape and size: an ordered invocation and how many
    statements it presents, or a statement and how many rows it inserts."""
    shapes: list[tuple[str, int]] = []
    for call in calls:
        if isinstance(call, OrderedCall):
            shapes.append(("ordered", len(call.writes)))
        elif isinstance(call, WriteCall):
            insert = call.sql.startswith("insert")
            shapes.append(
                ("insert" if insert else "alone", len(inserted_rows(call)) if insert else 1)
            )
    return shapes


def _effects(count: int) -> ScriptEntry:
    return Ordered(OrderedWriteResultComplete((1,) * count)) if count > 1 else Write()


@pytest.mark.parametrize(
    ("objects", "script", "shapes"),
    [
        (1, (Write(times=2),), [("alone", 1), ("insert", 1)]),
        (64, (_effects(64), Write()), [("ordered", 64), ("insert", 64)]),
        (
            65,
            (_effects(64), Write(times=3)),
            [("ordered", 64), ("insert", 64), ("alone", 1), ("insert", 1)],
        ),
        (
            130,
            (_effects(64), Write(), _effects(64), Write(), _effects(2), Write()),
            [("ordered", 64), ("insert", 64)] * 2 + [("ordered", 2), ("insert", 2)],
        ),
    ],
    ids=["1", "64", "65", "130"],
)
def test_a_transaction_time_loop_costs_two_calls_per_group(
    objects: int, script: Sequence[ScriptEntry], shapes: list[tuple[str, int]]
) -> None:
    port = _run("transaction-time", objects, script)
    assert _shapes(port.calls) == shapes
    assert port.calls[0] == BeginCall() and port.calls[-1] == CommitCall()


def test_a_bitemporal_loop_groups_every_objects_successors_behind_every_close() -> None:
    # Each object closes its milestone and opens a head before the change
    # and the changed tail, 128 rows for the first group's 64 objects.
    port = _run("bitemporal", 65, (_effects(64), Write(times=3), Write(), Write()))
    assert _shapes(port.calls) == [
        ("ordered", 64),
        ("insert", 64),
        ("insert", 64),
        ("alone", 1),
        ("insert", 2),
    ]
    first, second, *_tail = (
        call for call in port.calls if isinstance(call, WriteCall) and call.sql.startswith("insert")
    )
    keys = [row[0] for call in (first, second) for row in inserted_rows(call)]
    assert keys == [key for key in range(1, 65) for _ in range(2)]


@pytest.mark.parametrize("delete", [False, True], ids=["updates", "deletes"])
def test_a_non_temporal_loop_presents_its_keyed_effects_together(delete: bool) -> None:
    port = _run("plain", 65, (_effects(64), Write()), delete=delete)
    assert _shapes(port.calls) == [("ordered", 64), ("alone", 1)]
    (invocation,) = (call for call in port.calls if isinstance(call, OrderedCall))
    # Each statement binds its object's observed version as its gate, last.
    assert [write.binds[-1] for write in invocation.writes] == [1] * 64


def test_without_ordered_transport_each_effect_runs_alone_and_the_inserts_still_group() -> None:
    port = _run("transaction-time", 3, (Write(times=4),), ordered=False)
    assert _shapes(port.calls) == [("alone", 1)] * 3 + [("insert", 3)]


def test_a_narrow_bind_limit_splits_the_grouped_insert_and_writes_the_same_rows() -> None:
    wide = _run("transaction-time", 5, (_effects(5), Write()))
    # Five columns a row, so two rows fill a statement.
    narrow = _run(
        "transaction-time",
        5,
        (_effects(5), Write(times=3)),
        dialect=replace(POSTGRES, max_bind_parameters=10),
    )
    assert _shapes(narrow.calls) == [("ordered", 5), ("insert", 2), ("insert", 2), ("insert", 1)]

    def rows(port: ScriptedAdapter) -> list[object]:
        return [
            row for call in port.calls if isinstance(call, WriteCall) for row in inserted_rows(call)
        ]

    assert rows(narrow) == rows(wide)


class _Calls:
    def __init__(self) -> None:
        self.flushes = 0
        self.calls = 0
        self.shared: set[int] = set()

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler:
        del execution
        return self

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        raise AssertionError(error)

    def handle(self, event: ExecutionEvent, /) -> None:
        if isinstance(event, FlushStarted):
            self.flushes += 1
        elif isinstance(event, DatabaseCallStarted):
            self.calls += 1


def test_one_flush_counts_a_database_call_per_presented_statement() -> None:
    observed = _Calls()
    _run("transaction-time", 65, (_effects(64), Write(times=3)), lifecycle=observed)
    assert observed.flushes == 1
    # One per presented statement: the find, every close, ordered or alone,
    # and each insert statement, however many objects' rows it holds.
    assert observed.calls == 1 + 65 + 2


def test_a_failing_grouped_insert_reports_its_statement_error_and_replays_nothing() -> None:
    failure = DatabaseError(
        category="uniqueViolation",
        native_code="23505",
        message="duplicate key",
    )
    port = ScriptedAdapter(
        Transact(
            Read(rows=_rows("transaction-time", 3)),
            _effects(3),
            Write(raises=failure),
        ),
        ordered=True,
    )
    with raises_contextualized(DatabaseError) as raised:
        db_for(_MODEL, port).transact(_loop("transaction-time"), concurrency="optimistic")
    assert raised.value is failure
    assert _shapes(port.calls) == [("ordered", 3), ("insert", 3)]
    assert port.calls[-1] == RollbackCall()


def test_a_later_objects_shortfall_is_reported_before_an_earlier_objects_insert_runs() -> None:
    # Executed one object at a time, object 1's insert would run before object
    # 2's close; in one group every close is enforced first.
    port = ScriptedAdapter(
        Transact(
            Read(rows=_rows("transaction-time", 2)),
            Ordered(OrderedWriteResultComplete((1, 0))),
        ),
        ordered=True,
    )
    with raises_contextualized(OptimisticLockConflictError) as raised:
        db_for(_MODEL, port).transact(
            _loop("transaction-time"), concurrency="optimistic", max_retries=0
        )
    target = raised.value.target
    assert isinstance(target, MilestoneTarget)
    assert target.key_values == (2,)
    assert _shapes(port.calls) == [("ordered", 2)]
    assert [type(call) for call in port.calls] == [BeginCall, ReadCall, OrderedCall, RollbackCall]


def test_inserts_of_distinct_objects_share_a_statement_where_their_members_agree() -> None:
    # The PlainRow inserts between the cards keep batching from merging them,
    # and ordering then puts the three card inserts side by side. The last
    # card's Wire insert omits its nullable note, so it names other members.
    port = ScriptedAdapter(Transact(Write(times=3)))

    def body(tx: TxnContext) -> None:
        tx.insert(Card(id=1, note="a"))
        tx.insert(PlainRow(id=9, book=_BOOK, amount=0))
        tx.insert(Card(id=2, note="b"))
        tx.insert(PlainRow(id=10, book=_BOOK, amount=0))
        tx.wire.insert(Card.identity.canonical, {"id": 3})

    db_for(_MODEL, port).transact(body)
    cards = [
        call
        for call in port.calls
        if isinstance(call, WriteCall) and call.sql.startswith("insert into wgh_card")
    ]
    assert [inserted_rows(call) for call in cards] == [((1, "a"), (2, "b")), ((3,),)]


@pytest.mark.parametrize(
    ("assigns", "statements"),
    [(True, ["insert", "update", "insert"]), (False, ["insert"])],
    ids=["a-readless-barrier", "a-dropped-amendment"],
)
def test_no_group_crosses_a_readless_barrier_and_a_dropped_amendment_is_none(
    assigns: bool, statements: list[str]
) -> None:
    port = ScriptedAdapter(Transact(Write(times=len(statements))))

    def body(tx: TxnContext) -> None:
        tx.insert(Card(id=1, note="a"))
        query = Card.where(Card.id == 7)
        if assigns:
            tx.amend_where(query, Card.note.set("z"))
        else:
            tx.amend_where(query)
        tx.insert(Card(id=2, note="b"))

    db_for(_MODEL, port).transact(body)
    assert [
        call.sql.split(" ", 1)[0] for call in port.calls if isinstance(call, WriteCall)
    ] == statements
