# m-core — Core Conventions

The normative primitives the whole spec rests on: the neutral data-type set, the
timezone/UTC rules, and the temporal-infinity representation. `m-core` depends on
nothing; every other module depends on it, directly or transitively.

## Neutral data types

An implementation **MUST** support the neutral type set below and **MUST** map
each neutral type to an equivalent concrete column type through the dialect seam
(`m-dialect`). The neutral name is what appears in a model descriptor's
`attribute.type`; the Postgres type shown is the round-1 concrete dialect mapping.

| Neutral type | Description | Postgres type | Notes |
|---|---|---|---|
| `boolean` | true / false | `boolean` | |
| `int32` | 32-bit signed integer | `integer` | |
| `int64` | 64-bit signed integer | `bigint` | |
| `float32` | 32-bit IEEE-754 | `real` | |
| `float64` | 64-bit IEEE-754 | `double precision` | |
| `decimal(p,s)` | exact fixed-point | `numeric(p,s)` | money / exact math; precision `p` and scale `s` are REQUIRED |
| `string` | variable-length text | `text` / `varchar(n)` | optional `maxLength` ⇒ `varchar(n)`; UTF-8 |
| `bytes` | binary blob | `bytea` | |
| `date` | calendar date, no time | `date` | timezone-naive (wall-clock) |
| `time` | time of day, no date | `time` | timezone-naive (wall-clock) |
| `timestamp` | absolute instant | `timestamptz` | UTC-normalized, microsecond precision (see below) |
| `uuid` | 128-bit UUID | `uuid` | in core (Postgres-native) |
| `json` | embedded composite value | `jsonb` | the `m-value-object` mapping; dialects map this to their native structured-document type |

> The walking-skeleton phase exercises `int64`/`int32`, `string`, and (in the
> schema) the full set. `boolean`, `decimal(p,s)`, the temporal types, and the
> `json` type gain dedicated fixtures in later phases.

**Deferred (optional / extension, not in the core type set yet):** `int16`,
`int8`, `char`.

## The `json` embedded-value type

The optional `json` neutral type is the storage type a `valueObject` element
(`m-value-object`) maps to: an embedded composite value (e.g. an address, a money
pair) is stored as a **single structured-document column** rather than
column-flattened into the owning table. This is a **deliberate deviation from
Reladomo**, which flattens an embedded value object into individual columns; a
single document column keeps the composite atomic, schema-flexible, and directly
queryable.

The dialect seam (`m-dialect`) owns the concrete storage type and extraction
functions. Examples include Postgres `jsonb`, MariaDB `json`, and Snowflake
`VARIANT`.

An implementation **MUST** read and filter a value object's inner fields through
the nested-attribute access form (`m-op-algebra` `nestedEq` / `nestedNotEq`,
lowered to a dialect-specific document extraction by `m-sql` / `m-dialect`). A
`json`-typed column **MAY** be `null` when the value object is declared
`nullable`; otherwise it is `not null` and carries the embedded object.

## Timezone handling

- All `timestamp` (instant) columns **MUST** use `timestamp with time zone`
  (`timestamptz`) and the framework **MUST** normalize values to **UTC** at the
  boundary. Geographically distributed applications store and compare in UTC and
  convert only at presentation.
- Core `timestamp` values have **microsecond precision**: canonical timestamp
  literals MAY carry 0 through 6 fractional second digits and implementations
  MUST NOT silently truncate non-zero sub-microsecond precision. Inputs with
  fewer than 6 fractional digits are interpreted exactly and MAY be normalized
  with trailing zeros; inputs with more than 6 fractional digits MUST either
  already represent an exact microsecond value (trailing zeros beyond the sixth
  digit) or be rejected at the framework boundary. This keeps timestamp equality
  and temporal interval predicates portable across the supported dialects.
- `date` and `time` are **wall-clock and timezone-naive** by definition; no
  timezone normalization is applied to them.
- There is **no per-attribute timezone-conversion knob** (Reladomo's
  `timezoneConversion` is dropped): timestamps are UTC-normalized globally.

## Temporal infinity

The open upper bound of a temporal interval (the `to`/`thru`/`out` column) is
represented by the **database's native infinity** where one exists, not a
`9999-12-01` sentinel and not `NULL`. The metamodel declares that a temporal
dimension *has* an infinity sentinel; the **dialect seam (`m-dialect`) owns the
concrete representation**:

- **Postgres** → native `'infinity'::timestamptz`.
- **MariaDB** (and any dialect without native timestamp infinity) → a documented
  **max-sentinel**: `9999-12-31 23:59:59.999999`, the largest `DATETIME(6)`. The
  seam translates the suite's `infinity` literal to the sentinel on writes/binds
  and back on reads, so the metamodel, golden SQL, fixtures, and asserted table
  state stay dialect-neutral — the difference is confined to the seam.

The full temporal interval model and milestone-chaining writes are
`m-temporal-read` / `m-audit-write` / `m-bitemp-write`.

Benefits of native infinity over a `9999` sentinel or `NULL`: correct
ordering/comparison, no Y9999 cliff, no `NULL`-in-predicate/index complications,
and a clear current-row predicate (`to = infinity`). Where native infinity is
unavailable, the max-sentinel preserves the ordering and current-row predicate
(it sorts above every finite milestone) at the cost of reintroducing the Y9999
cliff — an acceptable trade for a dialect that offers no alternative.

**Temporal coordinates are UTC `timestamp` values.** Valid Time and Transaction
Time both use the `timestamp` instant type, UTC-normalized like every other
instant, so interval math is uniform across dimensions. A date-granular Valid
Time coordinate is a `timestamp` at UTC midnight by convention.
