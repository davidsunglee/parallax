# m-deep-fetch — Deep Fetch

`m-deep-fetch` specifies how **deep fetch** eagerly populates an object graph
while **eliminating N+1** round trips. Per the dependency graph, `m-deep-fetch`
depends on `m-navigate` alone (deep fetch traverses relationships). The
`deepFetch` **algebra node** is `m-op-algebra`; the **SQL emission** is `m-sql`.
This module ties them to observable behavior. The two lifecycle result surfaces
— operation-backed lists (`m-op-list`) for the managed lifecycle, snapshot
graphs (`m-snapshot-read`) for the plain-value lifecycle — sit **above** deep
fetch and are populated by it; deep fetch itself is a pure per-level fetch
algorithm and reifies neither.

Every `deepFetch` path segment names a **relationship** between identity-bearing
entities; a **value-object segment is invalid** in the path grammar and MUST be
rejected. Value objects have no identity, no correlation columns, and no
deep-fetch statement — they materialize *with* their owning entity in the owner's
own read (`m-value-object`, "Materialization and navigation contract").

## Deep fetch: one query per non-empty relationship level

`deepFetch(operand, paths)` resolves `operand` (the root query), then eagerly
fetches each navigation `path`. The normative guarantee:

> The number of SQL statements is **at most `1 + L`**, where `L` is the number
> of **distinct relationship hops** across all declared paths. A level whose
> parent-key set is empty issues **no** child SQL. A non-empty level issues
> **one** child statement — **never** one query per parent row.

Concretely, for each relationship level:

1. Gather the **distinct key values** of the already-fetched parent rows for that
   relationship's correlation column.
2. If the gathered set is empty, issue **no** child query for that level; attach
   the empty/null relationship result and let downstream levels see an empty
   parent set.
3. Otherwise, issue **one** query against the child entity constrained by
   `fk in (…)` over those distinct keys.
4. Fan the returned child rows back to their parents **in memory**, attaching
   each child set under the relationship name (a list for a to-many relationship,
   a single object or null for a to-one).

Paths that share a prefix (e.g. `[Order.items]` and
`[Order.items, OrderItem.statuses]`) fetch the shared hop **once** — the hop is
de-duplicated, so it counts as a single level.

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
`{attr, direction}` keys (`direction ∈ {asc, desc}`, default `asc`). When it
does, the per-level child query for that relationship **MUST** emit `ORDER BY`
over the declared keys, in declared sequence, each rendered with its declared
direction, and the in-memory-assembled to-many list **MUST** preserve that
order. A relationship with no declared `orderBy` leaves child order
**unspecified** — the database's natural order, which callers MUST NOT rely on.

Ordering is a property of the relationship, not of the query: every deep fetch
that materializes the relationship emits the same `ORDER BY`. Keys are evaluated
left to right — the first key is primary, later keys break ties — so a multi-key
`orderBy` with mixed directions (`[{score, desc}, {name, asc}]`) sorts by `score`
descending and breaks ties by `name` ascending.

A `NULL` in an `orderBy` key sorts **last** on that key, in both `asc` and
`desc` — the canonical, dialect-independent rule. The dialects' native `NULL`
placement differs, so the golden SQL achieves this per dialect (the `m-dialect`
seam), but the observable order is the same everywhere: non-`NULL` values in the
declared direction, then `NULL`s.

## Polymorphic and narrowed deep fetch

A deep-fetch hop whose relationship target is a **polymorphic position**
(`m-inheritance` — an abstract root or abstract subtype) eagerly fetches concrete
instances across the family. A path segment MAY carry a `narrow` (`m-op-algebra`,
the `{ to: [ … ] }` on the segment) to fetch only a **subset** of the target's
concrete subtypes; the narrow must resolve **within** the relationship target's
effective concrete set (`narrow-outside-relationship-target`, `m-navigate`).

**A narrowed hop populates a distinct narrowed relationship view**, keyed by a
**derived** name rather than the ordinary relationship name:

```text
<relationshipName>[<ConcreteSubtype>,<ConcreteSubtype>]
```

- the **local** relationship name (never the qualified `Class.rel` ref);
- the **effective concrete-subtype set**, in the family's canonical **alphabetical
  order** (by entity name, `m-inheritance`; never abstract names, never a
  `tagValue`), comma-joined with **no spaces**.

So `Person.pets` narrowed to `[Pet]` (or, equivalently, `[Cat, Dog]`) both derive
`pets[Cat,Dog]`. A narrowed include populates that view **only**; it does **not**
mark the broad relationship loaded, and a **broad** hop keeps the ordinary
relationship key. The polymorphic view's child objects additionally carry
`familyVariant` (the concrete subtype name), materialized from the tag map exactly
as an abstract-target flat read (`m-case-format`); a single-concrete narrowed view
carries none (the caller fetched a known variant).

**Dedup identity is the pair `(relationship hop, effective concrete set)`**, not
the relationship alone. Two paths whose segments resolve to the **same** effective
set deduplicate to **one** hop (one statement) — this is what makes the equivalent
spellings `[Pet]` and `[Cat, Dog]` converge. A **broad** hop and a **narrowed** hop
over the same relationship, or two hops narrowed to **different** sets
(`pets[Dog]` and `pets[Cat]`), are **distinct** hops that each count toward `L`, so
`1 + L` is preserved with narrowed hops counting as distinct.

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
