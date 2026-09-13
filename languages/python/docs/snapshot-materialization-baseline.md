# Snapshot materialization — recorded baseline

What a production Snapshot read spends turning returned rows into a sealed graph,
and what that costs in memory, measured on one machine under stated conditions,
under both storage layouts and on both supported CPython minors. COR-137 asks for
a reviewed baseline before any optimization, and for every later change to be
measured against it. Three readings are recorded here: the "before" half is the shipped path as it
stood at `431936be`; the middle column is that path with the per-row work whose
inputs a compiled read already fixed removed; and the "after" column adds the
canonical-decoding slice the middle column's own profile called for, which the
codec section below states in full.

## Phase 3 delivery addendum

The tables below remain the recorded COR-137 historical baseline. The current delivery boundary is no longer a sealed graph plus a later merge. One statement delivery now finishes a `Page` that owns occurrence arrays, identity claims, exact Payload Witnesses, and lazily judged Entity States. A `RootView` borrows that Page, compares every witness for a reached logical key before payload judgment, and reuses one decoded Entity State per key within the Page. Separate result roots receive separate published node objects even when they borrow the same Page state.

The report command now times `PreparedRead.materialize` through `PageBuilder.finish`: row transformation, identity claim formation, exact witness capture, view fan-back, and Page finishing. Root View construction, lazy payload judgment, classification, and Typed or Wire publication remain outside that timing window and are graded by the cost portfolio instead. The profiled contributor formerly occupied by the duplicate physical observation extraction is now `claim_identity`; read evidence and predicate-write staging view the same positional Entity State through `EntityStateRow` rather than decoding or rebuilding a second member dictionary.

The Page-era Budget Contract is executable in `tests/unit/snapshot/test_snapshot_materialization_scaling.py`, `tests/unit/snapshot/test_snapshot_evidence_retention.py`, and `tests/unit/snapshot/test_snapshot_stream_retention.py`. It grades fixed prepared state, one Page plus one published root at suspension, no accumulation of prior Pages, independence from total result size and equivalent cross-page position, peak dependence on the currently published root rather than unrelated Page roots, and immutable predecessor evidence shared until successor lowering detaches a writable document. Whole-interpreter readings remain confined to `in_a_child_interpreter`; `just python-check-cost` is the one local focused gate for this portfolio.

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

Per-row steady state, from an already prepared model and compiled read. `rows`
is the per-row work removed, `codec` adds the canonical-decoding slice, and Δ
spans the whole change. One recorded run per column; see the conditions table for
what a second run moved.

CPython 3.13:

| | Col. before | Col. rows | Col. codec | Δ | Doc. before | Doc. rows | Doc. codec | Δ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Batch, 64 rows (ms) | 22.699 | 19.251 | 13.804 | −39.2% | 25.032 | 23.439 | 16.845 | −32.7% |
| **Rows per second** | **2,819** | **3,324** | **4,636** | **+64.5%** | **2,557** | **2,731** | **3,799** | **+48.6%** |
| **Microseconds per row** | **354.7** | **300.8** | **215.7** | **−39.2%** | **391.1** | **366.2** | **263.2** | **−32.7%** |
| Model preparation (ms) | 0.178 | 0.179 | 0.177 | — | 0.182 | 0.177 | 0.177 | — |
| — decode preparation within it | 0 | 0 | 0 | — | 0 | 0 | 0 | — |
| Compiled-read preparation (ms) | 0.381 | 0.462 | 0.466 | +0.085 | 0.447 | 0.473 | 0.468 | +0.021 |
| — decode preparation within it (`bind`) | 0 | 0.014 | 0.014 | +0.014 | 0 | 0.014 | 0.014 | +0.014 |

CPython 3.14:

| | Col. before | Col. rows | Col. codec | Δ | Doc. before | Doc. rows | Doc. codec | Δ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Batch, 64 rows (ms) | 22.802 | 19.650 | 14.241 | −37.5% | 25.346 | 23.896 | 16.671 | −34.2% |
| **Rows per second** | **2,807** | **3,257** | **4,494** | **+60.1%** | **2,525** | **2,678** | **3,839** | **+52.0%** |
| **Microseconds per row** | **356.3** | **307.0** | **222.5** | **−37.5%** | **396.0** | **373.4** | **260.5** | **−34.2%** |
| Model preparation (ms) | 0.185 | 0.184 | 0.190 | — | 0.199 | 0.181 | 0.182 | — |
| — decode preparation within it | 0 | 0 | 0 | — | 0 | 0 | 0 | — |
| Compiled-read preparation (ms) | 0.384 | 0.459 | 0.492 | +0.108 | 0.451 | 0.474 | 0.481 | +0.030 |
| — decode preparation within it (`bind`) | 0 | 0.014 | 0.015 | +0.015 | 0 | 0.014 | 0.014 | +0.014 |

**Model preparation is untouched in all three columns**, which is this reading's
own control: nothing in this work reaches `prepare_model`, so a matrix whose model
preparation moved was taken on a busy machine and was discarded. Decode
preparation inside model preparation stays zero, and is a statement about
ownership rather than a figure that was not taken: every fact this work
pre-resolves is projection-specific, so it belongs to the compiled read and is
reported there.

**`bind` is what the compiled read now owns**, and it is the whole of the decode
preparation any stage of this path pays: 14 to 16 µs per execution for the five-level
plan, about 3% of compiled-read preparation and about one row of steady-state
work. **The codec slice adds no preparation at all**, on either side of the
matrix: it holds nothing, so compiled-read preparation reads the same in the last
two columns and the whole of its effect is in the batch.

## What preparation costs, and when it repays

The one-time cost this work added is compiled-read preparation; the recurring
saving is per row.

| | 3.13 Columns | 3.13 Document | 3.14 Columns | 3.14 Document |
|---|---:|---:|---:|---:|
| Preparation added, per execution (µs) | 85 | 21 | 108 | 30 |
| Time saved, per row (µs) | 139.0 | 127.9 | 133.8 | 135.5 |
| **Rows that repay it** | **1** | **1** | **1** | **1** |
| Prepared bytes added, per execution | 28,320 | 16,448 | 28,976 | 16,856 |
| Transient bytes saved, per row | 342 | 47 | 2 | 37 |
| **Rows that repay that** | **83** | **350** | — | **456** |

The time half repays inside a single row on every cell. The codec slice is what
moved it there: it added no preparation and took about a third of the batch, so
the same fixed cost now stands against a per-row saving two and a half times the
one the row work alone bought, where the middle column repaid in two rows.

The byte half is the honest awkward figure. Read as a running total — every
prepared byte held against every transient byte a row no longer allocates — one
execution of this workload converts 64 rows and repays the prepared cost on no
cell at all, 3.13 `Columns` coming nearest at 83 rows; and on 3.14 `Columns` the
per-row transient saving is inside this reading's own spread (the two codec runs
read 3,825 and 3,828 B/row against 3,827 before), so no row count can be stated
for it. The codec slice moved this half by nothing measurable, which is what it
should do: what it stopped allocating — a re-derived spelling and the objects
under it — was allocated and freed inside one leaf decode, and a container that
never outlives the row that made it never raises the batch's high-water mark. Two things make that comparison narrower than it looks. Prepared
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

| | Col. before | Col. rows | Col. codec | Δ | Doc. before | Doc. rows | Doc. codec | Δ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Retained graph bytes per projection** | **2,631.8** | **2,662.0** | **2,659.3** | **+1.0%** | **3,024.8** | **3,029.9** | **3,035.5** | **+0.4%** |
| Retained graph bytes, 64 projections | 168,434 | 170,368 | 170,196 | +1,762 | 193,584 | 193,915 | 194,273 | +689 |
| Peak traced bytes above the collected floor | 432,113 | 412,225 | 412,012 | −4.7% | 436,129 | 433,744 | 433,837 | −0.5% |
| **Transient bytes per row** | **4,120** | **3,779** | **3,778** | **−8.3%** | **3,790** | **3,747** | **3,743** | **−1.2%** |
| Prepared bytes, whole compiled read set | 14,116 | 42,436 | 42,436 | +28,320 | 38,446 | 54,894 | 54,894 | +16,448 |
| Prepared bytes per compiled read | 3,529 | 10,609 | 10,609 | +7,080 | 9,612 | 13,724 | 13,724 | +4,112 |
| — the levels `bind` holds, within it | 0 | 2,600 | 2,600 | +2,600 | 0 | 2,600 | 2,600 | +2,600 |
| **Prepared decode state per exact Entity layout** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** |
| Layout catalog bytes per exact Entity layout | 4,965 | 4,965 | 4,965 | 0 | 4,965 | 4,965 | 4,965 | 0 |
| One exact layout: tracked objects / references | 223 / 986 | 223 / 986 | 223 / 986 | 0 | 223 / 986 | 223 / 986 | 223 / 986 | 0 |

CPython 3.14:

| | Col. before | Col. rows | Col. codec | Δ | Doc. before | Doc. rows | Doc. codec | Δ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Retained graph bytes per projection** | **2,765.0** | **2,762.4** | **2,764.0** | **−0.0%** | **3,137.2** | **3,143.9** | **3,142.3** | **+0.2%** |
| Retained graph bytes, 64 projections | 176,957 | 176,792 | 176,896 | −61 | 200,782 | 201,211 | 201,106 | +324 |
| Peak traced bytes above the collected floor | 421,894 | 421,660 | 421,715 | −0.0% | 445,725 | 443,688 | 443,680 | −0.5% |
| **Transient bytes per row** | **3,827** | **3,826** | **3,825** | **−0.1%** | **3,827** | **3,789** | **3,790** | **−1.0%** |
| Prepared bytes, whole compiled read set | 14,516 | 43,492 | 43,492 | +28,976 | 39,686 | 56,542 | 56,542 | +16,856 |
| Prepared bytes per compiled read | 3,629 | 10,873 | 10,873 | +7,244 | 9,922 | 14,136 | 14,136 | +4,214 |
| — the levels `bind` holds, within it | 0 | 2,658 | 2,658 | +2,658 | 0 | 2,658 | 2,658 | +2,658 |
| **Prepared decode state per exact Entity layout** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** |
| Layout catalog bytes per exact Entity layout | 5,072 | 5,072 | 5,072 | 0 | 5,072 | 5,072 | 5,072 | 0 |
| One exact layout: tracked objects / references | 222 / 986 | 222 / 986 | 222 / 986 | 0 | 222 / 986 | 222 / 986 | 222 / 986 | 0 |

**Prepared decode state per exact Entity layout is zero on both sides**, and the
layout catalog is unchanged to the byte and to the reference. Every fact this
work pre-resolved is projection-aligned — which result key each position reads,
whether a cell arrives encoded, which members the statement's own transform
already judged, which documents the position carries — so none of it could be a
layout fact, and none of it was made one. What a compiled read holds tripled
under `Columns` and grew by about 43% under `Document`; that is the fixed cost
the per-row savings were bought with, and it dies with the execution that
compiled the read.

**The codec slice holds nothing at all**, which is why every prepared figure in
the last two columns is identical to the byte. It removed work from a decode
rather than moving it anywhere, so it has no preparation to pay for and nothing
that could grow with a model, a read, a row, or a graph.

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

The codec slice was measured the same way, against the code the middle column
reports — same seam, same three processes per cell, the codec file swapped under
one interpreter so the two arms share a floor:

| | rows (B) | codec (B) | Δ | Δ per projection |
|---|---:|---:|---:|---:|
| 3.13 `Columns` (mean of three) | 168,378 | 168,316 | −62 | −1.0 |
| 3.13 `Document` | 192,157 | 192,217 | +60 | +0.9 |
| 3.14 `Columns` | 177,018 | 176,702 | −316 | −4.9 |
| 3.14 `Document` | 200,533 | 200,574 | +41 | +0.6 |

**The verdict is that it did not increase.** Over the whole change two cells read
lower, and the two that read higher move by 40 B and 8 B over a 170 kB window —
one part in four thousand, and well inside the instrument's own spread on this
workload. The codec slice's own reading says the same at a tenth of the size: two
cells lower, two higher by under a byte per projection, each inside its own arm's
range (the 3.13 `Document` "before" arm spans 199 B across its three processes and
the Δ is 60). It is also the reading the structure predicts, because the slice
changes no value the builder retains: `decode_canonical_wire` answers the same
decoded value for the same literal, and what stopped being derived was only the
spelling it was compared against. The
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

| contributor | Col. before | Col. rows | Col. codec | Doc. before | Doc. rows | Doc. codec |
|---|---:|---:|---:|---:|---:|---:|
| `decode_canonical_wire` | 3,640 | 3,640 | 3,640 | 4,264 | 4,264 | 4,264 |
| `encode_wire` | 3,640 | 3,640 | **0** | 4,264 | 4,264 | **0** |
| `matches_neutral_type` | 7,360 | 7,360 | **2,544** | 8,536 | 7,800 | **2,080** |
| `admits_stored_scalar` | 864 | 864 | 864 | 864 | **128** | 128 |
| `reduce_declared_members_classified` | 672 | 672 | 672 | 672 | 672 | 672 |
| `decode_occurrence_classified` | 112 | 112 | 112 | 112 | 112 | 112 |
| `occurrence_shape` | 336 | **0** | 0 | 0 | 0 | 0 |
| `materialize_row` | 64 | 64 | 64 | 64 | 64 | 64 |
| `convert_row` — one `result_keys` dict | 64 | **0 dicts** | 0 dicts | 64 | **0 dicts** | 0 dicts |
| `LevelContext` — one fresh context per row | 64 | **0** | 0 | 64 | **0** | 0 |
| `CompiledRead.attribute_reads` — one dict per row | 64 | **0** | 0 | 64 | **0** | 0 |
| `_document_columns` — one projected frozenset | 128 | **gone** | gone | 128 | **gone** | gone |
| `observable_columns` | 64 | 64 | 64 | 64 | 64 | 64 |
| **containers rebuilt per row, summed** | **5.00** | **0.00** | **0.00** | **5.00** | **0.00** | **0.00** |

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

**`encode_wire` is no longer reached at all**, on either layout, and
`matches_neutral_type` falls with it by 4,816 calls under `Columns` and 5,720
under `Document` — about 75 calls per row on both. Both are the codec slice, and
the section below says which of those calls were redundant and why. The number
that does NOT move is `decode_canonical_wire`: the admission rule still runs once
per stored value, which is the contract this work was forbidden to touch.

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
| the codec slice | canonical decoding reaches its verdict without re-deriving a spelling it does not need | `encode_wire` 3,640 / 4,264 → 0 per batch; `matches_neutral_type` −4,816 / −5,720; µs/row −28.3% / −28.1% (3.13) and −27.5% / −30.2% (3.14); nothing prepared, retained, or transient moved |

The first four slices are attributable only as a trajectory, not slice by slice.
Each intermediate reading moved by about the ±10% this machine's own repeatability
covers, so no slice among them claimed a timing verdict of its own; what the four
together deliver is the −15.2% / −6.4% (3.13) and −13.8% / −5.7% (3.14) the middle
column records. Read as direction, the trajectory of µs/row on 3.13 `Columns` is
354.7 → 331–344 → 315–316 → 305–306 → 301, which puts the movement in the two
slices that removed the most per-row work.

The codec slice is the one that can be attributed on its own, because its effect
is many times that spread and because it was also measured as a controlled A/B in
one process, the codec file swapped under one interpreter between the arms:
19.594 and 19.890 ms per `Columns` batch before it against 14.008 after, and
23.992 and 24.084 against 16.642 under `Document` — a third of the batch,
reproduced by the matrix's own −28% to −30%.

## The codec decision

COR-137 permits removing redundant encode-back or membership work inside the
canonical-decoding contract *only if* canonical Wire validation is still a
material contributor once the per-row work above is gone. It sets no percentage
for that; the bar this work adopted is that the redundant legs — `encode_wire`,
reached only from `_is_canonical_output`, and the second `matches_neutral_type`
inside it; the decode itself is the contract — take at least 10% of the profiled
batch's cumulative time on either layout.

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
reason must come out unchanged. So the conditional codec phase **ran**, inside the
existing canonical-decoding contract, with `tests/unit/test_wire.py`'s inverse law
and `tests/unit/test_document_codec.py`'s spelling table as its acceptance —
neither edited by it.

## What the codec slice removed

**Most of the round trip turned out to be redundant rather than necessary,
because the verdict is per Neutral Type and most types settle it in the decoder.**
The Wire matrix in `core/spec/m-wire.md` names, for every declared type, what a
noncanonical spelling of it looks like. Five types have none at all — `boolean`,
`int32`, `int64`, `string`, `json` — so every literal their grammar admits is the
one the codec writes back. Four more have one, and each decoder refuses it against
the source text itself before the verdict is asked for: `decimal` against its
exact scaled spelling, `bytes` against the lowercase-hex grammar, `date` against
the fixed-width grammar, `uuid` against the lowercase hyphenated grammar. For
those nine the re-encode could only re-derive a string that had already been
compared, or compare a value with itself.

What is left needs a spelling, and still derives one: the numeric spellings, which
are not the value they name, and the temporal fraction widths, which the grammars
admit written at three digits, at six, and not at all. Those four types —
`int32`/`int64`, `float32`/`float64`, `time`, `timestamp` — reach the formatter
directly instead of through `encode_wire`, skipping the carrier normalization and
the membership check a decoded value has already passed. Three narrower
redundancies went with them: the second `_exact_decimal` every `decimal`
admission spelled, the two extra whole-carrier walks every `json` admission paid
(one for membership, one for the discarded re-encode), and the shortest-number
search at `float64`, where a number that names the value at binary64 width **is**
the value, so the search could only hand back what it was given.

| | 3.13 `Columns` | 3.13 `Document` | 3.14 `Columns` | 3.14 `Document` |
|---|---:|---:|---:|---:|
| Profiled batch, cumulative (ms) | 48.519 | 57.745 | 50.197 | 58.813 |
| — before the slice | 70.463 | 85.671 | 72.598 | 87.214 |
| `decode_canonical_wire` (the contract) | 61.0% | 66.1% | 61.2% | 66.3% |
| `_is_canonical_output` (the verdict) | 29.4% | 32.7% | 29.7% | 33.0% |
| — the `float32` shortest-number search within it | 20.8% | 23.6% | 21.3% | 24.1% |
| **`encode_wire`** | **0 calls** | **0 calls** | **0 calls** | **0 calls** |
| `matches_neutral_type` | 7.7% | 3.5% | 7.8% | 3.5% |

Every verdict is unchanged, and that was measured rather than argued: 25,872
outcomes of `decode_wire`, `decode_canonical_wire`, and `encode_wire` over
fourteen declared types and every literal the law suites, the Wire matrix, and a
seeded generator produce, compared value-for-value and reason-for-reason against
the previous implementation, with no difference; and 720,228 float outcomes on top
of that, over random bit patterns, subnormals, both extremes, and the matrix's own
double-rounding and tie-break representatives.

**One contributor stays, and it is the rule rather than a repeat.** The
shortest-number search at `float32` is 21% to 24% of the profiled batch and 18% to
21% of the untraced one, which is over that same 10% bar — but nothing about it is
redundant. A `float32`'s canonical Wire Value is a *different* number from the
value it names, and finding it means asking, digit count by digit count, which
numbers round back to that value at binary32 width. Nothing earlier in the decode
has that answer, so the only way to make it cheaper is to change how a decimal is
rounded to binary32 — a rounding shortcut inside `m-core`'s membership predicate,
which `m-wire` spends three rules keeping exact, and which COR-137 forbids this
work from touching. The ticket names that as a valid completion, and
`docs/deferred-ledger.md` **D-97** carries it.

## Secondary workload

The direct-converter 64-graph shape, driven through `convert_row` and
`GraphBuilder` alone. It is layout-independent, so the two cells of one runtime
measure one workload and the spread between them is this reading's own
repeatability. It calls no `compile_read` and no `materialize_row`, so what it
sees of this work is the conversion-side half and the codec — which is why it
moves at all, and why it moves again in the last column: an unclassified row's
occurrences are decoded in conversion, and every leaf of them is an admission.

| | 3.13 before | 3.13 rows | 3.13 codec | 3.14 before | 3.14 rows | 3.14 codec |
|---|---:|---:|---:|---:|---:|---:|
| Build (convert, write, seal), 448 projections | 26.20 ms | 24.10 ms | 22.31 ms | 26.06 ms | 24.31 ms | 22.26 ms |
| — per projection | 58.48 µs | 53.80 µs | 49.80 µs | 58.17 µs | 54.25 µs | 49.69 µs |
| — projections per second | 17,100 | 18,586 | 20,081 | 17,191 | 18,432 | 20,125 |
| Merge, 448 projections | 0.48 ms | 0.44 ms | 0.44 ms | 0.46 ms | 0.43 ms | 0.43 ms |
| — per projection | 1.06 µs | 0.97 µs | 0.99 µs | 1.03 µs | 0.96 µs | 0.96 µs |
| **64-graph `cost` item, recorded duration** | **47.6 s** | — | **45.2 s** | **47.6 s** | — | **45.2 s** |

The item itself is never re-run from a tool. Its duration is read from
`tests/_support/cost_durations.json`, which is what balances the `cost` class's
six CI shards, and it is one figure rather than one per minor: the store is
refreshed by a single whole-class session under the workspace interpreter, so the
same number stands in both halves of the row above. The "before" figure is that
file as it stood at `431936be`; the "after" figure was stored on 2026-09-11 by
`cd languages/python && uv run pytest -m cost -n auto --store-cost-durations`,
running the whole class in ten workers on the machine the conditions table names.

**Read the −2.4 s against its own family rather than on its own.** A stored
duration is a contended wall time from a ten-worker session, and between the two
refreshes the items this work cannot reach moved by −45% to +69%. What carries
the figure is that it moves with every other item of
`tests/unit/test_snapshot_graph_retention.py` — the suite whose workload is
`convert_row` and `GraphBuilder`, which is the path this section measures:
sixteen of that file's eighteen items over five seconds fell, by a median of
6.7%, while the rest of the class over five seconds scattered in both directions
around a median of −2.3%, seven of thirteen down. That file's total falls from
581.3 s to 544.6 s.

### The six CI cost cells

The cost class runs in six duration-balanced CI shards. The maximum below is a
**local prediction and not a CI reading**: it partitions the refreshed durations
with the same weights and the same assignment the collection hook uses
(`tests/_support/cost_durations.py`, whose `weights` and `shard_of_each`
`tests/unit/test_scheduling_partition.py` predicts every deployed cell through),
and it is stated in the seconds this machine measured rather than the seconds
`ubuntu-latest` will spend. What it predicts is the balance, not a wall time; the
actual six-cell wall time exists only once a pushed branch has run the six
shards.

| | before (`431936be`, 62 items) | after (64 items) |
|---|---:|---:|
| Whole class, summed | 1,003.8 s | 944.8 s |
| **Predicted maximum cell of six** | **167.5 s** | **157.6 s** |
| Predicted minimum cell of six | 167.1 s | 157.3 s |
| Items in the heaviest cell | 11 | 10 |

The heaviest cell is within a third of a second of the lightest in both columns,
which is the balance the store exists for; what the class as a whole lost, the
maximum cell lost with it. The two
`tests/unit/test_snapshot_materialization_scaling.py` items Phase 1 added enter
the store here for the first time, at 12.9 s and 1.7 s, and are inside the
"after" total — so the class gained two items and still summed 59.0 s less.
**The item's shard number is not stable and is recorded nowhere**: this refresh
moved the 64-graph item from cell 6 to cell 5, which is the rebalance COR-137
anticipates.

## Conditions

| | |
|---|---|
| Recorded | 2026-09-10, all three columns on the same machine on the same day |
| Machine | Apple M5, 10 cores, 32 GiB, darwin/arm64 |
| OS | macOS 26.6.2 (build 25G83) |
| Interpreters | CPython 3.13.15 and 3.14.7 (both `main`, Aug 5 2026, Clang 21.0.0) |
| Command | `just python-report-snapshot-materialization` |
| Source (before) | branch `cor-137-speed-up-snapshot-materialization-0ou36c`, base commit `431936be` |
| Source (rows) | the same branch at `72949d45`, the head of the four slices in *Where each saving came from* |
| Source (codec) | the same branch with the canonical-decoding slice applied — the commit this column landed in |
| Isolation | one fresh child interpreter per (minor, layout), `PYTHONHASHSEED=0`, no coverage tracer |
| Warm-up | 200 unsampled runs before every memory window; 5 before every timing |
| Timing samples | mean of 20 batches, taken untraced, from an already prepared model and compiled reads |
| Runtime | about three minutes for the whole matrix |
| Repeatability (before) | a second whole-matrix run moved the timings by up to 10% (Columns 3.14: 22.802 → 24.965 ms) and one memory row by 0.2% (Document 3.13 retained: 193,584 → 193,253 B); everything else was identical to the byte |
| Repeatability (rows) | a second whole-matrix run moved µs/row by 3.3% at most (3.13 Columns 300.8 → 310.9) and every retained, peak, and transient figure by under 0.3%; the prepared totals, the layout-catalog figures, the tracked/reference census, and every call count were identical to the byte |
| Repeatability (codec) | a second whole-matrix run moved µs/row by 2.3% at most (3.13 Document 263.2 → 257.2) and peak by under 0.4%; retained moved by up to 1.4% and transient by up to 1.0%, both on 3.13 `Document` and both the level-and-not-a-difference reading **D-96** describes — the controlled A/B above is what settles that figure. Every prepared total, every layout-catalog figure, the tracked/reference census, and every call count were identical to the byte |
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
