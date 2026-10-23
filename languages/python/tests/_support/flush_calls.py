"""A lifecycle Provider recording each Flush's own Database Calls and each
stream page's read, by the activity that parents them."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from parallax.core.execution_lifecycle import (
    DatabaseCallFinished,
    DatabaseCallStarted,
    DatabaseReadCompleted,
    ExecutionEvent,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    ExecutionLifecycleProvider,
    FlushStarted,
    RootExecution,
    StreamBatchStarted,
)

type Call = tuple[str, int | None]
"""``("read", returned rows)`` or ``("write", None)``."""


@dataclass
class Flush:
    trigger: str
    calls: list[Call] = field(default_factory=list[Call])

    @property
    def coverage_reads(self) -> int:
        return sum(kind == "read" for kind, _rows in self.calls)

    @property
    def writes(self) -> int:
        return sum(kind == "write" for kind, _rows in self.calls)


@dataclass(frozen=True)
class PageRead:
    requested: object
    """The page statement's last bind, its row limit."""
    returned: int


class FlushCalls:
    """Records into ``flushes`` and ``pages``, passing every event on to
    ``inner``'s Handler where one is given."""

    def __init__(self, inner: ExecutionLifecycleProvider | None = None) -> None:
        self._inner = inner
        self.flushes: list[Flush] = []
        self.pages: list[PageRead] = []

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        inner = None if self._inner is None else self._inner.open(execution)
        return _Recording(self, inner)

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        if self._inner is None:
            raise AssertionError(f"lifecycle handler failed: {error!r}")
        self._inner.report_handler_error(error)


class _Recording:
    def __init__(self, calls: FlushCalls, inner: ExecutionLifecycleHandler | None) -> None:
        self._calls = calls
        self._inner = inner
        self._flushes: dict[int, Flush] = {}
        self._batches: set[int] = set()
        self._started: dict[int, tuple[str, int | None, object]] = {}

    def handle(self, event: ExecutionEvent, /) -> None:
        if isinstance(event, FlushStarted):
            flush = Flush(event.trigger)
            self._flushes[event.activity_id] = flush
            self._calls.flushes.append(flush)
        elif isinstance(event, StreamBatchStarted):
            self._batches.add(event.activity_id)
        elif isinstance(event, DatabaseCallStarted):
            limit = event.statement.binds[-1] if event.statement.binds else None
            self._started[event.activity_id] = (event.kind, event.parent_activity_id, limit)
        elif isinstance(event, DatabaseCallFinished) and event.activity_id in self._started:
            kind, parent, limit = self._started.pop(event.activity_id)
            rows = (
                event.outcome.returned_rows
                if isinstance(event.outcome, DatabaseReadCompleted)
                else None
            )
            if parent in self._flushes:
                self._flushes[parent].calls.append((kind, rows))
            elif parent in self._batches and rows is not None:
                self._calls.pages.append(PageRead(limit, rows))
        if self._inner is not None:
            self._inner.handle(event)


def call_runs(calls: Sequence[Call]) -> list[Call]:
    """``calls`` with each run of writes as one ``("write", count)``."""
    runs: list[Call] = []
    for kind, rows in calls:
        if kind == "write" and runs and runs[-1][0] == "write":
            count = runs[-1][1]
            assert count is not None
            runs[-1] = ("write", count + 1)
        else:
            runs.append((kind, 1 if kind == "write" else rows))
    return runs
