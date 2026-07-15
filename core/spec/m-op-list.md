# m-op-list — Operation-Backed List Results

`m-op-list` specifies **operation-backed list results** — the collection an
implementation returns from a set-based query. Per the dependency graph,
`m-op-list` depends on `m-op-algebra` (a list is backed by an operation),
`m-unit-work` (it resolves within a unit of work), and `m-deep-fetch` (a lazy
list is *populated by* deep fetch — the same relationship `m-snapshot-read`
has with deep fetch). Lists sit *above* the shared fetch algorithm, not
underneath it: a navigation node used as a predicate inside an operation is a
semi-join and yields no list, so `m-navigate` carries no edge to `m-op-list` at
all; deep fetch populates the list instead, and this module's contract is what
makes that population's round-trip guarantees observable.

## Operation-backed lazy list results (`findMany`)

A set-based query returns a **list bound to an operation**, not an eagerly
materialized array. The canonical entry point is `findMany(operation)`:

- The result is an **operation-backed view**. Constructing it performs **no**
  database work; it carries the `m-op-algebra` operation it will resolve.
- It resolves **lazily on first access** (iteration, indexing, size) within the
  unit of work. Resolution issues the query and materializes the result.
- Resolution is **idempotent and stable**: re-accessing an already-resolved list
  does not re-query.

Where the **transaction-scoped identity map** (`m-identity-map`) is present, two
lists resolving the same identity key within one unit of work yield the **same**
logical object — the rows still round-trip; only the materialized objects
coalesce. Repeated-equal-operation round-trip *elimination* (a query cache) is
`m-process-cache` (deferred). The list-core contract above holds independently
of both.

This laziness is what makes the deep-fetch round-trip guarantees (`m-deep-fetch`)
observable: because a list defers resolution and a deep fetch issues one statement
per relationship level, the harness can count statements and prove that populating
an already-fetched relationship does not fan out. (A plain-value read is **not**
an operation-backed list — for snapshot graphs the same round-trip observability
is pinned by `m-snapshot-read` on its own materialization.)

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
