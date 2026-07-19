# Parallax

Parallax is a language-neutral specification and executable compatibility
corpus for building feature-rich object-relational mappers. The core defines
observable behavior—data modeling, queries, SQL, transactions, temporal
semantics, and object materialization—while each language target is free to
offer an idiomatic developer API and implementation architecture.

That separation makes multiple implementations possible without reducing
portability to a lowest-common-denominator interface. A target selects a named
**Conformance Slice**, records its language-specific decisions, and proves the
claim by compiling and running the shared corpus against real databases.

Parallax is informed by the bitemporal ORM
[Reladomo](https://github.com/goldmansachs/reladomo). It follows Reladomo's
runtime semantics where the core spec adopts them, while expressing the
contract independently of Java or any other host language.

## What Parallax Covers

Parallax focuses on the parts of ORM behavior that are difficult to reproduce
consistently across languages:

- **Temporal data:** processing-time audit histories, full bitemporal business
  and processing axes, latest and as-of reads, history and range queries, and
  bounded corrections implemented as rectangle splits.
- **Expressive queries and object graphs:** composable predicates, grouping,
  ordering, limits, relationship navigation and existence tests, eager deep
  fetch, subtype narrowing, and whole-graph temporal pinning. Canonical SQL,
  bind order, and round-trip counts are part of the observable contract.
- **Efficient, correct writes:** a unit of work buffers writes, coalesces or
  cancels compatible changes, batches DML, orders it around dependencies, and
  flushes when read-your-own-writes requires it. The contract also covers read
  locks, optimistic conflicts, bounded retry, and rollback-only behavior.
- **Rich modeling:** relationships, generated primary keys, nested value
  objects, and closed inheritance families mapped with
  table-per-hierarchy or table-per-concrete-subtype strategies.
- **Portable proof:** schemas and compatibility cases pin the neutral model and
  operation forms, emitted SQL, returned rows and graphs, final table state,
  errors, and concurrency observations. Implementations are graded against the
  same evidence rather than against another implementation's internals.

Capability modules remain independently specified, and named slices compose
them into honest implementation-sized claims. Deferred areas are explicit in
the [module catalog](core/spec/modules.md) and
[slice catalog](core/spec/slices.md).

## Python: The Primary Worked Example

[`languages/python/`](languages/python/) implements the complete
[`slice-snapshot-1`](core/spec/slices.md#snapshot-conformance-slice) claim for
Postgres. It is Python-first and SQLModel-inspired: developers declare
Pydantic-based entity classes, build typed expressions from those classes, and
receive fully materialized `Snapshot[T]` results made from frozen instances of
their own entity types.

The Snapshot lifecycle executes a query once and returns a closed, immutable
object graph. Included relationships are eager, graph-local identity preserves
shared nodes and cycles, temporal coordinates pin the whole graph, and
accessing an unloaded relationship never issues surprise SQL. Explicit
transactions provide buffered and batched writes, optimistic and locking
modes, retry, primary-key generation, inheritance routing, JSON-backed value
objects, and audit-only and bitemporal write verbs through the Postgres adapter.

The implementation is split into a lifecycle-neutral core, the Snapshot
extension, the psycopg Postgres adapter, and development-only conformance
tooling. Start with the document that matches what you want to learn:

- [Python Usage Guide](languages/python/docs/usage-guide.md) — tested examples
  of the public API, generated from the API Conformance Suite.
- [Completed Python language spec](languages/python/spec/python.md) — exact API,
  lifecycle, packaging, database, and quality-toolchain decisions.
- [Python operational guide](languages/python/GUIDE.md) — layout, commands,
  database setup, implementation status, and blockers.

The TypeScript implementation remains available under
[`languages/typescript/`](languages/typescript/README.md). Its current
`slice-mvp-1` claim is deprecated in favor of the lifecycle-complete Snapshot
and managed-object slices.

## How The Contract Fits Together

Parallax has three layers of authority:

1. **The core specification** defines language-neutral behavioral modules,
   their legal dependency graph, and the deployable seams implementations must
   preserve.
2. **Schemas and the compatibility corpus** encode canonical descriptors,
   fixtures, operations, writes, optimized SQL, independent reference SQL, and
   expected observations.
3. **A completed language spec** chooses the idiomatic public API, lifecycle,
   source layout, artifacts, database integration, and quality toolchain for
   one exact slice.

Each implementation proves its claim in two complementary ways:

- The **conformance adapter** exposes `describe`, `compile`, and `run`; its SQL
  and observations are compared directly with the corpus.
- The **API Conformance Suite** drives the idiomatic developer API through the
  shipped database adapter and renders a tested Usage Guide.

The Python reference harness validates that the core artifacts are internally
consistent and executes their authored SQL against real databases. It is not
an ORM and its internals are non-normative; language implementations bind to
the spec, schemas, corpus, and conformance-adapter contract.

## Repository Map

| Path | Purpose |
| --- | --- |
| [`core/spec/`](core/spec/) | Behavioral modules, dependency graph, slice catalog, and language-spec template |
| [`core/schemas/`](core/schemas/) | JSON Schemas for models, operations, cases, writes, and conformance envelopes |
| [`core/compatibility/`](core/compatibility/) | Canonical models, fixtures, cases, and benchmark workloads |
| [`languages/python/`](languages/python/) | Primary worked implementation: the Postgres Snapshot slice |
| [`languages/typescript/`](languages/typescript/) | TypeScript implementation and generated developer API |
| [`reference-harness/`](reference-harness/) | Non-normative oracle that validates and executes the core corpus |
| [`docs/adr/`](docs/adr/) | Cross-cutting architecture decisions |
| [`IMPLEMENTING.md`](IMPLEMENTING.md) | End-to-end playbook for specifying and building a language target |
| [`justfile`](justfile) | Root orchestration for validation and implementation checks |

## Running And Inspecting The Project

Run commands from the repository root. Inspect the exact capabilities and case
membership of the Python claim:

```bash
just core-slice-inspect slice-snapshot-1
```

Run database-free repository and Python checks:

```bash
just lint
just core-dep-graph
just python-static
```

Run the Python implementation against its pinned Testcontainers Postgres:

```bash
just python-verify
```

Run the reference oracle or the complete repository merge gate:

```bash
just oracle-test
just verify
```

Docker must be available for database-backed commands. Use `just --list` for
the full command catalog.

## Extending Parallax

The workflows below are intentionally brief. Their linked documents remain the
source of truth for sequencing and detailed requirements.

### Define A Conformance Slice

A slice is an exact, named compatibility-corpus claim—not a package plan or a
new module tier. Define its canonical `describe` envelope in
[`core/spec/slices.md`](core/spec/slices.md), tag every included case
explicitly, and let the profile gate derive and verify the capability union.
Only the slice catalog names slices; behavioral module specs remain independent
of who claims them.

Inspect and verify the result with:

```bash
just core-slice-inspect <slice-name>
just core-dep-graph
```

### Build A Language Implementation

Follow [`IMPLEMENTING.md`](IMPLEMENTING.md) rather than copying an existing
runtime. In outline:

1. Read the core overview, module catalog, slice catalog, conformance-adapter
   contract, and language-spec template in their prescribed order.
2. Select one canonical slice and complete a language spec with no unresolved
   decisions before writing runtime code.
3. Implement in module-dependency order, keeping the required runtime,
   lifecycle, and database-adapter seams.
4. Prove the claim through both the conformance adapter and the idiomatic API
   Conformance Suite against a real database.

Validate a completed language spec with:

```bash
just core-language-spec-check languages/<target>/spec/<spec>.md
```

### Add Or Change Core Behavior

Treat the spec, schemas, fixtures, and cases as one contract. A behavioral
change normally requires a consistent update across the relevant module spec,
serialized schemas, canonical descriptors or fixtures, and compatibility
cases. Cases should carry every module tag they exercise and should include
canonical statements, binds, expected observations, and independent reference
SQL where the behavior is non-trivial.

Use the [module catalog](core/spec/modules.md),
[case-format specification](core/spec/m-case-format.md), and existing corpus
shapes as the authoring references. Add benchmark coverage when a change makes
performance characteristics such as query shape, round trips, write shape, or
memory part of the claim, then run the smallest relevant gates followed by
`just verify` when feasible.

## License

Copyright 2026 David Lee.

Licensed under the [Apache License, Version 2.0](LICENSE).
