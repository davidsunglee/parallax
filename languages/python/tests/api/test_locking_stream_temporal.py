from __future__ import annotations

import datetime as dt
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest

from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import Attr, Document, DomainModel, TemporalBound, TxTemporal, attr
from parallax.core.entity import model_of
from parallax.core.execution import RetryPolicy
from parallax.snapshot import TxnContext, connect, edge_of
from tests._support.root_ownership import own_root

_NAMESPACE = "locking.stream.temporal"
_JAN, _FEB, _MAR = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 2, 3))


class ColumnsMilestone(TxTemporal, table="ls_columns_milestone", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    seats: Attr[int]


class DocumentMilestone(
    TxTemporal, table="ls_document_milestone", namespace=_NAMESPACE, layout=Document()
):
    id: Attr[int] = attr(primary_key=True)
    seats: Attr[int]


_MODEL = DomainModel(ColumnsMilestone, DocumentMilestone)
_TABLES = {
    ColumnsMilestone: "ls_columns_milestone",
    DocumentMilestone: "ls_document_milestone",
}


@pytest.mark.parametrize("wire", [False, True], ids=["typed", "wire"])
@pytest.mark.parametrize("entity", [ColumnsMilestone, DocumentMilestone])
def test_a_locking_continuation_never_publishes_a_closed_current_milestone(
    profile_run: Any, entity: type[Any], wire: bool
) -> None:
    profile_run.reset(model_of(_MODEL), {})
    db = own_root(
        connect(profile_run.port, _MODEL, clock=ScriptedClock([_JAN, _MAR]))
    ).using_database_login()
    db.transact(lambda tx: [tx.insert(entity(id=key, seats=4)) for key in range(1, 6)])
    first_page = threading.Event()
    updated = threading.Event()
    observed: dict[int, int] = {}
    failures: list[BaseException] = []
    table = _TABLES[entity]
    member = "(payload->>'seats')::int" if entity is DocumentMilestone else "seats"

    def read(tx: TxnContext) -> None:
        name = f"{_NAMESPACE}.{entity.__name__}"
        stream = (
            tx.wire.stream(
                {
                    "target": name,
                    "predicate": {"true": {}},
                    "temporal": {"transaction-time": {"asOf": "latest"}},
                    "orderBy": [{"attr": f"{name}.id", "direction": "asc"}],
                },
                batch_size=2,
            )
            if wire
            else tx.stream(entity.where(entity.all).order_by(entity.id.asc()), batch_size=2)
        )
        with stream as roots:
            iterator: Iterator[Any] = iter(roots)
            for expected in (1, 2):
                row = next(iterator)
                assert (row["id"] if wire else row.id) == expected
            first_page.set()
            assert updated.wait(10), "the peer never closed its milestone"
            for row in iterator:
                key = row["id"] if wire else row.id
                seats = row["seats"] if wire else row.seats
                assert key in (3, 4, 5)
                assert seats == (8 if key == 4 else 4)
                assert edge_of(row).tx_time == (_FEB if key == 4 else _JAN)
                assert (row["txEnd"] if wire else row.tx_end) == (
                    "infinity" if wire else TemporalBound.INFINITY
                )
                observed[key] = seats
                if wire:
                    tx.wire.amend(row, {"seats": seats + 1})
                else:
                    tx.amend(row.edit(seats=seats + 1))

    def run() -> None:
        try:
            db.transact(read, concurrency="locking", retry=RetryPolicy(max_retries=0))
        except BaseException as failure:
            failures.append(failure)

    peer = profile_run.control(autocommit=False)
    observer = profile_run.control()
    worker = threading.Thread(target=run)
    try:
        peer_pid = peer.execute("select pg_backend_pid()", [])[0][0]
        worker.start()
        assert first_page.wait(10), "the first page did not finish"
        # The first page also locks its lookahead row, id 3.
        assert (
            peer.execute_write(
                f"update {table} set out_z = %s where id = 4 and out_z = 'infinity'", [_FEB]
            )
            == 1
        )
        payload = "payload" if entity is DocumentMilestone else "seats"
        value = "'{\"seats\": 8}'" if entity is DocumentMilestone else "8"
        assert (
            peer.execute_write(
                f"insert into {table} (id, {payload}, in_z, out_z) "
                f"values (4, {value}, %s, 'infinity')",
                [_FEB],
            )
            == 1
        )
        updated.set()
        _wait_for_peer_lock(observer, peer_pid, worker)
        peer.execute("commit", [])
        worker.join(timeout=10)
        assert not worker.is_alive(), "the continuation did not finish after the peer committed"
    finally:
        updated.set()
        peer.close()
        worker.join(timeout=10)
        observer.close()
    if failures:
        raise failures[0]

    assert observed.get(3) == observed.get(5) == 4
    current = [
        tuple(row)
        for row in profile_run.port.execute(
            f"select id, {member} from {table} where out_z = 'infinity' order by id", []
        )
    ]
    assert current == [(1, 4), (2, 4), (3, 5), (4, 9 if 4 in observed else 8), (5, 5)]
    history = profile_run.port.execute(
        f"select in_z, out_z, {member} from {table} where id = 4 and in_z = %s", [_JAN]
    )
    assert [tuple(row) for row in history] == [(_JAN, _FEB, 4)]


def _wait_for_peer_lock(observer: Any, peer_pid: object, worker: threading.Thread) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        rows = observer.execute(
            "select count(*) from pg_stat_activity "
            "where datname = current_database() and wait_event_type = 'Lock' "
            "and %s = any(pg_blocking_pids(pid))",
            [peer_pid],
        )
        if rows[0][0]:
            return
        assert worker.is_alive(), "the continuation completed without waiting for the peer"
        threading.Event().wait(0.01)
    raise AssertionError("the continuation never waited for the peer's row lock")
