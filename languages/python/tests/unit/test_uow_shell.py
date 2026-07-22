"""Unit-of-work shell unit tests (m-unit-work, Docker-free).

Exercises the transaction-scope state machine independently of any real port or
SQL lowering (the flush is an injected neutral executor): the frame stack (a
nested scope joins the active transaction, ADR 0005), rollback-only doom and
re-entry refusal, abort that discards buffered effects and withholds the callback
value (ADR 0006), read-your-own-writes force-flush, Clock injection, and
use-after-scope rejection.
"""

from __future__ import annotations

import contextlib
import datetime as dt
from collections.abc import Callable

import pytest

from parallax.conformance import models
from parallax.core.descriptor import Metamodel
from parallax.core.unit_work import (
    Clock,
    EscapedTransactionError,
    FixedClock,
    FlushExecutor,
    FlushPlan,
    KeyedWrite,
    Observation,
    RollbackOnlyError,
    SystemClock,
    TransactionSettings,
    UnitOfWork,
    active_unit_of_work,
    run_unit_of_work,
)

pytestmark = pytest.mark.unit

_MODELS = models.load_models()
_ACCOUNT = _MODELS["account"]
_BALANCE = _MODELS["balance"]
_FIXED = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


class _Recorder:
    """Records each flush plan the shell hands the executor."""

    def __init__(self) -> None:
        self.plans: list[FlushPlan] = []

    def __call__(self, plan: FlushPlan) -> None:
        self.plans.append(plan)


class _CountingClock:
    """A clock that yields a scripted instant per call and counts its calls."""

    def __init__(self, instants: list[dt.datetime]) -> None:
        self._instants = instants
        self.calls = 0

    def now(self) -> dt.datetime:
        self.calls += 1
        return self._instants[self.calls - 1]


def _noop(plan: FlushPlan) -> None:
    return None


def _run[T](
    body: Callable[[UnitOfWork], T],
    *,
    clock: Clock | None = None,
    executor: FlushExecutor | None = None,
    settings: TransactionSettings | None = None,
    meta: Metamodel | None = None,
) -> T:
    return run_unit_of_work(
        body,
        settings=settings or TransactionSettings(),
        clock=clock or FixedClock(_FIXED),
        meta=meta or _ACCOUNT,
        flush_executor=executor or _noop,
    )


def _account_insert(account_id: int) -> KeyedWrite:
    return KeyedWrite("insert", "Account", ({"id": account_id, "owner": "N", "balance": 5.00},))


# --------------------------------------------------------------------------- #
# Commit / abort at the outermost boundary.                                    #
# --------------------------------------------------------------------------- #
def test_outermost_commit_flushes_and_returns_value() -> None:
    recorder = _Recorder()

    def body(tx: UnitOfWork) -> str:
        tx.buffer(_account_insert(9))
        return "ok"

    assert _run(body, executor=recorder) == "ok"
    assert len(recorder.plans) == 1
    assert len(recorder.plans[0].writes) == 1


def test_active_unit_of_work_tracks_the_scope() -> None:
    assert active_unit_of_work() is None
    seen: dict[str, object] = {}

    def body(tx: UnitOfWork) -> None:
        seen["same"] = active_unit_of_work() is tx
        assert tx.is_rollback_only is False
        assert tx.is_joined is False

    _run(body)
    assert seen["same"] is True
    assert active_unit_of_work() is None


def test_body_exception_aborts_discards_and_withholds() -> None:
    recorder = _Recorder()
    captured: dict[str, UnitOfWork] = {}

    def body(tx: UnitOfWork) -> str:
        tx.buffer(_account_insert(9))
        captured["tx"] = tx
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        _run(body, executor=recorder)
    assert recorder.plans == []  # never committed — the write is withheld
    with pytest.raises(EscapedTransactionError):
        captured["tx"].buffer(_account_insert(1))  # discarded + closed


def test_rollback_only_refuses_commit_and_withholds_value() -> None:
    recorder = _Recorder()
    cause = RuntimeError("inner")

    def body(tx: UnitOfWork) -> str:
        tx.buffer(_account_insert(9))
        tx.mark_rollback_only(cause)
        return "ignored"

    with pytest.raises(RollbackOnlyError) as exc:
        _run(body, executor=recorder)
    assert exc.value.__cause__ is cause
    assert recorder.plans == []  # commit (flush) refused


def test_first_rollback_cause_is_preserved() -> None:
    first = RuntimeError("first")
    second = RuntimeError("second")

    def body(tx: UnitOfWork) -> None:
        tx.mark_rollback_only(first)
        tx.mark_rollback_only(second)

    with pytest.raises(RollbackOnlyError) as exc:
        _run(body)
    assert exc.value.__cause__ is first


def test_settings_are_carried_on_the_unit_of_work() -> None:
    def body(tx: UnitOfWork) -> str:
        return tx.settings.concurrency

    assert _run(body, settings=TransactionSettings(concurrency="optimistic")) == "optimistic"


# --------------------------------------------------------------------------- #
# Read-your-own-writes force-flush.                                            #
# --------------------------------------------------------------------------- #
def test_read_force_flushes_pending_writes_first() -> None:
    order: list[str] = []
    recorder = _Recorder()

    def executor(plan: FlushPlan) -> None:
        order.append("flush")
        recorder(plan)

    def body(tx: UnitOfWork) -> str:
        tx.buffer(_account_insert(9))
        result = tx.read(lambda: (order.append("read"), "row")[1])
        order.append("after")
        return result

    assert _run(body, executor=executor) == "row"
    assert order == ["flush", "read", "after"]  # the dependent read observes the flushed write
    assert len(recorder.plans) == 1  # the outermost flush finds an empty buffer


def test_read_without_pending_writes_does_not_flush() -> None:
    recorder = _Recorder()

    def body(tx: UnitOfWork) -> str:
        return tx.read(lambda: "row")

    assert _run(body, executor=recorder) == "row"
    assert recorder.plans == []


# --------------------------------------------------------------------------- #
# Clock injection.                                                             #
# --------------------------------------------------------------------------- #
def test_clock_supplies_the_flush_processing_instant() -> None:
    recorder = _Recorder()

    def body(tx: UnitOfWork) -> None:
        tx.buffer(KeyedWrite("insert", "Balance", ({"id": 9, "acctNum": "D", "value": 100.00},)))

    _run(body, clock=FixedClock(_FIXED), executor=recorder, meta=_BALANCE)
    assert recorder.plans[0].tx_instant == "2024-06-01T00:00:00+00:00"


def test_system_clock_reads_an_aware_utc_instant() -> None:
    instant = SystemClock().now()
    assert instant.tzinfo is not None
    assert instant.utcoffset() == dt.timedelta(0)


def test_observe_binds_the_recorded_observation_into_the_flush_plan() -> None:
    recorder = _Recorder()
    observation = Observation(version=7)

    def body(tx: UnitOfWork) -> None:
        tx.observe(("Account", (("id", 1),)), observation)
        tx.buffer(KeyedWrite("update", "Account", ({"id": 1, "balance": 0.00},)))

    _run(body, executor=recorder)
    assert recorder.plans[0].writes[0].observation == observation


def test_a_fully_empty_transaction_never_touches_the_clock() -> None:
    # D-29's own empirical read-only/empty-transact truth: `flush()` returns
    # before ever computing `_processing_instant_literal()` when the buffer is
    # empty (`UnitOfWork.flush`), so a transaction that never buffers anything
    # (a pure read, or an empty body) never calls `Clock.now()` at all — the
    # commit-time flush at the outermost boundary is a no-op for it.
    clock = _CountingClock([dt.datetime(2024, 6, 1, tzinfo=dt.UTC)])

    def body(tx: UnitOfWork) -> str:
        return tx.read(lambda: "row")

    assert _run(body, clock=clock) == "row"
    assert clock.calls == 0


def test_processing_instant_is_captured_once_per_transaction() -> None:
    clock = _CountingClock(
        [dt.datetime(2024, 6, 1, tzinfo=dt.UTC), dt.datetime(2025, 1, 1, tzinfo=dt.UTC)]
    )
    recorder = _Recorder()

    def body(tx: UnitOfWork) -> None:
        tx.buffer(KeyedWrite("insert", "Balance", ({"id": 9, "acctNum": "D", "value": 1.00},)))
        tx.read(lambda: "row")  # forces the first flush
        tx.buffer(KeyedWrite("insert", "Balance", ({"id": 10, "acctNum": "E", "value": 2.00},)))

    _run(body, clock=clock, executor=recorder, meta=_BALANCE)
    assert clock.calls == 1  # one Transaction-Time instant per transaction (Reladomo's timestamp)
    assert [p.tx_instant for p in recorder.plans] == ["2024-06-01T00:00:00+00:00"] * 2


# --------------------------------------------------------------------------- #
# Frame stack — join, doom, re-entry.                                          #
# --------------------------------------------------------------------------- #
def test_nested_transaction_joins_the_active_one() -> None:
    outer_exec = _Recorder()
    inner_exec = _Recorder()
    seen: dict[str, object] = {}

    def inner(tx: UnitOfWork) -> str:
        seen["inner_tx"] = tx
        seen["joined"] = tx.is_joined
        tx.buffer(_account_insert(10))
        return "inner-result"

    def outer(tx: UnitOfWork) -> str:
        seen["outer_tx"] = tx
        seen["inner_ret"] = _run(inner, executor=inner_exec)  # joins the active transaction
        tx.buffer(_account_insert(9))
        return "outer-result"

    assert _run(outer, executor=outer_exec) == "outer-result"
    assert seen["inner_tx"] is seen["outer_tx"]  # the same unit of work
    assert seen["joined"] is True
    assert seen["inner_ret"] == "inner-result"  # a joined body returns immediately
    assert inner_exec.plans == []  # the joined call's executor is ignored
    assert len(outer_exec.plans) == 1  # one flush at the outermost boundary
    assert len(outer_exec.plans[0].writes) == 2  # both buffered writes


def test_inner_failure_dooms_the_transaction_even_if_caught() -> None:
    outer_exec = _Recorder()
    cause = RuntimeError("inner boom")

    def inner(tx: UnitOfWork) -> None:
        raise cause

    def outer(tx: UnitOfWork) -> str:
        # The outer body catches the inner failure and would return normally.
        with contextlib.suppress(RuntimeError):
            _run(inner)  # joins; the failure dooms the whole transaction
        return "outer-ok"

    with pytest.raises(RollbackOnlyError) as exc:
        _run(outer, executor=outer_exec)
    assert exc.value.__cause__ is cause  # the original cause + classification survives
    assert outer_exec.plans == []  # commit refused despite the caught exception


def test_reentry_into_a_rollback_only_transaction_is_refused() -> None:
    cause = RuntimeError("first failure")
    ran: dict[str, bool] = {"inner": False}

    def inner(tx: UnitOfWork) -> None:
        ran["inner"] = True

    def outer(tx: UnitOfWork) -> str:
        tx.mark_rollback_only(cause)
        with pytest.raises(RollbackOnlyError) as exc:
            _run(inner)  # joining a doomed scope raises before running the body
        assert exc.value.__cause__ is cause
        return "done"

    with pytest.raises(RollbackOnlyError):
        _run(outer)
    assert ran["inner"] is False


# --------------------------------------------------------------------------- #
# Use-after-scope.                                                             #
# --------------------------------------------------------------------------- #
def test_escaped_reference_raises_on_every_use() -> None:
    captured: dict[str, UnitOfWork] = {}

    def body(tx: UnitOfWork) -> None:
        captured["tx"] = tx

    _run(body)
    tx = captured["tx"]
    with pytest.raises(EscapedTransactionError):
        tx.buffer(_account_insert(1))
    with pytest.raises(EscapedTransactionError):
        tx.observe(("Account", (("id", 1),)), Observation())
    with pytest.raises(EscapedTransactionError):
        tx.flush()
    with pytest.raises(EscapedTransactionError):
        tx.read(lambda: None)
