# Deep fetch batches relationship traversal into one query per level, eliminating N+1

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/`.

Relationships are `Mapper`-backed at runtime; navigating `order.getItems()` executes a query against
the child type constrained to the parent's FK values. Deep fetch is driven by a `DeepFetchNode` tree
mirroring the user's `deepFetch(Nav)` calls (`finder/DeepFetchNode.java`), where each node owns a
`DeepFetchStrategy` chosen by `AbstractRelatedFinder.zGetDeepFetchStrategy()`:

| Relationship | Strategy |
|---|---|
| simple to-one | `SimpleToOneDeepFetchStrategy` |
| simple to-many | `SimpleToManyDeepFetchStrategy` |
| complex/multi-hop | `ChainedDeepFetchStrategy` (decomposes the `LinkedMapper` into per-hop delegates) |

The key method is `SingleLinkDeepFetchStrategy.mapOpToList()` (`finder/SingleLinkDeepFetchStrategy.java:106-113`):
it builds one `MappedOperation` covering **all** parents and calls `findMany()` once. Results are
fanned back out to per-parent buckets by `associateResultsWithOps()` (lines 171-210), which calls
`mapper.getOperationFromResult(related)` per row, and each per-parent op is cached so later navigation
hits the query cache (`cacheResults()`, lines 142-168). For small parent lists (< `MAX_SIMPLIFIED_IN = 1000`),
a simplified `IN (...)` query is used; for larger/multi-attribute keys, a temp-table join
(`deepFetchWithTempContext`).

Worked example — `orders.deepFetch(items); orders.deepFetch(orderStatus)` over 1,000 orders:

```text
root query           : SELECT * FROM order WHERE <pred>                    (1)
items (to-many)      : SELECT * FROM order_item WHERE ORDER_ID IN (1..1000) (1)
orderStatus (to-one) : SELECT * FROM order_status WHERE ORDER_ID IN (1..1000)(1)
                       → 3 queries total, not 1 + 1000 + 1000 = 2001
```

Dependent (cascade) relationships are walked via `DeepRelationshipUtility.getDependentRelationshipFinders()`;
reverse relationships resolve in-memory in `MappedOperation.applyOperation()` by building a
`ConcurrentFullUniqueIndex` of right-hand objects and matching left→right
(`finder/MappedOperation.java:157-198`).

## Testing patterns

`TestAdhocDeepFetch.java` is the primary suite; it asserts the exact DB-query count using the
before/after `getRetrievalCount()` pattern (e.g. `assertEquals(count+2, …)` for items+status) and
covers multi-attribute FK fetch and bitemporal temp-table paths. `TestDeepFetchExternalClose.java`
covers cursor/connection lifecycle.

## Code references

- `DeepFetchNode.java` (deepFetch 230), `DeepFetchStrategy.java`, `SingleLinkDeepFetchStrategy.java` (mapOpToList 106), `SimpleToOneDeepFetchStrategy.java`, `SimpleToManyDeepFetchStrategy.java`, `ChainedDeepFetchStrategy.java`, `DeepRelationshipUtility.java` (MAX_SIMPLIFIED_IN 41)
