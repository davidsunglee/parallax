# m-execution-lifecycle — Transient Execution Observability

`m-execution-lifecycle` specifies the transient, synchronous lifecycle of work
performed through a Parallax Handle. It replaces retained execution history with
a composition-level Provider that may open one fresh Handler for each accepted
Root Execution. The Handler receives a closed stream of immutable Started and
Finished events while execution proceeds; results, snapshots, streams, and
transactions retain no lifecycle record.

The module depends on `m-sql` for the Lowered Statement a database call executes,
`m-db-port` for call and transaction outcomes, `m-db-error` for neutral database
failure facts, `m-unit-work` for transaction and write-batch semantics, and
`m-auto-retry` for retry policy and classification. A composition root threads
the lifecycle publisher down to the observed modules. None of those modules
discovers a provider or records history for this module.

## Root execution and opening

A **Root Execution** is one outermost Handle operation and everything it causally
contains. Its immutable descriptor carries exactly:

- `id` — a random UUIDv4 whose equality and canonical text are meaningful;
- `kind` — `read`, `transaction-invocation`, or `snapshot-stream`.

Concurrent outermost operations are distinct roots. One outer transaction root
contains every retry, joined invocation, read, write batch, database call, and
transactional stream it causes. A standalone read or stream owns its own root.

Deterministic public preflight precedes Root Execution creation. Invalid
arguments, invalid query shape, an invalid target, incompatible transaction
options, or invalid stream context use therefore create no root, call no
Provider, and emit no events. Planning, lowering, database work, conversion, and
materialization happen after the root activity starts and are observable.

The composition root MAY install one **Execution Lifecycle Provider**. For each
accepted public operation:

1. the runtime allocates the Root Execution descriptor;
2. it synchronously asks the Provider to `open` that descriptor;
3. `None` deliberately declines the root and disables all further lifecycle
   work for it;
4. a Handler accepts the root and immediately receives its root Started event.

Provider opening happens before execution state, clocks, or database work. An
ordinary opening failure aborts the operation through a language-idiomatic
Provider Error preserving the original cause; it is never reinterpreted as a
decline. Language-native control-flow and fatal exceptions propagate unchanged.

Provider methods may run concurrently for different roots. Each accepted root
gets a distinct Handler; a Handler is invoked synchronously and serially for its
one root. Shared configuration and exporters therefore belong to the Provider
and must be concurrency-safe, while per-root counters and correlation state
belong to the Handler.

## Activities, correlation, and delivery

An **Execution Activity** starts once and finishes once with a terminal outcome
defined by its kind. The seven kinds are:

- Read;
- Write Batch;
- Database Call;
- Transaction Invocation;
- Transaction Attempt;
- Snapshot Stream;
- Stream Batch.

Every event carries this correlation envelope:

| Field | Contract |
|---|---|
| `executionId` | the root's UUIDv4 |
| `sequence` | positive, contiguous, one-based delivery position within the root |
| `activityId` | positive, contiguous, one-based ID assigned by Started and reused by its Finished peer |
| `parentActivityId` | absent only for the root activity; otherwise an earlier-started activity in the same root |

Concurrent roots have independent sequences and imply no global order. The
sequence is assigned immediately before delivery. Fan-out children receive the
same event object with the same sequence; delivery does not clone an event per
child.

The event algebra is the closed union of these fourteen concrete transitions:

```text
ReadStarted                       ReadFinished
WriteBatchStarted                 WriteBatchFinished
DatabaseCallStarted               DatabaseCallFinished
TransactionInvocationStarted      TransactionInvocationFinished
TransactionAttemptStarted         TransactionAttemptFinished
SnapshotStreamStarted             SnapshotStreamFinished
StreamBatchStarted                StreamBatchFinished
```

`ActivityStarted` and `ActivityFinished` are parent interfaces or unions, not
constructible kind-plus-payload records. Every concrete transition admits only
its own fields. There is no generic attribute bag and no callback return value.

## Failure values

A **Failure Diagnostic** is a total, detached, deeply immutable projection of an
exception. It contains:

- the fully qualified runtime type name;
- a best-effort human-readable message, limited to 8 KiB of UTF-8 text;
- an optional safely readable string-valued `code`;
- a rendered chained stack trace without locals, limited to 64 KiB of UTF-8
  text;
- independent message- and stack-truncated flags.

Truncation preserves code-point boundaries. Extracting or formatting a field
MUST NOT replace the original execution error, even when that extraction raises
a control-flow or fatal exception. The diagnostic retains no exception,
traceback graph, cause object, local, transaction state, statement, or bind.
Because the projection is detached and immutable, a failure reports a
diagnostic already rendered for its own value rather than copying its bounded
strings: the one the activity's attribution carries, or — for an activity
holding no attribution for that value — the one its parent holds for it when
that attribution names a child with a HIGHER Activity ID, which is exactly a
child that started inside this activity and unwound out through it. An activity
with neither renders its own.

An **Activity Failure** is exactly one of:

- `DirectFailure(diagnostic)` — the activity holds no attribution for this
  failure, so it is the activity's own;
- `CausedFailure(diagnostic, causeActivityId)` — it holds one, and
  `causeActivityId` is the child that attribution names.

The two arms are one rule over one input, because a **failure is an exception
value**: the same value is the same failure wherever it surfaces, however many
times it is raised. An activity holds at most one **attribution**, pairing one
value with one of its own DIRECT children — an activity whose `parentActivityId`
is this one's. A direct child reports a value to its parent by finishing failed
with it, and an explicit enforcement relation reports an already-finished child
for the value the enforcement itself raised — never temporal proximity. A
completed zero-row write call may therefore cause a Write Batch failure even
though the call itself completed successfully.

Three rules fix the answer for every implementation. Each speaks only of the
attribution an activity holds at the moment it is asked; a value it does not
hold then takes no part in any of them, however recently it was held.

- **Holding.** A report of a value other than the one held replaces the
  attribution outright, dropping the value and the child it paired. A report of
  the value already held replaces only the child named, and only when the new
  report's Activity ID is HIGHER. So where several direct children report one
  value with no report of a different value in between, `causeActivityId` is
  the HIGHEST of their Activity IDs: among children of one parent, a child
  reporting later but started earlier can only be a scope the value unwound out
  through, so the higher ID is the more specific child. A report of a different
  value ends that run of reports — the children that reported before it stop
  being candidates, and the next report of the dropped value starts a fresh run
  that can only name a child reporting from then on. One slot rather than a map
  is what keeps live memory independent of failures already completed.
- **Answering.** An activity failing with a value reports `CausedFailure` naming
  the child of the attribution it holds for that value, and `DirectFailure`
  otherwise. Whether the value unwound out of that child continuously or a
  handler in between caught it and raised it again makes no difference: a caller
  that catches a child's failure, does further work, and re-raises it still
  reports that child, so long as no different value was reported in between.
- **Chaining.** An activity that finishes failed reports the value of its own
  Activity Failure to its parent under its own Activity ID, whichever arm it
  answered with. Each level therefore names its direct child rather than the
  deepest activity beneath it, and a consumer walks a cause one link at a time.

Identifying a failure by value gives up the OCCURRENCE: while an activity holds
a value's attribution, failing with that value reports Caused naming the child
held, even when the raise is the activity's own and the child's occurrence was
handled long before. Telling occurrences apart would require observing every
raise and every handler, which this module's cost bound refuses, and would take
the cause away from the ordinary catch-and-re-raise too. Holding one attribution
gives up the converse case: a value stashed past a different child's failure
reports Direct when it is finally raised, because that different value evicted
the attribution that would have named its child.

A failed Database Call carries a **Database Failure Diagnostic** containing its
Failure Diagnostic plus the existing `m-db-error` Category or `None` and native
code or `None`. Those two database facts are copied directly from Database Error
and are never reclassified. An unexpected non-Database Error escaping the port
uses `None` for both.

## Read, write-batch, and database-call events

The read transitions are:

```text
ReadStarted(target, interface)
ReadFinished(ReadCompleted | ReadFailed(failure))
```

`interface` is `typed`, `wire`, or internal `rows`. A Read starts after public
preflight and any read-dependency Write Batch. It spans planning, lowering, all
of its Database Calls, conversion, materialization, and publication until the
public result is ready. It has no root-count or materialized-node count.

The write-batch transitions are:

```text
WriteBatchStarted(trigger)
WriteBatchFinished(WriteBatchCompleted | WriteBatchFailed(failure))
```

`trigger` is `read-dependency` or `pre-commit`. A Write Batch exists only for a
nonempty unit-of-work buffer and starts before planning. It spans planning,
lowering, every Database Call, and affected-row enforcement. It completes even
when planning reduces the batch to zero DML. An empty read dependency or
pre-commit boundary emits no Write Batch. A dependency batch and the Read it
enables are siblings in that order under their current Transaction Attempt.

The database-call transitions are:

```text
DatabaseCallStarted(target, kind, statement)
DatabaseCallFinished(statement, durationNs,
    DatabaseReadCompleted(returnedRows)
  | DatabaseWriteCompleted(affectedRows)
  | DatabaseCallFailed(diagnostic))
```

`kind` is `read` or `write`. `statement` is the exact deeply immutable Lowered
Statement presented to the port and is repeated on Finished. It is borrowed for
synchronous delivery: core does not copy its text or binds, and a Handler must
not retain it. `durationNs` is monotonic elapsed time around the port invocation
alone; Handler time is outside it. A failed call still counts one round trip.
Transaction begin, commit, and rollback are not Database Calls and count none.

Every statement-reaching operation belongs to exactly one Read, Write Batch, or
Stream Batch. A call is its direct child. No other activity kind owns a call.

## Transaction events

A **Transaction Invocation** is one call to callback demarcation. Its Started
transition carries exactly one invocation value:

```text
OuterInvocation(concurrency, retryPolicy)
JoinedInvocation()
```

An Outer Invocation is the root activity. It spans every physical attempt and
finishes exactly once as:

```text
OuterInvocationCommitted()
OuterInvocationFailed(failure)
```

A Joined Invocation is a child of the current Transaction Attempt. It shares
the outer root, sequence, unit of work, and transaction; creates no Transaction
Attempt; and finishes as:

```text
JoinedInvocationReturned()
JoinedInvocationRaised(failure)
```

Returning and raising describe the nested callback only. They never claim that
the physical transaction committed or rolled back.

A **Transaction Attempt** begins only after the database boundary has begun
successfully. Its Started transition carries no attempt-specific fields and its
Finished transition is exactly one of:

```text
AttemptCommitted()
AttemptRolledBack(failure)
AttemptRollbackFailed(triggeringFailure, rollbackFailure)
```

`failure` and `triggeringFailure` are **Attempt Failures** containing:

| Field | Contract |
|---|---|
| `phase` | `callback`, `pre-commit`, or `commit` |
| `failure` | Direct or Caused Activity Failure |
| `retryEligible` | classifier verdict under the effective policy, independent of remaining budget |

`callback` includes the callback, joined invocations, reads, and
read-dependency batches. `pre-commit` is the final automatic nonempty Write
Batch after the callback returns. `commit` is the durability call.

The transaction topology is:

1. Outer Invocation starts.
2. A begin failure finishes the invocation with a direct, non-retryable failure;
   no Transaction Attempt exists and the callback never runs.
3. Successful begin starts one Transaction Attempt.
4. Callback and pre-commit work run inside that attempt.
5. Commit or rollback finishes the attempt.
6. A retry starts another attempt under the same invocation.
7. Commit or terminal failure finishes the invocation.

Rollback failure preserves both diagnostics. An ordinary triggering error plus
rollback failure surfaces through a language-idiomatic Transaction Rollback
Error exposing both live errors and chaining the rollback error. If rollback
succeeds, the triggering error propagates unchanged. A control-flow or fatal
trigger remains primary and attaches rollback failure using the language's
native chaining mechanism. Rollback failure never retries and requires the
uncertain connection to be discarded, even when the triggering failure was
retry-eligible.

The database port reports one closed ephemeral transaction-boundary outcome:

```text
Committed(value)
BeginFailed(error)
RolledBack(CallbackRaised(error) | CommitFailed(error))
RollbackFailed(CallbackRaised(error) | CommitFailed(error), rollbackError)
```

Composition consumes this outcome immediately to drive lifecycle events and
public control flow. It is neither a public transaction return value nor
retained provenance. A transaction invocation returns the callback's value
directly only after outer commit; a joined invocation returns the nested
callback's value inside the still-active outer transaction.

## Snapshot-stream events

A standalone Snapshot Stream is a root; a transactional stream is a child of
the current Transaction Attempt. Construction alone emits nothing. The stream
starts only after successful context entry and finishes exactly once as:

```text
SnapshotStreamStarted(target, interface, batchSize)
SnapshotStreamFinished(
    StreamExhausted
  | StreamClosedEarly
  | StreamFailed(failure))
```

`batchSize` is positive. Exhaustion finishes immediately when discovered. A
caller break, explicit close, caller exception, or cancellation before
exhaustion is Closed Early and does not rewrite caller control flow. Failed is
reserved for Parallax planning, database, conversion, materialization,
invalid-data, or resource-cleanup work. Once exhausted, a later caller error
cannot rewrite the outcome.

Each requested page is a **Stream Batch**:

```text
StreamBatchStarted()
StreamBatchFinished(StreamBatchCompleted | StreamBatchFailed(failure))
```

It starts after any read-dependency Write Batch and before page planning. Its
Database Calls are direct children; it spans conversion and completes once the
page's converted result — the one shared input every root of that page is
published from — is ready, including a page that returned no root at all. Materializing and
publishing those roots runs one root at a time under the parent Snapshot Stream,
outside every batch, so a per-root materialization or invalid-data failure
reaches a batch that already finished Completed and is attributed to the
Snapshot Stream directly rather than to that batch. Caller processing happens
after batch completion. A failed batch finishes before the stream fails and is
the stream failure's cause. Stream Batch is the page-read activity; it never
nests a duplicate Read activity.

## Handler failures, re-entry, and fan-out

A Handler ordinary exception quarantines that Handler for the remainder of its
Root Execution and does not change execution semantics. The owning Provider is
called out of band with one detached **Handler Error** carrying the Root
Execution ID, Event Sequence, Activity ID, qualified handler type, nested
fan-out path, and Failure Diagnostic. It carries no event, statement, or binds.
The Provider's reporting method may be called concurrently.

An ordinary reporting failure is best effort and never changes execution. A
language defines one recursion-proof last-resort diagnostic path and silently
drops the report if that path is unavailable. A control-flow or fatal exception
from event delivery or reporting aborts the root, disables further lifecycle
delivery for it, runs required database cleanup without further events, and
propagates unchanged. It produces no Handler Error report.

Provider opening, event delivery, and error reporting are **lifecycle contexts**.
Calling an operation through the originating Handle or Transaction from one of
those contexts is Execution Lifecycle Re-entry. It is refused before execution
state, clocks, or database work. Re-entry during opening becomes the Provider
Error's cause; re-entry escaping a Handler is an ordinary handler failure and
causes quarantine. Unrelated handles remain usable.

An **Execution Lifecycle Fan-out** is an ordered, nonempty list of Providers. It
opens children in declaration order, omits deliberate declines, and declines if
all children decline. A child open failure aborts the root and discards handlers
already opened for it. Events are delivered in declaration order. One child's
ordinary failure quarantines only that child; later siblings receive that event
and future events. A child that is itself a Fan-out contributes its own children
to one composition tree, and every rule here reads over that flattened tree
rather than over one list of siblings: construction rejects the same Provider
object more than once anywhere in the tree, while distinct Providers may
deliberately share a backend.

## Cost and retention

With no installed Provider, a runtime MUST branch before all lifecycle-specific
work: no UUID, descriptor, publisher, Handler, event, outcome, diagnostic,
counter, or lifecycle clock is created, and no allocation, clock read, or I/O
occurs. A shared immutable inert activity MAY stand in for the activity seam.
A declining Provider costs only the UUID, descriptor, and opening call; after
decline it has the same event-, counter-, diagnostic-, and clock-free path.

With `N` concurrent accepted roots, `P` active Providers, and maximum activity
depth `D`, core live lifecycle memory is `O(N × (P + D))` and independent of
events already completed, retry count, stream length, result cardinality, and
materialized graph size. Core constructs one transient event per transition and
shares it across fan-out. Built-in non-recording handlers retain only bounded
per-root state; asynchronous exporters use application-owned bounded queues.
Delivery work is `O(events × active providers)`. A custom Handler that retains
borrowed events or uses unbounded state violates the Handler contract.

## Portable lifecycle oracle

The compatibility oracle is `then.executionLifecycle` (`m-case-format`). It
contains a `roots` list of normalized Root Executions, each with a positive
first-observation index, kind, and ordered events. A portable event retains sequence, activity,
parent, transition, outcome, stable code, database category, physical row
counts, retry classification, and statement indexes. It omits UUIDs, monotonic
durations, implementation type names, messages, stack traces, and native codes.

A Database Call transition names its statement by zero-based index into the
case's flattened golden statement order. Two calls name none: every call on an
`api-conformance` lane, which authors no golden SQL, and a resolving read a
keyed write owes, which reaches the database and is counted while the case
authors no golden for it (`m-case-format`). The indexes the remaining calls
name are that order exactly, in delivery order and once each, and each index is
named by a call of the kind its own statement is: a query by a read, DML by a
write. The adapter observation uses the identical shape and indexes its own
emissions. The shape is a case assertion format, not a public serialization
contract.

This module owns seven cases:

| Case | Observable distinction |
|---|---|
| standalone read | one Read brackets its Database Call outside a transaction |
| pre-commit batch | one nonempty boundary batch brackets two ordered writes |
| read dependency | the dependency batch finishes before its sibling Read starts |
| retry then commit | one invocation contains a rolled-back attempt and a later committed attempt; zero-row enforcement is attributed to the completed call |
| retry exhaustion | every failed call, batch, and attempt finishes before the next attempt; classifier truth remains retry-eligible when the budget ends |
| joined invocation | the joined activity has no attempt and its buffered write reaches the outer attempt's pre-commit batch |
| streamed delivery | a Snapshot Stream root brackets one Stream Batch per page, each page's Database Calls are that batch's own, and the delivery finishes exhausted |

The compatibility harness validates oracle shape and correlation but observes no
execution of its own. Each language grades the oracle through its conformance
adapter and proves Provider, Handler, fan-out, re-entry, quarantine, logger,
recorder, allocation, and performance obligations through its idiomatic API and
internal-seam suites.
