# m-sql — SQL Generation & Equivalence Contract

`m-sql` is the contract that turns an `m-op-algebra` operation into per-dialect
SQL, and the rules that make "equivalent SQL per database" **testable**. `m-sql`
depends on `m-op-algebra` (the algebra it lowers) and `m-dialect` (the dialect
that decides the concrete SQL).

The core does **not** mandate *how* an implementation produces SQL (a language
MAY lower the algebra onto an external SQL IR inside `m-sql`). The core mandates
the **output**: for each case, the SQL an implementation emits, after
normalization, **MUST** equal the case's golden `then.statements` for that
dialect, and **MUST** return the case's `then.rows`.

## The equivalence contract (DQ1)

The contract is layered. For a given dialect, an implementation is correct iff:

1. **Result equivalence.** The query returns exactly `then.rows`. The suite
   cross-checks this with an independent `then.referenceSql` oracle
   (`m-case-format`).
2. **Golden-SQL equivalence.** The SQL the implementation emits, **after
   normalization**, equals the per-dialect `sql` in `then.statements`.

Round 1 shipped golden SQL for **Postgres only**; the contract is per-dialect, so
additional dialects add a per-dialect `sql` key in each `then.statements` entry
(e.g. `mariadb`) without changing the rules. **MariaDB** is the second concrete
dialect (a representative subset of cases now carries a `mariadb` key in their
`then.statements` entries), proving the per-dialect contract beyond Postgres.

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
   placeholders (`?`), and each statement entry's `binds` list is the ordered set
   of values. The placeholder ordering follows left-to-right appearance in the
   normalized statement.
5. **Deterministic clause order.** Clauses appear in the fixed order
   `select … from … [where …] [group by …] [having …] [order by …] [limit …]`.

The normative implementation of these rules is
`reference-harness/src/reference_harness/sql_normalize.py` (sqlglot-based). A
golden statement's `sql` text is valid only if `normalize(sql) == sql` — i.e. the
stored form is already a fixed point of normalization. The harness asserts this
per case (`m-case-format`, layer 3).

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

- **Normative:** the **result** (`then.rows`) — every dialect MUST return the
  same logical rows for an operation — and, **per dialect**, the golden SQL after
  normalization. The result is the cross-dialect invariant; the golden SQL is the
  per-dialect contract.
- **Dialect-local:** the concrete SQL text itself — chosen by the `m-dialect`
  layer. Two dialects legitimately emit *different* golden SQL for the same
  operation (different type casts, limit syntax, lock suffixes); both are
  normative for their dialect and both must return the same logical rows.

### The cross-dialect cases (Postgres + MariaDB)

The MariaDB dialect (`m-dialect`) exercises two genuine divergences; a
representative subset of cases carries a `mariadb` key in their `then.statements`
entries and the harness runs them against **both** databases, proving the result
invariant while each dialect emits its own optimized SQL:

- **Identical SQL, different physical binds — the infinity fallback.** For most
  operations (`eq`, `in`, the `exists` semi-join, the as-of-now read, the
  milestone insert) Postgres and MariaDB emit the **same** golden SQL text. The
  temporal cases additionally exercise the **max-sentinel infinity convention**
  (`m-core` / `m-dialect`): the open upper bound `out_z = ?` is carried as the
  `infinity` literal bind, which Postgres binds as native `'infinity'::timestamptz`
  and MariaDB — having no native timestamp infinity — binds as the documented
  max-sentinel `9999-12-31 23:59:59.999999`, reading it back as `infinity`. The
  fixture history, golden SQL, and asserted table state are authored once and hold
  on both. The independent oracle for an infinity-fallback read is
  **dialect-neutral** by design (`out_z > '9000-01-01'` rather than the
  Postgres-only `'infinity'::timestamptz` cast), so it runs verbatim on both
  dialects.
- **Different SQL — the read-lock divergence.** The shared-row-lock suffix is the
  one case where the two dialects emit *different* canonical golden SQL for the
  same operation: Postgres `… for share of t0`, MariaDB `… lock in share mode`.
  Both are normalizer fixed points for their dialect; both return the same rows.

## Per-operator SQL emission

The table below fixes the **canonical Postgres golden SQL** each `m-op-algebra`
node lowers to. The golden form is what the `m-sql` normalizer (and the harness,
layer 3) treats as the fixed point; an implementation's emitted SQL must equal it
after normalization. The `?` placeholders consume the statement entry's `binds`
left-to-right.

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

The `m-sql` normalizer is the arbiter of canonical form, and three of its outputs
are worth calling out because the golden SQL must match them exactly:

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

The independent `then.referenceSql` oracle for a navigation filter is the naive
`id in (select fk from child where <op>)` subquery form — a different
formulation that must return the same rows (`m-case-format`).

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
(`m-deep-fetch`); round 1 uses the simplified `IN` form only.

## Temporal predicates and write sequences

### As-of read predicates

An `asOf` / defaulted as-of pin lowers to an **auto-injected** interval predicate
(the user never writes it). For a single dimension pinned to instant `d`, with
the exclusive `[from, to)` closure:

| Pin | Canonical predicate fragment | Binds |
|---|---|---|
| `now` (current row) | `t0.out_z = ?` | `[infinity]` |
| a past instant `d` | `t0.in_z <= ? and t0.out_z > ?` | `[d, d]` |

The open bound is the dialect's native infinity (`m-dialect`) — for Postgres the
literal `infinity`, carried as a `?` bind exactly like every other literal
(rule 4), so the current-row golden SQL is `… where t0.out_z = ?` with
`binds: [infinity]`. The injected term composes with a user predicate via `and`
and is appended **after** it (binds read user-first, then the as-of bind):

```yaml
# asOf(eq(Balance.acctNum,'A'), Balance.processingDate, now) lowers to the entry:
- sql:
    postgres: select t0.bal_id, t0.val from balance t0 where t0.acct_num = ? and t0.out_z = ?
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

The independent `then.referenceSql` oracle for a temporal read spells the infinity /
instant literals inline (`out_z = 'infinity'::timestamptz`) — a different
formulation the harness asserts returns the same rows (`m-case-format`).

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
> is the fixed point of the `m-sql` normalizer (it renders an identifier
> immediately followed by `(` tight, as it does function names), so golden DML is
> stored that way and passes the layer-3 idempotence check.

The close `update` is keyed by the **current-row predicate** (`pk and
out_z = ?` / `infinity`), so only the open milestone is closed. The harness
**applies** this DML in order to an empty table and asserts the resulting
`then.tableState` — including the `out_z = infinity` current row — so the
chaining contract is proven against real data, not merely asserted. The full
milestone-write semantics are `m-audit-write`.

**Optimistic-mode close (`m-opt-lock` × `m-audit-write`).** In optimistic mode the
close `update` gains an `and in_z = ?` gate on the observed processing-from — the
version analogue for a temporal entity (`m-opt-lock`, `m-opt-lock -->
m-temporal-read`):

| Mutation | Golden DML | Binds |
|---|---|---|
| **close** (optimistic) | `update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?` | `[txInstant, pk, infinity, observedInZ]` |

The locking-mode close keeps the ungated form above (`… where bal_id = ? and
out_z = ?`). A close **MUST** affect exactly one row; a zero-row close is a
conflict (optimistic) or a stale/consistency error (locking), never silent
(`m-audit-write` / `m-opt-lock`).

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
default is still `now` ⇒ `t0.thru_z = ?` with `binds: [infinity]`
(`m-business-only`).

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
empty table and asserts the resulting `then.tableState` — the inactivated
original (`out_z` finite) plus the `head` / `middle` / `tail` rectangles current
on processing (`out_z = infinity`) — so the rectangle split is proven against real
data, not merely asserted. The same multi-row physical primary key (business key
plus each axis's `fromColumn`, `m-descriptor`) makes the chained rectangles
admissible. The full rectangle-split semantics are `m-bitemp-write`.

**Optimistic-mode inactivation (`m-opt-lock` × `m-bitemp-write`).** In optimistic
mode the inactivate `update` gains the observed-processing-from gate; when the
key's current rows share an `in_z` (distinct business windows current at the same
processing time) the gate also carries the **business** discriminator `from_z = ?`
to inactivate exactly the observed rectangle:

| Mutation | Golden DML | Binds |
|---|---|---|
| **inactivate** (optimistic) | `update position set out_z = ? where pos_id = ? and out_z = ? and from_z = ? and in_z = ?` | `[txInstant, pk, infinity, observedFromZ, observedInZ]` |

The chained `head` / `middle` / `tail` rows stay ungated `INSERT`s at the fresh
`in_z`. A zero-row inactivation is a conflict (optimistic) or a stale error
(locking), never silent.

## Transactional SQL fragments

The unit-of-work layer (`m-unit-work`) is expressed in operations and object
state, not SQL — but it executes two dialect-specific SQL fragments through the
`m-dialect` seam, and their canonical Postgres golden form is fixed here.

### Read-lock suffix

An in-transaction **object find** that intends to write carries the dialect's
shared-row-lock suffix (`m-read-lock`, `m-dialect`). The read-lock is an
**object-find property**: a projection / aggregation SELECT — a `distinct`,
grouped, or aggregate result — **never** carries the suffix (it has no
identifiable base row to lock), and the `m-dialect` layer **owns applying** the
lock (whether and where to append it — see `m-dialect`'s *Read-lock application*).
For Postgres the suffix is `for share of t0` — `for share` qualified by the root
alias — appended **after** every other clause (it is the last thing in the
statement, after any `where`):

```yaml
- sql:
    postgres: select t0.id, t0.balance from account t0 where t0.id = ? for share of t0
  binds: [<pk>]
```

> **The lock-clause keywords are lowercased like any other keyword.** sqlglot
> tokenizes `SHARE` and `OF` as value tokens (not keyword tokens) and its
> generator emits them uppercase, but the `m-sql` normalizer lowercases them
> (rule 2), so the canonical golden SQL is `… for share of t0`. Golden SQL is
> stored in that fully-lowercase form and passes the layer-3 idempotence check.

For **MariaDB** the same in-transaction read appends `lock in share mode` instead
(MariaDB has no `for share`; `m-dialect`). It is the canonical fixed point for the
MariaDB dialect — the normalizer renders it through the seam, not through
sqlglot's MySQL generator (which would rewrite it to `for share`):

```yaml
- sql:
    mariadb: select t0.id, t0.owner, t0.balance from account t0 where t0.id = ? lock in share mode
  binds: [<pk>]
```

The lock is a concurrency property; a single-connection harness proves the
locking read is **well-formed and result-correct** (it executes against real
Postgres **and** real MariaDB and returns the expected rows) — the observable
half of the contract.

### Batched insert / update

The unit of work flushes buffered writes as set-based SQL (`m-batch-write`). A
batched **insert** of N rows of one entity is a **single multi-row `INSERT`** —
one statement, N value tuples — not N statements:

```yaml
- sql:
    postgres: insert into account(id, owner, balance) values (?, ?, ?), (?, ?, ?), (?, ?, ?)
  binds: [<row1…>, <row2…>, <row3…>]
```

A batched **update** of the same column over several keys is one keyed `UPDATE`
per distinct key (or a single statement with an `IN` predicate when the new value
is uniform across the keys):

```yaml
- sql:
    postgres: update account set balance = ? where id in (?, ?)
  binds: [<new-balance>, <key1>, <key2>]
```

The harness proves the batched forms against real data by **applying** the golden
DML in order to a loaded table and asserting the resulting table state (the
write-sequence machinery, `m-case-format`, reused for the non-temporal batched
case) — so "buffered writes flush as set-based SQL" is verified by the rows it
leaves behind, not merely asserted.

## Optimistic-lock UPDATE

When an entity declares an `optimisticLocking` version attribute (`m-descriptor`),
an `UPDATE` against it always **bumps the version in the `set`**, and — in
**optimistic mode** — also **gates** on the version the unit of work observed. The
golden form is therefore **mode-dependent** (`m-unit-work` strategy selection).

**Optimistic mode** appends the version check to the primary-key predicate:

```yaml
- sql:
    postgres: update account set balance = ?, version = ? where id = ? and version = ?
  binds: [<new-balance>, <new-version>, <pk>, <observed-version>]
```

The `where id = ? and version = ?` predicate is the conflict gate: the
**observed version** is the value the unit of work read before mutating (never a
caller-authored number, `m-opt-lock`). If a concurrent transaction committed first
(incrementing the row's version), the gate matches no row and the `UPDATE`
affects **zero** rows — the conflict signal `updatedRows != 1` (`m-opt-lock`). On
success exactly **one** row is affected and its version advances.

**Locking mode** issues the same statement **without** the version gate — the
shared read lock (`m-read-lock`), not the version, makes it correct — but still
advances the version (the `m-detach-002` / detached-merge-back shape):

```yaml
- sql:
    postgres: update account set balance = ?, version = ? where id = ?
  binds: [<new-balance>, <new-version>, <pk>]
```

In either mode the new version is carried as a `?` bind like every other literal
(rule 4). A versioned `UPDATE` whose `set` changes **no** attribute issues **no
DML** at all (`m-opt-lock`). The harness proves the optimistic halves — conflict
(0 rows) and success (1 row) — by **applying** the golden `UPDATE` to a loaded
table (after an optional out-of-band version mutation) and asserting the
**affected-row count** (`m-case-format` conflict case), and proves the
locking-mode advance by applying the ungated golden and asserting the resulting
table state (`m-case-format` write-sequence case), so both are verified against
real data.

### Versioned set-based updates materialize

There is **no** set-based versioned `UPDATE` template — no versioned analogue of
the batched `where <pk> in (…)` form above — because the gate binds a *per-row*
observed version a single statement cannot carry. A set-based update targeting a
versioned entity therefore **materializes** (`m-opt-lock`, ADR 0014): the runtime
resolves the predicate to rows (a read that records each row's observed version
and, in `locking` mode, takes the shared lock), then **lowers to one keyed
per-object `UPDATE` per resolved row** — the gated optimistic form or the ungated
locking form above. The scenario golden lists those per-object statements in order
(one per matched row), each statement entry carrying its own `binds`, and the
declared round trips are `1` read + `N` updates. For a **non-versioned** entity the readless batched
forms above stand (ADR 0014); materialization applies only where a framework-owned
version must ride each write.

### Versioned-read projection

A read of a versioned entity **projects the version column** alongside the row's
other columns, so the reader observes the current version (the value a later
optimistic gate binds). The canonical read golden lists the version column in its
projection like any other:

```text
select t0.id, t0.owner, t0.balance, t0.version from account t0 where t0.id = ?
```

## Metamodel-extension lowering — inheritance + valueObject

### Inheritance discriminator filter (table-per-hierarchy)

A `table-per-hierarchy` entity stores the whole hierarchy in one table, with a
**discriminator column** carrying each leaf's `discriminatorValue`
(`m-inheritance`). A query for a single subtype injects a **discriminator-equality**
predicate; a query across a family of subtypes injects a discriminator `in (…)`.
The injected term is an ordinary predicate over the root alias `t0`, composed with
any user predicate via `and`, with the discriminator value(s) carried as `?` binds:

| Query | Canonical predicate fragment | Binds |
|---|---|---|
| one subtype | `t0.kind = ?` | `[<discriminatorValue>]` |
| a family of subtypes | `t0.kind in (?, ?)` | `[<value1>, <value2>]` |
| the root (all rows) | *(no discriminator predicate)* | — |

```yaml
# find Card-payments (Payment table-per-hierarchy, discriminator `kind`, value 'card'):
- sql:
    postgres: select t0.id, t0.amount, t0.kind from payment t0 where t0.kind = ?
  binds: ['card']
```

A `table-per-leaf` subtype query injects **no** discriminator at all — the leaf
is selected by querying its **own** table — so its golden SQL is an ordinary
single-table read of that leaf's table. The independent `then.referenceSql` oracle
for a discriminator query spells the value inline (`where kind = 'card'`).

### valueObject — structured-column read and filter

A `valueObject` is stored in **one structured-document column** (`m-core` /
`m-value-object`), not column-flattened. Reading the whole value object projects
that backing column directly (`t0.address`). Reading or filtering an **inner
attribute** uses the `m-op-algebra` nested-attribute access form and lowers through
the `m-dialect` **nested-extraction** seam to a per-dialect extraction. The JSON
path is always carried as `?` bind(s) (rule 4 — never inlined, which keeps the
golden SQL a normalizer fixed point); the extraction function and the bind shape
differ per dialect (`m-dialect`):

| Operation | Postgres canonical fragment | MariaDB canonical fragment |
|---|---|---|
| project the whole object | `t0.address` (in the `select` list) | `t0.address` (identical) |
| project an inner field | `jsonb_extract_path_text(t0.address, ?) <as>` | `json_value(t0.address, ?) <as>` |
| `nestedEq(Class.vo.field, v)` | `jsonb_extract_path_text(t0.address, ?) = ?` | `json_value(t0.address, ?) = ?` |
| `nestedNotEq(Class.vo.field, v)` | `not jsonb_extract_path_text(t0.address, ?) = ?` | `not json_value(t0.address, ?) = ?` |
| nested deeper (`vo.a.b`) | `jsonb_extract_path_text(t0.address, ?, ?) = ?` | `json_value(t0.address, ?) = ?` |
| `nestedGt(vo.geo.num, v)` (numeric) | `cast(jsonb_extract_path_text(t0.address, ?, ?) as double precision) > ?` | `cast(json_value(t0.address, ?) as double) > ?` |
| `nestedGte` / `nestedLt` / `nestedLte` | as `nestedGt`, with `>=` / `<` / `<=` | as `nestedGt`, with `>=` / `<` / `<=` |
| `nestedIn(vo.field, [v, …])` | `jsonb_extract_path_text(t0.address, ?) in (?, …)` | `json_value(t0.address, ?) in (?, …)` |
| `nestedIsNull(vo.field)` | `jsonb_extract_path_text(t0.address, ?) is null` | `json_value(t0.address, ?) is null` |
| `nestedIsNotNull(vo.field)` | `not jsonb_extract_path_text(t0.address, ?) is null` | `not json_value(t0.address, ?) is null` |

The path bind(s) precede the comparison bind. **The bind order and count are
per-dialect** (`m-dialect`): Postgres carries **one bind per path segment** (in
`path` order) then the value; MariaDB carries **one `'$.a.b'` path bind** then the
value — so a deeper path is three binds on Postgres but two on MariaDB. Because the
hole structure diverges, the `binds` are authored as a **per-dialect map**
(`m-case-format`):

```yaml
# nestedEq(Customer.address.city, 'Oslo'):
- sql:
    postgres: select t0.id, t0.name from customer t0 where jsonb_extract_path_text(t0.address, ?) = ?
    mariadb: select t0.id, t0.name from customer t0 where json_value(t0.address, ?) = ?
  binds:
    postgres: ['city', 'Oslo']
    mariadb: ['$.city', 'Oslo']
# nestedEq(Customer.address.geo.country, 'US'):
- sql:
    postgres: select t0.id from customer t0 where jsonb_extract_path_text(t0.address, ?, ?) = ?
    mariadb: select t0.id from customer t0 where json_value(t0.address, ?) = ?
  binds:
    postgres: ['geo', 'country', 'US']
    mariadb: ['$.geo.country', 'US']
```

The compared `value` is a **typed** `m-op-algebra` literal; the extraction is cast
to the attribute's declared neutral type before comparing (the typed-cast form is a
per-dialect `m-dialect` decision). For a `string`-typed attribute the extraction is
already text and compares directly, as above. A future dialect with a different
document type — Snowflake `VARIANT` — uses its own extraction (a `VARIANT` path
expression) behind the same seam while preserving the path order and result
semantics. The independent `then.referenceSql` oracle spells the extraction a
**different** way per dialect, authored as a **per-dialect map** — Postgres uses the
native `->>` operator with an inline bare key (`t0.address ->> 'city'`), MariaDB uses
`nullif(json_unquote(json_extract(t0.address, '$.city')), 'null')` (a different
function family from the `json_value` golden; the `nullif(…, 'null')` restores the
absence collapse the `json_unquote(json_extract(…))` pair would otherwise lose on a
JSON `null` leaf) — each a different formulation from its golden extraction that the
harness asserts returns the same rows (`m-case-format`).

#### The flat `nested*` operator family

The range operators (`nestedGt` / `nestedGte` / `nestedLt` / `nestedLte`) apply
the **typed cast** (`m-dialect`) to the extraction before the SQL comparison, since
the extraction is text and the attribute is numeric. `nestedIn` lowers the
membership to `<extraction> in (?, …)` — the JSON path bind(s) first, then one
bind per list value in `values` order. `nestedIsNull` lowers to
`<extraction> is null` and `nestedIsNotNull` to a **leading `not`**
(`not <extraction> is null`) — the same negation normalization the scalar
`isNotNull`/`notIn`/`nestedNotEq` forms use. Because every not-present state casts
or compares SQL `NULL` (the absence-collapse rule, `m-op-algebra`), all of these
exclude the four not-present states identically, and `nestedIsNull` matches
exactly them:

```yaml
# nestedGt(Customer.address.geo.elevation, 8) — a float64 two-level path, cast:
- sql:
    postgres: select t0.id, t0.name from customer t0 where cast(jsonb_extract_path_text(t0.address, ?, ?) as double precision) > ?
    mariadb: select t0.id, t0.name from customer t0 where cast(json_value(t0.address, ?) as double) > ?
  binds:
    postgres: ['geo', 'elevation', 8]
    mariadb: ['$.geo.elevation', 8]
# nestedIsNull(Customer.address.geo.country) — the not-present collapse:
- sql:
    postgres: select t0.id, t0.name from customer t0 where jsonb_extract_path_text(t0.address, ?, ?) is null
    mariadb: select t0.id, t0.name from customer t0 where json_value(t0.address, ?) is null
  binds:
    postgres: ['geo', 'country']
    mariadb: ['$.geo.country']
```

The `then.referenceSql` oracle for a numeric predicate coerces a **different** way
per dialect (Postgres `(t0.address -> 'geo' ->> 'elevation')::double precision`,
MariaDB `nullif(json_unquote(json_extract(t0.address, '$.geo.elevation')), 'null') + 0`
— arithmetic coercion of an independent extraction rather than the golden's explicit
`cast(json_value(…) as double)`), each an independent formulation returning the same
rows. **All four not-present states collapse identically on both dialects.** The
MariaDB golden extraction is `json_value` precisely because it maps an explicit JSON
`null` leaf — like a missing key, a non-object intermediate, and a SQL `NULL` column
— to SQL `NULL` (as Postgres `jsonb_extract_path_text` does), so every not-present
state casts or compares SQL `NULL` and the absence-collapse rule (`m-op-algebra`)
holds portably. The compatibility corpus pins all four states on Postgres **and**
MariaDB (`m-value-object-013` asserts all four at `geo.country`).

#### To-many — exists / notExists and any-element predicates

A `cardinality: many` value object is a JSON **array** in the same column
(`m-value-object`). Filtering it lowers through the `m-dialect` **array-traversal**
seam, which the two dialects spell with **different function families** (Postgres a
correlated `jsonb_array_elements` unnest, MariaDB the `json_contains` / `json_length`
containment family — `m-dialect` explains why MariaDB does not use `JSON_TABLE`).
The path segment(s) reaching the array are `?` binds (rule 4) exactly as for the
scalar extraction, so the `binds` are a **per-dialect map** (`m-case-format`); the
element alias is the next alias after the root (`t1`, or `t1`/`t2` for two
independent any-element subqueries).

**Both dialects guard against a non-array `many` value.** Absence-collapse
(`m-op-algebra`) folds a member that is a SQL `NULL` column, a missing key, an
explicit JSON `null`, a JSON scalar, **or a JSON object** to the same "not present"
— **zero elements**. A member stored as a non-array is a real state (the JSON is
schema-flexible), and each dialect's traversal MUST read it as zero elements, never
as an error or a spurious element. So the canonical fragment carries an
**array-type guard**:

- **Postgres** — the strict `jsonb_array_elements` **errors** on a non-array
  argument, so the array is reached through a `case` that yields the extracted
  value only when it is an array and an empty `[]` otherwise:
  `case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? then
  jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end` — abbreviated
  `<arr>` below (binds: the path, the type name `array`, the path **again**, and
  `[]`; the path is bound **twice**).
- **MariaDB** — `json_length` / `json_contains` of a JSON scalar or object is
  non-zero / can match, so an array-type guard
  `json_type(json_extract(t0.address, ?)) = ?` (bind: the path, then the type name
  `ARRAY`) — abbreviated `<g>` below — precedes the containment/length test.

| Operation | Postgres canonical fragment | MariaDB canonical fragment |
|---|---|---|
| `nestedExists(Class.vo.arr)` (non-empty) | `exists (select 1 from jsonb_array_elements(<arr>) t1)` | `<g> and json_length(t0.address, ?) > ?` |
| `nestedNotExists(Class.vo.arr)` (empty-or-absent) | `not exists (select 1 from jsonb_array_elements(<arr>) t1)` | `not coalesce(<g> and json_length(t0.address, ?) > ?, ?)` |
| flat `nestedEq(Class.vo.arr.field, v)` (any-element) | `exists (select 1 from jsonb_array_elements(<arr>) t1 where jsonb_extract_path_text(t1.value, ?) = ?)` | `<g> and json_contains(t0.address, ?, ?)` |
| `nestedExists(Class.vo.arr, where: <compound>)` (same-element) | one `exists` with every element predicate on the **same** `t1` | `<g> and json_contains(t0.address, ?, ?)` with a candidate object carrying every field |
| `nestedNotExists(Class.vo.arr, where: <compound>)` (no element) | `not exists (select 1 from jsonb_array_elements(<arr>) t1 where <compound on t1>)` | `not coalesce(<g> and json_contains(t0.address, ?, ?), ?)` |

On Postgres the array is reached with `jsonb_extract_path` (the **jsonb** sibling of
the `jsonb_extract_path_text` extraction — it returns the array, not text) inside the
`<arr>` guard and unnested by the **strict** `jsonb_array_elements`, so a NULL
column, a missing key, a JSON `null`, a JSON scalar, or a JSON object all yield
**zero** elements; an element's own field is read with the ordinary
`jsonb_extract_path_text` over the element alias `t1.value`. On MariaDB the
`json_contains(col, candidate, path)` predicate binds a candidate JSON document and
the array path; containment against an array is **any-element**, and a candidate
object with several fields forces one element to carry **all** of them
(same-element). The `<g>` guard is required because `json_length` of a JSON scalar
(or JSON `null`) is `1` and `json_contains` matches a JSON **object** that happens
to contain the candidate — either would wrongly treat a non-array `phones` as
present without the guard. The negated forms wrap the guarded containment / length
in `coalesce(…, 0)` so an empty array, a NULL column, **and** a non-array value all
fall on the matching side of the leading `not` — all indistinguishable here, exactly
as `m-op-algebra`'s absence collapse requires.

```yaml
# nestedEq(Customer.address.phones.type, 'home') — flat any-element:
- sql:
    postgres: select t0.id, t0.name from customer t0 where exists (select 1 from jsonb_array_elements(case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t1 where jsonb_extract_path_text(t1.value, ?) = ?)
    mariadb: select t0.id, t0.name from customer t0 where json_type(json_extract(t0.address, ?)) = ? and json_contains(t0.address, ?, ?)
  binds:
    postgres: [phones, 'array', phones, '[]', type, home]
    mariadb: ['$.phones', 'ARRAY', '{"type":"home"}', '$.phones']
# nestedExists(Customer.address.phones, where: type='home' AND number='555-9999') — same-element:
- sql:
    postgres: select t0.id, t0.name from customer t0 where exists (select 1 from jsonb_array_elements(case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t1 where jsonb_extract_path_text(t1.value, ?) = ? and jsonb_extract_path_text(t1.value, ?) = ?)
    mariadb: select t0.id, t0.name from customer t0 where json_type(json_extract(t0.address, ?)) = ? and json_contains(t0.address, ?, ?)
  binds:
    postgres: [phones, 'array', phones, '[]', type, home, number, '555-9999']
    mariadb: ['$.phones', 'ARRAY', '{"type":"home", "number":"555-9999"}', '$.phones']
```

The unscoped `and(nestedEq(phones.type, 'home'), nestedEq(phones.number,
'555-9999'))` lowers to **two independent** any-element checks (Postgres two `exists`
subqueries with aliases `t1`, `t2`, each with its own `<arr>` guard; MariaDB two
`<g> and json_contains` conjuncts — each flat any-element predicate self-guards), so
a row whose two fields live in *different* elements matches — the discriminating
contrast with the same-element scoped form above (`m-op-algebra`; corpus
`m-value-object-018` vs `-019`). The independent `then.referenceSql` oracle spells
the traversal a **different** way per dialect: Postgres the `@>` containment operator
(`t0.address -> 'phones' @> '[{"type":"home"}]'`, which natively returns false on a
non-array) and `jsonb_array_length` (under a `jsonb_typeof` guard), MariaDB an
array-type-guarded `JSON_TABLE(…)` element unnest (parse-only, executed against real
MariaDB — the element-unnest golden SQL cannot use, since its `COLUMNS ( … PATH '…')`
paths cannot be `?` binds and do not normalize). Corpus `m-value-object-021` /
`-022` pin that a non-array `phones` collapses even when its scalar value or object
content collides with the query value.

The MariaDB `json_contains` golden expresses **equality/containment** element
predicates only (any-element `nestedEq`, same-element equality conjunctions);
non-equality element predicates through a `many` segment — `nestedGt` / `nestedLt` /
`nestedNotEq`, or a `where` compound with a range/`or`/`not` — need a set-returning
unnest and are a **documented deferred limitation on MariaDB** (`m-dialect`,
"Scope of the containment golden"). Postgres's `jsonb_array_elements` lowering is
fully general; the corpus's to-many coverage is equality-based accordingly.
