# Committed-change callbacks are list- or class-scoped notification listeners; telemetry is per-portal performance data, per-class SQL loggers, and a pluggable stats listener

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/`. This file covers the
> application-facing surface; the internal cache-invalidation bus is documented in
> [08-caching.md](08-caching.md).

## Application data-change callbacks

Two listener interfaces ride the same notification bus that drives cache invalidation:

- `MithraApplicationNotificationListener` (`mithra/notification/listener/MithraApplicationNotificationListener.java:21-30`) — three no-argument callbacks `updated()`, `deleted()`, `inserted()`; no payload identifies *which* object changed.
- `MithraApplicationClassLevelNotificationListener` (`mithra/notification/listener/MithraApplicationClassLevelNotificationListener.java:22-25`) — a single `processNotificationEvent(MithraNotificationEvent)` receiving the raw event: class name, operation byte (INSERT/UPDATE/DELETE/MASS_DELETE), `MithraDataObject[]`, the updated `Attribute[]` (`mithra/notification/MithraNotificationEvent.java:47,86-89`), source-attribute value, and the mass-delete `Operation`.

**List-scoped registration**: `someList.registerForNotification(listener)` on any generated list
(`mithra/list/DelegatingList.java:926-929`). For operation-based lists this builds a
`FullUniqueIndex` over the current elements' primary keys and registers per database identifier via
`portal.registerForApplicationNotification(subject, listener, list, operation)`
(`mithra/list/AbstractOperationBasedList.java:318-345`); adhoc lists register index-based (null
operation) (`mithra/list/AdhocFastList.java:341-417`). The registration holds the list in a
`WeakReference` with a `ReferenceQueue`; entries are expunged once the list is garbage-collected
(`mithra/notification/OperationBasedNotificationRegistrationEntry.java:38-43`,
`MithraNotificationEventManagerImpl.java:808`).

**Class-scoped registration**: generated finder statics `XFinder.registerForNotification(listener)`
plus source-attribute overloads taking a value or a `Set` (template
`reladomogen/src/main/templates/readonly/Finder.jsp:1533-1548`), delegating to
`MithraAbstractObjectPortal.registerForApplicationClassLevelNotification`
(`mithra/portal/MithraAbstractObjectPortal.java:1374-1406`), which throws
`MithraBusinessException` if a source-attribute value set is supplied for a sourceless class or omitted for a sourced one.

**What actually fires**: both list-entry implementations skip INSERT events entirely (guard
`databaseOperation != MithraNotificationEvent.INSERT`), so `inserted()` is never invoked by shipped
code — update/delete fire only when an event row hits the list's PK index; MASS_DELETE fires
`deleted()` (operation-based fires it unconditionally; index-based first applies the mass-delete
operation to the list) (`mithra/notification/OperationBasedNotificationRegistrationEntry.java:55-91`,
`IndexBasedNotificationRegistrationEntry.java:50-110`). Class-level entries forward every event
verbatim (`mithra/notification/ClassLevelNotificationRegistrationEntry.java:40-47`).
`DefaultMithraApplicationNotificationListener` is a no-op adapter (`mithra/notification/listener/DefaultMithraApplicationNotificationListener.java`).

**Threading and ordering**: normal incoming notification messages are dispatched on one daemon
`MithraNotificationThread` (a 1-thread `ThreadPoolExecutor`,
`mithra/notification/MithraNotificationEventManagerImpl.java:665-680`); replication polling can
invoke the same processing method directly from per-source daemon polling threads
(`mithra/notification/MithraReplicationNotificationManager.java:133-151, 392-395`). On both paths,
per event, the internal cache listener runs first, then application listeners
(`processNotificationEvents` :593-633 → `processApplicationNotification` :636-643); listener
exceptions are caught and logged, never propagated (:788-806). `RegistrationEntryList` is explicitly
unsynchronized "because they are engineered to be called from one thread" (:750-753).

## Per-object update listener (same-JVM, pre-commit)

Distinct from notification: `MithraUpdateListener` (`mithra/MithraUpdateListener.java:27-69`) is a
setter hook declared per class via the `<UpdateListener>` XML tag
(`reladomogen/src/main/xsd/mithraobject.xsd:53-57`), instantiated once per class by reflection.
`handleUpdate(updatedObject, UpdateInfo)` fires when a set-method changes a persistent object (not
detached/new objects, not dated ripple segments); `UpdateInfo` exposes the changed `Attribute` and
new value (`mithra/UpdateInfo.java:22-35`). `handleUpdateAfterCopy` fires on
`copyValuesToOriginalOrInsertIfNew()`/`copyNonPrimaryKeyAttributesFrom()`. Codegen emits a static
`mithraUpdateListener` field and `triggerUpdateHook`/`triggerUpdateHookAfterCopy`
(`reladomogen/src/main/templates/transactional/Abstract.jsp:81-82,1482-1491`); the generator rejects
it on non-transactional objects (`generator/MithraObjectTypeWrapper.java:1343-1345`).

## Telemetry: MithraPerformanceData and MithraManager counters

Every portal owns a `MithraPerformanceData` (`MithraObjectPortal.getPerformanceData()`,
`mithra/MithraObjectPortal.java:173`) holding five `PerformanceDataPerOperation` buckets —
find/refresh/insert/update/delete — plus `queryCacheHits`/`subQueryCacheHits`/`objectCacheHits`
counters (`mithra/util/MithraPerformanceData.java:26-35`). Each bucket accumulates
totalOperations/totalObjects/totalTime-ms with a `clear()` (`mithra/util/PerformanceDataPerOperation.java:20-53`).
Find time is recorded at cursor close (`mithra/database/MithraAbstractDatabaseObject.java:1062`);
cache hits in the portal (`mithra/portal/MithraAbstractObjectPortal.java:720,728,797`).

Enabling `MithraManager.setCaptureTransactionLevelPerformanceData(true)`
(`mithra/MithraManager.java:152-165`) makes every record also add to a per-transaction copy,
retrievable as `MithraTransaction.getTransactionPerformanceDataFor(portal)` or the whole
`Map<MithraObjectPortal, MithraPerformanceData>` (`mithra/MithraTransaction.java:349-351`;
double-write in `mithra/util/MithraPerformanceData.java:90-138`). `MithraManager` also keeps global
`getDatabaseRetrieveCount()` (AtomicInteger) and `getRemoteRetrieveCount()` counters, mirrored into
the current transaction when the capture flag is on (`mithra/MithraManager.java:178-206`).

## SQL observability

Each generated database object creates three per-class SLF4J loggers in its super constructor
(`mithra/database/MithraAbstractDatabaseObject.java:195-198`):
`com.gs.fw.common.mithra.sqllogs.<ClassName>` (per-statement),
`com.gs.fw.common.mithra.batch.sqllogs.<ClassName>` (batch/multi statements), and
`com.gs.fw.common.mithra.test.sqllogs.<ClassName>`; temp tables log under
`...sqllogs.temp.TemporaryObject` (`mithra/database/TemporaryObjectDatabaseObject.java:32-33`). At
DEBUG, SQL is rendered with bound values via `PrintablePreparedStatement` — a `PreparedStatement`
implementation that records set-calls into a printable string
(`mithra/finder/PrintablePreparedStatement.java:91`). Message shapes:
`source '<src>': connection:<identityHashCode> find with: <sql>` (:945,1571-1575, `logWithSource`
:1780-1790) followed by `retrieved N objects, X ms per` (:1048-1053).

Every SQL logger is wrapped in `SqlLogSnooper` (`mithra/database/SqlLogSnooper.java:24-59`): static
`startSqlSnooping()`/`completeSqlSnooping()` capture the current thread's debug-level SQL into a
thread-local `StringBuilder` even when the underlying logger is disabled (`isDebugEnabled()` returns
true while snooping).

A pluggable statistics hook exists for retrievals only:
`MithraStatsListener.processRetrieval(source, PrintableStatementBuilder, rowsRetrieved,
queryStartTime, dbObjectClass)` (`mithra/database/MithraStatsListener.java:20-23`), instantiated
per database object from a `MithraStatsListenerFactory` named by system property
`mithra.databaseObject.statsListenerFactory` or installed via static
`MithraAbstractDatabaseObject.setStatsListenerFactory` (:148-150,313,5246-5249); invoked at cursor
close and result-set completion (:1056-1060,1292-1295). `PrintableStatementBuilder` re-binds
parameters lazily and falls back to the placeholder SQL on error
(`mithra/database/PrintableStatementBuilder.java:44-58`). `mithra/util/LogAnalyzer.java` is a
standalone `main()` that parses `.sqllogs.` lines out of a log file, classifying `find with`/`update
with`/`multi updating with`/insert variants and aggregating counts and timings (:36-51,85-100).

There is no explain-plan surface: a case-insensitive search for "explain" in `reladomo/src/main/java` matches only javadoc prose in `mithra/notification/server/LinkedBlockingDeque.java`.

## Testing patterns

`TestApplicationNotification` (extends `RemoteMithraNotificationTestCase`) registers a list listener
and a class-level finder listener, mutates data in a remote VM, and synchronizes with
`waitForRegistrationToComplete()`/`waitForMessages(count, portal)`/`waitForNotification(listener)`
(`reladomo/src/test/java/com/gs/fw/common/mithra/test/TestApplicationNotification.java:347-443`;
helpers in `RemoteMithraNotificationTestCase.java:80-92`). `MithraPerformanceDataTest`
(`test/util/MithraPerformanceDataTest.java:42-162`) asserts portal-level
`getDataForFind().getTotalOperations()` and transaction-level data with the capture flag on/off.
SQL-shape assertions attach a `Log4JRecordingAppender` to
`com.gs.fw.common.mithra.sqllogs.<SimpleName>` at DEBUG via
`MithraTestAbstract.setupRecordingAppender(Class)` (`test/MithraTestAbstract.java:548-561`) and
inspect recorded messages, e.g. counting `left join` occurrences in `TestExists.java:80-93`.

## Code references

- `mithra/notification/listener/` — `MithraApplicationNotificationListener.java`, `MithraApplicationClassLevelNotificationListener.java`, `DefaultMithraApplicationNotificationListener.java`
- `mithra/notification/` — `MithraApplicationNotificationRegistrationEntry.java`, `OperationBasedNotificationRegistrationEntry.java`, `IndexBasedNotificationRegistrationEntry.java`, `ClassLevelNotificationRegistrationEntry.java`, `MithraNotificationEventManagerImpl.java` (dispatch 593-643, executor 665-680, RegistrationEntryList 750-806), `MithraNotificationEvent.java`
- Registration surface: `mithra/list/DelegatingList.java:926`, `mithra/list/AbstractOperationBasedList.java:318`, `mithra/list/AdhocFastList.java:341`, `mithra/portal/MithraAbstractObjectPortal.java:1360-1406`, `mithra/MithraObjectPortal.java:137-144`, `reladomogen/src/main/templates/readonly/Finder.jsp:1533-1548`
- Update hook: `mithra/MithraUpdateListener.java`, `mithra/UpdateInfo.java`, `mithra/MithraUpdateListenerAbstract.java`, `reladomogen/src/main/xsd/mithraobject.xsd:53`, `reladomogen/src/main/templates/transactional/Abstract.jsp:1482`
- Telemetry: `mithra/util/MithraPerformanceData.java`, `mithra/util/PerformanceDataPerOperation.java`, `mithra/MithraManager.java:152-206`, `mithra/MithraTransaction.java:349-351`
- SQL: `mithra/database/MithraAbstractDatabaseObject.java` (loggers 195-198, statsListener 148-193, 1056, 5246), `mithra/database/SqlLogSnooper.java`, `mithra/database/MithraStatsListener.java`, `mithra/database/MithraStatsListenerFactory.java`, `mithra/database/PrintableStatementBuilder.java`, `mithra/finder/PrintablePreparedStatement.java`, `mithra/util/LogAnalyzer.java`
