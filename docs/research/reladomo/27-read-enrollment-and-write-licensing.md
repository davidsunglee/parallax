# Read enrollment and write licensing: transaction read state is keyed by object identity *plus* temporal coordinate, and every dated UPDATE is unconditionally gated on the milestone's own end columns

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/`.

The question this finding answers: when one transaction reads the same logical row at two different
temporal coordinates — once current, once pinned at a finite past processing date — and then writes
the current row, what state does Reladomo carry between the reads and the write, and how is that
state keyed? [06](06-bitemporal-milestoning.md) covers milestone chaining and
[09](09-transactions-locking.md) covers optimistic retry; neither covers the read-enrollment
structures or their key construction, which is what this file adds.

The short answer is that Reladomo has no primary-key-keyed scalar "this row was read as of X" slot at
all. Read state hangs off individual object instances, and those instances are keyed by primary key
combined with every as-of date, so two coordinates produce two objects with independent state.
Separately, write eligibility is not derived from transaction history: it is re-checked against the
object being written, and the emitted UPDATE is gated on that object's own milestone-end columns in
every locking mode.

## Three layers of transaction read state, none keyed by primary key alone

**On the object instance.** Every dated business object carries a `DatedTransactionalState` field,
CAS-updated (`mithra/superclassimpl/MithraDatedTransactionalObjectImpl.java:51-52`), installed for
reads by `zEnrollInTransactionForRead` (`:253-261`). The state records the coordinate it was enrolled
at:

```java
// mithra/DatedTransactionalState.java:33-35
private Timestamp businessDate;
private boolean isCurrent;
```

**Per transaction × portal, keyed by the physical milestone row.** `PerPortalTemporalContainer` —
held in `MithraLocalTransaction.perPortalTemporalContainerMap`
(`mithra/transaction/MithraLocalTransaction.java:74`) — holds

```java
// mithra/transaction/PerPortalTemporalContainer.java:36
private UnifiedMap<MithraDataObject, InternalList> readEnrolled;
```

The key is the committed `MithraDataObject` — one specific milestone row — mapping to the business
objects that read it (`:73-87`). Generated `…Data` classes override neither `equals` nor `hashCode`,
so this is an identity map over milestone-row instances.

The registration is also filtered to current milestones only:

```java
// mithra/transaction/PerPortalTemporalContainer.java:75-77
if (processingAsOfAttribute == null ||
    processingAsOfAttribute.getToAttribute().timestampValueOfAsLong(committedData)
        == processingAsOfAttribute.getInfinityDate().getTime())
```

A read of a historical row (`OUT_Z != ∞`) is never entered. `enrollInWrite(committedData, container)`
(`:89-100`) subsequently upgrades exactly the read-enrolled objects registered for that same row. No
comment in the source states why the filter is there.

**Per transaction, keyed by non-dated primary key.** `AbstractDatedTransactionalCache` keeps one
`TemporalContainer` per (transaction, PK):

```java
// mithra/cache/AbstractDatedTransactionalCache.java:812-832
new FullUniqueIndex("containerIndex", getNonDatedPkAttributes())
```

This is the only structure keyed by primary key alone, and it is a *container of many milestone rows*
rather than a scalar observation. Every access re-qualifies by temporal coordinate —
`BiTemporalTransactionalDataContainer.getCommitedDataFor` / `getTxDataFor`
(`mithra/behavior/BiTemporalTransactionalDataContainer.java:66-97`) both read `businessDate` and
`processingDate` off the business object being asked about.

## The identity map folds every as-of date into the key

Two views of one logical row at different coordinates are two distinct Java objects. Each dated object
carries its own as-of timestamps as instance fields
(`generator/templates/datedtransactional/Abstract.jsp:80`, `protected transient Timestamp
<asOfAttrName>;`, assigned in the constructor at `:120-137`).

`ConcurrentDatedObjectIndex` keys on the non-dated PK hash combined with every as-of date:

```java
// mithra/cache/ConcurrentDatedObjectIndex.java:245-254
protected int computeHashCodeFromData(int nonDatedPkHashCode, Timestamp[] asOfDates) {
    int hashCode = nonDatedPkHashCode;
    for (int i = 0; i < asOfDates.length; i++)
        hashCode = HashUtil.combineHashes(hashCode, asOfDates[i].hashCode());
    return hashCode;
}
```

Equality is `((MithraDatedObject) candidate).zDataMatches(data, asOfDates)` (`:331`), generated as
primary-key equality **and** `this.<asOfAttr>.equals(asOfDates[i])` per dimension
(`generator/templates/datedtransactional/Abstract.jsp:2109-2118`); `candidateMatches` (`:279-292`)
applies the same rule, and a miss constructs a new object via `factory.createObject(data, asOfDates)`
(`:342`). So `(id=1, processingDate=∞)` and `(id=1, processingDate=T)` coexist as separate entries,
each with its own `DatedTransactionalState`.

## Writing a historical milestone is refused against the object's own coordinate

`GenericBiTemporalDirector.checkInfinityDate` runs first in every mutating path — `update` (`:408`),
`insert` (`:73`, `:113`, `:186`), `terminate` (`:689`), `updateUntil` (`:1014`), `inactivate`
(`:508`, `:558`):

```java
// mithra/behavior/GenericBiTemporalDirector.java:1305-1313
protected void checkInfinityDate(MithraDatedTransactionalObject mithraObject) {
    long processingDate = processingDateAttribute.timestampValueOfAsLong(mithraObject);
    if (processingDate != processingDateAttribute.getInfinityDate().getTime())
        throw new MithraTransactionException("processing date must be infinity when creating/modifying an object");
    this.checkNotInfinityBusinessDate(mithraObject);
}
```

`AuditOnlyTemporalDirector` carries the same check. The value is read by
`timestampValueOfAsLong(mithraObject)` — off the object's own transient `processingDate` field, not
from any map. The call path is setter → `DatedPersistedSameTxBehavior.update`
(`mithra/behavior/persisted/DatedPersistedSameTxBehavior.java:83-93`) → `issueUpdate` →
`obj.zGetTemporalDirector().update(...)` (`:113-118`).

Business date is symmetric but inverted: `checkNotInfinityBusinessDate` (`:1315-1322`) *rejects* a
business date of infinity. Writing at a past **business** date is legal — that is what milestoning is
for; writing at a past **processing** date is not.

Secondary guards on already-closed rows: `AbstractTemporalContainerWithBusinessDate.checkInactivated`
throws `MithraDeletedException("Cannot access deleted object …")` (`:63-75`), and
`DatedTransactionalState.getTxData` throws `MithraDeletedException("cannot access deleted/terminated
object. Check for call to terminate multiple times or check for bad chaining")`
(`mithra/DatedTransactionalState.java:98-105`).

## Every dated UPDATE is gated on the milestone's end columns, in both locking modes

This is the structural point. `getSqlWhereClauseForUpdate` composes the primary-key predicate, the
as-of fragment, and an optional optimistic clause
(`mithra/database/MithraAbstractDatedTransactionalDatabaseObject.java:219-238`), where the as-of
fragment is `AND THRU_Z = ? AND OUT_Z = ?` bound from the data object
(`generator/MithraObjectTypeWrapper.java:2219-2246`; binder at
`generator/templates/CommonDatabaseObjectAbstract.jspi:246-260`). **Reladomo has no ungated milestone
close.** Pessimistic mode does not remove the gate; optimistic mode only *adds* one.

The optimistic gate has two variants, one mechanism. A non-dated object with
`useForOptimisticLocking="true"` uses a version column
(`generator/MithraObjectTypeWrapper.java:865-873`, `:993-996`, appended as `AND <col> = ?` at
`:2590-2596`). Any object with a processing date uses `IN_Z`:

```java
// reladomo/src/main/java/com/gs/reladomo/metadata/ReladomoClassMetaData.java:125-133
public Attribute getOptimisticKeyFromAsOfAttributes() {
    AsOfAttribute processingDateAttribute = this.getProcessingDateAttribute();
    if (processingDateAttribute != null) return processingDateAttribute.getFromAttribute();
    return null;
}
```

`hasOptimisticLocking() = isTransactional() && (hasProcessingDate() || hasOptimisticLockAttribute())`
(`generator/MithraObjectTypeWrapper.java:3611-3614`), consumed at
`mithra/portal/MithraAbstractObjectPortal.java:1669-1683` and
`mithra/transaction/BatchUpdateOperation.java:200-204`.

The bind value comes off the data object rather than off recorded transaction state:

```jsp
// generator/templates/CommonDatabaseObjectAbstract.jspi:204-218
if (…getTxParticipationMode().isOptimisticLocking()) {
    <optimisticLockAttribute>.getSqlSetParameters("zGetPersistedVersion()")   // version case
    <processingDate>.getSqlSetParameters("getProcessingDateFrom()")           // dated case
}
```

`dataObj` here is `mithraObject.zGetCurrentData()`
(`mithra/database/MithraAbstractDatedTransactionalDatabaseObject.java:227-243`). A zero-row outcome
marks the object dirty and throws `MithraOptimisticLockException`
(`mithra/database/MithraAbstractDatabaseObject.java:3726-3746`, `:4978-4986`).

## Pessimistic locking has no read-licenses-write predicate

There is no license check. Under `FullTransactionalParticipationMode`, read enrollment goes
`DatedPersistedTxEnrollBehavior.enrollInTransaction`
(`mithra/behavior/persisted/DatedPersistedTxEnrollBehavior.java:41-47`) →
`cache.enrollDatedObject(obj, prevState, forWrite=false)`
(`mithra/cache/AbstractDatedTransactionalCache.java:607-695`) → persister `enrollDatedObject` →
`portal.refreshDatedObject(obj, mustLockOnRead())`
(`mithra/database/MithraAbstractDatedTransactionalDatabaseObject.java:110-115`). The locking SELECT is
scoped by the object's own coordinates:

```java
// mithra/database/MithraAbstractDatedDatabaseObject.java:288-297
int count0 = asOfAttributes[0].appendWhereClauseForValue(
                 asOfAttributes[0].timestampValueOf(mithraObject), whereClause);
…
int count1 = asOfAttributes[1].appendWhereClauseForValue(
                 asOfAttributes[1].timestampValueOf(mithraObject), whereClause);
```

A historical read locks the historical row; a current read locks the current row; they are separate
locks on separate objects. A transaction that reads a historical milestone and then writes the current
row never write-enrolls the historical object — `readEnrolled` never contained it
(`PerPortalTemporalContainer.java:75-77`) — and the write proceeds through the current object, whose
own `processingDate == ∞` passes `checkInfinityDate` and whose UPDATE is gated on `THRU_Z`/`OUT_Z`
from its own data. Calling a setter on the *historical* object instead throws `"processing date must
be infinity when creating/modifying an object"`.

## Key construction, collected

| Structure | Key | Citation |
|---|---|---|
| Identity map | non-dated PK hash ⊕ hash of every as-of date; equality is PK-equal **and** per-dimension as-of equal | `mithra/cache/ConcurrentDatedObjectIndex.java:245-254`, `:279-292`, `:305-353`; `generator/templates/datedtransactional/Abstract.jsp:2109-2118` |
| Read enrollment | the committed milestone `MithraDataObject` instance (identity), recorded only when `OUT_Z == ∞` | `mithra/transaction/PerPortalTemporalContainer.java:36`, `:73-87` |
| Per-transaction container | non-dated PK — but holds a *collection* of milestone rows, re-qualified by coordinate on every access | `mithra/cache/AbstractDatedTransactionalCache.java:812-832`; `mithra/behavior/BiTemporalTransactionalDataContainer.java:66-97` |

## Structural contrast with a primary-key-keyed observation map

Recorded factually, without recommendation, because this finding was gathered against a Parallax
design question about a transaction-scoped observation map keyed by `(entity, primary key)` with
last-write-wins recording.

Reladomo's shape has no place to lose an earlier read, for four independent reasons:

1. **No PK-keyed scalar slot exists.** The nearest analogue, `readEnrolled`, is keyed by milestone-row
   instance, so a current read and a historical read of the same logical row write to different
   entries.
2. **The two reads produce two objects with separate state.** The identity map folds all as-of dates
   into the key, so neither read can touch the other's `DatedTransactionalState`.
3. **Write eligibility is derived from the object being written, at write time.** `checkInfinityDate`
   re-reads `processingDate` off that object; nothing consults transaction-level history, so a second
   read is simply not in scope when the first object is written.
4. **The close is never ungated.** The row-identity gate `AND THRU_Z = ? AND OUT_Z = ?` is
   unconditional across locking modes, so a lock is an additional layer rather than the sole
   protection. A "was this read current?" precondition has no work to do.

Stated as one contrast: a PK-keyed observation map makes write eligibility a *transaction-scoped*
precondition consulted at write time; Reladomo makes it an *object-scoped* invariant checked on the
object being written, backed by an unconditionally gated UPDATE.

## Testing patterns

Reladomo's temporal transaction tests are H2-backed integration tests in the house style described in
[12](12-test-infrastructure.md) — no mocks, real SQL, per-test transaction scopes.

## Not determined

- No Reladomo test was found exercising the exact sequence "read current, then read the same PK at a
  past processing date, then write the current object, in one transaction." The behavior described
  above is derived from the code paths cited, not from an observed test run.
- The remote (`mithra/remote/RemoteMithraObjectPersister.java:704-720`) and `Pure` in-memory persister
  variants of `enrollDatedObject` were not traced; every conclusion here is for the JDBC-backed path.
- The source carries no stated rationale for restricting write enrollment to `OUT_Z == ∞` rows in
  `addToReadEnrolled`.

## Code references

- `mithra/superclassimpl/MithraDatedTransactionalObjectImpl.java:51-52`, `:253-261` — the
  `DatedTransactionalState` field and read enrollment
- `mithra/DatedTransactionalState.java:33-35`, `:98-105` — enrolled coordinate; deleted-object refusal
- `mithra/transaction/PerPortalTemporalContainer.java:36`, `:73-87`, `:89-100` — `readEnrolled`, the
  current-only filter, write upgrade
- `mithra/transaction/MithraLocalTransaction.java:74` — the per-portal container map
- `mithra/cache/AbstractDatedTransactionalCache.java:607-695`, `:812-832` — enrollment; the
  PK-keyed container index
- `mithra/cache/ConcurrentDatedObjectIndex.java:245-254`, `:279-292`, `:305-353` — coordinate-folded
  key construction
- `mithra/behavior/BiTemporalTransactionalDataContainer.java:66-97` — coordinate re-qualification
- `mithra/behavior/GenericBiTemporalDirector.java:73`, `:113`, `:186`, `:408`, `:508`, `:558`, `:689`,
  `:1014`, `:1305-1313`, `:1315-1322` — mutating paths and the infinity checks
- `mithra/behavior/persisted/DatedPersistedSameTxBehavior.java:83-93`, `:113-118` — setter to director
- `mithra/behavior/persisted/DatedPersistedTxEnrollBehavior.java:41-47` — read enrollment entry
- `mithra/behavior/AbstractTemporalContainerWithBusinessDate.java:63-75` — inactivated-row refusal
- `mithra/database/MithraAbstractDatedTransactionalDatabaseObject.java:110-115`, `:219-238`,
  `:227-243` — refresh-with-lock; the update where clause; the bound data object
- `mithra/database/MithraAbstractDatedDatabaseObject.java:288-297` — coordinate-scoped locking SELECT
- `mithra/database/MithraAbstractDatabaseObject.java:3726-3746`, `:4978-4986` — zero-row optimistic
  failure
- `mithra/portal/MithraAbstractObjectPortal.java:1669-1683`,
  `mithra/transaction/BatchUpdateOperation.java:200-204` — optimistic-locking consumers
- `reladomo/src/main/java/com/gs/reladomo/metadata/ReladomoClassMetaData.java:125-133` — `IN_Z` as the
  dated optimistic key
- `generator/MithraObjectTypeWrapper.java:865-873`, `:993-996`, `:2219-2246`, `:2590-2596`,
  `:3611-3614` — version column, as-of where fragment, optimistic clause, capability predicate
- `generator/templates/CommonDatabaseObjectAbstract.jspi:204-218`, `:246-260` — optimistic bind
  sources; as-of binder
- `generator/templates/datedtransactional/Abstract.jsp:80`, `:120-137`, `:2109-2118` — as-of instance
  fields and `zDataMatches`
