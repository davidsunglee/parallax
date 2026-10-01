# Transactions are JTA-backed with buffered/batched writes; correctness comes from read locks or optimistic version checks

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/`.

A transaction is `MithraRootTransaction` (extends `MithraLocalTransaction`, implements JTA
`Synchronization`) or a delegating `MithraNestedTransaction`. `MithraManager.executeTransactionalCommand()`
(`mithra/MithraManager.java:524-566`) runs a retry loop: `startOrContinueTransaction()` (begins a JTA
tx + creates the root + installs a per-tx query cache), `command.executeTransaction(tx)`, then
`tx.commit()`; on a retriable `MithraBusinessException` it rolls back and retries (default 10 retries).

The JTA `TransactionManager` is supplied through a one-method `JtaProvider` interface
(`mithra/JtaProvider.java:23-26`). By default `MithraManager` uses its own in-process implementation —
`private JtaProvider jtaProvider = new DefaultJtaProvider(new LocalTm())` (`MithraManager.java:65`),
where `LocalTm` (`mithra/transaction/LocalTm.java`) is a bundled `TransactionManager` and
`DefaultJtaProvider` (`mithra/DefaultJtaProvider.java:22-36`) is a thin holder that returns whatever
manager it was constructed with (no JNDI/auto-discovery). Production code installs a
container-managed or embedded manager via the single setter
`MithraManager.setJtaTransactionManagerProvider(JtaProvider)` (`MithraManager.java:223-226`, documented
as "must be called as part of initialization"). The actual `begin()` happens in
`startOrContinueTransaction`: `getJtaTransactionManager().begin()` (`MithraManager.java:262`), then
`getTransaction()` (264) is wrapped by `createMithraRootTransaction(jtaTx, …)` (404-410), which installs
the per-tx query cache and calls `jtaTx.registerSynchronization(result)`.

Writes are **buffered** as `TxOperations` (`mithra/transaction/TxOperations.java`): `addUpdate` merges
into an existing `UpdateOperation`/`InsertOperation` for the same object; `addInsert` upgrades to
`BatchInsertOperation`; `addDelete` cancels a matching insert. At commit, `executeBufferedOperations()`
runs `combineAll()` (combine/reorder with up to 10-op lookahead to respect FK ordering) then
`op.execute()` per operation, each calling the persister (`MithraAbstractDatabaseObject.zInsert/zUpdate/zBatchUpdate/zDelete`).

```text
executeTransactionalCommand(command)
  startOrContinueTransaction → jtaTx.begin(); new MithraRootTransaction; install per-tx QueryCache
  command.executeTransaction(tx)        # order.setStatus(...) → buffer UpdateOperation
  tx.commit()
    executeBufferedOperations()
      dependentOperations.combineAll()  # merge + order for FK constraints
      for each op: op.execute() → persister.update() → PreparedStatement.executeUpdate()
    jtaTx.commit()
      afterCompletion() → cache.commit(tx); incrementClassUpdateCount; broadcastNotification
```

**Correctness without user intervention.** The default `FullTransactionalParticipationMode` makes
reads inside a transaction acquire a row lock: enrolling a persisted object for read calls
`zRefreshWithLockForRead` → `portal.refresh(data, lockInDatabase=true)`, whose SQL appends a
dialect-specific lock suffix (Oracle `FOR UPDATE OF col`, Sybase `WITH HOLDLOCK`, DB2
`WITH RR USE AND KEEP SHARE LOCKS`). Per-object in-transaction state lives in `TransactionalState`
(`txData != null` ⇒ write-enrolled; null ⇒ read-locked) with an atomically-updated owning-transaction
reference. Deadlocks are detected by a wait-chain check (`waitForTransactionToFinish`), throwing a
retriable `MithraTransactionException`.

**Optimistic locking.** An attribute marked `useForOptimisticLocking="true"` becomes a version column.
In `ReadCacheWithOptimisticLockingTxParticipationMode`, reads do **not** lock; instead the generated
UPDATE appends `AND <version> = ?` (the shadow value read earlier). After `executeUpdate`,
`checkUpdatedRows` (`mithra/database/MithraAbstractDatabaseObject.java:3725-3746`) sees `updatedRows == 0`,
calls `cache.markDirtyForReload`, and throws `MithraOptimisticLockException` (marked retriable when
`tx.retryOnOptimisticLockFailure()`), which the outer retry loop catches — the next attempt re-reads
the fresh version.

More than one updated row is a corruption error rather than an optimistic retry; the
[affected-row checks](29-blind-write-prevention-for-deletes-and-terminates.md#affected-row-checking-is-stricter-for-update-than-for-delete) distinguish those outcomes.

```sql
update OPTIMISTIC_ORDER set STATE = ? where ORDER_ID = ? AND VERSION = ?
-- if 0 rows updated → MithraOptimisticLockException (retriable) → retry with refreshed version
```

## Bitemporal concurrency scope

[Bitemporal writes](06-bitemporal-milestoning.md#writes-resolve-complete-affected-business-ranges)
can affect several business-time intervals under either full or optimistic participation. Their
scope is distinct from the concurrency protection of each consumed physical row.

The initial dated refresh selects the row at the object's own business/processing coordinates.
A missing-range query instead selects current-processing rows overlapping the affected business
range, and can return several rows. Both paths use the portal's effective `mustLockOnRead()`:
full participation requests read locking, while optimistic participation does not. PostgreSQL
renders the requested lock as `FOR SHARE OF t0`.
[Point refresh](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/database/MithraAbstractDatedDatabaseObject.java#L275-L340),
[range query](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/database/MithraAbstractDatedTransactionalDatabaseObject.java#L117-L201),
[full mode](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/txparticipation/FullTransactionalParticipationMode.java#L34-L42),
[optimistic mode](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/txparticipation/ReadCacheWithOptimisticLockingTxParticipationMode.java#L34-L47),
[PostgreSQL suffix](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/databasetype/PostgresDatabaseType.java#L129-L136).

A logical-key temporal container groups interval state and tracks loaded ranges; it is not a
logical-key database lock. Its in-process enrollment of business-object views is distinct from a
JDBC read lock. A point refresh locks its selected row; a locking range query can lock a set of
matching rows. The eventual UPDATE/DELETE write locks apply under either mode.
[Container index](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/cache/AbstractDatedTransactionalCache.java#L812-L832),
[object enrollment](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/PerPortalTemporalContainer.java#L73-L141).

The [dated write predicates](29-blind-write-prevention-for-deletes-and-terminates.md#dated-writes-carry-an-unconditional-milestone-gate-plus-an-optional-processing-date-gate)
validate each physical predecessor separately. No shared logical-key version or range-generation
token appears in the traced range and gate paths. Successors from one transaction can share its
processing timestamp, but changing one interval does not advance every other interval's token.
[Per-row binding](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomogen/src/main/templates/CommonDatabaseObjectAbstract.jspi#L201-L245),
[bounded director](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L1011-L1137).

Row predicates alone do not establish a portable empty-gap or phantom guarantee. The supplied XA
pool obtains isolation from `DatabaseType.zGetTxLevel()`: the abstract default is SERIALIZABLE,
while Oracle overrides it to READ_COMMITTED. Isolation and dialect-specific locking can therefore
add protection beyond row gates; external connection managers and cache-hit paths also matter.
[Pool isolation](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/connectionmanager/XAConnectionPoolingDataSource.java#L406-L421),
[default isolation](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/databasetype/AbstractDatabaseType.java#L727-L730),
[Oracle override](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/databasetype/OracleDatabaseType.java#L530-L534).

A [split-conflict test](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestOptimisticTransactionParticipation.java#L113-L175)
races a cached predecessor against raw SQL that closes it and inserts two successors, then checks
an optimistic retry. This does not prove phantom protection for an empty gap or conflict behavior
for an initially multi-segment range. No such race witness was found in the inspected dated
optimistic and transaction-participation suites; test definitions were inspected, not executed.

## Testing patterns

`TestOptimisticTransactionParticipation.java` runs two-thread races (thread 2 mutates the version via
raw JDBC mid-flight) asserting the exception + retry resolves correctly; `TestDatedBitemporalOptimisticLocking`,
`TestDetachedOptimisticAuditOnly` cover dated/detached variants. `OptimisticOrder.xml` is the fixture.

## Code references

- `mithra/MithraTransaction.java`, `TransactionalCommand.java`, `TransactionalState.java`
- `mithra/transaction/` — `MithraLocalTransaction.java`, `MithraRootTransaction.java` (commit 814, executeBufferedOperations 687), `MithraNestedTransaction.java`, `TxOperations.java`, `AbstractTxOperations.java`, `InsertOperation.java`, `UpdateOperation.java`, `BatchUpdateOperation.java`, `DeleteOperation.java`
- `mithra/behavior/` — `AbstractTransactionalBehavior.java`, `TransactionalBehavior.java`, `state/PersistenceState.java` (40-58), `persisted/PersistedTxEnrollBehavior.java`, `detached/DetachedNoTxBehavior.java`, `txparticipation/{Full,ReadCacheWithOptimisticLocking}TransactionalParticipationMode.java`, `MithraOptimisticLockException.java`
- `mithra/database/MithraAbstractDatabaseObject.java` — checkUpdatedRows/throwOptimisticLockException (3725, 4978), refresh+lock (2225), getOptimisticLockingWhereSqlIfNecessary (4927)
