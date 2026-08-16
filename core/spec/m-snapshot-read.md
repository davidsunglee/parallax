# m-snapshot-read — Snapshot Graph Materialization

`m-snapshot-read` specifies the **snapshot graph**: the typed plain value graph
a snapshot read returns — identity-resolved within the graph, connected by hard
pointers, pinned whole-graph at one set of as-of coordinates, and **closed
world**. Per the dependency graph, `m-snapshot-read` depends on `m-deep-fetch`
(graph population is deep fetch; navigation, as-of propagation, and lists are
reached transitively). It is the **plain-value** read surface; a managed-object
surface materializes managed objects through `m-identity-map` instead.

A snapshot read is **execute → value**: one explicit execution materializes the
whole graph, and nothing about the graph is live afterwards. There is no
managed lifecycle, no identity map, no change tracking, and no write-back —
changes are persisted through the explicit write modules (`m-batch-write`,
`m-txtime-write`, `m-bitemp-write`, `m-cascade-delete`), never by diffing a
graph.

## Invalid stored data

Snapshot Read owns the one public stored-data issue vocabulary. Detecting modules
report facts in their own local terms; this module translates those facts without
re-judging them and classifies the affected result root. The initial vocabulary
is closed:

```text
stored-data-required-member-absent
stored-data-required-member-null
stored-data-one-wrong-kind
stored-data-many-wrong-kind
stored-data-leaf-undecodable
stored-data-attribute-null
stored-data-family-tag-unknown
stored-data-primary-key-null
stored-data-primary-key-undecodable
```

A raw non-object Entity document under Relational Document Layout does not add a
tenth issue code. The Structured Column is a physical carrier with no logical
member identity, so `m-document-codec`'s `locateEntityMember` accepts it and
returns `Missing` independently for each requested document-resident Entity
member. `decodeLocatedMemberClassified` then applies that member's existing
classification. Translation uses the existing member code, if any; nullable
missing members and accepted absent `Many` values remain conforming. An
unrequested member never acquires an issue merely because it shared that carrier.

The hydration rule is equally closed:

| Stored state | Root hydration |
|---|---|
| non-nullable, non-`Many` document member absent | hydrate with the normative absence collapse |
| non-nullable, non-`Many` document member JSON null | hydrate with the normative null collapse |
| non-null wrong-kind `One` occurrence | hydrate with the normative occurrence collapse |
| non-null wrong-kind `Many` occurrence, including an array with a non-object element | hydrate with the normative whole-occurrence collapse |
| non-null undecodable document leaf | unavailable |
| non-nullable top-level Entity Attribute absent or null in either physical representation | unavailable |
| family tag matching no concrete subtype | unavailable |
| null primary key | unavailable |
| undecodable primary key | unavailable |

Classification never repairs, defaults, substitutes, or fabricates. A root is
hydrated only when every requested value can be produced by an already-normative
collapse; otherwise its data is unavailable. The same stored state yields the
same issue and hydration answer under every Storage Layout. For a non-nullable
top-level Entity Attribute, SQL `NULL` under `Columns` and an absent or JSON-null
Entity-document member under `Document` all translate to
`stored-data-attribute-null` and make hydration unavailable. The codec's local
required-member finding remains evidence for the latter route; public translation
is fixed by the logical Entity member, not by its placement. No layout may instead
publish `stored-data-required-member-absent` or
`stored-data-required-member-null` with hydratable absence for that Attribute.
For a non-object Entity document, the member-local input returned by
`locateEntityMember` and classified by `decodeLocatedMemberClassified` follows
this same translation and hydration rule: a requested non-nullable Entity
Attribute makes hydration unavailable as `stored-data-attribute-null`, while
requested occurrences and nullable members retain their existing absence
behavior. The carrier itself is never substituted into the result graph.

Detection is demand-driven over `m-document-codec` Logical Judging Roots. The
Entity and each top-level Value Object occurrence supply the same roots under
both layouts. Member Placement locates each requested Entity member, but the
Entity-root classifier accepts either the direct column's already-tagged `m-core`
`DocumentRead` or `locateEntityMember`'s result over the raw Entity document. A
direct `SqlNull` remains distinct from `PresentDocument(document: JSON null)`;
materialization does not inspect a driver or host null sentinel. Both
occurrence placement arms pass that `LocatedMemberInput` to
`decodeLocatedMemberClassified` and emit one logical verdict before entering the
occurrence root. A requested occurrence descendant advances a Logical Judging
Cursor only after its carrier is classified; deeper wrong-kind or undecodable
stored state therefore returns a finding rather than escaping through strict
decoding. No cursor judges an unrequested sibling or descendant. Layout parity
fixes *where* the same requested logical member is judged without turning
classification into whole-subtree validation.

An issue anywhere in a root's requested include tree classifies that result root.
Shared affected nodes repeat the issue for every result root that reaches them,
while duplicate diagnoses within one root collapse. Classification preserves the
root's result position; it never prunes the node, silently drops the root, or
publishes a node-level invalid union. The public result and accessor shapes that
carry this classification are language-surface concerns built over this contract.

## What a materialized value carries

A materialized Value Object occurrence carries the members the stored document
**held**. A member the document omits is absent from the materialized value; a
member the document stores as JSON null is carried, as null. That is the presence
distinction `m-document-codec` keeps inside a Value Object subtree, and
materialization neither collapses nor fills it, so a materialized occurrence
serializes back to the document it came from — apart from the two positions
below, which are the only ones whose round trip changes a stored spelling. The
same stored state answers the same way under every Storage Layout.

Two positions carry a member the document does not hold, and neither is a fill:

- A `Many` occurrence has no absent state. An omitted key, JSON null, and `[]` are
  three stored spellings of one zero value (`m-document-codec`), so a `Many` is
  always carried, as the empty collection where the document supplied no elements.
- A **non-nullable** `One` occurrence the document omits is the
  `stored-data-required-member-absent` state, whose normative absence collapse is
  what the hydration table above admits. That position is carried as null, and its
  root is classified.

**What a member reads as and which members a value carries are two questions.** A
member the document omits *reads* as not present — the absence collapse
`m-predicate` fixes for a query and `m-value-object` fixes for a typed getter, both
of which answer null for it. That collapse says nothing about which keys a value
carries, and a representation that IS a document — a Wire Snapshot, whose leaves
this module's member names key — answers the second question rather than the first.
A representation with getters answers both, from one materialization: its getter
answers null for the omitted member and its document does not carry it. So the two
representations of one read observe one value, and neither can turn a stored
absence into a stored null.

## Graph-local identity resolution

Within **one materialized graph**, one row is **one node**:

- Two include paths that reach the same row — the diamond — materialize a
  **single** node referenced from both positions, never two equal copies. The
  resolution key is the same triple as `m-identity-map`'s: **(entity family,
  primary key, lowered as-of coordinate per declared axis)** — family-normalized
  (`m-inheritance`), coordinate-aware, degrading to (family, primary key) for a
  non-temporal entity.
- Resolution is **projection-independent**: the key alone decides which node a
  path reaches, never the attribute set the level fetched. Levels that reach one
  node with *different* fetched attribute sets still produce **one** node, and
  every attribute any reaching level fetched has a well-defined value (all
  levels read the same pinned row — the whole-graph pin below), but the exact
  attribute superset the node carries is **not pinned** here: materializing the
  union — or whole objects, as Reladomo's deep fetch does — is conforming.
- References between nodes are **hard pointers** (the language's plain object
  reference). Diamonds are expected; a back-reference include path produces a
  true in-memory cycle, which is legal — JSON-safety is the job of serialization
  shapes producing **Domain Snapshots**, never a constraint on the graph.
- Resolution is **graph-local**: two *separate* materializations make no
  same-node promise, and no node is ever interned beyond its own graph. There is
  no scope wider than the graph in this module.
- A **value object** (`m-value-object`) is not a node: it has no identity and
  materializes *with* its owning entity as a plain nested value, exactly as its
  materialization contract specifies.

## The whole-graph pin

A snapshot graph is **point-consistent**: the root query's lowered as-of
coordinates propagate per hop, matched by axis, to every temporal entity in the
graph (`m-navigate` as-of propagation, applied inside each `m-deep-fetch` child
level). Every temporal node is pinned at the propagated coordinates; an axis
unpinned at the root defaults to latest; a non-temporal node carries no
coordinate. Hard pointers are safe *because* of this rule — every node in one
graph represents the same instant, so a reference can never silently cross
temporal contexts.

A `history` / `asOfRange` read returns **one graph per milestone**, each pinned
at its **edge pin** — the milestone's own from-instant (`m-temporal-read`; for a
half-open `[from, to)` interval the from-instant is the one instant guaranteed
to select exactly that milestone). Combining a history read with `includes` is
the **`snapshot-history-includes` feature** — carried on its own feature tag so
the conformance adapter's claimed capability set can include or defer it
independently. This is an implementation claim, not a database-provider
capability. It is a staged feature, **not a rejection**: no case may mandate
that history-with-includes be refused.

## Closed world

After materialization a snapshot graph **never issues SQL**:

- Navigating a relationship the read did not include finds it **absent**; how
  absence surfaces (a missing property, a typed empty marker, an error on
  access) is per-language, but issuing a load is **not** a legal surfacing.
  There is no lazy loading and no deferred-load trigger of any kind — the
  deferred relationship load (`m-deep-fetch`) belongs to the managed-object
  surface and requires a live unit of work, which a snapshot graph never has.
- A snapshot graph is never enrolled in a unit of work: mutating a node is a
  plain in-memory change with no persistence meaning. Persisting a change means
  reformulating it as an explicit write.
- Wanting more data means issuing another read — including the batched
  second-query form (`find` with an `in` predicate over gathered keys), which
  costs the same single round trip a deferred load would.

## Round trips

Materialization is `m-deep-fetch`'s contract observed through the graph: **at
most `1 + L` statements** for `L` distinct relationship hops, one statement per
non-empty level, empty parent-key levels issuing no child SQL. Constructing the
query is side-effect-free; the single explicit execution is the only moment the
database is touched. (For the managed-object surface this round-trip
observability rides the lazy query-backed list, `m-op-list`; a snapshot
read is **not** a query-backed list — the count is pinned here instead,
on the same golden statements.)

A snapshot result carries the **Read Trace** (`m-execution-log`) of the calls it
issued, and the ceiling is observed through that record rather than through a
bare number the read invents: each Database Call names the Lowered Statement it
ran and how it completed, and the trace's round-trip count is what `1 + L`
bounds. A read that PARTICIPATES in a transaction shares that one trace object
with the Transaction Attempt that issued it, so the graph and the transaction's
own provenance never disagree about what a level cost.

## What the suite pins down

Snapshot cases are **read**-shape deep-fetch cases (`m-case-format`): golden
statements, the assembled `then.graph`, and the declared `then.roundTrips`. The
graph fixture is a tree, so the diamond's shared node appears as equal values at
both positions, and diamond fixtures stay **projection-neutral** — every path to
a shared row fetches the identical attribute set, so no graph expectation
depends on which path materializes a node first; the **reference-equality** half
of identity resolution (one node, two pointers) is asserted per-language by the
API Conformance Suite (`m-api-conformance`), the same division of labor as
`sameObjectAs` scenarios.

| Case | What it proves |
|---|---|
| diamond identity resolution | two include paths reach the same rows (`Order.items` and `Order.itemsByShipDate` — one `OrderItem` row set behind two orderings); the graph carries them at both positions from one statement per level — `1 + L` round trips, values identical at both positions |
| pinned graph consistency | a deep fetch pinned to a past instant materializes every temporal node at the propagated pin — a point-consistent graph containing now-superseded milestones |
