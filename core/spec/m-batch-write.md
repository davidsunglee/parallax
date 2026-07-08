# m-batch-write — Set-Based / Batched Writes

`m-batch-write` specifies **set-based flushing of buffered writes**: at the
unit-of-work boundary, multiple pending writes of one entity collapse into
**set-based SQL** rather than one statement per row. It depends on `m-unit-work`
(the boundary that buffers and flushes the writes). The canonical golden SQL is
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

A **versioned** entity has no set-based `UPDATE` template — a per-row observed
version cannot ride one statement — so a set-based update of a versioned entity
**materializes** to per-object keyed updates instead (`m-opt-lock`). A set-based
**delete** of a versioned entity materializes the **same** way: it **cannot**
collapse into an `IN` list, because each row's delete must **gate on that row's
observed version** (`delete from t where id = ? and version = ?`, one statement per
key), and a per-key `≠1`-row outcome is the `updatedRows != 1` conflict — mirroring
the versioned `UPDATE` exactly (`m-opt-lock`, ADR 0014). Reladomo gates deletes
per row and never collapses a versioned delete; Parallax follows.

## Beyond current scope

Broader **predicate-driven** bulk mutation — `setAttribute` over a list,
`deleteAll` / `deleteAllInBatches`, `insertAll` / `bulkInsertAll`, dated
`terminateAll` / `purgeAll` — is out of scope for this revision. It is named here
so the module boundary is clear; its golden-SQL forms and fixtures land with the
bulk fast-follow.

This deferred family is the mutation of an **unbounded set resolved by a
predicate** — distinct from the **in-unit-of-work set-based flush** above, which
collapses the *buffered writes of already-tracked objects* the unit of work holds.
The DELETE collapse and the versioned per-key delete are part of that in-UoW
flush (a bounded, enumerated set of tracked deletes) and are therefore **in
scope**; `deleteAll` / `deleteAllInBatches` (a `DELETE … WHERE <predicate>` over
rows the unit of work never loaded) stay deferred. The two do not overlap.
