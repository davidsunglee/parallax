# m-unit-work — Transactions & Unit of Work

`m-unit-work` is the unit of work: the coordinator of one writable transaction
attempt that **buffers, finalizes, and flushes** writes, and the automatic
read-correctness rules that make that attempt's reads safe. It is expressed entirely in terms of **operations
and object state** (`m-predicate`): it depends on `m-predicate`, on `m-wire` for
serialized write-literal conversion, on the execution port `m-db-port`, on
`m-temporal-read` for the coverage it judges, on `m-write-plan` for the Planned
Steps it produces and the State Observations it carries, on
`m-temporal-write` for the temporal expansion it drives, on `m-concurrency` for
each Entity's Effective Concurrency Strategy, version source, and what its writes
settle against, and on `m-edit`, which distinguishes authored assignments from state carried by
derivation, but **not** on `m-sql`. The
dialect-specific SQL the unit of work executes (the read-lock suffix, the
set-based forms) is produced by `m-sql` and run by the execution runtime
(`m-execution`) through the step-execution, flush, and row-acquisition
ports this module declares, so `m-unit-work` takes no direct edge to SQL generation.
Bounded automatic retry (`m-auto-retry`) coordinates replay of attempts.

`m-unit-work` also owns **write finalization**: the Write Planner and its planning
order, which settle buffered writes into `m-write-plan`'s Planned Steps;
the authoritative affected-row enforcer; and the Write Effect Error family that
enforcer raises (ADR 0041, ADR 0048). Its planner owns collapse batching over
admitted writes and prepared rows, without an injected batching strategy.
`m-batch-write` owns only readless predicate policy, which this module consults
when preparing a predicate write.
Concurrency policy is a fact of the accepted model, which this module reads from
the model's Concurrency Facet and applies to its own attempt state.

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
  when it runs, because **finalization** already names what planning does on
  every flush of every trigger.

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

### No cross-read identity promise

The unit of work coordinates operations and their evidence. It makes no promise
that separate reads of one row return the same instance or distinct instances;
within each snapshot graph, identity resolution belongs to `m-snapshot-read`.

### Single owner

A unit of work has one owner. Sharing one across concurrent tasks is not a
supported access pattern; a Database Root may be shared, and a unit of work may
not.

## Abort

The attempt a unit of work coordinates either **commits** or **aborts** (rolls
back). A commit makes its writes durable and observable; an **abort discards
them entirely**. The
observable contract:

- A write performed inside a unit of work that aborts **MUST NOT** be observable
  after the abort — whether it was still **buffered** or had been
  **force-flushed** to serve a dependent read (read-your-own-writes). A find
  issued after the abort **MUST** re-resolve and observe the **pre-transaction**
  state.
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
  optimistic version / observed `in_z` a gated write binds (`m-concurrency`) is attached
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
  statement (*Collapse is a membership decision*), so several rows under one
  instruction denote several independent chains rather than one wider write. An implementation **MUST** refuse
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
write frontend decodes each non-null authored leaf with
`m-wire.decodeWire(member.neutralType, literal)`. Null is handled by the member's nullability
rule and is never passed to the Neutral Wire Codec. Recursive Value Object
members are traversed by declared structure; opaque Json content is converted as
one `Json` value and is not recursively inferred as neutral leaf types.

Wire failures map to `neutral-literal-type-mismatch`,
`neutral-literal-noncanonical`, or `neutral-literal-out-of-space`, with the
canonical member identity and document path. The previous
`write-value-type-mismatch` rule is retired for resolved scalar leaves. Unknown
members, wrong document carriers, multiplicity violations, missing required
members, nullability, and other structural failures retain their existing rules.

Every ingress crosses one admissibility judgment. It resolves the target first
and judges whether it admits the write. A target whose
family is ReadOnly admits none, and that refusal precedes every judgment below
(*Writes to a ReadOnly family*). A
predicate-selected write then refuses a versioned or temporal target
(`set-based-write-target-unsupported`, `m-batch-write`) before anything else is
judged. A keyed or target write is judged for applicability: a temporal
target refuses `delete`; the window must be stated as the verb's form requires,
admitted by the target's temporal profile, and ordered; a non-temporal target
refuses a milestone verb; and a temporal keyed instruction carries one row. Only
then is the payload judged — a keyed row's subtype shape, members, and values, or
a predicate-selected write's predicate, family refusal, and payload: an
amendment's every assignment member resolved, in authored order, before any
value is judged, and a replacement's row naming declared members only, then
completed and judged as every replacement is (*Source-authorized replacement*).
A keyed instruction's rows are judged one row at a time, so an instruction
carrying several is refused at its first refused row. Within a row its member
names — its subtype shape, then an authored framework-owned or an undeclared
member — are judged before any of its values. A keyed amendment's named
members are assignments, including in its `amendUntil` form. Assigning a
[framework-owned member](m-metamodel.md#attributes-and-primary-keys) — the optimistic-lock
version or an As-Of Axis endpoint — **MUST** be refused during preparation as
`framework-owned-member-assigned`, regardless of its value. This does not
refuse framework-computed values carried by internal Planned Rows or treat
`validFrom`, `until`, or target revision arguments as row assignments.
A complete row — an opening's
(`insert`, `insertUntil`) or a replacement's, keyed, target, or
predicate-selected — then has its values judged in declaration order, a missing
required member and an inadmissible value found in one pass and the first one
met refused. A partial row — an amendment's assignments, or the identity a
destructive write addresses — has its values judged in the order its author
states them, each assigned member's assignment rule before its value and the
members addressing the object after every assignment. A row is judged in that
order on every ingress, whatever order a complete row states its members in.
Serialized input is decoded as above; typed input applies
`m-core.coerceNeutralInput` followed by managed membership and retains
developer-facing mismatch errors. The policy follows from the ingress, never from
the runtime carrier a value arrives in.

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

A prepared write retains no authored scalar literal or unresolved instruction
field, and omission and nullable assignment stay distinct. A write keeps what its
verb received: mutating an authored input after the verb returns changes nothing
the write stores or selects. Whether a target write assigns, replaces, or
destroys follows from its mutation, never from its row.

### Writes to a ReadOnly family

A family's Persistence Mode states whether Parallax accepts persistence writes to
it (`m-descriptor`), and the effective mode is the root's, shared by every
position of the family (`m-inheritance`). A model-aware validator **MUST** refuse
every write whose resolved target's effective Persistence Mode is `ReadOnly`, with
the pre-SQL rule `read-only-write-target` (`m-case-format` *Rejected cases*). The
rule covers every keyed, target, and predicate-selected mutation, at a standalone
Entity, an abstract root, an abstract subtype, and a concrete subtype alike. It is
judged against the effective mode, never a local declaration, so a descendant that
declares nothing is refused when its root is `ReadOnly`.

The judgment follows target resolution and precedes every other judgment of the
write: a keyed or target write's applicability, row count, and revision
arguments, a predicate-selected write's readless-target, predicate, and family
refusals, and every payload rule, so no verb, window, revision, predicate, or
payload could make the write admissible and none is weighed. A target spelling
that names no Entity, or names one ambiguously, keeps its own refusal. Refusals
an ingress makes before a write reaches preparation — a source's shape,
provenance, or pin, or an argument parsed without the model — keep their order.
An empty amendment is judged like any other, so stating nothing never lets a
write to a ReadOnly family pass as eliminated work.

The refusal is a preparation refusal: nothing is buffered, no Read Evidence is
admitted, nothing pending is flushed, no SQL is issued for the write, and the
attempt is not doomed. A caller that catches it may keep writing and commit what
it buffered before and after. Reads of a ReadOnly family are unaffected, and
stored state for one is established outside modeled execution.

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
attempt** attaches beside that provenance, by which a later write finds what that
read observed. Read Evidence is an implementation-private selector for evidence;
it is not itself a State Observation, a lock, a database gate, or write authority,
and a value carrying it must still satisfy the Effective Concurrency Strategy's
evidence rule. A standalone read and a read-only transaction attach none: they
collect no observation, participation, predecessor row, or raw document for a
write *Current-attempt source admission* would refuse anyway, and a value they
published is refused there for having no Read Evidence of the writing attempt.

Publication of diagnostic data is not source admission. A hydratable node
exposed inside a classified result root (`m-snapshot-read`) is treated as
**NotStored** by keyed amendment and replacement verbs: no valid managed read
source produced it for writing. This applies to every node in the classified
root's graph, including a node whose Entity State is also reached by
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
carried on the value, held in an implementation-owned
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

An **insertion-authorized write** is a write of an object this unit of work
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
under Locking, the shared lock it holds (*What licenses a Locking write*); under
Optimistic, the observation the gate binds (`m-concurrency` *What each strategy
promises*) — and evidence that reaches no state this attempt still protects is
refused, as a write-evidence failure tagged **`write-evidence-consumed`**, as
*Observation ownership and lifetime* states.

Admission precedes the empty amendment's elimination: an amendment that assigns
nothing is dropped only once its source is admitted, so stating nothing never
lets an ineligible source pass. Replay re-runs the callback's reads rather than
refreshing a captured value, so a value an earlier attempt published licenses
nothing in the attempt that replays it. A caller holding an earlier observation
states the revision it observed through a target write instead
(*Target writes*).

### Version values are framework-owned

The version a gate binds **MUST** be one this attempt authentically observed for
that row, under either strategy; under Locking that read is also what acquired
the shared lock, and under Optimistic the database gate remains the concurrency
authority. An implementation **MUST NOT** accept a caller-authored or
reconstructed version value as the gate or as the new version: the new version
is always computed from the observed one (`m-concurrency` *Version
arithmetic*). "Caller-driven" refers to conflict *handling* only, never to the
version *value*; a target write's stated revision is a precondition argument,
not a version value in a row (*Target writes*).

A keyed `UPDATE` or `DELETE` of a versioned row with no authentic observation is
a **read-before-write** error under either strategy, refused at settlement before
any DML: there is nothing from which to advance the version and, under
Optimistic, nothing to gate on. A `DELETE` writes no version, but still requires
the same evidence: current lock participation under Locking, or observed-version
evidence a read of the current attempt retained under Optimistic.

### What licenses a Locking write

An observation is mandatory for a gated *and* an ungated observation-requiring
write, and both strategies accept the same observation. The Locking strategy's
ungated write is licensed by the **shared read lock** the observing read took,
and it holds that lock on exactly the row it closes, because the two derive from
one value: the write's address is the milestone its own written value came
from, and the observation the address comes from is the record of the read that
locked that milestone (`m-write-plan` *State Observation*). There is no separate
license to check. A write whose value names a milestone this attempt never
observed is already refused under both strategies (*Current-attempt source
admission*), and a write over a view pinned at a finite Transaction-Time instant
is refused by the pin rule (`m-temporal-write`) before any planning.

The invariant is therefore a property of how the close is constructed rather
than a precondition validated on the input side. Nothing about the *read* that
produced an observation survives into it: two reads at different as-of
coordinates that resolve to one milestone produce one indistinguishable piece
of evidence, so no observation of a milestone can be less licensing than
another observation of that same milestone.

### What a locking read observes

Every observation a locking read returns **MUST** describe the physical row
state protected by its lock: payload, revision evidence, and continuation
coordinates remain coherent even when the locking read waits behind an updater.
This requirement also holds at Read Committed; safe observed writes do not
require a stable transaction snapshot. Read Committed may change result
membership between statements or streaming batches. A row that ceases to qualify
may be excluded, including a temporal milestone whose concurrent close changes
its physical key, without discovering its successor in the same statement.
Repeatable Read provides a stable transaction snapshot; a conflicting
modification follows the serialization-failure and whole-attempt retry rules
(`m-auto-retry`).

### What one temporal observation locks

A lock is taken on the **physical rows the read selected** — nothing wider. For a
temporal entity this bears repeating, because the vocabulary invites a stronger
reading than the lock supports: locking the current milestone a read selected
does **not** lock the milestone chain's edge, the Provenance Lineage behind it,
every row sharing that primary key, or every Valid-Time rectangle current at the
same Transaction Time. Exactly one physical row per selected milestone is locked.

Two consequences follow, and `m-write-plan`'s State Observation vocabulary depends
on both:

- A mutation that can change **several** current rectangles of one key must
  resolve and observe **every** rectangle it can change, materializing per row.
  Observing one rectangle licenses closing that rectangle alone. An observed
  keyed write whose requested extent reaches rectangles no read of it observed
  therefore reads them inside the flush before changing them (`m-temporal-write`
  *Observed writes span their requested extent*), and under Locking that read
  takes this same shared lock on every row it selects.
- A temporal observation names **one milestone** and records nothing about the
  read that produced it, so what it says about lock scope is exactly what this
  section says: the read locked that one row, the row a Locking write closes
  (*What licenses a Locking write*). A read at a **historical** Transaction-Time
  coordinate locks a historical row and observes the milestone it actually
  selected, which no current-milestone close addresses; a write over a view so
  pinned is refused by the Transaction-Time pin rule (`m-temporal-write`) rather
  than by any lock-scope claim. A finite **Valid-Time** pin may still select a
  current Transaction-Time row and so remains writable.

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

The replacement intent belongs to the verb, so it survives every admitted write
and composition a write travels through — an observed, insertion-authorized, or
target write, and the composition of a pending insertion — whatever
authorized it. On a Bitemporal object a replacement establishes its state over
its whole window: rows it reaches take the completed state, and every part of
the window no current row covers opens with it (`m-temporal-write` *Observed
writes span their requested extent*). Authority comes first: a source whose
evidence or insertion authority fails opens nothing, so a replacement is never
an upsert, and existing-row proofs still do not coordinate concurrent creation
inside a gap: storage refuses an overlap where the table carries the exclusion,
and elsewhere it can be left as invalid overlapping coverage (`m-temporal-write`
*Concurrent creation in gaps*).

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
through planning, so a missing or revised target is its caller's failed
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
  read of the stored row under the shared lock (*Row acquisition*) that executes no
  pending write and publishes nothing. The stated revision is compared with the
  row that acquisition holds; a row standing at another revision, or no row, is
  a failed precondition refused at the call, leaving the pending writes as they
  were, and more than one row is Cardinality Corruption. The write itself is
  ungated. A temporal target's state is the milestone its stated start and its
  `validFrom` name, so a live read hits only where `validFrom` is that
  milestone's own Valid-Time start; a pending write of the object over exactly
  the same window, which admission required to start from the same state,
  always stands in, while one over a disjoint window starts elsewhere and does
  not. A live read is a stand-in an implementation **MAY** use and need not:
  where none stands in, whether its values are gone or the implementation
  acquires regardless, the acquisition runs, so a Locking target write's Database
  Call count can vary with whether a source is still live.

  The acquisition's cardinality is decided before any row it returned is
  judged. Once its read has executed and its rows are assembled, more than one
  row is Cardinality Corruption naming the exact count, raised after the read
  completes and without judging any of those rows' stored data, so an invalid
  row among them is never what the caller observes instead. No row needs no
  judgement either. Only a unique row is judged — invalid stored data in it is
  refused as any read refuses it (`m-read-delivery` *Invalid stored data*) —
  and its stored revision then decides the precondition. A failure executing the
  read or assembling its rows still precedes the count.

  A Non-Temporal target's acquisition judges no Value Object occurrence: what it
  establishes is the row's presence and revision.

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
one **row acquisition** port this module declares; the execution runtime
implements it (`m-execution` *Row acquisition*):

| Request | What it reads | When |
|---|---|---|
| **Target** | the one row a Locking target write addresses, at `validFrom` for a Bitemporal target, when no pending write proves it and no live read stands in; a temporal one whole, retained with the write | when the write is buffered, with no force-flush |
| **Coverage** | the current milestones of one or several objects overlapping the parts of each object's window no row it holds covers, in statements naming a bounded number of object/part terms each | when the flush reaches the deferred settled write, inside that flush; within an acquisition span, between the span's first write's turn and each write's own (*Shared coverage acquisition*) |
| **Completion** | nothing: the retained rows of a deferred settled write that are still current, each occurrence the target read left pending judged as a read judges it | when the flush reaches that write, or the first write of its acquisition span, before any of the span's coverage is read |

Where a write reads nothing, it acquires nothing: a predicate write is readless
(`m-batch-write`).

A target read exists only under Locking and always takes the lock. A coverage
read takes it exactly when its range is ungated, the other half of the gate
decision settlement made for that range.

## Write finalization

### The Write Planner

One **Write Planner** turns a flush's buffered intent into finalized semantic
steps, for one accepted Metamodel. Planning issues no statement and reads no row,
and reaches the clock only through the attempt's lazy Transaction Instant.

**Attempt Ownership** is what the attempt's own successful settled writes opened
(*Rows the attempt opened*) and left for its temporal sources (*Observation
ownership and lifetime*). Planning reads it to decide what a temporal mutation
does to its predecessor and which of its sources continue; it never changes it.

The resulting **Write Plan** is execution-ordered, and its settled writes carry
the source evidence of **every** write admitted against
existing state — a write coalesced into another, superseded, or overwritten by a
later composed assignment included (*Observed-State Coalescing*). A write keeps
its source condition whatever happens to its values, so a settled write whose
surviving assignment came from one source still carries every source composed
into it, even when it emits no statement, and each such source stays live until
that settled write completes. Work that stated nothing against existing state —
folded into a pending insert, cancelled against one, or an amendment assigning
no member — carries no source.

A predicate-selected write is planned apart, as the one Planned Step its readless
statement executes as — unversioned, expecting any count, an update decorated once
by the configured audit — and publishes no settled write, completion, or Write
Group.

A buffered write against existing state settles against the observation resolved
from the value it was authored from; planning never searches for one.

Every flush of a unit of work plans under the accepted Metamodel that unit opened
with, and a joining invocation plans under the unit it joined. A re-executed
attempt opens a fresh unit of work and may adopt another accepted Metamodel.

The term **step** is reserved for one logical Planned Step.

### The planning pipeline

How planning is staged is private. Coalescing happens as each write is admitted
(*Same-transaction write coalescing*). **Write Settlement** is the part of
planning that turns the ordered surviving writes into Planned Steps, validating
each write's observation as it settles that write. These orderings are normative:

- **Coalescing and no-op elimination precede time.** Work that cancels or nets to
  zero never consults the Clock Strategy.
- **Observation validation precedes gate rendering.** A required observation that
  a surviving write lacks is a planning error, never a value that reaches
  lowering. A gate binds evidence about the row its write addresses, never about
  another.
- **Temporal expansion follows ordering.** A surviving temporal mutation stays one
  indivisible write through batching and ordering and expands at its
  already-decided position (ADR 0045), so its own steps hold its closes ahead of
  its successors. In a Write Group of several settled writes, other objects' steps
  may also come between them.
- **Audit follows topology and precedes realization and lowering.** Audit
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

### Write Plan and Planned Steps

A **Write Plan** is the execution-ordered result of planning one flush: its Write
Groups, its deferred settled writes, and every Planned Step that survives
coalescing, cancellation, and known no-op elimination, with temporal topology and
correctness semantics already decided. Complete cancellation or no-op elimination
leaves nothing to execute.

A **deferred settled write** is the one exception to fully expanded topology. A
temporal object's observed writes whose requested Valid-Time range reaches
current coverage no planning input observed (`m-temporal-write` *Observed writes
span their requested extent*) finalize to their meaning — the composed
assignments over that range, the source conditions, and the resolved instant —
together with the one coverage read that range needs. Such a settled write
carries no planned step. By the time the flush reaches
it, the unit of work has acquired the object's current rows over the range not
already covered (*Row acquisition*) — at that turn, or earlier through its
acquisition span's shared reads (*Shared coverage acquisition*), inside the
flush either way and under the shared lock when the effective
strategy is Locking — and at its group's turn it binds those rows, or the
absence of any, with the observed ones into the write's physical steps, before
any step of the Write Group it runs in executes. Temporal meaning,
concurrency, and gates are fixed when planning returns, and binding never
recaptures the instant or consults the model: only the physical enumeration
waits, for the rows read and for the Attempt Ownership and source continuation
every earlier Write Group published.
Binding audits each row it produces and each close it emits once, as audit
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
*Concurrent creation in gaps*). Each caller's start holds
only where a current row stands at the stated start, literally; any other
caller's start is a failed precondition.

Each settled write — one keyed write with its expanded temporal topology, or
one batch — retains its own completion facts, produced values like its steps,
and executes in exactly one Write Group: the plan's group holding it, or, for a
deferred settled write, the group its binding forms.

### Write Group formation

A **Write Group** is a run of settled writes that execute and complete together.
Which writes share one is the implementation's, within these rules:

- Inserts, then updates, then deletes run as **mutation phases**, in referential
  order, and an insert that must follow the removal clearing its way runs after
  that removal. No group spans two phases.
- No group holds two writes of one object under its Inheritance Family's primary
  key, so a later write of an object observes the completion of the earlier. A
  write whose key the database allocates, or which names no complete key, runs
  alone.
- Within a group every effect — each step that is not an insert — precedes every
  insert, and each write's own steps keep their order.
- On a dialect with array parameters, keyed effects of distinct objects in one
  group that share a step kind, Entity, key, assigned members, gate kind, and
  As-Of Axis ends apply as one grouped effect (`m-sql` *Grouped effects*), each
  enforced against its own count, unless a write's own step order or an effect
  keeping its authored place separates them.
- An effect advancing a registry (`m-pk-gen`), or assigning a member of a unique
  key other than the primary key, an As-Of Axis end excepted, keeps its authored
  place, since a unique value one object hands another must be released in
  authored order.

A group's size is bounded, and no smaller than an acquisition span's bound
(*Shared coverage acquisition*), so a group's inserts wait behind the non-insert
steps of a bounded number of settled writes, however many the flush holds. Within
that bound, writes of distinct objects adjacent in one phase, or separated only by
writes with no step, share a group wherever that lets their effects apply as one
grouped effect or their inserts join one statement
(`m-sql` *Batched insert / update*). Writes that another write's steps separate
need not share one, so the statement count of a flush interleaving unlike writes is
the implementation's. Above the bound, like effects split across groups, so a
flush's statement count there is the implementation's too.

Beyond these rules, the order of effects of distinct objects is not promised.

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

Once a settled write completes, every later write and read of the attempt is
judged against what it changed: the observations it invalidated, the sources it
advanced, continued, or ended (*Observation ownership and lifetime*), and the rows
the attempt owns (*Rows the attempt opened*). A deferred write binds against every
completion earlier groups published.

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
A row removed and reopened at one physical address remains owned, and an insertion
whose last tagged row the settled write removed still stands when a row the
settled write opened is tagged with it. A failed group, or a group one of whose
writes did not bind, dooms the attempt (*Abort*).
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
releases them all.

### Shared coverage acquisition

An **acquisition span** is a bounded run of at least two consecutive plan entries,
each one deferred settled write of a Bitemporal Entity that names its
one complete Object Key, a key the database does not allocate. Its writes belong
to one mutation phase, target one concrete Entity — so one key attribute and one
member selection — and either all take the shared lock their coverage read
takes under Locking or none do. Each names an object no earlier write of the
span names under its Inheritance Family's primary key. A span never skips an
entry: any Write Group, a deferred write of another Entity or lock requirement,
a repeated object, a phase boundary, or the bound, which is the implementation's,
ends it, and the next eligible write may start another. A deferred write outside
any span, a Transaction-Time-Only one included, acquires its coverage alone at its
turn and executes as a Write Group of its own.

A span grants acquisition permission; its execution groups follow readiness.
Whenever the span's first remaining write is ready, the unit of work binds it
and each consecutive ready write after it, up to the first that is not, as one
Write Group under *Write Group formation*'s rules; it executes
and completes that group before binding any later write or reading any further
statement (*Write Groups complete before later work runs*). No statement is read,
and no ready group delayed, to enlarge a group. Each write binds against
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
  statement selects, nothing wider (*What one temporal observation locks*), when
  that statement runs.
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
  its writes and precedes every statement the span would read after it. No
  waiting write binds or executes after any failure. Classification, retry eligibility, and rollback are the
  encountered failure's own (`m-db-error`, `m-auto-retry`); because which of two
  independent failures is encountered can differ from acquisition, binding, and
  execution at each write's own turn, so can they.

Each shared statement is one read Database Call of the enclosing flush; the
flush adds no activity, call, or record per span, per group, or per write for
it (`m-execution-lifecycle`).

## Planned Steps and State Observations

`m-write-plan` owns what a Planned Step means — Row Origin and Close Cause,
planned rows and assignments, the Write Target, the Write Gate and its
concurrency decision, and the Affected Rows Policy — and the State Observation
vocabulary: the Object Key and Object State Key that address evidence, and
the Predecessor Row a Temporal Observation retains. This module settles
buffered writes into those steps, carries each observation to the write it
settles, and owns how long that evidence stays eligible.

### Observation ownership and lifetime

A retained observation belongs to the **source values that observed it**, not to
the transaction that ran the read. Only a value a read of the writing attempt
produced is eligible at all (*Current-attempt source admission*); among those,
eligibility follows the rules below.

These rules follow, and an implementation **MUST** exhibit all of them:

- **Eligibility follows the value.** An observation stays eligible while a live
  source value or a buffered write reaches it. Evidence no such value reaches is
  reclaimable before the attempt ends, on the runtime's own schedule rather than
  at a source-code boundary, so an attempt's retained evidence follows what its
  caller still holds.
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

A required observation that is missing is a **planning error**. No mode lets an
observation-requiring write proceed unobserved, under either Effective Concurrency
Strategy (`m-concurrency`).

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

### Empty updates issue no DML

An empty write issues **no DML** — zero Database Calls — under both strategies,
while a nonempty keyed amendment issues its `UPDATE` and advances the version
even when every value it writes equals the observed one. Neither an empty write
nor a temporal milestone kept unchanged needs to advance a version: a concurrent
editor that races it advances the version itself, so nothing slips through.

## Buffered, batched, ordered writes

At the unit-of-work boundary the buffered writes are flushed as **set-based** SQL
wherever possible:

- Multiple inserts or same-column updates of one entity become **one** Planned
  Step with several rows or keys, lowered as a single multi-row `INSERT` or a
  batched `UPDATE`. The canonical golden forms belong to `m-sql`.
- Operations are **ordered** so that a parent row is inserted before a child
  that references it (and deleted after), honoring foreign-key constraints.

Ordering is otherwise **unconstrained**. No buffered write is ordered against a
predicate-selected write: that write's one readless statement runs at its call,
after every write buffered before it, in a flush of its own (`m-batch-write`
*A predicate-selected write executes at its call*), and every write buffered
after it reaches a later flush. Each write is admitted as it always is, against
what the earlier flushes completed (*Observation ownership and lifetime*,
*Insertion authority*).

### Collapse is a membership decision

Batching is expressed by **membership in one Planned Step**, not by a marker on
several. Compatible inserts become one Planned Insert with several entries;
compatible uniform keyed updates or deletes become one Planned Update or Planned
Delete whose Key Target holds several key tuples.

- Two writes either share a step or they do not, and that is the whole of the
  decision.
- Execution grouping is a separate fact. A Write Group (`m-unit-work` *Write
  Group formation*) decides which settled writes execute and complete together,
  and execution may present their steps in shared calls (`m-execution`), but two
  writes of one group never share a step: membership in one step stays the
  planner's decision alone.
- Incompatible writes remain **separate logical steps**. In particular a
  **per-row gated** write (`m-concurrency`) can never join another: its gate binds
  one row's observed version, so each stays its own step even where a driver
  later transmits several in one batch.
- Membership does not change semantics. One multi-key Key Target owns **one
  aggregate** affected-row expectation for the rows it names (`m-unit-work`);
  collapsing writes together never weakens or discards that expectation.

### Set-based flush

- Multiple inserts of the same entity stating the same member set and
  generated-value shape collapse into a **single multi-row `INSERT`** rather than
  one statement per row, spelled in the dialect's multi-row insert form (`m-sql`
  *Batched insert / update*, `m-dialect`). Inserts differing in either stay
  separate steps.
- Multiple updates of the same entity that set the same columns collapse into a
  single statement over a membership of their keys when the new value is
  uniform across the keys. Otherwise each key stays its own step, and a dialect
  with array parameters applies the steps setting one member set as one grouped
  effect (`m-sql` *Grouped effects*), where a dialect without them runs one
  statement per key.
- Multiple deletes of the same **non-versioned** entity collapse into a **single
  `DELETE`** over a membership of their keys rather than one statement per row —
  the delete analogue of the multi-row `INSERT`. A **versioned** entity's
  deletes cannot collapse: each key stays its own step, under its own
  observation and exactly-one expectation, however its steps are then
  presented. A dialect with array parameters applies them as one grouped effect
  (`m-sql` *Grouped effects*), and a dialect without them runs one statement per
  key.
- A collapsed update or delete stays one step and one statement however many
  keys it holds. A dialect with array parameters binds its membership as one
  array per key Column, so its bind count follows its key Columns rather than
  its keys; a dialect without them binds one placeholder per key value (`m-sql`
  *Batched insert / update*).

The suite proves the batched forms against real data by applying the golden DML
and asserting the resulting table state (`m-case-format`).

The planner decides eligibility, statement identity, member-presence shape,
and whole-run value uniformity together, using the admitted writes and their
prepared rows. It removes known no-op writes first. Only adjacent compatible
single-row inserts and object-locked writes may collapse; observed-state writes,
insertion-authorized writes, caller-conditioned writes, and inserts dependent
on a prior removal are barriers. A same-shape update run with differing values
stays decomposed as a whole, without smaller uniform sub-batches. A collapsed
write retains row order, each addressed object, and every distinct source
evidence in first-occurrence order.

Temporal inserts and inserts with framework-generated primary keys remain
separate. Insert rows state their applicable member set before collapse;
updates compare present assigned values excluding the addressing key. Deletes
compare no non-key payload shape. Document presence remains a member-level
shape even when several members share one physical document column.

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
  removed from it reopens. Only a write the opening's own insertion authorized is
  an edit of it. A write that a read of the object's stored coverage authorized
  never composes with a pending opening of the same object: it changes the
  coverage that read observed, under that read's observation and evidence, as
  *Observed-State Coalescing* composes it, and the opening keeps its own
  coverage and edits. Nothing reconciles such a write with an opening whose
  coverage it reaches.
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
facts: what the target Entity's family settles against (`m-concurrency`) and the
write's own mutation. It answers for a write addressing **one** object, which is every write
a keyed verb authors. It has exactly three arms:

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
the one row the value it was handed names. An implementation **MUST** refuse
such an instruction whatever evidence its caller supplies. Without evidence,
neither a read nor an insertion's authority licenses it, so nothing admits it as
a write. Evidence supplied with it cannot travel with it: one observation is
evidence about **one** row, so the pairing is refused rather than the evidence
dropped.

That refusal is a judgment about the write's own admitted form, and both it and
the refusal of an arriving intent the buffer's existing claim cannot absorb are made
**before** the write is buffered, each leaving the claim ledger and the buffer as
it found them. An implementation **MUST NOT** record a write's claim before the
write has passed the admitted-form judgments that precede buffering: a caller
that catches such a refusal and continues in the same unit of work would otherwise
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
conditions are validated when the composition executes (`m-temporal-write`).

An incompatible intent is refused **synchronously at the verb**, before buffering
and before any database access, and the refusal is a write-evidence failure naming
the object it addressed, tagged **`write-evidence-already-claimed`**: what the
write would settle against is already claimed by pending work it cannot join. The
remedy is the ordinary one: a participating read force-flushes the buffered intent
and returns fresh state, which nothing claims.

A readless predicate write claims nothing: it observes no state and is never
buffered, and the flush it executes in ends every claim pending before it
(*Buffered, batched, ordered writes*).

Coalescing is witnessed from ordered buffered instructions (`m-case-format`
*Buffered keyed write instructions*), so an adapter exercises it from the
requested operations, never from the golden SQL.

## The Transaction Instant

Each outermost unit-of-work attempt owns exactly one **lazy** Transaction
Instant. Constructing it does **not** consult the Clock Strategy; the first
surviving write that needs a Transaction-Time boundary or an Audit Provenance
timestamp captures, normalizes, and memoizes it (ADR 0010).

The observable contract:

- An **empty** flush, a **canceled** buffer, a buffer that **coalesces away**,
  and a nonempty flush whose surviving work requires **no timestamp** all
  consult the Clock Strategy **zero** times.
- Every timestamp-requiring write in **one attempt** shares **one** instant,
  including across a forced read-your-own-writes flush and the commit flush, so
  temporal boundaries and audit values in that attempt are coherent.
- A **retry** is a new attempt with its own uncaptured lazy instant. It captures
  a **fresh** value only if it independently reaches timestamp-requiring work,
  and it never reuses the previous attempt's value.

The Transaction Instant is planning and flush context. It **MUST NOT** become a
durable Write Instruction field.

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
**MUST NOT** be read as ownership — clocks may repeat an instant across attempts
— and a row an earlier attempt committed at that instant is refused rather than
closed (*Closes the instant cannot follow*, below).

### Closes the instant cannot follow

A close of a row the attempt did not open is legal only at an instant strictly
later than that row's stored Transaction-Time start (`m-temporal-write` *A close
follows its predecessor's start*). A clock that repeats an instant across
attempts, a clock behind another writer's, or an instant captured early — a
forced flush captures it, and another transaction then commits a later version
that the attempt reads and changes — would otherwise store an empty or inverted
interval. Temporal expansion refuses such a close with a **Temporal Conflict
Error**, raised with:

- the Entity Identity and the attempt's Transaction Instant, always;
- the object's key, by declared attribute name, where the refusing path knows
  it;
- the stored Transaction-Time start the instant failed to follow, where the
  refusal compared one.

It retains no statement, plan, row, or payload. It is not a Write Effect Error,
whose payload is counts, and it is not a Write Precondition Error, because no
caller stated the start it compares; it is their standalone sibling, owned by
`m-temporal-write` and exposed beside them.

The comparison uses the predecessor expansion already holds, so it consults the
Clock Strategy no more often than the expansion itself does and reads nothing
else. Where it runs follows *The planning pipeline* and *Abort* without an
exception of its own: a predecessor planning holds is refused while planning, a
planning refusal that leaves the attempt usable and its writes buffered, so the
next flush plans and refuses them again at the same instant; a predecessor a
deferred range binds inside the flush is refused while that flush executes,
which dooms the attempt with the refusal as its first cause. Either way the
attempt cannot commit the refused write. The instant is never clamped or
replaced within an attempt: the Temporal Conflict Error is a recoverable
conflict, so the bounded retry loop replays it (`m-auto-retry`) as a new
attempt with its own lazy instant and fresh reads.

This guard protects closes alone. A new lineage still opens at the attempt's
instant without reading the key's closed history. Where the table carries the
exclusion (`m-storage-layout` *Temporal history constraints*), storage refuses
an opening that would overlap stored history, and the refusal is a recoverable
conflict the bounded retry loop replays at a fresh instant (`m-auto-retry`);
elsewhere such an opening, or concurrent creation inside a gap, can still store
an overlap (`m-temporal-write` *Concurrent creation in gaps*).

## Actor Identity

An **Actor Identity** is the closed identity projection of the Execution Actor
captured by the invoking Execution Scope (`m-execution-authority`): either the
stable, nonempty, opaque application Subject Identity or the actual nonempty
Database Login Identity.

An **audit-neutral** plan makes no use of it: an Actor Identity leaves no trace,
and two flushes differing only in Actor Identity emit identical SQL and binds.

Scope-time capture, propagation across joined scopes and retries, and verbatim
comparison belong to Execution Authority, not to this module.

## Affected-row enforcement

The unit of work owns the **authoritative** interpretation of every non-insert
execution result:

An execution result reports the driver's affected-row count; this module alone
says what it means. SQL lowering and database adapters **report** counts and never
classify them. Inserts expect nothing.

Enforcement raises the closed, module-owned **Write Effect Error** family, four
classifications:

```text
Missing Target | Stale Write
Optimistic Lock Conflict | Cardinality Corruption
```

Each classification reports the same facts — the Entity Identity, the Write
Target, the expected count, and the actual count — and **nothing else**: no SQL, statement index, driver exception, whole Planned Step,
assignments, or observation. That keeps the diagnostic stable across dialects and
lets `m-auto-retry` recognize the canonical Optimistic Lock Conflict Error over
its own edge to this module.

Classification follows the step's **gate**, never its verb. A **gated** shortfall
is the retriable Optimistic Lock Conflict Error. An **ungated** shortfall on a
write that still required a prior observation — a versioned keyed `UPDATE`, a
versioned keyed `DELETE`, or a milestone close — is the non-retriable Stale Write
Error: no gate could have caused it, so it is no detected lost update a re-read
could resolve. An implementation **MUST NOT** classify by verb: an
effective-Locking `UPDATE` whose shortfall surfaced as the retriable conflict
would be retried against an unchanged cause, since re-reading cannot supply a
gate the strategy never rendered.

A `FailedPrecondition` shortfall raises the **Write Precondition Error**
instead, carrying the Entity Identity, the object's key, and the revision the
caller stated — no count, because what failed is the caller's condition rather
than an effect (*Target writes*). It is the same error a Locking
submission raises when its acquisition finds the condition already false.

Retriability follows the classification, not the raising site: an Optimistic Lock
Conflict Error is a recoverable conflict the bounded retry loop replays
(`m-auto-retry`), while a Missing Target Error, a Stale Write Error, a
Cardinality Corruption Error, and a Write Precondition Error are **never**
retriable. A Temporal Conflict Error (*Closes the instant cannot follow*) is
owned by `m-temporal-write`, raised by temporal expansion rather than by
enforcement, exposed here beside the Write Effect Error family, and recoverable.
A statement a flush executes that the exclusion of the table it writes refuses
surfaces as the original database error; execution recognizes it as a
recoverable conflict (`m-auto-retry`), and it dooms the attempt like any other
flush failure.

### When several steps share a driver batch

Multiple `ExactCount` steps MAY share one driver batch **only** when the adapter
returns one affected-row count aligned with each logical step; the unit of work
then enforces each count against its own step. One **aggregate** count is
sufficient only for a single Planned Step whose own Key Target holds several
keys, because that one target owns the aggregate expectation. An aggregate-only
backend **MUST** execute distinct `ExactCount` steps separately; it MAY still
reuse statement preparation and stream bind rows. This is what preserves exact
attribution of a shortfall to the step that caused it.

A grouped effect (`m-execution`) is such a batch: the source ordinals it returns
give each of its steps its own count, a step whose ordinal is absent counting
zero.

Ordered write transport (`m-db-port`) is such a batch wherever its result
confirms a count for a step. A statement failure, confirmed non-execution, an
unconfirmed statement, and an interruption supply no count: the unit of work
interprets only confirmed counts, each against its own step and in step order,
and a failure or interruption propagates as itself (`m-execution`).

## Strategy selection — one preference, an effective strategy per Entity

An outer unit of work resolves one **Concurrency Preference**, `locking` or
`optimistic`, from its boundary options; an omitted preference, and a joining
boundary's, resolve as `m-execution` *Option resolution* states. The unit of
work reads each Entity's **Effective Concurrency Strategy** for that preference
from the accepted model's Concurrency Facet (`m-concurrency` *Strategy
derivation*), and applies it to its own state; it re-derives the strategy
nowhere.

An object read resolves the strategy of the Entity it materializes, and each
deep-fetch level resolves its own. The strategy also decides write evidence.
Both strategies require a read of the current attempt (*Current-attempt source
admission*): under Locking that read's participation proves the lock is held
(*What licenses a Locking write*), while under Optimistic the version or
milestone evidence it retained becomes the gate.

Write admission asks the same Facet what each keyed write settles against and
applies that answer to its own state — the participation its reads stamp, what
its completed writes left of the states its sources observed, and the claims
its buffer holds — and buffering is the one operation that admits a write's
claim and buffers the write, all or nothing. The Write Planner settles each
Planned Step's gate or explicit `Ungated` decision from the same strategy.

### The Isolation Level beside it — what the transaction READS

A unit of work resolves a second, independent boundary option: the **Isolation
Level** (`m-db-port`), which the port carries and each adapter maps. The two are
not alternatives and neither substitutes for the other. The Concurrency
Preference decides what a participating read LOCKS and what a write GATES on —
mechanisms `m-concurrency` defines and this module applies, per Entity. The
level decides what a read SEES, uniformly for the whole boundary, and is graded
by the anomalies it forbids:

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
lock and reads at the level (*What a locking read observes*).

An omitted level, and a joining boundary's, resolve as `m-execution` *Option
resolution* states: the boundary requests a concrete level on every attempt
rather than falling back to the adapter's own default (`m-db-port` *Mapping
obligations*), and a join never renegotiates the level its boundary opened at,
because an isolation is a property of a boundary only at the moment it opens.

## What the suite pins down

Each isolation scenario declares `when.uow.isolation` and holds TWO units of work
open at once, labelled `reader` and `writer`, so that what the reading one
observes is graded WHILE the writing one is live. Each closes with an ungrouped
find stating only what both engines have committed: what the level permits is not
what it requires, so no step may assert a phantom or a write skew.

A scenario's declared Database Call counts **MUST** be internally consistent with
the golden SQL it lists: each step's `databaseCalls` equals the number of golden SQL
statements that step emits. A scenario whose groups compose several submissions
into one flush is graded on the state it states instead, because the statements a
composed flush issues are the implementation's, within *Write Group formation*
(`m-case-format` *State-graded scenarios*). The harness asserts this consistency without ever
compiling a query to SQL — proving the Database Call contract from the fixture
itself — and executes the listed golden SQL against the real database to confirm
result-correctness.

Two contracts above are deliberately **not** witnessed by golden SQL, because no
emitted statement can carry them: how many times an attempt consulted the Clock
Strategy, and that an Actor Identity left no trace. Both are observable only
from inside an implementation, so each language target proves them in its own
suite — clock access through a counting Clock Strategy, and audit neutrality by
running one flush twice under different Actor Identities and comparing its SQL
and binds.
