"""A Bitemporal correction written through a participating stream, against
real Postgres (`m-unit-work` *Shared coverage acquisition*).

Every object stores a head ``[January, June)`` at 100 and a tail ``[June, ∞)``
at 200, both known from T0. Each root a stream delivers as of March is amended
to 150 until September, which reaches the tail its read did not observe, so
each write owes one missing coverage window. The page after a root's page
flushes its write, and pre-commit flushes the last page's: each Flush reads its
writes' coverage in shared reads of at most 32 consecutive writes, and the
writes each read makes ready execute together as one Write Group. An eager read
of the same roots buffers every write into one Flush, and a source written again
after its write completed reads nothing.

A tail stored as many milestones, each labelled apart, keeps every amended
piece apart, so one ready group closes and opens more rows than one ordered
invocation or one insert carries: its closes span several invocations and its
openings several inserts, while each statement stays one Database Call.

Each case reads the whole stored history back and compares it with the one
these inputs determine. Every write runs under a clock answering 2024-11-01.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable, Iterator
from typing import Any, Final, Literal, cast

import psycopg
import pytest

from parallax.conformance._decoration import DecoratingAdapter
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import Attr, Bitemporal, Document, DomainModel, Entity, attr
from parallax.core.base import INFINITY
from parallax.core.entity._model import model_of
from parallax.snapshot import ScopedDatabase, TxnContext, WireEntity, connect
from tests._support.flush_calls import Call, FlushCalls, PageRead, call_runs
from tests._support.root_ownership import own_root
from tests._support.temporal_write_transport import CountingConnection, PortTally

_NAMESPACE: Final = "temporal.coverage.streams"


class StreamColumns(Bitemporal, table="tcs_columns", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    label: Attr[str] = attr(max_length=16)


class StreamDocument(Bitemporal, table="tcs_document", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    label: Attr[str] = attr(max_length=16)


class StreamFlag(Entity, table="tcs_flag", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


_MODEL: Final = DomainModel(StreamColumns, StreamDocument, StreamFlag)
_T0: Final = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_AT: Final = dt.datetime(2024, 11, 1, tzinfo=dt.UTC)
_JAN, _MAR, _JUN, _SEP = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 6, 9))

# Each write closes its head and its tail and opens three rows: the head's
# unamended part, the merged amended parts, and the tail's rest.
_CLOSES: Final = 2
_OPENINGS: Final = 3
_INSERT_ENTRIES: Final = 64


def _group_writes(writes: int) -> int:
    """The statements one Write Group of ``writes`` such writes presents:
    every close, then its openings in inserts of at most 64 entries."""
    return writes * _CLOSES + -(-writes * _OPENINGS // _INSERT_ENTRIES)


# 70 roots at 33 per page: pages of 33, 33, and 4 roots. A 33-write Flush is
# one shared read of 32 writes' coverage, which makes all 32 ready as one
# group, and one read of the 33rd write's, which runs alone.
_OBJECTS: Final = 70
_PAGE: Final = 33
_PAGE_FLUSH: Final[list[Call]] = [
    ("read", 32),
    ("write", _group_writes(32)),
    ("read", 1),
    ("write", _group_writes(1)),
]
_LAST_PAGE_FLUSH: Final[list[Call]] = [("read", 4), ("write", _group_writes(4))]

type _Layout = Literal["columns", "document"]
type _Representation = Literal["typed", "wire"]
type _Row = tuple[object, ...]
"""``(id, in_z, out_z, from_z, thru_z, amount, label)``, each open end ``None``."""

_ENTITIES: Final = {"columns": StreamColumns, "document": StreamDocument}
_LAYOUTS = pytest.mark.parametrize("layout", ["columns", "document"])
_REPRESENTATIONS = pytest.mark.parametrize("representation", ["typed", "wire"])
_STRATEGIES = pytest.mark.parametrize("concurrency", ["optimistic", "locking"])


def _day(days: int) -> dt.datetime:
    return _JUN + dt.timedelta(days=days)


def _tail(key: int, pieces: int) -> list[tuple[str, dt.datetime, object]]:
    """Object ``key``'s tail from June: one milestone labelled as its head,
    or ``pieces`` daily milestones each labelled apart, the last one open."""
    if pieces == 1:
        return [(f"k{key}", _JUN, INFINITY)]
    return [
        (f"k{key}-{index}", _day(index), INFINITY if index == pieces - 1 else _day(index + 1))
        for index in range(pieces)
    ]


def _seeded(profile_run: Any, layout: _Layout, objects: int, *, tail_pieces: int = 1) -> None:
    profile_run.reset(model_of(_MODEL), {})
    rows = [
        row
        for key in range(1, objects + 1)
        for row in (
            (key, 100, f"k{key}", _JAN, _JUN),
            *((key, 200, label, start, end) for label, start, end in _tail(key, tail_pieces)),
        )
    ]
    control = profile_run.control()
    try:
        control.execute_write("insert into tcs_flag(id, label) values (1, 'flag')", [])
        for start in range(0, len(rows), 500):
            chunk = rows[start : start + 500]
            binds: list[object] = []
            if layout == "columns":
                values = "(%s, %s, %s, %s, %s, %s, 'infinity')"
                for key, amount, label, begin, end in chunk:
                    binds += [key, amount, label, begin, end, _T0]
                insert = "insert into tcs_columns(id, amount, label, from_z, thru_z, in_z, out_z)"
            else:
                values = "(%s, %s, %s, %s, 'infinity', %s::jsonb)"
                for key, amount, label, begin, end in chunk:
                    payload = json.dumps({"amount": amount, "label": label})
                    binds += [key, begin, end, _T0, payload]
                insert = "insert into tcs_document(id, from_z, thru_z, in_z, out_z, payload)"
            control.execute_write(f"{insert} values {', '.join([values] * len(chunk))}", binds)
    finally:
        control.close()


def _db(profile_run: Any, calls: FlushCalls) -> ScopedDatabase:
    return own_root(
        connect(profile_run.port, _MODEL, clock=FixedClock(_AT), lifecycle_provider=calls)
    ).using_database_login()


def _history(profile_run: Any, layout: _Layout) -> list[_Row]:
    open_end = "case when {0} = 'infinity' then null else {0} end"
    members = (
        "amount, label" if layout == "columns" else "(payload->>'amount')::int, payload->>'label'"
    )
    rows = profile_run.port.execute(
        f"select id, in_z, {open_end.format('out_z')}, from_z, {open_end.format('thru_z')}, "
        f"{members} from tcs_{layout}",
        [],
    )
    return sorted((tuple(row) for row in rows), key=_order)


def _order(row: _Row) -> tuple[object, ...]:
    key, in_z, out_z, start = row[:4]
    return key, in_z, dt.datetime.max.replace(tzinfo=dt.UTC) if out_z is None else out_z, start


def _corrected(keys: Iterable[int], *, again: Iterable[int] = ()) -> list[_Row]:
    """Each object's history once its March-to-September amendment to 150
    committed, its amended row labelled ``again`` for each key in ``again``."""
    relabelled = set(again)
    history: list[_Row] = []
    for key in keys:
        label = f"k{key}"
        history += [
            (key, _T0, _AT, _JAN, _JUN, 100, label),
            (key, _T0, _AT, _JUN, None, 200, label),
            (key, _AT, None, _JAN, _MAR, 100, label),
            # The head's and the tail's amended pieces store one state and merge.
            (key, _AT, None, _MAR, _SEP, 150, "again" if key in relabelled else label),
            (key, _AT, None, _SEP, None, 200, label),
        ]
    return sorted(history, key=_order)


def _fragmented_corrected(keys: Iterable[int], pieces: int) -> list[_Row]:
    """Each object's history once its March-to-September amendment to 150
    committed over a tail of ``pieces`` milestones: every piece the window
    reaches is amended apart, and only the last one, which outlasts
    September, keeps a rest."""
    history: list[_Row] = []
    for key in keys:
        label = f"k{key}"
        tail = _tail(key, pieces)
        history += [(key, _T0, _AT, _JAN, _JUN, 100, label)]
        history += [
            (key, _T0, _AT, start, None if end is INFINITY else end, 200, piece)
            for piece, start, end in tail
        ]
        history += [
            (key, _AT, None, _JAN, _MAR, 100, label),
            (key, _AT, None, _MAR, _JUN, 150, label),
        ]
        history += [
            (key, _AT, None, start, _SEP if end is INFINITY else end, 150, piece)
            for piece, start, end in tail
        ]
        last = tail[-1][0]
        history.append((key, _AT, None, _SEP, None, 200, last))
    return sorted(history, key=_order)


def _name(layout: _Layout) -> str:
    return f"{_NAMESPACE}.{_ENTITIES[layout].__name__}"


def _streamed(
    tx: TxnContext, layout: _Layout, representation: _Representation, **size: int
) -> Iterator[Any]:
    if representation == "typed":
        stream = tx.stream(_typed_query(layout), **size)
    else:
        stream = tx.wire.stream(_wire_query(layout), **size)
    with stream as roots:
        yield from roots


def _found(tx: TxnContext, layout: _Layout, representation: _Representation) -> list[Any]:
    if representation == "wire":
        return list(tx.wire.find(_wire_query(layout)).results())
    return list(tx.find(_typed_query(layout)).results())


def _typed_query(layout: _Layout) -> Any:
    entity: Any = _ENTITIES[layout]
    return entity.where(entity.id >= 1).order_by(entity.id.asc()).as_of(valid_time=_MAR)


def _wire_query(layout: _Layout) -> dict[str, object]:
    name = _name(layout)
    return {
        "target": name,
        "predicate": {"true": {}},
        "temporal": {
            "transaction-time": {"asOf": "latest"},
            "valid-time": {"asOf": f"{_MAR:%Y-%m-%dT%H:%M:%S.%fZ}"},
        },
        "orderBy": [{"attr": f"{name}.id", "direction": "asc"}],
    }


def _key(source: Any) -> int:
    return cast("int", source["id"] if isinstance(source, WireEntity) else source.id)


def _amend(tx: TxnContext, source: Any, **changes: object) -> None:
    if isinstance(source, WireEntity):
        tx.wire.amend(source, changes, until=_SEP)
    else:
        tx.amend(source.edit(**changes), until=_SEP)


def _flushes(calls: FlushCalls) -> list[tuple[str, list[Call]]]:
    return [(flush.trigger, call_runs(flush.calls)) for flush in calls.flushes]


@_LAYOUTS
@_REPRESENTATIONS
@_STRATEGIES
def test_each_page_flush_shares_the_coverage_reads_of_the_writes_its_page_delivered(
    profile_run: Any,
    layout: _Layout,
    representation: _Representation,
    concurrency: Literal["optimistic", "locking"],
) -> None:
    _seeded(profile_run, layout, _OBJECTS)
    calls = FlushCalls()

    def fn(tx: TxnContext) -> None:
        for root in _streamed(tx, layout, representation, batch_size=_PAGE):
            _amend(tx, root, amount=150)

    _db(profile_run, calls).transact(fn, concurrency=concurrency)
    assert calls.pages == [PageRead(_PAGE + 1, _PAGE + 1)] * 2 + [PageRead(_PAGE + 1, 4)]
    assert _flushes(calls) == [
        ("read_dependency", _PAGE_FLUSH),
        ("read_dependency", _PAGE_FLUSH),
        ("pre_commit", _LAST_PAGE_FLUSH),
    ]
    assert _history(profile_run, layout) == _corrected(range(1, _OBJECTS + 1))


@_LAYOUTS
@_REPRESENTATIONS
@_STRATEGIES
def test_an_eager_read_of_the_same_roots_shares_their_coverage_reads_in_one_flush(
    profile_run: Any,
    layout: _Layout,
    representation: _Representation,
    concurrency: Literal["optimistic", "locking"],
) -> None:
    _seeded(profile_run, layout, _OBJECTS)
    calls = FlushCalls()

    def fn(tx: TxnContext) -> None:
        for source in _found(tx, layout, representation):
            _amend(tx, source, amount=150)

    _db(profile_run, calls).transact(fn, concurrency=concurrency)
    assert calls.pages == []
    span: list[Call] = [("read", 32), ("write", _group_writes(32))]
    assert _flushes(calls) == [
        ("pre_commit", [*span, *span, ("read", 6), ("write", _group_writes(6))])
    ]
    assert _history(profile_run, layout) == _corrected(range(1, _OBJECTS + 1))


@_LAYOUTS
@_REPRESENTATIONS
def test_streamed_sources_written_again_after_their_flushes_read_no_coverage(
    profile_run: Any, layout: _Layout, representation: _Representation
) -> None:
    # Only the roots either side of each page boundary are kept; every other
    # root is released once its write is buffered.
    kept_keys = {1, _PAGE, _PAGE + 1, 2 * _PAGE, 2 * _PAGE + 1, _OBJECTS}
    _seeded(profile_run, layout, _OBJECTS)
    calls = FlushCalls()

    def fn(tx: TxnContext) -> None:
        kept: list[Any] = []
        for root in _streamed(tx, layout, representation, batch_size=_PAGE):
            _amend(tx, root, amount=150)
            if _key(root) in kept_keys:
                kept.append(root)
        tx.find(StreamFlag.where(StreamFlag.id == 1)).result()
        for source in kept:
            _amend(tx, source, label="again")

    _db(profile_run, calls).transact(fn)
    *corrections, continuation = calls.flushes
    assert [(flush.trigger, call_runs(flush.calls)) for flush in corrections] == [
        ("read_dependency", _PAGE_FLUSH),
        ("read_dependency", _PAGE_FLUSH),
        ("read_dependency", _LAST_PAGE_FLUSH),
    ]
    assert continuation.trigger == "pre_commit"
    assert continuation.coverage_reads == 0
    assert continuation.writes > 0
    assert _history(profile_run, layout) == _corrected(range(1, _OBJECTS + 1), again=kept_keys)


def test_a_default_page_flushes_1024_writes_in_32_shared_coverage_reads(
    profile_run: Any,
) -> None:
    objects = 1025
    _seeded(profile_run, "columns", objects)
    calls = FlushCalls()

    def fn(tx: TxnContext) -> None:
        for root in _streamed(tx, "columns", "typed"):
            _amend(tx, root, amount=150)

    _db(profile_run, calls).transact(fn)
    assert calls.pages == [PageRead(1025, 1025), PageRead(1025, 1)]
    page_flush, last_flush = calls.flushes
    assert page_flush.trigger == "read_dependency"
    assert call_runs(page_flush.calls) == [("read", 32), ("write", _group_writes(32))] * 32
    assert last_flush.trigger == "pre_commit"
    assert call_runs(last_flush.calls) == [("read", 1), ("write", _group_writes(1))]
    assert _history(profile_run, "columns") == _corrected(range(1, objects + 1))


# 35 roots at 33 per page, each tail stored as 40 daily milestones from June,
# so each write closes 41 milestones and opens 43 rows: the head's rest, its
# amended part, each tail piece's amended part, and the last piece's rest.
_PIECES: Final = 40
_FRAGMENTED: Final = 35
_FRAGMENT_CLOSES: Final = 1 + _PIECES
_FRAGMENT_OPENINGS: Final = 3 + _PIECES
_STATEMENT_CAP: Final = 64


def _invocations(closes: int) -> int:
    """The ordered invocations one contiguous run of ``closes`` takes: full
    ones of 64, and the rest in one more unless it is a lone close."""
    full, rest = divmod(closes, _STATEMENT_CAP)
    return full + (rest >= 2)


def _fragmented_group(writes: int) -> tuple[list[Call], int, int]:
    """One ready group of ``writes``: its coverage read and statements, its
    ordered invocations, and its insert statements."""
    inserts = -(-writes * _FRAGMENT_OPENINGS // _INSERT_ENTRIES)
    calls: list[Call] = [
        ("read", writes * _PIECES),
        ("write", writes * _FRAGMENT_CLOSES + inserts),
    ]
    return calls, _invocations(writes * _FRAGMENT_CLOSES), inserts


@_LAYOUTS
@_REPRESENTATIONS
def test_a_ready_groups_many_milestones_span_several_invocations_and_inserts_of_one_call_each(
    profile_run: Any, layout: _Layout, representation: _Representation
) -> None:
    _seeded(profile_run, layout, _FRAGMENTED, tail_pieces=_PIECES)
    calls = FlushCalls()
    tally = PortTally()
    decorated = DecoratingAdapter(
        profile_run.port, lambda connection: cast("Any", CountingConnection(connection, tally))
    )
    db = own_root(
        connect(decorated, _MODEL, clock=FixedClock(_AT), lifecycle_provider=calls)
    ).using_database_login()

    def fn(tx: TxnContext) -> None:
        for root in _streamed(tx, layout, representation, batch_size=_PAGE):
            _amend(tx, root, amount=150)

    db.transact(fn)
    span, span_invocations, span_inserts = _fragmented_group(32)
    alone, alone_invocations, alone_inserts = _fragmented_group(1)
    last, last_invocations, last_inserts = _fragmented_group(_FRAGMENTED - _PAGE)
    assert calls.pages == [PageRead(_PAGE + 1, _PAGE + 1), PageRead(_PAGE + 1, 2)]
    assert _flushes(calls) == [("read_dependency", [*span, *alone]), ("pre_commit", last)]
    closes = _FRAGMENTED * _FRAGMENT_CLOSES
    inserts = span_inserts + alone_inserts + last_inserts
    assert (span_invocations, span_inserts) == (21, 22)
    if psycopg.capabilities.has_pipeline():
        # 1312 closes in 21 invocations, 41 in one, and 82 in two: one
        # Database Call per statement, whichever invocation presented it.
        assert (tally.ordered, tally.ordered_statements, tally.widest_ordered) == (
            span_invocations + alone_invocations + last_invocations,
            closes,
            _STATEMENT_CAP,
        )
        assert tally.standalone_non_insert_statements == 0
    else:
        assert (tally.ordered, tally.standalone_non_insert_statements) == (0, closes)
    assert (tally.inserts, tally.inserted_rows, tally.widest_insert) == (
        inserts,
        _FRAGMENTED * _FRAGMENT_OPENINGS,
        _INSERT_ENTRIES,
    )
    assert _history(profile_run, layout) == _fragmented_corrected(
        range(1, _FRAGMENTED + 1), _PIECES
    )
