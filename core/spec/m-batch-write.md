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

The canonical Postgres golden SQL (`m-sql`):

```text
insert into account(id, owner, balance) values (?, ?, ?), (?, ?, ?), (?, ?, ?)

update account set balance = ? where id in (?, ?)
```

The suite proves the batched forms against real data by **applying** the golden
DML and asserting the resulting table state — the write-sequence machinery
(`m-case-format`), reused for the non-temporal batched case (cases
`m-batch-write-001` / `m-batch-write-002`). So "buffered writes flush as set-based
SQL" is verified by the rows it leaves behind, not merely asserted.

A **versioned** entity has no set-based `UPDATE` template — a per-row observed
version cannot ride one statement — so a set-based update of a versioned entity
**materializes** to per-object keyed updates instead (`m-opt-lock`).

## Beyond current scope

Broader bulk mutation — `setAttribute` over a list, `deleteAll` /
`deleteAllInBatches`, `insertAll` / `bulkInsertAll`, dated `terminateAll` /
`purgeAll` — is out of scope for this revision. It is named here so the module
boundary is clear; its golden-SQL forms and fixtures land with the bulk fast-follow.
