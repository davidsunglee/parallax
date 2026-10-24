# The write flow

A write in Parallax is a request to change one object, or the rows a predicate
selects, inside a read-write transaction. Nothing reaches the database when you call
the verb. The write is judged, licensed and buffered; later, at a flush, every buffered
write is combined, ordered and turned into a fixed sequence of statements. This page
follows a write through those stages, names what licenses each kind of write, and
explains why a write that cannot show what it overwrites is refused.

Each stage names the specification that owns it. This page explains and links; when
it and a specification seem to disagree, the specification is right.

## The flow at a glance

```text
 Authored Instruction        what to write: a verb, the Entity, the row it states,
      │                      a Valid-Time window; keyed, target or predicate-selected
      ▼
 Prepared Instruction        judged once against the model: target, verb, window,
      │                      revision, then payload; refused before anything is buffered
      ▼
 Admitted Write              licensed by an observation, a lock, this attempt's own
      │                      insertion, or a revision the caller states; or an insert
      ▼
 composition                 writes of one object combine in the buffer: merged,
      │                      superseded, cancelled, or composed over its coverage
      ▼
 ordering                    at a flush: no-ops dropped, compatible writes batched,
      │                      parents inserted first and deleted last
      ▼
 settlement                  each write becomes Planned Steps: temporal expansion,
      │                      gates, audit; grouped for execution
      ▼
 execution                   Write Group by Write Group: SQL, affected-row checks,
                             and what each completed write publishes to later ones

 A predicate-selected write leaves this path after preparation: it runs at its call.
```

## The stages

### Authored Instruction

Every write a transaction buffers, through any interface, is a
[Write Instruction](../../core/spec/m-unit-work.md#write-instruction-vocabulary): the
write-side counterpart of the Object Query. It comes in three shapes:

- a **keyed** instruction writes the one object a value names: `insert`, `amend`,
  `replace`, `delete` or `terminate`, with a bounded form for Bitemporal writes;
- a **target** instruction writes one object by primary key under the revision its
  caller states;
- a **predicate-selected** instruction amends, replaces or deletes every row a
  Predicate matches.

The instruction names the Entity and states rows and a Valid-Time window. It never
carries a Transaction-Time instant, which the clock supplies at the flush, or a version
the framework observed, which stays with the value that observed it. So nothing a caller
writes can forge either one. The Typed and Wire interfaces spell the same instructions,
and an instruction's canonical document round-trips losslessly.

### Prepared Instruction

[Preparation](../../core/spec/m-unit-work.md#serialized-write-elaboration) is the one
judgment every write crosses, whichever interface it came through. It resolves the
target first and asks whether the target admits the write at all: a temporal target
refuses `delete`, a window must suit the target's profile, and a predicate-selected
write refuses any target that would need to be read first. Only then is the payload
judged, member by member, into managed values.

What comes out is immutable, and nothing downstream decodes or judges it again. A
refusal here happens before anything is buffered, and it leaves the transaction usable.

### Admitted Write

A keyed write against existing state needs a **licence**: something that proves the
write knows what it is overwriting. Admission checks the licence at the verb, before
the write is buffered
([current-attempt source admission](../../core/spec/m-unit-work.md#current-attempt-source-admission)).

| Licence | What it is | Where it comes from |
| -- | -- | -- |
| Observation | the [State Observation](../../core/spec/m-write-plan.md#state-observation) a read of this attempt took: the version, or the Transaction-Time start of the milestone it read | reading a versioned or temporal Entity inside the writing transaction |
| Lock | the shared row lock a read of this attempt holds | reading an unversioned Non-Temporal Entity, which has no state to observe |
| Insertion | this attempt's own insertion of the object | the inserted value and every value derived from it ([insertion authority](../../core/spec/m-unit-work.md#insertion-authority)) |
| Stated target | a version or Transaction-Time start the caller states | a [target write](../../core/spec/m-unit-work.md#target-writes) |

An insert needs no licence: it opens a row rather than writing over one.

The Entity's effective strategy decides what protects an observed write
([strategy selection](../../core/spec/m-unit-work.md#strategy-selection--one-preference-an-effective-strategy-per-entity)).
Under Optimistic, the statement is gated on the observed revision, so a concurrent
change makes it match no row. Under Locking, the shared lock the read took keeps the
row as it was read, and the statement is ungated. An unversioned Non-Temporal Entity
always locks.

**Why a blind write is refused.** A write with no licence would overwrite whatever is
stored, including a change another transaction made after you looked. There would also
be no revision to gate on or to advance from
([framework-owned versions](../../core/spec/m-opt-lock.md#version-values-are-framework-owned)).
The licence must also come from the writing attempt itself. A value from a standalone
read, a read-only transaction or an earlier attempt is refused at the verb, whatever key
or revision it carries: its read took part in nothing the writing attempt can stand on,
and after a retry its revision would be one the new attempt never read
([ADR 0072](../adr/0072-source-writes-are-admitted-only-by-a-read-of-the-current-attempt.md)).
Two ways remain. Read the row again inside the transaction, or state the revision you
hold in a target write. The difference matters on retry. A retried attempt re-runs its
reads and so observes afresh, while a stated revision stays exactly what the caller
said, and fails as the caller's precondition if the row has moved.

Two judgments about the value itself come earlier still, before the write is
prepared. Its provenance must suit the verb: an `amend` of a value no read produced
names `insert` as the verb you meant, and an `insert` of a stored value names `amend`
([write value provenance](../../core/spec/m-unit-work.md#write-value-provenance)). And a
value read at a past Transaction-Time instant is refused, for the reason
[the temporal model](temporal-model.md#why-a-past-transaction-time-view-is-read-only)
gives. An `amend` that assigns nothing is dropped only after its source is admitted, so
stating nothing never lets an ineligible value through.

### Composition

Writes of one object in one transaction combine in the buffer before anything executes
([same-transaction write coalescing](../../core/spec/m-unit-work.md#same-transaction-write-coalescing),
[ADR 0023](../adr/0023-same-transaction-writes-coalesce-in-the-unit-of-work.md)):

- **An insert takes later edits.** Insert-then-amend writes one row with the final
  values. Insert-then-delete cancels and writes nothing. A Bitemporal opening takes
  each edit over its own part of the window, so the flush opens only what survives.
- **Writes of existing state combine at their claim.** Each write claims what it
  settles against: the observed state, or the object for an unversioned row. A second
  write of the same claim merges its assignments into the first, a deletion supersedes
  them, and a repeated deletion adds nothing
  ([observed-state coalescing](../../core/spec/m-unit-work.md#observed-state-coalescing)).
- **A temporal object's writes compose over its coverage.** They form one
  [Coverage Transform](../../core/spec/m-temporal-write.md#coverage-transform), which
  [the temporal model](temporal-model.md#how-a-write-composes-over-coverage) describes.

Composition never loses a licence: the surviving write keeps the condition of every
write that composed into it. A write that cannot combine with what is pending, such as
an assignment after a deletion of the same object, is refused at its verb as already
claimed; so is a termination whose window overlaps another pending write's without
matching it. A read in the same transaction flushes the pending writes and
returns fresh state to write from.

### Ordering

At a flush, the [Write Planner](../../core/spec/m-unit-work.md#the-write-planner) takes
the composed buffer. Its first stages rewrite the sequence
([the planning pipeline](../../core/spec/m-unit-work.md#the-planning-pipeline)):

- Known no-op work is dropped, such as an amendment that names only the key.
- Compatible writes are batched into one Planned Step, such as several inserts into one
  multi-row `INSERT` ([batching](../../core/spec/m-batch-write.md#batching-is-a-membership-decision)).
  A write gated on an observation never joins a batch, because its gate belongs to one
  row.
- The rest is ordered into [Mutation Phases](../../core/spec/m-unit-work.md#write-group-formation):
  inserts parent-first, then updates in the order you wrote them, then deletes
  child-first, so foreign keys hold. An insert that must follow the removal clearing its
  way starts a new round of phases.

All of this happens before the Transaction Instant is captured, so a buffer that
cancels away never reads the clock
([the Transaction Instant](../../core/spec/m-unit-work.md#the-transaction-instant)).

### Settlement

Settlement turns the ordered writes into
[Planned Steps](../../core/spec/m-write-plan.md#the-planned-step-algebra): inserts,
updates, closes, deletes, and the revisions, removals and guards temporal writes use.
For each write it validates the observation the write carries, captures the Transaction
Instant if the write needs one, expands a temporal write over the milestones it reaches
([temporal expansion](../../core/spec/m-temporal-write.md#temporal-expansion)), decides
each gate, and lets audit finalize each row it produces.

A temporal write whose window reaches coverage no read observed cannot be expanded yet.
It settles as a **deferred** write: its meaning, gates and instant are fixed now, and
the flush reads the missing coverage when it reaches the write
([Write Plan](../../core/spec/m-unit-work.md#write-plan-and-planned-steps),
[row acquisition](../../core/spec/m-unit-work.md#row-acquisition)).

Settlement also forms the **Write Groups**: runs of settled writes of distinct objects
within one Mutation Phase, laid out with every effect before any insert
([ADR 0076](../adr/0076-write-groups-run-every-effect-before-any-insert.md)). The result
is the Write Plan, the one product of planning.

### Execution

The flush runs the Write Plan one Write Group at a time
([flush execution](../../core/spec/m-execution.md#flush-execution)). Each Planned Step
is lowered to SQL for the dialect, executed, and checked against the number of rows it
expected to affect, so a stale gate surfaces as a conflict rather than passing silently.

When every step of a group has succeeded, each of its writes **completes** before the
next group runs
([Write Groups complete before later work runs](../../core/spec/m-unit-work.md#write-groups-complete-before-later-work-runs)).
Completion invalidates observations of the states the write changed, carries the
licences of values that read those states on to what the write left, and records the
rows it opened, so later groups and later
writes stand on what this one did. A failure while executing dooms the attempt: it
accepts no more work and rolls back ([abort](../../core/spec/m-unit-work.md#abort)).

## Predicate writes run at the call

A predicate-selected write, such as `amend_where`, is one readless statement over
every row its Predicate matches
([`m-batch-write`](../../core/spec/m-batch-write.md#a-predicate-selected-write-is-readless-or-refused)).
Because it reads nothing, it has no observation to gate on and no milestone to close,
so it is allowed only on an unversioned Non-Temporal Entity. On any other target it is
refused before anything runs; write such an Entity by key after a read, or with a target
write.

It runs at its call, never from the buffer
([executes at its call](../../core/spec/m-batch-write.md#a-predicate-selected-write-executes-at-its-call),
[ADR 0077](../adr/0077-predicate-writes-execute-at-the-call-and-sources-continue-across-flushes.md)).
Everything buffered before it is flushed first, in the same flush, and the verb returns
the statement's affected-row count. It claims nothing, joins no Write Group, and tells
later writes nothing about the rows it reached.

## Flushes and reading your own writes

A flush happens for exactly
[three reasons](../../core/spec/m-unit-work.md#the-unit-of-work): a read that depends on
pending writes, a predicate-selected write, and the commit. There is no size threshold
and no flush you call yourself.

So a read inside a read-write transaction always sees the transaction's own writes: it
flushes them first, inside the still-open transaction, and a rollback still erases them.
A value you inserted can be written again without reading it back, because it carries
its insertion's licence until the attempt ends. A value you read stays usable after your
own writes change its row: its licence follows the state your completed writes left,
until a deletion, or a termination over the instant it was read at, leaves nothing of it
([observation ownership and lifetime](../../core/spec/m-unit-work.md#observation-ownership-and-lifetime)).

## Storage layout stays below the caller

An Entity's [Storage Layout](../../core/spec/m-storage-layout.md#storage-layout-transparency)
plays no part in the meaning of a write. Instructions, licences, composition and the
Planned Step algebra all speak in logical members and contain no physical column. The
layout is consulted only for physical work: deciding which rows can share one statement,
comparing what adjacent new rows would store, and, when a step is about to execute,
[payload preparation](../../core/spec/m-write-payload.md#row-assembly), which places
each member where the layout puts it, in its own Column or at a path in a shared
document, before SQL lowering renders the statement.

So a write leaves the same declared values, and replaces or keeps the same Value Object
occurrences, under either layout. What differs is physical: the statements, and the
fact that a document-layout update
[writes only the paths it assigns](../../core/spec/m-storage-layout.md#assignment-paths-and-mutation-composition-order)
and leaves every other key of the stored document standing.

## Common use cases

- **Change something you just read.** Read it inside the read-write transaction, edit
  the value, and amend or replace it. The read is the licence.
- **Create, then adjust.** Insert a value and keep writing through it. The flush writes
  one row with the final values.
- **Save a form shown earlier.** The value came from an earlier read, so state the
  revision it showed in a target write. If someone changed the row since, the write
  fails as your precondition, and a retry will not paper over it.
- **Change many rows of a simple table.** Use a predicate-selected write on an
  unversioned Non-Temporal Entity. It runs at once and reports how many rows matched.
- **Correct history.** Write a temporal Entity: the change appends new milestones and
  keeps what was known before. [The temporal model](temporal-model.md) explains how.

## Do it →

- [Non-Temporal entities](../../languages/python/docs/guide/04-writing.md#non-temporal-entities)
- [Transaction-Time-Only entities](../../languages/python/docs/guide/04-writing.md#transaction-time-only-entities)
- [Bitemporal entities](../../languages/python/docs/guide/04-writing.md#bitemporal-entities)
- [Target writes](../../languages/python/docs/guide/04-writing.md#target-writes)
- [Predicate writes](../../languages/python/docs/guide/04-writing.md#predicate-writes)
- [Wire writes](../../languages/python/docs/guide/04-writing.md#wire-writes)

How the Python implementation builds this flow, type by type:
[Write flow architecture](../../languages/python/docs/architecture/write-flow.md).
