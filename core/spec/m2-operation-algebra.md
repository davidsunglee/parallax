# M2 — Query, Operation & Aggregation Algebra

`M2` defines the **operation algebra** — the framework's own query language — and
its **canonical serialization**. The algebra *is* the protocol: the
compatibility suite's queries are instances of it, and every implementation
ships a serde module that round-trips them. `M2` depends on `M1` (operations are
bound to metamodel attributes).

The canonical schema is
[`core/schemas/operation.schema.json`](../schemas/operation.schema.json).

## Positioning (DQ13)

The core defines **its own higher-level, metamodel-bound algebra** rather than
adopting a SQL-oriented IR (SQLGlot, Substrait) as the core representation. The
algebra is deliberately *above* SQL:

- Relationship traversal is a **single navigation** (`Order.items`), not a
  user-written join with ON-conditions.
- Temporal joins (the per-axis `<`/`<=`/`>`/`>=` as-of predicates) are
  **auto-injected** from the as-of model, never written by the user.

A SQL IR forces those joins and predicates to be explicit — the wrong
abstraction level for a finder language. The algebra translates **down** to SQL
(M3); a language **MAY** implement M3 by lowering this algebra onto an external
SQL IR to get many dialects "for free", but that is a per-language decision
behind the M3 seam, not a core mandate.

## Canonical operation encoding (serde seam)

An operation is a tree of **nodes** with a **format-agnostic canonical
serialization**. This serialized form is the suite's normative encoding — one
source of truth so every implementation tests the same operation. Concrete
encodings exist in at least **JSON and YAML** (a format-agnostic core plus
pluggable writers); the format set is consistent with metamodel serde (M1).

Every implementation **MUST** ship a serde module whose sole job is operation
serialize/deserialize, with **round-trip** tests:
`serialize(deserialize(op)) == op`. The reference harness asserts this per case,
in both JSON and YAML. Idiomatic per-language re-expressions of a query (fluent
builders, etc.) are **illustrative only** — never the normative encoding.

The encoding is a tagged object: each node is a single-key object whose key names
the operation. Attribute references are `Class.attribute` strings, resolved
against the model. Examples:

```json
{ "all": {} }
```

```json
{ "eq": { "attr": "Order.id", "value": 42 } }
```

## Operation set (this phase)

This phase completes the **full non-temporal predicate algebra for single-entity
queries**, plus the result-shaping directives. Each node below carries a single
canonical serialization; an implementation **MUST** support every node and
**MUST** round-trip it through serde unchanged.

### Identities

| Operation | Encoding | Meaning |
|---|---|---|
| `all` | `{ "all": {} }` | the identity — selects every row (no `WHERE`) |
| `none` | `{ "none": {} }` | the absorbing element — matches nothing |

`none` is the dual of `all`; it lowers to an unsatisfiable predicate.

### Equality and range

Each takes `{ "attr": "Class.attribute", "value": <literal> }`. The value becomes
a bind placeholder in the golden SQL.

| Operation | SQL operator |
|---|---|
| `eq` | `=` |
| `notEq` | `<>` |
| `greaterThan` | `>` |
| `greaterThanEquals` | `>=` |
| `lessThan` | `<` |
| `lessThanEquals` | `<=` |

`between` is a convenience over a bounded pair and takes
`{ "attr", "lower", "upper" }`; it lowers to `attr between ? and ?` (two ordered
binds: lower, then upper) and is equivalent to `>= lower AND <= upper`.

### Null

`isNull` / `isNotNull` take `{ "attr": "Class.attribute" }`. Per SQL three-valued
logic, `isNotNull` excludes NULL rows; `notLike`/`notIn`/`notEq` against a NULL
column likewise yield NULL (not true) and so exclude that row.

### String

The string predicates take `{ "attr", "value", "caseInsensitive"? }`
(`caseInsensitive` defaults to `false`).

| Operation | Pattern semantics |
|---|---|
| `like` / `notLike` | `value` **is** the SQL pattern: `%` and `_` are wildcards |
| `startsWith` | `value` is a **literal** prefix ⇒ pattern `value%` |
| `endsWith` | `value` is a **literal** suffix ⇒ pattern `%value` |
| `contains` | `value` is a **literal** infix ⇒ pattern `%value%` |

**Wildcard / escape rule.** For the affix forms (`startsWith`/`endsWith`/
`contains`) the implementation **MUST** escape any `%`, `_`, or escape character
occurring in the literal `value` before wrapping it with the affix wildcards, so
the literal matches literally. The canonical escape character is the backslash
(`\`), rendered with an explicit `escape ?` (or `escape '\'`) clause whenever the
pattern contains an escape sequence. `like`/`notLike` do **not** escape — their
`value` is already a pattern.

**Case-insensitive rule.** When `caseInsensitive` is `true`, both the column and
the pattern are folded with `lower(...)`: `lower(attr) like lower(?)`. (A language
MAY use a dialect-native case-insensitive operator behind the M3 seam; the golden
SQL fixes the portable `lower(...)` form.)

### Membership

`in` / `notIn` take `{ "attr", "values": [ … ] }` (non-empty). Each value is a
bind, in list order; the SQL is `attr in (?, ?, …)`. The `in(subquery)` form is
introduced with relationships in a later phase.

### Boolean combinators

| Operation | Encoding |
|---|---|
| `and` | `{ "and": { "operands": [ op, op, … ] } }` (≥2 operands) |
| `or` | `{ "or": { "operands": [ op, op, … ] } }` (≥2 operands) |
| `not` | `{ "not": { "operand": op } }` |
| `group` | `{ "group": { "operand": op } }` |

Operand **order is significant** (it is preserved through serde and drives bind
order). The first-class **`group`** node explicitly nests a sub-expression so
precedence round-trips unambiguously: a *prefix* surface (`group(a.or(b)).and(c)`)
and a *fluent* surface (`a.or(b).group().and(c)`) are per-language DX only and
**MUST** serialize to the same canonical `group` node. Because `and` binds tighter
than `or`, `(a or b) and c` requires a `group`, whereas `a or b and c` parses as
`a or (b and c)` and needs none — the two are distinct canonical nodes with
distinct golden SQL.

### Result-shaping directives

Directives wrap an inner operation rather than filtering:

| Operation | Encoding | Effect |
|---|---|---|
| `orderBy` | `{ "orderBy": { "operand", "keys": [ { "attr", "direction"? } ] } }` | order rows; `direction` ∈ `asc` (default) / `desc` |
| `limit` | `{ "limit": { "operand", "count" } }` | cap the row count |
| `distinct` | `{ "distinct": { "operand" } }` | deduplicate rows |

## Relationship algebra

Relationships (M1) are traversed **by name** — never as a user-written join. A
navigation node references a relationship as `Class.relationship` and (for the
filter forms) carries an optional inner operation constraining the related
entity. These nodes lower to **correlated semi-joins** so a to-many traversal
never multiplies the queried entity's rows (M3, M4).

### Navigation filters

| Operation | Encoding | Meaning |
|---|---|---|
| `navigate` | `{ "navigate": { "rel", "op"? } }` | filter the queried entity by traversing `rel`; `op` (optional) constrains the related entity |
| `exists` | `{ "exists": { "rel", "op"? } }` | the queried entity has ≥1 related row (optionally matching `op`) |
| `notExists` | `{ "notExists": { "rel", "op"? } }` | the queried entity has no related row (optionally matching `op`) |

`rel` is a relationship reference of the form `Class.relationship`. `navigate`
and `exists` are the same correlated-`EXISTS` lowering (a navigation filter *is*
a positive existence check); `notExists` is the negated form. With no `op`,
`exists`/`notExists` are pure existence/absence checks. The inner `op` is a
normal operation tree resolved **against the related entity's attributes**
(`OrderItem.sku`, …), so any predicate from the single-entity algebra composes
inside a navigation.

### `deepFetch` directive

`deepFetch` is an eager-fetch **directive**, not a predicate: it shapes the
result into an **object graph** rather than a flat row set.

| Operation | Encoding | Effect |
|---|---|---|
| `deepFetch` | `{ "deepFetch": { "operand", "paths": [ [rel, …], … ] } }` | resolve `operand`, then eager-fetch each navigation `path` |

Each `path` is an ordered list of relationship references naming a chain to
fetch — one hop (`["Order.items"]`) or multi-hop
(`["Order.items", "OrderItem.statuses"]`). The normative guarantee is **one SQL
statement per relationship level** (N+1 elimination): the root query plus one
statement per distinct relationship hop, regardless of how many parent rows fan
out. Paths sharing a prefix fetch the shared hop **once**. This is specified in
full in [M4](m4-relationships-deepfetch.md) and proven by the round-trip-count
layer of the compatibility harness (M12).

## Aggregation algebra (M2 sub-area)

Aggregation is **part of the same operation algebra**, not a separate module
(DQ13): a `groupBy` node groups an inner operation, names one or more **aggregate
functions** over attributes, and optionally filters the *groups* with a `having`
expression. It lowers to SQL via M3 exactly as the predicate algebra does — a
`GROUP BY` / `HAVING` query rather than a per-attribute calculation. An
aggregate query returns **aggregate rows** (group-key columns plus aggregate
values), not entity rows.

### Aggregate functions

An aggregate function names a metamodel attribute (or, for `count`, optionally
the group itself) and produces one output column per group. Each function node
is `{ "<fn>": { "attr": "Class.attribute", "as": "<outputName>" } }`. The `as`
field is the **result column name** — it is significant: it is the key under
which the aggregate value appears in `expectedRows`, and it is fixed across
languages so the suite is portable.

| Function | Meaning | Domain |
|---|---|---|
| `sum` | sum of values | numeric |
| `avg` | arithmetic mean | numeric |
| `count` | row count | any (or the whole group — see below) |
| `min` | minimum | numeric, string, date, time, timestamp |
| `max` | maximum | numeric, string, date, time, timestamp |
| `stdDevSample` | sample standard deviation (n − 1) | numeric |
| `stdDevPop` | population standard deviation (n) | numeric |
| `varianceSample` | sample variance (n − 1) | numeric |
| `variancePop` | population variance (n) | numeric |

`count` additionally accepts **no `attr`** — `{ "count": { "as": "n" } }` — to
count whole rows in the group (`count(*)`); with an `attr` it counts non-NULL
values of that attribute (`count(attr)`). `min`/`max` are defined over ordered
types — **numeric, string, date/time/timestamp** — so the suite exercises
min/max over each. The four `stdDev*`/`variance*` functions are numeric-only.

> **Two-column read for `stdDev*` / `variance*`.** Reladomo's standard-deviation
> and variance calculators read **two result columns** — the statistic itself and
> the sample **count** — so a caller can distinguish "no rows" / "one row" (where
> the sample statistic is undefined / NULL) from a real zero, and combine partial
> aggregates. The core preserves this: a `stdDev*`/`variance*` aggregate emits its
> statistic column **and** a companion `count` column in the golden SQL. M3 fixes
> the exact emission (see m3-sql-contract.md).

### `groupBy`

`groupBy` is the aggregation node. It wraps an inner `operand` (the rows to
aggregate — typically `all` or a predicate), a non-empty list of **aggregate
functions**, an optional list of **group-by keys** (attribute references), and an
optional **`having`** expression.

| Operation | Encoding |
|---|---|
| `groupBy` | `{ "groupBy": { "operand", "keys"?, "aggregates": [ fn, … ], "having"? } }` |

- `operand` — the inner operation whose result rows are aggregated.
- `keys` — ordered attribute references to group by. **Omitting `keys`** (or an
  empty list) is a single-group (whole-table) aggregate — `count`, global
  `min`/`max`, a global `stdDev*` — with no `GROUP BY` clause.
- `aggregates` — one or more aggregate-function nodes; their `as` names become the
  aggregate result columns (the group-key columns project under their own column
  names).
- `having` — an optional boolean expression over **aggregate comparisons** that
  filters the groups (below).

### Having comparators

`having` is a boolean expression whose leaves are **aggregate comparisons** — an
aggregate function compared against a literal — composable with the same `and` /
`or` combinators as the predicate algebra. A having comparison is
`{ "<cmp>": { "agg": <aggregateFn>, "value": <literal> } }`, where `agg` is an
aggregate-function node (it need not appear in the projected `aggregates`).

| Comparator | SQL operator |
|---|---|
| `eq` | `=` |
| `notEq` | `<>` |
| `gt` | `>` |
| `gte` | `>=` |
| `lt` | `<` |
| `lte` | `<=` |

The comparators are **named for the having context** (`gt`/`gte`/`lt`/`lte`)
rather than reusing the predicate algebra's `greaterThan…` tags, because they
compare an *aggregate function applied to a group* — not a bare attribute. A
`having` leaf and the predicate `and`/`or` junctions compose freely:
`{ "and": { "operands": [ {"gt": {"agg": …, "value": …}}, {"lte": {"agg": …, "value": …}} ] } }`.

The aggregate value in a having comparison becomes a **bind** in the golden SQL,
appended after any `WHERE` binds, in left-to-right `HAVING`-clause order.

## Forward map of the rest of the algebra

For orientation, later phases fill in:

- Membership: the `in(subquery)` form (a navigation-backed sub-operation).
- Temporal (M7): `asOf`, `asOfRange`, `history`.
