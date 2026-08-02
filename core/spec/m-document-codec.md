# m-document-codec — Portable Document Encoding

`m-document-codec` owns the portable representation of every neutral value
stored inside a structured document, and the in-memory operations that build,
read, and patch such a document. It depends on `m-core` and `m-metamodel`.

The module is **pure**. It performs no I/O, holds no connection, imports no
driver, and emits no SQL. It contains no dialect or database-adapter seam:
`m-dialect` owns provider-specific path expressions, casts, and mutation
expressions, and `m-db-port` continues to carry a neutral managed document bind
that each concrete adapter hands to its own driver's structured-document
wrapper. A codec value crosses that seam already portable.

## One owner for two document kinds

Parallax stores structured documents in two places, and this module owns the
representation of both:

- a **Value Object document** — one top-level Value Object occurrence in its own
  Structured Column, under conventional Columns layout (`m-value-object`); and
- an **Entity document** — the shared Structured Column of a Relational Document
  Layout, whose root object holds every document-resident member of the row
  (`m-storage-layout`).

The two differ only in which shape reaches the codec: a Value Object occurrence's
own shape, or the applicable document shape of one Entity. Everything below —
the per-leaf encodings, presence, patching, and comparison — is identical for
both. That is the module's reason to exist: a `Decimal` inside a Value Object and
a `Decimal` inside an Entity document are the same six characters, so the two
kinds cannot drift apart and no consumer needs to know which kind it holds.

## Shapes, documents, and values

```text
Document                                  # a portable JSON value

DocumentShape
  members: immutable sequence<DocumentMember>

DocumentMember =
    Leaf(name: MemberName,
         type: NeutralType,
         nullable: boolean)
  | Occurrence(name: MemberName,
               multiplicity: Multiplicity,
               nullable: boolean,
               shape: DocumentShape)

Presence =
    Present(value: MemberValue)
  | ExplicitNull
  | Missing

MemberValue =
    NeutralValue     # a Leaf member's value, in the member's declared type
  | Document         # an Occurrence member's own document: one object for
                     # `One`, an ordered array of objects for `Many`
```

A `DocumentShape` is derived from accepted Metadata and names only members
applicable to the document being encoded or decoded. It carries canonical member
names, declared Neutral Types, multiplicity, and nullability, and nothing
physical: no Column, no dialect, no path string. `MemberName` is the canonical
declared name, the same spelling a materialized result uses.

A `Document` is a portable JSON value — object, array, string, number, boolean,
or null — and nothing else. It is not a driver value, a rendered text, or a
provider-native document handle.

A `Presence` is always classified against one member of a shape, and the member's
own kind fixes what a `Present` carries. A `Leaf` member carries a `NeutralValue`
of its declared Neutral Type. An `Occurrence` member carries that occurrence's
own `Document` — one object for `One`, an ordered array of objects for `Many` —
and that document is always a codec product: a consumer obtains a `One`'s object
from `encode` and a `Many`'s array from `encodeMany`, never by assembling a
host-language value graph or a JSON array of its own. Nesting is therefore
expressed by composition rather than by a second interface, and every leaf at
every depth still passes through the encoding table below.

## Operations

```text
encode(shape: DocumentShape,
       values: Mapping<MemberName, Presence>)        -> Document

encodeMany(shape: DocumentShape,
           elements: ordered sequence<
                       Mapping<MemberName, Presence>>) -> Document

decode(shape: DocumentShape,
       document: Document,
       path: nonempty sequence<MemberName>)          -> Presence

comparisonText(type: NeutralType,
               value: NeutralValue)                  -> string

encodeCandidate(shape: DocumentShape,
                constraints: nonempty Mapping<
                    nonempty sequence<MemberName>, NeutralValue>) -> Document

patch(document: Document,
      patches: nonempty ordered sequence<DocumentPatch>) -> Document

DocumentPatch =
    SetLeaf(path: nonempty sequence<MemberName>,
            value: Presence)
  | SetOccurrence(path: nonempty sequence<MemberName>,
                  value: Document | Null)
```

`encode` builds one complete document from a shape and one presence-classified
value per applicable member. Its result is the whole bind a consumer stores: an
insert, a fresh Value Object column value, and a fixture document all come from
here. Members are emitted in the shape's own order, so one set of values always
produces one document. An `Occurrence` member's value is written in place as the
occurrence's own document, which `encode` (for a `One`) or `encodeMany` (for a
`Many`) produced from that occurrence's shape, so one complete document is
composed from the leaves up.

`encodeMany` builds the one document a `Many` occurrence stores: the ordered JSON
array whose elements are, in the sequence's own order, the `encode` of each
element's values against that occurrence's shape. It exists because `encode`
builds one object from one value mapping while a `Many` is a *sequence* of them —
without it, a `many` occurrence would have exactly one construction route, a
consumer assembling the array itself, which is the one JSON structure this module
would then not own. An empty sequence yields `[]`, the same document a `Missing`
or `ExplicitNull` `Many` member encodes to (below). Every element crosses the
encoding table, and an element mapping may itself carry a nested occurrence's
document, so a `many` of nested occurrences composes to any depth through these
two operations and no other.

`decode` reads one known path and answers with its presence. The path is resolved
against the shape, so the declared Neutral Type comes from the model rather than
from the caller: a `Leaf` path answers with that leaf's value decoded by its
declared type rather than by the JSON value's own shape, and an `Occurrence` path
answers with that occurrence's own document exactly as stored, unknown keys
included — which is what whole-occurrence comparison (`m-unit-work`) and subtree
replacement need. A path naming no member of the shape is a caller error, not an
absence. Decoding is per path rather than whole-document because a row-form read
needs only the members its consumer asked for and never pays to decode the rest;
a consumer that wants an occurrence's members decodes them against that
occurrence's shape and its returned document. For a `Many` that returned document
is the array, and **each of its elements is itself a document over that same
shape**: the elements are decoded one at a time, in order, by passing an element
back to `decode` with the occurrence's shape. That is what makes a `many`
traversable without an element index — a `path` stays a sequence of member names
and never addresses an array position.

`comparisonText` answers the exact characters a dialect's text extraction returns
for the encoding of `value` — the literal SQL binds when the member's declared
type compares as **extracted text** rather than through a cast (`m-dialect`,
`m-sql`). It is defined for exactly the six **text-compared** types — `string`,
`bytes`, `date`, `time`, `timestamp`, and `uuid` — and for each it is that
string's own characters, unquoted and unescaped, so a consumer binds `0a1b`
rather than the JSON text `"0a1b"` that carries it, against an extraction that
returns the characters alone. The domain is fixed by how a type **compares**, not
by its document form: `decimal(p, s)`'s document form is a JSON string too and it
is deliberately not here, because it casts (below).

No other type has a comparison text, because no other type is compared as text. A
member whose comparison casts the extraction — the numeric family and `boolean`
(`m-dialect`) — is compared inside the engine's own type system, so what SQL binds
there is the **managed value in its declared Neutral Type**, not a literal this
module produces: a `decimal(p, s)` binds the exact decimal rather than any JSON
number, and a `boolean` binds the boolean rather than any text. The distinction is
not decorative. `decimal`'s document form is a digit string precisely because a
JSON number cannot carry its scale and precision, so binding one against
a cast extraction compares a binary float and matches stored values that merely
round to the same float; and a JSON boolean is the one document form the concrete
dialects' text extractions do not agree on the characters of (`m-dialect`), so no
bound text can match on both — which is why it has a cast rather than a comparison
text.

`encodeCandidate` builds the **containment candidate** a to-many equality binds:
the object carrying exactly the constrained paths, each at its declared position
under `shape` and spelled by the encoding table below, and no other key. It exists
because a dialect may express "some element of this `Many` equals this" as
document **containment** rather than as an extraction — MariaDB's `json_contains`
does (`m-dialect`, `m-sql`) — and containment compares **JSON values**, so neither
comparison form above is what it binds. Both are wrong there, silently: a
`boolean` in the form its cast comparison binds is MariaDB's `1`, and a candidate
`{"flag": 1}` matches no element storing a JSON boolean, while a `decimal(p, s)`
in that form is a JSON number, and `{"amt": 1.50}` matches no element storing the
exact digit string `"1.50"`. What containment needs is each constrained leaf's own
**document encoding**, in place inside an object — this module's answer, and no
consumer's to spell or to wrap a literal in.

A candidate is a probe, never a document a row holds, and that is where its rules
part from `encode`'s. A path the constraints do not name is left
**unconstrained** rather than absent, so it contributes no key at all — including
a `Many` member, which therefore contributes no `[]`. Each named path MUST reach a
`Leaf` of `shape`, and a path that descends through a `One` occurrence nests
inside the candidate exactly as the stored document nests. The result is never
written, never patched, never decoded, and never compared structurally, so the
presence table and the encode/decode inverse below say nothing about it. That is
why it is its own operation rather than an `encode` over a partial mapping, whose
`Missing` means the opposite thing.

The constraints are **keyed by path**, and that is a precondition on the caller,
not a convenience: a candidate object holds one value per key, so **one constrained
path is one candidate key**. A consumer holding two constraints on one path — the
`x = a and x = b` a same-element conjunction can express — has one candidate to
build only when the two values are equal, in which case they are one constraint.
When they differ, no candidate carries them: this operation is not the place to
choose which one survives, because a dropped constraint yields a probe that matches
elements the predicate excludes, silently. The consumer either collapses the
duplicate or refuses the predicate before it reaches here (`m-sql`, `m-dialect`).

`patch` applies ordered patches to a document in memory and returns the result.
It never reads the database and never issues a statement; composing the
equivalent database expression is `m-sql`'s and `m-dialect`'s job, and the two
MUST agree, which is what makes an in-memory successor and a path-patched
`UPDATE` interchangeable.

Every operation is a pure function of its arguments. None mutates its input
document, and a returned document shares no mutable state with one passed in.

## Portable leaf encodings

Every Neutral Type has exactly one document spelling:

| Neutral type | Document representation |
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

**Every type is here.** A member whose declared type has no row above is not
storable in a document. There is no fallback to a host language's default
serializer, and no consumer may invent a spelling for a type this table does not
cover.

**`json` is not a leaf spelling.** `Json` is the one variant no member declares —
neither an Attribute nor a Value Object field may name it (`m-core`) — so no
`Leaf` ever carries it and the codec never faces free-form structured content
where a declared shape should be. Its row keeps the table total over the type
algebra: `Json` is the storage type a whole occurrence maps to, and where such a
value is what is being stored, its document form is that value itself, whose
object-member order is the stored value's own and is not observable state.

**Exactness over convenience.** `decimal` and `timestamp` are strings precisely
because JSON numbers cannot carry their contracts: a JSON number has no declared
scale and no guaranteed precision, and a naive round trip through a binary float
silently changes a value the database would have preserved. `float32`/`float64`
are numbers because they *are* binary floats; a non-finite float is not a
`m-core` value and never reaches the codec.

**A float's JSON number is the shortest one that decodes back to it.** "A JSON
number" alone does not pin a binary float down: `0.1` and `0.10000000000000001`
decode to the same binary64, so two conforming implementations could write two
*different* JSON numbers for one value — and two different numbers are two
different documents, so a `then.tableState` authored as `0.1` would pass against
one implementation and fail against the other, and a whole-occurrence comparison
(`m-unit-work`) against a subtree some other writer stored would report a change
where the value never changed. The encoding is therefore the number with the
**fewest significant digits** that decodes back to the value under the member's
declared format — binary32 for `float32`, binary64 for `float64` — and, where
several equally short numbers decode to it, the one **nearest** the value, and
where two of those are equally near, the one whose **last significant digit is
even**. All three levels are load-bearing: binary64 `562949953421312.25` is
decoded from both `562949953421312.2` and `562949953421312.3` — sixteen
significant digits each, `0.05` from the value each, with no fifteen-digit
candidate in range — so the first two levels alone still admit two numbers, and
the third selects `562949953421312.2`. (`1048576.2` / `1048576.3` is the same tie
for binary32 `1048576.25`.) This fixes the *number*, not its spelling: `20` and
`20.0` are one JSON number and either may be written, while `0.1` and
`0.10000000000000001` are two numbers and only `0.1` is admissible. It is what a
shortest-round-trip float formatter produces, the even-digit tie-break included;
a fixed-width `17`-significant-digit rendering is not admissible, even though it
also round-trips.

**Encoding and decoding are inverse.** For every value of a declared type,
decoding its encoding yields an equal value, and the encoding is the unique
document value this table admits. So a value's document form does not depend on
which consumer wrote it, and a predicate literal binds the same value the writer
stored — an equality comparison over a `date` or a `decimal` compares like with
like without any consumer normalizing first. Uniqueness is uniqueness of the JSON
*value*: a string encoding is unique character for character, while a JSON number
is a number, so `1` and `1.0` are one document value and neither a serializer's
rendering nor an engine's numeric normalization can make two encodings of one
value differ. For a binary float that uniqueness is what the shortest-number rule
above delivers — without it the table would admit many JSON numbers per value,
which is a different document each time.

**Decoding is by declared type, never by inspection.** A JSON string is decoded
as a `uuid`, a `date`, or a `string` because the member declares which. The
codec never guesses a type from a value's shape, so a `string` member holding
`"2026-01-01"` stays that string.

**The string spellings are comparison-significant, not house style.** SQL compares
a document-resident member of the numeric family — and a `boolean`, whose extracted
characters the concrete dialects do not agree on — through a dialect cast, and the
six **text-compared** types — `string`, `bytes`, `date`, `time`, `timestamp`, and
`uuid` — **by comparing the extracted text directly**, with no cast on either
dialect (`m-dialect`, `m-sql`). The split is by comparison behavior, not by
document form: `decimal(p, s)` is a JSON string above and still casts, because its
integer part has no fixed width, so `10.00` sorts below `9.00` as text and a range
predicate over it would answer with the wrong rows. Each of those six spellings is
therefore chosen so that, for two values of one declared type, the encodings are
equal exactly when the values are equal, and — for an ordered type — the encodings
compare in the values' own order. Zero-padded fixed-width fields with the most
significant first, a `Z`-normalized UTC instant, lowercase hexadecimal, and the
canonical lowercase UUID form are what deliver that, so they are normative here for
a reason that lives outside this module. The literal such a comparison binds is the
type's `comparisonText` — the string's own characters — never the JSON text that
carries them. A change to any of these spellings changes predicate and ordering
results, and MUST therefore be made together with `m-dialect`'s corresponding
decision — adding a cast for that type — rather than alone.

## Presence

Presence has exactly these canonical meanings, in a document of either kind:

| Presence | Document form |
|---|---|
| an omitted nullable member | the key is absent |
| an explicit null value | the key is present with JSON null |
| a required member | the key is present with a non-null valid encoding |
| a member not applicable to this row's concrete subtype | the key is absent |
| an empty `Many` occurrence | the key is present with `[]` |

A `Many` occurrence is an ordered JSON array of documents and is never null: its
empty array is the only representation of no contained values, so `Missing` and
`[]` are the same logical zero state on decode and `[]` is what `encode` writes.
`encode` therefore writes `[]` for a `Many` member given `Missing`,
`ExplicitNull`, or `Present` with an empty array alike — the same document
`encodeMany` returns for an empty sequence — and `decode` of a `Many` path
answers `Present` with `[]` for a key that is absent, JSON null, or an empty
array.

A `One` occurrence is one nested object, `ExplicitNull`, or `Missing`. Each of
the three is expressible on both sides of the interface: `encode` omits the key
for `Missing` and writes JSON null for `ExplicitNull`, and `decode` of that
occurrence's path answers with the same arm it was given. Presence
inside a Value Object subtree is not collapsed: a missing nullable occurrence and
an explicitly null one remain distinct, and so do a missing and an explicitly
null leaf inside it. Where a consumer's own contract collapses the two — scalar
observed no-op equality does (`m-unit-work`) — that collapse belongs to the
consumer and is applied to the codec's answer, not built into it.

A key the shape does not name is an **unknown key**: valid data written by some
other version of an application. Decoding never fails on one and never turns one
into a member value: a `Leaf` path answers only for the member the shape names,
so an unknown key is never a result member and never reaches an Entity member. An
`Occurrence` path answers with the stored subtree as it is, unknown keys and all,
because its two consumers — whole-occurrence comparison (`m-unit-work`) and
subtree replacement — ask what the row holds rather than what the model declares.
That subtree is a carrier, exactly like the raw Structured Column document, and
is never a member value or a result field.

## Patching, unknown keys, and subtree replacement

`patch` preserves every key it is not told to change, including unknown keys.
That is the whole point of patching rather than re-encoding: an application that
rebuilt a document from the members it knows would silently drop the rest.

- `SetLeaf` writes one path and leaves every other key untouched. Its value is a
  leaf presence — a `NeutralValue`, `ExplicitNull`, or `Missing`: writing
  `ExplicitNull` stores JSON null and writing `Missing` removes the key. A whole
  occurrence is replaced through `SetOccurrence`, never through `SetLeaf`.
- `SetOccurrence` replaces the subtree at its path in place. Its value is that
  occurrence's own document — an `encode` object for a `One`, an `encodeMany`
  array for a `Many` — or `Null`, and it is the same value a subtree-replacing
  `UPDATE` binds (`m-sql`), which is what keeps the in-memory successor and the
  statement interchangeable. Every key outside the subtree survives; unknown keys
  **inside** the replaced subtree do not. That asymmetry is deliberate — an
  author who assigns a whole occurrence has stated what that occurrence now is —
  and it is the one case where patching loses data a newer writer stored.

Patches apply in the order given, left to right, each over the result of the
last. `m-storage-layout` fixes that order for a Parallax write: canonical logical
placement order, which is sufficient because every assignment path has exactly
one segment and therefore never needs a parent another patch would create.

A temporal successor is built by patching the retained raw predecessor document
rather than by re-encoding decoded members, so keys the running application does
not declare survive the close-and-insert (`m-unit-work`).

## Determinism and comparison

Document object-member order is **not observable state**. Construction is
nevertheless deterministic — `encode` emits members in shape order, `encodeMany`
emits elements in its sequence's order, and `patch` applies its patches in the
given order — so one set of logical values produces one document with one member
order, which is what makes a golden bind stable to author. Determinism is a property of the document the codec builds, not of any
serialized text: whitespace, and whatever order a driver, an engine, or a
storage type imposes when it stores or returns the document, sit below this
contract, which is why comparison is structural rather than textual.

Comparison is **structural**: two documents are equal when they have the same
members with equal values, regardless of key order or insignificant whitespace.
Two arrays — the stored form of a `Many` occurrence — are equal when they have
the same length and equal elements in the same order, because a `Many` is
ordered and its order is observable state.
Consumers that compare documents state their own rules on top of this one:
`m-case-format` fixes structural comparison for asserted table state and
fixtures, and `m-unit-work` fixes it for whole-occurrence observed equality.

## Invalid stored data

A stored document whose content contradicts its shape is **invalid stored
data**: a required path that is missing, a nested structure that is not the
declared kind, or a value that does not decode into its declared Neutral Type.

This module defines no repair, no defaulting, and no cross-dialect corruption
error normalization. A decode of such a value fails, and a predicate over it may
instead surface the underlying database's own cast failure, which is a different
observable outcome on different engines. Parallax does not promise to make those
two paths agree; it promises never to invent a value for one.

## Consumer contract

- SQL lowering takes a predicate or ordering literal from this module — the type's
  `comparisonText` — where the comparison compares the extraction as text, and
  binds the managed value in its declared Neutral Type, through the dialect's typed
  bind normalization, where the comparison casts the extraction (`m-dialect`). So a
  comparison against a document-resident member compares the spelling the writer
  stored, in the form the extraction actually yields, and never routes an exact
  `decimal` through a JSON number to get there.
- SQL lowering takes a **containment candidate** from this module — `encodeCandidate`
  — where a dialect expresses a to-many equality as document containment rather than
  as an extraction (`m-dialect`, `m-sql`). That candidate carries each constrained
  leaf's **document encoding**, which is neither of the two forms above, so the
  three together close the lowering: text where it compares text, the managed value
  where it casts, the encoding where it contains. It binds as the `Document` it is —
  the dialect adapts it to its structured-document type at bind time, exactly as it
  adapts a written document — so no lowering and no golden ever holds its rendered
  text.
- Write composition encodes an insert's complete document here and derives each
  update's patches here, then lowers them through `m-dialect`.
- Read materialization decodes only the paths its result form needs, by declared
  Neutral Type, and drops unknown keys.
- Temporal observation retains the raw predecessor document unchanged and patches
  it here to build a successor.
- Fixture provisioning and conformance table read-back build and compare
  documents here rather than each spelling a leaf themselves.

No consumer may hand a raw host-language value to a JSON serializer, spell a leaf
encoding of its own, assemble a `Many` occurrence's array or a containment
candidate itself, decode by inspecting a JSON value's shape, or expose a raw
document as an Entity member or result field.
