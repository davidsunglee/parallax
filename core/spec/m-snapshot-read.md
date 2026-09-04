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

### Evidence a public issue carries

Every issue names the value that was judged and the place it was found. The
**rejected stored value** is the provider-normalized logical value the detecting
module judged, captured where that verdict was formed — before any collapse
reduces it — and translated once on the way out:

| Stored shape | Evidence |
|---|---|
| immutable scalar | preserved as it was judged |
| array | an immutable sequence |
| object | a detached read-only mapping |
| stored SQL or JSON null | the ordinary null value |
| a member genuinely absent from a traversable object | the missing-value marker |
| wrong-kind, undecodable, or unknown family tag | the actual rejected value |

The missing-value marker is distinct from a stored null and from every value a
member could hold. A wrong-kind parent container yields one causal issue at that
parent's own place, and its declared descendants acquire none: the container is
what contradicts the model, and no stored state was ever seen for what it would
have held.

The **place** is the entity-relative logical path of that occurrence, keeping
declared member names distinct from array positions. It is empty where the
issue's member already locates the occurrence exactly — a direct Entity
Attribute under either Storage Layout, an unresolved family tag, and a whole
stored document read in a kind it cannot be read as — and otherwise names the
member sequence, with an array position for each element step, that reaches the
occurrence from the Entity.

The value and the place are part of an issue's identity: repeated reach to one
occurrence collapses within a root as before, while the same code at another
place, or a different rejected value at one place, remains a distinct diagnosis.
Comparison of structured evidence is structural and insensitive to object member
order.

The rejected value is diagnosis and grants nothing. It is reachable by explicitly
asking an issue for it, and is excluded from default renderings, exception
messages, lifecycle events, SQL emissions, default logging, and automatic
formatting. The place carries no stored state and is outside that exclusion: it
locates the diagnosis exactly as the issue's other locators do. The value never
becomes a cursor, a managed value, a predicate literal, a repair token, or a
storage capability, and passing it to an ordinary write is an ordinary validated
write. The lower wire-codec rejection reason stays unpublished: the
issue codes above remain the whole public classification.

A rejected value is retained deliberately, so exactly one frozen copy of it
survives: it is frozen where it is judged and shared by reference from that seam
to every seam that reports it. The count is over the copies a delivery retains
rather than over how many times the freezing walk runs; what makes a translation
per seam, or a copy per report, a defect rather than an implementation choice
(*What a delivery costs*) is that each leaves a further copy alive for as long as
the diagnosis is. A copy that exists only inside the conversion of the row that
judged it, and is gone when that conversion returns, retains nothing and is
bounded by that page's own converted result. Repeated reach to one occurrence is
one such report: a read that reaches it again retains the value it already froze
rather than an equal second one.

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
delivery derives rather than an Object Query clause. It is composed the same way
for every read — the query's authored Sort Keys, in the precedence the query
declares, then the primary key **ascending**, and then, for a milestone-set
(`history` / `asOfRange`) read, the **milestone edge** ascending — each appended
term omitted where a Sort Key already named it. Every term is an ordinary Sort
Key resolved at the query's own result position (`m-object-query`), so an
authored one is carried exactly as authored, absent direction and Null Placement
included, and the appended key is one Attribute (`m-metamodel` admits no
composite primary key).

The primary key alone is total for a single-instant read, where one key stands
behind one result root. A milestone-set read returns one root per milestone, so
several roots share one key and the key no longer separates them; what does is
the milestone each stands at, which is the family's own As-Of Axis starts in
canonical axis rank — Valid Time before Transaction Time. A milestone's edge is
unique within its key by construction (`m-temporal-read`: a from-instant lies
inside its own half-open interval, and two milestones of one key do not overlap
on every axis at once), so the composed order is total for every read shape and
no two roots tie in it — over storage the model describes. Where storage has lost
a constraint the order rests on, two roots may stand at ONE evaluated coordinate,
and *Ending a delivery at a tie* below settles what a delivery does about it. Every declared axis contributes, whether the query
scanned it or pinned it: a pin selects one coordinate on that axis and leaves
the other free to vary across the milestones the scan returns.

A delivery advances on **coordinates the database evaluated**, never on anything
materialization decoded. Every page captures, per root, what each Continuation
Order term's own ordering expression produced, and a page after the first carries
the query's own predicate conjoined with a **seek** admitting exactly the roots the
Continuation Order places after the one the previous page delivered last. Which
comparisons that seek expands into is `m-sql`'s (*Continuation coordinates*),
because it cannot be settled without knowing where the dialect placed a `NULL` in
the ordering clause that was emitted. What is settled here is the ORDER those
comparisons are measured against, and the rule that the position a page resumes
from is the coordinate of the last root that page **kept**.

"Exactly the roots" has one stated exception, and it is bounded by storage rather
than by data. Where the LEADING Continuation Order term is stored in a **Column** the
model declares **non-nullable** and that Column holds a stored `NULL` — which
conforming storage cannot produce, and which the declared model therefore does not
describe — the leading range `m-sql` hoists for the planner may place that root
outside the seek, and the delivery does not deliver it. That is a deliberate trade:
emitting a seek that admits it costs the leading index range on every page of every
delivery, and the value it would recover is a row a `NOT NULL` constraint was supposed
to make impossible. It is the same class `m-metamodel` already leaves to storage — a
duplicate or absent physical key — and it is the ONLY invalid stored data a delivery
may skip.

The exception stops there, at the Column. A leading term stored at a **Document Path**
hoists no range at all, because the ways its extraction reads `NULL` — a missing
member, an explicit JSON null, a parent document of the wrong kind — are ordinary
invalid stored data this specification guarantees a delivery publishes, not storage
outside what the model describes. Every other term of the order is measured only by
the branches, which follow the placement the clause emitted, so nothing below the
leading position skips a root either.

A coordinate is physical and carries no authority. It is not decoded, revalidated,
admitted as a managed value, published as a result, or turned back into one by any
public constructor; it is compared only by its own equality, and a diagnostic copy
of one is inert. A rejected stored value and a coordinate stay separate in both
directions: a rejected value is evidence and never becomes a cursor, and a
coordinate is pagination state and never becomes evidence. They may describe the
same stored cell and still differ — a document extraction whose cast a codec
rejects yields evidence of the rejected value while the coordinate carries what the
`ORDER BY` expression evaluated.

Delivery is bounded by a **page size** counting root positions. It never bounds
included relationship rows, and over storage the model describes it is a performance
dial and nothing else: changing it changes neither the order roots arrive in, nor
which roots arrive, nor the members, loadedness, identity, or issues any of them
carries. The stated exception above is where it stops being one, because only a
CONTINUING page carries a seek: a root the hoisted leading range excludes arrives in a
first page large enough to reach it and is skipped once a smaller page puts a boundary
in front of it. That is the same skip, observed through the dial, rather than a second
one.

Each page is an ordinary read of a bounded root query, so `m-deep-fetch`'s
**`1 + L` ceiling applies once per page** and a page's child levels are the same
`IN (gathered keys)` lookups any read issues.

A page reads one root MORE than it may deliver — a **lookahead** root, read
complete, used only to decide the page, and then dropped. A page that came back
short of what it asked for proves exhaustion; one that came back full proves
another page follows. Exhaustion therefore costs no terminal statement of its own,
not even where the result fills its final page exactly: the root-statement count is
`1` where no root is delivered and `ceil(N / B)` for `N` roots at page size `B`.

The lookahead root is **not** delivered by the page that read it. It is not
deep-fetched, converted, classified, or published there, and it is never paired
with children another page fetched: the next page's own root statement returns it
again, because that page resumes from the last root the page before it KEPT. The
`1 + L` ceiling is unaffected — a page gathers keys from the roots it kept.

A declared `limit` is a hard database-read and locking boundary rather than a
filter applied afterwards, so it caps the lookahead too: where no more than a page
is left of it, the final page asks for exactly that remainder and reads no root the
limit excludes. That page's result proves nothing about what follows it and needs
to prove nothing — the limit is already delivered in full. The consequence is
deliberate: a tie between the last included root and the first excluded one goes
undetected there, and no later seek exists that could skip it.

Delivery adds no capability and removes none. A query a whole-result read may not
execute is equally unexecutable streamed, and the reverse holds too: a `history`
read carrying `includes` is the `snapshot-history-includes` feature above, whose
availability is the target's own claim, and whichever way that claim answers it
answers identically — and at the same point — for a streamed read and a
whole-result one.

### Where a stream diverges from a whole-result read

A stream answers the same query over the same data, and four things about its
answer differ. All four follow from the two facts that make a delivery a
delivery, and neither fact is representation-specific, so every divergence
applies identically to every representation. Invalid stored data is not among
them: it ends no checked delivery, which is stated below the four.

**Because a stream publishes one root at a time**, it never holds two roots'
results together, and three divergences follow:

- **Sharing narrows to root-local.** A row two result roots both reach is one
  node per root, where a whole-result read may answer one node for both. The
  promise is root-local either way, so what changes is what a caller can observe
  beyond it rather than what they may rely on. Stated in full under *Graph-local
  identity resolution* above, because the promise governs both.
- **A milestone set arrives one root at a time rather than grouped by
  milestone.** A whole-result `history` / `asOfRange` read answers one graph per
  milestone, in chronological edge order, with every root of one milestone
  together. A stream has no graphs to group into: each root stands at its **own**
  edge pin — the same pin the whole-result read gives the graph that root would
  have belonged to — and a milestone-set delivery answers the **empty** pin for
  itself, exactly as the whole result of the same query does, because a scan is
  not a pin. Exactly as the whole result does, it also retains no write evidence:
  every milestone root stands at a finite Transaction-Time edge and is read-only
  through every keyed verb.
- **A milestone root whose edge did not decode is published at the page's own
  pin.** Every other milestone root stands at its own edge; this one has none to
  stand at, and the delivery continues past it. A whole-result milestone read
  refuses the whole read instead, because it must decode an edge before it can
  partition its rows at all — a refusal a per-root publication has no need of.

**Because a stream derives a Continuation Order the query did not declare**, it
answers in a total order where a whole-result read may answer in none, and one
more follows:

- **An unordered `limit` becomes specified.** `m-object-query` makes an
  unordered `limit` a cap rather than pagination, returning an unspecified
  matching subset. A stream orders by the Continuation Order before capping, so
  the same query with the same `limit` returns the Continuation Order's own
  first `n` roots. The stream is strictly more specified — nothing a
  whole-result read promised is broken — but the two answer differently, and
  that is a property of the delivery rather than of the query.

Invalid stored data ends **no** checked delivery. Every root the database placed in
the Continuation Order has an evaluated coordinate by construction, whatever its
stored data turned out to be, so a root whose sort key, primary key, or milestone
edge contradicts the model is published exactly as a whole-result read publishes it
— in band where the reading surface delivers classified roots in band, as a refusal
where it refuses them — and the delivery carries on. An unknown discriminator, an
undecodable scalar, a wrong-kind document, and a missing member all reach the caller
this way. Where such a value leaves an ordering term evaluating to `NULL` — which a
missing member, a JSON null, and a wrong-kind parent all do to a document-resident
term — the emitted clause still ranks that `NULL` somewhere, and the seek's branches
are measured against where it ranked it, so the root is still admitted. The one value
that is not is the stored `NULL` in a non-nullable leading **Column** named above,
which the hoisted leading range may exclude. A coordinate missing after execution is a
violation of the `m-sql` / `m-db-port` contract rather than a stream state.

The two deliver the same roots at the same pins whatever the query — save the one
root the stated exception above lets a continuing page's hoisted range exclude, which
a whole-result read has no seek to exclude with — and they deliver them in the same
sequence wherever their two orders agree. Over **one**
key's own history they always do: the Continuation Order there is the edge rank,
which is what the whole-result read groups by. Across several keys they generally
do not, and that is true of a read declaring no `orderBy` as much as of one that
authors a Sort Key — the whole-result read ranks by milestone across every key and
puts every root of one milestone together, while the stream ranks by the leading
term, the primary key or an authored member, before it reaches the edge. A key
whose milestones interleave with another key's is therefore delivered in one
sequence eagerly and another streamed.

### Ending a delivery at a tie

Two roots the page statement evaluated to ONE Continuation Order coordinate end the
delivery. There is no fallback: a delivery never knowingly skips a root, delivers one
twice, loops, or continues through an identical coordinate, and the strict seek a
later page would carry steps over the twin of the root it resumed from.

A tie is storage the model does not describe — the composed order is total over
storage that keeps the constraints it rests on — so this is a diagnosis of the data
rather than of the query or the caller. A delivery reaching one:

- **publishes the maximal strictly ordered prefix** of the page it was found in, in
  order, and every root before that page exactly as it published them;
- **touches neither tied root**: neither is deep-fetched, converted, classified, or
  published, so the stored-data issues they might have carried never compete with the
  refusal for precedence;
- then **refuses**, naming the Continuation Order it was measured against, an inert
  copy of the coordinate both roots stood at, and the ordinal — counted from the
  start of the delivery — of the first root it could not deliver.

Refusal follows publication in that order for both views. A throwing view's refusal
of invalid stored data is raised while the prefix is being published, so it arrives
FIRST where both apply; the tie refusal is raised only once the page's kept roots
have all been delivered. Sameness is the coordinate's own rule, over the carriers a
provider produced and normalized once at capture, and is deliberately narrow: under
storage that has lost a constraint a database may treat carriers as tied where this
comparison does not, and detecting that exhaustively is not attempted.

Because the scan covers the LOOKAHEAD root, a tie spanning a page boundary is caught
before a seek could step over it. The one boundary it does not cover is a declared
`limit`'s: the final page that limit caps reads no excluded root, so a tie between
the last included root and the first excluded one goes undetected, and no later seek
exists that could skip it.

### Stability under concurrent writing

A delivery is stable **per page**, and that is the whole of what it promises.
Each page is an ordinary read taking its own view of the data, and nothing
between two pages holds the roots a later one will reach — so a root that
changed after the page that would have delivered it was read is a change the
delivery never sees. A unit of work open around the delivery does not widen
this by itself: what a boundary adds is whatever its Isolation Level adds
(`m-db-port`), and at an ordinary per-statement default that is nothing, leaving
a participating delivery exactly as skewed as a standalone one. A participating
delivery INHERITS the level its transaction was opened at rather than requesting
one of its own — a standalone delivery has no boundary to name a level for, so
there is no isolation option on one — and a transaction opened at Repeatable
Read therefore carries that level's guarantee across every page it pages: the
nonrepeatable read the level forbids is forbidden for a delivery's rows exactly
as it is for a find's. Phantoms are permitted at that level, so what a caller
still does not get is one coherent predicate result across the pages. A shared
row lock closes no part of it either — it holds roots already read and says
nothing about roots not yet reached, and locking every root of an unbounded
delivery is a different problem. This contract states per-page stability; what
a level adds on top of it is `m-db-port`'s.

What per-page stability admits is stated against the delivery's **position** —
the Continuation Order coordinate the last delivered root stood at, which is
what the next page seeks from:

| Concurrent change | Effect on the delivery |
|---|---|
| a root inserted behind the position | never delivered — it did not exist when the delivery passed there |
| a root inserted ahead of the position | delivered |
| a root deleted ahead of the position | never delivered |
| a root moved from ahead of the position to behind it | skipped entirely |
| a root moved from behind the position to ahead of it | delivered twice |

**The last two require a Continuation Order term a write can move, so they are
reachable only where the query authored one.** With no authored `orderBy` the
Continuation Order is the primary key, followed for a milestone-set read by the
milestone edge. No write relocates either coordinate: a keyed write addresses a
row by its primary key rather than changing it, and a milestone's edge is the
start instant its own interval opened at, which a later write closes or
supersedes — writing a new milestone at a new start — rather than moving. Nothing
already delivered can cross the position, so neither a skip nor a duplicate is
possible at all. The hazard is a property of what the query ordered by, not of
streaming.

**The concurrent writer may be the reader.** A delivery consumed by a loop that
writes the member its query ordered by moves its own roots across its own
position, which is the two rows above with one caller on both sides of them. The
loop is under the same rule everything else is, and the same escape: order by
nothing, and every term the order is then composed of is one no write moves.

**Nothing de-duplicates across a delivery.** Recognizing a root already
delivered means retaining every delivered root's identity, which is `O(N)` in
the result — the whole-result retention a streamed delivery exists to remove —
and it would still repair no skip, because a skipped root is one nothing ever
saw.

**Delivery is per attempt.** A boundary that re-executes its closure after a
retriable failure re-executes what the closure did, and a root already delivered
cannot be recalled: the re-execution opens a **fresh** delivery, which starts
from the beginning and delivers those roots again. Nothing is buffered until
commit. An effect a consumer performs per root therefore owes exactly the
retry-safety every other effect performed inside such a closure owes.

### What a delivery costs

A streamed read exists for one guarantee about memory, and it is the guarantee
rather than the mechanism that is normative: **the implementation-owned working
set of a delivery is independent of the number of roots the query matches.**
Writing `B` for the page size, `P_B` for one page's own converted result, `G_max`
for the largest single root's published graph, and `N` for the whole result, the
bound is `O(P_B + G_max)` and contains no term in `N`.

Three layers, each separately bounded and each released at a stated point:

| Layer | Holds | Bound | Released |
|---|---|---|---|
| the page's converted result | every projection for one page's roots and their relationship fan-out | `O(P_B)` | after that page's last root is published |
| the current root's merge and classification | the merged nodes and issues reachable from that root | `O(G_max)` | when that root is published |
| the current root's materialized value | that root's published graph and its cycle and aliasing closure | `O(G_max)` | when the delivery advances |

Two page-scoped terms sit inside the first layer rather than beside it. A page holds
one evaluated coordinate per root POSITION it kept — `O(B x T)` for `T` Continuation
Order terms, and nothing per node below a root — plus the one the delivery carries
between two pages. And the lookahead root a page read and did not keep is released at
the page decision, before anything below it is fetched, so it costs one root's raw
result and nothing converted.

The bound is deliberately **not** `O(B)`. `P_B` is a page's whole converted
result rather than its root count, so a page of roots each carrying a large
relationship fan-out is priced at what it carries; and `G_max` is one root's own
graph, so a single root with a hundred thousand children dominates both terms at
every page size. The page size is the dial over the first term alone, and it
trades against round trips in the ordinary way: a smaller page holds less and
costs more statements.

Three things are **excluded**, and naming them is part of the contract, because a
bound that excluded nothing would be a claim about the consumer's program rather
than about the implementation:

- **Values the consumer retains.** A consumer that keeps every root it was handed
  has reproduced the whole-result retention on purpose, and nothing is expected
  to prevent it. This is the same fact *Nothing de-duplicates across a delivery*
  states from the other side: the implementation retains no delivered root, so
  the only thing that can be holding one is the caller.
- **Writes a surrounding unit of work has buffered, and the observations they
  captured.** These are the unit of work's, not the delivery's. A participating
  delivery does bound them in one respect — a page forces the buffer out before
  it reads, so a consuming loop that writes each root holds a page's worth of
  writes rather than a result's — but what they cost is `m-unit-work`'s subject
  and grows with what the loop wrote.
- **State the database holds for the delivery.** Server-side transaction state,
  cursors, and whatever a driver keeps for a result set are outside this bound
  entirely. An implementation whose port materialized a whole result set before
  answering the first page would satisfy every clause above and still allocate
  `O(N)`; what stops that is the paging itself — each page is a separate bounded
  query — rather than anything this section can state about the driver.

Nothing here fixes an absolute figure. Like `m-perf-bench`'s numeric targets, the
constants are per-language; what is portable is that the three layers are bounded
as above, that the three exclusions are the only ones, and that a language target
can demonstrate the independence from `N` rather than assert it.

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
