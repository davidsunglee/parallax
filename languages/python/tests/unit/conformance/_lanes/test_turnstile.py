"""The interleaved lane's threading primitives, driven with threads of their
own: the bounded join's three escalations — the turnstile release, the
survivor's own cancellation, and the termination it falls back to — each
proven to join every worker before the join reports a choreography that did
not finish.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from parallax.conformance._database_control import TerminationReport
from parallax.conformance._lanes.turnstile import Turnstile, await_workers
from parallax.conformance._mechanism.envelope import EngineError
from parallax.core.dialect import POSTGRES, Dialect
from parallax.snapshot import handle


class _BlockingExecution:
    """An interleaved execution whose worker parks in "driver I/O" until a named
    escalation reaches it.

    ``wakes_on`` is the rung that releases the block — ``"cancel"`` for a session
    a cancellation request can interrupt, ``"terminate"`` for one only the
    guaranteed ladder reaches — so a pin states exactly which escalation it is
    proving. ``ladder_failures`` is what the ladder RECORDS while getting there:
    a rung that failed on the way to one that worked, which the lane must carry
    as context rather than swallow.

    Its ``database`` is never reached: these pins drive
    :func:`~parallax.conformance._lanes.turnstile.await_workers` directly with
    threads of their own, so a Database over this session would be an unused
    composition standing in the way of what the pin is about.
    """

    def __init__(
        self,
        *,
        wakes_on: str = "terminate",
        trusted: bool = True,
        ladder_failures: tuple[str, ...] = (),
    ) -> None:
        self._wakes_on = wakes_on
        self._released = threading.Event()
        self._ladder_failures = ladder_failures
        self.trusted = trusted
        self.cancel_calls = 0
        self.terminate_calls = 0
        self.closed = False

    @property
    def database(self) -> handle.Database:  # pragma: no cover - never reached; see the docstring
        raise AssertionError("these pins never run a group through this execution")

    @property
    def dialect(self) -> Dialect:
        return POSTGRES

    @property
    def termination_ladder_trusted(self) -> bool:
        return self.trusted

    def block(self) -> None:
        """Stand in for a driver call parked in socket I/O.

        Self-bounded so a pin that never reaches the escalation it is proving
        fails on its own assertions rather than hanging the suite.
        """
        self._released.wait(timeout=5.0)

    def cancel_active(self) -> None:
        self.cancel_calls += 1
        if self._wakes_on == "cancel":
            self._released.set()

    def terminate_active(self) -> TerminationReport:
        self.terminate_calls += 1
        self._released.set()
        return TerminationReport(terminated=True, failures=self._ladder_failures)

    def close(self) -> None:
        self.closed = True
        self._released.set()


def _stuck_worker(turnstile: Any, name: str) -> threading.Thread:
    """A worker parked on a turnstile index this choreography never advances to."""

    def run() -> None:
        turnstile.wait_for(2**30)

    return threading.Thread(target=run, name=name)


def _workers(*entries: tuple[threading.Thread, Any]) -> dict[str, Any]:
    return {thread.name: (thread, execution) for thread, execution in entries}


def test_await_interleaved_workers_unsticks_both_on_timeout_then_joins_before_raising() -> None:
    # The join-timeout path: a genuine harness defect (a missing turnstile
    # `advance()` somewhere) leaves BOTH workers blocked in `wait_for` forever —
    # the timeout path must wake every one of them (`Turnstile.release_all`),
    # JOIN both threads, and only THEN raise; no live thread may outlive the
    # call. Nothing here needs destroying, so no execution is cancelled or
    # terminated and the error names the missing hand-off rather than a
    # termination. A tiny `timeout` (never the production 30s bound) keeps this
    # deterministic and fast.
    turnstile = Turnstile()
    ours = _BlockingExecution()
    peer = _BlockingExecution()
    thread_a = _stuck_worker(turnstile, "uow-ours")
    thread_b = _stuck_worker(turnstile, "uow-concurrent")
    thread_a.start()
    thread_b.start()

    with pytest.raises(EngineError, match="turnstile hand-off is missing"):
        await_workers(
            _workers((thread_a, ours), (thread_b, peer)),
            turnstile,
            "m-unit-work-999-synthetic.yaml",
            timeout=0.05,
        )

    assert not thread_a.is_alive()
    assert not thread_b.is_alive()
    assert (ours.cancel_calls, ours.terminate_calls) == (0, 0)
    assert (peer.cancel_calls, peer.terminate_calls) == (0, 0)


def test_await_interleaved_workers_cancels_a_survivor_blocked_in_real_io_then_joins() -> None:
    # A worker blocked in REAL database I/O on its OWN session survives the
    # first escalation intact: `release_all` has nothing to wake, because the
    # worker is not inside `turnstile.wait_for`. The second escalation must
    # cancel that survivor's own execution, rejoin bounded, and — every worker
    # now actually joined — raise the ordinary missing-hand-off error, since a
    # session cancellation released was never destroyed.
    turnstile = Turnstile()
    ours = _BlockingExecution(wakes_on="cancel")
    peer = _BlockingExecution()
    thread_a = threading.Thread(target=ours.block, name="uow-ours")
    thread_b = _stuck_worker(turnstile, "uow-concurrent")
    thread_a.start()
    thread_b.start()

    with pytest.raises(EngineError, match="turnstile hand-off is missing"):
        await_workers(
            _workers((thread_a, ours), (thread_b, peer)),
            turnstile,
            "m-unit-work-999-synthetic.yaml",
            timeout=0.1,
        )

    assert ours.cancel_calls == 1
    assert ours.terminate_calls == 0
    assert not thread_a.is_alive()
    assert not thread_b.is_alive()


def test_await_interleaved_workers_terminates_a_survivor_cancellation_cannot_reach() -> None:
    # A survivor neither `release_all` nor cancellation can reach escalates to
    # the third, destructive rung rather than this function ever raising while
    # that worker remains alive: the contract has no "loud leak" terminal state
    # at all. `is_alive()` must be False for EVERY worker at the moment of the
    # raise, the error must name the execution that had to be terminated, and
    # every rung the ladder recorded on its way must survive as context rather
    # than being swallowed.
    turnstile = Turnstile()
    ours = _BlockingExecution(
        ladder_failures=("the session's own close() raised RuntimeError('outer close failed')",)
    )
    peer = _BlockingExecution()
    thread_a = threading.Thread(target=ours.block, name="uow-ours")
    thread_b = _stuck_worker(turnstile, "uow-concurrent")
    thread_a.start()
    thread_b.start()

    with pytest.raises(EngineError, match="uow-ours had to be terminated") as raised:
        await_workers(
            _workers((thread_a, ours), (thread_b, peer)),
            turnstile,
            "m-unit-work-999-synthetic.yaml",
            timeout=0.1,
        )

    assert ours.cancel_calls == 1  # attempted first, and it could not reach this one
    assert ours.terminate_calls == 1
    assert peer.terminate_calls == 0  # the turnstile release was enough for its own worker
    assert not thread_a.is_alive()
    assert not thread_b.is_alive()
    notes = "\n".join(raised.value.__notes__)
    assert "uow-ours: the session's own close() raised" in notes
