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
- **`inactivateObject`** (301-345): close an existing row — `UPDATE … SET OUT_Z=txTime WHERE PK AND FROM_Z=? AND THRU_Z=? AND IN_Z=? AND OUT_Z=∞`.
- **Update** (405-503): close the old row and insert a new head row `[fromDate, ∞)` at `IN_Z=txTime`; `cutTail` shortens the preceding segment's `THRU_Z` to `fromDate`.
- **`updateUntil`** (1011-1127) + **`splitTailEnd`** (1129-1137): the bitemporal **rectangle split** — one row becomes head `[from, fromDate)`, middle `[fromDate, endDate)`, tail `[endDate, to)`, all at fresh processing time, with the original inactivated.
- **Terminate** (687-756): close all open rows (`OUT_Z=txTime`); no new insert. Terminated state = absence of any row with `OUT_Z=∞ AND THRU_Z=∞`.

```text
BEFORE:  business [FROM_Z ─────────────── THRU_Z=∞)   proc [IN_Z ───────────── OUT_Z=∞)
UPDATE at businessDate=BD:
  old row closed   :  business [FROM_Z ─────────── ∞)   proc [old_IN_Z ── OUT_Z=txNow)
  new head row     :  business [BD ──────────────── ∞)   proc [txNow ──────── OUT_Z=∞)
  new left residual:  business [FROM_Z ─── BD)           proc [txNow ──────── OUT_Z=∞)
```

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
- `mithra/transaction/InTransactionDatedTransactionalObject.java`; `mithra/database/MithraAbstractDatedTransactionalDatabaseObject.java`
- `reladomographql/docs/temporal-milestoning.md`
