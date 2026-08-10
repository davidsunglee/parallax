# m-db-port — Database Execution Port

`m-db-port` is the **abstract runtime database port**: the execution interface the
layers above the seam call to run compiled SQL and demarcate transactions. Each
language supplies **N concrete adapter artifacts** (one per supported database
type) that implement this behavioral contract. The module depends only on
`m-core`. It is the one **contract-covered** module — no compatibility fixture
maps to it; the port is proven by each language's
[database-provider test contract](database-provider-test-contract.md).

## The port contract

The port names an
`execute(sql, binds) → rows` /
`executeWrite(sql, binds) → affected-row count` /
`transaction(body)` contract and nothing more. `execute` is row/result oriented;
DML that needs write-outcome classification uses `executeWrite` and **MUST NOT**
append dialect-specific row-returning clauses merely to infer an affected count.

The port **depends on nothing application-specific** (beyond the neutral `m-core`
types its contract names) — no driver, no concrete database, no harness — so any
layer may hold the port without acquiring a database dependency. It carries the
**normalize-at-boundary contract**: an adapter behind it returns rows whose scalars
are already **managed values** (produced by the `m-dialect` layer's parse
functions), never raw driver representations. Nothing above the seam ever sees a
driver's `Date`, a binary-float `numeric`, or a raw byte buffer. `executeWrite`
returns the concrete driver's native affected-row count and no rows.

## One error instance per failed invocation

An error the port *itself raises* to report a failure — a statement failure
surfaced by `execute` or `executeWrite`, or a transaction-boundary failure
surfaced by `transaction`, which is the boundary's begin, its commit, or its
rollback — is an instance **shared with no other invocation**. An
implementation MUST build that error where the failure occurs and MUST NOT raise
a cached, pooled, or otherwise reused error object, however identical two
failures' category, native code, and message are (`m-db-error` constrains what a
raised error *carries*; this constrains its *identity*).

The rule exists because the port hands back no call handle a failure could be
tied to: the raised error is the whole of what a caller learns about which
invocation failed. A caller MAY catch one failed call and keep working — so
several failures can occur in one transaction and only one of them unwinds — and
a consumer that must name the failing call, as `m-execution-log` does for an
attempt failure, therefore has only the raised object to distinguish them. One
instance raised twice makes those occurrences indistinguishable, and the failure
is recorded against a sibling invocation's call. A boundary failure names no
call — and a begin or rollback failure is outside `m-execution-log` entirely —
but a reused instance would let one resurface carrying the identity of the
failed call it stood for earlier, so the rule covers every error the port makes.

The rule reaches exactly the errors the port makes. An exception raised by the
caller's own `transaction` body is not one of them: it propagates through the
seam unchanged, and the port could only govern its identity by replacing the
caller's own failure with an error of its own. Nothing needs that — such an
exception is a callback failure, which `m-execution-log` attributes to no
Database Call — and two bodies that raise one shared object are two occurrences
the caller chose not to distinguish.

The rule binds the raise site alone, and an adapter that classifies each failure
into a fresh error at the point of failure satisfies it structurally. No runtime
consumer can enforce it while attributing a failure: an error it has just caught
carries nothing saying whether some earlier occurrence was the same object, so a
reused instance is indistinguishable from the occurrence it impersonates and
nothing above the port checks. Detecting a violation instead needs several
failures held at once and compared by identity, which is a **conformance proof**
rather than a runtime attribution — one every adapter owes and the
[database-provider test contract](database-provider-test-contract.md) states,
driving each raise site repeatedly over a driver that reuses one exception
object.

## Concrete adapter artifacts — one per database type

Each adapter implements the port over exactly one driver. Its only Parallax
dependencies are the port and the pure dialect layer (`m-dialect`), and its only
database-specific external runtime dependency is that driver. It owns driver
setup and registration (which type codes to read as raw text, connection/pool
acquisition) and delegates every parse decision to the dialect layer, so parse
logic is never duplicated across adapters. Adding a database type is a **new
independently deployable adapter artifact and source enforcement scope**, not a
new behavioral-module node or a change to the port, dialect layer, or anything
above the seam. The adapter artifact's production manifest is the only Parallax
manifest that MAY declare its concrete driver.

Two structural rules make the decomposition load-bearing:

- **Only the composition root may depend on a *concrete* adapter.** Every runtime
  layer above the seam depends on the **port**, never on a specific adapter; a
  concrete adapter is selected and injected once, at the top. This is what lets
  one program target the production database and a test target a different one
  without recompiling the layers between.
- **The port depends on nothing application-specific, and the pure dialect layer
  performs no I/O.** A wrong-direction dependency here — the port reaching for a
  driver, or an above-seam module importing a concrete adapter — is the same class
  of spec violation the module-dependency graph forbids.

## Managed at the boundary, wire at the grader

The normalize-at-boundary contract fixes **where** a raw database value becomes a
first-class typed value: at the adapter boundary, **once**. An adapter returns
**managed** scalars — the language's exact-decimal type, big-integer type,
UTC-instant type, byte-array type — so every consumer above the seam reasons in
managed types and none re-parses driver text.

The compatibility harness (`m-case-format`) grades in a **different** domain and
must not be conflated with the runtime path. It takes the adapter's **managed** rows
and **serializes them to the canonical wire form** (`m-core`) for its result
envelope, then grades in **wire space** (decimals compared in decimal space,
instants as canonical UTC strings, and so on) so grading is cross-language-consistent
and independent of any one language's managed representation. **The wire rendering
is a grader concern, never an adapter concern:** a concrete adapter emits managed
types only and contains **no** wire or grading logic.

## Deployable packaging contract

This decomposition mandates one pure dialect layer (`m-dialect`), one abstract
port, and N concrete adapter artifacts under the dependency rules above. The port
and dialect layer MAY ship together in the common runtime or as further
driver-free artifacts. Every concrete adapter, however, MUST be independently
installable: adapters MUST NOT be combined in a mandatory umbrella artifact, and
installing one adapter MUST NOT install, initialize, or load another adapter or
driver. What every ecosystem MUST preserve is the **direction**: above-seam code
binds to the port, and concrete adapters are leaf production artifacts selected
by the composition root.

A **concrete dialect strategy** — one database's pure SQL strings and parse
functions — is a **different thing** from a **concrete adapter** — that database's
driver-bound port implementation — even though both are per-database. Only the
adapter carries a driver. The concrete dialect strategies MAY ship as a single
catalog or be split one pure module per database; either way they stay
**driver-free**, and each adapter depends on its matching dialect strategy (never
the reverse). Folding a database's dialect strings *into* its adapter is
**forbidden**: `m-sql` (SQL generation) and `m-unit-work` (transactions) depend on
the dialect layer to emit compiled SQL, so co-locating dialect strings with a
driver would pull that driver into modules that MUST stay database-free —
defeating the driver-free compile/golden path.

## Test obligation

The test obligation is split the same way as the decomposition: the pure dialect
layer is proved by a Docker-free, one-row-per-database contract suite, while each
concrete adapter is proved by a small real-database smoke suite, and the
`m-case-format` provider is proved by a provider-contract suite. The portable
checklist lives in
[`database-provider-test-contract.md`](database-provider-test-contract.md).
