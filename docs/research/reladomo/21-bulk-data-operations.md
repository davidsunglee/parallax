# Bulk data flows through four seams: key-matched `merge()`, in-memory `applyOperation`, streaming `DatabaseCursor`, and BCP `BulkLoader`s

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`test/`** =
> `reladomo/src/test/java/com/gs/fw/common/mithra/test/`.

## List merge/diff (`merge()` + `MergeOptions`)

Entry point: `MithraTransactionalList.merge(MithraList<E> incoming, TopLevelMergeOptions<E> mergeOptions)`
(`mithra/MithraTransactionalList.java:48`). The receiver list is the **DB baseline** (an operation-based
list is first copied via `asAdhoc()`, `mithra/list/DelegatingList.java:1174`); `incoming` holds the new
state (typically in-memory/detached objects). The adhoc delegate wraps a `MergeBuffer` in a single
transactional command (`mithra/list/AbstractTransactionalNonOperationBasedList.java:256`).

`MergeBuffer.mergeLists` (`mithra/list/merge/MergeBuffer.java:167`) indexes `incoming` in a
`FullUniqueIndex` keyed on the match extractors — default: primary-key attributes, minus any foreign
keys of a navigated relationship (`resolveToMatchOn`, line 608); overridable via
`MergeOptions.matchOn(Extractor...)`. Then per baseline element: **matched** → `considerUpdate`
(line 218) compares all persistent attributes except match keys and `doNotCompare` (with PK-match and
no exclusions, a canonical `nonPrimaryKeyAttributesChanged` comparator, line 129); **unmatched
baseline** → `considerTermination` (line 346); **leftover incoming** → `considerInsert` (line 296).
Duplicates on either side raise `MithraBusinessException` unless `TAKE_LAST_DUPLICATE` is configured
(`MergeOptions.DuplicateHandling`, `mithra/list/merge/MergeOptions.java:40`).

`executeBufferForPersistence` (line 467) then runs deletes/terminates **bottom-up** — `terminate()` for
dated classes, `delete()` otherwise (lines 592-596) — updates **top-down** via `Attribute.copyValueFrom`
over persistent attributes minus PK, match keys, `doNotUpdate`, FKs, and as-of columns
(`getAttributesToUpdate`, line 522), and inserts **top-down** (line 481).

Hooks and options (`mithra/list/merge/`): `doNotCompare` / `doNotUpdate` / `doNotCompareOrUpdate`
(`MergeOptions.java:90,111,127`); `withMergeHook` — `MergeHook` (`MergeHook.java:19`) can veto or
redirect each phase (`matchedNoDifference`, `matchedWithDifferenceBeforeAttributeCopy` →
`UPDATE`/`DO_NOT_UPDATE`/`TERMINATE_AND_INSERT_INSTEAD`, `beforeInsertOfNew`,
`beforeDeleteOrTerminate`); `NoDeleteOrTerminateMergeHook` turns the merge insert/update-only.
`TopLevelMergeOptions.navigateTo(navigation)` / `navigateToAllDeepDependents()`
(`TopLevelMergeOptions.java:85,130`) extend the merge to **dependent** relationships only (non-dependents
throw), building a `MergeOptionNode` tree mirrored by child `MergeBuffer`s that fix FKs through the
relationship setters. A detached variant (`mithra/list/DetachedList.java:79`) runs
`MergeBuffer(options, detached=true)`: attribute copies and list removals happen in memory, nothing is
persisted.

```java
OrderList dbList = OrderFinder.findMany(OrderFinder.userId().eq(1));   // baseline
TopLevelMergeOptions<Order> opts = new TopLevelMergeOptions<>(OrderFinder.getFinderInstance());
opts.matchOn(OrderFinder.trackingId());
opts.doNotUpdate(OrderFinder.orderDate());
opts.navigateToAllDeepDependents();
MithraList<Order> merged = dbList.merge(incomingOrders, opts);          // insert/update/delete diff
```

## In-memory evaluation over adhoc lists

`Operation.applyOperation(List)` (`mithra/finder/Operation.java:65`) "applies the operation to a
pre-determined list", returning `null` when it cannot be evaluated in memory;
`zCanFilterInMemory()` (line 145) advertises capability. Atomic operations
(`mithra/finder/AbstractAtomicOperation.java:160`) test `matches(item)` per element, return the *same*
list instance when everything matches, and fan out to `MithraCpuBoundThreadPool` for large lists
(line 167). `AndOperation` chains operands over the shrinking result (`AndOperation.java:605`);
`OrOperation` unions per-operand results using an identity index of leftovers (`OrOperation.java:274`);
`All` returns the input, `None` returns an empty list (`All.java:126`, `None.java:122`).
`MappedOperation.applyOperation` (`MappedOperation.java:156`) evaluates relationship-mapped clauses via
the **reverse mapper** (mapping the candidate list to the related side, filtering, then matching back
through a `ConcurrentFullUniqueIndex`), with one-by-one and partial-cache fallbacks; it returns `null`
if no reverse mapper exists. Callers: cache-side query resolution `zFindInMemory`
(`mithra/portal/MithraAbstractObjectPortal.java:483`), cursor post-load filters (below), the cache
loader (`mithra/cacheloader/DependentKeyIndex.java:56`,
`QualifiedByOwnerObjectListLoadContext.java:66`), mass-delete notification processing
(`mithra/notification/IndexBasedNotificationRegistrationEntry.java:68`), and join filters in
`mithra/finder/FilteredMapper.java:100-169`.

## Streaming cursor reads

`MithraList.forEachWithCursor(DoWhileProcedure[, Operation|Filter])` (`mithra/MithraList.java:81-85`);
the javadoc (lines 64-79) positions it for huge, operation-based lists on partially cached classes —
objects are loaded one by one into the weak part of the cache, iteration stops when the closure returns
`false`, and **deep fetch is not supported** (use `iterator()` instead). The `Operation` overload wraps
the filter in an `OperationBasedFilter` (`mithra/list/DelegatingList.java:294-296`).
`AbstractOperationBasedList.forEachWithCursor` (`mithra/list/AbstractOperationBasedList.java:380`) first
tries `resolveOperationInMemory` (line 254, full/partial cache hit → plain loop), otherwise opens a
cursor (line 235) via `portal.findCursorFromServer(op, postLoadFilter, orderBy, maxObjectsToRetrieve,
bypassCache, numberOfParallelThreads, forceImplicitJoin)`
(`mithra/portal/MithraAbstractObjectPortal.java:589`, retry loop at 606) and drains it in a
`try/finally { c.close(); }`. The `Cursor` interface is just `Iterator` + `close()`
(`mithra/list/cursor/Cursor.java:23`). `DatabaseCursor`
(`mithra/database/MithraAbstractDatabaseObject.java:819`) builds a `SqlQuery` with forced server-side
order-by (line 862), then walks source attributes and unioned statements one `ResultSet` at a time:
`hasNext()` (line 994) advances the ResultSet (re-preparing per source, honoring `maxRowCount`) and
inflates one row — `inflateDataGenericSource` + `cache.getObjectFromDataWithoutCaching`, skipping rows
that fail the post-load filter (lines 1092-1097); `close()` (line 1045) closes
ResultSet/Statement/Connection and records SQL-performance stats. Dated classes use the `DatedCursor`
subclass (`mithra/database/MithraAbstractDatedDatabaseObject.java:111`).
`setNumberOfParallelThreads(int)` exists on all lists (`mithra/list/DelegatingList.java:149`, stored at
`AbstractOperationBasedList.java:143`); it is forwarded to `findCursor` as `maxParallelDegree` but the
JDBC cursor itself is single-threaded (`MithraAbstractDatabaseObject.java:1223-1225` ignores it) — the
setting parallelizes list resolution and deep fetch (`AbstractOperationBasedList.java:360`). On adhoc
lists `forEachWithCursor` is a plain in-memory loop
(`mithra/list/AbstractNonOperationBasedList.java:188-196`).

## DB-native bulk load

`BulkLoader` (`mithra/bulkloader/BulkLoader.java:28`): `initialize(dbTimeZone, schema, tableName,
attributes, logger, tempTableName, columnCreationStatement, con)`, `bindObjectsAndExecute(list, con)`,
`destroy()`, `dropTempTable(name)`, `createsTempTable()`. Routing: `bulkInsertAll()` on an adhoc list
(`mithra/list/TransactionalAdhocFastList.java:96`) runs `InsertAllTransactionalCommand(this, 100)`,
which calls `tx.setBulkInsertThreshold(100)` (`mithra/list/InsertAllTransactionalCommand.java:46-48`);
operation-based lists throw (`mithra/list/AbstractTransactionalOperationBasedList.java:179`). At flush,
`BatchInsertOperation` reads the transaction threshold (`mithra/transaction/BatchInsertOperation.java:86`)
and `zBatchInsertForSameSourceAttribute` (`mithra/database/MithraAbstractDatabaseObject.java:4631`)
picks bulk when `bulkInsertThreshold > 0 && size > threshold && databaseType.hasBulkInsert()`, else
multi-row insert, else JDBC batch. The bulk path (`zBulkInsertListForSameSourceAttribute`, line 4472)
gets a loader from the connection manager (`createBulkLoader()`,
`mithra/connectionmanager/SourcelessConnectionManager.java:39`); if `createsTempTable()`, it BCPs into a
generated temp table (`assignTempTableName`, line 3172) in `databaseType.getTempDbSchemaName()`
(temp DB), then issues `insert into <table> select * from <tempTable>` and registers a
`DropBulkTempTableSynchronization` to drop it after commit. Tuple temp contexts reuse the same
machinery (`bulkInsertTuplesForSameSource`, line 3094).

`hasBulkInsert()` defaults to `false` (`mithra/databasetype/AbstractDatabaseType.java:373`;
`MsSqlDatabaseType.java:609` is also `false`). `SybaseDatabaseType` returns true when a bulk constructor
was reflectively loaded or file mode is forced (`SybaseDatabaseType.java:1137`); its constructor
(lines 261-278) loads `com.gs.fw.common.mithra.bulkloader.JtdsBcpBulkLoader` — shipped in the
**reladomogs** module (`reladomogs/src/main/java/com/gs/fw/common/mithra/bulkloader/JtdsBcpBulkLoader.java:55`)
— selected by system property `com.gs.fw.common.mithra.databasetype.SybaseDatabaseType.bulkInsertMethod`
(`jtds` default, or `file`). `createBulkLoader(user, password, hostName, port)`
(`SybaseDatabaseType.java:668-690`) returns `BcpBulkLoader` (spawns the `bcp` command-line against a
`SybaseBcpFile` data file, `mithra/bulkloader/BcpBulkLoader.java:43`) when file mode/no host, else a
`JtdsBcpBulkLoader` (pooled jTDS `jdbc:jbcp:sybase://host:port` connections; `createsTempTable()` =
`true`, line 459). `SybaseIqDatabaseType.createBulkLoader(dbLoadDir, appLoadDir)`
(`mithra/databasetype/SybaseIqDatabaseType.java:201`) returns `SybaseIqBulkLoader`, which writes a data
file to a shared directory and executes `load table ...` (`mithra/bulkloader/SybaseIqBulkLoader.java:197`);
`SybaseIqNativeDatabaseType` (line 58) returns `SybaseIqNativeBulkLoader`.

## Testing patterns

`test/TestListMerge.java` (4 tests: `testShallow`, `testShallowAudited` — terminate path, `testDeep`,
`testDeepFullDependents`; all use `matchOn(OrderFinder.trackingId())`). `test/TestCursor.java` covers
operation/non-operation and dated/non-dated iteration, post-load operation filters, early break, and
connection cleanup after mid-cursor exceptions. `test/bulkloader/BulkLoaderTestSuite.java` unit-tests
the formatters and `SybaseBcpFileTest`; end-to-end bulk inserts run in `TestSybaseGeneralTestCases` /
`SybaseBcpTestAbstract` (require a live Sybase). Adhoc in-memory behavior:
`TestTransactionalAdhocFastList`, `TestAdhocDeepFetch`.

## Code references

- `mithra/MithraTransactionalList.java` (merge 48, bulkInsertAll 35); `mithra/list/DelegatingList.java` (merge 1174, forEachWithCursor 284-306, setNumberOfParallelThreads 149)
- `mithra/list/merge/`: `MergeOptions.java`, `TopLevelMergeOptions.java` (navigateTo 85), `MergeBuffer.java` (mergeLists 167, executeBufferForPersistence 467, resolveToMatchOn 608), `MergeHook.java`, `NoDeleteOrTerminateMergeHook.java`, `MergeOptionNode.java`, `NavigatedMergeOption.java`; `mithra/list/DetachedList.java` (79)
- `mithra/finder/Operation.java` (applyOperation 65, zCanFilterInMemory 145); `AbstractAtomicOperation.java` (160), `AndOperation.java` (605), `OrOperation.java` (274), `MappedOperation.java` (156), `NotExistsOperation.java` (166), `All.java`/`None.java`/`NoOperation.java`
- `mithra/list/cursor/Cursor.java`; `mithra/list/AbstractOperationBasedList.java` (createCursor 235, forEachWithCursor 380); `mithra/portal/MithraAbstractObjectPortal.java` (findCursorFromServer 589); `mithra/database/MithraAbstractDatabaseObject.java` (DatabaseCursor 819, findCursor 1223); `MithraAbstractDatedDatabaseObject.java` (DatedCursor 111)
- `mithra/bulkloader/` (BulkLoader 28, BcpBulkLoader, SybaseIqBulkLoader, SybaseIqNativeBulkLoader, SybaseBcpFile); `reladomogs/.../bulkloader/JtdsBcpBulkLoader.java`; `mithra/databasetype/SybaseDatabaseType.java` (261-278, 668-690, hasBulkInsert 1137), `SybaseIqDatabaseType.java` (201), `SybaseIqNativeDatabaseType.java` (58), `AbstractDatabaseType.java` (373); `mithra/database/MithraAbstractDatabaseObject.java` (zBatchInsertForSameSourceAttribute 4631, zBulkInsertListForSameSourceAttribute 4472, bulkInsertTuplesForSameSource 3094); `mithra/transaction/BatchInsertOperation.java` (86); `mithra/connectionmanager/SourcelessConnectionManager.java` (39)
