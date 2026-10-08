# m-execution — Execution Runtime

`m-execution` is the lifecycle-neutral runtime over the database port: the
**Database Root** that owns one runtime's resources, the **Execution Scopes**
derived from it, the resolution of transaction options, the serving and adoption
of Model Editions, and the **Attempt** that runs one physical transaction
attempt. It executes reads by handing them to `m-read-delivery` under the
conditions it establishes, and executes writes by running the Write Plan
`m-unit-work` finalizes, acquiring the rows a write needs to read, and reporting
each completed unit back. Per the dependency graph it depends on `m-unit-work`
for admission, evidence, finalization, and effects; `m-read-delivery` for every
read it executes; `m-write-plan` for the plan and units it runs;
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

A root is connected with one complete, immutable record of the four
**transaction options**: the retry bound (`m-auto-retry`), the Concurrency
Preference (`m-unit-work` *Strategy selection*), the optimistic-conflict retry
opt-in (`m-auto-retry`), and the Isolation Level (`m-db-port`). A root
connected without a record carries the built-in record: **ten** re-executions,
the **`optimistic`** preference, the opt-in **off**, and **Read Committed**.
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
exposes it as a value of the same shape the root and scope carry.

A joining call never renegotiates. An omitted option inherits the active
transaction's resolved value; an explicit option equal to that value is
accepted; an explicit option different from it is an **option conflict**,
refused before the joined callback runs. Neither the joining scope's effective
record nor its root's enters that comparison on its own, so under an outer call
that overrode its default, a join naming that default conflicts. Options are
exact values rather than an ordered substitution rule: a join naming Read
Committed under a Serializable boundary conflicts rather than weakening what the
boundary already satisfies. The order of the join refusals — ownership, then
rollback-only, then authority, then explicit options — is
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

An **Attempt** is the execution state of one physical transaction attempt: its
unit of work, connection, adopted selection, attempt activity, resolved options,
captured authority, and flush state. The runtime constructs it, wires every
execution dependency its unit of work needs into it, and only then hands it to
the lifecycle's transaction surface and the application callback — so neither
can observe an Attempt whose unit of work is not ready. A retry constructs a
fresh Attempt; a joining call reuses the active one, and the lifecycle surface
the outer attempt was handed, rather than constructing another. The port owns
the physical begin, commit, and rollback (`m-db-port`), and the unit of work
owns buffering, rollback-only state, and the pre-commit flush (`m-unit-work`).

### Reads under an Attempt or a scope

A read through a scope or an Attempt runs one fixed ladder: refuse re-entry from
inside a lifecycle handler (`m-execution-lifecycle`), adopt (or, inside an
Attempt, reuse the adopted selection), have the lifecycle build its Publication
from the adopted read projection, convert and validate the query against the
adopted model, then — inside an Attempt — force the unit of work's pending
writes out through its read gate (`m-unit-work`), and finally deliver the read
inside its Read or Stream activity and connection bracket. A model-dependent
refusal therefore precedes query conversion and any force-flush, and a stream
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
| Selection of a predicate write | its own Read under the attempt, after the unit of work has flushed pending writes through its read gate |
| Target of a Locking caller-addressed write | its own Read under the attempt, with no force-flush |
| Coverage of a deferred range | a read Database Call inside the current Write Batch, opening no Read; one per bounded statement its uncovered parts need |
| Completion of retained rows | none: no statement, Database Call, or activity, before the range's coverage is read |

A row whose stored data is invalid is refused with the same judgement and
refusal every other read uses (`m-read-delivery` *Invalid stored data*) before
it contributes evidence. A retaining target read hands its consumer each row
with only what a read of the row alone judges judged, and its Value Object
occurrences pending; a completion judges those occurrences, from the retained
row alone, with the judgement and refusal the read would have applied to them.

### Flush execution

Execution runs the Write Plan a flush finalizes, unit by unit in plan order,
inside the Write Batch the unit of work opened for it. It lowers each unit's
Planned Writes through one shared path — the planner's payload preparer prepares
what the statement about to run stores, and `m-sql` renders it — executes them
through the port, and has the unit of work enforce each step's affected rows. A
deferred unit is bound first: the runtime asks the unit of work to complete the
retained rows it reuses, acquire the coverage they leave, and bind both against
the ownership earlier units published, then executes the bound steps. After a unit's steps all succeed — including a unit
with no steps — the runtime reports it to the unit of work, which publishes its
effects before the next unit binds (`m-unit-work` *Execution units complete
before later work runs*). No later unit's statement is prepared or lowered
before the earlier unit completes, so a later step's lowering failure cannot
overtake it. A unit that fails is never reported, and the failure dooms the
attempt.

## What the suite pins down

| Case | What it proves |
|---|---|
| root-default resolution | an outer invocation that names no option resolves all four from the configured root, states them on its invocation, and runs its attempt and read on one connection |
