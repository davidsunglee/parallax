# Structural metadata evidence

The read and write cost evidence for the structural-metadata unification: the
protocol every capture under this directory follows, the frozen workload
manifest, what each window contains and excludes, and the limits of what the
measurements can show. `before/` is the clean pre-optimization baseline; a later
`after/` capture uses the same protocol, and every comparison between the two is
rendered by `tools/cost_report.py --compare`.

The portfolio under `before/` is the repository's canonical current cost
portfolio: the non-required `python-report-cost` CI job verifies it against the
checked-out head, and the database-free gate recomputes its Snapshot delivery
member's Budget Contract and workload-catalog digests from the committed inputs.
The historical captures under `../write-lowering-envelope/` and
`../snapshot-delivery-envelope/` keep their original names, protocols, and
producing commits; nothing here is compared against them, because their write
window stopped at `LoweredStatement` and their read matrix ran on one runtime.

## Protocol

Every reading is taken in a child interpreter of its own with `PYTHONHASHSEED=0`,
on every supported CPython minor (3.13 and 3.14), by `just python-report-cost`
on one runner with no competing measurement. A reading names its runtime and its
window; `cost_report.py --compare` pairs two readings only when their subject,
runtime, window, workload, cell, and unit all agree, lists every cell present on
one side alone, and refuses a pair whose unit differs.

Timing uses three warm-ups and nine measured samples per cell; the value is the
median and every sample is retained. A timing delta between two captures within
**5%** is read as noise (`cost_report.TIMING_NOISE_ALLOWANCE`) and a byte delta
within **3%** likewise (`cost_report.MEMORY_NOISE_ALLOWANCE`); count deltas are
exact. Both allowances come from a diagnostic trial of two identical quiet
write-member captures on the capture runner, taken before the baseline and not
part of it: 89 of 90 elapsed medians agreed within 5% and the last within 5.3%;
every high-water mark agreed within 1% and every retained checkpoint within
2.8%, in steps of a few dozen bytes; every pass observation agreed exactly. A
delta near either allowance is therefore weak evidence on its own.

`cost_report.py --verify` fails only for evidence that is not evidence: a
missing, malformed, or incomplete required member, a non-authoritative or dirty
capture, a stale workload digest, or members produced at different commits.
Everything else it has to say is an advisory line, printed and never an exit
status: a timing or memory ceiling exceeded, a streamed-memory arm grown past
its limit, a `uv.lock` that moved since the capture (`--freshness-only` reports
the same way), and a producing commit the inspected head no longer descends
from. Blocking memory gates are cost-class tests, not this verifier; a
dependency bump or a rebase changes nothing a reading measured; and the capture
budget above is why drift is stated rather than made a reason to capture again.

Retained checkpoints are taken separately from the uninterrupted timing and
high-water runs, each after 200 warm-up runs of its seam, at the production
stage the window names. A checkpoint counts bytes reachable at that point that
were not reachable before the seam began, so shared definitions and subtrees are
counted once. Checkpoint figures are not additive and never establish cumulative
allocation; the high-water mark is a net rise over the window's floor, not a
total of what the window allocated.

### Windows

| Window | Member | Contains | Excludes |
|---|---|---|---|
| `keyed-write` | write-lowering | Typed row serialization or the caller's Wire mapping; preparation; settlement; SQL lowering; production PostgreSQL bind adaptation; psycopg's own transformer dump of every bind, document binds included | database execution and network time |
| `predicate-acquisition` | write-lowering | a prepared Bitemporal `updateUntil` predicate; the resolving read's planning and compilation; row publication and materialization; per-row no-op selection; predecessor ownership establishment from freshly composed mutable rows; aligned column construction; buffering of the Materialized Write Group | ingress preparation, JSON parsing, the flush, and driver serialization — the transaction is abandoned after the checkpoint |
| `model-preparation` | write-lowering | one `prepare_model` over the whole structural write model: formation from the declared Entity Classes, layouts, row codec, graph construction, and write planner | the Entity Class declarations themselves, which are retained by the importing module |
| `live-delivery` | snapshot-delivery | a connected Wire find or stream against PostgreSQL, parsing included | nothing |
| `provider-free-delivery` | snapshot-delivery | a Wire find over already-parsed provider rows through production planning, materialization, and publication | parsing and provider work |
| `positional-materialization` | snapshot-delivery | the shipped raw-row conversion loop over prepared reads, to a finished Page | planning, statement execution, and publication |
| `read-plan-compilation` | snapshot-delivery | one whole-table instance read planned through `ReadPlanCache.plan` into an empty cache of production capacity: deep-fetch planning, `compile_read`, and the prepared level binding the cache then retains, which is the growth from an empty cache to one compiled entry | the cache itself, composed before the window as production composes it when a handle connects; model preparation and query validation (`preflight`), likewise composed once outside it; statement execution, materialization, and publication |

Retained checkpoints: `keyed-write` samples with the serialized rows, the
prepared instruction, the buffered item, and the settled plan alive, before
lowering; `predicate-acquisition` samples inside the transaction body with the
group buffered, before any flush; `model-preparation` samples with the prepared
selection alive; a geometry read samples with the delivered results alive;
`read-plan-compilation` samples with the already composed cache holding its one
entry and the rendered plan handle already dropped, which is what production
retains between two deliveries of the same query; the empty cache each sample
opens on is restored outside every measured region.

The read-plan window lives in the Snapshot member rather than beside the write
member's `model-preparation` window because it is read-side evidence over the
same geometry Entities the geometry read families deliver, it runs on the same
runtime matrix as every other Snapshot cell, and the Snapshot member's recorded
`workloadDigest` already covers its reading child and the frozen manifest, so
one digest names everything the cell depends on. The per-root delivery cells
keep their warmed steady-state meaning: a delivery reading's floor holds the
compiled plan its 200 warm-ups established, and this window prices that plan
separately.

### Live roots and lifetimes

The keyed-write source stays alive across the window as production keeps it: a
Typed case holds its instances in the fixture and serializes them inside the
window, and a Wire case holds its authored mapping in the fixture and hands it to
preparation. Neither is counted by a retained checkpoint, because both were
allocated before the window opened; what the checkpoint sees is what the window
built and production still reaches. The acquisition port composes each resolving
row when the statement runs and keeps none, and the handle is composed once per
reading outside the window, so the checkpoint sees the retained columns, the
retained encoded documents, and the buffered group rather than a fixture-held
second batch. The provider-free read port likewise composes each row per
statement.

## Workload manifest

Every identity and numeric level below is frozen in
`parallax.conformance.workloads` (`GEOMETRY_LEVELS`, `ACQUISITION_LEVELS`,
`ANCESTOR_LEVEL_IDS`, `READ_GEOMETRY_ROOTS`, `STRUCTURAL_LAYOUTS`) and enters the
write member's `workloadDigest` through `structural_digest()` together with the
bytes of the three fixture modules, and the Snapshot member's through
`workload_digest()` beside the catalog fixtures and models. Those digests name
what was measured; they deliberately do not name the instruments that measured
it. A capture costs about an hour of runner time and this work budgets exactly
two — the baseline under `before/` and the after-capture beside it — so no
instrument or harness edit made after a capture may force a third through a
hash. Whether two captures remain comparable across such an edit is a judgement
recorded in this README beside the captures, and where it is in doubt the
original producing revision can be reproduced on the final runner. The levels
were chosen from diagnostic trial runs on the capture runner and then frozen;
the trials are not part of the baseline.

### Categorical keyed writes — 20 cases per runtime

Each Entity carries a One Value Object (`address`) nesting a One (`geo`) and a
Many (`tags`, two elements) beside a primary key and a string leaf, under both
storage layouts. Every case writes one row.

| Family | Temporal profile | Operation | Predecessor evidence | Statements |
|---|---|---|---|---:|
| `txtime.opening` | Transaction-Time-Only | `insert` | none | 1 |
| `txtime.changed` | Transaction-Time-Only | `update`, every member changed | complete predecessor row; the retained document under Relational Document | 2 |
| `txtime.unchanged` | Transaction-Time-Only | `update` restating the predecessor exactly | as above | 2 |
| `plain.changed` | non-temporal, unversioned | `update`, every member changed | none | 1 |
| `bitemporal.interior` | Bitemporal | `updateUntil` over `[2026-03-01, 2026-09-01)`, strictly inside the predecessor's open Valid interval | complete predecessor row with both axes | 4: close, carried head, changed middle, carried tail |

Each family runs as Typed and Wire ingress under Columns and Relational Document
layout, twelve Transaction-Time-Only cases and eight others. The Typed and Wire
twins of a case lower to identical statements and binds, which the fixture
suite proves. Under Columns an unchanged successor still re-encodes each Value
Object column; unchanged content there is not evidence of Entity-document reuse.

### Geometry families — 9 levels, both flows, both layouts

Each level fixes one Value Object geometry: a root One occurrence (`body`)
chained `depth` levels deep through `next`, a Many occurrence (`items`) of
`many` elements, `width` nullable string leaves per occurrence, and `populated`
leaves carried by every authored occurrence (fixed-width `NNN-KKKKKKKK`
strings). The shallow baseline is depth 1, two elements, four leaves, all
populated; every other level varies one dimension.

| Level | Family | depth | many | width | populated |
|---|---|---:|---:|---:|---:|
| `depth-1` | depth (also the small/shallow baseline) | 1 | 2 | 4 | 4 |
| `depth-4` | depth | 4 | 2 | 4 | 4 |
| `depth-8` | depth | 8 | 2 | 4 | 4 |
| `many-0` | many | 1 | 0 | 4 | 4 |
| `many-8` | many | 1 | 8 | 4 | 4 |
| `many-32` | many | 1 | 32 | 4 | 4 |
| `width-16` | width | 1 | 2 | 16 | 16 |
| `width-64` | width | 1 | 2 | 64 | 64 |
| `sparse-64` | sparsity (sparse/wide) | 1 | 2 | 64 | 1 |

The write side inserts one Typed row per level and layout
(`geometry.<level>.<layout>.typed`, `keyed-write` window). The read side
materializes 32 stored rows per level and layout through a provider-free Wire
find (`read-<level>`, cells `<layout>.elapsedUsPerRoot`, `<layout>.peakKiB`,
`<layout>.retainedKiB`, `provider-free-delivery` window). No level declares a
Json leaf: no class annotation denotes one, so Json-leaf payload size is not a
dimension of these families. Every stored row conforms, so malformed-read
evidence volume is not measured here either; both are limits stated below.

### Changed-ancestor widths — 4 levels, both layouts

The geometry levels above open a lineage. `depth-1`, `width-16`, `width-64`, and
`sparse-64` (`workloads.ANCESTOR_LEVEL_IDS`) are measured a second time as a
changed successor: a Transaction-Time-Only twin of the same geometry, written as
an `update` that restates every member and changes the first leaf of the root
occurrence (`ancestor.<level>.<layout>.typed`, two statements, `keyed-write`
window, Typed ingress). What the successor's Structured Column costs is then
read against the root occurrence's declared width rather than inferred from
depth and Many cardinality: the three widths are 4, 16, and 64, and `sparse-64`
holds the declared width at 64 while the change carries one populated leaf, so
the width of the replaced ancestor is separated from the payload that replaced
it. The predecessor and successor carry the same fixed-width leaves, so the two
differ in one value and in nothing a measurement reads as size.

### Read-plan compilation — 3 levels, both layouts

The whole-table instance read of `depth-1`, `depth-8`, and `width-64`
(`PLAN_LEVEL_IDS`) is compiled into an empty `ReadPlanCache` under each layout
(`plan-<level>`, cells `<layout>.elapsedUs`, `<layout>.peakKiB`,
`<layout>.retainedKiB`, `read-plan-compilation` window). The shallow baseline,
the deepest chain, and the widest occurrence are the structures a compiled plan
could differ over; sparsity and Many cardinality are stored-data properties and
add nothing a plan retains. Elapsed and peak are one compilation on a fresh
empty cache per sample; retained is the checkpoint above.

### Predicate-acquisition families — 3 levels per layout

A Bitemporal Entity with the categorical Value Object shape, under each layout.
The prepared predicate is `id >= 1` with `title` assigned to a value every
resolved row differs from, over the interior window above, so no-op elimination
retains every row. Levels resolve 8, 32, and 128 current milestones
(`acquisition.rows-<n>.<layout>`, per-row units). This companion measures the
converged prepared-predicate path once per layout and does not multiply ingress
forms.

### Preserved delivery workloads

The Budget Contract's `conventional-fanout`, `duplicate-include`,
`document-heavy`, `versioned-document`, and `bitemporal-current` delivery cells
and the `stress-columns` / `stress-document` positional-materialization cells run
unchanged, now on both supported minors; the contract's ceilings are compared on
the authority runtime alone, and the other runtime's readings stand beside them
without comparisons.

### Model and declaration retention

`model.prepared` prices one preparation of the complete structural write model:
the six categorical Entities, the ten geometry Entities and their six
changed-ancestor twins, and the two acquisition Entities. The Entity Class declarations and their Value Object classes are
retained by the fixture modules and are outside every window.

## Limits

- A retained checkpoint is a graph reachable at one point; a high-water mark is a
  net rise over one floor. Neither is cumulative allocation, and a duplicate
  traversal that allocates and frees inside a window need not move either.
- Pass observations (`calls.*`) count returns of named document-codec functions
  per row over the keyed-write window. They are diagnostics with units that
  distinguish roots, nested values, and repeated calls; they gate nothing.
- Timing is machine- and interpreter-relative and is compared only between
  captures taken on the same runner with the same protocol.
- Json-leaf payload size and malformed-read evidence volume are not dimensions
  of any family here.
- The acquisition window abandons its transaction after the checkpoint, so the
  cost of the flush that would follow is measured only by the keyed-write cases.
- The read-plan window compiles on a cache of production capacity that holds
  nothing else, so it prices one entry, never eviction or family reuse across
  entries; and it plans one query shape per level, the whole-table instance
  read, so a plan with includes or paging is not measured here. What the cache
shell itself costs is outside all three of its cells, because production pays it
once when a handle connects rather than per delivery.

## Diagnostic runs

`cost_report.py --diagnostic` takes readings for a chosen subset — one or both
required members (`--member`), workloads or cases by shell pattern (`--select`),
and runtimes (`--runtime`) — through the same reading children and windows the
capture uses, and writes each member's answer as `diagnostic-<subject>.json`
(or prints it), never into the directory a committed capture lives in. The
member scripts accept the same subset directly
(`snapshot_delivery_overhead.py --diagnostic --select … --cell … --runtime …`,
`write_lowering_overhead.py --diagnostic --case … --runtime …`) and print it;
`--out` is refused with `--diagnostic`, so no member run can put a diagnostic
document at an evidence path. A diagnostic
document is readings alone: it carries `diagnostic: true`, no provenance, no
comparisons, and is not an envelope, so `validate` refuses it, `--verify`
refuses any document that is or contains one, and it can never be retained as
a capture. Without `--diagnostic` every one of those options is refused and the
capture path runs exactly as documented above.

## Baseline capture — `before/`

> **Superseded pending recapture.** The capture below predates the
> changed-ancestor family and the read-plan compilation window, so it is no
> longer a complete capture of the manifest above and both members' recorded
> `workloadDigest` values disagree with the frozen manifest. Its measured values
> remain the readings that commit produced and are not rewritten; `--verify`
> reports the stale digests until the one recapture replaces this directory.
> Nothing here is a comparison base until then.

Produced from clean commit `572fa9441765` (`feat(cost): measure structural read
and write windows on every minor`) by `uv run --project languages/python python
languages/python/tools/cost_report.py --out /tmp/cor-158-before`, 2026-09-16
13:42–14:43 EDT, on Mac17,4 (Apple M5, 10 cores, 32 GiB, macOS 26.6.2) with
CPython 3.14.7 and 3.13.15 and PostgreSQL 18.6 (`postgres:18.6-alpine` through
Testcontainers), then retained here unchanged. The Snapshot delivery member is
`authoritative`; the other three are `non-authoritative` because their sampling
protocols are their own. Every member's `uv.lock` digest matches the capture
checkout.

| Member | Authority | Runtimes | Readings | Within | Outside |
|---|---|---|---:|---:|---:|
| snapshot-delivery | authoritative | 3.13, 3.14 | 288 | 83 | 7 |
| lifecycle-overhead | non-authoritative | 3.14 | 87 | 2 | 13 |
| instance-state | non-authoritative | 3.13, 3.14 | 624 | 4 | 4 |
| write-lowering | non-authoritative | 3.13, 3.14 | 802 | — | — |

`cost_report.py --verify before/portfolio.json` reports one failure and seven
advisories, all pre-existing in the historical `db56a19e` portfolio and none a
consequence of this ticket: `document-heavy.streamedMemory.page128PeakKiB` grows
37.69 KiB between the 200- and 2000-root arms against the 16 KiB limit (37.79
KiB historically), and the timing ceilings of
`duplicate-include.providerFreeCpu.eager` (`maxMs`, `minRootsPerSecond`),
`document-heavy.live.eager` (both), `versioned-document.live.page32` (both),
and `versioned-document.live.page128.minRootsPerSecond` are exceeded on the
authority runtime by 1–9%. No limit was relaxed to obtain this capture: the
growth failure is recorded as an outcome.

### Keyed writes per row (`keyed-write` window)

Median of nine samples; retained is one checkpoint after 200 warm-ups. Pass
observations are per row on either runtime (they agree exactly).

| Case | 3.13 µs | 3.13 peak B | 3.13 retained B | 3.14 µs | 3.14 peak B | 3.14 retained B | encodeDocument / encodeMany / applyPatches / detachJsonContainer |
|---|---:|---:|---:|---:|---:|---:|---|
| txtime.opening.columns.typed | 160.8 | 13186 | 3618 | 180.6 | 13698 | 3624 | 4 / 1 / 0 / 2 |
| txtime.opening.columns.wire | 158.0 | 12082 | 2612 | 171.2 | 12634 | 2610 | 4 / 1 / 0 / 2 |
| txtime.opening.document.typed | 177.9 | 13186 | 3618 | 190.8 | 13698 | 3624 | 5 / 1 / 0 / 11 |
| txtime.opening.document.wire | 149.0 | 12082 | 2562 | 171.5 | 12634 | 2610 | 5 / 1 / 0 / 11 |
| txtime.changed.columns.typed | 186.5 | 12767 | 4584 | 211.8 | 12919 | 4780 | 4 / 1 / 0 / 2 |
| txtime.changed.columns.wire | 185.6 | 11695 | 3610 | 191.6 | 11883 | 3648 | 4 / 1 / 0 / 2 |
| txtime.changed.document.typed | 204.8 | 13522 | 4634 | 223.8 | 13794 | 4730 | 4 / 1 / 1 / 22 |
| txtime.changed.document.wire | 193.3 | 12450 | 3610 | 208.9 | 12758 | 3648 | 4 / 1 / 1 / 22 |
| txtime.unchanged.columns.typed | 198.4 | 12761 | 4634 | 213.6 | 12913 | 4680 | 4 / 1 / 0 / 2 |
| txtime.unchanged.columns.wire | 201.9 | 11689 | 3560 | 201.8 | 11885 | 3698 | 4 / 1 / 0 / 2 |
| txtime.unchanged.document.typed | 198.2 | 13037 | 4684 | 220.5 | 13309 | 4730 | 2 / 1 / 1 / 16 |
| txtime.unchanged.document.wire | 189.0 | 11957 | 3610 | 201.7 | 12265 | 3748 | 2 / 1 / 1 / 16 |
| plain.changed.columns.typed | 159.9 | 12914 | 3848 | 171.9 | 13474 | 3936 | 4 / 1 / 0 / 2 |
| plain.changed.columns.wire | 158.2 | 11842 | 2824 | 163.2 | 12438 | 2904 | 4 / 1 / 0 / 2 |
| plain.changed.document.typed | 160.4 | 12914 | 3898 | 178.6 | 13474 | 3986 | 4 / 1 / 0 / 2 |
| plain.changed.document.wire | 143.2 | 11842 | 2824 | 163.0 | 12438 | 2904 | 4 / 1 / 0 / 2 |
| bitemporal.interior.columns.typed | 322.3 | 17612 | 6520 | 323.2 | 17062 | 6782 | 12 / 3 / 0 / 6 |
| bitemporal.interior.columns.wire | 301.6 | 16664 | 5592 | 303.7 | 16208 | 5796 | 12 / 3 / 0 / 6 |
| bitemporal.interior.document.typed | 302.0 | 18733 | 6520 | 351.8 | 17973 | 6682 | 4 / 1 / 1 / 44 |
| bitemporal.interior.document.wire | 287.5 | 17787 | 5592 | 313.5 | 17273 | 5796 | 4 / 1 / 1 / 44 |

An unchanged-document successor costs what a changed one costs under either
layout: the retained predecessor document is detached whole rather than reused,
which the sixteen `detachJsonContainer` returns per row make visible.

### Geometry inserts per row (`keyed-write` window, Typed)

| Level | Layout | 3.13 µs | 3.13 peak B | 3.13 retained B | 3.14 µs | 3.14 peak B | 3.14 retained B | encodeDocument / detachJsonContainer |
|---|---|---:|---:|---:|---:|---:|---:|---|
| depth-1 | columns | 156.7 | 12154 | 3162 | 170.0 | 12618 | 3168 | 3 / 0 |
| depth-1 | document | 158.8 | 12154 | 3112 | 181.4 | 12618 | 3168 | 4 / 16 |
| depth-4 | columns | 226.0 | 14546 | 4336 | 236.6 | 15106 | 4392 | 6 / 30 |
| depth-4 | document | 221.1 | 14546 | 4336 | 228.7 | 15106 | 4392 | 7 / 61 |
| depth-8 | columns | 266.5 | 18448 | 5968 | 293.0 | 19202 | 6024 | 10 / 140 |
| depth-8 | document | 275.3 | 18498 | 5918 | 302.0 | 19202 | 6074 | 11 / 191 |
| many-0 | columns | 138.9 | 11130 | 2208 | 146.0 | 11586 | 2306 | 1 / 0 |
| many-0 | document | 133.5 | 11130 | 2208 | 147.7 | 11586 | 2306 | 2 / 6 |
| many-8 | columns | 221.3 | 14682 | 5690 | 233.0 | 15146 | 5696 | 9 / 0 |
| many-8 | document | 280.7 | 15117 | 5590 | 250.0 | 15469 | 5696 | 10 / 46 |
| many-32 | columns | 534.1 | 38074 | 15816 | 491.7 | 38418 | 15822 | 33 / 0 |
| many-32 | document | 532.1 | 38637 | 15816 | 507.4 | 38989 | 15822 | 34 / 166 |
| width-16 | columns | 239.1 | 13834 | 4792 | 261.6 | 14298 | 4898 | 3 / 0 |
| width-16 | document | 263.3 | 13834 | 4792 | 356.1 | 14298 | 4798 | 4 / 52 |
| width-64 | columns | 563.7 | 29130 | 11512 | 971.2 | 29466 | 11518 | 3 / 0 |
| width-64 | document | 578.9 | 30234 | 11512 | 920.2 | 30578 | 11568 | 4 / 196 |
| sparse-64 | columns | 202.8 | 12034 | 3112 | 351.1 | 12498 | 3218 | 3 / 0 |
| sparse-64 | document | 214.3 | 12034 | 3112 | 316.8 | 12498 | 3218 | 4 / 7 |

Retained bytes at the settled checkpoint are the same under both layouts at
every level, as the managed representation is layout-independent. The wide and
sparse levels run substantially slower on 3.14 than on 3.13 (up to 1.7x at
`width-64`); the difference sits in the Typed ingress of a wide instance and is
recorded as an observation, not attributed.

### Predicate acquisition per resolved row (`predicate-acquisition` window)

| Case | 3.13 µs | 3.13 peak B | 3.13 retained B | 3.14 µs | 3.14 peak B | 3.14 retained B |
|---|---:|---:|---:|---:|---:|---:|
| acquisition.rows-8.columns | 72.1 | 5930 | 2368 | 101.7 | 6181 | 2577 |
| acquisition.rows-32.columns | 51.6 | 4060 | 1736 | 73.3 | 4248 | 1810 |
| acquisition.rows-128.columns | 48.6 | 3531 | 1582 | 50.9 | 3673 | 1617 |
| acquisition.rows-8.document | 75.6 | 7942 | 3581 | 79.5 | 8289 | 3789 |
| acquisition.rows-32.document | 58.0 | 6214 | 2922 | 59.4 | 6394 | 3005 |
| acquisition.rows-128.document | 51.0 | 5685 | 2767 | 57.3 | 5833 | 2811 |

Per-row figures fall with row count as the read's fixed planning and
compilation cost is amortized; the difference between the layouts is the retained
raw Structured Column document each Relational Document row carries beside its
decoded members.

### Model preparation (`model-preparation` window)

| Runtime | µs | peak B | retained B |
|---|---:|---:|---:|
| 3.13 | 3228.6 | 445192 | 430880 |
| 3.14 | 3277.6 | 447480 | 440280 |

### Geometry reads (`provider-free-delivery` window, 32 roots)

| Level | Layout | 3.13 µs/root | 3.13 peak KiB | 3.13 retained KiB | 3.14 µs/root | 3.14 peak KiB | 3.14 retained KiB |
|---|---|---:|---:|---:|---:|---:|---:|
| depth-1 | columns | 30.88 | 108.7 | 50.8 | 34.98 | 106.2 | 51.1 |
| depth-1 | document | 35.46 | 108.7 | 50.8 | 33.97 | 106.1 | 51.1 |
| depth-4 | columns | 59.25 | 154.3 | 88.0 | 57.57 | 155.1 | 88.2 |
| depth-4 | document | 52.33 | 153.7 | 88.0 | 56.73 | 153.6 | 88.2 |
| depth-8 | columns | 90.67 | 222.8 | 137.5 | 93.82 | 225.7 | 137.7 |
| depth-8 | document | 96.10 | 220.8 | 137.5 | 93.88 | 223.6 | 137.7 |
| many-0 | columns | 21.58 | 67.2 | 24.1 | 23.90 | 65.8 | 24.3 |
| many-0 | document | 21.20 | 73.0 | 24.1 | 22.47 | 71.5 | 24.3 |
| many-8 | columns | 55.94 | 205.0 | 125.1 | 59.14 | 208.0 | 125.3 |
| many-8 | document | 66.90 | 203.5 | 125.1 | 58.30 | 206.8 | 125.3 |
| many-32 | columns | 150.16 | 636.2 | 428.1 | 169.10 | 640.2 | 428.3 |
| many-32 | document | 152.16 | 633.8 | 428.1 | 159.83 | 637.9 | 428.3 |
| width-16 | columns | 52.64 | 220.5 | 136.7 | 59.09 | 223.9 | 137.0 |
| width-16 | document | 53.47 | 223.9 | 136.7 | 61.25 | 227.2 | 137.0 |
| width-64 | columns | 149.07 | 766.9 | 480.2 | 160.31 | 770.3 | 480.5 |
| width-64 | document | 155.05 | 770.4 | 480.2 | 163.81 | 773.6 | 480.5 |
| sparse-64 | columns | 47.12 | 139.0 | 35.9 | 48.58 | 136.4 | 36.2 |
| sparse-64 | document | 45.03 | 139.0 | 35.9 | 47.94 | 136.4 | 36.2 |

The retained page grows with the expanded positional output rather than with
the authored input: `sparse-64` retains 36 KiB for 32 roots carrying one
populated leaf each, against 24 KiB at `many-0`, because every declared
position is materialized.

### Preserved positional-materialization cells (authority runtime)

`stress-columns`: 7.5 µs/projection, 604.4 retained B/projection, 128.0
transient B/projection, 45.8 KiB peak for 64 KiB, 41.4 KiB prepared set.
`stress-document`: 10.4 µs/projection, 620.4 retained B/projection, 192.0
transient B/projection, 50.8 KiB peak for 64 KiB, 65.6 KiB prepared set. Every
delivery and stress ceiling other than the seven timing cells and the one
scaling arm named above is within its limit.
