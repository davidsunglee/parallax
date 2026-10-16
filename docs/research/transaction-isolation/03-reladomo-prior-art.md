---
date: 2026-10-16
git_commit: 8886e730c2f97b54f72bd6b9dce516aec1d36126
topic: "Reladomo prior art for transaction isolation, read participation, write gates, streaming and cache, and retry timing"
type: research
tags: [research, reladomo, isolation, read-only, participation, retry, backoff, streaming]
status: complete
---

# Reladomo: Isolation, Participation, and Retry Timing

> Prior art for [Research: Reladomo Core Features](../reladomo/00-index.md).
> Reladomo is at commit `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`, read from a
> peer checkout, and Parallax at the commit in the front matter.
>
> - Reladomo paths are relative to that checkout's root. **`mithra/`** means
>   `reladomo/src/main/java/com/gs/fw/common/mithra/`, and **`templates/`**
>   means `reladomogen/src/main/templates/`.
> - Source and first-party test definitions were inspected on 2026-10-16. No
>   Reladomo test was executed.

In Reladomo, transaction isolation is a per-dialect connection default,
read-only is a class property, and retries wait a flat randomized one to two
seconds after rollback. This note records that behavior, with Reladomo's read
participation, write gates, and streaming and cache behavior, as prior art for
evaluating Parallax's isolation default. It is descriptive and recommends no
Parallax semantics.

Existing notes already own parts of the subject. This note links to them
rather than restating them:

- [09](../reladomo/09-transactions-locking.md): the retry loop's shape,
  locking reads, optimistic version checks, and bitemporal concurrency scope.
- [23](../reladomo/23-transaction-integration.md): nesting, which joins the
  outer transaction with no inner retry, and JTA/XA integration.
- [27](../reladomo/27-read-enrollment-and-write-licensing.md): read-enrollment
  structures and the source of the gate value.
- [28](../reladomo/28-transaction-participation-mode-scope.md): per-class
  participation modes within one transaction.
- [29](../reladomo/29-blind-write-prevention-for-deletes-and-terminates.md):
  delete and terminate gates.
- [10](../reladomo/10-object-lifecycle.md#detached-merge-version-checks-and-retries):
  the retry-dependent detached version check.
- [08](../reladomo/08-caching.md) and
  [21](../reladomo/21-bulk-data-operations.md#streaming-cursor-reads): caches
  and the streaming cursor.

This note adds:

- the isolation level each dialect requests, and the read path that leaves the
  transaction's connection;
- the absence of a per-transaction read-only mode;
- what a non-transactional result retains;
- how each dialect classifies retriable failures;
- the wait between attempts, and when it starts.

## Isolation is fixed per dialect by the bundled connection pool

The bundled `XAConnectionPoolingDataSource` serves two kinds of connection:

- A transaction's connection is set to `autoCommit=false` and
  `setTransactionIsolation(databaseType.zGetTxLevel())`
  (`mithra/connectionmanager/XAConnectionPoolingDataSource.java:406-421`).
- A connection outside a transaction is set to `autoCommit=true` and
  `TRANSACTION_READ_COMMITTED` (`:124-136`).

`zGetTxLevel()` returns `TRANSACTION_SERIALIZABLE` in `AbstractDatabaseType`
(`mithra/databasetype/AbstractDatabaseType.java:727-730`). Only two dialects
override it, both with `TRANSACTION_READ_COMMITTED`:

- Oracle (`mithra/databasetype/OracleDatabaseType.java:530-534`).
- Snowflake (`mithra/databasetype/SnowflakeDatabaseType.java:197-201`).

Every other dialect therefore requests Serializable for transaction
connections. That covers PostgreSQL, MariaDB, Sybase ASE and IQ, DB2
(`Udb82DatabaseType`), MS SQL, H2, Derby, and Generic. Reladomo has no separate
MySQL dialect; `MariaDatabaseType` is the only member of that family in
`mithra/databasetype/`.

The transaction API cannot configure the isolation level:

- `TransactionStyle` carries only retries, timeout, and retry-after-timeout
  (`mithra/transaction/TransactionStyle.java:19-76`).
- No other runtime call sets an isolation level.
- `XAConnectionManager`'s connection wrapper only skips redundant
  `setTransactionIsolation` calls
  (`mithra/connectionmanager/XAConnectionManager.java:442-455`).
- A user-supplied connection manager returns its own connections, so their
  isolation is outside Reladomo's control
  ([09](../reladomo/09-transactions-locking.md#bitemporal-concurrency-scope)).

Statement-level hints then modify each read inside a transaction. Each dialect
chooses the hint from the result portal's effective `mustLockOnRead()`:

| Dialect | Locking read in a transaction | Non-locking read in a transaction | Source |
|---|---|---|---|
| PostgreSQL | `FOR SHARE OF t0` | no hint | `PostgresDatabaseType.java:111-137` |
| MariaDB | `LOCK IN SHARE MODE` | no hint | `MariaDatabaseType.java:110-136` |
| Oracle | `FOR UPDATE OF <first column>` | no hint | `OracleDatabaseType.java:111-149` |
| Sybase ASE | per-table `holdlock` | per-table `noholdlock` | `SybaseDatabaseType.java:338-345`, `:380-391`, `:1120-1129` |
| DB2 | `FOR READ ONLY WITH RR USE AND KEEP SHARE LOCKS` | `FOR READ ONLY WITH CS` | `Udb82DatabaseType.java:46-48`, `:113-155` |
| MS SQL | `with (serializable)` | `with (nolock)` | `MsSqlDatabaseType.java:209-212`, `:252-262`, `:597-606` |

On Sybase, DB2, and MS SQL, a non-locking read on a Serializable transaction
connection is therefore weakened statement by statement:

- `noholdlock` releases shared locks.
- `WITH CS` is cursor stability.
- `with (nolock)` is SQL Server's read-uncommitted table hint.

On PostgreSQL and MariaDB the non-locking read gets no hint and runs at the
connection's level. According to MariaDB's documentation, InnoDB at
Serializable with autocommit off converts plain `SELECT`s into shared-locking
reads. That is provider behavior, not something Reladomo emits.

### Non-locking reads before enlistment use a separate autocommit connection

Before each query, `prepareForQuery` sets the transaction's operation mode
(`mithra/database/MithraAbstractDatabaseObject.java:567-587`). The mode is
`TRANSACTIONAL_READ` if the target portal or any dependent portal must lock on
read, and `READ` otherwise. `isWriteOperationMode()` treats every mode except
`READ` as write mode (`mithra/MithraTransaction.java:302-305`).

The pool then routes the connection request
(`XAConnectionPoolingDataSource.java:69-107`):

- Suppose the transaction has not yet enlisted a JDBC resource and the mode is
  `READ`. The pool then returns `getConnectionForNoTransaction()`, which is
  autocommit at Read Committed.
- Once a write, locking read, or temp-table write has enlisted the resource,
  every later read uses the transaction's connections at `zGetTxLevel()`.

Under optimistic or other non-locking participation, the reads before the
first enlisting statement therefore run outside the database transaction.
Each sees committed data per statement, whatever level the transaction
connection would have requested.

The enlisted resource also keeps a list of connections (`:359-405`). A
connection returned with `close()` is reused within the transaction
(`:259-262`, `:369-375`). Concurrent use, such as an open cursor, can hold
more than one connection, and each is a separate database transaction.

## Read-only is a class property, not a transaction mode

The runtime has no read-only transaction entrypoint or access mode:

- Nothing calls `Connection.setReadOnly(true)` or issues
  `SET TRANSACTION READ ONLY`. `WrappedConnection.setReadOnly` only delegates
  (`mithra/util/WrappedConnection.java:98-101`).
- DB2's `FOR READ ONLY` is a cursor clause appended to every select, not a
  transaction access mode (`Udb82DatabaseType.java:46`, `:120`).

Read-only exists per class:

- `MithraReadOnlyPortal` fixes participation to
  `ReadCacheUpdateNotAllowedTxParticipationMode`, which neither locks nor
  participates on read.
- The portal refuses mode changes, deletes, and purges
  (`mithra/portal/MithraReadOnlyPortal.java:41-61`, `:88-93`;
  `mithra/behavior/txparticipation/ReadCacheUpdateNotAllowedTxParticipationMode.java`).

A transactional class can be made non-locking for one transaction only
through its portal's participation mode
([28](../reladomo/28-transaction-participation-mode-scope.md)).
`ReadCacheUpdateCausesRefreshAndLockTxParticipationMode` reads without locks
and refreshes with a lock when the object is enrolled for write
(`mithra/behavior/persisted/PersistedTxEnrollBehavior.java:62-77`). No mode
prohibits writes in a transaction.

The closest analog of a standalone read is a read outside any transaction. It
uses the autocommit Read Committed connection and is retried individually
(see *Retry timing*).

## Participation enrolls objects on access, from wherever they were read

Under `FullTransactionalParticipationMode`, reading an attribute inside a
transaction enrolls the object
(`mithra/behavior/state/PersistenceState.java:135-170`). Enrollment re-reads it
with a lock, through `zRefreshWithLockForRead`
(`PersistedTxEnrollBehavior.java:56-60`;
[09](../reladomo/09-transactions-locking.md)). The object can come from a read
outside the transaction or from an earlier transaction. Reladomo enrolls and
refreshes it rather than refusing it.

Optimistic participation does not enroll on read. Write enrollment does not
refresh, and the gate binds the version or `IN_Z` that the object's current
data carries (`PersistedTxEnrollBehavior.java:62-71`;
[27](../reladomo/27-read-enrollment-and-write-licensing.md#every-dated-update-is-gated-on-the-milestones-end-columns-in-both-locking-modes)).

Inside a transaction, the participation mode decides when the cache is
trusted:

- Full participation distrusts a full-cache hit unless every result object
  already participates. Otherwise it waits for other writers and goes to the
  database (`mithra/portal/MithraTransactionalPortal.java:257-288`).
- When neither the target portal nor its dependent portals require
  participation, a fully cached query is answered from the cache with no SQL
  (`:264-266`, `:291-308`).

Each transaction also gets its own query cache (`:72-75`).

## Gates use the cached data's token; the detached copy carries an earlier observation

The gate mechanics are owned by [09](../reladomo/09-transactions-locking.md),
[27](../reladomo/27-read-enrollment-and-write-licensing.md), and
[29](../reladomo/29-blind-write-prevention-for-deletes-and-terminates.md):

- Version or `IN_Z` predicates sit in the shared primary-key where clause for
  UPDATE and DELETE.
- Every dated write carries a milestone gate in every mode.
- Full participation on a non-dated class gates nothing and relies on the
  refresh-with-lock instead.

Three points from those notes bear on this note's subject:

- **The token is part of the cached carrier.** `zGetPersistedVersion()` reads
  the data object's own version field, adjusted by `_versionIncremented`
  (`templates/readonly/DataOnHeap.jspi:399-410`). Reladomo keeps no separate
  observation record.
- **An optimistic failure is retriable only on request.**
  - A zero-row result marks the data dirty for reload and throws
    `MithraOptimisticLockException`. The exception is retriable only if
    `tx.retryOnOptimisticLockFailure()`
    (`mithra/database/MithraAbstractDatabaseObject.java:4978-4986`).
  - That flag defaults to `false`
    (`mithra/transaction/MithraRootTransaction.java:69`, `:82-91`).
  - The bundled queue executors set it to `true`
    (`mithra/util/SingleQueueExecutor.java:847`,
    `mithra/util/MultiQueueExecutor.java:454`).
- **Detached merge is the path for an earlier observation.** When retry is
  enabled, the in-memory version comparison is skipped, so the detached token
  is not kept as a fixed precondition across attempts
  (`mithra/superclassimpl/MithraTransactionalObjectImpl.java:1411-1427`;
  [10](../reladomo/10-object-lifecycle.md#detached-merge-version-checks-and-retries)).
  This pass found no keyed write that accepts a caller-supplied expected
  version.

## Streaming and cache qualifications

`DatabaseCursor`
([21](../reladomo/21-bulk-data-operations.md#streaming-cursor-reads)) holds one
connection, statement, and `ResultSet` per source or union statement for as
long as iteration continues (`MithraAbstractDatabaseObject.java:819-830`,
`:915-971`). Outside a transaction, that connection is the autocommit Read
Committed one.

Reladomo never sets a JDBC fetch size; `setFetchSize` appears only in
delegating wrappers. The driver's default therefore decides how many rows are
buffered. pgjdbc, for example, materializes the whole result unless a fetch
size is set with autocommit off.

Rows are interned weakly through `getObjectFromDataWithoutCaching`
(`mithra/cache/AbstractNonDatedCache.java:1157-1160`,
`mithra/cache/AbstractDatedCache.java:1385-1388`).

- Outside a transaction, retry covers opening each statement
  (`MithraAbstractDatabaseObject.java:885-913`).
- A failure while advancing the `ResultSet` is wrapped and thrown
  (`:994-1031`).
- Inside a transaction the cursor has no retry of its own; replaying the whole
  command reruns it.

A non-transactional result retains nothing beyond the shared identity-cache
object:

- That object's current data carries the gate token. Later re-reads or
  notification refreshes can replace that data
  ([08](../reladomo/08-caching.md)).
- An object read outside a transaction has no transactional state until a
  transaction touches it.
- The explicit snapshot is a detached copy.

Query-cache and identity-cache hits outside a transaction never reach the
database. A result assembled from them reflects cache state, not one
statement's snapshot ([08](../reladomo/08-caching.md)).

## Retry classification

`executeTransactionalCommand` runs `retries + 1` executions
(`mithra/MithraManager.java:524-564`). `handleTransactionException` decides
whether to retry (`mithra/MithraTransaction.java:125-192`):

- A failure is retried only if it is a `MithraBusinessException` and one of
  two conditions holds (`:136-137`):
  - `tx.startedTransaction() && isRetriable()`, or
  - `style.isRetriableAfterTimeout() && isTimedOut()`.
- Any other `RuntimeException` is never retried.
- A joined transaction (`startedTransaction() == false`) never retries
  ([23](../reladomo/23-transaction-integration.md)).

The defaults are:

- 10 retries (`MithraTransaction.java:54`; `TransactionStyle.java:21`).
- A 60-second transaction timeout (`MithraManager.java:67`).
- Retry after timeout off (`MithraManager.java:77`, `:172-176`).

`analyzeAndWrapSqlExceptionGenericSource` sets the retriable flag from the
dialect's check, and otherwise sets the timed-out flag. The checks walk both
`getNextException()` and the cause chain
(`MithraAbstractDatabaseObject.java:2477-2512`;
`AbstractDatabaseType.java:189-208`). A dead connection is marked dead and
treated as retriable, unless it was killed and no retries remain
(`MithraAbstractDatabaseObject.java:2499-2511`).

| Dialect | Retriable | Timed out (retried only with retry-after-timeout) | Source |
|---|---|---|---|
| PostgreSQL | SQLSTATE `40P01` or `40001` | never | `PostgresDatabaseType.java:44-45`, `:190-198` |
| MariaDB | vendor error code `== 40001` | vendor code `1205` (lock wait timeout) | `MariaDatabaseType.java:49-51`, `:179-187` |
| Oracle | vendor error code `== 40001` | a specific state/code pair | `OracleDatabaseType.java:206-214` |
| Sybase ASE | `1205` deadlock, schema change, closed connection, batch deadlock message, jTDS server close | listed states/codes | `SybaseDatabaseType.java:419-438` |
| DB2 | `-911`, `57033`, `40001` | `-911` with reason `00C9008E` | `Udb82DatabaseType.java:34-37`, `:190-203` |
| MS SQL | `1205` or deadlock victim | listed states/codes | `MsSqlDatabaseType.java:287-305` |
| H2 | vendor error code `40001` | a specific state/code pair | `H2DatabaseType.java:204-212` |

The MariaDB and Oracle checks compare the vendor error code with `40001`, not
the SQLSTATE. MariaDB documents a deadlock as error `1213` with SQLSTATE
`40001`. As written, the check matches only if a driver reports `40001` as the
vendor code. This pass did not execute that path.

In-memory conflicts are retriable without the database:

- A wait-chain cycle throws
  `MithraTransactionException("Deadlock detected.", this)`
  (`mithra/transaction/MithraLocalTransaction.java:311-314`, `:542-575`).
- Conflicting write intents throw retriable exceptions that carry the blocking
  transaction (`MithraTransactionalObjectImpl.java:1482`, `:1535`).

## Retry timing

**The wait follows rollback and connection close.** For a retriable failure,
`handleTransactionException` calls `tx.rollbackWithCause` and then
`mithraException.waitBeforeRetrying()` (`MithraTransaction.java:151-156`).
With the bundled `LocalTm` and pool, rollback is synchronous through to the
connection:

1. `MithraRootTransaction.rollback`
   (`mithra/transaction/MithraRootTransaction.java:913-973`).
2. `LocalTx.rollback`, which rolls back resources and then runs
   `afterCompletion` (`mithra/transaction/LocalTx.java:285-300`).
3. The XA resource rollback (`XAConnectionPoolingDataSource.java:490-532`).
4. `protectedRollback`, which rolls back and closes the underlying connection,
   returning it to the pool (`:300-344`).

The connection is therefore released before the wait. Under a container
transaction manager the order depends on that manager. Reladomo's own test of
the manual pattern follows the same order: `tx.rollback()`, then
`mbe.waitBeforeRetrying()`
(`reladomo/src/test/java/com/gs/fw/common/mithra/test/TestConcurrentTransactions.java:890-899`).

**The default wait is flat and randomized.**
`MithraBusinessException.waitBeforeRetrying()` calls
`MithraManager.sleepBeforeTransactionRetry()`
(`mithra/MithraBusinessException.java:90-93`). That method sleeps
`RETRY_TRANSACTION_TIME/2 + nextInt(RETRY_TRANSACTION_TIME/2)`, with
`RETRY_TRANSACTION_TIME = 2000` (`MithraManager.java:62-63`, `:427-435`,
`:568-578`).

- The draw is a uniform integer number of milliseconds in [1000, 2000).
- It comes from one process-wide `Random` under a lock.
- The delay does not grow with the attempt number.
- The constant is `private static final` and has no setter.

At the default bound, ten waits add roughly 10 to 20 seconds to an exhausted
invocation.

**A conflict with a known blocker waits for that transaction instead.**

- `MithraTransactionException.waitBeforeRetrying()` overrides the sleep when
  the exception carries a `transactionToWaitFor`, as the in-memory deadlock
  and write-intent conflicts do.
- It waits until that transaction finishes, up to a static 30 seconds
  (`mithra/MithraTransactionException.java:30`, `:75-89`;
  `MithraLocalTransaction.java:655-690`).
- It waits for a remote transaction when one is identified, and otherwise
  falls back to the flat sleep.
- `MithraOptimisticLockException` from the SQL gate carries no blocker, so it
  takes the flat sleep.

**Reads outside a transaction use the same wait.**

- Finds, aggregate finds, and cursor preparation outside a transaction retry
  through `ifRetriableWaitElseThrow`, which uses the same wait
  (`MithraBusinessException.java:53-66`;
  `mithra/portal/MithraAbstractObjectPortal.java:596-620`, `:1004-1019`,
  `:1279-1293`; `MithraAbstractDatabaseObject.java:885-913`).
- Its `--retriesLeft > 0` test allows at most ten executions.
- Inside a transaction these paths do not retry. The whole command is retried
  instead (`MithraAbstractObjectPortal.java:596-603`, `:1006`).

## Relevance to Parallax

The observations below compare structure only; they do not recommend adopting
Reladomo behavior. Parallax's contracts live in `core/spec/m-execution.md`,
`m-unit-work.md`, `m-auto-retry.md`, and `m-read-delivery.md`.

- **Isolation.**
  - *Reladomo:*
    - The bundled pool requests Serializable on transaction connections for
      most dialects, including PostgreSQL and MariaDB, and Read Committed for
      Oracle and Snowflake.
    - Reads outside a transaction run at autocommit Read Committed.
    - No per-transaction choice exists.
    - The transaction's level does not reach non-locking reads that precede
      enlistment.
    - Statement hints weaken non-locking reads on Sybase, DB2, and MS SQL.
  - *Parallax:*
    - Each attempt requests a concrete level. The default is Read Committed,
      with explicit per-invocation overrides (`m-execution` *Options a root is
      configured with*).
    - Standalone reads open no transaction.
    - The level applies to every read form in the boundary (`m-unit-work`
      *The Isolation Level beside it — what the transaction READS*).
- **Read-only.**
  - *Reladomo:* read-only is a class property with no transaction access mode.
  - *Parallax:* `read_only` is an invocation mode. It requests a native
    read-only boundary on every attempt, takes no participation locks, and
    refuses cross-mode joins (`m-execution` *Read-only transactions*).
- **Participation.**
  - *Reladomo:* full mode enrolls any object on access and refreshes it under
    lock. Optimistic mode trusts the object's current cached data.
  - *Parallax:* an ordinary source mutation requires current-attempt read
    evidence or insertion authority. It refuses standalone, earlier-attempt,
    and read-only sources (`m-unit-work` *Current-attempt source admission*).
- **Gates and external observations.**
  - *Reladomo:* the comparable path is detached merge. With optimistic retry
    enabled, its in-memory version check is skipped, so the observation is
    rebased.
  - *Parallax:* the `*_if` family holds the caller's revision fixed across
    replays and has no unversioned form.
  - *Both:* each system gates versioned and transaction-time writes on the
    predecessor's token, and protects unversioned non-temporal writes with a
    read lock instead of a gate.
- **Retry eligibility.**
  - *Reladomo:* optimistic failures are retried only on request, which
    matches Parallax's former ADR 0008. Timeouts are retried only on request.
    Dead connections and in-memory deadlocks are retriable.
  - *Parallax:* optimistic conflicts replay automatically alongside deadlock
    and serialization failures (ADR 0073). Lock-wait timeouts are not retried.
- **Retry timing.**
  - *Reladomo:*
    - A flat uniform wait of one to two seconds, independent of the attempt,
      fixed in code, and started after rollback has closed the connection.
    - A conflict with a known blocker waits on that transaction instead.
    - No rationale for the 2000 ms constant appears in the source.
  - *Parallax:*
    - Exponential full jitter, `uniform(0, min(cap, base × 2^(n−1)))`,
      starting after release and attempt reporting (`m-auto-retry` *Waiting
      between attempts*).
    - The constants, an 8 ms base and a 25 ms cap, were selected from
      contention evidence ([`01-attribution.md`](01-attribution.md#c4-immediate-replay-versus-bounded-randomized-backoff)).
    - Reladomo's minimum wait is forty times that cap.
- **Streaming.**
  - *Reladomo:* the cursor holds one connection for the whole iteration, and
    the driver's default decides buffering.
  - *Parallax:* standalone streams acquire and release a connection per page.
    Transaction streams are scoped to one attempt.
- **Retained state.**
  - *Reladomo:* results are shared cache objects whose data carries the gate
    token, and that data can change under the caller.
  - *Parallax:* standalone and read-only results keep publication identity and
    provenance but no write evidence (`m-read-delivery` *Publication*).

## Not determined

- No Reladomo test was found that exercises the pool's routing of a
  pre-enlistment non-locking read to the autocommit connection. The finding
  follows from `prepareForQuery`, `isWriteOperationMode`, and
  `getConnectionForTransaction`. Test definitions were inspected, not
  executed.
- This pass did not execute whether the MariaDB and Oracle vendor-code
  comparisons with `40001` ever match a real deadlock or serialization
  failure.
- This pass did not trace the release order under a container-managed
  transaction manager.
- This pass did not trace whether rows delivered by a locking cursor are
  marked as participating, or whether they are re-enrolled on first attribute
  access.
