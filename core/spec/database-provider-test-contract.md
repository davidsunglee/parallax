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
- shared read-lock application for locking-mode object reads and omission for
  optimistic-mode object reads
- neutral scalar to column-type mapping, including parametric decimals and
  bounded strings
- bytes projection shape and any projection-introduced binds
- temporal infinity bind representation
- placeholder translation at the adapter boundary
- typed bind normalization for managed values
- parser behavior for precision-sensitive managed values
- paired document-read parsing, including distinct `SqlNull` and
  `PresentDocument(document: JSON null)` results when the raw driver values use
  the same host-language null sentinel
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
- a Structured Column read whose SQL presence/value pair becomes one managed
  `DocumentRead`, with the presence cell absent from the returned row and SQL
  `NULL` distinct from JSON null
- a transaction callback that commits on success and reports `Committed(value)`
- distinct `BeginFailed`, callback- and commit-triggered `RolledBack`, and
  callback- and commit-triggered `RollbackFailed` boundary outcomes
- a boundary opened at **each portable Isolation Level**, which the callback
  observes as the level the database reports for its own transaction. What is
  proved is the MAPPING: that every level of the closed vocabulary reaches the
  database as that engine's own name for it, and that a boundary opening at no
  level after those reports the connection's own default rather than the last
  request. The whole vocabulary rather than one level, because a mapping that
  crossed two levels or dropped one is exactly what a single-level proof admits
- a **session setup that fails**, which reports `BeginFailed`, runs no callback,
  and leaves the port usable for the next boundary; and a connection that also
  fails to undo the empty transaction, which is discarded. Proved against the
  driver seam rather than against a real refusal, because a conforming mapping
  sends only levels its own engine accepts
- a **connection whose own default Isolation Level is below Read Committed**,
  refused as a connection error when the adapter takes it — once per connection,
  not per boundary and not per attempt — and one at or above the floor, kept as
  it is. An engine with no level below Read Committed meets the floor by
  construction and refuses nothing, which is the whole of its obligation here;
  an engine that honors a weaker default owes the refusal, because a caller who
  named no level asked for the adapter's default and must not silently receive a
  guarantee the portable vocabulary does not admit
- a bytes write round trip through the dialect bind seam
- affected-row semantics for matched and unmatched DML
- feasible transient classification through the portable database error surface
- a **derived Physical Index Name at exactly this engine's identifier limit**,
  applied and then read back from the engine's own catalog and found unchanged.
  The generating input must be long enough that the readable half was really
  shortened, so what the proof establishes is that shortening produced a name the
  engine stores whole — a limit stated one byte too high fails here and nowhere
  else, because every shorter name a corpus happens to hold would survive. The
  fingerprint must be intact in what the catalog reports, since it is the half
  truncation never touches and the half the name is unique by
- a **duplicate whose neutral error names the index it violated**, read from the
  driver's structured diagnostics rather than from its message, and equal to the
  name the Schema Delta that created that index recorded. Both halves are the
  obligation: an error carrying some name proves only that a field was read,
  while one carrying the name the generator derived proves the correlation a host
  performs after a rollout

When a transient proof would be impractical for a specific database in local
tooling, the language spec must record the gap and name the deeper suite that
proves the same classification.

An adapter whose engine forbids a level's anomalies only with **session state**,
rather than with a boundary keyword alone, owes two further proofs — both about
that state's whole life rather than about the statement that sets it, because
`m-db-port` makes the option boundary-scoped while the state is the connection's.
MariaDB's Repeatable Read is the case that specification states, and the proofs
are: the saved value is restored after the attempt commits or rolls back, and the
save, set, and restore happen again for **every** attempt of a retried
invocation, so an invocation neither leaves the variable changed behind it nor
opens its second attempt without it; and a **restore that fails** preserves the
outcome already reached — the work committed or did not, and a failed restore
does not change that — while **discarding the connection** rather than returning
it. That second proof is the same shape as the failed-rollback discard above, for
the same reason: what the connection would run next would run under session state
nothing states. Both are driven against the driver seam, as that discard is. An
adapter whose engine needs no such state owes neither.

The rest of these obligations are portable and are stated by the corpus instead:
that a joining call may not name a second level, that one requested level stands
over every attempt of a retried invocation, that a connection's default is judged
at intake, and that a failed session setup opens no boundary are `boundary`-shape
cases each language's API Conformance Suite executes. A failed restore is the one
that has no corpus expression at all — it happens below the seam a case can reach
— which is why it is written here.

Each adapter must also prove its **dialect binding** (`m-db-port`). Neither half
needs a database. The adapter states its dialect as metadata reachable without a
connection, so the proof resolves it off the adapter itself rather than off a
constructed, connected instance, and checks that it is the strategy whose SQL
that adapter executes. And every port that stands in for another preserves it:
the transaction-scoped port `transaction` hands `body` reports the dialect of the
port that opened the boundary, and each port a language ships that decorates
another reports the dialect of the port it wraps rather than one of its own.
Enumerating those decorators is part of the obligation, and so is the input that
separates preserving from declaring: a decorator that authors a constant passes
against a port declaring that same dialect and fails against any other, so the
proof drives each one over a port whose dialect none of the language's own
adapters declare. The language spec names where that proof lives.

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
surface the translated port error instead. Neither the exception's type nor its
identity separates the branches, because the same driver that reuses one
exception object across failures — the input the identity rule above already
requires an adapter to withstand — hands the body and the rollback the same
object. An adapter must therefore separate them by where the failure occurred,
and the proof must include the case where one object is both: a body raising it,
a rollback failing with it, and the translated boundary error surfacing.

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
- `catalog`: report what the database itself holds for a named set of tables —
  each table's columns with their types and nullability, and each index with its
  ordered columns and its uniqueness. Column ordinal position is deliberately
  excluded: it records the order statements happened to run in, and two schemas
  differing only in it hold the same data under the same names. This is the one
  observation of physical schema the seam offers, and the only way an applied
  Schema Delta can be compared against independently derived provisioning DDL:
  what is compared is the schema each really produced, never the statements
  either authored

The provider matrix must be declared with named profiles. A profile records:

- provider/adapter under test
- case-selection rule
- whether it is full or partial
- expected included case ids or a mechanically checked count
- explicit exclusions with reasons
- the command or recipe that runs it

A profile does not record a dialect of its own. The adapter under test already
declares the dialect it executes in (`m-db-port`), and that declaration is
metadata rather than connection state, so the profile derives its dialect by
reading it back — without a container and without a connection. Deriving rather
than recording is what makes a profile naming a dialect its adapter does not
execute in unrepresentable rather than merely wrong, and it is why the derivation
must reach the adapter's declaration rather than an instance of it.

The recipe the profile names must be what actually runs the matrix. A declaration
some other wiring duplicates is a name, not a profile: the recipe and any
command surface that selects a profile must resolve the same declaration.

A run reported under a profile must execute through a database that profile's own
recipe opened. A reporting name and a database paired by whoever happens to hold
both produce a well-formed report of a run that did not happen, and two profiles
sharing a dialect leave nothing in the report to tell it from a true one. So the
pairing must be constructed by the profile rather than checked afterwards: what a
run is asked for is a profile, never a database.

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
