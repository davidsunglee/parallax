# Parallax

Parallax is a language-neutral specification and compatibility suite for
object-relational mapper implementations.

It defines observable behavior in documents, schemas, fixtures, and
executable compatibility cases. A reference harness is provided to
demonstrate those artifacts are internally consistent against real databases.

The feature set is derived from the bitemporal object-relational mapper
[Reladomo](https://github.com/goldmansachs/reladomo).

This repository is data- and contract-first. The root package provides project
tooling. Future language implementations are forthcoming. They will live beside
`core/` and prove conformance by running the same suite.

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

`core/spec/scope-and-tiers.md` marks each capability as MVP, fast-follow,
definitely-do, might-do, or won't-do. `core/spec/dependency-graph.md` gives the
normative module DAG and is checked by the harness tooling, so coverage cannot
drift away from the published scope.

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
`reference-harness/parallax_harness/providers/`. The built-in providers cover
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
just dep-graph
```

Run the compatibility suite against available database providers:

```bash
just test
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
PARALLAX_DATABASES=postgres just test
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

## Current Status

The core spec, schemas, compatibility suite, benchmark definitions, and
reference harness exist now. The suite already models descriptor validation,
operation serde, SQL canonicalization, real database execution, deep-fetch graph
assembly, temporal write expectations, cache and identity scenarios,
optimistic-lock conflicts, dialect differences, and cross-process coherence.

Future language implementations should treat `core/` as the shared contract and
use `reference-harness/` as the executable oracle. They prove implementation
conformance through the adapter contract in
`core/spec/conformance-adapter-contract.md` while building their own public APIs.
