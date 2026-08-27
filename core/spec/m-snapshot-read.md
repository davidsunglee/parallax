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

Three questions meet at a materialized Value Object occurrence — **which members
the value carries**, **what a member reads as**, and **which stored spellings are
one member's zero** — and this section answers all three. Every other statement of
them, in this specification or in any surface built over it, is a consequence of
what is stated here rather than an independent rule.

For a **conforming** member, a materialized Value Object occurrence carries what
the stored document held: a member the document omits is absent from the
materialized value, and a member it stores as JSON null is carried, as null. That
is the presence distinction `m-document-codec` keeps inside a Value Object
subtree, and materialization neither collapses nor fills it. What is preserved is
each **declared** member's presence, not the source document: a read reduces its
occurrence to the members the shape declares (`m-document-codec`), so re-encoding
a materialized occurrence reproduces that document's declared members alone —
each conforming one in the presence it held, and a `Many` in the single canonical
`[]` its three stored spellings share. A key the shape does not declare never
becomes a member of any value, so no read carries it and no re-encoding restores
it; carrying one forward is what patching a retained document does
(`m-document-codec`), not what a read does. The same stored state answers the same
way under every Storage Layout.

Held and carried are nevertheless two different questions, and stored state the
hydration table collapses is where they part — in both directions. Two positions
are carried though the document held nothing there, and neither is a fill:

- A `Many` occurrence has no absent state. An omitted key, JSON null, and `[]` are
  its three stored spellings of one zero value (`m-document-codec`), so a `Many` is
  always carried, as the empty collection where the document supplied no elements.
  There is no fourth spelling: a non-null value that is not an array of object
  documents is `ManyWrongKind`, invalid stored data whose root is classified, and
  hydrating it through the empty collapse below does not make it an alias of the
  zero.
- A **non-nullable** `One` occurrence the document omits is the
  `stored-data-required-member-absent` state, whose normative absence collapse is
  what the hydration table above admits. That position is carried as null, and its
  root is classified.

One position runs the other way: a non-null **undecodable leaf** is unavailable,
so no value of its declared Neutral Type exists to put there, and the materialized
occurrence omits a key the document did hold, with its root classified. The
remaining collapses keep their key and lose their content — a wrong-kind `One` is
carried as its collapse, and a wrong-kind `Many` as the empty collection. None of
these four round trips, and none is meant to.

**What a member reads as and which members a value carries are two questions.** A
leaf or a `One` occurrence the document omits *reads* as not present, and both a
query's absence collapse (`m-predicate`) and a typed getter over the materialized
value answer null for it. A `Many` has no absent state to collapse, so it reads as
the empty ordered collection its zero value already is — never null. Neither
reading says anything about which keys a value carries, and a representation that
IS a document — a Wire Snapshot, whose leaves this module's member names key —
answers the second question rather than the first. A representation with getters
answers both, from one materialization: its getter answers the reading above, and
— at every position but the two carried ones — its document does not carry the
omitted member. So the two representations of one read observe one value, and
neither turns a stored absence into a stored null the other leaves absent.

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
- **A result is not necessarily one graph**, so graph-local is narrower than
  result-wide. A milestone-set read materializes one graph per milestone; a
  streamed delivery materializes one graph per root, which is the bound that
  surface exists for; how an **eager** read divides its result is not pinned at
  all, and materializing the whole result as one graph is conforming. What every
  one of them promises is the same sentence above, applied to the graph a node
  was published from — and the only division every one of them shares is a
  single root's own tree, so **root-local is the floor every materialization
  meets and the whole of what any of them promises**. A row that two *result
  roots* both reach is therefore one node wherever one graph carries both, which
  an eager read materialized as one graph observably does and a streamed
  delivery does not; that wider sharing is permitted and never promised. A
  caller that needs to know two roots reached one row compares their identities.
- A **value object** (`m-value-object`) is not a node: it has no identity, adds
  no relationship hop, and materializes *with* its owning entity as a plain
  nested value carrying the members *What a materialized value carries* fixes
  above.

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

Every clause above survives **composition**. Deriving a node from a
materialized one, and persisting a write, are the two things that happen to a
graph after it exists, and neither reaches the view state the read paid for:

- A **derived copy's view state IS its source's**. An authored edit produces a
  new value carrying the same relationship views the node it derives from
  carries — an included relationship answers the **same objects** on the copy,
  and an un-included one is absent on both. A copy rebuilt from its declared
  members alone loses every view the read materialized and is not conforming.
- A **write changes nothing about a graph already materialized**. The write
  persists; the graph is a value taken at its pin, so it neither refreshes nor
  invalidates. Accessing an already-materialized relationship after a write
  still issues no SQL and still answers the objects the read produced, whatever
  the write did to the rows behind them — including deleting them. Observing
  the write means issuing another read.
- The **unloaded / loaded-empty distinction is preserved across both**. A
  relationship the read included and found empty stays loaded-and-empty; one
  the read did not include stays absent. Neither collapses into the other, and
  composition never turns absence into emptiness.

How absence surfaces is unchanged by all of this: it is the same per-language
surfacing the first bullet above leaves each language spec to fix, answered the
same way before and after. What composition fixes globally is the behavior —
same objects, no SQL, the distinction preserved — because otherwise one authored
program would answer differently per language.

## Streamed delivery

A snapshot read may be delivered as a **Snapshot Stream** instead of as a whole
result. A stream is scope-bound and single-pass: it delivers roots one at a
time, forward only, and exposes no whole-result accessor. Delivery is the
distinction and representation is not, so a stream is a peer of the read it
streams in every representation that read has — one delivery mechanism, never a
format argument.

Roots arrive in the **Continuation Order**: a deterministic total order the
delivery derives rather than an Object Query clause, which always includes the
primary key and is therefore total.

Delivery is bounded by a **page size** counting root positions. It never bounds
included relationship rows, and it is a performance dial and nothing else:
changing it changes neither the order roots arrive in, nor which roots arrive,
nor the members, loadedness, identity, or issues any of them carries.

Each page is an ordinary read of a bounded root query, so `m-deep-fetch`'s
**`1 + L` ceiling applies once per page** and a page's child levels are the same
`IN (gathered keys)` lookups any read issues. A page that returned fewer roots
than it asked for proves exhaustion; a full one does not, so exhaustion costs one
more root statement returning nothing — unless a declared `limit` was already
delivered in full, which proves it without asking.

### Where a stream diverges from a whole-result read

Three divergences, and they apply identically to every representation.

- **Sharing narrows to root-local.** A row two result roots both reach is one
  node per root, where a whole-result read may answer one node for both. The
  promise is root-local either way, so what changes is what a caller can observe
  beyond it rather than what they may rely on. Stated in full under *Graph-local
  identity resolution* above, because the promise governs both.
- **An unordered `limit` becomes specified.** `m-object-query` makes an
  unordered `limit` a cap rather than pagination, returning an unspecified
  matching subset. A stream orders by the Continuation Order before capping, so
  the same query with the same `limit` returns the Continuation Order's own
  first `n` roots. The stream is strictly more specified — nothing a
  whole-result read promised is broken — but the two answer differently, and
  that is a property of the delivery rather than of the query.
- **A root whose primary key did not decode ends the delivery.** Only decoded
  values are bindable and the primary key is always in the Continuation Order,
  so such a root supplies nothing to continue from. The rule is stated
  positionally-independent — *a stream cannot continue past a root whose primary
  key did not decode* — precisely so the page size cannot change it: the same
  stored row may not be survivable at one page size and fatal at another. The
  root itself is published exactly as a whole-result read publishes it, in band
  where the reading surface delivers classified roots in band and as a refusal
  where it refuses them; what follows it is the end of the delivery either way.

## Round trips

Materialization is `m-deep-fetch`'s contract observed through the graph: **at
most `1 + L` statements** for `L` distinct relationship hops, one statement per
non-empty level, empty parent-key levels issuing no child SQL. Constructing the
query is side-effect-free; the single explicit execution is the only moment the
database is touched. (For the managed-object surface this round-trip
observability rides the lazy query-backed list, `m-op-list`; a snapshot
read is **not** a query-backed list — the count is pinned here instead,
on the same golden statements.)

When an Execution Lifecycle Provider accepts the Root Execution, the read
publishes one transient Read activity containing its Database Call children
(`m-execution-lifecycle`). The snapshot result retains no trace or lifecycle
record. The portable `then.roundTrips` oracle and authored statements continue
to pin the `1 + L` ceiling independently of whether observation is installed.

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
