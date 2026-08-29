"""Per-story clock-control tests for ``ScriptedClock`` and ``Database.transact``.

The Transaction Instant a unit of work owns is lazy (ADR 0010), so a transaction
consumes a scripted instant only when its surviving writes actually need a
Transaction-Time boundary: an empty, read-only, coalesced-away, or purely
non-temporal transaction consumes none, a temporal one consumes exactly one
across its force-flush and its commit flush, and a retry attempt captures afresh
only if it independently reaches such work. Every assertion here reads the clock
indirectly, through script exhaustion and write counts, rather than by mocking
``now()``. ``test_uow_shell`` independently covers the shell-level rules.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from _support.db_port import (
    Read,
    ScriptedPort,
    Transact,
    Write,
    WriteCall,
)
from parallax.conformance.class_models import MODELS
from parallax.conformance.read_models import Balance
from parallax.conformance.scripted_clock import ClockExhaustedError, ScriptedClock
from parallax.conformance.story_models import Account
from parallax.core.db_error import DatabaseError
from parallax.core.unit_work import FixedClock
from parallax.snapshot.handle import Database, Transaction

_ACCOUNT = MODELS["account"]
_BALANCE = MODELS["balance"]
_I1 = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_I2 = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


def _writes(port: ScriptedPort) -> int:
    return sum(1 for call in port.calls if isinstance(call, WriteCall))


def _deadlock() -> DatabaseError:
    return DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")


def _account(account_id: int) -> Account:
    return Account(id=account_id, owner="Newton", balance=Decimal("5.00"))


def _balance(balance_id: int) -> Balance:
    """A Transaction-Time-Only instance — the timestamp-requiring write shape."""
    return Balance(id=balance_id, acct_num="A-1", value=Decimal("5.00"))


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
def test_each_flushing_temporal_transact_consumes_one_scripted_instant() -> None:
    port = ScriptedPort(Transact(Write()), Transact(Write()), Transact(Write()))
    db = Database.connect(port, _BALANCE, clock=ScriptedClock([_I1, _I2]))

    db.transact(lambda tx: tx.insert(_balance(1)))
    db.transact(lambda tx: tx.insert(_balance(2)))
    assert _writes(port) == 2

    # The two-instant script is now exhausted — a THIRD flushing transaction
    # asks the clock for an instant it never scripted.
    with pytest.raises(ClockExhaustedError):
        db.transact(lambda tx: tx.insert(_balance(3)))


def test_force_flush_and_commit_flush_share_one_instant_in_one_transaction() -> None:
    port = ScriptedPort(Transact(Write(), Read(), Write()), Transact(Write()), Transact())
    db = Database.connect(port, _BALANCE, clock=ScriptedClock([_I1, _I2]))

    def fn(tx: Transaction) -> None:
        tx.insert(_balance(7))
        tx.find(Balance.where(Balance.id == 7))  # force-flushes the buffered insert
        tx.insert(_balance(8))  # the commit flush reuses the SAME captured instant

    db.transact(fn)  # ONE instant across two flushes in one attempt
    assert _writes(port) == 2

    db.transact(lambda tx: tx.insert(_balance(9)))  # the SECOND (and last) scripted instant
    with pytest.raises(ClockExhaustedError):
        db.transact(lambda tx: tx.insert(_balance(10)))


def test_an_empty_or_read_only_transact_consumes_no_scripted_instant() -> None:
    clock = ScriptedClock([_I1])
    port = ScriptedPort(
        Transact(),
        Transact(
            Read(rows=[{"id": 1, "owner": "Ada", "balance": Decimal("100.00"), "version": 1}])
        ),
    )
    account_db = Database.connect(port, _ACCOUNT, clock=clock)

    account_db.transact(lambda tx: None)
    account_db.transact(lambda tx: tx.find(Account.where(Account.id == 1)).result())

    # The single scripted instant is untouched — still available for a temporal write.
    Database.connect(ScriptedPort(Transact(Write())), _BALANCE, clock=clock).transact(
        lambda tx: tx.insert(_balance(2))
    )


def test_a_nonempty_non_temporal_flush_consumes_no_scripted_instant() -> None:
    # A non-temporal write binds no Transaction-Time boundary, so the flush —
    # including the force-flush a dependent read triggers — never asks the Clock
    # Strategy for one.
    clock = ScriptedClock([_I1])
    port = ScriptedPort(
        Transact(
            Write(),
            Read(rows=[{"id": 7, "owner": "Newton", "balance": Decimal("5.00"), "version": 1}]),
        )
    )
    account_db = Database.connect(port, _ACCOUNT, clock=clock)

    def fn(tx: Transaction) -> None:
        tx.insert(_account(7))
        tx.find(Account.where(Account.id == 7))  # force-flushes the buffered insert

    account_db.transact(fn)
    assert _writes(port) == 1

    # The single scripted instant is still available, proving nothing above took it.
    Database.connect(ScriptedPort(Transact(Write())), _BALANCE, clock=clock).transact(
        lambda tx: tx.insert(_balance(1))
    )


def test_a_coalesced_away_buffer_consumes_no_scripted_instant() -> None:
    # The buffer is nonempty at flush, but same-transaction coalescing cancels
    # the pair before any surviving write could need a Transaction-Time
    # boundary — so no DML runs and no instant is captured.
    port = ScriptedPort(Transact(), Transact(Write()), Transact(Write()))
    db = Database.connect(port, _BALANCE, clock=ScriptedClock([_I1]))

    def fn(tx: Transaction) -> None:
        fresh = _balance(1)
        tx.insert(fresh)
        tx.terminate(fresh)

    db.transact(fn)
    assert _writes(port) == 0

    # The single scripted instant survives for a transaction that does reach work.
    db.transact(lambda tx: tx.insert(_balance(2)))
    with pytest.raises(ClockExhaustedError):
        db.transact(lambda tx: tx.insert(_balance(3)))


def test_a_retry_attempt_captures_a_fresh_instant() -> None:
    # A retry is a new attempt with its own unit of work, hence its own lazy
    # instant: the failed attempt's capture is never reused.
    port = ScriptedPort(Transact(Write(raises=_deadlock())), Transact(Write()), Transact(Write()))
    db = Database.connect(port, _BALANCE, clock=ScriptedClock([_I1, _I2]))

    db.transact(lambda tx: tx.insert(_balance(1)))
    assert _writes(port) == 2  # attempt 0's write failed, the retry's succeeded

    # Both scripted instants are gone — one per attempt that reached temporal work.
    with pytest.raises(ClockExhaustedError):
        db.transact(lambda tx: tx.insert(_balance(2)))


def test_a_retry_that_reaches_no_timestamp_requiring_work_captures_no_instant() -> None:
    clock = ScriptedClock([_I1])
    port = ScriptedPort(Transact(Write(raises=_deadlock())), Transact(Write()))
    account_db = Database.connect(port, _ACCOUNT, clock=clock)

    account_db.transact(lambda tx: tx.insert(_account(1)))
    assert _writes(port) == 2  # attempt 0's write failed, the retry's succeeded

    # Neither attempt asked the clock, so the single scripted instant is intact.
    Database.connect(ScriptedPort(Transact(Write())), _BALANCE, clock=clock).transact(
        lambda tx: tx.insert(_balance(2))
    )


def test_a_fixed_clock_factory_story_still_works_single_instant() -> None:
    # A story authored with `clock=lambda: FixedClock(instant)` (a single-
    # instant witness) is unaffected — `WriteStory.clock`'s own type
    # (`Callable[[], Clock]`) admits any `Clock`, not only `ScriptedClock`, and
    # a `FixedClock` never exhausts across successive flushes.
    port = ScriptedPort(Transact(Write()), Transact(Write()))
    db = Database.connect(port, _BALANCE, clock=FixedClock(_I1))
    db.transact(lambda tx: tx.insert(_balance(1)))
    db.transact(lambda tx: tx.insert(_balance(2)))
    assert _writes(port) == 2
