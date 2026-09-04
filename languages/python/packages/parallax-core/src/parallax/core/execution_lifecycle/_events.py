"""The Root Execution descriptor and the transitions its activities emit.

Every transition is its own immutable concrete type admitting only its own
fields: there is no generic attribute bag, no kind-plus-payload record, and no
callback return value. :data:`ActivityStarted` and :data:`ActivityFinished` are
union aliases over those concretes, so a consumer matches a transition type
rather than a discriminator — and the aliases gain a member for each activity
kind that becomes observable, which is why matching them is not a stable
exhaustiveness claim.

The correlation envelope is shared by inheritance rather than restated per
transition, so ``event.sequence`` reads the same off any member of the union
while each transition stays a concrete type of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from parallax.core.db_port import IsolationLevel
from parallax.core.execution_lifecycle._diagnostics import (
    ActivityFailure,
    DatabaseFailureDiagnostic,
    FailureDiagnostic,
)
from parallax.core.sql_gen import LoweredStatement
from parallax.core.unit_work import Concurrency, WriteBatchTrigger

type RootExecutionKind = Literal["READ", "TRANSACTION_INVOCATION", "SNAPSHOT_STREAM"]
"""Which outermost Handle operation a Root Execution describes."""

type ReadInterface = Literal["TYPED", "WIRE", "ROWS"]
"""Which read interface published a Read's result; ``ROWS`` is the internal
values lane."""

type DatabaseCallKind = Literal["READ", "WRITE"]
"""Whether a Database Call ran a query or DML — carried so a FAILED call stays
classifiable without parsing its SQL."""


@dataclass(frozen=True, slots=True)
class RootExecution:
    """One outermost Handle operation and everything it causally contains.

    ``id`` is a random UUIDv4 whose equality and canonical text are meaningful;
    concurrent outermost operations are distinct roots with independent
    sequences and no implied global order.
    """

    id: UUID
    kind: RootExecutionKind


@dataclass(frozen=True, slots=True)
class _Event:
    """The correlation envelope every transition carries.

    ``sequence`` is the one-based contiguous delivery position within the root,
    assigned immediately before delivery. ``activity_id`` is one-based and
    contiguous within the root, assigned by a Started transition and reused by
    its Finished peer. ``parent_activity_id`` is absent only for the root
    activity; otherwise it names an activity started earlier in the same root.

    Never constructed directly: it exists so the envelope has one definition
    rather than one per transition, while each transition stays a concrete type
    admitting only its own fields.
    """

    execution_id: UUID
    sequence: int
    activity_id: int
    parent_activity_id: int | None


@dataclass(frozen=True, slots=True)
class ReadCompleted:
    """The Read published its public result."""


@dataclass(frozen=True, slots=True)
class ReadFailed:
    """The Read did not reach publication."""

    failure: ActivityFailure


type ReadOutcome = ReadCompleted | ReadFailed
"""How a Read ended, a closed union of exactly one member."""


@dataclass(frozen=True, slots=True)
class ReadStarted(_Event):
    """A Read opened over ``target`` through ``interface``.

    It starts after public preflight and any read-dependency Write Batch, and
    spans planning, lowering, all of its Database Calls, conversion,
    materialization, and publication.
    """

    target: str
    interface: ReadInterface


@dataclass(frozen=True, slots=True)
class ReadFinished(_Event):
    """The Read reached its terminal outcome."""

    outcome: ReadOutcome


@dataclass(frozen=True, slots=True)
class DatabaseReadCompleted:
    """A query call's completion: the PHYSICAL number of rows the statement
    returned — never a count of result roots, unique graph nodes, or projection
    views."""

    returned_rows: int


@dataclass(frozen=True, slots=True)
class DatabaseWriteCompleted:
    """A DML call's completion: the affected-row count the driver reported.

    A count that falls short of what the step addressed is still a COMPLETION —
    the call reached the database and came back — and post-call enforcement of
    that shortfall is the enclosing Write Batch's failure, not the call's.
    """

    affected_rows: int


@dataclass(frozen=True, slots=True)
class DatabaseCallFailed:
    """The port could not complete the call."""

    diagnostic: DatabaseFailureDiagnostic


type DatabaseCallOutcome = DatabaseReadCompleted | DatabaseWriteCompleted | DatabaseCallFailed
"""How a Database Call ended, a closed union of exactly one member."""


@dataclass(frozen=True, slots=True)
class DatabaseCallStarted(_Event):
    """One attempted round trip to the database is about to run.

    ``statement`` is the exact deeply immutable Lowered Statement presented to
    the port. It is BORROWED for synchronous delivery: neither its text nor its
    binds are copied, and a Handler that retains it violates the Handler
    contract.
    """

    target: str
    kind: DatabaseCallKind
    statement: LoweredStatement


@dataclass(frozen=True, slots=True)
class DatabaseCallFinished(_Event):
    """The round trip came back, however it came back.

    ``statement`` repeats the same borrowed value Started carried.
    ``duration_ns`` is monotonic elapsed time around the port invocation alone:
    the clock starts after Started has been delivered and stops before Finished
    is constructed, so Handler time stays outside it.
    """

    statement: LoweredStatement
    duration_ns: int
    outcome: DatabaseCallOutcome


@dataclass(frozen=True, slots=True)
class WriteBatchCompleted:
    """Every write the batch still held after planning reached the database.

    A batch planning reduced to no DML at all completes exactly like one that
    ran statements: the buffer was spent either way.
    """


@dataclass(frozen=True, slots=True)
class WriteBatchFailed:
    """The batch did not spend its buffer."""

    failure: ActivityFailure


type WriteBatchOutcome = WriteBatchCompleted | WriteBatchFailed
"""How a Write Batch ended, a closed union of exactly one member."""


@dataclass(frozen=True, slots=True)
class WriteBatchStarted(_Event):
    """A nonempty unit-of-work buffer is being flushed for ``trigger``.

    It starts BEFORE planning, so a batch a planning refusal ended is still a
    batch that started, and it spans planning, lowering, every Database Call, and
    affected-row enforcement. An empty buffer produces no activity at all.
    """

    trigger: WriteBatchTrigger


@dataclass(frozen=True, slots=True)
class WriteBatchFinished(_Event):
    """The batch reached its terminal outcome."""

    outcome: WriteBatchOutcome


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """The bounded-retry policy one outer invocation resolved.

    ``retries`` bounds RE-EXECUTIONS rather than total attempts.
    ``retry_optimistic_conflicts`` is the caller opt-in that widens the
    classifier, so the two together are the effective policy an attempt's
    ``retry_eligible`` verdict is reached under.
    """

    retries: int
    retry_optimistic_conflicts: bool


@dataclass(frozen=True, slots=True)
class OuterInvocation:
    """The invocation that opened the boundary, and therefore the root activity.

    It contains every physical attempt and every joined invocation beneath them.

    ``isolation`` is the Isolation Level this invocation REQUESTED, and ``None``
    where it requested none. It is not the level the database went on to use: a
    request naming none leaves the adapter's own default, which nothing above
    the port knows, so reporting that default here would state a fact this
    invocation never established.
    """

    concurrency: Concurrency
    retry_policy: RetryPolicy
    isolation: IsolationLevel | None


@dataclass(frozen=True, slots=True)
class JoinedInvocation:
    """An invocation that joined the boundary already active on this thread.

    It shares the outer root, sequence, unit of work, and transaction, and runs
    no attempt of its own, so it carries neither concurrency nor retry policy:
    both were resolved by the invocation it joined.
    """


type TransactionInvocation = OuterInvocation | JoinedInvocation
"""Which of the two calls to callback demarcation started, a closed union."""


@dataclass(frozen=True, slots=True)
class OuterInvocationCommitted:
    """The boundary committed and the callback's value is the caller's."""


@dataclass(frozen=True, slots=True)
class OuterInvocationFailed:
    """The boundary did not commit, whatever its attempts did on the way."""

    failure: ActivityFailure


@dataclass(frozen=True, slots=True)
class JoinedInvocationReturned:
    """The nested callback returned.

    It says nothing about the physical transaction, which is still open and
    still owned by the invocation this one joined.
    """


@dataclass(frozen=True, slots=True)
class JoinedInvocationRaised:
    """The nested callback raised, which dooms the transaction it joined."""

    failure: ActivityFailure


type TransactionInvocationOutcome = (
    OuterInvocationCommitted
    | OuterInvocationFailed
    | JoinedInvocationReturned
    | JoinedInvocationRaised
)
"""How a Transaction Invocation ended, a closed union of exactly one member."""


@dataclass(frozen=True, slots=True)
class TransactionInvocationStarted(_Event):
    """One call to callback demarcation opened."""

    invocation: TransactionInvocation


@dataclass(frozen=True, slots=True)
class TransactionInvocationFinished(_Event):
    """The invocation reached its terminal outcome."""

    outcome: TransactionInvocationOutcome


type AttemptPhase = Literal["CALLBACK", "PRE_COMMIT", "COMMIT"]
"""Where inside a physical attempt its failure arose.

``CALLBACK`` covers the callback itself and everything it caused — joined
invocations, reads, and read-dependency batches. ``PRE_COMMIT`` is the final
automatic batch after the callback returned. ``COMMIT`` is the durability call.
"""


@dataclass(frozen=True, slots=True)
class AttemptFailure:
    """What ended one physical attempt.

    ``retry_eligible`` is the classifier's verdict under the effective policy and
    is INDEPENDENT of the budget that remained: an exhausting attempt still
    reports the truth about the failure, and a rollback failure reports it even
    though it is never retried.
    """

    phase: AttemptPhase
    failure: ActivityFailure
    retry_eligible: bool


@dataclass(frozen=True, slots=True)
class AttemptCommitted:
    """The attempt committed, so the invocation it belongs to is over."""


@dataclass(frozen=True, slots=True)
class AttemptRolledBack:
    """Something ended the attempt and the rollback completed."""

    failure: AttemptFailure


@dataclass(frozen=True, slots=True)
class AttemptRollbackFailed:
    """The rollback the attempt's failure required did not complete.

    Both live failures are reported because either alone misreports what
    happened, and what the attempt left behind is unknown — which is why this
    outcome is never retried however retry-eligible its trigger was.
    """

    triggering_failure: AttemptFailure
    rollback_failure: FailureDiagnostic


type TransactionAttemptOutcome = AttemptCommitted | AttemptRolledBack | AttemptRollbackFailed
"""How a Transaction Attempt ended, a closed union of exactly one member."""


@dataclass(frozen=True, slots=True)
class TransactionAttemptStarted(_Event):
    """The database boundary began, so one physical attempt is running.

    It carries no attempt-specific fields: which attempt of the invocation this
    is reads off the correlation envelope, and everything about the policy it
    runs under was stated by the invocation that opened it.
    """


@dataclass(frozen=True, slots=True)
class TransactionAttemptFinished(_Event):
    """The attempt reached its terminal outcome."""

    outcome: TransactionAttemptOutcome


@dataclass(frozen=True, slots=True)
class StreamExhausted:
    """The stream yielded its last page and finished at the moment that was
    discovered."""


@dataclass(frozen=True, slots=True)
class StreamClosedEarly:
    """The caller stopped before exhaustion — a break, an explicit close, an
    exception of its own, or a cancellation.

    It describes only that the stream ended early. The caller's control flow is
    untouched: an exception that ended the iteration still propagates as itself,
    and this outcome never turns into one.
    """


@dataclass(frozen=True, slots=True)
class StreamFailed:
    """Parallax's own work ended the stream: planning, a database call,
    conversion, materialization, invalid data, or resource cleanup.

    Reserved for those. Once a stream is exhausted a later caller error cannot
    rewrite the outcome into this one.
    """

    failure: ActivityFailure


type SnapshotStreamOutcome = StreamExhausted | StreamClosedEarly | StreamFailed
"""How a Snapshot Stream ended, a closed union of exactly one member."""


@dataclass(frozen=True, slots=True)
class SnapshotStreamStarted(_Event):
    """A stream over ``target`` opened and is about to be iterated.

    Constructing a stream emits nothing: this is delivered only once context
    entry has succeeded. ``batch_size`` is the positive page size the stream
    requests, which is what makes its Stream Batch children countable against a
    result the events never size.
    """

    target: str
    interface: ReadInterface
    batch_size: int


@dataclass(frozen=True, slots=True)
class SnapshotStreamFinished(_Event):
    """The stream reached its terminal outcome."""

    outcome: SnapshotStreamOutcome


@dataclass(frozen=True, slots=True)
class StreamBatchCompleted:
    """The whole page is ready to yield, a page that kept no root included."""


@dataclass(frozen=True, slots=True)
class StreamBatchFailed:
    """The page did not become ready."""

    failure: ActivityFailure


type StreamBatchOutcome = StreamBatchCompleted | StreamBatchFailed
"""How a Stream Batch ended, a closed union of exactly one member."""


@dataclass(frozen=True, slots=True)
class StreamBatchStarted(_Event):
    """One requested page opened.

    It carries no page-specific fields: which page of the stream this is reads
    off the correlation envelope, and the size it was requested at was stated by
    the stream that opened it. A batch is the page-read activity in its own
    right and never nests a Read.
    """


@dataclass(frozen=True, slots=True)
class StreamBatchFinished(_Event):
    """The page reached its terminal outcome."""

    outcome: StreamBatchOutcome


type ActivityStarted = (
    ReadStarted
    | WriteBatchStarted
    | DatabaseCallStarted
    | TransactionInvocationStarted
    | TransactionAttemptStarted
    | SnapshotStreamStarted
    | StreamBatchStarted
)
"""Every transition that opens an activity and assigns its ``activity_id``."""

type ActivityFinished = (
    ReadFinished
    | WriteBatchFinished
    | DatabaseCallFinished
    | TransactionInvocationFinished
    | TransactionAttemptFinished
    | SnapshotStreamFinished
    | StreamBatchFinished
)
"""Every transition that closes an activity with its terminal outcome."""

type ExecutionEvent = ActivityStarted | ActivityFinished
"""Every concrete transition a Handler receives."""
