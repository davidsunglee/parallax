# Snapshot materialization — recorded baseline

What a production Snapshot read spends turning returned rows into a sealed graph,
and what that costs in memory, measured on one machine under stated conditions,
under both storage layouts and on both supported CPython minors. COR-137 asks for
a reviewed baseline before any optimization, and for every later change to be
measured against it. Both halves are recorded here: the "before" half is the
shipped path as it stood at `431936be`, and the "after" half is the same path
with the per-row work whose inputs a compiled read already fixed removed.

Nothing here gates. `just python-report-snapshot-materialization` is a `report`:
it passes no verdict and belongs to no aggregate, because elapsed time is a
property of the machine that ran it — every CI job runs the floating
`ubuntu-latest` label — and a total in bytes is machine- and interpreter-relative,
since `tracemalloc` figures move with CPython. The *shape* of the claim is gated
instead, in `tests/unit/test_snapshot_materialization_scaling.py`, which the
`cost` class owns and CI runs on every change: it asserts that what preparation
holds is fixed by the model's exact Entity layouts and by the compiled reads,
across eight rows against sixty-four through one prepared read and one execution
against sixty-four against one prepared selection. Two readings carry that. One is
an exact equality over what each prepared structure reaches — every object it
reaches without crossing into another, and every reference between them. The other
is what every Python object in the process weighs at each end of a marked region
handed rows this process has never decoded, which must not rise; that is where a
container no prepared structure reaches at all shows up. A region rather than a
second arm because a cache keyed by what a row holds stops growing once the same
rows come back, so two arms compared in one process would both read it already
full. Neither reading is a `tracemalloc` figure, which is what leaves both of them
exact where a total in bytes allocated would need a tolerance.

## What the reading does not prove

Stated so a reader takes the figures for what they are. None of these is a known
defect; each is a shape the instrument cannot see.

**Wall clock.** One machine's readings, not a reproducible measurement. Every
timing here is recorded for direction only, and comparing one against a reading
taken elsewhere compares two machines.

**Anything a database does.** SQL execution, connection acquisition, and the
driver's own row materialization are outside every window by construction — the
rows are synthesized. What is measured begins after rows have returned, which is
the boundary COR-137 draws.

**Invalid stored data.** Every row in the batch is conforming. Missing, null,
wrong-kind, noncanonical, and undecodable values remain correctness cases, and
their cost is deliberately not in this mix.

**A cost per row that is really a cost per batch.** The batch is a fixed 64 rows,
so a fixed per-batch cost divides into the per-row figures. What separates the two
is the scaling regression, not this reading.

**`Json` as a declared Neutral Type.** No Python annotation denotes it, so a
class-backed model cannot declare one and the workload reaches every *declarable*
type and no more: `Boolean`, `Int32`, `Int64`, `Float32`, `Float64`, `String`,
`Decimal`, `Bytes`, `Date`, `Time`, `Timestamp`, `Uuid`.

**A holder whose entry count is fixed by the model.** Both gated readings are
sizes: an equality between two arms, and a refusal to rise across one region. Both
therefore see growth along rows, graphs, and executions — which is the whole of
what COR-137 asks — and neither separates a holder that grows along none of them
from state the model legitimately owns. One query shape banked once and shared by
every execution after it leaves both execution arms holding one. A decode memo
bounded by a value domain fills during warming only where warming covered that
domain: `Boolean` has two values and both are decoded before any reading, while
the wider modular domains are sampled rather than exhausted, so a memo over one
of those would take entries inside the region and fail that reading. That such
holders do not exist is a structural property of the code that would own them,
asserted where that code is, and outside what a measurement of size can say.

**A byte equality over a window that runs the codec.** Two runs of one identical
seam read about four hundred bytes apart on a forty-kilobyte window, in either
direction, after eight hundred warm-up batches: the interpreter's own `datetime`
formatting leaves a slowly saturating residue behind the `Timestamp` leg of the
canonical Wire codec. That is why the byte totals below are reported and the gated
regression asserts structure instead. The neighbouring 64-graph cost item still
asserts bytes because its workload declares four Neutral Types and reaches none of
that leg.

**A profiled share as a share of real time.** `cProfile` charges its own per-call
bookkeeping to every call, so a leg reached tens of times per row reads larger
under the profiler than it costs untraced — the profiled batch runs about 3.7×
the untraced one. The codec figures below are therefore stated twice: once as a
profiled cumulative share, and once as an untraced ablation, which is the reading
to trust for magnitude.

## The figure

Per-row steady state, from an already prepared model and compiled read. One
recorded run per half; see the conditions table for what a second run moved.

CPython 3.13:

| | Columns before | Columns after | Δ | Document before | Document after | Δ |
|---|---:|---:|---:|---:|---:|---:|
| Batch, 64 rows (ms) | 22.699 | 19.251 | −15.2% | 25.032 | 23.439 | −6.4% |
| **Rows per second** | **2,819** | **3,324** | **+17.9%** | **2,557** | **2,731** | **+6.8%** |
| **Microseconds per row** | **354.7** | **300.8** | **−15.2%** | **391.1** | **366.2** | **−6.4%** |
| Model preparation (ms) | 0.178 | 0.179 | — | 0.182 | 0.177 | — |
| — decode preparation within it | 0 | 0 | — | 0 | 0 | — |
| Compiled-read preparation (ms) | 0.381 | 0.462 | +0.081 | 0.447 | 0.473 | +0.026 |
| — decode preparation within it (`bind`) | 0 | 0.014 | +0.014 | 0 | 0.014 | +0.014 |

CPython 3.14:

| | Columns before | Columns after | Δ | Document before | Document after | Δ |
|---|---:|---:|---:|---:|---:|---:|
| Batch, 64 rows (ms) | 22.802 | 19.650 | −13.8% | 25.346 | 23.896 | −5.7% |
| **Rows per second** | **2,807** | **3,257** | **+16.0%** | **2,525** | **2,678** | **+6.1%** |
| **Microseconds per row** | **356.3** | **307.0** | **−13.8%** | **396.0** | **373.4** | **−5.7%** |
| Model preparation (ms) | 0.185 | 0.184 | — | 0.199 | 0.181 | — |
| — decode preparation within it | 0 | 0 | — | 0 | 0 | — |
| Compiled-read preparation (ms) | 0.384 | 0.459 | +0.075 | 0.451 | 0.474 | +0.023 |
| — decode preparation within it (`bind`) | 0 | 0.014 | +0.014 | 0 | 0.014 | +0.014 |

**Model preparation is untouched on both sides**, which is this reading's own
control: nothing in this work reaches `prepare_model`, so a matrix whose model
preparation moved was taken on a busy machine and was discarded. Decode
preparation inside model preparation stays zero, and is a statement about
ownership rather than a figure that was not taken: every fact this work
pre-resolves is projection-specific, so it belongs to the compiled read and is
reported there.

**`bind` is what the compiled read now owns**, and it is the whole of the decode
preparation any stage of this path pays: 14 to 16 µs per execution for the five-level
plan, about 3% of compiled-read preparation and about one row of steady-state
work.

## What preparation costs, and when it repays

The one-time cost this work added is compiled-read preparation; the recurring
saving is per row.

| | 3.13 Columns | 3.13 Document | 3.14 Columns | 3.14 Document |
|---|---:|---:|---:|---:|
| Preparation added, per execution (µs) | 81 | 26 | 75 | 23 |
| Time saved, per row (µs) | 53.9 | 24.9 | 49.3 | 22.6 |
| **Rows that repay it** | **2** | **2** | **2** | **2** |
| Prepared bytes added, per execution | 28,320 | 16,448 | 28,976 | 16,856 |
| Transient bytes saved, per row | 341 | 43 | 1 | 38 |
| **Rows that repay that** | **83** | **383** | — | **444** |

The time half repays inside two rows on every cell, which is the same order the
"before" half already recorded for preparation as a whole (one whole preparation
cost about two rows then and still does).

The byte half is the honest awkward figure. Read as a running total — every
prepared byte held against every transient byte a row no longer allocates — one
execution of this workload converts 64 rows and repays the prepared cost on no
cell at all, 3.13 `Columns` coming nearest at 83 rows; and on 3.14 `Columns` the
per-row transient saving is inside this reading's own spread (the two "after"
runs read 3,826 and 3,824 B/row against 3,827 before), so no row count can be
stated for it. Two things make that comparison narrower than it looks. Prepared
state is discarded with the execution that built it, exactly as the transient
bytes are, so what actually competes is concurrent bytes rather than a fixed cost
against a running saving — and **peak traced bytes fell on all four cells**, by
4.6% on 3.13 `Columns`, 0.5% on both `Document` cells, and a flat 0.1% on 3.14
`Columns`. And transient per row is peak-derived: a container
allocated and freed inside one row never raises the batch's high-water mark, so
the five per-row containers this work removed are legible in the call-count table
and not necessarily here.

## Memory

Over the same batch.

CPython 3.13:

| | Columns before | Columns after | Δ | Document before | Document after | Δ |
|---|---:|---:|---:|---:|---:|---:|
| **Retained graph bytes per projection** | **2,631.8** | **2,662.0** | **+1.1%** | **3,024.8** | **3,029.9** | **+0.2%** |
| Retained graph bytes, 64 projections | 168,434 | 170,368 | +1,934 | 193,584 | 193,915 | +331 |
| Peak traced bytes above the collected floor | 432,113 | 412,225 | −4.6% | 436,129 | 433,744 | −0.5% |
| **Transient bytes per row** | **4,120** | **3,779** | **−8.3%** | **3,790** | **3,747** | **−1.1%** |
| Prepared bytes, whole compiled read set | 14,116 | 42,436 | +28,320 | 38,446 | 54,894 | +16,448 |
| Prepared bytes per compiled read | 3,529 | 10,609 | +7,080 | 9,612 | 13,724 | +4,112 |
| — the levels `bind` holds, within it | 0 | 2,600 | +2,600 | 0 | 2,600 | +2,600 |
| **Prepared decode state per exact Entity layout** | **0** | **0** | **0** | **0** | **0** | **0** |
| Layout catalog bytes per exact Entity layout | 4,965 | 4,965 | 0 | 4,965 | 4,965 | 0 |
| One exact layout: tracked objects / references | 223 / 986 | 223 / 986 | 0 | 223 / 986 | 223 / 986 | 0 |

CPython 3.14:

| | Columns before | Columns after | Δ | Document before | Document after | Δ |
|---|---:|---:|---:|---:|---:|---:|
| **Retained graph bytes per projection** | **2,765.0** | **2,762.4** | **−0.1%** | **3,137.2** | **3,143.9** | **+0.2%** |
| Retained graph bytes, 64 projections | 176,957 | 176,792 | −165 | 200,782 | 201,211 | +429 |
| Peak traced bytes above the collected floor | 421,894 | 421,660 | −0.1% | 445,725 | 443,688 | −0.5% |
| **Transient bytes per row** | **3,827** | **3,826** | **−0.0%** | **3,827** | **3,789** | **−1.0%** |
| Prepared bytes, whole compiled read set | 14,516 | 43,492 | +28,976 | 39,686 | 56,542 | +16,856 |
| Prepared bytes per compiled read | 3,629 | 10,873 | +7,244 | 9,922 | 14,136 | +4,214 |
| — the levels `bind` holds, within it | 0 | 2,658 | +2,658 | 0 | 2,658 | +2,658 |
| **Prepared decode state per exact Entity layout** | **0** | **0** | **0** | **0** | **0** | **0** |
| Layout catalog bytes per exact Entity layout | 5,072 | 5,072 | 0 | 5,072 | 5,072 | 0 |
| One exact layout: tracked objects / references | 222 / 986 | 222 / 986 | 0 | 222 / 986 | 222 / 986 | 0 |

**Prepared decode state per exact Entity layout is zero on both sides**, and the
layout catalog is unchanged to the byte and to the reference. Every fact this
work pre-resolved is projection-aligned — which result key each position reads,
whether a cell arrives encoded, which members the statement's own transform
already judged, which documents the position carries — so none of it could be a
layout fact, and none of it was made one. What a compiled read holds tripled
under `Columns` and grew by about 43% under `Document`; that is the fixed cost
the per-row savings were bought with, and it dies with the execution that
compiled the read.

## Retained graph bytes per projection did not increase

COR-137 requires this figure not to rise, and the report's own cell cannot settle
it. That cell is read after the script's four timed seams have run in the same
process, and what those repetitions leave behind the reading then charges to the
graph: on this code the retained seam reads about 1.9 kB higher there than it
reads in a process that has done nothing else (170,368 against 168,453 on 3.13
`Columns`), while on the code the "before" half measured the two readings agree
inside their own spread. The cell is sound as a level and not as a difference. So
the requirement is settled by a controlled A/B instead — the batch seam alone,
nothing in front of it, one fresh child interpreter per reading, `PYTHONHASHSEED`
pinned, the "before" arm taken from a worktree at `4db79c8f` and the "after" arm
from this branch's head.

| | before (B) | after (B) | before (B/proj) | after (B/proj) |
|---|---:|---:|---:|---:|
| 3.13 `Columns` (mean of three) | 168,533 | 168,525 | 2,633.3 | 2,633.2 |
| 3.13 `Document` | 192,588 | 192,303 | 3,009.2 | 3,004.7 |
| 3.14 `Columns` | 176,752 | 176,792 | 2,761.8 | 2,762.4 |
| 3.14 `Document` | 200,634 | 200,499 | 3,134.9 | 3,132.8 |

**The verdict is that it did not increase.** Two cells read lower, and the two
that read higher move by 40 B and 8 B over a 170 kB window — one part in four
thousand, and well inside the instrument's own spread on this workload. The
spread is measured rather than assumed: three "before" processes on 3.13
`Columns` read 168,359, 168,734, and 168,505 B, a range of 375 B, which is the
`datetime` residue this workload's `Timestamp` leg leaves behind and which the
Phase 1 half of this document already records as the reason the gated regression
asserts structure rather than bytes. The structural argument agrees with the
measurement: conversion produces byte-identical member rows, issues, and view
rows before and after, and what moved is only where the level that reads a row is
held.

## Call counts

One profiled batch of 64 rows, counted by defining site. A `dict(...)` is a type
call, which `cProfile` does not record at all, so the containers whose inputs one
compiled read already fixed are counted at the function that builds each one.
Identical on both minors.

| contributor | Columns before | Columns after | Document before | Document after |
|---|---:|---:|---:|---:|
| `decode_canonical_wire` | 3,640 | 3,640 | 4,264 | 4,264 |
| `encode_wire` | 3,640 | 3,640 | 4,264 | 4,264 |
| `matches_neutral_type` | 7,360 | 7,360 | 8,536 | **7,800** |
| `admits_stored_scalar` | 864 | 864 | 864 | **128** |
| `reduce_declared_members_classified` | 672 | 672 | 672 | 672 |
| `decode_occurrence_classified` | 112 | 112 | 112 | 112 |
| `occurrence_shape` | 336 | **0** | 0 | 0 |
| `materialize_row` | 64 | 64 | 64 | 64 |
| `convert_row` — one `result_keys` dict | 64 | **0 dicts** | 64 | **0 dicts** |
| `LevelContext` — one fresh context per row | 64 | **0** | 64 | **0** |
| `CompiledRead.attribute_reads` — one dict per row | 64 | **0** | 64 | **0** |
| `_document_columns` — one projected frozenset | 128 | **gone** | 128 | **gone** |
| `observable_columns` | 64 | 64 | 64 | 64 |
| **containers rebuilt per row, summed** | **5.00** | **0.00** | **5.00** | **0.00** |

**Nothing is rebuilt per row any more**, which is COR-137's completion criterion
for the layout-, member-, and type-invariant work it names: the fresh
`LevelContext`, the `result_keys` dict, the `attribute_reads` dict, and both
projected frozensets are gone, and `occurrence_shape` — 5.25 calls per row under
`Columns`, every one of them re-deriving a shape the member's declaration fixed —
is called zero times on either layout. The conversion-side call counts that
remain are the contract rather than waste: `decode_occurrence_classified` and
`reduce_declared_members_classified` run in the compiled read's own fan-out, once
per projected occurrence, and the 128 `admits_stored_scalar` calls that survive
under `Document` are the key Columns alone — each row's primary key and the
correlation key its level joined on — which stay direct Columns under either
layout. The 736 that went are re-admissions of members the fan-out had already
classified; `matches_neutral_type` falls by the same 736, because admission
delegates to it.

Under `Columns` `admits_stored_scalar` is unchanged at 864, and that is correct
rather than a missed saving: that layout classifies no direct scalar, so all 864
are the position's real admissions.

**What the "before" column named as the target, and where each target landed.**
Optimization was allowed to begin only if the measured baseline showed a per-row
cadence for at least one contributor it could remove, and two of the three
thresholds stated in advance were cleared. `occurrence_shape` was called 5.25
times per row under `Columns` against a threshold of one, every one of them
re-deriving a shape the member's declaration fixed; it is now zero. Five
containers were rebuilt per row on **both** layouts against a threshold of four —
the fresh `LevelContext`, the `attribute_reads` dict, the `result_keys` dict, and
the projected frozenset twice; that count is now zero. The third,
`admits_stored_scalar` at 13.5 calls per row, was recorded as evidence rather
than counted, because its threshold term is zero under `Columns`; under
`Document` 736 of those 864 calls re-admitted members the compiled transform had
already classified, and those are the ones that went.

## Where each saving came from

Each slice was committed on its own and the matrix was rerun after it, so every
figure above is attributable.

| commit | what it changed | what moved |
|---|---|---|
| `398e2bac` | `AttributeReadContract` holds its `AttributeMetadata` by reference; `attribute_reads` scans its tuple instead of building a dict; `CompiledRead` publishes `resolvable` | prepared bytes per compiled read −400 B on both layouts; containers rebuilt per row 5.00 → 4.00 |
| `3d2b9d42` | seven `RowTransform` variants, two wrappers, and `RowTransformResult` collapse into one staged `RowMaterializer` | `occurrence_shape` 336 → 0 under `Columns`; transient −334 B/row and peak −20 kB on 3.13 `Columns`; compiled-read preparation +0.08 ms and +4.9 kB (`Columns`) / +1.9 kB (`Document`) per read |
| `61c852a1` | `LevelContext` derives the projected flags, the observation exclusions and each document's zero value once; conversion reads contracts by position; no re-admission for a classified member | `admits_stored_scalar` 864 → 128 under `Document`; containers rebuilt per row 4.00 → 1.00; µs/row −3% under `Columns` and −5 to −7% under `Document` |
| `72949d45` | `PreparedRead` binds one `LevelContext` per resolvable Entity per compiled read; every read lane goes through it | `LevelContext` constructions and `attribute_reads` calls 64 → 0 per batch; containers rebuilt per row 1.00 → 0.00; prepared +2,600 B (3.13) / +2,658 B (3.14) per read and 14–16 µs of `bind` per execution; transient −80 B/row on 3.13 `Columns` |

The timings are attributable only as a trajectory, not slice by slice. Each
intermediate reading moved by about the ±10% this machine's own repeatability
covers, so no slice claimed a timing verdict of its own; what the four together
deliver is the −15.2% / −6.4% (3.13) and −13.8% / −5.7% (3.14) recorded above.
Read as direction, the trajectory of µs/row on 3.13 `Columns` is
354.7 → 331–344 → 315–316 → 305–306 → 301, which puts the movement in the two
slices that removed the most per-row work.

## The codec decision

COR-137 permits removing redundant encode-back or membership work inside the
canonical-decoding contract *only if* canonical Wire validation is still a
material contributor once the per-row work above is gone. The stated criterion is
that the redundant legs — `encode_wire`, reached only from `_is_canonical_output`,
and the second `matches_neutral_type` inside it; the decode itself is the
contract — take at least 10% of the profiled batch's cumulative time on either
layout.

One profiled batch of 64 rows, after Phase 5:

| | 3.13 `Columns` | 3.13 `Document` | 3.14 `Columns` | 3.14 `Document` |
|---|---:|---:|---:|---:|
| Profiled batch, cumulative (ms) | 70.463 | 85.671 | 72.598 | 87.214 |
| `decode_canonical_wire` (the contract) | 69.3% | 73.2% | 69.3% | 73.6% |
| `_is_canonical_output` (the round trip) | 46.8% | 50.0% | 47.1% | 50.6% |
| **`encode_wire` (the redundant leg)** | **41.5%** | **44.6%** | **42.0%** | **45.4%** |
| — the `matches_neutral_type` within it | 9.0% | 9.5% | 9.0% | 9.6% |

**The criterion is met on both layouts and both minors, by four times the bar.**
Cross-checked untraced, with the canonicality re-encode short-circuited so the
difference is the leg's own wall clock: the round trip is 50.9% of the batch on
3.13 `Columns` (19.688 → 9.660 ms), 54.0% on 3.13 `Document` (23.857 → 10.983),
51.3% on 3.14 `Columns` and 55.6% on 3.14 `Document`. The shipped arm read the
same before and after the ablated one, so that is the leg and not a warm-up.

That ablation is an upper bound on the opportunity and not a target. It answers
"what does re-deriving the spelling cost", not "what may be removed": the
canonicality verdict itself is the admission rule, and every Neutral Type's
canonical spelling, noncanonical refusal, managed-carrier rule, and diagnostic
reason must come out unchanged. What is genuinely redundant is narrower — the
membership check `encode_wire` repeats on a value `decode_canonical_wire` has
already admitted, and the second `_exact_decimal` spelling every `Decimal`
admission pays — and how much of the leg that accounts for is what the codec
slice measures. So the conditional codec phase **runs**, inside the existing
canonical-decoding contract, with `tests/unit/test_wire.py`'s inverse law as its
acceptance.

## Secondary workload

The direct-converter 64-graph shape, driven through `convert_row` and
`GraphBuilder` alone. It is layout-independent, so the two cells of one runtime
measure one workload and the spread between them is this reading's own
repeatability. It calls no `compile_read` and no `materialize_row`, so it sees
only the conversion-side half of this work — which is why it moves at all.

| | 3.13 before | 3.13 after | 3.14 before | 3.14 after |
|---|---:|---:|---:|---:|
| Build (convert, write, seal), 448 projections | 26.20 ms | 24.10 ms | 26.06 ms | 24.31 ms |
| — per projection | 58.48 µs | 53.80 µs | 58.17 µs | 54.25 µs |
| — projections per second | 17,100 | 18,586 | 17,191 | 18,432 |
| Merge, 448 projections | 0.48 ms | 0.44 ms | 0.46 ms | 0.43 ms |
| — per projection | 1.06 µs | 0.97 µs | 1.03 µs | 0.96 µs |
| **64-graph `cost` item, recorded duration** | **47.6 s** | *refreshed with the duration store* | **47.6 s** | *refreshed with the duration store* |

The item itself is never re-run from a tool. Its duration is read from
`tests/_support/cost_durations.json`, which is what balances the `cost` class's
six CI shards; the "before" figure above is that file as it stood, and its
"after" figure lands when the store is refreshed, together with the predicted
maximum across the six CI cost cells.

## Conditions

| | |
|---|---|
| Recorded | 2026-09-10, both halves on the same machine on the same day |
| Machine | Apple M5, 10 cores, 32 GiB, darwin/arm64 |
| OS | macOS 26.6.2 (build 25G83) |
| Interpreters | CPython 3.13.15 and 3.14.7 (both `main`, Aug 5 2026, Clang 21.0.0) |
| Command | `just python-report-snapshot-materialization` |
| Source (before) | branch `cor-137-speed-up-snapshot-materialization-0ou36c`, base commit `431936be` |
| Source (after) | the same branch at `72949d45`, the head of the four slices in *Where each saving came from* |
| Isolation | one fresh child interpreter per (minor, layout), `PYTHONHASHSEED=0`, no coverage tracer |
| Warm-up | 200 unsampled runs before every memory window; 5 before every timing |
| Timing samples | mean of 20 batches, taken untraced, from an already prepared model and compiled reads |
| Runtime | about three minutes for the whole matrix |
| Repeatability (before) | a second whole-matrix run moved the timings by up to 10% (Columns 3.14: 22.802 → 24.965 ms) and one memory row by 0.2% (Document 3.13 retained: 193,584 → 193,253 B); everything else was identical to the byte |
| Repeatability (after) | a second whole-matrix run moved µs/row by 3.3% at most (3.13 Columns 300.8 → 310.9) and every retained, peak, and transient figure by under 0.3%; the prepared totals, the layout-catalog figures, the tracked/reference census, and every call count were identical to the byte |
| Load | every run above was taken at a one-minute load average under 2.5, with model preparation as the control: a matrix taken on a busy machine reads 1.5–2× slow in every cell, *including* the preparation this work does not touch |

Each half is one recorded run. A report matrix is worth only the machine it was
taken on, which is why the timing rows are direction only: what is stable to the
digit is the structure — the counts and the prepared totals — and that is also
what the gated regression asserts.

## What is measured, and what is excluded

The batch is what one read pays per statement of rows: row materialization
through the prepared read, conversion into a shared `GraphBuilder`, the
observation every hydrating row takes, the key gather and view fan-back each
level performs, and `seal`. Binding a compiled read to its levels is preparation
rather than batch work and is timed as such, inside compiled-read preparation and
reported separately within it, so nothing this work moved out of the row loop
left the report.

The root statement's rows are materialized whole and held until the batch closes,
because `read_roots` hands them over that way and the read that answers holds them
through every level below; a level below the root converts out of its own lazy
materialization and holds one row at a time. The peak in the memory table above
is therefore a peak the shipped loop also reaches.

**Compilation is outside the batch, and cannot be inside it.** A child level's
`compile_read` runs between gathering its parents' keys and converting its rows,
so timing `build_graph` as one unit would recompile four statements per repetition
and call the result throughput. The batch therefore compiles once, against the
fixture's own keys, and still gathers those keys per repetition because production
does — and still branches on them, so a level with no gathered key attaches the
empty result and issues nothing, exactly as the shipped loop does. Lifting the
compile out is the one place the measured loop differs from it.

**Merge, classification, and publication are excluded**, as the ticket's timing
boundary states, together with fixture construction, SQL execution, and Wire
rendering.

**Decoded payload leaves are excluded structurally, not by filtering.** Every
stored row and every document in it is built before any window opens, so a
converted row that merely references one of them costs the reading the position
and not the leaf.

**The graph is held at the sample point and the builder is not.** The builder is
transient in production, dying with the frame that sealed it, so a reading that
kept one would measure something no read retains.

**Transient bytes are derived, not measured directly.** They are the high-water
mark above the collected pre-batch floor, less what the sealed graph keeps.
Measuring each against its own floor would charge a batch for its own product
twice, or for none of it.

## The workload

A fourth workload model, because none of the three that exist fits:
`tools/snapshot_graph_overhead.py` is `Columns`-only and declares four Neutral
Types, `tests/unit/_document_layout_support.py` is a layout twin at the
accepted-Metamodel level with no `DomainModel` for `prepare_model` to prepare, and
`test_snapshot_graph_retention.py`'s workload is the frozen 64-graph cost item.
The members are declared once, in a factory over the layout, so the two layouts
are two namespaces rather than two transcriptions
(`tests/unit/_snapshot_materialization_support.py`).

```text
Owner (root of every batch)                        8 per batch
  |- nodes            broad to-many               4 per owner: 2 Alpha, 2 Beta
  |- special[Alpha]   narrowed to-many            2 per owner, the SAME rows again
  |- favorite         to-one into the same family 1 per owner, the first child again
  '- nodes -> owner   back-reference               issues no statement at all

Node   TPH family root, tag column `kind`
       14 Attributes: one of every declarable Neutral Type, plus the key and the
       owner correlation; one One occurrence and one Many occurrence
Special  abstract middle, adds `rank`     Alpha  concrete, tag `alpha`
Beta     concrete, tag `beta`, adds `weight`

Tag (each occurrence)  one leaf of every declarable Neutral Type,
                       a nested One `detail` and a nested Many `details`
Detail (nested)        three leaves

64 rows over 5 levels -> 64 projections, 40 logical nodes, 3 view slots
```

Under `Columns` every Attribute is a Column of its own and each occurrence is a
Structured Column of its own; under `Document` the key, the two correlation
Attributes and the discriminator stay direct and everything else lives in one
shared `payload` document. Both are the same members, so the layout is the only
thing that differs.

**The rows are synthesized from the compiled read itself** — one value per
Attribute contract, one document per projected occurrence, every leaf in the
codec's own canonical spelling, and each member placed where `m-storage-layout`
says it lives. A fixture that drifted from what the statement projects would leave
`ABSENT` positions or raise a stored-data issue, and the workload's own `verify`
refuses both before any window opens. That is also what makes the path measured a
*conforming* one, which is the path every absolute figure above is stated over.

## Rerunning it

```sh
just python-report-snapshot-materialization
```

It takes about three minutes and prints, per supported minor and per storage
layout, the steady-state timings, the memory readings, the call counts, and the
secondary workload. Comparing against the tables above needs the same conditions —
the same machine class, the same interpreters, no competing load — because the
absolute numbers are machine-relative even where the ratios are not. A reading
taken on a different CPython is a reading of that CPython as much as of this code.
