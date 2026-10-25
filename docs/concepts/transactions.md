# Transactions, concurrency and retry

A transaction in Parallax is a callback the framework runs, not a block the caller opens
and closes. Because Parallax owns the boundary, it can run the callback again when a
failure a fresh attempt could fix ends it, it can keep one transaction's writes together
until they commit, and it can refuse a write that doesn't show what it overwrites. This
page explains what a transaction is made of, how it protects the rows it writes, what
its isolation level promises, which failures it retries, and what happens when one
transaction calls code that opens another.

Each section names the specification that owns it. This page explains and links; when
it and a specification seem to disagree, the specification is right.

## Invocations, attempts and transactions

Three things that are easy to conflate are kept apart
([attempts](../../core/spec/m-execution.md#attempts)):

- a **Transaction Invocation** is one call to the transaction entrypoint. It resolves
  its options once, and it ends by returning the callback's value or by failing;
- a **Transaction Attempt** is one run of the callback. An invocation makes one attempt,
  and a further attempt each time it retries;
- the **database transaction** is what one attempt opens on its connection, and commits
  or rolls back.

```text
 Transaction Invocation            one call; options resolved once
   │
   ├─ Transaction Attempt 1        adopts a Model Edition, acquires a connection,
   │    begin → callback → pre-commit flush → commit
   │    failed → rolled back, connection released, failure classified once
   │      ├─ not a recoverable conflict, or the bound is used up
   │      │      → the failure reaches the caller
   │      └─ recoverable, bound remaining → a bounded random wait, then:
   │
   ├─ Transaction Attempt 2        a fresh connection, fresh reads, a fresh instant
   │    begin → callback → pre-commit flush → commit
   │
   └─ committed → only now does the callback's value reach the caller
```

Each attempt starts from nothing the previous one left behind. It acquires its own
connection, adopts the serving Model Edition afresh, re-runs every read, and captures its
own lazy Transaction Instant, the one timestamp all of its temporal and audit writes
share ([the Transaction Instant](../../core/spec/m-unit-work.md#the-transaction-instant)).
What the callback did outside the database is not undone, and a value it captured from
outside is not refreshed. That is the price of replay, and the reason the boundary is a
callback: only a callback can be run twice.

The callback's value is withheld until the commit succeeds. If the attempt rolls back or
the commit fails, the invocation fails rather than return a value as though it were
durable ([abort](../../core/spec/m-unit-work.md#abort),
[ADR 0006](../adr/0006-transaction-callbacks-return-after-commit.md)).

## The unit of work

A writable attempt holds a **Unit of Work**, the coordinator of its writes
([the unit of work](../../core/spec/m-unit-work.md#the-unit-of-work)). It is not the
transaction: the attempt owns the database transaction and its lifetime, and the unit of
work consults that lifetime. A read-only attempt has no unit of work at all.

The unit of work buffers each write, combines writes to the same object, and sends them
at a flush. A flush happens for exactly three reasons: a read that depends on pending
writes, a predicate-selected write, and the commit. Everything a flush sends lands
inside the still-open database transaction, so a rollback erases it, even when a read
already saw it. [The write flow](write-flow.md) follows a write through these stages.

## Licences: no blind writes

A keyed write to an object that already exists must show what it is overwriting. That
proof is its **licence**, and Parallax checks it when the verb is called, before anything
is buffered
([current-attempt source admission](../../core/spec/m-unit-work.md#current-attempt-source-admission)):

| Licence | Comes from |
| -- | -- |
| a State Observation: the version or Transaction-Time start a read saw | a read of a versioned or temporal Entity in the writing attempt |
| a shared lock that read holds | a read in the writing attempt of an Entity whose strategy is Locking |
| the attempt's own insertion of the object | the inserted value and values derived from it |
| a revision the caller states | a [target write](../../core/spec/m-unit-work.md#target-writes) |

A write with no licence would overwrite whatever is stored, including a change another
transaction made after the caller looked. So it is refused. The licence must also come
from the attempt that writes: a value from a standalone read, a read-only transaction or
an earlier attempt took part in nothing the writing attempt can stand on
([ADR 0072](../adr/0072-source-writes-are-admitted-only-by-a-read-of-the-current-attempt.md)).
This is what makes replay safe. The three licences the attempt gathers for itself are
gathered again by the re-run's own reads and insertions; only a stated revision carries
across attempts, unchanged, as the caller's assertion.

A predicate-selected write needs no licence because it reads nothing, which is why only
an Entity with no version and no history accepts one
([write flow](write-flow.md#predicate-writes-run-at-the-call)).

## Concurrency: one preference, a strategy per Entity

A transaction resolves one **Concurrency Preference**, `optimistic` or `locking`.
Parallax combines it with each Entity's model to derive the **Effective Concurrency
Strategy** that Entity actually uses
([strategy selection](../../core/spec/m-unit-work.md#strategy-selection--one-preference-an-effective-strategy-per-entity),
[ADR 0059](../adr/0059-concurrency-preference-defaults-optimistic-and-resolves-per-entity.md)):

```text
 Concurrency Preference   the Entity's model                 Effective Concurrency Strategy
 ──────────────────────   ─────────────────────────────────  ──────────────────────────────────────
 optimistic               an explicit version                Optimistic: reads take no lock;
                                                               writes are gated on the observed version
 optimistic               Transaction Time (temporal)        Optimistic: reads take no lock;
                                                               closes are gated on the observed start
 optimistic               unversioned Non-Temporal           Locking: reads take a shared lock;
                                                               writes are ungated
 locking                  any                                Locking: reads take a shared lock;
                                                               writes are ungated
```

So `optimistic` means "gate a write wherever the model supplies a revision, and lock
where it doesn't". One transaction can read one Entity optimistically and another under
a shared lock. The two strategies trade differently. Optimistic costs nothing until two
writers meet, and then one of them conflicts and replays
([conflict detection](../../core/spec/m-opt-lock.md#conflict-detection)). Locking makes
the second writer wait instead
([read locks](../../core/spec/m-read-lock.md#automatic-read-lock-correctness)), which
suits rows many transactions write at once, at the cost of waiting and of deadlocks
between waiters.

Only a read inside a writable transaction takes the lock. A standalone read and a
read-only transaction lock nothing, whatever the preference.

## Isolation: a portable vocabulary, graded per adapter

The **Isolation Level** is a second, independent option. The strategy decides what a
read locks and what a write gates, per Entity; the level decides what every read of the
transaction sees
([the isolation level beside it](../../core/spec/m-unit-work.md#the-isolation-level-beside-it--what-the-transaction-reads)).
Parallax names three levels, each defined by the anomalies it forbids, never by a
vendor's implementation
([the portable isolation vocabulary](../../core/spec/m-db-port.md#the-portable-isolation-vocabulary),
[ADR 0061](../adr/0061-transaction-isolation-is-a-portable-vocabulary-graded-per-adapter.md)):

| Level | Forbids | Still permits |
| -- | -- | -- |
| Read Committed | dirty reads | nonrepeatable reads, phantoms, serialization anomalies |
| Repeatable Read | dirty reads, nonrepeatable reads | phantoms, serialization anomalies such as write skew |
| Serializable | all of the above | a retryable failure rather than eventual success |

Each adapter maps a level to whatever its database needs to forbid those anomalies, for
every attempt. A level is exact: an adapter that can't open the level requested reports a
failure rather than open another one.
What a database does beyond the minimum is recorded per engine as its
[adapter profile](../../core/spec/m-db-port.md#adapter-profile--nonportable-per-engine),
and nothing may depend on it. PostgreSQL, for example, also rules out phantoms at
Repeatable Read, and enforces Serializable by failing a transaction that can't be put in
order with a serialization failure. **Permitted is not required**: no caller may count on
an anomaly happening because its level allows it. And Serializable protects only the
transactions that all ask for it.

Every transaction asks for a concrete level on every attempt. The built-in default is
Read Committed, requested explicitly rather than left to whatever the connection was
configured with
([ADR 0065](../adr/0065-boundary-option-defaults-belong-to-the-database-root.md)).

## Retry

A failed attempt is classified once, after its rollback, and that one verdict decides
whether the invocation re-runs it
([bounded automatic retry](../../core/spec/m-auto-retry.md#bounded-automatic-retry),
[ADR 0073](../adr/0073-internal-optimistic-conflicts-replay-automatically.md)). The
failures a re-run against fresh state can resolve are the **recoverable conflicts**:

| Failure | Retried? | Why |
| -- | -- | -- |
| Deadlock or serialization failure | yes | transient; a re-run can succeed |
| Optimistic Lock Conflict: a version or Transaction-Time start the framework observed in this attempt moved | yes | the re-run reads the newer state and applies the change to it |
| Either of the above caught by the callback, leaving a rollback-only refusal | yes, on the original failure's terms | the failure that doomed the attempt decides |
| Target write precondition failed: the revision the caller stated no longer matches | no | re-running would state the same revision again |
| Connection acquisition failure | no | no attempt began, so nothing can be replayed |
| Anything else | no | it surfaces after the attempt it ended |

The bound counts re-executions: the root's built-in bound is ten, so an invocation makes
at most eleven attempts, and a bound of zero runs the callback once. An exhausted bound
surfaces the last attempt's own failure, saying how many attempts ran. Before each
re-execution the boundary waits a bounded randomized delay, whose scale follows how long
the failed attempt took, so that invocations which collided spread out instead of
colliding again
([waiting between attempts](../../core/spec/m-auto-retry.md#waiting-between-attempts)).
Which failures are retried, and the delay, are fixed policy; the bound is the only
option.

### Observed and stated revisions

The table's second and fourth rows look alike: in both, a revision no longer matches.
The difference is who supplied it.

```text
 observed revision                           stated revision
 ────────────────────────────────────────    ────────────────────────────────────────
 taken by a read of this attempt             supplied by the caller with the write
 a re-run reads again and takes the          a re-run states it again, unchanged
   current revision
 a mismatch is a conflict the framework      a mismatch is the caller's failed
   resolves by replaying                       precondition, surfaced, never retried
```

A transaction can hold both kinds. Suppose it states a revision in a target write, and a
deadlock ends its first attempt. The deadlock is transient and not the caller's, so the
transaction retries. The re-run states the same revision again. If the row moved in the
meantime, the precondition fails, and that failure surfaces without a further retry
([target writes](../../core/spec/m-unit-work.md#target-writes),
[retry contract](../../core/spec/m-opt-lock.md#retry-contract)). A retry may re-take
what the framework observed; it must never override what the caller asserted.

## Joining and rollback-only

A transaction requested while another is active joins it rather than opening an
independent one
([ADR 0005](../adr/0005-nested-transactions-join-the-active-transaction.md)). The
joined callback runs in the active attempt, shares its unit of work, and returns its
value at once, because the outer invocation owns the commit. A join never renegotiates:
an option it leaves out is inherited, an option it names must equal the active value,
and a different value is an option conflict
([option resolution](../../core/spec/m-execution.md#option-resolution)). A join is also
refused when it comes from another root, runs as another actor
([execution authority](execution-authority-and-audit.md#transactions-keep-one-actor)),
or asks for the other access mode. Each refusal happens before the joined callback runs
and leaves the active transaction usable.

```text
 outer callback
   │
   ├─ joined call refused (owner, actor, access mode, options)
   │     → raised before the joined callback runs; the transaction stays usable
   │
   └─ joined callback raises, or a flush fails while executing
         → the attempt becomes rollback-only before the failure propagates
         → later reads, writes and joins are refused, citing the first cause
         → the callback may catch it and return: commit is still refused,
           the value withheld, the attempt rolled back
```

Rollback-only exists because the caller can't know what a failed joined callback left
behind: some of its writes may already be buffered or flushed. Letting the outer
callback catch the failure and commit would save part of a unit of work that failed.
Once an attempt is rollback-only it stays so until it rolls back. If its first cause
was a recoverable conflict, the invocation still retries, on that cause's terms
([abort](../../core/spec/m-unit-work.md#abort)).

## Read-only transactions

A read-only transaction is an invocation through the read-only entrypoint, whose
callback can read and has no modeled mutation
([read-only transactions](../../core/spec/m-execution.md#read-only-transactions)). Its
access mode is fixed by the entrypoint for every attempt. Its reads take no lock and
force no flush, so it suits several reads that must agree, at Repeatable Read or
Serializable, without making any writer wait. It joins only another read-only
transaction, and nothing it returns licenses a later write. It retries like a writable
transaction, and has no Concurrency Preference to resolve.

## Common use cases

- **Change what you just read.** Read inside a writable transaction and write the
  value; the read is the licence. A concurrent change replays the callback, or, under
  Locking, waits.
- **Compose helpers.** Give each helper its own transaction call. Called alone it
  commits; called from a transaction it joins, and everything commits together.
- **Keep a rule that spans several rows.** Check and write in one Serializable
  transaction. A concurrent transaction that would break the rule makes one of the two
  fail to serialize, and its re-run sees the other's work.
- **Save a form shown earlier.** State the revision the form showed in a target write.
  A retry won't paper over a change made since; the caller hears about it.
- **Hand retries to someone else.** A job queue that redelivers failed jobs can run each
  transaction with a bound of zero.
- **Read a consistent report.** Use a read-only transaction at Repeatable Read: one
  snapshot, no locks.

## Do it →

- [Running a transaction](../../languages/python/docs/guide/05-transactions.md#running-a-transaction)
- [Read-only and read-write transactions](../../languages/python/docs/guide/05-transactions.md#read-only-and-read-write-transactions)
- [Isolation levels](../../languages/python/docs/guide/05-transactions.md#isolation-levels)
- [Optimistic and locking concurrency](../../languages/python/docs/guide/05-transactions.md#optimistic-and-locking-concurrency)
- [No blind writes](../../languages/python/docs/guide/05-transactions.md#no-blind-writes)
- [Retries](../../languages/python/docs/guide/05-transactions.md#retries)
- [Options and root defaults](../../languages/python/docs/guide/05-transactions.md#options-and-root-defaults)
