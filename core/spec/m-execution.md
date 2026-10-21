# m-execution — Execution Runtime

`m-execution` is the lifecycle-neutral runtime over the database port: the
**Database Root** that owns one runtime's resources, the **Execution Scopes**
derived from it, the resolution of transaction options, the serving and adoption
of Model Editions, and the **Attempts**, writable or read-only, that run each
physical transaction attempt. It executes reads by handing them to `m-read-delivery` under the
conditions it establishes, and executes writes by running each sequence of Planned
Steps the unit of work hands it from the Write Plan `m-unit-work` finalizes and
acquiring the rows a write needs to read. Per the dependency graph it depends on `m-unit-work`
for admission, evidence, finalization, and effects; `m-read-delivery` for every
read it executes; `m-write-plan` for the Planned Steps it runs;
`m-write-payload` for the payload preparer model preparation wires into the
Write Planner and every statement stores; `m-sql` for the statements it lowers; `m-deep-fetch` for the row reads acquisition plans;
`m-execution-authority` for the authority a scope captures; `m-auto-retry` for
the attempt loop's bound and classification; `m-read-lock` for the lock an
acquisition takes; `m-execution-lifecycle` for the activities it opens;
`m-db-port` for the runtime, connections, and boundaries it drives; and
`m-batch-write`, whose collapse eligibility model preparation wires into the
Write Planner.

Execution decides the conditions an operation runs under — the authority, the
adopted model, the resolved options, the activity, the connection, and the
transaction — while read delivery and the unit of work carry the operation out
under them. It names no lifecycle: a lifecycle supplies the Publication its
reads publish through (`m-read-delivery`) and the transaction surface it hands
to an application callback, and turns its values into write instructions before
they reach the unit of work.

## Database Root

A **Database Root** is the configured owner of one runtime (`m-db-port`). It
owns that runtime, the installed Execution Lifecycle Provider
(`m-execution-lifecycle`), the clock a transaction instant is read from, the
Serving Model it serves, the reusable read-plan cache read delivery plans
through, and one transaction runner — each exactly once. Every Execution Scope
derived from the root shares those resources; none is rebuilt per scope or per
attempt. Closing the root closes its runtime and the registrations it owns, and
a scope derived from a closed root executes nothing.

A root exposes authority selection and option derivation, never a modeled read,
stream, or transaction of its own: modeled work is invoked through an Execution
Scope (`m-execution-authority` *Scope creation and use*).

### Options a root is configured with

A root is connected with one complete, immutable record of the three
**transaction options**: the retry bound (`m-auto-retry`), the Concurrency
Preference (`m-unit-work` *Strategy selection*), and the Isolation Level
(`m-db-port`). A root connected without a record carries the built-in record:
**ten** re-executions, the **`optimistic`** preference, and **Read Committed**.
Read Committed is a concrete level the runtime requests on every attempt, not
the absence of a request (`m-db-port` *Mapping obligations*).

A derived Execution Scope carries one complete effective record: its root's,
with any scope-level patch applied field by field. A patch names only the fields
it changes; omission alone inherits, and no field accepts an absent value as a
second spelling of omission. Deriving a scope or selecting its authority never
changes the record, and options never select, clear, or replace authority.

### Option resolution

An outer transaction resolves each option as its explicit argument, else its
invoking scope's effective value. Every physical attempt of that invocation, and
every call joining it, observes that one resolved record, and the transaction
exposes it as a value of the same shape the root and scope carry. A read-only
transaction (*Read-only transactions*, below) resolves the retry bound and the
Isolation Level the same way and nothing else: it has no Concurrency Preference,
whatever the scope's effective record names, and the record it exposes carries
none.

A joining call never renegotiates, and it compares only the options its own
entrypoint takes. An omitted option inherits the active transaction's resolved
value; an explicit option equal to that value is
accepted; an explicit option different from it is an **option conflict**,
refused before the joined callback runs. Neither the joining scope's effective
record nor its root's enters that comparison on its own, so under an outer call
that overrode its default, a join naming that default conflicts. Options are
exact values rather than an ordered substitution rule: a join naming Read
Committed under a Serializable boundary conflicts rather than weakening what the
boundary already satisfies. The order of the join refusals — ownership, then
rollback-only, then authority, then access mode, then explicit options — is
`m-execution-authority`'s *Join authority*.

A standalone read or stream opens no transaction, so no transaction option
applies to it: a scope whose effective preference is `locking` does not make a
standalone read take the shared lock (`m-read-lock`).

## Model Editions

A **Model Selection** is a fully prepared, process-local, immutable selection of
one accepted model under one **Model Edition**, an opaque nonempty token compared
only for equality. Preparation completes every fallible derivation the model
determines — member layouts, row facts, graph-construction facts, and the
configured Write Planner with its write payload preparer — before the selection
can be served, so no request
path derives any of them. Preparation guarantees structural readiness, not
schema readiness, valid stored data, or the success of a later operation.

A root's **Serving Model** holds its current selection. Reading it returns that
exact selection with no compilation, I/O, or callback. Publishing a candidate
replaces it atomically only when the held selection is the exact one the
publisher expected, compared by identity rather than by edition, and a stale
publication is refused, naming the expected and the held selection, leaving the
current one in place. Holding a root confers no authority to change the model it
serves.

Every execution **adopts** a selection once and keeps it to completion:

- a standalone eager read adopts before it starts, and the whole result is
  served under that one selection;
- a stream adopts at entry, and every page it reads and every root it publishes
  stays on that edition, with no page-level interface introduced to say so;
- each transaction attempt adopts before its physical boundary begins; a joining
  call inherits the attempt's selection and never renegotiates it, and a retry
  adopts afresh.

A publication landing after adoption revises nothing already adopted. A result
retains the edition it was read under, and a delayed refusal of its invalid
stored data, like a failure raised during execution, reports that same edition.
How the edition is exposed — on a result, an entered stream, a transaction, or a
failure — is a language-surface concern; that there is exactly one per
execution, fixed at adoption, is this contract's.

## Attempts

An **Attempt** is the execution state of one physical transaction attempt. A
**writable** attempt holds its unit of work, connection, adopted selection,
attempt activity, resolved options, captured authority, and flush state; a
**read-only** attempt holds the same less the unit of work and everything only a
write needs. Every attempt has one **lifetime**: whether it still admits work,
whether it is rollback-only, and the first failure that made it so. The lifetime
is the one state the attempt's handles and streams, the calls joining it, its
commit, and a writable attempt's unit of work all consult; a failure escaping a
joined callback, and one escaping a writable flush, doom that same lifetime. The
runtime constructs the attempt, wires every execution dependency its unit of
work needs into it, and only then hands it to the lifecycle's transaction surface
and the application callback — so neither can observe an Attempt whose unit of
work is not ready. A retry constructs a fresh Attempt; a joining call reuses the
active one, and the lifecycle surface the outer attempt was handed, rather than
constructing another. The port owns the physical begin, commit, and rollback
(`m-db-port`), the lifetime owns rollback-only state, and a writable attempt's
unit of work owns buffering and the pre-commit flush (`m-unit-work`).

Once the callback returns, an attempt refuses to commit a rollback-only
lifetime, then — writable only — flushes what its unit of work still buffers
while the lifetime admits work, and finally fences its handles and streams
before the port commits. A callback or completion failure withholds the
callback's value, discards a writable attempt's buffered state, fences the
attempt, and the port rolls back.

### Read-only transactions

A **read-only transaction** is an invocation made through the read-only
entrypoint, which hands its callback a surface with reads and no modeled
mutation. Its access mode is the entrypoint's, fixed for the whole invocation —
never by an option, a join, or a read:

- every attempt asks the port for a read-only boundary at the resolved level,
  and every attempt of a writable invocation asks for a read/write one
  (`m-db-port`), so neither mode is inherited from a native default;
- its reads take no participation lock — the unversioned fallback a writable
  read takes included (`m-read-lock`) — stamp no participation on what they
  publish, and force no flush, since nothing is buffered; the surface offers no
  mutation, so the runtime refuses one before native enforcement could;
- a joining call is admitted only in the same mode: a writable call while a
  read-only transaction is active, or a read-only call while a writable one is,
  is an **access-mode mismatch**, refused before its callback runs;
- immutable results remain readable after commit, while a live stream cannot
  outlive its attempt; no result licenses a source mutation in a later writable
  attempt, though the revisions it carries can state a caller-addressed write's
  condition (`m-unit-work` *Current-attempt source admission*).

Read-only prohibits modeled mutations. It promises nothing about external
effects of the callback's own code, and what the native transaction refuses or
locks implicitly is the provider's. A standalone read made while a transaction
of either mode is active stays standalone: it leases its own connection and is
never redirected into the active attempt.

### Reads under an Attempt or a scope

A read through a scope or an Attempt runs one fixed ladder: refuse re-entry from
inside a lifecycle handler (`m-execution-lifecycle`), adopt (or, inside an
Attempt, reuse the adopted selection), have the lifecycle build its Publication
from the adopted read projection, convert and validate the query against the
adopted model, then — inside an Attempt — admit the read through the attempt's lifetime,
which a writable attempt does through its unit of work's read gate, forcing its
pending writes out first (`m-unit-work`), and finally deliver the read inside
its Read or Stream activity and connection bracket. A model-dependent refusal
therefore precedes query conversion and any force-flush, and a stream
converts its query when it is constructed but adopts and builds its Publication
only at entry. A standalone read leases a connection for its read, and a
standalone stream for each page (`m-read-delivery` *The connection a delivery
holds*); a read inside an Attempt runs on the Attempt's connection.

Execution retains each eligible Page's write observations, so that a published
value can later serve as a write source (`m-unit-work` *Write value provenance*).
It records projections while the Page is converted and constructs the origins
lazily once the Page is sealed, handing them to the Publication by reference
and retaining no Page.

### Row acquisition

A write that must read existing rows reads them through the unit of work's
**row acquisition** port (`m-unit-work` *Row acquisition*), which execution
implements once for every request kind: plan the entity's row read, execute it,
assemble its flat Page, and hand the unit of work's consumer the judged member
rows and aligned raw documents while the Page's resources are still live.
Execution settles the read afterwards whatever the consumer did — finished,
stopped early, never started, or raised. The request kind decides the bracket:

| Request | Bracket |
|---|---|
| Target of a Locking caller-addressed write | its own Read under the attempt, with no force-flush |
| Coverage of a deferred range | a read Database Call inside the current Flush, opening no Read; one per bounded statement its uncovered parts need |
| Completion of retained rows | none: no statement, Database Call, or activity, before the range's coverage is read |

A row whose stored data is invalid is refused with the same judgement and
refusal every other read uses (`m-read-delivery` *Invalid stored data*) before
it contributes evidence. A retaining target read hands its consumer each row
with only what a read of the row alone judges judged, and its Value Object
occurrences pending; a completion judges those occurrences, from the retained
row alone, with the judgement and refusal the read would have applied to them.

### Flush execution

The unit of work runs the Write Plan a flush finalizes Write Group by Write
Group, binding each deferred settled write at its turn and completing every
settled write of a group before a later group executes (`m-unit-work` *Write
Groups complete before later work runs*). Execution implements the
step-execution port: it runs each sequence of Planned Steps the unit of work
hands it — a Write Group's steps, or the steps a deferred range bound — inside
the Flush the unit of work opened for the flush. It lowers those Planned Steps
through one shared path — the planner's payload preparer prepares what the
statement about to run stores, and `m-sql` renders it — executes them through
the port, and has the unit of work enforce each step's affected rows; for steps
opening rows whose keys the database allocates, it answers those keys in step
order. An execution returns once every step it was handed has succeeded, and
holds nothing of them afterwards. Execution neither walks a plan's Write Groups
nor interprets their settled writes' completions, so no later group's
statement is prepared or lowered before the earlier group completes, and a
later step's lowering failure cannot overtake it. A failed execution completes
no settled write, and the failure dooms the attempt.

Where the connection holds ordered write transport (`m-db-port`), a run of two
or more contiguous count-only effects on one row each — temporal closes,
guards, revisions, and removals, and Non-Temporal updates and deletes of one
key that expect an exact count — is presented in one invocation instead of one
call each; every other step, a multi-key or predicate-selected one included,
and every step on a connection holding none, runs alone. Whether a step
may join a run is decided from the step itself before its payload is demanded,
including the bound on binds its statement promises to fit the dialect's limit;
a statement exceeding that promise is a lowering failure. A run never crosses an
insert or a Write Group, and an internal statement cap ends it before another
step is even looked at. Before a run's first effect is lowered, execution looks
at the step after it, unprepared: where that step cannot join, or no step
remains, the effect would be its run's only one and runs alone, and the step
looked at waits its turn. Looking at a step reads the sequence it was handed
and cannot fail; only preparing or lowering a step can. The whole result is validated before any of it
is interpreted, so a malformed one fails the invocation with the integrity error
ahead of any shortfall it reports. Confirmed outcomes are then enforced in
original order against the exact steps they were lowered from: an earlier
shortfall outranks a later statement failure or interruption, a statement
failure propagates as itself, and an interruption no earlier outcome overtook
propagates last. Nothing after the run is lowered before the run is enforced.

Preparing or lowering a later effect of a run may fail ordinarily after earlier
effects were lowered. The run's lowered prefix is then presented and enforced as
it was selected — never lowered again, replayed, or split into calls of its own
— and that failure propagates only where the prefix succeeds. A failure lowering
the run's first effect presents nothing, and a control-flow or fatal exception
presents none of the prefix.

Ordered transport departs from running each step alone in exactly two ways.
Later effects of the current run can execute, and take locks, before an earlier
effect's shortfall is enforced, because a zero-row count is a successful
statement to the database; the failed Write Group still publishes nothing and
its attempt rolls back. And a later effect can be lowered before the prefix it
follows is submitted. Rollback, rollback-only state, retry classification of
the failure that propagates, and the precedence of cancellation and fatal
exceptions are unchanged.

Execution inserts a run of contiguous single-entry inserts of one Entity naming
the same members and holding no generated value — a range's temporal openings,
or inserts of distinct objects one Write Group lays out together — with one
multi-row statement (`m-sql` *Requested ranges* and *Batched insert / update*),
on every connection, whatever the Entity's temporality. Each insert remains its
own Planned Step, and the statement is one ordinary Database Call. Whether an
insert may join is decided from the step before its payload is demanded. Before another step is looked at the statement must have
room for one more entry within the dialect's bind limit (`m-dialect`) and an
internal entry cap; at that capacity the statement runs before another step is
looked at, and otherwise the one step looked at that cannot join waits,
unprepared, until the statement has run. A run never crosses a Write Group or
an effect, so no insert moves ahead of an effect before it. A logical
multi-entry insert, which batching formed by membership (`m-batch-write`), runs
alone and is never split or joined; any other insert runs alone as before.

Preparing or appending a later insert of a run may fail ordinarily.
The inserts appended before it are then inserted as the one statement they were
selected as — never prepared again or inserted one at a time — and that failure
propagates only where the statement succeeds. A failure preparing the run's
first insert inserts nothing, and a control-flow or fatal exception inserts
none of the run.

A grouped statement succeeds or fails as a whole, however many objects its rows
belong to. Its failure is the statement's own database error, classified and
judged for retry as any statement's is; it can name another constraint,
message, or category than the error the earliest failing row would raise alone,
and it is neither attributed to a row or an object nor explained by replaying or
reading anything. A Write Group whose statement fails completes none of its
settled writes, and its attempt rolls back and becomes rollback-only exactly as
for any other failure.

A Write Group presents every effect before any insert (`m-unit-work` *Write
Group formation*), so where two of its settled writes would each fail, the
failure presented first is the one that propagates: a later write's effect
shortfall can precede an earlier write's insert violation, and the two can
differ in retry eligibility. Either way the group completes none of its settled
writes and its attempt is doomed; which of two independent failures is reported
is not promised to match executing each settled write alone.

## What the suite pins down

| Case | What it proves |
|---|---|
| root-default resolution | an outer invocation that names no option resolves all four from the configured root, states them on its invocation, and runs its attempt and read on one connection |
| read-only invocation | a read-only invocation requests a read-only boundary at its explicit level, a read-only join reuses its attempt, nothing is flushed, and the invocation states its access mode and no preference |
| cross-mode joins | a read-only call under a writable transaction, and a writable call under a read-only one, are each refused before their callbacks run |
| access-mode setup failure | a refused access-mode setup opens no boundary and finishes the attempt begin-failed, terminally |
