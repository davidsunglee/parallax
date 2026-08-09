# m-execution-log — Transaction Execution Provenance

`m-execution-log` specifies the **Execution Log**: the language-neutral record of
what a transaction actually did, from a single Database Call through a
retry-spanning transaction result. It is a **composition-level observer** — it
records the work the other modules perform and none of them records itself. Per
the dependency graph it depends on `m-sql` (the Lowered Statement a call
executed), `m-db-port` (the call boundary), `m-db-error` (the category a failed
call classified to), `m-unit-work` (the transaction boundary, its write batches,
and their two triggers), and `m-auto-retry` (the retry policy and the
classifier's verdict). None of those modules depends back on this one: a
language's composition root threads the recorder down, so the observed never
names its observer.

The record is **read-only to every consumer**, is reachable from the active
transaction while its body runs, seals when the invocation terminates, and may
outlive the transaction it describes.

## The hierarchy

```text
Execution Log            one logical transaction invocation, spanning every attempt
  -> Transaction Attempt      status: active | committed | rolled back
       -> Read Trace          the calls one read issued
        | Write Batch Trace   trigger: read dependency | finalization
            -> Database Call  one attempted query or DML round trip
```

Each level exposes its own children (`calls` on a trace, `traces` on an attempt,
`attempts` on a log) and its own **round-trip count**. An attempt additionally
exposes a flattened `calls` projection over its ordered traces; that projection
is a read-only view, **not** a second collection of call references, so
convenience access adds no storage and no work proportional to the number of
calls.

## Database Call

A **Database Call** is one *attempted* round trip to the database. It records:

- the exact **Lowered Statement** (`m-sql`) executed — the canonical dialect
  value before an adapter converts placeholders or bind containers for its
  driver. That conversion stays unrecorded adapter detail, and the statement is
  retained by reference: its binds are not copied. **Retaining a log therefore
  retains, and exposes, whatever sensitive domain values those binds carry.**
- a **kind**, `read` or `write`, so a failed call stays classifiable without
  parsing its SQL;
- an **elapsed duration**, measured monotonically around the port invocation
  alone, including when that invocation fails. Duration is informational: it
  **MUST NOT** affect execution or conformance, and no wall-clock start or end
  timestamp is retained;
- exactly one **completion**, from a closed algebra:
  - **Read Completed** — the *physical* number of rows the statement returned.
    That is a row count, never a count of result roots, unique graph nodes, or
    projection views.
  - **Write Completed** — the affected-row count.
  - **Database Call Failed** — the detached diagnostic: the `m-db-error`
    category the failure classified to (absent when it classified to none), the
    provider's native code, and a human-readable message. The raised exception,
    its traceback, and every scrap of transaction state are **not** retained.

A `read` call admits Read Completed or Database Call Failed; a `write` call
admits Write Completed or Database Call Failed.

**Round-trip counting.** Every attempted Database Call counts one, a failed call
included. Transaction begin, commit, and rollback count **zero** — attempt status
and Attempt Failure record those boundary outcomes instead.

## Traces

A **Read Trace** and a **Write Batch Trace** each prove work that *reached* the
database, so each holds **at least one** Database Call. Planning or compilation
that fails before its first call creates **no** empty trace; the attempt's
Attempt Failure records that pre-execution failure instead. Each Database Call is
stored **exactly once**, inside the one trace that owns it.

A **Write Batch Trace** records a **closed trigger** naming which of
`m-unit-work`'s two flush triggers produced it:

- **read dependency** — the batch the unit of work flushed to serve a dependent
  read. It appears immediately *before* the Read Trace it enabled, which is how
  the log exposes that causality without anyone acquiring a public flush
  operation.
- **finalization** — the boundary-owned final batch. Nothing the attempt records
  follows it, so it is the attempt's last trace.

A read surfaced to a caller **shares** its Read Trace with the attempt that
issued it: the result and the current attempt reference the same trace, and no
second record of the same call exists.

## Attempts, policy, and failure

One Execution Log describes **one logical transaction invocation** and spans
every physical Transaction Attempt `m-auto-retry` runs. It retains, once:

- the **effective concurrency mode** (`m-unit-work`'s Locking or Optimistic),
  because that mode decides how the log's read locks, observations, and write
  gates are to be read;
- an immutable **Retry Policy** snapshot — the effective maximum re-execution
  count and the optimistic-conflict retry opt-in (`m-auto-retry`) — after
  defaults and outer-transaction inheritance are resolved.

Both record the **resolved value** only. Whether the caller supplied it
explicitly or inherited a default is not retained.

An attempt is **active** before its body runs, so the log never shows a gap. A
trace is appended only once its read or write batch has succeeded or raised, so
no partially built Database Call is ever observable. The attempt then transitions
to **committed** or **rolled back**, and the whole graph **seals** once the outer
invocation terminates — one stable object throughout, never replaced by a
snapshot.

A rolled-back attempt MAY carry a **detached Attempt Failure**:

| Field | Meaning |
|---|---|
| phase | `body` (callback work, explicit reads, read-forced write batches), `finalization` (the boundary-owned final write batch), or `commit` (the durability boundary) |
| error type | the implementation-level type name — deliberately not portable |
| message | human-readable |
| code | an optional stable Parallax or provider code |
| retry eligible | the classifier's verdict under the invocation's effective policy |
| database call | the existing call this failure references, when one caused it |

**Retry eligibility is a classification, not a history.** It states what the
classifier decided under the effective policy — its optimistic-conflict opt-in
included — *independently* of the remaining retry budget and without claiming
another attempt occurred. The phase algebra locates a failure that has **no**
Database Call without exposing language-specific stack locations or internal
planner stages; a failed port call, and post-call enforcement of a completed one
such as a zero affected-row shortfall, reference the call that already exists,
while planning, arbitrary callback, and commit failures reference none.

Failures of the database adapter's own **begin** or **rollback** operations are
outside this module: the log starts once the port has opened an attempt and
invoked the body, so a begin failure exposes no transaction from which to obtain
a log. Nothing here introduces an execution-bearing exception hierarchy either — a
successful standalone read carries its Read Trace, and a failed transactional
read stays observable through the retained log.

## Transaction Result

A transaction invocation returns a **Transaction Result**: the body's value
together with the whole Execution Log. Its **common execution view** is the
committed attempt, so the ordinary caller reads one attempt and the interested
caller reads the log.

The log's own accessors are looser than the result's, deliberately:

- **final attempt** is always the current or latest attempt;
- **committed attempt** is absent until and unless an attempt commits.

A **joined** invocation shares the outer transaction's live log rather than
opening a fictitious nested boundary, so its result describes the whole physical
transaction. Its common execution view is therefore **unavailable while the outer
transaction is still active**, and **remains unavailable** if that outer
transaction later rolls back; a language surfaces those two states as distinct
errors.

## Cost

Observability is bounded and stated as a contract, not as a hope. The incremental
cost is linear only in **physical Transaction Attempts and Database Calls** and
is **constant with respect to materialized result cardinality**: no Write Plan is
retained, and no work or storage is proportional to materialized rows, graph
nodes, or attributes. A language proves this with structural and
allocation-focused regression tests rather than a wall-clock threshold.

## What the suite pins down

This module owns a dedicated seven-case spine, so its coverage does not depend on
cases another module may re-author. Each reuses an existing model and its seeded
data.

| Case | What it proves |
|---|---|
| standalone read trace | a read outside any transaction carries a Read Trace of one call whose completion is the physical row count |
| finalization write batch | the boundary-owned batch carries the `finalization` trigger and one Write Completed call per statement |
| read-dependency ordering | the batch a dependent read forced carries the `read-dependency` trigger and appears immediately before the Read Trace it enabled |
| retry then commit | one log spans both attempts — the rolled-back one keeps its zero-row failure, the committed one its successful write |
| retry exhaustion | every attempt rolls back, each carrying a retry-eligible failure, and the bound stops the loop rather than the classifier |
| zero-row enforcement | a *completed* call whose affected-row count fell short still records Write Completed, and the attempt failure references that call |
| joined live-to-sealed | a joined body appends to the outer log rather than opening a second one: one attempt whose traces span both bodies, the joined write reaching the database under the outer boundary's `finalization` trigger |

The oracle is `then.execution` (`m-case-format`), a closed union of exactly one
`readTrace` or `transactionLog`. It states attempt, trace, call, and completion
*structure*; `then.statements` and `then.roundTrips` remain the sole SQL, bind,
and count oracles, and a call names its statement by index into the case's
flattened authored golden order rather than repeating any SQL or binds. Duration
and the implementation-level error type name are omitted from the portable
oracle and are checked only against their general API contracts. The shape is a
**case assertion format, not a public serialization contract**.

Three of the seven — retry then commit, retry exhaustion, and joined
live-to-sealed — turn on injected faults, a re-executed closure, and a nested
boundary that a single-connection harness cannot provoke, so they are authored on
the `api-conformance` lane and satisfied by each language's API Conformance Suite
(`m-api-conformance`). A **retry** in particular is not the ordered
`when.attempts` sequence a `conflict` case authors: that form states each
attempt's own write and each attempt is its own invocation, whereas a retry
re-executes ONE invocation's closure, which is what makes its attempts share one
Execution Log. The four that stay on the harness lane carry golden SQL, and a
call there names its statement by index into it.

A case authoring a `transactionLog` oracle describes **one** logical invocation,
so it must arrange one: an ordered write sequence is a sequence of independent
units of work, and two boundaries produce two logs rather than one with two
batches. Where a case's subject is what ONE boundary flushed, the corpus
expresses it as a unit-of-work-grouped scenario.

The oracle states a **terminal** value graph, which bounds what the spine proves
about the live half of the joined lifecycle. That the outer transaction's log is
reachable and `active` before the invocation terminates, that a joined result
exposes the same log object rather than a copy, that a trace appended after the
join becomes visible on it, that the graph seals at the outer boundary, and that
the two intermediate states surface as distinct errors are each an observation
taken *during* an invocation. They are normative above and are proven by each
language's API Conformance Suite against the story the joined case maps to, not
by the portable oracle.

Being terminal bounds the attempt history the oracle can state. Every attempt has
already transitioned, so **no attempt is `active`**; a commit ends the
invocation, so a **committed attempt is the last attempt** and there is at most
one; and the retained Retry Policy's maximum re-execution count bounds the
re-executions, so the attempts number at most **`maxRetries + 1`** — the original
execution plus the bound. The bound is not what licenses a re-execution, the
classifier is (`m-auto-retry`), so **every attempt another follows carries an
Attempt Failure whose retry eligibility is true**: a failure the classifier
refused surfaces to the caller rather than re-executing, and an attempt that
records no failure at all states no ground for the attempt after it.

The classifier and the bound must also agree about where the history *stops*.
A retriable failure re-executes the closure until the bound is spent, so a
terminal graph ending on a rolled-back attempt whose Attempt Failure is
retry-eligible is one whose attempts number exactly `maxRetries + 1` — the
retry exhaustion the case table above names. Under that count the record claims
a re-execution that the policy licensed and the loop did not run. A final
attempt whose failure the classifier **refused**, or which records none, is
terminal at any count, because nothing licensed a successor.

The compatibility harness validates the authored oracle itself — the case schema
fixes its shape, and the referential, arithmetic, trigger, and attempt-history
rules above are checked over the corpus — but it records no execution provenance
of its own, so it has nothing to compare the oracle against. Grading an
implementation against `then.execution` is therefore the language
implementations' alone; until a second grader observes an execution, this
module's runtime observables are single-witness, and each language records that
limit in its own deferred work.
