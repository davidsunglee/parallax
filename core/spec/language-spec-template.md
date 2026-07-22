# Language-Spec Template

This is the checklist every per-language spec must complete before implementation
begins. The core specification fixes language-neutral behavior, protocol seams,
the behavioral-module dependency graph, and the required production artifact
topology. A language spec records the remaining developer-surface, source,
packaging, and toolchain decisions once.

> **How to use this template.** Copy this file into `<language>/spec/`. Replace
> every **(decide and record)** marker with a concrete answer and a short
> rationale. Apply the applicability rules below, then delete their instructions
> from the completed spec. Nothing here may contradict the core specification,
> the canonical slice claim in [`slices.md`](slices.md), or the normative module
> DAG and artifact topology in [`modules.md`](modules.md).

## Applicability rules

Every decision prompt carries one of these labels:

- **All slices** — retain and answer it for every selected Conformance Slice.
- **Snapshot lifecycle** — retain and answer it only when the selected slice uses
  the plain-value snapshot lifecycle. Delete the managed-object alternative.
- **Managed-object lifecycle** — retain and answer it only when the selected
  slice uses managed objects. Delete the snapshot alternative.
- **When claimed: _capability_** — retain and answer it only when the selected
  canonical claim contains the named module, feature, dialect, or command. A
  module implemented only as a transitive prerequisite is not claimed behavior
  and does not activate one of these prompts. When several capabilities are
  named, the prompt states whether any or all must be claimed.

A completed language spec retains exactly one lifecycle profile in
[§3](#3-object-lifecycle-profile) and the matching result branch in
[§4](#4-result-collections-and-materialization). The canonical snapshot and
managed-object slices are sibling choices over a shared behavioral base; neither
is a prerequisite for the other. If a new slice does not identify its lifecycle
unambiguously, define that choice in [`slices.md`](slices.md) before completing a
language spec.

## 1. Scope and exact claim

Complete this table first. Its claim fields copy, rather than reinterpret, the
canonical `describe` envelope in [`slices.md`](slices.md). A slice's
`capabilities.modules` is the union of module tags on its cases; it is coverage,
not a dependency closure or packaging plan. Compute implementation prerequisites
separately from the DAG in [`modules.md`](modules.md).

| Scope decision | Required record |
|---|---|
| Conformance Slice | **(decide and record — All slices)** The canonical slice name, its one `caseTags.include` tag, lifecycle profile, and link to its definition in `slices.md`. |
| Exact `describe` claim | **(decide and record — All slices)** The complete canonical `describeOk` envelope. It MUST be structurally equal to the claim in `slices.md` after JSON parsing, except for the implementation's `adapter` identity. |
| Claimed capability coverage | **(decide and record — All slices)** The exact `modules`, `dialects`, `caseShapes`, `caseTags`, `commands`, and `provisioning` values copied from the canonical claim. State that `modules` is the tagged-case union, not a dependency closure. |
| Unclaimed implementation prerequisites | **(decide and record — All slices)** Every transitive prerequisite in the module DAG that is absent from claimed `capabilities.modules`, with the claimed module that reaches it and the source scope that supplies it. These are implementation dependencies, not developer-surface claims. |
| Deferred capabilities | **(decide and record — All slices)** Every known module, feature tag, dialect, command, or lifecycle style intentionally deferred from this milestone. Distinguish deferral from unsupported input classification. |
| Supported dialects and commands | **(decide and record — All slices)** The exact dialect and command sets in the canonical claim, plus the local and CI commands that exercise each supported combination. Do not describe an out-of-claim expansion as part of this claim. |

- **(decide and record — All slices)** Confirm that the adapter returns
  `status: "unsupported"` with exit `10` for every case command outside the
  claim, while never returning `unsupported` for an in-slice case. Record how
  out-of-claim shape, dialect, module tag, and slice tag are classified. See
  [`m-conformance-adapter.md`](m-conformance-adapter.md).
- **(decide and record — All slices)** Record the case-selection expression used
  for verification. It MUST select the intersection of the active slice tag and
  the relevant capability tags; filename prefixes are not a conformance target.

## 2. Shared developer API and model surface

### Query and operation API

- **(decide and record — All slices)** The finder/query entry point. Show the
  idiomatic spelling of `Order where orderId == 42 and items.sku in ['A','B']`
  and its canonical `m-op-algebra` serialization.
- **(decide and record — All slices)** The single-object find spelling and the
  behavior on no result and multiple results.
- **(decide and record — All slices)** The `group` operator spelling. It MUST
  serialize to the canonical `group` node regardless of surface syntax.
- **(decide and record — All slices)** Deep-fetch/include spelling and how a
  developer declares an eager-fetch navigation set.
- **(decide and record — All slices)** Temporal-read spelling for `asOf`,
  `asOfRange`, and `history`: public axis names, timestamp type and precision,
  Valid-Time / Transaction-Time dimension names, Latest defaults, finite Now,
  timestamp type and precision, and rejection of invalid combinations.
- **(decide and record — When claimed: `m-agg`)** Aggregation result and operation
  spelling for `groupBy`, aggregate functions, and `having`. Also record SQL
  lowering only when `m-sql-agg` is claimed.

### Metadata and model input

- **(decide and record — All slices)** The primary model-authoring format:
  canonical YAML/JSON, annotations/decorators, a builder DSL, or a hybrid. It
  MUST produce an in-memory metamodel that round-trips through canonical JSON
  and YAML serde.
- **(decide and record — All slices)** The runtime introspection API for
  attributes, primary keys, as-of attributes, relationships, inheritance, value
  objects, and name lookup.
- **(decide and record — All slices)** For every neutral scalar type, the
  generated property/read type, create/update input type, adapter bind type, and
  result materialization rule. Cover `int64`, `decimal(p,s)`, `bytes`, and
  `timestamp`, and distinguish wall-clock `date`/`time` from instant semantics.
- **(decide and record — All slices)** Metamodel serde ownership: source owner,
  enforcement scope, deployable artifact, and JSON/YAML round-trip tests.

### Code generation or runtime realization

- **(decide and record — All slices)** Whether code generation, dynamic proxies,
  metaprogramming, reflection, or handwritten classes realize the typed finder
  and object surface, and why.
- **(decide and record — All slices)** If code generation is used, its entry
  point, canonical descriptor inputs, output locations, regeneration command,
  and drift check. Otherwise record how equivalent drift is prevented.
- **(decide and record — All slices)** Which typed artifacts are derivable from
  the canonical descriptor. Do not promise a generated surface for information
  absent from the descriptor schema.

## 3. Object lifecycle profile

Retain exactly one of the following subsections in the completed language spec.

### Snapshot lifecycle

- **(decide and record — Snapshot lifecycle)** The public root result, entity
  node, to-one, and to-many collection types. State when execution occurs and
  how the one materialized plain-value graph is returned.
- **(decide and record — Snapshot lifecycle)** Graph-local identity resolution:
  the `(entity family, primary key, lowered as-of coordinates)` key, shared-node
  reference behavior for diamonds, cycles/back-references, projection merging,
  and the non-identity of value objects. Identity MUST NOT escape one graph.
- **(decide and record — Snapshot lifecycle)** Whole-graph temporal pinning,
  including latest defaults, per-hop axis propagation, and the graph-per-edge-pin
  representation of `history` and `asOfRange`. If
  `snapshot-history-includes` is deferred, say so without rejecting it as an
  invalid operation.
- **(decide and record — Snapshot lifecycle)** The closed-world relationship
  representation: how included to-one and to-many relationships are populated,
  how an unloaded relationship is distinguished from loaded-empty or loaded-null,
  and the defined result of accessing it. Access MUST NOT issue SQL.
- **(decide and record — Snapshot lifecycle)** Eager include execution and graph
  assembly, including one query per non-empty relationship level, empty-level
  behavior, ordering, narrowed views, and the `1 + L` round-trip ceiling.
- **(decide and record — Snapshot lifecycle)** Explicit writes: the create/update/
  delete and temporal-write input types and entry points, and how graph edits are
  kept semantically separate from persistence. A snapshot graph has no change
  tracking or merge-back.

### Managed-object lifecycle

- **(decide and record — Managed-object lifecycle)** The public managed entity,
  single-result, and set-result types, including how managed state is visible or
  intentionally hidden from developers.
- **(decide and record — Managed-object lifecycle)** The unit-of-work-owned
  identity map and exact `(entity family, primary key, lowered as-of coordinates)`
  key. Record inheritance-family normalization, latest lowering, finite pins,
  interning timing for read/application/generated identities, and coexistence of
  distinct pinned views.
- **(decide and record — Managed-object lifecycle)** The operation-backed list
  type and its operation binding, lazy first resolution, stable re-access,
  iteration/index/size/bulk ergonomics, and coalescing through the identity map
  without claiming query-cache round-trip elimination.
- **(decide and record — Managed-object lifecycle)** Eager and deferred
  relationship loading: explicit and any transparent load spellings, batching
  for ad-hoc object sets and coordinate groups, loaded/unloaded state, ordering,
  narrowed views, read-your-own-writes, and the defined Parallax Error raised
  when a detached object attempts a deferred load.
- **(decide and record — Managed-object lifecycle)** Mutation buffering for
  in-memory and persisted objects, implicit or explicit flush, write ordering,
  dependent-read flushing, generated-key transition timing, and deletion state.
- **(decide and record — Managed-object lifecycle)** Commit and abort transitions
  for the `in-memory`, `persisted`, `deleted`, `detached`, and
  `detached-deleted` states. On scope end, held managed objects detach in place;
  abort restores as-materialized values before detaching, discards buffered and
  flushed transactional work, and does not return a callback value as durable.
- **(decide and record — Managed-object lifecycle)** Deliberate detach: deep-copy
  boundaries, relationship state, identity-map separation, offline mutation,
  deletion marking, and `isModifiedSinceDetachment` semantics.
- **(decide and record — Managed-object lifecycle)** Merge-back spelling and the
  inside-unit-of-work rules for update-existing, insert-new, delete-existing,
  unmodified no-op, optimistic conflict, and the returned/re-associated managed
  object.

## 4. Result collections and materialization

Retain the branch matching the lifecycle profile; do not answer both.

### Snapshot results

- **(decide and record — Snapshot lifecycle)** The eager materialized collection
  types and iteration/indexing/bulk ergonomics. Query construction is
  side-effect-free, but explicit execution returns a value; it is not an
  `m-op-list` operation-backed lazy list.
- **(decide and record — Snapshot lifecycle)** How root-empty, relationship-empty,
  relationship-null, unloaded, ordered children, shared prefixes, and graph-local
  shared identity appear in the public result.

### Managed-object results

- **(decide and record — Managed-object lifecycle)** The lazy operation-backed
  collection surface and the access points that trigger resolution. Record the
  type returned by relationship navigation and how already-populated
  relationships avoid re-querying.
- **(decide and record — Managed-object lifecycle)** How root-empty,
  relationship-empty/null/unloaded, ordered children, shared prefixes, and
  identity-map-coalesced objects appear in the public result.

## 5. Transactions and writes

- **(decide and record — All slices)** The transaction demarcation construct.
  Show commit-on-success and rollback-on-exception, and state how callback
  results are withheld when rollback or commit fails.
- **(decide and record — All slices)** Nested/re-entrant transaction behavior,
  owner/concurrency rules, and the selected per-transaction locking or optimistic
  participation mode.
- **(decide and record — All slices)** Buffered/batched write surfacing, flush
  controls, foreign-key ordering, and read-your-own-writes behavior.
- **(decide and record — All slices)** Developer-facing Transaction-Time-Only
  `insert`, `update`, and `terminate`, and Bitemporal `insertUntil`, `updateUntil`,
  and `terminateUntil` names. Record Transaction-Time clock sourcing, Valid-Time
  windows, and precision validation.
- **(decide and record — All slices)** How this surface rests on the object model
  in [§3](#3-object-lifecycle-profile)/[§4](#4-result-collections-and-materialization).
  This section reads as self-contained, but parts of it are not: the participating
  `find` result and the instance-to-write-input derivation an `update` effective
  change set needs both rest on the **materialized object model**, whereas
  demarcation, buffered-write flush, and foreign-key ordering rest only on the
  write/unit-of-work modules. Record which part rests on which, and — when the DAG
  in [`modules.md`](modules.md) places those modules in **different implementation
  milestones** — the surface's **staged realization**: the demarcation and flush
  plumbing that can land before the object-model-dependent write input and read
  output. A milestone MUST NOT be planned to deliver a construct whose constituent
  modules are not all implemented; an interim milestone that lands only the
  plumbing MUST say so, naming the milestone that completes the ergonomic surface.

## 6. Database support and compatibility proof

### Database provider integration

- **(decide and record — All slices)** The test runner and exact discovery/filter
  mechanism for `core/compatibility/cases/**`, including active-slice and module
  tag intersection.
- **(decide and record — All slices)** The development-only provisioning
  mechanism and pinned database image/binary policy. Testcontainers, container
  clients, and embedded test binaries MUST stay out of production artifacts.
- **(decide and record — All slices)** The reset lifecycle: isolation, emptying,
  DDL application, fixture loading, any snapshot optimization and fallback.
- **(decide and record — All slices)** Golden SQL selection for every claimed
  dialect.
- **(decide and record — All slices)** The Docker-free dialect contract suite,
  its one-row-per-database matrix, and coverage of quoting, null ordering, locks,
  types, bytes, infinity, placeholders, binds, and error classification.
- **(decide and record — All slices)** Each real-adapter smoke suite and provider
  contract suite. Cover connection construction, scalar reads, transaction
  callbacks, byte writes, affected rows, feasible transient classification,
  `reset`, `applyDdl`, `loadFixtures`, `query`, `exec`, `execRolledBack`, and any
  independent `peer` connection.
- **(decide and record — All slices)** Named full and partial database matrix
  profiles. A partial profile MUST list exclusions with reasons; absent dialect
  SQL is an explicit exclusion, never a silent skip.
- **(decide and record — All slices)** Exact local and CI commands for fast
  dialect contracts, adapter smoke checks, provider contracts, API conformance,
  and every full/partial matrix profile. Define the visible report produced when
  database-backed checks cannot run.
- **(decide and record — All slices)** Database Error mapping at the port
  boundary, including native code preservation and unsupported/error
  classification.

### Additional dialects

- **(decide and record — When claimed: an additional dialect)** For each
  additional claimed dialect, the dialect strategy,
  separately deployable adapter and driver, case/profile coverage, golden SQL,
  and clean-install proof. If the canonical claim has only its initial dialect,
  delete this subsection and list future dialects as deferred in §1.

### API Conformance Suite and Usage Guide

- **(decide and record — All slices)** The test framework and suite location for
  idiomatic public-API proof against a real database through a shipped adapter.
- **(decide and record — All slices)** The coverage-partition assertion:
  exercised union reasoned-skipped equals the active slice, with no stale IDs and
  no empty skip reasons. Record the no-drift guard tying idiomatic operations to
  corpus operations.
- **(decide and record — All slices)** Usage Guide generation from suite source
  and the CI drift check. The guide and API suite are additive to, not substitutes
  for, conformance-adapter proof.

## 7. Source-enforcement topology

The behavioral-module DAG governs dependencies between source enforcement
scopes even when many scopes live in one source tree or common-runtime artifact.
Complete a row for every claimed module, every unclaimed transitive prerequisite,
and every language support scope. Do not use this table as a deployable-artifact
list.

| Behavioral/support module | Source owner/path | Enforcement scope | Allowed direct dependencies | Enforcement rule/config |
|---|---|---|---|---|
| **(decide and record — All slices)** | | | | |

- **(decide and record — All slices)** The dependency-analysis tool, exact
  configuration path, local command, and blocking CI command. State how the
  configuration is checked against the complete DAG in [`modules.md`](modules.md)
  and how a forbidden direction fails.
- **(decide and record — All slices)** If several enforcement scopes live inside
  one source tree or deployable artifact, the import/namespace/internal-package
  boundaries that keep their directions mechanically distinguishable. Artifact
  co-location MUST NOT make a forbidden source edge legal.
- **(decide and record — All slices)** Database seam scopes for pure dialect
  strategy, abstract `m-db-port`, error classification, each concrete adapter,
  and the composition root. Only the composition root imports a concrete adapter;
  the port imports nothing application-specific.

## 8. Deployable artifact topology

Complete a separate row for every production artifact and development-only
tooling artifact. At minimum this includes one independently deployable,
lifecycle-neutral common runtime; the selected lifecycle extension; and one
separately deployable adapter per supported database.

| Artifact/package | Production or development-only | Included source scopes | External runtime dependencies | Depends on artifacts | Public exports/entry points |
|---|---|---|---|---|---|
| **(decide and record — All slices)** | | | | | |

- **(decide and record — All slices)** The common runtime manifest and proof that
  it depends on neither lifecycle extension nor concrete database driver.
- **(decide and record — All slices)** The selected lifecycle extension manifest
  and proof that it depends downward on common behavior but not a sibling
  lifecycle or concrete adapter.
- **(decide and record — All slices)** Each concrete adapter manifest and proof
  that it alone introduces its matching driver. Record where pure driver-free
  dialect strategies ship.
- **(decide and record — All slices)** The application/test composition root that
  selects the lifecycle extension and adapter without leaking either dependency
  into common runtime code.
- **(decide and record — All slices)** Clean-install and runtime-load checks for:
  common runtime alone; common plus the selected lifecycle; and common plus that
  lifecycle plus one adapter. Each check MUST prove unselected lifecycles,
  adapters, drivers, conformance harnesses, benchmarks, and container tooling are
  absent from the installed and loaded production graph.

## 9. Conditional capability decisions

Delete every subsection whose applicability condition is false and record that
capability as deferred in §1 when appropriate.

### Process cache

- **(decide and record — When claimed: `m-process-cache`)** Process-wide identity
  and query cache scopes, keying, cache-hit behavior, write invalidation,
  transaction interaction, freshness, and public configuration.
- **(decide and record — When claimed: `m-process-cache`)** Cache data structures
  and any key-derived hashing or open-addressing choices. These techniques are
  non-normative; justify them against measurements rather than prior art alone.

### Cross-process coherence

- **(decide and record — When claimed: `m-coherence`)** Invalidation transport,
  delivery/failure policy, freshness boundary, mark-dirty/refetch behavior, and
  identity-preserving refresh across processes.

### Aggregation

- **(decide and record — When both `m-agg` and `m-sql-agg` are claimed)** The
  complete algebra-to-SQL ownership path, aggregate result types, bind ordering,
  numeric/nullable behavior, and API/corpus proof. Partial aggregation claims
  require a separately defined canonical slice.

### Benchmarks and performance targets

- **(decide and record — When claimed: `m-perf-bench`)** Wall-time `p50`/`p95`
  and peak/steady-memory thresholds for every claimed workload family, including
  measurement environment and regression policy.
- **(decide and record — When claimed: `m-perf-bench`)** The benchmark command,
  report-envelope implementation, artifact-copy location, and CI gate. Confirm
  fixture-defined round-trip expectations remain normative.
- **(decide and record — When claimed: `m-perf-bench`)** Any language-specific
  result-interchange or optimized collection technique and the evidence for it.

## 10. Mandatory quality toolchain

Every row is mandatory. Name executable tools rather than categories, and give
exact repository-relative config paths and copy-pasteable commands. A completed
row cannot say only “the ecosystem default” or “run in CI.” Every CI gate is
blocking unless its policy cell defines a narrower, objective exception.

| Quality concern | Tool and version policy | Configuration path(s) | Local command | Blocking CI command/job | Threshold, exclusions, and enforcement policy |
|---|---|---|---|---|---|
| Dependency directions within and across artifacts | **(decide and record — All slices)** | | | | Include DAG drift and wrong-direction failure policy. |
| Unit tests | **(decide and record — All slices)** | | | | Define unit/integration boundary and failure policy. |
| Code coverage | **(decide and record — All slices)** | | | | Give an explicit numeric threshold, metric, generated/vendor exclusions, and no-new-uncovered-code policy. |
| Linting | **(decide and record — All slices)** | | | | List enabled rule sets and suppression policy. |
| Deterministic formatter check | **(decide and record — All slices)** | | | | CI MUST check without rewriting; name the write command separately. |
| Strict static typing | **(decide and record — All slices)** | | | | Enable ecosystem strict mode across production and tests; Python MUST use a strict Pyright- or mypy-style policy. List and justify exclusions. |
| Import-cycle detection | **(decide and record — All slices)** | | | | Cover all production source scopes. |
| Dead code and unused exports | **(decide and record — All slices)** | | | | If ecosystem tooling cannot check one class, state the limitation, evidence, and compensating check. |
| Built-artifact and public-export health | **(decide and record — All slices)** | | | | Inspect packed artifacts, entry points, types/metadata, and accidental files/exports. |
| Clean-install production smoke tests | **(decide and record — All slices)** | | | | Exercise every selective topology from §8 in clean environments. |
| Supported language/runtime versions | **(decide and record — All slices)** | | | | List the exact version matrix, minimum policy, and end-of-life policy. |
| Dependency and supply-chain audit | **(decide and record — All slices)** | | | | Define lockfile/freshness policy, severity threshold, exception owner, expiry, and provenance/license checks if used. |
| Compatibility Conformance Suite | **(decide and record — All slices)** | | | | Select active slice ∩ capability tags and validate adapter envelopes. |
| API Conformance Suite and Usage Guide | **(decide and record — All slices)** | | | | Enforce coverage partition, no-drift guard, real-adapter proof, and guide drift. |
| Database-backed verification | **(decide and record — All slices)** | | | | Name required profiles and define how every skipped check is reported with reason; silent skips are forbidden. |

- **(decide and record — All slices)** The single local static-verification
  command and CI job that aggregate all database-free rows above.
- **(decide and record — All slices)** The full verification command and CI lane,
  including database-backed checks, plus the exact summary format for checks that
  were run, failed, or skipped.

## Completion check

A finished language spec satisfies every item:

- no **(decide and record)** marker or blank required table cell remains;
- exactly one §3 lifecycle profile and its matching §4 result branch remain, and
  every instruction for the unselected profile has been removed;
- the selected slice exists in `slices.md`, is lifecycle-complete rather than
  deprecated, and the recorded `describe` envelope equals its canonical claim
  except for `adapter` identity;
- claimed capability coverage is the canonical tagged-case union, while every
  transitive unclaimed prerequisite and every explicit deferral is listed
  separately;
- every developer-surface construct that composes modules the DAG places in
  different implementation milestones records its staged realization, so no
  milestone is planned to deliver a surface whose constituent modules are not all
  implemented;
- conditional sections exist exactly when their applicability condition is true;
- the source-enforcement map covers all claimed modules, transitive prerequisites,
  and support scopes and gives a mechanically enforceable legal DAG;
- the artifact map contains an independent common runtime, exactly the retained
  lifecycle extension, and separate selected database adapters, with manifests
  and selective clean-install proofs that exclude alternatives and development
  tooling;
- every mandatory quality row names a tool, config, local command, blocking CI
  command/job, and concrete enforcement policy; coverage has a numeric threshold,
  strict typing is explicit, and database skips cannot be silent; and
- a fresh reader can implement the language and run both conformance surfaces
  without inventing a lifecycle, source-boundary, packaging, or tooling decision.
