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
  spec/                 Normative modules, dependency graph, and slices
  schemas/              JSON Schemas for descriptors, operations, and cases
  compatibility/
    models/             Canonical entity descriptors
    fixtures/           Input rows used by compatibility cases
    cases/              Read, write, scenario, conflict, and coherence cases
    benchmarks/         Performance benchmark workloads and generated datasets
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

`core/spec/` is the behavioral contract. It is split into **modules**, each named
by a descriptive `m-<slug>` identifier and defined in its own file. Grouped by
area:

| Area | Modules |
| --- | --- |
| Core conventions | `m-core` |
| Metamodel | `m-descriptor`, `m-pk-gen`, `m-inheritance`, `m-value-object` |
| Query & SQL | `m-op-algebra`, `m-sql` (aggregation `m-agg` / `m-sql-agg` deferred) |
| Relationships | `m-navigate`, `m-deep-fetch` |
| Lists & bulk | `m-op-list`, `m-batch-write`, `m-cascade-delete` |
| Transactions | `m-unit-work`, `m-read-lock`, `m-auto-retry` (`m-process-cache` deferred) |
| Temporal | `m-temporal-read`, `m-audit-write`, `m-bitemp-write` (`m-business-only` deferred) |
| Lifecycle & locking | `m-detach`, `m-opt-lock` |
| Database seam | `m-dialect`, `m-db-port`, `m-db-error` |
| Conformance & performance | `m-case-format`, `m-conformance-adapter`, `m-api-conformance`, `m-perf-bench` (`m-coherence` deferred) |

A module names a *behavior*, not a package: a language MAY group many modules into
one package as long as it enforces the dependency graph. `core/spec/modules.md`
is the authoritative catalog — every module's status (`active` / `deferred`), its
coverage source, and the normative module dependency graph — checked by the
harness tooling so coverage cannot drift. `core/spec/slices.md` declares the
slices that compose modules into deliverables.

### 2. Describe the domain with models

`core/compatibility/models/*.yaml` contains canonical descriptors that exercise
the spec:

- `account.yaml` covers a simple versioned entity used by cache, transaction,
  batching, and optimistic-locking cases.
- `orders.yaml` defines `Order`, `OrderItem`, and `OrderStatus`, including
  one-to-many relationships for navigation and deep fetch.
- `balance.yaml` models audit-style temporal rows with processing milestones.
- `position.yaml` models two temporal axes for rectangle-split write behavior.
- `payment.yaml` and `animal.yaml` cover `table-per-hierarchy` inheritance —
  closed entity trees mapped to one shared table and discriminated by a `tag`
  column that carries each concrete subtype's `tagValue`; `animal.yaml` adds an
  abstract subtype, a concrete sibling branch, and polymorphic owner
  relationships for subtype narrowing, navigation, and deep fetch.
- `customer.yaml` covers JSON-backed value objects and nested attribute access.
- `document.yaml` covers `table-per-concrete-subtype` inheritance (one table per
  concrete subtype, with abstract reads assembled through `union all`);
  `instrument`, `rate`, `reading`, and `quote` add small temporal inheritance
  families that compose subtype routing with audit and bitemporal milestone
  writes.
- `reservation.yaml` and further descriptors cover additional shapes used by
  later compatibility cases.

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

Each case file is named `<module>-NNN-<slug>.yaml` and filed under the module it
chiefly proves — e.g. `m-op-algebra-001-find-all.yaml`,
`m-deep-fetch-007-shared-prefix.yaml`, `m-audit-write-001-insert.yaml`. A case
also carries a module tag for every behavior it exercises, so the corpus is
browsable by module and the coverage gate can map each active module to its
cases.

Each case reads top-to-bottom as **given / when / then** — setup, the action
under test, then the assertions — with identity and routing (`model`, `tags`,
`lane`) plus an explicit `shape` discriminator kept top-level. The schema supports
eight case shapes, named by that required top-level `shape`:

- `read`: execute canonical SQL (`then.statements`), compare `then.rows`, and
  optionally compare `then.referenceSql`.
- `writeSequence`: run ordered write statements and compare final `then.tableState`.
- `scenario`: model transactions, cache hits, identity checks, and round trips.
- `conflict`: apply `given.apply`, execute a write, and assert `then.affectedRows`.
- `coherence`: use two database connections to observe cross-process behavior.
- `error`: trigger a real DB error and assert `then.errorClass` + `then.nativeCode`.
- `concurrencySuccess`: a two-session read-lock choreography asserting no error.
- `boundary`: an `api-conformance`-lane retry case asserting `then.outcome`.

Every SQL statement — golden or naive — is a `{sql, binds}` **statement entry**:
its `sql` is a dialect-keyed map (`postgres` / `mariadb`) at golden locations and a
plain string at naive ones, and its `binds` are attached to it inline. There is no
positional pairing convention.

Every read case follows the same triple oracle:

```text
rows(then.statements[].sql[dialect] + binds) == then.rows
rows(then.referenceSql + binds) == then.rows
normalize(then.statements[].sql[dialect]) is canonical for the dialect
```

Deep-fetch cases extend this by asserting a bounded number of SQL statements and
a `then.graph`, not just flat rows.

### 5. Run cases through the reference harness

`reference-harness/` is a Python implementation of the compatibility harness
(the `m-case-format` contract). It is not an ORM and it does not compile
operations into SQL. Its job is to verify that the spec artifacts are coherent.

The reference harness's internals are non-normative and
MUST NOT be used as design input for a language implementation; the binding
inputs are the spec modules, `core/schemas/`, the compatibility corpus, and the
conformance-adapter contract.

For each case the harness:

1. Validates the descriptor, operation, and case JSON/YAML against schemas.
2. Derives test DDL from the descriptor.
3. Loads the requested fixture rows.
4. Executes the authored canonical SQL (`then.statements`) against a real database provider.
5. Executes `then.referenceSql` when present.
6. Compares rows, graphs, table state, affected rows, round trips, and cache or
   identity expectations.
7. Checks SQL normalization and deterministic descriptor/operation serde.

Database-specific behavior is isolated behind the provider seam in
`reference-harness/src/reference_harness/providers/`. The built-in providers cover
Postgres and MariaDB through Testcontainers, including type mapping, temporal
infinity handling, bind translation, JSON values, read-lock syntax, and peer
connections for coherence cases.

### 6. Use benchmarks as executable performance contracts

`core/compatibility/benchmarks/` contains `m-perf-bench` benchmark definitions. They reuse
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
5. Add compatibility cases with canonical `then.statements` (dialect-keyed `sql`
   plus inline `binds`) and expected observations.
6. Add benchmark coverage when the behavior changes query shape, write shape,
   round trips, or memory use.
7. Run `just verify` before relying on the change.

When adding a dialect, implement a new provider behind the database seam
(`m-dialect` / `m-db-port`) and add a new per-dialect `sql` key to the
`then.statements` entries of cases and benchmarks that need dialect-specific SQL.

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
example: it declares the (now-deprecated) `slice-mvp-1` Conformance Slice — its
migration target is `slice-managed-1`, one of the two object-lifecycle slices in
[core/spec/slices.md](core/spec/slices.md) — and proves it with both official
artifacts. Further language implementations should treat
`core/` as the shared contract and use `reference-harness/` as the executable
oracle. See
[Building A Language Implementation](#building-a-language-implementation) for the
slice-first process and its two official proof artifacts.
