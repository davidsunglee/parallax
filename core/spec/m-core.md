# m-core — Core Conventions

The normative primitives the whole spec rests on: the structured `NeutralType`
algebra, the `NeutralValue` value spaces, the timezone/UTC rules, and the
temporal-infinity representation. `m-core` depends on nothing; every other
module depends on it, directly or transitively.

## The `NeutralType` algebra

`NeutralType` is the closed structured type algebra every typed model fact
uses. Metadata (`m-metamodel` attribute and Value Object Attribute types),
operation literals and assignments (`m-op-algebra`), and neutral rows all reuse
these variants; no module defines a parallel type vocabulary.

```text
NeutralType =
    Boolean | Int32 | Int64 | Float32 | Float64
  | Decimal(precision: int, scale: int)   # both REQUIRED
  | String | Bytes | Date | Time | Timestamp | Uuid | Json
```

`Decimal(precision, scale)` is the sole parametric variant: precision and scale
are REQUIRED integer parameters with no defaults, so an unparameterized decimal
type is unconstructible. The parameters satisfy `precision >= 1` and
`0 <= scale <= precision`; a `Decimal` outside these bounds — a negative
parameter, a zero precision (e.g. `Decimal(0, 9)`), or a scale exceeding the
precision — is unconstructible, so every structured `Decimal` value has a
serializable descriptor spelling (`m-descriptor` "Type spellings").

Descriptor type spellings and serialized value encodings belong to
`m-descriptor` alone (`m-descriptor` "Type spellings" / "Value encodings"): a
structured `NeutralType` value carries no spelling, and no behavioral module
parses a type string or a serialized value.

An implementation **MUST** support the full variant set and **MUST** map each
variant to an equivalent concrete column type through the dialect seam
(`m-dialect`). The column mapping below is informative round-1 dialect prose
(Postgres shown), not part of the algebra:

| Variant | Description | Postgres type | Notes |
|---|---|---|---|
| `Boolean` | true / false | `boolean` | |
| `Int32` | 32-bit signed integer | `integer` | |
| `Int64` | 64-bit signed integer | `bigint` | |
| `Float32` | 32-bit IEEE-754 | `real` | |
| `Float64` | 64-bit IEEE-754 | `double precision` | |
| `Decimal(precision, scale)` | exact fixed-point | `numeric(p,s)` | money / exact math |
| `String` | variable-length text | `text` / `varchar(n)` | optional `maxLength` ⇒ `varchar(n)`; UTF-8 |
| `Bytes` | binary blob | `bytea` | |
| `Date` | calendar date, no time | `date` | timezone-naive (wall-clock) |
| `Time` | time of day, no date | `time` | timezone-naive (wall-clock) |
| `Timestamp` | absolute instant | `timestamptz` | UTC-normalized, microsecond precision (see below) |
| `Uuid` | 128-bit UUID | `uuid` | in core (Postgres-native) |
| `Json` | embedded composite value | `jsonb` | the `m-value-object` storage type; dialects map it to their native structured-document type |

**Deferred (optional / extension, not in the core algebra yet):** `Int16`,
`Int8`, `Char`.

## `NeutralValue` — logical value spaces

A `NeutralValue` is a value drawn from the declared `NeutralType`'s logical
value space. There is no tagged wrapper type: every position that carries a
`NeutralValue` — an attribute default (`m-metamodel` `AttributeDefault`), an
operation literal or assignment value (`m-op-algebra`), a neutral row cell —
is already typed by its declaration, so the declared type identifies the value
space and a stored tag could never carry information the declaration does not.
Wire encodings of these values belong to `m-descriptor` alone.

| `NeutralType` | Logical value space | Equality / normalization laws |
|---|---|---|
| `Boolean` | the two truth values | — |
| `Int32` / `Int64` | signed integers in the 32-/64-bit two's-complement range | numeric equality |
| `Float32` / `Float64` | **finite** IEEE-754 binary32 / binary64 values — NaNs and the infinities are not members (see below) | IEEE numeric equality on finite values; the two IEEE zeros are one logical value: `-0.0` normalizes to `+0.0` at the framework boundary, so the sign of a zero carries no information |
| `Decimal(precision, scale)` | exact decimal values `unscaled × 10^-scale` with at most `precision` total digits | exact numeric equality at the declared scale; no rounding and no floating-point intermediate |
| `String` | Unicode text (UTF-8 encodable) | codepoint equality; no Unicode normalization is applied |
| `Bytes` | finite octet sequences | byte equality |
| `Date` | timezone-naive proleptic-Gregorian calendar dates | wall-clock; no timezone normalization (see below) |
| `Time` | timezone-naive wall-clock times of day at microsecond precision | wall-clock; no timezone normalization (see below) |
| `Timestamp` | absolute UTC instants at microsecond precision | values normalize to UTC at the framework boundary; non-zero sub-microsecond precision is rejected (see below) |
| `Uuid` | 128-bit UUID values | equality on the 128-bit value; text case carries no information |
| `Json` | structured content: any value of the JSON data model (boolean, number, string, array, object) except a bare top-level `null`; JSON `null` may appear only *inside* a value, as an array element or object member | structural equality |

`Json` is the only type whose value space admits structured (non-scalar)
content; a self-describing payload is that type's job, never a tagged scalar.

The float value spaces are deliberately finite. NaN admits no total equality
law and the non-finite values have no portable descriptor encoding
(`m-descriptor` encodes a float value as a JSON number), so no
`NeutralValue`-carrying position — a default, a literal, an assignment, a row
cell — can hold one. What a dialect column may physically store is the dialect
seam's concern, outside the neutral contract.

Null is not a member of any value space — `Json` included: JSON `null` is
ordinary structured content *inside* a `Json` value, never a value of the
space itself. A position admits null only through its own contract (a
`nullable` member, or `m-metamodel`'s `AttributeDefault`, whose
`DefaultValue(null)` branch is legal for every declared type), so a null at
such a position always denotes that contractual null rather than a value drawn
from any value space, and null equals only itself.

## The `Json` embedded-value type

The `Json` neutral type is the storage type a `valueObject` element
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
`Json`-typed column **MAY** be `null` when the value object is declared
`nullable`; otherwise it is `not null` and carries the embedded object.

## Timezone handling

- All `Timestamp` (instant) columns **MUST** use `timestamp with time zone`
  (`timestamptz`) and the framework **MUST** normalize values to **UTC** at the
  boundary. Geographically distributed applications store and compare in UTC and
  convert only at presentation.
- Core `Timestamp` values have **microsecond precision**: canonical timestamp
  literals MAY carry 0 through 6 fractional second digits and implementations
  MUST NOT silently truncate non-zero sub-microsecond precision. Inputs with
  fewer than 6 fractional digits are interpreted exactly and MAY be normalized
  with trailing zeros; inputs with more than 6 fractional digits MUST either
  already represent an exact microsecond value (trailing zeros beyond the sixth
  digit) or be rejected at the framework boundary. This keeps timestamp equality
  and temporal interval predicates portable across the supported dialects.
- `Date` and `Time` are **wall-clock and timezone-naive** by definition; no
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
`m-temporal-read` / `m-txtime-write` / `m-bitemp-write`.

Benefits of native infinity over a `9999` sentinel or `NULL`: correct
ordering/comparison, no Y9999 cliff, no `NULL`-in-predicate/index complications,
and a clear current-row predicate (`to = infinity`). Where native infinity is
unavailable, the max-sentinel preserves the ordering and current-row predicate
(it sorts above every finite milestone) at the cost of reintroducing the Y9999
cliff — an acceptable trade for a dialect that offers no alternative.

**Temporal coordinates are UTC `Timestamp` values.** Valid Time and Transaction
Time both use the `Timestamp` instant type, UTC-normalized like every other
instant, so interval math is uniform across dimensions. A date-granular Valid
Time coordinate is a `Timestamp` at UTC midnight by convention.
