# m-write-plan — Planned Steps and State Observations

`m-write-plan` specifies what a finalized write means — its Planned Steps and the
Write Target, Write Gate, and Affected Rows Policy they are stated in — the State
Observation a write against existing state retains, including a temporal write's
Predecessor Row, and the neutral vocabulary of the payload a write persists. Per
the dependency graph it depends on `m-core`, `m-metamodel`, `m-predicate`,
`m-inheritance`, `m-document-codec`, and `m-temporal-read`, and on nothing that
buffers, plans, executes, lowers, or places a write. `m-unit-work` plans buffered
writes into these steps and carries each observation to the write it settles;
`m-write-payload` prepares what each write persists; `m-sql` lowers the steps with
those prepared values (`m-sql` *Compilation boundary*). None depends on another
for it.

## Planned Steps

A **Planned Step** is one semantic effect of a write on stored rows: the **Write
Target** it addresses — a set of keys, a resolved predicate selection, or one
milestone's complete address — what it assigns or opens, the concurrency condition
it carries, and the effect it expects, all settled before SQL lowering. One
statement may carry several steps (`m-execution`). A conforming implementation
distinguishes these kinds of step, because each has its own statement form and
expected effect; how it represents them is private. A step is stated in Attribute
and Value Object identities, never in physical columns, property names, or SQL
order.

| Step | Meaning | Expected effect |
|---|---|---|
| Planned Insert | opens one or more rows of one member set | none |
| Planned Update | revises existing Non-Temporal rows in place, uniformly | as *Affected Rows Policy* states |
| Planned Delete | physically removes Non-Temporal rows | as *Affected Rows Policy* states |
| Planned Close | closes one current temporal milestone | exactly one row |
| Planned Temporal Revision | revises in place a current milestone the attempt opened | exactly one row |
| Planned Temporal Removal | removes a current milestone the attempt opened | exactly one row |
| Planned Temporal Guard | proves a pre-attempt milestone still stands as observed, changing nothing | exactly one row |

### Write Rows, Row Origin, and Close Cause

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

**Row Origin** says how a Write Row came to be, and each row has its own, so a
multi-row insert whose rows have different origins keeps that distinction:
`NewLineage` begins a new Provenance Lineage; `CarriedFrom` carries represented
state unchanged from its predecessor; `ChangedFrom` changes it. **Close Cause**
says why a close ended a milestone: an update verb produces `Superseded`; a
terminate verb produces `Terminated` even when Bitemporal head or tail successors
survive — those survivors are independently `CarriedFrom`. Audit reads both
(`m-unit-work` *The planning pipeline*).

A row merged from several adjacent produced rows of identical persisted state
(`m-temporal-write` *Merging produced successors*) is one Write Row over the
merged Valid Time. Its origin is the origin of the produced row whose prepared
state it stores, which describes how that state is assembled, not which
predecessors it covers: every merged row's contributions, each a predecessor
over the part of the row it contributed, belong to the completion its settled write publishes
(`m-unit-work` *Write Groups complete before later work runs*), never to a
second origin or a list of predecessors on the row.

### Planned rows and assignments

A **Planned Row** is the immutable, duplicate-free complete semantic contents of
one Write Row, including framework-owned version, temporal, and audit
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
different value vocabularies.

### Write Target

A **Write Target** is the semantic row selection of a Planned Step. It is
distinct from observed predecessor state and from any concurrency condition, and
it is one of three meanings:

- A **Key Target** addresses rows by complete primary-key values. One key and
  several keys are cardinalities of one target, not two.
- A **Resolved Mutation Selection** addresses the rows a resolved Predicate
  selects, for a predicate-selected write (`m-batch-write`).
- A **Milestone Target** addresses one current milestone by its complete physical
  address (`m-temporal-write` *Address and gate are separate*).

### Write Gate and the concurrency decision

A **Write Gate** is the extra equality condition a step's statement carries: a
**Version Gate** compares one row's version with what was observed, and a
**Temporal Gate** one milestone's Transaction-Time start. A step with neither is
**Ungated**, which the effective Locking strategy records as a decision rather
than as a missing gate. The gate rule itself is uniform across update, delete,
and close and belongs to `m-concurrency`.

### Affected Rows Policy

Every surviving non-insert step carries a **fully resolved** Affected Rows
Policy before lowering. The **target** decides the expected cardinality and the
**concurrency decision** decides the shortfall classification (ADR 0044). A
step's expected effect is any count for a predicate-selected step, the number of
keys for a keyed step, and one for a milestone. A shortfall is classified
`MissingTarget`, `StaleWrite`, `OptimisticConflict`, or `FailedPrecondition` as
follows:

- a **gated** shortfall is `OptimisticConflict`, or `FailedPrecondition` where
  the gate binds a caller's stated revision rather than an observation;
- an **ungated observation-requiring** shortfall is `StaleWrite`; and
- an **observation-free keyed** shortfall is `MissingTarget`.

An **excess** over any exact count is always Cardinality Corruption. It is an
invariant failure rather than a concurrency outcome, so it is not one of the
shortfall tags. A Planned Insert carries no Affected Rows Policy.

The tags are **neutral**: the plan names an outcome class, never a language's
exception type.

## State Observation

```text
StateObservation =
    VersionObservation(observed_version)
  | TemporalObservation(predecessor)
```

A **State Observation** is the database evidence a surviving write against
existing state retains. Transaction-Time-Only and Bitemporal entities have
**identical** observation requirements; the accepted Temporal Facet — not a
separate observation variant per temporal flavor — decides which topology
applies.

### Object State Key

An observation is evidence about **one exact observed state**, and that state is
what addresses it:

```text
ObjectStateKey =
    VersionedObjectStateKey(object, version)
  | TemporalObjectStateKey(object, milestone)
```

An **Object Key** is Entity Identity plus ordered primary-key values and
deliberately carries no version and no temporal coordinate: it addresses the
object **across** its states, which is what write coalescing, cancellation, and
buffered-insert recognition each ask about. An **Object State Key** addresses
**one** of those states, which is what observation eligibility and claims
ask about. Inserts and unversioned Non-Temporal writes observe no state and
therefore have no Object State Key at all; the absence is the missing arm,
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

A snapshot graph's resolution key (`m-snapshot-read`) carries the *query's*
lowered as-of coordinate, because a node's pin drives its relationship
dereferencing. An Object State Key carries the *observed milestone's own*
coordinate, so two **distinct** pins that resolve to **one** milestone name
**one** observed state: an observation records what was read, not the reading,
and a milestone read twice is one piece of evidence.

### Predecessor Row

A **Predecessor Row** is the complete, immutable persisted state a Temporal
Observation retains: every applicable scalar Attribute value, every complete
Value Object occurrence, the complete primary key, every temporal bound, and
every audit value, with no generated-value expression. Completeness is required
because temporal expansion carries members the authored mutation never mentioned,
and because audit finalization must distinguish `m-edit`'s carried state from its
authored assignments without a second read (ADR 0042).

The state is immutable: nothing a caller does to a value after a read changes
what a successor stores, and no consumer hands retained state to a caller that
could change it.

Under Relational Document Layout a Predecessor Row additionally retains the
**raw Structured Column document**. The document is read-only: a successor that
changes a member composes its own document from a copy (`m-document-codec`
patching), and no reader alters the retained one.

Under Columns layout no document is retained. A retained document is no member:
it never surfaces as a result field or an Entity member.

Retention costs no additional query. A temporal write already materializes its
predecessor to obtain the key, milestone bounds, and complete state; the read
that observed it projects the Structured Column for that observation anyway, and this rule says only that the observation path carries the value
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

A Planned Step states what a write means; what it **persists** is its payload:
the cells a row stores and the values a revising step assigns, in Table Layout
slot order. Each cell is identified by model identity — a member, the Table's
shared Structured Column, or the table-per-hierarchy discriminator — never a
physical column. A value is a planned scalar or generated-value expression, a
complete encoded document, the discriminator's tag, or, for a revising step's
shared Structured Column, the ordered patches it applies. `m-write-payload` owns
how a payload is assembled. Settlement and lowering reach preparation through an
interface this module declares, so no Planned Step depends on storage placement.
No SQL, dialect object, or driver value enters a payload or a plan.
