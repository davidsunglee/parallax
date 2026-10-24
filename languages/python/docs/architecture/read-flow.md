# Read flow

> **Status:** a non-normative map of the current Python implementation. The
> [specification](../../../../core/spec/00-overview.md) and the
> [Python binding](../../spec/python.md) own behaviour; where this page and they
> disagree, they win. [The read flow](../../../../docs/concepts/read-flow.md)
> explains the same flow in domain terms.

This page follows one read through the code, from the method you call to the values
you get back. Four diagrams cover it: which public surface enters which read, how a
query becomes a judged Page, how a Page becomes Typed or Wire values, and where eager,
milestone-set and streamed delivery part ways.

Diagrams and prose use short names. The *Symbols* list closing each section names
every implementation symbol the section mentions by its defining module, as
`module:QualifiedName`.
[`check_architecture_references.py`](../../tools/check_architecture_references.py)
checks that each of those references names a declaration in that module; whether the
arrows between them are right is for review.

## Which public surface enters which read

`root` is a `Database`, `db` a `ScopedDatabase`, `rtx` a `ReadOnlyTxnContext` and `tx`
a `TxnContext`.

```text
Database (root) — owns, through RootResources, the runtime, the Serving Model, the
  │               ReadPlanCache and the TransactionRunner, once for every scope
  ├ using_database_login()
  └ using_principal(principal)
            │
            ▼
     ScopedDatabase (db) — wraps one ExecutionScope
       ├ db.find / db.stream / db.wire.find / db.wire.stream / db.read_rows
       │     → ExecutionScope → a StandaloneRead per operation
       ├ db.read_only(fn) → TransactionRunner.read_only
       │     → ReadOnlyTxnAttempt per attempt → read_only_context_for → rtx → fn(rtx)
       └ db.transact(fn)  → TransactionRunner.transact
             → TxnAttempt per attempt         → transaction_for       → tx  → fn(tx)

rtx.find / rtx.stream / rtx.wire.* / rtx.read_rows → the ReadOnlyTxnAttempt
 tx.find /  tx.stream /  tx.wire.* /  tx.read_rows → the TxnAttempt

public spelling     captured as (convert_query)                publication           graph execution
──────────────────  ─────────────────────────────────────────  ────────────────────  ───────────────────────
Typed find/stream   ObjectQuery → typed_read_query             typed_publication_for read_graph /
                      → AuthoredQuery                                                StreamDelivery
Wire find/stream    mapping → deserialize → ObjectQueryNode    wire_publication_for  read_graph /
                    ObjectQueryNode → itself                                         StreamDelivery
                    ObjectQuery → typed_read_query
                      → AuthoredQuery
read_rows           ObjectQueryNode                            none                  read_rows → find_rows
```

The root selects authority and derives option aliases; it runs no read itself. The
runner constructs each attempt inside the port's transaction callback and only then
builds the context the callback receives, so a callback never sees a half-wired
attempt. A retry constructs a fresh attempt; a joining call reuses the active one.

`ExecutionScope` never looks for an active transaction, so calling `db.find` inside a
callback still runs a standalone read on its own connection. The three lane objects —
`StandaloneRead`, `ReadOnlyTxnAttempt` and `TxnAttempt` — all satisfy one protocol,
`BegunRead`, which supplies the bracket a read runs inside; everything after the
capture is the same code for every lane and both representations. Typed and Wire graph
reads both plan with `result_form="instance"`. The row-form lane is separate: it
publishes plain rows and no graph, and Wire is not built on it.

### Symbols

- `parallax.snapshot._handle._database:Database`
- `parallax.snapshot._handle._database:ScopedDatabase`
- `parallax.snapshot._handle._database:ScopedDatabase.find`
- `parallax.snapshot._handle._database:ScopedDatabase.stream`
- `parallax.snapshot._handle._database:ScopedDatabase.wire`
- `parallax.snapshot._handle._database:ScopedDatabase.read_rows`
- `parallax.snapshot._handle._database:ScopedDatabase.read_only`
- `parallax.snapshot._handle._database:ScopedDatabase.transact`
- `parallax.core._execution._root:DatabaseRoot.using_database_login`
- `parallax.core._execution._root:DatabaseRoot.using_principal`
- `parallax.core._execution._root:RootResources`
- `parallax.core.read_delivery._read_plan:ReadPlanCache`
- `parallax.core._execution._transaction._runner:TransactionRunner.transact`
- `parallax.core._execution._transaction._runner:TransactionRunner.read_only`
- `parallax.core._execution._scope:ExecutionScope`
- `parallax.core._execution._read_policy:StandaloneRead`
- `parallax.core._execution._read_policy:BegunRead`
- `parallax.core._execution._transaction._attempt:ReadOnlyTxnAttempt`
- `parallax.core._execution._transaction._attempt:TxnAttempt`
- `parallax.snapshot._handle._transaction:ReadOnlyTxnContext`
- `parallax.snapshot._handle._transaction:ReadOnlyTxnContext.find`
- `parallax.snapshot._handle._transaction:ReadOnlyTxnContext.stream`
- `parallax.snapshot._handle._transaction:ReadOnlyTxnContext.wire`
- `parallax.snapshot._handle._transaction:ReadOnlyTxnContext.read_rows`
- `parallax.snapshot._handle._transaction:TxnContext`
- `parallax.snapshot._handle._transaction:TxnContext.find`
- `parallax.snapshot._handle._transaction:TxnContext.stream`
- `parallax.snapshot._handle._transaction:TxnContext.wire`
- `parallax.snapshot._handle._transaction:TxnContext.read_rows`
- `parallax.snapshot._handle._transaction:read_only_context_for`
- `parallax.snapshot._handle._transaction:transaction_for`
- `parallax.snapshot._handle._wire:WireDatabaseView`
- `parallax.snapshot._handle._wire:WireDatabaseView.find`
- `parallax.snapshot._handle._wire:WireDatabaseView.stream`
- `parallax.snapshot._handle._wire:WireTransactionView`
- `parallax.snapshot._handle._wire:wire_read_query`
- `parallax.core.object_query._fluent:ObjectQuery`
- `parallax.core.object_query._fluent:typed_read_query`
- `parallax.core.entity._expressions:AuthoredQuery`
- `parallax.core.object_query._nodes:ObjectQueryNode`
- `parallax.core.object_query.serde:deserialize`
- `parallax.snapshot._handle._read:typed_publication_for`
- `parallax.snapshot._handle._read:wire_publication_for`
- `parallax.core._execution._read_policy:read_graph`
- `parallax.core._execution._read_policy:read_rows`
- `parallax.core.read_delivery._row_lane:find_rows`
- `parallax.core.read_delivery._stream:StreamDelivery`

## From query spelling to a judged Page

An eager graph read, from the lane's entry point to the sealed Page:

```text
 ExecutionScope.read / ReadOnlyTxnAttempt.read / TxnAttempt.read
   │ refuse_reentry
   │ the read's selection: ExecutionScope.begin adopts one (AdoptedExecution)
   │   → SelectedReadModel; an attempt reuses the one it adopted at open
   │ build_publication(selected) → SnapshotPublication
   │   (typed_publication_for refuses a selection with no EntityGraphConstruction)
   │ convert_query(query) → ReadQuery: AuthoredQuery | ObjectQueryNode
   ▼
 read_graph(read, query, publication, planner)                          _read_policy
   │ interpreted(selected, query)
   │   ObjectQueryNode → itself
   │   AuthoredQuery   → InterpretedQuery + typed_interpretation
   ▼
 preflight(..., form="graph")                                           _preflight
   │ resolve the target → validate_object_query → refuse deferred_features
   ▼
 ResolvedObjectQuery
   │ BegunRead.eager — the lane's bracket, entered only after the gate:
   │   StandaloneRead      open the Read root, then lease this operation's connection
   │   ReadOnlyTxnAttempt  TxnAttemptLifetime.ensure_open, Read activity, attempt's connection
   │   TxnAttempt          UnitOfWork.read flushes pending writes, Read activity,
   │                       attempt's connection
   │ → ReadInputs(connection, preference, evidence_context)
   ▼
 scanned As-Of Axis? → deliver_history (next sections); otherwise
 deliver_find(EagerPageRequest(..., origin collector, ...), publication)  _delivery
   ▼
 PageReader.read_page                                                   _page_reader
   │ ReadPlanner.plan(edition, model, dialect, query, result_form="instance", preference)
   ▼
 ReadPlanCache: hit → reuse; miss → build below, once per key            _read_plan
   ├ deep_fetch.plan → ObjectQueryPlan
   │     root: PlannedEntityQuery
   │     includes: IncludeTree
   │     fetch_steps: QueryFetchStep | BackReferenceFetchStep
   ├ entity_read_lock(meta, entity, preference) for the root and each query fetch step
   ├ compile_read(root) / compile_template(each query fetch step)        sql_gen._compile
   │     resolve storage layout, inheritance and physical reads; append the lock
   ├ bind(model, result_contract, projection) → a ReadRowConverter per compiled read
   └ ReadPlan: compiled root + fetch work + converters + ViewSchema
   │ rendered for this query: a stream page's cap and seek coordinate are bound
   ▼
 execute_read(connection, CompiledRead, calls)                          _fetch
   LoweredStatement + document-read ordinals → driver SQL → DatabaseConnection.execute
   ▼
 driver rows
   ▼
 ReadRowConverter.convert_row → PageBuilder                             _row_converter
   resolve the concrete Entity and each member's source (Column or document);
   register the identity claim; leave payload judgement until it is needed;
   the origin collector observes each projection
   ▼
 each round of ready fetch steps (ReadPlan.ready_fetches):
   guarded_parents → gather_keys → CompiledTemplate.render(keys)
   one statement: execute_read; several: DatabaseConnection.execute_pipeline
   convert rows → attach_children / attach_back_reference / attach_empty
   ▼
 PageBuilder.finish(root refs, query pin)
   ▼
 EagerPageResult(page, includes, origins = collector.origins_for(page))
```

The gate runs before the bracket, so a query the model refuses opens no activity,
acquires no connection and flushes nothing. A stream crosses the same gate once, when
it is entered, through `ExecutionScope.resolved` or the attempt's `resolved`.

A `CompiledRead` carries its statement, the resolved concrete position, the
`ResolvedReadProjection`, the document-read ordinals and the `ReadResultContract`
together, and `bind` builds the converter from that same contract and projection. The
compiler and the converter therefore resolve each member's placement from one storage
layout facet, which is why nothing above this stage knows whether an Entity is stored
in Columns or as a document. A position with no concrete subtype compiles to `EmptyRead`
and executes no statement.

`entity_read_lock` returns no lock when there is no Concurrency Preference, which is
the case for every standalone and read-only read; inside a writable attempt each level
derives its own lock from its own Entity.

`ReadPlanCache` (owned once by `RootResources`) keeps the reusable planning products
and nothing else: no Page, result, connection, evidence or publication. Its key is the
Model Edition, model, dialect, result form and Concurrency Preference together with the
whole resolved query, literal operands included; only a stream page's cap and seek
coordinate are left out, and they are bound when a cached plan is rendered. A miss
whose key differs from a cached plan's only in its page shape reuses that plan's fetch
work and plans only the root. `UNCACHED_READ_PLANNER` is a zero-capacity cache, so
uncached planning builds the same products through the same code. Validation and read
admission stay outside the cache.

### Symbols

- `parallax.core._execution._scope:ExecutionScope.read`
- `parallax.core._execution._scope:ExecutionScope.begin`
- `parallax.core._execution._scope:ExecutionScope.resolved`
- `parallax.core._execution._transaction._attempt:_TxnAttemptBase.read`
- `parallax.core._execution._transaction._attempt:_TxnAttemptBase.resolved`
- `parallax.core.execution_lifecycle._activity:refuse_reentry`
- `parallax.core._execution._adoption:AdoptedExecution`
- `parallax.core._execution._publication:SelectedReadModel`
- `parallax.snapshot._handle._read:SnapshotPublication`
- `parallax.core.entity._graph_construction:EntityGraphConstruction`
- `parallax.core._execution._read_policy:ReadQuery`
- `parallax.core._execution._read_policy:interpreted`
- `parallax.core.object_query._nodes:InterpretedQuery`
- `parallax.core.entity._authored_resolver:typed_interpretation`
- `parallax.core._execution._preflight:preflight`
- `parallax.core.object_query.validate:validate_object_query`
- `parallax.core._execution._features:deferred_features`
- `parallax.core.object_query._resolved:ResolvedObjectQuery`
- `parallax.core._execution._read_policy:BegunRead.eager`
- `parallax.core._execution._transaction._lifetime:TxnAttemptLifetime.ensure_open`
- `parallax.core._execution._unit_work.uow:UnitOfWork.read`
- `parallax.core._execution._read_policy:ReadInputs`
- `parallax.core._execution._read_policy:ReadInputs.connection`
- `parallax.core._execution._read_policy:ReadInputs.preference`
- `parallax.core._execution._read_policy:ReadInputs.evidence_context`
- `parallax.core.read_delivery._delivery:deliver_find`
- `parallax.core.read_delivery._delivery:deliver_history`
- `parallax.core.read_delivery._page_reader:EagerPageRequest`
- `parallax.core.read_delivery._page_reader:PageReader.read_page`
- `parallax.core.read_delivery._read_plan:ReadPlanner.plan`
- `parallax.core.read_delivery._read_plan:ReadPlanCache`
- `parallax.core.read_delivery._read_plan:UNCACHED_READ_PLANNER`
- `parallax.core.deep_fetch:plan`
- `parallax.core.deep_fetch:ObjectQueryPlan`
- `parallax.core.deep_fetch:ObjectQueryPlan.root`
- `parallax.core.deep_fetch:ObjectQueryPlan.includes`
- `parallax.core.deep_fetch:ObjectQueryPlan.fetch_steps`
- `parallax.core.deep_fetch:PlannedEntityQuery`
- `parallax.core.deep_fetch._include_tree:IncludeTree`
- `parallax.core.deep_fetch:QueryFetchStep`
- `parallax.core.deep_fetch:BackReferenceFetchStep`
- `parallax.core.deep_fetch:ResolvedReadProjection`
- `parallax.core.read_delivery._fetch:entity_read_lock`
- `parallax.core.sql_gen._compile:compile_read`
- `parallax.core.sql_gen._compile:compile_template`
- `parallax.core.sql_gen._compile:CompiledRead`
- `parallax.core.sql_gen._compile:CompiledTemplate.render`
- `parallax.core.sql_gen._inheritance:ReadResultContract`
- `parallax.core.read_delivery._row_converter:bind`
- `parallax.core.read_delivery._row_converter:ReadRowConverter`
- `parallax.core.read_delivery._row_converter:ReadRowConverter.convert_row`
- `parallax.core.read_delivery._read_plan:ReadPlan`
- `parallax.core.read_delivery._read_plan:ReadPlan.ready_fetches`
- `parallax.core.read_delivery._read_plan:EmptyRead`
- `parallax.core.read_delivery._page._views:ViewSchema`
- `parallax.core.read_delivery._fetch:execute_read`
- `parallax.core.sql_gen._context:LoweredStatement`
- `parallax.core.db_port:DatabaseConnection.execute`
- `parallax.core.db_port:DatabaseConnection.execute_pipeline`
- `parallax.core.read_delivery._page._rows:PageBuilder`
- `parallax.core.read_delivery._page._rows:PageBuilder.finish`
- `parallax.core.read_delivery._fetch:guarded_parents`
- `parallax.core.read_delivery._fetch:gather_keys`
- `parallax.core.read_delivery._fetch:attach_children`
- `parallax.core.read_delivery._fetch:attach_back_reference`
- `parallax.core.read_delivery._fetch:attach_empty`
- `parallax.core.read_delivery._page_reader:EagerPageResult`
- `parallax.core.read_delivery._page_reader:PageOriginCollector.origins_for`
- `parallax.core._execution._root:RootResources`

## From Page to application values

```text
 EagerPageResult / HistoryPageResult / StreamPageResult (Page + IncludeTree + origins)
              │
              ▼
 SnapshotPublication.roots_of(page, includes, atomic, origins, milestones)  _handle/_read
              │   a milestone root's pin comes from its own edge
              ▼
 publish_roots → one transient RootView per Page root                   _root_publication
              ├ eager (atomic): RootView.complete → RootView.prime(origins)
              │                 → release Page rows after their last use
              │                 → publish every root, then hand them all over
              └ stream:         RootView → release raw rows → publish and hand over
                                each root in turn
              │
              ▼
 typed_root / wire_roots                                                _typed / _wire
              ├ classify_roots: a conforming root, or an InvalidData record
              ├ Read Evidence reaches the nodes of a conforming root only
              ├ Typed: EntityGraphConstruction → frozen Entity instances
              └ Wire:  WireWalk along the requested Include Paths
                        → frozen WireEntity mappings
              │
              ▼
 conforming value | InvalidData[value]
              ├ eager: from_find / from_history → Snapshot[T] / Snapshot[WireEntity]
              │          result() and results() raise InvalidDataError for an invalid root;
              │          checked() → CheckedSnapshot, with InvalidData in band
              └ stream: SnapshotStream iteration raises InvalidDataError at an invalid
                         root; SnapshotStream.checked yields InvalidData in band
```

A Root View is one root's view over the Page. Within it, one logical row is one node,
so a diamond of include paths shares a node and following a relationship never reads.
Two roots never share a node object, even when they reached the same Entity State.

The eager path publishes nothing until every root is ready, which is the whole-result
boundary; a stream publishes each root as soon as it is ready and keeps what it has
already published if a later root fails. Typed publication needs the selection's
`EntityGraphConstruction`; Wire publication does not, so Wire can serve a model with no
classes. The Wire publication holds one scalar encoder for the delivery and drops it
when the delivery releases the publication.

`Snapshot.wire()` and a paused Typed stream's `SnapshotStream.wire` project values that
are already published into Wire form in memory, with no further read.

### Symbols

- `parallax.core.read_delivery._page_reader:HistoryPageResult`
- `parallax.core.read_delivery._page_reader:StreamPageResult`
- `parallax.snapshot._handle._read:SnapshotPublication.roots_of`
- `parallax.snapshot._handle._read:SnapshotPublication.from_find`
- `parallax.snapshot._handle._read:SnapshotPublication.from_history`
- `parallax.snapshot._publication._root_publication:publish_roots`
- `parallax.snapshot._publication._root:RootView`
- `parallax.snapshot._publication._root:RootView.complete`
- `parallax.snapshot._publication._root:RootView.prime`
- `parallax.snapshot._publication._typed:typed_root`
- `parallax.snapshot._publication._wire:wire_roots`
- `parallax.snapshot._publication._classify:classify_roots`
- `parallax.snapshot._publication._wire:WireWalk`
- `parallax.snapshot._publication._wire:WireEntity`
- `parallax.snapshot._publication._wire:shared_wire_encoder`
- `parallax.core.read_delivery._page._stored_data:InvalidData`
- `parallax.core.read_delivery._page._stored_data:InvalidDataError`
- `parallax.snapshot._handle._read:Snapshot`
- `parallax.snapshot._handle._read:Snapshot.result`
- `parallax.snapshot._handle._read:Snapshot.results`
- `parallax.snapshot._handle._read:Snapshot.checked`
- `parallax.snapshot._handle._read:Snapshot.wire`
- `parallax.snapshot._handle._read:CheckedSnapshot`
- `parallax.snapshot._handle._stream:SnapshotStream`
- `parallax.snapshot._handle._stream:SnapshotStream.checked`
- `parallax.snapshot._handle._stream:SnapshotStream.wire`

## Where eager, milestone-set and streamed delivery diverge

```text
 ResolvedObjectQuery
        │
        ├ eager, one instant
        │     deliver_find → EagerPageRequest → PageReader → EagerPageResult
        │     → SnapshotPublication.from_find → Snapshot at the query's own pin
        │
        ├ eager milestone set (history / as_of_range: an As-Of Axis is scanned)
        │     deliver_history → find_history:
        │       continuation.ordered → ReadPlanner.plan → PlannedFlatPageRequest
        │       → PageReader → root-only Page → HistoryPageResult
        │     → SnapshotPublication.from_history
        │     → Snapshot with an empty Pin; each root at its own milestone edge
        │
        └ stream
              construct  SnapshotStream → ExecutionScope.stream or the attempt's stream:
                         capture the query, check_batch_size; no read begins
              enter      StreamDelivery.enter: begin → build_publication → resolved
                         (the shared gate) → PagingPlan(continuation.plan(...),
                         batch_size, limit) → the delivery's pin → open the Stream activity
              each page  read_page, inside the lane's BegunRead.paged bracket and a
                         Stream Batch:
                           StreamPageRequest(PagingPlan, At(coordinate, emitted))
                           → PageReader: ContinuationPlan.first / ContinuationPlan.after
                             → plan → root statement, reading one lookahead root
                           → page_decision: keep a strictly ordered prefix, detect a tie
                           → fetch levels for the kept roots
                           → StreamPageResult(delivered, resume_from, exhausted, tie)
              publish    outside the batch: roots_of for this Page; roots handed over
                         one at a time
              then       resume_from → next page | exhausted → done
                         | tie → StreamContinuationError
              milestone-set stream: the same pages, root-only, each root at its own
                         edge, and an empty delivery Pin

 connection  StandaloneRead → one lease around an eager read, held until its result
                              exists; one lease per stream page, returned before
                              that page's roots are published
             ReadOnlyTxnAttempt / TxnAttempt → the attempt's own connection;
                              a TxnAttempt flushes pending writes before every read
                              and every page

 origins     TxnAttempt, one instant → ReadEvidenceCollector → origins_for(page)
                              → Read Evidence on conforming Typed and Wire nodes
             StandaloneRead / ReadOnlyTxnAttempt (no evidence context),
             or a scanned-axis stream page → EMPTY_PAGE_ORIGIN_COLLECTOR → none
             eager milestone set → find_history observes no origins at all
             read_rows → find_rows → RowsResult: rows, no graph, no evidence
```

The `ReadInputs` a lane passes decide most of this. A standalone read passes its own
connection, no Concurrency Preference and no evidence context; a read-only attempt
passes its connection and neither of the others; a writable attempt passes its
connection, its unit of work's preference and the unit of work itself as the evidence
context. `_page_origin_collector` in `_read_policy` turns "no evidence context, or a
scanned axis" into `EMPTY_PAGE_ORIGIN_COLLECTOR`.

Read Evidence is not authority. A source write of a value a read returned hands the
value's evidence to `UnitOfWork.resolve_read_evidence`, which refuses it unless a read
of this attempt produced it (`write-evidence-unavailable`), before anything is
buffered; a value this attempt inserted is licensed by the insertion instead. The
value's pin is checked at the same verb: a value read at a finite Transaction-Time
instant is refused by `validate_source_pin` with `TransactionTimePinReadOnlyError`,
even when a writable attempt read it. Publication provenance — the concrete Entity,
the Pin, and whether the root conformed — is recorded on every published value, with
or without evidence. A standalone or read-only value therefore stays a stored value
whose revision a target write can state, though it cannot license a source write.
[Write flow](write-flow.md#what-licenses-each-admitted-write) follows the write from
admission onward.

A stream keeps the selection it adopted at entry for every page. A participating stream
is admitted again for each page, so a stream that outlives its attempt reads nothing
more, and closing a stream releases its publication and delivery state whether it was
exhausted, failed or stopped early.

### Symbols

- `parallax.core.object_query._fluent:ObjectQuery.history`
- `parallax.core.object_query._fluent:ObjectQuery.as_of_range`
- `parallax.core.read_delivery._delivery:find_history`
- `parallax.core.continuation:ordered`
- `parallax.core.continuation:plan`
- `parallax.core.continuation:ContinuationPlan.first`
- `parallax.core.continuation:ContinuationPlan.after`
- `parallax.core.read_delivery._page_reader:PlannedFlatPageRequest`
- `parallax.core.read_delivery._page_reader:StreamPageRequest`
- `parallax.core.read_delivery._page_reader:PageReader`
- `parallax.core.read_delivery._page_reader:StreamPageResult.delivered`
- `parallax.core.read_delivery._page_reader:StreamPageResult.resume_from`
- `parallax.core.read_delivery._page_reader:StreamPageResult.exhausted`
- `parallax.core.read_delivery._page_reader:StreamPageResult.tie`
- `parallax.snapshot._handle._stream:SnapshotStream`
- `parallax.core.read_delivery._read_plan:ReadPlanner.plan`
- `parallax.core._execution._read_policy:ReadInputs`
- `parallax.core._execution._scope:ExecutionScope.stream`
- `parallax.core._execution._transaction._attempt:_TxnAttemptBase.stream`
- `parallax.core.read_delivery._stream:check_batch_size`
- `parallax.core.read_delivery._stream:StreamDelivery.enter`
- `parallax.core.read_delivery._stream:StreamContinuationError`
- `parallax.core.read_delivery._paging:PagingPlan`
- `parallax.core.read_delivery._paging:At`
- `parallax.core.read_delivery._paging:page_decision`
- `parallax.core._execution._read_policy:read_page`
- `parallax.core._execution._read_policy:BegunRead.paged`
- `parallax.core._execution._read_policy:_page_origin_collector`
- `parallax.core._execution._page_origins:ReadEvidenceCollector`
- `parallax.core.read_delivery._page_reader:EMPTY_PAGE_ORIGIN_COLLECTOR`
- `parallax.core._execution._unit_work.retain:ReadEvidence`
- `parallax.core._execution._unit_work.uow:UnitOfWork.resolve_read_evidence`
- `parallax.core._execution._keyed_writes:validate_source_pin`
- `parallax.core._execution._keyed_writes:TransactionTimePinReadOnlyError`
- `parallax.core.read_delivery._row_lane:RowsResult`

## Where the contracts live

| Stage | Contract owner |
| -- | -- |
| Entry points, lanes, adoption, connections | [`m-execution`](../../../../core/spec/m-execution.md), [Python execution binding](../../spec/execution.md) |
| Query value and its resolution | [`m-object-query`](../../../../core/spec/m-object-query.md) |
| Levels and `1 + L` | [`m-deep-fetch`](../../../../core/spec/m-deep-fetch.md) |
| Statements, seeks, locks | [`m-sql`](../../../../core/spec/m-sql.md), [`m-read-lock`](../../../../core/spec/m-read-lock.md) |
| Storage layout | [`m-storage-layout`](../../../../core/spec/m-storage-layout.md#storage-layout-transparency) |
| Plan cache, Page, delivery, streams | [`m-read-delivery`](../../../../core/spec/m-read-delivery.md) |
| Root Views, classification, Snapshot values | [`m-snapshot-read`](../../../../core/spec/m-snapshot-read.md), [Python queries and results](../../spec/queries-and-results.md) |
| Read Evidence and write admission | [`m-unit-work`](../../../../core/spec/m-unit-work.md#current-attempt-source-admission) |
| Typed and Wire as peers | [ADR 0057](../../../../docs/adr/0057-typed-and-wire-are-peer-interfaces-over-one-transaction.md) |
