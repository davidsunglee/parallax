# m-agg — Aggregation Algebra

`m-agg` owns an aggregation query form separate from Object Query. Its query
envelope names a target Entity, an optional source predicate, an ordered `groupBy`
list, an ordered non-empty aggregate list, an optional `having` expression, and
optional aggregate-row ordering and limiting. An empty or omitted `groupBy` list
denotes one ungrouped result row. Each aggregate
has a caller-supplied unique alias and one function from `sum`, `avg`, `count`,
`min`, `max`, `stdDevSample`, `stdDevPop`, `varianceSample`, or
`variancePop`; every function except row `count` names one Attribute.
`having` may reference group keys and aggregate aliases, but it does not admit
Object Query result directives or relationship navigation.

The result is row-form. Each row contains the group keys followed by aggregate
values in envelope order, keyed by their declared names and aliases. It never
materializes an Entity instance and never accepts an Object Query projection.
The SQL lowering of this envelope is owned by the sibling module `m-sql-agg`.

- **Edge:** `m-agg --> m-predicate`. The source predicate uses the predicate
  subset of that algebra; aggregate-row ordering references group-key names or
  aggregate aliases rather than Entity Attributes.
- **Schema surface.** The aggregate query envelope requires its own closed
  interchange schema rather than alternatives in Object Query's operation schema.
- **Read-lock suppression.** An aggregation read never carries the shared read-lock
  suffix (`m-read-lock` / `m-sql`): a grouped / aggregate result has no identifiable
  base row to lock.
- **Fixture obligations.** Compatibility fixtures **MUST** cover every aggregate
  function, aliases that differ from Attribute names, grouped and ungrouped row
  shapes, `having` over both a group key and an aggregate alias, bind ordering,
  empty-input behavior, and rejection of duplicate aliases or illegal
  references. SQL fixtures **MUST** carry both canonical statements and
  independent result oracles.
