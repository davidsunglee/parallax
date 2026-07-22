# m-dialect — Database Dialect & Portability

All SQL-dialect variation **MUST** live behind a single normative `Dialect`
interface. This is the **only** place dialect-specific SQL is allowed. The
promise "equivalent SQL per database, optimized per dialect" is made enforceable
precisely because dialect divergence is localized to one swappable component.
`m-dialect` depends only on `m-core`.

This mirrors Reladomo's `DatabaseType` seam — obtained from the connection
manager at every SQL decision point, never from a global registry.

The database seam comprises this **pure dialect / portability layer**
(`m-dialect`), an **abstract runtime database port** (`m-db-port`) implemented by
**N independently deployable concrete adapter artifacts**, and **error
classification** (`m-db-error`). The pure dialect layer performs **no I/O**: it
holds no connection, opens no socket, and imports no database driver. It is the
single source of truth for every dialect-specific string and every
dialect-specific parse rule — SQL-fragment production (SELECT shape, identifier
quoting, row-limit clause, read-lock application, temp-table DDL), the
neutral-type → column-type mapping, the typed-bind normalization rules, and the
type-parse functions that turn a driver's raw column value into a core managed
value.

## The `Dialect` interface

A `Dialect` is the abstract authority for every dialect-specific decision. With
the second concrete dialect (**MariaDB**) added behind the seam, the full
decision-point catalog is now fixed. Two dialects legitimately make *different*
choices at each point; both are normative for their dialect (`m-sql`). The catalog
(derived from the research matrix, research §11):

| Decision point | Postgres (round-1 concrete) | MariaDB (second concrete) |
|---|---|---|
| `dialect` identifier | `postgres` | `mariadb` |
| type mapping (neutral type → column type) | per the `m-core` Postgres column | per the `m-core` MariaDB column (see below) |
| **nested extraction form** (`m-value-object` / `m-sql`) | `jsonb_extract_path_text(col, ?, …)` — one `?` bind per path segment | `json_value(col, ?)` — one `?` bind for the whole `'$.a.b'` path (see below) |
| **typed cast form** (`m-value-object` / `m-sql`) | `cast(<extraction> as double precision)` / `… as bigint` (the `<extraction>::type` surface normalizes to the same) | `cast(<extraction> as double)` / `… as signed` (see below) |
| **array traversal form** (`m-value-object` / `m-sql`) | correlated `exists (select 1 from jsonb_array_elements(<array-guard>) t1 …)` — a set-returning unnest, the array reached through a `case`/`jsonb_typeof` guard so a non-array yields zero elements | the JSON **containment family** — `json_contains(col, ?, ?)` / `json_length(col, ?)` under a `json_type(json_extract(col, ?)) = 'ARRAY'` guard (see below) |
| `SELECT` shape (column list, alias scheme) | `select t0.col, … from tbl t0 where …` | identical |
| identifier quoting | unquoted lowercase; `"…"` quote on demand | unquoted lowercase; **backtick** quote on demand (divergent quote char) |
| row-limit clause | `limit ?` | `limit ?` |
| **read-lock application** (`m-read-lock`) | object find: `for share of t0`; projection/aggregation: omitted | object find: **`lock in share mode`** (no `for share`; MDEV-17514); projection/aggregation: omitted |
| temp-table DDL | `CREATE TEMPORARY TABLE … ON COMMIT DROP` | `CREATE TEMPORARY TABLE …` |
| typed bind normalization | managed values render to canonical `m-core` wire values | timestamp binds remain typed `Instant`/`infinity` so the adapter can render `datetime(6)`/max-sentinel; other values render to canonical `m-core` wire values |
| **infinity representation** | native `'infinity'::timestamptz` | **max-sentinel** `datetime` (no native infinity) |
| error-code classification (`m-db-error`) | SQLSTATE: `23505` unique, `40P01`/`40001` deadlock, `55P03` lock timeout | errno: `1062` duplicate, `1213` deadlock, `1205` lock timeout |

The two decision points MariaDB **diverges** on — the read-lock (application) and
the infinity representation — are exactly the ones the second dialect was chosen
to exercise; they are detailed below. The divergent **type mappings** are
round-tripped against real MariaDB by the scalar witness (compatibility case
`m-core-004`), and the UTC-instant normalization + microsecond precision of
`datetime(6)` by the timestamp write cases (`m-core-002`/`m-core-003`). Error-code
classification is `m-db-error`.

### MariaDB type mapping (the `m-core` table, MariaDB column)

The dialect maps each `m-core` neutral type to a concrete MariaDB column type. The
mappings that **differ** from Postgres:

| Neutral type | Postgres | MariaDB | Why it differs |
|---|---|---|---|
| `boolean` | `boolean` | `tinyint(1)` | MariaDB has no native boolean (`true`/`false` alias `1`/`0`) |
| `timestamp` | `timestamptz` at core microsecond precision | `datetime(6)` | MariaDB `TIMESTAMP` is range-limited (2038) and auto-updates; `DATETIME(6)` is the UTC instant store, preserves the core microsecond precision, and has **no native infinity** |
| `float64` | `double precision` | `double` | spelling |
| `bytes` | `bytea` | `longblob` | |
| `uuid` | `uuid` | `char(36)` | no native UUID type |
| `json` | `jsonb` | `json` | structured-document storage; MariaDB `JSON` is a `longtext` alias |

`int32`/`int64`/`date`/`time`/`decimal(p,s)`/`string` map the same in spirit
(`int`/`bigint`/`date`/`time`/`decimal(p,s)`/`varchar(n)|text`).

Future dialects with a different document type, such as Snowflake `VARIANT`,
map the same `m-core` `json` neutral type behind this seam; the metamodel does not
name the concrete storage type.

### Nested extraction form (`m-value-object`)

Reading or filtering an inner attribute of a `valueObject` (`m-value-object`,
`m-op-algebra`'s `nested*` predicates) is a text/value extraction from the
structured-document column, and its **spelling and bind shape are a dialect
decision** owned here — the algebra fixes only the path, not the SQL:

| Aspect | Postgres | MariaDB |
|---|---|---|
| extraction function | `jsonb_extract_path_text(col, ?, …)` | `json_value(col, ?)` |
| path binds | one `?` per path segment, in path order (`?, ?` for `geo.country`) | one `?` for the whole JSON-path string (`'$.geo.country'`) |

So the same nested read binds differently per dialect: Postgres carries the path
segments as *separate* key binds (`['geo', 'country']`), MariaDB carries a *single*
`'$.a.b'` path bind (`['$.geo.country']`). This is why a nested case's `binds`
are authored as a **per-dialect map** (`m-case-format`). The comparison value bind
follows the path binds in both. A future dialect with a different document type —
Snowflake `VARIANT` — slots its own extraction (`GET_PATH(col, '…')` / the `:`
path operator) behind this same decision point; nothing above the seam names the
extraction function.

**Why `json_value`, not `json_unquote(json_extract(…))`.** The MariaDB golden
extraction is `json_value` precisely because it maps an explicit JSON `null` leaf
— **and** a missing path, **and** a non-object intermediate descent — to SQL
`NULL`, exactly as Postgres `jsonb_extract_path_text` does. `json_unquote(json_extract(…))`
would instead yield the *string* `'null'` for a JSON `null` leaf, so that one
not-present state would fail to collapse on MariaDB and diverge from Postgres. With
`json_value` all four not-present states (`m-op-algebra`'s absence-collapse rule)
resolve identically on both dialects, so the observable behavior is portable — the
whole point of localizing the extraction here. `json_value` returns SQL `NULL` for
a non-scalar (object/array) target as well, but the algebra only ever extracts a
declared **scalar** leaf, so that is never reached.

### Typed cast form (`m-value-object`)

A `valueObject` inner attribute has a declared `m-core` neutral type
(`m-value-object`). The document extraction above yields **text**, so a comparison
against a **non-text** attribute (a numeric `nestedGt` / `nestedLt`, …) **casts**
the extraction to the declared type before comparing — and the cast spelling is a
dialect decision owned here:

| Neutral type | Postgres | MariaDB |
|---|---|---|
| `int32` / `int64` | `cast(<extraction> as bigint)` | `cast(<extraction> as signed)` |
| `float64` | `cast(<extraction> as double precision)` | `cast(<extraction> as double)` |
| `decimal(p,s)` | `cast(<extraction> as decimal(p, s))` | `cast(<extraction> as decimal(p, s))` |

For a **text** (`string`) attribute the extraction already compares directly — no
cast. Postgres also admits the `<extraction>::type` surface; it denotes the same
cast and normalizes to the `cast(… as …)` canonical form (`m-sql`). Because every
not-present state casts SQL `NULL` (never a spurious value), the numeric predicates
obey the same absence-collapse rule as the text ones (`m-op-algebra`). A future
dialect (Snowflake `VARIANT`) supplies its own cast spelling behind this same
decision point.

### Placeholder cast form (`m-sql` inheritance `union all`)

A `table-per-concrete-subtype` abstract read lowers to `union all` over the effective
concrete tables (`m-sql`); a column not applicable to a branch is a `cast(null as
<type>)` placeholder in the column's declared type, so the union's result column types
resolve deterministically. The **CAST target-type spelling is a dialect decision owned
here** — and, for strings, it **diverges from the DDL column type**:

| Declared column type | Postgres | MariaDB |
|---|---|---|
| `decimal(p, s)` | `cast(null as decimal(p, s))` | `cast(null as decimal(p, s))` |
| bounded `string` (`maxLength n`) | `cast(null as varchar(n))` | `cast(null as char(n))` |
| unbounded `string` | `cast(null as text)` | `cast(null as text)` |

MariaDB's `CAST` target grammar does **not** accept `varchar`, so a bounded-string
placeholder casts to `char(n)` even though the *column* type is `varchar(n)` on both
dialects (the general rule: **string types map to `char` under a MariaDB `CAST`**). A
future dialect supplies its own placeholder-cast spelling behind this same decision
point; nothing above the seam names the concrete cast type.

### Array traversal form (`m-value-object`)

A `many` value object is a JSON **array** of documents in the same column
(`m-value-object`). Testing it — `nestedExists` / `nestedNotExists`, or a flat
`nested*` predicate whose path crosses the `many` member (any-element),
`m-op-algebra` — requires **traversing the array**, and the spelling is a dialect
decision owned here. The two concrete dialects pick genuinely different function
families; both produce the identical observable row set (the independent
`referenceSql` oracle proves it per case, `m-case-format`):

Both dialects **guard against a non-array** `many` value. A member is a real,
schema-flexible JSON value, so it may be stored not just as a SQL `NULL` column, a
missing key, or an empty array, but as an explicit JSON `null`, a JSON **scalar**,
or a JSON **object**. Absence-collapse (`m-op-algebra`) folds every non-array to
"not present" — **zero elements** — so the traversal MUST read a non-array that way,
never as an error or a spurious element. On Postgres the array is reached through a
**`case`/`jsonb_typeof` array guard** (`<array-guard>` below); on MariaDB a
**`json_type(json_extract(col, ?)) = 'ARRAY'` guard** (`<g>` below) precedes the
containment / length test.

| Aspect | Postgres | MariaDB |
|---|---|---|
| array guard | `<array-guard>` = `case when jsonb_typeof(jsonb_extract_path(col, ?)) = ? then jsonb_extract_path(col, ?) else cast(? as jsonb) end` — yields the array only when it **is** a JSON array, else an empty `[]`; the path binds **twice**, plus the type name `array` and `[]` | `<g>` = `json_type(json_extract(col, ?)) = ?` — true only when the member **is** a JSON array (bind: the path, then the type name `ARRAY`) |
| element unnest | `jsonb_array_elements(<array-guard>)` inside a correlated `exists (select 1 from … t1 where <element-predicate>)` — the element alias binds one row per element; `jsonb_array_elements` is **strict** and errors on a non-array, so the guard is required — a NULL column / missing key / JSON `null` / JSON scalar / JSON object all yield **zero** elements | none — MariaDB has no set-returning array unnest usable as golden SQL (see below); the containment family under `<g>` expresses the same predicates directly |
| any-element predicate | `exists (select 1 from jsonb_array_elements(<array-guard>) t1 where <ext>(t1.value, ?) = ?)` | `<g> and json_contains(col, ?, ?)` — bind a candidate JSON document (`'{"type":"home"}'`) and the array path (`'$.phones'`); containment against an array is **any-element**. The `<g>` guard is required because `json_contains` matches a JSON **object** that contains the candidate |
| same-element (`where`) | one `exists` with every element predicate on the **same** `t1` alias | one `<g> and json_contains(col, ?, ?)` whose candidate object carries **every** required field — a single element must contain all of them |
| non-empty (`exists`, no `where`) | `exists (select 1 from jsonb_array_elements(<array-guard>) t1)` | `<g> and json_length(col, ?) > ?` (`> 0`) — the `<g>` guard is required because `json_length` of a JSON scalar (or JSON `null`) is `1` |
| empty-or-absent (`notExists`) | `not exists (…)` — `not exists` over zero elements is **true**, so an empty array, a NULL column, and a non-array value all match | wrap the guarded containment / length in `coalesce(<g> and …, ?)` so a NULL column, missing key, non-array value, and empty array all read as the "no match" value the leading `not` then admits |

**Why MariaDB uses the containment family, not `JSON_TABLE`.** The natural
element-unnest on MariaDB is `JSON_TABLE(col, '$.phones[*]' columns (…))`, and it is
what a future set-returning dialect (Snowflake `LATERAL FLATTEN`) mirrors. But
`JSON_TABLE`'s path arguments are **literal syntax that cannot be a `?` bind**, and
the `m-sql` canonical normalizer (sqlglot, non-normative harness machinery, but the
fixed-point property it enforces **is** normative — `m-case-format` layer 3) does
not round-trip the `COLUMNS ( … PATH '…')` clause to a stable, re-parseable,
executable form. So golden SQL — which MUST be a normalizer fixed point — cannot use
`JSON_TABLE`. The **containment family** (`json_contains` / `json_length`) expresses
the same any-element and same-element predicates as scalar functions that keep their
paths and candidates as `?` binds and normalize cleanly; it is the MariaDB golden
form. `JSON_TABLE` still appears — as the **independent `referenceSql` oracle**
(parse-only, executed against real MariaDB), a deliberately different element-unnest
formulation that the harness asserts returns the same rows. A future dialect with a
set-returning unnest (Snowflake `LATERAL FLATTEN`) slots behind this same decision
point.

**Scope of the containment golden — equality only.** `json_contains` is a
**containment** predicate: it expresses element predicates that are equality against
a fixed candidate. It covers exactly two shapes: an **any-element `nestedEq`**
through a `many` segment, and a **same-element `where` whose compound is a
conjunction of equalities** (`nestedEq` and/or nested `and`) carried in one
candidate object. It **cannot** express any other element predicate, even though
`m-op-algebra` admits the whole scoped `nested*` family inside `where` and the flat
`nested*` family through a `many` segment. Concretely, `json_contains` cannot lower:

- a **flat any-element** non-equality predicate through a `many` segment —
  `nestedNotEq`, or a range `nestedGt` / `nestedGte` / `nestedLt` / `nestedLte`, or
  `nestedIn`, or a presence test `nestedIsNull` / `nestedIsNotNull`;
- an element-scoped **`where` containing any non-`eq` leaf** — a range
  (`elementNestedGt` / `elementNestedGte` / `elementNestedLt` / `elementNestedLte`),
  an `elementNestedNotEq`, an `elementNestedIn`, or an element null check
  (`elementNestedIsNull` / `elementNestedIsNotNull`);
- an element-scoped **`where` whose combinator is not a plain conjunction** — an
  `or`, a `not`, or a `group` around a disjunction (only a flat `and` of equalities
  maps to a single candidate object).

Each of those requires a **set-returning element unnest** that binds one row per
element (`JSON_TABLE`), which the current reference harness cannot normalize as
golden SQL (above). **These non-equality to-many element predicates on MariaDB are
therefore a documented deferred limitation**: the algebra and the Postgres lowering
(`jsonb_array_elements`, fully general — its `<array-guard>` unnest expresses every
element predicate and combinator) support them; the MariaDB **golden** does not until
a set-returning unnest can be normalized (or a set-returning dialect such as
Snowflake `LATERAL FLATTEN` supplies one behind this seam). The compatibility
corpus's to-many coverage is equality-based, consistent with this scope.

**MariaDB-lowering flag.** Because the schema (`operation.schema.json`)
*admits* these forms — the scoped `nested*` family and the flat `many`-crossing
family are schema-valid at every operator — a MariaDB implementation MUST NOT emit
wrong SQL for one it cannot lower. It **MUST reject it with a clear capability
diagnostic** (an unsupported-operation rejection naming the containment-golden
scope), exactly as it rejects any other unsupported operation, rather than silently
producing a `json_contains` that does not mean what the predicate says. This is the
MariaDB-lowering boundary: lower the equality shapes above to the
containment golden, reject every non-equality to-many element predicate until a
set-returning unnest is available.

### `NULL` ordering

The canonical ordered-relationship rule (`m-deep-fetch`) sorts `NULL`s **last** on
every key. The two dialects reach that order differently, because their native
`ORDER BY` `NULL` placement diverges:

| direction | Postgres | MariaDB |
|---|---|---|
| `asc` | `order by t0.c asc` (NULLs last by default) | `order by t0.c is null, t0.c asc` |
| `desc` | `order by t0.c desc nulls last` | `order by t0.c desc` (NULLs last by default) |

Postgres treats `NULL` as the largest value (so `asc` already trails `NULL`s and
`desc` needs an explicit `nulls last`); MariaDB/MySQL treat `NULL` as the
smallest and have **no** `NULLS FIRST/LAST` syntax, so the ascending case forces
`NULL`s last with a leading `<col> is null` term. The compatibility suite proves
both forms yield the identical observable order (case `m-deep-fetch-012`).

## Decision points needed now

- **Type mapping.** The dialect maps each `m-core` neutral type to a concrete
  column type (the Postgres column on the right of the `m-core` table). DDL
  derivation (`m-case-format` harness) asks the dialect for these.
- **Timestamp precision.** The dialect MUST preserve the `m-core` `timestamp`
  contract at microsecond precision. Dialects with higher-resolution client
  types MUST reject or explicitly normalize non-zero sub-microsecond values
  before binding; dialects with lower-resolution storage cannot satisfy the core
  `timestamp` type without an additional adapter or degraded optional profile.
- **Typed bind normalization.** Above-seam runtime code supplies the dialect with
  the target `m-core` neutral type when binding a managed value. The dialect MUST
  return the value shape expected by its concrete adapter without changing the
  emitted SQL. Postgres renders managed scalars to canonical `m-core` wire values
  because the driver can coerce those directly; MariaDB keeps `timestamp` values
  as typed instants (and the neutral `infinity` sentinel) so its adapter can bind
  `datetime(6)` and the max-sentinel without guessing whether an arbitrary string
  is text or time. Non-timestamp values render to canonical `m-core` wire values
  unless a future dialect documents a different typed carrier.
- **SELECT shape.** The canonical SELECT projects explicit, table-aliased columns
  (`t0.id, t0.name`) from a single aliased table (`from orders t0`). The alias
  scheme is `t0, t1, …` (see `m-sql` normalization). No `SELECT *`.
- **Identifier quoting.** Simple lowercase identifiers are unquoted on both
  dialects. A reserved word or otherwise non-simple name MUST be quoted, and the
  quote **character diverges** — Postgres double-quotes (`"order"`), MariaDB
  backticks (`` `order` ``). **Which names are reserved is itself per-dialect** — a
  database's keyword list differs — so the quoting *decision*, not only the quote
  character, is per-dialect; that **rule** is owned here, but the concrete
  reserved-word list is **not enumerated here**. `position` is a reserved function
  name on MariaDB (an unquoted `position` table emits an unparseable `POSITION(`
  call) but not on Postgres, so the `m-bitemp-write` cases quote `` `position` `` on
  MariaDB while leaving `position` bare on Postgres. The compatibility case
  `m-descriptor-001` witnesses the shared-reserved `order` on both dialects (a
  column literally named `order`); the `m-sql` normalizer preserves quoted
  identifiers, and the harness quotes reserved identifiers in the DDL/DML it
  generates while leaving simple names unquoted. The concrete per-dialect
  reserved-word lists themselves are **currently maintained by each conforming
  implementation** — the reference harness's DDL builder and each language's dialect
  layer — so a divergence such as MariaDB's `position` lives in those lists rather
  than in a shared table. A single shared normative reserved-word artifact (one
  `core` list the implementations derive from, with a cross-implementation drift
  guard) is a **deferred follow-on**, not yet part of `core`.
- **Infinity representation.** The open upper bound of a temporal interval
  (`m-core`) is owned here. **Postgres** uses native `'infinity'::timestamptz`, so
  the current-row predicate is `to = infinity` and a milestone insert writes
  `out_z = infinity` directly. **MariaDB's `DATETIME` has no native `'infinity'`**,
  so the seam maps the open-bound sentinel to a documented **max-sentinel** —
  `9999-12-31 23:59:59.999999`, the largest `DATETIME(6)`. This is the **only**
  place the difference is allowed to surface: the suite authors the `infinity`
  literal once (against native-infinity Postgres), and the MariaDB dialect
  translates it to the max-sentinel on the way **in** (binds, fixture loads) and
  back to `infinity` on the way **out** (reads), so the golden SQL (`t0.out_z = ?`),
  the fixture history, and the asserted table state are all dialect-neutral. The
  sentinel orders correctly above every finite milestone, preserving the
  current-row predicate. (The cost relative to native infinity is the Y9999 cliff
  Postgres avoids — acceptable for a dialect that offers no alternative.)
- **Read-lock application (`m-read-lock`).** *Applying* the in-transaction shared
  read lock is a dialect decision — not merely spelling the suffix, but deciding
  **whether, where, and when** to attach it. Given a compiled read and the
  unit-of-work mode, the dialect returns the read with this dialect's locking
  applied:
  - a lockable **object find** in `locking` mode gets the shared-row-lock form
    appended after every other clause — **Postgres** `for share of t0` (the
    alias-qualified `for share`), **MariaDB** the unaliased **`lock in share
    mode`** (no `for share` keyword; MDEV-17514);
  - a **projection / aggregation** read (a `distinct` / grouped / aggregate
    result) is returned **unchanged** — it has no identifiable base row to lock and
    the database rejects the clause on such shapes, so the dialect **omits** the
    lock rather than erroring (ADR 0012; mirrors Reladomo's never-locking
    `getSelectForAggregatedData` beside the object-find `getSelect(isInTransaction)`);
  - any read in **optimistic** mode is returned unchanged (`m-opt-lock` takes no
    lock).

  This divergence is surfaced here and **only** here — the operation, the result,
  and the independent oracle are identical; just the lock spelling differs. Each
  object-find form is the canonical fixed point of the `m-sql` normalizer for its
  own dialect (fully lowercase per rule 2; the normalizer renders the MariaDB lock
  through the seam rather than through sqlglot's MySQL generator, which would
  otherwise rewrite it to `for share`).
- **Error-code classification.** A raised database error is mapped to a neutral
  category via this seam's per-dialect native code source; the category set, the
  call-site predicates, and the per-dialect code tables are `m-db-error`.

## Two concrete dialects prove the seam, and it stays open

- **Postgres** is the round-1 concrete dialect; **MariaDB** is the second,
  proving the seam beyond Postgres. Each dialect's golden SQL is normative for
  that dialect (`m-sql`); the harness boots real Postgres **and** real MariaDB via
  Testcontainers (`m-case-format`), and the compatibility-matrix report
  (implementations × databases) shows reference × {postgres, mariadb} green.
- **Localization, proven.** Adding MariaDB required changes **only** inside the
  dialect seam — the normalizer's dialect mapping + read-lock rendering, the
  `m-core` type table's MariaDB column, and the MariaDB provider's infinity /
  instant adapters. **No spec prose outside this file and no fixture was
  MariaDB-specific** beyond the additive per-dialect `mariadb` keys in the
  affected cases' `then.statements` entries (which are the seam's output, not a
  leak). This is the "equivalent SQL per database, optimized per dialect" promise
  made good.
- **The matrix.** A golden statement's `sql` is **keyed by dialect from day one**
  (a `postgres` key, a `mariadb` key), and the database-provider seam in
  the harness selects a provider per dialect — so a third database is a new
  provider + a new per-dialect `sql` key in each statement entry, **not** a
  redesign.
- **Not a one-way door (DQ9).** The seam **MUST** stay open enough that
  per-source / per-tenant connection routing could be added later without
  re-plumbing. Source-attribute sharding is out of scope for round 1, but
  nothing here may *preclude* it: the dialect/connection seam is the natural
  future home for a routing hook.
