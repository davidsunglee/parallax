"""Writable reads published through the public seam, over a scripted port, as
sequences a memory or timing reading can run.

Each scenario opens a writable transaction, reads ``count`` Non-Temporal rows
eagerly or as a stream, and calls its sampler with every published value still
held, before the transaction ends. A scenario writing ``after`` its reads amends
one of the rows they published and flushes that amendment with a read; one
writing ``before`` them amends another row first, which their read flushes;
and one reading ``reinserted`` rows first deletes every row it reads and
inserts it again, its read flushing the insertions.
They name only the public read and write verbs, so the same sequence runs
wherever those verbs do.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any, Final, Literal

from parallax.conformance.scripted_clock import FixedClock
from parallax.snapshot import connect
from tests._support import mirrored_models as mm
from tests._support.db_port import Read, ScriptedAdapter, Transact, Write
from tests.unit._stream_page_support import paged_reads
from tests.unit._transact_support import ACCOUNT, FIXED, PERSON

__all__ = ["BATCH", "Delivery", "Family", "Writes", "people_rows", "writable_reads"]

type Delivery = Literal["eager", "stream"]
type Family = Literal["unversioned", "versioned"]
type Writes = Literal["none", "after", "before", "reinserted"]

BATCH: Final = 50
"""The page size a streamed scenario asks for."""


def people_rows(count: int, *, width: int = 8, start: int = 1) -> list[dict[str, object]]:
    """``count`` Person rows from key ``start`` whose names are ``width``
    characters long."""
    return [{"id": key, "name": f"{key:0{width}d}"[-width:]} for key in range(start, start + count)]


def _account_rows(count: int, *, start: int = 1) -> list[dict[str, object]]:
    return [
        {"id": key, "owner": "Ada", "balance": Decimal("1.00"), "version": 1}
        for key in range(start, start + count)
    ]


def writable_reads(
    family: Family,
    delivery: Delivery,
    count: int,
    *,
    writes: Writes = "none",
    width: int = 8,
) -> Callable[[Callable[[], None]], None]:
    """One writable transaction publishing ``count`` rows of ``family``, calling
    its sampler while every published value is held, writing as ``writes``
    says."""
    unversioned = family == "unversioned"
    rows = people_rows(count, width=width) if unversioned else _account_rows(count)
    entity: Any = mm.Person if unversioned else mm.Account
    model = PERSON if unversioned else ACCOUNT
    script = _script(writes, delivery, rows, unversioned=unversioned)
    query = entity.where(entity.id >= 1)

    def run(sample: Callable[[], None]) -> None:
        port = ScriptedAdapter(Transact(*script))

        def body(tx: Any) -> None:
            if writes == "before":
                _amend(tx, tx.find(entity.where(entity.id == 0)).result())
            elif writes == "reinserted":
                _reinsert(tx, entity, rows)
            held = _read(tx, query, delivery)
            if writes == "after":
                _amend(tx, held[0])
                tx.find(entity.where(entity.id == -1)).results()
            sample()
            assert len(held) == count

        with connect(port, model, clock=FixedClock(FIXED)) as root:
            root.using_database_login().transact(body)

    return run


def _script(
    writes: Writes, delivery: Delivery, rows: list[dict[str, object]], *, unversioned: bool
) -> tuple[Read | Write, ...]:
    reads = [Read(rows=rows)] if delivery == "eager" else paged_reads(rows, size=BATCH)
    if writes == "before":
        other = people_rows(1, start=0) if unversioned else _account_rows(1, start=0)
        return (Read(rows=other), Write(), *reads)
    if writes == "reinserted":
        count = len(rows)
        deletions = Write(affected=count) if unversioned else Write(times=count)
        return (Read(rows=rows), deletions, Read(rows=[]), Write(affected=count), *reads)
    if writes == "after":
        return (*reads, Write(), Read(rows=[]))
    return tuple(reads)


def _read(tx: Any, query: Any, delivery: Delivery) -> list[Any]:
    if delivery == "eager":
        return tx.find(query).results()
    with tx.stream(query, batch_size=BATCH) as stream:
        return list(stream)


def _amend(tx: Any, value: Any) -> None:
    tx.amend(value.edit(name="changed") if isinstance(value, mm.Person) else value.edit(owner="Bo"))


def _reinsert(tx: Any, entity: Any, rows: list[dict[str, object]]) -> None:
    for value in tx.find(entity.where(entity.id >= 1)).results():
        tx.delete(value)
    tx.find(entity.where(entity.id == -1)).results()
    for row in rows:
        tx.insert(entity(**{name: value for name, value in row.items() if name != "version"}))
