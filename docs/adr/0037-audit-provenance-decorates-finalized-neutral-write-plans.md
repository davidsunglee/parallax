# Audit provenance decorates finalized neutral write plans

Audit Provenance enriches a finalized neutral write plan after Unit Work coalescing and temporal milestone planning but before ordinary SQL lowering. The decorator consumes accepted Audit Metadata, the boundary-captured Subject Identity, the attempt's lazily captured Transaction Instant, and any observed predecessor state. It assigns provenance only to rows and assignments in a nonempty flush: canceled and net-zero writes that never flush receive no stamps and do not force a Clock Strategy read, temporal topology remains owned by the temporal planners, and SQL/dialect modules remain audit-unaware because they lower the resulting explicit attributes normally.

The finalized-plan interface exposes provenance-neutral write dispositions. It
distinguishes a Lineage Start, an In-Place Revision, a Carried-State Successor,
a Changed-State Successor, an Ordinary Revision Close, and an explicit State
Termination. A Lineage Start is an insert. An In-Place Revision is a
Non-Temporal update that emits DML, whether keyed, materialized, or readless. A
Carried-State Successor preserves represented state in a temporal successor; a
Changed-State Successor changes it. An Ordinary Revision Close supersedes a
temporal predecessor without asserting absence, while State Termination
explicitly makes state absent. The planner that creates the topology already
knows these facts and records them without naming an audit attribute. The Audit
Provenance decorator consumes those dispositions rather than reverse-engineering
mutation verbs or depending directly on Transaction-Time, Bitemporal, or batch
planner implementations. Non-Temporal delete has no row to stamp and therefore
no disposition.

The decorator interprets each disposition uniformly. A Lineage Start receives
current creation and revision provenance and, when Bitemporal, current
state-change provenance. An In-Place Revision preserves creation and replaces
revision provenance. A Carried-State Successor preserves creation while
receiving current revision provenance and, when Bitemporal, preserves
state-change provenance. A Changed-State Successor preserves creation while
receiving current revision provenance and, when Bitemporal, current state-change
provenance. A Transaction-Time-Only successor has no state-change attributes to
preserve or assign. An Ordinary Revision Close changes only the temporal end; it
does not invent a closure principal. State Termination changes the end and
assigns the termination principal, while any surviving head or tail is
independently a Carried-State Successor.

The composition boundary is lifecycle-neutral. Write-plan owners expose the
disposition-bearing neutral plan, Audit Provenance owns its decoration, and
ordinary SQL lowering follows. No lifecycle extension owns or redefines the
provenance semantics, and no SQL or dialect module interprets them.

A readless Non-Temporal predicate update remains one statement and gives every
matched row an In-Place Revision, stamping its revision provenance even when an
assignment happens to equal the stored value; discovering equality would
require the read this write family intentionally avoids. Matching zero rows
changes no stored row. A known canceled, coalesced, or net-zero write produces
no disposition. Materialized temporal writes retain their existing
effective-change and no-op rules.

The catalog records the resulting direct edges:

```text
m-execution-authority --> m-unit-work
m-execution-authority --> m-db-port

m-audit-provenance --> m-execution-authority
m-audit-provenance --> m-metamodel
m-audit-provenance --> m-model-formation
m-audit-provenance --> m-inheritance
m-audit-provenance --> m-storage-layout
m-audit-provenance --> m-temporal-read
m-audit-provenance --> m-unit-work
```

Both modules are common-runtime behavior. SQL, dialect, temporal, and batch
planning modules remain independent of Audit Provenance. Slice membership is
declared only by `core/spec/slices.md`.

## Amendment (2026-09): execution authority replaces the absent principal module

ADR 0066 supersedes ADR 0034 and establishes `m-execution-authority`; there is no
`m-principal` module. Unit Work owns the closed Actor Identity values that
planning receives, while Execution Authority owns explicit scope selection,
capture, provider authorization, retry propagation, and join comparison. The
dependency direction is therefore `m-execution-authority --> m-unit-work`, not
the reverse. Audit Provenance consumes both the captured actor and the finalized
plan, so it depends on Execution Authority and Unit Work independently.

Snapshot and managed execution surfaces do not gain direct behavioral edges to
authority merely because they carry an already-captured actor. Capture is
orchestration behavior and neutral planning and materialization remain
authority-unaware. This amendment changes no provenance semantics, disposition
interpretation, or ownership of decoration.

## Amendment (2026-07): the closed algebra superseded this ADR's own disposition vocabulary

COR-62's finalized `m-unit-work` algebra closed over Insert Origin and Close
Cause and, in doing so, retired the free-floating disposition vocabulary this
ADR's body coined and used throughout: a "disposition" is no longer a
free-floating label at all, but a value that lives only inside the Planned
Write variant that admits it. The semantics this ADR fixes are unchanged; only
the names are superseded, one for one:

| This ADR's original term | Current term |
|---|---|
| Lineage Start | Insert Origin `NewLineage` |
| In-Place Revision | Planned Update (a Non-Temporal update needs no label; being a Planned Update already says so) |
| Carried-State Successor | Insert Origin `CarriedFrom` |
| Changed-State Successor | Insert Origin `ChangedFrom` |
| Ordinary Revision Close | Close Cause `Superseded` |
| State Termination | State Termination (unchanged) |
| "disposition" (as a free-floating label) | retired outright — Insert Origin exists only on an insert entry, Close Cause only on a close |

A future reader should read this ADR's body with that substitution; the
decorator behavior each row describes — what each variant preserves, replaces,
or assigns — is exactly what COR-62 shipped.
