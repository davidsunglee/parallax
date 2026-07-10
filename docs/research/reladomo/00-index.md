---
date: 2026-06-26T00:00:00-04:00
git_commit: 9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4
branch: master
repository: reladomo (github.com/goldmansachs/reladomo)
topic: "Reladomo core features — architecture, metamodel, query/temporal/cache/transaction engine, DB seam, and excluded-feature entanglement"
type: research
tags: [research, codebase, reladomo, orm, bitemporal, milestoning, finder, cache, transactions, codegen, database-type, source-attribute, off-heap, remote]
status: complete
---

# Research: Reladomo Core Features

**Date**: 2026-06-26 · **Git commit**: `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4` · **Branch**: `master`

> **Subject of research.** The [Goldman Sachs Reladomo](https://github.com/goldmansachs/reladomo)
> Java O/R framework, checked out as a peer of this repository (`../reladomo`). All paths in the
> finding files are relative to that repo root, with two abbreviations used throughout:
> **`mithra/`** = `reladomo/src/main/java/com/gs/fw/common/mithra/` (the hand-written runtime) and
> **`generator/`** = `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/` (the code
> generator). GitHub permalinks follow
> `https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/<path>#L<line>`.

This index is the entry point. Read the Summary below for the shape of the system, then open only
the finding files a task needs. Each finding file is self-contained (provenance header, evidence
citations, testing patterns, code references).

## Summary

Reladomo is a code-generation-driven, cache-centric, bitemporal O/R framework. A domain object is
defined once in an XML descriptor validated against `mithraobject.xsd`; the `reladomogen` build-time
tool parses it, builds an in-memory model, and runs a JSP-based template engine to emit a fixed set
of Java artifacts per object — an `Abstract` object, a `Data` carrier, a `Finder`, a `List`, and a
`DatabaseObject`. The generated code is **typed scaffolding**: it declares fields and getters/setters
and delegates every behavior to hand-written runtime base classes in `com.gs.fw.common.mithra`
(`generator/templates/transactional/Abstract.jsp:55-70` shows the generated abstract class extending
`mithra/superclassimpl/MithraTransactionalObjectImpl`). The "spine" of the runtime is two
coordinators: the process-wide singleton `MithraManager` (transactions, config loading, notification)
and one `MithraObjectPortal` per object type, which holds and routes between that type's identity
cache, query cache, finder/metadata, and database object.

Queries are expressed through a typed, composable `Operation` tree built from finder-attribute
predicates (`.eq()`, `.in()`, `.greaterThan()`); relationship traversals become `MappedOperation`
nodes wrapping a `Mapper` that encodes join columns. A read flows query cache → identity cache →
database (`mithra/portal/MithraAbstractObjectPortal.java:832`), and `SqlQuery` walks the operation
tree calling `generateSql()` to produce the WHERE clause and a list of parameter setters. Deep fetch
collapses N+1 navigation into one bulk `IN`-clause (or temp-table-join) query per relationship level
via a `DeepFetchNode` tree and per-relationship `DeepFetchStrategy` objects. Bitemporality is a
first-class, deeply-woven feature: `AsOfAttribute` models a `[from,to)` interval over a pair of
timestamp columns (business date `FROM_Z/THRU_Z` and processing date `IN_Z/OUT_Z`), `AsOfEqualityChecker`
injects defaulted as-of predicates into every query, and `TemporalDirector` implementations chain
milestone rows on write (close the old row by setting its out-date; insert a new row), including
bitemporal "rectangle splitting."

The cache layer is the heart of the system: each type has an identity cache (one in-memory object
per primary key, with Full/Partial × Dated/NonDated × OnHeap/OffHeap variants) and a query cache
(`Operation` → `CachedQuery` result list) invalidated through `UpdateCountHolder` version tokens and a
cross-JVM notification bus. Transactions are JTA-backed: writes are buffered as `TxOperations`,
combined/batched/ordered at commit, and flushed through the `MithraObjectPersister`. Correctness is
enforced automatically via pessimistic read locks (`SELECT … FOR UPDATE`-style, dialect-specific) or
optimistic locking (a `useForOptimisticLocking` version column checked in the UPDATE WHERE clause,
throwing a retriable `MithraOptimisticLockException`). Object lifecycle is a state machine
(`IN_MEMORY`, `PERSISTED`, `DELETED`, `DETACHED`, `DETACHED_DELETED`) dispatched through per-state
singleton behavior objects. Database portability is isolated behind the `DatabaseType` interface (10+
concrete dialects incl. `PostgresDatabaseType`), obtained from the connection manager at query time.

On the entanglement question: **remote/client-server** and **XML-config** are cleanly separable
(remote is a drop-in `MithraObjectReader` implementation behind the portal; runtime config is a plain
bean graph with a programmatic, non-XML entry point). **Off-heap** is a medium-coupled parallel cache
implementation with a few leaks into the common `MithraDataObject`/`Cache` contracts.
**Source attributes / sharding is highly coupled** — an `Object source` parameter threads through
~25 sites in the database layer and the `MithraCodeGeneratedDatabaseObject` interface, and source
metadata is exposed on the `RelatedFinder` and every `Attribute`.

## Findings index

| File | Finding |
|---|---|
| [01-runtime-architecture.md](01-runtime-architecture.md) | The runtime is a multi-module build whose spine is `MithraManager` (global) and `MithraObjectPortal` (per-type) |
| [02-object-metamodel.md](02-object-metamodel.md) | A domain object is defined once in XML (`mithraobject.xsd`); runtime behavior is bound separately in a runtime-config XML |
| [03-code-generation.md](03-code-generation.md) | The code generator turns one XML into a fixed set of Java artifacts via a JSP template engine; generated code is scaffolding over the runtime |
| [04-query-operations.md](04-query-operations.md) | The finder query language builds a composable `Operation` tree that `SqlQuery` compiles to a WHERE clause |
| [05-deep-fetch.md](05-deep-fetch.md) | Deep fetch batches relationship traversal into one query per level, eliminating N+1 |
| [06-bitemporal-milestoning.md](06-bitemporal-milestoning.md) | Bitemporal milestoning: `AsOfAttribute` models `[from,to)` intervals; `TemporalDirector` chains milestone rows on every write |
| [07-lists-aggregation.md](07-lists-aggregation.md) | Lists are lazy operation-backed views; `AggregateList` runs GROUP BY/HAVING (in SQL or in-memory) |
| [08-caching.md](08-caching.md) | The identity cache guarantees one object per PK; the query cache maps operations to results; notification invalidates both |
| [09-transactions-locking.md](09-transactions-locking.md) | Transactions are JTA-backed with buffered/batched writes; correctness comes from read locks or optimistic version checks |
| [10-object-lifecycle.md](10-object-lifecycle.md) | Object lifecycle is a state machine dispatched through per-state singleton behavior objects; detach copies data and merges it back |
| [11-database-dialects.md](11-database-dialects.md) | Database portability is isolated behind `DatabaseType`, obtained from the connection manager at query time |
| [12-test-infrastructure.md](12-test-infrastructure.md) | The test suite is an H2-based, no-mock integration harness; the same tests re-run on real vendors via swapped connection managers |
| [13-excluded-feature-entanglement.md](13-excluded-feature-entanglement.md) | Entanglement check: remote and XML are cleanly separable; off-heap is medium-coupled; source-attribute/sharding is highly coupled |
| [14-metamodel-introspection.md](14-metamodel-introspection.md) | A runtime metamodel-introspection seam (`RelatedFinder` + `ReladomoClassMetaData`) lets non-core modules map the model without XML |
| [15-architecture-synthesis.md](15-architecture-synthesis.md) | Architecture synthesis: the cross-cutting design decisions and how the seams compose |
| [16-computed-attributes.md](16-computed-attributes.md) | Calculated attributes: expression methods wrap `AttributeCalculator`s that render SQL text and also evaluate in memory against cached objects |
| [17-identity-columns.md](17-identity-columns.md) | Identity columns: `identity="true"` omits the PK from INSERT and reads it back post-insert via a per-dialect `getLastIdentitySql` query — never JDBC `getGeneratedKeys` |
| [18-temporal-repair-and-recovery.md](18-temporal-repair-and-recovery.md) | Temporal repair and recovery: overlap detection is in-memory rectangle intersection; `OverlapFixer` delete-and-reinserts merged rectangles; `insertForRecovery` writes rows with caller-supplied milestones verbatim |
| [19-cache-operations.md](19-cache-operations.md) | Cache administration is per-class through `MithraRuntimeCacheController`; the cacheloader XML declares bulk loads; master-cache replication streams off-heap pages |
| [20-change-callbacks-and-telemetry.md](20-change-callbacks-and-telemetry.md) | Committed-change callbacks are list- or class-scoped notification listeners; telemetry is per-portal performance data, per-class SQL loggers, and a pluggable stats listener |
| [21-bulk-data-operations.md](21-bulk-data-operations.md) | Bulk data flows through four seams: key-matched `merge()`, in-memory `applyOperation`, streaming `DatabaseCursor`, and BCP `BulkLoader`s |
| [22-source-routing-and-parallel-deep-fetch.md](22-source-routing-and-parallel-deep-fetch.md) | Source attributes route one operation across per-shard connections; deep fetch parallelizes per relationship node and degrades to IN-clause queries across databases |
| [23-transaction-integration.md](23-transaction-integration.md) | Nesting joins the outer transaction (no savepoints); JTA/XA integration spans container TMs, pooled XA connections, and JMS two-phase commit |
| [24-pure-temp-objects-and-extraction.md](24-pure-temp-objects-and-extraction.md) | Pure objects are cache-only (no-op persister), temp objects are real temp tables with scoped contexts, and extractor/reverse-engineering tools round-trip data and schema |
| [25-cascade-operations.md](25-cascade-operations.md) | Cascade operations walk dependent lifecycle graphs for insert, delete, and temporal termination, including list and business-window-bounded variants |

## Research questions

The research-questions document (`01-research-questions-reladomo-core-features.md`) posed 13
descriptive questions — document how Reladomo works **today**, where each capability lives, and how
the pieces interact:

1. Overall architecture & module layout; `MithraManager`/`MithraObjectPortal` as coordination points → [01](01-runtime-architecture.md)
2. Object metamodel & definition format (XML/XSD), object types, runtime configuration → [02](02-object-metamodel.md)
3. Code generation pipeline and the generated/runtime boundary → [03](03-code-generation.md)
4. Bitemporal / milestoning support (`AsOfAttribute`, dated objects, milestone chaining) → [06](06-bitemporal-milestoning.md)
5. Finder query language & operation model (`Operation` tree → SQL; `Mapper`/`MapperStack`) → [04](04-query-operations.md)
6. Relationships & deep fetch (batching, N+1 elimination, reverse/dependent relationships) → [05](05-deep-fetch.md)
7. List / set-based operations & aggregation (`MithraList`, `AggregateList`) → [07](07-lists-aggregation.md)
8. Identity cache & query cache (units of work, indices, invalidation/notification) → [08](08-caching.md)
9. Transactions, optimistic locking & transactional correctness → [09](09-transactions-locking.md)
10. Detached objects & object lifecycle/behavior states → [10](10-object-lifecycle.md)
11. Pluggable database support & the SQL dialect seam (incl. PostgreSQL specifics) → [11](11-database-dialects.md)
12. Test infrastructure & cross-database compatibility testing → [12](12-test-infrastructure.md)
13. Footprint of the "excluded" features (source attributes/sharding, remote, XML, off-heap) → [13](13-excluded-feature-entanglement.md)

Question 14 arose during the research (how `reladomoserial`/`reladomographql` map the model without
XML) and is answered in [14](14-metamodel-introspection.md).

**Second pass (2026-07-07, same commit).** A follow-up gap-research pass covered the capabilities
the 13 questions missed, prioritized by [reladomo-gap-priority.md](../reladomo-gap-priority.md): computed attributes
([16](16-computed-attributes.md)), identity columns ([17](17-identity-columns.md)), temporal
repair/recovery ([18](18-temporal-repair-and-recovery.md)), cache operations
([19](19-cache-operations.md)), change callbacks and telemetry
([20](20-change-callbacks-and-telemetry.md)), list merge / cursors / bulk load
([21](21-bulk-data-operations.md)), source-routing semantics and parallel deep fetch
([22](22-source-routing-and-parallel-deep-fetch.md)), nested/XA transactions
([23](23-transaction-integration.md)), and pure/temp objects plus extraction tooling
([24](24-pure-temp-objects-and-extraction.md)).

**Applied cascade pass (2026-07-10, same commit).** A task-directed source pass enumerated the public
cascade insert/delete/terminate families, mixed-temporality dispatch, list behavior, and detached
integration, then applied those findings to a Parallax module-boundary recommendation and compatibility
case matrix ([25](25-cascade-operations.md)). Unlike the descriptive first and second passes, this
applied note intentionally includes recommendations.

## Scope — what this research does not cover

Coverage spans the 13 original questions plus the second-pass gap files (16–24) and the applied
cascade study (25). Against the
capability inventory in [reladomo-gap-priority.md](../reladomo-gap-priority.md), every rank is now
documented except the following, which remain shallow by choice:

- Cache-monitoring UI (rank 28) — the `reladomoui` GWT module is named in
  [01](01-runtime-architecture.md) only; it is a product layer over the
  [19](19-cache-operations.md) admin surface.
- GS-internal transport adapters (`reladomogs`/`reladomogsi` beyond the bulk loader, Tibco RV/LDAP
  integration) — named in the module map in [01](01-runtime-architecture.md); enterprise
  infrastructure specific to Goldman Sachs deployments.
- The serialization/GraphQL module test suites — noted as not enumerated in depth in
  [14](14-metamodel-introspection.md).

## Original research methodology (verbatim)

This document will remain objective and factual. It does not contain any recommendations or implementation suggestions.
Open questions will not ask Why things haven't been built or what should be built in the future.

There is no "implementation" section - that is intentional.

This methodology governs the original descriptive research and the second-pass gap inventory.
Finding 25 is separately labeled applied research and includes the Parallax recommendations requested
for that task.

## Open questions

None of the 13 original questions remain open. Capabilities *outside* those questions are not
resolved by this research — see the Scope section above.
