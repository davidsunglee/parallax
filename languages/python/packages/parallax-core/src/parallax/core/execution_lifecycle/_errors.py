"""What a lifecycle context refuses, and what a Provider is told about.

An opening failure and a re-entrant call are exceptions because no execution
effect has begun yet, so refusing the operation is still free. A Handler failure
is a VALUE rather than an exception because execution has already begun: it is
reported out of band and changes nothing about the query it was observing.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from parallax.core.execution_lifecycle._diagnostics import FailureDiagnostic


class ExecutionLifecycleProviderError(RuntimeError):
    """A Provider's ``open`` failed ordinarily, so the operation is refused.

    Raised before execution state, clocks, or database work, which is the whole
    reason opening is allowed to fail the operation at all. The ordinary
    exception is preserved as ``__cause__`` and is never reinterpreted as a
    deliberate decline; a control-flow or fatal exception from ``open``
    propagates unchanged instead.
    """


class ExecutionLifecycleReentryError(RuntimeError):
    """A Handle was asked to work from inside one of its own lifecycle contexts.

    Provider opening, event delivery, and error reporting are lifecycle
    contexts, and calling an operation through the Handle or Transaction that
    opened one of them re-enters the very execution being observed. It is
    refused before execution state, clocks, or database work, so a Handler
    cannot change the query it is watching.

    The refusal is per Handle and per thread: an unrelated Handle stays fully
    usable from a lifecycle context, and a Handler that hands work to another
    thread is not re-entering. Where the refusal surfaces decides what it
    becomes — raised during opening it is the
    :class:`ExecutionLifecycleProviderError`'s cause, and raised inside a Handler
    it is an ordinary delivery failure that quarantines that Handler like any
    other.
    """


@dataclass(frozen=True, slots=True)
class ExecutionLifecycleHandlerError:
    """What a Provider is told when one of its Handlers raised ordinarily.

    Deliberately a value rather than an exception: it is handed to
    ``report_handler_error`` and never raised, because a Handler failure must
    not change the execution it was observing. The name follows the failure it
    reports, and the ``Error`` suffix is what the specification names it.

    Correlation-only and fully detached — root ID, event sequence, activity ID,
    the qualified type of the Handler that raised, the nested fan-out path
    reaching it, and the Failure Diagnostic. It carries no event, statement, or
    bind, so reporting can never become a second channel onto borrowed data.
    ``fanout_path`` is empty for a Handler a Provider opened directly, and holds
    the zero-based child positions descended through otherwise.
    """

    execution_id: UUID
    sequence: int
    activity_id: int
    handler_type: str
    fanout_path: tuple[int, ...]
    diagnostic: FailureDiagnostic
