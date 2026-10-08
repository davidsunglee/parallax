# m-read-delivery — Read Delivery

`m-read-delivery` turns a validated, adopted read into a judged, identity-first
**Page** of Entity States and delivers it — whole, or streamed one bounded Page
at a time — to the lifecycle **Publication** that turns Page states into that
lifecycle's values. It owns read planning and the reusable plan cache, effective
read-lock derivation, statement execution and Page assembly, stored-data
judgement, and whole-result and streamed delivery. Per the dependency graph it
depends on `m-deep-fetch` for the fetch it plans, `m-sql` for the statements it
executes, `m-document-codec` for stored-document judgement, `m-db-port` for the
calls it makes, `m-temporal-read` for the pins a fetch propagates, `m-read-lock`
and `m-opt-lock` for the lock each fetch takes, and `m-execution-lifecycle` for
the activities it opens. It names no lifecycle: snapshot graphs
(`m-snapshot-read`) and managed objects are alternative Publications over the
same delivery, and neither depends on the other.

Delivery runs inside the conditions `m-execution` establishes: the adopted Model
Edition, the resolved options and captured authority, the connection, and the
enclosing Read or Stream activity. Execution decides under which conditions a
read runs; delivery carries the read out under them, its database calls
included.

## Publication

A **Publication** is the lifecycle behavior delivery invokes to turn a Page's
judged states into published values. It is delivery-scoped: an eager read uses
one Publication once, while a stream reuses one across every Page it reads and
releases it when the delivery ends, on exhaustion, failure, or early close
alike. Delivery invokes it inside the enclosing Read or Stream activity and never
returns a Page for a lifecycle to publish later. A Publication states the
representation its read reports (`m-execution-lifecycle` *Read, write-batch, and
database-call events*) and the
Model Edition the read adopted, publishes one root's values on request, and
composes an eager result from a whole Page by publishing its roots. Origins an
execution retains for a Page's projections travel to the Publication by
reference; delivery neither interprets nor rebuilds them.

## Invalid stored data

Read delivery owns the one public stored-data issue vocabulary. Detecting modules
report facts in their own local terms; this module translates those facts without
re-judging them, and the Publication that publishes the affected result root
classifies it (`m-snapshot-read` *Classified roots*). The initial vocabulary is
closed:

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
| non-nullable top-level Entity Attribute absent or null in a document | unavailable |
| family tag matching no concrete subtype | unavailable |
| host-checked null primary key | unavailable |
| host-checked undecodable primary key | unavailable |

Classification never repairs, defaults, substitutes, or fabricates. A root is
hydrated only when every requested value can be produced by an already-normative
collapse; otherwise its data is unavailable.

Delivery trusts a native scalar Column exactly as the database provider
normalized it. Its installed SQL type and constraints are the admission boundary;
the host neither decodes it through the Neutral Wire Codec nor re-judges its type,
nullability, range, precision, or key status. A value that could exist only after
those database guarantees were bypassed is outside this read contract rather than
a source of a host-side stored-data issue. Entity Graph Construction consumes the
resulting already-judged Entity State and performs no second scalar judgment.

A **host-checked position** is one whose installed SQL type and constraints do not
by themselves establish the managed value. The set comprises an unconstrained
inheritance discriminator, a refinement not expressed by the installed SQL type
or constraint, a temporal end whose native infinity is admitted only as an open
upper bound, an encoded Column whose selected cell is canonical Wire, and every
document occurrence. Discriminators are checked while resolving the concrete
Entity. Encoded Columns and temporal ends are checked at their prepared Attribute
positions. Document-resident Entity members and Value Object occurrences are
located and classified by `m-document-codec`; no later scalar pass repeats that
classification.

Consequently, physical layouts need not classify a physically impossible carrier
the same way. For a non-nullable top-level Entity Attribute, an absent or JSON-null
Entity-document member under `Document` translates to
`stored-data-attribute-null` and makes hydration unavailable. The codec's local
required-member finding remains evidence for that route; public translation is
fixed by the logical Entity member. Under `Columns`, the database constraint owns
the same invariant and a provider-returned cell is trusted. For a non-object
Entity document, the member-local input returned by
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
delivery does not inspect a driver or host null sentinel. Both
occurrence placement arms pass that `LocatedMemberInput` to
`decodeLocatedMemberClassified` and emit one logical verdict before entering the
occurrence root. A requested occurrence descendant advances a Logical Judging
Cursor only after its carrier is classified; deeper wrong-kind or undecodable
stored state therefore returns a finding rather than escaping through strict
decoding. No cursor judges an unrequested sibling or descendant. Layout parity
fixes *where* the same requested logical member is judged without turning
classification into whole-subtree validation.

Judgment is once per requested logical structured value, not once per projection
that happened to carry it. A Publication first establishes the logical Entity
State claims a root reaches in one Page and compares every claim for one logical
key (`m-snapshot-read` *Root View*); only then is the selected Payload Witness
judged and decoded. Equal witnesses share that one judgment and its frozen
evidence. Value construction and Wire publication trust the resulting judged
Entity State and never invoke a second codec or scalar-admission pass over it.

A write's acquisition can read a row whole while deferring its occurrences
(`m-unit-work` *Retained starting rows*). It judges the row's Attributes as a
read projecting no occurrence judges them, and locates and tags each occurrence
— SQL null, present JSON null, or present content — without examining its
content. Judging those inputs later, from the retained row alone, applies exactly
the classification, construction, findings, and paths an ordinary read gives the
same stored occurrences; only their findings follow the Attributes' in time.

For each requested Value Object occurrence, that one codec traversal constructs
the final positional member row directly in canonical `MemberShape` order. Nested
`One` outputs are member rows and nested `Many` outputs are ordered tuples of
member rows as soon as their children have been interpreted. Conversion
translates codec absence and unavailability to the positional absence marker
while consuming the traversal; it does not first retain a reduced
mapping/list tree, detach a raw occurrence subtree, or walk decoded members a
second time. Dictionary consumers select a mapping/list construction over the same
classification rules and finding paths rather than a second decoder.

### Evidence a public issue carries

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

## Entity State and the Page

An **Entity State** is the page-owned, judged positional member row for one
logical Entity at one lowered coordinate, together with the findings produced by
that one judgment. It is independent of any result root and of any published
representation. Every root a Publication publishes that reaches the same logical
state in one Page reads that same Entity State by reference. Relationship
loadedness is not Entity State: it belongs to whatever publishes a root, because
two roots may have reached the same row through different requested paths. A
published value retains only the member state and private write-origin state its
lifecycle requires; it retains no Page, raw provider row, unused witness, or
other root's relationship view.

Each database row occurrence first makes an **identity claim** consisting of its
resolved concrete Entity, its family-normalized logical key, and the level and
row ordinal where it occurred. The logical key is **(entity family, primary key,
lowered as-of coordinate per declared axis)**, degrading to (family, primary
key) for a non-temporal entity. An unreadable host-checked primary key makes the
occurrence keyless: it shares with nothing and is classified at its own result
position. A native primary-key Column is trusted as provider-normalized identity
after the database type and constraint boundary.

The remainder of the occurrence is its exact **Payload Witness**: the resolved
concrete Entity plus the provider-normalized values selected for the Entity's
positional member row. Witness equality is exact positional structural equality,
including stored-document structure and presence. It is independent of arrival
order and Include Path order.

A Publication judging one root compares only the claims that root reaches
(`m-snapshot-read` *Root View*). The Page keeps exact witnesses beside each key, so an already-judged,
exactly equal state may be borrowed by another root without extending either
root's reachability: one root-local witness establishes one Entity State and is
decoded and judged once; equal witnesses establish the same Entity State and
reuse that one decode and its findings, and a later root with the same witness
may borrow it. Unequal witnesses reached only by separate roots coexist in the
Page.

A **Page** is the bounded, page-owned occurrence table produced by one eager read
or one streamed batch: occurrence headers and raw witnesses, root ordinals,
root-local relationship rows, the paging verdict, and the Entity States judged
so far. Eager delivery uses one Page for its whole database-ordered result. A
stream drops each Page before it reads the next. Payload judgement is
demand-driven: identity and correlation are judged as a row is converted, and a
member's payload is judged when a Publication first asks for the state that
holds it.

## Whole-result delivery

An eager read has one whole-result publication boundary. It reads and prepares
every result root before any published value, classified root, or
`root_published` observation crosses that boundary. A failure while judging or
publishing any later root — including a Publication's own refusal, such as a
Snapshot Projection Conflict (`m-snapshot-read`), or a lifecycle-state
construction failure — therefore publishes no root and emits no
root-publication event for the read. Successfully classified `InvalidData` is a
result root rather than such a failure: a checked eager result contains every
valid and invalid root in result order, and a default accessor reports every
invalid root from that same fully prepared sequence.

This atomicity is specific to eager delivery. A stream retains the root-local
publication boundary stated below: once one root has crossed it, a later root's
failure cannot recall the published prefix.

## Streamed delivery

A read may be delivered as a **stream** instead of as a whole
result. A stream is scope-bound and single-pass: it delivers roots one at a
time, forward only, and exposes no whole-result accessor. Delivery is the
distinction and representation is not, so a stream is a peer of the read it
streams in every representation that read has — one delivery mechanism, never a
format argument.

Each root has one atomic publication boundary. Its whole root-local graph and
classification are prepared before any value for that root reaches the consumer;
failure while preparing it publishes none of that root. Publication of one root does
not wait for a later root, however, so every failure preserves exactly the maximal
prefix already published. This applies whether the failure is a projection conflict,
a provider or continuation failure on a later page, invalid-data refusal in the
default view, or a lifecycle failure during publication. The checked view differs
only by publishing classified invalid data in band; both views judge the same root
sequence and retain the same prefix boundary.

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
conversion decoded. Every page captures, per root, what each Continuation
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
read carrying `includes` is the `snapshot-history-includes` feature
(`m-snapshot-read` *The whole-graph pin*), whose
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

- **A milestone set arrives one root at a time rather than grouped by
  milestone.** Both whole-result and streamed `history` / `asOfRange` reads use
  the Continuation Order and publish a flat root sequence; a whole-result caller
  receives the finite tuple together while a stream receives one root at a time.
  Each root stands at its **own** edge pin, and a milestone-set delivery answers
  the **empty** pin for
  itself, exactly as the whole result of the same query does, because a scan is
  not a pin. Exactly as the whole result does, it also retains no write evidence:
  every milestone root stands at a finite Transaction-Time edge and is read-only
  through every keyed verb.
- **A milestone root whose edge did not decode is published in band with no
  edge.** Every other milestone root stands at its own edge; this one has none to
  stand at. In both eager and streamed checked views it is an `InvalidData` at
  its database-arrival ordinal, carrying no edge, and delivery continues past it.
  A default view refuses it by the ordinary invalid-data rule. No history lane
  partitions before classification or gives this state a separate refusal.

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
are measured against where it ranked it, so the root is still admitted. For a direct
leading Column, a continuing page whose placement leaves NULLs ahead joins a
NULL-tail arm to its seekable non-NULL range, so even a stored `NULL` under a dropped
`NOT NULL` constraint is admitted. A coordinate missing after execution is a
violation of the `m-sql` / `m-db-port` contract rather than a stream state.

The two deliver the same roots at the same pins and in the same Continuation Order
whatever the query and whatever positive page size the delivery uses. A milestone-set
whole result is the finite form of the same flat delivery: it ranks the leading
authored term or primary key before the milestone edge and never regroups roots by
milestone. Across several keys, milestones may therefore interleave exactly as the
Continuation Order places them in both eager and streamed results.

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

That shared lock is nevertheless mandatory authority for every root a
participating locking page DID read, including its lookahead. On PostgreSQL a
continuing page whose root statement needs the two-arm NULL-tail form uses
`m-sql`'s outer physical-identity join: both arms remain unlocked, the one outer
base alias is joined on its complete physical key and locked with `for share`,
and the derived capture order and cap still choose the page. It is one statement,
not an unlocked selection followed by a resolving lock read, so the unit of work
may retain pessimistic write authority from the row it published.

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
| the current root's publication judgment and classification | the nodes and issues reachable from that root | `O(G_max)` | when that root is published |
| the current root's materialized value | that root's published graph and its cycle and aliasing closure | `O(G_max)` | when the delivery advances |

Two page-scoped terms sit inside the first layer rather than beside it. The page
decision holds one evaluated coordinate per root POSITION it kept — `O(B x T)` for
`T` Continuation Order terms, and nothing per node below a root — while it chooses
the continuation boundary. It releases those coordinates before graph assembly,
retaining only the boundary the delivery carries between two pages. And the
lookahead root a page read and did not keep is released at the page decision, before
anything below it is fetched, so it costs one root's raw result and nothing converted.

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

### The connection a delivery holds

Where an implementation owns connection lifetimes (`m-db-port`), a standalone
delivery may lease one connection **per page**. The lease begins inside that page's
Stream Batch before its first statement and ends after the page's converted result is
ready, before any root from it is published. Every root and relationship statement in
one page therefore observes one connection, while no connection is promised or held
between pages or while caller code processes a published root.

Entering a delivery still does deterministic work and reaches no database, so a
delivery opened and closed without reading acquires and releases nothing. A later page
may receive a different connection and a different per-statement database view; that
is the resource form of the per-page consistency contract above, not transparent
recovery from a connection lost while a page was running. Such a loss fails that page,
and the already-published prefix stands.

Capacity not occupied by the current page is available to independent work, including
an operation started inside the consuming loop. A pool with one slot can therefore
serve that work between page reads without waiting for the delivery's scope to close.

A **participating** delivery — one inside a transaction — acquires nothing at
all: it runs on the attempt's connection, and it is one more thing running on
that connection rather than a second borrower of it.

## Round trips

Delivery is `m-deep-fetch`'s contract observed through the Page: **at most
`1 + L` statements** for `L` distinct relationship hops, one statement per
non-empty level, empty parent-key levels issuing no child SQL. Constructing the
query is side-effect-free; the single explicit execution is the only moment the
database is touched.

When an Execution Lifecycle Provider accepts the Root Execution, the read
publishes one transient Read activity containing its Database Call children
(`m-execution-lifecycle`). The delivered result retains no trace or lifecycle
record. The portable `then.roundTrips` oracle and authored statements continue
to pin the `1 + L` ceiling independently of whether observation is installed.

## What the suite pins down

Delivery is graded through the read cases every Publication answers
(`m-case-format`): golden statements and `then.roundTrips` pin the `1 + L`
ceiling, a streamed case's statements spell out its page partition, and a
batch-size pair grades the invariance the page size promises.

| Case | What it proves |
|---|---|
| whole-result delivery | an unfiltered read of every stored row returns them all from one statement, inside one standalone Read that acquires its connection before the call and releases it after |
