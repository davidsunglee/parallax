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
missing, malformed, or incomplete required member, a Snapshot delivery member
that is not authoritative, a capture taken from a dirty tree, a stale workload
digest, or members produced at different commits. The write-lowering member is
`non-authoritative` because its sampling protocol is its own, and verification
accepts it so. Everything else it has to say is an advisory line, printed and
never an exit status: a timing or memory ceiling exceeded, a streamed-memory arm
grown past its limit, a `uv.lock` that moved since the capture, and a producing
commit the inspected head no longer descends from. `--freshness-only` reports a
moved lock the same way and exits non-zero only where no comparison was made at
all — no single Snapshot delivery member, or provenance whose recorded
`lockDigest` is absent or not a digest — which is provenance `--verify` fails
the member for in any case. Blocking memory gates are cost-class tests, not this
verifier — `--verify` states a reading past its gate as one more advisory, on
whichever runtime read it (see *Memory gates* below); a dependency bump or a
rebase changes nothing a reading measured; and the capture budget recorded
below is why drift is stated rather than made a reason to capture again.

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
`workloadDigest` already covers the frozen manifest and the fixture and model
sources its levels are defined by, so one digest names what this cell measures
as it names what every other Snapshot cell measures. No digest names the reading
child that measures it, for the reason recorded under the manifest below. The
per-root delivery cells keep their warmed steady-state meaning: a delivery
reading's floor holds the compiled plan its 200 warm-ups established, and this
window prices that plan separately.

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

## Memory gates

`../../spec/memory-gates.yaml` is the blocking half of this evidence: one
ceiling per byte-unit reading address of the structural windows — the retained
checkpoint and the high-water mark of each of the 46 keyed-write cases, the six
acquisition levels, and the model-preparation checkpoint (106 gates, in bytes
per row or bytes), and the retained and peak readings of the eighteen geometry
reads and six cold plan compilations (48 gates, in KiB converted to bytes) —
154 in all, beside the scaling domains and the advisory allowances. The cost
class grades them, under both layouts and through the same reading children the
capture uses, in `tests/unit/tools/test_write_lowering_reading_gates.py` and
`tests/unit/tools/test_snapshot_delivery_reading_gates.py`; timing is asserted
nowhere. The gates live in a file of their own rather than in
`budget-contract.yaml` because that contract's digest is part of the
`authority` fingerprint the baseline's Snapshot member was classified under:
editing it would reclassify the retained capture or demand a third.

### Basis

Every ceiling is the rule's output, not an edit: the largest reading of the
address on either runtime in `before/`, scaled by **1.10** and rounded up to a
whole byte, and
`test_every_memory_gate_is_the_baseline_reading_under_the_stated_rule`
recomputes all 154 from `before/portfolio.json`. The headroom is the Budget
Contract's own `individualMax` for a memory cell; the run-to-run agreement
recorded under *Measured noise floor* — retained checkpoints within 2.8% and
high-water marks within 1% on this runner, and a further 1–3% between the two
runtimes, which taking the larger runtime absorbs — sits inside it. A byte
reading is a property of the interpreter's object layouts rather than of the
runner, which is why a fixed ceiling can be graded on CI's floating runner
label where an elapsed time cannot; the residual risk that a CPython patch
release or a platform allocator moves a reading by more than the headroom is
accepted, and would surface as a gate failure to be read against this basis,
never as a ceiling to relax.

The baseline is the pre-unification tree, so at the tree the gates were
introduced on most readings sit well under them: the categorical Typed
retained checkpoints by 13–22%, the geometry inserts and changed-ancestor
successors by up to 42%, the prepared model by 34%, while the Wire successor
checkpoints, the geometry reads' retained pages, and the acquisition rows
agree with the baseline within 1%. The readings above the baseline all sit
inside the headroom: `txtime.changed.document.wire` retains 3,698–3,748 B/row
against 3,648 (+1.4–2.7%), `bitemporal.interior.document.wire` +0.9%, the
Columns cold-plan checkpoints +1.5%, and the `read-depth-4` and
`read-depth-8` peaks +3.1% and +4.7%. Each is carried to Phase 5. The gates'
sensitivity at this tree is therefore the headroom plus whatever the
unification saved on the address, and the after-capture is the basis to
re-derive them from under the same rule.

### Scaling domains

The acquisition levels per layout are a scaling domain: per-row retained and
transient readings at 8, 32, and 128 rows must not increase with the row
count, since the resolving read's planning and compilation are a fixed cost
the rows amortize and nothing production keeps is sized by rows squared. The
geometry families are gated per level under both layouts, which bounds each
family's slope at its frozen levels; the read side's O(NW) positional
expansion (`sparse-64` retains 36 KiB for 32 roots carrying one populated leaf)
and the write side's O(W) changed-ancestor cost are inside those ceilings, not
separately gated.

### Sensitivity

Each seed below is a monkeypatch inside the gate suite's child, at the seam it
names, and is proved to trip the gate it targets. Figures are from the tree
the gates were introduced on (2026-09-17, CPython 3.14.7, this runner) and
are readings, not evidence.

| Seed | Seam | Effect | Proved on |
|---|---|---|---|
| A per-instruction registry keeping a detached copy of every prepared row, accumulating | `prepare_typed_write` / `prepare_wire_write` | retained +964 to +1,064 B/row on the categorical cases, +5,080 on `width-64` | the three Wire successor cases, which sit within one row of their gate |
| A second formed model retained beside the first | `DomainModel` formation inside the model window | retained 427 KB to 823 KB (formation is 396 KB of the 427; the catalog, codec, and planner are 31 KB) | `model.prepared` |
| Four complete mutable copies of every document bind held across the driver dump | `serialize` | peak +4.5 to +6.2 KB per copy; one copy leaves every case inside its gate (`width-64.document` 30,306 against 33,645; `many-32.columns` 34,106 against 42,269) | the three widest cases, at four copies |
| A resolving port keeping every row it answered | `projected_rows` | retained +1,000 to +1,160 B/row at every level | `rows-32.columns`, `rows-128.document` |
| A key tuple sized by the row count kept per row | `projected_rows` | retained +120 B/row at 8 rows, +1,080 at 128: the per-row readings stop falling | the Columns domain's monotonicity and `rows-128.columns` |
| A reduced dictionary kept beside every positional row | `build_positional_object` | retained +17.3 KiB at `depth-1`, +148 KiB at `sparse-64` (the full declared width), +190 KiB at `many-32` | `depth-1`, `sparse-64`, `many-32`, both layouts |
| A detached copy of the answered rows alive during materialization, replaced per statement | `projected_rows` | peak +23 to +28 KiB at `depth-1`, +216 KiB at `width-64`; the retained page is not raised | `depth-1`, `width-64`, both layouts |
| A second plan cache compiling every plan again | `ColdPlan.plan` | retained 16.2 to 32.6 KiB | every plan level, both layouts |

What the gates cannot see is pinned beside them: lowering the settled plan a
second time (`stream_lowered` twice on `txtime.changed.document.wire`) leaves
the checkpoint at 3,698–3,748 B/row and the high-water mark at 15,030 B/row —
neither gate moves — while the `applyPatches` pass observation goes from one
per row to two and the elapsed median from 227 to 270 µs/row (+19%), which the
advisory comparison would report as `slower`, past the 5% allowance and the
±15% floor. A duplicate traversal that allocates and frees inside a window is
visible only to the advisories; a transient copy under the headroom is
invisible to the peak gate; and a retained duplicate smaller than the slack
the unification opened under a gate is invisible to that gate until Phase 5
re-derives it.

### Ownership

`tests/unit/_memory_gate_support.py` names the cost item owning each gate;
`tests/unit/test_scheduling_partition.py` grades that every named item is
collected in the cost class and that the owners partition the 154 gates, so a
gate is never owned by a report member's registration. The cost class is
CI-owned (`python-check-cost`, six shards) and outside `just check`.

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

Produced from clean commit `b7abe2d055fd` (`docs(cost): keep the baseline's
historical verify result`) by `uv run --project languages/python python
languages/python/tools/cost_report.py --out /tmp/cor-158-before-b7abe2d0`,
2026-09-16 19:47–20:56 EDT, on Mac17,4 (Apple M5, 10 cores, 32 GiB, macOS
26.6.2) with CPython 3.14.7 and 3.13.15 and PostgreSQL 18.6
(`postgres:18.6-alpine` through Testcontainers), then retained here unchanged.
All four members name that commit and a clean tree, and none carries an
incomplete cell or an error. The Snapshot delivery member is `authoritative`;
the other three are `non-authoritative` because their sampling protocols are
their own. Every member's `uv.lock` digest matches the capture checkout. This
is the Phase 1 baseline: it is captured once and is the comparison base for the
after-capture.

| Member | Authority | Runtimes | Readings | Within | Outside |
|---|---|---|---:|---:|---:|
| snapshot-delivery | authoritative | 3.13, 3.14 | 324 | 72 | 18 |
| lifecycle-overhead | non-authoritative | 3.14 | 87 | 3 | 12 |
| instance-state | non-authoritative | 3.13, 3.14 | 624 | 4 | 4 |
| write-lowering | non-authoritative | 3.13, 3.14 | 962 | — | — |

`cost_report.py --verify before/portfolio.json` exits 0 and reports twenty
advisories, verbatim:

```text
advisory: conventional-fanout.providerFreeCpu.eager.maxMs is outside its timing ceiling
advisory: conventional-fanout.providerFreeCpu.eager.minRootsPerSecond is outside its timing ceiling
advisory: duplicate-include.live.page32.minRootsPerSecond is outside its timing ceiling
advisory: duplicate-include.providerFreeCpu.eager.maxMs is outside its timing ceiling
advisory: duplicate-include.providerFreeCpu.eager.minRootsPerSecond is outside its timing ceiling
advisory: duplicate-include.providerFreeCpu.page32.maxMs is outside its timing ceiling
advisory: duplicate-include.providerFreeCpu.page32.minRootsPerSecond is outside its timing ceiling
advisory: document-heavy.live.eager.maxMs is outside its timing ceiling
advisory: document-heavy.live.eager.minRootsPerSecond is outside its timing ceiling
advisory: document-heavy.live.page32.maxMs is outside its timing ceiling
advisory: document-heavy.live.page32.minRootsPerSecond is outside its timing ceiling
advisory: document-heavy.live.page128.maxMs is outside its timing ceiling
advisory: document-heavy.live.page128.minRootsPerSecond is outside its timing ceiling
advisory: versioned-document.live.eager.maxMs is outside its timing ceiling
advisory: versioned-document.live.eager.minRootsPerSecond is outside its timing ceiling
advisory: versioned-document.live.page32.maxMs is outside its timing ceiling
advisory: versioned-document.live.page32.minRootsPerSecond is outside its timing ceiling
advisory: versioned-document.live.page128.maxMs is outside its timing ceiling
advisory: document-heavy.streamedMemory.page128PeakKiB grows 37.865 KiB between memory arms
advisory: bitemporal-current.streamedMemory.page32PeakKiB grows 16.162 KiB between memory arms
```

Eighteen timing ceilings are exceeded on the authority runtime and two
streamed-memory arms grow past the 16 KiB limit. The `document-heavy` page-128
growth is pre-existing in the historical `db56a19e` portfolio (37.79 KiB there);
the `bitemporal-current` page-32 growth (16.162 KiB) is 0.16 KiB over its limit
and was within it in the earlier `572fa944` capture. No limit was relaxed to
obtain this capture; each outcome is recorded as the advisory it is, and the
blocking memory gates are the cost class's.

### Measured noise floor

An earlier capture of the same manifest's categorical, geometry, acquisition,
model, delivery, stress, and geometry-read cells was taken from `572fa944` on
this runner at 13:42–14:43 EDT the same day, before the changed-ancestor family
and the read-plan window existed; it is not retained, and this section is what
remains of it. A cell-by-cell `--compare` of that capture against this one
paired 1,425 cells with a median delta of 0.0% and a symmetric scatter: 219
cells slower by more than 5% and 221 faster, tenth percentile −8.9%, ninetieth
+14.8%. Nothing distinguishes either run as disturbed; that spread is the
run-to-run noise of timing on this machine and commit family across an hour of
capture, and it is wider than the 5% allowance the two-run trial above
supported. The after-capture's timing deltas must be read against this floor:
a per-cell timing delta inside roughly ±15% is not evidence on its own, and a
timing claim rests on the direction agreeing across a family of cells and both
runtimes, not on one cell crossing 5%.

Memory cells, which the blocking gates are stated over, agree far more closely
and are characterized here separately. Of the 148 paired Snapshot memory cells,
119 agreed exactly and 138 within 3%; every eager-memory, stress, geometry-read,
and read-plan cell agreed within 2.2%, and the ten outside 3% are all
streamed-memory `retainedKiB` and `page1PeakKiB` cells whose values are a few
KiB, where a 1–5 KiB swing between two drains is 3–112% (`versioned-document
.streamedMemory.retainedKiB`: 4.73 against 10.01 KiB on 3.13). Of the 180
paired write memory cells, 87 of 90 retained checkpoints agreed within 3% and
every pass observation agreed exactly, while every keyed-write high-water mark
in this capture is 4,184 B/row higher than in the earlier one — the same
constant on every categorical and geometry case and on both runtimes — and
`model.prepared` retains about 205 KB more. The prepared model gained six
Transaction-Time-Only twin Entities between the two captures, which accounts
for the model checkpoint; the constant per-row offset is coincident with that
growth and is recorded as an observation, not attributed. Phase 5 compares
against this capture alone.

### Keyed writes per row (`keyed-write` window)

Median of nine samples; retained is one checkpoint after 200 warm-ups. Pass
observations are per row on either runtime (they agree exactly).

| Case | 3.13 µs | 3.13 peak B | 3.13 retained B | 3.14 µs | 3.14 peak B | 3.14 retained B | encodeDocument / encodeMany / applyPatches / detachJsonContainer |
|---|---:|---:|---:|---:|---:|---:|---|
| txtime.opening.columns.typed | 193.2 | 17370 | 3618 | 206.5 | 17882 | 3674 | 4 / 1 / 0 / 2 |
| txtime.opening.columns.wire | 173.2 | 16266 | 2612 | 193.5 | 16818 | 2660 | 4 / 1 / 0 / 2 |
| txtime.opening.document.typed | 218.8 | 17370 | 3618 | 219.8 | 17882 | 3674 | 5 / 1 / 0 / 11 |
| txtime.opening.document.wire | 185.9 | 16266 | 2612 | 196.8 | 16818 | 2610 | 5 / 1 / 0 / 11 |
| txtime.changed.columns.typed | 219.9 | 16594 | 4584 | 241.4 | 16970 | 4780 | 4 / 1 / 0 / 2 |
| txtime.changed.columns.wire | 200.4 | 15522 | 3560 | 220.2 | 15934 | 3748 | 4 / 1 / 0 / 2 |
| txtime.changed.document.typed | 256.3 | 16594 | 4634 | 258.2 | 16970 | 4730 | 4 / 1 / 1 / 22 |
| txtime.changed.document.wire | 222.1 | 15522 | 3510 | 249.4 | 15934 | 3648 | 4 / 1 / 1 / 22 |
| txtime.unchanged.columns.typed | 222.2 | 16594 | 4634 | 242.6 | 16970 | 4780 | 4 / 1 / 0 / 2 |
| txtime.unchanged.columns.wire | 204.8 | 15522 | 3610 | 229.1 | 15934 | 3748 | 4 / 1 / 0 / 2 |
| txtime.unchanged.document.typed | 234.7 | 16594 | 4634 | 254.9 | 16970 | 4780 | 2 / 1 / 1 / 16 |
| txtime.unchanged.document.wire | 213.9 | 15522 | 3560 | 230.8 | 15934 | 3698 | 2 / 1 / 1 / 16 |
| plain.changed.columns.typed | 182.2 | 17098 | 3898 | 206.5 | 17658 | 3986 | 4 / 1 / 0 / 2 |
| plain.changed.columns.wire | 173.7 | 16026 | 2874 | 187.7 | 16622 | 2954 | 4 / 1 / 0 / 2 |
| plain.changed.document.typed | 198.9 | 17098 | 3848 | 215.4 | 17658 | 3936 | 4 / 1 / 0 / 2 |
| plain.changed.document.wire | 193.4 | 16026 | 2874 | 212.4 | 16622 | 2954 | 4 / 1 / 0 / 2 |
| bitemporal.interior.columns.typed | 328.2 | 17612 | 6620 | 366.1 | 17212 | 6632 | 12 / 3 / 0 / 6 |
| bitemporal.interior.columns.wire | 332.4 | 16656 | 5642 | 345.6 | 16274 | 5746 | 12 / 3 / 0 / 6 |
| bitemporal.interior.document.typed | 343.0 | 18709 | 6570 | 367.3 | 18031 | 6832 | 4 / 1 / 1 / 44 |
| bitemporal.interior.document.wire | 349.1 | 17703 | 5592 | 363.5 | 17323 | 5746 | 4 / 1 / 1 / 44 |

An unchanged-document successor costs what a changed one costs under either
layout: the retained predecessor document is detached whole rather than reused,
which the sixteen `detachJsonContainer` returns per row make visible.

### Geometry inserts and changed-ancestor updates per row (`keyed-write` window, Typed)

| Case | 3.13 µs | 3.13 peak B | 3.13 retained B | 3.14 µs | 3.14 peak B | 3.14 retained B | encodeDocument / encodeMany / applyPatches / detachJsonContainer |
|---|---:|---:|---:|---:|---:|---:|---|
| geometry.depth-1.columns | 205.3 | 16338 | 3162 | 206.3 | 16802 | 3218 | 3 / 1 / 0 / 0 |
| geometry.depth-1.document | 208.5 | 16338 | 3112 | 211.1 | 16802 | 3168 | 4 / 1 / 0 / 16 |
| geometry.depth-4.columns | 253.1 | 18730 | 4336 | 241.1 | 19290 | 4442 | 6 / 1 / 0 / 30 |
| geometry.depth-4.document | 260.3 | 18730 | 4336 | 258.8 | 19290 | 4392 | 7 / 1 / 0 / 61 |
| geometry.depth-8.columns | 330.6 | 22682 | 6018 | 316.4 | 23386 | 6024 | 10 / 1 / 0 / 140 |
| geometry.depth-8.document | 341.7 | 22682 | 6018 | 326.7 | 23386 | 6024 | 11 / 1 / 0 / 191 |
| geometry.many-0.columns | 166.5 | 15314 | 2208 | 183.8 | 15770 | 2256 | 1 / 1 / 0 / 0 |
| geometry.many-0.document | 177.8 | 15314 | 2258 | 178.2 | 15770 | 2256 | 2 / 1 / 0 / 6 |
| geometry.many-8.columns | 277.2 | 18866 | 5640 | 308.2 | 19330 | 5646 | 9 / 1 / 0 / 0 |
| geometry.many-8.document | 291.0 | 18866 | 5640 | 339.7 | 19330 | 5696 | 10 / 1 / 0 / 46 |
| geometry.many-32.columns | 561.2 | 38074 | 15816 | 631.5 | 38426 | 15822 | 33 / 1 / 0 / 0 |
| geometry.many-32.document | 588.2 | 38637 | 15816 | 732.3 | 38989 | 15872 | 34 / 1 / 0 / 166 |
| geometry.width-16.columns | 265.0 | 18018 | 4742 | 367.6 | 18482 | 4898 | 3 / 1 / 0 / 0 |
| geometry.width-16.document | 273.2 | 18018 | 4792 | 396.8 | 18482 | 4848 | 4 / 1 / 0 / 52 |
| geometry.width-64.columns | 592.2 | 29130 | 11512 | 812.1 | 29466 | 11518 | 3 / 1 / 0 / 0 |
| geometry.width-64.document | 619.1 | 30234 | 11562 | 804.8 | 30586 | 11618 | 4 / 1 / 0 / 196 |
| geometry.sparse-64.columns | 235.9 | 16218 | 3062 | 350.9 | 16682 | 3168 | 3 / 1 / 0 / 0 |
| geometry.sparse-64.document | 239.9 | 16218 | 3112 | 321.8 | 16682 | 3118 | 4 / 1 / 0 / 7 |
| ancestor.depth-1.columns | 238.6 | 16122 | 4226 | 337.1 | 16498 | 4272 | 3 / 1 / 0 / 0 |
| ancestor.depth-1.document | 244.8 | 16122 | 4226 | 361.6 | 16498 | 4372 | 3 / 1 / 1 / 33 |
| ancestor.width-16.columns | 310.6 | 17802 | 5856 | 447.6 | 18178 | 6002 | 3 / 1 / 0 / 0 |
| ancestor.width-16.document | 333.5 | 17802 | 5806 | 479.1 | 18178 | 6002 | 3 / 1 / 1 / 105 |
| ancestor.width-64.columns | 650.5 | 31483 | 12626 | 872.9 | 31835 | 12772 | 3 / 1 / 0 / 0 |
| ancestor.width-64.document | 697.8 | 33140 | 12576 | 916.0 | 33692 | 12722 | 3 / 1 / 1 / 393 |
| ancestor.sparse-64.columns | 281.7 | 16002 | 4226 | 411.2 | 16378 | 4322 | 3 / 1 / 0 / 0 |
| ancestor.sparse-64.document | 291.2 | 16002 | 4176 | 433.0 | 16378 | 4372 | 3 / 1 / 1 / 15 |

Retained bytes at the settled checkpoint are the same under both layouts at
every level, as the managed representation is layout-independent. Under
Relational Document layout a changed ancestor's `detachJsonContainer` count
tracks the replaced occurrence's declared width (33 at four leaves, 393 at
sixty-four), which is the whole-document detach a successor patch pays today.
The wide and sparse levels run substantially slower on 3.14 than on 3.13 (up to
1.5x at `sparse-64`); the difference sits in the Typed ingress of a wide
instance and is recorded as an observation, not attributed.

### Predicate acquisition per resolved row (`predicate-acquisition` window)

| Case | 3.13 µs | 3.13 peak B | 3.13 retained B | 3.14 µs | 3.14 peak B | 3.14 retained B |
|---|---:|---:|---:|---:|---:|---:|
| acquisition.rows-8.columns | 147.8 | 5920 | 2373 | 114.9 | 6239 | 2572 |
| acquisition.rows-32.columns | 56.9 | 4061 | 1745 | 73.4 | 4227 | 1807 |
| acquisition.rows-128.columns | 49.2 | 3530 | 1581 | 66.8 | 3681 | 1618 |
| acquisition.rows-8.document | 77.7 | 7948 | 3601 | 98.7 | 8226 | 3803 |
| acquisition.rows-32.document | 57.2 | 6224 | 2932 | 71.6 | 6415 | 3000 |
| acquisition.rows-128.document | 51.7 | 5687 | 2765 | 60.6 | 5853 | 2810 |

Per-row figures fall with row count as the read's fixed planning and
compilation cost is amortized; the difference between the layouts is the retained
raw Structured Column document each Relational Document row carries beside its
decoded members.

### Model preparation (`model-preparation` window)

| Runtime | µs | peak B | retained B |
|---|---:|---:|---:|
| 3.13 | 4482.2 | 652472 | 635624 |
| 3.14 | 6119.2 | 655608 | 649080 |

### Geometry reads (`provider-free-delivery` window, 32 roots)

| Level | Layout | 3.13 µs/root | 3.13 peak KiB | 3.13 retained KiB | 3.14 µs/root | 3.14 peak KiB | 3.14 retained KiB |
|---|---|---:|---:|---:|---:|---:|---:|
| depth-1 | columns | 33.48 | 108.7 | 50.8 | 31.58 | 106.2 | 51.1 |
| depth-1 | document | 33.03 | 108.7 | 50.8 | 31.96 | 106.1 | 51.1 |
| depth-4 | columns | 55.22 | 154.3 | 88.0 | 54.81 | 155.1 | 88.2 |
| depth-4 | document | 54.47 | 153.7 | 88.0 | 57.22 | 153.6 | 88.2 |
| depth-8 | columns | 90.43 | 222.8 | 137.5 | 93.34 | 225.7 | 137.7 |
| depth-8 | document | 95.17 | 220.8 | 137.5 | 92.50 | 223.6 | 137.7 |
| many-0 | columns | 23.33 | 67.2 | 24.1 | 23.76 | 65.8 | 24.3 |
| many-0 | document | 23.79 | 73.0 | 24.1 | 23.19 | 71.5 | 24.3 |
| many-8 | columns | 59.62 | 205.0 | 125.1 | 55.90 | 208.0 | 125.3 |
| many-8 | document | 58.56 | 203.5 | 125.1 | 58.38 | 206.8 | 125.3 |
| many-32 | columns | 166.70 | 636.2 | 428.1 | 160.18 | 640.2 | 428.3 |
| many-32 | document | 159.79 | 633.8 | 428.1 | 159.90 | 637.9 | 428.3 |
| width-16 | columns | 59.33 | 220.5 | 136.7 | 58.87 | 223.9 | 137.0 |
| width-16 | document | 58.62 | 223.9 | 136.7 | 57.96 | 227.2 | 137.0 |
| width-64 | columns | 156.98 | 766.9 | 480.2 | 160.50 | 770.3 | 480.5 |
| width-64 | document | 159.29 | 770.4 | 480.2 | 161.28 | 773.6 | 480.5 |
| sparse-64 | columns | 50.40 | 139.0 | 35.9 | 48.01 | 136.4 | 36.2 |
| sparse-64 | document | 46.91 | 139.0 | 35.9 | 46.01 | 136.4 | 36.2 |

The retained page grows with the expanded positional output rather than with
the authored input: `sparse-64` retains 36 KiB for 32 roots carrying one
populated leaf each, against 24 KiB at `many-0`, because every declared
position is materialized.

### Read-plan compilation (`read-plan-compilation` window)

| Level | Layout | 3.13 µs | 3.13 peak KiB | 3.13 retained KiB | 3.14 µs | 3.14 peak KiB | 3.14 retained KiB |
|---|---|---:|---:|---:|---:|---:|---:|
| depth-1 | columns | 120.5 | 22.55 | 14.55 | 125.1 | 23.57 | 15.94 |
| depth-1 | document | 122.3 | 23.01 | 15.33 | 119.5 | 24.40 | 16.75 |
| depth-8 | columns | 138.3 | 22.55 | 14.55 | 118.2 | 23.57 | 15.94 |
| depth-8 | document | 156.3 | 23.01 | 15.33 | 114.8 | 24.40 | 16.75 |
| width-64 | columns | 169.1 | 22.55 | 14.55 | 118.1 | 23.57 | 15.94 |
| width-64 | document | 132.9 | 23.01 | 15.33 | 114.8 | 24.40 | 16.75 |

The cold compiled plan is the same size at every level under a given layout: a
whole-table instance read's plan retains its top-level fan-out only, because
nested occurrence shapes are referenced from accepted metadata rather than
copied into the plan. The Columns-to-Document difference (0.8 KiB) is the
shared-document fan-out, which is what a later change to compiled-read
residency should be read against.

### Preserved positional-materialization cells (authority runtime)

`stress-columns`: 6.2 µs/projection, 604.4 retained B/projection, 128.0
transient B/projection, 45.8 KiB peak for 64 KiB, 41.4 KiB prepared set.
`stress-document`: 7.1 µs/projection, 620.4 retained B/projection, 192.0
transient B/projection, 50.8 KiB peak for 64 KiB, 65.6 KiB prepared set. Every
delivery and stress ceiling other than the eighteen timing cells and the two
scaling arms named above is within its limit.
