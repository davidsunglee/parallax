# Transaction participation mode is per class within a Reladomo transaction

> Task-directed research against Reladomo at commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4` and Parallax at commit
> `3c57bd36d2d1a043848506ecc7941a538e824b6d`. Reladomo paths are relative to the
> peer checkout (`../reladomo`); Parallax paths are relative to this repository.

The question this finding answers is whether selecting optimistic locking for one
transaction forces every participating entity class to use optimistic concurrency,
and whether a non-versioned, non-temporal class can use shared read locks in the
same transaction where a versioned class uses an optimistic gate.

The short answer is **yes, Reladomo permits that mixture**. Reladomo does not have
one transaction-wide participation-mode value. A mode override is keyed by the
pair `(transaction, object portal)`, where an object portal represents one generated
class. Its generated API exposes only the modes applicable to that class. Parallax,
at the research baseline named above, specified `locking | optimistic` as one
property of the entire unit of work, so the proposed mixture was a specification
change for Parallax, not merely a clarification of its adopted behavior. ADR 0059
subsequently adopted one Unit Work preference with an Effective Concurrency
Strategy derived per Entity.

## Reladomo stores a separate mode for each class within a transaction

The generic transaction API makes the scope explicit: the setter takes both a
`MithraObjectPortal` and a `TxParticipationMode`
(`reladomo/src/main/java/com/gs/fw/common/mithra/MithraTransaction.java:298-307`).
`MithraLocalTransaction.setTxParticipationMode` remembers the portal among the
transaction's custom portals and delegates the value to that portal
(`reladomo/src/main/java/com/gs/fw/common/mithra/transaction/MithraLocalTransaction.java:61-65`,
`:712-721`). Cleanup iterates only those portals and clears this transaction's
overrides (`MithraLocalTransaction.java:340-349`).

Each `MithraTransactionalPortal` owns both a class-wide default and a
`TransactionLocal` override:

```java
// reladomo/src/main/java/com/gs/fw/common/mithra/portal/MithraTransactionalPortal.java:56-58
private static TransactionLocal transactionalQueryCache = new TransactionLocal();
private TransactionLocal txPatricipationMode = new TransactionLocal();
private TxParticipationMode defaultTxParticipationMode = FullTransactionalParticipationMode.getInstance();
```

Lookup first asks that portal for the current transaction's override and otherwise
returns that portal's default (`MithraTransactionalPortal.java:365-373`). Setting an
override writes it to the portal's transaction-local slot and forwards it to the
class's persister (`:385-389`). Consequently, changing class A's mode does not
change class B's mode in the same transaction.

## The generated Finder API constrains which classes can select optimism

Every generated Finder offers a class-scoped full-participation setter:

```java
// reladomogen/src/main/templates/readonly/Finder.jsp:1470-1473
public static void setTransactionModeFullTransactionParticipation(MithraTransaction tx)
{
    tx.setTxParticipationMode(objectPortal, FullTransactionalParticipationMode.getInstance());
}
```

The optimistic setter is generated only when the class `hasOptimisticLocking()`
(`Finder.jsp:1475-1479`). The generator defines that capability as a transactional
class with either a processing-date axis or an explicit optimistic-lock attribute
(`reladomogen/src/main/java/com/gs/fw/common/mithra/generator/MithraObjectTypeWrapper.java:3611-3614`).
For a non-versioned, non-temporal transactional class, the alternative generated
method is `setTransactionModeReadCacheUpdateCausesRefreshAndLock`, not the
optimistic setter (`Finder.jsp:1480-1484`).

There is also a per-class default. A transactional portal starts in full
participation (`MithraTransactionalPortal.java:56-59`), while generated portal
initialization changes the default to optimistic for a class with an explicit
optimistic-lock attribute (`Finder.jsp:1329-1352`; the client-portal path repeats
the rule at `:1370-1395`). Processing-time temporal classes qualify for the
per-transaction optimistic setter but do not receive that explicit-version default.

The generated API therefore makes a mixed transaction ordinary:

1. an explicitly versioned class is optimistic by its portal default, or a
   gate-capable class is switched to optimistic through its own Finder;
2. an unversioned, non-temporal class remains in full participation; and
3. both portal-specific modes coexist under the same `MithraTransaction`.

Calling the lower-level transaction setter directly could attach the optimistic
mode to an incapable portal, but the generated class API does not expose that
combination and the incapable class has no optimistic predicate to emit. The
supported surface is therefore narrower than the raw portal setter's type permits.

## Reads and writes consult the participating class's effective mode

`FullTransactionalParticipationMode` returns `true` from both `mustLockOnRead()`
and `mustParticipateInTxOnRead()`
(`reladomo/src/main/java/com/gs/fw/common/mithra/behavior/txparticipation/FullTransactionalParticipationMode.java:34-42`).
`ReadCacheWithOptimisticLockingTxParticipationMode` returns `false` for both and
`true` from `isOptimisticLocking()`
(`reladomo/src/main/java/com/gs/fw/common/mithra/behavior/txparticipation/ReadCacheWithOptimisticLockingTxParticipationMode.java:34-47`).

SQL generation asks each portal whether its own effective mode requires a lock and
appends the locking or non-locking table fragment accordingly
(`reladomo/src/main/java/com/gs/fw/common/mithra/finder/SqlQuery.java:401-413`). A
query involving dependent portals is classified as a transactional read if the
target portal or any dependent portal requires locking
(`reladomo/src/main/java/com/gs/fw/common/mithra/database/MithraAbstractDatabaseObject.java:567-587`).
On the write side, enrollment likewise asks the object's portal: optimistic mode
enrolls without refresh, whereas every other mode refreshes with a write lock
(`reladomo/src/main/java/com/gs/fw/common/mithra/behavior/persisted/PersistedTxEnrollBehavior.java:62-76`).
The UPDATE path appends an optimistic predicate only when the class has optimistic
locking and that class's portal is optimistic in the current transaction
(`MithraAbstractDatabaseObject.java:4927-4937`).

These call sites confirm the operational consequence of the storage model: one
transaction can lock rows of an unversioned class while relying on version or
processing-start gates for rows of a different class. The exact database lock
strength remains dialect-specific; the important fact here is that the first
class's reads request the locking SQL path while the second class's reads do not.

Reladomo's tests also configure related classes separately rather than switching a
whole transaction. For example, one deep-fetch transaction calls the optimistic
setter independently on `AuditedOrderFinder`, `AuditedOrderItemFinder`, and
`AuditedOrderStatusFinder`
(`reladomo/src/test/java/com/gs/fw/common/mithra/test/TestAdhocDeepFetch.java:543-555`).
That is consistent with portal-scoped, not transaction-global, configuration.
`TestOptimisticTransactionParticipation` also exercises an explicitly versioned
`OptimisticOrder` under its generated optimistic default and, in another test,
switches that same Finder to full participation for one transaction
(`reladomo/src/test/reladomo-xml/OptimisticOrder.xml:32`;
`reladomo/src/test/java/com/gs/fw/common/mithra/test/TestOptimisticTransactionParticipation.java:332-368`).

## The Parallax research baseline specified one unit-of-work-wide mode

At the recorded Parallax baseline, the normative core specification said that a unit of work selects one of
two strategies per transaction: `locking` or `optimistic`
(`core/spec/m-unit-work.md:899-911`). It then states explicitly that the mode is a
property of the unit of work, **not** of the entity (`m-unit-work.md:913-919`). The
Python surface carries the same contract: the active transaction has one
participation mode, and an optimistic object find omits the shared lock
(`languages/python/spec/python.md:2780-2792`).

The optimistic facet nevertheless classifies entities individually. An
`ExplicitVersion` entity has a version attribute, a `TransactionTimeDerived`
entity uses its processing start, and an `Unversioned` entity has neither; the
latter's writes emit no gate and advance no version
(`core/spec/m-opt-lock.md:43-69`). Under the current unit-of-work-wide rule,
selecting `optimistic` also makes participating finds omit locks
(`m-opt-lock.md:26-35`). Thus an unversioned, non-temporal keyed write inside an
optimistic Parallax unit of work has no optimistic gate available and cannot gain
the protection the mode promises from that mechanism.

## Design consequence adopted by Parallax

The source evidence supports allowing the proposed mixture. The smallest safe
Parallax rule is to keep one ergonomic unit-of-work preference while deriving an
**effective concurrency strategy per written entity**:

- under `locking`, every lockable participating read uses the existing shared-lock
  path and writes remain ungated;
- under `optimistic`, a versioned or Transaction-Time entity uses lock-free reads
  plus its version/milestone gate; and
- under `optimistic`, an unversioned, non-temporal entity falls back to the shared-
  lock path because it has no gate.

That rule permits the exact mixed transaction in question without exposing
Reladomo's per-Finder configuration surface. It also preserves the source boundary:
an authentic value read outside the transaction can safely source a keyed write
only when its entity supplies an optimistic gate; a lock-fallback entity must have
been read inside the transaction so the shared lock is actually held.

ADR 0059 adopts this rule and supersedes Parallax's earlier statement that one
effective mode applies unit-of-work-wide. Its implementation requires
mixed-Entity compatibility coverage. A fuller Reladomo-style per-Entity override
API remains possible, but the evidence does not require that additional public
configuration surface to obtain the safety property.

## Not determined

- No single Reladomo test was found whose assertion explicitly names the mixed
  versioned/unversioned concurrency policy. The conclusion follows from the
  portal-keyed mode storage, generated class-specific setters, and mode-dependent
  read/write call sites cited above.
- This pass did not determine lock-clause portability for every SQL dialect. The
  existing Reladomo locking research covers dialect-specific syntax; this finding
  is about the scope at which the locking decision is selected.
