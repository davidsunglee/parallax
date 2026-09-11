"""The interleaved lane's own threading primitives: the strict step-index
cursor two worker threads take turns through, and the bounded join that
unsticks and joins both workers before it reports a choreography that did not
finish.

Not a lane. Nothing here reads a case, holds a port, or knows what a step
does: a :class:`Turnstile` sequences step INDICES across two threads, and
:func:`await_workers` joins two threads over the executions each runs on,
escalating through each execution's own termination ladder and naming the case
only in the error it raises. The interleaved lane
(:mod:`~parallax.conformance._lanes.interleaved`) is the one consumer.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import Final

from parallax.conformance._database_control import InterleavedExecution
from parallax.conformance._mechanism.envelope import EngineError

__all__ = ["JOIN_TIMEOUT", "Turnstile", "await_workers"]


class Turnstile:
    """A strict, shared step-index cursor two worker threads take turns
    through: a thread's own step at index ``i``
    calls :meth:`wait_for` ``(i)`` before running it (blocking until every
    EARLIER step, on EITHER thread, has finished) and :meth:`advance` after —
    so the two groups' steps interleave in EXACTLY authored order, never a
    genuine Python-level race, matching `m-case-format`'s own "steps execute
    in authored order" scenario contract even though they run on two
    independently-held connections.
    """

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._next = 0

    def wait_for(self, index: int) -> None:
        with self._condition:
            while self._next < index:
                self._condition.wait()

    def advance(self) -> None:
        with self._condition:
            self._next += 1
            self._condition.notify_all()

    def release_all(self) -> None:
        """Unstick every waiter unconditionally (a worker thread's own
        UNEXPECTED failure — never a witnessed path, defensive only): without
        this a partner thread blocked on a LATER index than one extra
        :meth:`advance` reaches would hang forever, and so would the
        orchestrator's own `thread.join()`."""
        with self._condition:
            self._next = 2**31
            self._condition.notify_all()


# The interleaved-group choreography's own bounded join (the provider-
# contract deadlock proof's own precedent): a genuine harness defect (a
# missing `advance()` somewhere) must surface as a loud failure, never an
# indefinitely hung test session. Named so :func:`await_workers`
# can be exercised directly with a SHRUNK bound — a real, unstuck-by-
# `release_all` timeout path in well under a second, rather than the
# production bound actually elapsing twice.
JOIN_TIMEOUT: Final[float] = 30.0


def await_workers(
    workers: Mapping[str, tuple[threading.Thread, InterleavedExecution]],
    turnstile: Turnstile,
    case_name: str,
    *,
    timeout: float = JOIN_TIMEOUT,
) -> None:
    """Join both interleaved-group worker threads within ``timeout``; on a
    timeout, cooperatively unstick them before raising rather than raising
    while they may still be alive.

    Three escalations, each reaching a survivor the one before it cannot:

    1. :meth:`Turnstile.release_all` wakes every thread parked on a hand-off
       that never arrived — the ordinary harness defect, and the only one that
       needs nothing destructive.
    2. :meth:`~parallax.conformance._database_control.InterleavedExecution.
       cancel_active` on a survivor's OWN execution, for a thread parked in real
       driver I/O that no turnstile release can reach. Non-destructive and
       best-effort, which it is allowed to be because the guarantee lives in the
       rung after it.
    3. :meth:`~parallax.conformance._database_control.InterleavedExecution.
       terminate_active` — the guaranteed one. Every execution here is a session
       this run opened for this choreography alone, so destroying it is a loss
       of nothing the caller still owns; that is why the lane never runs a group
       over the fixture's own connection.

    FINAL CONTRACT: no path — return, raise, or assert — runs while a started
    worker is alive. The join after the termination rung is therefore
    deliberately unbounded: against an execution whose ladder is somehow
    defeated, the failure mode is a diagnosable hang at that exact line rather
    than a live worker racing the caller through a session the caller believes
    is finished. Every execution reaching this point has DECLARED that the
    ladder unblocks it (the interleaved lane refuses one that grants no such
    trust before either worker starts), so in practice the join returns at
    once.

    Worker exceptions the termination itself provokes are expected collateral,
    captured on each worker's own result by the lane that started it and never
    consulted once this function has raised. The error names every execution
    that had to be terminated and carries every recorded ladder failure as
    :meth:`~BaseException.add_note` context — recorded, never masking it. The
    caller's own ``finally`` still closes every execution unconditionally.
    """

    def rejoin() -> list[str]:
        for thread, _execution in workers.values():
            thread.join(timeout=timeout)
        return [label for label, (thread, _) in workers.items() if thread.is_alive()]

    if not rejoin():
        return

    turnstile.release_all()
    survivors = rejoin()

    if survivors:
        for label in survivors:
            workers[label][1].cancel_active()
        survivors = rejoin()

    terminated: list[str] = []
    failures: list[str] = []
    for label in survivors:
        report = workers[label][1].terminate_active()
        terminated.append(label)
        failures.extend(f"{label}: {failure}" for failure in report.failures)

    # UNBOUNDED — see docstring: a diagnosable hang here beats ever raising (or
    # returning) while a worker is still alive, so there is no separate,
    # narrower termination-join bound to violate.
    for thread, _execution in workers.values():
        thread.join()

    if terminated:
        error = EngineError(
            f"{case_name}: the interleaved-group choreography did not finish within its "
            f"bound — {', '.join(terminated)} had to be terminated to unstick it"
        )
    else:
        error = EngineError(
            f"{case_name}: the interleaved-group choreography did not "
            "finish within its bound — a turnstile hand-off is missing"
        )
    for failure in failures:
        error.add_note(f"termination ladder: {failure}")
    raise error
