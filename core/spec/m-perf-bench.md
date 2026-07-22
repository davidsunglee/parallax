# m-perf-bench — Performance & Benchmark Harness

`m-perf-bench` is the **shared cross-language performance methodology**: a
normative set of **benchmark fixtures** (datasets, operation mixes, deep-fetch
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
| benchmark fixtures (datasets, op mixes, deep-fetch shapes, milestone workloads) | **shared** (normative, this module) |
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
to measure. The shipped fixtures cover the four workload families the spec calls
out:

| Workload family | Exercises | Example fixture |
|---|---|---|
| **operation mix** (point + range reads) | `m-op-algebra` / `m-sql` predicate evaluation, query-cache hit/miss (`m-process-cache`) | `read-mix.yaml` |
| **deep-fetch shapes** (to-one, to-many, multi-hop) | `m-deep-fetch` N+1 elimination — round-trips must stay `1 + levels` regardless of fan-out | `deep-fetch.yaml` |
| **milestone workloads** (insert / update / terminate chains) | `m-txtime-write` milestone-chaining write cost | `milestone-write.yaml` |
| **aggregation** (group-by / having) | `m-agg` aggregate path | folded into `read-mix.yaml` |

Each workload declares its golden SQL as an ordered list of `{sql, binds}`
**statement entries** (`statements`, per dialect, exactly like a compatibility
case's `then.statements` — each entry's `sql` is a dialect-keyed map and its
`binds` are authored inline) and an **`iterations`** count (how many times the
harness repeats it to gather a stable timing sample). A workload **MAY** declare an
**`expectRoundTrips`** count — the database round trips it should cost — so the
benchmark doubles as a *round-trip regression check* (a deep-fetch workload that
silently regressed to N+1 would blow its declared round-trip count). A workload
**MAY** instead declare **`kind: cache-hit`** — a repeated find an implementation
serves from its query cache at **zero** round trips (`expectRoundTrips: 0`),
listing no `statements` — so the operation-mix fixture measures the query-cache
hit/miss distinction, not only the miss.

### Dataset scale

Benchmark datasets are larger than the tiny correctness fixtures (which have a
handful of rows so `then.rows` is eyeball-verifiable). A benchmark fixture
declares a **`dataset`** — either inline rows or a **generated** dataset (a row
count + a generator recipe) — so the same workload can be measured at a meaningful
scale without hand-authoring thousands of rows. The reference harness ships a
small deterministic generator; the *shape* and *scale* are normative, the
generator implementation is not.

## Measurement protocol

For each workload the harness measures and reports:

- **wall-time percentiles** — `p50` and `p95` over the workload's iterations (a
  single mean hides tail latency; percentiles are the comparable metric);
- **database round trips** — the count of statements actually issued (the
  round-trip discipline that `m-deep-fetch` / `m-unit-work` guarantee, measured
  rather than asserted);
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
- **Round trips are measured, not assumed.** A workload's `expectRoundTrips`
  catches an implementation that "got faster" by quietly breaking the N+1 or
  cache-hit guarantee — the round-trip count would diverge from the declared one,
  failing the check even if wall-time improved.
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
