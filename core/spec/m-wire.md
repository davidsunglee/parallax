# m-wire — Neutral Wire Codec

`m-wire` owns the complete serialized typed-literal boundary: strict JSON source
loading, admitted literal decoding, canonical stored decoding, and the **one
canonical output spelling** of every managed value. It depends on `m-core`
alone. It knows no model, shape, path, layout, predicate, query, SQL, dialect,
driver, continuation, transaction, or conformance case.

The module is **pure**. It performs no I/O, holds no connection, imports no
driver, and emits no SQL. A consumer supplies a declared `NeutralType`; this
module never guesses one from a carrier.

## Operations and failures

The Neutral Wire Codec exposes four operations:

```text
loads(jsonTextOrBytes) -> WireValue
decodeWire(declaredType, admittedWireValue) -> ManagedValue
decodeCanonicalWire(declaredType, canonicalWireValue) -> ManagedValue
encodeWire(declaredType, managedValue) -> WireValue
```

`WireValue` is the recursive JSON data model: null, boolean, integer, finite
number, string, array, or string-keyed object. Private numeric provenance used
between `loads` and typed decoding is not part of that interface. `encodeWire`
returns only ordinary built-in JSON carriers and recursively ordinary
containers.

Decoding raises one classified failure:

```text
WireDecodingReason = TypeMismatch | Noncanonical | OutOfSpace
```

- **TypeMismatch** means the JSON carrier or its semantics cannot denote the
  declared type, such as a string for Int32, `1.5` for Int32, or malformed Date
  text.
- **Noncanonical** means the literal denotes an in-space value but violates an
  admitted representation rule, such as uppercase bytes, a Timestamp offset,
  or the wrong Decimal scale.
- **OutOfSpace** means the literal has the declared type's shape but denotes no
  managed member, such as integer overflow, an impossible date, float overflow,
  or a recursive Json number outside the finite host JSON space.

Public serialized ingress maps those reasons to
`neutral-literal-type-mismatch`, `neutral-literal-noncanonical`, and
`neutral-literal-out-of-space`, adding its own member or path location. Stored
canonical decoding maps every failure to the document codec's existing
`LeafUndecodable` verdict. `encodeWire` instead raises a framework/developer
encoding error when its input is not already a managed member; it performs no
developer coercion.

## Strict JSON source loading

`loads` accepts any valid JSON root from text or bytes. It rejects duplicate
object member names at every depth and the non-JSON constants `NaN`, `Infinity`,
and `-Infinity` as JSON parse failures before structural or model-aware
validation. Duplicate diagnostics identify the repeated key; exact source
offset accuracy is not required.

Every authored JSON number retains its exact token privately until a declared
type is known. Integral and fractional/exponent tokens are both retained,
including signed zero and values outside the host float range. Untouched
pass-through preserves that meaning; replacing or numerically modifying the leaf
makes the resulting programmatic carrier authoritative. Callers never import,
construct, inspect, or test the concrete provenance representation.

Parser allocation and work are proportional to source characters and parsed
members. Duplicate detection uses a hash-based seen-name set per object. Numeric
token handling applies the bounded `m-core` float projection precheck before any
power-of-ten expansion.

JSON text or bytes entering a public Wire read or write MUST pass through this
operation before framework or model resolution. Wire verbs continue to accept
structured mappings and values rather than each adding raw-body overloads. A
deliberately constructed mapping passes directly. Output Parallax publishes is
ordinary JSON data and serializes through an ordinary JSON encoder; generic
reserialization of an unconsumed `loads` result is valid JSON but is not promised
to preserve authored number tokens.

## One spelling, two consumers

Two seams write neutral values out, and both write the same characters:

- **Structured-document storage.** A leaf inside a Value Object document or an
  Entity document is stored as its canonical Wire Value (`m-document-codec`).
- **Wire transport.** A Wire Snapshot's leaves — Entity Attributes and Value
  Object fields alike — are rendered as their canonical Wire Values
  (`m-snapshot-read`).

Having one owner is what makes the two agree by construction. A value read back
out of a document and the same value delivered through a Wire read are the same
characters, so a consumer that stores what it read stores what was there, and a
`then.tableState` fixture and a `then.graph` fixture spell one value one way.

**Changing a spelling in this module is a storage-format migration.** Stored
documents carry these characters, and SQL compares several of the types by
comparing the extracted text directly (`m-dialect`, `m-document-codec`), so a
changed spelling changes stored bytes, predicate results, and ordering results
together. It is never a presentation preference.

## Neutral Wire Codec matrix

The matrix is exhaustive over the closed `NeutralType` algebra. “Alternative”
means admitted by `decodeWire` but rejected by `decodeCanonicalWire` after the
same one-pass conversion. A dash means that reason has no distinct representative
for that type under this grammar.

| Declared type | Admitted JSON carrier and grammar | Managed conversion | Canonical output | Admitted alternatives | Type mismatch | Noncanonical | Out of space |
|---|---|---|---|---|---|---|---|
| `boolean` | boolean | same truth value | boolean | none | `"true"` | — | — |
| `int32` | finite JSON number with an exact integral value | exact integer, signed 32-bit range | integral JSON number | none distinguishable under JSON-value equality | `1.5` | — | `2147483648` |
| `int64` | finite JSON number with an exact integral value | exact integer, signed 64-bit range | integral JSON number | none distinguishable under JSON-value equality | `"1"` or `1.5` | — | `9223372036854775808` |
| `float32` | finite JSON number | nearest binary32, ties even, widened to host float; zero is positive | shortest binary32 round trip | any other spelling rounding to the same value | `"1.0"` | `-0.0` | `1e39` |
| `float64` | finite JSON number | nearest binary64, ties even; zero is positive | shortest binary64 round trip | any other spelling rounding to the same value | `"1.0"` | `0.10000000000000001` | `1e309` |
| `decimal(p,s)` | plain JSON string with exactly `s` fractional digits; no exponent, plus, unnecessary leading zero, or negative zero | exact fixed-scale Decimal, with no rounding or binary intermediate | same declared-scale string | none | JSON number `10.25` | `"10.2"`, `"-0.00"` | coefficient exceeds precision `p` |
| `string` | JSON string of Unicode scalar text | same text | same JSON string | none | `42` | — | unpaired surrogate |
| `bytes` | JSON string of lowercase hexadecimal, two digits per byte | octet sequence | same lowercase hex | none | `42` or odd digit count | `"0A1B"` | — |
| `date` | JSON string `YYYY-MM-DD` | proleptic-Gregorian date | same fixed-width string | none | `20260101` | `"2026-1-1"` | `"2026-02-30"` |
| `time` | JSON string `hh:mm:ss`, or fraction of exactly three or six digits; no zone | wall-clock time at microsecond precision | omit zero fraction; otherwise six digits | zero fraction written explicitly; nonzero millisecond written with three digits | `42` | `"09:30:00.000"` | `"24:00:00"` |
| `timestamp` | JSON string in UTC `Z`, with no fraction or exactly three or six digits | UTC instant at microsecond precision | exactly six fraction digits plus `Z` | no fraction or three-digit fraction | `42` | `"2026-01-15T09:30:00Z"` | impossible date or year outside 0001–9999 |
| `uuid` | lowercase hyphenated 8-4-4-4-12 JSON string | 128-bit UUID | same lowercase hyphenated string | none | `42` or malformed hex groups | uppercase or hyphenless text | — |
| `json` | recursively valid JSON except bare top-level null; numbers fit the finite host JSON space | fresh ordinary recursive JSON structure; numeric provenance erased | recursively ordinary JSON | none distinguishable under JSON-value equality | top-level `null` or non-JSON host object | — | nested number outside finite host JSON space |

Well-formed but disallowed Bytes case, UUID case/hyphenation, Decimal spelling,
and Timestamp offset representations are deliberately not broad aliases. They
denote in-space values but fail public decoding as `Noncanonical`; they are not
repaired. Malformed hex or UUID text denotes no value and is `TypeMismatch` as
the matrix states. For Timestamp, a numeric offset including `+00:00` is
noncanonical rather than an admitted alternative. Decimal never admits a JSON
number.

Every public decoder dispatches explicitly over all thirteen variants with no
default or catch-all arm. The admitted conversion runs exactly once.

Seven rules make the table total rather than illustrative.

**Every type is here.** A member whose declared type has no row above has no
Wire Value at all. There is no fallback to a host language's default serializer,
and no consumer may invent a spelling for a type this table does not cover.

**`json` is not a leaf spelling.** `Json` is the one variant no member declares —
neither an Attribute nor a Value Object field may name it (`m-core`) — so no
declared leaf ever carries it. Its row keeps the table total over the type
algebra: `Json` is the storage type a whole occurrence maps to, and where such a
value is what is being written, its Wire Value is that value itself, whose
object-member order is the value's own and is not observable state.

**Exactness over convenience.** `decimal` and `timestamp` are strings precisely
because JSON numbers cannot carry their contracts: a JSON number has no declared
scale and no guaranteed precision, and a naive round trip through a binary float
silently changes a value the database would have preserved. `float32`/`float64`
are numbers because they *are* binary floats; a non-finite float is not a
`m-core` value and never reaches this table.

**A float's JSON number is the shortest one that decodes back to it.** "A JSON
number" alone does not pin a binary float down: `0.1` and `0.10000000000000001`
decode to the same binary64, so two conforming implementations could write two
*different* JSON numbers for one value — and two different numbers are two
different documents, so a `then.tableState` authored as `0.1` would pass against
one implementation and fail against the other, and a whole-occurrence comparison
(`m-unit-work`) against a subtree some other writer stored would report a change
where the value never changed. The spelling is therefore the number with the
**fewest significant digits** that decodes back to the value under the member's
declared format — binary32 for `float32`, binary64 for `float64` — and, where
several equally short numbers decode to it, the one **nearest** the value, and
where two of those are equally near, the one whose **last significant digit is
even**. All three levels are load-bearing: binary64 `562949953421312.25` is
decoded from both `562949953421312.2` and `562949953421312.3` — sixteen
significant digits each, `0.05` from the value each, with no fifteen-digit
candidate in range — so the first two levels alone still admit two numbers, and
the third selects `562949953421312.2`. (`1048576.2` / `1048576.3` is the same tie
for binary32 `1048576.25`.) This fixes the *number*, not its rendering: `20` and
`20.0` are one JSON number and either may be written, while `0.1` and
`0.10000000000000001` are two numbers and only `0.1` is admissible. It is what a
shortest-round-trip float formatter produces, the even-digit tie-break included;
a fixed-width `17`-significant-digit rendering is not admissible, even though it
also round-trips.

**A JSON number names the float of the declared width nearest it.** The rule
above is stated in terms of what a number *decodes back to*, so that decode
belongs to this table too: a number at a `float32` names the binary32 value
nearest it and a number at a `float64` the nearest binary64, under IEEE
round-to-nearest-even, and only a magnitude that would round to an infinity —
`1e39` at a `float32` — names no value at all. It is the *number* that is read,
never its rendering or the carrier a host parser put it in: `20` and `20.0` are
one JSON number, and so are `16777217` and `16777217.0`, so a consumer whose
parser hands the first of each pair back as an integer and the second as a float
MUST still answer the same value for both. The one distinction this rule does
draw is the width, and it is the same one the spelling draws: `1048576.2` names
binary32 `1048576.25` at a `float32` and a different, exactly-representable
binary64 at a `float64`.

**Rounding happens once, from the digits.** The number a Wire Value carries is
the one its digits name, so the declared width is applied to *that* number and to
nothing else. A consumer whose parser first rounds the digits into a wider
carrier — a binary64, say — and then narrows that carrier to the declared width
has rounded twice, and two roundings are not one: `1.0000000596046448` lies above
the midpoint between binary32 `1.0` and `1.00000011920928955078125`, so rounding
it once at binary32 names the upper value, while binary64-then-binary32 lands
exactly on the midpoint and its tie-to-even names `1.0`. Both consumers used
round-to-nearest-even at every step and answered different values, so a consumer
that parses into a wider carrier MUST keep enough of the authored number to round
from it. `float64` is unaffected only because its carrier is already the declared
width.

*What nearest-value decoding gives up, deliberately.* It is not exact. A number
no float of the declared width represents exactly is still admitted, and it names
a **different** value than the one written: `16777217` at a `float32` names
`16777216`, and `9007199254740993` at a `float64` names `9007199254740992`.
Refusing it instead cannot be spelled "the number must be exact", because a
canonical spelling is routinely inexact — `1e30` is the number this table gives
the binary32 value `1.0000000150474662e30` — so the honest refusing rule is
"exact **or** already the canonical spelling of the value it rounds to", which
narrows what a `float32` member may hold rather than how a number is read.

**The codec laws are exhaustive.** For every declared type and managed member:

```text
decodeCanonicalWire(t, encodeWire(t, managed)) == managed
encodeWire(t, decodeWire(t, admitted)) == canonical
decodeCanonicalWire(t, canonical) succeeds
decodeCanonicalWire(t, distinguishable admitted alternative) is Noncanonical
```

Canonical comparison is variant-aware rather than generic host equality. It
observes float zero sign, exact authored number meaning, temporal fraction width,
and string characters. Object member order remains unobservable for Json.

**The open upper bound is not a value of any space.** A temporal interval's open
upper bound is `m-core`'s infinity sentinel rather than a `timestamp` value, so
this table gives it no spelling; where a seam writes it out it carries `m-core`'s
own canonical `infinity` literal. A seam that hands the sentinel to this table is
asking for the spelling of a value that is not there, and is refused.

**Spelling is by declared type, never by inspection.** A JSON string is read as a
`uuid`, a `date`, or a `string` because the position declares which. This module
never guesses a type from a value's shape, so a `string` member holding
`"2026-01-01"` stays that string.

## Null and boundary ownership

Null is not a typed literal because it is not a member of any `NeutralType`.
Writes own member nullability, predicates use dedicated null-check nodes,
continuations generate those nodes, and document handling distinguishes missing,
JSON null, and SQL NULL. Nested null remains ordinary content inside a managed
Json value.

## What this module does not own

- **Structural shape and semantic location.** Schemas and surface adapters decide
  where a literal may occur, then resolve a member and call this codec. They do
  not duplicate the matrix's declared-type grammar.
- **Where a value sits.** Document shape, presence, absence, unknown keys, and
  patching belong to `m-document-codec`; the shape of a Wire Snapshot, the member
  names its keys carry, and **which** members it carries belong to
  `m-snapshot-read` (*What a materialized value carries*). This module spells the
  value at a position that exists and grants no consumer a spelling for one that
  does not: a declared member a Wire Snapshot has no key for has no Wire Value
  here either, and inventing one — a null for a member the stored document never
  held — would be reading a value out of this table for a position it was never
  given.
- **Comparison.** Which types SQL compares as extracted text and which it casts
  is a `m-dialect` / `m-sql` decision, stated where the comparison is
  (`m-document-codec` "Portable leaf encodings"). It is a *consequence* of the
  spellings here, and the two MUST move together.
- **Surface error location.** The codec classifies a literal; the consuming
  predicate, write, case, or document seam adds its member/path location and maps
  the reason into that surface's vocabulary.
