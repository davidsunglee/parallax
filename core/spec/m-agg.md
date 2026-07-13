# m-agg — Aggregation Algebra (deferred)

**Status: deferred.** `m-agg` is the aggregation extension of the operation
algebra — the `groupBy` node with its aggregate functions (`sum` / `avg` /
`count` / `min` / `max` / the `stdDev*` / `variance*` family) and its `having`
group filter. The SQL lowering of these nodes is the separate deferred module
`m-sql-agg`.

Aggregation is deferred **as a whole feature**: no active module depends on
`m-agg`, and core SQL generation (`m-sql`) never references aggregation
constructs.

- **Edge:** `m-agg --> m-op-algebra`.
- **Behavioral floor.** The `groupBy` / aggregate / `having` nodes are present in
  [`operation.schema.json`](../schemas/operation.schema.json), and cases
  `m-agg-001`–`m-agg-018` pin their golden SQL and result rows (including the
  two-column read for `stdDev*` / `variance*` and the `having` bind order). That
  floor stays green; the full algebra specification is deferred beyond it.
- **Read-lock suppression.** An aggregation read never carries the shared read-lock
  suffix (`m-read-lock` / `m-sql`): a grouped / aggregate result has no identifiable
  base row to lock. The in-transaction witnesses for this land with this module's
  implementation.
