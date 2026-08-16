# m-wire — Canonical Wire Values

`m-wire` owns the **one canonical output spelling** of every neutral value that
leaves the framework as portable data. It depends on `m-core` alone: a spelling
is fixed per `NeutralType`, so the module needs the type vocabulary and nothing
else — no model, no shape, no path, no layout, no dialect.

The module is **pure**. It performs no I/O, holds no connection, imports no
driver, emits no SQL, and knows nothing of documents, rows, graphs, or
transactions. It answers exactly one question — *how is a value of this declared
type written* — and its inverse.

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

## The canonical spellings

Every Neutral Type has exactly one Wire Value spelling:

| Neutral type | Wire Value |
|---|---|
| `boolean` | JSON boolean |
| `int32`, `int64` | JSON number, integral, no exponent or fraction |
| `float32`, `float64` | JSON number, finite, the shortest number that decodes back to the value (below) |
| `string` | JSON string |
| `decimal(p, s)` | JSON string, the exact decimal spelling: a `-` only for a value below zero, the integer digits with no leading zero (a single `0` when the integer part is zero), and — when `s > 0` — `.` and exactly `s` fraction digits |
| `bytes` | JSON string, lowercase hexadecimal, two digits per byte, no prefix or separator |
| `date` | JSON string, ISO-8601 `YYYY-MM-DD` |
| `time` | JSON string, ISO-8601 `hh:mm:ss`, with `.ffffff` when the value carries sub-second precision |
| `timestamp` | JSON string, ISO-8601 UTC at microsecond precision: `YYYY-MM-DDThh:mm:ss.ffffffZ` |
| `uuid` | JSON string, canonical lowercase 8-4-4-4-12 form |
| `json` | the JSON value itself |

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

**Encoding and decoding are inverse.** For every value of a declared type,
decoding its Wire Value yields an equal value, and that Wire Value is the unique
one this table admits. So a value's wire form does not depend on which consumer
wrote it, and a predicate literal binds the same value a writer stored — an
equality comparison over a `date` or a `decimal` compares like with like without
any consumer normalizing first. Uniqueness is uniqueness of the JSON *value*: a
string spelling is unique character for character, while a JSON number is a
number, so `1` and `1.0` are one value and neither a serializer's rendering nor
an engine's numeric normalization can make two spellings of one value differ. For
a binary float that uniqueness is what the shortest-number rule above delivers —
without it the table would admit many JSON numbers per value.

**The open upper bound is not a value of any space.** A temporal interval's open
upper bound is `m-core`'s infinity sentinel rather than a `timestamp` value, so
this table gives it no spelling; where a seam writes it out it carries `m-core`'s
own canonical `infinity` literal. A seam that hands the sentinel to this table is
asking for the spelling of a value that is not there, and is refused.

**Spelling is by declared type, never by inspection.** A JSON string is read as a
`uuid`, a `date`, or a `string` because the position declares which. This module
never guesses a type from a value's shape, so a `string` member holding
`"2026-01-01"` stays that string.

## What this module does not own

- **Accepted *input* spellings.** Each serde seam states what it accepts on the
  way in — the descriptor type spellings (`m-descriptor`), the case fixture forms
  (`m-case-format`), the predicate node encoding (`m-predicate`). Those remain
  as specified where they are stated. This module fixes only what is written
  out, and a seam that accepts several inputs still emits exactly one of them.
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
- **Validation of stored data.** Whether a stored value is the canonical
  spelling of the value it names, and what a non-canonical or undecodable one
  does to a read, belong to `m-document-codec` and `m-snapshot-read`.
