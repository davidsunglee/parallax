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

Round 1 shipped golden SQL for **Postgres only**; the contract is per-dialect, so
additional dialects add `goldenSql.<dialect>` without changing the rules.
**MariaDB** is the second concrete dialect (a representative subset of cases now
carries `goldenSql.mariadb`), proving the per-dialect contract beyond Postgres.

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

The textual rules (2 lowercase, 3 whitespace, 5 clause order) are produced by
re-rendering, so a violation simply changes the string. The structural rules are
enforced by **rejection**, since re-rendering alone would pass a lowercase-but-
non-canonical statement through unchanged: a **read** (`select`) whose table
aliases are not `t0, t1, …` in first-appearance order, or whose columns are not
alias-qualified (rule 1), and **any** statement carrying an inline literal where
a `?` bind belongs (rule 4), is not canonical. Two literals are *not* parameters
and remain canonical: the `1 = 0` `none`-identity and the `select 1` `EXISTS`
probe. DML keeps its own canonical shape — an **unaliased** target table with
**bare** columns (`update balance set out_z = ? where bal_id = ?`) — so rule 1
applies to reads only.

## What is normative vs. dialect-local

- **Normative:** the **result** (`expectedRows`) — every dialect MUST return the
  same logical rows for an operation — and, **per dialect**, the golden SQL after
  normalization. The result is the cross-dialect invariant; the golden SQL is the
  per-dialect contract.
- **Dialect-local:** the concrete SQL text itself — chosen by the M11 dialect.
  Two dialects legitimately emit *different* golden SQL for the same operation
  (different type casts, limit syntax, lock suffixes); both are normative for
  their dialect and both must return the same logical rows.

### The cross-dialect cases (Postgres + MariaDB)

The MariaDB dialect (M11) exercises two genuine divergences; a representative
subset of cases carries `goldenSql.mariadb` and the harness runs them against
**both** databases, proving the result invariant while each dialect emits its own
optimized SQL:

- **Identical SQL, different physical binds — the infinity fallback.** For most
  operations (`eq`, `in`, the `exists` semi-join, the as-of-now read, the
  milestone insert) Postgres and MariaDB emit the **same** golden SQL text. The
  temporal cases additionally exercise the **max-sentinel infinity convention**
  (M0/M11): the open upper bound `out_z = ?` is carried as the `infinity` literal
  bind, which Postgres binds as native `'infinity'::timestamptz` and MariaDB —
  having no native timestamp infinity — binds as the documented max-sentinel
  `9999-12-31 23:59:59.999999`, reading it back as `infinity`. The fixture history,
  golden SQL, and asserted table state are authored once and hold on both. The
  independent oracle for an infinity-fallback read is **dialect-neutral** by
  design (`out_z > '9000-01-01'` rather than the Postgres-only
  `'infinity'::timestamptz` cast), so it runs verbatim on both dialects.
- **Different SQL — the read-lock divergence.** The shared-row-lock suffix is the
  one case where the two dialects emit *different* canonical golden SQL for the
  same operation: Postgres `… for share of t0`, MariaDB `… lock in share mode`.
  Both are normalizer fixed points for their dialect; both return the same rows.

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

## Aggregation — `GROUP BY` / `HAVING`

A `groupBy` node (M2 sub-area) lowers to a single aggregate `SELECT`. The
projection is the **group-by key columns** followed by the **aggregate
expressions**; the optional `having` filters groups. An aggregate SELECT never
carries the in-transaction read-lock suffix (the read-lock is an object-find
property — its rows have no base row to lock; see *Read-lock suffix* below and
`M11`). The canonical clause order (rule 5) places `group by` after `where` and
`having` after `group by`:

```text
select <keys…>, <aggregates…> from <table> t0
  [where <predicate>]
  [group by <keys…>]
  [having <aggregate predicate>]
```

### Aggregate expression emission

Each aggregate function lowers to the obvious SQL function applied to the
alias-qualified column, **aliased by its `as` name** (the result column name).
The canonical form drops the `as` keyword (rule 2 — the normalizer renders
`sum(t0.quantity) total_quantity`, never `sum(...) AS total_quantity`), exactly
as table aliases are rendered `orders t0`:

| Function | Canonical SQL |
|---|---|
| `sum` | `sum(t0.col) <as>` |
| `avg` | `avg(t0.col) <as>` |
| `count` (attr) | `count(t0.col) <as>` |
| `count` (whole group) | `count(*) <as>` |
| `min` | `min(t0.col) <as>` |
| `max` | `max(t0.col) <as>` |
| `stdDevSample` | `stddev_samp(t0.col) <as>` |
| `stdDevPop` | `stddev_pop(t0.col) <as>` |
| `varianceSample` | `var_samp(t0.col) <as>` |
| `variancePop` | `var_pop(t0.col) <as>` |

Group-by key columns project under their **own column name** (`t0.order_id`),
not an alias, and the same columns appear in the `group by` clause:
`group by t0.order_id[, …]`.

### The two-column read for `stdDev*` / `variance*`

A `stdDevSample`/`stdDevPop`/`varianceSample`/`variancePop` aggregate emits **two**
projected columns: the statistic and a **companion sample-count** column. This
mirrors Reladomo's standard-deviation/variance calculators, which read two result
columns so the caller can tell an undefined sample statistic (zero or one row ⇒
SQL `NULL`) apart from a genuine zero and combine partial aggregates. The
companion column is a `count` over the same attribute, aliased
`<as>` + a stable suffix the case authors (e.g. `sample_count`):

```text
select stddev_samp(t0.quantity) quantity_stddev, count(t0.quantity) sample_count
from order_item t0
```

The harness asserts this golden SQL returns the same rows as an independent
`referenceSql` formulation, so the two-column contract is proven against real
data, not merely asserted in prose.

### Having emission

`having` lowers each aggregate comparison to `<aggregate-expression> <op> ?`,
combined by `and` / `or` like the predicate algebra. The aggregate function in a
having leaf is rendered the same way as a projected aggregate **but without an
alias** (it is a predicate term, not a projection):

```text
groupBy(order_item, keys=[OrderItem.orderId],
        aggregates=[sum(OrderItem.quantity) as total_quantity],
        having gt(sum(OrderItem.quantity), 3))
  → select t0.order_id, sum(t0.quantity) total_quantity from order_item t0
    group by t0.order_id having sum(t0.quantity) > ?
```

The having binds follow any `where` binds, in left-to-right `having`-clause order.
The independent `referenceSql` oracle for an aggregate case is the naive form of
the same query (e.g. spelling the literals inline instead of as binds, or
restating the `having` predicate) — a different formulation that must return the
same aggregate rows (M12).

### Aggregate result rows

An aggregate query's `expectedRows` are **aggregate rows**: each row is the group
key columns plus the aggregate columns under their `as` names. There is no
entity-row projection. For a whole-table aggregate (no `keys`) the result is a
single row of aggregate values.

## Temporal predicates and write sequences (M7)

### As-of read predicates

An `asOf` / defaulted as-of pin lowers to an **auto-injected** interval predicate
(the user never writes it). For a single dimension pinned to instant `d`, with
the exclusive `[from, to)` closure:

| Pin | Canonical predicate fragment | Binds |
|---|---|---|
| `now` (current row) | `t0.out_z = ?` | `[infinity]` |
| a past instant `d` | `t0.in_z <= ? and t0.out_z > ?` | `[d, d]` |

The open bound is the dialect's native infinity (M11) — for Postgres the literal
`infinity`, carried as a `?` bind exactly like every other literal (M3 rule 4),
so the current-row golden SQL is `… where t0.out_z = ?` with `binds: [infinity]`.
The injected term composes with a user predicate via `and` and is appended
**after** it (binds read user-first, then the as-of bind):

```text
asOf(eq(Balance.acctNum,'A'), Balance.processingDate, now)
  → select t0.bal_id, t0.val from balance t0 where t0.acct_num = ? and t0.out_z = ?
    binds: ['A', infinity]
```

`history(operand, asOfAttr)` injects **no** as-of predicate — it returns every
milestone — so its golden SQL is just the operand's predicate; its projection
**SHOULD** include the interval columns so the caller sees each milestone's
bounds (the current row's `out_z` reads back as `infinity`).

`asOfRange(operand, asOfAttr, from, to)` reads the dimension as **edge points**
rather than a single pin: it returns every milestone whose `[in_z, out_z)`
interval **overlaps** the half-open window `[from, to)`. The canonical overlap
predicate compares the milestone's start to the window **end** and the
milestone's end to the window **start**, so the two binds are the window bounds
in `[to, from]` order:

| Read | Canonical predicate fragment | Binds |
|---|---|---|
| `asOfRange(…, from, to)` | `t0.in_z < ? and t0.out_z > ?` | `[to, from]` |

Unlike a single `asOf` pin (one milestone per key) or `history` (no predicate at
all), the range can return **several** milestones per key — every one the window
straddles — while still excluding milestones that closed before, or opened
after, it.

The independent `referenceSql` oracle for a temporal read spells the infinity /
instant literals inline (`out_z = 'infinity'::timestamptz`) — a different
formulation the harness asserts returns the same rows (M12).

### Milestone-chaining write sequences

A temporal write (audit-only) is an **ordered DML sequence**, not a single
statement. Let `txInstant` be the processing instant. The canonical Postgres DML:

| Mutation | Golden DML |
|---|---|
| **insert** | `insert into balance(cols…) values (?, …, ?)` with `in_z = txInstant`, `out_z = infinity` |
| **update** (close) | `update balance set out_z = ? where bal_id = ? and out_z = ?` — binds `[txInstant, pk, infinity]` |
| **update** (chain) | `insert into balance(cols…) values (?, …, ?)` — new current row, `in_z = txInstant`, `out_z = infinity` |
| **terminate** | the close `update` only (no insert) |

> **The canonical `insert` form has no space before the column list** —
> `insert into balance(bal_id, …)`, not `insert into balance (bal_id, …)`. That
> is the fixed point of the M3 normalizer (it renders an identifier immediately
> followed by `(` tight, as it does function names), so golden DML is stored that
> way and passes the layer-3 idempotence check.

The close `update` is keyed by the **current-row predicate** (`pk and
out_z = ?` / `infinity`), so only the open milestone is closed. The harness
**applies** this DML in order to an empty table and asserts the resulting
`expectedTableState` — including the `out_z = infinity` current row — so the
chaining contract is proven against real data, not merely asserted.

### Bitemporal as-of reads (both axes)

A **bitemporal** entity is pinned on both axes by nesting two `asOf` nodes; each
axis lowers to its own injected fragment (current-row equality or `[from, to)`
containment), composed with `and`. The fragments read **business-axis-first** (the
outer pin) then **processing**, so binds follow the same order:

| Both-axis read | Golden predicate | Binds |
|---|---|---|
| business now, processing now | `t0.thru_z = ? and t0.out_z = ?` | `[infinity, infinity]` |
| business past `b`, processing now | `t0.from_z <= ? and t0.thru_z > ? and t0.out_z = ?` | `[b, b, infinity]` |
| business past `b`, processing past `p` | `t0.from_z <= ? and t0.thru_z > ? and t0.in_z <= ? and t0.out_z > ?` | `[b, b, p, p]` |

A **business-temporal-only** read injects the single-axis fragment over
`from_z`/`thru_z` (the audit-only forms with `out_z` swapped for `thru_z`); its
default is still `now` ⇒ `t0.thru_z = ?` with `binds: [infinity]`.

### Bitemporal write sequences — the rectangle split

A full-bitemporal write that bounds a change to a business window is an ordered
DML sequence over **both** axes. Let `txInstant` be the processing instant and
`[bf, bt)` the business window. The canonical Postgres DML:

| Mutation | Golden DML |
|---|---|
| **insertUntil** | one `insert into position(cols…) values (?, …, ?)` with business `[bf, bt)`, processing `[txInstant, infinity)` |
| **updateUntil** (inactivate) | `update position set out_z = ? where pos_id = ? and out_z = ?` — binds `[txInstant, pk, infinity]` (closes the processing axis of the current rectangle) |
| **updateUntil** (head / middle / tail) | three `insert`s at processing `[txInstant, infinity)` — `head` business `[from_z, bf)` old value, `middle` business `[bf, bt)` new value, `tail` business `[bt, infinity)` old value |
| **terminateUntil** | the inactivate `update` + `head` + `tail` inserts only (**no** `middle`) |

The inactivate `update` is keyed by the **current-on-processing** predicate
(`pk and out_z = ?` / `infinity`), so only the open rectangle is closed; the new
rows are inserted **after** it. The harness **applies** this DML in order to an
empty table and asserts the resulting `expectedTableState` — the inactivated
original (`out_z` finite) plus the `head` / `middle` / `tail` rectangles current
on processing (`out_z = infinity`) — so the rectangle split is proven against real
data, not merely asserted. The same multi-row physical primary key (business key
plus each axis's `fromColumn`, `M1`) makes the chained rectangles admissible.

## Transactional SQL fragments (M8)

The unit-of-work layer (`M8`) is expressed in operations and object state, not
SQL — but it executes two dialect-specific SQL fragments through the `M11` seam,
and their canonical Postgres golden form is fixed here.

### Read-lock suffix

An in-transaction **object find** that intends to write carries the dialect's
shared-row-lock suffix (`M8`, `M11`). The read-lock is an **object-find property**:
a projection / aggregation SELECT — a `distinct`, grouped, or aggregate result —
**never** carries the suffix (it has no identifiable base row to lock), and the
`M11` dialect **owns applying** the lock (whether and where to append it — see
M11's *Read-lock application*). For Postgres the suffix is `for share of t0` — `for
share` qualified by the root alias — appended **after** every other clause (it is
the last thing in the statement, after any `where`):

```text
select t0.id, t0.balance from account t0 where t0.id = ? for share of t0
binds: [<pk>]
```

> **The lock-clause keywords are lowercased like any other keyword.** sqlglot
> tokenizes `SHARE` and `OF` as value tokens (not keyword tokens) and its
> generator emits them uppercase, but the M3 normalizer lowercases them (rule 2),
> so the canonical golden SQL is `… for share of t0`. Golden SQL is stored in that
> fully-lowercase form and passes the layer-3 idempotence check.

For **MariaDB** the same in-transaction read appends `lock in share mode` instead
(MariaDB has no `for share`; M11). It is the canonical fixed point for the MariaDB
dialect — the normalizer renders it through the seam, not through sqlglot's MySQL
generator (which would rewrite it to `for share`):

```text
select t0.id, t0.owner, t0.balance from account t0 where t0.id = ? lock in share mode
binds: [<pk>]
```

The lock is a concurrency property; a single-connection harness proves the
locking read is **well-formed and result-correct** (it executes against real
Postgres **and** real MariaDB and returns the expected rows) — the observable
half of the contract.

### Batched insert / update

The unit of work flushes buffered writes as set-based SQL. A batched **insert**
of N rows of one entity is a **single multi-row `INSERT`** — one statement, N
value tuples — not N statements:

```text
insert into account(id, owner, balance) values (?, ?, ?), (?, ?, ?), (?, ?, ?)
binds: [<row1…>, <row2…>, <row3…>]
```

A batched **update** of the same column over several keys is one keyed `UPDATE`
per distinct key (or a single statement with an `IN` predicate when the new value
is uniform across the keys):

```text
update account set balance = ? where id in (?, ?)
binds: [<new-balance>, <key1>, <key2>]
```

The harness proves the batched forms against real data by **applying** the golden
DML in order to a loaded table and asserting the resulting table state (the
write-sequence machinery, `M12`, reused for the non-temporal batched case) — so
"buffered writes flush as set-based SQL" is verified by the rows it leaves
behind, not merely asserted.

## Optimistic-lock UPDATE (M10)

When an entity declares an `optimisticLocking` version attribute (`M1`), an
`UPDATE` against it always **bumps the version in the `set`**, and — in
**optimistic mode** — also **gates** on the version the unit of work observed. The
golden form is therefore **mode-dependent** (`M8` strategy selection).

**Optimistic mode** appends the version check to the primary-key predicate:

```text
update account set balance = ?, version = ? where id = ? and version = ?
binds: [<new-balance>, <new-version>, <pk>, <observed-version>]
```

The `where id = ? and version = ?` predicate is the conflict gate: the
**observed version** is the value the unit of work read before mutating (never a
caller-authored number, `M10`). If a concurrent transaction committed first
(incrementing the row's version), the gate matches no row and the `UPDATE`
affects **zero** rows — the conflict signal `updatedRows != 1` (`M10`). On
success exactly **one** row is affected and its version advances.

**Locking mode** issues the same statement **without** the version gate — the
`M8` shared read lock, not the version, makes it correct — but still advances the
version (the `0702` / detached-merge-back shape):

```text
update account set balance = ?, version = ? where id = ?
binds: [<new-balance>, <new-version>, <pk>]
```

In either mode the new version is carried as a `?` bind like every other literal
(`M3` rule 4). A versioned `UPDATE` whose `set` changes **no** attribute issues
**no DML** at all (`M10`). The harness proves the optimistic halves — conflict (0
rows) and success (1 row) — by **applying** the golden `UPDATE` to a loaded table
(after an optional out-of-band version mutation) and asserting the **affected-row
count** (`M12` conflict case), and proves the locking-mode advance by applying
the ungated golden and asserting the resulting table state (`M12` write-sequence
case), so both are verified against real data.

### Versioned set-based updates materialize

There is **no** set-based versioned `UPDATE` template — no versioned analogue of
the batched `where <pk> in (…)` form above — because the gate binds a *per-row*
observed version a single statement cannot carry. A set-based update targeting a
versioned entity therefore **materializes** (`M10`, ADR 0032): the runtime
resolves the predicate to rows (a read that records each row's observed version
and, in `locking` mode, takes the shared lock), then **lowers to one keyed
per-object `UPDATE` per resolved row** — the gated optimistic form or the ungated
locking form above. The scenario golden lists those per-object statements in order
(one per matched row) with a list-of-lists of binds, and the declared round trips
are `1` read + `N` updates. For a **non-versioned** entity the readless batched
forms above stand (ADR 0011); materialization applies only where a framework-owned
version must ride each write.

### Versioned-read projection

A read of a versioned entity **projects the version column** alongside the row's
other columns, so the reader observes the current version (the value a later
optimistic gate binds). The canonical read golden lists the version column in its
projection like any other:

```text
select t0.id, t0.owner, t0.balance, t0.version from account t0 where t0.id = ?
```

## Metamodel-extension lowering — inheritance + valueObject (M1)

### Inheritance discriminator filter (table-per-hierarchy)

A `table-per-hierarchy` entity stores the whole hierarchy in one table, with a
**discriminator column** carrying each leaf's `discriminatorValue` (M1). A query
for a single subtype injects a **discriminator-equality** predicate; a query
across a family of subtypes injects a discriminator `in (…)`. The injected term
is an ordinary predicate over the root alias `t0`, composed with any user
predicate via `and`, with the discriminator value(s) carried as `?` binds:

| Query | Canonical predicate fragment | Binds |
|---|---|---|
| one subtype | `t0.kind = ?` | `[<discriminatorValue>]` |
| a family of subtypes | `t0.kind in (?, ?)` | `[<value1>, <value2>]` |
| the root (all rows) | *(no discriminator predicate)* | — |

```text
find Card-payments  (Payment table-per-hierarchy, discriminator `kind`, value 'card')
  → select t0.id, t0.amount, t0.kind from payment t0 where t0.kind = ?
    binds: ['card']
```

A `table-per-leaf` subtype query injects **no** discriminator at all — the leaf
is selected by querying its **own** table — so its golden SQL is an ordinary
single-table read of that leaf's table. The independent `referenceSql` oracle for
a discriminator query spells the value inline (`where kind = 'card'`).

### valueObject — structured-column read and filter

A `valueObject` is stored in **one structured-document column** (M0/M1), not
column-flattened. Reading the whole value object projects that backing column
directly (`t0.address`). Reading or filtering an **inner field** uses the M2
nested-attribute access form and lowers through the M11 dialect seam to a text
extraction. For Postgres golden SQL this is **`jsonb_extract_path_text`**, whose
**path segments are carried as `?` binds** (M3 rule 4 — the JSON keys are
parameters, never inlined, which also keeps the golden SQL a normalizer fixed
point):

| Operation | Postgres canonical fragment |
|---|---|
| project the whole object | `t0.address` (in the `select` list) |
| project an inner field | `jsonb_extract_path_text(t0.address, ?) <as>` |
| `nestedEq(Class.vo.field, v)` | `jsonb_extract_path_text(t0.address, ?) = ?` |
| `nestedNotEq(Class.vo.field, v)` | `not jsonb_extract_path_text(t0.address, ?) = ?` |
| nested deeper (`vo.a.b`) | `jsonb_extract_path_text(t0.address, ?, ?) = ?` |

The path binds precede the comparison bind, in `path`-segment order then value:

```text
nestedEq(Customer.address.city, 'Oslo')
  → select t0.id, t0.name from customer t0 where jsonb_extract_path_text(t0.address, ?) = ?
    binds: ['city', 'Oslo']

nestedEq(Customer.address.geo.country, 'NO')
  → select t0.id from customer t0 where jsonb_extract_path_text(t0.address, ?, ?) = ?
    binds: ['geo', 'country', 'NO']
```

The extraction yields **text**, so the compared value is authored as a string and
matched textually. Other dialects use their equivalent structured-column
extraction, such as a `VARIANT` path expression, while preserving the same M2
path order and result semantics. The independent `referenceSql` oracle spells
the Postgres extraction with the native `->>` operator and inline keys
(`t0.address ->> 'city' = 'Oslo'`), a different formulation the harness asserts
returns the same rows (M12).
