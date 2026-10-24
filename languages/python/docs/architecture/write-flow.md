# Write flow

> **Status:** a non-normative map of the current Python implementation. The
> [specification](../../../../core/spec/00-overview.md) and the
> [Python binding](../../spec/python.md) own behaviour; where this page and they
> disagree, they win. [The write flow](../../../../docs/concepts/write-flow.md)
> explains the same flow in domain terms.

This page follows one write through the code, from the verb you call to the statements
the database runs. Five diagrams cover it: which verb produces which admitted write,
what licenses each admitted write, how a verb reaches the buffer, how a flush turns the
buffer into statements, and the temporal view that lone and composed writes share.

Diagrams and prose use short names. The *Symbols* list closing each section names
every implementation symbol the section mentions by its defining module, as
`module:QualifiedName`.
[`check_architecture_references.py`](../../tools/check_architecture_references.py)
checks that each of those references names a declaration in that module; whether the
arrows between them are right is for review.

## Which verb produces which admitted write

`tx` is a `TxnContext` and `tx.wire` its `WireTransactionView`. Every verb reaches one
of four `TxnAttempt` methods.

```text
verb (Typed tx.* / Wire tx.wire.*)      TxnAttempt       the value handed in          admitted write
──────────────────────────────────────  ───────────────  ───────────────────────────  ────────────────────────
insert / wire.insert                    keyed_insert     a new instance or document   KeyedInsert

amend / replace / delete / terminate    keyed_write      a value a read of THIS
                                                         attempt published:
                                                           versioned or temporal      StateObservedWrite
                                                           unversioned Non-Temporal   ObjectLockedWrite
                                                         a value carrying a standing  InsertionAuthorizedWrite
                                                         insertion's authority: the
                                                         inserted instance, a value
                                                         derived from it, or the node
                                                         wire.insert answered

amend_if / replace_if /                 target_write     a key and the revision the   TargetWrite
  delete_if / terminate_if                               caller states

amend_where / replace_where /           predicate_write  a predicate                  none: executes at the
  delete_where                                                                        call (ADR 0077)
```

Representation adapters sit between the verb and the attempt: Typed and Wire keyed
sources and insert sources, target adapters and predicate adapters. Everything after
them is shared.

What an `InsertionAuthorizedWrite` becomes depends on whether its insert is still
buffered. Once the insert has flushed, the write revises the stored row. While it is
pending, admission folds the write into it: on a Non-Temporal or Transaction-Time-Only
object an amendment or replacement merges into the `KeyedInsert` and a destruction
cancels the pair, and on a Bitemporal object the write composes into a
`ComposedBitemporalOpening`. A read-authorized write of a Bitemporal object never folds
into that object's pending opening; it changes the coverage its read observed.

### Symbols

- `parallax.snapshot._handle._transaction:TxnContext`
- `parallax.snapshot._handle._transaction:TxnContext.insert`
- `parallax.snapshot._handle._transaction:TxnContext.amend`
- `parallax.snapshot._handle._transaction:TxnContext.replace`
- `parallax.snapshot._handle._transaction:TxnContext.delete`
- `parallax.snapshot._handle._transaction:TxnContext.terminate`
- `parallax.snapshot._handle._transaction:TxnContext.amend_if`
- `parallax.snapshot._handle._transaction:TxnContext.replace_if`
- `parallax.snapshot._handle._transaction:TxnContext.delete_if`
- `parallax.snapshot._handle._transaction:TxnContext.terminate_if`
- `parallax.snapshot._handle._transaction:TxnContext.amend_where`
- `parallax.snapshot._handle._transaction:TxnContext.replace_where`
- `parallax.snapshot._handle._transaction:TxnContext.delete_where`
- `parallax.snapshot._handle._wire:WireTransactionView`
- `parallax.snapshot._handle._wire:WireTransactionView.insert`
- `parallax.snapshot._handle._wire:WireTransactionView.amend`
- `parallax.snapshot._handle._wire:WireTransactionView.amend_if`
- `parallax.snapshot._handle._wire:WireTransactionView.amend_where`
- `parallax.snapshot._handle._typed_writes:TypedKeyedInsertSource`
- `parallax.snapshot._handle._typed_writes:TypedKeyedWriteSource`
- `parallax.snapshot._handle._typed_writes:TypedKeyTargetWriteAdapter`
- `parallax.snapshot._handle._typed_writes:TypedInstanceTargetWriteAdapter`
- `parallax.snapshot._handle._typed_writes:TypedPredicateWriteAdapter`
- `parallax.snapshot._handle._wire_writes:wire_insert`
- `parallax.snapshot._handle._wire_writes:wire_keyed_write`
- `parallax.snapshot._handle._wire_writes:WireKeyedInsertSource`
- `parallax.snapshot._handle._wire_writes:WireKeyedWriteSource`
- `parallax.snapshot._handle._wire_writes:WireTargetWriteAdapter`
- `parallax.snapshot._handle._wire_writes:WirePredicateWriteAdapter`
- `parallax.core._execution._transaction._attempt:TxnAttempt.keyed_insert`
- `parallax.core._execution._transaction._attempt:TxnAttempt.keyed_write`
- `parallax.core._execution._transaction._attempt:TxnAttempt.target_write`
- `parallax.core._execution._transaction._attempt:TxnAttempt.predicate_write`
- `parallax.core._execution._unit_work.write_items:KeyedInsert`
- `parallax.core._execution._unit_work.write_items:StateObservedWrite`
- `parallax.core._execution._unit_work.write_items:ObjectLockedWrite`
- `parallax.core._execution._unit_work.write_items:InsertionAuthorizedWrite`
- `parallax.core._execution._unit_work.write_items:TargetWrite`
- `parallax.core._execution._unit_work.write_items:ComposedBitemporalOpening`

## What licenses each admitted write

```text
admitted write            licensed by                      claim scope                     carries
────────────────────────  ───────────────────────────────  ──────────────────────────────  ──────────────────────────────
KeyedInsert               nothing: it opens a row          none                            the instruction (one row),
                                                                                           object_key (None where the
                                                                                           database computes the key)
StateObservedWrite        a read of this attempt: its      versioned Non-Temporal: the     instruction, object_key,
                          RetainedObservation (a version   observed state, or `current`,   retained_observation,
                          or Transaction-Time start);      the later state this attempt's  current, source_evidence
                          gated on it under Optimistic,    own updates left it at;
                          covered by the read's shared     temporal: none, composes by
                          lock under Locking               object
ObjectLockedWrite         the shared row lock a read of    the object                      instruction, object_key,
                          this attempt holds; the row                                      source_evidence
                          has no state to observe
InsertionAuthorizedWrite  this attempt's own insertion     versioned: the version this     instruction, object_key,
                          (InsertionIdentity), while it    attempt left the row at;        identity
                          still stands                     unversioned: the object;
                                                           temporal or still pending: none
TargetWrite               the caller's stated revision     versioned: the stated version;  instruction, object_key,
                          (ExpectedVersion or              temporal: the object, which     expectation, claim_scope,
                          ExpectedTxStart)                 composes by object              source_evidence, retained
```

`source_evidence` is a lifetime edge: it keeps the Read Evidence of every source whose
write composed into this one reachable while the write is pending or planned, and
nothing reads it for a decision. `retained` is the starting row a Locking temporal
target write's admission read whole, which its range may reuse
(`RetainedTargetState`).

`UnitOfWork.resolve_read_evidence` turns a source's `ReadEvidence` into what the write
settles against, the `SettledEvidence`, and `admitted_write` picks the leaf from its
shape: a `RetainedObservation` or a `VersionedObjectStateKey` makes a
`StateObservedWrite`, and an `ObjectKey` makes an `ObjectLockedWrite`. Evidence from
another participation is refused as `write-evidence-unavailable`, and evidence whose
state this attempt's own completed writes replaced or ended is refused as
`write-evidence-consumed`. The Effective Concurrency Strategy decides only what the
participating read must also prove: under Optimistic it must have retained an
observation.

### Symbols

- `parallax.core._execution._unit_work.write_items:KeyedInsert.object_key`
- `parallax.core._execution._unit_work.write_items:StateObservedWrite.retained_observation`
- `parallax.core._execution._unit_work.write_items:StateObservedWrite.current`
- `parallax.core._execution._unit_work.write_items:StateObservedWrite.claim_scope`
- `parallax.core._execution._unit_work.write_items:StateObservedWrite.source_evidence`
- `parallax.core._execution._unit_work.write_items:ObjectLockedWrite.claim_scope`
- `parallax.core._execution._unit_work.write_items:InsertionAuthorizedWrite.identity`
- `parallax.core._execution._unit_work.write_items:InsertionAuthorizedWrite.claim_scope`
- `parallax.core._execution._unit_work.write_items:TargetWrite.expectation`
- `parallax.core._execution._unit_work.write_items:TargetWrite.claim_scope`
- `parallax.core._execution._unit_work.write_items:TargetWrite.retained`
- `parallax.core._execution._unit_work.write_items:admitted_write`
- `parallax.core._execution._unit_work.retain:ReadEvidence`
- `parallax.core._execution._unit_work.retain:RetainedObservation`
- `parallax.core._execution._unit_work.retain:RetainedTargetState`
- `parallax.core._execution._unit_work.retain:InsertionIdentity`
- `parallax.core._execution._unit_work.claims:SettledEvidence`
- `parallax.core._execution._unit_work.instructions:ExpectedVersion`
- `parallax.core._execution._unit_work.instructions:ExpectedTxStart`
- `parallax.core._execution._unit_work.uow:UnitOfWork.resolve_read_evidence`
- `parallax.core.write_plan.keys:ObjectKey`
- `parallax.core.write_plan.keys:VersionedObjectStateKey`
- `parallax.core._execution._unit_work.admission:WriteEvidenceError`

## From verb to buffer

```text
 keyed: TxnAttempt.keyed_insert / keyed_write                                  _keyed_writes
   refuse_reentry → source.capture → source.resolve → ResolvedKeyedWriteSource
   → a standing insertion? UnitOfWork.insertion_authority(authoring)
   → validate_provenance → validate_source_pin → source_start (Bitemporal start)
   → source.prepare: keyed_instruction → KeyedWriteInstruction → prepare_*_write
     (an insert checks validate_source_pin before validate_provenance, and refuses a
      repeated insert after preparation)

 target: TxnAttempt.target_write                                               _attempt
   refuse_reentry → stated_valid_from → adapter.write_input
   → TargetWriteInstruction, its revision exactly as stated → prepare_*_write

 predicate: TxnAttempt.predicate_write
   refuse_reentry → adapter.prepare → prepare_*_write

 AUTHORED   WriteInstruction = KeyedWriteInstruction | PredicateWriteInstruction    instructions
              | TargetWriteInstruction: entity by name, rows unjudged;
              deserialize / serialize give its canonical document form (ADR 0024)
              │
              │ prepare_typed_write (coerce) / prepare_wire_write (decode)
              │ → _prepare_write: target, verb and window first, then payload
              ▼
 PREPARED   PreparedKeyedInstruction | PreparedTargetInstruction
              | PreparedPredicateInstruction: exact target, owned managed rows, judged
              window; PreparedInstruction names the keyed and predicate pair

 PreparedKeyedInstruction
   insert  → KeyedInsert(prepared, object_key) → UnitOfWork.buffer
   source  → licence: the standing insertion's identity, or
             UnitOfWork.resolve_read_evidence(...) → SettledEvidence
           → admitted_write(prepared, evidence, object_key, source= / authority=)
           → an amend assigning nothing stops here, after admission
           → UnitOfWork.buffer
 PreparedTargetInstruction
           → UnitOfWork.buffer_target: an amend assigning nothing stops here
           → target_write: keyed_instruction_from_target + the caller's expectation
           → WriteAdmission.admit
 PreparedPredicateInstruction
           → UnitOfWork.execute_predicate (next section); never buffered
              │
              ▼
 ADMITTED   AdmittedWrite = KeyedInsert | StateObservedWrite | ObjectLockedWrite     write_items
              | InsertionAuthorizedWrite | TargetWrite
              │
              │ WriteAdmission.admit: compose with what is pending, or refuse    admission
              │   insert                   opens an insertion and issues its
              │                            InsertionIdentity
              │   write of an object whose Non-Temporal or Transaction-Time-Only:
              │     insert is pending      an amendment merges into the KeyedInsert,
              │                            a destruction cancels the pair;
              │                            Bitemporal, insertion-authorized only:
              │                            → ComposedBitemporalOpening
              │   Non-Temporal write       at its claim scope, never by key alone:
              │                            coalesce, supersede or deduplicate (admits);
              │                            the survivor stays a leaf, a TargetWrite
              │                            over a read's, a read's over an insertion's
              │   temporal write           by object: the first stays its leaf type;
              │                            the next → ComposedTemporalWrite (or, for an
              │                            observed run of one observation and window,
              │                            compact_observed_run)
              │   target write             refused for an object this attempt
              │                            inserted; under Locking, confirm_target reads
              │                            its starting row unless a pending write or a
              │                            live read already proves it
              │   anything else            WriteEvidenceError
              │                            (write-evidence-already-claimed)
              ▼
 COMPOSED   WriteAdmission.composed_writes()
            ComposedWrite = AdmittedWrite | ComposedTemporalWrite
              | ComposedBitemporalOpening | PostRemovalInsert
```

Every refusal on this path happens at the verb, before anything is buffered, and leaves
the buffer and its claims as they were. A source's licence is decided before an empty
amendment is dropped, so stating nothing never lets an ineligible source through. A
target write's empty amendment is dropped before any condition is consulted.

`PostRemovalInsert` is not something admission builds while composing. It is the marker
`composed_writes` wraps around an insert, or an opening composed over one, whose
object's earlier insertion in this attempt the pending writes remove completely, so
ordering can run it after that removal. State that existed before the attempt is never
removed and reinserted this way.

### Symbols

- `parallax.core._execution._keyed_writes:keyed_write`
- `parallax.core._execution._keyed_writes:keyed_insert`
- `parallax.core._execution._keyed_writes:KeyedWriteSource`
- `parallax.core._execution._keyed_writes:KeyedWriteSource.capture`
- `parallax.core._execution._keyed_writes:KeyedWriteSource.resolve`
- `parallax.core._execution._keyed_writes:KeyedWriteSource.prepare`
- `parallax.core._execution._keyed_writes:KeyedInsertSource`
- `parallax.core._execution._keyed_writes:ResolvedKeyedWriteSource`
- `parallax.core._execution._keyed_writes:validate_provenance`
- `parallax.core._execution._keyed_writes:validate_source_pin`
- `parallax.core._execution._keyed_writes:source_start`
- `parallax.core._execution._keyed_writes:refuse_repeated_insert`
- `parallax.core._execution._keyed_writes:keyed_instruction`
- `parallax.core._execution._keyed_writes:stated_valid_from`
- `parallax.core.execution_lifecycle._activity:refuse_reentry`
- `parallax.core._execution._transaction._attempt:TargetWriteAdapter.write_input`
- `parallax.core._execution._transaction._attempt:PredicateWriteAdapter.prepare`
- `parallax.core._execution._unit_work.instructions:WriteInstruction`
- `parallax.core._execution._unit_work.instructions:KeyedWriteInstruction`
- `parallax.core._execution._unit_work.instructions:PredicateWriteInstruction`
- `parallax.core._execution._unit_work.instructions:TargetWriteInstruction`
- `parallax.core._execution._unit_work.instructions:deserialize`
- `parallax.core._execution._unit_work.instructions:serialize`
- `parallax.core._execution._unit_work.instructions:prepare_typed_write`
- `parallax.core._execution._unit_work.instructions:prepare_wire_write`
- `parallax.core._execution._unit_work.instructions:_prepare_write`
- `parallax.core._execution._unit_work.instructions:PreparedKeyedInstruction`
- `parallax.core._execution._unit_work.instructions:PreparedTargetInstruction`
- `parallax.core._execution._unit_work.instructions:PreparedPredicateInstruction`
- `parallax.core._execution._unit_work.instructions:PreparedInstruction`
- `parallax.core._execution._unit_work.instructions:keyed_instruction_from_target`
- `parallax.core._execution._unit_work.uow:UnitOfWork`
- `parallax.core._execution._unit_work.uow:UnitOfWork.insertion_authority`
- `parallax.core._execution._unit_work.uow:UnitOfWork.buffer`
- `parallax.core._execution._unit_work.uow:UnitOfWork.buffer_target`
- `parallax.core._execution._unit_work.uow:UnitOfWork._confirm_target`
- `parallax.core._execution._unit_work.write_items:target_write`
- `parallax.core._execution._unit_work.write_items:AdmittedWrite`
- `parallax.core._execution._unit_work.write_items:ComposedTemporalWrite`
- `parallax.core._execution._unit_work.write_items:compact_observed_run`
- `parallax.core._execution._unit_work.write_items:PostRemovalInsert`
- `parallax.core._execution._unit_work.write_items:ComposedWrite`
- `parallax.core._execution._unit_work.admission:WriteAdmission`
- `parallax.core._execution._unit_work.admission:WriteAdmission.admit`
- `parallax.core._execution._unit_work.admission:WriteAdmission.composed_writes`
- `parallax.core._execution._unit_work.claims:admits`

## From buffer to the database

```text
 flush triggers: UnitOfWork.read (read_dependency) · execute_predicate (predicate_write)
                 · TxnAttempt.complete (pre_commit)
              │
              ▼
 UnitOfWork.flush → _flush_buffer                                                   uow
   WritePlanner.finalize(WritePlanningRequest(actor_identity, transaction_instant,   write_planner
                         concurrency, composed_writes, ownership, ...))
     _without_noop_rows   drop known no-op work
     _form_batches        KeyedInsert runs → InsertBatch, ObjectLockedWrite runs
                          → ObjectLockedBatch; a PostRemovalInsert closes any batch
     _order               per region: inserts by referential rank, updates in authored
                          order, deletes by reverse rank; a PostRemovalInsert starts a
                          new region and is unwrapped
              ▼
 ORDERED    list[MutationPhase], MutationPhase = tuple[OrderedWrite, ...]
            OrderedWrite = AdmittedWrite | ComposedTemporalWrite
              | ComposedBitemporalOpening | InsertBatch | ObjectLockedBatch
              │
              │ WritePlanCompiler.compile: settle each write once                 write_settlement
              │   insert or Non-Temporal write  → its Planned Steps now
              │   temporal write or composition → settle_range                   ranges
              │   pending Bitemporal opening    → settle_opening
              │       → BoundRange (steps now) | DeferredTemporalRange (no step yet)
              │   group: consecutive settled writes of one phase over distinct
              │     objects, at most 64; a write the database allocates a key for,
              │     or naming no complete key, alone; effects before inserts
              │   a deferred write: an entry of its own; consecutive eligible ones
              │     are recorded as an AcquisitionSpan of at most 32
              ▼
 WritePlan(entries: WriteGroup | SettledWrite, acquisition_spans)                  write_plan
              │
              │ UnitOfWork._run_write_plan, entry by entry, in order               uow
              │   WriteGroup        → _execute_write_group
              │   deferred entry    → RangeBindings: complete retained starting rows,
              │     (or its span)     read uncovered coverage through acquire_rows,
              │                       bind each ready range → WriteGroup
              │                       → _execute_write_group; repeat
              │
              │ _execute_write_group
              │   execute_write_steps → WriteStepExecutor.execute                  _write_step_executor
              │     per step, at its turn: LayoutPayloadPreparer prepares the payload,
              │     compile_write_step lowers it, the connection executes it,
              │     enforce_affected_rows checks its count
              │   then _complete_write for each write, in order → WriteAdmission.complete
              ▼
 database

 predicate: UnitOfWork.execute_predicate
   an amendment or replacement assigning nothing → 0, no Flush
   otherwise, in a predicate_write Flush: _flush_buffer if anything is pending
     → WritePlanner.predicate_step → execute_counted_step
     → WriteStepExecutor.execute_with_count → the affected-row count
```

The unit of work runs no SQL itself. It is constructed with three ports,
`ExecuteWriteSteps`, `ExecuteCountedStep` and `AcquireRows`, which `TxnAttempt`
implements on the attempt's connection. Write steps and coverage reads run as calls
of the current Flush; a target write's starting-row read, made at its verb, is a Read
of its own.

Planning is pure: `finalize` performs no I/O and reads no clock, and the
`TransactionInstant` it threads is captured only when settlement reaches a surviving
temporal write. `UnitOfWork` hands the planner the buffer as admission composed it, so
the planner indexes nothing again, and `compile` returns the `WritePlan` that
`finalize` returns unchanged.

A deferred settled write is the one entry whose steps are not known at planning:
its window reaches coverage no planning input held. Its meaning, gates and instant are
fixed in its `DeferredTemporalRange`, and the flush reads the missing coverage when it
reaches the entry, inside the same Flush. Planned groups and deferred entries
interleave in plan order, and each group completes before any later group binds or
executes.

Completion publishes what a write did to later work. It invalidates every
`RetainedObservation` of a state the write changed, advances or ends the sources of the
states it updated or deleted, retires the owned rows it removed before registering the
rows it opened, and records what it left for the temporal sources that continue through
it. A failure while executing, binding or completing dooms the attempt; a refusal while
planning precedes execution and leaves the attempt usable.

The Storage Layout decides no write's meaning: instructions, admitted writes and
Planned Steps are Attribute-keyed. It is consulted only for physical work. Batching asks
`collapse_group_key` whether neighbouring rows select the same physical slots, Columns
and document paths, and so can share one statement. Settlement asks the model's
`LayoutPayloadPreparer` whether adjacent produced temporal rows store identical state,
which decides whether they merge. And at each step's turn the preparer places every
member in its Column or at its path in the shared Structured Column, and
`compile_write_step` renders the statement for the dialect.

### Symbols

- `parallax.core._execution._unit_work.uow:UnitOfWork.read`
- `parallax.core._execution._unit_work.uow:UnitOfWork.execute_predicate`
- `parallax.core._execution._unit_work.uow:UnitOfWork.flush`
- `parallax.core._execution._unit_work.uow:UnitOfWork._flush_buffer`
- `parallax.core._execution._unit_work.uow:UnitOfWork._run_write_plan`
- `parallax.core._execution._unit_work.uow:UnitOfWork._execute_write_group`
- `parallax.core._execution._unit_work.uow:UnitOfWork._complete_write`
- `parallax.core._execution._unit_work.write_runner:ExecuteWriteSteps`
- `parallax.core._execution._unit_work.write_runner:ExecuteCountedStep`
- `parallax.core._execution._unit_work.acquisition:AcquireRows`
- `parallax.core._execution._transaction._attempt:TxnAttempt._execute_write_steps`
- `parallax.core._execution._transaction._attempt:TxnAttempt._execute_counted_step`
- `parallax.core._execution._transaction._attempt:TxnAttempt._acquire_rows`
- `parallax.core._execution._unit_work.uow:FlushTrigger`
- `parallax.core._execution._transaction._attempt:TxnAttempt.complete`
- `parallax.core._execution._unit_work.write_planner:WritePlanner`
- `parallax.core._execution._unit_work.write_planner:WritePlanner.finalize`
- `parallax.core._execution._unit_work.write_planner:WritePlanner.predicate_step`
- `parallax.core._execution._unit_work.write_planner:WritePlanner._form_batches`
- `parallax.core._execution._unit_work.write_planner:WritePlanner._order`
- `parallax.core._execution._unit_work.write_planner:WritePlanningRequest`
- `parallax.core._execution._unit_work.write_planner:_without_noop_rows`
- `parallax.core._execution._unit_work.write_items:InsertBatch`
- `parallax.core._execution._unit_work.write_items:ObjectLockedBatch`
- `parallax.core._execution._unit_work.write_items:MutationPhase`
- `parallax.core._execution._unit_work.write_items:OrderedWrite`
- `parallax.core._execution._unit_work.write_settlement:WritePlanCompiler`
- `parallax.core._execution._unit_work.write_settlement:WritePlanCompiler.compile`
- `parallax.core._execution._unit_work.ranges:settle_range`
- `parallax.core._execution._unit_work.ranges:settle_opening`
- `parallax.core._execution._unit_work.ranges:DeferredTemporalRange`
- `parallax.core._execution._unit_work.ranges:RangeBindings`
- `parallax.core.write_plan.plan:BoundRange`
- `parallax.core.write_plan.plan:SettledWrite`
- `parallax.core.write_plan.plan:SettledWrite.deferred`
- `parallax.core.write_plan.plan:WriteGroup`
- `parallax.core.write_plan.plan:WriteGroup.writes`
- `parallax.core.write_plan.plan:WriteGroup.steps`
- `parallax.core.write_plan.plan:AcquisitionSpan`
- `parallax.core.write_plan.plan:WritePlan`
- `parallax.core.write_plan.plan:WritePlan.entries`
- `parallax.core.write_plan.plan:WritePlan.acquisition_spans`
- `parallax.core.write_plan.steps:PlannedStep`
- `parallax.core._execution._unit_work.clock:TransactionInstant`
- `parallax.core._execution._write_step_executor:WriteStepExecutor`
- `parallax.core._execution._write_step_executor:WriteStepExecutor.execute`
- `parallax.core._execution._write_step_executor:WriteStepExecutor.execute_with_count`
- `parallax.core.write_payload._preparer:LayoutPayloadPreparer`
- `parallax.core._execution._keyed_sql:collapse_group_key`
- `parallax.core.sql_gen._write:compile_write_step`
- `parallax.core._execution._unit_work.effects:enforce_affected_rows`
- `parallax.core._execution._unit_work.admission:WriteAdmission.complete`

## The temporal view shared by lone and composed writes

```text
StateObservedWrite        ─┐  a leaf alone: .intents and .transform derived when asked
InsertionAuthorizedWrite  ─┤
TargetWrite               ─┤  TemporalCoverageWrite
ComposedTemporalWrite     ─┘  composed: .intents and .transform retained
                                     │
                                     ▼
                       TemporalIntent =
                         StateObservedIntent        WriteIntent, retained_observation,
                                                    source_evidence
                       | InsertionAuthorizedIntent  WriteIntent (its window's start is
                                                    the insertion's anchor)
                       | TargetIntent               WriteIntent, expected: ExpectedTxStart,
                                                    retained
                       CoverageTransform = ordered, disjoint CoverageSegments
                                     │
                                     ▼
                       settle_range reads each intent by type:
                         StateObservedIntent        a predecessor: its observed milestone,
                                                    or, where its source continues through
                                                    this attempt's completed writes, the
                                                    current rows those writes left
                         TargetIntent               a condition on the coverage at its
                                                    window's start, and its retained row
                         InsertionAuthorizedIntent  the anchor that coverage must hold
                                     │
                                     ▼
                       predecessors cover the window? → bind now: PredecessorExpander
                       otherwise                      → DeferredTemporalRange
```

The three leaf types are not temporal-only: each also carries Non-Temporal writes. Only
when the target is Transaction-Time-Only or Bitemporal does settlement route the leaf
through `settle_range` and read its `intents` and `transform`.

The intent sequence keeps the authority and windows composition needs; it is not a
record of every authored write. An initial run of observed writes sharing one
observation and window compacts into one intent, and an equal target intent is kept
once. Two observations whose coverage overlaps cannot both be current: the
later-authored one is bound, and the earlier is validated alone. A pending Bitemporal
opening is a separate composition: its `intents` are bare `WriteIntent`s, and it settles
through `settle_opening`, which seeds every surviving part of its window from the
insert's own state.

`PredecessorExpander` applies the transform to each predecessor: whether it is reached,
whether it is unchanged and how that is proven, its close and gate, whether the attempt
owns it and so revises or removes it in place, and the successors it opens.

### Symbols

- `parallax.core._execution._unit_work.write_items:TemporalCoverageWrite`
- `parallax.core._execution._unit_work.write_items:StateObservedWrite.intents`
- `parallax.core._execution._unit_work.write_items:StateObservedWrite.transform`
- `parallax.core._execution._unit_work.write_items:InsertionAuthorizedWrite.intents`
- `parallax.core._execution._unit_work.write_items:TargetWrite.intents`
- `parallax.core._execution._unit_work.write_items:ComposedTemporalWrite.intents`
- `parallax.core._execution._unit_work.write_items:ComposedTemporalWrite.transform`
- `parallax.core._execution._unit_work.write_items:TemporalIntent`
- `parallax.core._execution._unit_work.write_items:StateObservedIntent`
- `parallax.core._execution._unit_work.write_items:InsertionAuthorizedIntent`
- `parallax.core._execution._unit_work.write_items:TargetIntent`
- `parallax.core._execution._unit_work.write_items:TargetIntent.expected`
- `parallax.core._execution._unit_work.write_items:TargetIntent.retained`
- `parallax.core._execution._unit_work.write_items:ComposedBitemporalOpening.intents`
- `parallax.core._execution._unit_work.claims:WriteIntent`
- `parallax.core.temporal_write.coverage:CoverageTransform`
- `parallax.core.temporal_write.coverage:CoverageSegment`
- `parallax.core._execution._unit_work.ranges:settle_range`
- `parallax.core._execution._unit_work.ranges:settle_opening`
- `parallax.core._execution._unit_work.ranges:DeferredTemporalRange`
- `parallax.core.temporal_write.expansion:PredecessorExpander`

## Where the contracts live

| Stage | Contract owner |
| -- | -- |
| Verbs, sources, contexts | [Python execution binding](../../spec/execution.md) |
| Write Instructions and preparation | [`m-unit-work`](../../../../core/spec/m-unit-work.md#write-instruction-vocabulary), [ADR 0024](../../../../docs/adr/0024-write-instructions-are-hosted-in-m-unit-work-and-cases-declare-compile-eligibility.md) |
| Provenance, licences, insertion authority, target writes | [`m-unit-work`](../../../../core/spec/m-unit-work.md#write-value-provenance), [ADR 0072](../../../../docs/adr/0072-source-writes-are-admitted-only-by-a-read-of-the-current-attempt.md) |
| Gates and versions | [`m-opt-lock`](../../../../core/spec/m-opt-lock.md), [`m-read-lock`](../../../../core/spec/m-read-lock.md) |
| Coalescing and composition | [`m-unit-work`](../../../../core/spec/m-unit-work.md#same-transaction-write-coalescing), [ADR 0023](../../../../docs/adr/0023-same-transaction-writes-coalesce-in-the-unit-of-work.md) |
| Batching and predicate writes | [`m-batch-write`](../../../../core/spec/m-batch-write.md), [ADR 0075](../../../../docs/adr/0075-predicate-writes-are-readless-only.md), [ADR 0077](../../../../docs/adr/0077-predicate-writes-execute-at-the-call-and-sources-continue-across-flushes.md) |
| Write Planner, stage order, Write Plan, Write Groups | [`m-unit-work`](../../../../core/spec/m-unit-work.md#write-finalization), [ADR 0041](../../../../docs/adr/0041-write-finalization-is-centralized-behind-a-typed-planner.md), [ADR 0076](../../../../docs/adr/0076-write-groups-run-every-effect-before-any-insert.md) |
| Planned Steps and State Observations | [`m-write-plan`](../../../../core/spec/m-write-plan.md), [ADR 0068](../../../../docs/adr/0068-the-planned-write-algebra-is-its-own-module.md) |
| Temporal expansion | [`m-temporal-write`](../../../../core/spec/m-temporal-write.md#temporal-expansion), [ADR 0042](../../../../docs/adr/0042-temporal-plans-retain-complete-predecessor-state-and-close-cause.md), [ADR 0045](../../../../docs/adr/0045-temporal-mutations-expand-in-place-after-ordering.md), [ADR 0069](../../../../docs/adr/0069-temporal-writes-settle-through-one-coverage-transform-and-predecessor-expansion.md) |
| Audit of produced rows | [ADR 0071](../../../../docs/adr/0071-audit-finalizes-represented-rows-before-their-realization-is-chosen.md) |
| Payloads and storage layout | [`m-write-payload`](../../../../core/spec/m-write-payload.md), [`m-storage-layout`](../../../../core/spec/m-storage-layout.md#storage-layout-transparency) |
| Flush execution and row acquisition | [`m-execution`](../../../../core/spec/m-execution.md#flush-execution) |
