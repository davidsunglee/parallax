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
from collections.abc import Callable, Mapping

import pytest

from _support.clock_probes import CountingClock
from _support.planner_probes import TEST_SUBJECT_IDENTITY, planner_for
from parallax.conformance import models
from parallax.core.metamodel import AttributeIdentity, Metamodel
from parallax.core.unit_work import (
    Clock,
    EscapedTransactionError,
    FixedClock,
    FlushExecutor,
    KeyedWrite,
    PlannedInsert,
    PlannedUpdate,
    RollbackOnlyError,
    SystemClock,
    TransactionSettings,
    UnitOfWork,
    VersionObservation,
    WritePlan,
    active_unit_of_work,
    run_unit_of_work,
)

_MODELS = models.load_models()
_ACCOUNT = models.accepted_model(_MODELS["account"])
_BALANCE = models.accepted_model(_MODELS["balance"])
_FIXED = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


class _Recorder:
    """Records each Write Plan the shell hands the executor."""

    def __init__(self) -> None:
        self.plans: list[WritePlan] = []

    def __call__(self, plan: WritePlan) -> None:
        self.plans.append(plan)


def _noop(plan: WritePlan) -> None:
    return None


def _run[T](
    body: Callable[[UnitOfWork], T],
    *,
    clock: Clock | None = None,
    executor: FlushExecutor | None = None,
    settings: TransactionSettings | None = None,
    meta: Metamodel | None = None,
) -> T:
    resolved_meta = meta or _ACCOUNT
    return run_unit_of_work(
        body,
        settings=settings or TransactionSettings(),
        clock=clock or FixedClock(_FIXED),
        meta=resolved_meta,
        flush_executor=executor or _noop,
        planner=planner_for(resolved_meta),
        subject_identity=TEST_SUBJECT_IDENTITY,
    )


def _account_insert(account_id: int) -> KeyedWrite:
    return KeyedWrite("insert", "Account", ({"id": account_id, "owner": "N", "balance": 5.00},))


def _member_value(attributes: Mapping[AttributeIdentity, object], name: str) -> object:
    """The planned value carried under the Attribute spelled ``name``, from a
    Planned Row's or Planned Assignments' own ``attributes`` mapping."""
    for identity, value in attributes.items():
        if identity.name == name:
            return value
    raise AssertionError(f"no attribute named {name!r} in {attributes!r}")  # pragma: no cover


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
    assert len(recorder.plans[0].steps) == 1


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

    def executor(plan: WritePlan) -> None:
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
def test_clock_supplies_the_flush_transaction_time_instant() -> None:
    # `WritePlan` retains no Transaction Instant of its own (`m-unit-work`):
    # the captured value survives only where a settled step already carries
    # it, so the audit-only insert's own `tx_start` cell is the observable.
    recorder = _Recorder()

    def body(tx: UnitOfWork) -> None:
        tx.buffer(KeyedWrite("insert", "Balance", ({"id": 9, "acctNum": "D", "value": 100.00},)))

    _run(body, clock=FixedClock(_FIXED), executor=recorder, meta=_BALANCE)
    (step,) = recorder.plans[0].steps
    assert isinstance(step, PlannedInsert)
    (entry,) = step.entries
    assert _member_value(entry.row.attributes, "tx_start") == "2024-06-01T00:00:00+00:00"


def test_system_clock_reads_an_aware_utc_instant() -> None:
    instant = SystemClock().now()
    assert instant.tzinfo is not None
    assert instant.utcoffset() == dt.timedelta(0)


def test_observe_binds_the_recorded_observation_into_the_settled_step() -> None:
    # `PlannedUpdate` carries no raw observation either — the recorded version
    # survives only as the settled step's own advanced assignment.
    recorder = _Recorder()
    observation = VersionObservation(observed_version=7)

    def body(tx: UnitOfWork) -> None:
        tx.observe(("Account", (("id", 1),)), observation)
        tx.buffer(KeyedWrite("update", "Account", ({"id": 1, "balance": 0.00},)))

    _run(body, executor=recorder)
    (step,) = recorder.plans[0].steps
    assert isinstance(step, PlannedUpdate)
    assert _member_value(step.assignments.attributes, "version") == 8


def test_a_fully_empty_transaction_never_touches_the_clock() -> None:
    # `flush()` returns on an empty buffer before it even builds a plan, so a
    # read-only transaction never calls `Clock.now()`.
    clock = CountingClock([dt.datetime(2024, 6, 1, tzinfo=dt.UTC)])

    def body(tx: UnitOfWork) -> str:
        return tx.read(lambda: "row")

    assert _run(body, clock=clock) == "row"
    assert clock.calls == 0


def test_transaction_time_instant_is_captured_once_per_transaction() -> None:
    clock = CountingClock(
        [dt.datetime(2024, 6, 1, tzinfo=dt.UTC), dt.datetime(2025, 1, 1, tzinfo=dt.UTC)]
    )
    recorder = _Recorder()

    def body(tx: UnitOfWork) -> None:
        tx.buffer(KeyedWrite("insert", "Balance", ({"id": 9, "acctNum": "D", "value": 1.00},)))
        tx.read(lambda: "row")  # forces the first flush
        tx.buffer(KeyedWrite("insert", "Balance", ({"id": 10, "acctNum": "E", "value": 2.00},)))

    _run(body, clock=clock, executor=recorder, meta=_BALANCE)
    # The forced flush and the commit flush carry the SAME holder, so consuming
    # either yields one Transaction-Time instant for the whole transaction
    # (Reladomo's per-transaction timestamp) — observable only through the
    # settled step's own stamped `tx_start`, since a Write Plan retains no
    # Transaction Instant of its own.
    tx_starts: list[object] = []
    for plan in recorder.plans:
        (step,) = plan.steps
        assert isinstance(step, PlannedInsert)
        (entry,) = step.entries
        tx_starts.append(_member_value(entry.row.attributes, "tx_start"))
    assert tx_starts == ["2024-06-01T00:00:00+00:00"] * 2
    assert clock.calls == 1


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
    # Both buffered writes reached the SAME outermost flush — the production
    # planner's own batching then collapses the two uniform Account inserts
    # into one multi-row step, so the entry count is the observable, not the
    # step count.
    (step,) = outer_exec.plans[0].steps
    assert isinstance(step, PlannedInsert)
    assert len(step.entries) == 2


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
        tx.observe(("Account", (("id", 1),)), VersionObservation(observed_version=1))
    with pytest.raises(EscapedTransactionError):
        tx.flush()
    with pytest.raises(EscapedTransactionError):
        tx.read(lambda: None)
