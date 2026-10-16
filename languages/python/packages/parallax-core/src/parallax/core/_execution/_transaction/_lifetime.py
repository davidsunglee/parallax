from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager

from parallax.core._execution._unit_work.uow import EscapedTransactionError, RollbackOnlyError

__all__ = ["ActiveBinding", "TxnAttemptLifetime"]


class TxnAttemptLifetime:
    """Whether one transaction attempt still admits work, and why not.

    The single owner of the attempt's open/closed status, its rollback-only
    status, and the first failure that doomed it. The runner, the attempt, its
    handles and streams, and a writable attempt's unit of work all consult this
    one object, so no second flag can disagree with it.
    """

    __slots__ = ("_closed", "_first_cause", "_rollback_only")

    def __init__(self) -> None:
        self._closed = False
        self._rollback_only = False
        self._first_cause: BaseException | None = None

    @property
    def rollback_only(self) -> bool:
        return self._rollback_only

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
            raise EscapedTransactionError(
                "the transaction has ended; a reference escaped its attempt"
            )
        if self._rollback_only:
            raise RollbackOnlyError(
                "the transaction is rollback-only; it accepts no further work"
            ) from self._first_cause

    def refuse_join(self) -> None:
        """Refuse a joining invocation into a rollback-only attempt."""
        if self._rollback_only:
            raise RollbackOnlyError(
                "cannot join a rollback-only transaction"
            ) from self._first_cause

    def refuse_commit(self) -> None:
        """Refuse to commit an attempt a caught failure left rollback-only."""
        if self._rollback_only:
            raise RollbackOnlyError(
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
