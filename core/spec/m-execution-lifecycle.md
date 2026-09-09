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
defined by its kind. The nine kinds are:

- Read;
- Write Batch;
- Database Call;
- Transaction Invocation;
- Transaction Attempt;
- Snapshot Stream;
- Stream Batch;
- Acquisition;
- Release.

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

The event algebra is the closed union of these eighteen concrete transitions:

```text
ReadStarted                       ReadFinished
WriteBatchStarted                 WriteBatchFinished
DatabaseCallStarted               DatabaseCallFinished
TransactionInvocationStarted      TransactionInvocationFinished
TransactionAttemptStarted         TransactionAttemptFinished
SnapshotStreamStarted             SnapshotStreamFinished
StreamBatchStarted                StreamBatchFinished
AcquisitionStarted                AcquisitionFinished
ReleaseStarted                    ReleaseFinished
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
ReadStarted(target, interface, edition)
ReadFinished(ReadCompleted | ReadFailed(failure))
```

`interface` is `typed`, `wire`, or internal `rows`. A Read starts after public
preflight and any read-dependency Write Batch. It spans planning, lowering, all
of its Database Calls, conversion, materialization, and publication until the
public result is ready. It has no root-count or materialized-node count.
`edition` is the nonempty opaque token of the Model Edition a **standalone**
Read adopted for itself before it started, and is present exactly where the
Read is the root activity; a participating Read carries none, because the
Transaction Attempt it hangs under already stated the edition it inherits, and
the parent correlation is what relates the two.

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
Transaction begin, commit, and rollback are not Database Calls and count none,
and neither is whatever an adapter runs to open a boundary at a requested
Isolation Level: applying the level is part of opening the boundary, so it
belongs to the same demarcation the count already excludes.

Every statement-reaching operation belongs to exactly one Read, Write Batch, or
Stream Batch. A call is its direct child. No other activity kind owns a call.

## Transaction events

A **Transaction Invocation** is one call to callback demarcation. Its Started
transition carries exactly one invocation value:

```text
OuterInvocation(concurrency, retryPolicy, isolation)
JoinedInvocation()
```

`isolation` is the Isolation Level this invocation **requested**, in the
`m-db-port` portable vocabulary, and is **absent** when it requested none. It is
not the level the database used: a boundary naming none opens at whatever its
adapter defaults to, and that default is the adapter's own knowledge, so an
implementation MUST NOT infer or report it here. Every attempt of one invocation
opens at the same requested level, so the level belongs to the invocation and no
attempt restates it.

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

A **Transaction Attempt** begins after it has adopted the Model Edition it runs
under and before the database boundary is asked to begin. Its Started
transition carries exactly one attempt-specific field, `edition`: the nonempty
opaque token of the selection this attempt adopted, stated per attempt because
a retry adopts afresh and the attempts of one invocation may therefore carry
different editions. The invocation's own transitions carry none. Its Finished
transition is exactly one of:

```text
AttemptCommitted()
AttemptRolledBack(failure)
AttemptRollbackFailed(triggeringFailure, rollbackFailure)
AttemptBeginFailed(failure)
```

`AttemptBeginFailed` is the boundary that never opened: the callback did not
run, no child activity of the callback exists, and the outcome is terminal
without retry however retriable the error's own category is. It carries an
Activity Failure rather than an Attempt Failure, because there is no phase
inside the attempt to locate and no classifier verdict to report. Its
attribution is the ordinary rule rather than a fixed answer: the attempt's own
Acquisition is a child it may hold, so a boundary that never opened because no
connection was granted finishes `caused` naming that Acquisition, while one
that refused to open on a connection the attempt did acquire finishes `direct`.
Either way the invocation above finishes failed caused by that attempt under
the ordinary chaining rule. A successful begin continues within the same
attempt with no second Started transition.

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
2. One Transaction Attempt adopts an edition and starts.
3. The attempt acquires the connection its boundary will open on.
4. A begin failure — including an acquisition that granted none — finishes that
   attempt `beginFailed` and the invocation failed, caused by the attempt,
   without retry; the callback never runs.
5. Successful begin continues the same attempt: callback and pre-commit work
   run inside it.
6. Commit or rollback settles the attempt, which then releases its connection
   before finishing.
7. A retry starts another attempt under the same invocation, adopting afresh and
   acquiring afresh.
8. Commit or terminal failure finishes the invocation.

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
SnapshotStreamStarted(target, interface, batchSize, edition)
SnapshotStreamFinished(
    StreamExhausted
  | StreamClosedEarly
  | StreamFailed(failure))
```

`batchSize` is positive. `edition` is the nonempty opaque token of the Model
Edition a **standalone** stream adopted at context entry, retained through
every page, and is present exactly where the stream is the root activity; a
participating stream carries none, because the Transaction Attempt it hangs
under already stated the edition it inherits. Exhaustion finishes immediately when discovered. A
caller break, explicit close, caller exception, or cancellation before
exhaustion is Closed Early and does not rewrite caller control flow. Failed is
reserved for Parallax planning, database, conversion, materialization,
invalid-data, or resource-cleanup work that a delivery needed in order to
DELIVER. An ordinary problem met while RELEASING the connection a delivery held
after it ended is not one of them: the delivery is over, its roots stand, and a
cleanup fact is diagnostic rather than an outcome (`m-db-port`). Once exhausted,
a later caller error cannot rewrite the outcome.

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

## Resource events

An operation reaches the database through a connection it holds for its own
lifetime, and how long it held one is observable. Three activities own one: a
standalone Read, a Transaction Attempt, and a standalone Snapshot Stream — the
same three that adopt a Model Edition, because a connection and a selection are
held for exactly one operation (`m-db-port`). Each of them opens at most one
**Acquisition** and at most one **Release**, both as its own direct children:

```text
AcquisitionStarted()
AcquisitionFinished(durationNs, Acquired | AcquisitionFailed(reason, failure, cleanupResult))

ReleaseStarted()
ReleaseFinished(durationNs, holdDurationNs, cleanupResult)
```

They are SIBLINGS of the execution activities beside them rather than a lease
enclosing them. An eager Read's Database Calls stay its own direct children, an
attempt keeps its Reads, Write Batches, joined invocations, and streams, and a
standalone stream keeps its Stream Batches: what an operation asked the adapter
for is one more thing it did, not a scope the rest of it runs inside. Nothing
opens under an Acquisition or a Release, and no Read, Stream Batch, or Database
Call is duplicated to carry one.

The Acquisition is its owner's FIRST child and the Release its LAST. A
standalone Read acquires before its first statement; an attempt acquires before
its boundary is asked to begin, so an acquisition that granted nothing is the
begin failure above; a standalone stream acquires when it reads its first page,
before that page's Stream Batch opens, and releases where the delivery SETTLES
rather than where the caller leaves its scope. Work that INHERITS a connection
emits neither: a participating read, write batch, stream, or joined invocation
runs on the attempt's connection, and a stream's later pages run on the one its
first page took.

`reason` is the `m-db-port` acquisition-failure vocabulary — `timeout`,
`queue-rejected`, `closed`, `preparation-failed` — and is outside the
`m-db-error` categories, because no modeled statement ran to be classified.
`failure` is an ordinary Activity Failure and is always `direct`: an Acquisition
opens no child, so it has none to name. The owner holds it afterwards under the
ordinary Holding rule, which is what makes the owner's own failure `caused` by
it.

`cleanupResult` is the `m-db-port` cleanup outcome — `returned`, `invalidated`,
or `unrelinquished`, each with the finite conditions it met on the way. On a
failed Acquisition it is the partial cleanup that acquisition already ran over
whatever it had taken, and is absent where it owned nothing to clean up; it
rides there rather than on a Release because no hold was granted for a release
to end. A failed Acquisition therefore emits NO Release.

A cleanup fact never rewrites the outcome of the activity above it. A Read that
published, a stream that exhausted or closed early, and an attempt that
committed each keep what they established whatever the release ran into, and a
Release is never the cause named by another activity's failure. This is the
`m-db-port` rule that an ordinary post-execution cleanup problem is diagnostic
rather than an outcome, stated where the events state it.

`durationNs` follows the Database Call convention: monotonic elapsed time around
the resource call alone, with the activity's own Started and Finished deliveries
outside it. An Acquisition brackets asking the adapter for a connection and
getting an answer, the cleanup a failed acquisition runs included; a Release
brackets giving it back. `holdDurationNs` spans the whole exclusive use, from
the moment the acquisition call answered to the moment the release completed, so
it includes the Acquisition Finished delivery, every Handler that ran during the
operation, and any pause a stream's consumer took. These measure
composition-level calls: none of them claims exact physical occupancy, pure
adapter time, or anything the adapter finishes in the background afterwards.

Acquisition and release still happen where no Provider is installed, where one
declined, and after a Handler was quarantined — resource handling is execution
rather than observation. What does not happen there is the observation: no
event, no Activity ID, and no lifecycle clock read. The one thing an
implementation still reports without a Provider is a cleanup fact no Handler
received, which reaches the restricted failure-only resource log described
below.

## Pool observation is registered once and belongs to no root

Every event above describes ONE operation. A pool describes none of them —
capacity, idleness, and queue depth belong to the resource the operations share
— so an interest in it is REGISTERED at composition rather than delivered as
events to a Handler that would have to be retained for a root that never ends.

The seam is the Provider already named at composition. A Provider that also
implements the optional **pool observation** method is offered the runtime's
Pool Metrics Source (`m-db-port`) once, before the connected handle is
published, and answers with a **Pool Observation** — a registration whose only
verb is closing it — or with nothing, which declines. Implementing the method is
the whole declaration of interest: there is no capability flag and no second
composition argument.

Both halves are required and neither is inferred. A runtime that publishes no
source offers nothing to any Provider, and a Provider that does not implement
the method is asked nothing. Interest in the pool is INDEPENDENT of accepting
roots: a Provider may decline every root and observe the pool, or accept every
root and ignore it.

```text
compose
  prepare model -> open ready runtime
  offer the source to an interested provider -> registration or decline
  publish the handle

close
  close the runtime, which detaches the source
  then close every registration, whatever the close before it did
```

Registration happens BEFORE publication, so a registration that fails ordinarily
fails the composition: no handle is published, the runtime that was opened is
closed, and the exception keeps its own identity rather than being wrapped or
reinterpreted as a decline. Where several Providers are composed, the ones that
already registered are closed on the way out — a registration nobody holds could
never be closed — and every one of those closes is attempted.

The handle owns the REGISTRATION and nothing behind it. Closing gives the
interest up; it never closes the exporter, queue, or client the application
built, which outlive the handle. Closing the runtime comes first, because the
runtime is what the interest was in, and the registrations are closed afterwards
in every case, including one where closing the runtime itself failed. An
ordinary failure to close a registration is contained and reaches the restricted
failure-only resource log, which states that a registration would not close and
nothing about why: what raised is application code holding application state.

Sampling itself is the reader's, on its own cadence, and is described by
`m-db-port`. Nothing here polls, schedules, caches a reading, or retains a
sample: an interest is a lifetime, not a channel.

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

An event carrying a cleanup fact — a failed Acquisition's partial cleanup, and
every Release — additionally has a **delivery completion**: whether at least one
Handler RETURNED from receiving it. A Handler that accepted the root, a delivery
that was merely attempted, and a Fan-out that contained every one of its
children's failures and then returned are each NOT a completion. A cleanup fact
carrying at least one issue and completed by no Handler reaches the
implementation's restricted failure-only resource log instead, which states the
cleanup phase and code and fixed explanatory text and nothing else
(`m-db-port`). Reporting it in both places would report it twice, and in neither
would lose it, so exactly one of the two happens. That log stays failure-only,
so a cleanup that met no issue and reached no Handler is reported nowhere: the
fallback exists to keep a problem from being lost, and a cleanup with nothing to
say loses nothing by being unrecorded. A normal return acknowledges DELIVERY
rather than durable export: a
Handler that exports and then raises may cause duplicate reporting elsewhere,
which is the Handler's own trade.

An **Execution Lifecycle Fan-out** is an ordered, nonempty list of Providers. It
opens children in declaration order, omits deliberate declines, and declines if
all children decline. A child open failure aborts the root and discards handlers
already opened for it. Events are delivered in declaration order. One child's
ordinary failure quarantines only that child; later siblings receive that event
and future events. A composition whose every leaf has been quarantined leaves
the Root Execution with no Handler at all, and it is quarantined with them:
what follows takes no Activity ID, delivers no event, and reads no lifecycle
clock. A child that is itself a Fan-out contributes its own children
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
decline it has the same event-, counter-, diagnostic-, and clock-free path. The
resource clocks are lifecycle clocks and follow that rule: an unobserved
operation acquires and releases without reading one, and the deadline clocks
resource management needs for its own budgets are independent of observation and
are taken either way. The restricted resource log is the one deliberate
exception, and a failure-only one: it speaks where a cleanup fact reached no
Handler and stays silent on every path where nothing went wrong.

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

This module owns ten cases:

| Case | Observable distinction |
|---|---|
| standalone read | one Read brackets its Acquisition, its Database Call, and its Release outside a transaction |
| pre-commit batch | one nonempty boundary batch brackets two ordered writes |
| read dependency | the dependency batch finishes before its sibling Read starts |
| retry then commit | one invocation contains a rolled-back attempt and a later committed attempt, each acquiring and releasing its own connection, and the first releases before the second acquires; zero-row enforcement is attributed to the completed call |
| retry exhaustion | every failed call, batch, and attempt finishes before the next attempt; classifier truth remains retry-eligible when the budget ends |
| joined invocation | the joined activity has no attempt of its own and no Acquisition, and its buffered write reaches the outer attempt's pre-commit batch |
| streamed delivery | a Snapshot Stream root acquires once before its first page, brackets one Stream Batch per page, each page's Database Calls are that batch's own, and it releases where the delivery finishes exhausted |
| isolation setup failure | the attempt that adopted its edition starts before the boundary is asked to begin, acquires a connection, finishes `beginFailed` `direct` with no callback and no retry, and releases what it took; the invocation finishes failed caused by it |
| acquisition failure | the attempt's Acquisition grants nothing, carries the partial cleanup it ran and is followed by no Release, and the attempt finishes `beginFailed` caused by it |
| cleanup after commit | a Release reporting an unrelinquished connection leaves the attempt committed and the invocation committed |

Every Started transition of an adoption-owning activity in those cases — a
standalone Read, a standalone Snapshot Stream, and every Transaction Attempt —
asserts the literal edition the conformance adapter prepared the case's model
under (`m-conformance-adapter`); a Read or stream under an attempt asserts none.

The compatibility harness validates oracle shape and correlation but observes no
execution of its own. Each language grades the oracle through its conformance
adapter and proves Provider, Handler, fan-out, re-entry, quarantine, logger,
recorder, allocation, and performance obligations through its idiomatic API and
internal-seam suites.
