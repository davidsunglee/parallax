"""The two things a Provider is told about, when telling it is all that is left.

An opening failure is an exception because no execution effect has begun yet, so
refusing the operation is still free. A Handler failure is a VALUE rather than an
exception because execution has already begun: it is reported out of band and
changes nothing about the query it was observing.
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
