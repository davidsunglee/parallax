# m-op-list — Operation-Backed List Results

`m-op-list` specifies **operation-backed list results** — the collection an
implementation returns from a set-based query. Per the dependency graph,
`m-op-list` depends on `m-op-algebra` (a list is backed by an operation) and
`m-unit-work` (it resolves within a unit of work). Relationships sit *above*
lists: navigation yields lists and deep fetch populates them, so `m-navigate`
depends on `m-op-list` (the reverse of the obvious guess).

## Operation-backed lazy list results (`findMany`)

A set-based query returns a **list bound to an operation**, not an eagerly
materialized array. The canonical entry point is `findMany(operation)`:

- The result is an **operation-backed view**. Constructing it performs **no**
  database work; it carries the `m-op-algebra` operation it will resolve.
- It resolves **lazily on first access** (iteration, indexing, size) within the
  unit of work. Resolution issues the query and materializes the result.
- Resolution is **idempotent and stable**: re-accessing an already-resolved list
  does not re-query.

Where the **process caches** (`m-process-cache`) are present, resolution is served
from the query cache with **no** round trip on a repeated equal operation, and
identity is preserved — two lists resolving to the same primary key yield the
**same** logical object. Those cross-find guarantees are `m-process-cache`
(deferred); the list-core contract above holds independently of them.

This laziness is what makes the deep-fetch round-trip guarantees (`m-deep-fetch`)
observable: because a list defers resolution and a deep fetch issues one statement
per relationship level, the harness can count statements and prove that populating
an already-fetched relationship does not fan out.

### Observable contract

| Aspect | Rule |
|---|---|
| Construction | side-effect-free; no SQL |
| First access | resolves once within the unit of work |
| Re-access | no re-query (stable result) |
| Deep-fetch population | a deep fetch (`m-deep-fetch`) populates the relationship lists in `1 + L` statements |

The compatibility suite expresses the list-core contract through the deep-fetch
cases: the assembled object graph **is** the populated list result, and the
round-trip-count assertion proves the lazy resolution did not fan out.
