# Transactions retain production execution logs across retries

The core `m-execution-log` module owns the language-neutral production record
from an actual Database Call through a transaction's retry-spanning result. One
logical transaction invocation owns one Execution Log spanning
all of its physical Transaction Attempts. Each attempt retains ordered Read
Traces and Write Batch Traces made of actual Database Calls and has a live,
committed, or rolled-back status. A rolled-back attempt also retains a detached
Attempt Failure so a completed zero-row write, planning failure, body failure,
or commit failure remains diagnosable without retaining its exception or
traceback. The read-only log is visible from the active Transaction, seals when
the invocation terminates, and may outlive that Transaction. A successful
Transaction Result exposes the committed attempt as its common execution view
and the whole Execution Log separately; a joined result shares the outer
transaction's log and therefore describes the whole physical transaction rather
than a fictitious nested boundary.

The module is a composition-level observer with direct behavioral dependencies
on `m-sql`, `m-db-port`, `m-db-error`, `m-unit-work`, and `m-auto-retry` for the
Lowered Statement, call boundary, failure diagnostic, transaction/write-batch,
and retry semantics it records. `m-snapshot-read` depends on it to expose Read
Trace, while the transaction and retry modules do not depend back on
observation; language composition roots coordinate them. The resulting graph
remains acyclic and the execution vocabulary stays in the common runtime rather
than depending on a snapshot lifecycle.

The log retains one immutable Retry Policy snapshot containing the effective
maximum re-execution count and optimistic-conflict retry opt-in after defaults
and outer-transaction inheritance are resolved. It does not retain whether an
option was explicit or defaulted. Together with each failure's
`retry_eligible` value and the ordered attempts, that snapshot explains a
missing successor without duplicating policy on every attempt. The log also
retains the resolved Locking or Optimistic Concurrency Preference once. That
preference combines with each Entity's Optimistic Lock Facet to explain its
effective read-lock and write-gate behavior; it does not assert that one strategy
governed the whole transaction. Like the retry policy, it records the resolved
value rather than whether the caller supplied it explicitly.

The runtime records one lightweight value per database round trip and shares a
read's trace with its Snapshot instead of constructing a second record. It does
not retain Write Plans or add work proportional to materialized domain nodes or
attributes. A Database Call records both completed and failed round trips
through a closed completion value and owns the exact immutable
`LoweredStatement` used for execution without copying its binds. This is the
canonical dialect value emitted by lowering before an adapter converts
placeholders or bind containers for its driver; that conversion remains
unrecorded adapter detail.
Retaining a log therefore retains and exposes any sensitive domain values in
those binds. A failed call's diagnostic is detached from the raised exception
so the log retains no traceback or transaction state. Round-trip counts include
every attempted Database Call, including one that fails, but exclude transaction
begin, commit, and rollback operations; attempt status and failure record those
boundary outcomes. This bounded observability cost is preferred to a public
manual flush, an opt-in
mutable recorder, or conformance-owned database-port capture: those
alternatives respectively expose physical write timing, add retry and failure
boilerplate, or duplicate production execution semantics.

The incremental production cost is linear only in physical Transaction Attempts
and Database Calls and is constant with respect to materialized result
cardinality. The typed path constructs no neutral rows, nodes, views,
relationship wrappers, or copied bind collections. Verification uses structural
and allocation-focused regression tests rather than a wall-clock threshold.

Typed Snapshots and Neutral Read Results both expose their Read Trace directly.
When either read participates in a transaction, its result and the current
Transaction Attempt reference the exact same trace object; there is no result
wrapper around the trace and no duplicate transaction record.

The Python surface replaces the existing public `Execution` and
`ExecutedStatement` names with Read Trace and Database Call without aliases.
The new completion and transaction semantics are materially different, so an
alias would promise compatibility it cannot provide and would preserve the
ambiguous vocabulary this decision removes.

Python canonically defines the generic types in
`parallax.core.execution_log`. `parallax.snapshot.handle` re-exports the
developer-facing Read Trace, Database Call, Execution Log, Transaction Attempt,
and Transaction Result types beside Database and Transaction; completion
variants, policy, and diagnostic types remain available from their canonical
core module. This preserves one implementation owner without making common API
annotations inconvenient.

The same read-only log object remains stable for the invocation. Each attempt
appears as Active before its body runs; traces are appended only after their
read or write batch succeeds or raises, and no partially built Database Call is
observable. Attempt status then transitions to Committed or Rolled Back. The
complete graph seals after the outer invocation terminates, avoiding replacement
snapshots while keeping every published leaf complete.

The log's Final Attempt accessor always returns its current or latest attempt;
its Committed Attempt accessor returns none until and unless an attempt commits.
Transaction Result's common execution accessor is stricter: it returns that
committed attempt, is unavailable while a joined outer transaction is active,
and remains unavailable if that outer transaction later rolls back. Languages
surface distinct in-progress and not-committed errors for those two joined-result
states.

Every Database Call also records monotonic elapsed duration measured only
around the port invocation, including when that invocation fails. Python stores
this as integer `duration_ns` from its monotonic performance counter, avoiding
an additional duration object and making the unit explicit; the clock's actual
resolution may be coarser. Duration is informational and cannot affect
execution or conformance; wall-clock start and end timestamps are not retained.

Its closed completion algebra records `ReadCompleted` with the physical number
of rows returned by that statement, `WriteCompleted` with the affected-row
count, or `DatabaseCallFailed` with its detached database diagnostic. A read's
physical row count is not a count of result roots, unique graph nodes, or
projection views. Each call separately retains a Read or Write kind so a failed
call remains classifiable without parsing SQL: Read admits Read Completed or
Database Call Failed, while Write admits Write Completed or Database Call
Failed.

Each Database Call is stored exactly once inside its Read Trace or Write Batch
Trace. An attempt's flattened call traversal is a read-only projection over its
ordered traces, not a second collection of call references; its round-trip
count may be maintained as a scalar. Convenience access therefore adds no work
or storage proportional to the number of calls.

The collection vocabulary follows the hierarchy: Read Trace and Write Batch
Trace expose `calls`; Transaction Attempt exposes `traces` plus a derived
flattened `calls` projection; Execution Log exposes `attempts`. Each level also
exposes `round_trips`. Database Call exposes its exact `statement` and closed
`completion`, keeping Lowered Statement for the executable value and Call for
the attempt that reached the port. Python keeps the property name `statement`
while typing it as `LoweredStatement`.

Read Traces and Write Batch Traces prove work that reached the database, so
each contains at least one Database Call. Planning or compilation that fails
before its first call creates no empty trace; the Transaction Attempt's Attempt
Failure records that pre-execution failure instead.

A Write Batch Trace records a closed trigger of Read Dependency or
Finalization. A dependency-triggered batch appears immediately before the Read
Trace it enabled; the final buffered batch is marked Finalization. This exposes
causality without creating a public flush operation.

Attempt Failure classifies the failure under a small, stable phase algebra:
Body covers callback work, explicit reads, and read-forced write batches;
Finalization covers the boundary-owned final write batch; Commit covers the
durability boundary. These phases locate failures that have no Database Call
without exposing language-specific stack locations or internal planner stages.
The detached diagnostic carries that phase, an implementation-level error type
name, a human-readable message, an optional stable Parallax or provider code,
and a `retry_eligible` flag. Retry eligibility is the result of failure
classification under the invocation's effective policy, including its
optimistic-conflict opt-in, but is independent of the remaining retry budget
and does not claim that another attempt occurred. It is diagnostic rather than
a portable error algebra, so it can represent arbitrary callback failures
without retaining their exception objects. When a failed port call or
enforcement of a completed call caused the attempt failure, the diagnostic
references that existing Database Call without copying it; planning, arbitrary
callback, and commit failures carry no call reference.

This decision does not standardize failures of the database adapter's own begin
or rollback operations. The Execution Log starts once the port has opened an
attempt and invoked the transaction body; a begin failure therefore exposes no
Transaction from which to obtain a log. Richer demarcation diagnostics would
require outcome states beyond Active, Committed, and Rolled Back and remain a
separate observability concern.

Standalone read failures also do not introduce an execution-bearing exception
hierarchy. A successful standalone read carries its Read Trace; a failed
transactional read remains observable through the retained Execution Log. The
conformance adapter may consume the production executor's same internal trace
recorder while translating a standalone failure, but does not own a second
database-port capture path or expose that recorder publicly.

`m-execution-log` is cases-covered through a dedicated, module-owned
compatibility spine rather than relying only on cases owned by other functional
modules. Seven named cases cover standalone Read Trace, committed finalization,
read-dependency ordering, retry then commit, retry exhaustion, zero-row
enforcement after a completed call, and joined live-to-sealed behavior. They
reuse existing models and seeded data. A small `then.execution` oracle states
attempt, trace, call, and completion structure while existing `then.statements`
and `then.roundTrips` remain the sole SQL, bind, and count oracles; the execution
shape is a case assertion format, not a public serialization contract.

That oracle is a closed union containing exactly one explicit `readTrace` or
`transactionLog` wrapper. Calls reference the case's flattened authored golden
statement order by index rather than repeating SQL or binds; a failure's
`databaseCall` index is local to its attempt's flattened calls. The oracle
authors stable kinds, statuses, triggers, completion facts, policy values, and
portable diagnostics. Exact duration and implementation-specific error type
names are omitted and checked only against their general API contracts.

Runtime conformance accounting consumes production provenance as its sole
source. Successful reads derive emissions and round trips from Read Trace;
transactional writes and scenarios derive them from Execution Log, including
all attempted calls across retries. Compile-only conformance continues to
inspect produced Lowered Statements because no call occurred, and the internal
recorder above remains the standalone failure bridge. Capture-only conformance
database port wrappers are removed.
