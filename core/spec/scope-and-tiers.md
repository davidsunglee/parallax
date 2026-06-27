# Scope & Tiers

This document records the **defensible scope boundary** of the core spec: what is
in the MVP, what follows immediately, what is committed after the parity baseline,
what is optional, and what is explicitly **out** for round 1 — together with the
**pushback** on the ticket's exclusions where they collide with dependencies or
where prioritization needed adjusting.

Scope is organized into **five tiers** rather than a flat mandatory/excluded
split, so the line between "required for parity" and "nice to have" is explicit.
The **coverage gate** (`dep_graph_check --coverage`) mechanically asserts that
every module in the top three tiers (MVP / fast-follow / definitely-do) has at
least one compatibility fixture tagged to it; the **might-do** and **won't-do**
tiers are excluded from the gate.

## The five tiers

| Tier | Meaning | In the coverage gate? |
|---|---|---|
| **MVP** | Smallest cross-language vertical that proves the thesis end-to-end on Postgres | **yes** |
| **Fast-follow** | Required for parity; lands immediately after the MVP | **yes** |
| **Definitely-do** | Committed, after the parity baseline | **yes** |
| **Might-do** | Optional; revisit later | no |
| **Won't-do (round 1)** | Explicitly out of scope | no |

## Tier contents

### MVP

The smallest vertical that proves the thesis on Postgres, end-to-end:

- **M0** core conventions (neutral types · timezone/UTC · temporal infinity)
- **M1** metamodel **+ metamodel serde seam** (core model: entity / attribute /
  relationship / index / asOfAttribute / pkGenerator)
- **M2** operation algebra **+ operation serde seam** (core predicate /
  boolean / membership / string / directive set)
- **M3** SQL contract (Postgres golden SQL + normalization + equivalence)
- **M4** relationships & deep fetch (N+1 elimination)
- **M5** operation-backed list results
- **M7** temporal — **non-temporal + audit-only (processing-temporal)**, read +
  write (DQ7)
- **M8** transactions + unit of work + identity cache + query cache
- **M11** database seam (Postgres concrete)
- **M12** compatibility harness
- PK-generation strategies; the **module-dependency graph + enforcement**

### Fast-follow

Required for parity; lands immediately after the MVP:

- **M7** temporal — **full bitemporal**, read + write incl. the rectangle-split
  `updateUntil` / `terminateUntil` and the `insertUntil` / `updateUntil` /
  `terminateUntil` trio (DQ11)
- **M2** aggregation sub-area (group-by / having / aggregate functions)
- **M5** bulk-set ops + cascade
- **M9** object lifecycle & detach
- **M10** optimistic locking
- **Cross-process cache coherence** — multi-application-server cache coherence,
  not only client-server (DQ4)
- temp-table support (large deep-fetch / large `IN`)

### Definitely-do

Committed, after the parity baseline:

- **M13** performance & benchmark harness (shared fixtures + methodology;
  per-language targets) (DQ10)
- **M7** temporal — **business-temporal-only** mode (DQ7)
- **inheritance** — table-per-hierarchy + table-per-leaf (**not** table-per-class)
  (DQ9)
- **embedded value objects** — mapped to **JSONB** (Postgres) / VARIANT
  (Snowflake) / equivalent, a deliberate deviation from Reladomo's column
  flattening (DQ9)
- a **2nd concrete dialect** behind the M11 seam (proves the seam beyond
  Postgres — realized as **MariaDB**)
- cursor / streaming large-result handling

### Might-do

Optional; revisit later (excluded from the coverage gate):

- advanced slice / query-shape cache
- object/result serialization framework as a *mandate* (reuses the serde seam) +
  GraphQL-style tooling
- in-memory-only objects (`persistent = false`)
- temporal `insertWithIncrement` / `incrementUntil` / `purge` /
  `inactivateForArchiving` — RFC-2119 **MAY** (DQ11); the suite MAY carry optional
  fixtures, but these are excluded from the parity / coverage gate

### Won't-do (round 1)

Explicitly out of scope:

- **client-server / remote** three-tier mode
- **sharded DBs / source attributes** (see the not-a-one-way-door note below)
- **off-heap** storage
- **XML config as a *mandated* format** — a canonical YAML/JSON descriptor is
  mandated instead (DQ6)
- **mandated code generation** — the metamodel is mandated; codegen is a
  per-language technique, never a mandate (DQ5)

> Apache Arrow is intentionally **not listed**: it is out of the core spec
> entirely and left to per-language discretion (DQ12).

## Exclusion pushback (confirmed)

The ticket invited *pushback* where its exclusions collide with dependencies or
where prioritization seemed off. After review, **all exclusions are confirmed**
— with the rationale and one explicit guardrail:

| Excluded item | Decision | Rationale |
|---|---|---|
| **Source attributes / sharding** | Excluded round 1 — but **not a one-way door** | Threading `Object source` through ~25 database-layer sites is pervasive in Reladomo; we don't build it now, but the M11 seam **MUST** stay able to grow a per-tenant/source routing hook later. Nothing in the design may *preclude* it. (DQ9) |
| **Remote / client-server** | Excluded | Three-tier remoting is cleanly separable and not needed to prove the thesis. |
| **Off-heap storage** | Excluded | An implementation detail with no observable-behavior contract; per-language if ever. |
| **XML config as a mandate** | Excluded | The canonical YAML/JSON descriptor *is* the spiritual replacement for the XSDs and doubles as the suite's fixture format (DQ6). |
| **Codegen as a mandate** | Excluded | Decoupling "there must be a metamodel" from "you must codegen" keeps what codegen was *for* while leaving the technique to each language (DQ5). |

### The not-a-one-way-door note (source / tenant routing)

Source-attribute sharding is **excluded for round 1, but the door is left open.**
The M11 dialect/database seam is deliberately shaped so that a future per-tenant or
per-source **routing hook** can be added *without re-plumbing* the SQL-generation
or transaction layers. We simply do not build routing in round 1; we do not design
anything that forecloses it.

## Prioritization adjustments (from review)

Two scope calls were *changed* from the ticket's framing, both promotions:

- **Inheritance** — promoted from *might-do* to **definitely-do** (table-per-
  hierarchy + table-per-leaf, **not** table-per-class). Designed for from the
  start, resolving the "hard to retrofit later" concern (DQ9).
- **Embedded value objects** — promoted from *might-do* to **definitely-do**,
  with a deliberate deviation from Reladomo: map (possibly nested) value objects
  to a **JSONB** column rather than flattening into sibling columns (DQ9).

One regrouping: the former aggregation module (**M6**) is **folded into M2** —
group-by / having / aggregate functions are the same declarative operation algebra
and translate to SQL via M3 exactly like predicates do, so there is no separate
aggregation module (DQ13). The numbering of `M7`–`M13` is preserved to keep
cross-references stable.

## Relationship to the coverage gate

The MVP / fast-follow / definitely-do tiers are exactly the set the **coverage
gate** enforces: each numbered module in those tiers (and the un-numbered
cross-process coherence capability) **MUST** have at least one fixture tagged to
it. The might-do and won't-do tiers — including the MAY-tier temporal mutations —
are **excluded** from the gate, so "the spec is complete for parity" is a passing
mechanical check, not a judgment call. See
[`dependency-graph.md`](dependency-graph.md) for the gate mechanics.
