# m-core — Core Conventions

The normative primitives the whole spec rests on: the structured `NeutralType`
algebra, managed value spaces, developer-input coercion, the timezone/UTC rules,
and the temporal-infinity representation. `m-core` depends on nothing; every
other module depends on it, directly or transitively. It owns no serialized-
literal grammar, canonical spelling, or parser provenance; those belong to
`m-wire`.

## JSON container detachment

`detachJsonContainer(value)` recursively copies JSON-shaped mappings and
sequences into plain object and array container kinds. It retains scalar values,
normalizes no leaf spelling, consults no model shape or path, and shares no
container with its input. Modules use it when an immutable observation or pure
document operation must break aliases without acquiring document-codec semantics.

## Provider-neutral document reads

A `DocumentValue` is any value in the JSON data model, including a bare JSON
null. It is a portable tree of object, array, string, number, boolean, and null
values, never rendered JSON text, a driver object, or a provider-native document
handle. This carrier space is deliberately wider than the conforming `Json`
`NeutralValue` below: reads must preserve invalid stored JSON kinds so the
document codec can classify them instead of losing them at the database seam.

A structured-document result cell crosses that seam as this closed tagged value:

```text
DocumentRead =
    SqlNull
  | PresentDocument(document: DocumentValue)
```

`SqlNull` means the SQL column itself was `NULL`. `PresentDocument` means the SQL
column was not `NULL` and preserves every parsed document kind, including
`PresentDocument(document: JSON null)`. The tag is therefore semantically
required even when a driver represents SQL `NULL` and JSON null with the same
host-language sentinel. A `DocumentRead` is a transport value rather than a
`NeutralValue`; the no-wrapper rule below applies only where a declaration has
already fixed one neutral value space.

## The `NeutralType` algebra

`NeutralType` is the closed structured type algebra every typed model fact
uses. Metadata (`m-metamodel` attribute and Value Object Attribute types),
predicate literals and assignments (`m-predicate`), and neutral rows all reuse
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

Descriptor type spellings belong to `m-descriptor` alone (`m-descriptor`
"Type spellings"): a structured `NeutralType` value carries no spelling, and
no behavioral module parses a type string.

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
| `Json` | embedded composite value | `jsonb` | not declarable on a member — the `m-value-object` storage type only (see below); dialects map it to their native structured-document type |

**Deferred (optional / extension, not in the core algebra yet):** `Int16`,
`Int8`, `Char`.

## Managed values and logical value spaces

A **managed value** is a host-language carrier belonging to the declared
`NeutralType`'s logical value space. `NeutralValue` is the language-neutral name
for that value; `ManagedValue` is the implementation vocabulary for its carrier.
Neither is a tagged wrapper. Every position carrying one is already typed by its
declaration, so a stored tag could carry no additional information. Runtime
membership against the accompanying `NeutralType` remains authoritative because
a host-language union alone cannot express integer width, float width, Decimal
precision/scale, top-level `Json` null exclusion, or temporal bounds.

How a managed value is written, and which serialized literals decode to one,
belongs exclusively to `m-wire`. A behavioral algorithm MUST NOT infer a neutral
type from a carrier or implement a parallel string/number conversion table.

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
| `Timestamp` | absolute UTC instants at microsecond precision, within the range its canonical spelling carries (see below) | values normalize to UTC at the framework boundary; non-zero sub-microsecond precision and an out-of-range instant are rejected (see below) |
| `Uuid` | 128-bit UUID values | equality on the 128-bit value; text case carries no information |
| `Json` | structured content: any value of the JSON data model (boolean, number, string, array, object) except a bare top-level `null`; JSON `null` may appear only *inside* a value, as an array element or object member | structural equality |

`Json` is the only type whose value space admits structured (non-scalar)
content, and a member reaches that space only by declaring a `valueObject`
(see "The `Json` embedded-value type"), never by declaring `Json` itself and
never by packing a composite into a tagged scalar. Every other value space is
scalar.

The float value spaces are deliberately finite. NaN admits no total equality
law and the non-finite values have no portable serialized encoding
(the carrying serde seams encode a float value as a JSON number), so no
`NeutralValue`-carrying position — a literal, an assignment, a row
cell — can hold one. What a dialect column may physically store is the dialect
seam's concern, outside the neutral contract.

Null is not a member of any value space — `Json` included: JSON `null` is
ordinary structured content *inside* a `Json` value, never a value of the
space itself. A position admits null only through its own contract (a
`nullable` member), so a null at
such a position always denotes that contractual null rather than a value drawn
from any value space, and null equals only itself.

## Managed membership and developer-input coercion

`matchesNeutralType(value, declaredType)` asks one question: whether an existing
managed carrier belongs to the declared logical value space. It is total and
non-throwing. It performs no coercion, parsing, serialized-literal decoding, or
canonicalization. In particular, Float32 membership requires the host float to
be exactly the widened carrier of one finite IEEE-754 binary32 value; a wider
fractional carrier that would round to binary32 is not already a member.

`coerceNeutralInput(value, declaredType)` is the developer-facing runtime input
policy. It is total and non-throwing: it returns a managed value when the policy
admits the input and otherwise returns the original non-member for the caller's
own error adapter to reject. The policy is deliberately narrower than Wire
decoding:

- exact managed carriers are retained, with valid offset-aware timestamps
  normalized to UTC and float negative zero normalized to positive zero;
- an integer may widen to Decimal exactly;
- an integer may widen to Float32 or Float64 only when the target width carries
  it losslessly;
- a host float is projected immediately to the declared float width, rejecting
  overflow and non-finite values, and Float32 returns the widened host carrier of
  the actual binary32 result;
- a canonical UUID string may widen to a UUID carrier where a language's
  developer surface documents that convenience; and
- serialized spellings such as timestamp strings, byte hex, Decimal strings,
  and arbitrary Wire number alternatives are not developer-input coercions.

Developer adapters apply coercion and then managed membership before storage,
SQL lowering, or canonical encoding. Failures stay in the owning developer
surface's vocabulary. They never become `neutral-literal-*` failures and never
leak `m-wire` decoding errors.

## Float projection at a declared width

`nearestFloatAtWidth(value, declaredFloatType)` is the provenance-neutral
`m-core` operation shared by developer coercion and `m-wire`. Its input is an
exact integer, finite host float, or exact decimal value; its result is the
nearest finite value of the declared IEEE-754 width under round-to-nearest-even,
widened into the host float carrier, or absence when the value overflows that
space. It covers normals, subnormals, underflow to positive zero, both tie
directions, and positive-zero normalization. It never observes a source token or
serialized carrier subclass.

Work and allocation are bounded by the input coefficient digits plus the fixed
target width, not by the represented exponent. Before constructing an integer
ratio or a power of ten, an implementation MUST classify magnitudes provably
outside the target format's rounding neighborhood directly as overflow or
rounded zero. A fixed-size token such as `1e1000000000` therefore cannot trigger
exponent-sized allocation or work.

## The `Json` embedded-value type

The `Json` neutral type is the storage type a `valueObject` element
(`m-value-object`) maps to: an embedded composite value (e.g. an address, a money
pair) is stored as a **single structured-document column** rather than
column-flattened into the owning table. This is a **deliberate deviation from
Reladomo**, which flattens an embedded value object into individual columns; a
single document column keeps the composite atomic, schema-flexible, and directly
queryable.

`Json` is **not a declarable attribute type**. It is the one variant no member
names: an entity attribute **MUST NOT** declare it, and neither **MUST** a value
object's inner field, so its only occurrence is the storage type core derives
for a whole value object. Structured content therefore always has a declared
shape — a composite is modeled as a `valueObject` with typed fields, nested
to any depth, and free-form structured content is not modelable at all. The
value space above exists to give that derived storage type its meaning:
structural equality, the literal typing of nested predicates, and the dialect
column mapping are all defined over it.

The dialect seam (`m-dialect`) owns the concrete storage type and extraction
functions. Examples include Postgres `jsonb`, MariaDB `json`, and Snowflake
`VARIANT`.

An implementation **MUST** read and filter a value object's inner fields through
the nested-attribute access form (`m-predicate` `nestedEq` / `nestedNotEq`,
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
- The `Timestamp` value space is **bounded by what its canonical spelling can
  carry**: the instants from `0001-01-01T00:00:00.000000Z` through
  `9999-12-31T23:59:59.999999Z`. An input naming an instant outside that range —
  which an offset can produce from an in-range local reading, `0001-01-01` east
  of UTC being the smallest — is **not a member** and MUST be rejected at the
  framework boundary rather than normalized, stored, or spelled. Every value of
  a declared type has exactly one Wire Value (`m-wire`), and outside the range
  there is none to give.
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
`m-temporal-read` / `m-txtime-write` / `m-bitemp-write`. Those writes only ever
append: across the required parity surface the Transaction-Time past is never
rewritten, the invariant `m-txtime-write` states beside the chaining that
discharges it.

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
