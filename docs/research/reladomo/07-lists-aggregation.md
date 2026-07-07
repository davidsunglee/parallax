# Lists are lazy operation-backed views; `AggregateList` runs GROUP BY/HAVING (in SQL or in-memory)

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/`.

Every generated typed list (e.g. `OrderList`) extends `DelegatingList`
(`mithra/list/DelegatingList.java:86`), forwarding all `List` methods to a swappable
`MithraDelegatedList`. Two delegate forms exist: **operation-based (lazy)**
(`AbstractOperationBasedList`) and **non-operation-based (adhoc, mutable)**
(`AbstractNonOperationBasedList`). A lazy list resolves on first access via `resolveOperation()`
(`mithra/list/AbstractOperationBasedList.java:204-233`), which calls
`portal.findAsCachedQuery(op)`; `forceResolve()` triggers it explicitly, `forEachWithCursor()` streams
from the DB, and `asAdhoc()` copies the resolved items into a mutable list.

Set-oriented operations (transactional lists, `AbstractTransactionalOperationBasedList`):

| Operation | Mechanism |
|---|---|
| Bulk `setAttribute` | resolve list, call `attr.setXValue(item, v)` per item (multi-update buffered in tx) |
| `deleteAll` | `DeleteAllTransactionalCommand` → `tx.deleteUsingOperation(op)` (single `DELETE … WHERE`) |
| `deleteAllInBatches` | retry-loop command; halves batch size on rollback |
| `insertAll` / `bulkInsertAll` | `InsertAllTransactionalCommand` (+ bulk-insert threshold) |
| `cascadeInsertAll` / `…DeleteAll` / `…TerminateAll` | walk dependent relationships |
| `terminateAll` / `purgeAll` | dated equivalents of delete |

**Aggregation** uses a separate `AggregateList` (`mithra/AggregateList.java:38`, not a `MithraList`).
The user registers named aggregate attributes, group-bys, and an optional having operation:

```java
AggregateList list = new AggregateList(BalanceFinder.businessDate().eq(date));
list.addGroupBy("account", BalanceFinder.accountNum());
list.addAggregateAttribute("sumValue", BalanceFinder.value().sum());
list.setHavingOperation(BalanceFinder.value().sum().greaterThan(100.0));
```

It resolves lazily through `portal.findAggregatedData(...)`. There are two paths: an **in-memory**
aggregation (`MithraAbstractObjectPortal.aggregateInMemory()`, line 1121) used when the underlying
objects are already cached and all group-bys are to-one; otherwise a **SQL** path
(`MithraAbstractDatabaseObject.findAggregatedData()`, line 2313) building an `AggregateSqlQuery`. The
SQL produced for the example:

```sql
SELECT t0.account_num, sum(t0.value)
FROM balance t0
WHERE t0.business_date_from <= ? AND t0.business_date_to > ?
GROUP BY t0.account_num
HAVING sum(t0.value) > ?
```

Each row is an `AggregateData` (`Object[] values` indexed by an `AggregateDataConfig`). Supported
functions (via per-type calculators in `mithra/attribute/calculator/aggregateFunction/`): `sum`,
`avg`/`mean`, `count`, `min`/`max` (numeric, string, date, timestamp, time, boolean, char),
`standardDeviationSample`/`Population`, `varianceSample`/`Population` (the stddev/variance functions
read two result columns). HAVING comparators: `eq`, `notEq`, `greaterThan(Equals)`, `lessThan(Equals)`,
composable with AND/OR.

## Testing patterns

`aggregate/AggregateTestSuite.java` aggregates `TestAggregateList`, `TestAggregationWithHavingClause`,
`TestAggregateListWithOrderBy`, `TestAggregateWithNull`, `TestDatedAggregation`, and `AggregateBeanList`
variants. List/bulk operations: `TestTransactionalList`, `TestTransactionalAdhocFastList`,
`TestDetachedListUsesCache`.

## Code references

- `mithra/MithraList.java`, `MithraTransactionalList.java`; `mithra/list/DelegatingList.java` (86), `AbstractOperationBasedList.java` (resolveOperation 204), `AbstractTransactionalOperationBasedList.java`, `AbstractNonOperationBasedList.java`
- `mithra/list/*TransactionalCommand.java` (DeleteAll, DeleteAllInBatches, InsertAll, CascadeInsertAll, TerminateAll)
- `mithra/AggregateList.java` (38), `AggregateData.java`, `AggregateDataConfig.java`, `MithraAggregateAttribute.java`, `AggregateAttribute.java`, `GroupByAttribute.java`, `HavingOperation.java`
- `mithra/finder/AggregateSqlQuery.java`; `mithra/attribute/calculator/aggregateFunction/` (Sum/Avg/Count/Min/Max/StdDev/Variance calculators); `mithra/aggregate/operation/Having*`
- `reladomographql/docs/aggregation.md`
