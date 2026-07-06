# m-read-lock — In-Transaction Shared Read Lock

`m-read-lock` is the default (`locking`-mode) correctness strategy: an
in-transaction **object find** that intends to write acquires a **shared row lock**
so a concurrent transaction cannot mutate the row out from under a
read-then-write. Per the dependency graph, `m-read-lock` depends on `m-unit-work`
(the transaction whose mode selects it) and `m-dialect` (which owns the lock
spelling and application). The optimistic alternative — a read that takes no lock
and a version-gated write — is `m-opt-lock`.

## Automatic read-lock correctness

Reads performed **inside a unit of work** that intends to write **MUST** be made
correct without the caller writing locking SQL. The default (`locking`) in-
transaction **object find** acquires a **shared row lock**.

The lock applies to **object finds only**. A **projection or aggregation** read
inside a unit of work takes **no** lock and **proceeds unlocked — it never
errors**: its result rows have no identifiable base row to lock (the database
rejects a row-lock clause on a `distinct` / grouped / aggregate result), and per
ADR 0024 a projection returns **plain, unmanaged data** that never enters the
observed-version map or the write path — so there is nothing for a lock to
protect. Omitting the lock is therefore both necessary and safe.

**Whether and where to attach the lock is a `m-dialect` decision**, not
`m-unit-work`'s: the unit of work asks the dialect to apply this transaction's read
lock to a compiled read, and the dialect returns an object find with its
shared-row-lock form appended (Postgres `for share of t0`; MariaDB `lock in share
mode`) and a projection/aggregation read unchanged. `m-unit-work` contains no
dialect-specific SQL shaping.

The canonical Postgres golden SQL for an object find appends the suffix to the
otherwise-ordinary read (`m-sql`):

```text
select t0.id, t0.balance from account t0 where t0.id = ? for share of t0
```

> The lock-suffix keywords (`share`, `of`) are lowercased in the canonical form
> like any other keyword (`m-sql` rule 2), even though sqlglot tokenizes them as
> values, so golden SQL is stored as `for share of t0` and passes the layer-3
> idempotence check.

## What the suite pins down

The suite proves the read-lock golden SQL is **valid SQL that executes and
returns the expected rows** against real Postgres (the lock itself is a
concurrency property; a single-connection harness verifies the locking read is
well-formed and result-correct — the observable contract it can check). The
**behavioral** counterpart — that the emitted lock actually *behaves as a lock* —
is proven by the two-connection concurrency cases: it **excludes a writer**
(`m-read-lock-006`, `error`/`concurrency`), is **shared, not exclusive**
(`m-read-lock-007`, a second reader is admitted), and an **unlocked projection
admits a writer** (`m-read-lock-008`, the behavioral counterpart to the
projection-omits-lock emission case) — the last two carrying the
`concurrencySuccess` shape (two held sessions, no error raised). The
object-find-vs-aggregation split is recorded in ADR 0030 (which supersedes-in-part
ADR 0009).
