# m-unit-work — Transactions & Unit of Work

`m-unit-work` is the transaction scope: the unit of work that **buffers,
finalizes, and flushes** writes, and the automatic read-correctness rules that
make in-transaction reads safe. It is expressed entirely in terms of **operations
and object state** (`m-op-algebra`): it depends on `m-op-algebra` and on the
execution port `m-db-port`, but **not** on `m-sql`. The dialect-specific SQL the
unit of work executes (the read-lock suffix, the set-based forms) is produced by
`m-sql` and run through the `m-db-port` execution seam at the composition root,
so `m-unit-work` takes no direct edge to SQL generation. (`m-op-list` and
`m-navigate` in turn depend on `m-unit-work`, because a list is an
operation-backed view resolved within a unit of work.)

Layered on the unit of work are four modules: the automatic shared read lock
(`m-read-lock`), bounded automatic retry (`m-auto-retry`), the transaction-scoped
identity map (`m-identity-map`), and the process-wide identity + query caches
(`m-process-cache`, deferred).

`m-unit-work` also owns **write finalization**: the Write Planner and its stage
order; the Planned Write algebra and the Write Target, Write Observation, Write
Gate, and Affected Rows Policy vocabulary it is built from; the neutral shortfall
tags; the authoritative affected-row enforcer; and the Write Effect Error family
that enforcer raises (ADR 0041, ADR 0048). Sibling policy modules
(`m-batch-write`, `m-opt-lock`, `m-read-lock`, `m-txtime-write`,
`m-bitemp-write`) keep their own policies and reach planning only through
strategy ports this module declares, which the composition root injects once.

## The unit of work

A **unit of work** (transaction) is the scope within which object reads and
writes are coherent. Within one unit of work:

- Writes are **buffered** as pending operations, not flushed eagerly. At the
  unit-of-work boundary they are **finalized** — combined, batched, and ordered
  to respect foreign-key constraints — then flushed in one pass.
- A read that depends on a not-yet-flushed write **MUST** observe that write: the
  unit of work flushes pending writes before serving a dependent read
  (read-your-own-writes), so a query never returns stale in-transaction state.

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

Every write a unit of work buffers — from any frontend, keyed or predicate-selected
— is a neutral **write instruction**, the write-side analogue of the operation
algebra. The canonical, language-neutral shapes are hosted in
[`write-instruction.schema.json`](../schemas/write-instruction.schema.json), mirroring
how `m-op-algebra` hosts `operation.schema.json`; `m-case-format` and
`m-conformance-adapter` reference that shape rather than redefining it. There are two:

- a **keyed** instruction — a `mutation` on one `entity` carrying the flat
  attribute-named neutral write input (`rows`);
- a **predicate-selected** instruction — a `mutation` on every row of a `target`
  (`entity` plus a bare `m-op-algebra` predicate) matching that predicate, with
  `assignments` on the update forms.

The embedded predicate is a canonical `m-op-algebra` node, legal vocabulary here
because `m-unit-work` already depends on `m-op-algebra` (the dependency-graph edge);
the write instruction is the sole place the write side reaches the algebra. Two
structural rules keep the instruction framework-honest:

- **The instant surface is dimension-explicit.** A Bitemporal write's authored
  Valid-Time lower bound is `validFrom`; bounded writes use `until` for the
  exclusive Valid-Time upper bound. The Transaction-Time instant is *not* an
  instruction field — it is supplied at flush from the Clock Strategy (ADR 0010),
  so no caller-facing shape can smuggle one in. Compatibility-case `at` is harness
  clock context, not an alias or an instruction member.
- **The transaction observation is not an instruction field.** The framework-owned
  optimistic version / observed `in_z` a gated write binds (`m-opt-lock`) is attached
  **per materialized row at flush**, never carried on the durable instruction: the
  reserved `observedVersion` / `observedTxStart` control keys are explicitly **forbidden**
  on a `write-instruction.schema.json` write row, so an observation cannot round-trip
  as instruction state — the structural guarantee that versions stay framework-owned
  (ADR 0013). They are flush-time context on the case format's materialization row.

A conforming implementation **MUST** round-trip every instruction through the
canonical form losslessly (`serialize(deserialize(x)) == x`), the write-side of the
`m-op-algebra` serde contract.

A Write Instruction is **buffered author intent** and stays that until flush. It
is never a Planned Write, and a Planned Write is never serialized back into one.

## Write finalization

### The Write Planner

One **Write Planner** turns a flush's buffered intent into finalized semantic
steps. It is model-scoped, constructed once per accepted Metamodel with its
immutable batching, concurrency, temporal, and provenance strategies already
wired, and it exposes exactly **one** planning operation:

```text
plan(
    PlanningRequest(
        subject_identity:     SubjectIdentity,
        transaction_instant:  TransactionInstant,
        concurrency:          Concurrency,
        buffered_writes:      BufferedWrites,
        observations:         Observations,
    )
) -> WritePlan
```

A caller **MUST NOT** be required — or able — to sequence coalescing,
cancellation, no-op elimination, observation binding, batching, dependency
ordering, Transaction Instant acquisition, temporal expansion, or provenance
decoration itself. Those are private stages, and no second public finalized or
decorated plan exists beside the Write Plan.

The planner is **stateless across calls**: it retains neither request nor result.
The operation is **pure** with respect to its inputs — it performs no database
I/O, consults no clock directly, and emits no SQL, dialect object, physical
column, or driver value.

The term **step** is reserved for one logical Planned Write; the term **stage**
describes one private transformation inside the pipeline below.

### The planning pipeline

The Write Planner privately owns this stage order:

```text
1. resolve identities and coalesce buffered intent
2. eliminate known cancellation and no-op work
3. bind and validate required observations
4. form compatible batches
5. dependency-order private units within barrier regions
6. resolve the Transaction Instant only if surviving work needs it
7. expand temporal topology in place
8. decorate provenance
9. freeze the Planned Steps
```

Four of those orderings are load-bearing and therefore normative:

- **Coalescing and no-op elimination precede time.** Stages 1–2 run before stage
  6, so work that cancels or nets to zero never consults the Clock Strategy.
- **Observation binding precedes gate rendering.** A required observation that is
  missing is a planning error raised at stage 3, never a value that reaches
  lowering.
- **Temporal expansion follows ordering.** A surviving temporal mutation stays
  one indivisible unit through stages 4–5 and expands at its already-decided
  position in stage 7 (ADR 0045), so its close and successors are adjacent and no
  unrelated step interleaves.
- **Provenance decoration follows topology and precedes lowering.** Stage 8
  consumes the finalized Insert Origins and Close Causes and adds ordinary
  planned values; it changes no topology, classifies no gate, and emits no SQL
  (ADR 0037).

Stages are otherwise private. The stage list is an ordering contract, not an
interface: nothing outside the planner may name, observe, or invoke a stage.

### Write Plan and Planned Steps

```text
WritePlan(steps: PlannedSteps)

PlannedSteps: an immutable ordered logical sequence of Planned Writes
```

A **Write Plan** is the immutable, **execution-ordered** result of one planning
call. Its Planned Steps contain every Planned Write that survives coalescing,
cancellation, and known no-op elimination, with temporal topology and correctness
semantics already decided.

- A Write Plan **MUST NOT** retain a Transaction Instant, a raw Write
  Observation, the transaction's concurrency mode, a Subject Identity, a strategy
  object, a barrier marker, a private group, or any other planning context.
  Derived values are materialized *into* the steps instead.
- An **empty** Planned Steps sequence is the one canonical result for complete
  cancellation or known no-op elimination. There is no empty-plan sentinel and no
  second result variant.
- Planned Steps is a **logical** sequence. An implementation MAY pack homogeneous
  runs and expose stable immutable views during iteration rather than allocating
  one container per step; every exposed view is immutable and stable, and equal
  views need not have object identity.

## The Planned Write algebra

A **Planned Write** is one finalized semantic execution step. It may address one
row or many, and its target, row topology, concurrency decision, and expected
effect are all settled before SQL lowering. The algebra is **closed**:

```text
PlannedWrite =
    PlannedInsert(entity, entries: NonEmpty[InsertEntry])
  | PlannedUpdate(entity, target, assignments, concurrency, affected_rows)
  | PlannedClose(entity, target, assignments, cause, concurrency, affected_rows)
  | PlannedDelete(entity, target, concurrency, affected_rows)
```

The algebra is **semantic and Attribute-keyed**. It contains no SQL, dialect
object, driver value, physical column name, property name, or SQL ordering.

- **Planned Insert** carries one or more insert entries. Every entry of one step
  has the same canonical member set and generated-value shape; incompatible
  entries form separate steps. Membership *is* the batching decision, so there is
  no batch flag and no group identifier. A Planned Insert carries no Write
  Target, no gate, and no Affected Rows Policy.
- **Planned Update** revises existing Non-Temporal rows in place. Its
  assignments are uniform across every row its target selects; differing per-key
  assignments remain distinct steps. A Milestone Target is prohibited — a
  temporal change expands into Planned Close plus Planned Insert successors and
  never survives as a Planned Update.
- **Planned Close** closes one current temporal milestone. Its assignments carry
  the Transaction-Time end. Its expected effect is always exactly one row.
- **Planned Delete** is physical row deletion. It carries no row, assignments,
  predecessor, Insert Origin, or Close Cause, and a Milestone Target is
  prohibited: represented-state absence is a Planned Close, not a delete.

### Insert Origin and Close Cause

```text
InsertOrigin =
    NewLineage
  | CarriedFrom(predecessor)
  | ChangedFrom(predecessor)

InsertEntry(row: PlannedRow, origin: InsertOrigin)

CloseCause = Superseded | Terminated
```

Origin belongs to **each insert entry**, never to the whole step and never to a
parallel array, so a multi-row insert whose rows have different origins keeps
that distinction. `NewLineage` begins a new Provenance Lineage; `CarriedFrom`
carries represented state unchanged from its predecessor; `ChangedFrom` changes
it. An update verb produces `Superseded`; a terminate verb produces `Terminated`
even when Bitemporal head or tail successors survive — those survivors are
independently `CarriedFrom`.

An implementation **MUST NOT** introduce a generic disposition field, a parallel
mutation-kind tag, or any free-floating label that a variant could contradict.
Insert Origin exists only on an insert entry and Close Cause only on a close, so
a termination cause on an inserted row and a lineage-start origin on a close are
**unrepresentable** rather than merely invalid. A Planned Update needs no label
either: *being* a Planned Update already carries the fact that an existing row
was revised in place. A Planned Delete removes the row and so has nothing to
label.

### Planned rows and assignments

```text
PlannedValue = NeutralValue | Null | GeneratedValueExpression

PlannedRow(
    attributes:    AttributeIdentity     -> PlannedValue,
    value_objects: ValueObjectIdentity   -> StructuredOccurrence | Null,
)

PlannedAssignments(
    attributes:    AttributeIdentity     -> PlannedValue,
    value_objects: ValueObjectIdentity   -> StructuredOccurrence | Null,
)
```

A **Planned Row** is the immutable, duplicate-free complete semantic contents of
one insert entry, including framework-owned version, temporal, and audit
attributes the planner derived. **Planned Assignments** is nonempty, immutable,
and duplicate-free, and unlike a Planned Row it names only the members its step
changes. Entity Layout continues to decide physical `SET` and bind order
(`m-sql`).

A **Generated Value Expression** is the closed set of cell values the *database*
computes from the row being written rather than binding as a literal, and
`m-pk-gen` is its only source: the `max` allocation an insert folds into its own
statement, and the registry advance an update applies to the stored value. Each
is legal only where the statement that renders it can express it, so a Planned
Row and Planned Assignments admit different members of the set rather than
different value vocabularies. What neither admits is an **authored assignment
expression** — anything a caller composes out of the operation algebra — because
the planner resolves every caller-supplied value before a step is settled.

### Write Target

```text
WriteTarget = KeyTarget | PredicateTarget | MilestoneTarget
```

A **Write Target** is the semantic row selection of a Planned Write. It is
distinct from observed predecessor state and from any concurrency condition.

```text
KeyTarget(
    key_attributes: NonEmpty[AttributeIdentity],
    key_values:     NonEmpty[complete concrete non-null value tuples],
)

PredicateTarget(predicate: Predicate)

MilestoneTarget(
    key_attributes: NonEmpty[AttributeIdentity],
    key_values:     one complete value tuple,
    end_attributes: NonEmpty[AttributeIdentity],
    end_values:     NonEmpty[TemporalUpperBound],
)

TemporalUpperBound = Finite(Instant) | Infinity
```

- A **Key Target** stores the canonical primary-key shape once and one aligned
  value tuple per addressed row, in planner order. Every tuple is complete,
  concrete, non-null, and **distinct**: repeated authored keys are invalid rather
  than silently deduplicated. A singleton and a compatible multi-key selection
  are cardinalities of one target kind, not two — there is no separate key-set
  target.
- A **Predicate Target** is legal only for a **readless** unversioned
  Non-Temporal Planned Update or Planned Delete. It carries the typed predicate
  and nothing else — no materialized keys, observation, pin, concurrency data, or
  barrier flag — because the enclosing step owns the Entity Identity, and its
  presence already implies `Unversioned`, `AnyCount`, and barrier behavior.
- A **Milestone Target** addresses the current milestone slot: one complete key
  tuple plus one write-required **exclusive upper bound per As-Of Axis** — the
  observed predecessor's Valid-Time end where that axis exists, and invariant
  `Infinity` for Transaction Time. It contains no axis start, gate, observation,
  or concurrency mode, and it is **identical in both concurrency modes**
  (ADR 0046). Only the gate differs.

### Write Observation

```text
WriteObservation =
    VersionObservation(observed_version)
  | TemporalObservation(predecessor, transaction_time_basis)

TransactionTimeBasis = LatestPinned | HistoricalPinned
```

A **Write Observation** is the database evidence a surviving write against
existing state retains. Transaction-Time-Only and Bitemporal entities have
**identical** observation requirements; the accepted Temporal Facet — not a
separate observation variant per temporal flavor — decides which topology
applies.

Absence is **structural**:

- inserts have no observation;
- unversioned Non-Temporal writes have no observation;
- versioned Non-Temporal updates and deletes require a Version Observation; and
- every temporal close requires a Temporal Observation.

A required observation that is missing is a **planning error**. An implementation
**MUST NOT** define a `NoObservation` value, a nullable observation that flows
downstream, or a mode in which an observation-requiring write proceeds unobserved
— the requirement holds in **both** concurrency modes (`m-opt-lock`).

A **Predecessor Row** is the complete, immutable persisted state a Temporal
Observation retains: every applicable scalar Attribute value, every complete
Value Object occurrence, the complete primary key, every temporal bound, and
every audit value, with no generated-value expression. Completeness is required
because temporal expansion carries members the authored mutation never mentioned,
and because a decorator must distinguish carried from changed state without a
second read (ADR 0042). Successors retain or view that state rather than copying
it, and bulk materialization MAY expose a logical Predecessor Row view over
columnar storage instead of allocating one row object per observation.

Under Relational Document Layout a Predecessor Row additionally retains the
**raw Structured Column document**, as a distinct named field beside its member
state and never as an entry in it. The compact columnar form carries the same
value as an aligned raw-document column beside its decoded Attribute and Value
Object columns, so a logical Predecessor Row view over columnar storage exposes
the raw document without allocating a second per-row carrier.

The field is **absent — not empty — under Columns layout**, so its presence is
itself the signal that the row came from a document-mapped Table. It is not a
member: the member map stays purely logical, and a consumer that iterates
members can never surface the raw document as a result field or an Entity
member.

Retention costs no additional query. A temporal write already materializes its
predecessor to obtain the key, milestone bounds, complete state, and concurrency
basis; the resolving read projects the Structured Column for that observation
anyway, and this rule says only that the observation path carries the value
forward instead of discarding it once known members are decoded.

The successor is then built by patching that retained document
(`m-document-codec`) rather than by re-encoding decoded members. That is what
preserves keys a newer application version wrote: an application that predates a
key it never declares still carries that key across a close-and-insert. An
explicitly assigned `one` occurrence follows the same rule recursively: it
patches only the declared members its authored document names. An omitted
nullable member remains stored, an explicitly null occurrence stores JSON null,
and a key no member declares is untouched. A `many` assignment replaces its
ordered array whole because its elements have no identity by which to merge.

The **Transaction-Time Basis** records only whether the read licenses an ungated
locking-mode write. It is not a claim about lock scope (`m-read-lock`).

### Comparing an assigned member with its persisted value

Wherever this module compares an assigned member with the value a read observed —
the write-input comparison of a Materialized Write Group below, and the no-op
elimination that precedes planning — the comparison follows the member's kind,
and does so identically under either Storage Layout. These are the structural
equality rules those steps name.

A **scalar** member compares as one logical value with the two not-present forms
collapsed: an absent Document Path and a JSON null at that path are the same
observed null (`m-document-codec` keeps them distinct and leaves this collapse to
its consumer, which is this rule). Assigning null to a member whose key is absent
is therefore a no-op — it issues no DML, advances no version, and consults no
clock — exactly as assigning null to an already-null Column is.

A **whole Value Object occurrence** compares through `m-document-codec`'s one
declared-member reduction: recursively for a `one` and element-wise in stored
order for a `many`. A key no member declares takes no part on either side. A
`one` member omitted by the authored document takes no part either, because the
assignment leaves it untouched. An occurrence that differs only in undeclared
keys is therefore equal, matching the mutation's observable effect. Key order
and insignificant whitespace never make two otherwise equal documents differ.

### Write Gate and the concurrency decision

```text
VersionGate(attribute: AttributeIdentity, observed_version: PositiveInt)
TemporalGate(start_attribute: AttributeIdentity, observed_start: Instant)
Ungated

NonTemporalConcurrency =
    Unversioned
  | Versioned(VersionGate | Ungated)
```

A **Write Gate** carries only the extra equality predicate lowering renders. The
advanced version value and the close instant are **assignments**, not gate
members, and a gate repeats neither the full observation nor the transaction's
concurrency mode — both are consumed during planning and do not survive in the
plan.

Planned Update and Planned Delete carry a Non-Temporal Concurrency decision;
Planned Close carries `TemporalGate | Ungated` directly, because every close
requires a temporal observation and so has no unversioned case. Locking mode
records an **explicit** `Ungated` decision rather than a null gate, which is what
makes gate applicability structural. The gate rule itself is uniform across
update, delete, and close and belongs to `m-opt-lock`.

A Version Gate requires a **singleton** Key Target, because each observed version
belongs to exactly one row.

### Affected Rows Policy

```text
Shortfall = MissingTarget | StaleWrite | OptimisticConflict

AffectedRows =
    AnyCount
  | ExactCount(expected: PositiveInt, on_shortfall: Shortfall)
```

Every surviving non-insert step carries a **fully resolved** Affected Rows
Policy before lowering. The **target** decides the expected cardinality and the
**concurrency decision** decides the shortfall classification (ADR 0044):

| Target | Policy |
|---|---|
| Predicate Target | `AnyCount` |
| Key Target | `ExactCount(number of keys, …)` |
| Milestone Target | `ExactCount(1, …)` |

- a **gated** shortfall is `OptimisticConflict`;
- an **ungated observation-requiring** shortfall is `StaleWrite`; and
- an **observation-free keyed** shortfall is `MissingTarget`.

An **excess** over any exact count is always Cardinality Corruption. It is an
invariant failure rather than a concurrency outcome, so it is not one of the
shortfall tags and is never carried in the policy payload. Planned Inserts carry
no Affected Rows Policy.

The tags are **neutral**: the plan names an outcome class, never a language's
exception type.

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
position nothing passes.

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
  `m-txtime-write`; a **bitemporal** insert-then-update opens a single fully-current
  rectangle with the final value — no inactivation / head-tail split, in contrast to
  the cross-transaction rectangle split of `m-bitemp-write`.
- **Insert-then-delete cancels.** A row inserted and then deleted in the same unit of
  work **cancels**: the two buffered writes annihilate and the flush emits **no** DML
  for that object — the net-zero effective-change-set elision, extended across two
  verbs.

Coalescing is a property of **one** unit of work; across two committed transactions
the milestone modules chain and split as usual. The rule is centralized here because
it is a buffering decision, not a per-verb one — the milestone modules
(`m-txtime-write`, `m-bitemp-write`) describe the durable cross-transaction shapes and
defer the same-transaction combination to this scope.

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
2. performs the resolving database read;
3. acquires the selected physical row locks when locking mode requires them
   (`m-read-lock`);
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
authored mutation, one shared primary-key shape, one immutable value column per
key attribute, and either an aligned version column or complete Predecessor
Columns with **one group-wide** Transaction-Time Basis. Every key and observation
column has the same positive row count.

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
  wrapper, no mixed Transaction-Time Basis, and no observation-free variant. An
  empty resolution produces no group.
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

## Subject Identity

A **Subject Identity** — the stable, nonempty, opaque string identifying the
Principal captured at the outer database operation boundary (ADR 0034) — is a
**required** planning input and the first field of the planning request. Its
value type is owned by this module, exactly as the Write Observation vocabulary
is, so a planning request is well-typed before any provenance behavior exists.

An **audit-neutral** plan makes no use of it. Until provenance decoration is
implemented, an implementation **MUST NOT** inspect, validate, retain, serialize,
persist, lower, or bind the supplied Subject Identity, and two planning calls
differing only in Subject Identity **MUST** produce equal Write Plans and
identical emitted SQL and binds. Reserving the field now is what lets provenance
decoration later become an internal stage rather than an interface change.

Capture, propagation across joined scopes and retries, and verbatim comparison
belong to the Principal boundary, not to this module.

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

Retriability follows the classification, not the raising site: an Optimistic Lock
Conflict Error is retriable only under the unit of work's opt-in
(`m-auto-retry`), while a Missing Target Error, a Stale Write Error, and a
Cardinality Corruption Error are **never** retriable.

### When several steps share a driver batch

Multiple `ExactCount` steps MAY share one driver batch **only** when the adapter
returns one affected-row count aligned with each logical step; the unit of work
then enforces each count against its own step. One **aggregate** count is
sufficient only for a single Planned Write whose own Key Target holds several
keys, because that one target owns the aggregate expectation. An aggregate-only
backend **MUST** execute distinct `ExactCount` steps separately; it MAY still
reuse statement preparation and stream bind rows. This is what preserves exact
attribution of a shortfall to the step that caused it.

## Strategy selection — the per-unit-of-work participation mode

A unit of work selects, per transaction, **how** its read-then-writes are made
correct — mirroring Reladomo's `TxParticipationMode`. Two strategies:

- **`locking`** (the **default**) — the automatic in-transaction shared read lock
  (`m-read-lock`). Reads take a row lock, and every observation-requiring write
  records the explicit `Ungated` decision.
- **`optimistic`** — the alternative (`m-opt-lock`): reads take **no** lock (so
  readers never block writers), and every observation-requiring keyed write
  carries the gate its observation supplies. Selected explicitly on the unit of
  work (`concurrency: optimistic`).

The mode is a property of the **unit of work**, not of the entity: the same
versioned entity is written under the shared lock in one workflow and under the
version gate in another. The metamodel only *names* the version column
(`m-descriptor`); opting into optimistic mode is what drops the read locks and
emits the gate. The mode is consumed **during** planning: it decides each step's
concurrency decision and never appears in the Write Plan itself.

## What the suite pins down

`m-unit-work`'s observable rules are expressed as **scenario** cases — ordered
operation steps, each with a declared round-trip count — and plain write cases:

| Case | What it proves |
|---|---|
| read-your-own-writes scenario | a buffered write is flushed before a dependent find observes it |
| rollback scenario | an aborted write is discarded; a post-abort find observes the original rows |
| fk-ordering / flush cases | buffered writes flush ordered by foreign-key dependency |
| insert-then-update coalescing (`m-unit-work-008`, `m-txtime-write-008`, `m-bitemp-write-014`) | a same-transaction insert-then-update flushes as one write with the final value — no intermediate milestone (non-temporal / Transaction-Time-Only / Bitemporal) |
| insert-then-delete cancellation (`m-unit-work-010`) | a same-transaction insert-then-delete cancels — the flush emits no DML for that object |

A scenario's declared round-trip counts **MUST** be internally consistent with
the golden SQL it lists: each step's `roundTrips` equals the number of golden SQL
statements that step emits. The harness asserts this consistency without ever
compiling an operation to SQL — proving the round-trip contract from the fixture
itself — and executes the listed golden SQL against the real database to confirm
result-correctness.

Two contracts above are deliberately **not** witnessed by golden SQL, because no
emitted statement can carry them: how many times an attempt consulted the Clock
Strategy, and that a Subject Identity left no trace. Both are observable only
from inside an implementation, so each language target proves them in its own
suite — clock access through a counting Clock Strategy, and audit neutrality by
planning one flush twice under different Subject Identities and comparing the
resulting Write Plans, SQL, and binds.
