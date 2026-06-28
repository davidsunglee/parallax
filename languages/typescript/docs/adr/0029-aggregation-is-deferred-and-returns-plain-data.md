# Aggregation is deferred into project queries

The TypeScript V1 API defers aggregation even though aggregation is part of the core M2 operation algebra. When added, grouped aggregate reads should use the future `project(...)` operation surface rather than extending `find`.

`find` means "return managed domain objects." Projection queries mean "return plain data." Aggregate queries return grouped result rows made of group keys and aggregate values, not entity rows. Returning aggregate data through `find` would blur managed-object semantics and conflict with the decision that `find` does not return partial managed objects.

The future public verb is `project(...)`. Simple selective retrieval and grouped aggregation use the same plain-data query surface:

```ts
const summaries = await px.orders.project({
  where: Order.status.eq("Processing"),
  groupBy: [Order.customerId],
  select: {
    customerId: Order.customerId,
    orderCount: Order.id.count(),
    totalAmount: Order.totalAmount.sum(),
  },
  having: agg => agg.orderCount.gt(10),
  orderBy: agg => [agg.totalAmount.desc()],
});
```

Core may continue to describe the operation algebra sub-area as aggregation. The TypeScript user-facing API reserves `project(...)` for all non-managed-object query results.
