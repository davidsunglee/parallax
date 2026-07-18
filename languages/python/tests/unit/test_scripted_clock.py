"""D-29 per-story clock control unit tests (COR-3 Phase 8 increment 7
completion round): :class:`~parallax.conformance.scripted_clock.ScriptedClock`
itself, plus the consumption contract it must honor through
``Database.transact`` (Docker-free fake port). The memoized-per-``UnitOfWork``
clock read (`unit_work/uow.py`'s own ``_processing_instant_literal``) means
each FLUSHING ``db.transact`` call consumes exactly one scripted instant, a
force-flush (``tx.find``) shares the SAME instant as its own transaction's
commit flush, and a fully read-only/empty transact consumes none at all (the
shell-level half of this same truth is pinned independently,
``test_uow_shell.test_a_fully_empty_transaction_never_touches_the_clock``).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from decimal import Decimal

import pytest

from parallax.conformance import models
from parallax.conformance.scripted_clock import ClockExhaustedError, ScriptedClock
from parallax.conformance.story_models import Account
from parallax.core.db_port import Bind, DbPort, Row
from parallax.core.unit_work import FixedClock
from parallax.snapshot.handle import Database, Transaction

pytestmark = pytest.mark.unit

_ACCOUNT = models.load_models()["account"]
_I1 = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_I2 = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


class _RecordingPort:
    """A minimal in-memory ``m-db-port`` counting writes and serving a fixed
    row set to every read — only the shape these consumption-contract pins
    need (contrast `test_write_no_drift._RecordingPort`'s fuller wire-golden
    proof)."""

    def __init__(self, *, rows: Sequence[Row] = ()) -> None:
        self.write_count = 0
        self._rows = [dict(row) for row in rows]

    def execute(self, sql: str, binds: Sequence[Bind]) -> list[Row]:
        return [dict(row) for row in self._rows]

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        self.write_count += 1
        return 1

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        return body(self)


def _account(account_id: int) -> Account:
    return Account(id=account_id, owner="Newton", balance=Decimal("5.00"), version=1)


# --------------------------------------------------------------------------- #
# ScriptedClock itself.                                                        #
# --------------------------------------------------------------------------- #
def test_scripted_clock_yields_instants_in_order() -> None:
    clock = ScriptedClock([_I1, _I2])
    assert clock.now() == _I1
    assert clock.now() == _I2


def test_scripted_clock_normalizes_on_construction() -> None:
    naive = dt.datetime(2024, 1, 1)  # no tzinfo — rejected exactly like FixedClock
    with pytest.raises(ValueError):
        ScriptedClock([naive])


def test_scripted_clock_exhaustion_raises_loudly() -> None:
    clock = ScriptedClock([_I1])
    assert clock.now() == _I1
    with pytest.raises(ClockExhaustedError):
        clock.now()


def test_scripted_clock_requires_at_least_one_instant() -> None:
    with pytest.raises(ValueError):
        ScriptedClock([])


# --------------------------------------------------------------------------- #
# The consumption contract through `Database.transact`.                        #
# --------------------------------------------------------------------------- #
def test_each_flushing_transact_consumes_one_scripted_instant() -> None:
    port = _RecordingPort()
    db = Database.connect(port, _ACCOUNT, clock=ScriptedClock([_I1, _I2]))

    db.transact(lambda tx: tx.insert(_account(1)))
    db.transact(lambda tx: tx.insert(_account(2)))
    assert port.write_count == 2

    # The two-instant script is now exhausted — a THIRD flushing transaction
    # asks the clock for an instant it never scripted.
    with pytest.raises(ClockExhaustedError):
        db.transact(lambda tx: tx.insert(_account(3)))


def test_force_flush_and_commit_flush_share_one_instant_in_one_transaction() -> None:
    port = _RecordingPort(rows=[{"id": 7, "owner": "Newton", "balance": 5.00, "version": 1}])
    db = Database.connect(port, _ACCOUNT, clock=ScriptedClock([_I1, _I2]))

    def fn(tx: Transaction) -> None:
        tx.insert(_account(7))
        tx.find(Account.where(Account.id == 7))  # force-flushes the buffered insert

    db.transact(fn)  # ONE flushing transaction (force-flush + a no-op commit flush)
    db.transact(lambda tx: tx.insert(_account(8)))  # the SECOND (and last) scripted instant
    with pytest.raises(ClockExhaustedError):
        db.transact(lambda tx: tx.insert(_account(9)))


def test_a_read_only_transact_consumes_no_scripted_instant() -> None:
    port = _RecordingPort(rows=[{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}])
    db = Database.connect(port, _ACCOUNT, clock=ScriptedClock([_I1]))

    db.transact(lambda tx: tx.find(Account.where(Account.id == 1)).result())
    # The single scripted instant is untouched — still available for a write.
    db.transact(lambda tx: tx.insert(_account(2)))
    with pytest.raises(ClockExhaustedError):
        db.transact(lambda tx: tx.insert(_account(3)))


def test_a_fixed_clock_factory_story_still_works_single_instant() -> None:
    # A story authored with `clock=lambda: FixedClock(instant)` (a single-
    # instant witness) is unaffected — `WriteStory.clock`'s own type
    # (`Callable[[], Clock]`) admits any `Clock`, not only `ScriptedClock`, and
    # a `FixedClock` never exhausts across successive flushes.
    port = _RecordingPort()
    db = Database.connect(port, _ACCOUNT, clock=FixedClock(_I1))
    db.transact(lambda tx: tx.insert(_account(1)))
    db.transact(lambda tx: tx.insert(_account(2)))
    assert port.write_count == 2
