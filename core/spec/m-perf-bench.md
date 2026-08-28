# m-perf-bench — Performance & Benchmark Harness

`m-perf-bench` is the **shared cross-language performance methodology**: a
normative set of **benchmark fixtures** (datasets, query mixes, deep-fetch
shapes, milestone workloads) plus a **measurement protocol** (what to measure, how
to report it), so implementations are **comparable**, not just individually fast.
Per the dependency graph, `m-perf-bench` depends on `m-conformance-adapter` (it
emits its report through the adapter's `benchmark` command) and, through it, reuses
the compatibility harness (`m-case-format`) provisioning seam, model descriptors,
and fixture format.

The thing `m-perf-bench` standardizes is **methodology, not data structures.**
Reladomo leans on specialized open-addressing collections (`UnifiedMap` /
`UnifiedSet`) and key-derived hashing (`HashingStrategy`) for cache/index footprint
and speed; those are *implementation details*, not contracts. The portable analogue
is a shared benchmark + shared measurement protocol with **per-language numeric
targets** — every implementation runs the same workloads under the same protocol
and reports against its own targets, so performance is comparable across runtimes
without forcing non-idiomatic structures.

## What is shared vs. per-language

| Concern | Status |
|---|---|
| benchmark fixtures (datasets, query mixes, deep-fetch shapes, milestone workloads) | **shared** (normative, this module) |
| measurement protocol (what metrics, how aggregated) | **shared** (normative, this module) |
| numeric targets (the actual latency / memory ceilings) | **per-language** (placeholders here; set in each language spec) |
| optional optimized data structures (`UnifiedMap` / `UnifiedSet` / `HashingStrategy` analogues) | **per-language**, optional technique |

> **Per-language targets are placeholders, by design.** A Rust target is not a
> Python target. Mandating one absolute number across runtimes would be unfair and
> easily gamed (DQ10). `m-perf-bench` mandates the *workloads and the measurement*,
> not the ceilings; each language spec fills in its own targets and may list the
> optional specialized-collection techniques it uses to hit them.

## Benchmark fixtures

A benchmark fixture is a YAML document under `core/compatibility/benchmarks/`. It
names a model descriptor, a dataset to load, and an ordered list of **workloads**
to measure. The shipped fixtures cover the five workload families the spec calls
out:

| Workload family | Statement shape its golden SQL is | Example fixture |
|---|---|---|
| **query mix** (point + range reads) | the point and range reads `m-predicate` / `m-sql` compile to, paired with the query-cache hit a caching target serves without one (`m-process-cache`) | `read-mix.yaml` |
| **deep-fetch shapes** (to-one, to-many, multi-hop) | `m-deep-fetch`'s N+1-eliminated fetch — `1 + levels` statements regardless of fan-out | `deep-fetch.yaml` |
| **streamed delivery** (one result at several page sizes) | `m-snapshot-read` streamed delivery — that same `1 + levels` shape once per page, and the page-size / round-trip trade | `stream.yaml` |
| **milestone workloads** (insert / update / terminate chains) | `m-txtime-write` milestone chaining — the close-and-chain write pair | `milestone-write.yaml` |
| **aggregation** (group-by / having) | the `m-agg` aggregate statement | folded into `read-mix.yaml` |

**What a fixture observes, in all five families.** A workload declares golden SQL
rather than an Object Query, so a run of it executes the AUTHORED statements. What
lands in the report is therefore the cost of the WORKLOAD against the database —
those statements, that dataset, and the round trips between them — rather than the
cost of a target's own path to them. That is what makes one number mean the same
thing in every language: the read a run issues is the fixture's rather than the
runtime's. It is equally what a benchmark does not observe, and the reason the
behavioral guarantees live in the compatibility corpus and in each target's own
gates instead.

One workload kind stands outside that account rather than qualifying it. A
`kind: cache-hit` workload declares NO statements, so a run of it executes
nothing and records zero round trips. That zero is the fixture's own declaration
of what a query-cache hit costs — the report's witness for `expectRoundTrips: 0`
— and not a reading of any cache, because no cache is consulted and no read is
issued.

A **streamed-delivery** workload is the deep-fetch family's paging counterpart,
and it declares the same kind of thing: the round-trip arithmetic a paged delivery
of one result owes. A delivery of `N` roots at page size `B` over `L` relationship
levels costs `floor(N / B) + 1` root statements and `ceil(N / B) x L` child
statements, and each workload's `expectRoundTrips` is that arithmetic evaluated at
its own page size.

What the family exports is that count and the page statements behind it — the
shape a conforming delivery of the result must produce. It exports no delivery: a
fixture here carries golden SQL and no Object Query, so a run of it executes those
page statements as authored and reports how many it issued. The adapter's
`benchmark` command carries each workload's `roundTrips` beside its
`expectRoundTrips`, and the two agreeing says the arithmetic this module states
and the statements the fixture authors are consistent with each other. It says
nothing about a target's delivery: the round-trip discipline of a real paged read
is settled by `m-snapshot-read`'s streamed-delivery cases against golden
statements. The family is a set of workloads over ONE result at several page sizes
rather than one workload, because what it makes comparable is the trade: the same
rows for fewer round trips and a larger per-page working set.

Each workload declares its golden SQL as an ordered list of `{sql, binds}`
**statement entries** (`statements`, per dialect, exactly like a compatibility
case's `then.statements` — each entry's `sql` is a dialect-keyed map and its
`binds` are authored inline) and an **`iterations`** count (how many times the
harness repeats it to gather a stable timing sample). A workload **MAY** declare an
**`expectRoundTrips`** count — the database round trips a run of its authored
statements issues. That count is arithmetic the fixture exports, and a run reports
the count it actually issued beside it through the adapter's `benchmark` command,
so the two agreeing is a consistency check between a fixture's arithmetic and its
own statement list rather than an observation of a target. A workload
**MAY** instead declare **`kind: cache-hit`** — the repeated find a caching
implementation serves at **zero** round trips (`expectRoundTrips: 0`), listing no
`statements` — so the query-mix fixture carries the hit's declared zero beside the
miss's measured cost rather than the miss alone. A run of one executes nothing.

### Dataset scale

Benchmark datasets are larger than the tiny correctness fixtures (which have a
handful of rows so `then.rows` is eyeball-verifiable). A benchmark fixture
declares a **`dataset`** — either inline rows or a **generated** dataset (a row
count + a generator recipe) — so the same workload can be measured at a meaningful
scale without hand-authoring thousands of rows. The reference harness ships a
small deterministic generator; the *shape* and *scale* are normative, the
generator implementation is not.

A dataset's rows are keyed by Entity exactly as a fixture document's are
(`m-case-format`): **canonical Entity spellings**, whether the rows are authored
inline or produced by a recipe.

A recipe names the Entities it fills by emitting their keys, so a generated
dataset declares a row count and a recipe and nothing else about which Entity it
builds. A recipe may fill several — the `orders-tree` shape fills three — so no
single Entity property could describe one honestly.

## Measurement protocol

For each workload the harness measures and reports:

- **wall-time percentiles** — `p50` and `p95` over the workload's iterations (a
  single mean hides tail latency; percentiles are the comparable metric);
- **database round trips** — the count of authored statements the run issued,
  reported beside the workload's declared count, so the statement cost of a
  workload sits in the report next to its timings rather than being left to the
  wall-clock figures alone. The two agreeing is a fixture-consistency check and
  not a target-conformance one: what makes `m-deep-fetch` / `m-unit-work`
  round-trip discipline binding is the compatibility corpus's golden statements;
- **memory** — **peak** and **steady** resident set over the run (cache/index
  footprint is a first-class cost for a cache-centric framework).

The protocol fixes *what* is measured and *how it is aggregated* (percentiles over
iterations; peak + steady memory); the *absolute* numbers are the per-language
targets. The harness emits a machine-readable **`report.json`** so runs are
diffable across languages and over time.

### The report

```jsonc
// report.json (shape)
{
  "generatedAt": "2026-06-27T00:00:00+00:00",
  "dialect": "postgres",
  "benchmarks": [
    {
      "fixture": "read-mix.yaml",
      "model": "models/orders.yaml",
      "datasetRows": 1000,
      "workloads": [
        { "name": "point-read", "iterations": 200,
          "wallTimeMs": { "p50": 0.4, "p95": 0.9 },
          "roundTrips": 1, "expectRoundTrips": 1, "roundTripsOk": true },
        { "name": "deep-fetch-1-N-N", "iterations": 50,
          "wallTimeMs": { "p50": 2.1, "p95": 4.0 },
          "roundTrips": 3, "expectRoundTrips": 3, "roundTripsOk": true }
      ]
    }
  ],
  "memory": { "peakBytes": 0, "steadyBytes": 0 }
}
```

The reference harness's job is to prove the **methodology runs end-to-end and
emits a well-formed report**; the numbers it records are reference figures, not
normative ceilings. A language implementation runs the same fixtures, records its
own numbers, and grades them against its own targets.

## Comparability and anti-gaming (DQ10)

The methodology is built to be *comparable across languages* and *not trivially
gameable*:

- **Same workloads, same data.** Every language runs the identical fixtures
  against the identical (deterministically generated) dataset at the identical
  scale, so a number means the same thing everywhere.
- **Round trips are declared, and a run reports its own.** A workload's
  `expectRoundTrips` is the count a run of its authored statements owes; the
  adapter's `benchmark` command carries the count the run issued beside it, and
  `roundTripsOk` is that comparison. What that buys is a legible trade: a
  wall-time figure read beside a statement count says whether a number moved by
  doing the work faster or by issuing different work, which a timing column alone
  cannot. What it is not is an observation of the implementation — a run executes
  the fixture's own statements, so `roundTripsOk` grades a fixture against its own
  report and no target's read is in it. The round-trip DISCIPLINE is a conformance
  property, settled against golden statements in the compatibility corpus and in
  each target's own gates, rather than one a benchmark decides.
- **Percentiles, not means.** Reporting `p50`/`p95` makes tail latency visible, so
  an implementation cannot hide a slow path behind a fast average.
- **Memory is reported alongside time.** A space/time trade is visible rather than
  hidden, so "fast but memory-blowing" is not a free win.

## Optional specialized-collection techniques

The per-language spec template lists, as **optional** techniques for hitting
targets, the specialized-collection analogues Reladomo uses:

- **open-addressing map/set** (`UnifiedMap` / `UnifiedSet` analogues) — lower
  per-entry overhead than chained hash tables for the identity/query caches;
- **key-derived hashing** (`HashingStrategy` analogue) — index domain objects by a
  *derived* (e.g. composite primary) key **without** allocating wrapper key
  objects, a significant footprint saving for large caches.

These are **optional** and **non-normative**: a language may hit its targets any
way it likes. They are enumerated so an implementer knows the proven levers exist.
