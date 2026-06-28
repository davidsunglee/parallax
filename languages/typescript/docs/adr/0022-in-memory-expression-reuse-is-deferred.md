# In-memory expression reuse is deferred

The TypeScript V1 API does not make Parallax predicates usable as native JavaScript `Array.filter` callbacks, and it does not make Parallax sort keys usable as native `Array.sort` or `Array.toSorted` comparators. Predicate and sort-key expressions are first-class query expressions; in-memory collection reuse is deferred.

The reason is relationship traversal. A predicate such as `Order.lineItems.exists(item => item.quantity.gt(2))` should not work in SQL but fail as soon as a user applies it to materialized objects. Supporting relationship traversal over objects requires async evaluation, batching, and clear interaction with includes and the identity cache. Native JavaScript collection callbacks are synchronous, so making only scalar predicates callable would create an unintuitive split.

A later API may add Parallax-owned async collection operations that accept the same predicates and sort keys over materialized or operation-backed lists. V1 avoids promising native callback compatibility until relationship traversal can "just work" without hidden N+1 behavior.
