# The Module Catalog

Parallax's normative behavior is organized into **modules** with canonical
`m-<slug>` identifiers. A module is a **language-neutral behavioral module, not
a package**: a language implementation MAY group many modules into one
package / artifact / crate, so long as it enforces the module-dependency graph
internally. The identifier names *what behavior* a module owns, never *how* a
language ships it.

The catalog is **open**: a module is added when a real, separable behavior
exists — modules are not pre-registered for anticipated work.

## The module catalog

Each module carries a **status** — `active` (in the buildable catalog) or
`deferred` (named and edged, but not yet built) — and a **coverage** source:
`cases` (proven by tagged compatibility fixtures) or `contract` (proven by each
language's provider-contract suite). The coverage gate asserts every module that
is both `active` and `cases`-covered has at least one tagged fixture.

| Module | Summary | Status | Coverage |
|---|---|---|---|
| `m-core` | Neutral types, UTC / timezone, temporal infinity | active | cases |
| `m-descriptor` | Domain-model & metamodel descriptor (+ serde seam) | active | cases |
| `m-pk-gen` | Primary-key generation (`max`, `sequence`) | active | cases |
| `m-inheritance` | Closed-tree inheritance (table-per-hierarchy / -concrete-subtype) | active | cases |
| `m-value-object` | Embedded value objects (structured-document column) | active | cases |
| `m-op-algebra` | Query / operation algebra | active | cases |
| `m-agg` | Aggregation algebra (group-by / having / functions) | deferred | cases |
| `m-sql` | SQL generation & equivalence contract | active | cases |
| `m-sql-agg` | SQL lowering for aggregation | deferred | cases |
| `m-dialect` | Pure dialect rules (quoting, lock suffix, casing) | active | cases |
| `m-db-port` | Database execution port | active | contract |
| `m-db-error` | Database error classification | active | cases |
| `m-navigate` | Relationship navigation & semi-join | active | cases |
| `m-deep-fetch` | Deep fetch (N+1 elimination) | active | cases |
| `m-snapshot-read` | Snapshot graph materialization (plain value graphs) | active | cases |
| `m-op-list` | Operation-backed list results | active | cases |
| `m-batch-write` | Set-based / batched writes | active | cases |
| `m-cascade-delete` | Cascade delete | active | cases |
| `m-unit-work` | Transactions & unit of work | active | cases |
| `m-read-lock` | In-transaction shared read lock | active | cases |
| `m-auto-retry` | Bounded retry on transient conflict | active | cases |
| `m-identity-map` | Transaction-scoped identity map (managed-object interning) | active | cases |
| `m-process-cache` | Process-wide identity & query cache | deferred | cases |
| `m-temporal-read` | As-of temporal reads (all flavors) | active | cases |
| `m-audit-write` | Processing-axis (audit-only) temporal writes | active | cases |
| `m-bitemp-write` | Bitemporal rectangle-split writes | active | cases |
| `m-business-only` | Business-only temporal flavor | deferred | cases |
| `m-detach` | Object lifecycle & detach / merge-back | active | cases |
| `m-opt-lock` | Optimistic locking | active | cases |
| `m-case-format` | Compatibility case format | active | cases |
| `m-conformance-adapter` | Conformance-adapter contract | active | cases |
| `m-api-conformance` | API Conformance Suite contract | active | cases |
| `m-perf-bench` | Performance & benchmark harness | active | cases |
| `m-coherence` | Cross-process cache coherence | deferred | cases |

## The dependency graph

Each edge `A --> B` reads **"A depends on B"**: module `A` MAY reference, build
upon, or require `B`, but `B` **MUST NOT** depend on `A`. The graph MUST be a
**directed acyclic graph** — cycles and wrong-direction edges are spec
violations. Only direct edges are listed; transitive edges are implied and not
re-declared.

The fenced `dependency-graph` block below is the machine-readable source of
truth. The reference harness parses it
(`reference-harness/src/reference_harness/dep_graph_check.py`) and asserts the
graph is acyclic with legal directions. The prose and the block MUST agree.

```dependency-graph
m-descriptor --> m-core
m-pk-gen --> m-descriptor
m-inheritance --> m-descriptor
m-value-object --> m-descriptor
m-op-algebra --> m-descriptor
m-op-algebra --> m-inheritance
m-agg --> m-op-algebra
m-sql --> m-op-algebra
m-sql --> m-dialect
m-sql-agg --> m-agg
m-sql-agg --> m-sql
m-dialect --> m-core
m-db-port --> m-core
m-db-error --> m-db-port
m-db-error --> m-dialect
m-unit-work --> m-op-algebra
m-unit-work --> m-db-port
m-read-lock --> m-unit-work
m-read-lock --> m-dialect
m-auto-retry --> m-unit-work
m-auto-retry --> m-db-error
m-identity-map --> m-unit-work
m-identity-map --> m-temporal-read
m-process-cache --> m-unit-work
m-op-list --> m-op-algebra
m-op-list --> m-unit-work
m-batch-write --> m-unit-work
m-cascade-delete --> m-op-list
m-cascade-delete --> m-unit-work
m-navigate --> m-op-list
m-navigate --> m-unit-work
m-navigate --> m-temporal-read
m-deep-fetch --> m-navigate
m-deep-fetch --> m-op-list
m-snapshot-read --> m-deep-fetch
m-temporal-read --> m-op-algebra
m-audit-write --> m-temporal-read
m-audit-write --> m-unit-work
m-bitemp-write --> m-audit-write
m-business-only --> m-temporal-read
m-business-only --> m-unit-work
m-detach --> m-unit-work
m-detach --> m-identity-map
m-opt-lock --> m-unit-work
m-opt-lock --> m-temporal-read
m-case-format --> m-core
m-conformance-adapter --> m-case-format
m-api-conformance --> m-case-format
m-perf-bench --> m-conformance-adapter
m-coherence --> m-process-cache
```

**No active module depends on a deferred module.** Deferral is a leaf property:
`m-agg`, `m-sql-agg`, `m-business-only`, `m-process-cache`, and `m-coherence` are
only ever depended on by other deferred modules. The DAG checker asserts this
mechanically.

The **conformance family** (`m-case-format`, `m-conformance-adapter`,
`m-api-conformance`, `m-perf-bench`) declares only the structural edges above; by
construction it may reference any behavioral module it harnesses.

### Notable directions (and why they may surprise)

- **`m-op-algebra --> m-inheritance`.** The `narrow` node constrains a
  polymorphic entity position to a subset of its subtypes, and its validity rule
  (the resolved `to` list must be a non-empty subset of the position's **effective
  concrete-subtype set**) is stated in `m-inheritance`'s vocabulary. The algebra
  therefore references the inheritance family model, not the reverse — `m-sql`'s
  tag/branch lowering of a narrow reaches `m-inheritance` transitively through this
  edge and needs no separate `m-sql --> m-inheritance` declaration.
- **`m-navigate --> m-op-list`.** A list is an operation-backed collection;
  navigation *yields* lists and deep fetch *populates* them, so navigation
  depends on lists, not the reverse.
- **`m-navigate --> m-temporal-read`.** Navigation is temporal-aware: a pinned
  as-of value propagates per hop to every temporal entity in the path. As-of
  *reads* are algebra-level, so navigation references `m-temporal-read`, not the
  write modules.
- **`m-identity-map --> m-temporal-read`.** A temporal object's identity key
  includes its **lowered as-of coordinates** — a managed temporal object is a
  view pinned at a coordinate, so the identity module references the as-of read
  model, not just the unit of work that owns the map.
- **`m-detach --> m-identity-map`.** A detached copy is defined by living
  *outside* the identity map (and objects leave the map by detaching at their
  owning scope's end), so the lifecycle module references the map it detaches
  from.
- **`m-snapshot-read --> m-deep-fetch`.** A snapshot graph is *populated by*
  deep fetch; navigation, as-of propagation, and lists are reached transitively.
  Snapshot reads and managed reads (`m-identity-map`) are alternative
  materializations over the same query stack — neither depends on the other.
- **`m-opt-lock --> m-temporal-read`.** For a processing-axis temporal entity the
  optimistic-lock version analogue is DERIVED from the processing-from column, so
  an optimistic close references the milestoning read model.
- **Aggregation is deferred through two modules.** `m-agg` (algebra) and
  `m-sql-agg` (lowering) are both deferred; core SQL generation (`m-sql`) never
  references aggregation constructs.
- **`m-coherence --> m-process-cache`.** Coherence keeps process caches coherent
  across servers; `m-unit-work` stays reachable transitively.

## Enforcement

- **In core: MUST.** The reference harness enforces the DAG + direction property
  and the active→deferred rule mechanically (`just core-dep-graph`).
- **Per language: SHOULD.** Each per-language spec SHOULD prescribe a build-time
  mechanism (dependency-cruiser, import-linter, ArchUnit, crate boundaries, …)
  that fails the build on any dependency the graph does not permit — the common
  failure mode being a wrong-direction edge. Each records its tool and the
  module → package / crate mapping (see the
  [language-spec template](language-spec-template.md), §9).

### The coverage gate

The coverage gate rides the DAG check: every `active` module whose coverage
source is `cases` MUST have at least one compatibility fixture tagged to it
(measured against the `tags` of every fixture under `core/compatibility/`, cases
**and** benchmarks). `m-db-port` is the sole `contract`-covered module — no
fixture maps to it; the execution port is proven by each language's
[database-provider test contract](database-provider-test-contract.md). Run it
with the `--coverage` flag:

```sh
uv run python -m reference_harness.dep_graph_check --coverage core/spec core/compatibility
```

## Out of scope (round 1)

The catalog is a near-superset of an ORM's core behavior; a few capabilities are
explicitly declined for round 1. These are decisions, not oversights.

| Excluded item | Decision | Rationale |
|---|---|---|
| **Source attributes / sharding** | Excluded — but **not a one-way door** | Threading a source through the database layer is pervasive; we don't build it now, but the `m-dialect` / `m-db-port` seam MUST stay able to grow a per-tenant / per-source routing hook. Nothing in the design may *preclude* it. |
| **Conversation scope (a session spanning transactions)** | Excluded — but **not a one-way door** | The identity map's scope is the unit of work (`m-identity-map`); the cross-transaction editing pattern is detach → merge-back (`m-detach`, gated by `m-opt-lock`), and cross-transaction read reuse is a freshness claim belonging to the deferred `m-process-cache` family. Two drafting rules keep a future widening additive: managed objects detach when **the scope that owns them** ends (today, the transaction), and cross-transaction identity is **not promised but never mandated-distinct** — no spec text or compatibility case may assert that two transactions MUST return different instances. The word "session" stays unspent, reserved for the wider scope if it ever exists. |
| **Remote / client-server** | Excluded | Three-tier remoting is cleanly separable and not needed to prove the thesis. |
| **Off-heap storage** | Excluded | An implementation detail with no observable-behavior contract; per-language if ever. |
| **XML config as a mandate** | Excluded | The canonical YAML / JSON descriptor is the mandated model-input format. |
| **Codegen as a mandate** | Excluded | The metamodel is mandated; codegen is a per-language technique, never a mandate. |

**Source / tenant routing is not a one-way door.** The database seam is shaped so
a future per-source routing hook can be added *without re-plumbing* SQL
generation or the transaction layer. We do not build routing in round 1; we
design nothing that forecloses it.
