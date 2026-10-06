# m-txtime-write — Transaction-Time-Only Temporal Writes

`m-temporal-write` owns the Transaction-Time-Only profile: milestone chaining,
rows the attempt opened, caller-addressed writes, the Milestone Target, the
affected-row conflict contract, and statement order. This module remains only
for the topology table the Write Planner still reads to settle an observed keyed
write and a Materialized Write Group; it depends on `m-temporal-read` and
`m-unit-work`.

## Topology table

For one authored mutation the table names neutrally — no SQL, dialect, physical
column, or statement — what `m-temporal-write` *Temporal expansion* settles for a
lone milestone:

- the **Close Cause** — `Superseded` for an `update`, `Terminated` for a
  `terminate`;
- the **gate basis** — the observed `txStart` an optimistic close binds; and
- the **successors** — the one chained current row of an `update`, `ChangedFrom`
  its predecessor, and none for a `terminate`.

It describes one authored mutation, never one resolved row, and states nothing
those rules do not. An `insert` reads no table: it opens its new lineage
directly (`m-temporal-write` *Temporal expansion*).
