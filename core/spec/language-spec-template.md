# Language-Spec Template

This is the **checklist every per-language spec must pin down** before an
implementation begins. The core spec (`M0`–`M14`) fixes
the *language-neutral* contract — observable behavior, the protocol seams, the
module-dependency graph. It deliberately leaves the *developer-facing surface* —
API shape, configuration ergonomics, whether codegen is used — to each language.
This template is the boundary list: fill in every section and an agent can author
an implementation that passes the compatibility suite **without re-reading the
whole core spec**.

> **How to use this.** Copy this file into `<language>/spec/` and replace every
> *(decide and record)* with the language's concrete answer plus a one-line
> rationale. A section left blank is a gap an implementer will have to guess at —
> which is exactly the failure this template exists to prevent. Nothing here may
> contradict the core spec or the normative module-dependency graph
> ([`dependency-graph.md`](dependency-graph.md)); this template only fills in the
> non-normative, per-language choices the core spec leaves open (DQ3).

## 1. API surface (non-normative — DQ3)

The shape of the developer-facing API is **per-language and non-normative**. The
core mandates only the *canonical operation algebra* (`M2`) and its serde; how a
developer *spells* an operation in this language is a DX choice.

- **(decide and record)** The finder/query entry point: how does a developer
  start an operation (`OrderFinder.orderId().eq(42)` fluent builder, a function,
  a query DSL, …)? Show the idiomatic spelling of the running example
  `Order where orderId == 42 and items.sku in ['A','B']`.
- **(decide and record)** Result types: what does a `findMany` return (a lazy
  operation-backed list per `M5`, an iterator, a materialized collection)? How is
  a single-object find spelled, and what happens on not-found / multiple?
- **(decide and record)** The `group` operator surface (`M2`): prefix
  `group(a.or(b)).and(c)` vs. fluent `a.or(b).group().and(c)`. Both **MUST**
  serialize to the same canonical `group` node; the surface choice is yours.
- **(decide and record)** Deep-fetch spelling (`M4`): how a developer declares
  the eager-fetch navigation set on a query.
- **(decide and record)** Aggregation spelling (`M2` sub-area): `groupBy` /
  aggregate-function / `having` surface.
- **(decide and record)** Temporal read spelling (`M7`): how a developer
  requests a point-in-time read (`asOf`), a range/edge-point read (`asOfRange` in
  core), and full history (`history`). Record the public axis names for
  processing and business time, the runtime timestamp type and precision boundary
  from `M0`, how `now` / omitted axes are represented, and how invalid
  combinations are rejected (for example, point and history on the same axis).

## 2. Metadata / model input format (DQ5, DQ6)

The metamodel is a **mandated protocol** (introspection **and** serde); the
canonical descriptor (`metamodel.schema.json`) is its serialized form. **How a
developer authors a domain model** is the per-language choice.

- **(decide and record)** Primary authoring format: the canonical YAML/JSON
  descriptor directly, language-native **annotations/decorators**, a builder DSL,
  or a hybrid. Whatever the surface, it **MUST** produce an in-memory metamodel
  that round-trips through the canonical serde (JSON **and** YAML).
- **(decide and record)** Introspection API: how a program reads the metamodel at
  runtime (attribute list, primary-key attributes, as-of attributes, relationship
  finders, attribute-by-name) — the `RelatedFinder` / `ReladomoClassMetaData`
  analogue.
- **(decide and record)** M0 scalar runtime mapping: for every neutral scalar
  type, specify the language's generated property/read type, create/update input
  type, adapter bind type, and result materialization rule. The mapping MUST
  cover precision-sensitive values (`int64`, `decimal(p,s)`, `bytes`,
  `timestamp`) and distinguish wall-clock `date` / `time` from instant
  `timestamp` semantics.
- **(decide and record)** Serde module: the dedicated package whose sole job is
  metamodel serialize/deserialize, with **round-trip
  (serialize → deserialize → serialize) tests** in both JSON and YAML.

## 3. Transaction-block demarcation (M8)

The transaction **boundary** is **user-specified per-language and never expressed
in raw SQL** in the core spec. Pin down the idiom.

- **(decide and record)** The demarcation construct: a **closure**
  (`inTransaction { … }`), a **context manager** (`with transaction(): …`), a
  **decorator** (`@transactional`), or several. Show commit-on-success and
  rollback-on-exception semantics.
- **(decide and record)** How nested / re-entrant transactions behave.
- **(decide and record)** How the unit of work surfaces buffered/batched writes
  to the developer (implicit flush at commit vs. explicit flush).
- **(decide and record)** Temporal write spelling (`M7`): the developer-facing
  names for audit-only `insert` / `update` / `terminate`, the full-bitemporal
  `insertUntil` / `updateUntil` / `terminateUntil` trio, and any language-specific
  aliases (for example, `createUntil` if ordinary insert is spelled `create`).
  Record where processing instants come from, how business start/window options
  are passed, and which timestamp precision validation applies.

## 4. Test-double integration (M12, DQ15)

The compatibility suite is the **primary behavioral surface**; most tests bubble
up to it rather than living in per-language units. Pin down how the language's
test runner wires to the **database provider**.

- **(decide and record)** Test runner: `pytest` / JUnit / `cargo test` /
  `vitest` / … and how a suite run discovers and executes
  `core/compatibility/cases/**`.
- **(decide and record)** Provisioning mechanism: **Testcontainers** (the default
  — first-class across JVM / Python / Node / Go / Rust / .NET, so the *same
  substrate everywhere*) pinned to the latest-stable-major Postgres image, or an
  **embedded binary** that satisfies the same clean / migrated / isolated
  reset contract. Either way it sits behind the same provider seam.
- **(decide and record)** The provider reset lifecycle: the exact mechanism that
  returns the database to an empty, isolated state before a database-backed case,
  when DDL is applied, and when fixtures are loaded. If the implementation uses a
  snapshot/restore optimization, name the concrete package API, version
  assumptions, and fallback reset path; do not assume a portable Testcontainers
  snapshot API exists across languages or database modules.
- **(decide and record)** Which dialects this language runs in CI (Postgres is
  the round-1 normative target; MariaDB is the proven second dialect) and how the
  per-dialect golden SQL is selected.

## 5. Codegen-or-not (DQ5)

Code generation is a **per-language technique, never a mandate.** The metamodel
is mandated; *how* the in-memory model and the typed surface are produced is open.

- **(decide and record)** Whether the implementation uses **codegen**, **dynamic
  proxies / metaprogramming**, **reflection**, or **hand-written** classes to
  realize the typed finder/object surface from the metamodel — and why.
- **(decide and record)** If codegen: the generator entry point, its inputs (the
  canonical descriptor), and where generated artifacts live / how they are
  regenerated.
- **(decide and record)** Which generated artifacts are derivable from the
  canonical descriptor and which are intentionally absent. Do not promise
  generated enum types, structured value-object types, field-level value-object
  paths, or other typed surfaces unless the core descriptor schema contains the
  data needed to generate them.

## 6. Collection idioms (M5)

- **(decide and record)** The concrete collection type a list result exposes
  (the language's idiomatic lazy/eager collection), and how laziness +
  query-backing (`M5`) is surfaced.
- **(decide and record)** Iteration, indexing, and bulk-operation ergonomics on
  list results.

## 7. Build-time dependency enforcement (DQ3, dependency-graph)

The normative module-dependency graph is **MUST** in core; each language
**SHOULD** enforce it mechanically at build time so a wrong-direction edge fails
the build.

- **(decide and record)** The enforcement tool and its config. Ecosystem
  examples: `import-linter` / `tach` (Python), **ArchUnit** or Gradle module
  boundaries (Java), `dependency-cruiser` / `eslint-plugin-boundaries`
  (TypeScript), **crate boundaries + visibility** (Rust).
- **(decide and record)** The mapping from the core modules (`M0`–`M14`) onto
  this language's packages/modules/crates, any non-numbered support packages
  required by the language topology, and the contract that encodes the legal
  edges (the same numbered-module DAG as
  [`dependency-graph.md`](dependency-graph.md), plus any explicitly documented
  support-package edges).

## 8. Optional optimized data structures (M13, DQ10)

These are **optional, non-normative** levers for hitting performance targets —
enumerated so an implementer knows the proven techniques exist, not so they must
use them.

- **(decide and record, optional)** Whether to use **open-addressing map/set**
  analogues (`UnifiedMap` / `UnifiedSet`) for the identity / query caches.
- **(decide and record, optional)** Whether to use a **key-derived hashing**
  analogue (`HashingStrategy`) to index domain objects by a *derived* (e.g.
  composite-primary) key without allocating wrapper key objects.
- **(decide and record, optional)** Any language-specific result-interchange
  technique (e.g. Apache Arrow in Python) — wholly per-language; the core spec
  makes no Arrow mandate or seam (DQ12).

## 9. Per-language performance targets (M13, DQ10)

The benchmark **fixtures and the measurement protocol** are shared and normative
(`M13`); the **numeric ceilings are per-language placeholders** — a Rust target is
not a Python target.

- **(decide and record)** Wall-time targets (`p50` / `p95`) per benchmark
  workload family (operation mix, deep-fetch shapes, milestone writes,
  aggregation).
- **(decide and record)** Memory targets (peak / steady resident set).
- **(decide and record)** Round-trip expectations are **already fixed** by the
  fixtures' `expectRoundTrips` (a deep fetch is `1 + levels`, never N+1) — confirm
  the implementation honors them; they are not a per-language placeholder.
- **(decide and record)** How `parallax-conformance benchmark` emits the M13
  report shape fixed by `m13-performance.md` and
  `conformance-adapter-contract.md`: the adapter stdout envelope carries
  `report.generatedAt`, `report.benchmarks[]`, and `report.memory`, while any
  local `report.json` file is only an artifact copy.

## Completion check

A finished language spec has **no remaining *(decide and record)* markers**, never
contradicts the core spec or the dependency graph, and is sufficient for an agent
to author an implementation and run the compatibility suite to green — the test in
the outline's manual-verification step: *hand it to a fresh reader and confirm it
is sufficient without re-reading the whole core spec.*
