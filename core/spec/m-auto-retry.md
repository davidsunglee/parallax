# m-auto-retry — Bounded Retry on Transient Conflict

`m-auto-retry` is the unit-of-work boundary's **bounded automatic retry** loop.
Per the dependency graph, `m-auto-retry` depends on `m-unit-work` (the boundary it
wraps) and `m-db-error` (the neutral error categories that decide retriability).

## Bounded automatic retry

The unit-of-work boundary **MUST** offer **bounded automatic retry**. On a
**retriable** failure of the closure the boundary **MUST**:

1. **roll back** the failed attempt's atomic scope (the `m-unit-work` abort
   contract erases its writes — buffered, force-flushed, or cached);
2. **invalidate stale cached state** so the re-execution observes fresh state —
   the retry re-reads, it does not replay a stale in-memory shadow;
3. **re-execute the closure** against that fresh state, inside a new atomic scope.

The bound is **configurable** per boundary; an omitted bound resolves as
`m-execution` *Option resolution* states, and a root's built-in bound is **10**
re-executions. A bound of **`0` disables** the loop, so even a
retriable failure surfaces to the caller after the first attempt. A retry that
**exhausts** the bound surfaces the failure to the caller (diagnosably — the
surfaced error carries the attempt count). This mirrors Reladomo's
`MithraManager.executeTransactionalCommand` retry loop (`TransactionStyle`
default 10), with the default owned by the root rather than by each call.

Which failures are retriable is fixed policy rather than an option. Together
they are the **recoverable conflicts**: a failure a re-execution against fresh
state can resolve.

- **Transient database failures** — deadlock and serialization failure (the
  `m-db-error` `deadlock` category).
- An **Optimistic Lock Conflict Error** — a gate an observation of the attempt
  bound came up short because a concurrent writer moved the row first.
- Either one carried as the cause of the rollback-only refusal a caught failure
  left behind (`m-unit-work` *Abort*): the refusal is replayed on the terms of
  the failure that doomed the attempt.

Everything else surfaces after the attempt it ended:

- A **lock-wait timeout** (the `m-db-error` `lockWaitTimeout` category) is **not**
  retriable.
- The remaining Write Effect Errors — **Missing Target Error**, **Stale Write
  Error**, and **Cardinality Corruption Error** (`m-unit-work`) — are **never**
  retriable, under any option. None of them describes a lost update that a
  re-read could resolve: a missing target means the rows the write addressed do
  not exist, a stale write means an ungated locking-mode write fell short despite
  the shared read lock that licensed it, and a cardinality corruption means an
  accepted identity, storage, or lowering invariant does not hold. Re-executing
  the closure would repeat the failure or, worse, write again over corrupt state.

A failure to **acquire a connection** for an attempt is never retriable, under
any option. No boundary opened and no closure ran, so there is nothing to undo
and nothing to replay: it is the terminal begin-failure outcome `m-unit-work`
already states, and it reaches the caller after one attempt however retriable
its cause might look. Each attempt acquires afresh and releases before it
finishes, so a retry runs on a connection of its own; nothing about that release
authorizes another attempt, and an implementation MUST NOT add a wait, a
reacquisition loop, or a broadened retriable set to accommodate an acquisition
failure.

Because each re-execution opens a fresh atomic scope and re-reads through the
freshness rule, the retry re-observes the version(s) a subsequent `m-opt-lock` gate
binds — so an auto-retried conflict re-reads the current version and succeeds, with
no caller-authored retry code. A re-execution re-runs the whole closure: reads and
the work built from them are reconstructed inside it, a value captured outside it
is not refreshed, and a stream the closure consumed may deliver roots the failed
attempt already delivered.

## One verdict per attempt

The boundary classifies an attempt's failure **once**, after the attempt's
rollback completed, and that one verdict is both what the attempt reports
(`m-execution-lifecycle` `retryEligible`) and what decides a re-execution. It
does not consider the remaining bound. A recoverable conflict is re-executed only
once the failed attempt has rolled back, released its connection, and finished
reporting, and only if nothing after the classification failed: a rollback that
did not complete, or a failure raised while releasing the connection or
finishing the attempt, ends the invocation instead, whatever the verdict was. A
lifecycle handler's own failure, which `m-execution-lifecycle` quarantines,
changes nothing. The error a caller receives after exhaustion, or after any
terminal failure, is the failure itself with its own causal chain.

## Waiting between attempts

Before each re-execution the boundary **MUST** wait a **bounded randomized
delay**, so that conflicting invocations replaying at once spread out rather than
collide again. The wait begins only once the failed attempt has rolled back,
released its connection, and finished reporting, so no connection or attempt is
held while it lasts. Nothing waits before a first attempt, after the last one,
or after a terminal failure, and a bound of `0` never waits.

The delay's scale **SHOULD** follow the measured duration of the attempt that
just failed. How long a conflicting writer holds what it wrote depends on round
trips, statement count, and work inside the transaction, all of which differ by
deployment, so a delay fixed in absolute time suits only the environment it was
measured in. The delay keeps absolute bounds whatever the attempt took. Its
distribution, its scale, and its bounds are internal policy, chosen from
contention evidence rather than offered as an option.

## Recognizing the conflict

The Write Effect Error family, the Optimistic Lock Conflict Error included, is
owned by **`m-unit-work`** — the module that owns the affected-row enforcer that
raises it. This module therefore recognizes the canonical conflict **directly**,
over its existing `m-auto-retry --> m-unit-work` edge.

That ownership is what keeps the retry loop free of a dependency on an optional
concurrency module. An implementation **MUST NOT** require the composition root
to inject the conflict type into the retry classifier, and **MUST NOT** take a
`m-auto-retry --> m-opt-lock` edge to name it.

The Write Precondition Error a caller-addressed write raises (`m-unit-work`) is
never in the retriable set, and neither is a doom it caused: a retry re-states
the same caller revision against the same stored row.

## What the suite pins down

The observable loop-mechanics branches (a conflict replayed away, a conflict a
zero bound leaves unreplayed, an injected transient auto-retried away,
`maxRetries: 0`, bound exhaustion, the callback value withheld on abort) need
injected faults a single-connection harness cannot provoke, so they are authored
as **boundary** cases on the `api-conformance` lane and satisfied by each
language's API Conformance Suite (`m-api-conformance`). The root-owned defaults
(`m-execution` *Options a root is configured with*) are proven the same way,
through what the loop does under a configured root (`m-case-format` *Root
configuration*): a zero bound on the root disables the loop for an invocation
naming none, a conflict included, and an explicit bound overrides it; and a root
level stands over every attempt and an explicit level overrides it.
