# m-db-port — Database Execution Port

`m-db-port` is the **abstract runtime database port**: the execution interface the
layers above the seam call to run compiled SQL and demarcate transactions, and
the **lifetime** interface a composition root opens that execution from. Each
language supplies **N concrete adapter artifacts** (one per supported database
type) that implement this behavioral contract. The module depends on `m-core`
and on `m-dialect`, whose value it exposes. It is the one **contract-covered** module — no compatibility fixture
maps to it; the port is proven by each language's
[database-provider test contract](database-provider-test-contract.md).

## The port contract

The port names a
`dialect` /
`execute(sql, binds, documentReads) → rows` /
`executeWrite(sql, binds) → affected-row count` /
`transaction(body, isolation?)` contract and nothing more. `execute` is row/result oriented;
DML that needs write-outcome classification uses `executeWrite` and **MUST NOT**
append dialect-specific row-returning clauses merely to infer an affected count.
`documentReads` is the compiled read's ordered sequence of adjacent zero-based
projection ordinal pairs `(presence, document)`; it is empty for a result with no
selected Structured Column. It carries no model, member, layout, or driver type.

`dialect` is the concrete `m-dialect` strategy every statement crossing this
port is spelled in — read-only, and answerable at any time. The port is the
thing that holds the connection, so it is the only thing that knows which
spelling its statements must use; a caller that reaches a port therefore reads
the dialect off it rather than choosing a second value beside it and requiring
the two to agree. The mapping runs **adapter → dialect only**: two adapters MAY
report the same dialect, and nothing selects a port, an adapter, or a connection
*from* a dialect.

The port **depends on nothing application-specific** (beyond the neutral `m-core`
types its contract names, and the driver-free `m-dialect` value it exposes) — no
driver, no concrete database, no harness — so any layer may hold the port without
acquiring a database dependency. It carries the
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

## Configuration, runtime, and one connection at a time

The port has a second half, used by a different caller. Query code receives
EXECUTION alone — the four verbs above — and can neither acquire nor release;
composition receives the LIFETIME and never executes. That split is what lets a
connection be held for exactly one operation without any statement being able to
take or give one back.

```text
adapter configuration   immutable, resource-free; opens an independent runtime
  runtime               the running resource one connected handle owns
    connection context  one single-use acquisition, yielding scoped execution
```

**Configuration owns nothing.** Constructing it MUST open no connection, no
pool, and no background worker, and MUST validate what it can locally, so it is
safe to build before a process forks and to share between threads. It is
immutable: settings change by constructing another value, never by mutating one
a runtime was opened from. Every open produces an **independent** runtime — two
handles built from one configuration own two runtimes, and closing either leaves
the other working. External inputs a connection string refers to (environment,
service files, credentials, server defaults) resolve when each physical
connection is created rather than being frozen at construction.

**A runtime is ready or it is not.** Opening returns only a runtime that has
proved it can execute: waiting for retained capacity, where a mode retains any,
is not that proof — with no minimum to wait for it proves nothing at all, and
even with one it establishes that a connection exists rather than that a
statement works. Readiness therefore acquires a real connection, proves the
decoding the read path depends on through it, and requires it back. Readiness
runs under ONE cooperative budget that is checked between phases and never
restarted; a budget stops the next phase from starting and makes no claim about
interrupting a call already in flight. An open that fails releases everything it
took and publishes nothing.

**One acquisition is single-use.** Creating a connection context takes nothing.
Entering it acquires, prepares, and admits, or fails having cleaned up whatever
partial ownership it took. Leaving it revokes the execution it yielded and
relinquishes the connection exactly once. Re-entering one, entering one that has
exited, and entering one whose entry failed are each refused without touching
the resource. Each entry yields FRESH execution access even where the physical
connection is reused, so a reference kept past the exit executes nothing and
retains nothing.

Entering opens no transaction and leaving neither commits nor rolls back:
transaction outcomes stay the execution interface's, authoritative and unchanged.

**Admission decides what may finish.** Starting an acquisition reserves no right
to execute. Expiry and closure are decided together, once, immediately before
the connection is handed over. A native success that arrives after the budget is
spent is relinquished and reported as a timeout rather than admitted. Work
already admitted may finish everything it was going to do, including statements
it has not issued yet; anything needing a NEW acquisition after a close — a
retry, a delivery that has not read its first page — is refused from then on.

**Close is idempotent and permanent.** It stops admission and releases what the
runtime owns. It neither waits for borrowers nor interrupts their statements.
Ordinary problems met while closing are diagnostic-only: a handle that refused to
close would leave a caller unwinding with nothing better to do.

## What relinquishing a connection establishes

Every acquisition — however it ends, including a statement failure, a conversion
failure, a transaction that could not be undone, an abandoned delivery, an
observer that raised, and language-native control flow — reaches ONE cleanup
path, and that path reports what it ESTABLISHED rather than what it attempted:

| Outcome | Confirmed meaning |
|---|---|
| Returned | The handoff completed. It promises nothing about retention, idle availability, or later background work |
| Invalidated | Physical disposal was established BEFORE the handoff, and the handoff then completed for accounting |
| Unrelinquished | Required disposal or the accounting after it failed, or could not be confirmed |

Reuse is offered only for a connection that is idle and that the execution did
not declare suspect. Anything else is disposed of FIRST and handed back second:
disposal alone would leak the capacity, and a handoff alone would offer a
connection nothing may reuse. Nothing repairs an unexpected state in order to
reuse it, and idle status alone does not establish arbitrary session
cleanliness — safety also rests on owned initialization, controlled execution,
and the absence of raw access to a pooled connection.

Three refusals are required rather than optional. A failed physical disposal
MUST NOT fall back to returning a still-suspect connection. A failed handoff MUST
NOT be retried and MUST NOT be followed by a close, because a return that raised
may still have handed the connection to another borrower. A completed handoff
MUST NOT be inspected afterwards, for the same reason. Exactly-once handling is
therefore a guarantee about the SEQUENCE, never a promise of physical
reclamation when disposal or accounting itself fails.

Cleanup carries a finite, ordered set of issues describing conditions met, not
the disposition reached: a recovered condition may accompany a safe
invalidation. An ordinary post-execution cleanup problem is diagnostic-only and
**preserves what the operation already established** — a successful read, an
exhausted or closed delivery, a committed value, and an existing exception all
survive it — and it never authorizes replay. It does not suppress lost-connection
execution errors, rollback failure, uncertain commit, or fatal and control-flow
exceptions, whose existing precedence and cleanup rules are unchanged.

## Acquisition and readiness failures are outside the SQL categories

An acquisition that produces no usable connection reports one of four
driver-neutral reasons: **timeout**, **queue rejected**, **closed**, and
**preparation failed** — the last covering establishing or preparing execution
access, including a direct connection attempt that failed, a session
configuration the codecs cannot execute under, and a checkout that handed over a
connection which was not idle. No modeled statement ran, so nothing was
classified: these are not `m-db-error` categories and no retry rule reads them.

A runtime that did not become ready reports which readiness phase stopped it and
what is known about a connection it had already acquired. An earlier readiness
failure stays primary; cleanup that follows it reports through the
implementation's restricted resource reporting rather than replacing it.

## The dialect is preserved through every port that stands in for another

A port a caller holds MAY be a decorator over another port, or the
transaction-scoped port `transaction` hands `body`. Every such port reports the
dialect of the port it stands in for; none authors one of its own. Otherwise the
dialect a caller reads would depend on which port in a chain it happened to
hold, and a statement compiled inside a boundary could be spelled for a database
other than the one about to execute it.

A concrete adapter states its dialect as **metadata reachable without a
connection**, so a composition root can resolve which spelling an adapter
executes in — to report it, or to compile against it — before opening anything.

What the port does **not** carry is **adapter identity**. Which adapter, driver,
or configuration is behind a port is the composition root's own knowledge and
appears neither on the port nor in any envelope a harness publishes; the dialect
is a fact about the SQL, not a name for the thing executing it.

`isolation` is optional and, when present, is the **Isolation Level** the caller
asked **this** boundary to open at, named in the portable vocabulary the next
section defines. The port carries the requested value to the adapter unchanged,
and an adapter maps it to whatever its database needs. Two rules make the option
meaningful rather than advisory. It is **boundary-scoped**, never
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

## The portable isolation vocabulary

Parallax names exactly three Isolation Levels, each defined by the anomalies it
forbids rather than by any vendor's implementation of it. The serialized values
are `read-committed`, `repeatable-read`, and `serializable`.

| Level | Forbids | Still permitted |
|---|---|---|
| Read Committed | dirty reads | nonrepeatable reads, phantoms, serialization anomalies |
| Repeatable Read | dirty reads, nonrepeatable reads | phantoms, serialization anomalies such as write skew |
| Serializable | all of the above; committed participating transactions are equivalent to some serial order | a retryable failure rather than eventual success |

Read Uncommitted and vendor-specific levels are **not** part of the vocabulary
and cannot be requested. A level is exact, never an ordered substitution rule: an
adapter asked for Repeatable Read that can only open Serializable **reports a
boundary failure**, because a caller that named a level named the guarantee it
budgeted for on both sides.

What a level permits, it does not require. Nothing may depend on a phantom or a
write skew occurring merely because the requested level allows one, so the
contract promises no coherent predicate result across the several statements of a
deep fetch or a paged stream even where an engine happens to give one — that is
adapter-profile information, below.

**Serializable protects the committed outcome only among transactions that all
request it.** A transaction at a weaker level participating in the same
interleaving is outside the guarantee. Serializable promises neither identical
blocking behavior across engines nor eventual success: an engine may refuse a
participant with a retryable failure instead of ordering it, and that refusal is
the guarantee being kept.

### Mapping obligations

An adapter maps the requested level to whatever its database needs to forbid that
level's anomalies for exactly **one Transaction Attempt**, and repeats that work
for every attempt of an invocation, because an attempt is where the guarantee has
to hold. Applying the level acquires no snapshot of its own: an adapter **MUST
NOT** issue a query merely to force one, since when a snapshot is taken is the
database's own business and a forced one changes what the boundary observes.

Omission requests nothing and keeps the adapter's own default, **provided that
default is at least Read Committed**. An adapter checks this **once per
connection, when it takes the connection** — not per boundary and not per attempt
— and refuses a connection whose default is weaker as a connection error rather
than silently upgrading it, because a caller who named no level asked for the
adapter's default and would otherwise get one it did not configure. Where the
adapter owns the connection's whole life, "when it takes the connection" is that
connection's own initialization, and the refusal is an acquisition that failed
preparation rather than a statement that failed. A default at
or above the floor is kept as it is; an engine that executes Read Uncommitted as
Read Committed meets the floor.

Where a level needs session state rather than a boundary keyword, the adapter
owns that state's whole life, because `m-db-port` makes the option
boundary-scoped and an adapter may be handed a connection the application also
uses. For MariaDB's Repeatable Read, which forbids the lost update only with
`innodb_snapshot_isolation` on, that is four obligations per **physical attempt**:

1. read and save the session's current `innodb_snapshot_isolation`;
2. set it `ON` before the attempt when it is not already on — for Repeatable Read
   alone, never for Serializable, whose shared locking reads and range protection
   forbid the same anomaly without it;
3. restore the saved value after the attempt commits or rolls back;
4. repeat both for every retry attempt.

Session setup that fails before the callback **fails the boundary**: the callback
does not run, and the outcome is a boundary that never opened. Restoration that
fails after commit or rollback **preserves the outcome already reached** — the
work committed or did not, and a failed restore does not change that — and
**discards the connection** rather than returning it, since what it would run
next would run under session state nothing states.

### Adapter profile — nonportable, per engine

What each engine does with a level is stated here so it is documented rather than
promised. None of it is a portable guarantee: no case may assert any of it as
portable behavior, and nothing above the adapter seam may depend on it. A case
may still assert these facts **dialect-keyed**, where the assertion names the
engine it holds for and claims nothing about any other — `m-db-error`'s
per-dialect `nativeCode` is exactly that, and a conflict case asserts the codes
this table lists.

| Decision point | Postgres | MariaDB |
|---|---|---|
| Read Committed | fresh statement snapshot | fresh statement/read snapshot |
| Repeatable Read | transaction-stable snapshot; no phantoms on supported versions; write skew possible | transaction-stable snapshot with `innodb_snapshot_isolation` on; no phantoms on the supported floor; conflict raises `1020`, which retries |
| Serializable / conflict behavior | SSI; conflict raises `40001`, which retries | shared locking reads and range protection; conflict raises `1213`, which retries |

The graded MariaDB floor is **11.4.2+**, the first release of the 11.4
long-term-support series carrying `innodb_snapshot_isolation`; below it no
conforming Repeatable Read mapping exists. Both engines' native codes classify
through `m-db-error`'s per-dialect table into the neutral categories, so a
snapshot conflict is a `deadlock` on either engine and retries on the same terms.

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
  performs no I/O.** The port's dependency on `m-dialect` costs it neither
  property: the dialect layer opens no socket and imports no driver, so a layer
  holding a port still acquires no database dependency. A wrong-direction
  dependency here — the port reaching for a driver, an above-seam module
  importing a concrete adapter, or the dialect layer reaching back for the port —
  is the same class of spec violation the module-dependency graph forbids.

## Managed at the boundary, wire at the grader

The normalize-at-boundary contract fixes **where** a raw database value becomes a
first-class typed value: at the adapter boundary, **once**. An adapter returns
**managed** scalars — the language's exact-decimal type, big-integer type,
UTC-instant type, byte-array type — so every consumer above the seam reasons in
managed types and none re-parses driver text.

The compatibility harness (`m-case-format`) grades in a **different** domain and
must not be conflated with the runtime path. It takes the adapter's **managed** rows
and projects them through explicit Metadata to canonical Wire values
(`m-conformance-adapter`, `m-wire`) for its result envelope, then grades by exact
Wire structural equality except where the case authors an explicit tolerance
(`m-case-format`). Grading is therefore cross-language-consistent and independent
of any one language's managed representation. **The Wire rendering is a
conformance concern, never an adapter concern:** a concrete adapter emits managed
types only and contains **no** Wire or grading logic.

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
