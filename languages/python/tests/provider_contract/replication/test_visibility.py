"""What a reader observes of the writer's changes on a real streaming standby.

The writer commits ``local`` while the standby's replay is paused, so the
standby lags by exactly what was committed during the pause; resuming replay
and waiting on the primary's log position ends the lag. A standalone stream
leases each page separately and so shares no snapshot across pages; only a
Repeatable Read transaction gives a stream one, which on a lagging reader is
stale from its start.
"""

from __future__ import annotations

from contextlib import ExitStack
from typing import Any

import pytest

from parallax.snapshot import ReadOnlyTxnContext, connect
from tests._support.bindings import TEST_BINDING
from tests._support.root_ownership import own_root
from tests._support.routed_reads import (
    MODEL,
    READS,
    SEEDED,
    STREAMS,
    Ledger,
    identity,
    insert,
)
from tests.provider_contract.replication._replication_support import replicated

pytestmark = pytest.mark.xdist_group("replication")

_LAGGING = [3, 4]


def _lagging_scope(profile_run: Any) -> Any:
    pair = replicated(profile_run)
    db = own_root(
        connect(pair.adapter(synchronous_commit="local"), MODEL, binding=TEST_BINDING)
    ).using_database_login()
    return pair, db


@pytest.mark.parametrize("representation", list(STREAMS))
def test_a_standalone_stream_can_exhaust_before_lagging_rows_appear(
    profile_run: Any, representation: str
) -> None:
    pair, db = _lagging_scope(profile_run)
    streamed = STREAMS[representation]

    with pair.paused_replay():
        insert(db, Ledger, *_LAGGING)
        lsn = pair.writer_lsn()
        with streamed(db, Ledger) as rows:
            on_reader = [identity(row) for row in rows]
        with streamed(db.with_routing(read_policy="writer_only"), Ledger) as rows:
            on_writer = [identity(row) for row in rows]
    pair.wait_replayed(lsn)
    with streamed(db, Ledger) as rows:
        replayed = [identity(row) for row in rows]

    assert on_reader == SEEDED
    assert on_writer == replayed == [*SEEDED, *_LAGGING]


@pytest.mark.parametrize("representation", list(STREAMS))
def test_a_standalone_streams_later_pages_see_what_replayed_after_its_first(
    profile_run: Any, representation: str
) -> None:
    pair, db = _lagging_scope(profile_run)

    with ExitStack() as paused:
        paused.enter_context(pair.paused_replay())
        insert(db, Ledger, *_LAGGING)
        lsn = pair.writer_lsn()
        at_first_page = READS["typed-eager"](db, Ledger)
        with STREAMS[representation](db, Ledger) as rows:
            pages = iter(rows)
            first = identity(next(pages))
            paused.close()
            pair.wait_replayed(lsn)
            later = [identity(row) for row in pages]

    assert at_first_page == SEEDED
    assert [first, *later] == [*SEEDED, *_LAGGING]


@pytest.mark.parametrize("representation", list(STREAMS))
def test_a_repeatable_read_stream_on_the_reader_keeps_its_first_snapshot(
    profile_run: Any, representation: str
) -> None:
    pair, db = _lagging_scope(profile_run)

    with ExitStack() as paused:
        paused.enter_context(pair.paused_replay())
        insert(db, Ledger, *_LAGGING)
        lsn = pair.writer_lsn()

        def body(tx: ReadOnlyTxnContext) -> tuple[list[int], list[int]]:
            with STREAMS[representation](tx, Ledger) as rows:
                pages = iter(rows)
                first = identity(next(pages))
                paused.close()
                pair.wait_replayed(lsn)
                streamed = [first, *(identity(row) for row in pages)]
            return streamed, [
                ledger.id for ledger in tx.find(Ledger.where(Ledger.id >= 0)).results()
            ]

        streamed, found_after = db.read_only(body, isolation="repeatable_read")

    assert streamed == SEEDED
    assert sorted(found_after) == SEEDED
    assert READS["typed-eager"](db, Ledger) == [*SEEDED, *_LAGGING]
