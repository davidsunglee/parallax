# Parallax

Parallax is a language-neutral specification and compatibility suite for
object-relational mapper implementations.

It defines observable behavior in documents, schemas, fixtures, and
executable compatibility cases. A reference harness is provided to
demonstrate those artifacts are internally consistent against real databases.

The feature set is derived from the bitemporal object-relational mapper
[Reladomo](https://github.com/goldmansachs/reladomo).

This repository is data- and contract-first. The root package provides project
tooling. Language implementations live beside `core/` under `languages/` and
prove conformance by running the same suite; the TypeScript implementation in
`languages/typescript/` is the first worked example.

## Repository Map

```text
core/
  spec/                 Normative modules, scope tiers, dependency graph
  schemas/              JSON Schemas for descriptors, operations, and cases
  compatibility/
    models/             Canonical entity descriptors
    fixtures/           Input rows used by compatibility cases
    cases/              Read, write, scenario, conflict, and coherence cases
    benchmarks/         M13 benchmark workloads and generated datasets
reference-harness/      Python runner that validates and executes the suite
languages/
  typescript/           First language implementation (idiomatic API + adapter)
docs/adr/               Architecture decision records
IMPLEMENTING.md         Playbook for building a language implementation
justfile                Common verification commands
package.json            Markdown, commit, and repo-level developer tooling
```

## Functional Walkthrough

### 1. Start with the specification

`core/spec/` is the behavioral contract. It is split into modules so an
implementation can adopt functionality in a defensible order:

| Area | What it defines |
| --- | --- |
| M0 Core conventions | Neutral scalar types, UTC timestamps, JSON value objects, and temporal infinity handling |
| M1 Metamodel | Entity descriptors, attributes, relationships, indices, inheritance, temporal dimensions, and primary-key generation |
| M2 Operation algebra | A serialized query and mutation algebra above SQL |
| M3 SQL contract | Canonical SQL shape, binds, aliases, per-dialect differences, and equivalence rules |
| M4 Relationships/deep fetch | Relationship navigation, correlated `exists`, and bounded deep-fetch query plans |
| M5 Lists/bulk behavior | Operation-backed lazy lists, deferred bulk work, and cascade behavior |
| M7 Temporal behavior | Milestoned reads, audit-only writes, two-axis temporal writes, and business-temporal-only cases |
| M8 Transactions/cache | Unit of work, identity cache, query cache, invalidation, batching, and shared read locks |
| M9 Lifecycle/detach | Object states, detached copies, merge-back, detached inserts, and detached deletes |
| M10 Optimistic locking | Version columns, conflict detection, affected-row checks, and retry contracts |
| M11 Dialect seam | The boundary for Postgres, MariaDB, and future database providers |
| M12 Compatibility harness | The executable case format and assertion model |
| M13 Performance | Repeatable benchmark datasets, workloads, and report shape |
| Coherence | Multi-process cache invalidation expectations over a shared database |

`core/spec/modules.md` is the module catalog — each module's status
(`active` / `deferred`) and the normative module DAG — checked by the harness
tooling so coverage cannot drift away from the published catalog.
`core/spec/slices.md` declares the slices that compose modules into deliverables.

### 2. Describe the domain with models

`core/compatibility/models/*.yaml` contains canonical descriptors that exercise
the spec:

- `account.yaml` covers a simple versioned entity used by cache, transaction,
  batching, and optimistic-locking cases.
- `orders.yaml` defines `Order`, `OrderItem`, and `OrderStatus`, including
  one-to-many relationships for navigation and deep fetch.
- `balance.yaml` models audit-style temporal rows with processing milestones.
- `position.yaml` models two temporal axes for rectangle-split write behavior.
- `payment.yaml` covers table-per-hierarchy inheritance with a discriminator.
- `customer.yaml` covers JSON-backed value objects and nested attribute access.
- `document.yaml` and `reservation.yaml` cover additional descriptor shapes used
  by later compatibility cases.

The metamodel is validated by `core/schemas/metamodel.schema.json`. It gives
each implementation a stable input format before any language-specific API or
code generation exists.

### 3. Express behavior as operations

`core/schemas/operation.schema.json` defines a single-key tagged operation
algebra. Cases use that algebra for predicates, ordering, limits, relationship
navigation, deep fetch, aggregation, temporal reads, and history/range queries.

The operation layer is intentionally above SQL. Implementations should map their
native API to this algebra, then prove that the resulting behavior matches the
same case data.

### 4. Lock behavior down with compatibility cases

`core/compatibility/cases/` is the executable behavior suite. Each case combines
a descriptor, an operation or write sequence, canonical SQL, expected rows or
table state, and optional reference SQL.

The case families are numbered by topic:

- `00xx` and `02xx`: basic reads and predicate algebra.
- `03xx`: relationship navigation and deep fetch.
- `04xx`: aggregation and grouped results.
- `05xx`: audit temporal reads and writes.
- `06xx`: transactions, identity cache, query cache, read locks, and batched
  writes.
- `07xx`: detach/merge and optimistic-locking conflicts.
- `08xx`: two-axis and business-temporal behavior.
- `09xx`: inheritance and JSON value objects.
- `10xx`: MariaDB dialect coverage.
- `11xx`: cross-process coherence.

The compatibility case schema supports five top-level shapes:

- `read`: execute canonical SQL, compare rows, and optionally compare
  `referenceSql`.
- `writeSequence`: run ordered write statements and compare final table state.
- `scenario`: model transactions, cache hits, identity checks, and round trips.
- `conflict`: apply a precondition, execute a write, and assert affected rows.
- `coherence`: use two database connections to observe cross-process behavior.

Every read case follows the same triple oracle:

```text
rows(goldenSql + binds) == expectedRows
rows(referenceSql + binds) == expectedRows
normalize(goldenSql) is canonical for the dialect
```

Deep-fetch cases extend this by asserting a bounded number of SQL statements and
an `expectedGraph`, not just flat rows.

### 5. Run cases through the reference harness

`reference-harness/` is a Python implementation of the M12 harness. It is not an
ORM and it does not compile operations into SQL. Its job is to verify that the
spec artifacts are coherent.

The reference harness's internals are non-normative and
MUST NOT be used as design input for a language implementation; the binding
inputs are the spec modules, `core/schemas/`, the compatibility corpus, and the
conformance-adapter contract.

For each case the harness:

1. Validates the descriptor, operation, and case JSON/YAML against schemas.
2. Derives test DDL from the descriptor.
3. Loads the requested fixture rows.
4. Executes the authored canonical SQL against a real database provider.
5. Executes `referenceSql` when present.
6. Compares rows, graphs, table state, affected rows, round trips, and cache or
   identity expectations.
7. Checks SQL normalization and deterministic descriptor/operation serde.

Database-specific behavior is isolated behind the provider seam in
`reference-harness/src/reference_harness/providers/`. The built-in providers cover
Postgres and MariaDB through Testcontainers, including type mapping, temporal
infinity handling, bind translation, JSON values, read-lock syntax, and peer
connections for coherence cases.

### 6. Use benchmarks as executable performance contracts

`core/compatibility/benchmarks/` contains M13 benchmark definitions. They reuse
the same models, SQL conventions, and provider seam as cases, but report timing
and resource measurements instead of pass/fail row equivalence alone.

Current benchmark files cover generated account reads, range reads,
aggregations, deep-fetch workloads, and milestone writes. The benchmark runner
emits a JSON report with workload name, dialect, dataset, iterations, p50/p95
latency, round trips, memory, and row counts.

## Common Commands

Run from the repository root:

```bash
just lint
```

Validate schemas, SQL shape, and the module dependency graph:

```bash
just core-dep-graph
```

Run the compatibility suite against available database providers:

```bash
just oracle-test
```

Run all verification gates:

```bash
just verify
```

Generate the provider/case matrix:

```bash
just matrix
```

Provider selection is controlled by `PARALLAX_DATABASES`. For example:

```bash
PARALLAX_DATABASES=postgres just oracle-test
PARALLAX_DATABASES=postgres,mariadb just matrix
```

The harness currently expects Docker-compatible Testcontainers access for the
database-backed commands.

## Adding Or Changing Behavior

Use this path when extending the repository:

1. Update or add the normative module text in `core/spec/`.
2. Update JSON Schemas when the serialized contract changes.
3. Add or adjust descriptors in `core/compatibility/models/`.
4. Add fixtures only when the case cannot reuse existing rows.
5. Add compatibility cases with canonical `goldenSql`, binds, and expected
   observations.
6. Add benchmark coverage when the behavior changes query shape, write shape,
   round trips, or memory use.
7. Run `just verify` before relying on the change.

When adding a dialect, implement a new provider behind the M11 seam and add a
new `goldenSql.<dialect>` entry to cases and benchmarks that need dialect-
specific SQL.

## Building A Language Implementation

Building an idiomatic Parallax for a new language starts by declaring a
**Conformance Slice**: the subset of the compatibility corpus this first build
claims right now, captured as a machine-readable `describe` claim (see
[`core/spec/slices.md`](core/spec/slices.md)). A slice is
case-granular — it may claim some features of a module while deferring others,
without redefining that module's boundary — so an early build can commit to
exactly what it can honestly prove.

The declared slice is then proven two ways, and both are official deliverables:

- the wire-level **conformance-adapter grade** in
  [`core/spec/m-conformance-adapter.md`](core/spec/m-conformance-adapter.md)
  — the SQL and observations your adapter emits, compared against the corpus
  oracles; and
- the developer-surface **API Conformance Suite** and its rendered **Usage
  Guide** in
  [`core/spec/m-api-conformance.md`](core/spec/m-api-conformance.md)
  — the idiomatic code an application writes, run through the shipped adapter
  against a real database, reproducing the corpus's results.

Both prove the same slice while each language builds its own idiomatic public
API. [`IMPLEMENTING.md`](IMPLEMENTING.md) is the step-by-step playbook: it lays
out the reading order, planning deliverables, implementation sequence,
verification ladder, and completion checklist that carry you from the shared
contract to a conforming target.

## Current Status

The core spec, schemas, compatibility suite, benchmark definitions, and
reference harness exist now. The suite already models descriptor validation,
operation serde, SQL canonicalization, real database execution, deep-fetch graph
assembly, temporal write expectations, cache and identity scenarios,
optimistic-lock conflicts, dialect differences, and cross-process coherence.

The TypeScript implementation in
[`languages/typescript/`](languages/typescript/README.md) is the first worked
example: it declares the canonical `slice-mvp-1` Conformance Slice and proves it
with both official artifacts. Further language implementations should treat
`core/` as the shared contract and use `reference-harness/` as the executable
oracle. See
[Building A Language Implementation](#building-a-language-implementation) for the
slice-first process and its two official proof artifacts.
