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

The bound is **configurable** per boundary as part of its **Retry Policy**
(*The Retry Policy*, below); an omitted policy resolves as `m-execution` *Option
resolution* states. A bound of **`0` disables** the loop, so even a
retriable failure surfaces to the caller after the first attempt. A retry that
**exhausts** the bound surfaces the failure to the caller (diagnosably — the
surfaced error carries the attempt count). This mirrors Reladomo's
`MithraManager.executeTransactionalCommand` retry loop (`TransactionStyle`
default 10), with the default owned by the root rather than by each call.

Which failures are retriable is fixed policy rather than an option. Together
they are the **recoverable conflicts**: a failure a re-execution against fresh
state or with a fresh Transaction Instant can resolve.

- **Transient database failures** — deadlock and serialization failure (the
  `m-db-error` `deadlock` category).
- An **Optimistic Lock Conflict Error** — a gate an observation of the attempt
  bound came up short because a concurrent writer moved the row first.
- A **Temporal Conflict Error** — the attempt's Transaction Instant does not
  follow the stored start of a row it would close (`m-unit-work` *Closes the
  instant cannot follow*). The re-execution is a new attempt with its own lazy
  instant and fresh reads, so the ordinary bounded delay rides out a clock that
  is briefly behind or an instant another writer overtook; a clock behind by
  more than the attempts can cover exhausts the bound, and the conflict
  surfaces as the failure.
- A **recognized exclusion conflict** — a statement the attempt executed was
  refused by the exclusion of the temporal table it wrote (`m-storage-layout`
  *Temporal history constraints*). Recognition takes both the dialect's
  exclusion-violation kind and the exact name that table's layout compiled for
  its exclusion; neither a native code alone, a name prefix, nor any message
  text recognizes one, and execution, which knows which statement failed and
  which table it wrote, makes the recognition where it attributes the failure to
  that statement. It is not attributed to a caller's or a derived write: a
  concurrent writer may have opened coverage the plan did not hold, or a clock
  behind stored history may have stamped an opening inside it, and a
  re-execution plans again against fresh state at a fresh instant. The failure
  stays the original `m-db-error` `constraintViolation` error with its
  constraint name, retried or surfaced. A refusal no re-execution can resolve —
  an insert over coverage that is already current, or a planner defect — is
  re-executed until the bound is spent and then surfaces with the attempt count,
  so it costs up to the whole bound's attempts and waits; a caller expecting
  such a refusal lowers the bound for that transaction.
- Any of them carried as the cause of the rollback-only refusal a caught failure
  left behind (`m-unit-work` *Abort*): the refusal is replayed on the terms of
  the failure that doomed the attempt.

Everything else surfaces after the attempt it ended:

- A **lock-wait timeout** (the `m-db-error` `lockWaitTimeout` category) is **not**
  retriable.
- Every other `constraintViolation` — a check, a primary key's or unique
  index's duplicate (`uniqueViolation`), an exclusion of another name or of
  another table, and any exclusion violation not attributed to the statement
  that raised it — is **not** retriable.
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
freshness rule, the retry re-observes the version(s) a subsequent optimistic gate
binds — so an auto-retried conflict re-reads the current version and succeeds, with
no caller-authored retry code. A re-execution re-runs the whole closure: reads and
the work built from them are reconstructed inside it, a value captured outside it
is not refreshed, and a stream the closure consumed may deliver roots the failed
attempt already delivered.

## One verdict per attempt

The boundary classifies an attempt's failure **once**, and that one verdict is
both what the attempt reports (`m-execution-lifecycle` `retryEligible`) and what
decides a re-execution. It does not consider the remaining bound. A recoverable
conflict is re-executed only once the failed attempt has rolled back, released
its connection, and finished reporting, and only if none of those failed: a
rollback that did not complete, or a failure raised while releasing the connection or
finishing the attempt, ends the invocation instead, whatever the verdict was. A
lifecycle handler's own failure, which `m-execution-lifecycle` quarantines,
changes nothing. The error a caller receives after exhaustion, or after any
terminal failure, is the failure itself with its own causal chain.

## The Retry Policy

A **Retry Policy** is one immutable value holding everything a caller configures
about the loop:

| Field | Meaning | Built-in |
|---|---|---|
| `maxRetries` | the bound: re-executions after the first attempt, a nonnegative integer | `10` |
| `backoff.baseDelay` | the first attempt's fixed window, in seconds | `0.008` |
| `backoff.maxDelay` | the longest window, in seconds | `1` |

Each delay is finite and positive, and `baseDelay` **MUST NOT** exceed
`maxDelay`. A value outside these rules is refused before anything is acquired
or observed.

A policy is **one value**. A field it omits takes the built-in above, never a
value from a policy it replaces, so an explicit policy replaces an inherited one
whole and two policies are equal exactly when all three fields are.

The fields are what a deployment decides: how many attempts a conflict is worth,
how long conflicts typically take to clear, and the longest single wait it
accepts. Neither delay promises a minimum wait, because a draw may land anywhere
down to zero. Which failures are retriable, and how a window grows, adapts, and
is drawn from, are fixed rather than configured.

## Waiting between attempts

Before each re-execution the boundary **MUST** wait a **bounded randomized
delay**, so that conflicting invocations replaying at once spread out rather than
collide again. The wait begins only once the failed attempt has rolled back,
released its connection, and finished reporting, so no connection or attempt is
held while it lasts. Nothing waits before a first attempt, after the last one,
or after a terminal failure, and a bound of `0` never waits.

The wait after attempt `n` (the first attempt is `1`) that took `duration` is a
uniform draw from `[0, window]`:

```text
d      = n - 1
fixed  = min(maxDelay, baseDelay * 2^d)
scale  = min(8, 0.25 * 2^d)
window = min(maxDelay, max(fixed, scale * duration))
```

The rule holds for every attempt ordinal and every valid policy, whatever
arithmetic computes it. The doubling, the duration multiplier, and the full-jitter
draw are fixed policy, chosen from contention evidence rather than offered as
options.

The duration term exists because how long a conflicting writer holds what it
wrote depends on round trips, statement count, and work inside the transaction,
all of which differ by deployment, so a delay fixed in absolute time suits only
the environment it was measured in. `duration` runs from handing the attempt
control to receiving its failure, and excludes earlier waits.

The delay depends on the attempt ordinal and its duration alone, never on which
failure occurred. A fast-failing attempt therefore waits about the doubling
`baseDelay` windows, and a small bound can run out while a conflicting commit is
still becoming visible. That is a limit of a small budget rather than a case the
wait treats specially: a deployment that meets it raises `maxRetries` or
`baseDelay`.

## Failures a retry cannot resolve

The Write Precondition Error a target write raises (`m-unit-work`) is
never in the retriable set, and neither is a doom it caused: a retry re-states
the same caller revision against the same stored row.

## What the suite pins down

The observable loop-mechanics branches (a conflict replayed away, a conflict a
zero bound leaves unreplayed, an injected transient auto-retried away, a
`maxRetries` of `0`, bound exhaustion, the callback value withheld on abort) need
injected faults a single-connection harness cannot provoke, so they are authored
as **boundary** cases on the `api-conformance` lane and satisfied by each
language's API Conformance Suite (`m-api-conformance`). The root-owned defaults
(`m-execution` *Options a root is configured with*) are proven the same way,
through what the loop does under a configured root (`m-case-format` *Root
configuration*): a zero bound on the root disables the loop for an invocation
naming none, a conflict included, and an explicit bound overrides it; a root
level stands over every attempt and an explicit level overrides it; a tuned
policy is inherited and reported whole, an explicit one replaces it whole, and a
join compares policies by value. Waits are not observable through the portable
case format: the wait rule's own evidence belongs to each implementation's loop.
