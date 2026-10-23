"""Deferred writes of distinct objects sharing their coverage reads, against
real Postgres (`m-unit-work` *Shared coverage acquisition*).

One shared read observes the database as of its own execution under Read
Committed, and the transaction's snapshot under Repeatable Read; the writes it
serves still each bind at their own turn, so a peer's commit between the read
and a later write's binding is the later write's conflict, and a peer's commit
between two reads is the later read's to observe. Under Locking the rows a
shared read selects hold the shared lock, and no other row does.

Every write runs under a clock answering 2024-11-01 on each attempt; the peer
commits at 2024-10-15.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any, Final

import pytest

from parallax.conformance.scripted_clock import FixedClock
from parallax.core import Attr, Bitemporal, DomainModel, attr
from parallax.core.base import INFINITY
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import IsolationLevel
from parallax.core.entity._model import model_of
from parallax.core.execution import ExecutionFailure
from parallax.snapshot import ScopedDatabase, TxnContext, connect
from tests._support.flush_calls import FlushCalls, call_runs
from tests._support.root_ownership import own_root
from tests.api._coverage_interleaving import AfterCoverageRead
from tests.api._peer_commit import commit_as_a_peer

_NAMESPACE: Final = "shared.coverage"


class ShareSpan(Bitemporal, table="share_span", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    label: Attr[str] = attr(max_length=16)


_MODEL: Final = DomainModel(ShareSpan)
_T0: Final = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_TP: Final = dt.datetime(2024, 10, 15, tzinfo=dt.UTC)
_AT: Final = dt.datetime(2024, 11, 1, tzinfo=dt.UTC)
_JAN, _MAR, _JUN, _SEP = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 6, 9))

type _Row = tuple[object, ...]
"""``(id, in_z, out_z, from_z, thru_z, amount)``, each open end ``None``."""


def _day(index: int) -> dt.datetime:
    return _JAN + dt.timedelta(days=index)


def _seeded(profile_run: Any, *, fragmented: bool = False) -> None:
    """Objects 1 and 2 as a head ``[January, June)`` at 100 and a tail ``[June,
    ∞)`` at 200, object 3 as one rectangle, and with ``fragmented`` object 4 as
    ``frag(4, 64)``: 128 rectangles ``[d_i, d_{i+1})`` at amount ``i``, the last
    one open; every row known from T0."""
    profile_run.reset(model_of(_MODEL), {})
    rows: list[tuple[int, int, str, dt.datetime, object]] = [
        (1, 100, "k1", _JAN, _JUN),
        (1, 200, "k1", _JUN, INFINITY),
        (2, 100, "k2", _JAN, _JUN),
        (2, 200, "k2", _JUN, INFINITY),
        (3, 100, "k3", _JAN, INFINITY),
    ]
    if fragmented:
        rows.extend(
            (4, index, "k4", _day(index), INFINITY if index == 127 else _day(index + 1))
            for index in range(128)
        )
    control = profile_run.control()
    try:
        for key, amount, label, start, end in rows:
            control.execute_write(
                "insert into share_span(id, amount, label, from_z, thru_z, in_z, out_z) "
                "values (%s, %s, %s, %s, %s, %s, %s)",
                [key, amount, label, start, end, _T0, INFINITY],
            )
    finally:
        control.close()


def _db(profile_run: Any, instant: dt.datetime, provider: Any = None) -> ScopedDatabase:
    return own_root(
        connect(profile_run.port, _MODEL, clock=FixedClock(instant), lifecycle_provider=provider)
    ).using_database_login()


def _rows(profile_run: Any, key: int) -> list[_Row]:
    rows = profile_run.port.execute(
        "select id, in_z, case when out_z = 'infinity' then null else out_z end, from_z, "
        "case when thru_z = 'infinity' then null else thru_z end, amount "
        "from share_span where id = %s order by in_z, out_z, from_z",
        [key],
    )
    return [tuple(row) for row in rows]


def _corrected(key: int, *, tail: int = 200, peer: bool = False) -> list[_Row]:
    """Object ``key``'s history once its March-to-September amendment to 150
    committed at AT over a tail at ``tail`` — P's, committed at TP, where
    ``peer``."""
    history: list[_Row] = [(key, _T0, _AT, _JAN, _JUN, 100)]
    if peer:
        history += [(key, _T0, _TP, _JUN, None, 200), (key, _TP, _AT, _JUN, None, tail)]
    else:
        history += [(key, _T0, _AT, _JUN, None, tail)]
    history += [
        (key, _AT, None, _JAN, _MAR, 100),
        (key, _AT, None, _MAR, _SEP, 150),
        (key, _AT, None, _SEP, None, tail),
    ]
    return sorted(history, key=_order)


def _order(row: _Row) -> tuple[object, ...]:
    _key, in_z, out_z, start, _end, _amount = row
    return in_z, dt.datetime.max.replace(tzinfo=dt.UTC) if out_z is None else out_z, start


def _fragmented_history() -> list[_Row]:
    """``frag(4, 64)``'s history once its 64 amendments committed at AT."""
    history: list[_Row] = [
        (4, _T0, _AT, _day(index), None if index == 127 else _day(index + 1), index)
        for index in range(128)
    ]
    history += [
        (4, _AT, None, _day(2 * pair), _day(2 * pair + 2), 1000 + pair) for pair in range(64)
    ]
    history.append((4, _AT, None, _day(128), None, 127))
    return sorted(history, key=_order)


_UNCHANGED: Final[list[_Row]] = [(3, _T0, None, _JAN, None, 100)]


def _peer_change(profile_run: Any) -> Callable[[], None]:
    """P: object 2's tail amended to 300 from June, as stated at T0."""
    peer = _db(profile_run, _TP)
    return lambda: peer.transact(
        lambda tx: tx.wire.amend_if(
            f"{_NAMESPACE}.ShareSpan", {"id": 2, "amount": 300}, valid_from=_JUN, tx_start=_T0
        )
    )


def _found(tx: TxnContext, key: int, at: dt.datetime) -> Any:
    return tx.find(ShareSpan.where(ShareSpan.id == key).as_of(valid_time=at)).result()


def _heads(tx: TxnContext) -> list[Any]:
    found = tx.find(
        ShareSpan.where((ShareSpan.id == 1) | (ShareSpan.id == 2)).as_of(valid_time=_MAR)
    ).results()
    return sorted(found, key=lambda span: span.id)


def _correct_both(attempts: list[int], before: Callable[[], None] | None = None) -> Any:
    def fn(tx: TxnContext) -> None:
        attempts.append(1)
        heads = _heads(tx)
        if before is not None and len(attempts) == 1:
            before()
        for head in heads:
            tx.amend(head.edit(amount=150), until=_SEP)

    return fn


# --------------------------------------------------------------------------- #
# A peer commit before or after the shared read.                              #
# --------------------------------------------------------------------------- #
def test_a_peer_commit_after_the_shared_read_is_the_later_writes_conflict_and_retried(
    profile_run: Any,
) -> None:
    _seeded(profile_run)
    interleaving = AfterCoverageRead("share_span", _peer_change(profile_run), nth=2)
    attempts: list[int] = []
    _db(profile_run, _AT, interleaving).transact(_correct_both(attempts))
    assert interleaving.failures == []
    # Object 2's tail close found the row P had closed; the retry read P's row.
    assert len(attempts) == 2
    assert _rows(profile_run, 1) == _corrected(1)
    assert _rows(profile_run, 2) == _corrected(2, tail=300, peer=True)
    assert _rows(profile_run, 3) == _UNCHANGED


@pytest.mark.parametrize(
    ("isolation", "attempted"), [("read_committed", 1), ("repeatable_read", 2)]
)
def test_a_peer_commit_before_the_shared_read_is_seen_as_the_isolation_level_sees_it(
    profile_run: Any, isolation: IsolationLevel, attempted: int
) -> None:
    _seeded(profile_run)
    attempts: list[int] = []
    peer = _peer_change(profile_run)
    _db(profile_run, _AT).transact(
        _correct_both(attempts, lambda: commit_as_a_peer(peer)), isolation=isolation
    )
    # Read Committed reads P's row; Repeatable Read reads the snapshot's tail,
    # whose close P's change makes a serialization failure, and retries.
    assert len(attempts) == attempted
    assert _rows(profile_run, 1) == _corrected(1)
    assert _rows(profile_run, 2) == _corrected(2, tail=300, peer=True)
    assert _rows(profile_run, 3) == _UNCHANGED


def test_a_serialization_failure_after_a_snapshot_read_is_a_retryable_deadlock(
    profile_run: Any,
) -> None:
    _seeded(profile_run)
    peer = _peer_change(profile_run)
    attempts: list[int] = []
    with pytest.raises(ExecutionFailure) as failed:
        _db(profile_run, _AT).transact(
            _correct_both(attempts, lambda: commit_as_a_peer(peer)),
            isolation="repeatable_read",
            max_retries=0,
        )
    cause = failed.value.cause
    assert isinstance(cause, DatabaseError)
    assert cause.category == "deadlock"


# --------------------------------------------------------------------------- #
# A peer commit between two shared reads.                                     #
# --------------------------------------------------------------------------- #
def _correct_fragmented(attempts: list[int]) -> Any:
    def fn(tx: TxnContext) -> None:
        attempts.append(1)
        pieces = [_found(tx, 4, _day(2 * pair)) for pair in range(64)]
        head = _found(tx, 2, _MAR)
        for pair, piece in enumerate(pieces):
            tx.amend(piece.edit(amount=1000 + pair), until=_day(2 * pair + 2))
        tx.amend(head.edit(amount=150), until=_SEP)

    return fn


@pytest.mark.parametrize(
    ("isolation", "attempted"), [("read_committed", 1), ("repeatable_read", 2)]
)
def test_a_peer_commit_between_two_shared_reads_is_the_later_reads_to_observe(
    profile_run: Any, isolation: IsolationLevel, attempted: int
) -> None:
    _seeded(profile_run, fragmented=True)
    # 65 finds read the table first, so the 66th read is the span's first.
    interleaving = AfterCoverageRead("share_span", _peer_change(profile_run), nth=66)
    calls = FlushCalls(interleaving)
    attempts: list[int] = []
    _db(profile_run, _AT, calls).transact(_correct_fragmented(attempts), isolation=isolation)
    assert interleaving.failures == []
    assert len(attempts) == attempted
    # The first read finishes object 4, which completes before the second
    # read reads object 2.
    first = next(flush for flush in calls.flushes if flush.calls)
    expected = [("read", 64), ("write", 130), ("read", 1), ("write", 3)]
    if isolation == "repeatable_read":
        assert call_runs(first.calls)[:3] == expected[:3]
    else:
        assert call_runs(first.calls) == expected
    assert _rows(profile_run, 4) == _fragmented_history()
    assert _rows(profile_run, 2) == _corrected(2, tail=300, peer=True)
    assert _rows(profile_run, 3) == _UNCHANGED


# --------------------------------------------------------------------------- #
# Under Locking, the shared read's selected rows hold the shared lock.        #
# --------------------------------------------------------------------------- #
def test_a_locking_shared_read_holds_the_lock_on_the_rows_it_selected_and_no_other(
    profile_run: Any,
) -> None:
    _seeded(profile_run)
    outcomes: list[object] = []

    def peer() -> None:
        for statement in (
            "update share_span set label = label "
            "where id = 2 and from_z = '2024-06-01' and out_z = 'infinity'",
            "update share_span set label = label "
            "where id = 3 and from_z = '2024-01-01' and out_z = 'infinity'",
        ):
            control = profile_run.control()
            try:
                control.execute_write("set lock_timeout = '200ms'", [])
                outcomes.append(control.execute_write(statement, []))
            except DatabaseError as failure:
                outcomes.append(failure.category)
            finally:
                control.close()

    interleaving = AfterCoverageRead("share_span", peer, nth=2)
    attempts: list[int] = []
    _db(profile_run, _AT, interleaving).transact(_correct_both(attempts), concurrency="locking")
    assert interleaving.failures == []
    # Object 2's selected tail is locked; object 3's row, which no read of
    # ours selected, is not.
    assert outcomes == ["lockWaitTimeout", 1]
    assert len(attempts) == 1
    assert _rows(profile_run, 1) == _corrected(1)
    assert _rows(profile_run, 2) == _corrected(2)
    assert _rows(profile_run, 3) == _UNCHANGED
