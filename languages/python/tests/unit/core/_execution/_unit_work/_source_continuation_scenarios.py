"""Writable reads published through the public seam, over a scripted port, as
sequences a memory or timing reading can run.

Each scenario opens a writable transaction, reads ``count`` rows of one family
eagerly or as a stream, and calls its sampler with every published value still
held, before the transaction ends. A scenario writing ``after`` its reads amends
one of the rows they published and flushes that amendment with a read; one
writing ``before`` them amends another row first, which their read flushes;
and one reading ``reinserted`` rows first deletes every row it reads and
inserts it again, its read flushing the insertions. Only Non-Temporal
families write before their reads.
They name only the public read and write verbs, so the same sequence runs
wherever those verbs do.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import Any, Final, Literal

from parallax.conformance.scripted_clock import FixedClock
from parallax.core.base import INFINITY
from parallax.snapshot import connect
from tests._support import mirrored_models as mm
from tests._support.db_port import Read, ScriptedAdapter, Transact, Write
from tests.unit._stream_page_support import paged_reads
from tests.unit._transact_support import ACCOUNT, BALANCE, FIXED, PERSON
from tests.unit._where_position_model import WHERE_POSITION_META, WherePosition

__all__ = [
    "BATCH",
    "Delivery",
    "Family",
    "Writes",
    "people_rows",
    "position_rows",
    "writable_reads",
]

type Delivery = Literal["eager", "stream"]
type Family = Literal["unversioned", "versioned", "txtime", "bitemporal"]
type Writes = Literal["none", "after", "before", "reinserted"]

BATCH: Final = 50
"""The page size a streamed scenario asks for."""


def people_rows(count: int, *, width: int = 8, start: int = 1) -> list[dict[str, object]]:
    """``count`` Person rows from key ``start`` whose names are ``width``
    characters long."""
    return [{"id": key, "name": f"{key:0{width}d}"[-width:]} for key in range(start, start + count)]


_OPENED: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def _balance_rows(count: int) -> list[dict[str, object]]:
    return [
        {
            "bal_id": key,
            "acct_num": f"A-{key}",
            "val": Decimal("5.00"),
            "in_z": _OPENED,
            "out_z": INFINITY,
        }
        for key in range(1, 1 + count)
    ]


def position_rows(count: int) -> list[dict[str, object]]:
    """``count`` WherePosition rows, each current over every Valid Time since
    January."""
    return [
        {
            "id": key,
            "acct_num": f"A-{key}",
            "value": Decimal("5.00"),
            "from_z": _OPENED,
            "thru_z": INFINITY,
            "in_z": _OPENED,
            "out_z": INFINITY,
        }
        for key in range(1, 1 + count)
    ]


_FAMILIES: Final[dict[str, tuple[Any, Any, Callable[[int], list[dict[str, object]]]]]] = {
    "txtime": (mm.Balance, BALANCE, _balance_rows),
    "bitemporal": (WherePosition, WHERE_POSITION_META, position_rows),
}


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
    entity: Any
    if family in _FAMILIES:
        entity, model, temporal_rows = _FAMILIES[family]
        rows = temporal_rows(count)
        script = _temporal_script(family, writes, delivery, rows)
    else:
        rows = people_rows(count, width=width) if unversioned else _account_rows(count)
        entity = mm.Person if unversioned else mm.Account
        model = PERSON if unversioned else ACCOUNT
        script = _script(writes, delivery, rows, unversioned=unversioned)
    query = entity.where(entity.id >= 1)
    flushing = entity.where(entity.id == -1)
    if family == "bitemporal":
        query = query.as_of(valid_time=FIXED)
        flushing = flushing.as_of(valid_time=FIXED)

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
                tx.find(flushing).results()
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


def _temporal_script(
    family: Family, writes: Writes, delivery: Delivery, rows: list[dict[str, object]]
) -> tuple[Read | Write, ...]:
    reads = [Read(rows=rows)] if delivery == "eager" else paged_reads(rows, size=BATCH)
    if writes == "none":
        return tuple(reads)
    if writes == "after":
        return (*reads, Write(), Write(), Read(rows=[]))
    raise ValueError(f"a {family} scenario writes only after its reads")


def _read(tx: Any, query: Any, delivery: Delivery) -> list[Any]:
    if delivery == "eager":
        return tx.find(query).results()
    with tx.stream(query, batch_size=BATCH) as stream:
        return list(stream)


def _amend(tx: Any, value: Any) -> None:
    if isinstance(value, mm.Person):
        tx.amend(value.edit(name="changed"))
    elif isinstance(value, mm.Account):
        tx.amend(value.edit(owner="Bo"))
    else:
        tx.amend(value.edit(acct_num="B"))


def _reinsert(tx: Any, entity: Any, rows: list[dict[str, object]]) -> None:
    for value in tx.find(entity.where(entity.id >= 1)).results():
        tx.delete(value)
    tx.find(entity.where(entity.id == -1)).results()
    for row in rows:
        tx.insert(entity(**{name: value for name, value in row.items() if name != "version"}))
