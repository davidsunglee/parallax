# Temporal repair and recovery: overlap detection is in-memory rectangle intersection; `OverlapFixer` delete-and-reinserts merged rectangles; `insertForRecovery` writes rows with caller-supplied milestones verbatim

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`test/`** =
> `reladomo/src/test/java/com/gs/fw/common/mithra/test/`.

Reladomo ships a small `mithra/overlap/` package for finding and repairing corrupt milestoning, plus
recovery-oriented mutations on `MithraDatedTransactionalObject`: `insertForRecovery`, `purge`,
`inactivateForArchiving`, and the increment family (`insertWithIncrement[Until]`, `incrementUntil`).

## Overlap detection: `OverlapProcessor` + pluggable `OverlapHandler`

Two conditions flag a row (`OverlapProcessor.collectOverlaps`, `mithra/overlap/OverlapProcessor.java:168-193`):

- **Invalid single row**: any as-of pair with `from >= to` (`AsOfAttribute.isMilestoningValid`, `mithra/attribute/AsOfAttribute.java:559-571`).
- **Pairwise overlap**: two rows with the same primary key (ignoring as-of columns) whose intervals intersect on **every** as-of dimension — `from1 < to2 && from2 < to1` per dimension (`isMilestoningOverlap`/`isOverlap`, `AsOfAttribute.java:548-557,573-577`).

Detection is **not** a SQL self-join. `loadMithraDataObjects()` (`OverlapProcessor.java:121-146`) runs
`finder.findManyBypassCache(...)` with an `equalsEdgePoint()` operation on every as-of attribute
(lines 148-157) — i.e. it streams the **entire table** (or an optional caller-supplied `Operation`
scope, constructor at 58-62) through a cursor, copies each `MithraDataObject`, sorts in memory by
primary key (88-119), then does an O(n²) pairwise scan within each PK group. Results go to an
`OverlapHandler` (`mithra/overlap/OverlapHandler.java:24-31`, callbacks `overlapProcessingStarted` /
`overlapsDetected` / `overlapProcessingFinished`). `OverlapDetector.main(mithraClassName [, source])`
(`mithra/overlap/OverlapDetector.java:32-55`) is the CLI entry point: it boots a
`PropertiesBasedConnectionManager` runtime with `CacheType.NONE` and prints printable PKs via
`OverlapReporter` (`mithra/overlap/OverlapReporter.java:25-58`).

## Overlap repair: `OverlapFixer` deletes all offenders and reinserts merged rectangles

`OverlapFixer.overlapsDetected` (`mithra/overlap/OverlapFixer.java:128-148`):

1. **Delete every overlapping row** — each becomes an `InTransactionDatedTransactionalObject` in `DELETED_STATE` inside a `BatchDeleteOperation` (150-162), a physical delete.
2. **Sort survivors by precedence** (`getOrderOfPrecedence`, 178-203): as-of attributes iterated last-to-first, `fromAttribute` **descending** then `toAttribute` ascending, then all other persistent attributes ascending — for bitemporal classes the highest `IN_Z` (latest-known) row wins.
3. **Merge to disjoint rectangles**: `MilestoneRectangle.fromMithraData` + `merge` (`mithra/util/dbextractor/MilestoneRectangle.java:187-202,250-286`). Merge pops a stack, giving precedence to list-front rectangles and **fragmenting** losers into up to four residuals — left/bottom/top/right (`fragment`, 79-117; intersection test 119-130). Rectangles with `from >= thru` are dropped with a warning (255-263) — invalid rows are deleted and never reinserted.
4. **Reinsert** each merged rectangle as a copy of its source data with rewritten milestone columns (`getMithraDataCopyWithNewMilestones`, 219-234) via `BatchInsertOperation` (164-176).

Batching: constructor batch size (default 1000, `OverlapFixer.java:54-62`); when pending deletes+inserts
reach it, one `executeTransactionalCommand` runs deletes **before** inserts (101-126). `overlapProcessingFinished`
flushes the remainder (91-99).

## `insertForRecovery`: insert a row exactly as specified, all four milestone columns included

Declared on `MithraTransactionalObject` (`mithra/MithraTransactionalObject.java:80-84`: "Inserts the data
as is for recovery of dated objects. All attributes, including to/from AsOfAttributes, must be set") and
routed through the behavior chain (`mithra/superclassimpl/MithraDatedTransactionalObjectImpl.java:711-714`)
to `TemporalDirector.insertForRecovery` (`mithra/behavior/TemporalDirector.java:43`).

`GenericBiTemporalDirector.insertForRecovery` (`mithra/behavior/GenericBiTemporalDirector.java:804-829`) validates:

- business date != infinity (`checkNotInfinityBusinessDate`, 1315-1322);
- all four of `FROM_Z/THRU_Z/IN_Z/OUT_Z` are set (`checkDatesAreAllSet`, 831-856; `to` columns may be skipped only when mapped infinite-null);
- the object's as-of dates fall inside its own from/to pairs (`checkDatesAreWithinRange`, 1324-1339);
- collision: if the container already has active data for the business date **and** the new row's `OUT_Z` is infinity → `MithraTransactionException` "cannot insert data. data already exists" (814-818). A `//todo` at 820 notes there is no database-side collision check.

It then inserts the single row unmodified — no chaining, no closing of neighbors. Contrast with `insert`
(71-103), which stamps `IN_Z=txTime, OUT_Z=∞, THRU_Z=∞` itself, and `insertUntil` (260-280), which only
lets the caller pick `THRU_Z` (and throws "until date set incorrectly" on mismatch, 269-277). So
`insertForRecovery` is the only mutation that can write already-inactive history rows (past `OUT_Z`) —
which is how `InactivateForArchivingLoader` expects late-arriving rows to reach an archive DB
(`mithra/util/InactivateForArchivingLoader.java:184`). `AuditOnlyTemporalDirector` (283-303) validates the
processing pair only; `GenericNonAuditedTemporalDirector` (542-546) checks business from/to then delegates
to plain `insert`.

## MAY-tier dated mutations

- **`insertWithIncrement`** (`GenericBiTemporalDirector.java:111-182`): back-dated insert of a new business segment when later segments exist. Requires no active data at the as-of date (117-120); with no later segments it degrades to `insert` (124-128). Sets `IN_Z=txTime, OUT_Z=∞`, `THRU_Z` = next segment's `FROM_Z` (132-143), then builds `DoubleIncrementUpdateWrapper`/`BigDecimalIncrementUpdateWrapper` for every non-zero double/BigDecimal attribute and **adds those deltas to all later segments** (145-171) before inserting. `AuditOnlyTemporalDirector` throws `RuntimeException` for the whole insert-until/increment family (109-122).
- **`insertWithIncrementUntil`** (184-258): same, but increments only segments in `[businessDate, exclusiveUntil)`.
- **`incrementUntil`** (858-873 + `incrementMultipleWrappersUntil` 875-951): applies an increment to the business range `[fromDate, endDate)`. Segments extending past `endDate` are split (`splitTailEnd`, 902/914/924); overlapped portions get an incremented copy at fresh `IN_Z` (`insertIncrementUntilSegment`, 953-964) while old rows are inactivated (`OUT_Z=txTime`) and a left residual is re-inserted when `activeFrom < fromDate` (930-936).

```text
incrementUntil(qty += 100, until=BD2) at businessDate=BD1, tx time T; one current row, qty=Q:
BEFORE:  qty=Q      [FROM_Z ───────────── ∞)      [IN_Z t0 ─── OUT_Z ∞)
AFTER:   old row    [FROM_Z ───────────── ∞)      [t0 ── T)             (inactivated)
         qty=Q      [FROM_Z ── BD1)               [T ───── ∞)           (left residual)
         qty=Q+100  [BD1 ──── BD2)                [T ───── ∞)           (incremented slice)
         qty=Q      [BD2 ───── ∞)                 [T ───── ∞)           (splitTailEnd)
```

- **`purge`** (758-802; javadoc `mithra/MithraDatedTransactionalObject.java:84-88` "no audit trail"): enrolls the current row and **every** cached row for the PK ignoring dates as `DELETED_STATE`, clears the container, and issues `tx.purge`, which executes `DELETE FROM <table> WHERE <pk-columns-without-dates>` (`mithra/database/MithraAbstractDatedTransactionalDatabaseObject.java:320-357`) — the entire bitemporal history for that key is physically destroyed.

```text
purge() on balance 50:
BEFORE:  [2003-01-01 ── ∞)[t1 ── t2)   [2003-01-01 ── 2004-01-01)[t2 ── ∞)   [2004-01-01 ── ∞)[t2 ── ∞)
AFTER:   -- DELETE FROM TINY_BALANCE WHERE BALANCE_ID = 50 → zero rows; past/current/future finds return null
```

- **`inactivateForArchiving(processingDateTo, businessDateTo)`** (1140-1183; javadoc `MithraDatedTransactionalObject.java:90-99` "must only be used in archiving scenarios"): expects exactly one segment whose `FROM_Z` equals the object's (else `MithraBusinessException` "stale data in object", 1152-1155). A row new in the same transaction is deleted (1156-1159); otherwise raw `TimestampUpdateWrapper` UPDATEs set `OUT_Z=processingDateTo` and, when non-null, `THRU_Z=businessDateTo` (1162-1177) — no chaining, no replacement row. Bulk driver: `InactivateForArchivingLoader` (`mithra/util/InactivateForArchivingLoader.java:37-122`, constructor takes `startTime/endTime/finder/source/destination`).

## Testing patterns

`test/overlap/AbstractOverlapFixerTest.java:57-283` drives three subclasses
(`OverlapFixerFullyMilestonedTest`, `OverlapFixerBusinessDateMilestonedTest`,
`OverlapFixerProcessingDateMilestonedTest`) over fixture
`reladomo/src/test/resources/testdata/overlapTestDataBroken.txt` (commented cases: "no milestoning",
"good milestoning on processing date", overlapping variants). Tests run the fixer at default and
batch-size-1 (142-150), with an `Operation` scope (152-179), compare surviving rows attribute-by-attribute
against `overlapTestDataFixed[WithOperation].txt`, then re-run detection with an `ExplodingOverlapHandler`
that fails on any remaining overlap (204, 265-282) — repair must reach a fixpoint.

`test/TestDatedBitemporal.java` covers the MAY tier with SQL-level checks via
`TestDatedBitemporalDatabaseChecker`: `testPurge` (3795, asserts `checkDatedBitemporalRowCounts == 0`
across past/current/future), `testPurgeThenInsert` (3848), `testPurgeThenRollback` (3998),
`testPurgeInPast` (5200), `testPurgeBadChaining` (5242), `testInsertForRecovery` (4039-4084, builds a
fully-inactive row with explicit `IN_Z/OUT_Z/FROM_Z/THRU_Z` then finds it at interior dates),
`testInsertForRecoveryMultipleTimes` (4086), `testInsertForRecoveryThenPurge` (4229),
`testInactivateForArchive[WithBusinessDate]` (~4412/4434), `testInsertWithIncrement*` (3068-3339),
`testInsertUntil` (3376), `testIncrementUntilSameBusinesDay`/`ForLaterBusinesDay` (1944/1993).

## Code references

- `mithra/overlap/OverlapProcessor.java` (process 64, load 121, collectOverlaps 168), `OverlapHandler.java`, `OverlapReporter.java`, `OverlapDetector.java` (main 32), `OverlapFixer.java` (overlapsDetected 128, precedence 178, batching 101)
- `mithra/attribute/AsOfAttribute.java` (isMilestoningOverlap 548, isMilestoningValid 559, isOverlap 573)
- `mithra/util/dbextractor/MilestoneRectangle.java` (fragment 79, merge 250, getMithraDataCopyWithNewMilestones 219)
- `mithra/behavior/TemporalDirector.java` (31-55); `GenericBiTemporalDirector.java` (insertWithIncrement 111, insertWithIncrementUntil 184, insertUntil 260, purge 758, insertForRecovery 804, incrementUntil 858, inactivateForArchiving 1140, validations 1315-1339); `AuditOnlyTemporalDirector.java` (purge 237, insertForRecovery 283, unsupported ops 109-122); `GenericNonAuditedTemporalDirector.java` (purge 495, insertForRecovery 542)
- `mithra/MithraTransactionalObject.java` (insertForRecovery 84), `mithra/MithraDatedTransactionalObject.java` (insertWithIncrement 62, purge 88, inactivateForArchiving 99, insertWithIncrementUntil 106)
- `mithra/database/MithraAbstractDatedTransactionalDatabaseObject.java` (purge SQL 320-357); `mithra/util/InactivateForArchivingLoader.java` (37-122, 184)
- `test/overlap/AbstractOverlapFixerTest.java`; `test/TestDatedBitemporal.java` (purge 3795+, insertForRecovery 4039+, inactivateForArchiving ~4412)
