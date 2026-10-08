# m-unit-work — Transactions & Unit of Work

`m-unit-work` is the transaction scope: the unit of work that **buffers,
finalizes, and flushes** writes, and the automatic read-correctness rules that
make in-transaction reads safe. It is expressed entirely in terms of **operations
and object state** (`m-predicate`): it depends on `m-predicate`, on `m-wire` for
serialized write-literal conversion, on the execution port `m-db-port`, on
`m-temporal-read` for the coverage it judges, on `m-write-plan` for the Planned
Write algebra it produces and the Write Observations it carries, on
`m-temporal-write` for the temporal expansion it drives, and on `m-edit`, which distinguishes authored assignments from state carried by
derivation, but **not** on `m-sql`. The
dialect-specific SQL the unit of work executes (the read-lock suffix, the
set-based forms) is produced by `m-sql` and run by the execution runtime
(`m-execution`) through the flush, write-batch, and row-acquisition ports this
module declares, so `m-unit-work` takes no direct edge to SQL generation. (`m-op-list` and
`m-navigate` in turn depend on `m-unit-work`, because a list is an
query-backed view resolved within a unit of work.)

Layered on the unit of work are four modules: the automatic shared read lock
(`m-read-lock`), bounded automatic retry (`m-auto-retry`), the transaction-scoped
identity map (`m-identity-map`), and the process-wide identity + query caches
(`m-process-cache`, deferred).

`m-unit-work` also owns **write finalization**: the Write Planner and its stage
order, which settle buffered writes into `m-write-plan`'s Planned Write algebra;
the authoritative affected-row enforcer; and the Write Effect Error family that
enforcer raises (ADR 0041, ADR 0048). Sibling policy modules
(`m-batch-write`, `m-opt-lock`, `m-read-lock`) keep their own policies and
reach planning and write admission only through strategy ports this module
declares, which model preparation (`m-execution`) wires in once per accepted
model.

## The unit of work

A **unit of work** (transaction) is the scope within which object reads and
writes are coherent. Within one unit of work:

- Writes are **buffered** as pending operations, not flushed eagerly. At the
  unit-of-work boundary they are **finalized** — combined, batched, and ordered
  to respect foreign-key constraints — then flushed in one pass.
- A read that depends on a not-yet-flushed write **MUST** observe that write: the
  unit of work flushes pending writes before serving a dependent read
  (read-your-own-writes), so a query never returns stale in-transaction state.
- Those two are the **whole** trigger vocabulary: a **read dependency** and the
  boundary's **pre-commit** batch. There is no size threshold, no periodic flush,
  and no caller-invoked one — physical write timing stays encapsulated, and a
  batch that reached the database is therefore attributable to exactly one of
  the two. The joined (nested) boundary adds no third trigger: it shares the
  outer unit of work's buffer, and the outer boundary's pre-commit batch is what
  flushes it. The second trigger is named for when it runs, because
  **finalization** already names the planner stage every batch of either trigger
  goes through.

Where an implementation owns connection lifetimes (`m-db-port`), each **attempt**
holds one connection. It is acquired after the attempt begins and before the
physical boundary opens, every read, write batch and participating delivery
inside the attempt runs on it, and it is released **before the attempt
finishes** — so a retry acquires afresh rather than replaying over what its
predecessor left, and the same physical connection coming back is the resource's
own business rather than the loop's. An attempt that cannot acquire one runs no
callback and opens no boundary: it is a boundary that never opened, with nothing
to undo and nothing to replay (`m-auto-retry`).

> **The transaction boundary is user-specified, per-language.** How a unit of
> work is opened and committed — a closure, a context manager, a decorator, an
> explicit `begin`/`commit` pair — is an idiomatic, per-language concern and is
> pinned down in the per-language spec, **never** in raw SQL terms in core. Core
> mandates the *observable effects within and at* the boundary, not its syntax.

### No identity promise

`m-unit-work` is expressed purely in **operations** — it promises nothing about
*object identity*. Without a claimed identity module, two reads of one row
within a unit of work MAY yield distinct managed instances, and mutating both
buffers conflicting updates whose interleaving is unspecified — a **named
hazard**, not a contract. The guarantee that one database identity resolves to
one managed object within the unit of work is `m-identity-map`; a plain-value
read surface (`m-snapshot-read`) has no managed instances to promise identity
for. This silence is deliberate in **both** directions: nothing here mandates
that two reads yield the *same* instance, and nothing may mandate they yield
*distinct* instances.

## Abort

A unit of work either **commits** or **aborts** (rolls back). A commit makes its
writes durable and observable; an **abort discards them entirely**. The
observable contract:

- A write performed inside a unit of work that aborts **MUST NOT** be observable
  after the abort — whether it was still **buffered**, had been **force-flushed**
  to serve a dependent read (read-your-own-writes), or had populated a cache. A
  find issued after the abort **MUST** re-resolve and observe the
  **pre-transaction** state.
- The transaction callback's return value is **withheld on abort**: if the unit
  of work rolls back — or its commit fails — the operation **fails** rather than
  returning the callback value as though it were durable (promoting ADR 0006 into
  normative text).

This reconciles the abort contract with the **read-your-own-writes forced flush**.
The forced flush is safe precisely *because* it lands **inside the still-open
atomic scope** the abort discards: the unit of work may push a buffered write to
the database mid-transaction so a dependent read observes it, yet an abort still
erases that write — the flush never escapes the transaction it belongs to. An
implementation **MUST NOT** satisfy read-your-own-writes with a flush that survives
the abort.

A failure while a flush **executes** its Write Plan — a database error, an
affected-row shortfall, or a failure applying a completed unit (*Execution
units*, below) — **dooms** the attempt before it propagates, whichever operation
triggered the flush. A doomed attempt accepts no further reads, writes, or
flushes, refuses commit, withholds the callback's return value, and rolls back,
even when the callback caught the failure and returned normally; the first
cause is retained. A refusal raised while a write is prepared, admitted, or
planned precedes execution and does not doom the attempt.

The suite proves this with a **rollback scenario**: a find, a write step whose
golden DML is applied and then **rolled back**, and the *same* find re-issued —
which **MUST** re-resolve and observe the **original** rows, never the aborted
write. The canonical proof also has a **grouped** form (`m-case-format`'s
scenario-step `uow` grouping): the observing find, the doomed write, and a
find RE-ISSUED INSIDE the still-open transaction all share one unit of work,
so that re-issued find is the forced-flush read-your-own-writes case above —
it **MUST** observe the write (the deletion, the new value) *before* the
group's abort, proving the forced flush lands inside the atomic scope the
abort discards, not merely that the abort discards a buffered write it never
served to a reader. A find OUTSIDE the doomed group, issued after the group's
rollback, is the ungrouped rollback scenario above: it re-resolves and
observes the original, pre-transaction rows.

## Write instruction vocabulary

Every write a unit of work buffers — from any frontend, of any shape below — is a
neutral **write instruction**, the write-side analogue of the Object
Query. The canonical, language-neutral shapes are hosted in
[`write-instruction.schema.json`](../schemas/write-instruction.schema.json), mirroring
how `m-predicate` hosts `predicate.schema.json`; `m-case-format` and
`m-conformance-adapter` reference that shape rather than redefining it. There are three:

- a **keyed** instruction — a `mutation` on one `entity` carrying the flat
  attribute-named neutral write input (`rows`);
- a **predicate-selected** instruction — a `mutation` on every row of a `target`
  (`entity` plus a bare `m-predicate` predicate) matching that predicate, with
  `assignments` on the update forms;
- a **caller-addressed** (target) instruction — a sparse patch (`update` /
  `updateUntil`) or a complete replacement (`replace` / `replaceUntil`) of the one
  existing `entity` object its `row` names by primary key, carrying its caller's
  own starting revision as `ifVersion` or `ifTxStart` (*Caller-addressed writes*).

The embedded predicate is a canonical `m-predicate` node, legal vocabulary here
because `m-unit-work` already depends on `m-predicate` (the dependency-graph edge);
the write instruction is the sole place the write side reaches the algebra.

**How a write instruction spells the Entity it addresses.** A keyed or
caller-addressed instruction's `entity`, a predicate-selected instruction's
`target.entity`, and the Entity prefix
of every `assignments[].attr` all carry an Entity spelling, and all three obey
`m-metamodel`'s identifier constraint and parse rule: an Entity's local name begins
capitalized, every namespace segment is lowercase, every member identifier is
lowercase-initial, and the last capitalized segment of a dotted reference is the
Entity's local name. Each position therefore admits exactly the two spellings a
reference position admits (`m-predicate`) — the bare local name, legal wherever it
names one declared Entity, or the canonical `<namespace>.<Entity>` — and resolves by
the same rule. An `assignments[].attr` is that Entity spelling followed by one
member identifier: `Account.balance`, `parallax.compatibility.Account.balance`.

Input is permissive and output is exact here exactly as it is in the Predicate
algebra: a frontend accepts either spelling, and every durable write instruction
it **serializes** MUST carry the resolved canonical one at all three positions.
The owner of an `assignments[].attr` is measured by IDENTITY rather than by text,
so a canonical owner names the write's exact target while a bare one two
namespaces share resolves nowhere and is refused — never silently matched against
the target's local name.

Three structural rules keep the instruction framework-honest:

- **The instant surface is dimension-explicit.** A Bitemporal write's authored
  Valid-Time lower bound is `validFrom`; bounded writes use `until` for the
  exclusive Valid-Time upper bound. Each authored bound is a finite instant: a
  serialized one is `m-wire`'s `timestamp`, decoded by that codec when the
  document is deserialized, and an unbounded write omits `until` rather than
  stating an infinite one. The Transaction-Time instant is *not* an
  instruction field — it is supplied at flush from the Clock Strategy (ADR 0010),
  so no caller-facing shape can smuggle one in. Compatibility-case `at` is harness
  clock context, not an alias or an instruction member.
- **The transaction observation is not an instruction field.** The framework-owned
  optimistic version / observed `in_z` a gated write binds (`m-opt-lock`) is attached
  **per materialized row at flush**, never carried on the durable instruction: the
  reserved `observedVersion` control key and both halves of an observed milestone's own
  coordinate (`observedTxStart` / `observedValidStart`) are explicitly **forbidden**
  on a `write-instruction.schema.json` write row, so an observation cannot round-trip
  as instruction state — the structural guarantee that versions stay framework-owned
  (ADR 0013). Neither milestone coordinate is a row cell at any location: a
  temporal write observes a whole predecessor milestone, which no flat row cell can
  name.
- **A temporal keyed instruction carries exactly one row.** A keyed instruction on a
  **temporal** target — one whose inheritance family derives an As-Of Axis, which for a
  descendant is the root's declaration it inherits unchanged (`m-inheritance`:
  temporality is family-level metadata only the root may declare) — **MUST** carry a
  single row. Each row of a milestone chain closes its own current milestone,
  consumes its own Temporal Observation, and
  opens its own successors, and a temporal entity never collapses into a set-based
  statement (`m-batch-write`), so several rows under one instruction denote several
  independent chains rather than one wider write. An implementation **MUST** refuse
  such an instruction rather than settle its first row: reducing it would silently
  discard the rows the author wrote and invent an observation-to-row mapping the
  instruction cannot express. The row count a keyed instruction may carry therefore
  depends on the target, which is why the neutral schema states the general
  one-or-more bound and defers this case to the model. The refusal's own witness is
  `m-unit-work-016`, a `rejected` case whose `when.write` is a whole keyed
  instruction rather than a row — the one case shape in which the instruction is
  itself the input under test (`m-case-format`), classified
  `temporal-keyed-write-multi-row`.

A conforming implementation **MUST** round-trip every canonical instruction
document losslessly (`serialize(deserialize(x)) == x`), the write-side of the
`m-predicate` serde contract. Deserialization judges the document's own grammar;
whether its bounds suit the target is judged when the write is prepared.

A Write Instruction is **buffered author intent** and stays that until flush. It
is never a Planned Write, and a Planned Write is never serialized back into one.

### Serialized write elaboration

A serialized keyed or caller-addressed row, or a predicate-selected assignment, is
structural input, not a planned value. After resolving the exact target Entity and member identity, the
write frontend calls `m-wire.decodeWire(member.neutralType, literal)` exactly
once for each non-null authored leaf. Null is handled by the member's nullability
rule and is never passed to the Neutral Wire Codec. Recursive Value Object
members are traversed by declared structure; opaque Json content is converted as
one `Json` value and is not recursively inferred as neutral leaf types.

Wire failures map to `neutral-literal-type-mismatch`,
`neutral-literal-noncanonical`, or `neutral-literal-out-of-space`, with the
canonical member identity and document path. The previous
`write-value-type-mismatch` rule is retired for resolved scalar leaves. Unknown
members, wrong document carriers, multiplicity violations, missing required
members, nullability, and other structural failures retain their existing rules.

Two producer operations converge on the same private immutable prepared-write
algebra, and they are the one admissibility judgment every ingress crosses. Each
resolves the target first and judges whether it admits the write: a temporal
target refuses `delete`; the window must be stated as the verb's form requires,
admitted by the target's temporal profile, and ordered; a non-temporal target
refuses a milestone verb; and a temporal keyed instruction carries one row. Only
then is the payload judged — a keyed row's subtype shape, members, and values, or
a predicate-selected write's predicate, family refusal, and assignments in
authored order, each assignment's member resolved before its value is judged. `prepareWireWrite` applies the serialized decoding above;
`prepareTypedWrite` applies `m-core.coerceNeutralInput` followed by managed
membership and retains developer-facing mismatch errors. Neither consumer may
choose the other policy from the runtime carrier it happens to receive.
Both producers supply their source access and leaf policy to
`m-document-codec`'s one authored-document traversal. The Typed producer borrows
live Value Object instances and tuples until that traversal; it does not first
render a recursive mapping/list tree. Structural validation consumes the sparse
position-keyed findings from that same pass rather than walking the document
again. A validation-only caller invokes the same traversal without constructing
successful managed output.

A caller-addressed instruction is judged in its own fixed order: its target and
window first, as above; then its revision arguments against the target's
revision kind — stating both is refused first, then a misstated kind, then a
missing one, then a value of the wrong type; and only then its payload, whose
key names the object and whose every other member is judged as an assignment. A
replacement additionally states every writable member: an omitted required one
is refused, an omitted nullable one is written empty, and an omitted `many` the
empty collection. A missing revision is therefore heard before an undeclared
member, and an inadmissible window before both.

`PreparedKeyedWrite` carries the exact target, deeply owned managed rows, and
prepared temporal bounds. `PreparedPredicateWrite` carries its
`ValidatedMutationSelection`, ordered managed assignments, and prepared temporal
bounds. `PreparedTargetWrite` carries the exact target, its one owned managed row,
prepared temporal bounds, whether it replaces, and its validated starting
expectation — an expected version, an expected Transaction-Time start, or the
explicit absence of a revision for an unversioned target. Omission and nullable assignment remain structural states; no prepared
variant retains an authored scalar literal or unresolved instruction field.
Construction is restricted to these operations, with no public constructor or
serialization contract. Buffering, evidence envelopes, coalescing, and planning
retain the immutable product and do not decode or recursively copy it again.

### Write value provenance

A keyed frontend verb is handed a **value**, not an instruction: the instruction's
row is derived from that value. Which verbs accept a given value is decided by the
value's **provenance** — which framework-managed source, if any, produced it from a
read — and never by whether an author has since changed it. Editedness answers a
different question: it decides what a write *contains*, not whether the verb the
author called was the right one.

A **framework-managed source** is one managed value lifecycle: the machinery that
materializes values from reads and attaches to each the state by which it later
recognizes its own. A source is not a connection, an Execution Scope, or a transaction. Any
number of those sharing one lifecycle over one store are **one** source, and a
value any of them read is a value that source produced. Provenance therefore
carries no cross-read guarantee, and none is asked of it: whether a write may
proceed from a row an earlier read returned is settled by whether the writing unit
of work **observed** that row, which the observation requirements decide on their
own and independently of which reader produced the value.

A **Read Origin** is the opaque record a managed source attaches when it publishes
a value from valid Entity State. It records the concrete Entity, Object Key, source
Pin, read participation, and retained observation when one exists. The Read Origin
is provenance and an implementation-private selector for evidence; it is not
itself a Write Observation, a lock, a database gate, or write authority. A source
recognizes a keyed write value as its own through that record, but must still
satisfy the Effective Concurrency Strategy's evidence rule.

Publication of diagnostic data is not source admission. When a classified result
root suppresses its Read Origins under `m-snapshot-read`, a hydratable node exposed
inside that result is treated as **NotStored** by keyed update verbs: no valid
managed read source produced it for writing. This applies to every node in the
classified root's graph, including a node whose page-owned Entity State is also
reached by a separate valid root. The separate root-local node may carry its own
Read Origin; the classified root's node may not borrow it.

Provenance has exactly three answers for a given verb, and they **partition** the
values that verb can be handed: no valid managed read admitted the value as a
keyed source, the source this verb writes through did, or a **different** managed
source did. Each answer is a refusal for one family of verbs, so a refused value
always has exactly one code:

```text
WriteValueRefusal = NotStored | AlreadyStored | ForeignLifecycle
```

- **NotStored** (`write-value-not-stored`) — an `update` / `updateUntil` verb was
  handed a value **no valid** managed read admitted as a keyed source. No source
  provenance establishes a stored row for it to address, so the refusal names the
  `insert` verb as the one that accepts it —
  **unless the value carries the authority of an insertion still standing in the
  writing unit of work** (*Insertion authority*), in which case it is accepted
  and revises what that insertion opened.
- **AlreadyStored** (`write-value-already-stored`) — an `insert` / `insertUntil`
  verb was handed a value produced by a read through **the very source this verb
  writes through**. That value already denotes a row that source stores, so the
  refusal names the `update` verb.
- **ForeignLifecycle** (`write-value-foreign-lifecycle`) — the value was produced
  by a read through some **other** framework-managed source than the one this verb
  writes through. Both families refuse it, including when that other lifecycle
  reads the same store: a value's stored counterpart is only the one the writing
  source itself produced, and no verb may treat another source's value as its own.

The set is **closed**, and the tags are **neutral**: each names a class of value a
verb rejects, never a language's exception type. The one fact an implementation
**MUST** be able to decide about a value it is handed is *which of those three
answers holds* — no valid managed read admitted it, this verb's own source did, or
another managed source did — which any implementation that materializes values
already knows at the moment it publishes them. How that fact is retained —
carried on the value, held in an identity map, held in an implementation-owned
registry — is the implementation's own affair, and no conforming behavior depends
on the choice.

The partition is over **provenance**; whether a given answer *refuses* is the
verb's question, and NotStored is the one answer whose refusal a second fact can
lift. The value an insertion was stated through keeps the NotStored provenance —
no read produced it — but it carries that insertion's authority, and the
insertion opened a row for the update to address. **Read-your-own-writes** is
therefore normative: an implementation that refused such a value would refuse the
developer spelling of *Insert-then-update coalesces in place*, and its refusal
would name the `insert` verb the developer had just called. The exemption is the
**authority the value carries**, never the object it names: a value of an object
this unit of work inserted that carries no standing authority — one built
independently with the same key, or derived before the insertion was admitted —
is refused exactly as any other value no read produced is, and no other unit of
work's insertion lifts anything.

Three consequences are normative:

- A value this verb's own source produced that no author has changed is **not** a
  refusal for an `update` verb. It assigns nothing, so it buffers nothing, issues
  no statement, and raises nothing. Requiring an author to
  test each value before writing it would defeat the change tracking the framework
  performs on the author's behalf.
- Every refusal is decided from provenance **before** the row is derived, so a
  value a verb does not accept reaches no row derivation, no buffer, no plan, no
  SQL, and no database. A refusal is never a translation of a lower-level failure
  raised further down that path.
- The read-your-own-writes exemption is decided the same way, from the authority
  the value carries rather than from a row derived for it. A value that can key
  no row at all carries none, so it reaches the NotStored refusal rather than
  whatever failure deriving its row would have produced.

The `delete`, `terminate`, and `terminateUntil` verbs derive an identity row alone
and take no position on provenance; nor do caller-addressed verbs, which address
their object by key (*Caller-addressed writes*).

### Insertion authority

An **insertion-authoring write** is a write of an object this unit of work
inserted, authorized by that insertion rather than by a read. Successful
admission of an insertion grants an **authority** that belongs to the source the
insertion was stated through — the value a typed insert took and every value
derived from it afterwards, or the node a document insert answered — and is
compared by identity alone: an equal key, physical address, or Transaction
Instant never stands for it. A value derived before the admission, a value built
independently with the same key, and a plain or serialized copy of a source carry
none; a refused admission grants none. The authority is private to its source and
outside its members, so no data conversion can manufacture it. A value a read
produced keeps that read's own evidence whatever this unit of work inserted.

The authority survives flushes and joined scopes, and ends with the attempt:
commit, rollback, and every retry end it, so a source carrying an earlier
attempt's authority licenses nothing. Within an attempt it ends when everything
the insertion opened has been removed (*Rows the attempt opened*), and a later
admitted insertion of the same object grants a fresh authority that no earlier
source shares. Completing a write it licensed spends nothing of it.

Every write the authority licenses on a Bitemporal object starts at the
insertion's own authored Valid-Time start — its **anchor** — however its
coverage has been edited since; a bounded write states only its exclusive end,
which must follow the anchor. The write requires current coverage at the anchor
and never shifts it: a write over an anchor a pending write of the object already
destroyed is a resurrection, refused at the verb, and a stored anchor that no
current row covers when the write executes fails it as a missing target, which
dooms the attempt.

While the insert is pending, the writes it licenses compose over the coverage it
opens (*Same-transaction write coalescing*). Once a flush has executed it, the
same writes transform the stored rows: the object's current coverage from the
anchor is read inside the write batch — under the shared row lock where the
Entity's Effective Concurrency Strategy is Locking — and every row the attempt
opened is revised or removed in place (*Rows the attempt opened*). A versioned
Non-Temporal row advances from the version the attempt's own writes left it at,
which needs no read. Such writes compose with observed writes of the same object
in authored order — over unequal windows on a temporal object, and at one claim
scope on a Non-Temporal one — each keeping its own anchor or source condition;
completion spends the observed sources and not the insertion's authority.

A further insertion of an object is a repeat, refused as **AlreadyStored**,
while anything an admitted insertion of it opened is pending, or is stored and
not removed in full by the writes pending beside it. Once everything those
admissions opened has been removed — or the pending writes remove all of it — a
fresh insertion is admitted. It executes after every write authored before it,
so the removal it depends on precedes it whatever the batching, and a failed
removal or insertion dooms the attempt. Removing only part of the coverage, or
an interior gap, removes nothing in this sense. None of this permits removing
and re-inserting state that existed before the attempt.

### Caller-addressed writes

A **caller-addressed** (target) write is addressed by the object's primary key
and conditioned by the starting revision its caller states — the version, or the
Transaction-Time start of the milestone, an earlier query returned — never by a
read's evidence or by anything the payload carries. A **patch** assigns the
members it names and leaves every other member as stored; a **replacement**
states the object's whole writable state. Neither creates an object: the state
it starts from must exist. Each buffers and answers nothing; an explicit read
reports the saved state. A versioned target requires `ifVersion`, a temporal one
`ifTxStart`, and an unversioned Non-Temporal target takes no revision, so it
cannot detect a change since its caller's query.

A patch that names nothing beside the key is the **empty** write: once it is
validated it is dropped, with no database work, no existence or revision check,
and no effect on earlier pending work. A nonempty patch and every replacement
carry **revision intent**: a versioned row's version advances even when every
value it writes equals the stored one, and a later write composing with it keeps
that intent. A temporal target's milestone is judged as any temporal write's
instead, and one it leaves exactly as it was is kept, under the guard or lock
that proves it (`m-temporal-write` *Unchanged milestones*): the stated start
establishes the write's authority, not a demand for new history.

A temporal target write also states its **window**: none on a
Transaction-Time-Only target, whose current row it writes, and `validFrom` with
an optional exclusive `until` on a Bitemporal one, `validFrom` lying anywhere
inside a stored rectangle. Its stated Transaction-Time start describes the
coverage at `validFrom` alone. It is a range over current coverage like an
observed write's (*deferred range unit*): its flush reads the coverage its
window reaches, a patch assigns to each existing interval and creates nothing,
and a replacement also opens its state over every gap of its window
(`m-temporal-write` *Caller-addressed writes span their requested extent*). Where
that read shows no current row at `validFrom`, or one at another
Transaction-Time start, the write is a failed precondition before any of its
statements executes.

Submission follows the target Entity's Effective Concurrency Strategy:

- **Optimistic** — nothing is read. The stated version becomes the write's gate,
  and a shortfall against it is a **failed precondition**. A temporal write's
  stated start gates its starting row, and only that row's shortfall is the
  failed precondition; a later row's gate binds its own Transaction-Time start,
  and its shortfall is an ordinary conflict.
- **Locking** — after the write is judged compatible with the object's pending
  writes, the participation it needs comes from a pending write of the same
  stated state, else from a live, unspent read of exactly that state this
  attempt holds under its shared lock, else from one **acquisition**: a point
  read of the stored row under the shared lock (`m-read-lock`) that executes no
  pending write and publishes nothing. The stated revision is compared with the
  row that acquisition holds; a row standing at another revision, or no row, is
  a failed precondition refused at the call, leaving the pending writes as they
  were, and more than one row is Cardinality Corruption. The write itself is ungated. An unversioned target takes this path under
  either preference, and a missing row is its ordinary missing target at flush.
  A temporal target's state is the milestone its stated start and its
  `validFrom` name, so a live read hits only where `validFrom` is that
  milestone's own Valid-Time start; a pending write of the object over exactly
  the same window, which admission required to start from the same state,
  always stands in, while one over a disjoint window starts elsewhere and does
  not.

  The acquisition's cardinality is decided before any row it returned is
  judged. Once its read has executed and its rows are assembled, more than one
  row is Cardinality Corruption naming the exact count, raised after the read
  completes and without judging any of those rows' stored data, so an invalid
  row among them is never what the caller observes instead. No row needs no
  judgement either. Only a unique row is judged — invalid stored data in it is
  refused as any read refuses it (`m-read-delivery` *Invalid stored data*) —
  and its stored revision then decides the precondition. A failure executing the
  read or assembling its rows still precedes the count.

A failed precondition is the caller's: re-running the transaction re-states the
same revision, so it is **never retried**, whatever the retry option, and no
diagnostic read distinguishes a deleted row from a revised one. A failure at
flush dooms the attempt like any other execution failure.

An object this attempt **admitted an insertion** of is refused to every
nonempty caller-addressed write, before and after a flush, whatever became of
the insertion, as a write-evidence failure tagged **`write-evidence-inserted`**:
until commit, it is written through its insertion's source or a fresh read. The
attempt keeps that admission for its whole life for this reason alone (*Rows the
attempt opened*). An object the attempt only rewrote is no
insertion, and a later transaction addresses a committed insertion like any
other row.

### Row acquisition

A write that must read existing rows before it can be settled reads them through
one **row acquisition** port this module declares and the unit of work is
constructed with; the execution runtime implements it (`m-execution` *Row
acquisition*). A request describes what to read and performs no read:

| Request | What it reads | When |
|---|---|---|
| **Selection** | the rows a predicate-selected write on a versioned or temporal target will change | when the write is buffered, after pending writes are flushed through the read gate |
| **Target** | the one row a Locking caller-addressed write addresses, at `validFrom` for a Bitemporal target, when no pending write or live read already proves it | when the write is buffered, with no force-flush |
| **Coverage** | an object's current milestones across a deferred range unit's window | when the flush reaches that unit, inside its write batch |

The unit of work hands each request a consumer of its own and receives the
consumer's result. The consumer reads the judged rows, and their aligned raw
documents, while the acquisition still holds them, adopts the row and document
references it keeps into canonical evidence (`m-write-plan`), and retains
nothing of the read itself; acquisition settles its resources however the
consumer ends. Where a write reads nothing, it requests nothing: whether a
predicate write is readless — an unversioned Non-Temporal target — is decided
once, when it is buffered, and a readless write reaches settlement already
marked so, without a second routing decision there.

## Write finalization

### The Write Planner

One **Write Planner** turns a flush's buffered intent into finalized semantic
steps. It is model-scoped, constructed once per accepted Metamodel with its
immutable batching, concurrency, temporal, and provenance strategies already
wired, and it exposes exactly **one** planning operation:

```text
finalize(
    WritePlanningRequest(
        actor_identity:       ActorIdentity,
        transaction_instant:  TransactionInstant,
        concurrency_preference: ConcurrencyPreference,
        buffered_writes:      BufferedWrites,
        ownership:            AttemptOwnership,
    )
) -> WritePlan
```

**Attempt Ownership** is a read-only view of the current temporal rows the
attempt's own successful execution units opened (*Rows the attempt opened*,
below). Planning reads it to decide what a temporal mutation does to its
predecessor; it never changes it.

The returned **Write Plan** is execution-ordered, and its execution units name
the source authority of **every** write admitted against
existing state — a write coalesced into another, superseded, or overwritten by a
later composed assignment included (*Observed-State Coalescing*). A write keeps
its source condition whatever happens to its values, so a unit whose surviving
assignment came from one source still spends every source composed into it,
even when it emits no statement. Work that stated nothing against existing
state — folded into a pending insert, cancelled against one, or an update
assigning no member — contributes no claim. Spending is idempotent, because
consumption records a fact about one source rather than about one statement; a
claim several units name is spent once.

No second planning operation exists to project the plan.

A caller **MUST NOT** be required — or able — to sequence coalescing,
cancellation, no-op elimination, batching, dependency ordering, Transaction
Instant acquisition, temporal expansion, or audit itself. Those
are private stages, and no second public finalized or decorated plan exists
beside the Write Plan.

Resolving *which* observation a write settles against is the caller's, because
only the caller holds the value the write was authored from and therefore the
milestone that value came from. A buffered write against existing state
**carries** the observation resolved for it (below); the planner is handed
evidence, never a store to search. Validating that a required observation is
present remains the planner's, at stage 5.

The planner is **stateless across calls**: it retains neither request nor result.
The operation is **pure** with respect to its inputs — it performs no database
I/O, consults no clock directly, and emits no SQL, dialect object, physical
column, or driver value.

A unit of work is handed its planner when it opens and **retains it for its
life**: every flush of that unit plans through the one planner it was opened
with, and a joining invocation plans through the planner of the unit it
joined rather than resolving one of its own. A re-executed attempt opens a
fresh unit of work and may be handed a different planner — the one belonging
to whatever accepted Metamodel that attempt adopted.

The term **step** is reserved for one logical Planned Write; the term **stage**
describes one private transformation inside the pipeline below.

### The planning pipeline

The Write Planner privately owns this stage order:

```text
1. resolve identities and coalesce buffered intent
2. eliminate known cancellation and no-op work
3. form compatible batches
4. dependency-order private units within barrier regions
5. validate the observation each surviving write carries
6. resolve the Transaction Instant only if surviving work needs it
7. temporal expansion: expand each temporal unit's Coverage Transform over the
   predecessors planning holds (`m-temporal-write`), or finalize a requested
   range whose coverage no planning input holds
8. audit: finalize each produced row, and decorate each update and close
9. freeze the Planned Steps
```

Four of those orderings are load-bearing and therefore normative:

- **Coalescing and no-op elimination precede time.** Stages 1–2 run before stage
  6, so work that cancels or nets to zero never consults the Clock Strategy.
- **Observation validation precedes gate rendering.** A required observation
  that is missing is a planning error raised at stage 5, never a value that
  reaches lowering. The write it belongs to carries it rather than being matched
  to it, so nothing downstream of stage 5 can bind a gate from evidence about a
  different row.
- **Temporal expansion follows ordering.** A surviving temporal mutation stays
  one indivisible unit through stages 3–4 and expands at its already-decided
  position in stage 7 (ADR 0045), so its close and successors are adjacent and no
  unrelated step interleaves.
- **Audit follows topology and precedes realization and lowering.** Stage 8
  reads each produced row's Row Origin and each close's Close Cause and adds
  ordinary planned values; it changes no topology, target, gate, or affected-row
  policy, and emits no SQL. Every row a write produces — a new lineage's
  opening, or a successor carried or changed from its predecessor, a
  Materialized Write Group's rows included — is **finalized once**, before
  settlement chooses whether it is inserted or revises a row the attempt owns,
  and every value finalization adds is an executed assignment of the row
  (`m-write-plan` *Write Rows*). Each Non-Temporal update, keyed or readless, and
  each emitted close is **decorated once**; neither needs a complete row. A
  guard, a removal, a delete, and a milestone kept unchanged store no
  represented value and are not audited. A Materialized Write Group keeps only
  what its audit added, beside its compact evidence, so rebuilding one of its
  steps audits nothing again, and the audit-neutral default answers each input
  itself without resolving the Transaction Instant (ADR 0071, superseding ADR 0037).

Stages are otherwise private. The stage list is an ordering contract, not an
interface: nothing outside the planner may name, observe, or invoke a stage.

Stages 1–4 rewrite the buffered sequence: they merge, drop, split, and reorder
it. Stages 5–9 are **Write Settlement**, and the sequence stops changing shape
there — settlement reads it once, validates the observation each surviving write
carries as it settles that write, and only Planned Writes come out. Settlement
is owned by the planner and constructed for the same accepted Metamodel: it
reuses that model's compiled facets, never observes model publication, and is
never rebound after one. It is reached through exactly **one** private
operation over the **complete** dependency-ordered sequence, because packing is
a property of adjacency and a claim survives by its carrier having reached
settlement at all. That operation answers the Write Planning Result, which the
planner returns unchanged: the planner neither wraps nor reconstructs it, so no
fact about a settled write is decided twice.

### Write Plan and Planned Steps

```text
WritePlan(steps: PlannedSteps, units: ExecutionUnits)

PlannedSteps: an immutable ordered logical sequence of Planned Writes
ExecutionUnits: an ordered partition of those steps, each unit with the
    claims it spends, the Observed States it changes, and the attempt-owned
    rows it removes and opens
```

A **Write Plan** is the immutable, **execution-ordered** result of one planning
call. Its Planned Steps contain every Planned Write that survives coalescing,
cancellation, and known no-op elimination, with temporal topology and correctness
semantics already decided.

- A Write Plan **MUST NOT** retain a Transaction Instant, a raw Write
  Observation, the transaction's Concurrency Preference, an Actor Identity, a strategy
  object, a barrier marker, a private group, or any other planning context.
  Derived values are materialized *into* the steps instead.
- A Write Plan **MAY** retain an immutable value a strategy, a clock, or a facet
  **produced** for one settled write — a resolved instant, a Close Cause, resolved
  Milestone Successors, the target's compiled Inheritance Entity View, the version
  arithmetic the effective Concurrency Strategy answers with — and
  **MUST NOT** retain the producer: no clock, no strategy, no Metamodel, no
  Inheritance Facet, no private group, no planner. What separates the two is
  whether the retained thing can still **consult** something to reach an answer:
  a producer reaches the model, a facet, the clock, or the transaction's
  Concurrency Preference, so it could answer differently than settlement did,
  while a produced value answers from what the step itself supplies and nothing
  else. Carrying an operation is therefore not what makes something a producer —
  advancing an observed version by an already-fixed step is the strategy's
  settled answer restated, not a fresh decision.
- An **empty** Planned Steps sequence is the one canonical result for complete
  cancellation or known no-op elimination. There is no empty-plan sentinel and no
  second result variant.
- A **deferred range unit** is the one exception to fully expanded topology. A
  temporal object's observed writes whose requested Valid-Time range reaches
  current coverage no planning input observed (`m-temporal-write` *Observed writes
  span their requested extent*) finalize to their meaning — the composed
  assignments over that range, the source conditions, and the resolved instant —
  together with the one coverage read that range needs. Such a unit carries no
  planned step, and its meaning is data: it retains no binder, Attempt
  Ownership, clock, strategy, or Actor Identity. When the executor reaches it,
  the unit of work acquires the object's current rows over the range not
  already covered (*Row acquisition*) — inside the write batch and under
  `m-read-lock`'s shared lock when the effective strategy is Locking — and binds
  those rows, or the absence of any, with the observed ones into the unit's
  physical steps before they run.
  Temporal meaning, concurrency, and gates are fixed when planning returns, and
  binding never recaptures the instant or consults the model: only the physical
  enumeration waits, for the rows read and for the Attempt Ownership and
  continuity every earlier unit of the flush published. Binding audits each row
  it produces and each close it emits once, as stage 8 does for a write settled
  at planning, changing no topology or gate. A range whose observed rows already cover it
  settles at planning like any other write. A caller-addressed temporal write is
  such a range whatever it composes with, unless observed rows of its
  composition cover its window; its meaning also carries the caller's starting
  condition, which binding judges against the rows read before any step exists,
  and a replacement's extent, whose uncovered parts binding opens. A composition
  an ordering barrier kept after earlier writes of its object reads its whole
  window when its turn comes and binds to those rows alone: each observed
  condition holds where its rectangle still stands or an earlier unit of the
  flush proved it, each caller's start where it stands at the stated start or at
  a row derived from a proven original that held it at that start (*Execution
  units complete before later work runs*); any other caller's start is a failed
  precondition, and any other observed condition fails as that write's own
  shortfall would, the caller's first.
- Planned Steps is a **logical** sequence. An implementation MAY pack homogeneous
  runs and expose stable immutable views during iteration rather than allocating
  one container per step; every exposed view is immutable and stable, and equal
  views need not have object identity.
- Each settled write — one keyed write with its expanded temporal topology, one
  batch, one readless predicate write, or one Materialized Write Group — is one
  **execution unit**. A unit's completion facts are produced values like its
  steps, and a group's MAY be read on demand from the group's compact evidence.
- A packed run of a Materialized Write Group's rows MAY be held **compactly** —
  the group's own aligned evidence beside the facts settlement decided for the
  whole group — and its step access reads those two and nothing else. It
  **MUST NOT** consult a clock, a strategy, a Metamodel, an Inheritance Facet, or
  a Temporal Facet there, and **MUST NOT** re-resolve a Milestone Successor or
  re-derive the applicable member set: every one of those was answered while the
  plan was being made. Reading one settled row's cells through an index a facet
  compiled when the model was accepted is not a re-derivation.

### Execution units complete before later work runs

The executor runs a Write Plan's steps in order and reports each execution unit
as soon as every step of that unit has executed and its effect has been
enforced, before any step of a later unit runs. The unit of work then completes
the unit synchronously:

```text
spend the source authority of every write the unit composed
invalidate evidence of every Observed State the unit changed
retire the attempt-owned rows the unit removed
register the rows the unit opened
```

A deferred range unit's changed states, removals, and openings are those its
binding produced. A milestone a unit kept unchanged (`m-temporal-write`
*Unchanged milestones*) is
no changed state, even where a guard executed for it, and derives nothing a
later unit relies on: it still stands. A source that carries no observation — an unversioned
Non-Temporal read's — has no state for a unit to name; its authority is spent
on the source itself once the flush that held its write succeeds, and every
value derived from that source shares it. Removals are retired before openings
are registered, so a row removed and reopened at one physical address remains
owned, and an insertion whose last tagged row the unit removed still stands when
a row the unit opened is tagged with it. Nothing is published for a
unit whose steps did not all succeed; such a failure dooms the attempt
(*Abort*). Completion therefore happens per unit, not at the end of the flush:
a later unit, and any read the flush serves, observes the earlier units'
published effects.

A unit that a later unit of the same flush follows across an ordering barrier
(*Observed-State Coalescing*) also records, for each original it transformed,
the current rows it derived from that original. Its guarded effect, or the
shared lock it held, has then **proven** the original: a condition the later
unit was admitted with on that original holds for it, provided every row
derived from the original inside the later unit's window still stands as it
was opened — at its owned address, at the attempt's Transaction Instant, from
the Valid-Time start it was opened with — and rows a later unit derives from
such a row descend from the same original. Spending and invalidation apply to
the earlier unit's sources as usual: a proof serves only the writes admitted
before the flush began, never a later submission, and it ends with the flush,
however the flush ends.

## Planned Writes and Write Observations

`m-write-plan` owns the Planned Write algebra — Row Origin and Close Cause,
planned rows and assignments, the Write Target, the Write Gate and its
concurrency decision, and the Affected Rows Policy — and the Write Observation
vocabulary: the Object Key and Observed State Key that address evidence, and
the Predecessor Row a Temporal Observation retains. This module settles
buffered writes into that algebra, carries each observation to the write it
settles, and owns how long that evidence stays eligible.

### Observation ownership and lifetime

A retained observation belongs to the **source values that observed it**, not to
the transaction that ran the read. A read outside any transaction still produces
values a later effective-Optimistic write may settle against, so an
implementation **MUST** make the evidence reachable from the source value and
**MUST NOT** make eligibility depend on a transaction-scoped store. A
transaction retains only a **weak index** of the states its own reads have seen,
plus the **participation** those reads license.

Three rules follow, and an implementation **MUST** exhibit all three:

- **Eligibility is liveness.** An observation stays eligible while at least one
  live source value or one buffered write reaches it, and becomes unavailable
  when none does. Liveness means strong reachability; a language runtime MAY
  discover unreachable values on its own collection schedule rather than at a
  source-code boundary.
- **States coexist.** Several observed states of one object are distinct
  retained observations reached from distinct values, so rereading a row never
  upgrades or overwrites the evidence an older live value carries. Two reads that
  resolve to **one** observed state within a transaction share **one** retained
  observation, exactly as two graph positions reaching one node do.
- **A successful execution unit consumes.** Every observation an admitted
  write used is spent when the execution unit it composed into completes —
  whether or not its own values survived, and whether or not the unit emitted a
  statement — and a value still tied to a spent observation cannot drive
  another write; the caller must read again. An update assigning no member
  consumes nothing, and a failed flush dooms the attempt, so nothing needs
  restoring. A source with no observation is spent the same way, on the
  source's own provenance shared by every value derived from it, once the flush
  holding its write succeeds; spending it consumes neither the transaction's
  participation nor any other source.
- **An own change invalidates.** When an execution unit successfully revises,
  closes, or removes an observed state, every observation of that state the
  attempt's reads produced becomes ineligible for further writes, even one no
  write used and even when the changed row keeps its address and revision
  token. The rule is judged against the state the rows had **when the read
  acquired them**: evidence built later from an earlier read's rows is
  ineligible too. A read after the change observes fresh, eligible evidence.
  Invalidation is per Observed State — an unaffected rectangle of the same
  object stays eligible — and is distinct from consumption. It moves one way and
  survives the attempt, exactly as consumption does.

Absence is **structural**:

- inserts have no observation;
- unversioned Non-Temporal writes have no observation;
- versioned Non-Temporal updates and deletes require a Version Observation; and
- every temporal close requires a Temporal Observation.

A required observation that is missing is a **planning error**. An implementation
**MUST NOT** define a `NoObservation` value, a nullable observation that flows
downstream, or a mode in which an observation-requiring write proceeds unobserved
— the requirement holds under **both** Effective Concurrency Strategies (`m-opt-lock`).

Structural absence extends to the buffer. A buffered write that has an
observation is buffered **paired** with it — one keyed instruction and the one
observation resolved for it, the keyed counterpart of a Materialized Write
Group's own aligned evidence (below) — and a write with none carries no
observation field for anything to be absent from. Absence is therefore the
absence of the pairing rather than a field carrying it, which is what lets
planning read a write's address, gate, and carried state off one object. What an
unobserved write MAY still travel with is what *Observed-State Coalescing* below
gives it: the claim scope it takes, and the source authority it spends. Neither
is an observation, and neither survives the stage that reads it.

### Comparing an assigned member with its persisted value

A **keyed** write's assignments are **literal**. The members its author
expressed — a Typed edit's cumulative touched members, a Wire change document's
keys — are assigned whatever the source published for them, so an assignment
equal to the stored value is still written: it advances a version, and for a
temporal entity it is applied like any other assignment. A keyed temporal
write's changed successor overlays every member the write assigns and carries
every other member's persisted state. Only an update expressing **no** member is
empty; it buffers nothing and claims nothing.

A temporal milestone such a write leaves exactly as it was is kept rather than
closed and chained wherever that is proven (`m-temporal-write` *Unchanged
milestones*).

A predicate-selected write compares instead. The write-input comparison of a
Materialized Write Group below, and the no-op elimination it performs before
planning, use `m-document-codec`'s one effective-change classification, over the
members the write explicitly assigns and, under those same names, the values the
resolving read observed, and it answers identically under either Storage
Layout. What this module states is which members it hands that operation and
what it does with the answer; the rule it applies — scalar, whole occurrence,
and undeclared key alike — is the codec's and is not restated here.

A resolved row every assigned member of which the classification answers as
**restored** is **eliminated**: it issues no DML, advances no version, consults
no clock, and for a temporal entity performs no close and chains no row. That
holds however the codec reached the answer.

Elimination decides the whole row and nothing smaller. A Materialized Write
Group row that survives because one of its assigned members is effective
executes **every** assignment, exactly as a keyed write does: a member the
classification answers as restored is still written, so an assigned occurrence
equal to its stored value replaces the stored subtree whole, keys no member
declares included (`m-write-plan` *Write Rows*).

Elimination is deliberately the conservative direction wherever that answer makes
equal two documents a store spells differently: eliminating the row leaves the
stored spelling standing where writing it would have replaced the assigned
subtree whole. A row the codec finds nothing changed in is not the place to
destroy stored state no assignment can name.

## Buffered, batched, ordered writes

At the unit-of-work boundary the buffered writes are flushed as **set-based** SQL
wherever possible:

- Multiple inserts or same-column updates of one entity become **one** Planned
  Write with several rows or keys, lowered as a single multi-row `INSERT` or a
  batched `UPDATE`. The canonical golden forms and their proof are
  `m-batch-write`.
- Operations are **ordered** so that a parent row is inserted before a child
  that references it (and deleted after), honoring foreign-key constraints.

Ordering is otherwise **unconstrained**, with one exception: a **readless
predicate write** (`m-batch-write`) is a hard **ordering barrier**. It keeps its
authored position and partitions the buffer into independently reorderable
**regions**; batching and foreign-key ordering apply within a region alone, and
no write crosses the barrier in either direction. A readless predicate does not
reveal which rows it matches, so moving a write across it could change what it
writes (ADR 0043). The barrier is **private planning structure only** — it
produces no group, wrapper, flag, or identifier in the Write Plan, just a
position nothing passes. No two writes combine across it, whatever they have in
common, so every effect executes on the side of the barrier it was buffered on:

- A temporal object's writes on each side of a barrier compose apart, each
  region's into its own execution unit, though admission judges every one of
  them together (*Observed-State Coalescing*); the later unit binds to what the
  earlier left (*deferred range unit*).
- Two Non-Temporal writes of one claim scope on two sides of a barrier stay two
  writes. Admission still judges the later against the earlier, and an
  assignment after a destruction is refused as it is within a region, while a
  repeated destruction still adds nothing. Otherwise the later write executes
  after the barrier against the state the earlier one leaves: a versioned row
  is gated on, and advances from, the version the earlier write produced.
- A write of an object whose insert was buffered before a barrier does not fold
  into that insert (*Same-transaction write coalescing*): the insert executes
  before the barrier, and the write revises or removes the row it opened after
  it, as a write through the insertion's source does once that insert has
  flushed (*Insertion authority*).

## Same-transaction write coalescing

Buffered writes of the **same object within one unit of work** combine before flush —
they annihilate or merge rather than each producing durable SQL, because a state a
transaction never durably exposed to any other reader is never separately recorded.
This follows Reladomo's transaction write queue (`TxOperations` /
`GenericBiTemporalDirector` same-transaction handling): a same-transaction
insert-then-update writes the final value in place, and a delete cancels a matching
pending insert.

- **Insert-then-update coalesces in place.** A row inserted and then updated in the
  same unit of work flushes as a **single** write carrying the **final** value; no
  intermediate milestone is fabricated. A **non-temporal** insert-then-update emits
  one `INSERT` with the post-update values (never `INSERT` + `UPDATE`); an
  **Transaction-Time-Only** insert-then-update opens a single current milestone with the final
  value — no close-and-chain, in contrast to the cross-transaction chaining of
  `m-temporal-write`; a **bitemporal** insert-then-update covering the whole
  opening opens a single fully-current rectangle with the final value — no
  inactivation / head-tail split, in contrast to its cross-transaction rectangle
  split.
- **A pending Bitemporal opening takes each edit over its own coverage.** An edit
  of a still-pending opening is a temporal edit, composed with the opening as
  observed writes compose over stored coverage (*Observed-State Coalescing*): an
  edit bounded inside the opening splits it at its bound, one bounded at or beyond
  the opening's end changes all of it, and nothing extends the opening past its
  own window. Every edit starts at the insertion's anchor (*Insertion authority*).
  The flush opens only the pieces that survive, each at the one Transaction
  Instant, carrying the opening's values with the edits' assignments overlaid.
- **Insert-then-delete cancels.** A row inserted and then deleted in the same unit of
  work **cancels**: the two buffered writes annihilate and the flush emits **no** DML
  for that object — the net-zero effective-change-set elision, extended across two
  verbs. A bounded termination of part of a Bitemporal opening removes only its
  own window; the pair does not cancel, and the flush opens what survives.

These combinations hold within one barrier region; a write buffered after a
readless predicate write never combines with a pending insert buffered before
it (*Buffered, batched, ordered writes*).

Coalescing is a property of **one** unit of work; across two committed transactions
the milestone modules chain and split as usual. The rule is centralized here because
it is a buffering decision, not a per-verb one — `m-temporal-write` describes the
durable cross-transaction shapes and defers the same-transaction combination to
this scope.

### Observed-State Coalescing

The rules above combine writes of one **object** whose first write OPENED it. The
rule below combines writes against an object that already existed, at the **claim
scope** each of them takes.

Claim scope is a **total derivation over the write kind**, from two declared
facts: the target Entity's Optimistic Key (`m-opt-lock`) and the write's own
mutation. It answers for a write addressing **one** object, which is every write
a keyed verb authors. It has exactly three arms, and an implementation **MUST
NOT** reach one of them because something was absent — an insert observes no
state either, so a default taken on a missing observation would sweep it in:

- an **insert** claims nothing: it opens a row rather than writing against one, so
  there is no prior row for a second intent to conflict over;
- a **versioned or temporal** existing-row write is claimed at its **Observed
  State Key**, because what such writes share is the evidence they settle against
  and two writes of one key that observed two different states are two independent
  intents; and
- an **unversioned Non-Temporal** existing-row write is claimed at its **Object
  Key**, because the shared row lock its evidence rule demands is held on the
  object and covers every state the row can be in. Two such writes can never have
  observed two different states, so the state-keyed arm's own reason does not
  apply and the object is the correct grain.

A claim addresses one object, so a keyed instruction naming **several** rows
reaches no arm's scope: it has no single Object Key and no single observed state,
and an implementation **MUST NOT** claim it at either grain. Only a caller
holding a pre-formed multi-row instruction can author one; a keyed verb writes
the one row the value it was handed names. Where that caller supplies no evidence
of its own, the derivation answers none and the write is buffered **bare** —
neither coalesced with another write nor refused for a claim — and a target
entitled to evidence still fails the required-observation rule when the write is
settled. Evidence such a caller **does** supply travels with the write it was
supplied for, and one observation is evidence about **one** row, so an
implementation **MUST** refuse the pairing rather than drop the evidence.

That refusal is a judgment about the write's own carrier, and both it and the
refusal of an arriving intent the buffer's existing claim cannot absorb are made
**before** the write is buffered, each leaving the claim ledger and the buffer as
it found them. An implementation **MUST NOT** record a write's claim before the
write has passed the carrier judgments that precede buffering: a caller that
catches such a refusal and continues in the same unit of work would otherwise
hold a claim for a write nothing buffered, and a later legal write of that scope
would be refused, deduplicated, coalesced, or superseded against it. A refusal a
buffered write earns later — when the buffer is planned or the write is settled —
needs no such guarantee, because a failed flush aborts the unit of work.

Each buffered write against existing state carries a **Write Intent** — what it
does (an **assignment** that writes member values against a surviving row, or a
**destruction** that removes the row or closes the milestone) over which **temporal
region** (the authored Valid-Time bounds, absent on both ends for a non-temporal or
Transaction-Time-Only write). One closed rule decides what an arriving intent
becomes against the intent a buffer already holds at that exact scope, and both the
arriving verb and the flush read it, so a synchronous refusal can never disagree
with what the flush would have done:

| Held | Arriving | Outcome |
| -- | -- | -- |
| nothing | any | the arriving intent is admitted |
| assignment | assignment, same region | **coalesce** — the sparse assignments merge in authored order, the later value winning a repeated member, into one surviving write |
| assignment | destruction, same region | **supersede** — the destruction replaces the assignments buffered before it, so an update then a delete at one scope is one delete |
| destruction | destruction, same region | **deduplicate** — the second says what the first said and adds nothing |
| destruction | assignment | **incompatible** — no write means to resurrect a row that is going away |
| any | any, different region | **incompatible** for a non-temporal write; a temporal object's observed writes compose instead (below) |
| a Materialized Write Group's selection | any | **incompatible** — the group is one compact indivisible unit, so a keyed intent has nothing to join |

Merged assignments are literal: the merge keeps the caller's last word on each
member, and a member set back to the value its source observed is still
assigned. A superseded or coalesced write's source condition is kept by the
survivor, which claims the same scope.

**A caller-addressed write claims the state its revision names** — the object at
its stated version, or the object itself when it is unversioned — so it composes
with observed writes of that same state by the table above: a patch and an
observed assignment merge member by member, a replacement replaces what came
before it and is overlaid by what follows, and a destruction supersedes both
while keeping the caller's condition, which a destruction's own gate then binds.
One object's writes start from one state: a caller-addressed write is refused
where any other write of the object pending — another stated revision, or an
observation of another state — stands at another scope, and so is an observed
write of another state while a caller-addressed write of the object is pending.
The survivor of a composition keeps the caller's condition, its revision intent,
and every observation the composed writes were admitted through, which its
completion spends; a shortfall against its gate is the caller's failed
precondition, ahead of any observed write's own classification.

A caller-addressed write of a **temporal** object joins that object's
composition (next paragraph), judged against every write of the object still
pending — overwritten ones, and those in other barrier regions, included — and
not only the latest. Against each one, at least one of the two caller-addressed:

- over **exactly the same window**, the two are one operation and start from
  one state: the caller's stated Transaction-Time start and the observed
  rectangle's agree, and no assignment follows a destruction;
- over **disjoint windows** — half-open, so adjacent windows are disjoint — the
  two are **separate operations**, each keeping its own condition, scope, and
  revision intent, even where both starts lie inside one stored rectangle;
  they are refused only where an observed rectangle holds the caller's start at
  another Transaction-Time start, a condition no current coverage can meet;
- over any **other overlapping** window, they are refused. An unbounded window
  overlaps every window after its start, whatever rectangle holds either start.

A Non-Temporal write has no window, and every Transaction-Time-Only write of
an object states the same one, so neither admits a separate operation. The
composition's transform records a replacement's window
as its **extent**: an assignment composed after it overlays its values and
keeps the extent, so the gaps it fills take the overlaid state, and a
destruction ends it, opening no gap only to destroy it. The condition every
caller stated stays its operation's starting condition through every overwrite
and destruction, and a replacement's extent never reaches another operation's
window.

**A temporal object's observed writes compose by object.** Writes of one temporal
object through observed sources — whichever states they observed and whatever
Valid-Time windows they request — form one pending composition at the position
of the first in their barrier region, judged against every write of the object
still pending:

- an **assignment** composes in authored order: where requested windows
  overlap, the later assignment's value wins member by member, and outside the
  overlap each keeps its own; an assignment after a destruction at the same
  scope or over an overlapping window is **incompatible**;
- a **destruction** composes only with writes it neither overlaps nor shares a
  scope with, or with writes of exactly its own window, which it supersedes or
  repeats; any other pairing is **incompatible**.

Composition keeps every admitted write's source condition and requested window,
whether or not any of its values survive, and finalizes the surviving
assignments into one ordered set of disjoint Valid-Time segments, each stating
the members assigned over it. That composition is the write's whole meaning:
binding it to coverage substitutes each current row's own unassigned values and
never revives a value a later write overwrote. Two writes of one observed state
over one window are an ordinary pair of the table above. Stale and current
observations of one object compose without a refusal of their own; their
conditions are validated when the composition executes (`m-opt-lock`).

An incompatible intent is refused **synchronously at the verb**, before buffering
and before any database access, and the refusal is a write-evidence failure naming
the object it addressed, tagged **`write-evidence-already-claimed`**: what the
write would settle against is already claimed by pending work it cannot join. The
remedy is the ordinary one: a participating read force-flushes the buffered intent
and returns fresh state, which nothing claims.

A **Materialized Write Group** claims every state its predicate resolution
selected. A later keyed write of one of those states is refused rather than merged
in, because merging would mean indexing and mutating the compact group. In the
reverse order there is nothing to refuse: the group's resolving read force-flushes
the buffer first, so it selects state no pending intent still holds.

A coalescing witness encodes **both** buffered mutations explicitly by authoring
the write step as an ordered **buffer-and-flush** scenario. `/scenario/<n>/write`
carries a **general ordered buffer of one-or-more keyed write instructions** — the
writes a single unit of work accumulates and flushes together — and the step's
golden SQL is the independent expected lowering of that flush. **Same-object folding
at flush is the coalescing rule**, a runtime/planner property rather than a
structural one: when two buffered instructions name the **same** entity and
primary-key identity the flush combines them (insert-then-update writes the final
value in place; insert-then-delete cancels to no DML — one final-value write, or no
DML at all). The two-keyed same-object insert-then-update / insert-then-delete pair
is that rule's **single-object special case**; the same buffer equally expresses a
single keyed write and a mixed multi-object flush (an `insert` / `update` / `delete`
of **different** objects, ordered by foreign-key dependency). Predicate-selected
buffered instructions remain **deferred** — the buffer is keyed-only. The buffered
form and its authoring surface are the case format's (`m-case-format`); the
instructions themselves are the canonical `write-instruction.schema.json` shapes, so
an adapter exercises coalescing from the requested operations, never from the golden
SQL.

### Materialized Write Groups

A predicate-selected write whose target requires per-row observation
(`m-opt-lock`, ADR 0014 — a versioned or temporal target with no single-statement
template) cannot be planned from buffered data alone. Its resolving read happens
**before** the pure planning call, in Unit Work's write-input preparation, which:

1. force-flushes preceding writes when the read needs read-your-own-writes;
2. performs the resolving read through its row acquisition port (*Row
   acquisition*);
3. acquires the selected physical row locks when the Entity's Effective
   Concurrency Strategy is Locking (`m-read-lock`);
4. compares assigned members with their persisted values, using this module's
   structural equality rules, for an assignment-bearing mutation;
5. records the effective rows in database resolution order; and
6. produces **no item at all** when the result is empty or entirely no-op.

Delete and terminate have no assignments to compare and therefore retain every
resolved row. This streaming comparison is the one narrow result-dependent
normalization performed before planning; it exists so comparison-only state is
never carried into the planner merely to be discarded. Every no-op decision
derivable from buffered data alone remains the planner's.

One authored predicate becomes exactly one **Materialized Write Group**: the
authored mutation and, for each selected row in database resolution order, that
row's key value with either its observed version or its complete Predecessor Row
state and optional raw document. The entries are aligned and number at least
one. How the group holds them — aligned columns, the resolving read's own row
state, or another compact form — is the implementation's, and none of it appears
in a Write Plan.

- The group is **private**. It is an input to planning, never a member of a Write
  Plan, and it disappears during finalization.
- It stays **indivisible** through batching and dependency ordering: the planner
  moves it as one unit and never folds its rows into an unrelated buffered
  instruction, never regroups them by statement kind, and never reorders them
  internally. Each row's close-and-successor sequence stays adjacent.
- Because the read observed only existing rows — and read-your-own-writes has
  already flushed past any pending same-key insert — no same-object coalescing
  candidate can structurally arise against it.
- It contains no managed Entity object, no composite-key object per selected row,
  no eager Predecessor Row object per selected row, no generic per-row planning
  wrapper, and no observation-free variant. An empty resolution produces no
  group.
- A zero-row shortfall encountered while flushing the group aborts the **whole**
  unit of work (`m-opt-lock`); a later row is never silently continued past it.

## The Transaction Instant

Each outermost unit-of-work attempt owns exactly one **lazy** Transaction
Instant. Constructing it does **not** consult the Clock Strategy; the first
surviving write that needs a Transaction-Time boundary or an Audit Provenance
timestamp captures, normalizes, and memoizes it (ADR 0010).

The observable contract:

- An **empty** flush, a **canceled** buffer, a buffer that **coalesces away**,
  and a nonempty flush whose surviving work requires **no timestamp** all
  consult the Clock Strategy **zero** times. This is why pipeline stages 1–2
  precede stage 6.
- Every timestamp-requiring write in **one attempt** shares **one** instant,
  including across a forced read-your-own-writes flush and the commit flush, so
  temporal boundaries and audit values in that attempt are coherent.
- A **retry** is a new attempt with its own uncaptured lazy instant. It captures
  a **fresh** value only if it independently reaches timestamp-requiring work,
  and it never reuses the previous attempt's value.

The Transaction Instant is planning and flush context. It **MUST NOT** become a
durable Write Instruction field, and it **MUST NOT** survive in a Write Plan:
every step that needed it already carries the resulting concrete value.

### Rows the attempt opened

Because every flush of one attempt stamps one instant, a later write in the same
attempt can address a current temporal row an earlier flush of that attempt
opened. Such a row has no history to preserve, and closing it would leave an
empty `[T, T)` interval whose physical address collides with the row the
earlier flush closed. The attempt therefore records, by complete physical
address, every current row its successful execution units open — keyed inserts,
temporal successors, and the successors of Materialized Write Groups alike —
and retires a row from that record when a unit removes it. Reads record nothing.
A row whose key the database allocates has no address until its insert
executes, so that insert answers the key as row-producing DML (`m-db-port`) and
the unit records the row under it. The answer is validated before it is used:
one row per row opened, each holding the key alone, an integer, none twice.
Anything else is a **Write Result Error**, an invariant failure that is never
retriable and, like any failure while executing, dooms the attempt.
Every admitted insertion stays recorded until the attempt ends, even once
everything it opened was removed or a pending removal cancelled it, because a
caller-addressed write of the object is refused on that admission alone
(*Caller-addressed writes*).
The record survives flushes and joined scopes, ends at commit or rollback, and
starts empty on retry. The row an admitted insertion's own insert opens is
tagged with that insertion in the record, and so is every successor of a row
tagged with it; a successor of a row that existed before the attempt, or of any other
untagged row, is untagged, so rewriting other coverage of the object beside an
insertion adds nothing to what the insertion opened. The insertion's coverage is
completely removed once no row tagged with it remains (*Insertion authority*).
Address and instant carry no tag: a reinsertion's row opened where a removed row
stood is tagged with the reinsertion, never with the insertion that row was
tagged with.

Temporal expansion disposes of each predecessor by this record: a row that
existed before the attempt is closed, and one the attempt opened is revised in
place or removed (`m-temporal-write` *Ownership disposal*). Ownership is the
attempt's record alone. A Transaction-Time start equal to the attempt's instant
**MUST NOT** be read as ownership — clocks may repeat an instant across attempts.

## Actor Identity

An **Actor Identity** is the closed identity projection of the Execution Actor
captured by the invoking Execution Scope (`m-execution-authority`): either the
stable, nonempty, opaque application Subject Identity or the actual nonempty
Database Login Identity. It is a **required** planning input and the first field
of the planning request. Its value type is owned by this module, exactly as the
Write Observation vocabulary is, so a planning request is well-typed before any
provenance behavior exists.

An **audit-neutral** plan makes no use of it. Until provenance decoration is
implemented, an implementation **MUST NOT** inspect, validate, retain, serialize,
persist, lower, or bind the supplied Actor Identity, and two planning calls
differing only in Actor Identity **MUST** produce equal Write Plans and
identical emitted SQL and binds. Reserving the field now is what lets provenance
decoration later become an internal stage rather than an interface change.

Scope-time capture, propagation across joined scopes and retries, and verbatim
comparison belong to Execution Authority, not to this module.

## Affected-row enforcement

The unit of work owns the **authoritative** interpretation of every non-insert
execution result:

```text
enforce_affected_rows(step: PlannedWrite, actual_count: NonNegativeInt)
```

The executor reports the driver's affected-row count and asks this module what it
means. SQL lowering and database adapters **report** counts; they **MUST NOT**
reconstruct or reinterpret the semantics (ADR 0048). Inserts carry no policy, so
enforcement accepts them and returns.

Enforcement raises the closed, module-owned **Write Effect Error** family:

```text
MissingTargetError | StaleWriteError
OptimisticLockConflictError | CardinalityCorruptionError
```

Each error carries the same semantic payload — the Entity Identity, the Write
Target (retained by reference), the expected count, and the actual count — and
**nothing else**: no SQL, statement index, driver exception, whole Planned Write,
assignments, or observation. That keeps the diagnostic stable across dialects and
lets `m-auto-retry` recognize the canonical Optimistic Lock Conflict Error
without depending on an optional concurrency module.

A `FailedPrecondition` shortfall raises the **Write Precondition Error**
instead, carrying the Entity Identity, the object's key, and the revision the
caller stated — no count, because what failed is the caller's condition rather
than an effect (*Caller-addressed writes*). It is the same error a Locking
submission raises when its acquisition finds the condition already false.

Retriability follows the classification, not the raising site: an Optimistic Lock
Conflict Error is retriable only under the unit of work's opt-in
(`m-auto-retry`), while a Missing Target Error, a Stale Write Error, a
Cardinality Corruption Error, and a Write Precondition Error are **never**
retriable.

### When several steps share a driver batch

Multiple `ExactCount` steps MAY share one driver batch **only** when the adapter
returns one affected-row count aligned with each logical step; the unit of work
then enforces each count against its own step. One **aggregate** count is
sufficient only for a single Planned Write whose own Key Target holds several
keys, because that one target owns the aggregate expectation. An aggregate-only
backend **MUST** execute distinct `ExactCount` steps separately; it MAY still
reuse statement preparation and stream bind rows. This is what preserves exact
attribution of a shortfall to the step that caused it.

## Strategy selection — one preference, an effective strategy per Entity

An outer unit of work resolves one **Concurrency Preference**, `locking` or
`optimistic`, from its boundary options; an omitted preference, and a joining
boundary's, resolve as `m-execution` *Option resolution* states.
The preference is not itself the correctness mechanism: the Unit Work combines it
with the target Entity's Optimistic Lock Facet to derive an **Effective
Concurrency Strategy** for each participating Entity:

| Concurrency Preference | Optimistic Key | Effective Concurrency Strategy |
|---|---|---|
| `locking` | any | **Locking** — participating object reads take the `m-read-lock` shared lock; observation-requiring writes are `Ungated` |
| `optimistic` | `ExplicitVersion` | **Optimistic** — reads omit the shared lock; writes gate on the observed version |
| `optimistic` | `TransactionTimeDerived` | **Optimistic** — reads omit the shared lock; temporal closes gate on observed `txStart` |
| `optimistic` | `Unversioned` | **Locking** — participating object reads take the shared lock; writes are ungated |

Thus `optimistic` means **use optimistic concurrency wherever the model supplies
a gate, with a locking fallback where it does not**. It never means that a
heterogeneous transaction is universally lock-free. An explicit `locking`
preference remains the workflow-level override for making every lockable Entity
participate pessimistically. The same versioned or temporal Entity can therefore
use its optimistic key in one workflow and a shared lock in another.

An object read resolves the strategy of the Entity it materializes. Separate
deep-fetch levels resolve independently, so one transaction may read a versioned
root optimistically and an unversioned included Entity under a shared lock. The
Effective Concurrency Strategy also determines write evidence: Locking requires
current-transaction read participation proving that the lock is held, while
Optimistic may use authentic retained version or milestone evidence and lets the
database gate detect an intervening write (`m-opt-lock`).

Reladomo is prior art for mixed participation, but exposes the choice per
transaction and object portal/class. Parallax deliberately keeps one ergonomic
Unit Work preference and derives the safe per-Entity result instead of exposing
per-Entity overrides.

The Write Planner consumes the Concurrency Preference and the model's Optimistic
Lock Facet, settles each Planned Write's gate or explicit `Ungated` decision, and
retains neither the preference nor the Effective Concurrency Strategy in the
Write Plan.

Write admission resolves the same strategy through the connected model's
injected write-evidence policy (`m-opt-lock` "The Optimistic Lock Facet"), which
also names what each keyed write settles against. The unit of work applies that
answer to its own state — the participation its reads stamp, the observations a
flush has consumed, and the claims its buffer holds — and buffering is the one
operation that admits a write's claim and buffers the write, all or nothing.

### The Isolation Level beside it — what the transaction READS

A unit of work resolves a second, independent boundary option: the **Isolation
Level** (`m-db-port`), which the port carries and each adapter maps. The two are
not alternatives and neither substitutes for the other. The Concurrency
Preference decides what a participating read LOCKS and what a write GATES on —
mechanisms this module owns, applied per Entity. The level decides what a read
SEES, uniformly for the whole boundary, and is graded by the anomalies it
forbids:

| Level | Forbidden | Still permitted |
|---|---|---|
| Read Committed | dirty reads | nonrepeatable reads, phantoms, serialization anomalies |
| Repeatable Read | dirty reads, nonrepeatable reads | phantoms, serialization anomalies such as write skew |
| Serializable | all of the above | a retryable failure rather than eventual success |

**Permitted is not required.** A stronger engine forbids more than the level
promises, and neither a caller nor a compatibility case may require an anomaly to
occur merely because the level allows it. Serializable protects the committed
outcome only among transactions that ALL request it, and promises neither
identical blocking behavior across engines nor eventual success.

The forbidden anomalies are forbidden for every read form the boundary runs —
a plain object find, a deep fetch's own included levels, and a streamed
delivery's pages — because the guarantee belongs to the transaction rather than
to a statement. A read taking the shared lock is no exception: the lock and the
level compose, so a Locking read inside a Repeatable Read boundary both holds its
lock and reads at the level.

An omitted level, and a joining boundary's, resolve as `m-execution` *Option
resolution* states: the boundary requests a concrete level on every attempt
rather than falling back to the adapter's own default (`m-db-port` *Mapping
obligations*), and a join never renegotiates the level its boundary opened at,
because an isolation is a property of a boundary only at the moment it opens.

## What the suite pins down

`m-unit-work`'s observable rules are expressed as **scenario** cases — ordered
operation steps, each with a declared round-trip count — and plain write cases:

| Case | What it proves |
|---|---|
| read-your-own-writes scenario | a buffered write is flushed before a dependent find observes it |
| rollback scenario | an aborted write is discarded; a post-abort find observes the original rows |
| fk-ordering / flush cases | buffered writes flush ordered by foreign-key dependency |
| insert-then-update coalescing (`m-unit-work-008`, `m-temporal-write-008`, `m-temporal-write-030`) | a same-transaction insert-then-update flushes as one write with the final value — no intermediate milestone (non-temporal / Transaction-Time-Only / Bitemporal) |
| insert-then-delete cancellation (`m-unit-work-010`) | a same-transaction insert-then-delete cancels — the flush emits no DML for that object |
| dirty-read refusal (`m-unit-work-031`) | at Read Committed, a reading unit of work observes the committed row while a concurrent one holds an uncommitted write to it |
| nonrepeatable-read refusal (`m-unit-work-032`, `-033`, `-034`) | at Repeatable Read, a unit of work's second read answers what its first did across a peer's committed write — for a plain find, a deep fetch's own included level, and a streamed delivery's pages |

Each isolation scenario declares `when.uow.isolation` and holds TWO units of work
open at once, labelled `reader` and `writer`, so that what the reading one
observes is graded WHILE the writing one is live. Each closes with an ungrouped
find stating only what both engines have committed: what the level permits is not
what it requires, so no step may assert a phantom or a write skew.

A scenario's declared round-trip counts **MUST** be internally consistent with
the golden SQL it lists: each step's `roundTrips` equals the number of golden SQL
statements that step emits. A scenario whose groups compose several submissions
into one flush is graded on the state it states instead, because the statements a
composed flush issues are this module's to choose (`m-case-format` *State-graded
scenarios*). The harness asserts this consistency without ever
compiling a query to SQL — proving the round-trip contract from the fixture
itself — and executes the listed golden SQL against the real database to confirm
result-correctness.

Two contracts above are deliberately **not** witnessed by golden SQL, because no
emitted statement can carry them: how many times an attempt consulted the Clock
Strategy, and that an Actor Identity left no trace. Both are observable only
from inside an implementation, so each language target proves them in its own
suite — clock access through a counting Clock Strategy, and audit neutrality by
planning one flush twice under different Actor Identities and comparing the
resulting Write Plans, SQL, and binds.
