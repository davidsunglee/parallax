---
date: 2026-10-16
git_commit: 649d6abb5876f240eeb59a6dfed7b85e46b18455
topic: "Per-change attribution of the transaction execution changes across checkpoints C0–C6"
type: research
tags: [research, isolation, repeatable-read, read-committed, postgres, retry, backoff, read-evidence, benchmark]
status: complete
---

# Transaction Execution Attribution, C0–C6

This note attributes each measured change to the checkpoint that isolates it.
Every number below is read from the raw JSON under [`captures/`](captures/).
Each section links the files it uses. [`00-index.md`](00-index.md) owns the
drivers, their digests, and the checkpoint arms. The isolation-default
question is treated separately in
[`02-isolation-recommendation.md`](02-isolation-recommendation.md).

## Summary

| Change | Checkpoint | Attributed effect (PostgreSQL) |
|---|---|---|
| Read-only transactions | C1 | A held read-only stream finishes 12–15% sooner than a writable one, near standalone speed, and peaks about 0.2 MB lower in client memory. Its snapshot horizon and dead tuples match the writable stream at the same level. |
| Strict current-attempt source admission | C2 | No measurable cost: statements are identical, and traced peaks are within 0.25%. Latency differences are noise. |
| Automatic optimistic replay, immediate | C3 | Read Committed hot-key completion rises from 0.213 to 0.931. Committed throughput stays flat at about 400/s, p99 rises from 7 to 53 ms, and 6.9% of invocations exhaust the bound. |
| Bounded randomized backoff, 8 ms base and 25 ms cap | C4 | Against immediate replay, hot-key committed throughput rises from 429 to 830/s, exhaustion falls from 6.44% to 0.88%, and attempts per success fall from 4.66 to 1.62. Disjoint p50 is unchanged. |
| Evidence-free standalone and read-only reads | C5 | Held-result bytes fall 25–26% for Typed account results and versioned document results, 49–50% for Wire account results, and 54–56% for temporal document results. Standalone and read-only results are cut the same, eager and streamed. |
| All of the above | C6 | Hot-key completion at the default bound rises from 0.204 to 0.989 at Read Committed and from 0.928 to 0.991 at Repeatable Read. At Repeatable Read the guard/guard schedule commits 400 of 400. First-attempt outcomes are unchanged. |

## Reading the captures

- **Provider.** Every capture is Python against PostgreSQL 18.6
  (`postgres:18.6-alpine@sha256:d3e1620b…`) on CPython 3.14.8. The machine is
  an Apple M5 with 10 cores and 32 GiB. No capture exercises MariaDB. MariaDB
  outcomes come from the compatibility witnesses listed in
  [`00-index.md`](00-index.md#compatibility-cases). Those are reference-harness
  evidence of native engine behavior, not Python performance.
- **Retained, not diagnostic.** Every figure comes from a retained capture
  that passed `capture.py --verify`. Diagnostic runs are cited only where
  marked.
- **Contention.** Eight writers each issue 200 back-to-back invocations, 1,600
  per run. An invocation reads one account inside its attempt and amends it.
  `hot` sends every writer to one account; `disjoint` gives each writer its
  own. Each key mode runs at `max_retries=0` first, then at the default bound.
- **Contention metrics.**
  - *Completion* is committed invocations over invocations. *Surfaced
    failures* count by type and native code.
  - *Committed throughput* is committed invocations over the run's wall time.
  - *Attempts per success* is total attempts over committed invocations. A
    failed invocation's attempts count too.
  - Every attempt does the same work: one point read and one gated update. So
    attempts per success is the work per committed invocation, in attempts.
  - Latency percentiles use `statistics.quantiles` (inclusive) over every
    invocation, or over committed invocations only where marked.
- **p99 time to success.** This scores an exhausted invocation as unbounded
  latency. It takes the nearest-rank 99th percentile (rank 1,584 of 1,600), so
  it is finite only when 16 or fewer invocations fail. The backoff selection
  rule uses this figure.
- **Snapshot horizon and dead tuples.** The oldest-snapshot age is
  `age(backend_xmin)`, counted in transaction IDs, not time. Dead tuples are
  superseded MVCC versions of the non-temporal `account` table, not temporal
  history.
- **Placements.** A *transaction-held* stream runs inside one transaction for
  the whole delivery. A *standalone* stream acquires a connection per page and
  holds no transaction between pages.
- **Load.** The preflight refuses to start above a 1-minute load of 2.5. Each
  `provenance.json` records the load average after its arm's drivers finish,
  so that figure includes the drivers' own load.

## C0: current behavior at Read Committed and Repeatable Read

Arms: `7b465769` at explicit RC and at explicit RR
([RC](captures/C0/7b465769dc87-read_committed/provenance.json),
[RR](captures/C0/7b465769dc87-repeatable_read/provenance.json)). This
checkpoint isolates the level alone, under the selective retry policy.

**Contention**
([RC](captures/C0/7b465769dc87-read_committed/contention.json),
[RR](captures/C0/7b465769dc87-repeatable_read/contention.json)):

| Hot key | RC | RR |
|---|---|---|
| Completion, `max_retries=0` | 0.208 (1,267 `OptimisticLockConflictError`) | 0.236 (1,223 `40001`) |
| Completion, default bound | 0.204 (1,274 conflicts, each after one attempt) | 0.934 (105 `40001`, each after 11 attempts) |
| Committed throughput, default bound | 404/s | 471/s |
| Attempts per success, default bound | 4.91 | 4.22 |
| Latency p50/p95/p99, default bound | 4.0 / 5.6 / 6.7 ms | 11.2 / 43.3 / 47.4 ms |
| Disjoint p50, default bound | 3.9 ms | 4.0 ms |

- The first-attempt outcomes are close: about four in five hot-key first
  attempts fail at either level.
- Only the retry policy separates the levels. At RC the selective policy
  surfaces a stale gate's conflict even at the default bound. At RR the same
  race is a `40001`, which the policy replays.
- RC's p99 is short because its failures are fast.

**Traces**
([RC](captures/C0/7b465769dc87-read_committed/lock_snapshot_trace.json),
[RR](captures/C0/7b465769dc87-repeatable_read/lock_snapshot_trace.json)):

| Schedule | RC, either bound | RR, `max_retries=0` | RR, default bound |
|---|---|---|---|
| Gate race | `OptimisticLockConflictError` | `40001` | commits on attempt 2 |
| Fixed revision (`amend_if` after a peer change) | `WritePreconditionError` | `40001` | `WritePreconditionError` on attempt 2 |
| Key-selecting delete after a correlation change | waits, then deletes both rows, including the moved one | waits, then `40001` | waits, then on attempt 2 deletes only the row still matching |
| Unchanged guard, then a peer's close | waits, then commits | waits, then `40001` | commits on attempt 2 |

**Guard WAL and replay**
([RC](captures/C0/7b465769dc87-read_committed/guard_wal.json),
[RR](captures/C0/7b465769dc87-repeatable_read/guard_wal.json)):

- WAL per write is identical at both levels, and in every later arm. The
  bytes are deterministic for the statements issued.
  - An unchanged-milestone guard writes 176 B at p50 (240/352 B at p95/p99).
  - A Locking amendment that keeps the milestone, with no statement, writes
    96 B.
  - A changing amendment that closes and chains writes 416 B at p50.
- Two writers guard the same balance, 200 invocations each:

  | | RC | RR |
  |---|---|---|
  | `max_retries=0` | 400 of 400 commit on the first attempt | 200 of 400 commit; 200 surface `40001` |
  | Default bound | 400 of 400 commit on the first attempt | 382 of 400 commit; 18 exhaust; 1.52 attempts per success |

  No value changes, so this is replay cost with no semantic conflict.

**Transaction-held stream churn**
([RC](captures/C0/7b465769dc87-read_committed/stream_churn.json),
[RR](captures/C0/7b465769dc87-repeatable_read/stream_churn.json)). The reader
streams 20,000 accounts in pages of 500 beside two writers.

| Slow consumer, about 19 s | RC | RR |
|---|---|---|
| Oldest snapshot age p50/p99 | 101 / 228 | 4,453 / 8,628 |
| Dead tuples at reader release | 261 | 8,680 |
| Relation / index bytes after release | 1,248 / 456 KiB | 1,696 / 888 KiB |
| After `VACUUM` | 0 dead, sizes unchanged | 0 dead, sizes unchanged |
| Writer commits per second | 444 | 465 |
| Client traced peak | 0.97 MB | 0.99 MB |

- A fast consumer, about 1.6 s, shows the same shape at a smaller scale: an
  oldest snapshot age of 1.5 against 45, and 2 against 100 dead tuples.
- Standalone streams are indifferent to the level. Snapshot age stays at 0–2
  and dead tuples at 157–159 at both levels, because no transaction spans
  pages.

**End-to-end writes**
([RC](captures/C0/7b465769dc87-read_committed/end_to_end_writes.json),
[RR](captures/C0/7b465769dc87-repeatable_read/end_to_end_writes.json)):

- Statements per invocation are identical at both levels:

  | | Keyed | Conditional (`amend_if`) | Predicate (`amend_where`) |
  |---|---|---|---|
  | Account | 2 | 1 | 2 |
  | Transaction-Time-Only balance | 3 | 3 | 3 |
  | Bitemporal position | 3 | 3 | 3 |

- Traced peaks agree within 0.5%.
- Latency p50s fall between 1.4 and 3.1 ms. Run-to-run noise exceeds any
  difference between levels.

## C1: writable versus read-only reads

Arms: `3850203e9`, where read-only transactions landed, once at RC and once at
RR ([RC](captures/C1/3850203e9cad-read_committed/stream_churn.json),
[RR](captures/C1/3850203e9cad-repeatable_read/stream_churn.json)). Each arm
runs writable-held, read-only-held, and standalone streams at one level. At
this commit a read-only stream still built deferred read evidence, through the
same branch a standalone read took. So this checkpoint attributes the
read-only transaction itself, not evidence removal; C5 attributes that.

| RC / RR | Writable held | Read-only held | Standalone |
|---|---|---|---|
| Fast: reader elapsed | 1.65 / 1.62 s | 1.40 / 1.42 s | 1.32 / 1.33 s |
| Fast: first root | 24.1 / 22.0 ms | 17.9 / 15.7 ms | 17.8 / 16.1 ms |
| Fast: client traced peak | 0.83 / 0.84 MB | 0.59 / 0.58 MB | 0.64 / 0.62 MB |
| Slow: client traced peak | 1.01 / 0.98 MB | 0.79 / 0.81 MB | 0.80 / 0.80 MB |
| Slow: oldest snapshot age p50 | 98 / 4,511 | 107 / 4,491 | 0 / 0 |
| Slow: dead tuples at release | 280 / 8,687 | 254 / 8,577 | 129 / 135 |
| Slow: relation / index after release | 1,248 / 456 and 1,696 / 888 KiB | 1,248 / 456 and 1,696 / 888 KiB | 1,232 / 456 KiB at both levels |

- **Delivery.** The read-only placement removes the writable attempt's
  per-read evidence context and unit of work. That shows as 12–15% less
  fast-consumer elapsed time and about 0.2 MB less client peak.
- **Snapshot horizon.** It does not change. A held read-only transaction pins
  its snapshot exactly as a writable one does at the same level.
- **Locks.** The streamed `account` is versioned, so under the Optimistic
  preference neither placement takes a participation lock. The lock
  difference is graded by `m-read-lock-024` and `-025`, not by this driver.
- **Replay and setup.** Nothing is replayed, because the stream conflicts with
  no writer. Native read-only setup travels in the request that sets the
  level, so it adds no round trip. No driver times it separately.
- **Connection occupancy.** Both held placements keep one connection for the
  whole reader elapsed time. The standalone placement holds one per page.

## C2: existing versus strict source admission

Arms: `3850203e9` and `44e78b3e2` at RC, both retaining evidence
([A](captures/C2/3850203e9cad-read_committed/end_to_end_writes.json),
[B](captures/C2/44e78b3e25d6-read_committed/end_to_end_writes.json)).

- Statements per invocation are identical across arms for all nine
  workflow/target cells.
- Median traced peaks agree within 0.25%, for example 22,480 B against
  22,480 B for the keyed account. Median net retention agrees within 1%.
- Latency moves in both directions, by more than the change could explain.
  - The keyed account p50 goes from 1.16 to 3.01 ms.
  - The conditional position p50 goes from 2.49 to 1.34 ms.
  - The predicate position p50, which the change does not touch, goes from
    1.40 to 3.01 ms.

  These are noise.

Strict admission therefore costs nothing measurable on workflows that already
read inside the attempt. Its effect is on caller workflows. A standalone,
read-only, or earlier-attempt source is refused, and an external observation
goes through a fixed-revision `*_if`. In every capture that write is the
cheapest end-to-end path for a versioned account: one statement, with no
licensing read.

## C3: selective versus automatic optimistic replay

Arms: `563e54eae`, the complete conditional family, and `ef923969b`, automatic
replay that is still immediate. Both run at RC
([A](captures/C3/563e54eaed18-read_committed/contention.json),
[B](captures/C3/ef923969b801-read_committed/contention.json)).

| Hot key | Selective | Automatic, immediate |
|---|---|---|
| Completion, `max_retries=0` | 0.214 | 0.213 |
| Completion, default bound | 0.213 (1,259 conflicts surfaced) | 0.931 (111 exhausted after 11 attempts) |
| Committed throughput, default bound | 415/s | 400/s |
| Attempts per success | 4.69 | 4.76 |
| Latency p50/p95/p99 (all) | 4.1 / 5.6 / 7.1 ms | 14.0 / 46.2 / 52.8 ms |
| Committed-only p99 | 6.1 ms | 49.1 ms |
| Disjoint p50, default bound | 4.1 ms | 4.4 ms |

- First-attempt outcomes are unchanged.
- Replay converts surfaced conflicts into commits, but the hot row's committed
  rate does not rise. Immediate replay spends 3.8 wasted attempts per commit,
  and the run takes 4.5 times as long.
- In the traces, the RC gate race now commits on its second attempt at the
  default bound. At `max_retries=0` it still surfaces the conflict. Every
  other schedule is unchanged
  ([A](captures/C3/563e54eaed18-read_committed/lock_snapshot_trace.json),
  [B](captures/C3/ef923969b801-read_committed/lock_snapshot_trace.json)).
- At RR the C0 baseline already replayed this race as `40001`. So this is the
  behavior RR's serialization retries concealed. RC and RR now treat a
  current-attempt gate race alike.

## C4: immediate replay versus bounded randomized backoff

Arms: `ef923969b`, immediate, and `e3785f21a`. At `e3785f21a` the backoff
mechanics, unchanged from where they landed, run once per candidate with the
base and cap substituted. Both run at RC
([immediate](captures/C4/ef923969b801-read_committed/contention.json),
[grid](captures/C4/e3785f21ad23-read_committed/contention.json)). Full jitter
draws `uniform(0, min(cap, base × 2^(attempt−1)))` after the failed attempt
has released its connection.

| Backoff (base/cap) | Hot throughput | Exhausted | Hot p99 (all) | Committed p99 | p99 to success | Attempts per success | Disjoint p50 |
|---|---|---|---|---|---|---|---|
| immediate | 429/s | 6.44% | 48.2 ms | 44.5 ms | unbounded | 4.66 | 4.02 ms |
| 0.5/25 ms | 666/s | 1.81% | 104.2 | 91.0 | unbounded | 2.95 | 4.08 |
| 0.5/100 ms | 751/s | 1.19% | 180.8 | 82.4 | unbounded | 2.12 | 4.11 |
| 0.5/400 ms | 758/s | 1.19% | 253.3 | 86.3 | unbounded | 1.99 | 4.10 |
| 2/25 ms | 769/s | 0.94% | 113.4 | 98.6 | 133.5 | 2.16 | 4.14 |
| 2/100 ms | 791/s | 0.56% | 207.8 | 153.8 | 217.8 | 1.47 | 4.10 |
| 2/400 ms | 655/s | 0.44% | 248.4 | 55.1 | 248.2 | 1.25 | 4.05 |
| **8/25 ms** | **830/s** | **0.88%** | 132.4 | 109.8 | **149.6** | **1.62** | 4.17 |
| 8/100 ms | 726/s | 0.38% | 270.7 | 178.6 | 270.7 | 1.24 | 4.08 |
| 8/400 ms | 497/s | 0.06% | 168.1 | 149.1 | 168.0 | 1.15 | 4.16 |

- **Zero retries and disjoint keys.** The backoff never runs on these, and
  they match the immediate arm. Hot completion is 0.217 against 0.214, and
  disjoint p50 spans 4.00–4.17 ms across every run that never waits.
- **Guard WAL** is identical across the arms
  ([immediate](captures/C4/ef923969b801-read_committed/guard_wal.json),
  [grid](captures/C4/e3785f21ad23-read_committed/guard_wal.json)). At RC the
  guard/guard schedule never conflicts, so its replay figures cannot separate
  the arms.
- **Every candidate beats immediate replay** on exhaustion, attempts, and
  throughput. Immediate replay burns its eleven attempts within 18–65 ms. Its
  p99 over all invocations is short only because 6.44% of invocations fail
  fast.
- **Selection.** The rule takes the highest hot-key committed throughput among
  candidates that are no worse than immediate replay on three counts:
  disjoint p50, exhaustion rate, and hot-key p99 time to success.
  - Immediate replay's p99 to success is unbounded. Every candidate passes the
    disjoint and exhaustion criteria.
  - 8/25 ms has the highest throughput of the nine, so it is selected whether
    or not the three 0.5 ms candidates, whose p99 is also unbounded, count as
    ties. It landed in `8886e730c`.
- **The p99 criterion is fragile near 1% exhaustion.** The selected
  candidate's exhaustion was 0.88% here (14 failures). In C6 the same
  constants exhausted 1.12% at RC (18) and 0.94% at RR (15). The nearest-rank
  p99 to success therefore flips between finite and unbounded from run to
  run. The runner-up 2/25 ms (0.94%) sits as close to the line.
  - The ranking among finite candidates is a single-run ordering, not a
    confidence-bounded one.
  - The throughput margin is the robust part. Every candidate beats immediate
    replay, and five of the six with a finite p99 to success do so by more
    than 1.5×. A rerun could reorder candidates within a few percent of each
    other.

## C5: standalone and read-only reads before and after evidence removal

Arms: `e3785f21a` and `7ab69577a` at RC
([A](captures/C5/e3785f21ad23-read_committed/read_retention.json),
[B](captures/C5/7ab69577aa2b-read_committed/read_retention.json)).
`read_retention` reads 2,000 roots in pages of 500. It covers 32 cells:
standalone and read-only placements, Typed and Wire, eager and stream, over
four subjects.

| Subject | Representation | Held-result bytes | Traced peak |
|---|---|---|---|
| Versioned Column-layout account | Typed | −25.4% to −25.7% | −14% to −21% |
| Versioned Column-layout account | Wire | −49.1% to −49.7% | −24% to −35% |
| Versioned document charter | Typed and Wire | −26.0% to −26.2% | −18% to −20% |
| Transaction-Time-Only document charter | Typed and Wire | −54.1% to −55.1% | −49% to −50% |
| Bitemporal document charter | Typed and Wire | −53.7% to −55.6% | −48% to −50% |

- **Placement.** For each subject, representation, and delivery, the
  standalone and read-only cells agree within 0.1 percentage point. Before
  removal, a read-only transaction's results retained exactly what standalone
  results did.
- **Census.** A held result loses one `ReadEvidence` and one
  `_DeferredEvidence` per root.
  - For the Typed account eager cell that is 16,067 to 10,067 tracked objects.
  - Temporal charters also lose the retained raw documents and their
    containers. The Transaction-Time-Only Typed eager cell goes from 60,031 to
    32,005 objects, with 20,000 dicts falling to 2,000. The bitemporal Wire
    stream cell's 18,000 dicts fall to none.
- **Latency.** Whole-read p50 moves from −3.5% to −23.4% in 31 cells and
  +11.8% in one, the Transaction-Time-Only Wire eager standalone cell.
  First-root latency is unchanged within noise. Treat the timing as within
  noise of a modest improvement.
- **Delivery instrument** on CPython 3.14
  ([A](captures/C5/e3785f21ad23-read_committed/snapshot_delivery.json),
  [B](captures/C5/7ab69577aa2b-read_committed/snapshot_delivery.json)):

  | | Conventional fan-out | Versioned document | Bitemporal current |
  |---|---|---|---|
  | Eager retained | −21.2% | −40.2% | −56.4% |
  | Eager peak | −10.7% | −22.6% | −36.2% |
  | Streamed page-128 peak | −14.2% | −16.5% | −20.8% |

- **Stream churn**
  ([A](captures/C5/e3785f21ad23-read_committed/stream_churn.json),
  [B](captures/C5/7ab69577aa2b-read_committed/stream_churn.json)):
  - Fast-consumer client peaks fall from 0.63 to 0.45 MB standalone and from
    0.58 to 0.46 MB read-only-held. The writable-held peak, 0.84 to 0.83 MB,
    is unchanged.
  - Slow-consumer peaks are within 0.04 MB. The process-wide peak there is
    dominated by the writers.
  - Snapshot horizon and dead tuples are unchanged in every placement.

## C6: the C0 source versus the final design

Arms: `7b465769` and `8886e730c`, the selected backoff's landing commit, each
at RC and at RR
([`7b465769` RC](captures/C6/7b465769dc87-read_committed/provenance.json),
[`7b465769` RR](captures/C6/7b465769dc87-repeatable_read/provenance.json),
[`8886e730c` RC](captures/C6/8886e730c2f9-read_committed/provenance.json),
[`8886e730c` RR](captures/C6/8886e730c2f9-repeatable_read/provenance.json)).

**Noise caveat.** Outside load slowed two sets of RC runs.

- The `7b465769` RC arm's first three contention runs ran at 236/s hot
  zero-retry, against 414/s in C0, and at 6.8 ms disjoint p50.
- The `8886e730c` RC arm's disjoint runs had p50s of 5.1 and 4.7 ms.

C6's RC throughput and latency deltas are therefore unreliable. Attribute RC
throughput from C3 and C4 instead. Use C6 for completion, exhaustion,
attempts, and trace outcomes, which counting does not distort. The RR arms
show no such disturbance.

**Contention**
([`7b465769` RC](captures/C6/7b465769dc87-read_committed/contention.json),
[`7b465769` RR](captures/C6/7b465769dc87-repeatable_read/contention.json),
[`8886e730c` RC](captures/C6/8886e730c2f9-read_committed/contention.json),
[`8886e730c` RR](captures/C6/8886e730c2f9-repeatable_read/contention.json)):

| Hot key | RC `7b465769` | RC `8886e730c` | RR `7b465769` | RR `8886e730c` |
|---|---|---|---|---|
| Completion, `max_retries=0` | 0.209 | 0.213 | 0.239 | 0.239 |
| Completion, default bound | 0.204 | 0.989 | 0.928 | 0.991 |
| Surfaced, default bound | 1,273 conflicts after 1 attempt | 18 exhausted | 115 `40001` exhausted | 15 `40001` exhausted |
| Attempts per success | 4.89 | 1.72 | 4.34 | 1.62 |
| Committed throughput | 237/s (disturbed) | 686/s | 439/s | 801/s |
| Latency p50/p95/p99 (all) | 6.9 / 9.8 / 11.1 ms (disturbed) | 1.4 / 63.2 / 150.6 ms | 12.0 / 45.1 / 50.8 ms | 1.2 / 63.5 / 139.8 ms |
| p99 to success | unbounded | unbounded (1.12%) | unbounded | 171.3 ms (0.94%) |

- RC throughput, attributed from C3 and C4: about 405–415/s under the
  selective policy, about 400–430/s under immediate replay, and 830/s with
  the selected backoff.
- At the final head the two levels converge: completion 0.989 against 0.991,
  and 1.72 against 1.62 attempts per success.

**Traces**
([`7b465769` RC](captures/C6/7b465769dc87-read_committed/lock_snapshot_trace.json),
[`8886e730c` RC](captures/C6/8886e730c2f9-read_committed/lock_snapshot_trace.json),
[`7b465769` RR](captures/C6/7b465769dc87-repeatable_read/lock_snapshot_trace.json),
[`8886e730c` RR](captures/C6/8886e730c2f9-repeatable_read/lock_snapshot_trace.json)):

- The RC gate race now commits on attempt 2 at the default bound.
- Every other schedule is unchanged at each level, as tabulated in C0. That
  includes the RR fixed-revision command, which still spends a second attempt
  before failing its precondition.

**Guard replay at RR**
([`7b465769`](captures/C6/7b465769dc87-repeatable_read/guard_wal.json),
[`8886e730c`](captures/C6/8886e730c2f9-repeatable_read/guard_wal.json)):

- At the default bound, commits rise from 382 to 400 of 400. Attempts per
  success fall from 1.52 to 1.06, and p99 from 13.9 to 1.9 ms.
- At `max_retries=0` half the invocations still surface `40001`.
- RC stays at 400 of 400 on first attempts. WAL per write is unchanged.

**Stream churn**
([`7b465769` RC](captures/C6/7b465769dc87-read_committed/stream_churn.json),
[`8886e730c` RC](captures/C6/8886e730c2f9-read_committed/stream_churn.json),
[`7b465769` RR](captures/C6/7b465769dc87-repeatable_read/stream_churn.json),
[`8886e730c` RR](captures/C6/8886e730c2f9-repeatable_read/stream_churn.json)):

- The RR slow transaction-held stream still holds back cleanup:
  - oldest snapshot age p50 4,425 at `7b465769` and 3,818 at `8886e730c`;
  - 8,605 and 7,742 dead tuples at release;
  - a relation of 1,696 and 1,648 KiB and an 888 KiB index.
- RC stays at about 100 snapshot age, 257–260 dead tuples, and a 1,248 KiB
  relation.
- The lower final-head RR figures follow its fewer writer commits during the
  read: 7,783 against 8,736.
- The final design does not change the RR retention cost of a held stream.

**End-to-end writes**
([`7b465769` RC](captures/C6/7b465769dc87-read_committed/end_to_end_writes.json),
[`8886e730c` RC](captures/C6/8886e730c2f9-read_committed/end_to_end_writes.json),
[`7b465769` RR](captures/C6/7b465769dc87-repeatable_read/end_to_end_writes.json),
[`8886e730c` RR](captures/C6/8886e730c2f9-repeatable_read/end_to_end_writes.json)):

- Statements per invocation are unchanged.
- The median traced peak per invocation rose by 1.1–1.2 KB on every workflow
  at both levels, 4–9%. Net retention stayed within 1.5%.
- C2's arm A, `3850203e9`, already carried about 0.6 KB of that rise over C0.
  No checkpoint isolates the rest, because only C0, C2, and C6 run this
  driver.
- Latency differences are within noise.

**Delivery instrument** on CPython 3.14
([`7b465769` RC](captures/C6/7b465769dc87-read_committed/snapshot_delivery.json),
[`8886e730c` RC](captures/C6/8886e730c2f9-read_committed/snapshot_delivery.json)):

- Eager retained memory falls 21%, 40%, and 56%, and eager peak 11%, 23%, and
  36%, for conventional fan-out, the versioned document, and bitemporal
  current. These match C5.
- Its timings move in both directions by up to 94% between the RR arms, so
  they carry no signal.

## What these captures do not measure

- Python against MariaDB. No production MariaDB adapter exists, and the
  MariaDB evidence is the harness witnesses.
- The backoff at RR as a grid. C4 tuned at RC alone, and C6 shows the selected
  constants at RR only as one run.
- Locking-preference contention. Every contention invocation reads a versioned
  account under the Optimistic preference.
- A read-only transaction's native setup cost apart from its read delivery.
