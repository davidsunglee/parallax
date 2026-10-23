# m-unit-work — Transactions & Unit of Work

`m-unit-work` is the unit of work: the coordinator of one writable transaction
attempt that **buffers, finalizes, and flushes** writes, and the automatic
read-correctness rules that make that attempt's reads safe. It is expressed entirely in terms of **operations
and object state** (`m-predicate`): it depends on `m-predicate`, on `m-wire` for
serialized write-literal conversion, on the execution port `m-db-port`, on
`m-temporal-read` for the coverage it judges, on `m-write-plan` for the Planned
Step algebra it produces and the State Observations it carries, on
`m-temporal-write` for the temporal expansion it drives, and on `m-edit`, which distinguishes authored assignments from state carried by
derivation, but **not** on `m-sql`. The
dialect-specific SQL the unit of work executes (the read-lock suffix, the
set-based forms) is produced by `m-sql` and run by the execution runtime
(`m-execution`) through the step-execution, flush, and row-acquisition
ports this module declares, so `m-unit-work` takes no direct edge to SQL generation. (`m-op-list` and
`m-navigate` in turn depend on `m-unit-work`, because a list is an
query-backed view resolved within a unit of work.)

Layered on the unit of work are four modules: the automatic shared read lock
(`m-read-lock`), bounded automatic retry (`m-auto-retry`), the transaction-scoped
identity map (`m-identity-map`), and the process-wide identity + query caches
(`m-process-cache`, deferred).

`m-unit-work` also owns **write finalization**: the Write Planner and its stage
order, which settle buffered writes into `m-write-plan`'s Planned Step algebra;
the authoritative affected-row enforcer; and the Write Effect Error family that
enforcer raises (ADR 0041, ADR 0048). Sibling policy modules
(`m-batch-write`, `m-opt-lock`, `m-read-lock`) keep their own policies and
reach planning and write admission only through strategy ports this module
declares, which model preparation (`m-execution`) wires in once per accepted
model.

## The unit of work

A **unit of work** coordinates the writable work of one transaction attempt:
the scope within which object reads and writes are coherent. It is not the
transaction. The attempt opens the native transaction and owns its lifetime —
whether it still admits work, whether it is rollback-only, and the first cause
that made it so (`m-execution` *Attempts*) — and the unit of work consults and
dooms that lifetime rather than holding a state of its own. A read-only attempt
opens a transaction with no unit of work at all. Within one unit of work:

- Writes are **buffered** as pending operations, not flushed eagerly. At the
  unit-of-work boundary they are **finalized** — combined, batched, and ordered
  to respect foreign-key constraints — then flushed in one pass.
- A read that depends on a not-yet-flushed write **MUST** observe that write: the
  unit of work flushes pending writes before serving a dependent read
  (read-your-own-writes), so a query never returns stale in-transaction state.
- A predicate-selected write's one readless statement runs **at its call**
  (`m-batch-write`): it never enters the buffer, and every write buffered before
  it is flushed first, in the same flush as that statement.
- Those three are the **whole** trigger vocabulary: a **read dependency**, a
  **predicate write**, and the boundary's **pre-commit** flush. There is no size
  threshold, no periodic flush, and no caller-invoked one — physical write
  timing stays encapsulated, and a flush that reached the database is therefore
  attributable to exactly one of the three. The joined (nested) boundary adds no
  further trigger: it shares the outer unit of work's buffer, and the outer
  boundary's pre-commit flush is what flushes it. The last trigger is named for
  when it runs, because **finalization** already names the planner stage every
  flush of every trigger goes through.

Where an implementation owns connection lifetimes (`m-db-port`), each **attempt**
holds one connection. It is acquired after the attempt begins and before the
physical boundary opens, every read, flush and participating delivery
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

The attempt a unit of work coordinates either **commits** or **aborts** (rolls
back). A commit makes its writes durable and observable; an **abort discards
them entirely**. The
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
affected-row shortfall, or a failure applying a completed settled write (*Write
Groups*, below) — **dooms** the attempt before it propagates, whichever operation
triggered the flush. A doomed attempt accepts no further reads, writes, or
flushes, refuses commit, withholds the callback's return value, and rolls back,
even when the callback caught the failure and returned normally; the first
cause is retained. A refusal raised while a write is prepared, admitted, or
planned precedes execution and does not doom the attempt. That holds for a
predicate-selected write's own statement too: a refusal building or auditing it
after its flush executed the writes buffered before it fails that flush without
dooming the attempt and returns none of those writes to the buffer, while a
failure lowering, executing, or enforcing it dooms the attempt as any execution
failure does.

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
  attribute-named neutral write input (`rows`), authorized by the source it was
  stated through: `insert` opens a row, `amend` assigns the members its row
  names, `replace` states the object's complete writable state
  (*Source-authorized replacement*), and `delete` / `terminate` end it, each
  with its bounded `*Until` form where one exists;
- a **predicate-selected** instruction — an `amend`, `replace`, or `delete` of
  every row of a `target` (`entity` plus a bare `m-predicate` predicate)
  matching that predicate, with `assignments` on the amendment and a `row`
  stating the complete writable state on the replacement, written by one
  readless statement at its call and so admitted only over an unversioned,
  non-temporal target, which has no history to close and no Valid Time to bound
  (`m-batch-write`);
- a **target** instruction — an amendment (`amend` /
  `amendUntil`), a complete replacement (`replace` / `replaceUntil`), a
  deletion (`delete`), or a termination (`terminate` / `terminateUntil`) of the
  one existing `entity` object its `row` names by primary key, carrying exactly
  one caller's starting revision as `ifVersion` or `ifTxStart`
  (*Target writes*).

The embedded predicate is a canonical `m-predicate` node, legal vocabulary here
because `m-unit-work` already depends on `m-predicate` (the dependency-graph edge);
the write instruction is the sole place the write side reaches the algebra.

**How a write instruction spells the Entity it addresses.** A keyed or
target instruction's `entity`, a predicate-selected instruction's
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
  settles against its own Temporal Observation, and
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
is never a Planned Step, and a Planned Step is never serialized back into one.

### Serialized write elaboration

A serialized keyed, target, or predicate-selected row, or a
predicate-selected assignment, is structural input, not a planned value. After resolving the exact target Entity and member identity, the
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
resolves the target first and judges whether it admits the write. A
predicate-selected write refuses a versioned or temporal target
(`set-based-write-target-unsupported`, `m-batch-write`) before anything else is
judged. A keyed or target write is judged for applicability: a temporal
target refuses `delete`; the window must be stated as the verb's form requires,
admitted by the target's temporal profile, and ordered; a non-temporal target
refuses a milestone verb; and a temporal keyed instruction carries one row. Only
then is the payload judged — a keyed row's subtype shape, members, and values, or
a predicate-selected write's predicate, family refusal, and payload: an
amendment's every assignment member resolved, in authored order, before any
value is judged, and a replacement's row naming declared members only, then
completed and judged as every replacement is (*Source-authorized replacement*). `prepareWireWrite` applies the serialized decoding above;
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

A target instruction is judged in its own fixed order: its target,
verb, and window first, as above; then its revision arguments against the
target's revision kind — an unversioned Non-Temporal target, which has no
revision kind, is refused before any argument is weighed, and otherwise
stating both is refused first, then a misstated kind, then a missing one, then
a value of the wrong type; and only then its payload, whose key names the
object. An amendment's every other member is judged as an assignment, and a
replacement additionally states every writable member: an omitted required one
is refused, an omitted nullable one is written empty, and an omitted `many` the
empty collection. A deletion or termination names the key alone, and any other
member it states is refused. A missing revision is therefore heard before an
undeclared member, and an inadmissible window before both.

`PreparedKeyedWrite` carries the exact target, deeply owned managed rows, and
prepared temporal bounds. `PreparedPredicateWrite` carries its
`ResolvedMutationSelection` and the one owned managed row it assigns every
selected object, which never states the key and is empty for a deletion.
`PreparedTargetWrite` carries its exact mutation, the exact target, its one
owned managed row, prepared temporal bounds, and its validated starting
expectation — an expected version or an expected Transaction-Time start.
Whether it assigns, replaces, or destroys follows from that mutation, so no
later stage reconstructs the verb from its row. Omission and nullable assignment remain structural states; no prepared
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

A managed source recognizes a keyed write value as its own through the
**publication provenance** it records when it publishes the value from valid
Entity State: the concrete Entity, the source Pin, and whether the result root
conforms. That provenance needs no write evidence, so a value a standalone read
or a read-only transaction published is a stored value of its source exactly as
one a writable attempt's read published.

**Read Evidence** is the opaque record a read of a **writable transaction
attempt** attaches beside that provenance. It records the concrete Entity, Object
Key, source Pin, read participation, and retained observation when one exists.
Read Evidence is an implementation-private selector for evidence; it is not
itself a State Observation, a lock, a database gate, or write authority, and a
value carrying it must still satisfy the Effective Concurrency Strategy's
evidence rule. A standalone read and a read-only transaction attach none: they
collect no observation, participation, predecessor row, or raw document for a
write *Current-attempt source admission* would refuse anyway, and a value they
published is refused there for having no Read Evidence of the writing attempt.

Publication of diagnostic data is not source admission. A hydratable node
exposed inside a classified result root (`m-snapshot-read`) is treated as
**NotStored** by keyed amendment and replacement verbs: no valid managed read
source produced it for writing. This applies to every node in the classified
root's graph, including a node whose page-owned Entity State is also reached by
a separate valid root. The separate root-local node is a stored value and may
carry its own Read Evidence; the classified root's node may borrow neither.

Provenance has exactly three answers for a given verb, and they **partition** the
values that verb can be handed: no valid managed read admitted the value as a
keyed source, the source this verb writes through did, or a **different** managed
source did. Each answer is a refusal for one family of verbs, so a refused value
always has exactly one code:

```text
WriteValueRefusal = NotStored | AlreadyStored | ForeignLifecycle
```

- **NotStored** (`write-value-not-stored`) — an `amend` / `amendUntil` /
  `replace` / `replaceUntil` verb was
  handed a value **no valid** managed read admitted as a keyed source. No source
  provenance establishes a stored row for it to address, so the refusal names the
  `insert` verb as the one that accepts it —
  **unless the value carries the authority of an insertion still standing in the
  writing unit of work** (*Insertion authority*), in which case it is accepted
  and revises what that insertion opened.
- **AlreadyStored** (`write-value-already-stored`) — an `insert` / `insertUntil`
  verb was handed a value produced by a read through **the very source this verb
  writes through**. That value already denotes a row that source stores, so the
  refusal names the `amend` verb.
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
insertion opened a row for the write to address. **Read-your-own-writes** is
therefore normative: an implementation that refused such a value would refuse the
developer spelling of *Insert-then-amend coalesces in place*, and its refusal
would name the `insert` verb the developer had just called. The exemption is the
**authority the value carries**, never the object it names: a value of an object
this unit of work inserted that carries no standing authority — one built
independently with the same key, or derived before the insertion was admitted —
is refused exactly as any other value no read produced is, and no other unit of
work's insertion lifts anything.

Three consequences are normative:

- A value this verb's own source produced that no author has changed is **not** a
  provenance refusal for an `amend` verb. Once its source is admitted
  (*Current-attempt source admission*) it assigns nothing, so it buffers nothing,
  claims no state, issues no statement, and raises nothing. Requiring an
  author to test each value before writing it would defeat the change tracking
  the framework performs on the author's behalf.
- Every refusal is decided from provenance **before** the row is derived, so a
  value a verb does not accept reaches no row derivation, no buffer, no plan, no
  SQL, and no database. A refusal is never a translation of a lower-level failure
  raised further down that path.
- The read-your-own-writes exemption is decided the same way, from the authority
  the value carries rather than from a row derived for it. A value that can key
  no row at all carries none, so it reaches the NotStored refusal rather than
  whatever failure deriving its row would have produced.

The `delete`, `terminate`, and `terminateUntil` verbs derive an identity row alone
and take no position on provenance; nor do target write verbs, which address
their object by key (*Target writes*).

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
anchor is read inside the flush — under the shared row lock where the
Entity's Effective Concurrency Strategy is Locking — and every row the attempt
opened is revised or removed in place (*Rows the attempt opened*). A versioned
Non-Temporal row advances from the version the attempt's own writes left it at,
which needs no read. Such writes compose with observed writes of the same object
in authored order — over unequal windows on a temporal object, and at one claim
scope on a Non-Temporal one — each keeping its own anchor or source condition;
completion treats the observed sources as *Observation ownership and lifetime*
states, and spends nothing of the insertion's authority.

A further insertion of an object is a repeat, refused as **AlreadyStored**,
while anything an admitted insertion of it opened is pending, or is stored and
not removed in full by the writes pending beside it. Once everything those
admissions opened has been removed — or the pending writes remove all of it — a
fresh insertion is admitted. It executes after every write authored before it,
so the removal it depends on precedes it whatever the batching, and a failed
removal or insertion dooms the attempt. Removing only part of the coverage, or
an interior gap, removes nothing in this sense. None of this permits removing
and re-inserting state that existed before the attempt.

### Current-attempt source admission

An ordinary source mutation — `amend`, `amendUntil`, `replace`, `replaceUntil`,
`delete`, `terminate`, and `terminateUntil` handed a value whose provenance the
verb accepts — is **admitted** only by Read Evidence a read of the **current
writable transaction attempt** produced, under either Effective Concurrency
Strategy, or by the standing authority of an insertion that attempt admitted
(*Insertion authority*). A joined callback shares its attempt, so a value either
of them read is current for both. A value a standalone read, a read-only
transaction, or an earlier attempt produced is refused at the verb as a
write-evidence failure tagged **`write-evidence-unavailable`**, before anything
is buffered and before any database access, whatever key or revision it shares
with the stored row: it participated in nothing the writing attempt can stand
on. The strategy then decides what the participating read must also prove —
under Locking, the shared lock it holds; under Optimistic, the observation the
gate binds (`m-opt-lock`) — and evidence that reaches no state this attempt
still protects is refused, as a write-evidence failure tagged
**`write-evidence-consumed`**, as *Observation ownership and lifetime* states.

Admission precedes the empty amendment's elimination: an amendment that assigns
nothing is dropped only once its source is admitted, so stating nothing never
lets an ineligible source pass. Replay re-runs the callback's reads rather than
refreshing a captured value, so a value an earlier attempt published licenses
nothing in the attempt that replays it. A caller holding an earlier observation
states the revision it observed through a target write instead
(*Target writes*).

### Source-authorized replacement

A keyed `replace` / `replaceUntil` states the complete writable state of the
object its source addresses, under exactly the authority an amendment of that
source would have: the source's current-attempt read evidence, or the standing
authority of an insertion it carries (*Current-attempt source admission*), and
on a Bitemporal object the start that source names. Provenance, pins, evidence, continuation, and
invalidation follow the amendment's rules unchanged; the write takes no
condition or start of its own.

Every replacement, source-authorized, target, or predicate-selected,
states the same **completed writable state**. Each writable member it omits is completed rather
than carried forward: an omitted required scalar or single value object is
refused, an omitted nullable one is written null, and an omitted collection is
written empty. Nothing is filled from the source's evidence or any predecessor;
the state excludes framework-owned revision and temporal members, read-only
members other than the primary key, derived inheritance metadata, and
relationships, whose loadedness never changes it. The key addresses the object
and is never assigned; a predicate-selected replacement's predicate selects its
rows, so a key its row states addresses nothing and is never written. A replacement whose completed state equals what a
milestone holds keeps that milestone exactly as an equal amendment does
(`m-temporal-write` *Unchanged milestones*).

The replacement intent belongs to the verb, so it survives every carrier and
composition a write travels through — an observed, insertion-authorized, or
target write, and the composition of a pending insertion — whatever
authorized it. On a Bitemporal object a replacement establishes its state over
its whole window: rows it reaches take the completed state, and every part of
the window no current row covers opens with it (`m-temporal-write` *Observed
writes span their requested extent*). Authority comes first: a source whose
evidence or insertion authority fails opens nothing, so a replacement is never
an upsert, and existing-row proofs still do not coordinate concurrent creation
inside a gap, which can leave invalid overlapping coverage (`m-temporal-write`
*Concurrent creation in gaps is not coordinated*).

### Target writes

A **target write** addresses one existing logical object by primary key under
the starting revision its caller states, independently of a source value. The
revision is the version or Transaction-Time start of the milestone an earlier
query returned; it never comes from a read's evidence or anything the payload
carries. A predicate write remains predicate-selected even when its predicate
names a primary key or matches one object.

An **amendment** assigns the members it names and leaves every other member as
stored; a **replacement** states the object's whole writable state, completed exactly as a
source-authorized one is (*Source-authorized replacement*); a **deletion**
removes a Non-Temporal object; and a **termination** ends a temporal object's
coverage over its window, as a keyed `terminate` does (`m-temporal-write`). None
creates an object: the state it starts from must exist. Each buffers and
answers nothing; an explicit read reports the saved state. A versioned target
requires `ifVersion` and a temporal one `ifTxStart`. The revision a caller
states never changes: a replayed callback states it again, and nothing an
attempt reads replaces it. An unversioned Non-Temporal target has no revision a
caller could state, so no write can detect a change to it since a caller's
query, and it takes no target write: a caller writes it through a read
of the writing attempt, whose shared lock protects it (*Strategy selection*). A
write that states its condition is never admitted under a source's authority
instead, and a source-authorized write states no condition.

An amendment that names nothing beside the key is the **empty** write: once it is
validated it is dropped, with no database work, no existence or revision check,
and no effect on earlier pending work. Only an amendment can be empty. A deletion
or termination states nothing beside the key either, yet it keeps its intent
through every stage, so a missing or revised target is its caller's failed
precondition and never an empty selection that succeeds. A nonempty amendment
and every replacement carry **revision intent**: a versioned row's version advances even when every
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
observed write's (*deferred settled write*): its flush reads the coverage its
window reaches that no row its settled write already holds covers, an amendment assigns
to each existing interval and creates nothing,
and a replacement also opens its state over every gap of its window
(`m-temporal-write` *Target writes span their requested extent*). Where
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
  stated state, else from a live read of exactly that state this attempt holds
  under its shared lock and no completed write of it has changed since, else
  from one **acquisition**: a point
  read of the stored row under the shared lock (`m-read-lock`) that executes no
  pending write and publishes nothing. The stated revision is compared with the
  row that acquisition holds; a row standing at another revision, or no row, is
  a failed precondition refused at the call, leaving the pending writes as they
  were, and more than one row is Cardinality Corruption. The write itself is
  ungated. A temporal target's state is the milestone its stated start and its
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

  A temporal target's acquisition reads its row **whole**, every Value Object
  occurrence and the raw Structured Column included, so the write's range can
  reuse that row as coverage (*Retained starting rows*). The call still judges
  only what a read of the row alone judges — its Attributes; each occurrence is
  judged at the write's execution turn, if the row is reused at all. The wider
  read is the one place a failure can move earlier: a database or driver failure
  producing an occurrence's column is the acquisition's, at the call.

A failed precondition is the caller's: re-running the transaction re-states the
same revision, so it is **never retried**, and no diagnostic read distinguishes
a deleted row from a revised one. A failure at
flush dooms the attempt like any other execution failure.

An object this attempt **admitted an insertion** of is refused to every
nonempty target write, before and after a flush, whatever became of
the insertion, as a write-evidence failure tagged **`write-evidence-inserted`**:
until commit, it is written through its insertion's source or a fresh read. The
attempt keeps that admission for its whole life for this reason alone (*Rows the
attempt opened*). An object the attempt only rewrote is no
insertion, and a later transaction addresses a committed insertion like any
other row.

### Retained starting rows

A temporal target's Locking acquisition keeps the row it read with the write as
**pending data**, not evidence: its Attributes judged, its Value Object
occurrences pending, its raw Structured Column beside them. The row names the
exact milestone it is, by its own coordinates rather than the caller's
`validFrom`, and the attempt's count of completed changes when the read ran. It
grants no authority — the condition the call proved stays the caller's — and it
is no observation: no write is admitted on it.

When the write's range reaches its turn — or its acquisition span's first
write's turn (*Shared coverage acquisition*) — the row is **current** if no settled
write completed since its read has changed that exact milestone (*Write Groups
complete before later work runs*) — even one that kept its address and
revision. A write that kept the milestone unchanged, or changed other states, does
not make it stale. A current row
is **completed** — each pending occurrence judged as an ordinary read judges it,
with no statement, Database Call, or activity, and a finding refusing the write
at that turn — and joins the range's coverage exactly as a row its coverage read
returned would. A row no longer current is discarded without being judged and
the coverage it held is read instead; the caller's condition is still judged,
against the rows the range binds. Under Optimistic nothing is retained, since
no acquisition runs. A retained row is released once its range has reused or
discarded it, and with its write wherever the write itself is dropped.

### Row acquisition

A write that must read existing rows before it can be settled reads them through
one **row acquisition** port this module declares and the unit of work is
constructed with; the execution runtime implements it (`m-execution` *Row
acquisition*). A request describes what to read and performs no read:

| Request | What it reads | When |
|---|---|---|
| **Target** | the one row a Locking target write addresses, at `validFrom` for a Bitemporal target, when no pending write or live read already proves it; a temporal one whole, retained with the write | when the write is buffered, with no force-flush |
| **Coverage** | the current milestones of one or several objects overlapping the parts of each object's window no row it holds covers, in statements naming a bounded number of object/part terms each | when the flush reaches the deferred settled write, inside that flush; within an acquisition span, between the span's first write's turn and each write's own (*Shared coverage acquisition*) |
| **Completion** | nothing: the retained rows of a deferred settled write that are still current, each occurrence the target read left pending judged as a read judges it | when the flush reaches that write, or the first write of its acquisition span, before any of the span's coverage is read |

The unit of work hands each request a consumer of its own and receives the
consumer's result. The consumer reads the judged rows, and their aligned raw
documents, while the acquisition still holds them, adopts the row and document
references it keeps into canonical evidence (`m-write-plan`), and retains
nothing of the read itself; acquisition settles its resources however the
consumer ends. A completion reaches the same kind of consumer with no read
behind it. Where a write reads nothing, it requests nothing: a predicate write
is readless (`m-batch-write`), so it requests no acquisition at all.

## Write finalization

### The Write Planner

One **Write Planner** turns a flush's buffered intent into finalized semantic
steps. It is model-scoped, constructed once per accepted Metamodel with its
immutable batching, concurrency, temporal, and provenance strategies already
wired, and it exposes exactly **one** planning operation over buffered writes:

```text
finalize(
    WritePlanningRequest(
        actor_identity:       ActorIdentity,
        transaction_instant:  TransactionInstant,
        concurrency_preference: ConcurrencyPreference,
        buffered_writes:      CoalescedWrites,
        ownership:            AttemptOwnership,
    )
) -> WritePlan
```

**Attempt Ownership** is a read-only view of the current temporal rows the
attempt's own successful settled writes opened (*Rows the attempt opened*,
below), and of what those writes left for its temporal sources (*Observation
ownership and lifetime*). Planning reads it to decide what a temporal mutation
does to its predecessor, which of its sources continue, and which current rows
they bind to; it never changes it.

The returned **Write Plan** is execution-ordered, and its settled writes carry
the source evidence of **every** write admitted against
existing state — a write coalesced into another, superseded, or overwritten by a
later composed assignment included (*Observed-State Coalescing*). A write keeps
its source condition whatever happens to its values, so a settled write whose
surviving assignment came from one source still carries every source composed
into it, even when it emits no statement, and each such source stays live until
that settled write completes. Work that stated nothing against existing state —
folded into a pending insert, cancelled against one, or an amendment assigning
no member — carries no source.

No second planning operation exists to project the plan. A predicate-selected
write is planned apart, by one more operation answering the one Planned Step its
readless statement executes as — unversioned, expecting any count, an update
decorated once by the configured audit — and no settled write, completion, or
Write Group:

```text
predicateStep(prepared: PreparedPredicateWrite, actor_identity: ActorIdentity,
              transaction_instant: TransactionInstant) -> PlannedStep
```

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

The term **step** is reserved for one logical Planned Step; the term **stage**
describes one private transformation inside the pipeline below.

### The planning pipeline

The Write Planner privately owns this stage order:

```text
1. resolve identities and coalesce buffered intent
2. eliminate known cancellation and no-op work
3. form compatible batches
4. dependency-order writes into mutation phases
5. validate the observation each surviving write carries
6. resolve the Transaction Instant only if surviving work needs it
7. temporal expansion: expand each temporal write's Coverage Transform over the
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
  one indivisible write through stages 3–4 and expands at its already-decided
  position in stage 7 (ADR 0045), so its own steps hold its closes ahead of its
  successors. In a Write Group of several settled writes, other objects' steps
  may also come between them (*Write Group formation*; ADR 0076).
- **Audit follows topology and precedes realization and lowering.** Stage 8
  reads each produced row's Row Origin and each close's Close Cause and adds
  ordinary planned values; it changes no topology, target, gate, or affected-row
  policy, and emits no SQL. Every row a write produces — a new lineage's
  opening, or a successor carried or changed from its predecessor — is
  **finalized once**, before
  settlement chooses whether it is inserted or revises a row the attempt owns,
  and every value finalization adds is an executed assignment of the row
  (`m-write-plan` *Write Rows*). Each Non-Temporal update, keyed or readless, and
  each emitted close is **decorated once**; neither needs a complete row. A
  guard, a removal, a delete, and a milestone kept unchanged store no
  represented value and are not audited. The audit-neutral default answers each
  input itself without resolving the Transaction Instant (ADR 0071, superseding
  ADR 0037).

Stages are otherwise private. The stage list is an ordering contract, not an
interface: nothing outside the planner may name, observe, or invoke a stage.

Stages 1–4 rewrite the buffered sequence: they merge, drop, split, and reorder
it. Stages 5–9 are **Write Settlement**, and the sequence stops changing shape
there — settlement reads it once, validates the observation each surviving write
carries as it settles that write, and only Planned Steps come out. Settlement
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
WritePlan(entries: PlanEntries, acquisition_spans: AcquisitionSpans)

PlanEntries: an immutable, ordered, possibly empty sequence, each entry one
    Write Group or one deferred settled write
WriteGroup(writes: Writes, steps: PlannedSteps)
Writes: the group's writes in order, at least one, each with the effects its
    success publishes: the states it changes, advances, and destroys, the
    temporal rows it derives from its predecessors, the attempt-owned rows it
    removes and opens, and the current rows it leaves
PlannedSteps: the immutable, ordered, possibly empty sequence of Planned Steps
    the group's writes execute, indexable and repeatable
AcquisitionSpans: the immutable, ordered, possibly empty sequence of
    non-overlapping half-open ranges of entry positions whose deferred settled
    writes share coverage acquisition (*Shared coverage acquisition*)
```

A **Write Plan** is the immutable, **execution-ordered** result of one planning
call: a sequence of entries, each a **Write Group** owning its Planned Steps and
the settled writes they belong to, or one deferred settled write, which no
planned group holds: execution forms the Write Group it runs in once its range
binds (*Shared coverage acquisition*). Its Planned Steps contain every Planned
Step that survives coalescing, cancellation, and known no-op elimination, with
temporal topology and correctness semantics already decided.

- A Write Plan **MUST NOT** retain a Transaction Instant, a raw Write
  Observation, the transaction's Concurrency Preference, an Actor Identity, a strategy
  object, a private group, or any other planning context.
  Derived values are materialized *into* the steps instead. A Write Group is the
  plan's produced execution structure, not planning context.
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
- A plan of **no** entry is the one canonical result for complete cancellation
  or known no-op elimination. There is no empty-plan sentinel and no second
  result variant.
- A **deferred settled write** is the one exception to fully expanded topology. A
  temporal object's observed writes whose requested Valid-Time range reaches
  current coverage no planning input observed (`m-temporal-write` *Observed writes
  span their requested extent*) finalize to their meaning — the composed
  assignments over that range, the source conditions, and the resolved instant —
  together with the one coverage read that range needs. Such a settled write
  carries no planned step, and its meaning is data: it retains no binder, Attempt
  Ownership, clock, strategy, or Actor Identity. By the time the flush reaches
  it, the unit of work has acquired the object's current rows over the range not
  already covered (*Row acquisition*) — at that turn, or earlier through its
  acquisition span's shared reads (*Shared coverage acquisition*), inside the
  flush either way and under `m-read-lock`'s shared lock when the effective
  strategy is Locking — and at its group's turn it binds those rows, or the
  absence of any, with the observed ones into the write's physical steps, before
  any step of the Write Group it runs in executes. Temporal meaning,
  concurrency, and gates are fixed when planning returns, and binding never
  recaptures the instant or consults the model: only the physical enumeration
  waits, for the rows read and for the Attempt Ownership and source continuation
  every earlier Write Group published. Binding reads the one Attempt Ownership
  view its flush planned under (*Write Groups complete before later work runs*).
  Binding audits each row it produces and each close it emits once, as stage 8
  does for a write settled at planning, changing no topology or gate. A range
  whose observed rows already cover it
  settles at planning like any other write. A target temporal write is
  such a range whatever it composes with, unless observed rows of its
  composition cover its window; its meaning also carries the caller's starting
  condition, which binding judges against the rows read before any step exists,
  and a replacement's extent, whose uncovered parts binding opens. Its meaning
  carries, too, the starting rows its callers' Locking acquisitions retained
  (*Retained starting rows*): one still current when its coverage is prepared is
  completed and reused as coverage, a stale one is discarded unjudged, and only the parts
  of the window neither those rows, the observed originals, nor the current rows
  the attempt holds for a continuing source (*Write Groups complete before later
  work runs*) hold are read; a
  part that read finds nothing in is a gap, read once, and a rectangle created
  concurrently inside a held row's interval is not reached (`m-temporal-write`
  *Concurrent creation in gaps is not coordinated*). Each caller's start holds
  only where a current row stands at the stated start, literally; any other
  caller's start is a failed precondition.
- A Write Group's Planned Steps are a **logical** sequence. An implementation MAY
  pack homogeneous runs and expose stable immutable views during iteration
  rather than allocating one container per step; every exposed view is
  immutable and stable, and equal views need not have object identity.
- Each settled write — one keyed write with its expanded temporal topology, or
  one batch — retains its own completion facts, produced values like its steps,
  and executes in exactly one Write Group: the plan's group holding it, or, for a
  deferred settled write, the group its binding forms.

### Write Group formation

Settlement forms the Write Groups as it settles the sequence stage 4 ordered.
A flush's writes form one **region**, except that an insert which must follow
the removal clearing its way starts a new one. Within each region the inserts,
then the updates, then the deletes are each one **mutation phase**. A Write
Group never spans two mutation phases.

Consecutive settled writes of one mutation phase share a Write Group while the
objects they write are distinct:

- Each settled write names its **complete** set of Object Keys under its
  Inheritance Family's primary key: every row of a batch, and the one object a
  keyed, composed, or step-less write names. A write naming an object the open
  group already holds starts the next group.
- A group holds at most 64 settled writes, so a group's inserts wait behind the
  non-insert steps of at most that many settled writes, however many the flush
  holds.
- A write whose insert the database allocates a key for, and a write naming no
  complete key — an insert whose key is absent or database-computed — each form
  a group of their own.
- A deferred settled write is a plan entry of its own, in no planned group: the
  group it executes in forms when it binds, from the ready writes of its
  acquisition span, or from it alone outside any span (*Shared coverage
  acquisition*).
- A settled write with no step joins like any other and completes with its group.

A group's Planned Steps are every write's non-insert steps — each step that is
not an insert — followed by every write's inserts, each write's own order kept
within both. An update- or delete-phase write's inserts open the successors of
its own non-insert steps, and an insert-phase write produces only inserts, so
the layout moves only successors, and only past other objects' steps: no insert
moves behind a non-insert step of another mutation phase. A group of bound
deferred writes is laid out the same way. Nothing else is reordered: the phases,
the referential order, and the authored order of updates are stage 4's, and no
key sort applies. As it forms the groups, settlement also records which
consecutive deferred settled writes share coverage acquisition (*Shared coverage
acquisition*); that record reorders nothing.

### Write Groups complete before later work runs

The unit of work runs a finalized Write Plan entry by entry, in order, Write
Group by Write Group: a planned group as settlement formed it, and a deferred
settled write in the group its binding forms (*Shared coverage acquisition*),
every write of which binds before any step of the group executes. It hands each
group's Planned Steps to the step-execution port as one sequence, which executes
every step of the sequence and has its effect enforced. As soon as every step
of a group has succeeded — at once for a group with no step — and the keys the
database allocated are as many as the group's writes open with keys it
allocates, and before any step of a later group executes or any later write
binds, the unit of work completes every write of the group synchronously, in
order. A coverage read is no step:
within an acquisition span a later write's coverage can be read before an
earlier group completes, while its binding, steps, and completion still wait
for its own group's turn (*Shared coverage acquisition*). No write of a group
depends on another's completion, because their objects are distinct (*Write
Group formation*).

A flush plans and binds its deferred settled writes under one Attempt Ownership
view, chosen once for the flush: the attempt's live ownership for a
read-dependency or predicate-write flush, and for the pre-commit flush the
same live ownership demanding nothing a write leaves for a source, so neither
its planning nor its binding describes a continuation it would discard. Either
view reads every completion earlier groups published. Completing a settled
write:

```text
record every state the settled write changed, invalidating its observations
advance the Non-Temporal sources of every versioned state it updated
end the Non-Temporal sources of every object it deleted
retire the attempt-owned rows the settled write removed
register the rows the settled write opened
continue the temporal sources of every state it transformed through the rows it derived
hold the current rows its execution stored that a continuing source reaches
```

A deferred settled write's changed states, removals, and openings are those its
binding produced. A milestone a settled write kept unchanged (`m-temporal-write`
*Unchanged milestones*) is
no changed state, even where a guard executed for it, and derives nothing a
later settled write relies on: it still stands. A Non-Temporal update or
deletion changes the state it addresses — a versioned row's observed state, or
an unversioned row's object, which observes no state — whether or not its
values equal what was stored; an update of a versioned row advances that state
to the version it writes, and a keyed deletion destroys every object it
addresses, all of a batch's included (*Observation ownership and lifetime*).
A predicate-selected write is no settled write: it identifies no object and
publishes none of these.
Removals are retired before openings
are registered, so a row removed and reopened at one physical address remains
owned, and an insertion whose last tagged row the settled write removed still
stands when a row the settled write opened is tagged with it. Nothing is
published for a group whose steps did not all succeed, nor for any write of a
group one of whose writes did not bind; such a failure dooms the attempt
(*Abort*). A failure completing one write of a group leaves the writes completed
before it published, completes none after it, and dooms the attempt.
Completion therefore happens per Write Group, not at the end of the flush: a
later group, and any read the flush serves, observes the earlier groups'
published effects.

A completed temporal settled write also records, for each predecessor it
transformed that a temporal source still reaches — an observed state some live
source value or pending or planned write still shares, or a row an earlier such
record reaches — the current rows it derived from that predecessor and the part
of each the predecessor's sources reach: the whole row, or only their own part
of a row merged from several predecessors' successors (`m-temporal-write`
*Merging produced successors*). A row a later settled write derives from such a
row carries each of the same sources over the part of it that came from their
part, and none over the rest, however many unobserved rows lie between it and
the state a source observed; a target-addressed write carries them like any
other, though it starts none of its own. A merged row may carry several
sources, each over its own part. Its guarded effect, or the shared lock it
held, protects what it derived: no other writer can have changed a row the
attempt opened. The same completion holds the complete stored state of each
current row such a part reaches, exactly as its execution persisted it, until
a later completed write derives from, removes, or replaces that row, or until
no part it holds describes a live observation, whichever of that observation's
sources still continue. Reading a row holds nothing, and neither does a
write no source's continuation needs. A later write through a continuing
source binds to those rows without reading them again or taking another lock;
coverage no held row covers is read as any range reads it (*Row acquisition*).
These records serve every later submission of the attempt, whatever flush it
reaches; nothing releases them at the end of a flush, and the attempt's end
releases them all. The pre-commit flush, which no submission follows and none of
whose writes continues from another, records none.

### Shared coverage acquisition

An **acquisition span** is a run of at least two and at most 32 consecutive plan
entries, each one deferred settled write of a Bitemporal Entity that names its
one complete Object Key, a key the database does not allocate. Its writes belong
to one mutation phase, target one concrete Entity — so one key attribute and one
member selection — and either all take the shared lock their coverage read
takes under Locking or none do. Each names an object no earlier write of the
span names under its Inheritance Family's primary key. A span never skips an
entry: any Write Group, a deferred write of another Entity or lock requirement,
a repeated object, a phase boundary, or the bound ends it, and the next eligible
write may start another. A deferred write outside any span, a
Transaction-Time-Only one included, acquires its coverage alone at its turn and
executes as a Write Group of its own.

A span grants acquisition permission; its execution groups follow readiness.
Whenever the span's first remaining write is ready, the unit of work binds it
and each consecutive ready write after it, up to the first that is not, as one
Write Group laid out as *Write Group formation* lays out any group; it executes
and completes that group before binding any later write or reading any further
statement (*Write Groups complete before later work runs*). The span's bound of
32 writes keeps every such group within the 64-write bound, and no statement is
read, and no ready group delayed, to enlarge a group. Each write binds against
the rows read and the Attempt Ownership every earlier group published; the
writes of one group name distinct objects, so none binds against another's
completion. A deferred dependency is not coverage: no write's coverage is read
before an earlier write of its own object completes, because that write ends
the span first.

When the flush reaches a span's first write, the unit of work, before binding
any write of the span or reading any of its coverage, completes every
still-current retained starting row of every write in the span and discards the
stale ones (*Retained starting rows*), then determines each write's uncovered
parts once. It reads those parts in shared coverage statements (`m-sql`
*Requested ranges*), packed in the span's write order and each write's
Valid-Time order. A write is **ready** once every statement naming its parts has
succeeded, whatever those statements returned; a write with no uncovered part
needs no statement, takes no lock, and is ready at once. Before reading each
statement, the flush binds every leading write of the span that is ready as one
group, then executes and completes it; a ready write never passes a write
before it that is not. A statement is read only while the span's next write is
not ready, and no statement is read once every write of the span is.

That timing deliberately qualifies acquisition at each write's own turn:

- **Observation.** Under Read Committed, each shared statement observes the
  database as of its own execution, which can be earlier than a later write's
  turn; under Repeatable Read, it observes the transaction's snapshot and the
  attempt's own writes as any read does (*The Isolation Level beside it*).
- **Locks.** Under Locking, the shared lock is taken on the physical rows each
  statement selects, nothing wider (`m-read-lock`), when that statement runs.
  No order of lock acquisition across objects or transactions is promised.
- **Failures.** The failure actually encountered first propagates, and no
  failure is collected, deferred, ranked, or replayed to reproduce acquisition
  at each write's turn. A refusal completing any write's retained rows precedes
  the span's first statement and every binding, even that of a write ready at
  once. A statement's failure, or an invalid stored row it returns, precedes the
  binding and execution of every write still waiting for that statement, an
  earlier write's included; which of several invalid rows one statement returns
  is reported is not promised. Every write of a ready group binds and audits
  before any of the group's steps executes, so a later write's binding failure
  precedes an earlier write's statement failure, and the group's non-insert
  steps precede its inserts, so a later write's affected-row shortfall can
  precede an earlier write's insert violation (`m-execution` *Flush
  execution*). A ready group's binding or execution failure completes none of
  its writes and precedes every statement the span would read after it. Writes
  that completed before a later statement or group failed stay published until
  the doomed attempt ends (*Abort*), and no waiting write binds or executes
  after any failure. Classification, retry eligibility, and rollback are the
  encountered failure's own (`m-db-error`, `m-auto-retry`); because which of two
  independent failures is encountered can differ from acquisition, binding, and
  execution at each write's own turn, so can they.

Each shared statement is one read Database Call of the enclosing flush; the
flush adds no activity, call, or record per span, per group, or per write for
it (`m-execution-lifecycle`).

## Planned Steps and State Observations

`m-write-plan` owns the Planned Step algebra — Row Origin and Close Cause,
planned rows and assignments, the Write Target, the Write Gate and its
concurrency decision, and the Affected Rows Policy — and the State Observation
vocabulary: the Object Key and Object State Key that address evidence, and
the Predecessor Row a Temporal Observation retains. This module settles
buffered writes into that algebra, carries each observation to the write it
settles, and owns how long that evidence stays eligible.

### Observation ownership and lifetime

A retained observation belongs to the **source values that observed it**, not to
the transaction that ran the read. An implementation **MUST** make the evidence
reachable from the source value and **MUST NOT** make eligibility depend on a
transaction-scoped store. A transaction retains only a **weak index** of the
states its own reads have seen, a **weak registration** of each Non-Temporal
source its reads published, the **participation** those reads license, and what
its own completed writes established about the states they produced — for a
temporal source still reaching them, the current rows those writes left. Only a
value a read of the writing attempt produced is eligible at all
(*Current-attempt source admission*); among those, eligibility follows the rules
below.

These rules follow, and an implementation **MUST** exhibit all of them:

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
- **Own writes continue temporal sources.** A temporal source's authority
  follows what this attempt's completed writes left of the state it observed,
  and its values and observation never change. Until a completed write changes
  that state it settles against the state itself. Once one does — through this
  source, another source, a caller's stated start, or an insertion's authority
  — it reaches the current rows those writes derived from it, through any
  number of further completed writes and unobserved rows, without another
  read, while some part they hold of the state it observed covers its
  Valid-Time pin, or, read without a finite one, while any part survives. Its
  write settles against those rows as against any row the attempt opened
  (*Rows the attempt opened*), under either strategy. A
  milestone a completed write kept unchanged (`m-temporal-write` *Unchanged
  milestones*) changes no state, so its sources settle against it as before.
  Survival is judged per pin, so sources sharing one observation can part: one
  whose pin a bounded destruction removed is ended while one whose pin
  survived continues. A pin the attempt's later writes cover again reaches
  nothing it observed, so an ended source never revives, however the object
  is written or reinserted since. A write through an ended source is refused
  at the verb as `write-evidence-consumed`. Lineage serves sources, never
  conditions: a caller's stated start is judged literally against the current
  rows, whatever this attempt wrote before it. A failed flush dooms the
  attempt, so nothing needs restoring.
- **Own writes continue Non-Temporal sources.** A Non-Temporal source's
  authority follows the protected state it reaches, and its values and
  observation never change. A versioned source reaches the state it observed
  until a settled write of this attempt completes an update of that state —
  through this source, another source, a caller's stated revision, or an
  insertion's authority — and from then on the version that update wrote,
  through any number of such updates, without another read. Its write settles
  against that state, gated on it under Optimistic and protected by the lock
  the attempt's own write holds under Locking. An unversioned source's shared
  lock covers every state of its object, so its own completed updates leave it
  standing. A completed keyed deletion of an object ends every source of it
  for good: an insertion admitted at the same key later grants a fresh
  authority, which no earlier source shares. A write through an ended source is
  refused at the verb as `write-evidence-consumed`. A readless predicate write
  ends nothing and advances nothing, since it identifies no row (*Readless
  writes identify no target*).
- **A source publishes as fresh as its read.** Evidence published from rows a
  read acquired before a settled write of this attempt completed a change of
  what it observed — a versioned or temporal row's observed state, or an
  unversioned row's object — licenses no write, however long after that change
  it is published, whatever source the change came through, and even once its
  object was reinserted; a write through it is refused as
  `write-evidence-consumed`. A read after the change publishes fresh evidence.
  The judgment is made once, when the evidence is published, so a later change
  never makes an already published source stale: that source follows the
  continuation rules above.
- **An own change invalidates.** When a settled write successfully revises,
  closes, or removes an observed state, every observation of that state the
  attempt's reads produced no longer describes the stored row, even one no
  write used and even when the changed row keeps its address and revision
  token, so no later read reuses it and a source tied to it settles only
  through the continuation rules above. The rule is judged against the state
  the rows had **when the read acquired them**: evidence built later from an
  earlier read's rows is ineligible. A read after the change observes fresh,
  eligible evidence. Invalidation is per Observed State — an unaffected
  rectangle of the same object stays as it was — and it moves one way and
  survives the attempt.

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
observation resolved for it — and a write with none carries no
observation field for anything to be absent from. Absence is therefore the
absence of the pairing rather than a field carrying it, which is what lets
planning read a write's address, gate, and carried state off one object. What an
unobserved write MAY still travel with is what *Observed-State Coalescing* below
gives it: the claim scope it takes, and the source it was admitted through.
Neither is an observation.

### Comparing an assigned member with its persisted value

A **keyed** write's assignments are **literal**. The members its author
expressed — a Typed edit's cumulative touched members, a Wire change document's
keys — are assigned whatever the source published for them, so an assignment
equal to the stored value is still written: it advances a version, and for a
temporal entity it is applied like any other assignment. A keyed temporal
write's changed successor overlays every member the write assigns and carries
every other member's persisted state. Only an amendment expressing **no**
member is empty; it buffers nothing and claims nothing. A replacement is never
empty: its completed state assigns every writable member.

A temporal milestone such a write leaves exactly as it was is kept rather than
closed and chained wherever that is proven (`m-temporal-write` *Unchanged
milestones*).

A predicate-selected write's assignments are literal too: its one readless
statement writes every row its predicate matches, whatever that row already
holds. An amendment of it expressing no member is empty as well, and so is a
replacement of an Entity whose only writable member is its key, since the
key is never written; each answers zero once judged, running nothing
(`m-batch-write`).

## Buffered, batched, ordered writes

At the unit-of-work boundary the buffered writes are flushed as **set-based** SQL
wherever possible:

- Multiple inserts or same-column updates of one entity become **one** Planned
  Step with several rows or keys, lowered as a single multi-row `INSERT` or a
  batched `UPDATE`. The canonical golden forms and their proof are
  `m-batch-write`.
- Operations are **ordered** so that a parent row is inserted before a child
  that references it (and deleted after), honoring foreign-key constraints.

Ordering is otherwise **unconstrained**. No buffered write is ordered against a
predicate-selected write: that write's one readless statement runs at its call,
after every write buffered before it, in a flush of its own (`m-batch-write`
*A predicate-selected write executes at its call*), and every write buffered
after it reaches a later flush. Each write is admitted as it always is, against
what the earlier flushes completed (*Observation ownership and lifetime*,
*Insertion authority*).

### Readless writes identify no target

A readless predicate write never reveals which rows it matched, so its
completion publishes nothing about any object: it changes no observed state,
advances or ends no source, and leaves no fact a later write is judged against.
An unversioned Non-Temporal source of the attempt stays usable after one, its
shared lock standing. A later amendment through such a source writes only the
members it assigns, so a member the predicate write assigned and the amendment
does not keeps the predicate write's value, while a replacement writes its
source's complete literal state, the predicate write's assignments included. A
source whose row a predicate deletion removed is still admitted; its keyed write
then fails its own affected-row expectation (*Affected-row enforcement*) — unlike
a completed keyed deletion, which ends the source at the verb. Nothing reads the
rows a predicate write reached, re-evaluates its predicate, or records them.

## Same-transaction write coalescing

Buffered writes of the **same object within one unit of work** combine before flush —
they annihilate or merge rather than each producing durable SQL, because a state a
transaction never durably exposed to any other reader is never separately recorded.
This follows Reladomo's transaction write queue (`TxOperations` /
`GenericBiTemporalDirector` same-transaction handling): a same-transaction
insert-then-amend writes the final value in place, and a delete cancels a matching
pending insert.

- **Insert-then-amend coalesces in place.** A row inserted and then amended or
  replaced in the same unit of work flushes as a **single** write carrying the
  **final** value; no intermediate milestone is fabricated. A **non-temporal**
  insert-then-amend emits one `INSERT` with the final values (never `INSERT` +
  `UPDATE`); an **Transaction-Time-Only** insert-then-amend opens a single current
  milestone with the final value — no close-and-chain, in contrast to the
  cross-transaction chaining of `m-temporal-write`; a **bitemporal**
  insert-then-amend covering the whole
  opening opens a single fully-current rectangle with the final value — no
  inactivation / head-tail split, in contrast to its cross-transaction rectangle
  split.
- **A pending Bitemporal opening takes each edit over its own coverage.** An edit
  of a still-pending opening is a temporal edit, composed with the opening as
  observed writes compose over stored coverage (*Observed-State Coalescing*): an
  edit bounded inside the opening splits it at its bound, one bounded at or beyond
  the opening's end changes all of it, and no amendment extends the opening past
  its own window. Every edit starts at the insertion's anchor (*Insertion
  authority*). The flush opens only the pieces that survive, each at the one
  Transaction Instant, carrying the opening's values with the edits' assignments
  overlaid; adjacent pieces of identical stored state open as one row
  (`m-temporal-write` *Merging produced successors*). A replacement reaching past the opening establishes its complete
  state over its whole window there too, as it would once the insertion had
  executed: still without a flush at the call or an intermediate insertion, the
  opening settles as one settled write at the normal flush that reads the stored coverage
  past its window inside the flush, transforms each row the composed
  writes reach under its own proof, opens the surviving pieces, and opens the
  replacement's remaining extent (`m-temporal-write` *Observed writes span their
  requested extent*). Every other composed edit reaches past the opening's window
  only as far as such a replacement does, the stored coverage there included. The
  opening's window counts as coverage, so nothing an earlier composed destruction
  removed from it reopens.
- **Insert-then-delete cancels.** A row inserted and then deleted in the same unit of
  work **cancels**: the two buffered writes annihilate and the flush emits **no** DML
  for that object — the net-zero effective-change-set elision, extended across two
  verbs. A bounded termination of part of a Bitemporal opening removes only its
  own window; the pair does not cancel, and the flush opens what survives.

A predicate-selected write's flush executes a pending insert, so a write of the
object buffered after it revises or removes the row that insert opened, through
the insertion's authority (*Insertion authority*), rather than combining with it.

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
  intents. A versioned Non-Temporal source's write is claimed at the protected
  state its authority reaches (*Observation ownership and lifetime*): sources
  that observed different states share one claim once this attempt's own
  completed writes carried them to the same current state, while equal keys or
  versions never relate two sources by themselves; and
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
| assignment | destruction, same region | **supersede** — the destruction replaces the assignments buffered before it, so an amendment then a delete at one scope is one delete |
| destruction | destruction, same region | **deduplicate** — the second says what the first said and adds nothing |
| destruction | assignment | **incompatible** — no write means to resurrect a row that is going away |
| any | any, different region | **incompatible** for a non-temporal write; a temporal object's observed writes compose instead (below) |

Merged assignments are literal: the merge keeps the caller's last word on each
member, and a member set back to the value its source observed is still
assigned. A superseded or coalesced write's source condition is kept by the
survivor, which claims the same scope.

**A target write claims the state its revision names** — the object at
its stated version — so it composes with observed writes of that same state by
the table above: an amendment and an observed assignment merge member by
member, a replacement replaces what came before it and is overlaid by what
follows, and a destruction — an observed one, or the caller's own deletion —
supersedes both while keeping the caller's condition, which the destruction's
own gate then binds.
One object's writes start from one state: a target write is refused
where any other write of the object pending — another stated revision, or an
observation of another state — stands at another scope, and so is an observed
write of another state while a target write of the object is pending.
The survivor of a composition keeps the caller's condition, its revision intent,
and every source the composed writes were admitted through; a shortfall against
its gate is the caller's failed precondition, ahead of any observed write's own
classification.

A target write of a **temporal** object joins that object's
composition (next paragraph), judged against every write of the object still
pending — overwritten ones included — and not only the latest. In each pair,
at least one write is a target write:

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
of the first, judged against every write of the object still pending:

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

A readless predicate write claims nothing: it observes no state and is never
buffered, and the flush it executes in ends every claim pending before it
(*Buffered, batched, ordered writes*).

A coalescing witness encodes **both** buffered mutations explicitly by authoring
the write step as an ordered **buffer-and-flush** scenario. `/scenario/<n>/write`
carries a **general ordered buffer of one-or-more keyed write instructions** — the
writes a single unit of work accumulates and flushes together — and the step's
golden SQL is the independent expected lowering of that flush. **Same-object folding
at flush is the coalescing rule**, a runtime/planner property rather than a
structural one: when two buffered instructions name the **same** entity and
primary-key identity the flush combines them (insert-then-amend writes the final
value in place; insert-then-delete cancels to no DML — one final-value write, or no
DML at all). The two-keyed same-object insert-then-amend / insert-then-delete pair
is that rule's **single-object special case**; the same buffer equally expresses a
single keyed write and a mixed multi-object flush (an `insert` / `amend` / `delete`
of **different** objects, ordered by foreign-key dependency). Predicate-selected
buffered instructions remain **deferred** — the buffer is keyed-only. The buffered
form and its authoring surface are the case format's (`m-case-format`); the
instructions themselves are the canonical `write-instruction.schema.json` shapes, so
an adapter exercises coalescing from the requested operations, never from the golden
SQL.

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
address, every current row its successful settled writes open — keyed inserts,
and temporal successors alike — and retires a row from that record when a settled write removes it. Reads record nothing.
A row whose key the database allocates has no address until its insert
executes, so that insert answers the key as row-producing DML (`m-db-port`) and
the settled write records the row under it. The answer is validated before it is used:
one row per row opened, each holding the key alone, an integer, none twice.
Anything else is a **Write Result Error**, an invariant failure that is never
retriable and, like any failure while executing, dooms the attempt.
Every admitted insertion stays recorded until the attempt ends, even once
everything it opened was removed or a pending removal cancelled it, because a
target write of the object is refused on that admission alone
(*Target writes*).
The record survives flushes and joined scopes, ends at commit or rollback, and
starts empty on retry. The row an admitted insertion's own insert opens is
tagged with that insertion in the record, and so is every successor of the part
of a row the insertion contributed, over that part; a successor of a row that
existed before the attempt, or of any other untagged coverage, is untagged, so
rewriting other coverage of the object beside an insertion adds nothing to what
the insertion opened. A row merged from an insertion's coverage and other
coverage (`m-temporal-write` *Merging produced successors*) is tagged over the
insertion's parts alone, and a row revised in place takes the tag its new
extent leaves. The insertion's coverage is completely removed once no part of
any row tagged with it remains (*Insertion authority*).
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
State Observation vocabulary is, so a planning request is well-typed before any
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
enforce_affected_rows(step: PlannedStep, actual_count: NonNegativeInt)
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
**nothing else**: no SQL, statement index, driver exception, whole Planned Step,
assignments, or observation. That keeps the diagnostic stable across dialects and
lets `m-auto-retry` recognize the canonical Optimistic Lock Conflict Error
without depending on an optional concurrency module.

A `FailedPrecondition` shortfall raises the **Write Precondition Error**
instead, carrying the Entity Identity, the object's key, and the revision the
caller stated — no count, because what failed is the caller's condition rather
than an effect (*Target writes*). It is the same error a Locking
submission raises when its acquisition finds the condition already false.

Retriability follows the classification, not the raising site: an Optimistic Lock
Conflict Error is a recoverable conflict the bounded retry loop replays
(`m-auto-retry`), while a Missing Target Error, a Stale Write Error, a
Cardinality Corruption Error, and a Write Precondition Error are **never**
retriable.

### When several steps share a driver batch

Multiple `ExactCount` steps MAY share one driver batch **only** when the adapter
returns one affected-row count aligned with each logical step; the unit of work
then enforces each count against its own step. One **aggregate** count is
sufficient only for a single Planned Step whose own Key Target holds several
keys, because that one target owns the aggregate expectation. An aggregate-only
backend **MUST** execute distinct `ExactCount` steps separately; it MAY still
reuse statement preparation and stream bind rows. This is what preserves exact
attribution of a shortfall to the step that caused it.

Ordered write transport (`m-db-port`) is such a batch wherever its result
confirms a count for a step. A statement failure, confirmed non-execution, an
unconfirmed statement, and an interruption supply no count: the unit of work
interprets only confirmed counts, each against its own step and in step order,
and a failure or interruption propagates as itself (`m-execution`).

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
Effective Concurrency Strategy also determines write evidence. Both strategies
require a read of the current attempt (*Current-attempt source admission*):
under Locking that read's participation proves the lock is held, while under
Optimistic the version or milestone evidence it retained becomes the gate that
lets the database detect an intervening write (`m-opt-lock`).

Reladomo is prior art for mixed participation, but exposes the choice per
transaction and object portal/class. Parallax deliberately keeps one ergonomic
Unit Work preference and derives the safe per-Entity result instead of exposing
per-Entity overrides.

The Write Planner consumes the Concurrency Preference and the model's Optimistic
Lock Facet, settles each Planned Step's gate or explicit `Ungated` decision, and
retains neither the preference nor the Effective Concurrency Strategy in the
Write Plan.

Write admission resolves the same strategy through the connected model's
injected write-evidence policy (`m-opt-lock` "The Optimistic Lock Facet"), which
also names what each keyed write settles against. The unit of work applies that
answer to its own state — the participation its reads stamp, what its
completed writes left of the states its sources observed, and the claims its
buffer holds — and buffering is the one operation that admits a write's claim
and buffers the write, all or nothing.

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
operation steps, each with a declared Database Call count — and plain write
cases:

| Case | What it proves |
|---|---|
| read-your-own-writes scenario | a buffered write is flushed before a dependent find observes it |
| rollback scenario | an aborted write is discarded; a post-abort find observes the original rows |
| fk-ordering / flush cases | buffered writes flush ordered by foreign-key dependency |
| insert-then-amend coalescing (`m-unit-work-008`, `m-temporal-write-008`, `m-temporal-write-030`) | a same-transaction insert-then-amend flushes as one write with the final value — no intermediate milestone (non-temporal / Transaction-Time-Only / Bitemporal) |
| insert-then-delete cancellation (`m-unit-work-010`) | a same-transaction insert-then-delete cancels — the flush emits no DML for that object |
| grouped inserts of distinct objects (`m-unit-work-058`) | inserts batching left as separate Planned Steps share one Write Group once ordering makes them adjacent, and execution inserts them with one statement |
| dirty-read refusal (`m-unit-work-031`) | at Read Committed, a reading unit of work observes the committed row while a concurrent one holds an uncommitted write to it |
| nonrepeatable-read refusal (`m-unit-work-032`, `-033`, `-034`) | at Repeatable Read, a unit of work's second read answers what its first did across a peer's committed write — for a plain find, a deep fetch's own included level, and a streamed delivery's pages |

Each isolation scenario declares `when.uow.isolation` and holds TWO units of work
open at once, labelled `reader` and `writer`, so that what the reading one
observes is graded WHILE the writing one is live. Each closes with an ungrouped
find stating only what both engines have committed: what the level permits is not
what it requires, so no step may assert a phantom or a write skew.

A scenario's declared Database Call counts **MUST** be internally consistent with
the golden SQL it lists: each step's `databaseCalls` equals the number of golden SQL
statements that step emits. A scenario whose groups compose several submissions
into one flush is graded on the state it states instead, because the statements a
composed flush issues are this module's to choose (`m-case-format` *State-graded
scenarios*). The harness asserts this consistency without ever
compiling a query to SQL — proving the Database Call contract from the fixture
itself — and executes the listed golden SQL against the real database to confirm
result-correctness.

Two contracts above are deliberately **not** witnessed by golden SQL, because no
emitted statement can carry them: how many times an attempt consulted the Clock
Strategy, and that an Actor Identity left no trace. Both are observable only
from inside an implementation, so each language target proves them in its own
suite — clock access through a counting Clock Strategy, and audit neutrality by
planning one flush twice under different Actor Identities and comparing the
resulting Write Plans, SQL, and binds.
