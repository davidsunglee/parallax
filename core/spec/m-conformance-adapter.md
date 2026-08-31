# m-conformance-adapter — Conformance Adapter Contract

The conformance adapter is the seam between the language-neutral compatibility
corpus and a concrete language implementation. It gives an external runner a
small interface for asking an implementation what it supports, what SQL it
emits for a case, and what observations it produces when it runs a case.

This contract is adjacent to `m-case-format`: the reference harness proves the
core corpus is internally coherent; a language implementation proves itself by
satisfying this adapter contract against that same corpus.

## Purpose

The adapter exists so a conformance runner can validate a TypeScript, Java,
Python, Rust, or other implementation without knowing that implementation's
internal modules or public developer API.

The adapter MUST NOT expose internal classes, finder builders, cache objects, or
language-specific query surfaces. It accepts compatibility corpus files and
returns JSON observations.

Every modeled scalar leaf in an observation MUST be the canonical
`m-wire.encodeWire(declaredType, managedValue)` output for its resolved
declaration. This applies to rows, graphs, milestone pins, step observations,
table state, and modeled statement binds. Declared Value Object documents apply
the rule recursively; opaque Json is one recursive value and receives no inferred
leaf types. Null is an enclosing member-presence value, not a typed literal.

An adapter MUST fail conformance production rather than stringify, coerce, or
otherwise repair a non-member carrier. The runner validates observations with
canonical Wire decoding, so a noncanonical Decimal, bytes, UUID, temporal,
integer, or float observation is an adapter failure even when it denotes the
expected managed value. Dialect-native control binds that are not modeled values
retain their owning SQL or dialect representation.

The adapter SHOULD be implemented as a CLI because a CLI is portable across
language ecosystems. A language MAY also expose the same interface as an
in-process test helper, but the CLI is the shared contract.

## Commands

An adapter binary SHOULD be named `parallax-conformance` or exposed through a
language-native wrapper that accepts the same commands.

```text
parallax-conformance describe
parallax-conformance compile --case <case.yaml> --dialect <dialect>
parallax-conformance run --case <case.yaml> --profile <profile>
parallax-conformance benchmark --benchmark <benchmark.yaml> --profile <profile>
```

`compile` executes nothing, so it is asked for a dialect: there is no adapter to
read one off. `run` and `benchmark` execute, so they are asked for a **profile** —
the declared database matrix profile
([`database-provider-test-contract.md`](database-provider-test-contract.md)) naming
the adapter configuration to run against — and the dialect they report is the one
that adapter executes in rather than one the caller named beside it. One
invocation runs one profile; running the matrix is the caller's loop, not a
command-line option.

Each command writes exactly one JSON document to stdout. That JSON document MUST
validate against
[`core/schemas/conformance-adapter.schema.json`](../schemas/conformance-adapter.schema.json).
Human-readable logs MAY be written to stderr.

### Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | Command completed and stdout contains `status: "ok"` |
| `10` | Requested capability is intentionally unsupported and stdout contains `status: "unsupported"` |
| `11` | `compile` targets a claimed but compile-ineligible (run-only) case and stdout contains `status: "run-only"` |
| `1` | Command failed and stdout contains `status: "error"` |
| `2` | CLI usage error, such as a missing flag or unreadable file |

The `unsupported` result is only valid when the adapter has not claimed the
requested command, dialect, case shape, module tags, or case-tag selection in
`describe`, or when a `run` or `benchmark` names a profile the implementation does
not declare. The `run-only` result is only valid for a `compile` command on a
**claimed** case the corpus declares run-only (`compileEligibility`, `m-case-format`).

## Common Output Envelope

Every JSON output document has these common fields:

```json
{
  "schemaVersion": "1",
  "command": "compile",
  "status": "ok",
  "adapter": {
    "language": "typescript",
    "name": "@parallax/typescript",
    "version": "0.1.0"
  }
}
```

`status` is one of:

- `ok`: the command completed and command-specific fields are present.
- `unsupported`: the request is outside the adapter's claimed capability set.
- `run-only`: a `compile`-only status — the requested case is claimed but the
  corpus declares it run-only (`compileEligibility`), so it can only be graded by
  `run` (see [`compile`](#compile) below).
- `error`: the adapter attempted the request and failed.

`unsupported` and `error` outputs MUST include at least one diagnostic:

```json
{
  "schemaVersion": "1",
  "command": "compile",
  "status": "unsupported",
  "adapter": {
    "language": "typescript",
    "name": "@parallax/typescript",
    "version": "0.1.0"
  },
  "diagnostics": [
    {
      "code": "unsupported-dialect",
      "message": "mariadb is not claimed by this adapter"
    }
  ]
}
```

## `describe`

`describe` reports the adapter's claimed capability set. It does not read cases
or connect to a database.

Example:

```json
{
  "schemaVersion": "1",
  "command": "describe",
  "status": "ok",
  "adapter": {
    "language": "typescript",
    "name": "@parallax/typescript",
    "version": "0.1.0"
  },
  "capabilities": {
    "modules": ["m-core", "m-descriptor", "m-predicate", "m-sql", "m-dialect", "m-case-format"],
    "dialects": ["postgres"],
    "caseShapes": ["read"],
    "caseTags": {
      "exclude": ["groupBy", "having"]
    },
    "commands": ["describe", "compile", "run"],
    "provisioning": "external-url"
  }
}
```

Capability claims are deliberately **case-tag aware**. `modules`,
`dialects`, and `caseShapes` are broad filters; `caseTags` is an optional
fine-grained filter over the compatibility case's own `tags` array. This lets a
partial implementation honestly claim, for example, `m-predicate` predicate reads
while deferring aggregation (`m-agg`) reads, or `m-unit-work` transaction/write
cases while deferring the `m-process-cache` query-cache and identity-cache
scenarios.

Inheritance capability follows this same shape and needs **no**
inheritance-specific adapter surface. An adapter claims it by listing
`m-inheritance` in `modules` and, where a claim defers part of the module, by the
ordinary `caseTags` filter; abstract-target reads, subtype narrowing, polymorphic
navigation, narrowed deep fetch, and concrete-subtype writes are all ordinary case
commands under the existing `describe` / `compile` / `run` contract, with no new
command, dialect, case shape, or observation field.

The example above is intentionally minimal. An include-driven claim selects an
exact case subset with `caseTags.include`, avoiding a fragile list of
exclusions. A completed language spec ordinarily adopts its selected canonical
`capabilities` block verbatim; only the `adapter` identity differs.

A case command is claimed only when **all** of these are true:

- the command is listed in `commands`
- the dialect the case is requested in is listed in `dialects` — the one named by
  `compile --dialect`, or the one the profile named by `run --profile` executes in
- the case shape is listed in `caseShapes`
- every module-like tag on the case (`m-core`, `m-predicate`, …) is
  listed in `modules`
- if `caseTags.include` is present, the case has at least one listed tag
- if `caseTags.exclude` is present, the case has none of the listed tags

`caseTags.include` and `caseTags.exclude` use exact tag strings from case files,
including tags that contain spaces such as `identity cache`. The filters are
evaluated after the broad module/dialect/shape filters. If `caseTags` is omitted,
then the module, dialect, and shape claims are all-or-nothing for matching cases.

For a claimed case command, returning `unsupported` is invalid: the adapter MUST
return `ok` or `error` — or, for a `compile` on a case the corpus declares run-only,
the defined `run-only` answer (see [`compile`](#compile)). For an unclaimed case
command, returning `unsupported` is valid and SHOULD include a diagnostic naming the
first failed filter, such as `unsupported-case-tag` or `unsupported-case-shape`.

`provisioning` is one of:

- `external-url`: `run` and `benchmark` expect the caller to provide a database
  URL or equivalent language-specific connection configuration.
- `self-managed`: the adapter provisions its own clean database, for example
  with Testcontainers. The adapter owns the reset lifecycle needed to make each
  database-backed case isolated: reset to an empty state, apply the case model's
  derived DDL, and load fixtures according to the core case lifecycle. The
  contract does not assume any generic container snapshot API; language specs
  that use snapshot/restore optimizations MUST name the concrete provider API
  and fallback reset path.

The target language spec records which mode the implementation uses.
The reusable provider-test obligations for `reset`, `applyDdl`, fixture loading,
query/write execution, rollback execution, peer connections, and declared
full/partial database matrix profiles are recorded in
[`database-provider-test-contract.md`](database-provider-test-contract.md). That
document guides implementation suites; this adapter contract remains the
normative wire surface.

## `compile`

`compile` reads one compatibility case and emits the SQL statements and binds
the implementation would execute for the requested dialect. It MUST NOT execute
SQL.

The command is valid for any case shape whose behavior can be represented as
SQL emissions. Cache-hit scenario steps that perform no database work simply
produce no emission for that step and still contribute `0` round trips.
For a predicate-selected scenario write, the adapter consumes the structured
`/scenario/<n>/write` instruction as the requested operation; it MUST NOT treat
authored DML text as its only write input or reverse-engineer the operation from
golden SQL.

For a **buffered** scenario write — the **ordered keyed buffer** under
`/scenario/<n>/write` (`m-case-format`), **one or more** keyed instructions a single
unit of work accumulates — the adapter buffers **every** entry in **one** unit of
work and applies the `m-unit-work` flush: it **coalesces same-object entries**
(same-transaction insert-then-update → a single final-value write in place;
insert-then-delete → cancel to no DML), then **foreign-key-orders and elides** the
general multi-object flush, emitting the per-object DML. The **same-object
coalescing pair** — a buffer of exactly two same-object entries — is the
single-object **special case** of that flush, emitting a **single** final-value
write or **no** DML at all; a **single** keyed write (a buffer of one) and a
**mixed multi-object flush** (an `insert`, `update`, and `delete` of **different**
objects) are the general cases. The adapter consumes the ordered structured
instructions as the requested operations exactly as for the single-instruction
forms — it MUST NOT treat the authored golden SQL as its write input or
reverse-engineer the operation from golden SQL — and under `compile` the buffer
follows the same compile-eligibility rules as any other write.

### Compile eligibility

`compile` applies only to a **compile-eligible** case. A case the corpus declares
**run-only** (`compileEligibility`, `m-case-format`) — because its emissions intend a
single-connection concurrency/locking interaction or depend on a query result — cannot
be compiled: the adapter neither derives its SQL (that would require executing a query)
nor returns `unsupported` (invalid for a claimed case command). Instead it returns the
defined **`status: "run-only"`** answer, exit code `11`, echoing the `case`, `dialect`,
and `caseShape` and carrying at least one diagnostic whose `code` is
**`compile-run-only`**:

```json
{
  "schemaVersion": "1",
  "command": "compile",
  "status": "run-only",
  "adapter": { "language": "python", "name": "parallax-conformance", "version": "0.1.0" },
  "case": "core/compatibility/cases/m-opt-lock-005-conflict.yaml",
  "dialect": "postgres",
  "caseShape": "conflict",
  "diagnostics": [
    { "code": "compile-run-only", "message": "single-connection conflict case is run-only" }
  ]
}
```

Only `run` grades a run-only case. An adapter's static compile lane wires its database
port to **refuse** any row-returning read; a `compile` on a case declared eligible that
nonetheless requests a row proves the case was mis-declared, so the refusing port
structurally enforces the `query-result-dependent` criterion the authored declaration
cannot. `describe` does not enumerate run-only cases — eligibility is a per-case
property the runner reads from each case, not a capability claim.

A **rejected**-shape case (`m-case-format`) is **implicitly** run-only, by construction
rather than declaration: `then.statements` is disallowed for the shape, so it carries no
golden SQL to compile. `compile` on a rejected case therefore answers the same
`status: "run-only"` envelope with a `compile-run-only` diagnostic — a **shape-intrinsic**
rule needing no per-case `compileEligibility` authoring, unlike the query-result-dependent
run-only cases above.

Example:

```json
{
  "schemaVersion": "1",
  "command": "compile",
  "status": "ok",
  "adapter": {
    "language": "typescript",
    "name": "@parallax/typescript",
    "version": "0.1.0"
  },
  "case": "core/compatibility/cases/m-predicate-002-eq.yaml",
  "dialect": "postgres",
  "caseShape": "read",
  "emissions": [
    {
      "casePointer": "/objectQuery",
      "sql": "select t0.id, t0.name from account t0 where t0.id = ?",
      "binds": [1]
    }
  ],
  "roundTrips": 1
}
```

`casePointer` is a JSON Pointer into the compatibility case. Common values are:

- `/objectQuery`
- `/writeSequence/0`
- `/scenario/0/objectQuery`
- `/scenario/1/write`
- `/coherence/1/objectQuery`

For deep-fetch and write-sequence cases, `emissions` contains one item per
statement in execution order.

## `run`

`run` executes a compatibility case through the language implementation and
returns the observations required to compare against the case.

It consumes the same structured predicate-write instruction as `compile`, then
compares emitted SQL and binds to the authored golden unchanged. The instruction
adds neutral write input; it does not relax SQL comparison.

It likewise consumes the same **ordered keyed buffer** as `compile`, buffering
**every** entry in one unit of work and applying the `m-unit-work` flush —
coalescing same-object entries, then foreign-key-ordering and eliding the general
multi-object flush. The per-object DML that flush emits — for the same-object
coalescing special case, one final-value write or none — is compared to the
authored golden unchanged, exactly as for any other write, never reverse-engineered
from it.

`run` is asked for a **profile** rather than a dialect, and its envelope reports
both. `profile` echoes the requested profile — the adapter configuration the case
was run under. `dialect` is a **report of what executed**: the dialect the adapter
that profile opened spells its SQL in, which is the key a runner resolves the
case's per-dialect goldens under. The derivation runs one way only. A profile
fixes its dialect, by reading it back off the adapter it declares
(`database-provider-test-contract.md`); a dialect fixes no profile, because two
profiles may execute in the same one. Both are reported because a consumer of the
envelope holds neither the roster nor the adapter the derivation reaches through.
An adapter asked for a profile it does not declare returns `unsupported` with a
diagnostic naming it, exactly as an unclaimed dialect does under `compile`, and
provisions nothing.

The adapter is responsible for using a clean database according to its declared
provisioning mode, applying schema and fixtures, executing the implementation's
public behavior, and reporting observations. A runner may compare those
observations to `then.rows`, `then.graph`, `then.graphs`, `then.tableState`,
`then.affectedRows`, cache/identity expectations, and `then.roundTrips`.

The `roundTrips` a `run` reports is what its execution actually cost: every
database call the run made, a failed one included, with begin, commit, and
rollback counting none (`m-execution-lifecycle`). It is therefore not a tally of the
statements the adapter emitted — the two differ whenever a statement is planned
but never executed, and whenever a retry re-executes one — so an adapter reports
the count its own execution recorded rather than the length of its `emissions`
array. `compile`, which executes nothing, reports the emitted-statement count
instead; that is the one place the two readings legitimately differ.

When a language implementation routes case execution through its `m-db-port`
runtime database port, read/result statements and DML outcome statements remain
separate: row-returning reads use the port's row execution method, while
write-sequence and conflict affected counts come from the port's affected-row
write method. An adapter MUST NOT weaken
the emitted SQL by adding dialect-specific row-returning clauses solely to compute
affected rows.

Example:

```json
{
  "schemaVersion": "1",
  "command": "run",
  "status": "ok",
  "adapter": {
    "language": "typescript",
    "name": "@parallax/typescript",
    "version": "0.1.0"
  },
  "case": "core/compatibility/cases/m-predicate-002-eq.yaml",
  "profile": "pg-full",
  "dialect": "postgres",
  "caseShape": "read",
  "emissions": [
    {
      "casePointer": "/objectQuery",
      "sql": "select t0.id, t0.name from account t0 where t0.id = ?",
      "binds": [1]
    }
  ],
  "observations": {
    "rows": [
      {
        "id": 1,
        "name": "Alice"
      }
    ],
    "roundTrips": 1
  }
}
```

The observations object is intentionally shape-flexible because case shapes
assert different things:

- read cases report `rows`, `graph`, or `graphs`; `graphs` is the ordered
  per-milestone `{pin, graph}` observation for a milestone-set snapshot read. A
  graph-form read additionally reports `storedDataIssues` for the result positions
  whose stored state contradicted the declared model, and omits the key entirely
  when every position conformed. A read case carrying `when.stream` reports the
  same result observation its unstreamed peer would — `graph`, or `graphs` for a
  milestone-set read — delivered rather than materialized whole (see *Streamed
  reads*, below)
- write-sequence cases report `tableState`
- conflict cases report `affectedRows` and MAY report `tableState`
- scenario cases report `identityChecks` and `roundTrips`, plus `stepRows` for the
  values their read steps published, `stateChecks` for any step declaring
  `expectState`, and `errors` for any step declaring `expectError`
- coherence cases report the final observed `rows`, and `identityChecks` for any step that declares `sameObjectAs`
- error cases with a single-connection trigger (top-level `then.statements`)
  report `errorClass` — the neutral `m-db-error` category the final trigger
  statement's raised failure classified to — paired with `nativeCode`, the
  preserved native witness (Postgres SQLSTATE string, MariaDB vendor errno
  integer), compared against the case's `then.errorClass` / per-dialect
  `then.nativeCode`; `roundTrips` counts the executed trigger statements,
  including the raising one. This pair is distinct from the
  application-lifecycle `errors` observation. An error case whose trigger is a
  `when.concurrency` choreography needs two barrier-synchronized sessions
  (`m-case-format`), which the single-connection `run` command cannot drive —
  the harness's provider choreography proves it instead, and an adapter asked
  to `run` one returns `error` with a diagnostic naming that lane.
- any case authoring `then.executionLifecycle` additionally reports
  `executionLifecycle` — the normalized transient Root Executions and events
  (see *Execution lifecycle*, below)
- a rejected case executes **no SQL** and requires **no provisioning or
  dialect**: an adapter whose claim includes the `rejected` caseShape **MUST**
  report `rejectedRule` — the classified normative rule identifier
  (`m-predicate` / `m-navigate` / `m-value-object` / `m-inheritance`) the
  input was refused with — with `roundTrips: 0`. This obligation is
  unconditional for every claimant of the shape; the schema field itself stays
  optional and additive, exactly like `errorClass` before it, so an existing
  run output that never claims `rejected` stays valid unchanged.

### Streamed reads (`when.stream`)

A `read` case carrying `when.stream` (`m-case-format`) is satisfied by the
implementation's own **streamed** read, opened over the case's `when.objectQuery`
with the declared `when.stream.batchSize`, and by nothing else. Running the eager
read and reporting its result is a conformance failure even where the graph
matches: what the case states is the page partition — the requested size each
root statement binds, the Continuation Order coordinates each later page
continues from, and the statement a full final page costs to prove exhaustion —
and an eager read produces none of it.

The case names **no representation**, because delivery is the verb and the
namespace stays the surface's. An adapter drives whichever streamed read it
exposes and reports:

- **`observations.graph`** — the roots the delivery published, in delivery order,
  in the same root-class-keyed shape an eager graph read reports. Delivery
  publishes one root at a time; the observation is what the case's `then.graph`
  is compared against, so an adapter accumulates the delivered roots for
  reporting and the memory that costs is the runner's, never a claim about the
  implementation's own working set.
- **`observations.graphs`** in its place, for a **milestone-set** delivery
  (`history` / `asOfRange`), reported exactly as the eager milestone-set read
  reports it: the ordered per-milestone `{pin, graph}` entries. A delivery has no
  graphs to report directly — it publishes roots — so the entries are recovered
  from each published root's own edge pin, which is the coordinate the entry
  states. Roots of one milestone are grouped wherever they fall in the delivery
  and never only where they fall adjacently: a delivery arrives in the
  Continuation Order, the key before the edge, so several objects standing at one
  milestone reach the caller in as many runs as there are objects. The entries
  are ordered by **edge rank**, Valid Time before Transaction Time — the eager
  order — because what a milestone-set result states is which milestones the read
  reached, and an order the delivery happened to visit them in would make the
  observation depend on the page size. An adapter reports whichever of the two
  its case authors, and the choice is the query's: a scanned axis makes the read
  milestone-set.
- **`observations.roundTrips`** — every database call the delivery made, the
  terminal empty root statement included.
- **`emissions`** — every statement the delivery executed, in execution order
  across pages: each page's root statement followed by the child levels that page
  ran. The list is the whole delivery's, not one page's. It is read off the
  Database Calls the delivery publishes (`m-execution-lifecycle`), like every
  other run's, and never off the database port — a port carries the driver's own
  statement text rather than the lowered statement a Database Call borrows, so an
  adapter reporting from there would report a statement it recovered rather than
  one it ran. An adapter whose streams publish no such activity reports an
  **empty** `emissions` list; the statements the case authors are then graded by
  executing them, which is what the corpus runner does with every golden.

A **scenario read step** carrying `stream` (`m-case-format` *Streamed read
steps*) is satisfied the same way, inside the unit of work its `uow` group runs
in: the adapter opens its own streamed read over that step's `objectQuery` at
that step's `batchSize`, drains it, and reports the delivery's own statements
under the step's pointer — every page's, in execution order — exactly as an
ordinary find step reports its one. The roots the delivery publishes are what
the step's `expectRows` states, and the adapter reports them under the step's own
pointer as its `stepRows` entry (*Per-step row observations*, below) — across
every page, in delivery order — so a delivery that published its roots short,
duplicated, altered, or **reordered** fails against the rows the case states.
Those same roots are
the evidence a later write step naming that step with `on` settles against, and
that write's **gate** is the second observable holding an adapter to its own
delivery: resolving it from anything but the observation that delivery recorded
binds a generation the delivery never published, and the case fails there too.

Under `compile`, a case carrying a `stream` member anywhere is **always**
run-only: its later pages bind coordinates read off an earlier page's result,
which is the `query-result-dependent` criterion, so the adapter answers the
defined `status: "run-only"` envelope for one exactly as it does for a deep
fetch.

### Execution lifecycle (`executionLifecycle`)

A case may author the `m-execution-lifecycle` oracle
`then.executionLifecycle` (`m-case-format`). The adapter answers it with the
same optional normalized `executionLifecycle` shape: ordered Root Executions
whose UUIDs are replaced by positive first-observation indexes, each carrying
its kind and ordered correlated events. Mirroring the oracle lets a runner
compare the two structurally without making portable assertions about UUIDs,
durations, runtime type names, or diagnostic text.

The observation reports events the implementation's own installed recording
Handler received, never a re-derivation from the case. A Database Call names its
statement by index into this envelope's own `emissions` array, just as the oracle
uses the case's flattened authored statements. A call the envelope emits no
statement for — the resolving read a keyed write owes (`m-case-format`) — names
no index, and the indexes the rest name are the emission order exactly, in
delivery order and once each. Every present index must be in range and be named
by a call of the kind its own emission is — a query by a read, DML by a write;
JSON Schema cannot express those cross-array relations, so the adapter and
reference harness enforce them semantically.

The key is optional and additive, but an adapter claiming
`m-execution-lifecycle` MUST report it for every case authoring the oracle. It
MUST NOT synthesize the observation from authored goldens.

### Lifecycle observations (`stateChecks`, `errors`)

Two optional `observations` keys carry the object-lifecycle assertions a wire
golden SQL cannot see, mirroring the explicit-verdict shape of `identityCheck`:

- **`stateChecks`** — one entry per scenario step declaring `expectState`, each
  `{ at, expected, observed, pass }`: `at` is a JSON Pointer into the case (the
  step), `expected` the case's `expectState` (the `m-detach` five-state machine),
  `observed` the state the implementation saw, and `pass` the verdict.
- **`errors`** — one entry per scenario step declaring `expectError`, each
  `{ at, errorClass, native? }`: `at` the step pointer, `errorClass` the neutral
  application-lifecycle error the verb raised (`detached-relationship-load` /
  `transaction-time-pin-read-only` / `write-value-not-stored` /
  `write-value-already-stored` / `write-value-foreign-lifecycle` — `m-detach` /
  `m-identity-map` / `m-unit-work`, **distinct** from the
  `m-db-error` taxonomy), and an optional `native` witness carrying the raw
  implementation error.

Both are additive and optional: an adapter that observes no lifecycle state or
raised error simply omits them, so an existing `run` output (`roundTrips` plus
`rows` / `graph` / `identityChecks` / `storedDataIssues`) stays valid unchanged.

### Per-step row observations (`stepRows`)

A scenario has no single whole-read result, so a read step's rows cannot ride the
`rows` key: they are one observation **per step**. `stepRows` is the optional
`observations` array carrying them — one `{ at, rows }` entry per scenario read
step, `at` the JSON Pointer naming the step and `rows` the values that step
published, in the same physically-keyed shape a whole-read `rows` observation
carries and a step's `expectRows` is authored in (`m-case-format` *Row and
table-state style*). Entries appear in step order.

What is reported is what the step **published** — the roots the read handed over
— never the result sets its statements returned. The two differ wherever a read
publishes something other than its rows: a deep fetch's child levels return rows
belonging UNDER the roots rather than beside them, and a streamed step returns one
result set per page while publishing one root at a time. A streamed step's entry
is therefore the roots of its whole delivery, across every page, in delivery order
(`m-case-format` *Streamed read steps*); an eager step's is the roots of its one
result, the child levels its Include Paths populated being graded by `stepGraphs`
instead. An adapter answering this from a re-read, or from the rows its driver
returned, reports that the database is right where the case asks what the caller
was handed — the same distinction the `access` placement of `stepGraphs` draws.

One read step reports no entry: the resolving read of a **materializing predicate
write** (`m-case-format` *Materializing cases*). That read is the write's own
internal resolve — an implementation performs it while planning the write and
hands its rows to no caller, and an adapter that executed the find separately
would resolve twice and report a round trip the case does not count. What holds an
implementation to that step is what the case already states about it: its golden
read statement, which fixes the projection the resolve carries, and the per-row
binds the write then emits, which the planner derived from those very rows. Every
other read step owns an entry, and a step that owns one and is missing it is an
unanswered oracle rather than a pass.

It is additive and optional in the same sense as `stateChecks` / `errors` /
`stepGraphs`: a run reporting no such step omits it, and every existing `run`
output stays valid unchanged.

### Per-step graph observations (`stepGraphs`)

A scenario has no single whole-read graph, so a step's relationship contents
cannot ride the `graph` key: they are one observation **per step**. `stepGraphs`
is the optional `observations` array carrying them — one `{ at, graph }` entry
per scenario step declaring `expectGraph` (`m-case-format`), `at` the JSON
Pointer naming the step and `graph` the contents that step observed, in the same
entity-keyed shape a `graph` observation carries. Entries appear in step order,
and a step declaring the oracle whose entry is missing is an unanswered oracle
rather than a pass.

The contents reported are the ones **that step's own graph** holds, which the
observable's two placements make two different things. For an **access** step
they are what the already-materialized view the step navigates still holds —
**never a re-read**: an adapter that re-queries to answer it reports that the
database is right while the case asks whether the view survived, which is the
distinction the oracle exists to draw. For a **read** step they are what that
read itself materialized, roots and included relationships together — the same
value a whole-read `graph` observation carries, reported per step because a
scenario has many reads. An adapter answering a read step from some earlier
step's retained view would report the same confusion from the other side.

A multi-hop access `path` is walked under the null-branch rule `m-case-format` states:
a path fanning out through any to-many hop reports its **non-null** terminals,
and an all-to-one path reports one terminal per root, `null` where its branch
reached no row. That rule belongs to the observable rather than to any one
language's traversal API, so every adapter reports the contents the case states
instead of the shape its own inspection surface happens to answer.

It is additive and optional in the same sense as `stateChecks` / `errors`: a run
whose case declares no `expectGraph` omits it, and every existing `run` output
stays valid unchanged.

An **`identityCheck`'s semantics are the claiming module's identity contract**, not
a single fixed rule. For a **wire-level** scenario check (the PK-value one-object-
per-PK rule the harness itself grades) `same` means **primary-key-value equality**.
For a **managed-slice lifecycle** check (`differentObjectFrom`, and identity checks
on managed objects generally) `same` means **reference identity** — value equality
is insufficient, because two finite coordinates in one milestone have identical row
values yet are distinct pinned views (`m-identity-map`). An adapter grading a
managed-slice case therefore compares object references, not sorted PK values.

An **abstract-target read** — an abstract query `target`, or an abstract position
still abstract after the query's `narrowTo` (`m-object-query`) — materializes complete concrete
instances, so each observed row (and each `graph` leaf) additionally carries a
**`familyVariant`** key: the concrete subtype's family variant spelling (`Dog`,
`Cat`, …; a canonical qualified Entity spelling when duplicate local concrete
names make the bare spelling ambiguous). `familyVariant` is a materialized observation, **never projected as SQL** —
under `table-per-hierarchy` the emitted SQL projects the raw tag column and the
implementation materializes `familyVariant` from the tag metadata map, and under
`table-per-concrete-subtype` it is a per-branch subtype-name literal
(`m-inheritance` / `m-sql`). It rides inside the already-open `rows` / `graph`
observation objects, so the adapter output gains no field for it. A
concrete-target read carries no `familyVariant`.

## `benchmark`

`benchmark` runs one benchmark fixture and reports measurements using the
`m-perf-bench` methodology. The command returns the same report shape
`m-perf-bench` calls `report.json`, wrapped in the standard adapter envelope. For a
single `--benchmark <b.yaml>` invocation, `report.benchmarks` contains one entry
for that requested fixture. Adapters MAY also write the same `report` object to a
local `report.json` artifact for CI collection, but stdout is the normative adapter
output.

Example:

```json
{
  "schemaVersion": "1",
  "command": "benchmark",
  "status": "ok",
  "adapter": {
    "language": "typescript",
    "name": "@parallax/typescript",
    "version": "0.1.0"
  },
  "benchmark": "core/compatibility/benchmarks/read-mix.yaml",
  "profile": "pg-full",
  "report": {
    "generatedAt": "2026-06-27T00:00:00+00:00",
    "dialect": "postgres",
    "benchmarks": [
      {
        "fixture": "read-mix.yaml",
        "model": "models/account.yaml",
        "datasetRows": 1000,
        "workloads": [
          {
            "name": "point-read",
            "iterations": 200,
            "wallTimeMs": {
              "p50": 2.8,
              "p95": 4.7
            },
            "roundTrips": 1,
            "expectRoundTrips": 1,
            "roundTripsOk": true
          }
        ]
      }
    ],
    "memory": {
      "peakBytes": 12582912,
      "steadyBytes": 10485760
    }
  }
}
```

Benchmarks are required only when a language implementation claims `m-perf-bench`
support. The benchmark envelope MUST NOT use the legacy single-workload `metrics`
object; the report object is the machine-readable performance artifact.

## Comparison Rules

A conformance runner compares adapter output to the compatibility case using the
same rules as `m-case-format`:

- emitted SQL is normalized and compared to each `then.statements` entry's
  `sql[dialect]`
- binds compare in authored order (each statement entry's own `binds`)
- rows compare using the case's row comparison rules
- deep-fetch graphs compare to `then.graph`
- milestone-set snapshot graphs compare in authored order to `then.graphs`, with
  each observation's `pin` and `graph` compared to the corresponding oracle entry
- write table state compares to `then.tableState`
- conflict affected rows compare to `then.affectedRows`
- round trips compare to the case's declared `then.roundTrips` or scenario step
  counts
- a rejected case's `rejectedRule` compares **string-equal** to `then.rejectedRule`;
  accepting the input, omitting the observation, or naming a different rule all
  fail

The adapter output is not allowed to weaken the core corpus. If an
implementation disagrees with a case, fix the implementation or update the core
spec, schemas, fixtures, and cases together.
