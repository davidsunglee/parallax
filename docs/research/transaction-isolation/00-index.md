---
date: 2026-10-15
git_commit: 7b465769dc87521c758a06d3d1fbfe3f55edba92
topic: "Transaction execution changes and the isolation default: witnesses, drivers, and paired captures"
type: research
tags: [research, isolation, repeatable-read, read-committed, postgres, mariadb, retry, read-evidence, benchmark]
status: living
---

# Transaction Isolation Evaluation

This directory holds the evidence for evaluating Parallax's transaction
execution changes and, separately, whether the built-in isolation level should
stay Read Committed. It has two parts. Functional behavior is pinned by
two-session witnesses: compatibility cases graded on every `just check`, and a
few evaluation-only scripts. Performance is measured by drivers that run
against pinned package sources in paired captures. The captures are
calibration evidence, not gates; nothing here except the corpus cases is read by
a check.

Python performance is PostgreSQL performance. MariaDB results come from the
reference harness and are labeled harness/native evidence, not Python
implementation performance.

## Witnesses

### Compatibility cases

Each schedule below is a `when.concurrency` choreography: two held sessions
running Parallax's emitted SQL verbatim at an explicit level, graded on both
providers by the reference harness and on PostgreSQL by the Python run sweep.
A step that waits for its peer's lock declares `blocks`, and the case states
each write's affected rows and the final table state
([`m-case-format`](../../../core/spec/m-case-format.md) *Error cases*). Where
the engines reach different outcomes, each engine has its own case. That the
golden statements are Parallax's emission is checked by the compile-graded
corpus and by the two scripts below that read statements off the real API.

| Schedule | Cases | PostgreSQL | MariaDB |
|---|---|---|---|
| Eager root and include statements around a peer commit | `m-unit-work-051`, `-052` | RC: torn graph; RR: one snapshot | same |
| Stream pages around a peer commit | `m-unit-work-053`, `-054` | RC: membership changes between pages; RR: stable | same |
| Keyed optimistic gate race | `m-opt-lock-034`, `-035` | RC: 0 rows; RR: `40001` | RC: 0 rows; RR: `1020` |
| Fixed-revision `*_if` after a peer change, snapshot taken first | `m-opt-lock-036`, `-037` | RC: 0 rows; RR: `40001` | RC: 0 rows; RR: `1020` |
| Fixed revision older than the snapshot | `m-opt-lock-038` | RR: 0 rows | same |
| Key-selecting DELETE/UPDATE after a correlation change | `m-batch-write-020`–`-027` | RC: waits, writes the moved target; RR: waits, `40001` | RC: delete waits and excludes the target, update waits and writes it; RR: waits and excludes it |
| Key-selecting DELETE/UPDATE after a target-column change | `m-batch-write-028`–`-035` | RC: waits, writes the target; RR: waits, `40001` | waits and excludes it |
| Key-selecting DELETE/UPDATE after a joined-row change | `m-batch-write-036`–`-042` | no wait; acts on the state its statement read | RC delete and both RR forms wait on the joined row and select nothing; RC update acts on the state it read |
| Materialized versioned predicate delete | `m-batch-write-043`, `-044` | RC: 0 rows; RR: `40001` | RC: 0 rows; RR: `1020` |
| Materialized Transaction-Time-Only predicate terminate | `m-batch-write-045`, `-046` | RC: 0 rows; RR: `40001` | RC: 0 rows; RR: `1020` |
| A locking read protecting a row the transaction never writes | `m-read-lock-023` | RR: the peer's update times out (`55P03`) | RR: `1205` |
| Bitemporal range read around a peer replacement | `m-temporal-write-061`, `-062` | RC: sees the replacement; RR: stable | same |
| Concurrent creation in a Valid-Time gap | `m-temporal-write-063`, `-064` | RR: overlapping rectangles both commit; disjoint ones stay valid | same |
| Unchanged-milestone guard against a guard or a close | `m-temporal-write-065`–`-068` | RC: waits and proceeds; RR: `40001` with no semantic change | no guard is planned |
| Write skew | `m-db-error-012` | RR: both commit; the invariant breaks | same |
| Predicate truth at commit | `m-db-error-013` | RR: commits while an unwritten row matches the predicate | same |
| A revision read before the snapshot | `m-db-error-014` | RR: the write commits unrefused | same |

### Evaluation scripts

| Script | What it retains |
|---|---|
| `predicate_in_place.py` | COR-211's schedules on PostgreSQL for UPDATE and DELETE in the key-selecting form Parallax emits and the historical in-place form; `--compare` grades them against the table COR-211's probes recorded |
| `lock_snapshot_trace.py` | Each witness schedule driven through the public API: the statements Parallax sent, each backend's state, wait, and snapshot horizon at every hand-off, and the outcome at `max_retries=0` and at the default bound |
| `guard_wal.py` | WAL bytes per unchanged-milestone guard against a locking write and a changing write, and guard/guard replay cost |

## Drivers

Every driver takes `--isolation`, `--smoke`, and `--out`, and runs under the
Python environment of the arm `capture.py` checks out. The measured work uses
only the public Snapshot API present in every arm of the checkpoints that run
it; provisioning and statement
recording use the conformance tooling the corpus runners already rely on.
`_support.py` declares the drivers' own model, so a corpus model change cannot
move a workload.

| Driver | Workload |
|---|---|
| `contention.py` | Hot and disjoint keyed writers, each invocation reading its account inside the attempt; `max_retries=0` first, then the default bound. With `--backoff-grid`, which C4 passes, the default bound once per `(base, cap)` candidate of the full-jitter backoff grid |
| `stream_churn.py` | A transaction-held or standalone stream with fast or slow consumption beside writers; client memory, oldest snapshot age, dead and live tuples, relation and index size, and cleanup after release. With `--read-only`, which C1 and C5 pass, a read-only transaction-held stream as well, so one arm reports writable and read-only reads at one level |
| `end_to_end_writes.py` | Keyed, conditional, and predicate amendments over non-temporal, Transaction-Time-Only, and bitemporal targets, each window a whole `db.transact` call with any licensing read inside it |
| `lock_snapshot_trace.py`, `guard_wal.py` | As above, captured per arm |
| Arm tool `tools/snapshot_delivery_overhead.py` | The committed delivery instrument, run from each arm's own tree |

The workloads are frozen at these digests (SHA-256). A later change to a driver
records its new digest here with the reason; `provenance.json` records the
digests a capture actually ran.

| File | SHA-256 |
|---|---|
| `scripts/_support.py` | `c41ef7b63439739b1f659a2e8d9ce3930f13310832726689e159360b12ea0605` |
| `scripts/capture.py` | `f878ceac3857728288bd311c0fe61b331c329578331a1a1757fca34a0a645a6d` |
| `scripts/contention.py` | `91fd3a2cbccd171779f6b9c9e149aa2141cb134241ff04d327bb8d7cd1b220ce` |
| `scripts/end_to_end_writes.py` | `015d7dc667a50fad1b6f63059755ee9ec82e0413352dd178684cced2b22f8963` |
| `scripts/guard_wal.py` | `3eaed87f4999e964e1d984983134ad30942bb0f2033a22ba08d203cadefe0d79` |
| `scripts/lock_snapshot_trace.py` | `a06a14359b95c45b1e5b5b890394d7bbbff9300aac7dd215fcb260937832fc18` |
| `scripts/predicate_in_place.py` | `9cd1a7fb74edd7aaa40f132996ea6525151032146c233a97c2bbc90cf751b810` |
| `scripts/stream_churn.py` | `16a2f0747f7f36cf965379f3a2e84497309214aa48ddff7ebd5255aa01dcfc0d` |

Read-only transactions re-froze two of them: `stream_churn.py` gained the
`--read-only` placement C1 compares against the writable one, and `capture.py`
runs it for C1 and C5. The placements every other checkpoint runs, and the
other drivers, are unchanged.

Bounded randomized backoff re-froze `contention.py` and `capture.py` again.
The driver fixes the `(base, cap)` candidate grid C4 selects from, whose middle
cell is the provisional backoff, and its `--backoff-grid` repeats the
default-bound runs once per candidate with the arm's internal constants
substituted, recording the backoff each run measured. An arm without the backoff
replays immediately and runs the default bound once. `capture.py` passes the
option for C4 alone.

## Checkpoints

`capture.py` owns each checkpoint's drivers. Each checkpoint runs both of its
arms in one session; no checkpoint reuses another's numbers.

| Id | Arm A | Arm B | Attributes |
|---|---|---|---|
| C0 | `7b465769` at explicit RC | `7b465769` at explicit RR | Current behavior at each level, and the delivery, selective-retry, and immediate-replay baselines |
| C1 | Read-only transactions' landing commit, writable reads | The same commit, read-only reads | Participation locks, evidence, setup cost, blocked and replayed reads, connection occupancy |
| C2 | The read-only landing commit | Strict source admission's landing commit | Existing versus strict admission, evidence retained |
| C3 | The complete conditional family's landing commit | Automatic optimistic replay, still immediate | Replay that Repeatable Read's serialization retries could conceal |
| C4 | Immediate automatic replay | Bounded randomized backoff candidates | Backoff selection |
| C5 | Backoff's landing commit | Evidence-free reads' landing commit | Standalone and read-only eager and stream reads before and after evidence removal |
| C6 | `7b465769` | The final design, at RC and RR | The combined change, and long transaction-stream churn |

A retained capture writes `captures/<checkpoint>/<arm>/`: one JSON report per
driver and a `provenance.json` naming the arm's commit, isolation, and lock
digest, the drivers' digests, the machine, the load average, and each driver's
server version, settings, image, fixture, pool, and offered load. Each
checkpoint stays within 10 MiB of raw JSON. `captures/` is empty until the
measurement campaign.

## Findings

These describe behavior at the C0 source, read from the witnesses above. A
diagnostic smoke run, which is not a retained capture, confirms the Parallax-level
outcomes through the public API.

- **PostgreSQL Read Committed rechecks only the target row.** A key-selecting
  write that waited on a target whose correlation or own predicate column
  changed still writes it, while the historical in-place form skips it. All
  twenty-four COR-211 schedules agree with the recorded table.
- **PostgreSQL Repeatable Read refuses physical change, not semantic change.**
  A stale gate, a fixed-revision `*_if` stated before the peer committed, and a
  write after an unchanged-milestone guard all raise `40001`, the retriable
  category. At the default bound Parallax replays them: the gate race commits on
  its second attempt, and the `*_if` command's replay then fails its
  precondition, terminally. At Read Committed the same gate race surfaces as an
  optimistic conflict after one attempt even at the default bound, because the
  selective policy does not replay it, and the `*_if` command fails its
  precondition at once.
- **MariaDB Repeatable Read conflicts only once a read view exists.** A
  transaction that read before its peer committed gets `1020`. One whose first
  statement is the write has no read view yet: the key-selecting statements
  re-read the changed rows and exclude them without a conflict.
- **MariaDB Read Committed runs with snapshot isolation off.** MariaDB 12.3
  defaults `innodb_snapshot_isolation` to on. Under that default a
  key-selecting UPDATE whose target changed during its wait failed with `1020`,
  while the matching DELETE excluded the target. The harness's Read Committed
  mapping now sets the variable off for each attempt
  ([`m-db-port`](../../../core/spec/m-db-port.md) *Mapping obligations*), and
  the UPDATE waits and writes the moved target, as on PostgreSQL, so the two
  engines share `m-batch-write-024` and `-025` is retired. The DELETE still
  excludes the target. No other MariaDB witness changed outcome.
- **Repeatable Read stabilizes reads, not decisions.** Deep fetches, stream
  pages, and Valid-Time range reads see one snapshot on both engines, but write
  skew commits, a predicate need not hold at commit, a revision read before the
  snapshot is not validated, and two transactions can both fill a Valid-Time gap.
  Dependency locks keep protecting rows a transaction never writes.

## Reproducing

From `languages/python`:

```sh
uv run python ../../docs/research/transaction-isolation/scripts/predicate_in_place.py --compare
uv run python ../../docs/research/transaction-isolation/scripts/capture.py C0 --smoke
uv run python ../../docs/research/transaction-isolation/scripts/capture.py C0
uv run python ../../docs/research/transaction-isolation/scripts/capture.py C0 --verify
```

A later checkpoint names its arms, for example
`capture.py C3 --arm <commit> --arm <commit>`; an arm takes `@repeatable_read`
to measure at that level.
