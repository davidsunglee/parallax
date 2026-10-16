---
date: 2026-10-16
git_commit: 649d6abb5876f240eeb59a6dfed7b85e46b18455
topic: "Whether the built-in transaction isolation should stay Read Committed or become Repeatable Read"
type: research
tags: [research, isolation, repeatable-read, read-committed, postgres, mariadb, recommendation]
status: complete
---

# Isolation Default Recommendation

**Recommendation: keep Read Committed as the built-in default.** Applications
that need a transaction-wide snapshot should request Repeatable Read per
invocation or per root.

This is evidence for a separate design decision. It is not that decision. The
built-in default stays Read Committed (`m-execution` *Options a root is
configured with*) until a human decides otherwise. Nothing in this evaluation
changed it.

The measurements behind each figure are in
[`01-attribution.md`](01-attribution.md). The witnesses are listed in
[`00-index.md`](00-index.md#witnesses). Reladomo's choices are recorded as
prior art in [`03-reladomo-prior-art.md`](03-reladomo-prior-art.md).

## Evidence

### Witness outcomes on both providers

The compatibility witnesses run Parallax's emitted SQL in two held sessions.
`just check` grades them on PostgreSQL and on MariaDB. The MariaDB results are
reference-harness evidence of native engine behavior. No Python MariaDB
adapter exists. The full table is in
[`00-index.md`](00-index.md#compatibility-cases). Grouped by what they mean for
the default:

- **Repeatable Read stabilizes reads on both engines.** At Read Committed:
  - an eager root and its include can see different states (`m-unit-work-051`,
    `-052`);
  - stream pages can gain or lose members between pages (`-053`, `-054`);
  - a bitemporal range read sees a peer's replacement (`m-temporal-write-061`,
    `-062`).

  At Repeatable Read each of these sees one snapshot.
- **Repeatable Read turns a stale write into a retriable failure.** The keyed
  gate race (`m-opt-lock-034`, `-035`), a fixed-revision `*_if` after a peer
  change (`-036`, `-037`), and the materialized versioned and
  Transaction-Time-Only predicates (`m-batch-write-043`–`-046`) match zero
  rows at Read Committed. At Repeatable Read they raise `40001` on PostgreSQL
  and `1020` on MariaDB.
- **Key-selecting writes differ by engine at Read Committed.**
  - On PostgreSQL, a key-selecting DELETE or UPDATE that waited on a target
    whose correlation or own predicate column changed still writes that
    target, because only key membership is rechecked (`m-batch-write-020`–
    `-035`). At Repeatable Read the same schedules raise `40001`.
  - On MariaDB at Read Committed, after a correlation change the DELETE
    excludes the target and the UPDATE writes it (`-021`, `-024`). After an
    own-column change both exclude it (`-029`, `-033`).
  - On MariaDB at Repeatable Read both exclude it with no error. MariaDB's
    Repeatable Read conflicts only once a read view exists, and here the write
    is the transaction's first statement.
- **MariaDB Read Committed runs with snapshot isolation off.** MariaDB 12.3
  defaults `innodb_snapshot_isolation` to on. Under that default, a
  key-selecting UPDATE after a correlation change raised `1020` at Read
  Committed. The harness's Read Committed mapping now sets the variable off
  for each attempt, as `m-db-port` *Mapping obligations* requires. With that
  setting the UPDATE writes the moved target, as on PostgreSQL, and both
  engines share `m-batch-write-024`. The engines still differ at Read
  Committed where MariaDB re-reads the changed row and excludes it: the
  correlation-change DELETE and both own-column-change writes above, and the
  joined-row schedules tabulated in [`00-index.md`](00-index.md#compatibility-cases).
  Repeatable Read keeps the variable on.
- **Dependency locks keep protecting unwritten rows at Repeatable Read**
  (`m-read-lock-023`). The level does not replace them.
- **PostgreSQL Repeatable Read refuses physical change, not semantic change.**
  An unchanged-milestone guard rewrites its row to hold the gate. At
  Repeatable Read, guard/guard and guard/write schedules therefore raise
  `40001` with no value changed (`m-temporal-write-065`–`-068`). MariaDB plans
  no guard.

### C0–C6 deltas

These are PostgreSQL figures.

- **Hot-key completion.** Before this work:
  - Read Committed completed 0.204 of hot-key invocations at the default
    bound, because the selective policy surfaced gate races.
  - Repeatable Read completed 0.934, because it replayed them as `40001`.

  With uniform replay and the selected backoff, the two converge: 0.989 at
  Read Committed against 0.991 at Repeatable Read, with 1.72 against 1.62
  attempts per success. That is C0 against C6.
- **First attempts are close at either level**: 0.21 against 0.24 at
  `max_retries=0`, in every arm.
- **The gate race replays to commit at both levels.** That changed at C3.
- **The changes that matter here are level-independent.**
  - Read-only transactions cost no more than reads in a writable attempt and
    hold no locks (C1).
  - Evidence-free standalone and read-only results retain 25–56% fewer bytes
    (C5).
  - Strict source admission costs nothing measurable (C2).

  None of these depends on the default.

### Guard WAL and replay cost

- **WAL is identical at both levels.** A guard writes 176 B at p50. A
  statement-free Locking amendment writes 96 B, and a changing amendment
  416 B.
- **Replay cost differs.** Two writers guard one balance, 400 invocations:

  | | Read Committed | Repeatable Read |
  |---|---|---|
  | `max_retries=0` | 400 of 400 commit on the first attempt | 200 of 400 surface `40001` |
  | Default bound, immediate replay | 400 of 400 | 382 of 400 commit; 18 exhaust |
  | Default bound, selected backoff | 400 of 400 | 400 of 400 commit; 1.06 attempts per success |

  Every Repeatable Read failure here comes with no semantic conflict
  (C0, C6).

### Snapshot-horizon cost

A slowly consumed transaction-held stream of 20,000 rows ran beside two
writers for about 19 s.

| | Read Committed | Repeatable Read |
|---|---|---|
| Oldest snapshot age p50 | about 100 | 3,800–4,500 |
| Dead tuples at release | about 260 | 7,700–8,700 |
| Relation after release | 1,248 KiB | 1,648–1,696 KiB |
| Index after release | 456 KiB | 888 KiB |

- `VACUUM` reclaimed the dead tuples but did not shrink the files.
- A held read-only transaction pins its snapshot exactly as a writable one
  does (C1).
- Standalone streams, which hold no transaction between pages, show no level
  effect.
- Writer throughput was not reduced in this window.

This cost is a database-retained MVCC cost, distinct from Parallax's
intentional temporal history.

## Limits Repeatable Read does not remove

The witnesses show the same outcome on both engines:

- **Predicate truth at commit** (`m-db-error-013`). A Repeatable Read
  transaction commits while an unwritten row matches its predicate.
- **Write skew** (`m-db-error-012`). Two transactions each check an invariant
  against their snapshot and both commit, breaking it.
- **Pre-snapshot external revisions** (`m-db-error-014`, `m-opt-lock-038`). A
  revision read before the snapshot is not validated by the snapshot. Only
  the caller-stated condition of a fixed-revision `*_if` protects it.
- **Gap creation** (`m-temporal-write-063`, `-064`). Two transactions can both
  fill one Valid-Time gap with overlapping rectangles. Disjoint creation stays
  valid.

Decision correctness for writes therefore rests on Parallax's gates,
dependency locks, and fixed-revision commands at either level, or on
Serializable. Repeatable Read stabilizes what a transaction reads. It does
not make what it decides true at commit.

## Recommendation: keep Read Committed

1. **Replay no longer depends on the level.** At the C0 source, the levels
   differed most in replay: Read Committed surfaced a current-attempt gate
   race that Repeatable Read replayed. Uniform recoverable-conflict replay
   with the selected backoff removed that difference. Both levels now
   complete about 99% of hot-key invocations at the default bound.
2. **Repeatable Read's benefit is opt-in where it matters.**
   - Read stability inside one transaction is the real gain: no torn graphs,
     stable stream membership, and stable range reads.
   - Applications that need it can request it per invocation or per root. The
     read-only form is now the cheap way to ask, with
     `db.read_only(fn, isolation="repeatable_read")`: no participation locks,
     no write evidence, no unit of work, and no write conflicts to replay.
   - Standalone reads, the default read path, never get a shared snapshot
     under either default. Changing the default would change only reads
     inside transactions.
3. **Repeatable Read adds costs Read Committed does not.**
   - *Snapshot horizon.* Long transaction-held reads retain about 30 times the
     dead tuples, and the files grow by amounts `VACUUM` does not return.
   - *Physical-change failures.* Unchanged-milestone guards conflict with no
     semantic change. A fixed-revision `*_if` spends a second attempt before
     its terminal precondition failure, and key-selecting writes replay.
4. **Repeatable Read does not remove the decision anomalies a default could be
   expected to address.** Write skew, predicate truth at commit, pre-snapshot
   revisions, and gap creation remain. A stronger default would suggest a
   guarantee it does not give.
5. **The strongest argument for Repeatable Read is predicate writes, and it
   has a per-invocation remedy.**
   - At PostgreSQL Read Committed, a key-selecting write acts on a target
     whose predicate truth changed while it waited. The C0 trace deleted a row
     no longer matching.
   - At Repeatable Read the write raises `40001`, and the replay acts on the
     current membership.
   - COR-211 kept the key-selecting lowering and documented the engine
     outcomes. Callers whose predicate writes must not act on a selected
     target whose predicate truth changed while they waited can request
     Repeatable Read for those invocations.
   - That protects only the targets the statement selected. A row that
     comes to match after the snapshot is not written, and the transaction
     still commits (`m-db-error-013`).

The recommendation would change in two cases:

- The project decides that reads inside a transaction must share one snapshot
  by default.
- Read Committed's predicate-write outcome is judged unacceptable as default
  behavior.

Either is a product decision about default semantics, not a measured cost.

## If the default were switched

The follow-up decision needs this inventory whichever way it goes. It is
accurate at `649d6abb5`.

**Contracts, schemas, and decision records.**

- `m-execution` *Options a root is configured with*: the built-in record
  states Read Committed, a concrete level requested on every attempt.
- `m-db-port`: a modeled outer transaction's omitted isolation resolves to Read
  Committed. The connection-intake floor, which refuses a session default
  below Read Committed, is independent and would stay.
- `m-case-format`:
  - the built-in `read-committed` in `given.databaseOptions`;
  - the meaning of an omitted `when.uow.isolation`;
  - *Conflict cases*, which require Read Committed for a staged `given.apply`
    writer.
- `compatibility-case.schema.json` names the built-in `read-committed` in its
  `given.databaseOptions`, `when.uow.isolation`, and
  `lifecycleInvocationStarted` descriptions. `conformance-adapter.schema.json`
  repeats it in its `lifecycleInvocationStarted` description.
- ADR 0065 states Read Committed as the concrete default. A switch needs a
  superseding ADR. ADR 0061's portable vocabulary is unaffected.

**Options.**

- `TxnOptions.isolation`'s default.
- `ReadOnlyTxnOptions` resolves from the same root record, so read-only
  invocations inherit any switch.
- Three choices for the follow-up:
  - switch both entrypoints;
  - keep Read Committed;
  - give read-only invocations their own default. A read-only Repeatable Read
    transaction raises no write conflicts, but it still pins the snapshot
    horizon. This would change the current contract that a read-only
    invocation inherits the root's isolation.

**Cases.**

- The conflict cases that stage `given.apply` without naming a level
  (`m-opt-lock-005`, `-009`) would be refused by the conformance lane. They
  would need an explicit `read-committed`.
- The interleaved conflict-abort witnesses (`m-opt-lock-012`,
  `m-inheritance-105`, `m-temporal-read-010`, `m-temporal-write-021`) grade an
  optimistic conflict. At Repeatable Read their peer change would arrive as a
  serialization failure instead.
- The lifecycle oracles that record the resolved level as `read-committed`
  would change, for example `m-unit-work-038` and
  `m-execution-lifecycle-004`.
- Python's `tests/api/test_database_options.py` pins that an unconfigured root
  runs at Read Committed over a stronger session default, and the
  transaction-runner unit tests pin that an omitted level asks the port for
  Read Committed.
- Usage-guide examples that rely on the default would need review, and the
  guide would need regenerating.

**Adapter and harness work.**

- PostgreSQL needs none. It already maps every level per attempt with
  `set local`.
- The reference harness resolves an omitted level to its own built-in
  `read-committed` (`DEFAULT_ISOLATION` in `reference_harness/case.py`).
- No production MariaDB adapter exists. A future adapter owes the harness's
  per-attempt `innodb_snapshot_isolation` mapping for both levels (on for
  Repeatable Read on 12.3.2+, off for Read Committed) whichever default is
  chosen, so a switch adds no MariaDB adapter work.

**Migration.**

- Applications that rely on seeing peers' commits within a transaction, or
  that hold long transaction streams, would need to request Read Committed
  explicitly.
- Operators should expect more serialization-failure replays, from guards and
  key-selecting writes, and snapshot-horizon growth under long transactions.
- The backoff constants were selected at Read Committed. C6 measured them
  once at Repeatable Read (0.991 completion, 0.94% exhausted). A grid at
  Repeatable Read would be owed before a switch.
