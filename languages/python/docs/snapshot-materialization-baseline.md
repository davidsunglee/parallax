# Snapshot materialization — recorded baseline

What a production Snapshot read spends turning returned rows into a sealed graph,
and what that costs in memory, measured on one machine under stated conditions,
under both storage layouts and on both supported CPython minors. COR-137 asks for
a reviewed baseline before any optimization, and for every later change to be
measured against it. This is the "before" half of that reading.

Nothing here gates. `just python-report-snapshot-materialization` is a `report`:
it passes no verdict and belongs to no aggregate, because elapsed time is a
property of the machine that ran it — every CI job runs the floating
`ubuntu-latest` label — and a total in bytes is machine- and interpreter-relative,
since `tracemalloc` figures move with CPython. The *shape* of the claim is gated
instead, in `tests/unit/test_snapshot_materialization_scaling.py`, which the
`cost` class owns and CI runs on every change: it asserts that what preparation
holds is fixed by the model's exact Entity layouts and by the compiled reads, as
an exact equality between eight rows and sixty-four through one prepared read, and
between one execution and sixty-four against one prepared selection. That equality
is read as a closure — every object one prepared structure reaches without crossing
into another, and every reference between them — beside a census of what each
window leaves alive, because references and positions answer definitely where a
total in bytes does not.

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

**A byte equality over a window that runs the codec.** Two runs of one identical
seam read about four hundred bytes apart on a forty-kilobyte window, in either
direction, after eight hundred warm-up batches: the interpreter's own `datetime`
formatting leaves a slowly saturating residue behind the `Timestamp` leg of the
canonical Wire codec. That is why the byte totals below are reported and the gated
regression asserts structure instead. The neighbouring 64-graph cost item still
asserts bytes because its workload declares four Neutral Types and reaches none of
that leg.

## The figure

Per-row steady state, from an already prepared model and compiled read. Both
minors, both layouts.

| | CPython 3.13 | | CPython 3.14 | |
|---|---:|---:|---:|---:|
| | **Columns** | **Document** | **Columns** | **Document** |
| Batch, 64 rows (ms) | 22.699 | 25.032 | 22.802 | 25.346 |
| **Rows per second** | **2,819** | **2,557** | **2,807** | **2,525** |
| **Microseconds per row** | **354.7** | **391.1** | **356.3** | **396.0** |
| Model preparation (ms) | 0.178 | 0.182 | 0.185 | 0.199 |
| — decode preparation within it | 0 | 0 | 0 | 0 |
| Compiled-read preparation (ms) | 0.381 | 0.447 | 0.384 | 0.451 |
| — decode preparation within it | 0 | 0 | 0 | 0 |
| Rows of steady state one whole preparation costs | 2 | 2 | 2 | 2 |
| — compiled-read preparation alone | 1 | 1 | 1 | 1 |

Memory, over the same batch.

| | CPython 3.13 | | CPython 3.14 | |
|---|---:|---:|---:|---:|
| | **Columns** | **Document** | **Columns** | **Document** |
| **Retained graph bytes per projection** | **2,631.8** | **3,024.8** | **2,765.0** | **3,137.2** |
| Retained graph bytes, 64 projections | 168,434 | 193,584 | 176,957 | 200,782 |
| Peak traced bytes above the collected floor | 432,113 | 436,129 | 421,894 | 445,725 |
| **Transient bytes per row** | **4,120** | **3,790** | **3,827** | **3,827** |
| Prepared bytes, whole compiled read set | 14,116 | 38,446 | 14,516 | 39,686 |
| Prepared bytes per compiled read | 3,529 | 9,612 | 3,629 | 9,922 |
| **Prepared decode state per exact Entity layout** | **0** | **0** | **0** | **0** |
| Layout catalog bytes per exact Entity layout | 4,965 | 4,965 | 5,072 | 5,072 |
| One exact layout: tracked objects / references | 223 / 986 | 223 / 986 | 222 / 986 | 222 / 986 |

**Amortization.** One whole preparation — the model's and the execution's
together — costs about two rows of steady-state work, and compiled-read
preparation alone about one. A *repayment* row count needs two halves and cannot
be computed from one: it is the preparation the "after" half added divided by the
per-row time it saved, and it belongs beside the "after" tables.

**Prepared decode state is zero on both sides of this table**, which is a
statement about the code rather than a measurement that was skipped: no
model-derived and no compiled-read-derived decode preparation exists yet. The
layout-catalog line is context — what a model's own exact-layout state already
costs — and this work does not change it.

## Call counts

One profiled batch of 64 rows, counted by defining site. A `dict(...)` is a type
call, which `cProfile` does not record at all, so the containers whose inputs one
compiled read already fixed are counted at the function that builds each one.
Identical on both minors.

| contributor | Columns | per row | Document | per row |
|---|---:|---:|---:|---:|
| `decode_canonical_wire` | 3,640 | 56.88 | 4,264 | 66.62 |
| `encode_wire` | 3,640 | 56.88 | 4,264 | 66.62 |
| `matches_neutral_type` | 7,360 | 115.00 | 8,536 | 133.38 |
| `admits_stored_scalar` | 864 | 13.50 | 864 | 13.50 |
| `reduce_declared_members_classified` | 672 | 10.50 | 672 | 10.50 |
| `decode_occurrence_classified` | 112 | 1.75 | 112 | 1.75 |
| `occurrence_shape` | **336** | **5.25** | 0 | 0.00 |
| `materialize_row` | 64 | 1.00 | 64 | 1.00 |
| `convert_row` — one `result_keys` dict | 64 | 1.00 | 64 | 1.00 |
| `LevelContext.__post_init__` — one fresh context | 64 | 1.00 | 64 | 1.00 |
| `CompiledRead.attribute_reads` — one contract dict | 64 | 1.00 | 64 | 1.00 |
| `_document_columns` — one projected frozenset | 128 | 2.00 | 128 | 2.00 |
| `observable_columns` | 64 | 1.00 | 64 | 1.00 |
| **containers rebuilt per row, summed** | **320** | **5.00** | **320** | **5.00** |

**The decision gate COR-137's Phase 1 ends at is met, on both layouts.** Its
stated criterion is a per-row cadence for at least one contributor the later
phases remove, and two of the three named thresholds are cleared:

- `occurrence_shape` is called 336 times over 64 rows on the `Columns` layout —
  5.25 per row against a threshold of 1, and every one of them re-derives a shape
  fixed by the member's declaration. The `Document` layout reaches it zero times,
  which is why the criterion is stated per layout.
- Five containers are rebuilt per row on **both** layouts — the fresh
  `LevelContext`, the `attribute_reads` dict, the `result_keys` dict, and the
  projected frozenset twice — against a threshold of four.

The third, `admits_stored_scalar` at 13.5 calls per row, is a re-admission count
rather than a rebuild: on the `Document` layout most of those members were already
classified by the compiled transform, which is the specific waste COR-137's first
narrow change removes.

## Secondary workload

The direct-converter 64-graph shape, driven through `convert_row` and
`GraphBuilder` alone. It is layout-independent, so the two cells of one runtime
measure one workload and the spread between them is this reading's own
repeatability.

| | CPython 3.13 | CPython 3.14 |
|---|---:|---:|
| Build (convert, write, seal), 448 projections | 26.20 ms | 26.06 ms |
| — per projection | 58.48 µs | 58.17 µs |
| — projections per second | 17,100 | 17,191 |
| Merge, 448 projections | 0.48 ms | 0.46 ms |
| — per projection | 1.06 µs | 1.03 µs |
| **64-graph `cost` item, recorded duration** | **47.6 s** | **47.6 s** |

The item itself is never re-run from a tool. Its duration is read from
`tests/_support/cost_durations.json`, which is what balances the `cost` class's
six CI shards, and it is recorded here as the "before" figure the ticket asks for.

## Conditions

| | |
|---|---|
| Recorded | 2026-09-10 |
| Machine | Apple M5, 10 cores, 32 GiB, darwin/arm64 |
| OS | macOS 26.6.2 (build 25G83) |
| Interpreters | CPython 3.13.15 and 3.14.7 (both `main`, Aug 5 2026, Clang 21.0.0) |
| Command | `just python-report-snapshot-materialization` |
| Source | branch `cor-137-speed-up-snapshot-materialization-0ou36c`, base commit `431936be` |
| Isolation | one fresh child interpreter per (minor, layout), `PYTHONHASHSEED=0`, no coverage tracer |
| Warm-up | 200 unsampled runs before every memory window; 5 before every timing |
| Timing samples | mean of 20 batches, taken untraced, from an already prepared model and compiled reads |
| Runtime | about three minutes for the whole matrix |
| Repeatability | a second whole-matrix run on the same machine moved the timings by up to 10% (Columns 3.14: 22.802 → 24.965 ms) and one memory row by 0.2% (Document 3.13 retained: 193,584 → 193,253 B); everything else was identical to the byte — the three other retained totals, every peak and transient figure, the prepared bytes, the layout-catalog figures, the tracked/reference census, and every call count |

The tables above are one recorded run. A second run is what the repeatability row
reports, and it is why the timing rows are direction only: what is stable to the
digit here is the structure — the counts and the prepared totals — and that is
also what the gated regression asserts.

## What is measured, and what is excluded

The batch is what one read pays per statement of rows: row materialization
through `CompiledRead.materialize_row`, the per-row `LevelContext`, `convert_row`
into a shared `GraphBuilder`, the observation every hydrating row takes, the key
gather and view fan-back each level performs, and `seal`.

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
