# m-sql — SQL Generation & Equivalence Contract

`m-sql` is the contract that turns one `m-predicate` `EntityQuery` into
per-dialect SQL, and the rules that make "equivalent SQL per database"
**testable**. `m-sql` depends on `m-predicate` (the query value and predicate
algebra it lowers) and `m-dialect` (the dialect that decides the concrete SQL).
It reads canonical model identities from `m-metamodel`, family and
discriminator semantics from `m-inheritance`, physical Tables and slots from
`m-storage-layout`, and compiled relationship directions from `m-relationship`.

The compilation interface accepts the `EntityQuery` fields directly: the exact
target Entity Identity, a predicate with temporal terms already injected,
optional query-wide narrowing, ordered result keys, and an optional row cap.
Compilation resolves the target against the accepted model and lowers those
fields; it does not discover them by peeling query-wide operation directives
from the predicate.

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
   are assigned `t0`, `t1`, … in **source order** — the left-to-right textual order
   the table sources first appear reading the statement as written. This is a
   **single global sequence** over the whole read: a correlated `EXISTS`
   sub-select's table **continues** the outer numbering (the outer query is `t0`,
   the first sub-select's table is `t1`) and **sibling** sub-selects do **not**
   restart — two independent `EXISTS` in one predicate alias `t1` and `t2`, a
   sub-select nested inside `t1` aliases `t2`. (The per-branch restart to `t0`
   applies only across the independent branches of a `union all`, below.) Column
   references are always qualified by alias (`t0.id`, never bare `id`). Because
   `and` / `or` are associative, a grouped predicate is stored in its **left-deep**
   spine — `a or b or c`, never the right-nested `a or (b or c)` — so a chain has
   one canonical shape and the branches number in source order without a hand-fold.
2. **Lowercase keywords and identifiers.** SQL keywords and unquoted identifiers
   are lowercased.
3. **Whitespace collapsed.** Runs of whitespace collapse to a single space;
   no leading/trailing whitespace; canonical single-space token separation.
4. **Bind placeholders, sorted.** Literal parameters are represented as bind
   placeholders (`?`), and each statement entry's `binds` list is the ordered set
   of values. The placeholder ordering follows left-to-right appearance in the
   normalized statement.
5. **Deterministic clause order.** Clauses appear in the fixed order
   `select … from … [where …] [group by …] [having …] [order by …] [limit …]
   [offset …]`. The optimizer-fence form is the only read that emits `offset`:
   its dialect-owned fenced branch ends in the literal clause `offset 0`.

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
re-rendering, and the left-deep reassociation of `and` / `or` chains (rule 1) is
applied during re-rendering, so a violation of any of these simply changes the
string. The remaining structural rules are enforced by **rejection**, since
re-rendering alone would pass a lowercase-but-non-canonical statement through
unchanged: a **read** (`select`) whose table aliases are not `t0, t1, …` in source
order, or whose columns are not alias-qualified (rule 1), and **any** statement
carrying an inline literal where a `?` bind belongs (rule 4), is not canonical.
Three literals are *not* parameters and remain canonical: the `1 = 0`
`none`-identity, the `select 1` `EXISTS` probe, and the optimizer-fence
`offset 0`. DML keeps its own canonical shape — an **unaliased** target table with
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
  operations (`eq`, `in`, the `exists` semi-join, the as-of-Latest read, the
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

## Read projection

The predicate fragments in this module fix a read's **`where` clause**; this section
fixes its **`select` list**. A read's projected column list is a **pure function of
the model and the read's target (`objectQuery.target`, `m-object-query`) plus its result
form — never of the predicate**. Exactly one read takes a fourth input: the internal
materialized-predicate-write resolving read derives its `Document` slots from the
**declared needs of the write it serves** — that write's target designation and its
declared assignments — and from nothing else, its own predicate included (the
`Document` slot rule and *Result form*, below). Predicate deliberately
carries **no projection node** (`m-predicate`): no Object Query read may project
a proper subset of the derived list. The directives `orderBy` and `limit` never
change the list.

Inheritance first resolves the target and every `narrow` to one canonical
effective concrete-Entity sequence. `StorageLayoutFacet.position(...)` then
supplies one logical contributor sequence and one slot-or-absence mapping per
physical Table. A concrete or standalone read may use the corresponding Entity
view directly. SQL never walks ancestry, merges a whole shared Table, or orders
physical declarations itself.

For each physical branch, SQL selects from the layout values as follows:

1. Every applicable Attribute slot is projected. This includes model identity,
   optimistic version, ordinary Domain, Temporal start/end, and future Audit
   slots; a designation changes the slot's tier, not whether the Attribute is
   readable.
2. A table-per-hierarchy discriminator slot is projected **iff** the read's
   the queried `target` is abstract, regardless of whether result narrowing reduces the
   effective set to one concrete. A concrete target uses the same slot for its
   tag predicate but does not project it.
3. Every applicable top-level Value Object `Document` slot is projected for an
   **instance-form** read. A row-form read omits those slots by default; the
   internal materialized-predicate-write resolving read is the one row-form read
   that widens the default, projecting the slots the write it serves needs
   (*Result form*, below).
4. A table-per-concrete-subtype abstract read appends the SQL-owned
   `familyVariant` literal to each branch. It is not a layout slot. Typed `NULL`
   placeholders and collision-safe aliases are likewise SQL renderings over a
   branch's absent slot entries.
5. Under Relational Document Layout, the shared Structured Column slot is
   projected **once** for a branch that needs it, and not at all for a branch
   that does not. Two independent needs reach it. A read whose requested members
   include one placed at a Document Path needs it to produce that member. An
   **observation-bearing** read — an instance-form read, and the internal
   materialized-predicate-write resolving read that widens its own projection
   (*Result form*, below) — needs it whenever the branch's Table carries one at
   all, because the stored document is itself part of what such a read observes:
   a Predecessor Row retains the raw document (`m-unit-work`), and an owner
   declaring no document-resident member still holds whatever keys a newer
   application version wrote. Outside that lane a row-form read projects it only
   for a requested document-resident member, so a row-form read of direct members
   alone emits no document extraction and no document projection at all. The
   Structured Column is never a result field: the row transform fans it out into
   the requested logical members — none, where the read requested none — and the
   raw value is not among them.

Within one Table, selected physical slots retain `TableLayout.columns` order:
`Identity`, `Discriminator`, `Domain`, `Temporal`, `Audit`, then `Document`, with
stable declaration order inside each tier. A cross-table
table-per-concrete-subtype union uses the Position Layout's one logical
contributor sequence and aligns each branch through its slot-or-absence map.
Duplicate removal is by structural contributor identity, never by a Column or
result-key spelling. Per-type rendering seams — the `bytes`
`encode(t0.payload, ?) payload_hex` form or reserved-word quoting
`t0."order"` — render a selected slot without changing its position.

### Result form — row-form vs instance-form

A read is consumed in one of two lanes, and the projection differs only in
whether `Document` slots are selected:

- **Instance-form** (the **object lane**) — the result materializes into instances: a
  snapshot-graph read, an eager fetch (its root and every child level), a deferred
  relationship **`load`** or an operation-list **first `access`** (`m-op-list`), or any
  other find whose rows become objects. It projects Document slots, so a value-object-bearing
  entity's whole document rides the owner's single statement (the one-round-trip
  materialization contract, `m-value-object`). Deep-fetch and snapshot **child levels
  are instance-form** — each level projects the child entity's own instance-form list
  (its scalars, plus any value-object document columns it declares) — as does a deferred
  `load` / first `access`, which is a child level resolved on demand.
- **Row-form** (the **values lane**) — the result is consumed as flat values, with no
  instance constructed. It omits Document slots by default. The corpus's predicate
  `read` cases (`then.rows`) and the internal materialized-predicate-write read —
  which resolves a set-based write to each row's pk and gate values (ADR 0014) — are
  the values lane; aggregation results (`m-agg`) use this lane too. The
  resolving read is the one row-form read whose consumer can widen the default: it
  additionally projects the Document slots the write it serves needs, which for a
  temporal target is every declared one, because the observation it records is a
  complete Predecessor Row (`m-unit-work`). Widening the projection does not make it
  instance-form — it still constructs no instance.

Row-form is **not a developer surface**: the idiomatic find API always materializes,
so the developer path is instance-form; row-form is the internal / conformance
consumption lane. `m-case-format` fixes the selector — a **top-level** read case's result
form is declared by **which result member it asserts** (`then.rows` = row-form;
`then.graph` / `then.graphs` = instance-form), and a scenario / coherence / concurrency
**step** read (asserted with `expectRows` / `observeRows`) is fixed by the step's read
semantics: a managed-object find or refresh, a relationship `load`, an operation-list
first `access`, and a full-scalar shared concurrency read are **instance-form**; the
internal materialized-predicate-write resolving read is **row-form**.

Everything already specified composes with this rule unchanged: a version
Attribute is an applicable Attribute slot; a TPH abstract read selects its
discriminator slot; a TPCS abstract read appends its per-branch synthetic
variant; and a deep-fetch child level includes its declared join-key Attribute
slots. The whole-value-object projection `t0.address` is a selected Document
slot on an instance-form read. A `history` read's interval Attributes are
Temporal slots and are projected automatically.

## Physical DML ordering

Physical DML obtains its target Table and complete slot order from the concrete
Entity's `EntityLayoutView`. An `INSERT` filters that table-ordered sequence to
the caller-present and framework-derived cells. An `UPDATE` filters it to the
present assignable cells after excluding semantic keys and gates from the `set`
clause. Batch grouping compares those resulting ordered slot selections; it
does not reconstruct order from the payload mapping.

Accepted Storage Layout ownership guarantees that this view belongs to exactly
one standalone mapping, one complete TPH family, or one TPCS concrete mapping.
Its physical primary key therefore contains only that owner's model-key and
temporal-end slots: DML never targets a layout whose key combines independent
Entity mappings that can supply only disjoint subsets.

The layout supplies physical lookup, not operation semantics. Model primary-key
Attributes, a TPH discriminator assignment, an optimistic observation, and
temporal start/end Attributes are selected for their operation-specific roles by
their owning modules, then mapped through layout contributor lookups. The
predicate order and bind order specified by each DML template below remain
normative even when they differ from complete table order. `familyVariant`, SQL
aliases, and typed `NULL` expressions never become DML slots.

### Document-resident assignments

Under Relational Document Layout an `UPDATE` splits its assignments by Member
Placement. A `DirectColumn` assignment is an ordinary `set <column> = ?` term in
layout order, unchanged. Every `DocumentPath` assignment instead composes into
**one** `set <structured column> = <mutation expression>` term, in the Structured
Column's own layout position, rendered through `m-dialect`'s document
mutation-expression form.

The composition order is **canonical logical placement order** — the order the
assigned members occupy in the Table's logical placement order — never caller
mapping order and never a hash or set iteration order. Both dialects apply their
composed assignments left to right, so this order is observable, and it is what
makes a golden statement stable to author. Assignments are neither merged nor
deduplicated: one assigned member is one path in the expression.

A top-level Value Object assignment is one assignment tree in this order. A
`one` tree recursively carries only the declared members present in the authored
document and patches those members through `m-dialect`'s guarded occurrence
mutation; omitted and undeclared members remain untouched. A `many` tree carries
the complete encoded ordered array and replaces that array whole. No ordinary
update binds the whole Structured Column, and an accepted readless update does
not read the row first to rewrite it.

An `INSERT` binds the Structured Column exactly once, as one complete encoded
document, in its layout position — the same shape a conventional Value Object
column already has. A temporal successor is an insert, and the document it binds
is built from the retained raw predecessor document (`m-unit-work`), never
re-encoded from decoded members.

Assignments to a document-resident member never appear in a primary-key,
discriminator, optimistic, or temporal gate, because no direct role is
document-resident.

## Per-operator SQL emission

The table below fixes the **canonical Postgres golden SQL** each `m-predicate`
node lowers to. The golden form is what the `m-sql` normalizer (and the harness,
layer 3) treats as the fixed point; an implementation's emitted SQL must equal it
after normalization. The `?` placeholders consume the statement entry's `binds`
left-to-right.

| Predicate | Canonical predicate fragment |
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
| `orderBy` | `order by <key term>[, …]`, one term per key — `t0.col [asc\|desc]` for a non-nullable key, else the `m-dialect` Null Placement term |
| `limit` | `limit ?` |
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
already a pattern, no escape clause). The `escape ?` clause and its second bind
appear **only** when escaping actually changed the literal: `startsWith 'A-'`
lowers to the bare `t0.sku like ?` with a single `'A-%'` bind.

The five **nested** string predicates render identically against the extraction
their scope resolved (`<extraction> like ?`, and the infix
`<extraction> not like ?` for `nestedNotLike`), so the rule above is stated once
and reused rather than restated per scope.

### `order by` key terms

`orderBy` emits one comma-separated term per key, in the authored key order. A key
over a **non-nullable** attribute lowers to the plain `t0.col [asc|desc]` term
under either Null Placement — the placements denote the same order there, so
neither dialect compensates. A key over a **nullable** attribute delegates its
whole term to the `m-dialect` Null Placement seam, which owns both the suffix form
and the leading-rank-term form; the emitter joins the returned terms and never
composes the placement itself. The canonical Postgres terms are `t0.col asc`,
`t0.col asc nulls first`, `t0.col desc nulls last`, and `t0.col desc` for
`asc`/`last`, `asc`/`first`, `desc`/`last`, and `desc`/`first` respectively;
`m-dialect`'s table is normative for every dialect.

### Clause order

The `EntityQuery` ordering and cap fields lower into the fixed clause order
(rule 5):
`select … from … [where …] [order by …] [limit …]`. `orderBy` and `limit`
therefore always follow any predicate.

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
  → select t0.id, t0.name, t0.sku, t0.qty, t0.price, t0.active, t0.ordered_on from orders t0
    where exists (select 1 from order_item t1 where t1.order_id = t0.id and t1.sku = ?)

notExists(Order.items)
  → select t0.id, t0.name, t0.sku, t0.qty, t0.price, t0.active, t0.ordered_on from orders t0
    where not exists (select 1 from order_item t1 where t1.order_id = t0.id)
```

The independent `then.referenceSql` oracle for a navigation filter is the naive
`id in (select fk from child where <op>)` subquery form — a different
formulation that must return the same rows (`m-case-format`).

### Polymorphic navigation lowering

When a relationship target is a **polymorphic position** (`m-inheritance` — an
abstract root / abstract subtype, optionally narrowed by a `narrow` in the filter's
`op`, `m-predicate`), the semi-join constrains the sub-select to the target's
**effective concrete-subtype set**. The shape depends on the strategy:

- **`table-per-hierarchy`** — one shared child table, so the hop is a **single**
  correlated `EXISTS` with the **interior tag predicate** over the effective set,
  appended after the correlation predicate. An abstract-**root** target spans the
  whole shared table and injects **no** tag predicate; an abstract-**subtype** (or
  narrowed) target injects `t1.kind in (?, …)` (or `t1.kind = ?` for one concrete),
  in the family's canonical alphabetical order (`m-inheritance`), excluding sibling
  branches:

  ```text
  exists(Person.pets)  # Pet -> {Cat, Dog}, a proper subset of the animal table
    → select … from person t0
      where exists (select 1 from animal t1
                    where t1.owner_id = t0.id and t1.kind in (?, ?))
      binds: ['cat', 'dog']
  ```

- **`table-per-concrete-subtype`** — each concrete subtype has its own table, so
  the hop is a **grouped `OR` of one correlated `EXISTS` per effective concrete
  subtype**, in the family's canonical **alphabetical order** (`m-inheritance`; a
  single concrete is one ungrouped `EXISTS`):

  ```text
  exists(Folder.documents)  # Document -> {Invoice, Memo, Receipt}
    → select … from folder t0
      where (exists (select 1 from invoice t1 where t1.folder_id = t0.id)
          or exists (select 1 from memo    t2 where t2.folder_id = t0.id)
          or exists (select 1 from receipt t3 where t3.folder_id = t0.id))
  ```

## Deep fetch — one statement per relationship level

Includes does **not** emit a single joined statement. It emits the **root
query** followed by **one `IN`-keyed statement per distinct relationship hop**
across the declared paths. Each child level selects the related rows whose
foreign key is `in` the **distinct parent keys gathered from the previous
level** — so the round-trip count is `1 + (number of relationship levels)`,
never one query per parent (N+1 elimination):

```text
objectQuery(Order, all, includes = [ { segments: [{ rel: Order.items }] },
                                { segments: [{ rel: Order.items }, { rel: OrderItem.statuses }] } ])
  level 0 (root)  : select t0.id, t0.name, t0.sku, t0.qty, t0.price, t0.active, t0.ordered_on from orders t0
  level 1 (items) : select t0.id, t0.order_id, t0.sku, t0.quantity, t0.shipped_on from order_item t0
                    where t0.order_id in (?, ?)          -- distinct Order.id values
  level 2 (statuses):
                    select t0.id, t0.order_id, t0.order_item_id, t0.code from order_status t0
                    where t0.order_item_id in (?, ?, ?)  -- distinct OrderItem.id values
```

This is the **1 → N → N** shape that resolves in exactly **3 statements**, not
`1 + N + N`. Each child level is **instance-form** (*Read projection*), so it projects
the child entity's full scalar set; this **subsumes** the join key columns the harness
needs to fan results back to their parents (the FK that correlates to the parent, and
the child's own key when it is itself a parent of a deeper level).
The temp-table variant for very large parent key sets is a **fast-follow**
(`m-deep-fetch`); round 1 uses the simplified `IN` form only.

A **path-root guard** (`m-predicate`'s `{ to }` beside `segments`) emits
**no statement and no clause of its own**. It restricts which already-fetched root
rows a path's first level gathers its keys from, so it is observable only in that
level's `IN` list — which carries the guarded roots' keys alone — and, through it,
in the rows that level returns. The root query itself is unchanged, because the
guard does not change the read's own result set (`m-inheritance`), and a level
beneath a guarded one carries no guard term either: its parents are already the
guarded branch's rows.

```text
# target: Animal (Dog 1 -> owner 10, Dog 2 -> owner 11, Cat 3 -> owner 10,
# WildBoar 4 -> owner 12), one path guarded to the Dogs:
objectQuery(Animal, all, includes = [ { appliesTo: [Dog],
                                   segments: [{ rel: Animal.owner }] } ])
  level 0 (root)  : select t0.id, t0.kind, t0.name, t0.owner_id, t0.license_id,
                    t0.indoor, t0.bark_volume, t0.tusk_length from animal t0
  level 1 (owner) : select t0.id, t0.name from person t0 where t0.id in (?, ?)
                    -- the DOG rows' distinct owner_id values, never the Cat's or the WildBoar's
```

A **polymorphic** hop (relationship target abstract, optionally narrowed by a path
`narrow`, `m-predicate` / `m-deep-fetch`) stays **one statement per level**. Under
`table-per-hierarchy` the child level is the shared-table `IN` read with the
effective set's tag predicate appended after the `IN` list (`… where t0.owner_id in
(?, …) and t0.kind in (?, …)`); a polymorphic view projects the raw tag column so
`familyVariant` can be materialized, a single-concrete narrowed view projects only
that concrete's columns. Under `table-per-concrete-subtype` the child level is a
single **`union all`** statement whose branches — one per effective concrete
subtype in canonical alphabetical order (`m-inheritance`) — share the **same**
parent-id `IN` list (the stable superset projection + per-branch `familyVariant`
literal of the abstract-read lowering below); the hop remains one statement,
preserving `1 + L`.

## Temporal predicates and write sequences

### As-of read predicates

An `asOf` / defaulted as-of pin lowers to an **auto-injected** interval predicate
(the user never writes it). For the Transaction-Time dimension pinned to
coordinate `d`, with the exclusive `[in_z, out_z)` closure:

| Pin | Canonical predicate fragment | Binds |
|---|---|---|
| Latest | `t0.out_z = ?` | `[infinity]` |
| finite instant `d` | `t0.in_z <= ? and t0.out_z > ?` | `[d, d]` |

The open bound is the dialect's native infinity (`m-dialect`) — for Postgres the
literal `infinity`, carried as a `?` bind exactly like every other literal
(rule 4), so the current-row golden SQL is `… where t0.out_z = ?` with
`binds: [infinity]`. The injected term composes with a user predicate via `and`
and is appended **after** it (binds read user-first, then the as-of bind):

```yaml
# asOf(eq(Balance.acctNum,'A'), transaction-time, latest) lowers to the entry:
- sql:
    postgres: select t0.bal_id, t0.val from balance t0 where t0.acct_num = ? and t0.out_z = ?
  binds: ['A', infinity]
```

`history(operand, dimension)` injects **no** as-of predicate — it returns every
milestone — so its golden SQL is just the operand's predicate; its projection
**includes** the interval columns automatically — they are declared attributes in
the layout's Temporal tier — so the caller sees each milestone's bounds
(the current row's `out_z` reads back as `infinity`).

`asOfRange(operand, dimension, start, end)` reads the dimension as **edge points**
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

A Transaction-Time-Only write is an **ordered DML sequence**, not a single
statement. Let `txInstant` be the finite Transaction-Time instant supplied by the
handle clock. The canonical Postgres DML:

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
milestone-write semantics are `m-txtime-write`.

**Optimistic-mode close (`m-opt-lock` × `m-txtime-write`).** In optimistic mode the
close `update` gains an `and in_z = ?` gate on the observed `txStart` — the
version analogue for a temporal entity (`m-opt-lock`, `m-opt-lock -->
m-temporal-read`):

| Mutation | Golden DML | Binds |
|---|---|---|
| **close** (optimistic) | `update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?` | `[txInstant, pk, infinity, observedTxStart]` |

The locking-mode close keeps the ungated form above (`… where bal_id = ? and
out_z = ?`). A close **MUST** affect exactly one row; a zero-row close is a
conflict (optimistic) or a stale/consistency error (locking), never silent
(`m-txtime-write` / `m-opt-lock`).

### Bitemporal as-of reads (both axes)

A Bitemporal Entity is pinned on both dimensions by nesting two `asOf` nodes;
each dimension lowers to its own injected fragment (Latest equality or finite
containment), composed with `and`. Valid Time is the outer pin and Transaction
Time the inner pin, so binds follow the same order:

| Both-axis read | Golden predicate | Binds |
|---|---|---|
| Valid-Time Latest, Transaction-Time Latest | `t0.thru_z = ? and t0.out_z = ?` | `[infinity, infinity]` |
| Valid-Time finite `v`, Transaction-Time Latest | `t0.from_z <= ? and t0.thru_z > ? and t0.out_z = ?` | `[v, v, infinity]` |
| Valid-Time finite `v`, Transaction-Time finite `t` | `t0.from_z <= ? and t0.thru_z > ? and t0.in_z <= ? and t0.out_z > ?` | `[v, v, t, t]` |

Valid-Time-Only belongs to the separate `m-validtime-only` contract and adds no
SQL shape to `m-temporal-read`.

### Bitemporal write sequences — the rectangle split

A Bitemporal write that bounds a change to a Valid-Time window is an ordered DML
sequence over both dimensions. Let `txInstant` be the handle-supplied
Transaction-Time instant and `[vf, until)` the Valid-Time window. The canonical
Postgres DML:

| Mutation | Golden DML |
|---|---|
| **insertUntil** | one `insert into position(cols…) values (?, …, ?)` with Valid Time `[vf, until)` and Transaction Time `[txInstant, infinity)` |
| **updateUntil** (inactivate) | `update position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ?` — binds `[txInstant, pk, observedValidEnd, infinity]` (closes Transaction Time of the addressed rectangle) |
| **updateUntil** (head / middle / tail) | three `insert`s at Transaction Time `[txInstant, infinity)` — `head` Valid Time `[from_z, vf)` old value, `middle` Valid Time `[vf, until)` new value, `tail` Valid Time `[until, infinity)` old value |
| **terminateUntil** | the inactivate `update` + `head` + `tail` inserts only (**no** `middle`) |

The inactivate `update` **addresses** the one rectangle it closes: the primary key
plus one exclusive upper bound **per As-Of Axis** — the observed rectangle's own
`thru_z`, then the invariant `out_z` / `infinity` that keeps the close on a row
current on Transaction Time. The key and `out_z` alone would be ambiguous, because
one key may hold several disjoint Valid-Time rectangles current at the same
Transaction Time. The new rows are inserted **after** it.

The harness **applies** this DML in order to an
empty table and asserts the resulting `then.tableState` — the inactivated
original (`out_z` finite) plus the `head` / `middle` / `tail` rectangles current
on Transaction Time (`out_z = infinity`) — so the rectangle split is proven against real
data, not merely asserted. The same multi-row physical primary key (domain key
plus each dimension's end column, `m-descriptor`) makes the chained rectangles
admissible. The full rectangle-split semantics are `m-bitemp-write`.

**Plain (unbounded) writes.** Alongside the bounded `*Until` templates, the plain
(unbounded) `insert` / `update` / `terminate` govern a value from an effective
Valid-Time instant `V` **through infinity** — the degenerate rectangle splits with no
`until` (`m-bitemp-write`). Plain `insert` is a **single** fully-current `INSERT`;
plain `update` is the inactivate `update` plus a `head` **and** a new `tail`; plain
`terminate` is the inactivate `update` plus a **single `head`** (no tail):

| Mutation | Golden DML | Binds |
|---|---|---|
| **insert** (plain) | `insert into position(cols…) values (?, …, ?)` — fully-current row, Valid Time `[V, infinity)`, Transaction Time `[txInstant, infinity)` | `[…row…, V, infinity, txInstant, infinity]` |
| **update** (inactivate) | `update position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ?` | `[txInstant, pk, observedValidEnd, infinity]` |
| **update** (head) | `insert into position(cols…) values (?, …, ?)` — old value, Valid Time `[from_z, V)`, Transaction Time `[txInstant, infinity)` | `[…row…, from_z, V, txInstant, infinity]` |
| **update** (new tail) | `insert into position(cols…) values (?, …, ?)` — new value, Valid Time `[V, infinity)`, Transaction Time `[txInstant, infinity)` | `[…row…, V, infinity, txInstant, infinity]` |
| **terminate** (inactivate) | `update position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ?` | `[txInstant, pk, observedValidEnd, infinity]` |
| **terminate** (head) | `insert into position(cols…) values (?, …, ?)` — old value, Valid Time `[from_z, V)`, Transaction Time `[txInstant, infinity)` | `[…row…, from_z, V, txInstant, infinity]` |

Plain `insert` opens a fully-current rectangle (`thru_z = out_z = infinity`) with
**no** inactivation and no prior row to close — the `until = infinity`
degenerate of `insertUntil`, sharing that template's `INSERT` shape (so the optimistic
inactivation gate below does not apply to it). Plain `update` is **three** statements
(inactivate + `head` + new `tail`) and plain `terminate` is **two** (inactivate +
`head`); neither chains a `middle` or an old-`tail`, so a plain `update` runs the new
value unbounded to infinity and a plain `terminate` leaves `[V, infinity)` covered by
no current-on-Transaction-Time row. The inactivate `update` for both addresses its
rectangle exactly as the `*Until` inactivate above does, so the optimistic gate below
applies to it verbatim.

**Optimistic-mode inactivation (`m-opt-lock` × `m-bitemp-write`).** The address above
is what the inactivate `update` renders in **both** modes; optimistic mode only
**appends** the observed-`txStart` gate, and that gate binds last:

| Mutation | Golden DML | Binds |
|---|---|---|
| **inactivate** (optimistic) | `update position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ? and in_z = ?` | `[txInstant, pk, observedValidEnd, infinity, observedTxStart]` |

`observedValidEnd` is the observed rectangle's own exclusive Valid-Time end and is
**finite** whenever that rectangle is bounded; only `out_z` is invariantly `infinity`.
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
**object-find property**, and the `m-dialect` layer **owns applying** the lock
(whether and where to append it — see `m-dialect`'s *Read-lock application*).
For Postgres the suffix is `for share of t0` — `for share` qualified by the root
alias — appended **after** every other clause (it is the last thing in the
statement, after any `where`):

```yaml
- sql:
    postgres: select t0.id, t0.owner, t0.balance, t0.version from account t0 where t0.id = ? for share of t0
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
    mariadb: select t0.id, t0.owner, t0.balance, t0.version from account t0 where t0.id = ? lock in share mode
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
other columns because the `optimisticLocking` version is an applicable declared
Attribute slot — so the reader observes the
current version (the value a later optimistic gate binds). The canonical read golden
lists the version column in its projection like any other:

```text
select t0.id, t0.owner, t0.balance, t0.version from account t0 where t0.id = ?
```

## Metamodel-extension lowering — inheritance + valueObject

### Inheritance — table-per-hierarchy lowering

A `table-per-hierarchy` family stores every concrete subtype in one **shared
table**; rows are told apart by the root's **tag column** (`tag.column`, carrying
each concrete subtype's `tagValue`, `m-inheritance`). The tag is **framework-owned
metadata, not a declared attribute** (resolved Q6), so it appears in the golden
SQL only where the lowering puts it, never because a user named it.

#### Tag-predicate selection

A read's queried position (the query's `target`, optionally further constrained by a
`narrow`, `m-predicate`) resolves to an **effective concrete-subtype set**. The
lowering injects a tag predicate over the root alias `t0` from that set, composed
with any user predicate via `and` (appended **after** it, so binds read
user-first then tag):

| Position resolves to | Canonical tag fragment | Binds |
|---|---|---|
| the whole family (abstract root, no narrow) | *(no tag predicate)* | — |
| one concrete subtype | `t0.kind = ?` | `[<tagValue>]` |
| several concrete subtypes (abstract subtype, or a narrow) | `t0.kind in (?, …)` | `[<tagValue>, …]` (canonical alphabetical order) |

An abstract **root** read spans the whole shared table, so it injects **no** tag
predicate; the *absence* is the contract. An abstract **subtype** read (or any
narrow) that resolves to a **proper subset** of the table's concretes injects the
`in (…)` list of exactly those `tagValue`s, in the family's canonical alphabetical
order (`m-inheritance`), so a sibling branch in the same table is excluded. A single
concrete subtype lowers to `t0.kind = ?`.

#### Grouped branch predicates

A predicate over a **concrete-subtype-declared** attribute is only meaningful for
that branch's rows, so it is **guarded by that branch's tag predicate**. The tag
guard is appended **after** the branch predicate (binds read branch-predicate-first
then tag), exactly as an injected tag composes after a user predicate above. When a
read ORs across two concrete branches, each branch is a **grouped** `(branch-
predicate AND tag)` and the branches are joined by `or`:

```text
# target: Animal, or( narrow[Dog] & barkVolume>5, narrow[Cat] & indoor=true ):
  → select … from animal t0
    where (t0.bark_volume > ? and t0.kind = ?) or (t0.indoor = ? and t0.kind = ?)
    binds: [5, 'dog', true, 'cat']
```

A single narrow to one concrete subtype with a branch predicate needs no grouping:
`narrow[Dog] & barkVolume>5` lowers to `t0.bark_volume > ? and t0.kind = ?` with
binds `[5, 'dog']`.

#### Abstract-read projection and `familyVariant`

An **abstract-target** read must materialize complete concrete instances, so its
projection selects the complete Position Layout superset reachable from the
position plus the raw discriminator slot (resolved Q6). The slot sequence follows
the shared Table Layout's semantic tiers; canonical concrete order from
`m-inheritance` remains the stable encounter order within a tier. A subtype slot
not applicable to a returned row reads back `NULL`; SQL projects the discriminator
because an abstract target must materialize each concrete variant:

```yaml
# target: Animal (root over Cat / Dog / WildBoar) — the Identity slot, raw
# Discriminator slot, then Domain slots in stable declaration encounter order:
- sql:
    postgres: select t0.id, t0.kind, t0.name, t0.owner_id, t0.license_id, t0.indoor, t0.bark_volume, t0.tusk_length from animal t0
```

`familyVariant` is **not projected as SQL**. It is materialized from the tag
metadata map (`tagValue` -> concrete subtype **variant spelling**) at row construction — the
same independent, metadata-derived recomputation as the as-of and PK-allocation
oracles. The variant spelling is the bare local name when family-unique and the
canonical qualified Entity spelling when duplicate local concrete names make the
bare spelling ambiguous (`m-inheritance`). It appears only in the compatibility
rows/graphs (`m-case-format`). A
**concrete-target** read needs no tag in its projection (the caller already knows
the variant) and carries no `familyVariant`: it projects the concrete instance's
own columns and injects `t0.kind = ?`.

The independent `then.referenceSql` oracle for a tag-filtered read spells the
value inline (`where kind = 'card'`); for an abstract-root read it is the plain
whole-table select. Table-per-concrete-subtype lowering (`union all` over the
effective concrete tables) is specified next.

### Inheritance — table-per-concrete-subtype lowering

A `table-per-concrete-subtype` family maps **each concrete subtype to its own
table** (`m-inheritance`); there is **no shared table and no tag column**. A
concrete table physically carries the full inherited attribute chain (root +
abstract-ancestor columns) plus that subtype's own columns in its canonical
Storage Layout.

#### Concrete-subtype read

A read whose queried position resolves to a **single** concrete subtype is an
**ordinary single-table read** of that subtype's table — no tag predicate, no
`union all`. The subtype is selected by *which* table is queried. The projection is
the applicable slots from its Entity Layout view, and it carries **no
`familyVariant`** (the caller queried a known variant):

```yaml
# target: Invoice — ordinary single-table read of the concrete table:
- sql:
    postgres: select t0.id, t0.title, t0.currency, t0.amount_due from invoice t0
```

#### Abstract read — `union all` over the effective concrete tables

A read whose queried position resolves to **two or more** concrete subtypes — an
abstract root, an abstract subtype, or a `narrow` (`m-predicate`) to multiple
concretes — lowers to canonical **`union all`**, one branch per concrete subtype in
that effective set, in the family's canonical **alphabetical order** (by entity name,
`m-inheritance`). Each branch is an ordinary single-table read of that concrete's
table (each branch's alias scheme restarts at `t0`, and the branch order is
preserved). A sibling branch outside the effective set contributes no branch — an
abstract-subtype read `union all`s only that subtype's concrete descendants.

Every branch projects the **same stable Position Layout sequence**. Declaration-
backed contributors follow `Identity`, `Domain`, `Temporal`, `Audit`, then
`Document` tier order (there is no physical discriminator), with root-first
ancestry, local declaration order, and canonical concrete order stable within
each tier. The SQL-owned **`familyVariant`** literal follows those contributors.

Result aliases for the declaration-backed contributors are allocated
hygienically in that Position Layout order. Before allocation, the complete
reservation set is every contributor's physical column spelling plus the synthetic
`family_variant` carrier. A contributor retains its physical spelling as the result
alias only when that spelling occurs once in the superset and is not
`family_variant`. Every other contributor receives the first unallocated
`parallax_attr_N`, starting at `N = 0`; allocation skips candidates in the complete
reservation set and aliases already allocated. Thus an authored physical
`parallax_attr_0` remains reserved even when another contributor needs an internal
alias, and a physical `family_variant` never collides with the synthetic carrier.
The same allocated alias occupies that contributor's slot in every branch, whether
the branch projects its column or a typed `NULL` placeholder.

After execution, materialization uses the selected branch's exact concrete identity
to remap each applicable result alias back to that contributor's physical column
spelling and discards non-applicable duplicate-spelling slots. Internal aliases are
never member names and never appear in the materialized graph unless an authored
physical column itself has that spelling.

A column not applicable to a branch is a **`NULL` placeholder** — `cast(null as
<type>)` in that branch's declared column type, so the union's result column types
resolve deterministically rather than defaulting to an untyped `NULL`. The cast
**target-type spelling is a dialect decision** owned by `m-dialect` and **diverges
from the DDL column type for strings**:

| Declared column type | Postgres placeholder cast | MariaDB placeholder cast |
|---|---|---|
| `decimal(p, s)` | `cast(null as decimal(p, s))` | `cast(null as decimal(p, s))` (identical) |
| bounded `string` (`maxLength n`) | `cast(null as varchar(n))` | `cast(null as char(n))` |
| unbounded `string` | `cast(null as text)` | `cast(null as text)` |

MariaDB's `CAST` target grammar **does not accept `varchar`** — a bounded string
placeholder casts to **`char(n)`** even though the *column* type is `varchar(n)` on
both dialects (`m-dialect`: string types map to `char` under MariaDB `CAST`). This is
the general rule; a future dialect supplies its own placeholder-cast spelling behind
the same `m-dialect` seam.

Because nothing else identifies a row's source table after the union, `familyVariant`
is projected **as a subtype variant-spelling string literal per branch** (the
family-unique bare name or ambiguity-required canonical qualified spelling, not
the physical `tagValue` — there is none). This is the settled
asymmetry with table-per-hierarchy: TPH projects the raw tag column and derives
`familyVariant` at materialization (resolved Q6), whereas TPCS projects the variant
literal directly:

```yaml
# target: Record (abstract root over two canonically qualified SharedVariant
# entities) — case 120's reservation and collision-skipping witness. Physical
# family_variant and parallax_attr_0 spellings are restored after alias remapping:
- sql:
    postgres: select t0.id, t0.family_variant parallax_attr_1, t0.parallax_attr_0 parallax_attr_2, cast(null as varchar(64)) parallax_attr_3, 'archive.SharedVariant' family_variant from archive_shared t0 union all select t0.id, t0.family_variant parallax_attr_1, cast(null as varchar(64)) parallax_attr_2, t0.parallax_attr_0 parallax_attr_3, 'catalog.SharedVariant' family_variant from catalog_shared t0
    mariadb: select t0.id, t0.family_variant parallax_attr_1, t0.parallax_attr_0 parallax_attr_2, cast(null as char(64)) parallax_attr_3, 'archive.SharedVariant' family_variant from archive_shared t0 union all select t0.id, t0.family_variant parallax_attr_1, cast(null as char(64)) parallax_attr_2, t0.parallax_attr_0 parallax_attr_3, 'catalog.SharedVariant' family_variant from catalog_shared t0
```

The equivalent authored spellings of a narrow collapse to the same lowering: a
`narrow` to an abstract subtype and a `narrow` to that subtype's explicit concrete
list produce the same effective set and therefore the same branches, in canonical
alphabetical order, regardless of the authored `to` order. `familyVariant` appears only in the
compatibility rows/graphs (`m-case-format`); the projected `family_variant` literal
is the on-the-wire carrier the harness renames to `familyVariant`.

### Inheritance — concrete-subtype DML

A create / update / delete of an inheritance participant is a **concrete-subtype
write** (`m-inheritance`): the payload's accepted fields are exactly the target's
ancestry chain, `tag` / `tagValue` / `familyVariant` are never authored, and the
target is a concrete subtype (an abstract-target or keyless set-based write is
refused pre-SQL, `m-case-format`). The DML shape depends on the strategy.

#### Table-per-hierarchy DML

Every concrete subtype shares one table discriminated by the root's tag column. The
tag is **framework-owned metadata**: an **insert** sets it from the subtype's
`tagValue` (slotted at its Entity Layout's `Discriminator` position, after every
`Identity` slot, so
the value list carries the derived tag exactly as the versioned insert carries the
derived initial version); an existing-row statement (**update** / **delete**, and the
temporal closes of `m-txtime-write` / `m-bitemp-write`) carries a **tag guard** —
`and <tag.column> = ?` — so it touches only that subtype's rows in the shared table.

| Mutation | Canonical Postgres DML | Binds |
|---|---|---|
| **insert** | `insert into payment(id, kind, amount, card_network) values (?, ?, ?, ?)` | `[<pk>, <tagValue>, …row…]` |
| **update** | `update payment set amount = ? where id = ? and kind = ?` | `[…set…, <pk>, <tagValue>]` |
| **delete** | `delete from payment where id = ? and kind = ?` | `[<pk>, <tagValue>]` |

The tag guard is positioned **immediately after the primary-key equality** — it
joins the **identity predicates**, not the tail of the `where` clause. The insert's
tag bind sits in layout order; the update/delete's tag bind sits with the
pk (right after it). DML keeps its canonical DML shape (`m-sql` rule 1): an
**unaliased** target table with **bare** columns, so the tag guard reads `kind`, not
`t0.kind`.

**Opt-lock composition (`m-inheritance` × `m-opt-lock`).** When the entity is
versioned and the unit of work runs optimistic (`m-opt-lock`), a concrete-subtype
`UPDATE` advances the version in the `set` and **gates** on the observed version —
and the gate still **binds last**. The tag guard rides with the identity predicates
(after the pk); the version gate follows it:

```yaml
# concrete-subtype gated UPDATE (optimistic), the resolved Q9 bind order end to end:
- sql:
    postgres: update animal set name = ?, version = ? where id = ? and kind = ? and version = ?
  binds: [<new-name>, <new-version>, <pk>, <tagValue>, <observed-version>]
```

That is `[…set values…, pk, tagValue, observed-version]`: the tag guard binds with
the identity predicates immediately after the pk, and `m-opt-lock`'s invariant —
**the version gate binds last** — survives inheritance composition verbatim (there
is no inheritance exception to it). The locking-mode form drops the version gate and
keeps `… where id = ? and kind = ?` (tag guard still present, no gate).

#### Table-per-concrete-subtype DML

Each concrete subtype owns its **own table** and carries no tag, so the subtype is
selected by *which* table the DML targets. An **insert** writes the concrete table
with the present cells filtered from its Entity Layout; a **delete** removes the keyed row
from that same table. There is no tag column and therefore **no tag guard**:

| Mutation | Canonical Postgres DML | Binds |
|---|---|---|
| **insert** | `insert into invoice(id, title, currency, amount_due) values (?, ?, ?, ?)` | `[…full chain…]` |
| **delete** | `delete from invoice where id = ?` | `[<pk>]` |

The insert's column list is the target's layout-ordered slots present in the
payload (a nullable inherited slot the payload omits is simply absent from the
list, defaulting to `NULL`); a sibling branch's write names *its* table, never a
shared one (`memo` for a `Memo`, `invoice` for an `Invoice`). A concrete-subtype
`UPDATE` under table-per-concrete-subtype is the ordinary single-table versioned /
non-versioned form (`m-opt-lock`); no tag guard applies.

### Inheritance — temporal composition

A temporal inheritance participant composes the milestone-chaining **writes**
(`m-txtime-write` / `m-bitemp-write`) and the as-of **reads** (`m-temporal-read`)
with the strategy's routing and tag guard. The temporal semantics are
**unchanged** — the close/inactivate keying, the head/middle/tail chaining, and the
injected as-of predicate are exactly the standalone forms above; only the **table**
the DML names and the **identity predicates** it carries differ. The temporal axes
are declared on the family's abstract root and inherited by every concrete subtype
(`m-inheritance`), so every concrete instance is a milestone-owning row.

#### Table-per-hierarchy temporal writes — tag-guarded closes, tag-set chains

Under `table-per-hierarchy` the whole family shares one milestone table. Every
temporal statement that targets **existing** rows — the Transaction-Time-Only **close**
(`m-txtime-write`) and the bitemporal **inactivation** (`m-bitemp-write`) — carries
the **tag guard** among the identity predicates, immediately **after** the
primary-key equality and **before** the address's per-axis upper bounds; every
chained **insert** (the Transaction-Time-Only chain, or the bitemporal `head` / `middle` / `tail`)
sets the tag column from the subtype's `tagValue` in its Entity Layout position,
exactly as a non-temporal concrete-subtype insert does (above). There is no temporal
exception to the resolved-Q9 bind order: the tag guard rides with the identity
predicates; any gate the temporal write already carries (the optimistic
`txStart` / physical `in_z` gate, `m-txtime-write` / `m-bitemp-write`) still binds
**last**.

| Statement | Canonical Postgres DML | Binds |
|---|---|---|
| **Transaction-Time-Only insert** | `insert into reading(id, kind, celsius, in_z, out_z) values (?, ?, ?, ?, ?)` | `[<pk>, <tagValue>, …row…, <txInstant>, infinity]` |
| **Transaction-Time-Only close** (`terminate` / `update` step 1) | `update reading set out_z = ? where id = ? and kind = ? and out_z = ?` | `[<txInstant>, <pk>, <tagValue>, infinity]` |
| **bitemporal inactivation** (`terminate` / `terminateUntil` / `update` / `*Until` step 1) | `update instrument set out_z = ? where id = ? and kind = ? and thru_z = ? and out_z = ?` | `[<txInstant>, <pk>, <tagValue>, <observedValidEnd>, infinity]` |
| **bitemporal head / middle / tail insert** | `insert into instrument(id, kind, price, coupon, from_z, thru_z, in_z, out_z) values (?, …, ?)` | `[<pk>, <tagValue>, …domain row…, <from_z>, <thru_z>, <txInstant>, infinity]` |

The close / inactivation addresses its milestone exactly as its standalone form does
(the Transaction-Time-Only / bitemporal write sequences above) — the primary key plus
one exclusive upper bound per As-Of Axis, which on a single axis is `out_z` /
`infinity` alone; the tag guard is inserted **between** the primary key and those
bounds — `… where id = ? and kind = ? and out_z = ?` for a Transaction-Time-Only
milestone, `… where id = ? and kind = ? and thru_z = ? and out_z = ?` for a
bitemporal rectangle — so it touches only the subtype's own milestones in the
shared table. The chained inserts write the full
physical row (a milestone always writes the whole row) with the tag column slotted
after the primary key. The corpus witnesses are `m-inheritance-090` (txtime terminate),
`-094` (bitemporal terminate), `-096` (bitemporal `terminateUntil`).

#### Table-per-concrete-subtype temporal writes — own-table routing

Under `table-per-concrete-subtype` each concrete subtype owns its milestone table and
carries no tag, so a temporal write is the ordinary standalone milestone-chaining
sequence (`m-txtime-write` / `m-bitemp-write`) targeting **that subtype's own table** —
no tag guard, no shared table. The close / inactivation is `update <concrete> set
out_z = ? where <pk> = ? and out_z = ?` for a Transaction-Time-Only milestone and
`… where <pk> = ? and thru_z = ? and out_z = ?` for a bitemporal rectangle; every
chained insert writes `<concrete>`.
The witnesses are `m-inheritance-091` / `-095` / `-097`.

#### Temporal abstract reads — per-branch as-of

A temporal **abstract-target** read composes the injected as-of predicate
(`m-temporal-read`) with the strategy's abstract-read lowering. Under
`table-per-hierarchy` it is the single shared-table select of the abstract-read
lowering above with the injected as-of predicate appended after the tag predicate
(or, for an abstract-**root** read, after the projection with no tag predicate); the
raw tag column is still projected so `familyVariant` materializes (`m-inheritance-092`).
Under `table-per-concrete-subtype` it is the `union all` of the abstract-read
lowering, and the injected as-of predicate is applied **per branch**: every branch
carries its own as-of `where` fragment over its own alias, in the same
Valid-Time-first bind order as a single-entity as-of read (`m-temporal-read` /
`m-navigate` as-of propagation). Because every concrete branch inherits the same axes
from the root, each branch's as-of fragment is identical, so the union's binds are
the per-branch as-of binds repeated in **alphabetical branch order**:

```yaml
# target: Rate (Bitemporal abstract root over DepositRate / LoanRate), Valid Time
# finite v, Transaction Time Latest — each branch injects `from_z <= ? and thru_z > ? and out_z = ?`
# (Valid-Time-first) and the binds repeat per branch in alphabetical branch order:
- sql:
    postgres: select t0.id, t0.amount, t0.grade, cast(null as decimal(18, 2)) spread, t0.from_z, t0.thru_z, t0.in_z, t0.out_z, 'DepositRate' family_variant from deposit_rate t0 where t0.from_z <= ? and t0.thru_z > ? and t0.out_z = ? union all select t0.id, t0.amount, cast(null as varchar(8)) grade, t0.spread, t0.from_z, t0.thru_z, t0.in_z, t0.out_z, 'LoanRate' family_variant from loan_rate t0 where t0.from_z <= ? and t0.thru_z > ? and t0.out_z = ?
  binds: [v, v, infinity, v, v, infinity]
```

The witness is `m-inheritance-093`. As with any abstract read, the projection is the
stable superset (here the interval columns are part of the inherited chain) plus the
per-branch `familyVariant` literal; a column not applicable to a branch is the
`cast(null as <type>)` placeholder in that dialect's type (`m-dialect`).

### valueObject — structured-column read and filter

A `valueObject` is stored in **one structured-document column** (`m-core` /
`m-value-object`), not column-flattened. Reading the whole value object — an
**instance-form** read selecting its layout `Document` slot — projects that backing
column directly (`t0.address`). Reading or filtering an **inner
attribute** uses the `m-predicate` nested-attribute access form and lowers through
the `m-dialect` **nested-extraction** seam to a per-dialect extraction. The JSON
path is always carried as `?` bind(s) (rule 4 — never inlined, which keeps the
golden SQL a normalizer fixed point); the extraction function and the bind shape
differ per dialect (`m-dialect`):

| Predicate | Postgres canonical fragment | MariaDB canonical fragment |
|---|---|---|
| project the whole object | `t0.address` (in the `select` list) | `t0.address` (identical) |
| `nestedEq(Class.vo.field, v)` | `jsonb_extract_path_text(t0.address, ?) = ?` | `json_value(t0.address, ?) = ?` |
| `nestedNotEq(Class.vo.field, v)` | `not jsonb_extract_path_text(t0.address, ?) = ?` | `not json_value(t0.address, ?) = ?` |
| nested deeper (`vo.a.b`) | `jsonb_extract_path_text(t0.address, ?, ?) = ?` | `json_value(t0.address, ?) = ?` |
| `nestedGt(vo.geo.num, v)` (numeric) | `cast(jsonb_extract_path_text(t0.address, ?, ?) as double precision) > ?` | `cast(json_value(t0.address, ?) as double) > ?` |
| `nestedGte` / `nestedLt` / `nestedLte` | as `nestedGt`, with `>=` / `<` / `<=` | as `nestedGt`, with `>=` / `<` / `<=` |
| `nestedBetween(vo.geo.num, lo, hi)` (numeric) | `cast(jsonb_extract_path_text(t0.address, ?, ?) as double precision) between ? and ?` | `cast(json_value(t0.address, ?) as double) between ? and ?` |
| `nestedIn(vo.field, [v, …])` | `jsonb_extract_path_text(t0.address, ?) in (?, …)` | `json_value(t0.address, ?) in (?, …)` |
| `nestedNotIn(vo.field, [v, …])` | `not jsonb_extract_path_text(t0.address, ?) in (?, …)` | `not json_value(t0.address, ?) in (?, …)` |
| `nestedLike(vo.field, p)` | `jsonb_extract_path_text(t0.address, ?) like ?` | `json_value(t0.address, ?) like ?` |
| `nestedNotLike(vo.field, p)` | `jsonb_extract_path_text(t0.address, ?) not like ?` | `json_value(t0.address, ?) not like ?` |
| `nestedStartsWith` / `nestedEndsWith` / `nestedContains` | as `nestedLike`, the affix pattern bound (plus `escape ?` when escaping changed it) | as `nestedLike`, identically |
| `nestedLike(vo.field, p)` (case-insensitive) | `lower(jsonb_extract_path_text(t0.address, ?)) like lower(?)` | `lower(json_value(t0.address, ?)) like lower(?)` |
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

The compared `value` is a **typed** `m-predicate` literal, and which form is bound
follows `m-dialect`'s two typed-cast tables. An attribute in the **cast** table —
the numeric family and `boolean` — casts the extraction to its declared neutral
type before comparing (the fragments in the table above show the uncast form; the
`nestedGt` rows show the cast one) and binds the **managed value** in that type: a
`decimal(p, s)` field binds the exact decimal rather than a JSON number, and a
`boolean` field binds the boolean. Each of the six **text-compared** types —
`string` included — compares the extraction directly against that type's
**comparison text** (`m-document-codec`): the characters the extraction itself
returns, which is the stored text as above. That set is fixed by comparison
behavior rather than by document form, so `decimal(p, s)` — a JSON string in the
document — is not in it. A `boolean` field cannot join them either, because the
two extractions disagree on its characters —
`jsonb_extract_path_text` returns `true` / `false` where `json_value` returns `1` /
`0` — so one bound text would match on Postgres and silently match nothing on
MariaDB. A future dialect with a different
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
the **typed cast** (`m-dialect`) to the extraction before the SQL comparison when
the attribute's declared type is in that seam's cast table, since text order is not
numeric order; over a type whose canonical spelling already orders as text they
compare the extraction directly. `nestedBetween` follows the same rule and lowers to **one**
`<extraction> between ? and ?` — never a pair of
comparisons (`m-predicate`) — binding the JSON path first, then `lower`, then
`upper`. `nestedIn` lowers the membership to `<extraction> in (?, …)` — the JSON
path bind(s) first, then one bind per list value in `values` order — and
`nestedNotIn` to the same fragment under a **leading `not`**, adding no bind.

The five string predicates apply **no** cast — their leaf is `String` by the
non-string-member rule (`m-predicate`), so the extraction is already the text they
match — and lower to `<extraction> like ?`, `nestedNotLike` to
`<extraction> not like ?` (the **infix** negation the scalar `notLike` renders, not
the leading `not` the membership and presence forms normalize
to). The bind order is the JSON path bind(s), then the pattern, then
the escape character when the affix escaping actually changed the literal; the
`escape ?` clause and its bind are emitted **only** then, exactly as the scalar
affix forms do. Under `caseInsensitive` both sides fold —
`lower(<extraction>) like lower(?)` — which changes no bind count. The worked
escape example is the scalar one applied to a nested extraction:
`nestedContains(Customer.address.street, '50%')` binds the path, then `'%50\%%'`,
then `'\'`.

`nestedIsNull` lowers to `<extraction> is null` and `nestedIsNotNull` to a
**leading `not`** (`not <extraction> is null`) — the same negation normalization the
scalar `isNotNull`/`notIn`/`nestedNotEq` forms use. Because every not-present state casts
or compares SQL `NULL` (the absence-collapse rule, `m-predicate`), all of these
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
state casts or compares SQL `NULL` and the absence-collapse rule (`m-predicate`)
holds portably. The compatibility corpus pins all four states on Postgres **and**
MariaDB (`m-value-object-013` asserts all four at `geo.country`).

#### To-many — exists / notExists and any-element predicates

A `multiplicity: many` value object is an ordered JSON **array** in the same column
(`m-value-object`). Filtering it lowers through the `m-dialect` **array-traversal**
seam, which the two dialects spell with **different function families** (Postgres a
correlated `jsonb_array_elements` unnest, MariaDB the `json_contains` / `json_length`
containment family — `m-dialect` explains why MariaDB does not use `JSON_TABLE`).
The path segment(s) reaching the array are `?` binds (rule 4) exactly as for the
scalar extraction, so the `binds` are a **per-dialect map** (`m-case-format`); the
element alias is the next alias after the root (`t1`, or `t1`/`t2` for two
independent any-element subqueries).

**Both dialects guard against a non-array `many` value.** Absence-collapse
(`m-predicate`) folds a member that is a SQL `NULL` column, a missing key, an
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

| Predicate | Postgres canonical fragment | MariaDB canonical fragment |
|---|---|---|
| `nestedExists(Class.vo.arr)` (non-empty) | `exists (select 1 from jsonb_array_elements(<arr>) t1)` | `<g> and json_length(t0.address, ?) > ?` |
| `nestedNotExists(Class.vo.arr)` (empty-or-absent) | `not exists (select 1 from jsonb_array_elements(<arr>) t1)` | `not coalesce(<g> and json_length(t0.address, ?) > ?, ?)` |
| flat `nestedEq(Class.vo.arr.field, v)` (any-element) | `exists (select 1 from jsonb_array_elements(<arr>) t1 where jsonb_extract_path_text(t1.value, ?) = ?)` | `<g> and json_contains(t0.address, ?, ?)` |
| flat `nestedBetween(Class.vo.arr.field, lo, hi)` (any-element) | `exists (select 1 from jsonb_array_elements(<arr>) t1 where jsonb_extract_path_text(t1.value, ?) between ? and ?)` | — not expressible by the `json_contains` containment seam; reject per `m-dialect` |
| flat `nestedNotIn(Class.vo.arr.field, [v, …])` (any-element) | `exists (select 1 from jsonb_array_elements(<arr>) t1 where not jsonb_extract_path_text(t1.value, ?) in (?, …))` | — not expressible by the `json_contains` containment seam; reject per `m-dialect` |
| flat `nestedStartsWith(Class.vo.arr.field, s)` (any-element) | `exists (select 1 from jsonb_array_elements(<arr>) t1 where jsonb_extract_path_text(t1.value, ?) like ?)` | — not expressible by the `json_contains` containment seam; reject per `m-dialect` |
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
as `m-predicate`'s absence collapse requires.

**The candidate document comes from `m-document-codec`, and it is a third bind
form.** It is that module's `encodeCandidate` over the element's own shape: each
constrained path placed where the stored element would place it — nesting through a
`one` occurrence exactly as the document nests — and spelled with that leaf's
**document encoding**. Neither literal of the scalar split above works here, and
neither fails loudly: `json_contains` compares **JSON values**, so a `boolean`
element bound as the managed value its cast comparison takes gives the candidate
`{"flag": 1}`, which matches no element storing a JSON boolean, and a
`decimal(p, s)` bound the same way gives `{"amt": 1.50}`, which matches no element
storing the exact digit string `"1.50"`. A `date`, `uuid`, or `bytes` candidate a
host serializer produced would miss for the same reason — the stored element
carries the codec's canonical spelling and containment is exact. So the candidate
is built through the codec, never assembled around a predicate literal, exactly as
the atomic document write is; the dialect adapts the finished candidate to its
structured-document type at bind time.

**The candidate therefore rides the bind list as a document, not as its rendered
text**, exactly as the atomic value-object write's document does (below): the
serialized form is what the MariaDB adapter produces *below* this seam, so it is
neither this lowering's output nor a golden's authored value (`m-case-format`). A
golden that spelled the candidate as text would fix a key order and a separator
convention that nothing specifies, and two conforming implementations whose
serializers differ by one space would then disagree on a document
`m-document-codec` says is one value.

**One constrained path, one candidate key.** The lowering builds
`encodeCandidate`'s constraints from the element predicates of the scoped `where`
(or from the single flat predicate), one entry per constrained element-relative
path. A conjunction that constrains the **same** path twice with the same value is
one constraint and collapses to one entry; one that constrains it with two
**different** values has no candidate at all — an object carries one value per key,
and dropping either constraint yields a candidate that matches elements the
predicate excludes — so it is outside the containment seam and MariaDB rejects it
with the capability diagnostic (`m-dialect`, "Scope of the containment golden").
Postgres, whose element predicates ride one alias rather than one object, lowers it
unchanged and answers with no rows.

```yaml
# nestedEq(Customer.address.phones.type, 'home') — flat any-element:
- sql:
    postgres: select t0.id, t0.name from customer t0 where exists (select 1 from jsonb_array_elements(case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t1 where jsonb_extract_path_text(t1.value, ?) = ?)
    mariadb: select t0.id, t0.name from customer t0 where json_type(json_extract(t0.address, ?)) = ? and json_contains(t0.address, ?, ?)
  binds:
    postgres: [phones, 'array', phones, '[]', type, home]
    mariadb: ['$.phones', 'ARRAY', { type: home }, '$.phones']
# nestedExists(Customer.address.phones, where: type='home' AND number='555-9999') — same-element:
- sql:
    postgres: select t0.id, t0.name from customer t0 where exists (select 1 from jsonb_array_elements(case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t1 where jsonb_extract_path_text(t1.value, ?) = ? and jsonb_extract_path_text(t1.value, ?) = ?)
    mariadb: select t0.id, t0.name from customer t0 where json_type(json_extract(t0.address, ?)) = ? and json_contains(t0.address, ?, ?)
  binds:
    postgres: [phones, 'array', phones, '[]', type, home, number, '555-9999']
    mariadb: ['$.phones', 'ARRAY', { type: home, number: '555-9999' }, '$.phones']
```

The unscoped `and(nestedEq(phones.type, 'home'), nestedEq(phones.number,
'555-9999'))` lowers to **two independent** any-element checks (Postgres two `exists`
subqueries with aliases `t1`, `t2`, each with its own `<arr>` guard; MariaDB two
`<g> and json_contains` conjuncts — each flat any-element predicate self-guards), so
a row whose two fields live in *different* elements matches — the discriminating
contrast with the same-element scoped form above (`m-predicate`; corpus
`m-value-object-018` vs `-019`). The independent `then.referenceSql` oracle spells
the traversal a **different** way per dialect: Postgres the `@>` containment operator
(`t0.address -> 'phones' @> '[{"type":"home"}]'`, which natively returns false on a
non-array) and `jsonb_array_length` (under a `jsonb_typeof` guard), MariaDB an
array-type-guarded `JSON_TABLE(…)` element unnest (parse-only, executed against real
MariaDB — the element-unnest golden SQL cannot use, since its `COLUMNS ( … PATH '…')`
paths cannot be `?` binds and do not normalize). Corpus `m-value-object-021` /
`-022` pin that a non-array `phones` collapses even when its scalar value or object
content collides with the query value.

A range, a negated membership, or a string predicate crossing a `many` member
composes the same way, in
either scope. The bind order is the guarded unnest's own binds first, then the
element path segment(s), then the predicate's own binds in authored order — `lower`
then `upper` for a range, one per list value for a membership, the pattern (then the
escape character, when escaping applies) for a string predicate. Because the whole
range, list, or pattern rides **one** element predicate on **one** alias, a single
element must satisfy it (`m-predicate`):

```yaml
# nestedBetween(Customer.address.phones.number, '555-0000', '555-1234') — any-element:
- sql:
    postgres: select t0.id, t0.name from customer t0 where exists (select 1 from jsonb_array_elements(case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t1 where jsonb_extract_path_text(t1.value, ?) between ? and ?)
  binds:
    postgres: [phones, 'array', phones, '[]', number, '555-0000', '555-1234']
# nestedStartsWith(Customer.address.phones.number, '555-1') — any-element:
- sql:
    postgres: select t0.id, t0.name from customer t0 where exists (select 1 from jsonb_array_elements(case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t1 where jsonb_extract_path_text(t1.value, ?) like ?)
  binds:
    postgres: [phones, 'array', phones, '[]', number, '555-1%']
# nestedExists(Customer.address.phones, where: nestedNotIn(type, [work])) — same-element:
- sql:
    postgres: select t0.id, t0.name from customer t0 where exists (select 1 from jsonb_array_elements(case when jsonb_typeof(jsonb_extract_path(t0.address, ?)) = ? then jsonb_extract_path(t0.address, ?) else cast(? as jsonb) end) t1 where not jsonb_extract_path_text(t1.value, ?) in (?))
  binds:
    postgres: [phones, 'array', phones, '[]', type, work]
```

The MariaDB `json_contains` golden expresses **equality/containment** element
predicates only (any-element `nestedEq`, same-element equality conjunctions **over
distinct paths**);
non-equality element predicates through a `many` segment — `nestedGt` / `nestedLt` /
`nestedNotEq` / `nestedBetween` / `nestedNotIn`, any of the five string predicates,
or a `where` compound with a
range/negated membership/string predicate/`or`/`not`, or one whose equalities
constrain a single path with two different values — need a set-returning
unnest, which lies **outside what the MariaDB containment seam can express**; a
MariaDB implementation rejects them with a capability diagnostic rather than
lowering them (`m-dialect`, "Scope of the containment golden"). Postgres's
`jsonb_array_elements` lowering is fully general; the corpus's **dual-dialect**
to-many coverage is equality-based accordingly, so these forms carry a Postgres
golden only.

#### valueObject — atomic document write

A `valueObject` is **written atomically as one document** (`m-value-object`). On
an insert or an update the backing column takes **one bind** in the entity's
layout `Document` position, carrying the whole embedded composite; the write path
**never** decomposes it into path-level binds. Unlike the read extraction — whose
per-dialect function family and bind holes diverge (`json_value` vs
`jsonb_extract_path_text`, one `'$.a.b'` bind vs per-segment binds) — the write DML
is **identical on both dialects**: a plain column bind, no JSON function. The
document value itself is adapted to the dialect's structured-document type at bind
time (Postgres wraps it as `jsonb`, MariaDB serializes it to `json` text), so the
**hole structure is shared** and the `binds` are authored as a single flat array
(`m-case-format` — the shared-hole form), the document riding as one element:

```yaml
# insert one Customer, binding the whole address document in layout position:
- sql:
    postgres: insert into customer(id, name, address) values (?, ?, ?)
    mariadb: insert into customer(id, name, address) values (?, ?, ?)
  binds:
    - 100
    - Solveig
    - { street: 12 Aurora Ave, city: Tromso, geo: { country: 'NO' }, phones: [ { type: home, number: '555-0001' } ] }
# replace the WHOLE document (no path-level update, no merge):
- sql:
    postgres: update customer set address = ? where id = ?
    mariadb: update customer set address = ? where id = ?
  binds:
    - { street: 9 New Way, city: Stavanger }
    - 100
# null out a nullable value object → SQL NULL (the whole column, not a document of nulls):
- sql:
    postgres: update customer set address = ? where id = ?
    mariadb: update customer set address = ? where id = ?
  binds: [null, 100]
```

The value-object column appears in the `INSERT` column list and the `UPDATE`
`set` clause **exactly like a scalar column** — one `?` in its layout position,
after every scalar tier. A whole-document update **replaces** the column value;
there is no `UPDATE` of a path inside the document (`m-value-object`). A null bind
stores SQL `NULL`. On a temporal owner the same document rides milestone chaining
like any scalar column (the milestone-chaining write sequences above); there is no
value-object-specific write machinery. The harness proves each form by **applying**
the golden DML and reading the resulting `then.tableState` document back (decoding
the structured-document column to a Python structure so both dialects compare
against the authored document), the write-sequence oracle (`m-case-format`) — corpus
`m-value-object-025` (insert), `-026` (whole-document update), `-027` (null-out).

### Relational Document Layout — document-path predicates and ordering

Under Relational Document Layout a predicate or ordering term over a
document-resident member lowers through the **same** `m-dialect` extraction and
typed-cast seams the nested value-object forms above already use. Two things
change, and nothing else does.

**The extraction target and path come from Member Placement, not from a string.**
The member's placement (`m-storage-layout`) supplies the Structured Column and
the complete Document Path; SQL binds that path's segments in the dialect's own
shape and never re-splits an authored dotted spelling, appends an occurrence name
by hand, or reconstructs a path from member names. A document-resident top-level
Attribute is a one-segment path — the ordinary scalar comparison that would have
been `t0.display_name = ?` under Columns layout becomes an extraction over
`t0.payload` with one path bind.

**Whether the extraction casts is fixed by the declared Neutral Type.** The
extraction yields text, and `m-dialect`'s two typed-cast tables say which types do
what: a member of the **numeric family** — `int32`, `int64`, `float32`, `float64`,
`decimal(p,s)` — and a `boolean` member cast through the typed-cast form before
comparing, exactly as a numeric `nestedGt` does today; each of the six
**text-compared** types — `string`, `bytes`, `date`, `time`, `timestamp`, `uuid` —
compares the extracted text directly, with no cast, because `m-document-codec`'s
canonical spelling for it already equates and orders correctly as text. Which
family a type falls in is a comparison-behavior question, not a document-form one:
`decimal(p, s)` encodes as a JSON string and casts with the numeric family
regardless. Those two tables are closed over the declarable types, so no
document-resident member is left without a comparison form.

**Which literal is bound follows the same split, and the two are not
interchangeable.** A text comparison binds the type's **comparison text**
(`m-document-codec`) — the characters the extraction itself returns, which for
those six spellings is the stored text unquoted. A cast comparison binds the
**managed value in its declared Neutral Type**, through the dialect's typed bind
normalization (`m-dialect`), because the cast has already moved the comparison into
the engine's own type system. Neither side may substitute the member's document
encoding for the other's answer:

- a `decimal(p, s)` member encodes as an exact digit string, so there is no
  encoded JSON number to bind; producing one would compare
  `cast(<extraction> as decimal(p, s))` against a binary float and match every
  stored decimal that rounds to the same float, not the one that equals the
  literal;
- a `boolean` member encodes as a JSON boolean, and the two dialects extract it as
  different characters — `true` / `false` on Postgres, `1` / `0` on MariaDB — so it
  has no comparison text at all and compares through its cast instead.

Everything else is unchanged: the absence collapse, the operator-by-operator
fragments, the negation normalizations, the per-dialect bind-hole divergence that
makes `binds` a per-dialect map, and the `many` traversal seam with its MariaDB
containment scope.

#### Variant partitioning for a non-uniform path

A shared table-per-hierarchy document is **heterogeneous**: two disjoint sibling
branches may derive one Document Path (`m-storage-layout`), and a subtype-only
member's key is simply absent from a sibling variant's document. A cast over such
a path must therefore never evaluate against a row of the wrong variant.

**When a path is applicable to every concrete variant the statement selects,
nothing changes**: one statement, one extraction, the tag predicate composed as
today. Existing uniform-path statement counts, bind order, and golden SQL do not
move.

**When a path is not applicable to every concrete variant the statement selects,
the read is partitioned by variant** as one `union all` of tag-filtered branches,
so each branch's extraction and cast see only rows of its concrete variant. The
branches retain canonical concrete order and branch-local bind order; the read
remains one statement and one round trip.

Each tag-filtered branch is an optimizer barrier, not a flattenable derived
table. PostgreSQL appends `offset 0` to the inner tag-filtered SELECT; MariaDB
appends `limit ?` and binds its unsigned maximum row count,
`18446744073709551615`, immediately after the tag bind. These dialect forms
prevent the outer cast predicate from being pulled into the base-table scan, so
the tag filter completes before any variant-specific extraction or cast is
evaluated.

A locking partitioned read wraps that union as a derived identity relation,
joins it back to the shared TPH base Table on every primary-key column, projects
from the base alias, and applies the dialect's read-lock suffix to the outer
SELECT. PostgreSQL qualifies `for share` with that base alias; MariaDB's
`lock in share mode` is unqualified. The derived relation projects only the
identity needed for the join, so casts remain isolated in tag-disjoint branches
while the returned base rows—not a materialized derived result—are locked in one
atomic acquisition. Ordering, limit, projection order, result form, and document
decoding retain the same outer-read rules as an unpartitioned TPH
read.

Partitioning is required rather than merely preferred, because the alternative
was measured not to hold. Wrapping the cast in a tag-aware `case` is not
sufficient on PostgreSQL, whose documented constant-folding of a `case` branch
can raise from a branch no row reaches; and placing the tag predicate elsewhere
in the `where` clause is plan-dependent, since a subquery that becomes an
optimization barrier evaluates the cast before the filter. MariaDB fails
differently and worse: a failed `CAST` in a non-data-modifying statement is a
warning rather than an error under every `SQL_MODE`, so the same query returns a
**silently coerced** value instead of raising. One engine's hard error and the
other's wrong answer are not a portable contract, which is why the guard is a
statement-shape rule rather than an expression-shape rule.

This reuses machinery that already exists. A subtype-declared member can never be
referenced without a compatible `narrow` (`m-predicate`), so every legal
subtype-specific predicate already carries a resolved variant position and a tag
fragment; table-per-concrete-subtype reads are already a per-branch `union all`
with a fresh context per branch. Partitioning applies that same fan-out at a
finer granularity.

A **broad polymorphic read** resolves the variant tag first and decodes only that
variant's applicable document shape, so projection needs no partitioning: the
Structured Column is projected raw and the row transform chooses the shape.
Under table-per-concrete-subtype each branch projects its own Structured Column
and decodes against its own applicable shape before the union result is
normalized.
