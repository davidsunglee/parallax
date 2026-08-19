"""``parallax.core.execution_lifecycle`` enforcement scope (m-execution-lifecycle).

Transient execution observability: a composition-supplied Provider opens at most
one Handler per Root Execution and receives a closed stream of immutable Started
and Finished events while the work proceeds. Nothing is retained — results,
snapshots, streams, and transactions expose no lifecycle accessor, and a
completed root leaves no reference behind.

The module is a composition-level OBSERVER. It names `m-sql` (the Lowered
Statement a call ran), `m-db-port` (the call boundary), `m-db-error` (the
category a failed call classified to), `m-unit-work` (the transaction and its
write batches) and `m-auto-retry` (the retry policy and the classifier's
verdict); none of them names it. A composition root threads the publisher down
to the observed work, which is why no observed module discovers a Provider or
records history of its own.

The names below are the whole supported seam; everything else in this package is
private implementation. The activity scopes the composition root drives —
:data:`~parallax.core.execution_lifecycle._activity.INERT` and the per-kind
activity Protocols — are deliberately absent: they are the internal seam an
observed module is HANDED, not a surface an application names.

The private modules split by change rate rather than by tidiness:

* ``_events`` — the Root Execution descriptor and the transitions its activities
  emit. Its shape answers to the specified algebra rather than to any caller.
* ``_diagnostics`` — the detached, byte-bounded projection of an exception and
  the causal attribution an activity failure carries.
* ``_activity`` — the Provider and Handler Protocols, the per-root publisher,
  the live activity scopes, and the shared inert stand-in.
* ``_errors`` — the opening refusal, and the Handler failure a Provider is told
  about out of band.

``testing`` is a separate enforcement scope with no production importer: the
recorder there grows with the number of events by design, and declaring the
scope ISOLATED — a child a grant on this package does not carry — is what turns
"not a production observability path" from a sentence into a rejected import.
Outside this package a generated forbidden contract rejects it; inside it, where
no such contract can name a module of its own source package, the file-level
check in ``tools/check_scope_ownership.py`` does.
"""

from __future__ import annotations

from parallax.core.execution_lifecycle._activity import (
    ExecutionLifecycleHandler,
    ExecutionLifecycleProvider,
)
from parallax.core.execution_lifecycle._diagnostics import (
    MESSAGE_LIMIT_BYTES,
    STACK_LIMIT_BYTES,
    ActivityFailure,
    CausedFailure,
    DatabaseFailureDiagnostic,
    DirectFailure,
    FailureDiagnostic,
)
from parallax.core.execution_lifecycle._errors import (
    ExecutionLifecycleHandlerError,
    ExecutionLifecycleProviderError,
)
from parallax.core.execution_lifecycle._events import (
    ActivityFinished,
    ActivityStarted,
    AttemptCommitted,
    AttemptFailure,
    AttemptPhase,
    AttemptRollbackFailed,
    AttemptRolledBack,
    DatabaseCallFailed,
    DatabaseCallFinished,
    DatabaseCallKind,
    DatabaseCallOutcome,
    DatabaseCallStarted,
    DatabaseReadCompleted,
    DatabaseWriteCompleted,
    ExecutionEvent,
    JoinedInvocation,
    JoinedInvocationRaised,
    JoinedInvocationReturned,
    OuterInvocation,
    OuterInvocationCommitted,
    OuterInvocationFailed,
    ReadCompleted,
    ReadFailed,
    ReadFinished,
    ReadInterface,
    ReadOutcome,
    ReadStarted,
    RetryPolicy,
    RootExecution,
    RootExecutionKind,
    TransactionAttemptFinished,
    TransactionAttemptOutcome,
    TransactionAttemptStarted,
    TransactionInvocation,
    TransactionInvocationFinished,
    TransactionInvocationOutcome,
    TransactionInvocationStarted,
    WriteBatchCompleted,
    WriteBatchFailed,
    WriteBatchFinished,
    WriteBatchOutcome,
    WriteBatchStarted,
)

__all__ = [
    "MESSAGE_LIMIT_BYTES",
    "STACK_LIMIT_BYTES",
    "ActivityFailure",
    "ActivityFinished",
    "ActivityStarted",
    "AttemptCommitted",
    "AttemptFailure",
    "AttemptPhase",
    "AttemptRollbackFailed",
    "AttemptRolledBack",
    "CausedFailure",
    "DatabaseCallFailed",
    "DatabaseCallFinished",
    "DatabaseCallKind",
    "DatabaseCallOutcome",
    "DatabaseCallStarted",
    "DatabaseFailureDiagnostic",
    "DatabaseReadCompleted",
    "DatabaseWriteCompleted",
    "DirectFailure",
    "ExecutionEvent",
    "ExecutionLifecycleHandler",
    "ExecutionLifecycleHandlerError",
    "ExecutionLifecycleProvider",
    "ExecutionLifecycleProviderError",
    "FailureDiagnostic",
    "JoinedInvocation",
    "JoinedInvocationRaised",
    "JoinedInvocationReturned",
    "OuterInvocation",
    "OuterInvocationCommitted",
    "OuterInvocationFailed",
    "ReadCompleted",
    "ReadFailed",
    "ReadFinished",
    "ReadInterface",
    "ReadOutcome",
    "ReadStarted",
    "RetryPolicy",
    "RootExecution",
    "RootExecutionKind",
    "TransactionAttemptFinished",
    "TransactionAttemptOutcome",
    "TransactionAttemptStarted",
    "TransactionInvocation",
    "TransactionInvocationFinished",
    "TransactionInvocationOutcome",
    "TransactionInvocationStarted",
    "WriteBatchCompleted",
    "WriteBatchFailed",
    "WriteBatchFinished",
    "WriteBatchOutcome",
    "WriteBatchStarted",
]
