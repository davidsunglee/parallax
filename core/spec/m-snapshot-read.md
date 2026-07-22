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

A snapshot graph is **point-consistent**: the root operation's lowered as-of
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
an adapter capability set can include or defer it independently. It is a staged
feature, **not a rejection**: no case may mandate that history-with-includes be
refused.

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
observability rides the lazy operation-backed list, `m-op-list`; a snapshot
read is **not** an operation-backed list — the count is pinned here instead,
on the same golden statements.)

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
