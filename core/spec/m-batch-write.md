# m-batch-write — Buffered Batching / Readless Predicate Writes

`m-batch-write` distinguishes two related but non-interchangeable write families:

1. **buffered tracked-row batching** at an `m-unit-work` boundary, where the unit
   of work already holds an enumerated set of objects; and
2. **predicate-selected writes** over a bare `m-op-algebra` predicate, whose
   canonical instruction is supplied by `m-case-format`.

It owns only the set-based/readless vocabulary for the second family. Versioning,
locking, conflict abort, and temporal chaining belong respectively to `m-opt-lock`,
`m-read-lock`, `m-txtime-write`, and `m-bitemp-write`. The canonical golden SQL is
fixed by `m-sql`.

## Set-based flush

- Multiple inserts of the same entity collapse into a **single multi-row
  `INSERT`** (one statement, many value tuples) rather than one statement per
  row.
- Multiple updates of the same entity that set the same columns collapse into a
  **batched `UPDATE`** — executed once per distinct key, or as a single statement
  with an `IN` predicate when the new value is uniform across the keys.
- Multiple deletes of the same **non-versioned** entity collapse into a **single
  `DELETE`** with an `IN` predicate (`delete from t where id in (?, …)`) rather
  than one statement per row — the delete analogue of the multi-row `INSERT`. (A
  **versioned** entity's set-based delete cannot collapse — see below.)

The canonical Postgres golden SQL (`m-sql`), as `then.statements` entries:

```yaml
# m-batch-write-001 (set-based flush) then.statements:
- sql:
    postgres: insert into account(id, owner, balance) values (?, ?, ?), (?, ?, ?), (?, ?, ?)
# m-batch-write-002 (update per key) then.statements:
- sql:
    postgres: update account set balance = ? where id in (?, ?)
# m-batch-write-003 (batch DELETE collapse) then.statements:
- sql:
    postgres: delete from wallet where id in (?, ?, ?)
# m-batch-write-004 (versioned delete materializes per key) then.statements:
- sql:
    postgres: delete from account where id = ? and version = ?
```

The suite proves the batched forms against real data by **applying** the golden
DML and asserting the resulting table state — the write-sequence machinery
(`m-case-format`), reused for the non-temporal batched case (cases
`m-batch-write-001` / `m-batch-write-002` for the insert/update collapse,
`m-batch-write-003` for the DELETE collapse, `m-batch-write-004` for the versioned
per-key delete). So "buffered writes flush as set-based SQL" is verified by the
rows it leaves behind, not merely asserted.

A **versioned** entity has no readless predicate-write template — a per-row
observed version cannot ride one statement — so predicate update and delete
materialize to keyed writes (`m-opt-lock`). Transaction-Time temporal predicate
writes likewise materialize so each observed milestone can close/chain
(`m-txtime-write` / `m-bitemp-write`). Those are not buffered-batch collapse rules.

## Predicate-selected readless forms

For an **unversioned, non-temporal** target, a predicate-selected write is
readless and emits exactly one statement. `update` is:

```text
update <table> set <column> = ?, … where <predicate>
```

There is no materialization and no equality-elimination pass: rows already equal
to an assigned value are still matched by ordinary SQL set semantics. The emitted
`set` columns and their assignment-value binds follow descriptor declared column
order, regardless of the instruction's ordered assignment list; predicate binds
come after those assignment binds. `delete` is exactly:

```text
delete from <table> where <predicate>
```

`m-batch-write-005` pins readless predicate delete and
`m-batch-write-006` pins the update's descriptor-order SQL and bind determinism.
Reladomo's transaction behavior remains prior art for the materializing branch:
it reads under a lock or gates on an observed optimistic version, not a Java bulk
API template. Parallax applies that runtime rule through the owning modules above.

A readless statement that **matches zero rows succeeds with zero affected rows —
never an error.** Ordinary SQL set semantics already make `update … where
<predicate>` and `delete … where <predicate>` no-ops when nothing matches; a
predicate-selected write that matches nothing simply wrote nothing, the same way
a materializing verb's resolving read matching zero rows emits zero keyed writes
and succeeds (`m-opt-lock`). This is categorically distinct from the zero-row
**conflict** error a *gated* per-row write raises (`m-opt-lock` / `m-txtime-write`):
that error fires when a row the caller **did** match and observe was concurrently
changed underneath it — matching nothing is never that.

## What the suite pins down

The existing `m-batch-write-001`–`-004` cases prove only **buffered tracked-row
batching**: multi-row insert, uniform-key update, non-versioned `IN` delete, and
versioned per-key delete. The predicate-write witnesses prove a distinct target:

| Case | Target | Predicate-write witness |
|---|---|---|
| `m-batch-write-005` | non-versioned `Wallet` delete | one readless `delete … where <predicate>` |
| `m-batch-write-006` | non-versioned `Wallet` update | one readless update; reversed authored assignments still emit descriptor column order and assignment-before-predicate binds |
| `m-opt-lock-015` | versioned `Account` delete | materialize plus one optimistic per-row delete for each match |

The two families share SQL terminology but not an observation contract: an `IN`
list can collapse an already tracked set, whereas a predicate write starts from an
operation and either remains readless or materializes because its target requires
per-row observation.
