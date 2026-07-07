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
`checkUpdatedRows` (`mithra/database/MithraAbstractDatabaseObject.java:3725-3746`) sees `updatedRows != 1`,
calls `cache.markDirtyForReload`, and throws `MithraOptimisticLockException` (marked retriable when
`tx.retryOnOptimisticLockFailure()`), which the outer retry loop catches — the next attempt re-reads
the fresh version.

```sql
update OPTIMISTIC_ORDER set STATE = ? where ORDER_ID = ? AND VERSION = ?
-- if 0 rows updated → MithraOptimisticLockException (retriable) → retry with refreshed version
```

## Testing patterns

`TestOptimisticTransactionParticipation.java` runs two-thread races (thread 2 mutates the version via
raw JDBC mid-flight) asserting the exception + retry resolves correctly; `TestDatedBitemporalOptimisticLocking`,
`TestDetachedOptimisticAuditOnly` cover dated/detached variants. `OptimisticOrder.xml` is the fixture.

## Code references

- `mithra/MithraTransaction.java`, `TransactionalCommand.java`, `TransactionalState.java`
- `mithra/transaction/` — `MithraLocalTransaction.java`, `MithraRootTransaction.java` (commit 814, executeBufferedOperations 687), `MithraNestedTransaction.java`, `TxOperations.java`, `AbstractTxOperations.java`, `InsertOperation.java`, `UpdateOperation.java`, `BatchUpdateOperation.java`, `DeleteOperation.java`
- `mithra/behavior/` — `AbstractTransactionalBehavior.java`, `TransactionalBehavior.java`, `state/PersistenceState.java` (40-58), `persisted/PersistedTxEnrollBehavior.java`, `detached/DetachedNoTxBehavior.java`, `txparticipation/{Full,ReadCacheWithOptimisticLocking}TransactionalParticipationMode.java`, `MithraOptimisticLockException.java`
- `mithra/database/MithraAbstractDatabaseObject.java` — checkUpdatedRows/throwOptimisticLockException (3725, 4978), refresh+lock (2225), getOptimisticLockingWhereSqlIfNecessary (4927)
