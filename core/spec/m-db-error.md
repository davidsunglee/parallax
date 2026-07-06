# m-db-error — Database Error Classification

`m-db-error` maps a raised database error to a neutral **category** so
language-neutral code can react without dialect knowledge. Per the dependency
graph, `m-db-error` depends on `m-db-port` (errors are raised at the execution
boundary) and `m-dialect` (the per-dialect native code source). This is the
**only** place native error codes are interpreted; everything above the seam
reasons in categories.

## Neutral categories and call-site predicates

The categories are a closed set: `uniqueViolation` (duplicate key / unique-index
violation), `deadlock` (a true deadlock **or** a serialization failure — both
retriable), `lockWaitTimeout` (blocked past the lock-wait budget), plus
`connectionDead` (reserved).

Classification is interrogated at **distinct call sites**, so the seam exposes it
as predicates defined as category membership — not one stringly-typed method:

- the transaction retry loop asks `isRetriable` (`category = deadlock`);
- the insert / detached merge-back path asks `violatesUniqueIndex`
  (`category = uniqueViolation`);
- the lock path asks `isTimedOut` (`category = lockWaitTimeout`).

## Per-dialect native codes

The native code source **diverges**: Postgres keys on the **`SQLSTATE` string**,
MariaDB on the **vendor errno**. This is load-bearing: `SQLSTATE 40001` is a
*serialization failure* on Postgres (distinct from deadlock `40P01`) but the
*deadlock* state on MariaDB (whose errno `1213` is what the seam matches) — so a
naive cross-dialect `SQLSTATE` compare would misclassify. The mapping:

| Category | Postgres (`SQLSTATE`) | MariaDB (errno) |
|---|---|---|
| `uniqueViolation` | `23505` | `1062` |
| `deadlock` | `40P01`, `40001` | `1213` |
| `lockWaitTimeout` | `55P03` | `1205` |

## What the suite pins down

The compatibility suite exercises all three classes on both dialects (cases
`m-db-error-001`–`m-db-error-008`): a case triggers a real error and asserts the
neutral category, the per-dialect native code, and the call-site predicate
partition. `uniqueViolation` cases trigger single-connection (a duplicate insert /
colliding update whose final statement raises); `deadlock` and `lockWaitTimeout`
cases trigger two-connection (a `concurrency` choreography of barrier-separated
rounds). The classifier is a thin per-dialect extraction over the shared, DB-free
category map + call-site predicates, so the harness exercises the interface the
language implementations build, not a harness-only shortcut (`m-case-format`).
