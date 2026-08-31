# The Module Catalog

Parallax's normative behavior is organized into **modules** with canonical
`m-<slug>` identifiers. A module is a **language-neutral behavioral module**,
not a source or deployment unit. The identifier names *what behavior* a module
owns, never *where* a language implements it or *how* that implementation ships.

The catalog is **open**: a module is added when a real, separable behavior
exists — modules are not pre-registered for anticipated work.

## Implementation topology vocabulary

The core behavioral catalog, a language's source topology, and its deployable
topology are three different views:

- A **behavioral module** is a normative `m-<slug>` behavior and a node in the
  dependency graph below.
- A **source module** is an implementation-owned unit of source organization.
  Depending on the ecosystem, it may be a file, folder, namespace, internal
  package, crate, or another import-addressable unit. It need not be published
  or independently installable.
- An **enforcement scope** is a named source boundary that a dependency-analysis
  tool treats as a node. A scope may be a source module, a subdivision of one,
  or a set of them, but the behavioral-module-to-scope mapping MUST remain fine
  grained enough to reject every dependency direction forbidden by this catalog.
- A **deployable artifact** is an independently installable or publishable
  production unit with its own declared external dependencies. One artifact may
  contain many source modules and enforcement scopes.
- The **common runtime** is the independently deployable, lifecycle-neutral
  artifact that supplies behavior shared by all supported object lifecycle
  styles.
- A **lifecycle extension** is a separately deployable production artifact that
  implements exactly one supported object lifecycle style, such as snapshot
  graphs or managed objects, over the common runtime.
- A **database adapter** is a separately deployable production artifact that
  implements the abstract database port for exactly one database type over one
  concrete driver.
- A **composition root** is the application- or test-owned assembly point that
  selects one lifecycle extension and the concrete database adapter or adapters
  the application uses, then injects them into the runtime. It is a wiring
  boundary, not another behavioral module.

The normative DAG applies to behavioral dependencies between enforcement scopes
regardless of how many deployable artifacts contain those scopes. A language MAY
place many behavioral modules in one source tree or deployable artifact, provided
its dependency tooling still enforces the DAG between files, folders, namespaces,
internal packages, crates, or equivalent scopes. Co-location in an artifact does
not make a forbidden source dependency legal, and the DAG does not imply one
artifact per behavioral module.

## Required production artifact topology

Deployable artifacts follow optional-dependency seams rather than the
behavioral-module catalog:

- Every language implementation MUST ship the common runtime independently of
  every lifecycle extension and concrete database adapter. The common runtime
  MUST depend on neither a lifecycle extension nor a concrete database driver.
- Every supported lifecycle style MUST ship as its own lifecycle extension.
  Each extension depends downward on the common runtime and MUST NOT depend on a
  sibling lifecycle extension or a concrete database adapter.
- Every concrete database adapter MUST ship as its own deployable artifact. Its
  manifest is the only Parallax production-artifact manifest that MAY declare
  that adapter's concrete driver; the adapter depends on the abstract port and
  its matching driver-free dialect strategy, wherever those driver-free
  components ship.
- Installing or using a selected lifecycle extension and database adapter MUST
  NOT install, initialize, or load an unselected lifecycle extension, adapter,
  or driver. A mandatory umbrella artifact that depends on all lifecycle styles
  or concrete adapters is therefore forbidden.
- Pure, driver-free dialect strategies MAY ship in the common runtime or in
  further independently deployable artifacts. Languages MAY split any required
  artifact further, but MUST NOT collapse the common runtime into a lifecycle
  extension or combine concrete drivers into a mandatory artifact.
- Conformance harnesses, benchmarks, container tooling, and other
  development-only tools MUST NOT enter a production runtime dependency graph.

The composition root may import the selected concrete artifacts. Common-runtime
code above the database seam binds to lifecycle-neutral interfaces and the
abstract database port whether the port is co-packaged or supplied by another
driver-free artifact; each lifecycle extension depends only downward on that
common behavior. No runtime layer above the database seam imports a concrete
adapter. The rationale and consequences are recorded in
[ADR 0022](../../docs/adr/0022-deployable-artifacts-follow-optional-dependency-seams.md).

## The module catalog

Each module carries a **status** — `active` (in the buildable catalog) or
`deferred` (named and edged, but not yet built) — and a **coverage** source:
`cases` (proven by tagged compatibility fixtures) or `contract` (proven by each
language's provider-contract suite). The coverage gate asserts every module that
is both `active` and `cases`-covered has at least one tagged fixture.

| Module | Summary | Status | Coverage |
|---|---|---|---|
| `m-core` | Neutral types, managed value membership, developer coercion, UTC / timezone, temporal infinity | active | cases |
| `m-wire` | Strict JSON loading and the sole serialized typed-literal codec per Neutral Type | active | cases |
| `m-metamodel` | Representation-independent declarations, identity, lookup, and compiled metadata | active | cases |
| `m-model-formation` | Explicit deterministic composition of model rules and facet compilers | active | cases |
| `m-descriptor` | Canonical descriptor interchange & serde | active | cases |
| `m-pk-gen` | Primary-key generation (`max`, `sequence`) | active | cases |
| `m-inheritance` | Closed-tree inheritance (table-per-hierarchy / -concrete-subtype) | active | cases |
| `m-storage-layout` | Canonical physical Table composition and column layout | active | cases |
| `m-value-object` | Embedded value objects (structured-document column) | active | cases |
| `m-document-codec` | Portable document encoding, decoding, and patching | active | cases |
| `m-relationship` | Relationship formation and symmetric relationship facet | active | cases |
| `m-predicate` | Predicate algebra (the recursive selection grammar) | active | cases |
| `m-object-query` | Object Query (the flat query value for full objects) | active | cases |
| `m-agg` | Aggregation algebra (group-by / having / functions) | deferred | contract |
| `m-sql` | SQL generation & equivalence contract | active | cases |
| `m-sql-agg` | SQL lowering for aggregation | deferred | contract |
| `m-dialect` | Pure dialect rules (quoting, lock suffix, casing) | active | cases |
| `m-db-port` | Database execution port | active | contract |
| `m-db-error` | Database error classification | active | cases |
| `m-navigate` | Relationship navigation & semi-join (incl. polymorphic targets) | active | cases |
| `m-deep-fetch` | Deep fetch (N+1 elimination) & narrowed relationship views | active | cases |
| `m-snapshot-read` | Snapshot graph materialization (plain value graphs) | active | cases |
| `m-op-list` | Query-backed list results | active | cases |
| `m-batch-write` | Set-based / batched writes | active | cases |
| `m-cascade-delete` | Cascade delete | active | cases |
| `m-unit-work` | Transactions & unit of work | active | cases |
| `m-read-lock` | In-transaction shared read lock | active | cases |
| `m-auto-retry` | Bounded retry on transient conflict | active | cases |
| `m-execution-lifecycle` | Transient execution observability | active | cases |
| `m-identity-map` | Transaction-scoped identity map (managed-object interning) | active | cases |
| `m-process-cache` | Process-wide identity & query cache | deferred | cases |
| `m-temporal-read` | As-of temporal reads (all flavors) | active | cases |
| `m-txtime-write` | Transaction-Time-Only temporal writes | active | cases |
| `m-bitemp-write` | Bitemporal rectangle-split writes | active | cases |
| `m-validtime-only` | Valid-Time-Only temporal formation (deferred) | deferred | cases |
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
This graph says nothing about artifact count: implementations enforce it across
their declared source enforcement scopes, including scopes co-located in one
deployable artifact.

```dependency-graph
m-metamodel --> m-core
m-wire --> m-core
m-model-formation --> m-metamodel
m-descriptor --> m-core
m-descriptor --> m-metamodel
m-descriptor --> m-inheritance
m-pk-gen --> m-metamodel
m-inheritance --> m-metamodel
m-inheritance --> m-model-formation
m-storage-layout --> m-metamodel
m-storage-layout --> m-model-formation
m-storage-layout --> m-inheritance
m-storage-layout --> m-relationship
m-value-object --> m-metamodel
m-value-object --> m-model-formation
m-document-codec --> m-core
m-document-codec --> m-metamodel
m-document-codec --> m-wire
m-relationship --> m-metamodel
m-relationship --> m-model-formation
m-predicate --> m-metamodel
m-predicate --> m-inheritance
m-predicate --> m-wire
m-object-query --> m-predicate
m-object-query --> m-metamodel
m-object-query --> m-inheritance
m-object-query --> m-wire
m-agg --> m-predicate
m-sql --> m-predicate
m-sql --> m-object-query
m-sql --> m-dialect
m-sql --> m-metamodel
m-sql --> m-inheritance
m-sql --> m-storage-layout
m-sql --> m-relationship
m-sql --> m-document-codec
m-sql --> m-wire
m-sql --> m-unit-work
m-sql --> m-deep-fetch
m-sql-agg --> m-agg
m-sql-agg --> m-sql
m-dialect --> m-core
m-db-port --> m-core
m-db-port --> m-dialect
m-db-error --> m-db-port
m-db-error --> m-dialect
m-unit-work --> m-predicate
m-unit-work --> m-wire
m-unit-work --> m-db-port
m-unit-work --> m-temporal-read
m-read-lock --> m-unit-work
m-read-lock --> m-dialect
m-auto-retry --> m-unit-work
m-auto-retry --> m-db-error
m-execution-lifecycle --> m-sql
m-execution-lifecycle --> m-db-port
m-execution-lifecycle --> m-db-error
m-execution-lifecycle --> m-unit-work
m-execution-lifecycle --> m-auto-retry
m-identity-map --> m-unit-work
m-identity-map --> m-temporal-read
m-process-cache --> m-unit-work
m-op-list --> m-object-query
m-op-list --> m-unit-work
m-batch-write --> m-unit-work
m-cascade-delete --> m-op-list
m-cascade-delete --> m-unit-work
m-navigate --> m-predicate
m-navigate --> m-unit-work
m-navigate --> m-temporal-read
m-navigate --> m-inheritance
m-navigate --> m-relationship
m-deep-fetch --> m-navigate
m-deep-fetch --> m-relationship
m-deep-fetch --> m-object-query
m-deep-fetch --> m-inheritance
m-deep-fetch --> m-predicate
m-deep-fetch --> m-unit-work
m-deep-fetch --> m-wire
m-op-list --> m-deep-fetch
m-snapshot-read --> m-deep-fetch
m-snapshot-read --> m-document-codec
m-snapshot-read --> m-metamodel
m-snapshot-read --> m-inheritance
m-snapshot-read --> m-relationship
m-snapshot-read --> m-temporal-read
m-snapshot-read --> m-execution-lifecycle
m-snapshot-read --> m-wire
m-temporal-read --> m-predicate
m-temporal-read --> m-object-query
m-temporal-read --> m-metamodel
m-temporal-read --> m-model-formation
m-temporal-read --> m-inheritance
m-txtime-write --> m-temporal-read
m-txtime-write --> m-unit-work
m-bitemp-write --> m-txtime-write
m-validtime-only --> m-temporal-read
m-validtime-only --> m-unit-work
m-detach --> m-unit-work
m-detach --> m-identity-map
m-opt-lock --> m-unit-work
m-opt-lock --> m-temporal-read
m-opt-lock --> m-metamodel
m-opt-lock --> m-model-formation
m-opt-lock --> m-inheritance
m-case-format --> m-core
m-conformance-adapter --> m-case-format
m-api-conformance --> m-case-format
m-perf-bench --> m-conformance-adapter
m-coherence --> m-process-cache
```

**No active module depends on a deferred module.** Deferral is a leaf property:
`m-agg`, `m-sql-agg`, `m-validtime-only`, `m-process-cache`, and `m-coherence` are
only ever depended on by other deferred modules. The DAG checker asserts this
mechanically.

The **conformance family** (`m-case-format`, `m-conformance-adapter`,
`m-api-conformance`, `m-perf-bench`) declares only the structural edges above; by
construction it may reference any behavioral module it harnesses.

### Notable directions (and why they may surprise)

- **`m-predicate --> m-metamodel`.** Resolved predicate nodes carry canonical
  model Identities, not descriptor records or authoring strings. Relationship
  execution remains owned by `m-navigate`, which consumes the compiled
  `m-relationship` facet; Predicate does not rebuild that facet.
- **`m-predicate --> m-wire`; `m-object-query --> m-predicate`, `--> m-wire`,
  `--> m-metamodel`, `--> m-inheritance`.** A
  query CARRIES a predicate as one clause; it never extends the selection grammar.
  Its own clauses name canonical model Identities (the queried target, a Sort Key's
  attribute, an Include Path's relationships) and resolve their shared Subtype
  Selection through the effective-concrete-set rules `m-inheritance` owns.
  Predicate elaboration decodes serialized typed literals exactly once through
  `m-wire`, and Object Query owns the mandatory validated-product boundary.
- **`m-temporal-read --> m-object-query`, `m-deep-fetch --> m-object-query`,
  `m-sql --> m-object-query`.** The three modules that REALIZE a clause depend on
  the query that states it, never the reverse: **a clause's value belongs to the
  query; the behavior realizing it belongs to its own module.** Temporal Selection
  is a query clause while injection, `Pin`/`Edge`, and per-hop propagation are
  `m-temporal-read`'s; Includes is a query clause while trie and level planning
  are `m-deep-fetch`'s; ordering, the row cap, and the normalized per-Entity query
  value are query-owned while their SQL is `m-sql`'s. Reversing any of these would
  make the canonical wire contract depend on an execution module.
- **`m-predicate --> m-inheritance`.** The `narrow` node constrains a
  polymorphic entity position to a subset of its subtypes, and its validity rule
  (the resolved `to` list must be a non-empty subset of the position's **effective
  concrete-subtype set**) is stated in `m-inheritance`'s vocabulary. The algebra
  therefore references the inheritance family model, not the reverse.
- **`m-descriptor --> m-inheritance`.** A descriptor document may declare an
  inheritance family that never forms — an unknown parent, a parent cycle, a
  non-root redeclaring a family-owned fact — and those defects are only
  observable on the raw records, before resolution discards or normalizes the
  authored spelling. The interchange module therefore validates the family
  invariants it can see and reports them in `m-inheritance`'s own rule
  vocabulary rather than minting a second one. The edge runs the direction
  descriptor already travels (`--> m-core`, `--> m-metamodel`) and stays
  one-way: `m-inheritance` reaches only `m-metamodel` and `m-model-formation`,
  neither of which names a descriptor record.
- **`m-storage-layout --> m-metamodel`, `m-storage-layout -->
  m-model-formation`, `m-storage-layout --> m-inheritance`.** Storage Layout
  validates Candidate Metamodel physical claims through Inheritance's pure
  table-group projection, then compiles immutable Table Layouts from Compiled
  Metadata plus the Inheritance Facet. It depends on Formation for those phase
  contracts and does not move family topology into physical storage.
- **`m-storage-layout --> m-relationship`.** Accepted Relationship Joins
  *designate* direct-role Attributes: under Relational Document Layout both
  endpoints of every join stay ordinary columns so navigation, joins, and
  referential DDL keep one relational shape, which Storage Layout can only
  compose if it knows the endpoints. It reads them the same two ways it reads
  Inheritance — a pure, total, issue-free Candidate Metamodel projection during
  validation, then the compiled Relationship Facet — so the edge adds no
  Rule Set ordering dependency. This is the direction the placement question
  runs: Relationship never asks where an Attribute is stored.
- **`m-sql --> m-metamodel`, `m-sql --> m-inheritance`, `m-sql -->
  m-storage-layout`.** SQL lowering reads resolved model Identities directly,
  lowers a `narrow` node's tag/branch predicate against the inheritance family
  model, and obtains physical Tables, ordered slots, and branch presence from
  Storage Layout. These direct collaborations are not left to the transitive
  closure through `m-predicate`.
- **`m-document-codec --> m-core`, `m-document-codec --> m-metamodel`,
  `m-document-codec --> m-wire`.** The codec places `m-wire`'s canonical leaf
  spelling into a structured document, decodes stored leaves through its canonical
  seam, and reads each member by the type its accepted Metadata declares. It
  therefore names the managed value spaces, the document shape's Metadata, and the
  sole serialized typed-literal owner. It depends on nothing else: it is pure,
  holds no connection, imports no driver, emits no SQL, and carries no dialect
  seam, so a codec value crosses the database seam already portable.
- **`m-sql --> m-document-codec`.** A comparison against a document-resident member
  compares like with like only when both sides agree on the spelling, so lowering takes
  its literal from the codec rather than rendering one: the type's comparison text
  where the extraction compares as text, and — where a dialect expresses a to-many
  equality as document containment — the containment candidate. The direction is
  one-way: the codec knows nothing about SQL, extraction, or casting, and the cast
  decision itself stays a `m-dialect` one.
- **`m-sql --> m-relationship`.** A navigation hop lowers to a correlated
  semi-join whose columns come from the relationship's join predicate. The
  Relationship Facet is the one place a reverse direction's swapped join exists,
  so SQL lowering reads the compiled direction rather than re-pairing a reverse
  declaration with its defining peer and exchanging the sides itself.
- **`m-op-list --> m-deep-fetch`.** A navigation filter is a *predicate*
  (semi-join) and yields no list; deep fetch is a pure per-level fetch
  algorithm. The lifecycle result surfaces — query-backed lists for the
  managed lifecycle, snapshot graphs for the plain-value lifecycle — sit
  *above* it and are populated by it, mirroring the documented
  `m-snapshot-read --> m-deep-fetch` bullet below: the two are peers, and
  neither depends on the other.
- **`m-navigate --> m-predicate`.** Navigation's `navigate`/`exists`/
  `notExists` nodes are algebra vocabulary, so navigation references the
  algebra directly; before this edge, `m-predicate` was reachable from
  navigate only transitively, through the now-removed `m-navigate -->
  m-op-list` edge.
- **`m-navigate --> m-inheritance`.** A relationship target may be a **polymorphic
  position** (`m-inheritance`): navigation resolves it to its effective
  concrete-subtype set (single-`EXISTS` interior tag predicate under
  table-per-hierarchy, grouped-`OR` per-branch `EXISTS` under
  table-per-concrete-subtype), and a relationship-scope `narrow` must stay within
  it. Navigation therefore references the inheritance family model directly.
- **`m-deep-fetch --> m-inheritance`.** Deep fetch owns narrowed relationship
  views and their derived keys, so it resolves an Include Segment's Subtype
  Selection to its effective concrete set and orders that set canonically —
  directly, rather than leaving the reach to the transitive closure through
  `m-navigate`.
- **`m-deep-fetch --> m-relationship`.** Deep fetch resolves and lowers the
  relationship facet it fetches through (join shape, symmetric reverse) directly,
  rather than leaving that reach to the transitive closure through `m-navigate`.
- **`m-deep-fetch --> m-predicate`, `--> m-unit-work`, `--> m-wire`.** Deep-fetch
  levels are resolved flat reads within the owning transaction. Their authored
  selections arrive elaborated, while generated child-key membership consumes
  managed values directly rather than creating public literals for another Wire
  pass.
- **`m-navigate --> m-temporal-read`.** Navigation is temporal-aware: a pinned
  as-of value propagates per hop to every temporal entity in the path. As-of
  *reads* are algebra-level, so navigation references `m-temporal-read`, not the
  write modules.
- **`m-db-port --> m-dialect`.** A port is the thing that holds a connection, so
  it is the only place that knows which SQL spelling the statements crossing it
  are written in. It therefore EXPOSES that dialect rather than receiving one:
  a caller reads the dialect off the port it already holds instead of choosing a
  second value beside it and hoping the two agree. The edge costs the port none
  of its independence — `m-dialect` is pure, opening no socket and importing no
  driver — so any layer may still hold a port without acquiring a database
  dependency. The direction is one-way: nothing selects a port from a dialect,
  and two ports may report the same one.
- **`m-unit-work --> m-temporal-read`.** A write-planning module depending on a
  read module is the surprise, and it is load-bearing: a temporal Observed State
  Key addresses the object it observed **plus the observed milestone's own
  coordinate**, and that coordinate is `m-temporal-read`'s Edge. A milestone
  chain holds more than one row per primary key at a time, so identity alone
  cannot address the evidence a close needs — the unit of work therefore states
  its observed-state address in the as-of read model's vocabulary rather than
  inventing an opaque parallel one. The edge is to the read *model* only: nothing here
  reaches as-of lowering, and the direction stays one-way, since
  `m-temporal-read` names no unit-of-work construct.
- **`m-unit-work --> m-wire`.** Serialized keyed rows, assignments, and
  predicate-selected writes decode resolved scalar leaves once before they become
  buffered prepared-write products. Managed-object mutation remains developer
  input governed by `m-core`.
- **`m-sql --> m-deep-fetch`, `--> m-unit-work`, `--> m-wire`.** SQL's private
  compilers consume resolved flat reads and planned writes. The Wire edge exists
  for canonical document values and carrier contracts, not to authorize SQL to
  decode an authored literal; resolution and conversion have already happened.
- **`m-execution-lifecycle --> m-unit-work`, `--> m-auto-retry`, `--> m-db-port`,
  `--> m-db-error`, `--> m-sql`.** Transient observability is a
  **composition-level publisher**: its event vocabulary names the statement a
  call executes, call and boundary outcomes, write-batch triggers, retry policy,
  and classifier verdict. A composition root threads one publisher down as an
  ordinary parameter; observed modules discover no Provider and retain no
  lifecycle history.
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
- **`m-snapshot-read --> m-document-codec`.** Snapshot materialization decodes
  document leaves and reduces occurrences to their declared members through the
  codec's single shape-aware operation. The codec remains independent of lifecycle
  and graph construction.
- **`m-snapshot-read --> m-metamodel` / `m-inheritance` / `m-relationship` /
  `m-temporal-read`.** A snapshot graph is stated in **members**, not columns:
  converting a row names each Attribute, Value Object occurrence, and
  relationship view by its declared identity (`m-metamodel`), resolves a row's
  concrete position and its family-effective member set (`m-inheritance`), orders
  a node's views by accepted relationship declaration order (`m-relationship`),
  and carries the whole-graph pin and each node's milestone edge
  (`m-temporal-read`). All four were previously reachable only through
  `m-deep-fetch`; naming them directly is what makes the vocabulary a snapshot
  graph is built from legible to every language target rather than an accident of
  the planner's own closure.
- **`m-snapshot-read --> m-execution-lifecycle`.** Snapshot reads and streams
  publish their transient Read, Stream Batch, and Snapshot Stream activities
  through the composition-supplied lifecycle seam. Their returned graphs and
  stream values retain no observation record.
- **`m-opt-lock --> m-temporal-read`.** For a Transaction-Time Entity the
  optimistic-lock version analogue is derived from `txStart` / physical `in_z`, so
  an optimistic close references the milestoning read model.
- **Aggregation is deferred through two modules.** `m-agg` (algebra) and
  `m-sql-agg` (lowering) are both deferred; core SQL generation (`m-sql`) never
  references aggregation constructs.
- **`m-coherence --> m-process-cache`.** Coherence keeps process caches coherent
  across servers; `m-unit-work` stays reachable transitively.

## Enforcement

- **In core: MUST.** The reference harness enforces the DAG + direction property
  and the active→deferred rule mechanically (`just core-check-module-graph`).
- **Per language: SHOULD.** Each per-language spec SHOULD prescribe a build-time
  mechanism (dependency-cruiser, import-linter, ArchUnit, crate boundaries, …)
  that fails the build on any dependency the graph does not permit — the common
  failure mode being a wrong-direction edge. Each records its tool and the
  behavioral-module → source-ownership / enforcement-scope mapping (see the
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
