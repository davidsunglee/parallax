"""What one run did, read off the Execution Lifecycle events it delivered.

The engine installs one Provider per Handle it builds, and everything the
corpus asks about a run is answered from the stream that Provider received:
`then.statements` is the Lowered Statement each Database Call carried, in
delivery order — for a write lane, the plan that stream confirmed, because the
compile lane grades the same oracle with no delivery to read; `then.roundTrips`
is how many Database Call activities the run opened, so transaction demarcation
counts none without the counter having to know that; and
`then.executionLifecycle` is the stream itself, normalized.

Reading them from the delivered stream rather than from a decorator around the
Database Port is what keeps the adapter thin over production: a statement
arrives here in its canonical `?`-placeholder form because that is the form the
activity borrowed, so nothing has to recover it from driver text.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal, assert_never

from parallax.core.execution_lifecycle import (
    AttemptCommitted,
    AttemptFailure,
    AttemptRollbackFailed,
    AttemptRolledBack,
    CausedFailure,
    DatabaseCallFailed,
    DatabaseCallFinished,
    DatabaseCallStarted,
    DatabaseReadCompleted,
    DatabaseWriteCompleted,
    DirectFailure,
    ExecutionEvent,
    ExecutionLifecycleProvider,
    JoinedInvocation,
    JoinedInvocationRaised,
    JoinedInvocationReturned,
    OuterInvocation,
    OuterInvocationCommitted,
    OuterInvocationFailed,
    ReadCompleted,
    ReadFailed,
    ReadFinished,
    ReadStarted,
    RootExecutionKind,
    SnapshotStreamFinished,
    SnapshotStreamStarted,
    StreamBatchCompleted,
    StreamBatchFailed,
    StreamBatchFinished,
    StreamBatchStarted,
    StreamClosedEarly,
    StreamExhausted,
    StreamFailed,
    TransactionAttemptFinished,
    TransactionAttemptStarted,
    TransactionInvocationFinished,
    TransactionInvocationStarted,
    WriteBatchCompleted,
    WriteBatchFailed,
    WriteBatchFinished,
    WriteBatchStarted,
)
from parallax.core.execution_lifecycle.testing import RecordedRoot, RecordingLifecycleProvider
from parallax.core.sql_gen import LoweredStatement

__all__ = [
    "LifecycleObservation",
    "LifecycleRun",
    "ObservedCall",
    "StatementIndexError",
    "execution_lifecycle_observation",
    "lifecycle_run",
]


class StatementIndexError(RuntimeError):
    """A Database Call's statement index would name nothing, or the wrong thing.

    Raised rather than reported: the two sides it reconciles are the adapter's
    own, so a disagreement is an adapter defect and not a case failure.
    """


@dataclass(frozen=True, slots=True)
class ObservedCall:
    """One attempted round trip, in the canonical form the activity borrowed.

    ``kind`` is the Database Call's own, which is the same read/write split the
    corpus charges a materializing pair's resolve and its per-row writes to
    separate pointers by.
    """

    statement: LoweredStatement
    kind: Literal["read", "write"]


_CALL_KIND: Final[dict[str, Literal["read", "write"]]] = {"READ": "read", "WRITE": "write"}

_ROOT_KIND: Final[dict[RootExecutionKind, str]] = {
    "READ": "read",
    "TRANSACTION_INVOCATION": "transaction-invocation",
    "SNAPSHOT_STREAM": "snapshot-stream",
}

_READ_INTERFACE: Final[dict[str, str]] = {"TYPED": "typed", "WIRE": "wire", "ROWS": "rows"}

_WRITE_BATCH_TRIGGER: Final[dict[str, str]] = {
    "read_dependency": "read-dependency",
    "pre_commit": "pre-commit",
}

_ATTEMPT_PHASE: Final[dict[str, str]] = {
    "CALLBACK": "callback",
    "PRE_COMMIT": "pre-commit",
    "COMMIT": "commit",
}


class LifecycleObservation:
    """One Handle's own roots, and the projections a step or unit reports.

    An observation spans however many transactions and attempts the Handle it is
    installed on drives: a failed attempt's statements are recorded exactly like
    a committed one's, because a round trip is charged for reaching the database
    rather than for surviving. Roots are answered in the order they opened.

    The unit an observation covers is the unit whose counts a case states —
    a whole read, one buffered write unit, one held `uow` group — because
    `then.roundTrips` is authored per step. Whole-run questions are the
    :class:`LifecycleRun`'s.
    """

    __slots__ = ("_recorder",)

    def __init__(self) -> None:
        self._recorder = RecordingLifecycleProvider()

    @property
    def provider(self) -> ExecutionLifecycleProvider:
        """The Provider to install on the Handle whose work this observes."""
        return self._recorder

    @property
    def roots(self) -> tuple[RecordedRoot, ...]:
        """Every Root Execution this observation's Handle opened, in opening
        order."""
        return self._recorder.roots

    @property
    def calls(self) -> tuple[ObservedCall, ...]:
        """Every Database Call this run opened, in delivery order.

        Read off ``DatabaseCallStarted`` rather than off the Finished peer, so a
        call the database never answered is still the round trip it was charged
        for.
        """
        return tuple(
            ObservedCall(event.statement, _CALL_KIND[event.kind])
            for root in self.roots
            for event in root.events
            if isinstance(event, DatabaseCallStarted)
        )

    @property
    def statements(self) -> tuple[LoweredStatement, ...]:
        return tuple(call.statement for call in self.calls)

    @property
    def reads(self) -> tuple[LoweredStatement, ...]:
        return tuple(call.statement for call in self.calls if call.kind == "read")

    @property
    def writes(self) -> tuple[LoweredStatement, ...]:
        return tuple(call.statement for call in self.calls if call.kind == "write")

    def since(
        self, mark: int, kind: Literal["read", "write"] | None = None
    ) -> tuple[LoweredStatement, ...]:
        """Every statement of ``kind`` issued after ``mark`` round trips.

        A run driving many steps through one handle reads each step's own
        emissions by taking :attr:`round_trips` before it and asking for the
        difference after, so one observation serves a whole scenario without a
        second observation per step.

        ``kind`` matters because a participating read force-flushes: the DML a
        read triggers belongs to the write step that buffered it, which reports
        its own pure re-lowering, so asking a find step for its reads is what
        keeps one statement from being emitted under two pointers.
        """
        return tuple(
            call.statement for call in self.calls[mark:] if kind is None or call.kind == kind
        )

    @property
    def round_trips(self) -> int:
        """Every attempted call, failed ones included. Begin, commit, and
        rollback are no Database Call and so count none (`m-db-port`,
        `m-execution-lifecycle`)."""
        return len(self.calls)


class LifecycleRun:
    """Every Root Execution one whole case run opened, in the order it opened them.

    A run builds a Handle per unit of work it drives rather than one for the
    whole case, and each Handle reports its own counts through an observation of
    its own. This is what puts their roots back into one order, which is what
    `then.executionLifecycle` grades: the oracle describes the run, while
    `then.roundTrips` describes a step.

    Observations are minted here in the order the lanes run, so the flattened
    order is execution order for every lane that runs its work sequentially.
    The one lane that does not — two connections driven at once — reports no
    oracle and could not, because two simultaneous connections have no single
    root order to state.
    """

    __slots__ = ("_observations",)

    def __init__(self) -> None:
        self._observations: list[LifecycleObservation] = []

    def observation(self) -> LifecycleObservation:
        """A fresh observation for the next Handle this run builds."""
        observation = LifecycleObservation()
        self._observations.append(observation)
        return observation

    @property
    def roots(self) -> tuple[RecordedRoot, ...]:
        return tuple(root for observation in self._observations for root in observation.roots)


def lifecycle_run(supplied: LifecycleRun | None) -> LifecycleRun:
    """``supplied``, or a run of this call's own.

    Every engine entry point drives its work through a run, because each Handle
    it builds needs an observation of its own; whether anything READS that run
    afterwards is the caller's business, and a caller grading no lifecycle
    oracle supplies none.
    """
    return LifecycleRun() if supplied is None else supplied


def execution_lifecycle_observation(
    roots: Sequence[RecordedRoot], statements: Sequence[str]
) -> dict[str, object]:
    """One run's `executionLifecycle` observation, in the shape the case authors.

    ``statements`` is the envelope's own emission order, which a Database Call
    names by index instead of repeating its SQL. A lane reporting no emission at
    all — `api-conformance` — leaves every call's index absent, which is exactly
    what its cases author.
    """
    indexer = _StatementIndexer(statements)
    return {
        "roots": [
            {
                "execution": position,
                "kind": _ROOT_KIND[root.execution.kind],
                "events": [_portable(event, indexer) for event in root.events],
            }
            for position, root in enumerate(roots, start=1)
        ]
    }


class _StatementIndexer:
    """Hands each Database Call, in delivery order, its index into the
    envelope's own emissions, and VALIDATES that the index names the statement
    the call ran.

    The correspondence is positional — the k-th call ran the k-th emission — but
    it is not assumed. On the grouped-scenario lanes the two sides are built
    independently: the emissions are a pure re-lowering of the case-authored
    rows, per step, while execution buffers the whole group and flushes it as one
    plan, so foreign-key reordering inside that plan, or any drift between the
    two lowerings, would leave position *k* naming a different statement while
    the case still graded green. Comparing the SQL text closes every mechanism
    that changes it.

    Binds are reconciled before this, by the lane that reported the emission:
    the two sides differ in representation on purpose — the emission stays on the
    undecoded, case-authored wire spelling (an authored ``250.00``) while
    execution binds the native carrier a decode produced (``Decimal("250.00")``)
    — so they are compared where the difference is known, in wire space with the
    exact-Decimal reconciliation goldens are graded under. What is left here is
    the index's own question, which the SQL answers.
    """

    __slots__ = ("_position", "_statements")

    def __init__(self, statements: Sequence[str]) -> None:
        self._statements = statements
        self._position = 0

    def take(self, statement: LoweredStatement) -> int | None:
        """``statement``'s index, or ``None`` on a lane reporting no emission."""
        if not self._statements:
            return None
        index = self._position
        self._position += 1
        if index >= len(self._statements):
            raise StatementIndexError(
                f"the lifecycle delivered {index + 1} database call(s) but the envelope "
                f"reports only {len(self._statements)} emission(s): the observation's "
                "statement index would name nothing (m-conformance-adapter)"
            )
        emitted = self._statements[index]
        if statement.sql != emitted:
            raise StatementIndexError(
                f"the lifecycle's database call {index} ran {statement.sql!r}, but the "
                f"envelope's emission {index} reports {emitted!r}: the observation's "
                "statement index would name a different statement (m-conformance-adapter)"
            )
        return index


def _portable(event: ExecutionEvent, indexer: _StatementIndexer) -> dict[str, object]:
    """One delivered transition as the case authors it.

    The correlation envelope is stated on every event and the transition rides
    one wrapper, so a reader tells the transitions apart by name rather than by
    which fields happen to be present. ``parent`` is null on the root activity
    and on no other, which is the claim rather than an omission.
    """
    return {
        "sequence": event.sequence,
        "activity": event.activity_id,
        "parent": event.parent_activity_id,
        **_transition(event, indexer),
    }


def _transition(event: ExecutionEvent, indexer: _StatementIndexer) -> dict[str, object]:
    """The one wrapper naming ``event``'s transition, and its portable payload.

    The one exhaustive match over the event union: a transition added to the
    algebra fails to type-check here until the observation can spell it.
    """
    match event:
        case ReadStarted(target=target, interface=interface):
            return {"readStarted": {"target": target, "interface": _READ_INTERFACE[interface]}}
        case ReadFinished(outcome=outcome):
            return {"readFinished": _read_outcome(outcome)}
        case WriteBatchStarted(trigger=trigger):
            return {"writeBatchStarted": {"trigger": _WRITE_BATCH_TRIGGER[trigger]}}
        case WriteBatchFinished(outcome=outcome):
            return {"writeBatchFinished": _write_batch_outcome(outcome)}
        case DatabaseCallStarted(target=target, kind=kind, statement=statement):
            started: dict[str, object] = {"target": target, "kind": _CALL_KIND[kind]}
            index = indexer.take(statement)
            if index is not None:
                started["statement"] = index
            return {"databaseCallStarted": started}
        case DatabaseCallFinished(outcome=outcome):
            return {"databaseCallFinished": _database_call_outcome(outcome)}
        case TransactionInvocationStarted(invocation=invocation):
            return {"transactionInvocationStarted": _invocation(invocation)}
        case TransactionInvocationFinished(outcome=outcome):
            return {"transactionInvocationFinished": _invocation_outcome(outcome)}
        case TransactionAttemptStarted():
            return {"transactionAttemptStarted": {}}
        case TransactionAttemptFinished(outcome=outcome):
            return {"transactionAttemptFinished": _attempt_outcome(outcome)}
        case SnapshotStreamStarted(target=target, interface=interface, batch_size=batch_size):
            return {
                "snapshotStreamStarted": {
                    "target": target,
                    "interface": _READ_INTERFACE[interface],
                    "batchSize": batch_size,
                }
            }
        case SnapshotStreamFinished(outcome=outcome):
            return {"snapshotStreamFinished": _stream_outcome(outcome)}
        case StreamBatchStarted():
            return {"streamBatchStarted": {}}
        case StreamBatchFinished(outcome=outcome):
            return {"streamBatchFinished": _stream_batch_outcome(outcome)}
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _activity_failure(failure: DirectFailure | CausedFailure) -> dict[str, object]:
    """How an activity's failure was attributed, and the one portable fact its
    diagnostic carries.

    ``attribution`` is stated rather than implied by the presence of ``cause``:
    which child a failure names — or that it names none — is the assertion, and
    an absent key would read as an unwritten one. ``code`` is the stable string
    an exception publishes as its own, absent for one publishing none, which is
    every first-party failure this corpus can produce.
    """
    fields: dict[str, object] = {}
    match failure:
        case DirectFailure():
            fields["attribution"] = "direct"
        case CausedFailure(cause_activity_id=cause):
            fields["attribution"] = "caused"
            fields["cause"] = cause
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)
    if failure.diagnostic.code is not None:
        fields["code"] = failure.diagnostic.code
    return fields


def _read_outcome(outcome: ReadCompleted | ReadFailed) -> dict[str, object]:
    match outcome:
        case ReadCompleted():
            return {"outcome": "completed"}
        case ReadFailed(failure):
            return {"outcome": "failed", **_activity_failure(failure)}
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _write_batch_outcome(outcome: WriteBatchCompleted | WriteBatchFailed) -> dict[str, object]:
    match outcome:
        case WriteBatchCompleted():
            return {"outcome": "completed"}
        case WriteBatchFailed(failure):
            return {"outcome": "failed", **_activity_failure(failure)}
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _database_call_outcome(
    outcome: DatabaseReadCompleted | DatabaseWriteCompleted | DatabaseCallFailed,
) -> dict[str, object]:
    """A call's own terminal outcome.

    A failed call is the ONE place the neutral `m-db-error` Category is
    portable, because it is the one place `m-execution-lifecycle` puts a
    Database Failure Diagnostic; the native code it sits beside is not portable
    and stays out.
    """
    match outcome:
        case DatabaseReadCompleted(returned_rows):
            return {"outcome": "readCompleted", "returnedRows": returned_rows}
        case DatabaseWriteCompleted(affected_rows):
            return {"outcome": "writeCompleted", "affectedRows": affected_rows}
        case DatabaseCallFailed(diagnostic):
            failed: dict[str, object] = {"outcome": "failed", "category": diagnostic.category}
            if diagnostic.failure.code is not None:
                failed["code"] = diagnostic.failure.code
            return failed
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _invocation(invocation: OuterInvocation | JoinedInvocation) -> dict[str, object]:
    match invocation:
        case OuterInvocation(concurrency=concurrency, retry_policy=policy):
            return {
                "invocation": "outer",
                "concurrency": concurrency,
                "retries": policy.retries,
                "retryOptimisticConflicts": policy.retry_optimistic_conflicts,
            }
        case JoinedInvocation():
            return {"invocation": "joined"}
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _invocation_outcome(
    outcome: OuterInvocationCommitted
    | OuterInvocationFailed
    | JoinedInvocationReturned
    | JoinedInvocationRaised,
) -> dict[str, object]:
    match outcome:
        case OuterInvocationCommitted():
            return {"outcome": "committed"}
        case OuterInvocationFailed(failure):
            return {"outcome": "failed", **_activity_failure(failure)}
        case JoinedInvocationReturned():
            return {"outcome": "returned"}
        case JoinedInvocationRaised(failure):
            return {"outcome": "raised", **_activity_failure(failure)}
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _attempt_failure(failure: AttemptFailure) -> dict[str, object]:
    return {
        "phase": _ATTEMPT_PHASE[failure.phase],
        "retryEligible": failure.retry_eligible,
        **_activity_failure(failure.failure),
    }


def _attempt_outcome(
    outcome: AttemptCommitted | AttemptRolledBack | AttemptRollbackFailed,
) -> dict[str, object]:
    match outcome:
        case AttemptCommitted():
            return {"outcome": "committed"}
        case AttemptRolledBack(failure):
            return {"outcome": "rolledBack", **_attempt_failure(failure)}
        case AttemptRollbackFailed(triggering, rollback):
            rolled: dict[str, object] = {
                "outcome": "rollbackFailed",
                **_attempt_failure(triggering),
            }
            if rollback.code is not None:
                rolled["rollbackCode"] = rollback.code
            return rolled
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _stream_outcome(
    outcome: StreamExhausted | StreamClosedEarly | StreamFailed,
) -> dict[str, object]:
    match outcome:
        case StreamExhausted():
            return {"outcome": "exhausted"}
        case StreamClosedEarly():
            return {"outcome": "closedEarly"}
        case StreamFailed(failure):
            return {"outcome": "failed", **_activity_failure(failure)}
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _stream_batch_outcome(
    outcome: StreamBatchCompleted | StreamBatchFailed,
) -> dict[str, object]:
    match outcome:
        case StreamBatchCompleted():
            return {"outcome": "completed"}
        case StreamBatchFailed(failure):
            return {"outcome": "failed", **_activity_failure(failure)}
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)
