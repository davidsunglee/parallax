# M3 — SQL Generation & Equivalence Contract

`M3` is the contract that turns an M2 operation into per-dialect SQL, and the
rules that make "equivalent SQL per database" **testable**. `M3` depends on `M2`
(the algebra it lowers) and `M11` (the dialect that decides the concrete SQL).

The core does **not** mandate *how* an implementation produces SQL (a language
MAY lower the algebra onto an external SQL IR inside M3). The core mandates the
**output**: for each case, the SQL an implementation emits, after normalization,
**MUST** equal the case's `goldenSql` for that dialect, and **MUST** return the
case's `expectedRows`.

## The equivalence contract (DQ1)

The contract is layered. For a given dialect, an implementation is correct iff:

1. **Result equivalence.** The query returns exactly `expectedRows`. The suite
   cross-checks this with an independent `referenceSql` oracle (M12).
2. **Golden-SQL equivalence.** The SQL the implementation emits, **after
   normalization**, equals `goldenSql[dialect]`.

Round 1 ships golden SQL for **Postgres only**; the contract is per-dialect, so
additional dialects add `goldenSql.<dialect>` without changing the rules.

## Canonical normalization rules

Golden SQL is stored in **canonical normalized form**, and an implementation's
emitted SQL is compared **after applying the same normalization**. Normalization
makes the comparison deterministic and language-neutral. The rules:

1. **Table-alias scheme `t0, t1, …`.** Every table reference is aliased; aliases
   are assigned `t0`, `t1`, … in first-appearance order. Column references are
   always qualified by alias (`t0.id`, never bare `id`).
2. **Lowercase keywords and identifiers.** SQL keywords and unquoted identifiers
   are lowercased.
3. **Whitespace collapsed.** Runs of whitespace collapse to a single space;
   no leading/trailing whitespace; canonical single-space token separation.
4. **Bind placeholders, sorted.** Literal parameters are represented as bind
   placeholders (`?`), and the case's `binds` list is the ordered set of values.
   The placeholder ordering follows left-to-right appearance in the normalized
   statement.
5. **Deterministic clause order.** Clauses appear in the fixed order
   `select … from … [where …] [group by …] [having …] [order by …] [limit …]`.

The normative implementation of these rules is
`reference-harness/src/reference_harness/sql_normalize.py` (sqlglot-based). A
golden SQL string is valid only if `normalize(goldenSql) == goldenSql` — i.e. the
stored form is already a fixed point of normalization. The harness asserts this
per case (M12, layer 3).

> **Idempotence is the test.** Because normalization is idempotent, the stored
> golden SQL being a fixed point is exactly the property the harness checks.
> A contributor who hand-writes non-canonical golden SQL fails this check
> immediately, before any database is touched.

## What is normative vs. dialect-local

- **Normative:** the result (`expectedRows`) and the per-dialect golden SQL
  (after normalization).
- **Dialect-local:** the concrete SQL text itself — chosen by the M11 dialect.
  Two dialects legitimately emit *different* golden SQL for the same operation
  (different type casts, limit syntax, lock suffixes); both are normative for
  their dialect and both must return the same logical rows.

## Per-operator SQL emission

The table below fixes the **canonical Postgres golden SQL** each M2 node lowers
to. The golden form is what the M3 normalizer (and the harness, layer 3) treats
as the fixed point; an implementation's emitted SQL must equal it after
normalization. The `?` placeholders consume the case's `binds` left-to-right.

| Operation | Canonical predicate fragment |
|---|---|
| `all` | *(no `where` clause)* |
| `none` | `where 1 = 0` |
| `eq` | `t0.col = ?` |
| `notEq` | `t0.col <> ?` |
| `greaterThan` | `t0.col > ?` |
| `greaterThanEquals` | `t0.col >= ?` |
| `lessThan` | `t0.col < ?` |
| `lessThanEquals` | `t0.col <= ?` |
| `between` | `t0.col between ? and ?` |
| `isNull` | `t0.col is null` |
| `isNotNull` | `not t0.col is null` |
| `like` | `t0.col like ?` |
| `notLike` | `t0.col not like ?` |
| `startsWith`/`endsWith`/`contains` | `t0.col like ?` (affix pattern in the bind) |
| `like … escape` (literal wildcard) | `t0.col like ? escape ?` |
| case-insensitive string | `lower(t0.col) like lower(?)` |
| `in` | `t0.col in (?, ?, …)` |
| `notIn` | `not t0.col in (?, ?, …)` |
| `and` | operands joined by ` and ` |
| `or` | operands joined by ` or ` |
| `not` | `not <operand>` |
| `group` | `( <operand> )` |
| `orderBy` | `order by t0.col [asc\|desc][, …]` |
| `limit` | `limit ?` |
| `distinct` | `select distinct …` |
| `navigate`/`exists` | `exists (select 1 from child t1 where t1.fk = t0.key [and <op>])` |
| `notExists` | `not exists (select 1 from child t1 where t1.fk = t0.key [and <op>])` |

### Normalization notes (the surprising fixed points)

The M3 normalizer is the arbiter of canonical form, and three of its outputs are
worth calling out because the golden SQL must match them exactly:

1. **`is not null` → `not t0.col is null`.** The negation normalizes to a leading
   `not`; golden SQL for `isNotNull` is stored in that form.
2. **`not in (…)` → `not t0.col in (…)`.** Likewise for negated membership.
3. **Function names are lowercased and tight.** `LOWER(...)` normalizes to
   `lower(...)` (rule 2 — lowercase unquoted identifiers; the renderer keeps the
   function name tight against its `(`). The case-insensitive golden SQL is stored
   as `lower(t0.col) like lower(?)`.

### Wildcard / escape rendering

For the affix string forms the wildcard chars are placed by the implementation and
the literal value is escaped: `contains '50%'` lowers to
`t0.sku like ? escape ?` with binds `['%50\%%', '\\']`, so the embedded `%` is
matched literally. `like`/`notLike` pass the bind through verbatim (the value is
already a pattern, no escape clause).

### Clause order

Directives lower into the fixed clause order (rule 5):
`select [distinct] … from … [where …] [order by …] [limit …]`. `orderBy` and
`limit` therefore always follow any predicate, and `distinct` attaches to the
`select`.

## Joins by navigation

A `navigate` / `exists` / `notExists` node lowers to a **correlated `EXISTS`
sub-select** — a semi-join — so a to-many traversal never multiplies the queried
entity's rows. The correlated alias is `t1` (the next alias after the root
`t0`); the correlation predicate joins the related entity's foreign-key column to
the queried entity's key column, derived from the relationship's `join`. Any
inner operation is appended with `and`, its attributes resolved against the
related entity (alias `t1`):

```text
navigate(Order.items, eq(OrderItem.sku, 'A-100'))
  → select t0.id, t0.name from orders t0
    where exists (select 1 from order_item t1 where t1.order_id = t0.id and t1.sku = ?)

notExists(Order.items)
  → select t0.id, t0.name from orders t0
    where not exists (select 1 from order_item t1 where t1.order_id = t0.id)
```

The independent `referenceSql` oracle for a navigation filter is the naive
`id in (select fk from child where <op>)` subquery form — a different
formulation that must return the same rows (M12).

## Deep fetch — one statement per relationship level

`deepFetch` does **not** emit a single joined statement. It emits the **root
query** followed by **one `IN`-keyed statement per distinct relationship hop**
across the declared paths. Each child level selects the related rows whose
foreign key is `in` the **distinct parent keys gathered from the previous
level** — so the round-trip count is `1 + (number of relationship levels)`,
never one query per parent (N+1 elimination):

```text
deepFetch(all(Order), paths = [ [Order.items], [Order.items, OrderItem.statuses] ])
  level 0 (root)  : select t0.id, t0.name from orders t0
  level 1 (items) : select t0.id, t0.order_id, t0.sku, t0.quantity from order_item t0
                    where t0.order_id in (?, ?)          -- distinct Order.id values
  level 2 (statuses):
                    select t0.id, t0.order_item_id, t0.code from order_status t0
                    where t0.order_item_id in (?, ?, ?)  -- distinct OrderItem.id values
```

This is the **1 → N → N** shape that resolves in exactly **3 statements**, not
`1 + N + N`. Each child level's projection **MUST** include the join key columns
the harness needs to fan results back to their parents (the FK that correlates to
the parent, and the child's own key if it is itself a parent of a deeper level).
The temp-table variant for very large parent key sets is a **fast-follow**
(M4); round 1 uses the simplified `IN` form only.

Subsequent phases extend the emission + normalization rules for aggregation and
temporal predicates.
