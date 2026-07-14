"""The unit-of-work shell (m-unit-work).

The transaction scope's stateful machinery around the pure planner: the frame
stack (a nested scope joins the active transaction, ADR 0005), the write buffer,
the recorded observations, call-time reads that force-flush pending writes so a
dependent read observes them (read-your-own-writes), and abort — which discards
buffered effects and **withholds** the callback value (ADR 0006).

This is deliberately **not** ``db.transact``: there is no public sentinel-backed
option surface and no bounded-retry loop (both are M4). The shell exposes the
primitives ``db.transact`` composes — :func:`run_unit_of_work` decides join vs. a
new outermost frame, and the outermost frame commits (flushes) or aborts. Because
lowering a flush plan to DML needs ``m-sql`` (which the DAG forbids ``m-unit-work``
from importing), the shell **delegates** the flush to an injected
:data:`FlushExecutor` supplied by the composition layer that legally sees both;
here it is a neutral callable, so the shell stays DML-free and testable.

The active transaction is tracked **per thread**; the object is owned by its
outermost invocation and is not thread-safe. A reference used after its scope ends
raises :class:`EscapedTransactionError`.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from parallax.core.descriptor import Metamodel
from parallax.core.unit_work.clock import Clock, instant_literal
from parallax.core.unit_work.instructions import WriteInstruction
from parallax.core.unit_work.planner import FlushPlan, ObjectKey, Observation, plan_flush

__all__ = [
    "Concurrency",
    "EscapedTransactionError",
    "FlushExecutor",
    "RollbackOnlyError",
    "TransactionSettings",
    "UnitOfWork",
    "UnitOfWorkError",
    "active_unit_of_work",
    "run_unit_of_work",
]

# The composition-layer sink a flush plan is handed to for lowering + execution.
# Neutral here (m-unit-work takes no m-sql edge); M4 injects the real lowering.
FlushExecutor = Callable[[FlushPlan], None]

# The per-transaction participation mode (m-unit-work strategy selection).
Concurrency = Literal["locking", "optimistic"]


class UnitOfWorkError(RuntimeError):
    """A unit of work was driven into an illegal state."""


class EscapedTransactionError(UnitOfWorkError):
    """A unit-of-work reference was used after its owning scope ended."""


class RollbackOnlyError(UnitOfWorkError):
    """A doomed (rollback-only) transaction refused commit or re-entry.

    Raised when the outermost boundary would commit a transaction an inner failure
    marked rollback-only, and when a nested scope tries to join one — carrying the
    original failure as its cause (``__cause__``), so its retriability classification
    survives for the outermost retry loop (M4).
    """


@dataclass(frozen=True, slots=True)
class TransactionSettings:
    """A unit of work's fixed settings — today just the participation mode."""

    concurrency: Concurrency = "locking"


class UnitOfWork:
    """The buffering, observing, flushing transaction scope (m-unit-work).

    Construct via :func:`run_unit_of_work` (which owns the frame lifecycle); the
    body receives the unit of work and drives it with :meth:`buffer`, :meth:`observe`,
    and :meth:`read`.
    """

    __slots__ = (
        "_buffer",
        "_closed",
        "_frame_depth",
        "_observations",
        "_processing_instant",
        "_rollback_cause",
        "_rollback_only",
        "clock",
        "companion",
        "flush_executor",
        "meta",
        "settings",
    )

    def __init__(
        self,
        *,
        settings: TransactionSettings,
        clock: Clock,
        meta: Metamodel,
        flush_executor: FlushExecutor,
    ) -> None:
        self.settings = settings
        self.clock = clock
        self.meta = meta
        self.flush_executor = flush_executor
        # An opaque demarcation-layer companion (the `db.transact` transaction
        # facade), published for the scope's duration so a joining call recovers
        # it via `active_unit_of_work()`. The shell never reads it, and it needs
        # no cleanup of its own: it is reachable only through the per-thread
        # active binding, which `run_outermost` already clears on every exit.
        self.companion: object | None = None
        self._buffer: list[WriteInstruction] = []
        self._observations: dict[ObjectKey, Observation] = {}
        self._frame_depth = 0
        self._rollback_only = False
        self._rollback_cause: BaseException | None = None
        self._processing_instant: str | None = None
        self._closed = False

    # --- caller surface --------------------------------------------------- #
    def buffer(self, instruction: WriteInstruction) -> None:
        """Buffer a write instruction for flush at the unit-of-work boundary."""
        self._ensure_open()
        self._buffer.append(instruction)

    def observe(self, key: ObjectKey, observation: Observation) -> None:
        """Record the transaction observation for one object (attached at flush)."""
        self._ensure_open()
        self._observations[key] = observation

    def read[T](self, read_fn: Callable[[], T]) -> T:
        """Serve a call-time read, force-flushing pending writes first.

        Read-your-own-writes: buffered writes are flushed inside the still-open
        atomic scope before the dependent read runs, so the read never observes
        stale in-transaction state. An abort still erases the force-flushed write
        (the DB rollback the enclosing transaction performs, upstream).
        """
        self._ensure_open()
        if self._buffer:
            self.flush()
        return read_fn()

    def flush(self) -> None:
        """Plan and execute the buffered writes (the injected executor lowers them)."""
        self._ensure_open()
        if not self._buffer:
            return
        plan = plan_flush(
            tuple(self._buffer), self._observations, self._processing_instant_literal(), self.meta
        )
        self._buffer.clear()
        self.flush_executor(plan)

    def mark_rollback_only(self, cause: BaseException) -> None:
        """Doom the transaction: commit will be refused. The first cause is kept."""
        self._rollback_only = True
        if self._rollback_cause is None:
            self._rollback_cause = cause

    @property
    def is_rollback_only(self) -> bool:
        """Whether the transaction is marked rollback-only (commit will be refused)."""
        return self._rollback_only

    @property
    def is_joined(self) -> bool:
        """Whether the unit of work is inside a joined (nested) frame."""
        return self._frame_depth > 0

    # --- internals -------------------------------------------------------- #
    def _processing_instant_literal(self) -> str:
        # One processing instant per transaction (Reladomo's per-transaction
        # timestamp): captured once from the Clock, shared by every flush.
        if self._processing_instant is None:
            self._processing_instant = instant_literal(self.clock.now())
        return self._processing_instant

    def _ensure_open(self) -> None:
        if self._closed:
            raise EscapedTransactionError(
                "the unit of work has ended; a reference escaped its scope"
            )

    def _discard(self) -> None:
        # Abort: drop buffered + force-flushed in-memory state. The DB rollback the
        # enclosing transaction performs (upstream) erases any force-flushed rows.
        self._buffer.clear()
        self._observations.clear()

    def run_outermost[T](self, body: Callable[[UnitOfWork], T]) -> T:
        """Run ``body`` as the outermost frame: commit (flush) on success, else abort.

        Driven by :func:`run_unit_of_work`; not part of the developer surface.
        """
        _bind_active(self)
        try:
            result = body(self)
            if self._rollback_only:
                # An inner failure doomed the scope; commit is refused even though
                # the outer body returned normally, and the value is withheld.
                raise RollbackOnlyError(
                    "transaction is rollback-only; commit refused"
                ) from self._rollback_cause
            self.flush()
            return result
        except BaseException:
            # Abort: discard buffered effects and withhold the callback value.
            self._discard()
            raise
        finally:
            self._closed = True
            _clear_active()

    def run_joined[T](self, body: Callable[[UnitOfWork], T]) -> T:
        """Run ``body`` as a joined (nested) frame: return immediately, doom on failure.

        Driven by :func:`run_unit_of_work`; not part of the developer surface.
        """
        if self._rollback_only:
            # No new work may start inside a doomed scope.
            raise RollbackOnlyError(
                "cannot join a rollback-only transaction"
            ) from self._rollback_cause
        self._frame_depth += 1
        try:
            # The joined body returns immediately; commit/abort/retry belong to the
            # outermost boundary (ADR 0005). An inner failure dooms the whole txn.
            return body(self)
        except BaseException as exc:
            self.mark_rollback_only(exc)
            raise
        finally:
            self._frame_depth -= 1


class _ActiveState(threading.local):
    """Per-thread holder for the active unit of work (the class default is the
    per-thread fallback until a thread binds its own instance attribute)."""

    uow: UnitOfWork | None = None


_active = _ActiveState()


def active_unit_of_work() -> UnitOfWork | None:
    """The unit of work active on the current thread, or ``None``."""
    return _active.uow


def _bind_active(uow: UnitOfWork) -> None:
    _active.uow = uow


def _clear_active() -> None:
    _active.uow = None


def run_unit_of_work[T](
    body: Callable[[UnitOfWork], T],
    *,
    settings: TransactionSettings,
    clock: Clock,
    meta: Metamodel,
    flush_executor: FlushExecutor,
) -> T:
    """Run ``body`` in a unit of work — joining the active one or opening a new frame.

    A call while a transaction is active on the current thread **joins** it: the
    body receives the same unit of work and its return value is returned
    immediately (commit and abort belong to the outermost frame), and the passed
    ``settings`` / ``clock`` / ``meta`` / ``flush_executor`` are ignored in favor of
    the active transaction's (M4's ``db.transact`` performs the option-conflict
    check before calling). Otherwise a new outermost frame is opened, and its value
    is returned only after a durable flush; an abort withholds it.
    """
    active = active_unit_of_work()
    if active is not None:
        return active.run_joined(body)
    uow = UnitOfWork(settings=settings, clock=clock, meta=meta, flush_executor=flush_executor)
    return uow.run_outermost(body)
