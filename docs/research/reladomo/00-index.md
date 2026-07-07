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

## Scope — what this research does not cover

Coverage is bounded by the 13 questions above. The following Reladomo capabilities exist but are
**not documented here** (or only named in passing). Ranks refer to
`docs/misc/reladomo-gap-priority.md`.

**Not covered at all:**

- Calculated/computed attributes and SQL scalar expressions — `mithra/attribute/calculator/` beyond
  the aggregate functions (rank 3)
- DB-native identity / auto-increment primary keys — the XSD `identity` flag is named once; runtime
  behavior, generated-key retrieval, and dialect support are undocumented (rank 4)
- Bitemporal overlap detection / repair — the `OverlapFixer` tooling (its test is cited only as
  evidence for XML-free config) (rank 6)
- Runtime cache administration and the declarative cache-loader framework — warm-up, reload,
  clear/renew, `MithraRuntimeCacheController` admin surface, dependent loaders (rank 10)
- Application-level data-change callbacks — user-facing subscriptions on committed changes, as
  distinct from cache-invalidation notification (rank 13)
- Query/SQL introspection and telemetry hooks — explain/analyze surfaces, performance stats
  listeners, SQL snooping (rank 16)
- Object-graph extraction and DB-to-model reverse engineering (rank 20)
- Multi-threaded deep fetch and cross-database adhoc deep fetch (rank 21)
- Temporal `insertForRecovery` (rank 22) and `incrementUntil` (rank 23)

**Named but not explained:**

- Source-attribute/sharding *semantics* — [13](13-excluded-feature-entanglement.md) documents the
  coupling footprint, not how routing behaves for users (rank 2)
- List diff/merge API — bulk operations are covered in [07](07-lists-aggregation.md); merge is not
  (rank 7)
- Nested-transaction *semantics* — `MithraNestedTransaction` is named in
  [09](09-transactions-locking.md) without commit/rollback behavior (rank 11)
- `MasterCacheReplicationServer` (rank 12), streaming cursors beyond one line on
  `forEachWithCursor()` (rank 14), vendor bulk-load mechanics (rank 15), operations applied to
  in-memory lists (rank 17), pure-object runtime behavior (rank 18), the remaining MAY-tier
  temporal ops' semantics (rank 23), XA/JMS two-phase commit (rank 24), and the cache-monitoring
  UI (rank 28)

## Methodology (verbatim)

This document will remain objective and factual. It does not contain any recommendations or implementation suggestions.
Open questions will not ask Why things haven't been built or what should be built in the future.

There is no "implementation" section - that is intentional.

## Open questions

None of the 13 original questions remain open. Capabilities *outside* those questions are not
resolved by this research — see the Scope section above.
