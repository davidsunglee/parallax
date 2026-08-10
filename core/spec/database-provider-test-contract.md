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

Each row proves the database's answers for the `m-dialect` decision catalog:

- stable dialect identifier used as the per-dialect `sql` key in a case's `then.statements` entries
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

Each concrete adapter artifact is driver-bound and therefore needs a small
database-backed smoke suite. This suite proves the shipped adapter path, not the
`m-case-format` case runner.

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

Each adapter must also prove the port's failure-instance identity rule
(`m-db-port`). The rule binds every error the port itself raises, so the proof
must reach every raise site: a statement failure surfaced by `execute`, one
surfaced by `executeWrite`, and each transaction-boundary failure surfaced by
`transaction` — its begin, its commit, and its rollback. An adapter that wraps
the whole boundary translates all three, so a proof stopping at commit leaves the
two that bracket it unproven. Repeating each site establishes that no site reuses
an instance across its own invocations, and driving every site over one adapter
establishes that no two sites share one — a per-site cache satisfies the first
and fails the second. Every
error so raised is distinct while carrying the same category, native code, and
message. This obligation needs
no database and belongs wherever the language can drive the adapter over a driver
that raises one reused exception object for every failure — the input the rule
exists to stop an adapter from passing on — so a Docker-free structural test
discharges it, and the language spec names where that proof lives.

The same rule bounds what an adapter may translate. An exception the caller's own
`transaction` body raises is not an error the port made, so it must reach the
caller as the same object even when it is a driver exception — an adapter that
wraps the whole boundary in one translating block substitutes a port error for it
unless it excludes the body. The two branches are one proof: a body raising a
driver exception over a rollback that succeeds must surface that same object, and
the same body over a rollback that itself fails with a driver exception must
surface the translated port error instead. Only identity separates them, so a
proof asserting error types alone establishes neither.

## 3. Provider and matrix contract

The `m-case-format` database provider is the case-runner provisioning surface. It
is selected at the composition root and must not leak concrete driver dependencies
into above-seam runtime modules.

A provider contract suite must exercise these operations:

- `reset`: return the database to an empty, isolated state
- `applyDdl`: apply the ordered DDL derived for a case model
- `loadFixtures`: resolve fixture cells through the target Entity Layout and
  insert them in Table Layout order
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
second dialect with incomplete `m-case-format` coverage must classify cases whose
`then.statements` entries carry no `sql` key for that dialect as profile
exclusions, not as silent skips.

## Reporting

Database-backed suites may be skipped when Docker or another documented database
substrate is unavailable. The skip must be visible in the test output or final
verification report, and the language implementation must report which
database-backed checks were skipped.
