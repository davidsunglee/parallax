# M5 — Lists & Bulk/Set Operations

`M5` specifies **operation-backed list results** — the collection an
implementation returns from a set-based query. Per the dependency graph, `M5`
depends on `M2` (a list is backed by an operation) and `M8` (it resolves through
the unit-of-work / query cache). Relationships sit *above* lists: navigation
yields lists and deep fetch populates them, so `M4` depends on `M5` (the reverse
of the obvious guess). Bulk/set mutation and cascade are **deferred** (noted at
the end, not specified here).

## Operation-backed lazy list results (`findMany`)

A set-based query returns a **list bound to an operation**, not an eagerly
materialized array. The canonical entry point is `findMany(operation)`:

- The result is an **operation-backed view**. Constructing it performs **no**
  database work; it carries the M2 operation it will resolve.
- It resolves **lazily on first access** (iteration, indexing, size). Resolution
  runs the operation through the query cache (M8): a cache hit returns the
  already-interned objects with **no** round trip; a miss issues the query and
  interns the results.
- Resolution is **idempotent and stable**: re-accessing a resolved list does not
  re-query. Identity is preserved — two lists resolving to the same primary key
  yield the **same** logical object (M8 identity cache).

This laziness is what makes the deep-fetch round-trip guarantees (M4) observable:
because a list defers and a resolved query is cached, the harness can count
statements and prove that navigating an already-fetched relationship costs **zero**
additional round trips.

### Observable contract

| Aspect | Rule |
|---|---|
| Construction | side-effect-free; no SQL |
| First access | resolves once via the query cache (M8) |
| Re-access | no re-query (stable result) |
| Identity | one logical object per primary key across all lists |
| Deep-fetch population | a deep fetch (M4) populates the relationship lists in `1 + L` statements |

The compatibility suite expresses the list-core contract through the deep-fetch
cases: the assembled object graph **is** the populated list result, and the
round-trip-count assertion proves the lazy/cached resolution did not fan out.

## Minimal dependent cascade-delete witness

Broader bulk/set mutation and cascade APIs remain deferred, but the compatibility
corpus includes one **minimal `cascadeDelete` witness** over an M1
`dependent: true` relationship graph. The case is intentionally narrow: deleting
an owning root deletes dependent child rows before the root row, then asserts the
remaining table state. It pins the observable dependent-delete ordering without
claiming support for Reladomo's full cascade or bulk mutation surface.

The witness reuses the M12 `writeSequence` shape. Its `cascadeDelete` mutation
name documents intent; the harness applies the authored ordered DML and compares
the resulting rows.

## Deferred: broad bulk/set mutation and cascade

The following are **out of scope for this revision** and specified in a later
tier (fast-follow):

- **Bulk mutation** — `setAttribute` over a list, `deleteAll` /
  `deleteAllInBatches`, `insertAll` / `bulkInsertAll`, dated `terminateAll` /
  `purgeAll`.
- **Broad cascade** — `cascadeInsertAll` / `cascadeDeleteAll` /
  `cascadeTerminateAll`, which walk **dependent** relationships (M1
  `dependent: true`) across the full Reladomo API surface. Cascade is a
  capability layered *above* M4 (it traverses dependents), kept separate from the
  list-core so the dependency graph stays acyclic.

They are named here so the module boundary is clear; their golden-SQL forms and
fixtures land with the bulk/cascade fast-follow, apart from the minimal
dependent cascade-delete witness above.
