# Bitemporal milestoning: `AsOfAttribute` models `[from,to)` intervals; `TemporalDirector` chains milestone rows on every write

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`generator/`** =
> `reladomogen/src/main/java/com/gs/fw/common/mithra/generator/`.

This is Reladomo's signature feature. An `AsOfAttribute` (`mithra/attribute/AsOfAttribute.java:59-665`)
is a query-time virtual attribute backed by a **pair** of timestamp columns — a `fromAttribute` and a
`toAttribute`. A row is "current" when its `to` equals the **infinity** sentinel (e.g.
`9999-12-01 23:59:00.0`). Two as-of dimensions are typical: business date (`FROM_Z/THRU_Z` — when the
fact is true in the world) and processing date (`IN_Z/OUT_Z`, `isProcessingDate="true"` — when the
system knew it).

The interval is `[from, to)` when `toIsInclusive=false` (the default). The SQL predicate
(`finder/asofop/AsOfEqOperation.java:215-252`):

```text
asOfDate == infinity              →  toColumn = ?                       (1 bind, matches current rows)
asOfDate <  infinity, exclusive   →  fromColumn <= ?  AND toColumn > ?  (2 binds)
asOfDate <  infinity, inclusive   →  fromColumn <  ?  AND toColumn >= ? (2 binds)
```

**Edge-point** queries (`equalsEdgePoint()`, lines 189-197) select rows by the stored boundary itself
rather than containment — used to fetch full history.

**Defaulting**: `AsOfEqualityChecker` (`mithra/finder/AsOfEqualityChecker.java`) walks the operation
tree, finds all as-of attributes, and `lookForMissingDefaults()` (lines 158-179) synthesizes an
`AsOfEqOperation` from `getDefaultDate()` for any dimension the caller omitted — so leaving out
`processingDate` automatically adds `processingDate = infinity` ("as of now").

Dated objects carry extra runtime state: a `DatedTransactionalState`
(`mithra/DatedTransactionalState.java:27-335`) with a `TemporalContainer` that holds all in-transaction
date segments for a primary key, enabling multi-slice chaining. The mutation contract on
`MithraDatedTransactionalObject` adds `insertUntil`, `insertWithIncrement`, `terminate`,
`terminateUntil`, `purge`, `inactivateForArchiving`.

**Write-time chaining** is performed by a `TemporalDirector` (`mithra/behavior/TemporalDirector.java`),
with three implementations: `GenericBiTemporalDirector` (both axes), `AuditOnlyTemporalDirector`
(processing only), `GenericNonAuditedTemporalDirector` (business only). The core is
`GenericBiTemporalDirector` (`mithra/behavior/GenericBiTemporalDirector.java`):

- **Insert** (71-103): set `IN_Z=txTime`, `OUT_Z=∞`, `THRU_Z=∞`; insert one row.
- **`inactivateObject`** (301-345): close an existing predecessor by setting `OUT_Z=txTime`. Its predicate uses the primary key and as-of **end** columns, plus processing-start `IN_Z` under optimistic participation; it does not add `FROM_Z`. [Dated gate construction](29-blind-write-prevention-for-deletes-and-terminates.md#dated-writes-carry-an-unconditional-milestone-gate-plus-an-optional-processing-date-gate) owns the details.
- **Update** (405-503): resolve rows overlapping `[fromDate, ∞)`, close affected predecessors, preserve an earlier fragment where necessary, and insert changed successor state. `cutTail` handles the segment crossing `fromDate`.
- **`updateUntil`** (1011-1127) + **`splitTailEnd`** (1129-1137): resolve rows overlapping `[fromDate, endDate)`, preserve fragments outside the window, and insert changed state inside it. The single-predecessor case is the bitemporal **rectangle split** into head, middle, and tail; the same operation can cross several predecessors.
- **Terminate** (687-756): resolve rows overlapping `[fromDate, ∞)`, close or remove affected rows, and preserve an earlier fragment where necessary. A surviving fragment can require an insert; termination removes current-processing state inside the affected range, not all history for the key.

```text
BEFORE:  business [FROM_Z ─────────────── THRU_Z=∞)   proc [IN_Z ───────────── OUT_Z=∞)
UPDATE at businessDate=BD:
  old row closed   :  business [FROM_Z ─────────── ∞)   proc [old_IN_Z ── OUT_Z=txNow)
  new head row     :  business [BD ──────────────── ∞)   proc [txNow ──────── OUT_Z=∞)
  new left residual:  business [FROM_Z ─── BD)           proc [txNow ──────── OUT_Z=∞)
```

## Writes resolve complete affected business ranges

The object's business-date coordinate selects its starting view; it does not limit a mutation to
that view's one physical row. `GenericBiTemporalDirector` asks the transaction's temporal container
for every row overlapping the mutation's range:

| Mutation | Business-time range |
| --- | --- |
| ordinary update | `[businessDate, infinity)` |
| `updateUntil` | `[businessDate, until)` |
| ordinary terminate | `[businessDate, infinity)` |

The calls and predecessor handling are visible in
[update](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L405-L503),
[bounded update](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L1011-L1137),
and [terminate](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L687-L754).

`AbstractTemporalContainerWithBusinessDate.getObjectsForRange` checks its loaded-range knowledge.
If that knowledge is insufficient, `getForDateRange` supplies additional persisted rows before the
container selects and write-enrolls the overlapping in-transaction rows. The database query uses the
logical key, business-interval overlap, and current processing-end. Cached state and resolving reads
therefore supply predecessor payloads and boundaries for all affected segments; one caller token is
not their substitute.
[Container resolution](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/AbstractTemporalContainerWithBusinessDate.java#L221-L344),
[range query](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/database/MithraAbstractDatedTransactionalDatabaseObject.java#L117-L201).

Optimistic participation supports this multi-interval scope. Test definitions cover
[updating two segments](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestDatedBitemporalOptimisticLocking.java#L837-L885),
[a bounded update crossing segments while preserving residuals](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestDatedBitemporalOptimisticLocking.java#L2180-L2247),
and [terminating multiple segments while retaining processing history](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestDatedBitemporalOptimisticLocking.java#L1031-L1107).
These definitions were inspected, not executed, in the range-concurrency research pass.
[Bitemporal concurrency scope](09-transactions-locking.md#bitemporal-concurrency-scope) distinguishes
this mutation scope from physical-row gates, read locks, and isolation guarantees.

## Rows created by the current transaction remain its own after flushing

Physical flushing does not turn a transaction's new row into a predecessor requiring another
processing-time revision. `InsertOperation` marks the object inserted after executing SQL;
`InTransactionDatedTransactionalObject.isNewInThisTransaction()` includes that `INSERTED_STATE`,
and subsequent updates preserve it. Its `needsTransactionalUpdate()` distinguishes an inserted
row needing real UPDATE SQL from an insertion whose buffered values can still change
([insert completion](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/transaction/InsertOperation.java#L34-L38),
[own-transaction classification](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/transaction/InTransactionDatedTransactionalObject.java#L168-L170),
[state transitions](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/transaction/InTransactionDatedTransactionalObject.java#L362-L380),
[update eligibility](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/transaction/InTransactionDatedTransactionalObject.java#L455-L457)).

For an ordinary update whose business start matches an own-transaction row with an open business
end, `GenericBiTemporalDirector.update` changes its values in place; after an INSERT flush it
buffers an UPDATE instead of closing and reopening processing time. When interval geometry changes,
the director can cut the business end, insert successors, or delete/reinsert its own rows.
`inactivateObject` deletes an own-transaction row rather than giving it a processing end equal to
its processing start. These paths revise uncommitted state without making each physical flush a
separate processing-time revision
([ordinary update branch](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L442-L456),
[own-row inactivation](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L301-L307)).
A test performs bounded changes, flushes, then changes the same interval again before committing
([test definition](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestDatedBitemporalOptimisticLocking.java#L2407-L2465)).
The test was inspected, not executed; the ordinary-update SQL distinction above is source-derived.

## Generated DDL keys on the `to` columns, and author-declared indices may not name as-of columns

The generated physical primary key of a dated object is **declared PK columns ++ each as-of
attribute's `to` column**, never its `from` column. `getWithAsOfAttributes`
(`generator/MithraObjectTypeWrapper.java:1163-1207`) appends one synthetic bare `Attribute` per
dimension carrying only `getToColumnName()`; `getFromColumnName()` is never consulted when building
an index. The routine dedups (`:1177-1191`), so the double call at `:1151` is harmless, and ordering
is fixed by `Index.getIndexColumns()` (`generator/Index.java:100-112`). For `TinyBalance`
(`reladomo/src/test/reladomo-xml/TinyBalance.xml:28-36`) this yields:

```sql
alter table TINY_BALANCE add constraint TINY_BALANCE_PK primary key (BALANCE_ID, THRU_Z, OUT_Z);
```

The same convention drives schema validation: `DatabaseIndexValidator`
(`reladomogenutil/…/objectxmlgenerator/DatabaseIndexValidator.java:212-231`) builds the expected key
as declared PK columns ∪ as-of `to` columns and accepts a match when the live database's primary key
or any unique index is a superset (`:156-165,180-198`).

No comment or javadoc states why `to` rather than `from`, but the rationale is derivable and
operational: the `to` columns are exactly what a mutation's WHERE clause pins.
`MithraAbstractDatedTransactionalDatabaseObject.java:219-238` composes
`getSqlWhereClauseForUpdate`/`ForDelete` as the PK `where` plus the as-of fragment plus the
optimistic lock, and the as-of fragment is generated from the **to** columns alone
(`generator/MithraObjectTypeWrapper.java:2219-2246`, rendered by
`generator/templates/CommonDatedDatabaseObjectAbstract.jspi:24-25`); there is even a helper named
`getPrimaryKeyWithAsOfToAttributeWhereSql()` (`:2204-2217`). An affected current-processing row can
have a finite business-time end; each mutation binds that row's own end values. Keying the physical
primary key on the same columns makes each UPDATE and DELETE a key hit. One consequence: with
`infinityIsNull="true"` the
`to` column is generated **nullable** (`:946-966`, specifically `:952`) — a nullable column inside
the physical primary key — and the WHERE switches to `IS NULL` (`:2229-2237`).

Because the generator appends those columns unconditionally, an author-declared `<Index>` naming an
as-of column is rejected at build time (`generator/MithraObjectTypeWrapper.java:1894-1924`, the check
at `:1911`):

```java
else if (attribute.isAsOfAttribute() || attribute.isAsOfAttributeFrom() || attribute.isAsOfAttributeTo())
{
    errorMessages.add("Index '" + indexType.getName() + "' is invalid. AsOfAttributes or part of "
        + "AsOfAttributes are not allowed in an Index for dated objects: " + attributeNames[j]);
}
```

All three spellings are rejected because `addAsOfAttribute` registers three entries per dimension
(`:939-966`): the virtual as-of attribute and its derived `…From` / `…To` scalars. The check fires
through `BaseMithraGenerator.validateMithraObjectXml()` → `checkRelationships()`
(`generator/BaseMithraGenerator.java:368,532-538`). `BitemporalOrder.xml:27-39,103-105` is the
canonical illustration: the author writes `<Index name="byTrackingId" unique="true">trackingId</Index>`
with no as-of column, and the generated DDL is a unique index on `(TRACKING_ID, THRU_Z, OUT_Z)`.

The physical key is deliberately not the cache key. The runtime's dated key is
`nonDatedPk ++ fromAttributes` (`mithra/cache/FullSemiUniqueDatedIndex.java:221-239`;
`mithra/cache/AbstractDatedCache.java:143-148`), so the DDL and the cache use *different* temporal
columns for the same object.

## Testing patterns

`TestDatedBitemporal.java` (5600+ lines, 100+ methods) is the canonical suite, with SQL-level
assertions via `TestDatedBitemporalDatabaseChecker` (`checkDatedBitemporalInfinityRow`,
`checkDatedBitemporalTerminated`, etc.). Companions: `TestDatedAuditOnly`, `TestDatedNonAudited`,
`TestDatedBitemporalOptimisticLocking`, `TestDatedDetached`, `FullDatedTransactionalCacheTest`.

## Code references

- `mithra/attribute/AsOfAttribute.java` (59-665)
- `mithra/MithraDatedObject.java`, `MithraDatedTransactionalObject.java`, `DatedTransactionalState.java`, `MithraDatedObjectFactory.java`
- `mithra/finder/asofop/AsOfEqOperation.java`, `AsOfEdgePointOperation.java`; `mithra/finder/AsOfEqualityChecker.java`
- `mithra/behavior/TemporalDirector.java`, `GenericBiTemporalDirector.java` (insert 71, inactivateObject 301, update 405, terminate 687, updateUntil 1011, splitTailEnd 1129), `AuditOnlyTemporalDirector.java`, `GenericNonAuditedTemporalDirector.java`
- `mithra/transaction/InTransactionDatedTransactionalObject.java`; `mithra/database/MithraAbstractDatedTransactionalDatabaseObject.java` (219-238)
- `generator/MithraObjectTypeWrapper.java` (addAsOfAttribute 939-966, getPrefixFreeIndices 1121-1161, getWithAsOfAttributes 1163-1207, checkAttributeNamesInIndices 1894-1924, getPrimaryKeyWithAsOfToAttributeWhereSql 2204-2217, getAsOfAttributeWhereSql 2219-2246); `generator/Index.java` (100-112); `generator/BaseMithraGenerator.java` (368, 532-538); `generator/templates/CommonDatedDatabaseObjectAbstract.jspi` (24-25)
- `reladomogenutil/src/main/java/…/objectxmlgenerator/DatabaseIndexValidator.java` (156-231)
- `mithra/cache/FullSemiUniqueDatedIndex.java` (221-239); `mithra/cache/AbstractDatedCache.java` (143-148)
- `reladomo/src/test/reladomo-xml/TinyBalance.xml` (28-36), `BitemporalOrder.xml` (27-39, 103-105)
- `reladomographql/docs/temporal-milestoning.md`
