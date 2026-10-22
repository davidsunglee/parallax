"""A Bitemporal correction written through a participating stream, against
real Postgres (`m-unit-work` *Shared coverage acquisition*).

Every object stores a head ``[January, June)`` at 100 and a tail ``[June, ∞)``
at 200, both known from T0. Each root a stream delivers as of March is amended
to 150 until September, which reaches the tail its read did not observe, so
each write owes one missing coverage window. The page after a root's page
flushes its write, and pre-commit flushes the last page's: each Flush reads its
writes' coverage in shared reads of at most 32 consecutive writes, while every
write still runs its own statements. An eager read of the same roots buffers
every write into one Flush, and a source written again after its write
completed reads nothing.

Each case reads the whole stored history back and compares it with the one
these inputs determine. Every write runs under a clock answering 2024-11-01.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable, Iterator
from typing import Any, Final, Literal, cast

import pytest

from parallax.conformance.scripted_clock import FixedClock
from parallax.core import Attr, Bitemporal, Document, DomainModel, Entity, attr
from parallax.core.base import INFINITY
from parallax.core.entity._model import model_of
from parallax.snapshot import ScopedDatabase, TxnContext, WireEntity, connect
from tests._support.root_ownership import own_root
from tests.api._flush_calls import Call, FlushCalls, PageRead, call_runs

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

# 70 roots at 33 per page: pages of 33, 33, and 4 roots. A 33-write Flush is
# one shared read of 32 writes' coverage and one read of the 33rd write's.
_OBJECTS: Final = 70
_PAGE: Final = 33
_PAGE_FLUSH: Final[list[Call]] = [("read", 32), ("write", 96), ("read", 1), ("write", 3)]
_LAST_PAGE_FLUSH: Final[list[Call]] = [("read", 4), ("write", 12)]

type _Layout = Literal["columns", "document"]
type _Representation = Literal["typed", "wire"]
type _Row = tuple[object, ...]
"""``(id, in_z, out_z, from_z, thru_z, amount, label)``, each open end ``None``."""

_ENTITIES: Final = {"columns": StreamColumns, "document": StreamDocument}
_LAYOUTS = pytest.mark.parametrize("layout", ["columns", "document"])
_REPRESENTATIONS = pytest.mark.parametrize("representation", ["typed", "wire"])
_STRATEGIES = pytest.mark.parametrize("concurrency", ["optimistic", "locking"])


def _seeded(profile_run: Any, layout: _Layout, objects: int) -> None:
    profile_run.reset(model_of(_MODEL), {})
    rows = [
        (key, amount, f"k{key}", start, end)
        for key in range(1, objects + 1)
        for amount, start, end in ((100, _JAN, _JUN), (200, _JUN, INFINITY))
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
    span: list[Call] = [("read", 32), ("write", 96)]
    assert _flushes(calls) == [("pre_commit", [*span, *span, ("read", 6), ("write", 18)])]
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
    assert call_runs(page_flush.calls) == [("read", 32), ("write", 96)] * 32
    assert last_flush.trigger == "pre_commit"
    assert call_runs(last_flush.calls) == [("read", 1), ("write", 3)]
    assert _history(profile_run, "columns") == _corrected(range(1, objects + 1))
