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

The bound is **configurable** with a **default of 10** re-executions; a bound of
**`0` disables** the loop, so even a retriable failure surfaces to the caller
after the first attempt. A retry that **exhausts** the bound surfaces the failure
to the caller (diagnosably — the surfaced error carries the attempt count). This
mirrors Reladomo's `MithraManager.executeTransactionalCommand` retry loop
(`TransactionStyle` default 10).

Which failures are retriable:

- **Transient database failures** — deadlock and serialization failure (the
  `m-db-error` `deadlock` category) — are retriable **by default**, no caller
  action needed.
- An **Optimistic Lock Conflict Error** is **not** retriable by default: a
  conflict surfaces to the caller after one attempt, and joins the retriable set
  **only** when the unit of work opts in (`retryOptimisticConflicts`, Reladomo's
  `setRetryOnOptimisticLockFailure`, default off).
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

Because each re-execution opens a fresh atomic scope and re-reads through the
freshness rule, the retry re-observes the version(s) a subsequent `m-opt-lock` gate
binds — so an auto-retried conflict re-reads the current version and succeeds, with
no caller-authored retry code.

## Recognizing the conflict

The Write Effect Error family, the Optimistic Lock Conflict Error included, is
owned by **`m-unit-work`** — the module that owns the affected-row enforcer that
raises it. This module therefore recognizes the canonical conflict **directly**,
over its existing `m-auto-retry --> m-unit-work` edge.

That ownership is what keeps the retry loop free of a dependency on an optional
concurrency module. An implementation **MUST NOT** require the composition root
to inject the conflict type into the retry classifier, and **MUST NOT** take a
`m-auto-retry --> m-opt-lock` edge to name it. The `retryOptimisticConflicts`
opt-in above is genuine caller policy and stays; wiring whose only purpose was
carrying a type across a module boundary does not.

## What the suite pins down

The observable loop-mechanics branches (a conflict surfacing without the opt-in, an
injected transient auto-retried away, `retries: 0`, bound exhaustion, the callback
value withheld on abort) need injected faults a single-connection harness cannot
provoke, so they are authored as **boundary** cases on the `api-conformance` lane
and satisfied by each language's API Conformance Suite (`m-api-conformance`).
