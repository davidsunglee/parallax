# m-identity-map — Transaction-Scoped Identity Map

`m-identity-map` is the **identity map**: the transaction-scoped cache that
interns managed objects so one database identity resolves to one logical object
within a unit of work. Per the dependency graph, `m-identity-map` depends on
`m-unit-work` (the unit of work is the scope that owns the map) and on
`m-temporal-read` (a temporal object's identity includes its as-of coordinates).
It is the identity half of the **managed-object** read surface; a read surface
that materializes plain snapshot graphs (`m-snapshot-read`) has no managed
objects and no use for it.

This module exists because managed write-behind mutation without an identity
guarantee is a hazard: two managed instances of one row inside one unit of work
buffer conflicting updates with unspecified interleaving. The identity map is
what makes managed object graph mutation safe — which is why `m-unit-work`
itself promises **no** identity (see its *No identity promise* note) and a
managed-object surface needs the two modules together.

## The identity guarantee

Within one **open** unit of work:

- At most **one managed object** exists per **identity key** (below). Two reads
  that resolve the same key — a primary-key lookup and a predicate query
  returning the same row — denote the **same logical object**, never two equal
  copies.
- A repeated lookup for an already-managed key returns the managed object.
- **Query materialization coalesces through the map**: a SQL-producing read
  still executes its statement (this module makes **no round-trip-elimination
  claim** — an operation-to-result cache is `m-process-cache`, deferred), but
  each returned row resolves through the identity map, reusing the managed
  object where the key is already interned.

**No identity promise crosses the unit-of-work boundary.** Independent
transactions make no same-instance promise for the same key. This is a
*no-promise*, not a mandate: nothing in this module — and no compatibility case
— may assert that two transactions MUST return **distinct** instances. (That
silence is what keeps a future conversation-scoped widening additive; see the
*Out of scope* table in [`modules.md`](modules.md).)

## The identity key

The identity key is the triple:

> **(entity family, primary key, lowered as-of coordinate per declared axis)**

- **Entity family** — the key normalizes to the **inheritance family**
  (`m-inheritance`): a row read through the abstract family root and through its
  concrete leaf finder interns to the **same** managed object. Identity is a
  property of the row's family position, never of the query's declared type.
- **Primary key** — the entity's declared primary key (`m-descriptor`).
- **Lowered as-of coordinates** — one coordinate per declared `asOfAttribute`
  axis, in its **lowered** form (`m-temporal-read`): **latest** is the infinity
  sentinel (an omitted axis, and an explicit `asOf(…, now)`, lower to the same
  pin — one canonical coordinate, not a wall-clock instant); a finite pin is the
  instant itself. A **non-temporal** entity has no coordinate component: its key
  degrades to (family, primary key).

Two lookups with the **same** lowered coordinates resolve to the same managed
object. **Distinct** lowered coordinates denote **distinct pinned views** — even
when both currently resolve to the same milestone row — because each view's
coordinates drive its own relationship dereferencing (`m-navigate`, as-of
propagation): an object that belonged to two pins at once would have no
well-defined coordinate to propagate.

This mirrors Reladomo's dated-cache uniquing (a dated wrapper per
`(data, asOfDates)` pair, milestone data shared underneath); the *mechanism* —
shared data objects, per-view wrappers, a keyed hash — is non-normative. Only
the key and the resulting object identities are mandated.

## Pinned views over one timeline

A managed **temporal** object is a *view of its milestone timeline pinned at its
coordinates*, not a copy of one row:

- After an in-transaction milestone-chaining write (`m-audit-write`,
  `m-bitemp-write`), **every held view reflects the post-write timeline at its
  own pin**: a latest-pinned view shows the newly chained milestone; a view
  pinned at a finite past instant keeps showing the milestone its pin selects.
- A view pinned at a **finite processing-axis instant** is **read-only** — the
  processing past records what the system knew and is never rewritten. A finite
  **business-axis** pin is writable: mutating it is the retroactive correction
  that lowers to the `m-bitemp-write` rectangle split.
- A `history` / `asOfRange` read materializes **one view per milestone**, each
  interned at its **edge pin** — the milestone's own from-instant, the one
  instant guaranteed to select exactly that milestone (`m-temporal-read`,
  Reladomo's `equalsEdgePoint` heritage: for a half-open `[from, to)` interval
  the edge is the from column).

## Interning timing

- A **persisted** object interns when it **materializes** from a read.
- An **in-memory** object (`m-detach` lifecycle) interns when its identity key
  first **exists**: an application-assigned key interns on insert-buffering; a
  **generated** key (`m-pk-gen`) interns at key generation/flush, since there is
  no key to intern under before then.
- A **detached copy** lives *outside* the map by construction (`m-detach`); at
  the owning scope's end every managed object leaves the map by transitioning to
  detached.

## Scope, lifetime, and abort

The identity map is **owned by the unit of work**: created when the unit of work
opens, discarded when it ends. **Abort discards the map with everything else**
(`m-unit-work` abort contract) — no interned object, and no identity fact, from
an aborted unit of work survives it. There is no session, no process scope, and
no cross-transaction freshness claim in this module; the process-wide identity
and query caches remain the separately deferred `m-process-cache`.

Concurrency follows scope: the map is a **single-owner** structure. Sharing one
unit of work — and therefore one identity map — across concurrent tasks is not a
supported access pattern; a process-wide handle or pool may be shared, the map
may not be shared implicitly.

## What the suite pins down

The map's row-level observables are **scenario** cases (`m-case-format`); the
object-**reference** identity they imply is asserted per-language by the API
Conformance Suite (`m-api-conformance`), which runs each scenario inside one
unit of work on the idiomatic surface.

| Case | What it proves |
|---|---|
| same-transaction identity | two *different* operations resolving one row (a PK find, a unique-attribute find) denote the same logical object (`sameObjectAs`), at one round trip each — identity without any query-cache claim |
| coordinate coexistence | a latest-pinned read and a finite past pin of the same primary key coexist as distinct pinned views (each milestone's own rows); a repeat of the latest pin resolves the same logical object as the first |
