# Write finalization is centralized behind a typed planner

Unit Work owns one typed Write Planner that turns buffered Write Instructions
and applicable Write Observations into an ordered Write Plan. It is the sole
authority for coalescing and cancellation, no-op elimination possible from
buffered planning data, target and observation binding, batching and dependency
ordering, temporal topology, concurrency gates, affected-row expectations, and
each Planned Write's Insert Origin or Close Cause. Result-dependent no-op filtering for an
observation-requiring predicate mutation is the one narrow pre-planning
exception: Unit Work's write-input materializer compares assigned values while
streaming the resolving cursor and contributes only effective rows. Delete and
terminate mutations contribute every resolved row. Batching, temporal, locking,
and Audit Provenance behavior enters through injected strategy ports; the
composition root wires those collaborators once but does not sequence planning
stages. This extends ADR 0024, which hosts the write vocabulary in
`m-unit-work`, and ADR 0037, which requires a finalized neutral plan before
provenance decoration.

The Write Planner is constructed once per connected Metamodel with that model
and its immutable strategy adapters. Its sole external operation is
`plan(PlanningRequest) -> WritePlan`, where each request carries the current
flush's boundary-captured Subject Identity, attempt-owned lazy Transaction
Instant, concurrency mode, buffered writes, and observations. Subject Identity
is the first required field of the keyword-only request, emphasizing that
planning occurs inside an established Principal boundary without making field
order a positional API. The planner is stateless across calls and retains
neither the request nor result. Forced flushes in one attempt pass the same
Subject Identity and Transaction Instant; a retry retains the boundary's
Subject Identity but supplies the fresh attempt's Transaction Instant.

The planning operation is pure. Its interface contains no Clock Strategy,
database port, SQL generator, dialect, driver, or composition-root staging
callback. The Transaction Instant itself owns lazy clock consultation; the
planner may resolve its value when a surviving step needs time without gaining
a Clock dependency. The request carries only normalized Subject Identity, never
the opaque application Principal. Audit Provenance consumes it during planning,
and it survives in the Write Plan only where decoration materializes it as an
explicit planned audit value.

A Planned Write is a closed semantic execution unit and may cover one row or
multiple rows. Absence is structural: inserts and unversioned Non-Temporal
writes do not carry an invented no-observation value, while a locking mode that
deliberately omits an optimistic predicate is an explicit ungated decision.
Ordinary SQL lowering consumes only the Write Plan; it never interprets the
configured concurrency mode or a raw observation to rediscover semantics. The
planner resolves the attempt-scoped Transaction Instant only when surviving
work requires it and materializes the derived temporal and future audit values
into Planned Writes before freezing the plan. Write Plan retains neither the
Transaction Instant nor any other planning context beside its ordered
`steps: PlannedSteps`, an immutable logical `Sequence[PlannedWrite]`.
The same aggregate represents complete cancellation or no-op elimination with
an empty sequence; there is no separate empty-plan sentinel or result variant.

Resolving an observation-requiring predicate write produces one private compact
Materialized Write Group before the pure planning call. The group stores the
authored mutation, a shared primary-key shape, one immutable value column per
key attribute, and one closed observation-column variant:
`VersionColumns(versions)` or
`TemporalColumns(predecessors: PredecessorColumns,
transaction_time_basis)`. Predecessor Columns stores one complete shared row
shape plus aligned Attribute and Value Object columns; a Predecessor Row is a
logical view, not one eagerly allocated object per selected row. A predicate
materialization uses one Transaction-Time pin, so its Basis is group-wide and
cannot vary by selected row. Every key and observation value column has the
same positive row count. Because only observation-requiring writes use this
boundary, there is no observation-free variant. The group contains neither
managed Entity objects, one composite-key object per selected row, nor one
input wrapper per resolved row. Assignment-bearing materialization uses Unit
Work's structural equality rules as each cursor row arrives and retains only
effective rows, avoiding current-value comparison columns; delete and terminate
materialization retains every row. An empty or entirely no-op resolution
contributes no group. The planner retains or transfers immutable backing
columns instead of copying keys, predecessor state, or uniform assignments into
a parallel object graph.

The first Python materializer builds those value columns incrementally from the
database cursor as private immutable
`ChunkedColumn[T](chunks: tuple[tuple[T, ...], ...], length: int)` values. It
seals bounded chunks rather than retaining `fetchall()` row tuples, transposing
them into a second full-size structure, or performing one full-size
list-to-tuple copy. Private column slices retain a column plus bounds, so
planner segments share backing storage. The read-only column abstraction does
not expose this representation and permits later packed numeric columns without
changing the Write Plan contract.

The first Python implementation represents Planned Steps as a frozen, slotted,
segmented sequence whose private segments pack homogeneous runs. Iteration and
indexing expose logical Planned Write views as needed, and lowering may stream
those views. The public semantic contract is the immutable sequence, not a
concrete tuple or an eagerly allocated wrapper for every step. Planning memory
therefore scales with required row data and genuinely distinct plan segments,
not required row data plus simultaneous per-row input and output wrappers.

Compactness is an end-to-end planning invariant rather than a property of one
boundary type. Injected planning strategies accept compact segments and columns
and preserve structural sharing. Temporal expansion produces close and
successor segments instead of eager per-row Planned Close and Insert Entry
arrays. Audit Provenance decoration adds shared or columnar assignment overlays.
SQL lowering streams segment views and bind rows. A participant may allocate
necessary indexes, genuinely distinct values, and derived columns, but it may
not eagerly turn the logical row count into an equivalent object-wrapper graph.

Every Planned Write and nested target exposed by Planned Steps is an immutable,
stable logical view over segment storage and indices. Iteration never mutates
and reuses one flyweight object. Structural equality is meaningful, but object
identity is not guaranteed: repeated indexing may return equal distinct views,
and implementations need not cache them. Core consumers stream views; a caller
that deliberately retains every view owns the resulting wrapper memory. This
also makes a target retained by a Write Effect Error stable after iteration
continues.

The first implementation is memory-resident and does not include disk spilling.
The private read-only column abstraction keeps spilled or memory-mapped storage
substitutable later. Excluding retained input, genuinely derived output
columns, and necessary compact indexes, transient materialization and planning
memory is bounded by the active chunk builders and genuinely distinct segments
rather than by logical row count. COR-62 includes a synthetic large-write
allocation benchmark or equivalent regression check so an accidental return to
eager per-row wrappers is observable.

The alternative was to let batching, temporal planning, locking, audit
decoration, composition, and lowering share orchestration. Centralizing the
pipeline creates a deeper contract and prevents semantic decisions from
leaking into SQL generation, while injected ports preserve the behavioral
module DAG and keep the planner from owning those modules' rules.

## Amendment (2026-08): a Planning Request carries no observation map

The request shape recorded above carries "buffered writes, and observations" as
two independent fields, and the planner's stage list includes "target and
observation binding" — the planner resolving each surviving write's observation
out of a transaction-wide store keyed by the object the write addresses.

**Superseding decision:** the request carries **buffered writes only**, and a
buffered write against existing state travels **paired** with the one
observation resolved for it. The planner is handed evidence rather than a store
to search, and binding is no longer a planning stage. What remains at the same
position in the pipeline is *validation*: a required observation that is missing
is still a planning error raised there, before any gate is rendered.

The reason is that an observation cannot be resolved from what a Planning
Request holds. Evidence about a temporal row is evidence about **one milestone**,
and a milestone chain holds more than one row per primary key at a time, so
resolution needs the milestone the written value came from — which only the
caller holding that value knows. A store keyed by the object alone could not
express the distinction, and a keyed close resolved from it settled against
whichever milestone was read most recently.

Absence stays structural, as this ADR requires: a write with no observation is
buffered bare, so no no-observation value and no nullable observation field
exists at any point. A Materialized Write Group is unaffected — it already
carried its own aligned per-row evidence, which is the shape the keyed pairing
now mirrors.

Everything else recorded above is unchanged: the planner is still the sole
finalization authority, still stateless and pure, still resolves the Transaction
Instant lazily, and still emits one immutable `WritePlan`. Subject Identity
remains the first required field of the keyword-only request.

## Amendment (2026-08): a Materialized Write Group carries no Transaction-Time Basis

The Materialized Write Group shape recorded above stores
`TemporalColumns(predecessors: PredecessorColumns, transaction_time_basis)`,
with the accompanying reasoning that a predicate materialization uses one
Transaction-Time pin so its Basis is group-wide and cannot vary by selected row.

**Superseding decision:** the variant is `TemporalColumns(predecessors)`. The
Transaction-Time Basis is retired outright (ADR 0042's amendment), so the
group-wide-versus-per-row question it raised no longer arises.

Everything else about the group is unchanged: the authored mutation, the shared
primary-key shape, one immutable value column per key attribute, the closed
observation-column variant, equal positive row counts, no observation-free
variant, and the compactness invariants that follow.
