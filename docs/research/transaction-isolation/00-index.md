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

| Document | Content |
|---|---|
| [`01-attribution.md`](01-attribution.md) | Per-change results across C0–C7, each linked to the capture files it reads |
| [`02-isolation-recommendation.md`](02-isolation-recommendation.md) | Whether the built-in level should stay Read Committed: evidence, limits Repeatable Read leaves, the recommendation, and what a switch would take |
| [`03-reladomo-prior-art.md`](03-reladomo-prior-art.md) | Reladomo's isolation, read participation, gates, streaming and cache qualifications, and retry timing |

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
The drivers declare their own models, `_support.py` the shared one, so a corpus
model change cannot move a workload.

| Driver | Workload |
|---|---|
| `contention.py` | Hot and disjoint keyed writers, each invocation reading its account inside the attempt; `max_retries=0` first, then the default bound. With `--backoff-grid`, which C4 passes, the default bound once per `(base, cap)` candidate of the full-jitter backoff grid. With `--environments`, which C7 passes, both key modes in each simulated environment, the default bound once per replay policy |
| `stream_churn.py` | A transaction-held or standalone stream with fast or slow consumption beside writers; client memory, oldest snapshot age, dead and live tuples, relation and index size, and cleanup after release. With `--read-only`, which C1 and C5 pass, a read-only transaction-held stream as well, so one arm reports writable and read-only reads at one level |
| `end_to_end_writes.py` | Keyed, conditional, and predicate amendments over non-temporal, Transaction-Time-Only, and bitemporal targets, each window a whole `db.transact` call with any licensing read inside it |
| `read_retention.py` | Standalone and read-only reads, eager and streamed, Typed and Wire, of a non-temporal Column-layout account and of non-temporal, Transaction-Time-Only, and bitemporal document charters with value-object payloads; whole-read and first-root latency, traced peak and held-result bytes, and a census of the objects a held result keeps |
| `lock_snapshot_trace.py`, `guard_wal.py` | As above, captured per arm. With `--environments`, which C7 passes, `guard_wal.py` runs only its guard/guard replay, in each simulated environment and once per replay policy |
| Arm tool `tools/snapshot_delivery_overhead.py` | The committed delivery instrument, run from each arm's own tree |

The workloads are frozen at these digests (SHA-256). A later change to a driver
records its new digest here with the reason; `provenance.json` records the
digests a capture actually ran.

| File | SHA-256 |
|---|---|
| `scripts/_support.py` | `d0594ab2e6aea9d118a0946cea2daab2c8be2d5fe2595aff1fad880ed58af64f` |
| `scripts/capture.py` | `a0aa4b22e012995c9d9f51ecb716f668876aac0190018bc0954a3366888d2c0d` |
| `scripts/contention.py` | `0a9f496e13cb337b573804aa1a9b2a190c2c26fa2c67e17ff5d79c4e9767cad8` |
| `scripts/end_to_end_writes.py` | `015d7dc667a50fad1b6f63059755ee9ec82e0413352dd178684cced2b22f8963` |
| `scripts/guard_wal.py` | `243345275cba7a3a92ec9ea43b2f359d0e1804072be8877bb8cbdcaddd1665ae` |
| `scripts/lock_snapshot_trace.py` | `a06a14359b95c45b1e5b5b890394d7bbbff9300aac7dd215fcb260937832fc18` |
| `scripts/predicate_in_place.py` | `9cd1a7fb74edd7aaa40f132996ea6525151032146c233a97c2bbc90cf751b810` |
| `scripts/read_retention.py` | `225e6e4a40e60e397a347987d723600ec8475fec5218d2fa3ea1e0d3c5481bd9` |
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

Evidence-free reads added `read_retention.py`, so C5 also measures eager reads
inside a read-only transaction, and the bytes a held result keeps apart from the
whole client's memory, over temporal structured payloads as well as the flat
account. It declares its own model; `_support.py`'s provisioning and scoping
helpers now take a model, defaulting to the shared one, so the other drivers'
workloads are unchanged. `capture.py` runs it for C5 alone.

Retaining summaries alone re-froze `capture.py`, after every checkpoint was
captured; no driver changed. It writes each driver's full report under
`--raw-dir`, outside the repository, and keeps in `captures/` the report
without its per-invocation and per-sample arrays. Where the notes quote a
figure only those arrays held, the retained summary records it: a contention
or guard-replay run's surfaced failures with their attempt and latency spans
and its p99 time to success, and an end-to-end cell's per-invocation peak and
net bytes and its statements. `--verify` refuses a retained report that still
holds the arrays.

Portable replay backoff re-froze `_support.py`, `contention.py`,
`guard_wal.py`, and `capture.py`, so C7 can test a backoff in environments
slower than the local container. `_support.py` gained the simulated
environments: `local`; `rtt-2ms`, which adds 2 ms of client-side latency to
every round trip; and `rtt-5ms+think`, which adds 5 ms and does 10 ms of
application work between an invocation's read and its write. The latency is
injected in the drivers' own connection wrapper, half before each request and
half before its answer, so the server sees statements as far apart as a remote
client would send them. Each statement, pipeline, and ordered write batch is
one round trip; a boundary opens with two (`BEGIN`, then the request that sets
its level and access mode) and settles with one; and each acquisition costs
one more, the pool's validation probe. A statement the server refuses still
waits for its answer. Each run records the round trips its connections waited
and their mean realized latency, and each report starts with a discarded
warm-up run. `_support.py` also names
the replay policies C7 compares: immediate replay, the fixed full-jitter
windows 8/25 ms and 8/400 ms, and the arm's own duration-scaled window, each
substituted for the arm's window per run, recording every wait's failed-attempt
duration and window. `contention.py` and `guard_wal.py` take `--environments`,
and `capture.py` passes it for C7 alone. Without it every driver runs the
workload it ran before.

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
| C7 | The duration-scaled backoff's landing commit at RC | The same commit at RR | Immediate, fixed, and duration-scaled replay in each simulated environment; contention and guard/guard replay |

A retained capture writes `captures/<checkpoint>/<arm>/`: one summary report
per driver and a `provenance.json` naming the arm's commit, isolation, and lock
digest, the drivers' digests, the machine, the load average, and each driver's
server version, settings, image, fixture, pool, offered load, and full report
size. Each checkpoint's retained JSON stays within 1 MiB.

| Id | Arms captured | Raw JSON, archived | Retained |
|---|---|---|---|
| C0 | `7b465769` at RC and at RR | 3.6 MB | 85 KB |
| C1 | `3850203e9` at RC and at RR; each arm reports its writable, read-only, and standalone streams | 0.2 MB | 19 KB |
| C2 | `3850203e9` and `44e78b3e2`, at RC | 0.4 MB | 32 KB |
| C3 | `563e54eae` and `ef923969b`, at RC | 2.6 MB | 35 KB |
| C4 | `ef923969b` and `e3785f21a`, at RC; `e3785f21a`'s `auto_retry` is the backoff's landing commit `95844b0c2`'s, unchanged | 6.6 MB | 41 KB |
| C5 | `e3785f21a` and `7ab69577a`, at RC | 0.4 MB | 168 KB |
| C6 | `7b465769` and `b04687c3f`, the selected backoff's landing commit, each at RC and at RR | 7.3 MB | 309 KB |
| C7 | `0581fd395`, the duration-scaled backoff's landing commit, at RC and at RR | 17.9 MB | 129 KB |

### Raw reports and rewritten commits

C7 was captured after the rewrite, so its full reports went straight to the
archive. Its `provenance.json` records each one's size and SHA-256; the
`SHA256SUMS` manifest below predates it.

The checkpoints were first committed with their full reports. The branch
history was then rewritten so that no commit holds the raw arrays: each
capture was reduced in place, as `capture.py` now reduces it. The full reports
are archived outside git at
`~/.local/share/parallax/evidence/cor-214/transaction-isolation-captures/`,
where `--raw-dir` points by default. Their `SHA256SUMS` manifest has SHA-256
`0067879b2a6a2c1ef6203bfd208f470868f1b7e799045d641b43cbbf00a23bc8`.

The rewrite changed only `captures/`, so each rewritten commit's code tree is
identical to its original's. Each `provenance.json` and capture directory
keeps the original SHA as the historical record of what was captured, and from
which tree:

| Original | Rewritten | Commit |
|---|---|---|
| `2d07ac327` | `3cc2f715b` | C0's capture; C1's capturing tree |
| `5ced6887d` | `9012a1939` | C1's capture; C2's capturing tree |
| `125148596` | `abce63a48` | C2's capture; C3's capturing tree |
| `5912d0a18` | `184ccca9a` | C3's capture; C4's capturing tree |
| `8886e730c` | `b04687c3f` | The selected backoff, C6's arm B; C5's capturing tree |
| `31eb4dc82` | `2d93a52ba` | C5's capture; C6's capturing tree |
| `649d6abb5` | `64b662d91` | The commit the attribution and recommendation notes were written against |

## Findings

These describe behavior at the C0 source, read from the witnesses above. The
retained C0 traces confirm the Parallax-level outcomes through the public API.
[`01-attribution.md`](01-attribution.md) attributes what each later change
moved, and [`02-isolation-recommendation.md`](02-isolation-recommendation.md)
weighs them for the default.

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
