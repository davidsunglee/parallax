"""``parallax.core.execution_lifecycle.testing`` enforcement scope — the complete
recorder.

TESTING ONLY. :class:`RecordingLifecycleProvider` retains every event of every
root it accepts, so it grows ``O(events)`` by design and violates the bounded
per-root state a production Handler owes. It is also the one Handler that
retains the Lowered Statements a Database Call borrows. Both are deliberate: a
suite grading a delivered event stream needs the whole stream, and a production
observability path needs neither.

It is its own ISOLATED enforcement scope precisely so that "not a production
observability path" is a build failure rather than a sentence: a grant on the
parent package does not carry this child, so every production scope outside that
package has it as a forbidden target rather than merely an unstated one, and the
one import a contract cannot reject — a module of the parent package reaching
this child — is rejected over the files themselves by
``tools/check_scope_ownership.py``. This package is also absent from
:mod:`parallax.core.execution_lifecycle`'s re-exports.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from parallax.core.execution_lifecycle._activity import ExecutionLifecycleHandler
from parallax.core.execution_lifecycle._errors import ExecutionLifecycleHandlerError
from parallax.core.execution_lifecycle._events import ExecutionEvent, RootExecution

__all__ = ["RecordedRoot", "RecordingLifecycleProvider"]


@dataclass(frozen=True, slots=True)
class RecordedRoot:
    """One accepted Root Execution's descriptor and the events it delivered.

    ``events`` is in delivery order, so its positions and each event's own
    ``sequence`` agree for a root no Handler failure quarantined.
    """

    execution: RootExecution
    events: tuple[ExecutionEvent, ...]


class _Recorder:
    """One root's Handler: an append-only list under the Provider's lock.

    Events are immutable values already detached from the execution that
    produced them, so recording is an append rather than a copy.
    """

    __slots__ = ("_events", "_lock")

    def __init__(self, lock: threading.Lock) -> None:
        self._lock = lock
        self._events: list[ExecutionEvent] = []

    def handle(self, event: ExecutionEvent, /) -> None:
        with self._lock:
            self._events.append(event)

    def recorded(self) -> tuple[ExecutionEvent, ...]:
        with self._lock:
            return tuple(self._events)


class RecordingLifecycleProvider:
    """A Provider that accepts every root and keeps everything it is told.

    Roots are grouped and answered in the order they were opened, so concurrent
    roots stay separable without exposing their UUIDs to a caller that only
    needs to tell them apart. Handler failures cannot arise from the recorder
    itself, but :attr:`handler_errors` still records any it is told about, which
    is what lets a suite driving a deliberately failing Handler alongside it
    assert the report.
    """

    __slots__ = ("_errors", "_lock", "_roots")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._roots: list[tuple[RootExecution, _Recorder]] = []
        self._errors: list[ExecutionLifecycleHandlerError] = []

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        recorder = _Recorder(self._lock)
        with self._lock:
            self._roots.append((execution, recorder))
        return recorder

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        with self._lock:
            self._errors.append(error)

    @property
    def roots(self) -> tuple[RecordedRoot, ...]:
        """Every root opened so far, in opening order, with its events."""
        with self._lock:
            opened = tuple(self._roots)
        return tuple(RecordedRoot(execution, recorder.recorded()) for execution, recorder in opened)

    @property
    def handler_errors(self) -> tuple[ExecutionLifecycleHandlerError, ...]:
        """Every Handler failure this Provider was told about, in report order."""
        with self._lock:
            return tuple(self._errors)
