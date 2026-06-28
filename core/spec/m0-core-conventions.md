# M0 — Core Conventions

The normative primitives the whole spec rests on: the neutral data-type set, the
timezone/UTC rules, and (introduced in a later phase) the temporal-infinity
representation. `M0` depends on nothing; every other module depends, directly or
transitively, on it.

## Neutral data types

An implementation **MUST** support the neutral type set below and **MUST** map
each to the Postgres type shown. The neutral name is what appears in a model
descriptor's `attribute.type`; the concrete column type is owned by the M11
dialect seam.

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
| `json` | embedded composite value | `jsonb` | the `valueObject` mapping (M1); see below |

> The walking-skeleton phase exercises `int64`/`int32`, `string`, and (in the
> schema) the full set. `boolean`, `decimal(p,s)`, the temporal types, and the
> `json` type gain dedicated fixtures in later phases.

**Deferred (optional / extension, not in the core type set yet):** `int16`,
`int8`, `char`.

## The `json` embedded-value type

The optional `json` neutral type maps to Postgres **`jsonb`** and is the storage
type a `valueObject` element (M1) is mapped to: an embedded composite value
(e.g. an address, a money pair) is stored as a **single JSONB column** rather
than column-flattened into the owning table. This is a **deliberate deviation
from Reladomo**, which flattens an embedded value object into individual columns;
JSONB keeps the composite atomic, schema-flexible, and directly queryable.

An implementation **MUST** read and filter a value object's inner fields through
the nested-attribute access form (M2 `nestedEq` / `nestedNotEq`, lowered to a
JSONB extraction by M3). A `json`-typed column **MAY** be `null` when the value
object is declared `nullable`; otherwise it is `not null` and carries the
embedded object.

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
dimension *has* an infinity sentinel; the **M11 dialect seam owns the concrete
representation**:

- **Postgres** → native `'infinity'::timestamptz`.
- **MariaDB** (and any dialect without native timestamp infinity) → a documented
  **max-sentinel**: `9999-12-31 23:59:59.999999`, the largest `DATETIME(6)`. The
  seam translates the suite's `infinity` literal to the sentinel on writes/binds
  and back on reads, so the metamodel, golden SQL, fixtures, and asserted table
  state stay dialect-neutral — the difference is confined to the seam.

The full temporal interval model and milestone-chaining writes are M7.

Benefits of native infinity over a `9999` sentinel or `NULL`: correct
ordering/comparison, no Y9999 cliff, no `NULL`-in-predicate/index complications,
and a clear current-row predicate (`to = infinity`). Where native infinity is
unavailable, the max-sentinel preserves the ordering and current-row predicate
(it sorts above every finite milestone) at the cost of reintroducing the Y9999
cliff — an acceptable trade for a dialect that offers no alternative.

**As-of business date is a UTC `timestamp`.** Both temporal axes — processing and
business — use the `timestamp` (instant) type, UTC-normalized like every other
instant, so interval math is uniform across axes. A date-granular business date
is a `timestamp` at UTC midnight by convention.
