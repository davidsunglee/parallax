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
`execute(sql, binds, documentReads) → rows` /
`executeWrite(sql, binds) → affected-row count` /
`transaction(body, isolation?)` contract and nothing more. `execute` is row/result oriented;
DML that needs write-outcome classification uses `executeWrite` and **MUST NOT**
append dialect-specific row-returning clauses merely to infer an affected count.
`documentReads` is the compiled read's ordered sequence of adjacent zero-based
projection ordinal pairs `(presence, document)`; it is empty for a result with no
selected Structured Column. It carries no model, member, layout, or driver type.

The port **depends on nothing application-specific** (beyond the neutral `m-core`
types its contract names) — no driver, no concrete database, no harness — so any
layer may hold the port without acquiring a database dependency. It carries the
**normalize-at-boundary contract**: an adapter behind it returns rows whose cells
are already **managed values** (produced by the `m-dialect` layer's parse
functions), never raw driver representations. Nothing above the seam ever sees a
driver's `Date`, a binary-float `numeric`, a raw byte buffer, or a raw
structured-document value. `executeWrite`
returns the concrete driver's native affected-row count and no rows.

`transaction(body)` returns one closed, ephemeral boundary outcome rather than
raising away which boundary failed:

```text
Committed(value)
BeginFailed(error)
RolledBack(CallbackRaised(error) | CommitFailed(error))
RollbackFailed(CallbackRaised(error) | CommitFailed(error), rollbackError)
```

The composition root consumes this value immediately. It returns a committed
callback value, propagates a triggering error after successful rollback, and
preserves both triggering and rollback errors when rollback fails. The outcome
is not public provenance and transaction begin, commit, and rollback remain
outside Database Call accounting.

`isolation` is optional and, when present, is the isolation the caller asked
**this** boundary to open at, spelled in the concrete database's own vocabulary.
The port defines no portable vocabulary of levels and grades no level's
behavior: it carries the requested value to the adapter unchanged, and an
adapter applies it to the transaction it is about to open. Two rules make the
option meaningful rather than advisory. It is **boundary-scoped**, never
connection-scoped — a session default would outlive the transaction that asked
for it and silently govern the next one — and an adapter that cannot open a
boundary at the requested isolation **reports a boundary failure** rather than
opening one at a different level, because a request silently downgraded is
indistinguishable from one honored. Absence asks for nothing and leaves whatever
the adapter or its driver already defaults to, which is what every caller that
names no isolation gets.

For each `documentReads` pair, the adapter reads both cells before building the
managed row. The presence ordinal MUST immediately precede the document ordinal
and MUST hold the SQL boolean projected by `m-sql`; malformed or overlapping
pairs are an implementation-contract violation, not stored-data classification.
The adapter passes the pair to its dialect's document-read parser, omits the
presence cell from the managed row, and stores the resulting provider-neutral
`m-core` `DocumentRead` under the document cell's ordinary result key. Thus one
managed row value is either `SqlNull` or `PresentDocument(document)`, and SQL
`NULL` remains distinct from `PresentDocument(document: JSON null)` even when the
driver used one host sentinel for both raw values. No consumer may reconstruct
the tag from the raw document cell after the adapter boundary.

## One error instance per failed invocation

An error the port itself produces — raised by `execute` or `executeWrite`, or
carried by a `transaction` outcome for begin, commit, or rollback failure — is
an instance **shared with no other invocation**. An implementation MUST build
that error where the failure occurs and MUST NOT report a cached, pooled, or
otherwise reused error object, however identical two failures' category, native
code, and message are (`m-db-error` constrains what an error carries; this
constrains its identity).

The rule exists because the port hands back no call handle a statement failure
could be tied to: the error is the whole of what a caller learns about which
invocation failed. A caller MAY catch one failed call and keep working — so
several failures can occur in one transaction and only one of them unwinds — and
a consumer that must name the failing call, as `m-execution-lifecycle` does for an
attempt failure, therefore has only the raised object to distinguish them. One
instance raised twice makes those occurrences indistinguishable, and the failure
is recorded against a sibling invocation's call. A boundary failure names no
call — while begin and rollback failures are boundary outcomes rather than calls —
but a reused instance would let one resurface carrying the identity of the
failed call it stood for earlier, so the rule covers every error the port makes.

The rule reaches exactly the errors the port makes. An exception raised by the
caller's own `transaction` body is not one of them: `CallbackRaised` carries the
same object, and the port could only govern its identity by replacing the
caller's failure with an error of its own. Nothing needs that — such an
exception is a callback failure, which `m-execution-lifecycle` attributes to no
Database Call — and two bodies that raise one shared object are two occurrences
the caller chose not to distinguish.

The rule binds the failure site alone, and an adapter that classifies each
port-owned failure into a fresh error there satisfies it structurally. Enforcing
it is an obligation of the adapter's proof, not of the port's consumers: no
consumer is required to check, and one that does learns of a reuse only by
retaining the failures it caught earlier and comparing each new one against them
by identity, since the caught error carries nothing of its own marking it as a
reuse. Enforcement is therefore a **conformance proof** every adapter owes: the
[database-provider test contract](database-provider-test-contract.md) states it,
driving each raise site repeatedly over a driver that reuses one exception
object and comparing the collected errors by identity.

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

`DocumentRead` is likewise a managed transport value, but never a developer or
grader result cell. The compiled row transform consumes it to preserve or
classify the document carrier before ordinary row/graph serialization. A harness
that observes a logical row therefore renders the classified logical member, not
the `DocumentRead` tag or its SQL presence discriminator.

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
