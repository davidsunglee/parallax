# m-bitemp-write — Bitemporal Rectangle-Split Writes

`m-temporal-write` owns the Bitemporal profile: the rectangle split, plain
unbounded writes, observed and caller-addressed writes over their requested
extents, rectangles the attempt opened, address and gate, and the MAY-tier
mutations. This module remains only for the topology table the Write Planner
still reads to settle an observed keyed write inside its rectangle and a
Materialized Write Group; it depends on `m-txtime-write`.

## Topology table

For one authored mutation the table names neutrally — no SQL, dialect, physical
column, or statement — what `m-temporal-write` *Temporal expansion* settles for a
lone rectangle:

- the **Close Cause** — `Superseded` for `update` / `updateUntil`, `Terminated`
  for `terminate` / `terminateUntil`;
- the **gate basis** — the observed `txStart` an optimistic inactivation binds;
  and
- the **successors**, in the canonical order `head`, `middle`, `tail`, each
  bounded by the mutation's own `validFrom` / `until` or the predecessor's own
  Valid-Time start and end: a `CarriedFrom` head and a `ChangedFrom` tail for an
  `update`; a carried head, a changed middle, and a carried tail for an
  `updateUntil`; only the carried survivors for a `terminate` or
  `terminateUntil`.

It describes one authored mutation, never one resolved row, and states nothing
those rules do not. An `insert` or `insertUntil` reads no table: it opens its
new lineage directly (`m-temporal-write` *Temporal expansion*).
