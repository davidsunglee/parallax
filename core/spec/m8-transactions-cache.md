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

## Automatic read-lock correctness

Reads performed **inside a unit of work** that intends to write **MUST** be made
correct without the caller writing locking SQL. The default in-transaction read
acquires a **shared row lock**, so a concurrent transaction cannot mutate the row
out from under the read-then-write. The **lock suffix is a dialect decision**
owned by `M11`:

| Dialect | Read-lock suffix |
|---|---|
| Postgres | `for share of t0` |
| (MariaDB) | `lock in share mode` (added with the MariaDB dialect) |

The canonical Postgres golden SQL appends the suffix to the otherwise-ordinary
read (`M3`):

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
verify). Optimistic locking — the *alternative* correctness strategy, where a
read takes **no** lock and a version column is checked in the `UPDATE` — is
`M10`.

## What the suite pins down

The compatibility suite expresses M8's observable rules as **scenario** cases —
ordered operation steps, each with a declared round-trip count, plus identity/
cache assertions — and as plain read / write cases for the SQL fragments:

| Case | What it proves |
|---|---|
| cache-hit scenario | two identical finds ⇒ **one** round trip (the query cache eliminates the second) |
| identity scenario | two finds for the same primary key ⇒ the **same logical object** |
| read-lock case | the `for share of t0` read is valid and result-correct |
| batched-write case | a multi-row `INSERT` and a batched `UPDATE` produce the expected rows |
| rollback scenario | an aborted write is discarded; a post-abort find observes the original rows |

A scenario's declared round-trip counts **MUST** be internally consistent with
the golden SQL it lists: each step's `roundTrips` equals the number of golden
SQL statements that step emits (a cache hit emits **zero**), and the steps' total
equals the case-level `roundTrips`. The harness asserts this consistency without
ever compiling an operation to SQL — proving the round-trip contract from the
fixture itself — and executes the listed golden SQL against the real database to
confirm result-correctness.
