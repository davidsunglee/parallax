# m-batch-write — Buffered Batching / Readless Predicate Writes

`m-batch-write` distinguishes two related but non-interchangeable write families:

1. **buffered tracked-row batching** at an `m-unit-work` boundary, where the unit
   of work already holds an enumerated set of objects; and
2. **predicate-selected writes** over a bare `m-predicate` predicate, whose
   canonical instruction is supplied by `m-case-format`.

It owns only the set-based/readless vocabulary for the second family, including
which targets that family can write at all, when its statement runs, and the count
its verb returns. Versioning,
locking, conflict abort, and temporal chaining belong respectively to `m-opt-lock`,
`m-read-lock`, and `m-temporal-write`. The canonical golden SQL is
fixed by `m-sql`.

`m-batch-write` decides only **compatibility**: whether two buffered writes may
share one step. The Planned Step algebra and the affected-row policy that step
then carries are `m-write-plan`'s, and the flush's stage order is
`m-unit-work`'s; this module reaches planning through the strategy port that
module declares.

## Batching is a membership decision

Batching is expressed by **membership in one Planned Step**, not by a marker on
several. Compatible inserts become one Planned Insert with several entries;
compatible uniform keyed updates or deletes become one Planned Update or Planned
Delete whose Key Target holds several key tuples.

- An implementation **MUST NOT** introduce a batch flag, batch identifier, group
  wrapper, or per-row batch annotation. Two writes either share a step or they do
  not, and that is the whole of the decision.
- Execution grouping is a separate fact. A Write Group (`m-unit-work` *Write
  Group formation*) decides which settled writes execute and complete together,
  and execution may present their steps in shared calls (`m-execution`), but two
  writes of one group never share a step: membership in one step stays this
  module's decision alone.
- Incompatible writes remain **separate logical steps**. In particular a
  **per-row gated** write (`m-opt-lock`) can never join another: its gate binds
  one row's observed version, so each stays its own step even where a driver
  later transmits several in one batch.
- Batching shares the canonical member shape and uniform values across the step;
  it **MUST NOT** deep-copy one assignment payload per addressed row.
- Membership does not change semantics. One multi-key Key Target owns **one
  aggregate** affected-row expectation for the rows it names (`m-unit-work`);
  collapsing writes together never weakens or discards that expectation.

## Set-based flush

- Multiple inserts of the same entity collapse into a **single multi-row
  `INSERT`** (one statement, many value tuples) rather than one statement per
  row.
- Multiple updates of the same entity that set the same columns collapse into a
  **batched `UPDATE`** — executed once per distinct key, or as a single statement
  with an `IN` predicate when the new value is uniform across the keys.
- Multiple deletes of the same **non-versioned** entity collapse into a **single
  `DELETE`** with an `IN` predicate (`delete from t where id in (?, …)`) rather
  than one statement per row — the delete analogue of the multi-row `INSERT`. (A
  **versioned** entity's set-based delete cannot collapse — see below.)

The canonical Postgres golden SQL (`m-sql`), as `then.statements` entries:

```yaml
# m-batch-write-001 (set-based flush) then.statements:
- sql:
    postgres: insert into account(id, owner, balance) values (?, ?, ?), (?, ?, ?), (?, ?, ?)
# m-batch-write-002 (update per key) then.statements:
- sql:
    postgres: update account set balance = ? where id in (?, ?)
# m-batch-write-003 (batch DELETE collapse) then.statements:
- sql:
    postgres: delete from wallet where id in (?, ?, ?)
# m-batch-write-004 (versioned delete materializes per key, locking mode) then.statements:
- sql:
    postgres: delete from account where id = ?
```

The suite proves the batched forms against real data by **applying** the golden
DML and asserting the resulting table state — the write-sequence machinery
(`m-case-format`), reused for the non-temporal batched case (cases
`m-batch-write-001` / `m-batch-write-002` for the insert/update collapse,
`m-batch-write-003` for the DELETE collapse, `m-batch-write-004` for the versioned
per-key delete). So "buffered writes flush as set-based SQL" is verified by the
rows it leaves behind, not merely asserted.

## A predicate-selected write is readless, or refused

A predicate-selected write is **one readless statement**, so its target is an
**unversioned, non-temporal** Entity. Every write of an existing object of any
other target is judged against that object's own prior observation: a
**versioned** target's version, under **both** Effective Concurrency Strategies —
Optimistic binds it as that row's gate, while Locking needs the read that took
its shared lock (`m-opt-lock`) — and a **temporal** target's current milestone,
which the write closes and chains from (`m-temporal-write`). One predicate
statement can neither carry nor acquire such an observation.

A model-aware validator therefore **MUST** refuse a predicate-selected write
whose target is versioned (any Attribute of its family declares
`optimisticLocking`) or temporal (Transaction-Time-Only or Bitemporal), with the
pre-SQL rule `set-based-write-target-unsupported` (`m-case-format` *Rejected
cases*). It is judged once the target Entity resolves and before the write's
predicate, inheritance family, or payload, because none of them could make
the write admissible. The refusal is a preparation refusal
(`m-unit-work`): nothing is read, nothing pending is flushed, and the attempt is
not doomed. An implementation's refusal **SHOULD** name the writes that reach
such a target: reading its objects and writing each one by key, or a
caller-addressed write stating the revision the caller holds — and, for a
temporal target, a termination rather than a deletion.

`m-batch-write-047`, `-048`, and `-049` witness the refusal for a versioned, a
Transaction-Time-Only, and a Bitemporal target.

## Predicate-selected readless forms

A predicate-selected write is an `amend`, a `replace`, or a `delete`. Its target
has no history to close and no Valid Time to bound, so the family has no
milestone verb and states no window. It emits exactly one statement, whatever members it assigns. A Value
Object occurrence — `one` or `many`, any nested `many` it holds included — and a
scalar collection are each assigned whole at their own path, exactly as any
other amendment assigns them (`m-storage-layout`): the statement reads no stored
value, inspects no authored content to choose its route, and writes no element
alone. `amend` is:

```text
update <table> set <column> = ?, … where <predicate>
```

There is no equality-elimination pass: rows already equal
to an assigned value are still matched by ordinary SQL set semantics. The
emitted `set` columns and their assignment-value binds follow `m-sql`'s physical
DML rule: filter the assigned cells from the target Entity Layout in Table
Layout order, regardless of the instruction's ordered assignment list.
Predicate binds come after those assignment binds. `delete` is exactly:

```text
delete from <table> where <predicate>
```

A `true` predicate selects every row of the target, exactly as it does in a read
(`m-predicate`), and needs no further opt-in: the statement then carries no
`where` clause at all — `update <table> set <column> = ?, …` or `delete from
<table>` — never `where true`. The target refusal above still applies first, so
only an unversioned, non-temporal target is ever written whole.

Where a demand of the predicate reads a shared to-one join (`m-sql` *Shared
to-one joins*), the `where` instead tests the membership of the target's physical
primary key in a selection of the rows the predicate matches, `<key> in (select
t0.<key> from <table> t0 <joins> where <predicate>)`, inside the same statement:
the write still reads nothing back and returns no key, and the selection's binds
still follow the assignment binds.

The selection is part of the statement's own read, not a re-test of each target
row as it is written. Under Read Committed (`m-db-port`), a target row that a
concurrent transaction changes and commits while the statement waits for it may
therefore still be written even where the committed version's own columns, the
correlation columns its joins read included, no longer match. Read Committed
permits that outcome without requiring it, so nothing may depend on either
result. Which one occurs is engine behavior: PostgreSQL writes the row, because
it re-tests the newer version only for key membership in the selection its
snapshot already read; MariaDB reads a `delete`'s selection with a locking read
that waits for the concurrent commit and then excludes the row. Under
PostgreSQL's Repeatable Read the same race raises the snapshot conflict
`m-db-error` classifies as retryable, whichever form the write takes.

`replace` states a whole state rather than changes. Its `row` is completed as
every replacement's is (`m-unit-work` *Source-authorized replacement*): an
omitted nullable member is written null, an omitted collection is written
empty, and an omitted required member is refused before anything executes
(`write-required-attribute-missing` / `write-required-value-object-missing`).
The completed state then lowers exactly as an `amend` assigning every one of its
members does — the same Table Layout order, the same binds ahead of the
predicate's, and the same key-selecting form through a shared to-one join.
Its predicate selects the rows, so a primary-key member the row states
addresses nothing: it is accepted, so a state read or echoed back needs no
stripping, and it is never written. Under Relational Document Layout a
completed null is JSON null at the member's own path, never the removal of its
key, so a document key no member declares survives the replacement as it
survives any amendment.

`m-batch-write-005` pins readless predicate delete and
`m-batch-write-006` pins the update's layout-order SQL and bind determinism.
`m-batch-write-051`–`-055` pin the replacement.

A readless statement that **matches zero rows succeeds with zero affected rows —
never an error** — and its verb returns `0`. Ordinary SQL set semantics already make `update … where
<predicate>` and `delete … where <predicate>` no-ops when nothing matches; a
predicate-selected write that matches nothing simply wrote nothing. This is
categorically distinct from the shortfall an
**observation-backed** per-row write raises (`m-opt-lock` / `m-temporal-write`),
which fires when a row the caller **did** match and observe was concurrently
changed underneath it. Both effective strategies raise it, and the settled gate
decides which one it is: a gated shortfall is an Optimistic Conflict, an ungated
one a Stale Write (`m-unit-work`). Matching nothing is never either.

An `amend` whose assignment list is empty is the **empty amendment**. It is
judged exactly as any other predicate-selected write is — its target, including
the refusal above, its predicate, and its inheritance family, and the attempt's
lifetime — and its verb then returns `0`: it emits no statement, makes no
database call, opens no Flush, and leaves every buffered write pending. A keyed
amendment expressing no member is empty in the same way (`m-unit-work`).
`m-batch-write-050` witnesses it. A `replace` of an Entity whose only writable
member is its key writes nothing either, since the key is never written, and
returns `0` the same way. An amendment assigning a member the value it already
stores is not empty.

### A predicate-selected write executes at its call

Unlike a keyed write, a readless predicate never reveals which rows it touches:
its read/write set is whatever the predicate matches when its statement runs.
Its statement therefore runs **at the call**, never from the buffer, and every
write buffered before it reaches the database first. A nonempty
predicate-selected write opens one Flush with the `predicate-write` trigger
(`m-unit-work`, `m-execution-lifecycle`), which executes and completes every
Write Group the unit of work buffered before it and then the predicate's one
statement; with nothing buffered, that statement is the Flush's only work. It is
never buffered, claims nothing, joins no Write Group, and is planned apart from
every buffered write, so no write is ordered across it and its statement executes
exactly once. The statements a transaction emits are therefore those of an
authored order in which every write buffered before the predicate write precedes
it and every later write follows it.

The verb returns the **affected-row count** of that one statement as an integer:

- an `amend` or `replace` counts every row its predicate matched, including a
  matched row whose stored values it left unchanged;
- a `delete` counts the target rows it deleted;
- a statement matching nothing counts `0`.

The count is the outer statement's own result as the configured driver reports
it (`m-db-port`, `m-dialect` *Unchanged-row count*), not a count of value
transitions, of separately selected keys, or of rows a cascade or trigger
changed. A Postgres `UPDATE` a `BEFORE UPDATE` trigger skips for a row writes and
counts nothing for it. The key-selecting form's isolation differences above are
unchanged: a normalized count does not normalize which rows a concurrent
transaction leaves the selection to match.

Preparation judges the write — its target, predicate, inheritance family,
payload, and the attempt's lifetime — before anything buffered executes, and a
refusal there executes nothing. A refusal planning the buffered writes fails the
Flush and leaves them pending in a usable attempt, and a failure executing them
dooms the attempt before the predicate's statement is built. Once they
completed, a refusal building or auditing the predicate's own statement fails
the Flush without dooming the attempt or returning the completed writes to the
buffer, while a failure lowering, executing, or enforcing it dooms the attempt
(`m-unit-work` *Abort*). A statement error therefore surfaces at the verb; a
constraint the database defers still fails at commit.

## What the suite pins down

The existing `m-batch-write-001`–`-004` cases prove only **buffered tracked-row
batching**: multi-row insert, uniform-key update, non-versioned `IN` delete, and
versioned per-key delete. The predicate-write witnesses prove a distinct target:

| Case | Target | Predicate-write witness |
|---|---|---|
| `m-batch-write-005` | non-versioned `Wallet` delete | one readless `delete … where <predicate>` |
| `m-batch-write-006` | non-versioned `Wallet` update | one readless update; reversed authored assignments still emit Entity Layout order and assignment-before-predicate binds |
| `m-batch-write-009` | unversioned, non-temporal document-mapped `Traveler` update | one readless update replacing a top-level document-resident `many` whole at its path, every other key kept |
| `m-batch-write-010` | unversioned, non-temporal document-mapped `NestedRoute` update | one readless update replacing a `one` whose authored content holds a nested `many`, its whole subtree included |
| `m-batch-write-012`/`-013` | unversioned, non-temporal `CollectionTwinItem` update under each layout | one readless update assigning whole scalar collections and a `many` holding one, in Table Layout order |
| `m-batch-write-056`–`-061` | unversioned, non-temporal `LayoutTwinItem` amendment, replacement, and delete under each layout, selected by `true` | one readless statement with no `where` clause, counting every row |
| `m-batch-write-050` | non-versioned `Wallet` update assigning nothing | judged, then returns `0`: no statement and no database call |
| `m-batch-write-051` | non-versioned `Wallet` replacement | one readless update; a reversed authored row still emits Table Layout order and assignment-before-predicate binds |
| `m-batch-write-052` | non-versioned `Wallet` replacement stating a key | the key is accepted and never written |
| `m-batch-write-053` | unversioned, non-temporal `OrderItem` replacement through a shared to-one join | the key-selecting form; the omitted nullable `shippedOn` written null |
| `m-batch-write-054` | unversioned, non-temporal document-mapped `Traveler` replacement | omitted members completed as JSON null and the empty array at their paths; an undeclared document key survives |
| `m-batch-write-055` | non-versioned `Wallet` replacement omitting `balance` | refused: `write-required-attribute-missing` |
| `m-batch-write-047` | versioned `Account` update | refused before its predicate and assignments: `set-based-write-target-unsupported` |
| `m-batch-write-048` | Transaction-Time-Only `Balance` delete | refused: `set-based-write-target-unsupported` |
| `m-batch-write-049` | Bitemporal `Position` replacement | refused: `set-based-write-target-unsupported` |
| `m-batch-write-011` | unversioned, non-temporal `OrderItem` update after a buffered delete and before buffered inserts | runs at its call after the delete; the inserts follow at commit |
| `m-execution-lifecycle-011` | non-versioned `Wallet` updates and deletes after a buffered insert | each nonempty write is one `predicate-write` Flush returning its count, an unchanged match and a match of nothing included; the empty one opens none |

The two families share SQL terminology but not an observation contract: an `IN`
list can collapse an already tracked set, whereas a predicate write starts from an
operation, observes nothing, and so writes only a target that needs no per-row
observation.
