# Write flow

> **Status:** a non-normative map of the current Python implementation. The
> [specification](../../../../core/spec/00-overview.md) and the
> [Python binding](../../spec/python.md) own behaviour; where this page and they
> disagree, they win. [The write flow](../../../../docs/concepts/write-flow.md)
> explains the same flow in domain terms.

This page follows one write through the code, from the verb you call to the statements
the database runs. Five diagrams cover it: which verb produces which admitted write,
what licenses each licensed write, how a verb reaches the buffer, how a flush turns the
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
──────────────────────────────────────  ───────────────  ───────────────────────────  ───────────────────────────────────
insert / wire.insert                    keyed_insert     a new instance or document   KeyedInsert

amend / replace / delete / terminate    keyed_write      a value a read of THIS
                                                         attempt published:
                                                           versioned or temporal      LicensedWrite[StateObserved]
                                                           unversioned Non-Temporal   LicensedWrite[UnversionedLocked]
                                                         a value carrying a standing  LicensedWrite[InsertionAuthorized]
                                                         insertion's authority: the
                                                         inserted instance, a value
                                                         derived from it, or the node
                                                         wire.insert answered

amend_if / replace_if /                 target_write     a key and the revision the   versioned:
  delete_if / terminate_if                               caller states                  LicensedWrite[VersionConditioned]
                                                                                      temporal:
                                                                                        LicensedWrite[TxStartConditioned]

amend_where / replace_where /           predicate_write  a predicate                  none: executes at the
  delete_where                                                                        call (ADR 0077)
```

Representation adapters sit between the verb and the attempt: Typed and Wire keyed
sources and insert sources, target adapters and predicate adapters. Everything after
them is shared.

Every admitted write but an insert is one `LicensedWrite`: the instruction, the object it
writes, and the `authority` that licenses it. What a write licensed by
`InsertionAuthorized` becomes depends on whether its insert is still buffered. Once the insert has flushed, the write revises the stored row. While it is
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
- `parallax.core._execution._unit_work.write_items:LicensedWrite`
- `parallax.core._execution._unit_work.write_items:LicensedWrite.authority`
- `parallax.core._execution._unit_work.write_items:StateObserved`
- `parallax.core._execution._unit_work.write_items:UnversionedLocked`
- `parallax.core._execution._unit_work.write_items:InsertionAuthorized`
- `parallax.core._execution._unit_work.write_items:VersionConditioned`
- `parallax.core._execution._unit_work.write_items:TxStartConditioned`
- `parallax.core._execution._unit_work.write_items:ComposedBitemporalOpening`

## What licenses each licensed write

A `KeyedInsert` needs no licence: it opens a row and claims nothing. Every other admitted
write is a `LicensedWrite` whose `authority` is one of five closed values. The authority's
fields are the stored licence; the record's `LicensedWrite.claim_scope` and
`LicensedWrite.source_evidence` are views of it.

```text
authority             licensed by                      claim scope                     authority holds
────────────────────  ───────────────────────────────  ──────────────────────────────  ──────────────────────────────
StateObserved         a read of this attempt: its      versioned Non-Temporal: the     retained_observation, current,
                      RetainedObservation (a version   observed state, or `current`,   source_evidence
                      or Transaction-Time start);      the later state this attempt's
                      gated on it under Optimistic,    own updates left it at;
                      covered by the read's shared     temporal: composes by object
                      lock under Locking
UnversionedLocked     the shared row lock a read of    the object                      source_evidence (never empty)
                      this attempt holds; the row
                      has no state to observe
InsertionAuthorized   this attempt's own insertion     versioned: the version this     identity, claim_scope
                      (InsertionIdentity), while it    attempt left the row at;
                      still stands                     unversioned: the object;
                                                       temporal or still pending: none
VersionConditioned    the caller's stated version      the stated version              expected, source_evidence
                      (ExpectedVersion)
TxStartConditioned    the caller's stated              the object, which composes by   expected, starting_row
                      Transaction-Time start           object
                      (ExpectedTxStart)
```

Preparation judges which condition a target write takes, and `target_write` maps that
judgment once. `source_evidence` is a lifetime edge: it keeps the Read Evidence of every
source whose write composed into this one reachable while the write is pending or
planned, and nothing reads it for a decision. Neither an insertion nor a
Transaction-Time start holds any. Planning carries it onto every `SettledWrite` and
`DeferredRange`, and binding carries a deferred range's onto the `SettledWrite` it
binds, so the sources stay published while the plan, or the Write Group running the
write, is reachable. `starting_row` is the starting row a Locking temporal target write's
admission read whole, which its range may reuse (`RetainedStartingRow`). Neither field
takes part in equality. Where the whole write, or a temporal intent holding its authority, must move on to a
signature taking only some licences, `is_licensed_by` narrows it, one authority class at
a time; a decision that needs only the licence matches on the authority.

The unit of work's `SourceRegistry` judges every licence. Its
`SourceRegistry.resolve_read_evidence` turns a source's `ReadEvidence` into what the
write settles against, the `SettledEvidence`, and `admitted_write` picks the authority from
its shape: a `RetainedObservation` or a `VersionedObjectStateKey` makes a
`StateObserved`, and an `ObjectKey` makes an `UnversionedLocked`. Evidence from
another participation is refused as `write-evidence-unavailable`. A source continues
through this attempt's own completed writes and settles against what they left of the
state it observed; `write-evidence-consumed` refuses only evidence published from rows a
read acquired before such a write changed them, and a source those writes ended: one
whose object a keyed deletion removed, or a temporal source whose observed state they
left nothing of at its Valid-Time pin. The Effective Concurrency Strategy decides only
what the participating read must also prove: under Optimistic it must have retained an
observation. An insertion's licence is the `InsertionIdentity` its insert was issued,
which `SourceRegistry.insertion_anchor` answers while that insertion stands: until
everything it opened is removed, or a later insertion of the object supersedes it.

### Symbols

- `parallax.core._execution._unit_work.write_items:KeyedInsert.object_key`
- `parallax.core._execution._unit_work.write_items:LicensedWrite.claim_scope`
- `parallax.core._execution._unit_work.write_items:LicensedWrite.source_evidence`
- `parallax.core._execution._unit_work.write_items:StateObserved.retained_observation`
- `parallax.core._execution._unit_work.write_items:StateObserved.current`
- `parallax.core._execution._unit_work.write_items:StateObserved.source_evidence`
- `parallax.core._execution._unit_work.write_items:UnversionedLocked.source_evidence`
- `parallax.core._execution._unit_work.write_items:InsertionAuthorized.identity`
- `parallax.core._execution._unit_work.write_items:InsertionAuthorized.claim_scope`
- `parallax.core._execution._unit_work.write_items:VersionConditioned.expected`
- `parallax.core._execution._unit_work.write_items:VersionConditioned.source_evidence`
- `parallax.core._execution._unit_work.write_items:TxStartConditioned.expected`
- `parallax.core._execution._unit_work.write_items:TxStartConditioned.starting_row`
- `parallax.core._execution._unit_work.write_items:is_licensed_by`
- `parallax.core._execution._unit_work.write_items:target_write`
- `parallax.core._execution._unit_work.write_items:admitted_write`
- `parallax.core._execution._unit_work.evidence:ReadEvidence`
- `parallax.core._execution._unit_work.evidence:RetainedObservation`
- `parallax.core._execution._unit_work.row_acquisition:RetainedStartingRow`
- `parallax.core._execution._unit_work.evidence:InsertionIdentity`
- `parallax.core._execution._unit_work.claims:SettledEvidence`
- `parallax.core._execution._unit_work.write_plan:SettledWrite.source_evidence`
- `parallax.core._execution._unit_work.ranges:DeferredRange.source_evidence`
- `parallax.core._execution._unit_work.instructions:ExpectedVersion`
- `parallax.core._execution._unit_work.instructions:ExpectedTxStart`
- `parallax.core._execution._unit_work.source_registry:SourceRegistry`
- `parallax.core._execution._unit_work.source_registry:SourceRegistry.resolve_read_evidence`
- `parallax.core._execution._unit_work.source_registry:SourceRegistry.insertion_anchor`
- `parallax.core.internal.planned_step.keys:ObjectKey`
- `parallax.core.internal.planned_step.keys:VersionedObjectStateKey`
- `parallax.core._execution._unit_work._errors:write_evidence_refusal`

## From verb to buffer

```text
 keyed: TxnAttempt.keyed_insert / keyed_write                                  _keyed_writes
   refuse_reentry → source.capture → source.resolve → ResolvedKeyedWriteSource
   → a standing insertion? SourceRegistry.insertion_anchor(insertion)
   → validate_provenance → validate_source_pin → source_start (Bitemporal start)
   → source.prepare: keyed_instruction → KeyedWriteInstruction → prepare_*_write
     (an insert checks validate_source_pin before validate_provenance; a repeated
      insert is refused as it is buffered, after preparation)

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
   insert  → InsertKeying (TxnAttempt._keyed): a row omitting a KeySequence key
             takes KeyAllocator.next_key, restated into the prepared row; a
             supplied key passes unchanged
           → KeyedInsert(prepared, object_key) → UnitOfWork.buffer_insert
           → WriteAdmission.admit_insert → the issued InsertionIdentity
           → OpenedKeyedWrite (allocated_key) → the source publishes the answer:
             TypedKeyedInsertSource.publish binds the identity to a keyed
             instance or calls inserted_value(..., insertion=...) to publish a
             new one from the row.
             WireKeyedInsertSource.publish renders the node from the row
   source  → licence: the standing insertion's identity, or
             SourceRegistry.resolve_read_evidence(...) → SettledEvidence
           → admitted_write(prepared, evidence, object_key, source= / insertion=)
           → an amend assigning nothing stops here, after admission
           → UnitOfWork.buffer → WriteAdmission.admit
 PreparedTargetInstruction
           → UnitOfWork.buffer_target: an amend assigning nothing stops here
           → target_write: keyed_instruction_from_target + the caller's expectation
           → WriteAdmission.admit
 PreparedPredicateInstruction
           → UnitOfWork.execute_predicate (next section); never buffered
              │
              ▼
 ADMITTED   AdmittedWrite = KeyedInsert | LicensedWrite[WriteAuthority]                write_items
              │
              │ WriteAdmission.admit / admit_insert: compose with what is        admission
              │   pending, or refuse; an insertion moves only through
              │   SourceRegistry transitions onto its WriteOwnership
              │   insert                   open_insertion issues an InsertionIdentity,
              │                            superseding an earlier insertion's; a repeat
              │                            of a standing insertion → UsageError
              │                            (write-value-already-stored)
              │   insertion-authorized     resolve_insertion_authorized_write: refused
              │     write                  once that insertion no longer stands; takes
              │                            the claim scope its stored row has
              │   write of an object whose Non-Temporal or Transaction-Time-Only:
              │     insert is pending      an amendment merges into the KeyedInsert,
              │                            a destruction cancels the pair;
              │                            Bitemporal, insertion-authorized only:
              │                            → ComposedBitemporalOpening;
              │                            apply_insertion_composition says whether
              │                            the insertion survives, ends or is cancelled
              │   Non-Temporal write       at its claim scope, never by key alone:
              │                            coalesce, supersede or deduplicate (admits);
              │                            the survivor keeps the higher licence, a
              │                            caller's condition over a read's, a read's
              │                            over an insertion's, and every source's
              │                            evidence (distinct_evidence)
              │   temporal write           by object: the first stays alone;
              │                            the next → ComposedTemporalWrite (or, for an
              │                            observed run of one observation and window,
              │                            compact_observed_run)
              │   target write             refused for an object this attempt
              │                            inserted (has_admitted_insertion); then,
              │                            unless a pending write or a live read
              │                            (has_live_observation) already proves it,
              │                            confirmed by its condition: under Locking
              │                            _confirm_version reads the stored version,
              │                            and _confirm_tx_start reads the starting
              │                            row whole and keeps it on the authority
              │   anything else            UsageError
              │                            (write-evidence-already-claimed)
              ▼
 COMPOSED   WriteAdmission.composed_writes()
            ComposedWrite = AdmittedWrite | ComposedTemporalWrite
              | ComposedBitemporalOpening | PostRemovalInsert
```

Every refusal on this path happens at the verb, before anything is buffered, and leaves
the buffer, its claims and every insertion as they were. A source's licence is decided
before an empty amendment is dropped, so stating nothing never lets an ineligible
source through. A target write's empty amendment is dropped before any condition is
consulted.

This composition begins the unit of work's
[planning pipeline](../../../../core/spec/m-unit-work.md#the-planning-pipeline):
admission resolves each write's object and coalesces it with the pending intent as the
write arrives, so the buffer only ever holds coalesced intent, and the Write Planner
owns the rest.

Admission owns the buffer and its claims, not an insertion's lifecycle. The
`SourceRegistry` keeps its `WriteOwnership` behind it, and that owner's
`InsertionRecord` for each object moves only through named transitions: opened at
`admit_insert`, composed as a write folds into its pending opening, stored once a flush
has planned the buffer holding it, and retired once everything it opened is removed:
by a whole removal that buffer held, or as completed writes report the rows they
removed (next section). A write an insertion authorized is checked against it again
at admission, because preparation runs caller code that can retire or supersede it.

A generated key is spent only once preparation has accepted the row, and before the
row names its object, so a refused row spends none and a failed allocation buffers
nothing. The `KeyAllocator` belongs to the root's `RootResources` and reaches each
attempt through the `TransactionRunner`; it keeps one `_Reservation` per physical
sequence and allocation settings, the binding's `ResolvedSequence` supplying both.
Handing out a key the reservation holds is a locked increment. When it runs out, the
attempt's `reservation_read` runs one reservation Read on the runtime's
`reservation_source`, with its own acquisition, statement and release, and the
allocator checks the live definition the statement returns before handing out the new
block. The answered value carries no Read Evidence, and no flush writes into it.

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
- `parallax.core._execution._keyed_writes:OpenedKeyedWrite`
- `parallax.core._execution._keyed_writes:OpenedKeyedWrite.allocated_key`
- `parallax.core._execution._keyed_writes:InsertKeying`
- `parallax.core._execution._transaction._attempt:TxnAttempt._keyed`
- `parallax.core._execution._key_allocation:KeyAllocator`
- `parallax.core._execution._key_allocation:KeyAllocator.next_key`
- `parallax.core._execution._key_allocation:_Reservation`
- `parallax.core._execution._root:RootResources`
- `parallax.core._execution._transaction._runner:TransactionRunner`
- `parallax.core._execution._connection_lifecycle:reservation_read`
- `parallax.core.internal.db_port._resources:DatabaseRuntime.reservation_source`
- `parallax.core.internal.database_binding._physical:ResolvedSequence`
- `parallax.snapshot._handle._typed_writes:TypedKeyedInsertSource.publish`
- `parallax.snapshot._handle._wire_writes:WireKeyedInsertSource.publish`
- `parallax.snapshot._publication._graph_view:inserted_value`
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
- `parallax.core._execution._unit_work.source_registry:SourceRegistry.insertion_anchor`
- `parallax.core._execution._unit_work.uow:UnitOfWork.buffer_insert`
- `parallax.core._execution._unit_work.uow:UnitOfWork.buffer`
- `parallax.core._execution._unit_work.uow:UnitOfWork.buffer_target`
- `parallax.core._execution._unit_work.uow:UnitOfWork._confirm_version`
- `parallax.core._execution._unit_work.uow:UnitOfWork._confirm_tx_start`
- `parallax.core._execution._unit_work.write_items:target_write`
- `parallax.core._execution._unit_work.write_items:AdmittedWrite`
- `parallax.core._execution._unit_work.write_items:WriteAuthority`
- `parallax.core._execution._unit_work.write_items:distinct_evidence`
- `parallax.core._execution._unit_work.write_items:ComposedTemporalWrite`
- `parallax.core._execution._unit_work.write_items:compact_observed_run`
- `parallax.core._execution._unit_work.write_items:PostRemovalInsert`
- `parallax.core._execution._unit_work.write_items:ComposedWrite`
- `parallax.core._execution._unit_work.admission:WriteAdmission`
- `parallax.core._execution._unit_work.admission:WriteAdmission.admit`
- `parallax.core._execution._unit_work.admission:WriteAdmission.admit_insert`
- `parallax.core._execution._unit_work.source_registry:SourceRegistry.open_insertion`
- `parallax.core._execution._unit_work.source_registry:SourceRegistry.resolve_insertion_authorized_write`
- `parallax.core._execution._unit_work.source_registry:SourceRegistry.apply_insertion_composition`
- `parallax.core._execution._unit_work.source_registry:SourceRegistry.has_admitted_insertion`
- `parallax.core._execution._unit_work.source_registry:SourceRegistry.has_live_observation`
- `parallax.core._execution._unit_work._write_ownership:WriteOwnership`
- `parallax.core._execution._unit_work._write_ownership:WriteOwnership.open_insertion`
- `parallax.core._execution._unit_work._write_ownership:InsertionRecord`
- `parallax.core._execution._unit_work._errors:KeyedWriteValueCode`
- `parallax.core._execution._unit_work.admission:WriteAdmission.composed_writes`
- `parallax.core._execution._unit_work.claims:admits`

## From buffer to the database

```text
 flush triggers: UnitOfWork.read (read_dependency) · execute_predicate (predicate_write)
                 · TxnAttempt.complete (pre_commit)
              │
              ▼
 UnitOfWork.flush → _flush_buffer                                                   uow
   SourceRegistry.planning_ownership(concluding: a pre_commit flush) → ownership
   WritePlanner.finalize(WritePlanningRequest(actor_identity, transaction_instant,   write_planner
                         concurrency, composed_writes, ownership, ...))
     FlushFacts           what every write this finalization settles shares: the    flush_facts
                          preference, instant, ownership, audit, guards, read keys
     _without_noop_rows   drop known no-op work
     collapse_writes      KeyedInsert runs → InsertBatch, LicensedWrite[UnversionedLocked]
                          runs → UnversionedWriteBatch; a PostRemovalInsert closes any
                          batch
     _mutation_phases     per region: inserts by referential rank, updates in authored
                          order, deletes by reverse rank; a PostRemovalInsert starts a
                          new region and is unwrapped
                          → MutationPhase = tuple[OrderedWrite, ...], in flush order
     each OrderedWrite, by its target's temporal shape, settles once:
       TemporalSettlement.settle                                                   temporal_settlement
         temporal write or composition → settle_range                              ranges
         pending Bitemporal opening    → settle_opening
         keyed insert                  → its opening, directly
       NonTemporalSettlement.settle                                                non_temporal_settlement
         insert, or update or delete of existing rows → its Planned Steps
       → SettledWrite (steps, effects, source_evidence) | DeferredRange (no step yet)
     _WritePlanBuilder
       add_settled    consecutive SettledWrites of one phase over distinct objects,
                      up to the group bound → WriteGroup.from_writes; effects before
                      inserts
       add_deferred   each unbroken run → form_spans → AcquisitionSpans          acquisition_spans
                      reading alike, each object once, up to the span bound
       close_phase    no group or span crosses a mutation phase
              ▼
 WritePlan(entries: WriteGroup | AcquisitionSpan)                                  write_plan
              │
              │ WriteAdmission.drain_planned: the buffer empties, and the          admission
              │   insertions it held are stored or retired
              │   (SourceRegistry.finish_insertion_planning)
              │
              │ UnitOfWork._run_write_plan, entry by entry, in order               uow
              │   WriteGroup        → _execute_write_group
              │   AcquisitionSpan   → write_groups: complete reusable            acquisition_spans
              │                       starting rows, read uncovered coverage
              │                       through acquire_rows, bind each ready
              │                       range → SettledWrite.from_bound
              │                       → WriteGroup.from_writes
              │                       → _execute_write_group; repeat
              │
              │ _execute_write_group
              │   execute_write_steps → WriteStepExecutor.execute                  _write_step_executor
              │     per step, at its turn: LayoutPayloadPreparer prepares the payload,
              │     compile_write_step lowers it, the connection executes it,
              │     enforce_affected_rows checks its count
              │   then, for each write in order,                                   source_registry
              │     SourceRegistry.complete_write → WriteOwnership.complete
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
the planner indexes nothing again and starts by dropping known no-op work in
`_without_noop_rows`. Write Settlement is one module per temporal profile, each built
once when the planner is wired over only the facets it reads. Every value one flush
shares reaches settlement in that finalization's `FlushFacts`, which no plan reaches.
`ConcurrencyFacet.gates` alone decides whether a write gates, for both settlement
modules and for `SourceRegistry.resolve_read_evidence`. Every settled write, whether
planned or bound at execution, is built by `SettledWrite.from_bound` from the
`BoundRange` binding answered, which is not kept.

```text
WritePlan
└ entries: WriteGroup | AcquisitionSpan        in execution order
   ├ WriteGroup       writes: SettledWrite …   one per ordered item, a batch included;
   │                                           each carries its own steps and effects
   │                  steps:  PlannedStep …    laid out across its writes; like effects
   │                                           share a statement
   └ AcquisitionSpan  ranges: DeferredRange …  a run's deferred writes, bound into
                                               WriteGroups at execution
```

A deferred write is the one write whose steps are not known at planning: its window
reaches coverage no planning input held. Its meaning, read key, gates, instant and
source evidence are fixed in its `DeferredRange`, and the flush reads the missing
coverage when it reaches the write's acquisition span, inside the same Flush. Planned
groups and spans interleave in plan order, and each group completes before any later
group binds or executes.

Completion publishes what a write did to later work, through the same
`SourceRegistry` that resolved the write's licence. It invalidates every
`RetainedObservation` of a state the write changed, advances or ends the sources of the
states it updated or deleted, retires the owned rows it removed before registering the
rows it opened, and records what it left for the temporal sources that continue through
it. A deferred write binds against the same facts: its span's `SpanWriteGroups` asks
`SourceRegistry.is_unchanged_since` whether a retained starting row is still current.
The pre-commit flush plans under a concluding view of the same ownership, which demands
nothing its writes leave, since no later write follows it. A failure while executing,
binding or completing dooms the attempt; a refusal while planning precedes execution
and leaves the attempt usable.

The Storage Layout decides no write’s meaning: instructions, admitted writes and
Planned Steps describe members. The planner’s `collapse_writes` compares neighbouring
writes and positional row presence, preserving distinct document-member shapes even
when those members share one physical column. Settlement asks the model’s
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
- `parallax.core._execution._unit_work.source_registry:SourceRegistry.planning_ownership`
- `parallax.core._execution._unit_work.source_registry:SourceRegistry.is_unchanged_since`
- `parallax.core._execution._unit_work.source_registry:SourceRegistry.complete_write`
- `parallax.core._execution._unit_work._write_ownership:WriteOwnership.complete`
- `parallax.core._execution._unit_work.admission:WriteAdmission.drain_planned`
- `parallax.core._execution._unit_work.source_registry:SourceRegistry.finish_insertion_planning`
- `parallax.core._execution._unit_work.write_runner:ExecuteWriteSteps`
- `parallax.core._execution._unit_work.write_runner:ExecuteCountedStep`
- `parallax.core._execution._unit_work.row_acquisition:AcquireRows`
- `parallax.core._execution._transaction._attempt:TxnAttempt._execute_write_steps`
- `parallax.core._execution._transaction._attempt:TxnAttempt._execute_counted_step`
- `parallax.core._execution._transaction._attempt:TxnAttempt._acquire_rows`
- `parallax.core._execution._unit_work.uow:FlushTrigger`
- `parallax.core._execution._transaction._attempt:TxnAttempt.complete`
- `parallax.core._execution._unit_work.write_planner:WritePlanner`
- `parallax.core._execution._unit_work.write_planner:WritePlanner.finalize`
- `parallax.core._execution._unit_work.write_planner:WritePlanner.predicate_step`
- `parallax.core._execution._unit_work.write_collapse:collapse_writes`
- `parallax.core._execution._unit_work.write_planner:WritePlanner._mutation_phases`
- `parallax.core._execution._unit_work.write_planner:WritePlanningRequest`
- `parallax.core._execution._unit_work.write_planner:_without_noop_rows`
- `parallax.core._execution._unit_work.write_items:InsertBatch`
- `parallax.core._execution._unit_work.write_items:UnversionedWriteBatch`
- `parallax.core._execution._unit_work.write_items:MutationPhase`
- `parallax.core._execution._unit_work.write_items:OrderedWrite`
- `parallax.core._execution._unit_work.flush_facts:FlushFacts`
- `parallax.core._execution._unit_work.flush_facts:FlushFacts.coverage_read_key`
- `parallax.core._execution._unit_work.temporal_settlement:TemporalSettlement`
- `parallax.core._execution._unit_work.temporal_settlement:TemporalSettlement.settle`
- `parallax.core._execution._unit_work.non_temporal_settlement:NonTemporalSettlement`
- `parallax.core._execution._unit_work.non_temporal_settlement:NonTemporalSettlement.settle`
- `parallax.core.internal.concurrency._facet:ConcurrencyFacet.gates`
- `parallax.core._execution._unit_work.write_planner:_WritePlanBuilder`
- `parallax.core._execution._unit_work.write_planner:_WritePlanBuilder.add_settled`
- `parallax.core._execution._unit_work.write_planner:_WritePlanBuilder.add_deferred`
- `parallax.core._execution._unit_work.write_planner:_WritePlanBuilder.close_phase`
- `parallax.core._execution._unit_work.ranges:settle_range`
- `parallax.core._execution._unit_work.ranges:settle_opening`
- `parallax.core._execution._unit_work.ranges:DeferredRange`
- `parallax.core._execution._unit_work.ranges:DeferredRange.read_key`
- `parallax.core._execution._unit_work.ranges:DeferredRange.bind`
- `parallax.core._execution._unit_work.acquisition_spans:form_spans`
- `parallax.core._execution._unit_work.acquisition_spans:AcquisitionSpan`
- `parallax.core._execution._unit_work.acquisition_spans:AcquisitionSpan.ranges`
- `parallax.core._execution._unit_work.acquisition_spans:write_groups`
- `parallax.core._execution._unit_work.acquisition_spans:SpanWriteGroups`
- `parallax.core._execution._unit_work.row_acquisition:CoverageReadKey`
- `parallax.core.internal.planned_step.write_effects:BoundRange`
- `parallax.core._execution._unit_work.write_plan:SettledWrite`
- `parallax.core._execution._unit_work.write_plan:SettledWrite.steps`
- `parallax.core._execution._unit_work.write_plan:SettledWrite.from_bound`
- `parallax.core._execution._unit_work.write_plan:WriteGroup`
- `parallax.core._execution._unit_work.write_plan:WriteGroup.writes`
- `parallax.core._execution._unit_work.write_plan:WriteGroup.steps`
- `parallax.core._execution._unit_work.write_plan:WriteGroup.from_writes`
- `parallax.core._execution._unit_work.write_plan:WritePlan`
- `parallax.core._execution._unit_work.write_plan:WritePlan.entries`
- `parallax.core._execution._unit_work.write_plan:PlanEntry`
- `parallax.core.internal.planned_step.steps:PlannedStep`
- `parallax.core._execution._unit_work.clock:TransactionInstant`
- `parallax.core._execution._write_step_executor:WriteStepExecutor`
- `parallax.core._execution._write_step_executor:WriteStepExecutor.execute`
- `parallax.core._execution._write_step_executor:WriteStepExecutor.execute_with_count`
- `parallax.core.internal.write_payload._preparer:LayoutPayloadPreparer`
- `parallax.core.internal.sql_gen._write:compile_write_step`
- `parallax.core._execution._unit_work.effects:enforce_affected_rows`

## The temporal view shared by lone and composed writes

```text
LicensedWrite[TemporalCoverageAuthority]  ─┐  alone: .intents and .transform derived
  StateObserved | InsertionAuthorized      │  when asked, its one intent holding
  | TxStartConditioned                     │  the write's own authority
                                           ├  TemporalCoverageWrite
ComposedTemporalWrite                     ─┘  composed: .intents and .transform retained
                                     │
                                     ▼
                       TemporalIntent[TemporalCoverageAuthority]
                         write_intent               WriteIntent: kind and window
                         authority                  the same authority object its
                                                    write was admitted under
                       CoverageTransform = ordered, disjoint CoverageSegments
                                     │
                                     ▼
                       settle_range reads each intent by its authority:
                         StateObserved              a predecessor: its observed milestone,
                                                    or, where its source continues through
                                                    this attempt's completed writes, the
                                                    current rows those writes left
                         TxStartConditioned         a condition on the coverage at its
                                                    window's start, and its starting row
                         InsertionAuthorized        the anchor that coverage must hold
                                     │
                                     ▼
                       predecessors cover the window? → bind now: PredecessorExpander
                       otherwise                      → DeferredRange
```

`StateObserved` and `InsertionAuthorized` also license Non-Temporal writes, and a
`TxStartConditioned` write is always temporal. Only when the target is
Transaction-Time-Only or Bitemporal does settlement route the write through
`settle_range` and read its `intents` and `transform`, which only a write whose
authority is a `TemporalCoverageAuthority` answers.

The intent sequence keeps the authority and windows composition needs; it is not a
record of every authored write. Admission turns an arriving temporal write into its
intent before judging it, so every judgment against the pending writes compares intents
on both sides, and composition keeps that same intent. An initial run of observed writes
sharing one observation and window compacts into one intent, and a caller's condition
equal to one already held over the same window and start is kept once. Two observations whose coverage overlaps cannot both be current: the
later-authored one is bound, and the earlier is validated alone. A pending Bitemporal
opening is a separate composition: its `intents` are bare `WriteIntent`s, and it settles
through `settle_opening`, which seeds every surviving part of its window from the
insert's own state.

`PredecessorExpander` applies the transform to each predecessor: whether it is reached,
whether it is unchanged and how that is proven, its close and gate, whether the attempt
owns it and so revises or removes it in place, and the successors it opens.

### Symbols

- `parallax.core._execution._unit_work.write_items:TemporalCoverageWrite`
- `parallax.core._execution._unit_work.write_items:TemporalCoverageAuthority`
- `parallax.core._execution._unit_work.write_items:LicensedWrite.intents`
- `parallax.core._execution._unit_work.write_items:LicensedWrite.transform`
- `parallax.core._execution._unit_work.write_items:ComposedTemporalWrite.intents`
- `parallax.core._execution._unit_work.write_items:ComposedTemporalWrite.transform`
- `parallax.core._execution._unit_work.write_items:TemporalIntent`
- `parallax.core._execution._unit_work.write_items:TemporalIntent.write_intent`
- `parallax.core._execution._unit_work.write_items:TemporalIntent.authority`
- `parallax.core._execution._unit_work.write_items:ComposedBitemporalOpening.intents`
- `parallax.core._execution._unit_work.claims:WriteIntent`
- `parallax.core.internal.temporal_write.coverage:CoverageTransform`
- `parallax.core.internal.temporal_write.coverage:CoverageSegment`
- `parallax.core._execution._unit_work.ranges:settle_range`
- `parallax.core._execution._unit_work.ranges:settle_opening`
- `parallax.core._execution._unit_work.ranges:DeferredRange`
- `parallax.core.internal.temporal_write.expansion:PredecessorExpander`

## Where the contracts live

| Stage | Contract owner |
| -- | -- |
| Verbs, sources, contexts | [Python execution binding](../../spec/execution.md) |
| Write Instructions and preparation | [`m-unit-work`](../../../../core/spec/m-unit-work.md#write-instruction-vocabulary), [ADR 0024](../../../../docs/adr/0024-write-instructions-are-hosted-in-m-unit-work-and-cases-declare-compile-eligibility.md) |
| Provenance, licences, insertion authority, target writes | [`m-unit-work`](../../../../core/spec/m-unit-work.md#write-value-provenance), [ADR 0072](../../../../docs/adr/0072-source-writes-are-admitted-only-by-a-read-of-the-current-attempt.md) |
| Gates and versions | [`m-concurrency`](../../../../core/spec/m-concurrency.md) |
| Coalescing and composition | [`m-unit-work`](../../../../core/spec/m-unit-work.md#same-transaction-write-coalescing), [ADR 0023](../../../../docs/adr/0023-same-transaction-writes-coalesce-in-the-unit-of-work.md) |
| Readless predicate writes | [`m-batch-write`](../../../../core/spec/m-batch-write.md), [ADR 0075](../../../../docs/adr/0075-predicate-writes-are-readless-only.md), [ADR 0077](../../../../docs/adr/0077-predicate-writes-execute-at-the-call-and-sources-continue-across-flushes.md) |
| Write Planner, planning order, Write Plan, Write Groups | [`m-unit-work`](../../../../core/spec/m-unit-work.md#write-finalization), [ADR 0041](../../../../docs/adr/0041-write-finalization-is-centralized-behind-a-typed-planner.md), [ADR 0076](../../../../docs/adr/0076-write-groups-run-every-effect-before-any-insert.md), [ADR 0080](../../../../docs/adr/0080-write-groups-hold-up-to-1024-settled-writes.md) |
| Planned Steps and State Observations | [`m-planned-step`](../../../../core/spec/m-planned-step.md), [ADR 0068](../../../../docs/adr/0068-the-planned-write-algebra-is-its-own-module.md) |
| Temporal expansion | [`m-temporal-write`](../../../../core/spec/m-temporal-write.md#temporal-expansion), [ADR 0042](../../../../docs/adr/0042-temporal-plans-retain-complete-predecessor-state-and-close-cause.md), [ADR 0045](../../../../docs/adr/0045-temporal-mutations-expand-in-place-after-ordering.md), [ADR 0069](../../../../docs/adr/0069-temporal-writes-settle-through-one-coverage-transform-and-predecessor-expansion.md) |
| Audit of produced rows | [ADR 0071](../../../../docs/adr/0071-audit-finalizes-represented-rows-before-their-realization-is-chosen.md) |
| Payloads and storage layout | [`m-write-payload`](../../../../core/spec/m-write-payload.md), [`m-storage-layout`](../../../../core/spec/m-storage-layout.md#storage-layout-transparency) |
| Flush execution and row acquisition | [`m-execution`](../../../../core/spec/m-execution.md#flush-execution) |
