# M4 — Relationships & Deep Fetch

`M4` specifies how **relationship navigation** turns into joins, and how **deep
fetch** eagerly populates an object graph while **eliminating N+1** round trips.
Per the dependency graph, `M4` depends on `M5` (deep fetch *populates* lists) and
`M8` (the query cache that makes round-trip counts observable). The navigation
**algebra** (the `navigate` / `exists` / `notExists` / `deepFetch` nodes) is M2;
the **SQL emission** is M3. This module ties them to observable behavior.

## Navigation → join semantics

A relationship (M1) is a named association whose `join` predicate has the
canonical form `this.<attr> = <Entity>.<attr>`. From that single declaration two
things are derived, and an implementation **MUST** derive them mechanically (the
user never writes a join):

- the **correlation columns** — the owning-entity key column and the related
  entity's foreign-key column;
- the **cardinality** — `one-to-one` / `many-to-one` (to-one) versus
  `one-to-many` / `many-to-many` (to-many).

A **navigation filter** (`navigate` / `exists` / `notExists`) lowers to a
**correlated `EXISTS` semi-join** (M3). The semi-join form is deliberate: it
filters the queried entity by the *existence* of a related row without joining
the related columns into the projection, so a to-many traversal **MUST NOT**
multiply the queried entity's rows. `notExists` is the negated semi-join.

The independent `referenceSql` oracle for every navigation filter is the naive
`key in (select fk from child where <inner op>)` subquery — an obviously-correct
different formulation that the harness asserts returns the same rows (M12).

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
placement differs, so the golden SQL achieves this per dialect (the M11 seam),
but the observable order is the same everywhere: non-`NULL` values in the
declared direction, then `NULL`s.

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
> assembled graph. The threshold value and the temp-table DDL are M11
> dialect-seam concerns. Round 1 specifies and tests only the simplified `IN`
> form; the temp-table path is a stub to be filled in with `M5` bulk support.

## As-of propagation across relationships

When a read pins an as-of value on a temporal entity (M7), that value
**propagates — per hop, matched by axis — to every temporal entity reached by
navigation or eager loading along the path.** It is auto-injected from the as-of
model and **never written by the user**. At each temporal entity the propagated
value drives *that entity's own* as-of predicate: **latest** lowers to the single
equality `to = infinity`; an **as-of instant** lowers to the half-open
containment `from <= ? and to > ?`. Each axis propagates and lowers
independently; an axis unpinned at the root defaults to **latest** (the M7
default-injection rule, applied per axis).

A **non-temporal** entity in the path carries **no** as-of term. A **temporal**
entity reached from a **non-temporal** one defaults every axis to latest. Because
each entity reconstructs the milestone whose interval *contains* the propagated
date, a deep fetch as of an instant yields a **point-in-time-consistent object
graph** — every entity as it stood at that instant, including now-superseded
milestones. The propagated as-of term is appended **after** the navigation/IN-list
predicate (the bind order is the correlation keys, then the per-axis as-of binds,
business axis first).

## Dependent and reverse relationships

- A **reverse** relationship (`reverseName`) is the same association navigated
  from the related entity back to the owner. It resolves to the mirror
  correlation columns; navigation and deep fetch work identically in either
  direction.
- A **dependent** relationship (`dependent: true`) marks the target as **owned**
  by the source. Ownership matters for **cascade** write operations (insert /
  delete / terminate following dependents), which are part of `M5` bulk/cascade
  — **deferred to a fast-follow** and not specified here. Dependency does not
  change read-side navigation or deep fetch.

## What the harness verifies

For each M4 case the compatibility harness (M12) asserts, in addition to the
standard layers: the golden SQL statement count equals the declared `roundTrips`;
each non-empty child level executes keyed by the parents gathered from the
previous level (with the authored `IN` binds matching the gathered keys); empty
parent-key levels execute no child SQL; and the in-memory-assembled object graph
equals the case's `expectedGraph`. Additionally, for each to-many level whose relationship declares `orderBy`, the
harness derives the expected child order from the declared keys/directions (an
independent oracle) and asserts the rows the golden SQL returned obey it, so a
dropped or wrong `ORDER BY` fails the case.
