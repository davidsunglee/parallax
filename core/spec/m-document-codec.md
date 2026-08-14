# m-document-codec — Portable Document Encoding

`m-document-codec` owns the portable representation of every neutral value
stored inside a structured document, and the in-memory operations that build,
read, and patch such a document. It depends on `m-core`, `m-metamodel`, and
`m-wire`, which owns the one canonical spelling every stored leaf carries.

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

LogicalJudgingRoot
  position: EntityIdentity | top-level ValueObjectIdentity
  members: immutable sequence<DocumentMember>

LogicalJudgingCursor
  root: LogicalJudgingRoot
  prefix: sequence<MemberName>
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

A `LogicalJudgingRoot` is also derived from accepted Metadata, but it defines a
read-validity boundary rather than a physical document shape. Every Entity
supplies one root over its applicable top-level members, and every top-level
Value Object occurrence supplies one root over its direct members. These roots
and their member trees are identical under `Columns` and `Document`; a Structured
Column root, a Column, and a `DocumentPath` are physical locations and cannot
create or remove one.

A `LogicalJudgingCursor` is an on-demand position within one root. The root cursor
has an empty prefix. Materialization advances it only through an occurrence on a
requested path, after that occurrence's carrier has been classified. A nested
occurrence therefore supplies no independent root: its cursor retains the
top-level root and records the logical prefix used for findings. A `One` has one
cursor over its object; a `Many` has one cursor over each visited element object.
Creating a cursor neither inspects nor judges any sibling member.

A `Document` is `m-core`'s portable `DocumentValue` — object, array, string,
number, boolean, or null — and nothing else. It is not a driver value, rendered
text, or provider-native document handle.

The raw Entity document read from a Relational Document Layout Structured Column
is a physical carrier, not itself a logical member. Its database type guarantees
only a non-SQL-null `Document`, so JSON null, an array, or a scalar can reach read
materialization even though every codec-produced Entity document is an object.
Such a value cannot create a root cursor. `locateEntityMember` accepts the raw
carrier instead: for an object it locates the requested direct Entity member as
`PresentDocument` or `Missing`, and for a non-object it locates that member as
`Missing`. `decodeLocatedMemberClassified` then applies the member's existing
rules to that located input. A required member produces its existing absent
finding, a nullable member remains missing, and a `Many` uses its accepted
absent-to-empty collapse. There is no separate root-carrier finding. This is a
demand-driven codec projection onto requested logical member positions, not a
replacement of the stored document; the raw carrier remains unchanged for
observation and writing.

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

locateEntityMember(root: LogicalJudgingRoot,
                   document: Document,
                   member: MemberName)                -> LocatedMemberInput

decodeLocatedMemberClassified(root: LogicalJudgingRoot,
                              input: LocatedMemberInput,
                              member: MemberName)      -> DecodedMember

decodeClassified(cursor: LogicalJudgingCursor,
                 document: Document,
                 member: MemberName)                  -> DecodedMember

LocatedMemberInput =
    SqlNull
  | Missing
  | PresentDocument(document: Document)

DecodedMember
  presence: Presence | Unavailable
  findings: immutable sequence<StoredShapeFinding>

StoredShapeFinding =
    RequiredMemberAbsent
  | RequiredMemberNull
  | OneWrongKind
  | ManyWrongKind
  | LeafUndecodable

comparisonText(type: NeutralType,
               value: NeutralValue)                  -> string

encodeCandidate(shape: DocumentShape,
                constraints: nonempty Mapping<
                    nonempty sequence<MemberName>, NeutralValue>) -> Document

patch(shape: DocumentShape,
      document: Document,
      patches: nonempty ordered sequence<DocumentPatch>) -> Document

DocumentPatch =
    SetLeaf(path: nonempty sequence<MemberName>,
            value: Presence)
  | SetOccurrence(path: nonempty sequence<MemberName>,
                  document: Document | Null)
  | SetMany(path: nonempty sequence<MemberName>,
            elements: sequence<Document>)
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

`locateEntityMember` is the only operation that accepts a raw Entity document
carrier. `root` MUST be the Entity's Logical Judging Root and `member` MUST name
one direct document-resident member of it. When `document` is an object, the
operation returns `PresentDocument` with that key's raw value or `Missing` when
the key is absent. When it is JSON null, an array, or a scalar, the operation
also returns `Missing`. It creates no cursor for the non-object carrier and
inspects no other member. An Entity root not derived from accepted Metadata or
an unknown member is a caller error; every `Document` carrier kind is stored
input, not a caller error.

`decodeLocatedMemberClassified` is the Entity-root form of classified decoding.
It accepts the carrier-independent input for one located document-valued Entity
member. For a direct Structured Column, `SqlNull` and `PresentDocument` are the
two arms of the `m-core` `DocumentRead` already formed at the database boundary;
the materializer MUST NOT infer either arm from its payload. `Missing` arises
after codec-owned Entity-document location found no member. A
`PresentDocument` from either placement arm carries the raw parsed document
value. `member` MUST name that
direct member in the Entity root. `SqlNull` has the same member presence as an
absent key; `PresentDocument` preserves JSON null and every other document kind
for classification. The operation applies the member's declared nullability,
multiplicity, and type exactly once. In particular, a direct `One` may classify
as absent, explicit null, present object, or `OneWrongKind`, and a direct `Many`
may classify as empty, a present array of objects, or `ManyWrongKind`, including
for an array containing a non-object element. It creates the same `DecodedMember`
for equal logical inputs under either placement and inspects no sibling.

`decodeClassified` is the cursor-facing form of classified decoding. `member`
MUST name one direct member of `cursor`, and `document` MUST be that cursor's
carrier object. An unknown member, a cursor not derived from accepted Metadata,
or a non-object supplied as an occurrence cursor's carrier is a caller error.
Stored state on a requested branch is not a caller error: the classified
operations return findings as values for every shape contradiction they
encounter and never raise for one. A conforming member has the same `Presence`
as `decode` and no finding.
Stored data that contradicts the member's declared shape produces one or more
`StoredShapeFinding` values and is therefore the third semantic answer beside
*present* and *not present*. Where the ordinary read collapse can produce a value
without invention, `presence` carries that collapsed value: an absent or
JSON-null required non-`Many` member retains its absence, a non-null wrong-kind
`One` is absent, and a wrong-kind `Many` is the empty array. A non-null
undecodable leaf carries `Unavailable`, because no value of its declared Neutral
Type can be produced.

When a requested path continues through an occurrence,
`decodeLocatedMemberClassified` at the Entity root or `decodeClassified` at a
cursor first classifies that occurrence. A conforming `One` object advances to
one cursor and a conforming `Many` array advances to one cursor per element, in
stored order. A `Many` is conforming only when every element is an object
document. A non-array value or an array containing a non-object element is one
`ManyWrongKind` at the occurrence position; it collapses the whole occurrence to
the empty array and creates no element cursor. A wrong-kind `One` likewise
creates no cursor. The requested descendant therefore never reaches strict
`decode` after a malformed ancestor.

Materialization obtains a requested top-level occurrence carrier before using its
root. Under `Columns`, the occurrence's Structured Column supplies the port's
`DocumentRead` as `SqlNull` or `PresentDocument` without the materializer
interpreting the document value. Under `Document`,
`locateEntityMember` supplies `Missing` or `PresentDocument` from the raw Entity
document. Both arms pass that input to `decodeLocatedMemberClassified` before
entering the occurrence root. The materializer then classifies only the requested
branch, advancing a cursor after each conforming occurrence. Thus `address.city`
and `address.geo.lat` are judged from the `address` root under both layouts even
though their physical paths differ.

Judgement remains demand-driven rather than a scan of an opaque subtree. One
classified invocation judges one requested direct member of one Entity root or
cursor. Advancing through an occurrence judges only its carrier kind; its members
are judged only when the requested path or requested result shape names them.
Unrequested siblings and descendants are never inspected for findings. A
multi-segment placement used only for SQL predicate extraction likewise performs
no codec judgement. Logical roots select the validity boundary, cursors keep
descendant work within that boundary, and physical paths only locate carriers.

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

`patch` resolves each path against `shape` for the same reason every other
operation here takes one. A `SetLeaf` carries a `NeutralValue`, so writing it
needs that leaf's declared Neutral Type; without the shape the caller would have
to spell the encoding itself, which the consumer contract below forbids. The
shape is also what makes a path the model does not declare a caller error rather
than a new key, so patching can never introduce one. `comparisonText` is the one
operation that takes an explicit `NeutralType` instead, because it is given a
value rather than a position in a document.

Every operation is a pure function of its arguments. None mutates its input
document, and a returned document shares no mutable state with one passed in.

## Portable leaf encodings

A document leaf's spelling is the value's canonical **Wire Value** (`m-wire`):
one spelling per Neutral Type, total over the type algebra, unique per value, and
inverse under decoding. This module states no table of its own and admits no
second spelling — the characters a Wire read renders are the characters a
document stores, so storage and transport cannot drift apart.

A member whose declared type has no Wire Value is not storable in a document, and
`json` is never a leaf spelling: no Attribute and no Value Object field may
declare it (`m-core`), so the codec never faces free-form structured content
where a declared shape should be.

Three obligations belong to the document position rather than to the spelling.

**The string spellings are comparison-significant, not house style.** SQL compares
a document-resident member of the numeric family — and a `boolean`, whose extracted
characters the concrete dialects do not agree on — through a dialect cast, and the
six **text-compared** types — `string`, `bytes`, `date`, `time`, `timestamp`, and
`uuid` — **by comparing the extracted text directly**, with no cast on either
dialect (`m-dialect`, `m-sql`). The split is by comparison behavior, not by
document form: `decimal(p, s)` is a JSON string and still casts, because its
integer part has no fixed width, so `10.00` sorts below `9.00` as text and a range
predicate over it would answer with the wrong rows. Each of those six spellings is
chosen so that, for two values of one declared type, the encodings are equal
exactly when the values are equal, and — for an ordered type — the encodings
compare in the values' own order. Zero-padded fixed-width fields with the most
significant first, a `Z`-normalized UTC instant, lowercase hexadecimal, and the
canonical lowercase UUID form are what deliver that, so `m-wire`'s choice of them
is load-bearing here for a reason that lives outside that module. The literal such
a comparison binds is the type's `comparisonText` — the string's own characters —
never the JSON text that carries them. A change to any of these spellings changes
predicate and ordering results, and MUST therefore be made together with
`m-dialect`'s corresponding decision — adding a cast for that type — rather than
alone.

**Reading a value and validating a stored document are two questions.** `m-wire`
answers the first for every value wherever it appears — a case literal, a
predicate literal, a member of a document being decoded — and never refuses on
canonicality, because what a value names cannot depend on who wrote it.

Canonicality is a separate, *writer* obligation, and the seam that reads a
document back **out of storage** is where it is enforced: that seam MUST reject a
stored value that is not the canonical spelling of the value it names, when its
carrier preserves enough information to tell the two apart. A `decimal(p, s)`
short of its declared scale, uppercase hexadecimal, a `timestamp` at a non-UTC
offset, an uppercase or hyphenless UUID, and a float number that is not the
shortest one for the value it names all decode into their declared type and are
still a DIFFERENT document from the one a writer of that value would have stored.
When parsing has already collapsed two spellings to the same carrier value, as a
binary64 carrier does for `float64`, the seam cannot recover the distinction and
MUST materialize the declared value; that does not weaken the obligation on the
writer. A case literal is not a stored document and is not subject to this check —
it is an input a case authored, graded for membership alone (`m-case-format`
"In-space").

**Rejection is not repair.** A stored leaf that is the encoding of nothing is
invalid stored data ("Invalid stored data", below): the codec reports it and
never substitutes, defaults, or re-spells it.

## Presence

Encoding writes exactly these canonical presence forms, in a document of either
kind:

| Presence | Document form |
|---|---|
| an omitted nullable non-`Many` member | the key is absent |
| an explicit null nullable leaf or `One` | the key is present with JSON null |
| a required member | the key is present with a non-null valid encoding |
| a member not applicable to this row's concrete subtype | the key is absent |
| an empty `Many` occurrence | the key is present with `[]` |

A `Many` occurrence's canonical encoded form is an ordered JSON array of
documents and is never null: its empty array is the only form an encoder produces
for no contained values. `encode` therefore writes `[]` for a `Many` member given
`Missing`, `ExplicitNull`, or `Present` with an empty array alike — the same
document `encodeMany` returns for an empty sequence. On decode, an absent key and
JSON null are accepted non-canonical stored aliases for that same logical zero
state, and both answer `Present` with `[]`. They are conforming inputs but are
normalized to `[]` by any subsequent encode.

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
because a patch must see the state it writes over in order to preserve it.
That subtree is a carrier, exactly like the raw Structured Column document, and
is never a member value or a result field.

## Patching, unknown keys, and occurrence assignments

`patch` preserves every key it is not told to change, including unknown keys.
That is the whole point of patching rather than re-encoding: an application that
rebuilt a document from the members it knows would silently drop the rest.

- `SetLeaf` writes one path and leaves every other key untouched. Its value is a
  leaf presence — a `NeutralValue`, `ExplicitNull`, or `Missing`: writing
  `ExplicitNull` stores JSON null and writing `Missing` removes the key. A whole
  occurrence is stated only through its matching occurrence arm.
- `SetOccurrence` states a `one` occurrence's named declared members. It patches
  each named leaf or nested occurrence recursively, leaves omitted nullable
  members and every undeclared key untouched, and stores JSON null when its
  document is `Null`. At every nested level an absent, JSON-null, or non-object
  target is treated as an empty object before applying the named members.
- `SetMany` replaces its encoded ordered array whole. Elements have no identity,
  so no stored element state survives the replacement.

The exported declared-member reduction is the sole shape-aware operation used by
materialization and write comparison. It decodes leaves by declared Neutral Type,
reduces a `one` recursively and a `many` element-wise, and excludes every key the
shape does not declare. Consumers MUST NOT implement another local reduction.

The reduction takes two independent options that each narrow its result, and they
are not interchangeable because they answer different questions. The
**authored-member mask** asks which members a *caller* authored: it is supplied
from outside the source document, and only the members it names contribute,
recursively through `one` occurrences. **Presence preservation** asks which
members *this document* holds, which the source answers by itself: a member the
source omits contributes nothing, at every containment depth, including inside a
`many` element, while a member stored as JSON null still contributes its null. A
reduction that preserves presence therefore carries the missing-versus-explicitly-null
distinction this module already keeps at the interface, instead of collapsing it
onto the declared member list. A consumer materializing stored state into carriers
that record presence preserves it; a consumer comparing an assignment against
stored state masks by the assignment. Neither option is the other's default.

Patches apply in the order given, left to right, each over the result of the
last. `m-storage-layout` fixes that order for a Parallax write: canonical logical
placement order. Top-level assignments name disjoint subtrees. Within a
`SetOccurrence`, each occurrence level establishes its own object parent before
applying its nested assignments, so no dependency sort exists between top-level
members.

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

A stored document whose content contradicts its shape is **invalid stored data**.
At a judged member position, the verdict is closed:

| Stored state | Verdict | Read hydration |
|---|---|---|
| non-nullable, non-`Many` member key absent | `RequiredMemberAbsent` | retain the normative absence collapse |
| non-nullable, non-`Many` member key present with JSON null | `RequiredMemberNull` | retain the normative null collapse |
| `One` occurrence present with a non-null, non-object value | `OneWrongKind` | collapse the occurrence to absent |
| `Many` occurrence present with a non-null value that is not an array of object documents | `ManyWrongKind` | collapse the whole occurrence to the empty array |
| non-null leaf value not decodable as its declared Neutral Type | `LeafUndecodable` | `Unavailable` |

The complementary states remain conforming: an absent or JSON-null nullable leaf
or nullable `One` preserves its exact `Missing` or `ExplicitNull` presence; the
accepted non-canonical absent and JSON-null `Many` forms and the canonical empty
array all decode to `Present([])`; a `Many` array is correctly shaped only when
every element is an object document; every other correctly shaped occurrence and
a decodable leaf are present; and unknown keys remain valid carrier state. There
is no implementation-selected middle category.

A non-object raw Entity document is outside this member-position table because
the shared Structured Column is a physical carrier rather than a declared
member. `locateEntityMember` maps it to `Missing` member by member, and
`decodeLocatedMemberClassified` applies the existing row: each requested
document-resident Entity member's nullability and multiplicity determine whether
an existing finding and collapse apply. The carrier creates neither a sixth
local finding nor an unrequested-member scan.

This module defines no repair, no defaulting, and no cross-dialect corruption
error normalization. Classification records the contradiction; it does not make
the stored value conforming. Hydration is permitted only for the four rows whose
collapse already has a normative value. `Unavailable` is mandatory for an
undecodable leaf because substituting a null, zero, empty string, or any other
value would invent domain state. Predicate extraction retains `m-predicate`'s
own absence-collapse truth table and may still surface a database cast failure;
neither outcome changes this shape-aware verdict.

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
- Read materialization obtains `LocatedMemberInput` from the direct Structured
  Column's already-tagged `DocumentRead` or from `locateEntityMember`, passes
  either arm to `decodeLocatedMemberClassified`, then uses `decodeClassified`
  after entering a conforming occurrence. The classified operations decode by
  declared Neutral Type and drop unknown keys. Materialization never inspects an
  Entity carrier's JSON shape, projects `Missing` itself, interprets a direct
  document carrier, or falls back to strict decoding for requested stored state
  below a logical root.
- Temporal observation retains the raw predecessor document unchanged and patches
  it here to build a successor.
- Fixture provisioning and conformance table read-back build and compare
  documents here rather than each spelling a leaf themselves.

No consumer may hand a raw host-language value to a JSON serializer, spell a leaf
encoding of its own, assemble a `Many` occurrence's array or a containment
candidate itself, decode by inspecting a JSON value's shape, or expose a raw
document as an Entity member or result field.
