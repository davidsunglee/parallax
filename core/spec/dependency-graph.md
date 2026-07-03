# Normative Module-Dependency Graph

The **direction of dependency between modules is itself a normative part of the
core spec.** The graph below is the **only** legal dependency direction. An
implementation **MUST** respect it.

## "Depends-on" semantics

Each edge `A --> B` reads **"A depends on B"** — that is, module `A` MAY
reference, build upon, or require module `B`, but `B` **MUST NOT** depend on `A`.

- The graph **MUST** be a **directed acyclic graph (DAG)**. **Cycles are
  prohibited.**
- An "upward" or wrong-direction dependency (e.g. `M1` depending on `M12`, or
  `B` depending on `A` when only `A --> B` is declared) is a **spec violation**.
- Transitive dependencies are implied: if `A --> B` and `B --> C`, then `A` may
  depend transitively on `C`. Only the **direct** edges are listed below;
  transitive edges are omitted for readability and are **not** re-declared.

The fenced `dependency-graph` block below is the machine-readable source of
truth. The reference harness parses it
(`reference-harness/src/reference_harness/dep_graph_check.py`) and asserts the
graph is acyclic and that every declared edge points in a legal direction. The
prose and the block **MUST** agree.

```dependency-graph
M1 --> M0
M11 --> M0
M2 --> M1
M3 --> M2
M3 --> M11
M8 --> M2
M8 --> M11
M5 --> M2
M5 --> M8
M4 --> M5
M4 --> M8
M4 --> M7
M7 --> M8
M9 --> M8
M10 --> M8
M10 --> M7
M12 --> M2
M12 --> M3
M12 --> M4
M12 --> M7
M12 --> M8
M12 --> M9
M12 --> M10
M12 --> M11
M13 --> M12
M14 --> M8
```

## The modules

| Module | Title |
|---|---|
| M0 | Core Conventions (types · infinity · timezone) |
| M1 | Domain Model & Metamodel (+ metamodel serde) |
| M2 | Query, Operation & Aggregation Algebra (+ operation serde) |
| M3 | SQL Generation Contract |
| M4 | Relationships & Deep Fetch |
| M5 | Lists & Bulk/Set Operations |
| M7 | Bitemporal / Milestoning |
| M8 | Transactions, Unit of Work & Identity + Query Cache |
| M9 | Object Lifecycle & Detach |
| M10 | Optimistic Locking |
| M11 | Database Seam & Portability |
| M12 | Compatibility Harness & Test-Double Integration |
| M13 | Performance & Benchmark Harness |
| M14 | Cross-Process Cache Coherence (fast-follow; depends on `M8`) |

> `M6` does not exist: aggregation is folded into `M2`. The numbering of
> `M7`–`M13` is preserved to keep cross-references stable.
>
> **Cross-process cache coherence is `M14`**, a fast-follow capability that
> **depends on `M8`** — it keeps the caches `M8` defines coherent across multiple
> application servers. Its single legal dependency direction is `M14 --> M8` (the
> machine-readable edge above); like every edge, the reverse is a spec violation
> (`M8` MUST NOT depend on it). It was previously left un-numbered; it is now a
> first-class numbered module on equal footing with the other numbered modules (`M0`–`M13`).

## Notable directions (and why they may surprise)

- **Aggregation is part of M2, not its own module.** Group-by / having /
  aggregate functions are the same declarative operation algebra and translate
  to SQL via `M3` exactly like predicates do — so there is no aggregation module
  depending on `M3`.
- **M8 depends on M2, not M3.** The transaction / unit-of-work / cache layer is
  expressed in terms of *operations and object state* (`M2`); the
  dialect-specific SQL it executes is produced by `M3` and run through the `M11`
  execution seam at the composition root, so `M8` takes no direct edge to SQL
  generation.
- **Lists are foundational; relationships sit above them.** A list is an
  operation-backed collection, so **`M5` depends on `M2` and `M8`**.
  Relationship navigation *yields* lists and deep fetch *populates* them, so
  **`M4` depends on `M5`** — the reverse of the obvious guess.
- **M4 depends on M7 (as-of propagation).** Deep fetch and navigation are
  temporal-aware: a pinned as-of value propagates per-hop to every temporal
  entity in the path (M4, "As-of propagation across relationships"), so the
  relationship layer references the as-of model. The reverse — M7 depending on
  M4 — remains forbidden.
- **M10 depends on M7 (optimistic × temporal composition).** For a processing-axis
  temporal entity the optimistic-lock key is DERIVED from the processing-from
  column — the observed `in_z` is the version analogue — so an optimistic close
  gates on it (`… and in_z = ?`); optimistic locking therefore composes *over* the
  milestoning model and references it. The single legal direction is `M10 --> M7`;
  the reverse — M7 depending on M10 — is forbidden. The DAG stays acyclic:
  `M7 --> M8` and `M10 --> M8`, so `M10 --> M7 --> M8` introduces no cycle.
- **M12 depends on M8 directly, not only via M10.** The compatibility harness
  executes M8 unit-of-work behavior itself — batched write-sequence flushes and
  read-your-own-writes scenarios — independently of optimistic locking, so it
  references M8 directly. That direct reference is the declared `M12 --> M8` edge,
  coexisting with the transitive `M12 --> M10 --> M8` path exactly as `M4 --> M8`
  is declared alongside `M4 --> M5 --> M8`: the graph lists an edge whenever a
  module *directly* references another, even when the target is also transitively
  reachable. Only *purely* transitive edges are omitted (the "Depends-on
  semantics" rule above).
- **M12 depends on M11 directly.** The harness is the SQL-assembly orchestrator:
  it derives DDL, quotes identifiers, and **applies the in-transaction read lock**
  (a dialect decision — an object find takes the shared lock, an aggregation omits
  it; `m11-dialect-seam.md`) using the pure dialect rules, so it references M11
  directly. That is the declared `M12 --> M11` edge; the driver stays injected
  through the execution port, so the harness holds the dialect *rules* without
  acquiring a driver dependency.

## Enforcement expectations

- **In core: MUST.** This graph is normative; every implementation MUST respect
  it, and the reference harness enforces the DAG + direction property
  mechanically.
- **Per language: SHOULD.** Each per-language spec **SHOULD** prescribe a
  **build-time enforcement mechanism** that fails the build when a
  module/package introduces a dependency not permitted by this graph (the common
  failure mode being a wrong-direction edge added by a contributor who does not
  understand the layering).

### Per-ecosystem enforcement tooling

The mechanism differs per ecosystem, but the contract is the same: encode the
legal edges of the DAG above and fail the build on any other module-to-module
dependency.

| Ecosystem | Tool(s) | How the contract is encoded |
|---|---|---|
| **Python** | [`import-linter`](https://import-linter.readthedocs.io/) or [`tach`](https://github.com/gauge-sh/tach) | a *layers* / *forbidden* contract listing the modules top-to-bottom; the linter fails on any import that crosses a forbidden boundary |
| **Java / JVM** | **ArchUnit** rules, or Gradle/Maven module boundaries | `layeredArchitecture()` / `noClasses().that()...should().dependOnClassesThat()` rules in a unit test; or split modules so the build graph itself forbids the wrong-direction dependency |
| **TypeScript / Node** | [`dependency-cruiser`](https://github.com/sverweij/dependency-cruiser) or `eslint-plugin-boundaries` | a `forbidden` rule set mapping each module to the modules it MAY depend on |
| **Rust** | **crate boundaries + visibility** | split modules into crates so Cargo's dependency graph (plus `pub` visibility) makes a wrong-direction dependency a compile error |

Each per-language spec records its chosen tool and the module → package/crate
mapping (see the
[language-spec template](language-spec-template.md), §9).

### The coverage gate

The reference harness adds a **coverage gate** on top of the DAG check: it asserts
that **every in-scope module has at least one compatibility fixture tagged to
it.** "In-scope" means the **MVP**, **fast-follow**, and **definitely-do** tiers
(see [`scope-and-tiers.md`](scope-and-tiers.md)); the **might-do** and
**won't-do** tiers — including the RFC-2119 **MAY** temporal mutations — are
**excluded** from the gate.

The gate turns *"the spec is complete for parity"* into a passing check rather than
a judgment call: if a module in the top three tiers exists in the dependency graph
but no fixture is tagged to it, the gate fails and names the uncovered module.
Coverage is measured against the `tags` field of every fixture under
`core/compatibility/` (cases **and** benchmarks): a module `M`*n* is covered when
at least one fixture's `tags` contains `m`*n* (case-insensitive).

Run it with the `--coverage` flag, passing the spec and compatibility roots:

```sh
uv run python -m reference_harness.dep_graph_check --coverage core/spec core/compatibility
```

This runs the DAG + direction check **and** the coverage gate together; it exits
non-zero (naming the gap) if any in-scope module is uncovered or the graph is not
a legal DAG.
