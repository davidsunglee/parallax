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

`m-batch-write` decides only **compatibility**: whether two buffered writes may
share one step. The Planned Write algebra, the flush's stage order, and the
affected-row policy that step then carries are `m-unit-work`'s; this module
reaches planning through the strategy port that module declares.

## Batching is a membership decision

Batching is expressed by **membership in one Planned Write**, not by a marker on
several. Compatible inserts become one Planned Insert with several entries;
compatible uniform keyed updates or deletes become one Planned Update or Planned
Delete whose Key Target holds several key tuples.

- An implementation **MUST NOT** introduce a batch flag, batch identifier, group
  wrapper, or per-row batch annotation. Two writes either share a step or they do
  not, and that is the whole of the decision.
- Incompatible writes remain **separate logical steps**. In particular a
  **per-row gated** write (`m-opt-lock`) can never join another: its gate binds
  one row's observed version, so each stays its own step even where a driver
  later transmits several in one batch.
- Batching shares the canonical member shape and uniform values across the step;
  it **MUST NOT** deep-copy one assignment payload per addressed row.
- Membership does not change semantics. One multi-key Key Target owns **one
  aggregate** affected-row expectation for the rows it names (`m-unit-work`);
  collapsing writes together never weakens or discards that expectation.

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
# m-batch-write-004 (versioned delete materializes per key, locking mode) then.statements:
- sql:
    postgres: delete from account where id = ?
```

The suite proves the batched forms against real data by **applying** the golden
DML and asserting the resulting table state — the write-sequence machinery
(`m-case-format`), reused for the non-temporal batched case (cases
`m-batch-write-001` / `m-batch-write-002` for the insert/update collapse,
`m-batch-write-003` for the DELETE collapse, `m-batch-write-004` for the versioned
per-key delete). So "buffered writes flush as set-based SQL" is verified by the
rows it leaves behind, not merely asserted.

A **versioned** entity has no readless predicate-write template. Every one of its
writes against an existing row requires that row's own prior observation, in
**both** concurrency modes — optimistic mode binds it as that row's gate, locking
mode needs the read that took its shared lock — and one predicate statement can
neither carry nor acquire one. Predicate update and delete therefore materialize
to keyed writes (`m-opt-lock`). Transaction-Time temporal predicate
writes likewise materialize so each observed milestone can close/chain
(`m-txtime-write` / `m-bitemp-write`). Those are not buffered-batch collapse rules.

A materializing predicate write resolves **before** planning and enters it as one
**Materialized Write Group** (`m-unit-work`) — one authored mutation, one shared
key shape, aligned key and observation columns. Batching treats that group as
**indivisible**: it is never split across steps, never merged with an unrelated
buffered instruction, and never regrouped by statement kind, and it survives no
further than finalization. It is an input to planning, not a member of a Write
Plan, so no group wrapper or identifier reaches the flush.

## Predicate-selected readless forms

For an **unversioned, non-temporal** target, a predicate-selected write is
readless and emits exactly one statement unless it assigns a document-resident
`many` occurrence. That narrow combination is refused before buffering or SQL as
`predicate-write-readless-document-many-unsupported`; it never falls back to a
planning-time read. Scalar and `one` assignments remain readless. `update` is:

```text
update <table> set <column> = ?, … where <predicate>
```

There is no materialization and no equality-elimination pass: rows already equal
to an assigned value are still matched by ordinary SQL set semantics. The
emitted `set` columns and their assignment-value binds follow `m-sql`'s physical
DML rule: filter the assigned cells from the target Entity Layout in Table
Layout order, regardless of the instruction's ordered assignment list.
Predicate binds come after those assignment binds. `delete` is exactly:

```text
delete from <table> where <predicate>
```

`m-batch-write-005` pins readless predicate delete and
`m-batch-write-006` pins the update's layout-order SQL and bind determinism.
Reladomo's transaction behavior remains prior art for the materializing branch:
it reads under a lock or gates on an observed optimistic version, not a Java bulk
API template. Parallax applies that runtime rule through the owning modules above.

A readless statement that **matches zero rows succeeds with zero affected rows —
never an error.** Ordinary SQL set semantics already make `update … where
<predicate>` and `delete … where <predicate>` no-ops when nothing matches; a
predicate-selected write that matches nothing simply wrote nothing, the same way
a materializing verb's resolving read matching zero rows emits zero keyed writes
and succeeds (`m-opt-lock`). This is categorically distinct from the shortfall an
**observation-backed** per-row write raises (`m-opt-lock` / `m-txtime-write`),
which fires when a row the caller **did** match and observe was concurrently
changed underneath it. Both concurrency modes raise it, and the settled gate
decides which one it is: a gated shortfall is an Optimistic Conflict, an ungated
one a Stale Write (`m-unit-work`). Matching nothing is never either.

### A readless predicate write is an ordering barrier

A readless predicate write **MUST** keep its authored position in the flush. It
partitions the buffered sequence into **regions**: the writes before it and the
writes after it. Batching and dependency ordering (`m-unit-work`) apply freely
**within** each region — order there is unconstrained, so the collapse and
foreign-key rules operate exactly as they otherwise would — but **no write may
cross the barrier in either direction**.

Unlike a keyed or materialized write, a readless predicate never reveals which
rows it touches: its read/write set is whatever the predicate matches at
execution time. Moving another write across it could therefore change which rows
it matches, and so change what the transaction wrote. Treating the whole buffer
as globally reorderable could produce larger batches, but only by assuming a
non-overlap no implementation can prove.

The barrier is **planning structure only**. It introduces no group, wrapper,
flag, or identifier into the emitted result; the sole observable is that the
emitted statement order never carries a write past a readless predicate write.

## What the suite pins down

The existing `m-batch-write-001`–`-004` cases prove only **buffered tracked-row
batching**: multi-row insert, uniform-key update, non-versioned `IN` delete, and
versioned per-key delete. The predicate-write witnesses prove a distinct target:

| Case | Target | Predicate-write witness |
|---|---|---|
| `m-batch-write-005` | non-versioned `Wallet` delete | one readless `delete … where <predicate>` |
| `m-batch-write-006` | non-versioned `Wallet` update | one readless update; reversed authored assignments still emit Entity Layout order and assignment-before-predicate binds |
| `m-batch-write-009` | unversioned, non-temporal document-mapped `Voyage` update | refuse a top-level document-resident `many` assignment before buffering or SQL |
| `m-batch-write-010` | unversioned, non-temporal document-mapped `Route` update | refuse an authored nested document-resident `many` assignment while an omitted sibling `many` does not trigger the rule |
| `m-opt-lock-015` | versioned `Account` delete | materialize plus one optimistic per-row delete for each match |

The two families share SQL terminology but not an observation contract: an `IN`
list can collapse an already tracked set, whereas a predicate write starts from an
operation and either remains readless or materializes because its target requires
per-row observation.
