# m-navigate — Relationship Navigation

`m-navigate` specifies how **relationship navigation** turns into joins, and it
owns **cross-entity as-of propagation**. Per the dependency graph, `m-navigate`
depends on `m-op-list` (navigation *yields* lists), `m-unit-work` (navigation
resolves through the unit of work), and `m-temporal-read` (a pinned as-of value
propagates per hop). The navigation **algebra** (the `navigate` / `exists` /
`notExists` nodes) is `m-op-algebra`; the **SQL emission** is `m-sql`. This module
ties them to observable behavior. Deep fetch — eagerly populating an object graph
while eliminating N+1 — builds on navigation and is `m-deep-fetch`.

## Navigation → join semantics

A relationship (`m-descriptor`) is a named association whose `join` predicate has
the canonical form `this.<attr> = <Entity>.<attr>`. From that single declaration
two things are derived, and an implementation **MUST** derive them mechanically
(the user never writes a join):

- the **correlation columns** — the owning-entity key column and the related
  entity's foreign-key column;
- the **cardinality** — `one-to-one` / `many-to-one` (to-one) versus
  `one-to-many` / `many-to-many` (to-many).

A **navigation filter** (`navigate` / `exists` / `notExists`) lowers to a
**correlated `EXISTS` semi-join** (`m-sql`). The semi-join form is deliberate: it
filters the queried entity by the *existence* of a related row without joining
the related columns into the projection, so a to-many traversal **MUST NOT**
multiply the queried entity's rows. `notExists` is the negated semi-join.

A navigation path segment names a **relationship**; a **value-object segment is
invalid** here and MUST be rejected. A value object has no identity to correlate
on — its inner fields are queried *through* the owner with the `m-op-algebra`
nested-attribute form, never navigated to (`m-value-object`, "Materialization and
navigation contract").

The independent `referenceSql` oracle for every navigation filter is the naive
`key in (select fk from child where <inner op>)` subquery — an obviously-correct
different formulation that the harness asserts returns the same rows
(`m-case-format`).

## As-of propagation across relationships

`m-navigate` owns cross-entity as-of propagation. When a read pins an as-of value
on a temporal source entity (`m-temporal-read`), navigation filters (`navigate` /
`exists` / `notExists`) and eager-loading paths (`m-deep-fetch`) **MUST propagate
that value per hop, matched by axis, to every temporal entity reached along the
path.** The propagated value is auto-injected from the as-of model and **never
written by the user**. It is part of the SQL for that hop: inside the correlated
semi-join for navigation filters and inside the per-level child query for deep
fetch. At each temporal target the propagated value drives *that entity's own*
as-of predicate: **latest** lowers to the single equality `to = infinity`; an
**as-of instant** lowers to the half-open containment `from <= ? and to > ?`. Each
axis propagates and lowers independently; an axis unpinned at the root defaults to
**latest** (the `m-temporal-read` default-injection rule, applied per axis).

A **non-temporal** entity in the path carries **no** as-of term. A **temporal**
entity reached from a **non-temporal** one defaults every axis to latest. Because
each entity reconstructs the milestone whose interval *contains* the propagated
date, a deep fetch as of an instant yields a **point-in-time-consistent object
graph** — every entity as it stood at that instant, including now-superseded
milestones. The propagated as-of term is appended **after** the navigation/IN-list
predicate (the bind order is the correlation keys, then the per-axis as-of binds,
business axis first).

The rule extends from the query algebra to **object graphs**: every relationship
dereference from an already-materialized object — a deferred relationship load
on a managed object (`m-deep-fetch`), a hard pointer inside a plain value graph
(`m-snapshot-read`) — resolves the target timeline **at the source object's own
pinned coordinates**, matched by axis. An object's coordinates are part of its
identity (`m-identity-map`), so a dereference never has to guess which instant
to propagate: the source *is* a pin. This is what makes both materializations
temporally coherent — a graph's pointers cannot silently cross temporal
contexts, and a view materialized from a `history` read (edge-pinned at its
milestone's from-instant, `m-temporal-read`) dereferences at its own edge.

## Polymorphic navigation

A relationship target (`relatedEntity`) may be a **polymorphic position** in an
inheritance family (`m-inheritance`): an **abstract root** (reaching any concrete
subtype in the family), an **abstract subtype** (reaching only its concrete
descendants), or a **concrete subtype** (monomorphic). The navigation semi-join
resolves the target to its **effective concrete-subtype set** and constrains the
correlated sub-select to exactly that set — the same effective-set derivation a
top-level read uses, applied at the relationship target.

`narrow` (`m-op-algebra`) MAY appear in a navigation filter's inner operation
(`op`) to constrain the relationship target: `narrow.entity` names the
**relationship target's** polymorphic position, and the narrowed set drives the
semi-join. A narrow whose resolved concrete set is **not a subset** of the
relationship target's effective concrete set is rejected
(`narrow-outside-relationship-target`, `m-case-format`) — narrowing to a concrete
outside the reachable set, even a **sibling** sharing the family root, is invalid.

The lowering per strategy (fixed by `m-sql`):

- **`table-per-hierarchy`** — one shared child table, so a polymorphic hop is a
  **single correlated `EXISTS`** whose sub-select carries the correlation predicate
  **plus the interior tag predicate** over the effective set's `tagValue`s
  (`t1.kind = ?` for one concrete, `t1.kind in (?, …)` for several, in the family's
  canonical alphabetical order, `m-inheritance`). An abstract-**root** target spans
  the whole shared table and injects **no** tag predicate; an abstract-**subtype**
  (or narrowed) target injects the `in`-list so sibling branches in the same table
  are excluded.
- **`table-per-concrete-subtype`** — each concrete subtype has its own table, so a
  polymorphic hop is a **grouped `OR` of one correlated `EXISTS` per effective
  concrete subtype**, in the family's canonical **alphabetical order**
  (`m-inheritance`): `(exists (select 1 from invoice …) or exists (select 1 from
  memo …) or exists (select 1 from receipt …))`. The grouped `OR` is a **flat
  left-deep** chain (`m-sql` rule 1), so each branch's `EXISTS` alias continues the
  single source-order sequence (`t1`, `t2`, `t3` — the outer query is `t0`); it is
  never hand-folded right-nested. A single concrete is one `EXISTS` (no grouping).

**As-of propagation** (above) is unchanged by polymorphism: the root as-of value
propagates per hop, matched by axis, to **every temporal concrete branch** reached
— evaluated at the root's pinned coordinates, appended after each branch's
correlation predicate (and, for `table-per-concrete-subtype`, per `EXISTS` branch).

## Dependent and reverse relationships

- A **reverse** relationship (`reverseName`) is the same association navigated
  from the related entity back to the owner. It resolves to the mirror
  correlation columns; navigation and deep fetch work identically in either
  direction.
- A **dependent** relationship (`dependent: true`) marks the target as **owned**
  by the source. Ownership matters for **cascade** write operations (insert /
  delete / terminate following dependents), which are `m-cascade-delete`.
  Dependency does not change read-side navigation or deep fetch.

## What the harness verifies

For each navigation-filter case the compatibility harness (`m-case-format`)
asserts the standard read layers: the semi-join golden SQL returns exactly
`then.rows`, and the naive `key in (select fk …)` oracle returns the same rows.
The round-trip and object-graph assertions specific to eager loading are
`m-deep-fetch`.
