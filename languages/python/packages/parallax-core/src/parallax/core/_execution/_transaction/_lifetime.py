from __future__ import annotations

import threading
from collections.abc import Collection, Generator
from contextlib import contextmanager
from typing import Final, Literal

from parallax.core.base import ParallaxError, UsageError

__all__ = [
    "TRANSACTION_ESCAPED",
    "TRANSACTION_ROLLBACK_ONLY",
    "ActiveBinding",
    "TransactionLifetimeCode",
    "TxnAttemptLifetime",
]

type TransactionLifetimeCode = Literal["transaction-escaped", "transaction-rollback-only"]
"""Why an attempt refused work: a reference to it escaped once it ended, or a
failure doomed it.

A rollback-only refusal carries the failure that doomed the attempt as its
``__cause__``, so that failure's retriability survives for the outermost retry
loop, and answers ``is_transient`` from it.
"""

TRANSACTION_ESCAPED: Final = "transaction-escaped"
TRANSACTION_ROLLBACK_ONLY: Final = "transaction-rollback-only"


class _RollbackOnlyRefusal(UsageError):
    """The refusal of work in an attempt a failure doomed.

    Running the same work later may succeed exactly when it may for the
    failure that doomed the attempt, so ``is_transient`` is that failure's,
    and ``False`` for a cause Parallax did not raise.
    """

    def __init__(self, message: str) -> None:
        super().__init__(TRANSACTION_ROLLBACK_ONLY, message)

    @property
    def is_transient(self) -> bool:
        cause = self.__cause__
        return isinstance(cause, ParallaxError) and cause.is_transient


class TxnAttemptLifetime:
    """Whether one transaction attempt still admits work, and why not.

    The single owner of the attempt's open/closed status, its rollback-only
    status, the first failure that doomed it, and the statement failures its
    execution recognized as recoverable conflicts. The runner, the attempt, its
    handles and streams, and a writable attempt's unit of work all consult this
    one object, so no second flag can disagree with it.
    """

    __slots__ = ("_closed", "_first_cause", "_recognized_conflicts", "_rollback_only")

    def __init__(self) -> None:
        self._closed = False
        self._rollback_only = False
        self._first_cause: BaseException | None = None
        self._recognized_conflicts: list[BaseException] = []

    @property
    def recognized_conflicts(self) -> Collection[BaseException]:
        """The statement failures execution recognized as recoverable conflicts."""
        return tuple(self._recognized_conflicts)

    def recognize_conflict(self, failure: BaseException) -> None:
        """Record that execution recognized ``failure`` as a recoverable conflict."""
        self._recognized_conflicts.append(failure)

    def doom(self, cause: BaseException) -> None:
        """Make the attempt rollback-only, keeping the first cause."""
        self._rollback_only = True
        if self._first_cause is None:
            self._first_cause = cause

    def close(self) -> None:
        """Fence the attempt: no handle, stream, or join admits work after this."""
        self._closed = True

    def ensure_open(self) -> None:
        """Refuse work on an attempt that ended or is rollback-only."""
        if self._closed:
            raise UsageError(
                TRANSACTION_ESCAPED, "the transaction has ended; a reference escaped its attempt"
            )
        if self._rollback_only:
            raise _RollbackOnlyRefusal(
                "the transaction is rollback-only; it accepts no further work"
            ) from self._first_cause

    def refuse_join(self) -> None:
        """Refuse a joining invocation into a rollback-only attempt."""
        if self._rollback_only:
            raise _RollbackOnlyRefusal(
                "cannot join a rollback-only transaction"
            ) from self._first_cause

    def refuse_commit(self) -> None:
        """Refuse to commit an attempt a caught failure left rollback-only."""
        if self._rollback_only:
            raise _RollbackOnlyRefusal(
                "transaction is rollback-only; commit refused"
            ) from self._first_cause


class ActiveBinding[Payload]:
    """The one per-thread slot naming the transaction attempt running on it.

    Scoped: a payload is visible exactly while :meth:`bound` is entered, so
    nothing outlives the callback that installed it. The payload is opaque here;
    whoever binds it interprets it.
    """

    __slots__ = ("_local",)

    def __init__(self) -> None:
        self._local = _Slot[Payload]()

    def active(self) -> Payload | None:
        return self._local.payload

    @contextmanager
    def bound(self, payload: Payload) -> Generator[None]:
        self._local.payload = payload
        try:
            yield
        finally:
            self._local.payload = None


class _Slot[Payload](threading.local):
    payload: Payload | None = None
