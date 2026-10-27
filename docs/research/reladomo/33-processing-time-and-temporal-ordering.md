# Processing time and temporal ordering: one JVM-clock instant per transaction, no ordering guard, and delete-on-equal

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). Path abbreviations: **`mithra/`** =
> `reladomo/src/main/java/com/gs/fw/common/mithra/`; **`test/`** =
> `reladomo/src/test/java/com/gs/fw/common/mithra/test/`.
>
> Source and first-party test definitions inspected on 2026-10-26. No Reladomo tests or
> database reproducer were executed; the stored outcomes below are traced through the source.

## Finding

Reladomo takes a transaction's processing time once, from the JVM clock, and stamps every
milestone the transaction closes or opens with it. No temporal director compares that instant
with a stored row's `IN_Z` for order. The one stored-value comparison is equality: a predecessor
whose `IN_Z` equals the instant is physically deleted rather than closed. Insertion validation
is an in-memory check of the transaction's active data, and overlap with committed history is
left to the generated primary key.

## Processing time per transaction

- `MithraLocalTransaction.getProcessingStartTime()` memoizes `System.currentTimeMillis()` on first
  use ([source](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/transaction/MithraLocalTransaction.java#L272-L279)). A nested transaction
  delegates to its root ([source](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/transaction/MithraNestedTransaction.java#L109-L118)), and a
  retry runs in a new transaction, so it takes a new instant.
- `setProcessingStartTime(long)` is public and unvalidated
  ([source](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/transaction/MithraLocalTransaction.java#L281-L285)); Reladomo's own tests use it
  to write processing times in the past.
- The directors truncate the instant to ten milliseconds ("clamp for sybase") and never consult
  the database clock ([source](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L104-L109)).

## No ordering guard; delete on an equal instant

`GenericBiTemporalDirector.inactivateObject` deletes a row new in the transaction, deletes a
committed row whose `IN_Z` equals the instant with the warning "has changed too fast. Deleting,
instead of inactivating", and otherwise closes it at the instant with no comparison
([source](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L301-L345)).
`AuditOnlyTemporalDirector.inactivate` applies the same equality rule to Transaction-Time-only
objects ([source](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/AuditOnlyTemporalDirector.java#L181-L203)). A processing time
behind the stored `IN_Z` therefore closes the row into an inverted interval. Two tests in
`test/TestDatedBitemporal.java` that set a custom processing time, `testTerminateAllCustomInz`
and `testUpdateLaterBusinesDayCustomInz`, close rows whose `IN_Z` is later than that time, and
assert query results rather than the stored bounds.

## Insert validation

`GenericBiTemporalDirector.insert` refuses only when the transaction's in-memory container holds
active data at the business date, then notes `//todo: rezaem: check the database to ensure nothing
matches this new object` ([source](https://github.com/goldmansachs/reladomo/blob/9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/GenericBiTemporalDirector.java#L71-L103)). Committed
history is checked by nothing but the generated primary key, the declared key plus each as-of
`to` column ([Gap-starting writes and insert overlap](32-gap-starting-writes-and-insert-overlap.md)).

## Relevance to Parallax

Parallax shares the per-attempt instant (ADR 0010) but not the remaining choices: ownership of a
row the attempt opened is an address record rather than an equal `IN_Z`, and a close the
instant cannot follow is refused and retried rather than deleted or inverted
([ADR 0078](../../adr/0078-stored-temporal-history-is-ordered-and-refused-never-clamped.md)).
