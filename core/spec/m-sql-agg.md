# m-sql-agg — SQL Lowering for Aggregation

`m-sql-agg` lowers the aggregate query envelope owned by `m-agg`. It is split
from core SQL generation so `m-sql` never references aggregation constructs.

- **Edges:** `m-sql-agg --> m-agg`, `m-sql-agg --> m-sql`.
- **Select shape.** Group keys lead the `select` list in envelope order, followed
  by aggregate expressions in envelope order. Every expression uses its declared
  alias. `stdDev*` and `variance*` additionally select a collision-safe companion
  sample-count alias so result decoding can distinguish an empty sample from a
  database-specific numeric representation.
- **Clauses.** The canonical statement order is `select`, `from`, optional
  `where`, optional `group by`, optional `having`, then ordering or limiting
  owned by the aggregate envelope. `group by` terms follow group-key order.
- **Binds.** Source-filter binds precede `having` binds; within `having`, binds
  follow expression traversal order. Alias references in `having` lower through
  their aggregate expressions when a dialect does not admit select aliases in
  that clause.
- **Ownership.** `m-agg` validates envelope shape, names, and result rows;
  `m-sql-agg` resolves Attributes, renders aggregate functions and aliases, and
  decodes companion sample counts. `m-sql` supplies ordinary predicate and
  dialect primitives without importing this module.
- **Fixture obligations.** Golden SQL **MUST** cover grouped and ungrouped
  queries, every function family, companion columns, `having` bind order, alias
  collisions, and both supported dialects; execution fixtures **MUST** assert
  the corresponding row-form values.
