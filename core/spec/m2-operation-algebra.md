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

`deepFetch` (eager relationship fetch) is introduced with relationships in a
later phase.

## Forward map of the rest of the algebra

For orientation, later phases fill in:

- Relationship: `navigate(rel) → predicate`, `exists`, `notExists`, the
  `in(subquery)` membership form, and the `deepFetch` directive.
- Temporal (M7): `asOf`, `asOfRange`, `history`.
- Aggregate (M2 sub-area): `sum`/`avg`/`count`/`min`/`max`/`stdDev*`/`variance*`,
  `groupBy`, and having comparators.
