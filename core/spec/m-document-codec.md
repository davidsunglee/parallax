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
and that document is itself a codec product: a consumer obtains it by encoding
the occurrence's own shape, never by assembling a host-language value graph.
Nesting is therefore expressed by composition rather than by a second interface,
and every leaf at every depth still passes through the encoding table below.

## Operations

```text
encode(shape: DocumentShape,
       values: Mapping<MemberName, Presence>)        -> Document

decode(shape: DocumentShape,
       document: Document,
       path: nonempty sequence<MemberName>)          -> Presence

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
occurrence's own document, which the same `encode` produced from that
occurrence's shape, so one complete document is composed from the leaves up.

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
occurrence's shape and its returned document.

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
| `float32`, `float64` | JSON number; a finite value only |
| `string` | JSON string |
| `decimal(p, s)` | JSON string, the exact decimal spelling: a `-` only for a value below zero, the integer digits with no leading zero (a single `0` when the integer part is zero), and — when `s > 0` — `.` and exactly `s` fraction digits |
| `bytes` | JSON string, lowercase hexadecimal, two digits per byte, no prefix or separator |
| `date` | JSON string, ISO-8601 `YYYY-MM-DD` |
| `time` | JSON string, ISO-8601 `hh:mm:ss`, with `.ffffff` when the value carries sub-second precision |
| `timestamp` | JSON string, ISO-8601 UTC at microsecond precision: `YYYY-MM-DDThh:mm:ss.ffffffZ` |
| `uuid` | JSON string, canonical lowercase 8-4-4-4-12 form |
| `json` | the JSON value itself |

Six rules make the table total rather than illustrative.

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

**Encoding and decoding are inverse.** For every value of a declared type,
decoding its encoding yields an equal value, and the encoding is the unique
document value this table admits. So a value's document form does not depend on
which consumer wrote it, and a predicate literal binds the same value the writer
stored — an equality comparison over a `date` or a `decimal` compares like with
like without any consumer normalizing first. Uniqueness is uniqueness of the JSON
*value*: a string encoding is unique character for character, while a JSON number
is a number, so `1` and `1.0` are one document value and neither a serializer's
rendering nor an engine's numeric normalization can make two encodings of one
value differ.

**Decoding is by declared type, never by inspection.** A JSON string is decoded
as a `uuid`, a `date`, or a `string` because the member declares which. The
codec never guesses a type from a value's shape, so a `string` member holding
`"2026-01-01"` stays that string.

**The non-numeric spellings are comparison-significant, not house style.** SQL compares
a document-resident member of the numeric family through a dialect cast, and every
other declarable type — `boolean`, `bytes`, `date`, `time`, `timestamp`, `uuid`,
and `string` itself — **by comparing the extracted text directly**, with no cast on
either dialect (`m-dialect`, `m-sql`). Each spelling above is therefore chosen so
that, for two values of one declared type, the encodings are equal exactly when the
values are equal, and — for an ordered type — the encodings compare in the values'
own order. Zero-padded fixed-width fields with the most significant first, a
`Z`-normalized UTC instant, lowercase hexadecimal, and the canonical lowercase UUID
form are what deliver that, so they are normative here for a reason that lives
outside this module. A change to any of these spellings changes predicate and
ordering results, and MUST therefore be made together with `m-dialect`'s
corresponding decision — adding a cast for that type — rather than alone.

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
`ExplicitNull`, or `Present` with an empty array alike, and `decode` of a `Many`
path answers `Present` with `[]` for a key that is absent, JSON null, or an empty
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
- `SetOccurrence` replaces the subtree at its path in place. Every key outside
  the subtree survives; unknown keys **inside** the replaced subtree do not. That
  asymmetry is deliberate — an author who assigns a whole occurrence has stated
  what that occurrence now is — and it is the one case where patching loses data
  a newer writer stored.

Patches apply in the order given, left to right, each over the result of the
last. `m-storage-layout` fixes that order for a Parallax write: canonical logical
placement order, which is sufficient because every assignment path has exactly
one segment and therefore never needs a parent another patch would create.

A temporal successor is built by patching the retained raw predecessor document
rather than by re-encoding decoded members, so keys the running application does
not declare survive the close-and-insert (`m-unit-work`).

## Determinism and comparison

Document object-member order is **not observable state**. Construction is
nevertheless deterministic — `encode` emits members in shape order and `patch`
applies its patches in the given order — so one set of logical values produces
one document with one member order, which is what makes a golden bind stable to
author. Determinism is a property of the document the codec builds, not of any
serialized text: whitespace, and whatever order a driver, an engine, or a
storage type imposes when it stores or returns the document, sit below this
contract, which is why comparison is structural rather than textual.

Comparison is **structural**: two documents are equal when they have the same
members with equal values, regardless of key order or insignificant whitespace.
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

- SQL lowering encodes a predicate or ordering literal through this module before
  binding it, so a comparison against a document-resident member compares the
  spelling the writer stored.
- Write composition encodes an insert's complete document here and derives each
  update's patches here, then lowers them through `m-dialect`.
- Read materialization decodes only the paths its result form needs, by declared
  Neutral Type, and drops unknown keys.
- Temporal observation retains the raw predecessor document unchanged and patches
  it here to build a successor.
- Fixture provisioning and conformance table read-back build and compare
  documents here rather than each spelling a leaf themselves.

No consumer may hand a raw host-language value to a JSON serializer, spell a leaf
encoding of its own, decode by inspecting a JSON value's shape, or expose a raw
document as an Entity member or result field.
