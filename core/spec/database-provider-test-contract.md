# Database Provider Test Contract

This document records the portable test obligations for adding or maintaining a
database provider. It is a checklist for language implementations, not a new
runtime API. The behavioral source of truth remains the module specs, schemas,
compatibility cases, and the conformance-adapter contract.

The contract has three layers. A language implementation may organize files
differently, but it must be able to point at equivalent proof for each supported
database.

## 1. Docker-free dialect contract

The pure `Dialect` layer has no I/O and no driver dependency. Its conformance
suite is a table-driven test with one row per database. Adding a database means
adding one row to that shared table, not creating a one-off suite.

Each row proves the database's answers for the M11 decision catalog:

- stable dialect identifier used by `goldenSql.<dialect>`
- identifier quoting, including reserved and non-simple identifiers
- neutral `NULL` ordering for ascending and descending sort keys
- row-limit rendering
- shared read-lock application for object reads, projection/aggregation
  omission, and non-locking reads
- neutral scalar to column-type mapping, including parametric decimals and
  bounded strings
- bytes projection shape and any projection-introduced binds
- temporal infinity bind representation
- placeholder translation at the adapter boundary
- typed bind normalization for managed values
- parser behavior for precision-sensitive managed values
- native error-code classification and call-site predicates

The dialect suite must remain Docker-free. It should fail quickly when a new
provider row is incomplete.

## 2. Real-database adapter smoke contract

Each concrete adapter module is driver-bound and therefore needs a small
database-backed smoke suite. This suite proves the shipped adapter path, not the
M12 case runner.

For every supported adapter, the smoke suite covers:

- construction from the language's documented connection configuration
- a managed scalar read returning adapter-boundary values, not driver defaults
- a transaction callback that commits on success and returns the callback value
- a bytes write round trip through the dialect bind seam
- affected-row semantics for matched and unmatched DML
- feasible transient classification through the portable database error surface

When a transient proof would be impractical for a specific database in local
tooling, the language spec must record the gap and name the deeper suite that
proves the same classification.

## 3. Provider and matrix contract

The M12 database provider is the case-runner provisioning surface. It is selected
at the composition root and must not leak concrete driver dependencies into
above-seam runtime modules.

A provider contract suite must exercise these operations:

- `reset`: return the database to an empty, isolated state
- `applyDdl`: apply the ordered DDL derived for a case model
- `loadFixtures`: insert physical table rows in descriptor column order
- `query`: execute row-returning canonical SQL and return wire-normalized rows
- `exec`: execute DML and return affected rows
- `execRolledBack`: execute DML in a transaction that is rolled back
- `peer`: expose an independent connection for concurrent-writer and coherence
  style checks when the language's composition root needs one

The provider matrix must be declared with named profiles. A profile records:

- dialect
- provider/adapter under test
- case-selection rule
- whether it is full or partial
- expected included case ids or a mechanically checked count
- explicit exclusions with reasons
- the command or recipe that runs it

A full profile runs every case in the claimed slice for that dialect. A partial
profile is first-class only when its omissions are explicit. In particular, a
second dialect with incomplete M12 coverage must classify cases without
`goldenSql.<dialect>` as profile exclusions, not as silent skips.

## Reporting

Database-backed suites may be skipped when Docker or another documented database
substrate is unavailable. The skip must be visible in the test output or final
verification report, and the language implementation must report which
database-backed checks were skipped.
