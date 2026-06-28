# M10 — Optimistic Locking

`M10` is the **optimistic concurrency** strategy: instead of holding a row lock
for the duration of a read-then-write (`M8`'s automatic shared-row lock), an
entity carries a **version column** that is checked in — and advanced by — every
`UPDATE`. A concurrent write that changed the version first makes the stale-
version write match **no** row, and that *missing* row is the conflict signal.

`M10` is a fast-follow module. It depends on `M8` (the unit of work whose flush
issues the versioned `UPDATE`, and the identity cache that holds the version a
reader observed) and on nothing below it. The version-check SQL is fixed by `M3`;
`M10` mandates the **observable** conflict-detection rule.

Optimistic locking is the **alternative** correctness strategy to `M8`'s
automatic read lock: a read takes **no** lock (so readers never block writers),
and correctness is recovered at write time by the version check. It suits
read-mostly workloads and detached edits (`M9`), where holding a lock across the
edit is undesirable or impossible.

## The version column

An entity opts into optimistic locking by marking exactly one attribute
`optimisticLocking: true` (`M1`). That attribute is the **version**: an integer
that an implementation **MUST**:

- read alongside the row (the reader observes the current version);
- include in the `where` clause of every `UPDATE` of that row (the **expected**
  version — the value read earlier);
- **advance** in the `UPDATE`'s `set` (so every successful write moves the
  version forward).

A `read-only` attribute is never written; a version attribute is the exception
that an implementation **MUST** write on every update even when no domain field
changed, because advancing the version is what makes the *next* writer's check
meaningful.

## Conflict detection

The version turns a lost update into a **detectable** event. The canonical golden
`UPDATE` (`M3`) gates on the expected version:

```text
update account set balance = ?, version = ? where id = ? and version = ?
binds: [<new-balance>, <new-version>, <pk>, <expected-version>]
```

The detection rule is the **affected-row count**:

- The `UPDATE` affects **exactly one** row ⇒ **success**. No concurrent write
  intervened; the version advanced.
- The `UPDATE` affects **zero** rows ⇒ **conflict**. A concurrent transaction
  committed first and incremented the version, so the `where … and version = ?`
  gate matched no row. This is the `updatedRows != 1` signal.

An implementation **MUST** treat `updatedRows != 1` on a versioned `UPDATE` as a
conflict (a row that exists but no longer matches the expected version), and
**MUST NOT** silently succeed. The primary-key row still exists; only its version
moved, so the count — not an error from the database — is the conflict carrier.

## Retry contract

A detected conflict is **retriable**. On conflict an implementation **MUST**:

1. surface the conflict to the unit-of-work boundary (e.g. by raising a
   conflict / retriable exception, the per-language shape of which is an
   idiomatic concern);
2. invalidate the stale cached row so a re-read fetches the **current** version
   and values (`M8` cache freshness);
3. permit a **retry** that re-reads the fresh version and re-applies the
   intended change against it.

Whether retry is **automatic** (a bounded retry loop around the unit of work, as
Reladomo does by default) or **caller-driven** is a per-language policy; core
mandates only that a conflict is *retriable* and that a retry re-reads the fresh
version. A retry that exhausts its bound surfaces the conflict to the caller.

The suite proves the retriable half observably with a conflict case's
**`attempts`** sequence (M12): a stale-version `UPDATE` affects `0` rows, then a
retry that re-reads the fresh version and re-applies affects `1` — the `0`-then-
`1` transition, asserted against real data.

Optimistic locking composes with **detached merge-back** (`M9`): the version a
detached copy carries is the one read at detachment, so a merge-back `UPDATE`
gates on that version and detects a conflict if the original changed in the
interim — exactly the same `updatedRows != 1` rule.

## What the suite pins down

`M10` is proven by a **conflict case** (`M12`): the golden `UPDATE` is applied to
a loaded table and the **affected-row count** is asserted. The case carries an
optional out-of-band **`precondition`** — a naive SQL statement that simulates a
concurrent transaction mutating the row — and an **`expectedAffectedRows`** count:

| Case | Precondition | Golden UPDATE version | Affected rows |
|---|---|---|---|
| optimistic-lock conflict | bump the row's version out of band | the now-stale version | **0** (conflict detected) |
| optimistic-lock success | none | the current version | **1** (write applied) |

The harness loads the model's fixtures (the row exists with its current
version), applies the precondition (a concurrent version bump, for the conflict
case), runs the golden `UPDATE`, and asserts the affected-row count equals
`expectedAffectedRows` — and, when authored, the resulting table state. This
proves conflict detection against **real data**: the stale-version `UPDATE`
provably touches zero rows, the fresh-version one provably touches exactly one,
so `updatedRows != 1` is verified as the conflict signal rather than merely
asserted in prose.
