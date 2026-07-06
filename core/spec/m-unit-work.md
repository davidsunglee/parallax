# m-unit-work — Transactions & Unit of Work

`m-unit-work` is the transaction scope: the unit of work that **buffers, orders,
and flushes** writes, and the automatic read-correctness rules that make
in-transaction reads safe. It is expressed entirely in terms of **operations and
object state** (`m-op-algebra`): it depends on `m-op-algebra` and on the execution
port `m-db-port`, but **not** on `m-sql`. The dialect-specific SQL the unit of work
executes (the read-lock suffix, the batched forms) is produced by `m-sql` and run
through the `m-db-port` execution seam at the composition root, so `m-unit-work`
takes no direct edge to SQL generation. (`m-op-list` and `m-navigate` in turn
depend on `m-unit-work`, because a list is an operation-backed view resolved within
a unit of work.)

Layered on the unit of work are three modules: the automatic shared read lock
(`m-read-lock`), bounded automatic retry (`m-auto-retry`), and the identity + query
caches (`m-process-cache`, deferred).

## The unit of work

A **unit of work** (transaction) is the scope within which object reads and
writes are coherent. Within one unit of work:

- Every read of a given primary key resolves to the **same** logical object
  (identity — the cache that guarantees this is `m-process-cache`).
- Writes are **buffered** as pending operations, not flushed eagerly. At the
  unit-of-work boundary they are **combined, batched, and ordered** to respect
  foreign-key constraints, then flushed in one pass.
- A read that depends on a not-yet-flushed write **MUST** observe that write: the
  unit of work flushes pending writes before serving a dependent read
  (read-your-own-writes), so a query never returns stale in-transaction state.

> **The transaction boundary is user-specified, per-language.** How a unit of
> work is opened and committed — a closure, a context manager, a decorator, an
> explicit `begin`/`commit` pair — is an idiomatic, per-language concern and is
> pinned down in the per-language spec, **never** in raw SQL terms in core. Core
> mandates the *observable effects within and at* the boundary, not its syntax.

## Abort

A unit of work either **commits** or **aborts** (rolls back). A commit makes its
writes durable and observable; an **abort discards them entirely**. The
observable contract:

- A write performed inside a unit of work that aborts **MUST NOT** be observable
  after the abort — whether it was still **buffered**, had been **force-flushed**
  to serve a dependent read (read-your-own-writes), or had populated a cache. A
  find issued after the abort **MUST** re-resolve and observe the
  **pre-transaction** state.
- The transaction callback's return value is **withheld on abort**: if the unit
  of work rolls back — or its commit fails — the operation **fails** rather than
  returning the callback value as though it were durable (promoting ADR 0006 into
  normative text).

This reconciles the abort contract with the **read-your-own-writes forced flush**.
The forced flush is safe precisely *because* it lands **inside the still-open
atomic scope** the abort discards: the unit of work may push a buffered write to
the database mid-transaction so a dependent read observes it, yet an abort still
erases that write — the flush never escapes the transaction it belongs to. An
implementation **MUST NOT** satisfy read-your-own-writes with a flush that survives
the abort.

The suite proves this with a **rollback scenario**: a find, a write step whose
golden DML is applied and then **rolled back**, and the *same* find re-issued —
which **MUST** re-resolve and observe the **original** rows, never the aborted
write.

## Buffered, batched, ordered writes

At the unit-of-work boundary the buffered writes are flushed as **set-based** SQL
wherever possible:

- Multiple inserts or same-column updates of one entity collapse into set-based
  SQL — a single multi-row `INSERT`, a batched `UPDATE`. The canonical golden
  forms and their proof are `m-batch-write`.
- Operations are **ordered** so that a parent row is inserted before a child
  that references it (and deleted after), honoring foreign-key constraints.

## Strategy selection — the per-unit-of-work participation mode

A unit of work selects, per transaction, **how** its read-then-writes are made
correct — mirroring Reladomo's `TxParticipationMode`. Two strategies:

- **`locking`** (the **default**) — the automatic in-transaction shared read lock
  (`m-read-lock`). Reads take a row lock; writes need no version gate.
- **`optimistic`** — the alternative (`m-opt-lock`): reads take **no** lock (so
  readers never block writers), and every keyed write gates on the version the
  unit of work observed. Selected explicitly on the unit of work
  (`concurrency: optimistic`).

The mode is a property of the **unit of work**, not of the entity: the same
versioned entity is written under the shared lock in one workflow and under the
version gate in another. The metamodel only *names* the version column
(`m-descriptor`); opting into optimistic mode is what drops the read locks and
emits the gate.

## What the suite pins down

`m-unit-work`'s observable rules are expressed as **scenario** cases — ordered
operation steps, each with a declared round-trip count — and plain write cases:

| Case | What it proves |
|---|---|
| read-your-own-writes scenario | a buffered write is flushed before a dependent find observes it |
| rollback scenario | an aborted write is discarded; a post-abort find observes the original rows |
| fk-ordering / flush cases | buffered writes flush ordered by foreign-key dependency |

A scenario's declared round-trip counts **MUST** be internally consistent with
the golden SQL it lists: each step's `roundTrips` equals the number of golden SQL
statements that step emits. The harness asserts this consistency without ever
compiling an operation to SQL — proving the round-trip contract from the fixture
itself — and executes the listed golden SQL against the real database to confirm
result-correctness.
