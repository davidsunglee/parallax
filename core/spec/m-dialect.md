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
decision-point catalog covers every construct currently emitted. Two dialects legitimately make *different*
choices at each point; both are normative for their dialect (`m-sql`). The catalog
(derived from the research matrix, research §11):

| Decision point | Postgres (round-1 concrete) | MariaDB (second concrete) |
|---|---|---|
| `dialect` identifier | `postgres` | `mariadb` |
| type mapping (neutral type → column type) | per the `m-core` Postgres column | per the `m-core` MariaDB column (see below) |
| **nested extraction form** (`m-value-object` / `m-sql`) | `jsonb_extract_path_text(col, ?, …)` — one `?` bind per path segment | `json_value(col, ?)` — one `?` bind for the whole `'$.a.b'` path (see below) |
| **typed cast form** (`m-value-object` / `m-sql`) | `cast(<extraction> as double precision)` / `… as bigint` (the `<extraction>::type` surface normalizes to the same) | `cast(<extraction> as double)` / `… as signed` (see below) — the numeric family and `boolean`; the six text-compared types compare as the canonical document text on both dialects |
| **array traversal form** (`m-value-object` / `m-sql`) | correlated `exists (select 1 from jsonb_array_elements(<array-guard>) t1 …)` — a set-returning unnest, the array reached through a `case`/`jsonb_typeof` guard so a non-array yields zero elements | the JSON **containment family** — `json_contains(col, ?, ?)` / `json_length(col, ?)` under a `json_type(json_extract(col, ?)) = 'ARRAY'` guard (see below) |
| **document mutation-expression form** (`m-storage-layout` / `m-sql`) | **nested** `jsonb_set(<inner>, ?, cast(? as jsonb))` — one call per assigned path, innermost first | **native N-pair** `json_set(col, ?, json_extract(?, '$'), …)` — one call, one pair per assigned path (see below) |
| **occurrence-scoped mutation form** (`m-storage-layout` / `m-document-codec`) | nested `jsonb_set` over a `jsonb_typeof` object guard at every occurrence level | nested `json_set` over a `json_type` object guard at every occurrence level |
| **structural document equality** (`m-document-codec` / `m-case-format`) | `=` on `jsonb` — the type normalizes on storage, so `=` is already structural | `json_equals(a, b)` — `json` is a `longtext` alias, so `=` is textual and key-order sensitive (see below) |
| `SELECT` shape (column list, alias scheme) | `select t0.col, … from tbl t0 where …` | identical |
| identifier quoting | unquoted lowercase; `"…"` quote on demand | unquoted lowercase; **backtick** quote on demand (divergent quote char) |
| row-limit clause | `limit ?` | `limit ?` |
| **optimizer-fence form** (`m-sql`) | append `offset 0` to each tag-filtered branch; no bind | append `limit ?` to each tag-filtered branch; bind unsigned maximum `18446744073709551615` immediately after the tag bind |
| **read-lock application** (`m-read-lock`) | object find: `for share of t0`; projection/aggregation: omitted | object find: **`lock in share mode`** (no `for share`; MDEV-17514); projection/aggregation: omitted |
| temp-table DDL | `CREATE TEMPORARY TABLE … ON COMMIT DROP` | `CREATE TEMPORARY TABLE …` |
| typed bind normalization | managed values render to canonical `m-core` wire values | timestamp binds remain typed `Instant`/`infinity` so the adapter can render `datetime(6)`/max-sentinel; other values render to canonical `m-core` wire values |
| **infinity representation** | native `'infinity'::timestamptz` | **max-sentinel** `datetime` (no native infinity) |
| error-code classification (`m-db-error`) | SQLSTATE: `23505` unique, `40P01`/`40001` deadlock, `55P03` lock timeout | errno: `1062` duplicate, `1213` deadlock, `1205` lock timeout |

The read-lock application and infinity representation are the original two
decision points the second dialect was chosen to exercise; they are detailed
below. The catalog also records the dialects' other settled divergences, including
the optimizer fence that protects tag-disjoint document casts. The divergent **type mappings** are
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

The one place the two dialects' extractions return **different characters** for
one document value is a JSON boolean: `json_value` yields `1` / `0` where
`jsonb_extract_path_text` yields `true` / `false`. That is why `boolean` compares
through a cast rather than as text (below), and it is a property of the extraction
rather than of the encoding — the document still carries a JSON boolean on both
engines.

### Typed cast form (`m-value-object` / `m-storage-layout`)

A document-resident member has a declared `m-core` neutral type — a `valueObject`
inner attribute (`m-value-object`) or a document-resident Attribute under
Relational Document Layout (`m-storage-layout`). The document extraction above
yields **text**, and whether a comparison casts that text is fixed by the declared
type. Both halves of the answer are owned here, and between them the two tables
below cover **every declarable neutral type**, so no type is left without a
comparison form.

**A type casts for one of two reasons.** The **numeric family** casts because its
document spelling does not compare in value order as text — `'10'` is less than
`'9'`. **`boolean`** casts because the two extraction forms above do not yield the
same text for it: `jsonb_extract_path_text` returns `true` / `false` where
`json_value` returns `1` / `0` — MariaDB's scalar extraction hands back a SQL
value, and MariaDB has no boolean SQL type, the same absence the `tinyint(1)` row
of the type mapping records — so no single bound text matches on both engines.
Either way the cast spelling is a dialect decision:

| Neutral type | Postgres | MariaDB |
|---|---|---|
| `int32` / `int64` | `cast(<extraction> as bigint)` | `cast(<extraction> as signed)` |
| `float32` | `cast(<extraction> as real)` | `cast(<extraction> as float)` |
| `float64` | `cast(<extraction> as double precision)` | `cast(<extraction> as double)` |
| `decimal(p,s)` | `cast(<extraction> as decimal(p, s))` | `cast(<extraction> as decimal(p, s))` |
| `boolean` | `cast(<extraction> as boolean)` | `cast(<extraction> as signed)` — MariaDB's `CAST` grammar admits no `boolean` target, and the extracted `1` / `0` is already the value in that dialect's boolean representation |

**A cast comparison binds the value, never the document encoding.** The cast moves
the comparison into the engine's own type system, so the bound operand is the
managed `m-core` value in the member's declared Neutral Type, rendered by the typed
bind normalization above — exactly what an ordinary Column comparison of that type
binds. A `decimal(p, s)` therefore binds the **exact decimal**: its document form
is a digit string precisely because no JSON number carries the type's contract
(`m-document-codec`), and binding a JSON number instead compares a binary float,
which matches stored decimals that are merely near the literal. A `boolean` binds
the boolean, which each dialect renders for its own cast target.

**Six types compare as the extracted text, with no cast on either dialect**,
because the canonical spelling `m-document-codec` writes already equates and
orders correctly as text — which is why that module states those spellings to be
comparison-significant rather than a serialization convenience. Membership is
fixed by comparison behavior, not by document form: `decimal(p, s)`'s document
form is a JSON string as well and it casts with the rest of the numeric family,
because its integer part has no fixed width, so `10.00` sorts below `9.00` as
text.

| Neutral type | Document spelling (`m-document-codec`) | Why no cast |
|---|---|---|
| `string` | JSON string | the extraction already **is** the text the predicate compares |
| `bytes` | lowercase hex, two digits per byte | equal texts are equal octet sequences, and text order is octet order |
| `date` | ISO-8601 `YYYY-MM-DD` | fixed width, most-significant field first — text order is calendar order |
| `time` | ISO-8601 `hh:mm:ss[.ffffff]` | zero-padded, most-significant field first — text order is clock order |
| `timestamp` | ISO-8601 UTC `YYYY-MM-DDThh:mm:ss.ffffffZ` | fixed width, already UTC-normalized — text order is instant order |
| `uuid` | canonical lowercase 8-4-4-4-12 | equal texts are equal 128-bit values |

`json` needs no row: it is the one variant no member may declare (`m-core`), so it
never reaches a comparison as a leaf.

The no-cast half is a claim about these ASCII spellings under both concrete
dialects' text comparison, not a general claim that text comparison is enough. A
future dialect whose text comparison does not equate or order them in value order —
or whose extraction does not yield those characters at all, which is what moved
`boolean` into the cast table above — supplies a cast for those types **at this
decision point**, rather than changing the spelling: the spelling is shared with
every other consumer of the document and is not a dialect's to move, while the
cast table is exactly where a dialect's own extraction behavior is allowed to
surface.

Postgres also admits the `<extraction>::type` surface; it denotes the same
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
| any-element predicate | `exists (select 1 from jsonb_array_elements(<array-guard>) t1 where <ext>(t1.value, ?) = ?)` | `<g> and json_contains(col, ?, ?)` — bind a candidate JSON **document** (the codec's `{"type": "home"}`, adapted to this dialect's structured-document type at bind time exactly as a written document is) and the array path (`'$.phones'`); containment against an array is **any-element**. The `<g>` guard is required because `json_contains` matches a JSON **object** that contains the candidate |
| same-element (`where`) | one `exists` with every element predicate on the **same** `t1` alias | one `<g> and json_contains(col, ?, ?)` whose candidate object carries **every** required field, one key per constrained path — a single element must contain all of them |
| non-empty (`exists`, no `where`) | `exists (select 1 from jsonb_array_elements(<array-guard>) t1)` | `<g> and json_length(col, ?) > ?` (`> 0`) — the `<g>` guard is required because `json_length` of a JSON scalar (or JSON `null`) is `1` |
| empty-or-absent (`notExists`) | `not exists (…)` — `not exists` over zero elements is **true**, so an empty array, a NULL column, and a non-array value all match | wrap the guarded containment / length in `coalesce(<g> and …, ?)` so a NULL column, missing key, non-array value, and empty array all read as the "no match" value the leading `not` then admits |

**The candidate document is not this seam's to spell.** `json_contains` binds a
candidate document, and its content — each constrained leaf's **document
encoding**, placed where the stored element places it — is `m-document-codec`'s
(`encodeCandidate`), not a dialect literal. Containment compares JSON values
rather than extracted text, so neither of this seam's two comparison forms fits:
the managed `boolean` this dialect's cast takes is `1`, and `{"flag": 1}` matches
no element storing a JSON boolean. What this seam owns is the containment
*spelling* — the function family, the guard, and the bind order — exactly as it
owns the extraction spelling without owning the text the codec writes. The
candidate reaches the driver the way a written document does: SQL binds the
finished `Document`, and **serializing it to this dialect's `json` text happens
here, below the bind**, so no golden and no lowering ever names a key order or a
separator (`m-sql`, `m-case-format`).

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
conjunction of equalities over distinct paths** (`nestedEq` and/or nested `and`)
carried in one candidate object. It **cannot** express any other element predicate,
even though
`m-op-algebra` admits the whole scoped `nested*` family inside `where` and the flat
`nested*` family through a `many` segment. Concretely, `json_contains` cannot lower:

- a **flat any-element** non-equality predicate through a `many` segment —
  `nestedNotEq`, or a range `nestedGt` / `nestedGte` / `nestedLt` / `nestedLte` /
  `nestedBetween`, or a membership `nestedIn` / `nestedNotIn`, or a string predicate
  `nestedLike` / `nestedNotLike` / `nestedStartsWith` / `nestedEndsWith` /
  `nestedContains`, or a presence test `nestedIsNull` / `nestedIsNotNull`;
- an element-scoped **`where` containing any non-`eq` leaf** — that is, every one of
  the fifteen element nodes `elementNestedEq` is not: a range
  (`elementNestedGt` / `elementNestedGte` / `elementNestedLt` / `elementNestedLte` /
  `elementNestedBetween`), an `elementNestedNotEq`, a membership
  (`elementNestedIn` / `elementNestedNotIn`), a string predicate
  (`elementNestedLike` / `elementNestedNotLike` / `elementNestedStartsWith` /
  `elementNestedEndsWith` / `elementNestedContains`), or an element null check
  (`elementNestedIsNull` / `elementNestedIsNotNull`);
- an element-scoped **`where` whose combinator is not a plain conjunction** — an
  `or`, a `not`, or a `group` around a disjunction (only a flat `and` of equalities
  over distinct paths maps to a single candidate object);
- an element-scoped **`where` whose equalities constrain one element-relative path
  with two different values** — `type = 'home' and type = 'work'` on the same
  element. A candidate object carries **one value per key**, so the two constraints
  cannot both ride it, and lowering either one alone produces a `json_contains` that
  matches elements the predicate excludes: the conjunction is unsatisfiable and must
  return **no** row, while `{"type":"work"}` returns every row with a work phone.
  Two equalities on one path that carry the **same** value are one constraint, not
  two, and the candidate expresses them exactly (`m-sql`).

Each of those requires a **set-returning element unnest** that binds one row per
element (`JSON_TABLE`) — the last one included, since two constraints on one path
are two ordinary predicates on one unnested row — which the current reference
harness cannot normalize as
golden SQL (above). **These to-many element predicates on MariaDB are
therefore a documented deferred limitation**: the algebra and the Postgres lowering
(`jsonb_array_elements`, fully general — its `<array-guard>` unnest expresses every
element predicate and combinator) support them; the MariaDB **golden** does not until
a set-returning unnest can be normalized (or a set-returning dialect such as
Snowflake `LATERAL FLATTEN` supplies one behind this seam). The compatibility
corpus's **dual-dialect** to-many coverage is equality-based, consistent with this
scope; a case exercising one of the forms above carries a Postgres golden only.

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

### Document mutation-expression form (`m-storage-layout`)

A Relational Document Layout `UPDATE` assigns one or more logical paths inside
one Structured Column and MUST NOT rewrite the column whole
(`m-storage-layout`). Composing those assignments into one `SET` expression is a
dialect decision owned here, and the two engines take genuinely different
shapes:

| Aspect | Postgres | MariaDB |
|---|---|---|
| one assignment | `jsonb_set(col, ?, cast(? as jsonb))` | `json_set(col, ?, json_extract(?, '$'))` |
| N assignments | **nested** — each call's target is the previous call's result: `jsonb_set(jsonb_set(col, ?, cast(? as jsonb)), ?, cast(? as jsonb))` | **native N-pair** — one call: `json_set(col, ?, json_extract(?, '$'), ?, json_extract(?, '$'))` |
| path bind | one `?` carrying the Postgres text-array path (`{displayName}`) | one `?` carrying the JSON-path string (`$.displayName`) |
| value bind | one `?` per assignment, the encoded document value, wrapped in the **value expression** below | one `?` per assignment, the encoded document value, wrapped in the **value expression** below |

```sql
-- two assignments, canonical logical placement order
-- postgres
set payload = jsonb_set(jsonb_set(payload, ?, cast(? as jsonb)), ?, cast(? as jsonb))
-- mariadb
set payload = json_set(payload, ?, json_extract(?, '$'), ?, json_extract(?, '$'))
```

**The value hole needs a per-dialect expression, and a bare `?` works on
neither engine.** Both spellings are this decision point's own, for reasons that
are properties of the two engines rather than of the value being written:

- On **Postgres** a bare `?` in `jsonb_set`'s value position resolves to the
  function's declared `jsonb` parameter type, so nothing but a `jsonb`-typed
  bind or JSON text is admissible there: an ordinary string bind is an
  `invalid input syntax for type json` error and an ordinary integer bind is a
  `function jsonb_set(jsonb, unknown, smallint) does not exist` error.
  `cast(? as jsonb)` admits both a composite adapted to the driver's `jsonb`
  type and a JSON scalar's text.
- On **MariaDB** a bare `?` in `json_set`'s value position accepts a scalar but
  **silently escapes a composite** — `json_set(payload, '$.addr', '{"city": "Oslo"}')`
  stores the *string* `"{\"city\": \"Oslo\"}"` rather than an object — because
  MariaDB's `json` is a `longtext` alias with no JSON-typed bind. `CAST(… AS JSON)`
  is a MySQL feature MariaDB does not have, and of the two functions that do
  unwrap a value only `json_extract(?, '$')` unwraps a scalar as well as a
  composite, so it is the one expression that serves every assignment.

A future dialect supplies its own value expression at this decision point.
Nothing above this seam wraps, quotes, or type-tags an assigned value: `m-sql`
hands the seam the encoded document value and the seam decides how it reaches
the engine, exactly as it does for the containment candidate.

**Both forms apply left to right, so assignment order is semantically
significant on both dialects** — the innermost Postgres call and the first
MariaDB pair are the first assignment. The dialect does not choose that order:
it renders the sequence `m-sql` hands it, which is canonical logical placement
order. A dialect MUST NOT reorder, deduplicate, or merge assignments.

Both engines create only the **final** path segment: a flat assignment whose
parent is absent, JSON null, or a non-object silently leaves the document
unchanged. An occurrence-scoped mutation therefore MUST type-test the stored
subtree at every occurrence level, retain it only when it is an object, otherwise
substitute an empty object, apply the inner mutation, and write the result back at
that level. PostgreSQL uses `jsonb_typeof` and nested `jsonb_set`; MariaDB uses
`json_type` and nested `json_set`. A dialect MUST NOT emit a standalone flat deep
path for an occurrence assignment, even when fixtures happen to store its parent.

Because the bind-hole structure diverges — the same two assignments are four
holes inside two nested Postgres calls and four holes inside one MariaDB call,
with different path spellings — a document-mutation case authors its `binds` as
a **per-dialect map** (`m-case-format`), exactly as nested extraction does.

### Structural document equality (`m-document-codec`)

Two documents are equal when they carry the same members with equal values,
independent of key order and insignificant whitespace (`m-document-codec`). The
expression that decides it is a dialect decision, because the two engines do not
agree by default:

| Aspect | Postgres | MariaDB |
|---|---|---|
| comparison | `a = b` on `jsonb` | `json_equals(a, b)` |
| why | `jsonb` normalizes on storage — whitespace removed, duplicate keys reduced, numerics canonicalized — so `=` is already structural | `json` is `longtext` with a `JSON_VALID` check, so `=` is a **text** comparison and is sensitive to key order and whitespace |

A consumer comparing documents MUST obtain the comparison through this seam. On
MariaDB the naive `=` returns false for two documents that differ only in key
order, which under Relational Document Layout is most of a row's state, so
leaving the choice to each consumer would make an assertion mean different
things on the two engines. `json_equals` is available from MariaDB 10.7.

### Document column DDL (`m-storage-layout`)

A Relational Document Layout Structured Column renders as `jsonb not null` on
Postgres and `json not null` on MariaDB. It carries no database default, because
every write this contract admits binds a complete object explicitly, including
the empty object. The non-null spelling is not a dialect choice — it is the
slot's `effectiveNullable` answer (`m-storage-layout`), rendered here.

A conventional Value Object Structured Column keeps its existing derivation: the
`json` neutral type through the mapping table above, with the occurrence's own
declared nullability.

The initial contract adds no generated deep `CHECK` constraint over document
contents on either dialect.

### `NULL` ordering

An ordering key carries an authored **Null Placement** alongside its direction —
the operation Sort Key's `nulls` member (`m-op-algebra`) and the relationship
declaration's (`m-relationship`), which lower through this one seam; an omitted
placement is `last`,
the canonical dialect-independent default in both directions (`m-deep-fetch`). The two
dialects reach a requested placement differently, because their native `ORDER BY`
`NULL` placement diverges:

| direction | placement | Postgres | MariaDB |
|---|---|---|---|
| `asc` | `last` | `order by t0.c asc` (NULLs last by default) | `order by t0.c is null, t0.c asc` |
| `desc` | `last` | `order by t0.c desc nulls last` | `order by t0.c desc` (NULLs last by default) |
| `asc` | `first` | `order by t0.c asc nulls first` | `order by t0.c asc` (NULLs first by default) |
| `desc` | `first` | `order by t0.c desc` (NULLs first by default) | `order by not t0.c is null, t0.c desc` |

Postgres treats `NULL` as the largest value, MariaDB/MySQL as the smallest, so
exactly one dialect compensates per row and the two placements are mirror images.
Postgres spells its compensation as a `nulls first`/`nulls last` suffix; MariaDB has
**no** `NULLS FIRST/LAST` syntax at all, so it compensates with a leading boolean
rank term (`t0.c is null` sorts `NULL`s last, `not t0.c is null` sorts them first —
the `m-sql` normalizer's canonical spelling of `is not null`). Where a dialect's
native default already yields the requested placement it emits neither form: that is
a deliberate lowering decision recorded here, not an omission.

The seam returns the **whole** rendered key term, comma-joined leading rank term
included, so a caller joining terms never learns which structure a dialect chose.

Placement is observable only on a **nullable** key. A non-nullable key lowers to the
plain `t0.c [asc|desc]` term in both dialects under either placement, because there
are no `NULL`s to place. The compatibility suite proves the compensating and native
forms yield the identical observable order (case `m-deep-fetch-012` for the
`asc`/`last` default; `m-op-algebra-035` through `-038` for all four combinations on
an operation Sort Key, and `m-deep-fetch-021` through `-023` for the three a canonical
relationship declaration spells distinctly — canonical descriptor form omits a `nulls`
equal to the default, so an explicit `asc`/`last` on a declaration canonicalizes to the
placement-free spelling `m-deep-fetch-012` already witnesses).

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
