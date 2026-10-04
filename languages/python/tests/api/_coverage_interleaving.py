"""A lifecycle Provider that lets another session commit between a flush's
coverage read and the writes it binds."""

from __future__ import annotations

import threading
from collections.abc import Callable

from parallax.core.execution_lifecycle import (
    DatabaseCallFinished,
    DatabaseReadCompleted,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    RootExecution,
)


class AfterCoverageRead:
    """A Provider whose Handler runs ``peer`` to completion on another thread
    once, right after the ``nth`` coverage read write batches issue for
    ``table`` — between that read and the writes it binds."""

    def __init__(self, table: str, peer: Callable[[], None], *, nth: int = 1) -> None:
        self._table = table
        self._peer = peer
        self._remaining = nth
        self.fired = False
        self.failures: list[BaseException] = []
        self.reported: list[ExecutionLifecycleHandlerError] = []

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        del execution
        return _Interleave(self)

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        self.reported.append(error)

    def interleave(self, sql: str) -> None:
        if self.fired or self._table not in sql or "thru_z >" not in sql:
            return
        self._remaining -= 1
        if self._remaining:
            return
        self.fired = True

        def run() -> None:
            try:
                self._peer()
            except BaseException as failure:
                self.failures.append(failure)

        peer = threading.Thread(target=run)
        peer.start()
        peer.join(timeout=30.0)


class _Interleave:
    def __init__(self, provider: AfterCoverageRead) -> None:
        self._provider = provider

    def handle(self, event: object, /) -> None:
        if isinstance(event, DatabaseCallFinished) and isinstance(
            event.outcome, DatabaseReadCompleted
        ):
            self._provider.interleave(event.statement.sql)
