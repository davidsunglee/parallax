# m-snapshot-read — Snapshot Publication

`m-snapshot-read` specifies the **snapshot graph**: the typed plain value graph
a snapshot read returns — identity-resolved within the graph, connected by hard
pointers, pinned whole-graph at one set of as-of coordinates, and **closed
world**. Per the dependency graph, `m-snapshot-read` depends on `m-execution`
(a snapshot read runs under its adopted model, options, and connection policy),
`m-read-delivery` (whose judged Page a snapshot graph is published from),
`m-deep-fetch` (graph population is deep fetch; navigation, as-of propagation,
and lists are reached transitively), and `m-edit` (derivation carries a
materialized value's state by complement). It is the **plain-value** read
surface; a managed-object surface materializes managed objects through
`m-identity-map` instead.

A snapshot read is **execute → value**: one explicit execution materializes the
whole graph, and nothing about the graph is live afterwards. There is no
managed lifecycle, no identity map, no change tracking, and no write-back —
changes are persisted through the explicit write modules (`m-batch-write`,
`m-temporal-write`, `m-cascade-delete`), never by diffing a
graph.

## Publishing a snapshot graph

A snapshot read runs through `m-execution` and is delivered, whole or streamed,
by `m-read-delivery`; Snapshot is the Publication that delivery invokes. It
builds Typed and Wire values from a Page's judged Entity States — choosing each
root's reachable projections through its Root View, checking them for
consistency, classifying the root, and attaching Read Origins to eligible
values — and composes the eager result envelope from those roots. Stored-data
judgement and its vocabulary, the Page, whole-result atomicity, the Continuation
Order, page bounds, and the connection a delivery holds are `m-read-delivery`'s
and apply to every snapshot read unchanged; the Snapshot surface names its
streamed delivery a **Snapshot Stream**. Publication opens no lifecycle activity
of its own: it runs inside the Read or Stream activity execution and delivery
open (`m-execution-lifecycle`), and a published graph or stream value retains no
observation record.

## Classified roots

The stored-data issue vocabulary and its hydration rule are `m-read-delivery`'s
(*Invalid stored data*); Snapshot attributes the issues a root reaches to that
root.

An issue anywhere in a root's requested include tree classifies that result root.
Shared affected nodes repeat the issue for every result root that reaches them,
while duplicate diagnoses within one root collapse. Classification preserves the
root's result position; it never prunes the node, silently drops the root, or
publishes a node-level invalid union. The public result and accessor shapes that
carry this classification are language-surface concerns built over this contract.

Any finding suppresses write authority for the complete classified root. A
hydratable root may still publish its collapsed diagnostic data, but neither that
root nor any node reached only through it carries a Read Origin. Entity State
sharing does not share this authority decision: when a valid root and an invalid
root reach one page-owned Entity State, their root-local node graphs are distinct;
the valid root's node may carry its ordinary Read Origin and the invalid root's
corresponding node carries none. A diagnostic value is never a route around the
classification that produced it.

## What a materialized value carries

Three questions meet at a materialized Value Object occurrence — **which members
the value carries**, **what a member reads as**, and **which stored spellings are
one member's zero** — and this section answers all three. Every other statement of
them, in this specification or in any surface built over it, is a consequence of
what is stated here rather than an independent rule.

Each value is built from a judged Entity State (`m-read-delivery` *Entity State
and the Page*). A published Typed or Wire value retains only the member state
and private write-origin state its lifecycle requires; it retains no Page, Root
View, raw provider row, unused witness, or other root's relationship view.

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

## Root View

A **Root View** is one root's
borrowed reachability and relationship-view union over a Page; it owns no payload
copy and does not outlive publication of that root.

Within a Root View, unequal witnesses are refused rather than chosen between:

- Unequal witnesses reached by the same root are a **Snapshot Projection Conflict**.
  Unequal witnesses reached only by separate roots coexist in the Page
  (`m-read-delivery`) and neither root conflicts. A conflicting Root View refuses
  with the logical Object Key and lowered coordinates, the member identities at
  every differing witness position, and the two occurrence positions (level and
  ordinal) where those witnesses physically occurred, but with no raw stored
  value. The selected witness pair, Object Key Entity, and differing-member
  sequence are canonical, so reversing row arrival or Include Path order cannot
  change those facts. The physical occurrence positions may change when provider
  rows are reordered.
- A concrete-Entity disagreement is a witness disagreement even where all
  member cells compare equal. It is reported with the same conflict family and
  an empty differing-member sequence where no shared member position names it.

Within **one Root View**, one logical key is **one node**:

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
- Resolution is **root-local**. Two result roots always publish distinct node
  objects even when they borrow the same page-owned Entity State. No node is
  interned beyond its Root View, and eager and streamed delivery therefore make
  the same identity promise. A caller that needs to know two roots reached one
  logical row compares their identities.
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

A `history` / `asOfRange` read returns one flat root sequence in Continuation
Order (`m-read-delivery`), each root pinned at its **edge pin** — the milestone's own from-instant
(`m-temporal-read`; for a half-open `[from, to)` interval the from-instant is the
one instant guaranteed to select exactly that milestone). A conformance oracle
may group that flat sequence by edge to state `then.graphs`; the grouping is a
presentation of the result, not a materialization boundary. Combining a history
read with `includes` is
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

- A **derived copy's view state IS its source's**. Under `m-edit`'s complement
  rule, an authored edit carries the relationship views the node it derives from
  carries: an included relationship answers the **same objects** on the copy,
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

## Round trips

A snapshot graph's statements are its delivery's (`m-read-delivery` *Round
trips*): at most `1 + L` statements for `L` distinct relationship hops. (For the
managed-object surface this round-trip observability rides the lazy query-backed
list, `m-op-list`; a snapshot read is **not** a query-backed list — the count is
pinned here instead, on the same golden statements.)

## What the suite pins down

Snapshot cases are **read**-shape deep-fetch cases (`m-case-format`): golden
statements, the assembled `then.graph`, and the declared `then.roundTrips`. A
**streamed** case is the same shape carrying `when.stream`, so the page
partition its statements spell out — the requested size, lookahead root
included, the seek each later page continues from, and the page that came back
short of it and so ended the delivery — is graded beside the delivered graph, and a **batch-size pair** grades the invariance the
page size promises. The
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
