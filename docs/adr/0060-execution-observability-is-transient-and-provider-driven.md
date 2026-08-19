# Execution observability is transient and provider-driven

Parallax exposes execution observability as a synchronous stream of immutable
Started and Finished events, not as provenance retained by results or active
transactions. A composition root accepts one Execution Lifecycle Provider. For
each outermost Handle operation, that Provider may open one fresh Handler whose
lifetime and serial event stream are confined to the resulting Root Execution.
Transactions, snapshots, streams, and return values retain no lifecycle record.

This supersedes ADR 0055. The retained Execution Log, Read Trace, Write Batch
Trace, Transaction Attempt record, Transaction Result wrapper, and their public
accessors are removed without compatibility aliases. An outer transaction
returns its callback value directly after commit. The database port reports a
closed ephemeral boundary outcome so composition can distinguish begin,
callback, commit, rollback, and rollback-failure outcomes without turning that
outcome into public provenance.

The event algebra brackets Reads, Write Batches, Database Calls, Transaction
Invocations, Transaction Attempts, Snapshot Streams, and Stream Batches. Each
activity has one Started event and one terminal Finished outcome, with per-root
execution, sequence, activity, and parent correlation. Failure events carry
bounded, detached diagnostics and causal activity IDs rather than live
exceptions. A failure is identified by its exception value rather than by the
raise that produced it, so a value re-raised past the descendant that produced
it still names that descendant; each activity holds one attribution, which is
what keeps the causal chain from growing with failures already completed. Exact
immutable Lowered Statements are borrowed during synchronous Database Call
delivery and must not be retained by handlers.

Provider opening is allowed to fail the operation because no execution effects
have begun. An ordinary Handler failure instead quarantines that handler for the
rest of the root, reports a detached Handler Error through its Provider, and
does not change query semantics. Fan-out opens Providers in declaration order,
shares each event object across active children, and quarantines a failing child
without hiding the event from later children. Re-entry through the originating
Handle or Transaction during lifecycle callbacks is refused.

The built-in logging integration writes detached structured records to an
application-configured Python logger and leaves queueing, sinks, flushing, and
shutdown to the application. Its safe mode omits SQL, binds, messages, and
stacks; a diagnostic mode adds only bounded detached failure text. The recorder
is testing-only and deliberately retains all events.

When no Provider is installed, the runtime branches before every
lifecycle-specific allocation and clock read; a shared immutable inert activity
may stand in for the activity seam, so that branch is one object rather than a
nullable at every observed site. With accepted concurrent roots,
core live memory is bounded by active Providers and activity depth, independent
of completed events, retries, stream length, and result cardinality. Production
fan-out shares one event object, keeps per-handler state bounded, and requires
application-owned asynchronous queues to be bounded. The Python implementation
must establish a reproducible baseline for three lightweight production-style
handlers and initially targets no more than 5 microseconds p95 Parallax-owned
dispatch per event, 5 percent p50 end-to-end overhead, and 10 percent p95
end-to-end overhead on the pinned runner. These are feature acceptance budgets
and a ratchet for later implementations, not a claim on the general benchmark
module or external exporter latency.

The language-neutral contract and six-case compatibility spine live in
`m-execution-lifecycle`. Language suites additionally prove opening, fan-out,
failure quarantine, re-entry, allocation, logging, recorder isolation, memory
retention, and the performance budgets above.
