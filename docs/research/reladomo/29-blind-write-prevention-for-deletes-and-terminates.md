# Deletes and terminates carry the same concurrency gate as updates, and dated writes carry a milestone gate in every mode

> Task-directed research against Reladomo at commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer
> to this repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/`; **`templates/`** =
> `reladomogen/src/main/templates/`.

The question this finding answers: does Reladomo's blind-write prevention extend to
deletes and terminates, or only to updates? [09](09-transactions-locking.md) covers
the update path and optimistic retry, [27](27-read-enrollment-and-write-licensing.md)
covers enrollment keys and the dated UPDATE gate, and
[28](28-transaction-participation-mode-scope.md) covers how a mode is selected. None
of them state what a DELETE or a `terminate()` emits.

The short answer is that deletes and terminates are gated, and the gate is not
special-cased for them: the version predicate is spliced into the shared
`getPrimaryKeyWhereSql()` that both UPDATE and DELETE consume, and a dated write's
milestone predicate is appended by a dated-specific override of both where-clause
builders. Terminates are gated more strongly than either, because their milestone
predicate is unconditional rather than mode-dependent. The one real asymmetry is in
the affected-row check afterwards, which is weaker for DELETE than for UPDATE.

## The version predicate lives in the shared primary-key where clause

`MithraAbstractDatabaseObject` builds the update and delete where clauses from the
same generated method:

```java
// mithra/database/MithraAbstractDatabaseObject.java:3447-3478
protected String getSqlWhereClauseForUpdate(MithraDataObject firstDataToUpdate)
{ … sql = " where " + this.getPrimaryKeyWhereSql(); … }

protected String getSqlWhereClauseForDelete(MithraDataObject dataToDelete)
{ … sql = " where " + this.getPrimaryKeyWhereSql(); … }
```

`getPrimaryKeyWhereSql()` is generated per class and is mode-aware. For a class with
an explicit `useForOptimisticLocking` attribute it returns the version-extended
predicate whenever that class's portal is optimistic in the current transaction:

```jsp
<%-- templates/CommonDatabaseObjectAbstract.jspi:259-270 --%>
public String getPrimaryKeyWhereSql()
{
    if (<Finder>.getMithraObjectPortal().getTxParticipationMode().isOptimisticLocking())
    {
        return "<%= wrapper.getPrimaryKeyWithOptimisticLockWhereSql()%>";
    }
    return "<%= wrapper.getPrimaryKeyWhereSql()%>";
}
```

The version fragment is `AND <col> = ?`
(`generator/MithraObjectTypeWrapper.java:2590-2597`), and the matching binder appends
the shadow version after the key columns
(`templates/CommonDatabaseObjectAbstract.jspi:201-217`, binding
`zGetPersistedVersion()`). `zDelete` binds through that same
`setPrimaryKeyAttributes` call (`MithraAbstractDatabaseObject.java:3781`), so the
delete and the update emit and bind identically:

```sql
update OPTIMISTIC_ORDER set STATE = ? where ORDER_ID = ? AND VERSION = ?
delete from OPTIMISTIC_ORDER        where ORDER_ID = ? AND VERSION = ?
```

Nothing in the delete path opts out. The protection is a property of the where-clause
builder, not of the statement kind.

## Dated writes carry an unconditional milestone gate plus an optional processing-date gate

`MithraAbstractDatedTransactionalDatabaseObject` overrides both builders and appends
two fragments:

```java
// mithra/database/MithraAbstractDatedTransactionalDatabaseObject.java:219-238
protected String getSqlWhereClauseForUpdate(MithraDataObject firstDataToUpdate)
{
    String sql = super.getSqlWhereClauseForUpdate(firstDataToUpdate);
    sql += this.getAsOfAttributeWhereSql(firstDataToUpdate);
    sql += this.getOptimisticLockingWhereSqlIfNecessary();
    return sql;
}

protected String getSqlWhereClauseForDelete(MithraDataObject dataToDelete)
{
    String sql = super.getSqlWhereClauseForDelete(dataToDelete);
    sql += " " + this.getAsOfAttributeWhereSql(dataToDelete);
    sql += this.getOptimisticLockingWhereSqlIfNecessary();
    return sql;
}
```

`getAsOfAttributeWhereSql` emits `AND <to-column> = ?` per as-of dimension —
`AND THRU_Z = ? AND OUT_Z = ?` for a bitemporal class
(`generator/MithraObjectTypeWrapper.java:2219-2246`). It is appended
unconditionally, in every participation mode.
`getOptimisticLockingWhereSqlIfNecessary` adds `AND IN_Z = ?` only when the class's
portal is optimistic (`MithraAbstractDatabaseObject.java:4927-4938`;
`MithraObjectTypeWrapper.java:2590-2597` selects `IN_Z` when no explicit version
attribute exists).

The consequence is that a dated write — a milestone close, a chained update, or a
physical row removal — can only land on the exact row the in-memory object was
hydrated from. A row another transaction already chained has a different `OUT_Z` and
matches zero rows.

## Terminate resolves into gated updates, inserts, and deletes

`terminate()` is not a statement kind; it is a director-planned sequence over the
milestone rows overlapping the terminate date. Each director calls `enrollInWrite`
and then emits ordinary buffered operations:

- `GenericBiTemporalDirector.terminate` (`mithra/behavior/GenericBiTemporalDirector.java:687-754`)
  runs `checkInfinityDate` first, then per overlapping in-transaction row either
  `inactivateObject` (UPDATE writing `OUT_Z`), `cutTail` (UPDATE writing `THRU_Z`),
  an insert of a head fragment, or `delete` (`:282`). Its
  `inactivateOnSameDayUpdate` returns `true` (`:1351-1354`), so the physical-delete
  branch is reached only for rows new in this transaction.
- `GenericNonAuditedTemporalDirector.terminate` (`:464-493`) has no processing-date
  axis to chain into, so a row whose business-from is at or after the terminate date
  is physically deleted (`:291`); earlier rows are split.
- `AuditOnlyTemporalDirector.terminate` (`:230-235`) delegates entirely to
  `inactivateForArchiving`, i.e. an UPDATE writing `OUT_Z`.

Every statement produced by those branches goes through the dated where-clause
builders above, so all of them carry the milestone gate.

## Affected-row checking is stricter for UPDATE than for DELETE

This is the one place the two diverge. `checkUpdatedRows` raises in every mode:

```java
// mithra/database/MithraAbstractDatabaseObject.java:3725-3746
if (updatedRows != 1)
{
    if (…getTxParticipationMode(tx).isOptimisticLocking())
    {
        …markDirtyForReload(data, tx);
        if (updatedRows < 1) throwOptimisticLockException(…);
        else throw new ReladomoCorruptMilestoneException(…);
    }
    throw new MithraDatabaseException("in trying to update instance of " + printableKey + ' ' + updatedRows + " were updated!");
}
```

`checkDeletedRows` raises only under optimistic locking:

```java
// mithra/database/MithraAbstractDatabaseObject.java:3801-3817
if (deletedRows != 1 && this.getMithraObjectPortal().getTxParticipationMode(tx).isOptimisticLocking())
{
    …markDirtyForReload(data, tx);
    if (deletedRows < 1) this.throwOptimisticLockException(…);
    else throw new ReladomoCorruptMilestoneException(…);
}
```

Under a locking mode, a DELETE that matched zero rows is accepted silently. The
distinction is consistent with intent rather than with mechanism: a delete that finds
nothing to delete has reached its goal, while an update that finds nothing to update
has not. In practice the locking modes reach the same outcome earlier — see the next
section — so the silent path is only observable when nothing re-read the row.

The batch path repeats the same split. `executeBatchWithObjects` always runs the
optimistic check and skips only the plain count check when `checkCount` is false
(`MithraAbstractDatabaseObject.java:4963-4976`), and `batchDeleteQuietly` is exactly
the `checkCount == false` entry point
(`mithra/database/MithraAbstractTransactionalDatabaseObject.java:52-61`, selected by
`mithra/transaction/BatchDeleteOperation.java:88-103`). A "quiet" batch delete is
quiet about missing rows, never about optimistic failures.

## Under a locking mode the delete is protected before the statement is built

Optimistic mode is the only mode where the where-clause predicate is the sole
defence. Every other mode refreshes with a lock at write enrollment, which is the
step `delete()` and `terminate()` both pass through:

```java
// mithra/behavior/persisted/PersistedTxEnrollBehavior.java:62-78
if (mto.zGetPortal().getTxParticipationMode(threadTx).isOptimisticLocking())
{ … zEnrollInTransactionForWrite(…) … }
else
{ mto.zRefreshWithLockForWrite(this); … }
```

`zRefreshWithLockForWrite` re-reads with `refresh(oldData, true)` and raises
`MithraDeletedException` when the row is gone
(`mithra/superclassimpl/MithraTransactionalObjectImpl.java:1501-1515`). The dated
analogue is `AbstractDatedTransactionalCache.enrollDatedObject` (`:607-695`), which
in non-optimistic mode calls the persister's `enrollDatedObject` →
`portal.refreshDatedObject(obj, mustLockOnRead())`
(`mithra/database/MithraAbstractDatedTransactionalDatabaseObject.java:110-115`) and
raises `MithraDeletedException("… has been terminated.")` on a null result.
`PersistedSameTxBehavior.delete` (`:67-74`) only buffers the operation; the
protection already happened at enrollment.

## Three paths are blind by construction

- **`deleteAll()` on an operation-based list.** `DeleteAllTransactionalCommand:36-43`
  calls `tx.deleteUsingOperation(op)`, which emits one `DELETE … WHERE <operation>`
  with no version or milestone predicate and no affected-row check
  (`MithraAbstractDatabaseObject.java:5060-5119`).
  `MithraTransactionalPortal.prepareForMassDelete:136-156` only evicts cache and
  in-memory state. `verifyNonDatedList`
  (`mithra/list/AbstractTransactionalOperationBasedList.java:208-214`) refuses the
  call on dated classes.
- **`purgeAll()`** takes the same shape through `purgeUsingOperation`
  (`mithra/list/PurgeAllTransactionalCommand.java:37-44`).
- **`purge()` on a single dated object** emits `delete from T where <PK>` bound with
  `setPrimaryKeyAttributesWithoutDates`
  (`mithra/database/MithraAbstractDatedTransactionalDatabaseObject.java:320-357`) —
  no as-of columns at all, so it removes every milestone row for the key, and it
  checks nothing.

`terminateAll()` is not in this list: it resolves the list and calls `terminate()`
per object (`mithra/list/TerminateAllTransactionalCommand.java:37-45`), so it keeps
the full gate.

## Related observations

- **An UPDATE sets only the attributes whose setters were called.** The SET clause is
  built from the buffered `AttributeUpdateWrapper` list
  (`MithraAbstractDatabaseObject.java:3645-3661`), so a concurrent write to a
  different column is never overwritten regardless of locking. What the concurrency
  machinery protects is the read that fed the decision, not untouched columns.
- **Optimistic retry is opt-in.** `MithraRootTransaction.retryOnOptimisticLockFailure`
  defaults to `false` (`mithra/transaction/MithraRootTransaction.java:69`, `:84-91`);
  the exception is marked retriable only when the application called
  `setRetryOnOptimisticLockFailure(true)`
  (`MithraAbstractDatabaseObject.java:4978-4986`). Otherwise
  `MithraManager.executeTransactionalCommand`'s retry loop propagates it.
- **More than one affected row is a distinct failure.** Both checks raise
  `ReladomoCorruptMilestoneException` when the gate matched several rows — a gate that
  is supposed to identify one physical row matching many means the milestone table is
  corrupt.
- **A `Dangerous` mode setter exists for business-date-only classes.** The generated
  Finder offers `setTransactionModeReadCacheWithOptimisticLocking` when the class has
  a gate, `setTransactionModeReadCacheUpdateCausesRefreshAndLock` for a non-dated
  ungated class, and `setTransactionModeDangerousNoLocking` for a dated class with
  neither a processing date nor a version attribute
  (`templates/readonly/Finder.jsp:1470-1491`). That third case is the only
  transactional shape where dropping read locks leaves a write with just its
  business-date milestone gate.
- **The detached-merge path checks the version in memory first.**
  `zCopyAttributesFromImpl` compares versions and raises a non-retriable
  `MithraOptimisticLockException` before issuing any statement, but only when retry is
  off (`mithra/superclassimpl/MithraTransactionalObjectImpl.java:1411-1427`).
- **`ReadCacheUpdateNotAllowedTxParticipationMode` is not a user-selectable
  transactional mode**; it is what `MithraReadOnlyPortal` returns (`:45-51`).

## Testing patterns

`TestOptimisticTransactionParticipation` covers the delete and terminate cases
directly, in the H2-backed no-mock style of [12](12-test-infrastructure.md):
`testOptimisticDelete` (`:550`), `testOptimisticBatchDelete` (`:758`),
`testAuditOnlyOptimisticTerminate` (`:96`), and the two-thread races
`testNonDatedOptimisticLockFailureForDelete` (`:584`),
`testNonDatedOptimisticLockFailureForDeleteAfterUpdate` (`:642`), and
`testNonDatedOptimisticLockFailureForBatchDeleteAfterUpdate` (`:700`). The race tests
delete the row from a second thread through raw JDBC, assert the first thread's
`delete()` fails, and assert the retried transaction observes the row as already
absent.

## Not determined

- No test was found asserting the silent-zero-row DELETE under a locking mode; that
  behavior is read from `checkDeletedRows` and the absence of any other caller-side
  check.
- The interaction of `hasNullablePrimaryKeys()` with optimistic locking was not
  traced. `getSqlWhereClauseForDelete` switches to
  `getPrimaryKeyWhereSqlWithNullableAttribute`, which the template emits without the
  version fragment, while `setPrimaryKeyAttributes` still binds it; whether any
  validation forbids that combination was not established.
- The remote and `Pure` persister variants of the delete and terminate paths were not
  traced; every conclusion here is for the JDBC-backed path.

## Code references

- `mithra/database/MithraAbstractDatabaseObject.java:3447-3478` — shared update/delete
  where-clause builders
- `mithra/database/MithraAbstractDatabaseObject.java:3645-3661`, `:3725-3746` — update
  SET construction; `checkUpdatedRows`
- `mithra/database/MithraAbstractDatabaseObject.java:3758-3799`, `:3801-3817` —
  `zDelete`; `checkDeletedRows`
- `mithra/database/MithraAbstractDatabaseObject.java:4849-4925`, `:4927-4938`,
  `:4963-4976`, `:4978-4986`, `:5019-5052`, `:5060-5119` — batch delete; optimistic
  fragment; batch checks; retriability; mass delete
- `mithra/database/MithraAbstractDatedTransactionalDatabaseObject.java:110-115`,
  `:219-238`, `:320-357` — dated enrollment; dated where clauses; purge
- `mithra/database/MithraAbstractTransactionalDatabaseObject.java:52-61` —
  `batchDelete` versus `batchDeleteQuietly`
- `mithra/behavior/GenericBiTemporalDirector.java:282`, `:687-754`, `:758`,
  `:1351-1354` — delete helper; terminate; purge; same-day rule
- `mithra/behavior/GenericNonAuditedTemporalDirector.java:291`, `:464-493` —
  business-date-only terminate
- `mithra/behavior/AuditOnlyTemporalDirector.java:205`, `:230-235` — audit-only
  terminate
- `mithra/behavior/persisted/PersistedTxEnrollBehavior.java:62-78`,
  `mithra/behavior/persisted/PersistedSameTxBehavior.java:67-74` — write enrollment;
  buffered delete
- `mithra/behavior/persisted/DatedPersistedTxEnrollBehavior.java:41-66`,
  `mithra/cache/AbstractDatedTransactionalCache.java:607-695` — dated enrollment for
  read, write, and delete
- `mithra/superclassimpl/MithraTransactionalObjectImpl.java:1411-1427`, `:1501-1515` —
  detached version check; refresh-with-lock-for-write
- `mithra/transaction/MithraRootTransaction.java:69`, `:84-91` — retry default
- `mithra/transaction/BatchDeleteOperation.java:33`, `:42`, `:50-57`, `:88-103` —
  quiet batch delete selection
- `mithra/list/AbstractTransactionalOperationBasedList.java:208-214`, `:267-289`,
  `:356-377`, `mithra/list/DeleteAllTransactionalCommand.java:36-43`,
  `mithra/list/TerminateAllTransactionalCommand.java:37-45`,
  `mithra/list/PurgeAllTransactionalCommand.java:37-44` — bulk entry points
- `mithra/portal/MithraTransactionalPortal.java:136-156`,
  `mithra/portal/MithraReadOnlyPortal.java:45-51` — mass-delete preparation; read-only
  mode
- `generator/MithraObjectTypeWrapper.java:2219-2246`, `:2590-2597` — as-of fragment;
  optimistic fragment
- `templates/CommonDatabaseObjectAbstract.jspi:201-217`, `:259-270` — parameter
  binding; mode-aware primary-key where clause
- `templates/readonly/Finder.jsp:1470-1491` — generated participation-mode setters
- `reladomo/src/test/java/com/gs/fw/common/mithra/test/TestOptimisticTransactionParticipation.java:96`,
  `:550`, `:584`, `:642`, `:700`, `:758` — delete and terminate coverage
