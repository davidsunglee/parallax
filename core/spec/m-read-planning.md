# m-read-planning — Read Planning

`m-read-planning` owns pure planning of flat Entity reads and included object
graphs, including the target and temporal-coverage reads required by writes.
It turns accepted query meaning into complete read plans for `m-sql` to lower.
Planning resolves the effective inheritance position, temporal visibility, and
requested projection; include planning additionally determines relationship
correlations and fetch steps that eliminate N+1 Database Calls.

Write execution decides which target or predecessor evidence it needs. Read
planning constructs the reads that obtain that evidence; it does not decide
write authority, evidence sufficiency, or temporal state transformations.

The module depends on `m-object-query` (the validated query and Includes clause),
`m-predicate` (elaborated selection products), `m-wire` (managed keys already
produced at ingress), `m-relationship` (compiled relationship directions),
`m-navigate` (temporal
visibility and per-hop propagation), and `m-inheritance` (effective positions).
SQL emission belongs to `m-sql`; execution, paging execution, and Page assembly
belong to `m-read-delivery`. Planning performs no database work
and publishes no lifecycle objects. Snapshot publication (`m-snapshot-read`)
consumes its plans through read delivery.

## Include planning and deep fetch

Every Include Path segment names a **relationship** between identity-bearing
entities; a **value-object segment is invalid** in the path grammar and MUST be
rejected. Value objects have no identity, no correlation columns, and no
deep-fetch statement — they materialize *with* their owning entity in the owner's
own read (`m-value-object`, "Materialization and navigation contract").

## Deep fetch: one query per non-empty relationship level

A query's `includes` clause resolves the root query first, then eagerly
fetches the canonical include-path set owned by `m-object-query`. That module owns
the path and segment grammar, canonical ordering, duplicate collapse, maximal-
path rule, and the distinction between broad and narrowed paths. This module
consumes that canonical set and owns its level planning. The normative guarantee:

> The number of SQL statements is **at most `1 + L`**, where `L` is the number
> of **distinct relationship hops** across all declared paths. A level whose
> parent-key set is empty or whose target position has no concrete subtype
> issues **no** child SQL. Neither does a **back-reference level**, a to-one
> level that is the reverse direction of the hop it arrived on: its target is
> the already-fetched object that hop started from, attached without a read.
> Every other level issues **one** child statement — **never** one query per
> parent row.

Concretely, for each relationship level:

1. Gather the **distinct key values** of the already-fetched parent rows for that
   relationship's correlation column — of the root objects a path-root guard
   admits, when the level is a guarded path's first one.
2. If the gathered set is empty, or the level's target position resolves to no
   concrete subtype (`m-inheritance` *Positions with no composed concrete
   subtype*), issue **no** child query for that level; attach the empty/null
   relationship result to each admitted parent and let downstream levels see an
   empty parent set. The two causes are distinct — an empty target attaches
   empty however many keys its parents carry — but load the view the same way:
   a to-many view is loaded empty and a to-one view loaded null, never left
   unloaded. A back-reference level issues **no** child query either, and
   attaches to each admitted parent the already-fetched object its arriving hop
   started from.
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

A back-reference level ends its path. A path continuing past one, such as
`Order.items`, `OrderItem.order`, `Order.items`, **MUST** be rejected before any
SQL with `deep-fetch-past-back-reference` (`m-case-format`).

### The 1 → N → N proof

The canonical witness is a two-hop fan-out: a root with `N` children, each child
with `N` grandchildren. Naively this is `1 + N + N` statements; with deep fetch
it is exactly **3** — root, one `IN` query for all children, one `IN` query for
all grandchildren. The compatibility harness asserts the statement count equals
the declared `databaseCalls` and that the assembled graph equals the expected
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
instances across the family. `m-object-query` owns the segment's optional
`narrowTo` grammar; this planner resolves that shared Subtype Selection and
fetches only the resolved subset of the relationship target. A selection escaping
that target is `narrow-outside-relationship-target` (`m-inheritance`).

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
relationship key. A view's child objects carry `familyVariant` as every inheritance
participant's nodes do (`m-inheritance`), a single-concrete narrowed view's included.

A back-reference level fills a narrowed view without a read, under either
inheritance strategy: the narrow selects among the already-fetched objects by
concrete type.

**Dedup identity is the triple `(relationship hop, whether a narrow was
authored, effective concrete set)`**, not the relationship alone. Deduplication
of equivalent spellings applies **between two narrowed hops**: two paths whose
`segments` both author a narrow over the same relationship, resolving to the
**same** effective set, deduplicate to **one** hop (one statement) — this is what
makes the equivalent spellings `[Pet]` and `[Cat, Dog]` converge. Two hops
narrowed to **different** sets (`pets[Dog]` and `pets[Cat]`) stay **distinct**.

A **broad** hop and **any** authored narrow over the same relationship are
**distinct** hops — including a **redundant** narrow, one whose `narrowTo`
resolves to the relationship target's entire effective concrete set. A redundant narrow
returns exactly the rows the broad hop returns, yet the two populate **different**
views (`pets` and `pets[Cat,Dog]`), because a segment's view key is derived from
whether a narrow was **authored**, independent of what that narrow resolves to.
Identity therefore cannot key on the resolved set alone: doing so would collapse
the redundant pair into one hop and leave one of the two views unpopulated.

Each distinct hop counts toward `L`, so `1 + L` is preserved with narrowed hops
counting as distinct.

### Path-root guards

The optional path-root `appliesTo` owned by `m-object-query` **guards which
queried objects the path starts from**. It is the deliberate opposite of a
segment `narrowTo`, and the contrast is the whole of its planning semantics:

| | root `appliesTo` | segment `narrowTo` |
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
| equal / equivalent | `appliesTo: [Pet]` and `appliesTo: [Cat, Dog]` over the same family | **1** — they deduplicate |
| disjoint | `appliesTo: [Dog]` and `appliesTo: [Cat]` | 2 — neither fills anything the other does |
| overlapping | `appliesTo: [Dog, WildBoar]` and `appliesTo: [Cat, Dog]` | 2 — the shared roots' view is filled twice, identically |
| containment (including broad) | no guard, and `appliesTo: [Dog]` | 2 — the guarded hop fetches nothing new |

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
need. That cost is **deliberate**: it keeps `databaseCalls` **compositional** — an
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
narrowing-dependent and weaken every `databaseCalls` assertion.

## As-of propagation

A deep fetch as of an instant yields a **point-in-time-consistent object graph**.
The per-hop as-of propagation rule (matched by axis, defaulting unpinned axes to
latest) is owned by `m-navigate` and applies inside each per-level child query.

## Child reads over gathered keys

A child level's read is built from already-resolved metadata and the managed key
values gathered from materialized parents, so it raises no authored-name,
type-inference, or literal failure of its own (`m-object-query`). Every gathered key
satisfies the correlation Attribute's neutral type; a key that does not is an
internal framework error, never a `neutral-literal-*` rejection.

## What the harness verifies

For each deep-fetch case the compatibility harness (`m-case-format`) asserts, in
addition to the standard layers: the golden SQL statement count equals the
declared `then.databaseCalls`; each non-empty child level executes keyed by the parents
gathered from the previous level (with the authored `IN` binds matching the
gathered keys); empty parent-key levels, levels whose target position has no
concrete subtype, and back-reference levels execute no child SQL; and the
in-memory-assembled object graph equals the case's `then.graph`. Additionally,
for each to-many level whose relationship declares `orderBy`, the harness derives
the expected child order from the declared keys/directions (an independent oracle)
and asserts the rows the golden SQL returned obey it, so a dropped or wrong
`ORDER BY` fails the case.
