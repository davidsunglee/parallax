# M8 — Transactions, Unit of Work & Identity + Query Cache

`M8` is the in-memory coherence layer: the unit of work that buffers and orders
writes, the **identity cache** that guarantees one object per primary key, the
**query cache** that maps an operation to its result set, and the automatic
read-correctness rules that make in-transaction reads safe without the caller
writing a single line of locking SQL.

`M8` is expressed entirely in terms of **operations and object state** (`M2`):
it depends on `M2` and on the execution seam `M11`, but **not** on `M3`. The
dialect-specific SQL the unit of work executes (the read-lock suffix, the
batched insert/update forms) is produced by `M3` and run through the `M11`
execution seam at the composition root, so `M8` takes no direct edge to SQL
generation. (`M5` and `M4` in turn depend on `M8`, because a list is an
operation-backed view resolved through the cache, and deep fetch populates the
cache.)

This mirrors Reladomo's per-type portal (identity cache + query cache + reader/
persister) coordinated by a process-wide manager (transactions + notification),
but `M8` mandates only the **observable** rules — not any particular class
decomposition.

## The unit of work

A **unit of work** (transaction) is the scope within which object reads and
writes are coherent. Within one unit of work:

- Every read of a given primary key resolves to the **same** logical object
  (identity, below).
- Writes are **buffered** as pending operations, not flushed eagerly. At the
  unit-of-work boundary they are **combined, batched, and ordered** to respect
  foreign-key constraints, then flushed in one pass.
- A read that depends on a not-yet-flushed write **MUST** observe that write
  (the unit of work flushes pending writes before serving a dependent read, so a
  query never returns stale in-transaction state).

> **The transaction boundary is user-specified, per-language.** How a unit of
> work is opened and committed — a closure, a context manager, a decorator, an
> explicit `begin`/`commit` pair — is an idiomatic, per-language concern and is
> pinned down in the per-language spec, **never** in raw SQL terms in core. Core
> mandates the *observable effects within and at* the boundary, not its syntax.

## Identity cache — one object per primary key

The identity cache **interns** objects: there is **exactly one** in-memory
object per primary key per cache scope. Two finds that resolve the same primary
key **MUST** yield the **same logical object** — not two equal copies. This is
the foundation the rest of the layer rests on:

- it lets the unit of work track per-object pending state by identity;
- it lets a detached copy (`M9`) and an optimistic-lock version (`M10`) be keyed
  to a single canonical object;
- it makes the query cache safe to hold *references* to interned objects rather
  than copies.

A row read from the database is funneled through the identity cache on the way
in: on a primary-key **hit** the existing object is returned (the row is
discarded); on a **miss** a new object is created and interned. The
compatibility suite proves the observable half of this — *same PK ⇒ same
logical object* — with an **identity scenario** (below): two finds keyed to the
same primary key are asserted to denote one object by carrying the **same
primary-key identity** in both results.

## Query cache — operation ⇒ result, and round-trip elimination

The query cache maps an **operation** (an `M2` node) to the **result list** of
already-interned objects it produced. A repeated find for an **equal operation**
is served from the query cache **without a database round trip**.

The query cache is **mandatory**, not optional. The deep-fetch and round-trip-
count guarantees (`M4`, a core selling point) are only **observable** when the
query cache exists: without it, "two identical finds cost one round trip" and
"a deep fetch is `1 + levels` statements, never `1 + N + N`" cannot be stated as
portable, testable contracts. Gating the query cache behind a flag would gate
those guarantees too, so the core mandates it (DQ4).

The observable contract:

- A find whose operation **equals** an operation already resolved in the same
  cache scope **MUST** cost **zero** additional database round trips (a cache
  hit).
- A cache hit **MUST** return the same interned objects as the original find
  (identity is preserved across the hit).

The suite proves this with a **cache-hit scenario**: two identical finds whose
declared round-trip total is **one** (the second is a hit), with the single
golden SQL statement listed once.

### Cache invalidation (freshness)

A write that changes an entity invalidates the dependent cached queries. The
**mechanism** (a version-token / update-count bumped on write, so dependent
cached queries expire without being enumerated) is non-normative; the
**observable** rule is: after a committed write to an entity, a subsequent find
**MUST NOT** return stale rows for that entity. The suite proves this with a
**cache-invalidation scenario**: a find, a committed write step, then the *same*
find re-issued — which must re-resolve (a cache miss) and observe the new value,
not be served the stale cached row. The companion **read-your-own-writes
scenario** buffers a write then issues a dependent find that must observe it
(the unit of work flushes before the dependent read). Cross-**process**
invalidation
(one app server seeing another's writes) is a separate, fast-follow concern —
[cross-process cache coherence](m14-cross-process-coherence.md), which extends exactly
this rule to multiple application servers sharing one database — not part of this
MVP module.

## Abort

A unit of work either **commits** or **aborts** (rolls back). A commit makes its
writes durable and observable; an **abort discards them entirely**. The
observable contract:

- A write performed inside a unit of work that aborts **MUST NOT** be observable
  after the abort — whether it was still **buffered**, had been **force-flushed**
  to serve a dependent read (read-your-own-writes, above), or had populated the
  **identity / query cache**. A find issued after the abort **MUST** re-resolve
  and observe the **pre-transaction** state.
- The transaction callback's return value is **withheld on abort**: if the unit
  of work rolls back — or its commit fails — the operation **fails** rather than
  returning the callback value as though it were durable (promoting ADR 0008 into
  normative text).

This reconciles the abort contract with the **read-your-own-writes forced flush**
(above). The forced flush is safe precisely *because* it lands **inside the
still-open atomic scope** the abort discards: the unit of work may push a
buffered write to the database mid-transaction so a dependent read observes it,
yet an abort still erases that write — the flush never escapes the transaction it
belongs to. An implementation **MUST NOT** satisfy read-your-own-writes with a
flush that survives the abort.

The suite proves this with a **rollback scenario**: a find, a write step whose
golden DML is applied and then **rolled back**, and the *same* find re-issued —
which **MUST** re-resolve (a cache miss) and observe the **original** rows, never
the aborted write.

## Buffered, batched, ordered writes

At the unit-of-work boundary the buffered writes are flushed as **set-based**
SQL wherever possible:

- Multiple inserts of the same entity collapse into a **single multi-row
  `INSERT`** (one statement, many value tuples) rather than one statement per
  row.
- Multiple updates of the same entity that set the same columns collapse into a
  **batched `UPDATE`** (executed once per distinct key, or as a single statement
  with an `IN` predicate when the new values are uniform).
- Operations are **ordered** so that a parent row is inserted before a child
  that references it (and deleted after), honoring foreign-key constraints.

The canonical golden SQL for the batched forms is fixed by `M3` (the multi-row
`INSERT ... VALUES (…), (…), (…)` and the keyed `UPDATE`). The suite proves the
batched writes against real data by **applying** the golden DML and asserting
the resulting table state — exactly the write-sequence machinery (`M12`), reused
for the non-temporal batched case.

## Strategy selection — the per-unit-of-work participation mode

A unit of work selects, per transaction, **how** its read-then-writes are made
correct — mirroring Reladomo's `TxParticipationMode`. Two strategies:

- **`locking`** (the **default**) — the automatic in-transaction shared read
  lock, below. Reads take a row lock; writes need no version gate.
- **`optimistic`** — the alternative (`M10`): reads take **no** lock (so readers
  never block writers), and every keyed write gates on the version the unit of
  work observed. Selected explicitly on the unit of work
  (`concurrency: optimistic`).

The mode is a property of the **unit of work**, not of the entity: the same
versioned entity is written under the shared lock in one workflow and under the
version gate in another. The metamodel only *names* the version column (`M1`);
opting into optimistic mode is what drops the read locks and emits the gate. This
section specifies the default `locking` strategy; `M10` specifies the optimistic
one.

### Automatic read-lock correctness

Reads performed **inside a unit of work** that intends to write **MUST** be made
correct without the caller writing locking SQL. The default (`locking`) in-
transaction **object find** acquires a **shared row lock**, so a concurrent
transaction cannot mutate the row out from under the read-then-write.

The lock applies to **object finds only**. A **projection or aggregation** read
inside a unit of work takes **no** lock and **proceeds unlocked — it never
errors**: its result rows have no identifiable base row to lock (the database
rejects a row-lock clause on a `distinct` / grouped / aggregate result), and per
ADR 0024 a projection returns **plain, unmanaged data** that never enters the
observed-version map or the write path — so there is nothing for a lock to
protect. Omitting the lock is therefore both necessary and safe.

**Whether and where to attach the lock is a `M11` dialect decision**, not M8's:
M8 asks the dialect to apply this unit of work's read lock to a compiled read, and
the dialect returns an object find with its shared-row-lock form appended (Postgres
`for share of t0`; MariaDB `lock in share mode`, added with that dialect) and a
projection/aggregation read unchanged. M8 contains no dialect-specific SQL shaping.

The canonical Postgres golden SQL for an object find appends the suffix to the
otherwise-ordinary read (`M3`):

```text
select t0.id, t0.balance from account t0 where t0.id = ? for share of t0
```

> The lock-suffix keywords (`share`, `of`) are lowercased in the canonical form
> like any other keyword (`M3` rule 2), even though sqlglot tokenizes them as
> values, so golden SQL is stored as `for share of t0` and passes the layer-3
> idempotence check. See `M3`.

The suite proves the read-lock golden SQL is **valid SQL that executes and
returns the expected rows** against real Postgres (the lock itself is a
concurrency property; the suite asserts the locking read is well-formed and
result-correct, which is the observable contract a single-connection harness can
verify). The **behavioral** counterpart — that the emitted lock actually *behaves
as a lock* — is proven by the two-connection concurrency cases: it **excludes a
writer** (`0728`, `error`/`concurrency`), is **shared, not exclusive** (`0729`, a
second reader is admitted), and an **unlocked projection admits a writer** (`0734`,
the behavioral counterpart to the projection-omits-lock emission case) — the last
two carrying the `concurrencySuccess` shape (two held sessions, no error raised).
The object-find-vs-aggregation split is recorded in ADR 0030 (which
supersedes-in-part ADR 0009). Optimistic locking — the *alternative* correctness
strategy, where a read takes **no** lock and a version column is checked in the
`UPDATE` — is `M10`.

## Bounded automatic retry

The unit-of-work boundary **MUST** offer **bounded automatic retry**. On a
**retriable** failure of the closure the boundary **MUST**:

1. **roll back** the failed attempt's atomic scope (the *Abort* contract erases
   its writes — buffered, force-flushed, or cached);
2. **invalidate stale cached state** so the re-execution observes fresh state
   (the *Cache invalidation (freshness)* rule) — the retry re-reads, it does not
   replay a stale in-memory shadow;
3. **re-execute the closure** against that fresh state, inside a new atomic scope.

The bound is **configurable** with a **default of 10** re-executions; a bound of
**`0` disables** the loop, so even a retriable failure surfaces to the caller
after the first attempt. A retry that **exhausts** the bound surfaces the failure
to the caller (diagnosably — the surfaced error carries the attempt count). This
mirrors Reladomo's `MithraManager.executeTransactionalCommand` retry loop
(`TransactionStyle` default 10).

Which failures are retriable:

- **Transient database failures** — deadlock and serialization failure (the `M11`
  `deadlock` category) — are retriable **by default**, no caller action needed.
- **Optimistic-lock conflicts** (`M10`) are **not** retriable by default: a
  conflict surfaces to the caller after one attempt, and joins the retriable set
  **only** when the unit of work opts in (`retryOptimisticConflicts`, Reladomo's
  `setRetryOnOptimisticLockFailure`, default off).
- A **lock-wait timeout** (the `M11` `lockWaitTimeout` category) is **not**
  retriable.

Because each re-execution opens a fresh atomic scope and re-reads through the
freshness rule, the retry re-observes the version(s) a subsequent `M10` gate binds
— so an auto-retried conflict re-reads the current version and succeeds, with no
caller-authored retry code. The observable loop-mechanics branches (a conflict
surfacing without the opt-in, an injected transient auto-retried away, `retries:
0`, bound exhaustion, the callback value withheld on abort) are authored as
**boundary** cases on the `api-conformance` lane (they need injected faults a
single-connection harness cannot provoke) and satisfied by each language's API
Conformance Suite.

## What the suite pins down

The compatibility suite expresses M8's observable rules as **scenario** cases —
ordered operation steps, each with a declared round-trip count, plus identity/
cache assertions — and as plain read / write cases for the SQL fragments:

| Case | What it proves |
|---|---|
| cache-hit scenario | two identical finds ⇒ **one** round trip (the query cache eliminates the second) |
| identity scenario | two finds for the same primary key ⇒ the **same logical object** |
| read-lock case | the `for share of t0` read is valid and result-correct |
| read-lock-blocks-writer case | the shared read lock has **locking effect** — A holds `for share`, B's concurrent UPDATE blocks and times out (`error`/`concurrency` shape, two held sessions) |
| read-lock-shared-compatible case | the shared read lock is **shared, not exclusive** — A and B both take `for share` on the same row and **both succeed** (`concurrencySuccess` shape; pins `for share`, not `for update`) |
| projection-omits-lock-admits-writer case | an **unlocked projection admits a writer** — A holds a `distinct` projection (no lock), B's concurrent UPDATE succeeds without blocking (the behavioral counterpart to the projection-omits-lock emission case) |
| batched-write case | a multi-row `INSERT` and a batched `UPDATE` produce the expected rows |
| rollback scenario | an aborted write is discarded; a post-abort find observes the original rows |
| retry boundary cases | bounded automatic retry: transients auto-retried, conflicts only on opt-in, `retries: 0` disables, bound exhaustion surfaces (`api-conformance` lane) |

A scenario's declared round-trip counts **MUST** be internally consistent with
the golden SQL it lists: each step's `roundTrips` equals the number of golden
SQL statements that step emits (a cache hit emits **zero**), and the steps' total
equals the case-level `roundTrips`. The harness asserts this consistency without
ever compiling an operation to SQL — proving the round-trip contract from the
fixture itself — and executes the listed golden SQL against the real database to
confirm result-correctness.
