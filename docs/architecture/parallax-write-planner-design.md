# Write Planner architecture

**Status:** Accepted for implementation

**Accepted:** 2026-07-29

**Scope:** COR-62; `m-unit-work` write finalization and its Python runtime
representation

## Purpose

Parallax buffers writes at a neutral semantic level, but the current Python
runtime carries too much unfinished meaning across the boundary into temporal
planning, concurrency handling, Audit Provenance, and SQL lowering. A raw write
instruction plus an optional observation is not a sufficient execution
contract: downstream code must still decide which row is targeted, whether a
gate applies, how many rows must be affected, how temporal state expands, and
what provenance disposition the write represents.

This design introduces one model-scoped Write Planner owned by Unit Work. It
turns the buffered intent and transaction observations for one flush into a
closed, ordered, immutable Write Plan. Ordinary lowering can then translate
each Planned Write without rediscovering semantic policy from raw inputs or
configured transaction mode.

The design has four equally important goals:

1. settle write meaning once, before SQL lowering;
2. preserve temporal, concurrency, cardinality, ordering, and provenance
   invariants in the type structure;
3. keep Unit Work independent of optional behavioral modules even when their
   policies participate at runtime; and
4. remain practical for very large materialized writes without building
   parallel per-row object graphs.

Parallax specifications remain authoritative. The ADRs linked throughout this
document record the decisions that refine those specifications. Reladomo is
used only as prior art, as required by the repository's
[research policy](../research/reladomo/00-index.md); its Java object model is
not a template for the implementation.

## Goals and non-goals

### Goals

- Give Unit Work one typed, pure planning entry point.
- Make every surviving write's target, assignments or row, concurrency
  decision, affected-row policy, temporal topology, and provenance disposition
  explicit before lowering.
- Represent absence structurally instead of with nullable observations or
  universal sentinel variants.
- Apply the same observation rules in locking and optimistic modes while
  varying only the resulting concurrency decision.
- Preserve read-your-own-writes, readless ordering barriers, relationship
  ordering, and temporal adjacency.
- Retain enough predecessor state to derive temporal successors and provenance
  without another database read.
- Let plans be inspected as immutable logical sequences while packing their
  physical Python representation into shared segments and columns.
- Give affected-row failures one Unit Work-owned classification and diagnostic
  payload.

### Non-goals

- The planner does not render SQL, choose physical columns, order binds, adapt
  driver values, or inspect a dialect.
- The planner does not perform database reads or acquire locks.
- The planner does not own Clock Strategy or capture wall-clock time directly.
- This work does not introduce a new behavioral module or deployable artifact.
- The first implementation does not spill plan data to disk.
- The design does not copy Reladomo's mutable transaction-operation hierarchy,
  portal model, cache behavior, or Java collection choices.
- Deferred mutation families such as recovery, purge, archiving, and increments
  remain outside the closed algebra until their specifications are accepted.

## Design principles

### Finalize semantics before lowering

SQL lowering should answer a physical question: how to express an already
settled Planned Write for one storage layout and dialect. It must not decide
whether a version predicate applies, infer a temporal target from predecessor
state, classify a row-count mismatch, or recover whether a close was
supersession or termination.

### Keep target, observation, and gate separate

These values answer different questions:

| Value | Question |
|---|---|
| Write Target | Which stored row or row set does the mutation address? |
| Write Observation | What persisted state did this transaction observe? |
| Write Gate | Which additional optimistic equality predicate detects a stale observation? |
| Affected Rows Policy | What execution count is valid, and what does a shortfall mean? |

Conflating them caused the previous temporal ambiguity: a Valid-Time upper bound
was sometimes treated as an optimistic predicate even though it is required to
identify the physical rectangle in both concurrency modes.

### Make invalid states structurally difficult

An insert has no observation. A readless unversioned predicate write has no
observation. A versioned or temporal mutation requires one. Locking mode does
not remove the observation requirement; it produces an explicit `Ungated`
decision after the observation's locking license is validated.

The algebra therefore has no `NoObservation`, nullable gate, or universal
`NoGate` value.

### Separate semantic values from storage representation

The semantic contract describes `PlannedWrite`, `KeyTarget`, `PredecessorRow`,
and related immutable values. The Python runtime may expose those values as
stable views over packed segments and columns. Code must not depend on an
eager tuple of independently allocated dataclass graphs.

## Vocabulary and lifecycle

The root [ubiquitous language](../../CONTEXT.md) is the canonical terminology.
The following sequence places the central terms in their lifecycle:

```text
Write Instruction
    + optional required Write Observation
    + transaction Concurrency mode
    + attempt-owned Transaction Instant
                  |
                  v
             Write Planner
                  |
                  v
 Write Plan { Planned Steps { Planned Write... } }
                  |
                  v
       ordinary SQL lowering and execution
```

- A **Write Instruction** is buffered author intent.
- A **Write Observation** is persisted evidence required for a surviving
  versioned or temporal mutation.
- A **Materialized Write Group** is the compact private result of resolving one
  observation-requiring predicate mutation before pure planning.
- A **Planned Write** is one finalized semantic execution step; it may address
  one row or multiple rows.
- **Planned Steps** is the immutable ordered logical sequence of those steps.
- A **Write Plan** is the possibly empty finalized handoff to lowering.

The term *step* is reserved for one logical Planned Write. The term *stage*
describes a private transformation inside the planning pipeline.

## Ownership and module direction

Unit Work owns:

- the Write Planner interface and pipeline order;
- the planned-write, target, gate, affected-row, and observation vocabulary;
- the neutral shortfall tags;
- the public Write Effect Error family; and
- the authoritative affected-row enforcer.

Optional modules own their policies. Batching decides collapse compatibility,
temporal modules decide successor topology, concurrency modules decide gates and
locking license, and Audit Provenance decides provenance attributes. They
implement Unit Work-owned strategy ports, which the composition root injects
once when constructing the planner.

```text
source dependencies

m-batch-write ------\
m-opt-lock ----------\
m-read-lock ----------> m-unit-work
m-txtime-write ------/
m-bitemp-write -----/
m-audit-provenance -/

runtime composition

composition root
    |
    +-- constructs WritePlanner(model, immutable strategy adapters)
    |
    +-- supplies planner to UnitOfWork
    |
    +-- connects finalized WritePlan to SQL lowering and the database port
```

The source arrows point from optional policy modules to the stable Unit Work
mechanism. Runtime calls may travel from the injected planner port to those
policies without creating a reverse import. In particular,
`m-opt-lock --> m-unit-work` is not inverted merely because the planner invokes
an optimistic-lock strategy at runtime.

Unit Work must not:

- import optional policy implementations;
- switch on their implementation classes;
- expose a composition-root staging callback;
- take SQL, dialect, driver, or database dependencies into planning; or
- allow the composition root to sequence private planning stages.

This direction is the decision in
[ADR 0041](../adr/0041-write-finalization-is-centralized-behind-a-typed-planner.md).

### Subject Identity ownership and the module catalog

Unit Work also owns the `SubjectIdentity` **value type** that
`PlanningRequest.subject_identity` is typed as, exactly as it already owns the
Write Observation vocabulary. `m-principal` owns the **behavior**: obtaining and
validating one Subject Identity at an outer database operation boundary,
propagating it through joined scopes and automatic retries, and comparing it
verbatim.

Splitting ownership that way means no `m-unit-work --> m-principal` edge is
required. [ADR 0037](../adr/0037-audit-provenance-decorates-finalized-neutral-write-plans.md)
declares that edge, and its amendment records this narrowing; the cycle-free
direction is unchanged, because identity enters planning as an already
normalized value and provenance decoration still consumes the finalized neutral
plan.

The consequence for COR-62 is concrete: it adds **no** module catalog row, **no**
`dependency-graph` fence edge, **no** slice claim, and **no** Python
`MODULE_SCOPE` entry. `m-principal` and `m-audit-provenance` stay undeclared
until the work that implements them declares them together with the fixtures the
catalog's coverage rule requires. A diff in `core/spec/modules.md`,
`core/spec/slices.md`, `languages/python/tools/check_dag_sync.py`, or the
generated contracts block in `languages/python/pyproject.toml` during this work
is therefore a signal that something crossed a boundary it should not have —
apart from support-scope membership changes inside `parallax.snapshot.handle`,
which move files between existing scopes without adding a module or an edge.

A later decision may re-home `SubjectIdentity` into `m-principal` once that
module exists. Nothing here forecloses it, and no temporary identity provider
port or compatibility overload is introduced in the meantime.

## Planner boundary

One Write Planner is constructed per connected Metamodel:

```text
WritePlanner(
    model,
    batching_strategy,
    concurrency_strategy,
    temporal_strategy,
    audit_strategy,
)

plan(
    PlanningRequest(
        subject_identity: SubjectIdentity,
        transaction_instant: TransactionInstant,
        concurrency: Concurrency,
        buffered_writes: BufferedWrites,
        observations: Observations,
    )
) -> WritePlan
```

The strategy names above are conceptual ports, not a required set of public
constructor parameters. The implementation may combine cohesive private ports,
but it must preserve the ownership and sequencing rules.

The first Python request is frozen, slotted, and keyword-only. Subject Identity
is its first required field, followed by the remaining attempt context and then
the flush data. This order emphasizes that planning occurs inside an already
established Principal boundary without making field order a positional API.
Only the normalized Subject Identity enters planning; the opaque application
Principal does not.

The planner is stateless across calls. It retains neither request nor result.
The operation is pure with respect to its inputs: it performs no database I/O,
does not capture a clock, and emits no SQL.

### Transaction Instant

Each outermost Unit Work attempt owns one lazy `TransactionInstant`:

```text
TransactionInstant(clock)

value() -> Instant
```

Construction does not consult the clock. The first surviving write that needs a
Transaction-Time boundary or Audit Provenance timestamp calls `value()`, which
captures, normalizes, and memoizes the instant. Every forced flush in that
attempt receives the same object. A retry is a new attempt and receives a new
instance.

Canceled, empty, read-only, and known net-zero work never consults the clock.
The planner depends on `TransactionInstant`, not on Clock Strategy. This
preserves [ADR 0010](../adr/0010-transaction-instants-come-from-clock-strategy.md)
while giving the planner lazy access to the one attempt-wide value.

Forced flushes reuse both the boundary-captured Subject Identity and the
attempt-owned Transaction Instant. An automatic retry retains the same outer
boundary Subject Identity but creates a new attempt-owned Transaction Instant.
Audit Provenance consumes Subject Identity during planning; it survives in
Write Plan only where decoration materializes it as an explicit planned audit
value. This preserves the boundary lifecycle in
[ADR 0034](../adr/0034-principal-is-required-at-every-database-operation-boundary.md).

## Planning inputs and observations

### Observation algebra

```text
WriteObservation =
    VersionObservation(
        observed_version: PositiveInt,
    )
  | TemporalObservation(
        predecessor: PredecessorRow,
        transaction_time_basis:
            LatestPinned | HistoricalPinned,
    )
```

Transaction-Time-only and Bitemporal entities have identical observation
requirements. The accepted Temporal Facet determines which topology applies;
duplicating observation variants by temporal flavor would repeat model truth.

Absence is structural:

- inserts have no observation;
- unversioned Non-Temporal writes have no observation;
- versioned Non-Temporal updates and deletes require `VersionObservation`; and
- every temporal close requires `TemporalObservation`.

A required observation that is missing is a planning error, not a
`NoObservation` value that may flow downstream.

### Complete predecessor state

A `PredecessorRow` contains the complete immutable persisted state applicable
to the observed temporal entity:

- every scalar Attribute value;
- every complete Value Object occurrence;
- the complete primary key;
- every temporal bound;
- every audit value; and
- no generated-value expression.

Successors retain or view this state instead of copying it. Complete state is
necessary because temporal expansion may carry fields the authored mutation did
not mention, and Audit Provenance must distinguish carried from changed state.
Identity plus temporal bounds would force another read or downstream
reconstruction.

The close also retains its authored cause:

```text
CloseCause = Superseded | Terminated
```

An update produces `Superseded`. A terminate verb produces `Terminated`, even
when Bitemporal head or tail successors survive. This preserves the distinction
required by [ADR 0042](../adr/0042-temporal-plans-retain-complete-predecessor-state-and-close-cause.md)
and [ADR 0037](../adr/0037-audit-provenance-decorates-finalized-neutral-write-plans.md).

### Transaction-Time Basis and lock scope

`LatestPinned | HistoricalPinned` is licensing metadata, not a description of
lock scope.

In locking mode, one temporal observation locks the selected current physical
milestone row. It does not lock an entire edge, lineage, primary key, or all
Valid-Time rectangles sharing that key. A mutation spanning multiple current
rectangles must materialize and observe every rectangle it can change.

A finite Valid-Time pin may still select a current Transaction-Time row and is
therefore compatible with locking. A historical Transaction-Time pin is not:
locking mode rejects `HistoricalPinned` before planning because that read did
not lock the current row the write must close. Optimistic mode may accept the
observation and let its gate detect that it is stale.

## Predicate writes and materialization

### Readless path

An unversioned Non-Temporal predicate update or delete can remain readless:

```text
PredicateTarget(predicate: Predicate)
```

The target contains only the typed predicate. Its enclosing Planned Write owns
the Entity Identity. The target repeats no keys, observation, pin, concurrency
mode, or barrier flag.

A Readless Write is an ordering barrier. The planner may coalesce, batch, and
dependency-order writes independently on either side, but no write may cross
the predicate operation because its exact read/write set is unknown. The
barrier is private planning structure and does not survive as a public wrapper.
See [ADR 0043](../adr/0043-readless-predicate-writes-are-ordering-barriers.md).

### Observation-requiring path

A versioned or temporal predicate write must resolve before the pure planner
call. Unit Work's write-input preparation:

1. force-flushes preceding writes when the read needs read-your-own-writes;
2. performs the resolving database read;
3. acquires the selected physical row locks when locking mode requires them;
4. for an assignment-bearing mutation, compares assigned members with their
   persisted values using Unit Work's structural equality rules;
5. records effective rows in database resolution order; and
6. produces no item when the result is empty or entirely no-op.

Delete and terminate mutations have no assignments to compare and therefore
retain every resolved row. Streaming comparison is the one narrow
result-dependent pre-planning normalization. It avoids retaining current-value
comparison columns merely so the pure planner can discard them later. The
planner continues to own every no-op decision possible from buffered planning
data.

One authored predicate becomes one compact private group:

```text
MaterializedWriteGroup(
    mutation,
    key_attributes,
    key_columns,
    observations:
        VersionColumns(versions)
      | TemporalColumns(
            predecessors: PredecessorColumns,
            transaction_time_basis:
                LatestPinned | HistoricalPinned,
        ),
)
```

`key_columns` contains one immutable column per canonical primary-key
attribute. Every key and observation value column has the same positive row
count.

`PredecessorColumns` stores complete predecessor state columnarly:

```text
PredecessorColumns(
    shape,
    attribute_columns,
    value_object_columns,
)
```

The one Transaction-Time pin used by the predicate read determines one
group-wide basis; mixed latest and historical rows are impossible. The group
therefore has no per-row basis column and no observation-free variant.

The group contains no managed Entity objects, composite-key tuple per selected
row, eager `PredecessorRow` object per selected row, or generic per-row planning
wrapper. It remains indivisible through batching and dependency ordering and
disappears during finalization.

## Finalized algebra

The following algebra is semantic. The Python representation may expose its
values as stable views over compact storage.

### Planned values and assignments

```text
GeneratedValueExpression =
    MaxPlusOne
  | SelfIncrement(amount)

PlannedValue =
    NeutralValue
  | Null
  | GeneratedValueExpression

PlannedRow(
    attributes: AttributeIdentity -> PlannedValue,
    value_objects:
        ValueObjectIdentity -> StructuredOccurrence | Null,
)
```

A Planned Row is immutable and duplicate-free. It is the complete semantic
contents of one insert entry. Framework-owned version, temporal, and audit
attributes may be present. Property names, physical columns, SQL order, dialect
objects, and driver values are prohibited.

```text
PlannedAssignments(
    attributes: AttributeIdentity -> PlannedValue,
    value_objects:
        ValueObjectIdentity -> StructuredOccurrence | Null,
)
```

Planned Assignments is nonempty, immutable, and duplicate-free. Unlike a
Planned Row, it names only the members its step changes. Entity Layout
continues to determine physical `SET` and bind order.

Each generated value is legal **only at the statement position that can express
it**, and each carrier refuses the other: a Planned Row admits `MaxPlusOne`,
which folds into the row an insert opens, and Planned Assignments admit
`SelfIncrement`, which the database computes from the very row an update
revises. Neither combination is representable, so no consumer needs a
position-aware re-check.

**Amendment (implementation, COR-62).** Planned Assignments originally excluded
generated-value expressions along with authored Assignment expressions. The
exclusion of authored Assignment expressions stands. The blanket exclusion of
generated values does not: `m-pk-gen`'s simulated sequence is a registry counter
advanced by an ordinary `update`, and the advance is a value the *database*
computes from the row being written — the same category as the `max` allocation
an insert folds in, and the same one-key marker vocabulary in the write
instruction schema. The non-goal above concerns a deferred *mutation family* —
an increment verb — which remains outside the algebra; the cell marker is not
one.

The first Python representation shares:

```text
AssignmentShape(
    attributes,
    value_objects,
)

PlannedAssignments(
    shape,
    attribute_values,
    value_object_values,
)
```

Shapes and complete uniform assignment values are reused across compatible
steps. Typed item iterators expose the mapping contract without making a
mutable mapping or third-party persistent map part of the design.

### Insert origins and close causes

```text
InsertOrigin =
    NewLineage
  | CarriedFrom(predecessor)
  | ChangedFrom(predecessor)

InsertEntry(
    row: PlannedRow,
    origin: InsertOrigin,
)

CloseCause = Superseded | Terminated
```

Origin belongs to each insert entry, not to the whole batch and not to a
parallel array. It is the provenance-neutral disposition Audit Provenance
consumes:

- `NewLineage` is a Lineage Start;
- `CarriedFrom` is a Carried-State Successor; and
- `ChangedFrom` is a Changed-State Successor.

A Planned Update implies In-Place Revision. `Superseded` implies Ordinary
Revision Close; `Terminated` implies State Termination. Planned Delete has no
row to decorate.

### Targets

```text
WriteTarget =
    KeyTarget
  | PredicateTarget
  | MilestoneTarget
```

#### Key Target

```text
KeyTarget(
    key_attributes: NonEmpty[AttributeIdentity],
    key_values:
        NonEmpty[tuple[NeutralValue, ...]],
)
```

The canonical primary-key shape is stored once. Every aligned value tuple is
complete, concrete, non-null, and distinct. Planner order is preserved.
Repeated authored keys are invalid rather than silently deduplicated.

Singleton and compatible multi-key forms are cardinalities of one target kind;
there is no separate Key Set Target. A Version Gate requires a singleton Key
Target because each observed version belongs to one row.

The logical row tuples do not require an eager physical tuple per row.
Materialized groups and Planned Steps may expose them as views over key columns.

#### Predicate Target

```text
PredicateTarget(
    predicate: Predicate,
)
```

This target is legal only for a readless unversioned Non-Temporal Planned
Update or Planned Delete. Its presence implies `Unversioned`, `AnyCount`, and
barrier behavior.

#### Milestone Target

```text
TemporalUpperBound =
    Finite(Instant)
  | Infinity

MilestoneTarget(
    key_attributes: NonEmpty[AttributeIdentity],
    key_values: tuple[NeutralValue, ...],
    end_attributes: NonEmpty[AttributeIdentity],
    end_values: NonEmpty[TemporalUpperBound],
)
```

The singular key tuple is complete. End attributes and values align one
write-required exclusive upper bound per canonical As-Of Axis:

- Valid Time uses the observed predecessor's `valid_end`; and
- Transaction Time always uses `Infinity`.

The target identifies the current temporal milestone slot independently of
concurrency mode. It contains no axis start, gate, observation, or mode.
This is [ADR 0046](../adr/0046-milestone-targets-use-axis-upper-bounds-independent-of-gates.md).

### Gates and concurrency

```text
VersionGate(
    attribute: AttributeIdentity,
    observed_version: PositiveInt,
)

TemporalGate(
    start_attribute: AttributeIdentity,
    observed_start: Instant,
)

Ungated
```

The gate carries only the extra equality predicate lowering needs. Advanced
version values and close instants belong in Planned Assignments. Full
observations and transaction mode are consumed during planning.

```text
NonTemporalConcurrency =
    Unversioned
  | Versioned(
        VersionGate | Ungated,
    )
```

Planned Updates and Planned Deletes carry `NonTemporalConcurrency`. Planned
Closes carry `TemporalGate | Ungated` directly because every close requires a
temporal observation.

The uniform rule is:

| Write | Optimistic mode | Locking mode |
|---|---|---|
| Versioned Non-Temporal update/delete | `VersionGate` | `Ungated` |
| Temporal close | `TemporalGate` | `Ungated` |
| Unversioned Non-Temporal write | `Unversioned` | `Unversioned` |

Locking mode deliberately removes the version predicate from versioned deletes
as well as updates. The observation remains mandatory; its shared row lock is
the concurrency mechanism. This intentional correction is recorded in
[ADR 0047](../adr/0047-concurrency-mode-determines-write-gates-uniformly.md).

### Affected rows

```text
Shortfall =
    MissingTarget
  | StaleWrite
  | OptimisticConflict

AffectedRows =
    AnyCount
  | ExactCount(
        expected: PositiveInt,
        on_shortfall: Shortfall,
    )
```

The target determines expected cardinality:

| Target | Policy |
|---|---|
| Predicate Target | `AnyCount` |
| Key Target | `ExactCount(number_of_keys, ...)` |
| Milestone Target | `ExactCount(1, ...)` |

Concurrency determines shortfall classification:

- a gated shortfall is `OptimisticConflict`;
- an ungated observation-requiring shortfall is `StaleWrite`; and
- an observation-free keyed shortfall is `MissingTarget`.

An excess over every Exact Count is always Cardinality Corruption. It is an
invariant failure, not an optimistic conflict, and is therefore not repeated in
the policy payload. Inserts do not carry an Affected Rows Policy.

This separation is defined by
[ADR 0044](../adr/0044-write-target-cardinality-governs-affected-row-validation.md).

### Planned Write variants

```text
PlannedWrite =
    PlannedInsert
  | PlannedUpdate
  | PlannedClose
  | PlannedDelete
```

```text
PlannedInsert(
    entity: EntityIdentity,
    entries: NonEmpty[InsertEntry],
)
```

Every entry in one Planned Insert has the same canonical member set and
generated-value shape. Incompatible entries form separate steps. Membership is
the batching decision, so there is no batch flag or group identifier.

```text
PlannedUpdate(
    entity: EntityIdentity,
    target: KeyTarget | PredicateTarget,
    assignments: PlannedAssignments,
    concurrency: NonTemporalConcurrency,
    affected_rows: AffectedRows,
)
```

Assignments are uniform for every row in the target. Different per-key
assignments remain different logical steps. A Milestone Target is prohibited;
temporal changes expand into Planned Close and Planned Insert.

```text
PlannedClose(
    entity: EntityIdentity,
    target: MilestoneTarget,
    assignments: PlannedAssignments,
    cause: Superseded | Terminated,
    concurrency: TemporalGate | Ungated,
    affected_rows: ExactCount,
)
```

The expected count is always one. Assignments include the Transaction-Time end
and, after Audit Provenance decoration, may include termination provenance only
for `Terminated`. Planned Close carries no Insert Origin or generic
disposition.

```text
PlannedDelete(
    entity: EntityIdentity,
    target: KeyTarget | PredicateTarget,
    concurrency: NonTemporalConcurrency,
    affected_rows: AffectedRows,
)
```

Planned Delete carries no row, assignments, predecessor, Insert Origin, or
Close Cause. Temporal absence is expressed as Planned Close, so Milestone
Target is prohibited.

### Write Plan

```text
WritePlan(
    steps: PlannedSteps,
)

PlannedSteps: immutable Sequence[PlannedWrite]
```

Write Plan retains no Transaction Instant, raw observation, transaction mode,
or other planning context. Derived instants and decisions have already been
materialized into its steps.

An empty Planned Steps sequence is the one canonical result for complete
cancellation or known no-op elimination. There is no empty-plan sentinel or
second result variant.

## Planning pipeline

The Write Planner privately owns this order:

```text
1. resolve identities and coalesce buffered intent
2. eliminate known cancellation and no-op work
3. bind and validate required observations
4. form compatible batches
5. dependency-order private atomic units within barrier regions
6. resolve Transaction Instant only if surviving work needs it
7. expand temporal topology in place
8. apply Audit Provenance decoration
9. freeze compact Planned Steps
```

### 1. Resolve and coalesce

Entity spellings and family-effective members resolve once against the connected
Metamodel. Same-attempt writes obey [ADR 0023](../adr/0023-same-transaction-writes-coalesce-in-the-unit-of-work.md):

- insert then update becomes one final-value Lineage Start; and
- insert then delete cancels completely.

A state never made durable to another reader does not manufacture history.

### 2. Eliminate known no-ops

Cancellation and effective-change checks run before time is requested. A
buffered assignment-bearing write whose resulting values are known to equal its
predecessor is skipped. Observation-requiring predicate materialization has
already filtered result-dependent no-op rows while streaming, so it does not
carry comparison-only columns into this stage. Readless predicate updates
cannot perform the check because doing so would require the read their semantics
intentionally avoid.

### 3. Bind observations

Every surviving versioned or temporal mutation receives the observation its
entity and verb require. Concurrency policy validates locking licenses and
derives the later gate decision. Raw observations remain available through
temporal expansion and provenance decoration but do not survive in Write Plan.

### 4. Form compatible batches

Compatible inserts and uniform unversioned keyed updates or deletes may become
multi-row Planned Writes. Per-row gated writes remain separate logical steps
even when a driver later executes them as a batch.

Batching shares shapes and uniform values. It does not deep-copy one assignment
payload per target.

### 5. Order private units

Relationship and inheritance-family dependencies determine legal write order.
Readless predicates partition the sequence into independent regions. A
materialized predicate group moves as one private unit. A surviving temporal
mutation also remains indivisible while its final position is chosen.

### 6. Resolve time lazily

Only after no-op elimination, batching, and ordering establish surviving
time-requiring work may the planner call `transaction_instant.value()`. This
prevents canceled work from consulting Clock Strategy and gives every temporal
boundary and audit stamp in the attempt the same value.

### 7. Expand temporal topology in place

At its already-decided position, one temporal mutation expands to:

```text
PlannedClose
PlannedInsert successor 1
PlannedInsert successor 2
PlannedInsert successor 3
```

There may be zero to three successors depending on verb, Temporal Facet, and
Valid-Time overlap. The close is first; successors follow immediately in the
facet's canonical semantic order. No unrelated step may interleave.

The private atomic wrapper then disappears. Adjacency in Planned Steps is
sufficient; no public group identifier survives. This is
[ADR 0045](../adr/0045-temporal-mutations-expand-in-place-after-ordering.md).

### 8. Decorate provenance

Audit Provenance consumes the finalized neutral dispositions and adds ordinary
planned values or assignments:

| Neutral disposition | Provenance behavior |
|---|---|
| `NewLineage` | current creation and revision provenance; current state-change provenance when Bitemporal |
| `PlannedUpdate` | preserve creation, replace revision provenance |
| `CarriedFrom` | preserve creation and state-change provenance; replace revision provenance |
| `ChangedFrom` | preserve creation; replace revision and state-change provenance |
| `Superseded` | no termination provenance |
| `Terminated` | add termination principal to the closed predecessor |

The decorator does not change temporal topology, classify gates, or emit SQL.
SQL lowering remains audit-unaware.

### 9. Freeze

The final stage constructs immutable Planned Steps. No private barrier, atomic
group, raw instruction, observation index, mode, instant supplier, or strategy
object accompanies the Write Plan.

## Temporal targeting and concurrency

### Current milestone targeting

Every operational temporal close targets the current Transaction-Time slot:

```text
primary key
AND each As-Of upper bound
AND tx_end = Infinity
```

For Bitemporal data, the Valid-Time upper bound is required because multiple
current rectangles can share a primary key and `tx_end = Infinity`.

Optimistic mode then adds:

```text
AND tx_start = observed_tx_start
```

The `tx_start` comparison is a gate, not part of target identity. Locking mode
omits it but retains the exact same Milestone Target.

### Historical optimistic observation

Suppose an editor observed an older Transaction-Time predecessor with:

```text
tx_start = old_start
tx_end   = finite_historical_end
```

An optimistic write still targets `tx_end = Infinity`; it never copies the
historical finite end into Milestone Target. The Temporal Gate carries
`tx_start = old_start`. If a newer current row exists, the gate affects zero
rows and produces Optimistic Lock Conflict. Closed history is never mutated.

Locking mode rejects that historical observation before planning because its
read lock did not license the current milestone.

## Ordering examples

### Readless barrier

Given:

```text
A: keyed child update
P: readless predicate update
B: keyed parent update
```

The planner may reorder within the region containing `A` and independently
within the region containing `B`, but neither may cross `P`. It cannot prove
whether either keyed write changes the predicate's match set.

### Bitemporal bounded update

A bounded Bitemporal update may produce:

```text
PlannedClose(
    target = key + observed valid_end + tx_end Infinity,
    cause = Superseded,
    concurrency = TemporalGate(observed tx_start),
)
PlannedInsert(head, CarriedFrom(predecessor))
PlannedInsert(changed range, ChangedFrom(predecessor))
PlannedInsert(tail, CarriedFrom(predecessor))
```

The exact successor count depends on interval overlap. The entire topology
occupies one position relative to unrelated writes.

### Termination

A temporal terminate produces a Planned Close with `cause = Terminated`.
Bitemporal head or tail survivors remain `CarriedFrom`, not terminated. Audit
Provenance stamps termination only on the closed predecessor.

## Execution and affected-row enforcement

Unit Work owns:

```text
enforce_affected_rows(
    step: PlannedWrite,
    actual_count: NonNegativeInt,
)
```

It raises the public Write Effect Error family:

```text
MissingTargetError
StaleWriteError
OptimisticLockConflictError
CardinalityCorruptionError
```

Every error carries the same semantic payload:

```text
entity: EntityIdentity
target: KeyTarget | MilestoneTarget
expected: PositiveInt
actual: NonNegativeInt
```

The target is retained by reference. Errors carry no SQL, statement index,
driver exception, entire Planned Write, assignments, or observation. This keeps
the diagnostic stable across dialects and lets Auto Retry recognize the
canonical optimistic conflict without depending on an optional implementation.
See [ADR 0048](../adr/0048-unit-work-owns-affected-row-failure-enforcement.md).

### Driver batching constraint

Multiple Exact Count logical steps may share a driver batch only when the
adapter returns one affected-row count aligned with every logical step. Unit
Work then enforces each result against its owning target.

An aggregate count is sufficient for one Planned Write whose own Key Target
contains multiple keys, because that one target owns the aggregate expectation.
An aggregate-only backend must execute distinct Exact Count steps separately.
It may still reuse statement preparation and stream bind rows.

This constraint preserves exact conflict attribution. It also matches the
useful Reladomo distinction between JDBC batch results, which preserve
per-operation counts, and set-based multi-update results, which know only the
candidate group.

## Compact Python representation

The semantic algebra must not force eager Python allocation proportional to the
number of logical rows at every planning layer.

### Chunked columns

The first implementation uses a private read-only column abstraction backed by:

```text
ChunkedColumn[T](
    chunks: tuple[tuple[T, ...], ...],
    length: int,
)

ColumnSlice(
    column,
    start,
    stop,
)
```

The materializer reads a database cursor incrementally into bounded builders
and seals each chunk once. It does not:

- retain a complete `fetchall()` array of row tuples;
- transpose that array into a second full-size collection; or
- perform one full-size list-to-tuple copy.

Column slices let later stages share immutable backing storage. The private
abstraction permits packed integer, memory-mapped, or spilled implementations
later without changing the semantic plan interface.

### Predecessor columns

Bulk temporal state shares one row shape and stores values by field column.
`PredecessorRow` remains the logical complete-state contract, but the runtime
creates a row view only when a consumer requests one. Temporal expansion should
prefer column slices and overlays rather than materializing every predecessor.

### Segmented Planned Steps

The first `PlannedSteps` implementation is a frozen, slotted segmented
sequence:

```text
PlannedSteps(
    segments: tuple[private StepSegment, ...],
)
```

Segments pack homogeneous runs and may retain shared columns, column slices,
uniform assignments, and row indices. Iteration and indexing expose logical
Planned Write views as needed. SQL lowering streams those views and bind rows.

Every exposed Planned Write and nested target is immutable and stable.
Iteration never mutates and reuses a flyweight. Views have structural equality
but no object-identity guarantee; repeated indexing may return equal distinct
objects. A consumer that retains all views owns the resulting wrapper memory.

### End-to-end compactness

Compactness is a contract for the whole path:

- materialization produces columns, not row wrapper arrays;
- strategy ports accept compact segments and preserve structural sharing;
- temporal expansion emits close and successor segments;
- Audit Provenance adds shared or columnar overlays;
- lowering streams views and binds; and
- no core participant eagerly converts logical row count into an equivalent
  object-wrapper graph.

Necessary indexes, genuinely distinct values, and derived columns are allowed.
For a million logical writes, the keys, observations, values, and executions
are inherently linear. The avoidable cost is a million input wrappers plus a
second million output wrappers.

The first implementation is memory-resident. Excluding retained input and
genuinely derived output columns and necessary compact indexes, transient
planning memory is:

```text
O(active chunk builders + genuinely distinct plan segments)
```

It is not `O(logical row count)`. A synthetic large-write allocation benchmark
or equivalent regression check must make accidental eager materialization
visible.

## Reladomo prior art

The detailed evidence is indexed in
[Reladomo research](../research/reladomo/00-index.md). The design adopts
semantics only where a Parallax decision explicitly says so.

| Reladomo behavior | Parallax use |
|---|---|
| Transaction operations buffer and combine adjacent compatible writes. | Supports centralized coalescing and batching, without copying the mutable operation hierarchy. |
| Same-transaction insert/update changes the pending insert; matching insert/delete cancels. | Adopted through ADR 0023. |
| Uniform multi-update shares update metadata across many targets. | Supports shared assignment shapes and compact segments. |
| Dated update predicates include primary keys and every As-Of `to` attribute. | Adopted for Milestone Target. |
| Operational dated writes constrain Reladomo's `OUT_Z` upper bound to Infinity. | Adopted for Transaction-Time upper-bound targeting. |
| Reladomo's `IN_Z` start acts as the temporal optimistic-version analogue. | Adopted as the separate Temporal Gate. |
| Optimistic JDBC batches inspect a result count per operation. | Supports the exact-count batching constraint. |
| Full participation locks the selected row; optimistic participation gates writes. | Supports uniform observation requirements with `Ungated` versus gate decisions. |

Parallax deliberately differs where its specifications or architecture are
stricter:

- target, observation, gate, and affected-row policy are separate typed values;
- locking-mode versioned delete is ungated, consistently with every other
  locking write;
- every Exact Count excess is Cardinality Corruption;
- the historical optimistic target always uses Transaction-Time Infinity;
- temporal units order before expanding, rather than relying on specialized
  post-expansion movement rules;
- neutral dispositions preserve supersession versus termination for Audit
  Provenance; and
- compact columnar storage avoids a managed-object-per-row planning boundary.

## Rejected alternatives

### Distributed orchestration

Allowing batching, temporal logic, locking, provenance, composition, and
lowering to sequence one another leaves no single finalized contract and makes
SQL lowering rediscover policy. Injected strategies under one Unit Work-owned
pipeline keep the module graph legal without distributing orchestration.

### A public `NoObservation`

This would make invalid combinations representable, such as a temporal close
with no predecessor. Structural absence plus explicit `Ungated` expresses the
two real cases without one ambiguous sentinel.

### Injecting Clock Strategy into the planner

A memoizing clock implementation could produce a stable instant, but the
attempt, not the clock, owns the lifecycle. `TransactionInstant` gives forced
flushes one value and retries a new value without turning Clock Strategy into
transaction state.

### Public atomic or temporal groups

Atomicity and barriers constrain private ordering. Once ordering and in-place
temporal expansion finish, adjacency is sufficient. Public group wrappers
would leak temporary machinery into every consumer.

### Separate Key Target and Key Set Target

Singleton and multi-key writes have the same semantics and invariants. One
nonempty Key Target with variable cardinality avoids duplicated lowering and
validation branches.

### Eager tuples of Planned Writes

`tuple[PlannedWrite, ...]` makes one wrapper per logical step part of the
interface. A logical immutable sequence preserves inspectability while allowing
segments, views, and streaming.

### Per-field assignment objects or persistent maps

One wrapper per field per row multiplies memory without adding semantics. Frozen
shapes plus aligned values provide immutability and deterministic iteration
using standard Python data structures, while leaving alternative backing
representations substitutable.

### Disk spilling in the first implementation

Spill infrastructure would solve a later storage problem before real workloads
and benchmarks establish the need. Private chunked columns avoid the one-way
door while keeping COR-62 focused.

## Implementation plan

Implementation should proceed in dependency order while keeping the repository
green between migrations.

### 1. Establish the normative contract

- Update `m-unit-work` and affected temporal, batching, concurrency, and Audit
  Provenance specifications to use the finalized algebra.
- Update the completed Python specification for the corrected locking-delete
  behavior, cardinality failures, planner interface, and compact internal
  representation where Python-specific.
- Add or revise compatibility cases before changing behavior.

The ADRs and this document explain the design, but specifications and cases
remain the product contract.

### 2. Introduce the new Unit Work values

- Add identity-based targets, observations, gates, affected-row policies, and
  Planned Write variants under `parallax.core.unit_work`.
- Add construction-time invariant checks.
- Introduce `TransactionInstant`.
- Add `enforce_affected_rows` and move canonical Write Effect Errors to Unit
  Work, retaining temporary re-exports only where compatibility requires them.

### 3. Add compact storage

- Implement private chunked columns, column slices, shared row and assignment
  shapes, Predecessor Columns, Step Segments, and Planned Steps.
- Test logical sequence behavior independently from physical representation.
- Make all exposed views frozen and stable.

### 4. Replace the planner

- Replace the current function-level `plan_flush` orchestration with one
  model-scoped `WritePlanner`.
- Inject immutable policy adapters at construction.
- Preserve one pure `plan(PlanningRequest) -> WritePlan` operation.
- Migrate `AtomicUnit` inputs to Materialized Write Groups.
- Remove legacy `FlushPlan.tx_instant`, optional `Observation`, and
  `expected_affected` fields once all consumers use the finalized values.

### 5. Migrate write-input preparation

- Resolve observation-requiring predicate writes into chunked columns directly
  from cursor iteration.
- Preserve forced-flush read-your-own-writes behavior.
- Acquire only the selected physical row locks in locking mode.
- Filter assignment-bearing no-op rows during cursor iteration using the shared
  Unit Work equality rules; retain every delete and terminate row.
- Avoid managed object materialization and row-wise intermediate collections.

### 6. Migrate temporal and provenance strategies

- Keep temporal mutations private and indivisible through ordering.
- Expand them in place into close and successor segments.
- Preserve complete predecessor state and close cause.
- Apply Audit Provenance as shared or columnar overlays after topology is
  settled.

### 7. Migrate lowering and execution

- Lower only Planned Write values.
- Remove raw transaction mode, observation, instant, and audit interpretation
  from ordinary lowering.
- Stream logical steps and bind rows.
- Enforce affected counts in Unit Work.
- Use driver batching only when count attribution satisfies the Exact Count
  rule.

### 8. Remove transitional seams

- Remove obsolete Atomic Unit, old Planned Write, and old Flush Plan shapes
  after production, conformance, and direct planner callers migrate.
- Reduce exports to the supported internal engine seam rather than preserving
  accidental implementation types.
- Update package documentation to describe the finalized pipeline.

## Verification

Follow the repository's [testing map](../../TESTING.md): use focused selectors
while implementing and run `just check` once after the final relevant change.

### Algebra and invariants

Unit tests must cover:

- empty Write Plan;
- duplicate and incomplete keys;
- repeated authored keys;
- target/variant legality;
- missing required observations;
- singleton requirement for Version Gate;
- nonempty Planned Assignments and Insert Entries;
- aligned column lengths;
- one group-wide Transaction-Time Basis;
- stable view equality and lifetime; and
- construction without eager per-row wrappers.

### Pipeline behavior

Tests must pin:

- insert/update coalescing and insert/delete cancellation;
- no clock capture for canceled and net-zero work;
- one instant across forced flushes and a new instant on retry;
- readless barrier partitioning;
- dependency ordering around materialized and temporal units;
- temporal in-place adjacency;
- no-op elimination before temporal and audit decoration; and
- provenance dispositions for lineage, carried, changed, superseded, and
  terminated state.

### Concurrency and effects

Compatibility and integration tests must cover:

- versioned update and delete in optimistic and locking modes;
- Transaction-Time-only and Bitemporal closes in both modes;
- selected-row locking rather than edge-wide locking;
- historical Transaction-Time observation rejection in locking mode;
- historical optimistic gating against the current Infinity target;
- Key, Predicate, and Milestone cardinality;
- Missing Target, Stale Write, Optimistic Lock Conflict, and Cardinality
  Corruption;
- exact diagnostic payloads; and
- per-step versus aggregate driver batch counts.

### Storage and scale

Tests or benchmarks must demonstrate:

- cursor-to-column materialization without `fetchall()`;
- streaming no-op filtering without retained comparison-only columns;
- bounded chunk construction;
- structural sharing across materialization, temporal expansion, provenance,
  and lowering;
- streaming lowering;
- no mutable flyweight views; and
- large versioned and temporal materialized writes without parallel per-row
  input and output wrapper graphs.

The scale check should measure allocation shape and peak auxiliary memory, not
promise a universal absolute byte limit independent of key width, predecessor
shape, driver representation, and workload.

## Decision status

The Write Planner design is ready for implementation. No unresolved semantic
choice remains in COR-62's planner boundary, finalized algebra, pipeline order,
temporal targeting, concurrency handling, affected-row enforcement, or initial
Python memory representation.

Implementation must begin by making the authoritative specifications and cases
match these accepted decisions, then migrate the runtime through the staged
plan above.

## Related decisions

- [ADR 0010: Transaction instants come from Clock Strategy](../adr/0010-transaction-instants-come-from-clock-strategy.md)
- [ADR 0023: Same-transaction writes coalesce in Unit Work](../adr/0023-same-transaction-writes-coalesce-in-the-unit-of-work.md)
- [ADR 0024: Write instructions are hosted in `m-unit-work`](../adr/0024-write-instructions-are-hosted-in-m-unit-work-and-cases-declare-compile-eligibility.md)
- [ADR 0033: Audit provenance distinguishes revision, state change, and termination](../adr/0033-audit-provenance-distinguishes-revision-state-change-and-termination.md)
- [ADR 0034: Principal is required at every database operation boundary](../adr/0034-principal-is-required-at-every-database-operation-boundary.md)
- [ADR 0037: Audit Provenance decorates finalized neutral write plans](../adr/0037-audit-provenance-decorates-finalized-neutral-write-plans.md)
- [ADR 0041: Write finalization is centralized behind a typed planner](../adr/0041-write-finalization-is-centralized-behind-a-typed-planner.md)
- [ADR 0042: Temporal plans retain complete predecessor state and close cause](../adr/0042-temporal-plans-retain-complete-predecessor-state-and-close-cause.md)
- [ADR 0043: Readless predicate writes are ordering barriers](../adr/0043-readless-predicate-writes-are-ordering-barriers.md)
- [ADR 0044: Write target cardinality governs affected-row validation](../adr/0044-write-target-cardinality-governs-affected-row-validation.md)
- [ADR 0045: Temporal mutations expand in place after ordering](../adr/0045-temporal-mutations-expand-in-place-after-ordering.md)
- [ADR 0046: Milestone targets use axis upper bounds independent of gates](../adr/0046-milestone-targets-use-axis-upper-bounds-independent-of-gates.md)
- [ADR 0047: Concurrency mode determines write gates uniformly](../adr/0047-concurrency-mode-determines-write-gates-uniformly.md)
- [ADR 0048: Unit Work owns affected-row failure enforcement](../adr/0048-unit-work-owns-affected-row-failure-enforcement.md)
