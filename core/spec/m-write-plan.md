# m-write-plan — Planned Writes and Write Observations

`m-write-plan` specifies the finalized semantic form of a write — the Planned
Write algebra and the Write Target, Write Gate, and Affected Rows Policy
vocabulary it is built from — the Write Observation a write against existing
state retains, including a temporal write's Predecessor Row, and the neutral
vocabulary of the payload a write persists. Per the dependency graph it depends
on `m-core`, `m-metamodel`, `m-predicate`, `m-inheritance`, `m-document-codec`,
and `m-temporal-read`, and on nothing that buffers, plans, executes, lowers, or
places a write. `m-unit-work` plans buffered writes into this algebra and carries
each observation to the write it settles; `m-write-payload` prepares what each
write persists; `m-sql` lowers the algebra with those prepared values (`m-sql`
*Private compiler inputs*). None depends on another for it.

## The Planned Write algebra

A **Planned Write** is one finalized semantic execution step. It may address one
row or many, and its target, row topology, concurrency decision, and expected
effect are all settled before SQL lowering. The algebra is **closed**:

```text
PlannedWrite =
    PlannedInsert(entity, entries: NonEmpty[WriteRow])
  | PlannedUpdate(entity, target, assignments, concurrency, affected_rows)
  | PlannedClose(entity, target, assignments, cause, concurrency, affected_rows)
  | PlannedDelete(entity, target, concurrency, affected_rows)
  | PlannedTemporalRevision(entity, target, assignments, concurrency, affected_rows)
  | PlannedTemporalRemoval(entity, target, concurrency, affected_rows)
  | PlannedTemporalGuard(entity, target, concurrency: TemporalGate, affected_rows)
```

The algebra is **semantic and Attribute-keyed**. It contains no SQL, dialect
object, driver value, physical column name, property name, or SQL ordering.

- **Planned Insert** carries one or more Write Rows. Every entry of one step
  has the same canonical member set and generated-value shape; incompatible
  entries form separate steps. Membership *is* the batching decision, so there is
  no batch flag and no group identifier. A Planned Insert carries no Write
  Target, no gate, and no Affected Rows Policy.
- **Planned Update** revises existing Non-Temporal rows in place. Its
  assignments are uniform across every row its target selects; differing per-key
  assignments remain distinct steps. A Milestone Target is prohibited — a
  temporal change is a temporal step, never a Planned Update.
- **Planned Close** closes one current temporal milestone. Its assignments carry
  the Transaction-Time end. Its expected effect is always exactly one row.
- **Planned Delete** is physical row deletion. It carries no row, assignments,
  predecessor, Row Origin, or Close Cause, and a Milestone Target is
  prohibited: represented-state absence is a temporal step, not a delete.
- **Planned Temporal Revision** revises one current milestone the attempt itself
  opened, in place at its complete physical address. Its assignments carry
  writable payload and, on a Bitemporal row, a moved Valid-Time start; they never
  carry the logical key, an axis end, or the Transaction-Time start. Its expected
  effect is exactly one row.
- **Planned Temporal Removal** physically removes one current milestone the
  attempt itself opened. Its expected effect is exactly one row. It removes
  uncommitted state of the attempt's own: a milestone that existed before the
  attempt is never revised or removed, only closed (`m-temporal-write`
  *Ownership disposal*).
- **Planned Temporal Guard** proves that one current milestone that existed
  before the attempt still stands as it was observed, for a write that leaves it
  unchanged (`m-temporal-write` *Unchanged milestones*). It addresses the milestone as a close does
  and always carries the close's Temporal Gate, assigns nothing it represents,
  and its expected effect is exactly one row. It changes no observed state.

### Write Rows, Row Origin, and Close Cause

```text
RowOrigin =
    NewLineage
  | CarriedFrom(predecessor)
  | ChangedFrom(predecessor)

WriteRow(
    row:      PlannedRow,
    origin:   RowOrigin,
    executed: PlannedAssignments | absent,
    prepared: RowPayload | absent,      -- backing, outside the row's meaning
)

CloseCause = Superseded | Terminated
```

A **Write Row** is one represented row's state before settlement decides how it
is realized — opened, or revised in place where the attempt owns its
predecessor — and does not imply that every represented row changed: a new
lineage and carried state are equally Write Rows. It is what a Planned Insert's
entries are.

A Write Row's **executed assignments** are the members it states explicitly —
the authored assignments of the write that produced it, plus any audit value
finalization added — each holding the value the row holds. Every other member of
a carried or changed row is its predecessor's own state. An assignment is
executed whatever value the predecessor already holds there: an equal authored
value is still an assignment, and nothing infers executed members from value
inequality or from whether a cell is its predecessor's own object. Rows the same
assignments reach share one executed set. A new lineage writes every member it
holds, so it needs none.

A Write Row MAY carry **prepared** persisted backing (*Write payloads*, below)
derived from exactly that row, which lowering reuses rather than preparing
again. It is not part of the row's meaning, so equality ignores it.

Origin belongs to **each Write Row**, never to the whole step and never to a
parallel array, so a multi-row insert whose rows have different origins keeps
that distinction. `NewLineage` begins a new Provenance Lineage; `CarriedFrom`
carries represented state unchanged from its predecessor; `ChangedFrom` changes
it. An update verb produces `Superseded`; a terminate verb produces `Terminated`
even when Bitemporal head or tail successors survive — those survivors are
independently `CarriedFrom`.

An implementation **MUST NOT** introduce a generic disposition field, a parallel
mutation-kind tag, or any free-floating label that a variant could contradict.
Row Origin exists only on a Write Row and Close Cause only on a close, so
a termination cause on an inserted row and a lineage-start origin on a close are
**unrepresentable** rather than merely invalid. A Planned Update needs no label
either: *being* a Planned Update already carries the fact that an existing row
was revised in place. A Planned Delete removes the row and so has nothing to
label.

### Planned rows and assignments

```text
PlannedValue = ManagedValue | Null | GeneratedValueExpression

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
one Write Row, including framework-owned version, temporal, and audit
attributes the planner derived. **Planned Assignments** is nonempty, immutable,
and duplicate-free, and unlike a Planned Row it names only the members its step
changes. Entity Layout continues to decide physical `SET` and bind order
(`m-sql`).

Trusted settlement builders construct each final Attribute and Value Object map
once and transfer that storage directly into the immutable carrier. Public or
untrusted construction still establishes ownership defensively. Temporal
expansion builds each successor directly as its final `WriteRow` and
`PlannedRow`; there is no separate successor-row carrier and no metadata-to-name-
to-metadata remapping between prepared assignments and final member identities.

A **Generated Value Expression** is the closed set of cell values the *database*
computes from the row being written rather than binding as a literal, and
`m-pk-gen` is its only source: the `max` allocation an insert folds into its own
statement, and the registry advance an update applies to the stored value. Each
is legal only where the statement that renders it can express it, so a Planned
Row and Planned Assignments admit different members of the set rather than
different value vocabularies. A `max` allocation is **returned** where the row it
opens is temporal: the statement then answers the allocated key, because the
attempt records that row by its complete address (`m-unit-work` *Rows the
attempt opened*)
and nothing else names it. What neither admits is an **authored assignment
expression** — anything a caller composes out of Predicate — because
the planner resolves every caller-supplied value before a step is settled.

### Write Target

```text
WriteTarget = KeyTarget | ValidatedMutationSelection | MilestoneTarget
```

A **Write Target** is the semantic row selection of a Planned Write. It is
distinct from observed predecessor state and from any concurrency condition.

```text
KeyTarget(
    key_attributes: NonEmpty[AttributeIdentity],
    key_values:     NonEmpty[complete concrete non-null value tuples],
)

ValidatedMutationSelection(
    target:    EntityIdentity,
    predicate: ValidatedPredicate,
)

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
- A **Validated Mutation Selection** is legal only for a **readless** unversioned
  Non-Temporal Planned Update or Planned Delete. It carries the exact target and
  producer-owned validated Predicate and nothing else — no materialized keys,
  observation, pin, concurrency data, or barrier flag. Its presence already
  implies `Unversioned`, `AnyCount`, and barrier behavior; mutation lowering never
  fabricates an Object Query around it.
- A **Milestone Target** addresses the current milestone slot a close,
  revision, or removal acts on: one complete key tuple plus one write-required
  **exclusive upper bound per As-Of Axis** — the observed predecessor's
  Valid-Time end where that axis exists, and invariant `Infinity` for
  Transaction Time. That tuple is the row's complete **physical address**. It contains no axis start, gate, observation,
  or Effective Concurrency Strategy, and it is **identical under both strategies**
  (ADR 0046). Only the gate differs.

### Write Gate and the concurrency decision

```text
VersionGate(observed_version: PositiveInt)
TemporalGate(start_attribute: AttributeIdentity, observed_start: Instant)
Ungated

NonTemporalConcurrency =
    Unversioned
  | Versioned(attribute: AttributeIdentity, gate: VersionGate | Ungated)
```

A **Write Gate** carries only the extra equality predicate lowering renders. The
advanced version value and the close instant are **assignments**, not gate
members, and a gate repeats neither the full observation nor the transaction's
Effective Concurrency Strategy — both are consumed during planning and do not
survive in the plan.

`Versioned` names the target's version Attribute once, as planning settled it.
Both strategies advance that Attribute, and only a Version Gate compares it
against the observed version, so lowering reads it from the decision rather than
deriving the target's version source again.

Planned Update and Planned Delete carry a Non-Temporal Concurrency decision;
Planned Close carries `TemporalGate | Ungated` directly, because every close
requires a temporal observation and so has no unversioned case. The effective
Locking strategy records an **explicit** `Ungated` decision rather than a null gate, which is what
makes gate applicability structural. The gate rule itself is uniform across
update, delete, and close and belongs to `m-opt-lock`.

A Version Gate requires a **singleton** Key Target, because each observed version
belongs to exactly one row.

### Affected Rows Policy

```text
Shortfall = MissingTarget | StaleWrite | OptimisticConflict | FailedPrecondition

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

- a **gated** shortfall is `OptimisticConflict`, or `FailedPrecondition` where
  the gate binds a caller's stated revision rather than an observation;
- an **ungated observation-requiring** shortfall is `StaleWrite`; and
- an **observation-free keyed** shortfall is `MissingTarget`.

An **excess** over any exact count is always Cardinality Corruption. It is an
invariant failure rather than a concurrency outcome, so it is not one of the
shortfall tags and is never carried in the policy payload. Planned Inserts carry
no Affected Rows Policy.

The tags are **neutral**: the plan names an outcome class, never a language's
exception type.

## Write Observation

```text
WriteObservation =
    VersionObservation(observed_version)
  | TemporalObservation(predecessor)
```

A **Write Observation** is the database evidence a surviving write against
existing state retains. Transaction-Time-Only and Bitemporal entities have
**identical** observation requirements; the accepted Temporal Facet — not a
separate observation variant per temporal flavor — decides which topology
applies.

### Observed State Key

An observation is evidence about **one exact observed state**, and that state is
what addresses it:

```text
ObservedStateKey =
    VersionedStateKey(object, version)
  | TemporalStateKey(object, milestone)
```

An **Object Key** is Entity Identity plus ordered primary-key values and
deliberately carries no version and no temporal coordinate: it addresses the
object **across** its states, which is what write coalescing, cancellation, and
buffered-insert recognition each ask about. An **Observed State Key** addresses
**one** of those states, which is what observation eligibility and consumption
ask about. Inserts and unversioned Non-Temporal writes observe no state and
therefore have no Observed State Key at all; the absence is the missing arm,
never a key with an empty coordinate. The two differ in what follows from that
absence: an insert opens a row and has no prior state for anything to be about,
while an unversioned Non-Temporal existing-row write does write against a stored
row and is claimed at that row's **Object Key** (`m-unit-work` *Observed-State
Coalescing*), whose shared row lock is its evidence. Both keys address **one** object,
so a write instruction naming **several** rows has neither and is claimed
nowhere.

An implementation **MUST NOT** address observations by identity alone. Two reads
of one primary key may observe two different states — two generations of one
versioned row, or two milestones of one chain — and a slot keyed by identity
alone would let the second erase the first, after which a write settles against
a state its own value never came from. The version or milestone coordinate
**MUST** be derived from the observation's own evidence, so a recorder cannot
address an observation by a state other than the one it is recording.

The milestone coordinate is deliberately the **converse** of the identity key
(`m-identity-map`), and a reader who knows that key will assume it is the same
one unless told otherwise. The identity triple carries the *query's* lowered
as-of coordinate and makes **distinct** coordinates denote **distinct pinned
views**, even when both currently resolve to one milestone row, because each
view drives its own relationship dereferencing. An Observed State Key carries
the *observed milestone's own* coordinate, so two **distinct** pins that resolve
to **one** milestone deliberately name **one** observed state: an observation
records what was read, not the reading, and a milestone read twice is one piece
of evidence.

### Predecessor Row

A **Predecessor Row** is the complete, immutable persisted state a Temporal
Observation retains: every applicable scalar Attribute value, every complete
Value Object occurrence, the complete primary key, every temporal bound, and
every audit value, with no generated-value expression. Completeness is required
because temporal expansion carries members the authored mutation never mentioned,
and because audit finalization must distinguish `m-edit`'s carried state from its
authored assignments without a second read (ADR 0042). Successors retain or view
that state rather than copying it, and bulk materialization MAY expose a logical
Predecessor Row view over a group's compact storage — aligned columns, or the
resolving read's own row state, for example — instead of allocating one row
object per observation. Where a trusted producer already owns the observed state
outright, it transfers that state into the Predecessor Row; the carrier does not
copy it and then freeze it again.

The state is immutable **logically**: no consumer mutates it, and none hands it to
a caller that could. That is what lets a trusted producer transfer state it owns
exclusively — decoded host containers included — rather than freeze a copy. State
a caller supplies is not owned that way, so a carrier constructed from it retains
it in immutable form.

Under Relational Document Layout a Predecessor Row additionally retains the
**raw Structured Column document**, as a distinct named field beside its member
state and never as an entry in it. A group's compact storage carries the same
value aligned with each row's member state, so a logical Predecessor Row view over
it exposes the raw document without allocating a second per-row carrier. The
document is read-only under the same logical immutability: a successor that
changes a member composes its own document from a copy (`m-document-codec`
patching), and no reader alters the retained one. What a successor binds from it
crosses the port as `m-db-port` requires of a retained document.

The field is **absent — not empty — under Columns layout**, so its presence is
itself the signal that the row came from a document-mapped Table. It is not a
member: the member map stays purely logical, and a consumer that iterates
members can never surface the raw document as a result field or an Entity
member.

Retention costs no additional query. A temporal write already materializes its
predecessor to obtain the key, milestone bounds, and complete state; the
resolving read projects the Structured Column for that observation
anyway, and this rule says only that the observation path carries the value
forward instead of discarding it once known members are decoded.

The successor is then built by patching that retained document
(`m-document-codec`) **at its executed assignments' paths alone** rather than by
re-encoding decoded members (`m-write-payload`). That is what preserves keys a newer application
version wrote: an application that predates a key it never declares still
carries that key across a close-and-insert, and so does every member the mutation
left alone.

An assigned occurrence is where `m-edit`'s carry-forward stops. Assigning one
replaces the subtree stored at its path, whole and at either cardinality, so an
omitted declared member is absent in the successor and a key no member declares
does not survive inside it — the author stated a complete value, and no stored
member is merged back into it. That holds for an assigned occurrence equal to
the stored one too: it is executed, so the undeclared keys inside the stored
subtree are gone. An explicitly null occurrence stores JSON null. Everything
outside an assigned occurrence — every unassigned occurrence, every unassigned
document-resident Attribute, and every undeclared key at any position the
mutation did not name — rides forward exactly as stored.

## Write payloads

```text
WritePayloadPreparer
  assignments(entity, PlannedAssignments) -> AssignmentPayload
  row(entity, WriteRow)                   -> RowPayload
  proven_unequal_non_interval(entity, WriteRow, WriteRow) -> Boolean
  equal_non_interval(RowPayload, RowPayload)              -> Boolean

RowPayload(entity, row: PlannedRow, cells: [PayloadCell])
AssignmentPayload(entity, assignments: PlannedAssignments, cells: [PayloadCell])
PayloadCell(contributor, value)
```

A Planned Write states what a write means; what it **persists** is its payload.
This module declares the payload vocabulary and the interface that prepares it,
so that settlement and lowering share one preparer without the algebra depending
on storage placement. `m-write-payload` implements the interface; the execution
module constructs it for one accepted model and hands it to the Write Planner it
configures.

A payload's cells follow Table Layout slot order, and each names its contributor
by model identity — a member, the Table's shared Structured Column, or the
table-per-hierarchy discriminator — never a physical column. A value is a
planned scalar or generated-value expression, a complete encoded document, the
discriminator's tag, or, for a revising step's shared Structured Column, the
ordered prepared patches it applies. A payload holds the semantic row or
assignment set it was prepared from by identity, which is the whole of its
binding: a consumer handed a payload prepared from other inputs refuses it
without comparing documents. No SQL, dialect object, driver value, or executable
recipe enters a payload or a plan.
