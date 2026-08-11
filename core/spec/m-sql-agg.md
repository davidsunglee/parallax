# m-sql-agg — SQL Lowering for Aggregation (deferred)

**Status: deferred.** `m-sql-agg` is the SQL lowering of the aggregation algebra
(`m-agg`): the `GROUP BY` / `HAVING` `SELECT`, the per-function emission (`sum` →
`sum(t0.col) <as>`, the `stdDev*` / `variance*` two-column read, and so on), and
the having-clause bind order. It is split out of core SQL generation so that
`m-sql` never references aggregation constructs.

Aggregation is deferred **as a whole feature**: no active module depends on
`m-sql-agg`.

- **Edges:** `m-sql-agg --> m-agg`, `m-sql-agg --> m-sql`.
- **Coverage.** This deferred module is contract-covered and carries no
  compatibility fixtures. Its future implementation must define and fixture the
  grouped `select`, aggregate-expression aliases, companion sample-count columns
  for `stdDev*` / `variance*`, and `having` bind order together with the aggregate
  query envelope that invokes them.
