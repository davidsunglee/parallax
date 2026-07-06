# m-sql-agg — SQL Lowering for Aggregation (deferred)

**Status: deferred.** `m-sql-agg` is the SQL lowering of the aggregation algebra
(`m-agg`): the `GROUP BY` / `HAVING` `SELECT`, the per-function emission (`sum` →
`sum(t0.col) <as>`, the `stdDev*` / `variance*` two-column read, and so on), and
the having-clause bind order. It is split out of core SQL generation so that
`m-sql` never references aggregation constructs.

Aggregation is deferred **as a whole feature**: no active module depends on
`m-sql-agg`.

- **Edges:** `m-sql-agg --> m-agg`, `m-sql-agg --> m-sql`.
- **Behavioral floor.** The aggregate golden SQL is pinned by cases
  `m-agg-001`–`m-agg-018` (which carry both `m-agg` and `m-sql-agg` tags): the
  grouped `select`, the aggregate-expression emission with `<as>` aliases, the
  companion sample-count column for `stdDev*` / `variance*`, and the
  `having` binds appended after any `where` binds. That floor stays green; the
  full lowering specification is deferred beyond it.
