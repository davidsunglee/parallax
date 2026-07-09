---
date: 2026-07-09
topic: "Reladomo session/cache and transaction management prior art for Parallax"
type: research
tags: [research, reladomo, parallax, session-cache, transactions, cache, identity-map, prior-art]
status: complete
---

# Reladomo Session, Cache, and Transaction Prior Art

## Summary

Reladomo does **not** have a first-class ORM `Session`/`EntityManager` object analogous to SQLAlchemy or Hibernate. The inspected core API is organized around a process-wide `MithraManager`, one `MithraObjectPortal` per mapped type, thread-local `MithraTransaction` scopes, per-type identity/query caches, and detached-copy APIs rather than an application-created session object. The existing Reladomo research summarizes this as a process-wide manager plus per-type portals; the source shows `MithraManager` owning the thread-local current transaction and `MithraAbstractObjectPortal` owning the cache/query-cache pair for a type. [R01] [S-manager-fields] [S-portal-fields]

Reladomo's cache model is stronger and broader than a session identity map: loaded rows are interned in process-level identity caches behind portals, query results are cached by operation, and writes invalidate cached queries through update-count tokens and cross-JVM notification. Detached objects are the main explicit "outside the live cache" lifecycle concept: a detached copy is a new object carrying copied data, while the original remains live in the cache. [R08] [S-cache-intern] [S-query-expiry] [S-detach-copy]

Reladomo's transaction model is a JTA-backed unit of work. `executeTransactionalCommand` opens or joins a transaction, buffers writes as transaction operations, flushes combined operations before commit, and relies on either pessimistic read participation or optimistic version checks for correctness. Nested transactions join the root transaction rather than creating savepoints. [R09] [R23] [S-manager-execute] [S-tx-buffer] [S-nested]

For a Parallax session-cache slice that intentionally has no process-wide cache or coherence concerns, Reladomo is useful prior art mostly for the responsibilities to preserve, not the cache scope to copy: identity deduplication, read-your-own-writes, stale-row invalidation on conflict, detached-copy merge behavior, and transaction retry/flush ordering can be scoped to a session/unit of work without importing Reladomo's portal-level full/partial caches, cacheloader, off-heap cache, master-cache replication, or notification bus. [P-unit-work] [P-process-cache] [P-coherence] [R19]

## Cache/session-equivalent responsibilities

Reladomo splits responsibilities that a Hibernate/SQLAlchemy-style session usually centralizes:

| Responsibility | Reladomo coordination point | Evidence |
|---|---|---|
| Open/current transaction | `MithraManager` thread-local `MithraTransaction`; `executeTransactionalCommand`; `startOrContinueTransaction` | [S-manager-fields] [S-manager-start] [S-manager-execute] |
| Per-type object coordination | One `MithraObjectPortal` per mapped type, holding cache, query cache, finder, and reader/persister | [R01] [S-portal-fields] |
| Identity map | Portal identity cache; `getObjectFromData` returns existing object by primary key or creates and indexes one on miss | [R08] [S-cache-intern] |
| Query cache | Portal query cache; operation equality maps to a `CachedQuery` result list | [S-query-cache] [S-query-expiry] |
| Transaction-local query cache | `MithraTransactionalPortal.initializeTransactionalQueryCache(tx)` installs a per-transaction `QueryCache`; `getQueryCache()` returns that cache when a transaction is current | [R09] [S-tx-query-cache] |
| Write buffering and flush | `MithraRootTransaction` and `TxOperations`; pending inserts/updates/deletes are combined then executed | [R09] [S-root-buffer] [S-tx-buffer] |
| Detach/merge | `getDetachedCopy`, `copyDetachedValuesToOriginalOrInsertIfNew`, and generated `zFindOriginal` | [R10] [S-detach-copy] [S-detach-merge] [S-generated-find-original] |
| Cache administration | `MithraRuntimeCacheController` per finder/class; manager-wide query-cache clearing delegates to controllers | [R19] [S-runtime-cache-controller] [S-clear-query-caches] |

The important shape is that Reladomo's live identity cache is not scoped to a user session. It is per mapped type and lives behind the type portal for the process. `MithraAbstractObjectPortal` constructs the `QueryCache` in the portal constructor and wires the cache back to the portal; `MithraTransactionalPortal` temporarily redirects query-cache lookup to a transaction-local cache, but the identity cache remains the portal cache. [S-portal-fields] [S-tx-query-cache]

Reads flow through that portal spine. `findAsCachedQuery` checks the query cache when local cache use is allowed, analyzes the operation if needed, tries in-memory cache resolution, flushes relevant transaction state before a server read, and increments the database-retrieve count only on the server-read path. [R01] [S-find-flow]

## Transaction semantics

`MithraManager` is the transaction entry point. It has a configurable `JtaProvider`, defaults to `DefaultJtaProvider(new LocalTm())`, stores the current `MithraTransaction` in a `ThreadLocal`, and exposes `executeTransactionalCommand`. When no transaction exists, `executeTransactionalCommand` starts one, executes the callback, commits, and retries through `MithraTransaction.handleTransactionException`; when a transaction already exists, it executes inside the existing transaction and does not run an inner retry loop. [R09] [R23] [S-manager-fields] [S-manager-execute]

Starting a transaction either wraps the current transaction in a `MithraNestedTransaction` or begins/obtains a JTA transaction and creates a `MithraRootTransaction`. Creating the root transaction also initializes the transaction-local query cache and registers the root as a JTA `Synchronization`. [R23] [S-manager-start] [S-manager-join]

Nested transactions are joins, not savepoints. `MithraNestedTransaction.commit()` only optionally flushes buffered SQL and then pops the thread-local transaction; `rollback()` marks the root transaction as expecting rollback. The root commit rejects a transaction marked `expectRollback`. [R23] [S-nested] [S-root-commit]

Reladomo can also join an externally managed JTA transaction. `joinJtaTransaction` requires an active JTA transaction, creates a `MithraRootTransaction`, marks it as not started, and stores it in the thread-local; the root transaction will flush Reladomo work but not commit the external transaction manager. [R23] [S-manager-join] [S-root-commit]

Writes are buffered as `TxOperations`. Updates register affected update-count holders and consolidate adjacent updates to the same object; inserts and deletes add transaction operations and update per-portal bookkeeping. Before execution, `AbstractTxOperations.combineAll()` merges updates and scans forward/backward for combinable operations; `TxOperations.executeBufferedOperations()` then executes each remaining operation and clears the operation list. [R09] [S-tx-ops-add] [S-tx-combine] [S-tx-buffer]

The root transaction flushes buffered operations directly in `commit()` and also from JTA `beforeCompletion()`. Cache commit and notifications are separated: `MithraLocalTransaction.handleCacheCommit()` calls `zHandleCommit()` on enrolled resources, calls `cache.commit(this)` on transaction caches, performs synchronized cache-commit work, finalizes cleanup, and then broadcasts notification events if any were collected. [R09] [S-root-buffer] [S-root-commit] [S-cache-commit]

Correctness has two modes. The default full participation mode requires read participation and locking: `FullTransactionalParticipationMode.mustLockOnRead()` and `mustParticipateInTxOnRead()` both return true, and refresh SQL appends database-specific lock clauses when `lockInDatabase` is true. The optimistic mode returns false for both read lock/participation and true for `isOptimisticLocking()`, so correctness moves to the write affected-row check. [R09] [S-full-participation] [S-optimistic-participation] [S-refresh-lock]

Optimistic conflicts are detected by affected row count. `MithraAbstractDatabaseObject.checkUpdatedRows` treats `updatedRows != 1` as an error; in optimistic participation it marks the cached row dirty for reload and throws an optimistic-lock exception when zero rows were updated. [R09] [S-check-updated-rows]

JTA/XA integration is real, not only an abstraction. `XAConnectionPoolingDataSource` creates a per-transaction `JDBCConnectionXAResource` and enlists it with the current Mithra transaction when participation is required; its `commit(Xid, boolean)` commits the pooled JDBC connections and rolls them back on commit failure. The Reladomo XA/JMS module extends this pattern with a bundled transaction manager and two-phase commit for JMS plus database work. [R23] [S-xa-enlist] [S-xa-commit]

## Cache/identity/coherence semantics

Each mapped type has an identity cache and query cache behind its portal. The identity cache is responsible for one live object per primary key in the process cache: `AbstractNonDatedCache.getObjectFromData` acquires a read lock, looks up by primary key, upgrades to a write lock on miss, double-checks, creates the object through the factory only if still absent, and indexes it. `getManyObjectsFromData` applies the same pattern in bulk. [R08] [S-cache-intern]

The query cache maps an `Operation` to a `CachedQuery`. `QueryCache` uses a non-LRU index for full caches or for unbounded/zero-TTL settings, and an LRU index for partial/timed caches; `findByEquality` returns cached queries by operation equality. [R08] [S-query-cache]

Cached-query freshness is token-based. A `CachedQuery` records `UpdateCountHolder` values for the portals and attributes it depends on; `isExpired()` returns true as soon as any holder's current count differs from the recorded count. That means Reladomo does not have to enumerate every cached query on write; it increments class/attribute update counts, and dependent cached queries become expired by comparison. [R08] [S-query-expiry]

Reladomo has process-wide cache administration. `MithraRuntimeCacheController.clearQueryCache()` clears a finder/type's portal query cache, `reloadCache()` reloads a full cache, and `clearPartialCacheOrReloadFullCache()` chooses between clearing partial cache state and reloading a full cache. `MithraConfigurationManager.clearAllQueryCaches()` snapshots all runtime cache controllers and clears each, while its javadoc explicitly says a transaction's special query cache is not cleared by this method. [R19] [S-runtime-cache-controller] [S-clear-query-caches]

Cross-process coherence is notification-driven. On transaction cache commit, Reladomo broadcasts collected notification events. Full-cache listeners re-read changed rows from the database and increment class update counts; partial-cache listeners mark affected objects dirty and increment update counts as needed. The existing research notes also describe master-cache replication and full-cache startup loading, which are cache-scope features rather than session/unit-of-work features. [R08] [R19] [S-cache-commit] [S-full-listener] [S-partial-listener] [S-partial-update]

Object identity is therefore a process-cache property for live persistent objects, not a session-local property. Detached copies are explicitly outside that rule: `PersistedBehavior.getDetachedCopy` copies the data object, creates a new object instance, and marks it `DETACHED`, while the live original remains in the cache. [R10] [S-detach-copy]

## Failure modes and lifecycle edge cases

Reladomo models object lifecycle as persistence-state dispatch. The base state constants include `IN_MEMORY`, `PERSISTED`, `DELETED`, `DETACHED`, and `DETACHED_DELETED`, and behavior selection depends on whether there is no transaction, the same transaction, an enrolling transaction, or another transaction. [R10] [S-persistence-state]

A detached copy of a persisted object is a copied data object, not another live cache entry. Mutating it changes only the copy. Merging a persisted detached copy resolves the original by primary key through generated `zFindOriginal`; if found, detached behavior copies attributes and persists detached relationships onto the live original. If the original persisted row is gone, the non-dated detached behaviors throw a deleted-object exception rather than silently inserting a replacement. [R10] [S-detach-copy] [S-detach-merge] [S-generated-find-original]

The `copyDetachedValuesToOriginalOrInsertIfNew` wrapper starts a Reladomo transaction when none is active, names it, invokes the implementation, commits, and delegates failures to the standard transaction exception/retry handling. The "insert if new" branch is represented by in-memory behavior: `InMemoryBehavior.updateOriginalOrInsert` cascades a copy then inserts. [R10] [S-detach-wrapper] [S-inmemory-insert]

Detached-deleted merge is a delete of the live original when it still exists. `DetachedDeletedBehavior.updateOriginalOrInsert` finds the original and calls `cascadeDelete()` when present. For dated detached-deleted objects, the corresponding behavior updates in place before terminating and then cascade-terminates the original. [S-detached-deleted] [S-dated-detached-deleted]

Nested rollback is whole-root rollback. A nested transaction rollback marks the root as expecting rollback; root commit then throws instead of committing. There is no inner savepoint state to keep. [R23] [S-nested] [S-root-commit]

Optimistic conflict recovery depends on cache invalidation. On a stale optimistic update, Reladomo marks the cache entry dirty for reload before throwing. The outer retry loop can then re-run the user closure and re-read fresh state when optimistic retry is enabled. [R09] [S-check-updated-rows] [S-manager-execute]

Read-your-own-writes can force buffered SQL before commit. The portal read path calls `flushTransaction` before a server read, while `m-unit-work` in Parallax describes the same observable rule: a dependent read must observe not-yet-committed writes, but abort must still discard writes that were force-flushed inside the open transaction. [S-find-flow] [P-unit-work]

## Implications for Parallax session-cache slice

For a Parallax slice scoped to **session caching** rather than Reladomo-style process caching, the Reladomo prior art suggests these design points:

1. Keep the identity guarantee scoped precisely. Reladomo's live guarantee is one process-cached object per primary key; a Parallax session-cache slice can instead guarantee one object per primary key **within a session/unit-of-work cache** and make no same-instance promise across independent sessions. This is narrower than current deferred `m-process-cache`, which names an in-process identity/query cache layered on unit of work. [R08] [P-process-cache]

2. Preserve the read path ordering without importing the global cache. Reladomo's portal path is query cache, identity cache, transaction flush, database read, intern; a session-cache slice can keep the important behavioral ordering as session query/identity lookup, flush pending dependent writes, database read, session interning. [S-find-flow] [P-unit-work]

3. Make invalidation local. Reladomo uses class/attribute update-count tokens and notification to expire process caches. A no-process-cache Parallax slice only needs invalidation for the current session's stale identity/query entries after local writes, rollback, and optimistic conflict; it should not claim cross-session or cross-process freshness. [S-query-expiry] [S-check-updated-rows] [P-coherence]

4. Do not include Reladomo cache operations in the slice. Runtime cache controllers, full-cache startup load, cacheloader refresh, off-heap/master-cache replication, and cross-JVM notification are all consequences of process-level caches. They are out of scope for a session-cache slice with no coherence concerns. [R19] [P-process-cache] [P-coherence]

5. Keep transaction scope and cache scope aligned. Reladomo separates a transaction-local query cache from process identity caches; Parallax can choose a simpler rule where the session cache is owned by the explicit session/unit-of-work boundary and is cleared or invalidated on rollback/close. The unit-of-work contract already requires buffered writes, ordered flush, dependent-read flush, and abort erasure. [S-tx-query-cache] [P-unit-work]

6. Treat detached copies as outside the session cache. Reladomo's detached copies are independent objects made from copied data; merge-back resolves the live original and drives normal buffered writes. The Parallax session-cache slice should preserve that boundary: detached objects are snapshots, not alternate identity-map entries. [S-detach-copy] [S-detach-merge] [P-detach]

7. Carry observed versions through the cache boundary. Reladomo optimistic mode relies on the version observed by the read and marks stale cache entries dirty on `updatedRows != 1`. Parallax's optimistic-lock spec similarly requires the observed version to be framework-owned and stale cached state to be invalidated before retry. [S-check-updated-rows] [P-opt-lock]

8. Be explicit that this slice is not `m-process-cache` unless the spec is changed. The current Parallax catalog names `m-process-cache` as deferred process-level identity/query cache and `m-coherence` as a separate deferred multi-node extension. A session-cache slice can be a smaller deliverable, but it should not silently claim the existing process-cache/coherence modules. [P-modules] [P-slices] [P-process-cache] [P-coherence]

## Source map

Existing Parallax research and spec sources:

- [R01] [docs/research/reladomo/01-runtime-architecture.md](../reladomo/01-runtime-architecture.md)
- [R08] [docs/research/reladomo/08-caching.md](../reladomo/08-caching.md)
- [R09] [docs/research/reladomo/09-transactions-locking.md](../reladomo/09-transactions-locking.md)
- [R10] [docs/research/reladomo/10-object-lifecycle.md](../reladomo/10-object-lifecycle.md)
- [R19] [docs/research/reladomo/19-cache-operations.md](../reladomo/19-cache-operations.md)
- [R23] [docs/research/reladomo/23-transaction-integration.md](../reladomo/23-transaction-integration.md)
- [P-modules] [core/spec/modules.md](../../../core/spec/modules.md)
- [P-slices] [core/spec/slices.md](../../../core/spec/slices.md)
- [P-unit-work] [core/spec/m-unit-work.md](../../../core/spec/m-unit-work.md)
- [P-process-cache] [core/spec/m-process-cache.md](../../../core/spec/m-process-cache.md)
- [P-coherence] [core/spec/m-coherence.md](../../../core/spec/m-coherence.md)
- [P-detach] [core/spec/m-detach.md](../../../core/spec/m-detach.md)
- [P-opt-lock] [core/spec/m-opt-lock.md](../../../core/spec/m-opt-lock.md)

Reladomo source checkout: local `../reladomo`, commit `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. GitHub permalinks below point to that commit.

- [S-manager-fields] [`MithraManager.java` fields for default JTA provider, thread transaction, retrieve count, notification manager](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/MithraManager.java#L65-L75)
- [S-manager-start] [`MithraManager.startOrContinueTransaction`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/MithraManager.java#L235-L286)
- [S-manager-join] [`MithraManager.joinJtaTransaction`, `leaveJtaTransaction`, `createMithraRootTransaction`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/MithraManager.java#L352-L410)
- [S-manager-execute] [`MithraManager.executeTransactionalCommand`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/MithraManager.java#L524-L566)
- [S-portal-fields] [`MithraAbstractObjectPortal` cache/query-cache fields and constructor wiring](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/portal/MithraAbstractObjectPortal.java#L115-L170)
- [S-find-flow] [`MithraAbstractObjectPortal.findAsCachedQuery`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/portal/MithraAbstractObjectPortal.java#L832-L870)
- [S-tx-query-cache] [`MithraTransactionalPortal` transaction-local query cache](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/portal/MithraTransactionalPortal.java#L56-L75) and [`getQueryCache`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/portal/MithraTransactionalPortal.java#L215-L225)
- [S-cache-intern] [`AbstractNonDatedCache.getObjectFromData` and bulk variant](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/cache/AbstractNonDatedCache.java#L1023-L1125)
- [S-query-cache] [`QueryCache` constructor, put/find/clear operations](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/querycache/QueryCache.java#L39-L88)
- [S-query-expiry] [`CachedQuery` update-count capture and `isExpired`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/querycache/CachedQuery.java#L224-L268)
- [S-root-buffer] [`MithraRootTransaction.executeBufferedOperations` and `beforeCompletion`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/transaction/MithraRootTransaction.java#L687-L725)
- [S-root-commit] [`MithraRootTransaction.commit`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/transaction/MithraRootTransaction.java#L814-L855)
- [S-cache-commit] [`MithraLocalTransaction.handleCacheCommit`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/transaction/MithraLocalTransaction.java#L374-L397)
- [S-nested] [`MithraNestedTransaction` commit/rollback/root delegation](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/transaction/MithraNestedTransaction.java#L52-L84)
- [S-tx-ops-add] [`TxOperations` add update/insert/delete](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/transaction/TxOperations.java#L33-L99)
- [S-tx-combine] [`AbstractTxOperations.combineAll` and update consolidation](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/transaction/AbstractTxOperations.java#L204-L260)
- [S-tx-buffer] [`TxOperations.executeBufferedOperations`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/transaction/TxOperations.java#L213-L235)
- [S-full-participation] [`FullTransactionalParticipationMode`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/txparticipation/FullTransactionalParticipationMode.java#L24-L42)
- [S-optimistic-participation] [`ReadCacheWithOptimisticLockingTxParticipationMode`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/txparticipation/ReadCacheWithOptimisticLockingTxParticipationMode.java#L24-L48)
- [S-refresh-lock] [`MithraAbstractDatabaseObject.refresh` lock-aware SQL path](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/database/MithraAbstractDatabaseObject.java#L2225-L2255)
- [S-check-updated-rows] [`MithraAbstractDatabaseObject.checkUpdatedRows`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/database/MithraAbstractDatabaseObject.java#L3725-L3748)
- [S-xa-enlist] [`XAConnectionPoolingDataSource` resource enlistment](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/connectionmanager/XAConnectionPoolingDataSource.java#L70-L88)
- [S-xa-commit] [`XAConnectionPoolingDataSource.JDBCConnectionXAResource.commit`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/connectionmanager/XAConnectionPoolingDataSource.java#L540-L565)
- [S-runtime-cache-controller] [`MithraRuntimeCacheController` query-cache and cache reload operations](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/util/MithraRuntimeCacheController.java#L95-L130)
- [S-clear-query-caches] [`MithraConfigurationManager.clearAllQueryCaches` javadoc and implementation](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/util/MithraConfigurationManager.java#L1166-L1188)
- [S-full-listener] [`FullCacheMithraNotificationListener`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/notification/listener/FullCacheMithraNotificationListener.java#L29-L55)
- [S-partial-listener] [`PartialCacheMithraNotificationListener`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/notification/listener/PartialCacheMithraNotificationListener.java#L29-L39)
- [S-partial-update] [`AbstractMithraNotificationListener.onUpdateForPartialCache`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/notification/listener/AbstractMithraNotificationListener.java#L82-L108)
- [S-persistence-state] [`PersistenceState` constants and behavior dispatch](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/state/PersistenceState.java#L34-L95)
- [S-detach-copy] [`PersistedBehavior.getDetachedCopy`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/persisted/PersistedBehavior.java#L73-L82)
- [S-detach-wrapper] [`MithraTransactionalObjectImpl.copyDetachedValuesToOriginalOrInsertIfNew`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/superclassimpl/MithraTransactionalObjectImpl.java#L1560-L1595)
- [S-detach-merge] [`DetachedNoTxBehavior.updateOriginalOrInsert`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/detached/DetachedNoTxBehavior.java#L51-L83) and [`DetachedSameTxBehavior.updateOriginalOrInsert`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/detached/DetachedSameTxBehavior.java#L56-L88)
- [S-generated-find-original] [`transactional/Abstract.jsp` generated `zFindOriginal`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomogen/src/main/templates/transactional/Abstract.jsp#L251-L270)
- [S-inmemory-insert] [`InMemoryBehavior.updateOriginalOrInsert`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/inmemory/InMemoryBehavior.java#L58-L63)
- [S-detached-deleted] [`DetachedDeletedBehavior.updateOriginalOrInsert`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/detached/DetachedDeletedBehavior.java#L177-L185)
- [S-dated-detached-deleted] [`DatedDetachedDeletedBehavior.updateOriginalOrInsert`](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/detached/DatedDetachedDeletedBehavior.java#L147-L158)
