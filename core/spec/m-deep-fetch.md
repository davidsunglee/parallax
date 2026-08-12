# m-deep-fetch — Deep Fetch

`m-deep-fetch` specifies how **deep fetch** eagerly populates an object graph
while **eliminating N+1** round trips. Per the dependency graph, `m-deep-fetch`
depends on `m-navigate` alone (deep fetch traverses relationships). The
**Includes** clause is `m-object-query`; the **SQL emission** is `m-sql`.
This module ties them to observable behavior. The two lifecycle result surfaces
— operation-backed lists (`m-op-list`) for the managed lifecycle, snapshot
graphs (`m-snapshot-read`) for the plain-value lifecycle — sit **above** deep
fetch and are populated by it; deep fetch itself is a pure per-level fetch
algorithm and reifies neither.

Every Include Path segment names a **relationship** between identity-bearing
entities; a **value-object segment is invalid** in the path grammar and MUST be
rejected. Value objects have no identity, no correlation columns, and no
deep-fetch statement — they materialize *with* their owning entity in the owner's
own read (`m-value-object`, "Materialization and navigation contract").

## Deep fetch: one query per non-empty relationship level

A query's `includes` clause resolves the root query first, then eagerly
fetches the canonical include-path set owned by `m-predicate`. That module owns
the path and segment grammar, canonical ordering, duplicate collapse, maximal-
path rule, and the distinction between broad and narrowed paths. This module
consumes that canonical set and owns its level planning. The normative guarantee:

> The number of SQL statements is **at most `1 + L`**, where `L` is the number
> of **distinct relationship hops** across all declared paths. A level whose
> parent-key set is empty issues **no** child SQL. A non-empty level issues
> **one** child statement — **never** one query per parent row.

Concretely, for each relationship level:

1. Gather the **distinct key values** of the already-fetched parent rows for that
   relationship's correlation column — of the root objects a path-root guard
   admits, when the level is a guarded path's first one.
2. If the gathered set is empty, issue **no** child query for that level; attach
   the empty/null relationship result and let downstream levels see an empty
   parent set.
3. Otherwise, issue **one** query against the child entity constrained by
   `fk in (…)` over those distinct keys.
4. Fan the returned child rows back to their parents **in memory**, attaching
   each child set under the relationship name (a list for a to-many relationship,
   a single object or null for a to-one).

Every retained path materializes its prefixes as levels. Thus the canonical
maximal path `{ segments: [{ rel: Order.items }, { rel:
OrderItem.statuses }] }` fetches both `items` and `statuses`; separately spelling
the exact `Order.items` prefix changes neither the canonical include set nor the
plan. Paths whose retained branches share a segment prefix fetch that shared hop
**once** — the hop is de-duplicated, so it counts as a single level.

### A level names its correlation members, not only their columns

Steps 1 and 4 correlate on an **Attribute**: the owner-side attribute the
relationship's join reads a key from, and — on a level that issues a child query
— the child-side attribute that key is matched against. A planned level **MUST**
carry both as modeled member identities, addressed at the positions the join
names them at, **alongside** whatever physical column each maps to.

Step 4 attaches on a **relationship**, and the same rule applies to it: a planned
level **MUST** carry the direction it attaches under as a modeled relationship
identity, alongside the attach key — the relationship name, or the derived
narrowed-view key of a narrowed polymorphic hop. The attach key stays, because it
is the key the graph presents the view under; what the identity adds is again the
inverse direction, so a consumer attaching the level names the declared direction
instead of matching the derived key back against the owner's relationship names.

The physical column stays: a level's own child statement is emitted against
columns, and the keys it gathers are column values. What the member identity adds
is the *inverse* direction. A consumer that has already turned a parent row into
its own materialized form holds that form keyed by member, not by column, so
without the identity it would have to invert a physical column back to a member
to gather the level's keys — re-deriving a mapping the model already fixes, in a
layer that otherwise never needs to know one. Carrying the identity is what lets
a result surface **stop reaching for a row once that row has been converted**,
and it is what keeps column-to-member inversion confined to whichever layer
legitimately owns it.

The identities are a property of the planned level alone. A level's emitted
statement, its gathered key set, and its dedup identity are fixed by the hop's
columns and its authored narrow, so each stays exactly what the rules above
state whether or not a consumer reads the identities.

### The 1 → N → N proof

The canonical witness is a two-hop fan-out: a root with `N` children, each child
with `N` grandchildren. Naively this is `1 + N + N` statements; with deep fetch
it is exactly **3** — root, one `IN` query for all children, one `IN` query for
all grandchildren. The compatibility harness asserts the statement count equals
the declared `roundTrips` and that the assembled graph equals the expected
graph, so the N+1-elimination claim is verified **automatically**, not by
inspection.

### Ordered to-many children

A to-many relationship MAY declare an `orderBy` — a non-empty list of
`{ attribute, direction?, nulls? }` keys (`direction ∈ {asc, desc}`, default
`asc`; `nulls ∈ {first, last}`, default `last`). When it
does, the per-level child query for that relationship **MUST** emit `ORDER BY`
over the declared keys, in declared sequence, each rendered with its declared
direction, and the in-memory-assembled to-many list **MUST** preserve that
order. A relationship with no declared `orderBy` leaves child order
**unspecified** — the database's natural order, which callers MUST NOT rely on.

Ordering is a property of the relationship, not of the query: every deep fetch
that materializes the relationship emits the same `ORDER BY`. Keys are evaluated
left to right — the first key is primary, later keys break ties — so a multi-key
`orderBy` with mixed directions
(`[{ attribute: score, direction: desc }, { attribute: name }]`) sorts by
`score` descending and breaks ties by `name` ascending.

A `NULL` in an `orderBy` key sorts where the key's **Null Placement** asks, and
an omitted placement sorts it **last** on that key in both `asc` and `desc` —
the canonical, dialect-independent default. Placement is authored per key and is
independent of direction, so the four direction/placement pairs are four
distinct observable orders. The dialects' native `NULL` placement differs, so
the golden SQL achieves the requested placement per dialect (the `m-dialect`
seam), but the observable order is the same everywhere: under `last`, non-`NULL`
values in the declared direction, then `NULL`s; under `first`, `NULL`s, then
the non-`NULL` values in the declared direction.

## Polymorphic and narrowed deep fetch

A deep-fetch hop whose relationship target is a **polymorphic position**
(`m-inheritance` — an abstract root or abstract subtype) eagerly fetches concrete
instances across the family. `m-predicate` owns the segment's optional `narrow`
grammar; this planner resolves that shared Subtype Selection and fetches only the
resolved subset of the relationship target. A selection escaping that target is
`narrow-outside-relationship-target` (`m-navigate`).

**A narrowed hop populates a distinct narrowed relationship view**, keyed by a
**derived** name rather than the ordinary relationship name:

```text
<relationshipName>[<ConcreteSubtype>,<ConcreteSubtype>]
```

- the **local** relationship name (never the qualified `Class.rel` ref);
- the **effective concrete-subtype set**, in the family's canonical **alphabetical
  order** (`m-inheritance`; never abstract names, never a `tagValue`), rendered
  with each concrete's family variant spelling and comma-joined with **no
  spaces**. A family-unique local name stays bare; duplicate local concrete names
  use their canonical qualified Entity spellings.

So `Person.pets` narrowed to `[Pet]` (or, equivalently, `[Cat, Dog]`) both derive
`pets[Cat,Dog]`. A narrowed include populates that view **only**; it does **not**
mark the broad relationship loaded, and a **broad** hop keeps the ordinary
relationship key. The polymorphic view's child objects additionally carry
`familyVariant` (the concrete subtype name), materialized from the tag map exactly
as an abstract-target flat read (`m-case-format`); a single-concrete narrowed view
carries none (the caller fetched a known variant).

**Dedup identity is the triple `(relationship hop, whether a narrow was
authored, effective concrete set)`**, not the relationship alone. Deduplication
of equivalent spellings applies **between two narrowed hops**: two paths whose
`segments` both author a narrow over the same relationship, resolving to the
**same** effective set, deduplicate to **one** hop (one statement) — this is what
makes the equivalent spellings `[Pet]` and `[Cat, Dog]` converge. Two hops
narrowed to **different** sets (`pets[Dog]` and `pets[Cat]`) stay **distinct**.

A **broad** hop and **any** authored narrow over the same relationship are
**distinct** hops — including a **redundant** narrow, one whose `to` resolves to
the relationship target's entire effective concrete set. A redundant narrow
returns exactly the rows the broad hop returns, yet the two populate **different**
views (`pets` and `pets[Cat,Dog]`), because a segment's view key is derived from
whether a narrow was **authored**, independent of what that narrow resolves to.
Identity therefore cannot key on the resolved set alone: doing so would collapse
the redundant pair into one hop and leave one of the two views unpopulated.

Each distinct hop counts toward `L`, so `1 + L` is preserved with narrowed hops
counting as distinct.

### Path-root guards

The optional path-root `narrow` owned by `m-predicate` **guards which queried
objects the path starts from**. It is the deliberate opposite of a segment
narrow, and the contrast is the whole of its planning semantics:

| | root `narrow` | segment `narrow` |
|---|---|---|
| Narrows | the hop's **source** objects | the hop's **target** subtypes |
| View key | **none** — the path fills the view its unguarded spelling would | a **distinct** `<rel>[<Concrete>,<Concrete>]` view |
| Hop identity | the **resolved source set** | whether a narrow was **authored**, plus the resolved set |

A root guard therefore **creates no view**. `include(Dog.owner, Cat.owner)` —
one relationship `Animal.owner`, guarded to two disjoint source sets — populates
the **ordinary** `owner` view on Dogs and on Cats; there is no `owner[Dog]` view
and no unioning of the two hops. A root object **outside** every authored guard
is never attached at all, which is observably different from being attached
empty: the closed-world graph distinguishes "this object has no such related
row" from "this object never participated in that path".

Because identity at the root keys on the **resolved source set**, the
distinctness rule *falls out* rather than being asserted separately:

| Relation between two guards | Example | Hops |
|---|---|---|
| equal / equivalent | `to: [Pet]` and `to: [Cat, Dog]` over the same family | **1** — they deduplicate |
| disjoint | `to: [Dog]` and `to: [Cat]` | 2 — neither fills anything the other does |
| overlapping | `to: [Dog, WildBoar]` and `to: [Cat, Dog]` | 2 — the shared roots' view is filled twice, identically |
| containment (including broad) | no guard, and `to: [Dog]` | 2 — the guarded hop fetches nothing new |

Every **proper** guard resolves to a strict subset of the queried position, so
its key differs from the broad path's automatically; only a guard admitting
**every** queried object collapses onto broad, and there every observable agrees
(same rows, same view, same objects), so collapsing is not a special case but the
absence of a difference.

The overlapping row compares two sibling selections. It does not relax Subtype
Selection's pairwise-disjointness rule inside either value: `[Pet, Dog]` is
invalid because those two alternatives overlap within one selection, while the
two separately authored guards in the table remain legal.

The last three rows cost one statement more than a set-unioning planner would
need. That cost is **deliberate**: it keeps `roundTrips` **compositional** — an
authored path's statement cost does not depend on which other paths were authored
beside it — and it keeps each hop's branch provenance explicit, so a path
continuing past a guarded hop knows which parents it descends from. In the
overlapping and containment rows the extra work is invisible in the assembled
graph, so the only observable is the statement count.

The two positions **compose** on one path, keeping their own semantics: a guarded
root continuing through a narrowed segment fills the segment's derived view key on
the guarded branch's objects alone, and a segment beneath a guarded hop needs no
guard of its own because its parents are already the guarded ones.

**One statement per hop, both strategies.** Under `table-per-hierarchy` a
polymorphic hop is one shared-table `IN`-keyed read with the effective set's tag
predicate appended (`… where t0.owner_id in (?, …) and t0.kind in (?, …)`). Under
`table-per-concrete-subtype` a polymorphic hop is **one `union all` statement**
(`m-sql`) whose branches — one per effective concrete subtype in canonical
alphabetical order — share the **same** parent-id `IN` list, so the hop stays a
**single** statement and
`1 + L` holds verbatim; the per-branch as-of binds propagate exactly as
`m-navigate` specifies. Splitting a polymorphic hop into one statement per branch is
**not** permitted — it would make the statement count strategy- and
narrowing-dependent and weaken every `roundTrips` assertion.

## Simplified `IN` vs. temp-table threshold

The per-level child query uses a **simplified `IN (…)` list** of the gathered
parent keys. This is correct and optimal for the parent-set sizes the round-1
suite exercises. Reladomo switches to a **temp-table join** once the parent set
exceeds a threshold (`MAX_SIMPLIFIED_IN`), because a multi-thousand-element `IN`
list (and per-dialect `IN`-clause limits) degrades.

> **Temp-table deep fetch is declared here but deferred to a fast-follow.** The
> contract is: when the gathered parent-key count exceeds the dialect's
> threshold, the implementation **MAY** materialize the keys into a session
> temp table and **join** against it instead of inlining an `IN` list — while
> preserving the **same one-statement-per-level round-trip count** and the same
> assembled graph. The threshold value and the temp-table DDL are `m-dialect`
> concerns. Round 1 specifies and tests only the simplified `IN` form.

## As-of propagation

A deep fetch as of an instant yields a **point-in-time-consistent object graph**.
The per-hop as-of propagation rule (matched by axis, defaulting unpinned axes to
latest) is owned by `m-navigate` and applies inside each per-level child query.

## Deferred relationship load

A **deferred relationship load** resolves declared relationship paths for an
**ad-hoc set of already-materialized managed objects** — the
query-many/navigate-few pattern ("load `customer` for these 10 of my 1000
orders") without an up-front include and without N+1. It is the same machinery
as deep fetch, applied after materialization (Reladomo's ad-hoc list deep fetch
is the prior art). The semantic is **one**, and it is this module's; only the
**trigger** is per-language idiom:

- an **explicit load call** over the object set (always available);
- **transparent relationship access** on a managed object, permitted in
  synchronous languages (where property access can resolve) — the access *is*
  the trigger, the semantics are identical;
- eager `includes` at query time remain the third form of the same load.

The normative rules, whatever the trigger:

- A deferred load resolves **only through the live unit of work** that owns the
  objects — the `m-unit-work` rules apply, including the flush of dependent
  buffered writes before the read. On an object whose owning scope has ended (a
  detached object, `m-detach`) it raises a **defined Parallax Error**; it never
  opens a transaction implicitly.
- It propagates **each source object's pinned as-of coordinates** (`m-navigate`,
  applied at the object level), batching sources **per coordinate group**: one
  child statement per relationship level per distinct coordinate group. The
  common all-latest set collapses to exactly the deep-fetch form — one statement
  per level.
- Round trips stay query-determined: a deferred load is an explicit resolution
  point whose statement count follows the same one-statement-per-non-empty-level
  contract, so scenario cases can declare it.

A plain-value graph (`m-snapshot-read`) has **no trigger at all**: a snapshot
graph is closed-world and never issues SQL after materialization.

## What the harness verifies

For each deep-fetch case the compatibility harness (`m-case-format`) asserts, in
addition to the standard layers: the golden SQL statement count equals the
declared `then.roundTrips`; each non-empty child level executes keyed by the parents
gathered from the previous level (with the authored `IN` binds matching the
gathered keys); empty parent-key levels execute no child SQL; and the
in-memory-assembled object graph equals the case's `then.graph`. Additionally,
for each to-many level whose relationship declares `orderBy`, the harness derives
the expected child order from the declared keys/directions (an independent oracle)
and asserts the rows the golden SQL returned obey it, so a dropped or wrong
`ORDER BY` fails the case.
