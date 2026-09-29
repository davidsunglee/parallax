# Structural metadata evidence

The read and write cost evidence for the structural-metadata unification: the
protocol every capture under this directory follows, the frozen workload
manifest, what each window contains and excludes, and the limits of what the
measurements can show. `before/` is the clean pre-optimization baseline,
`after/` the clean capture of the unified implementation under the same
protocol, on the same runner and interpreters, and `recovered/` the one
capture of the tree that recovers the read and predicate-acquisition time the
unification cost, under the same protocol again; `after/comparison.md` is the
cell-by-cell rendering of `tools/cost_report.py --compare before/portfolio.json
after/portfolio.json`, which *After capture* below reads, and
`recovered/comparison-before.md` and `recovered/comparison-after.md` are the
renderings of `recovered/` against each, which *Recovered capture* reads.

The portfolio under `recovered/` is the repository's canonical current cost
portfolio: `just python-check-evidence` verifies the members `verify` in
`tools/cost_report.py` names from any clone, against the committed inputs, and
exits non-zero if they do not verify; the memory gates are derived from it.
`before/` is retained unchanged as the recovery reference and `after/` as the
fixed regression baseline; both are comparison bases rather than verification
inputs, held to their original provenance by the cost class. Every check of this evidence is in
the cost class, which CI runs on every change and `just check` omits. Only
`recovered/` carries the `conditions.json` and `durations.json` sidecars the
collector writes beside a capture; `before/` and `after/` predate both writers
and carry neither, which is why `--require-compatible` reaches no source digest
or interpreter identity against them. The historical captures under
`../write-lowering-envelope/` and `../snapshot-delivery-envelope/` keep their
original names, protocols, and producing commits; nothing here is compared
against them, because their write window stopped at `LoweredStatement` and their
read matrix ran on one runtime.

## Protocol

Every reading is taken in a child interpreter of its own with `PYTHONHASHSEED=0`,
on every supported CPython minor (3.13 and 3.14) — the leaf-type families below
on the newest alone — by `just python-report-cost` on one runner with no
competing measurement. A reading names its runtime and its
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

`cost_report.py --verify` fails only for evidence that is not evidence, and
everything else it has to say is an advisory line, printed and never an exit
status; the tool's documentation names each failure, each advisory, and what
`--freshness-only` fails on. Blocking memory gates are cost-class tests, not
this verifier — `--verify` states a reading past its gate as one more advisory,
on whichever runtime read it (see *Memory gates* below); a dependency bump or a
rebase changes nothing a reading measured; and the capture budget recorded
below is why drift is stated rather than made a reason to capture again.

Every envelope carries the Budget Contract it was classified against, as the
authored YAML text whose bytes its `budgetContractDigest` hashes, so `--verify`
reconstructs the contract that was in force at capture from the envelope alone.
The producing commit stays in provenance as a recorded fact rather than a tree
to resolve: `--verify` reads it to refuse a portfolio whose members name
different commits, and the not-an-ancestor advisory asks whether the inspected
head still descends from it. Pairing under `--compare` never reads it.
Reconstructing the contract and grading the capture against it read the envelope
alone, so they run identically in a shallow clone, in a fresh one, and here;
only that advisory consults history, and a clone too shallow to hold the commit
prints it. The alternative — keeping every producing commit reachable, by capturing on `main`
or tagging each one — was weighed and refused: it makes a retained capture
verifiable only where its branch survives, which is precisely what the
squash-merged captures under this directory had already stopped being. The
authority label a verified envelope carries therefore attests to the envelope's
internal consistency, not to the unforgeability of the reading: the digest binds
the embedded contract to the classification, and the evidence's integrity rests
on review of these tracked files, exactly as it did when the contract bytes were
read from the producing commit.

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
| `keyed-write` | write-lowering | one public keyed verb (`tx.insert`, `tx.update`, `tx.update_until`, or its `tx.wire` peer) until `transact` returns: Typed row serialization or the caller's Wire document; preparation; effective-change classification and buffering; the pre-commit flush's planning, settlement, and SQL lowering; production PostgreSQL bind adaptation; psycopg's own transformer dump of every bind, document binds included; the commit | the read of the row a write revises, earlier in the same transaction, and the Typed `edit` or Wire changes document authored against it; database execution and network time |
| `predicate-acquisition` | write-lowering | one public `tx.wire.update_until_where` of a Bitemporal `updateUntil` over the caller's target and changes documents: document capture, instruction deserialization and preparation; the resolving read's planning and compilation; row publication and materialization; per-row no-op selection; predecessor ownership establishment from freshly composed mutable rows; aligned column construction; buffering of the Materialized Write Group | the flush and driver serialization — the transaction is abandoned after the checkpoint |
| `model-preparation` | write-lowering | one `prepare_model` over the whole structural write model: formation from the declared Entity Classes, layouts, row codec, graph construction, and write planner | the Entity Class declarations themselves, which are retained by the importing module |
| `wire-insert-response` | write-lowering | one public `tx.wire.insert` of a nested, polymorphic Create Payload inside an open transaction, from the payload arriving to the frozen Wire node it answers | the commit that flushes the buffered row, its lowering, and driver serialization |
| `live-delivery` | snapshot-delivery | a connected Wire find or stream against PostgreSQL, parsing included | nothing |
| `provider-free-delivery` | snapshot-delivery | a Wire find over already-parsed provider rows through production planning, materialization, and publication | parsing and provider work |
| `positional-materialization` | snapshot-delivery | production's Page build (`Materializer._build_page`) over an already executed root statement: root row conversion, fetch-template rendering, provider-free fetch execution and its Database Call bookkeeping, conversion and attachment, and read-source retention (`_retained`), to a finished Page; `preparedSetKiB` prices one uncached `ReadPlanCache.plan` | planning, root statement execution (`Materializer._read_root`), and publication |
| `read-plan-compilation` | snapshot-delivery | one whole-table instance read planned through `ReadPlanCache.plan` into an empty cache of production capacity: deep-fetch planning, `compile_read`, and the prepared level binding the cache then retains, which is the growth from an empty cache to one compiled entry | the cache itself, composed before the window as production composes it when a handle connects; model preparation and query validation (`preflight`), likewise composed once outside it; statement execution, materialization, and publication |
| `read-plan-reuse` | snapshot-delivery | one read looked up on the read plan cache already holding its compiled entry | planning, compilation, execution, and materialization |
| `control-delivery` | snapshot-delivery | a Wire or Typed find or stream over already-parsed provider rows through production planning, materialization, and publication; the Typed result is never projected | parsing and provider work; the root and its port, composed before the window |
| `result-held-metadata` | snapshot-delivery | the bytes one eager Typed result keeps reachable, read with its root open and sharing the prepared model and again with the root closed and the result the sole owner of whatever it still reaches | nothing but what the result does not reach |

Retained checkpoints: `keyed-write` reads what the verb kept — the difference
between a sample taken after the read and one taken once the verb has buffered,
both inside the transaction body and before the flush; `predicate-acquisition`
samples inside the transaction body with the group buffered, before any flush;
`model-preparation` samples with the prepared selection alive; a geometry or
leaf-type read samples with the delivered results alive;
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

The keyed-write source stays alive across the window as production keeps it: an
update's source is the node the transaction's read published, edited by a Typed
caller or handed with a changes document by a Wire one, and an insert's is the
instance or payload the fixture holds. None is counted by the retained increment,
which starts after the read, so what it sees is what the verb built and
production still reaches until the flush. The keyed port composes its stored row
per statement and keeps none. The acquisition port composes each resolving row
when the statement runs and keeps none, and the handle and the caller's target
and changes documents are composed once per reading outside the window, so the
checkpoint sees the retained columns, the retained encoded documents, and the
buffered group rather than a fixture-held second batch. The provider-free read
ports likewise compose each row per statement.

## Workload manifest

Every identity and numeric level below is frozen in
`parallax.conformance.workloads` (`GEOMETRY_LEVELS`, `ACQUISITION_LEVELS`,
`ANCESTOR_LEVEL_IDS`, `READ_GEOMETRY_ROOTS`, `STRUCTURAL_LAYOUTS`) and enters the
write member's `workloadDigest` through `structural_digest()` together with the
bytes of the fixture modules, and the Snapshot member's through
`workload_digest()` beside the catalog fixtures and models. The leaf-type
families' identity enters both members' digests through `leaf_type_digest()`
rather than `structural_digest()`. Those digests name
what was measured; they deliberately do not name the instruments that measured
it. A capture costs about an hour of runner time. The unification budgeted
exactly two — the baseline under `before/` and the after-capture beside it —
and the recovery capture under `recovered/` was authorized separately by the
owner once the recovery's implementation and review had closed; under either
budget no instrument or harness edit made after a capture may force another
through a hash. Whether two captures remain comparable across such an edit is a
judgement recorded in this README beside the captures, and where it is in doubt
the original producing revision can be reproduced on the final runner. The levels
were chosen from diagnostic trial runs on the capture runner and then frozen;
the trials are not part of the baseline.

### Categorical keyed writes — 20 cases per runtime

Each Entity carries a One Value Object (`address`) nesting a One (`geo`) and a
Many (`tags`, two elements) beside a primary key and a string leaf, under both
storage layouts. Every case addresses one row, and every transaction runs at the
default Optimistic preference, so a temporal close carries its milestone gate.

| Family | Temporal profile | Operation | Predecessor evidence | Statements |
|---|---|---|---|---:|
| `txtime.opening` | Transaction-Time-Only | `insert` | none | 1 |
| `txtime.changed` | Transaction-Time-Only | `update`, every member changed | the row read in the same transaction: its complete predecessor row, and the retained document under Relational Document | 2 |
| `txtime.unchanged` | Transaction-Time-Only | `update` restating the predecessor exactly | as above | 0: every member is restored, so the verb buffers nothing |
| `plain.changed` | non-temporal, unversioned | `update`, every member changed | the row read in the same transaction, which licenses the object claim | 1 |
| `bitemporal.interior` | Bitemporal | `updateUntil` over `[2026-03-01, 2026-09-01)`, strictly inside the predecessor's open Valid interval | the row read in the same transaction at the latest Valid Time, with both axes | 4: close, carried head, changed middle, carried tail |

Each family runs as Typed and Wire ingress under Columns and Relational Document
layout, twelve Transaction-Time-Only cases and eight others. The Typed and Wire
twins of a case lower to identical statements and binds, which the fixture
suite proves.

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

### Before/after controls — the `control` group and two write cases

The controls price what a change to result publication could move without
being the feature itself, so a before capture and an after capture pair every
one of them. `tests/unit/_delivery_control_support.py` spells the Snapshot
member's control matrix once, and the write member's two control cases sit
beside its lowering matrix in `tests/unit/_write_lowering_support.py`.

| Control | Addresses | Window |
|---|---|---|
| Unprojected Typed delivery beside direct Wire delivery | `control-delivery-<workload>`, cells `<lane>.<form>.roots<n>.<metric>` over `conventional-fanout` and `duplicate-include`, lanes `wire` and `typed`, forms `eager` and `page32`, `n` at each memory scaling arm, metrics `elapsedUs`, `peakKiB`, `retainedKiB` | `control-delivery` |
| Guarded include planning and delivery | `control-guarded-<width>` for widths 1, 2, and 3 — `Dog.owner`, then `Cat.owner`, then `WildBoar.owner`, each continued by `pets` narrowed to `Cat` — cells `plan.cold.<metric>`, `plan.warm.elapsedUs`, `plan.warm.retainedKiB`, and `<lane>.eager.roots<n>.<metric>` at 32 and 256 roots | `read-plan-compilation`, `read-plan-reuse`, `control-delivery` |
| Result-held metadata | `control-held`, cells `<model>.<state>.retainedKiB` over the `small` orders model and the `large` geometry model, `shared` with the root open and `closed` after it | `result-held-metadata` |
| Public Wire insert response | `response.insert.family.wire`: one `tx.wire.insert` of a `Dog` row of a table-per-hierarchy family carrying a One nesting a One and a Many, per-row units | `wire-insert-response` |
| Family-bearing preparation | `model.prepared.family`: one `prepare_model` over that family alone | `model-preparation` |

A Snapshot envelope is exact with the whole control group or, as the retained
captures are, without it; `--verify --require-member snapshot-delivery` and
`--require-member write-lowering` accept the current matrices alone, and
`--compare --require-compatible` pairs every control before any arithmetic.

### Predicate-acquisition families — 3 levels per layout

A Bitemporal Entity with the categorical Value Object shape, under each layout.
The Wire target selects `id >= 1` and the changes document assigns `title` a
value every resolved row differs from, over the interior window above, so no-op
elimination retains every row. Levels resolve 8, 32, and 128 current milestones
(`acquisition.rows-<n>.<layout>`, per-row units). This companion measures the
Wire ingress once per layout and does not multiply ingress forms.

### Leaf-type families — 12 types, three flows, both layouts

Every declarable Neutral Type is measured at the `width-64` geometry: String,
the control, and the eleven types read against it
(`workloads.LEAF_TYPE_IDS`). Json is not declarable as a leaf, which is why the
limits below exclude its payload size. A type's Entities declare the level's
root occurrence and its two Many elements with all 64 leaves of that type and
populated, under each layout. The leaves live inside structured documents under
both layouts, and every stored row spells them in canonical Wire form, so two
types differ only in how production decodes, compares, publishes, and encodes a
leaf. `tests/unit/_leaf_type_support.py` owns the model, the value recipes, and
the rows.

| Flow | Addresses | Window |
|---|---|---|
| Provider-free read of 32 roots | `leaf-<type>`, cells `<layout>.elapsedUsPerRoot`, `<layout>.peakKiB`, `<layout>.retainedKiB` | `provider-free-delivery` |
| Keyed insert, Typed and Wire | `leaf.<type>.<layout>.<ingress>`, per-row units | `keyed-write` |
| Predicate acquisition resolving 8 rows | `leaf-acquisition.<type>.rows-8.<layout>`, per-row units | `predicate-acquisition` |

Where a geometry cell already measures the structure, it is the String control:
`read-width-64` for the read and `geometry.width-64.<layout>.typed` for the
Typed insert. The fixture suite proves the String type's stored and Wire rows
equal to that geometry level's. The Wire insert and the acquisition, which no
geometry case measures at this level, read String cells of their own. The acquisition's changes document
assigns the root occurrence a value every resolved row differs from, over the
interior window above.

The families are read on the newest supported CPython minor alone
(`workloads.LEAF_TYPE_RUNTIMES`). An envelope carrying them is exact only with
every leaf-type reading on that runtime and none on another. A capture taken
before them verifies without them, but `--require-member` accepts the current
matrices alone, which include them. They carry no Budget Contract ceiling; their
memory gates are derived under the rule in *Basis* from the first capture that
reads them.

### Preserved delivery workloads

The Budget Contract's `conventional-fanout`, `duplicate-include`,
`document-heavy`, `versioned-document`, and `bitemporal-current` delivery cells
and the `stress-columns` / `stress-document` positional-materialization cells
keep their workloads, now on both supported minors; the contract's ceilings are
compared on the authority runtime alone, and the other runtime's readings stand
beside them without comparisons. The stress rows keep the recipe `m-perf-bench`
fixes. Their documents stay deferred until publication, which the
positional-materialization window excludes, so the window decodes no document
leaf.

A live streamed-memory reading (`streamedMemory.*`) drains the workload once
untraced as a warm-up, without collecting at page boundaries, and then traces a
second drain that holds only the last root and collects at each page boundary as
the Budget Contract's memory sampling directs. A `page<n>PeakKiB` reading drains
at page size `n`; `retainedKiB` drains at page size 128
(`snapshot_delivery_reading.STREAMED_RETAINED_PAGE_SIZE`), the largest the
contract reads.

### Model and declaration retention

`model.prepared` prices one preparation of the complete structural write model:
the six categorical Entities, the ten geometry Entities and their six
changed-ancestor twins, and the two acquisition Entities. The leaf-type
families' model is their own and outside it. The Entity Class declarations and
their Value Object classes are retained by the fixture modules and are outside
every window.

## Limits

- A retained checkpoint is a graph reachable at one point; a high-water mark is a
  net rise over one floor. Neither is cumulative allocation, and a duplicate
  traversal that allocates and frees inside a window need not move either.
- Pass observations (`calls.*`) count returns of named functions per row over
  the keyed-write window, taken in a pass of their own after the timing samples
  and before the memory samples. They are diagnostics with units that
  distinguish roots, nested values, and repeated calls; they gate nothing. A
  count is of returns, never of semantic complete-row encodings: a nested
  document counts once per recursive return, one `encodeManagedMany` return
  covers every element it encodes, a successor lowered as patches over its
  retained predecessor pays managed encodings only for the subtrees it
  replaces, and an unchanged successor pays none. Three vocabularies exist and a
  capture carries exactly one of them whole. `before/` and `after/` carry the legacy names frozen with
  the manifest, `encodeDocument` and `encodeMany`, which count the source
  codec's `encode_document` and `encode_many`; the unified write path no longer
  reaches those functions, so both cells read zero at `after/` and say nothing
  about how many encodings a row pays there. `recovered/` carries the managed
  names, `encodeManagedDocument` and `encodeManagedMany`, which count the
  managed encoders `encode_managed_document` and `encode_managed_many` that the
  unified path does run, observed at the private module SQL lowering imports
  them from. The two pairs are different functions under different names:
  `--compare` leaves a renamed counter unmatched on each side rather than
  aliasing it or reading a historical zero as a count of anything, while every
  timing and memory address pairs as before. Both of those vocabularies also
  carry `shapeOfDeclaration` and `entityShape`, which counted document-codec
  functions the write path never reached and which no longer exist; every
  later capture carries the current vocabulary, the managed names without
  those two. `occurrenceShape`, `applyPatches`, and `detachJsonContainer`
  count what they name under every vocabulary.
  `cost_report.py --verify` accepts a write-lowering matrix only under one
  whole vocabulary across every keyed case and runtime; a mixture is not exact
  under any, and a live child answering a historical vocabulary is refused.
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
acquisition levels, the two model-preparation checkpoints, and the leaf-type
families' 46 keyed inserts and 24 acquisitions (248 gates, in bytes per row or
bytes), and the retained and peak readings of the eighteen geometry reads, nine
cold plan compilations, and twenty-two leaf-type reads (98 gates, in KiB
converted to bytes) — 346 in all, beside the scaling domains and the advisory
allowances. The cost
class grades them, under both layouts and through the same reading children the
capture uses, in `tests/unit/tools/test_write_lowering_reading_gates.py` and
`tests/unit/tools/test_snapshot_delivery_reading_gates.py`; timing is asserted
nowhere. The gates live in a file of their own rather than in
`budget-contract.yaml` because that contract's digest is part of the
`authority` fingerprint the baseline's Snapshot member was classified under:
editing it would reclassify the retained captures or demand a fresh one.

### Basis

Every ceiling is the rule's output, not an edit: the largest reading of the
address on either runtime in the capture the file names as its basis —
`recovered/portfolio.json` — scaled by **1.10** and rounded up to a whole byte, and
`test_every_memory_gate_is_the_basis_reading_under_the_stated_rule`
recomputes all 346 from it. The headroom is the Budget Contract's own
`individualMax` for a memory cell; the run-to-run agreement recorded under
*Measured noise floor* — retained checkpoints within 2.8% and high-water marks
within 1% on this runner, and a further 1–3% between the two runtimes, which
taking the larger runtime absorbs — sits inside it. A byte reading is a
property of the interpreter's object layouts rather than of the runner, which
is why a fixed ceiling can be graded on CI's floating runner label where an
elapsed time cannot; the residual risk that a CPython patch release or a
platform allocator moves a reading by more than the headroom is accepted, and
would surface as a gate failure to be read against this basis, never as a
ceiling to relax.

The gates were first derived from `before/` and have since been re-derived
under the same rule from `after/` and from each capture that became the
canonical `recovered/`. Git history keeps each earlier derivation's account
beside the capture it came from. The present basis is the capture described
under *Recovered capture*, as amended, and every reading of it had first been graded against
the ceilings the outgoing basis set (*Recovered capture*, *Memory*). Its
derivation took the file from 162 gates to 346: 184 were inserted, 132 fell, 18
are unchanged to the byte, and 12 rose.

- **Inserted:** the 184 leaf-type addresses (44 read, 92 keyed-insert and 48
  acquisition gates). This is the first capture that reads them.
- **Unchanged:** the eighteen geometry-read `retainedKiB` ceilings.
- **Fell, in windows the source alignment changed:** 84 keyed-write ceilings,
  every retained checkpoint among them, by 3.3% to 99.2%, and the twelve
  acquisition ceilings by 16.2% to 56.3%. The four `txtime.unchanged` retained
  checkpoints fall to 36 B/row because the verb's no-op path buffers nothing.
  These are new baselines, not measured gains (*Against COR-173's capture*).
- **Fell, in unchanged windows:** the cold-plan checkpoints by 10.7% to 14.1%,
  the guarded cold plans by 6.5% to 15.6%, and the geometry-read peaks by 0.1%
  to 2.7%.
- **Rose:** eight keyed-write high-water marks and the four model-preparation
  ceilings.
  - The keyed-write marks are in the changed window, which now includes the
    verb's validation and the flush: `ancestor.width-64.document.typed` +9.1%,
    `bitemporal.interior.document.wire` +6.2% (16,907 to 17,958 B/row),
    `bitemporal.interior.columns.wire` +2.0%,
    `bitemporal.interior.document.typed` +0.3%, and the `geometry.width-64` and
    `geometry.many-32` transients by 0.7% to 1.3%.
  - The model-preparation ceilings are the attributed, accepted growth under
    *Recovered capture*: `model.prepared` retained +2.6% (469,929 to 482,284 B)
    and transient +2.0%, and `model.prepared.family` retained +5.9% (24,843 to
    26,312 B) and transient +2.0%.

A gate's
sensitivity is therefore the headroom alone at every address: a retained
duplicate or a transient copy worth more than 10% of the reading trips it on
either runtime, and one worth less is inside the noise the headroom absorbs.

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
names, and is proved to trip the gate it targets. Figures are diagnostic
readings taken on this runner (2026-09-17, CPython 3.14.7) at the tree
`after/` was captured from, not evidence.

| Seed | Seam | Effect | Proved on |
|---|---|---|---|
| A per-instruction registry keeping a detached copy of every prepared row, accumulating | `prepare_typed_write` / `prepare_wire_write` | retained +964 to +1,064 B/row on the categorical cases, +5,080 on `width-64` | the three Wire successor cases and the Typed opening Columns case: one row's duplicate is 17–35% of a categorical checkpoint, against a 10% headroom |
| A second formed model retained beside the first | `DomainModel` formation inside the model window | retained 427 KB to 823 KB (formation is 396 KB of the 427; the catalog, codec, and planner are 31 KB) | `model.prepared` |
| One complete mutable copy of every document bind held across the driver dump — the preliminary tree the immutable-serialization bridge removed | `serialize` | peak +4.5 to +6.4 KB: `width-64.document` 25,434 to 30,306 B/row, `many-32.columns` 27,746 to 34,106 | the three widest cases, at one copy: 19–23% over the reading, against a 10% headroom |
| A resolving port keeping a copy of every row it answered, its document included; the group already retains the answered rows' documents by transfer, so keeping the rows themselves duplicates little | `projected_rows` | retained +1,025 to +1,165 B/row at every level (read 2026-09-26, after that transfer landed) | `rows-32.columns`, `rows-128.document` |
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
visible only to the advisories, and a transient copy or retained duplicate
worth less than the headroom is invisible to its gate.

### Ownership

`tests/unit/_memory_gate_support.py` names the cost item owning each gate;
`tests/unit/test_memory_gate_ownership.py` grades that every named item is
collected in the cost class and that the owners partition the 346 gates, so a
gate is never owned by a report member's registration. The prepared-model owner
claims both preparation cases, `model.prepared` and `model.prepared.family`; the
cold-plan owner claims the geometry levels under `plan-` and the guarded include
widths under `control-guarded-`, whose delivery and warm-plan cells are read in
windows no gate covers. Ownership is graded a second time against the addresses
the instruments read in a gated window rather than against the file, so a
manifest that widens the matrix is claimed at the change that widens it and not
at the next rebaseline, and every claimed control address is held to a cold
read-plan compilation, the one control reading an owner's child takes. The cost
class's tests are CI-owned (`python-test-cost`, six shards) and outside
`just check`.

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
is the baseline: it is captured once and is the comparison base for the
after-capture and the recovery reference for `recovered/`.

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
growth and is recorded as an observation, not attributed. The after-capture
is compared against this capture alone.

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

## After capture — `after/`

Produced from clean commit `1636e9f0ce07` (`test(cost): gate structural memory
against the baseline`, the tree carrying every phase of the unification and the
memory gates) by `uv run --project languages/python python
languages/python/tools/cost_report.py --out /tmp/cor-158-after-1636e9f0`,
2026-09-17 06:05–07:05 EDT, on the same Mac17,4 (Apple M5, 10 cores, 32 GiB,
macOS 26.6.2) with the same CPython 3.14.7 and 3.13.15, PostgreSQL 18.6, and
`uv.lock` as the baseline, launched from `/bin/sh` at nice 0 as the baseline
was, with no other measurement running; then retained here unchanged, with the
`--compare` rendering beside it as `comparison.md`. All four members name that
commit and a clean tree, none carries an incomplete cell or an error, and every
one of the 1,286 Snapshot delivery and write-lowering cells the baseline read
is paired: `--compare` reports no cell missing on either side, and its 72
`incomparable` rows are zero-valued instance-state cells no delta can be taken
over.

| Member | Authority | Runtimes | Readings | Within | Outside |
|---|---|---|---:|---:|---:|
| snapshot-delivery | authoritative | 3.13, 3.14 | 324 | 72 | 18 |
| lifecycle-overhead | non-authoritative | 3.14 | 87 | 4 | 11 |
| instance-state | non-authoritative | 3.13, 3.14 | 624 | 4 | 4 |
| write-lowering | non-authoritative | 3.13, 3.14 | 962 | — | — |

`cost_report.py --verify after/portfolio.json` exits 0 and reports twenty
advisories, verbatim:

```text
advisory: conventional-fanout.providerFreeCpu.eager.maxMs is outside its timing ceiling
advisory: conventional-fanout.providerFreeCpu.eager.minRootsPerSecond is outside its timing ceiling
advisory: duplicate-include.live.eager.maxMs is outside its timing ceiling
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
advisory: bitemporal-current.eagerMemory.peakKiB is outside its memory ceiling
advisory: document-heavy.streamedMemory.page128PeakKiB grows 37.974 KiB between memory arms
advisory: bitemporal-current.streamedMemory.page128PeakKiB grows 23.032 KiB between memory arms
```

Seventeen timing ceilings are exceeded on the authority runtime — sixteen of
the baseline's eighteen, with `duplicate-include.live.page32.minRootsPerSecond`
and `versioned-document.live.page128.maxMs` back inside and
`duplicate-include.live.eager.maxMs` newly outside — one memory ceiling is
exceeded (`bitemporal-current.eagerMemory.peakKiB`, 428.6 KiB against 425, read
under *Preserved delivery and stress cells* below), and two streamed-memory
arms grow past the 16 KiB limit: the pre-existing `document-heavy` page-128
growth, and `bitemporal-current`'s page-128 arm in place of the baseline's
page-32 one. No reading is past its memory gate. No limit was relaxed.

### Comparison with the baseline

Every delta below is `after/` against `before/`, read per cell under the
protocol: a timing delta inside roughly ±15% is noise on its own, and a timing
claim rests on the direction agreeing across a family and both runtimes; a byte
delta within 3% is noise. Medians are over the family's cells on one runtime;
ranges name the extreme cells.

| Family (window) | Cells per runtime | Elapsed, 3.13 | Elapsed, 3.14 | High-water | Retained |
|---|---:|---|---|---|---|
| Categorical keyed writes, Typed (`keyed-write`) | 10 | −11.7% (−19.5% to −5.7%) | −8.3% (−14.0% to −6.6%) | −11% (−19.4% to −7.7%) | −20% (−24.2% to −9.4%) |
| Categorical keyed writes, Wire | 10 | −14.4% (−23.6% to −6.8%) | −13.3% (−18.4% to −6.8%) | −6% (−15.7% to −3.5%) | within noise (−5.3% to +2.8%) |
| Geometry inserts, Typed | 18 | −9.5% (−19.6% to +8.6%) | −11.8% (−26.8% to −2.8%) | −14% (−29.0% to −6.9%) | −30% (−42.1% to −10.6%) |
| Changed-ancestor updates, Typed | 8 | −7.6% (−11.4% to +11.6%) | −24.6% (−32.9% to −13.7%) | −11% (−28.0% to −8.0%) | −21% (−38.7% to −14.8%) |
| Predicate acquisition (`predicate-acquisition`) | 6 | **+94%** (−15.3% to +119.2%) | **+51%** (+14.4% to +80.3%) | within noise (−2.4% to +4.2%) | within noise (−0.9% to +0.3%) |
| Model preparation (`model-preparation`) | 1 | −16.6% | −40.0% | −33% | −34% |
| Geometry reads (`provider-free-delivery`) | 18 | **+21%** (−8.9% to +83.5%) | **+26%** (+1.2% to +83.4%) | within noise (−0.5% to +5.4%) | identical to the byte |
| Read-plan compilation (`read-plan-compilation`) | 6 | −16.5% (−32.8% to −7.1%) | −3.5% (−6.8% to +2.4%) | within noise | within noise (−2.5% to +1.7%) |
| Positional-materialization stress (`positional-materialization`) | 2 | **+45%** µs/projection | **+68%** µs/projection | unchanged | unchanged |
| Preserved live delivery, eager (`live-delivery`) | 5 | **+23%** maxMs | **+19%** maxMs | within noise except `bitemporal-current` | within noise except `bitemporal-current` |

The write side is what the unification set out to change and it moved as
designed: 80 of the 92 keyed-write cells are faster past the 5% allowance and
10 within it, every high-water mark is lower, and every Typed checkpoint
retains less, with the savings largest where the intermediate trees were
largest. The read side and
the predicate-acquisition companion, whose retained and peak readings the
unification was to leave in place, kept them to the byte — and pay materially
more elapsed time per root and per resolved row, on both runtimes, in every
family. The attribution follows the per-workload conclusions.

#### Categorical keyed writes

All twenty cases are faster on both runtimes: Typed by 5.7–19.5%, Wire by
6.8–23.6%, with direction agreeing across every family and both runtimes,
which is what makes a claim of this size against the ±15% floor. The Typed
settled checkpoint retains 9–24% less (`txtime.opening.columns.typed` 3,618 to
2,744 B/row on 3.13): the authored value is borrowed from the instance and
prepared once into its final immutable form, so no rendered dictionary tree
and no frozen copy of it sit beside the managed value at settlement. The Wire
checkpoint is unchanged within noise on seventeen cells and 3.4–5.3% smaller on
three Columns cells on 3.14, because a Wire row's authored mapping was already
its own carrier; what Wire saves is the high-water mark (3.5–15.7%) and the elapsed time. An
unchanged Relational Document successor now reuses its retained predecessor by
identity — `applyPatches` 1 to 0 and `detachJsonContainer` 16 to 0 per row on
`txtime.unchanged.document` — and costs less than a changed one for the first
time (3.13: 211 against 224 µs/row Typed); under Columns it still re-encodes
each Value Object column, as the manifest states, and costs what a changed
successor costs. The small and shallow cases regress nowhere: the smallest
categorical case (`txtime.opening.columns.wire`, 157 µs/row on 3.13) is 9%
faster and the shallowest geometry (`many-0`, 152 µs/row) 7–18% faster.

#### Geometry inserts and changed ancestors

Retained bytes at the settled checkpoint fall with the size of the value —
10.6% at `many-0`, 32% at `depth-8`, 40% at `many-32`, 42% at `width-64` —
because the managed value no longer coexists with a rendered and a frozen copy
of itself, and the high-water mark falls 7–29% because the encoded document is
composed once and serialized without a mutable copy. Elapsed time is faster
past the 5% allowance on 40 of the 52 geometry-and-ancestor cells across the
two runtimes and within it on 10. The two slower cells are the widest Columns
cases on 3.13 alone — `geometry.width-64.columns` +8.6% and
`ancestor.width-64.columns` +11.6% — both inside the noise floor, both faster
on 3.14 (−15.2%, −13.7%) and both faster under Relational Document on 3.13
(−4.6% and −7.0% on the twin cases), so no wide-Columns regression is claimed
or excluded. The changed ancestor's `detachJsonContainer` count, 33 to 393 per
row with the replaced occurrence's width, is 0: a changed successor shares the
predecessor's untouched subtrees and builds one root. The baseline's open
observation that wide and sparse Typed inserts ran up to 1.5x slower on 3.14
than on 3.13 is largely resolved by the borrowed Typed access:
the 3.14-to-3.13 ratio at `width-64.columns` is 1.07 (was 1.37), at
`sparse-64.columns` 1.16 (was 1.49), at `width-16.columns` 1.13 (was 1.39).

#### Source and managed coexistence, and serialization

Peak coexistence is measured by the keyed-write high-water mark, which includes
the source, the prepared value, the settled plan, the encoded documents, and
psycopg's own dump buffers at once: it is lower on every one of the 92
keyed-write cells, by 3.5–29%. The frozen-document serialization bridge — a
per-bind standard-library `json.dumps` reading `FrozenMap` backing through a
default hook, one callback per nested mapping — is inside every keyed-write
elapsed reading above and is not separated from it; the whole-window result is
faster on every case but the two 3.13 wide-Columns cells, so its per-mapping
callback cost is at most inside those cells' noise. No serialization saving is
claimed on its own, and the mutable-copy seed under *Sensitivity* is what the
peak gate would see if the bridge were bypassed.

#### Predicate acquisition

Per-row retained and high-water readings are unchanged within noise at every
level and under both layouts (the one cell past 3%, `rows-128.columns` peak
+4.2% on 3.13, is −0.1% on 3.14), and the per-row amortization over 8, 32, and
128 rows that the scaling domains gate still holds. Elapsed time per resolved
row roughly doubles on 3.13 (`rows-128.columns` 49 to 108 µs, `rows-32.document`
57 to 110) and rises 14–80% on 3.14, on every level but one, with the largest
rise at the largest row count — so the fixed planning cost the rows amortize is
not what grew; the per-row work did. This companion window is the one place the
unification made no structural removal and left a per-row structure standing:
`EntityStateRow.__getitem__` still finds a member by scanning
`(*layout.attributes, *layout.occurrences)` for its storage name on every
lookup, and `row_payload` performs two such lookups per member per row. The
regression is attributed under *Attribution diagnostics*.

#### Structural retention

`model.prepared` retains 34% less (649,080 to 427,016 B on 3.14) and prepares
in 17–40% less time: one canonical `MemberShape` per declaration shared by
reference across occurrences and models, one `EntityMemberSelection` per
Entity referenced by the layout, row codec, storage residency, and graph
construction, and no independent nested layout tree or duplicate name index.
The declarations and their Value Object classes remain outside the window, as
the manifest states.

#### Geometry reads and output expansion

The retained page is identical to the byte at every level under both layouts
(`sparse-64` still retains 36 KiB for 32 roots carrying one populated leaf
each, the O(NW) positional expansion the manifest names), and the high-water
mark is within noise everywhere but `depth-4` (+3.1–3.3%) and `depth-8`
(+4.4–5.4%), the two addresses whose diagnostic readings sat above the
baseline when the gates were introduced, which the capture confirms and the
re-derived gates now carry. Elapsed time per root is slower past the 5%
allowance on 33 of the 36 cells: 21–37% at the shallow baseline (`depth-1`
33.5 to 40.7 µs/root on 3.13),
22–27% at `many-0` and `many-32`, 13–26% at the width levels, and 70–83% at
`sparse-64` (47 to 86 µs/root), while the deepest chain is flat (`depth-8`
−8.9% to +10.1%). The pattern — cost per declared position rather than per
populated value, worst where declared width most exceeds populated width — is
the read side's regression and is attributed below.

#### Read-plan compilation

The cold compiled plan is the same size at every level under a layout as it
was (retained within 2.5%, the Columns-to-Document difference still 0.8 KiB),
and compiles 7–33% faster on 3.13 and within noise on 3.14. Compiled-read
residency now references storage's complete resident selection rather than
building a selected-only shape, and the plan retains no more for it.

#### Preserved delivery and stress cells

The Budget Contract's delivery workloads read the same regression at delivery
scale: the eager live cells are 19–23% slower at the median on both runtimes
with direction agreeing across four of the five workloads, the paged live and
provider-free cells are 14–15% slower on 3.13 and within noise on 3.14, and
the positional-materialization stress cells are 33–84% slower per projection
(`stress-columns` 6.2 to 9.5 µs/projection on 3.14) with retained and
transient bytes per projection unchanged and the prepared set 12% smaller
under Relational Document. Delivery memory is unchanged within noise on four
of the five workloads; `bitemporal-current` alone retains 3.5–5.0% more
eagerly, peaks 7.5–9.3% higher eagerly (428.6 KiB on 3.14 against a 425 KiB
ceiling, the one memory advisory above) and 8–19% higher while streaming. No
read-path change touched temporal materialization, and the two other
Relational Document delivery workloads (`document-heavy`, `versioned-document`)
did not move, so this growth is recorded as an observation, not attributed.

#### Pass observations

`detachJsonContainer` is 0 per row on every keyed-write case (it was 2 to 393),
`applyPatches` is 1 on every changed Relational Document successor and 0 on
every unchanged one (it was 1 on both), and `encodeDocument` and `encodeMany`
read 0 everywhere for the reason stated under *Limits*: the legacy names are
functions the unified path no longer calls. The current names that count the
managed encoders were introduced after this capture and are first read by the
`recovered/` capture below.

### Attribution diagnostics

Two regressions above are material and attributed. The readings below are
`cProfile` and `perf_counter` diagnostics taken on this runner at the `after/`
tree and, for comparison, at the baseline's producing commit checked out
beside it — not evidence, and not the report's windows: 200 provider-free
finds or 100 acquisitions in one process, warmed.

**One root cause is shared.** The structural unification replaced the plain
tuples an occurrence and an Entity layout exposed as `attributes` /
`value_objects` / `occurrences` with `_BindingRange` views over the aligned
binding tuple (`inheritance/_facet.py`, `metamodel/_compile.py`). The views
implement
`__len__` and `__getitem__` and inherit `__iter__` from `collections.abc
.Sequence`, so iterating one costs a Python-level `__getitem__` call, a slice
check, and two `len` calls per element where a tuple iterates in C. Every hot
per-row loop that walks declared members iterates one of them:

- the read side's Wire publication (`materialize/_wire.py` `_held_members`)
  walks `declared.attributes` per occurrence per root — 0.05 s of the
  baseline's 1.18 s profile of `sparse-64.document`, 0.76 s of the after
  tree's 2.19 s, with `_BindingRange.__getitem__` called 1.27 million times;
- the acquisition path's `EntityStateRow.__getitem__` unpacks
  `(*layout.attributes, *layout.occurrences)` per lookup and `row_payload`
  looks each member up twice per row — 0.39 s of the baseline's 2.03 s profile
  of `rows-128.columns`, 2.49 s of the after tree's 5.02 s, with the
  inheritance `_BindingRange.__getitem__` called 2.86 million times.

**The read side's second cause** is the direct decode's per-position dispatch:
the codec yields each declared position through an `interpreted_members`
generator, one `_interpreted_member` call, and one `build_positional_object`
comprehension step (1.25 million of each in the same profile, 0.6 s of
`tottime` together) where the baseline's `reduce_declared_members_classified`
and `_structure` were two tight loops over `dict.get` (0.36 s). It is per
declared position, which is why `sparse-64` is the worst case. **The
acquisition path's second cause** is `PredecessorRow.__post_init__` retaining
each selected row's payload through `retain_document_value`, which walks the
lazy `_EntityDocumentRow` views the payload holds (332,800 calls, 0.71 s,
against the baseline's `freeze_retained_value` at 0.23 s).

Giving the two `_BindingRange` views a `__iter__` over their tuple slice —
patched in the diagnostic process only, nothing in the repository — isolates
the shared cause (medians of nine, µs per root or per resolved row):

| Cell | After tree | With a C-speed `__iter__` | Baseline, for scale |
|---|---:|---:|---:|
| `read-depth-1.columns` | 37.6 | 33.2 (−12%) | 31.6–33.5 |
| `read-sparse-64.document` | 78.2 | 54.6 (−30%) | 46.0–46.9 |
| `read-width-64.columns` | 172.4 | 147.7 (−14%) | 157.0–160.5 |
| `read-many-32.document` | 192.9 | 162.4 (−16%) | 159.8–159.9 |
| `acquisition.rows-128.columns` | 98.2 | 63.8 (−35%) | 49.2–66.8 |
| `acquisition.rows-8.document` | 129.1 | 93.3 (−28%) | 77.7–98.7 |

The view iteration is therefore most of the acquisition regression and roughly
half of the read regression; what remains on the read side after it is the
per-position dispatch, and on the acquisition side the per-row retention and
the surviving storage-name scan. None of the three is a carrier alternative or
a temporal optimization: the first is a Sequence view iterating through the
ABC mixin, the second the direct decode's control-flow shape, the third an
inventoried per-row structure the unification left standing. Whether to
refine them is the tradeoff decision this evidence is presented for; a
refinement changes the read and acquisition windows and needs fresh evidence
on both sides.

### Open observations

- Resolved by this capture: the wide and sparse Typed inserts' 3.14 slowdown
  (now at most 1.16x, from 1.49x); the four addresses whose diagnostic
  readings sat above the baseline when the gates were introduced
  (`txtime.changed.document.wire` retained, the Columns cold-plan checkpoints,
  the `read-depth-4` and `read-depth-8` peaks) are confirmed at
  +1.4%, +1.6%, and +3.1% to +5.4% and now carried by the re-derived gates.
- Unchanged: the cold compiled plan is the same size at every geometry level.
- Attributed after this capture, by inspection of the read path between the
  two producing commits and by diagnostic readings, not by this capture:
  `bitemporal-current`'s 3.5–19% delivery memory growth, alone among the
  delivery workloads, is the cost of owning each delivered row's raw Structured
  Column in deferred read evidence. `Charter` is the one bitemporal Entity among
  the five delivery workloads, and the retention seam
  (`snapshot/handle/_retention.py`) retains a temporal row's raw document
  through `retain_document_value` when it retains the row — one owned
  `FrozenMap` tree per delivered Charter (`payload` and its nested `terms`),
  alive for the delivered snapshot's lifetime — where the baseline stored the
  provider's reference. The `document-heavy` and `versioned-document` Relational
  Document workloads declare no temporal axis and did not move. The ownership
  is required by the complete-predecessor rule, so the cost stands as `after/`'s
  own; diagnostic readings of the recovery tree put this workload's eager peak
  and retained memory within 2.1% of `after/` on both runtimes, and the
  `recovered/` capture within 0.5%. The baseline's 4,184
  B/row high-water offset between its own two captures is superseded by this
  comparison, which pairs the retained baseline alone.
- Recorded, not measured separately: the frozen-document serialization
  bridge's per-mapping callback cost, inside the keyed-write windows.

### Keyed writes per row (`keyed-write` window)

Median of nine samples; retained is one checkpoint after 200 warm-ups. Pass
observations are per row on either runtime (they agree exactly).

| Case | 3.13 µs | 3.13 peak B | 3.13 retained B | 3.14 µs | 3.14 peak B | 3.14 retained B | encodeDocument / encodeMany / applyPatches / detachJsonContainer |
|---|---:|---:|---:|---:|---:|---:|---|
| txtime.opening.columns.typed | 168.8 | 15042 | 2744 | 193.0 | 15554 | 2900 | 0 / 0 / 0 / 0 |
| txtime.changed.columns.typed | 204.5 | 14826 | 3710 | 222.2 | 15290 | 3906 | 0 / 0 / 0 / 0 |
| txtime.unchanged.columns.typed | 206.5 | 14826 | 3810 | 224.7 | 15290 | 3856 | 0 / 0 / 0 / 0 |
| plain.changed.columns.typed | 171.8 | 15138 | 3024 | 190.3 | 15666 | 3062 | 0 / 0 / 0 / 0 |
| bitemporal.interior.columns.typed | 283.4 | 15866 | 5646 | 315.0 | 15890 | 6008 | 0 / 0 / 0 / 0 |
| txtime.opening.columns.wire | 157.2 | 14810 | 2612 | 170.1 | 15266 | 2560 | 0 / 0 / 0 / 0 |
| txtime.changed.columns.wire | 186.9 | 14626 | 3610 | 205.2 | 15030 | 3548 | 0 / 0 / 0 / 0 |
| txtime.unchanged.columns.wire | 178.9 | 14626 | 3560 | 202.5 | 15030 | 3748 | 0 / 0 / 0 / 0 |
| plain.changed.columns.wire | 154.5 | 14938 | 2824 | 166.7 | 15406 | 2854 | 0 / 0 / 0 / 0 |
| bitemporal.interior.columns.wire | 277.2 | 15748 | 5642 | 295.5 | 15702 | 5746 | 0 / 0 / 0 / 0 |
| txtime.opening.document.typed | 176.2 | 15042 | 2744 | 192.7 | 15554 | 2900 | 0 / 0 / 0 / 0 |
| txtime.changed.document.typed | 224.1 | 14826 | 3710 | 239.3 | 15290 | 3856 | 0 / 0 / 1 / 0 |
| txtime.unchanged.document.typed | 211.2 | 14826 | 3760 | 223.9 | 15290 | 3806 | 0 / 0 / 0 / 0 |
| plain.changed.document.typed | 177.2 | 15138 | 2974 | 196.7 | 15666 | 3112 | 0 / 0 / 0 / 0 |
| bitemporal.interior.document.typed | 287.6 | 15075 | 5696 | 331.3 | 15440 | 5908 | 0 / 0 / 1 / 0 |
| txtime.opening.document.wire | 149.8 | 14810 | 2612 | 168.9 | 15266 | 2660 | 0 / 0 / 0 / 0 |
| txtime.changed.document.wire | 188.0 | 14626 | 3610 | 212.5 | 15030 | 3698 | 0 / 0 / 1 / 0 |
| txtime.unchanged.document.wire | 185.3 | 14626 | 3510 | 201.9 | 15030 | 3698 | 0 / 0 / 0 / 0 |
| plain.changed.document.wire | 149.0 | 14938 | 2824 | 173.3 | 15406 | 2904 | 0 / 0 / 0 / 0 |
| bitemporal.interior.document.wire | 266.8 | 14922 | 5592 | 300.2 | 15370 | 5696 | 0 / 0 / 1 / 0 |

### Geometry inserts and changed-ancestor updates per row (`keyed-write` window, Typed)

| Case | 3.13 µs | 3.13 peak B | 3.13 retained B | 3.14 µs | 3.14 peak B | 3.14 retained B | encodeDocument / encodeMany / applyPatches / detachJsonContainer |
|---|---:|---:|---:|---:|---:|---:|---|
| geometry.depth-1.columns | 178.5 | 14690 | 2472 | 191.5 | 15186 | 2528 | 0 / 0 / 0 / 0 |
| geometry.depth-1.document | 179.2 | 14690 | 2422 | 191.9 | 15186 | 2528 | 0 / 0 / 0 / 0 |
| geometry.depth-4.columns | 217.7 | 15426 | 3194 | 234.5 | 15858 | 3200 | 0 / 0 / 0 / 0 |
| geometry.depth-4.document | 213.0 | 15426 | 3194 | 234.7 | 15858 | 3200 | 0 / 0 / 0 / 0 |
| geometry.depth-8.columns | 265.9 | 16746 | 4040 | 301.6 | 17234 | 4096 | 0 / 0 / 0 / 0 |
| geometry.depth-8.document | 280.2 | 16746 | 4040 | 295.2 | 17234 | 4096 | 0 / 0 / 0 / 0 |
| geometry.many-0.columns | 152.4 | 14186 | 1968 | 166.5 | 14674 | 2016 | 0 / 0 / 0 / 0 |
| geometry.many-0.document | 145.6 | 14186 | 2018 | 165.5 | 14674 | 1966 | 0 / 0 / 0 / 0 |
| geometry.many-8.columns | 265.2 | 16082 | 3914 | 268.6 | 16578 | 3920 | 0 / 0 / 0 / 0 |
| geometry.many-8.document | 260.7 | 16082 | 3914 | 264.2 | 16578 | 3920 | 0 / 0 / 0 / 0 |
| geometry.many-32.columns | 530.8 | 27242 | 9432 | 557.7 | 27746 | 9488 | 0 / 0 / 0 / 0 |
| geometry.many-32.document | 524.4 | 27429 | 9432 | 578.2 | 27925 | 9488 | 0 / 0 / 0 / 0 |
| geometry.width-16.columns | 266.2 | 15530 | 3312 | 301.8 | 16090 | 3368 | 0 / 0 / 0 / 0 |
| geometry.width-16.document | 266.0 | 15530 | 3362 | 290.5 | 16090 | 3368 | 0 / 0 / 0 / 0 |
| geometry.width-64.columns | 642.9 | 23321 | 6672 | 689.0 | 23817 | 6678 | 0 / 0 / 0 / 0 |
| geometry.width-64.document | 647.6 | 24874 | 6722 | 708.3 | 25434 | 6728 | 0 / 0 / 0 / 0 |
| geometry.sparse-64.columns | 239.0 | 14690 | 2522 | 277.9 | 15186 | 2528 | 0 / 0 / 0 / 0 |
| geometry.sparse-64.document | 236.9 | 14690 | 2472 | 274.3 | 15186 | 2528 | 0 / 0 / 0 / 0 |
| ancestor.depth-1.columns | 211.3 | 14602 | 3536 | 248.0 | 15066 | 3632 | 0 / 0 / 0 / 0 |
| ancestor.depth-1.document | 224.6 | 14602 | 3586 | 242.6 | 15066 | 3632 | 0 / 0 / 1 / 0 |
| ancestor.width-16.columns | 321.7 | 15442 | 4426 | 345.6 | 15970 | 4422 | 0 / 0 / 0 / 0 |
| ancestor.width-16.document | 304.9 | 15442 | 4326 | 339.4 | 15970 | 4422 | 0 / 0 / 1 / 0 |
| ancestor.width-64.columns | 726.3 | 25739 | 7736 | 753.2 | 26259 | 7832 | 0 / 0 / 0 / 0 |
| ancestor.width-64.document | 648.8 | 23874 | 7736 | 712.3 | 24604 | 7932 | 0 / 0 / 1 / 0 |
| ancestor.sparse-64.columns | 284.8 | 14602 | 3536 | 324.2 | 15066 | 3682 | 0 / 0 / 0 / 0 |
| ancestor.sparse-64.document | 266.5 | 14552 | 3486 | 309.8 | 15066 | 3632 | 0 / 0 / 1 / 0 |

### Predicate acquisition per resolved row (`predicate-acquisition` window)

| Case | 3.13 µs | 3.13 peak B | 3.13 retained B | 3.14 µs | 3.14 peak B | 3.14 retained B |
|---|---:|---:|---:|---:|---:|---:|
| acquisition.rows-8.columns | 125.1 | 5908 | 2368 | 131.4 | 6091 | 2552 |
| acquisition.rows-32.columns | 111.3 | 4207 | 1738 | 110.8 | 4231 | 1811 |
| acquisition.rows-128.columns | 107.9 | 3677 | 1583 | 100.8 | 3675 | 1616 |
| acquisition.rows-8.document | 134.5 | 7988 | 3568 | 136.7 | 8210 | 3789 |
| acquisition.rows-32.document | 110.2 | 6272 | 2922 | 119.0 | 6332 | 3008 |
| acquisition.rows-128.document | 104.4 | 5831 | 2768 | 109.2 | 5838 | 2808 |

### Model preparation (`model-preparation` window)

| Runtime | µs | peak B | retained B |
|---|---:|---:|---:|
| 3.13 | 3738.2 | 436760 | 415992 |
| 3.14 | 3673.3 | 435016 | 427016 |

### Geometry reads (`provider-free-delivery` window, 32 roots)

| Level | Layout | 3.13 µs/root | 3.13 peak KiB | 3.13 retained KiB | 3.14 µs/root | 3.14 peak KiB | 3.14 retained KiB |
|---|---|---:|---:|---:|---:|---:|---:|
| depth-1 | columns | 40.71 | 109.9 | 50.8 | 42.30 | 107.7 | 51.1 |
| depth-1 | document | 39.99 | 109.9 | 50.8 | 43.87 | 107.6 | 51.1 |
| depth-4 | columns | 64.85 | 158.4 | 88.0 | 65.86 | 159.9 | 88.2 |
| depth-4 | document | 60.38 | 158.4 | 88.0 | 64.23 | 158.8 | 88.2 |
| depth-8 | columns | 86.34 | 231.7 | 137.5 | 94.49 | 236.4 | 137.7 |
| depth-8 | document | 86.71 | 230.6 | 137.5 | 101.88 | 235.7 | 137.7 |
| many-0 | columns | 28.58 | 67.7 | 24.1 | 30.08 | 66.6 | 24.3 |
| many-0 | document | 29.10 | 73.4 | 24.1 | 28.16 | 72.3 | 24.3 |
| many-8 | columns | 77.55 | 205.8 | 125.1 | 72.33 | 209.0 | 125.3 |
| many-8 | document | 72.87 | 204.8 | 125.1 | 72.18 | 208.3 | 125.3 |
| many-32 | columns | 210.10 | 635.3 | 428.1 | 253.33 | 639.8 | 428.3 |
| many-32 | document | 203.78 | 635.1 | 428.1 | 208.59 | 639.4 | 428.3 |
| width-16 | columns | 69.79 | 220.8 | 136.7 | 66.65 | 224.3 | 137.0 |
| width-16 | document | 69.52 | 224.3 | 136.7 | 85.61 | 227.8 | 137.0 |
| width-64 | columns | 185.60 | 763.3 | 480.2 | 201.05 | 767.2 | 480.5 |
| width-64 | document | 184.99 | 766.9 | 480.2 | 194.02 | 770.7 | 480.5 |
| sparse-64 | columns | 85.67 | 139.6 | 35.9 | 88.04 | 137.5 | 36.2 |
| sparse-64 | document | 86.10 | 139.6 | 35.9 | 84.40 | 137.5 | 36.2 |

### Read-plan compilation (`read-plan-compilation` window)

| Level | Layout | 3.13 µs | 3.13 peak KiB | 3.13 retained KiB | 3.14 µs | 3.14 peak KiB | 3.14 retained KiB |
|---|---|---:|---:|---:|---:|---:|---:|
| depth-1 | columns | 111.8 | 22.85 | 14.80 | 116.6 | 23.82 | 16.19 |
| depth-1 | document | 113.7 | 22.81 | 14.94 | 112.7 | 23.98 | 16.34 |
| depth-8 | columns | 113.3 | 22.85 | 14.80 | 116.7 | 23.82 | 16.19 |
| depth-8 | document | 108.0 | 22.81 | 14.94 | 116.5 | 23.98 | 16.34 |
| width-64 | columns | 113.7 | 22.85 | 14.80 | 110.3 | 23.82 | 16.19 |
| width-64 | document | 113.1 | 22.81 | 14.94 | 117.5 | 23.98 | 16.34 |

### Preserved positional-materialization cells (authority runtime)

`stress-columns`: 9.5 µs/projection, 604.4 retained B/projection, 127.3
transient B/projection, 45.7 KiB peak for 64 KiB, 42.3 KiB prepared set.
`stress-document`: 13.0 µs/projection, 620.4 retained B/projection, 191.3
transient B/projection, 50.7 KiB peak for 64 KiB, 57.4 KiB prepared set. Every
delivery and stress ceiling other than the seventeen timing cells, the one
memory cell, and the two scaling arms named above is within its limit.

## Recovered capture — `recovered/`

The repository's canonical current cost portfolio: one complete capture of the
head of `main`, taken immediately after COR-178 aligned every cost source with
the path production runs (`5adb0802..9676ec8a`) and nothing else had merged,
with its byte readings on the aware-timestamp path re-measured after one
production fix (*Amendment*). `before/` stays the recovery reference and `after/` the fixed regression
baseline; neither is recaptured. `comparison-before.md`, `comparison-after.md`
and `comparison-cor-173.md` are this capture's plain `--compare` renderings
against `before/`, `after/`, and the capture it replaces. This capture is the
basis every memory gate is derived from (*Memory gates* › *Basis*).

The capture this one replaces was taken at `93733e93` on macOS 26.6.2 and
narrated here as the delivery recovery's canonical portfolio, amended in place
for the `PageBuilder.add_claim` fix (470 re-measured and 8 derived readings,
recorded in its own `conditions.json`). That account belongs to the tree it was
taken from and is not restated here. Git history keeps its bytes, and a
byte-for-byte copy is kept outside Git at
`$HOME/.local/share/parallax/evidence/cor-173/recovered/`, beside the other
retained captures the comparisons are rendered against; no tool, test, or
workflow reads that path.

### Provenance

Produced from clean commit `9676ec8a75610b14894f8aabb631521185ee3764`
(`docs(python): name the evidence verifier's contract once, at verify`, the head
of `main` at capture time and already published) by `uv run --project
languages/python python languages/python/tools/cost_report.py --out
languages/python/docs/structural-metadata-envelope/recovered`, 2026-09-29
13:05:42–14:10:05 EDT (17:05:42–18:10:05 UTC, 64 minutes wall clock and
3861.749 s of recorded collection span; collector exit 0), on the same Mac17,4
(Apple M5, 10 cores, 32 GiB, arm64), now on macOS 27.0.1 build 26A434, with
CPython 3.14.7 in the project environment and 3.13.15 in a per-member throwaway
environment, and PostgreSQL 18.6 (`postgres:18.6-alpine` through
Testcontainers). `uv.lock` has moved since the outgoing capture, and this one
records its digest `99db96b8…`. OrbStack was restarted (`orb stop && orb
start`) before the run, since a VM up for days reads the live cells slow. The
machine was otherwise idle: on AC power at 100%, the collector and every child
at nice 5, with no process above 21% of one core before the run and none above
3% after it. Of the collection span, snapshot-delivery took 3502.2 s (1323.0 s
of it the leaf-type reads on 3.14), write-lowering 332.4 s, instance-state
14.3 s, and lifecycle-overhead 12.6 s.

All four members name that commit and a clean tree, none carries an incomplete
cell or an error, and snapshot-delivery classifies authoritative. The
write-lowering `workloadDigest` `860741a2…` and the Snapshot `workloadDigest`
`b6af4d92…` equal `write_lowering_digest()` and `workload_digest()` at the
producing commit. The run wrote a portfolio whose sha256 is `9dc20d3e…`; as
amended it is
`bb09c6ff45fec6170e961ee889db0e4deba3f56c45af4d892762d37bc3c478a9`.

| Member | Authority | Runtimes | Readings | Within | Outside |
|---|---|---|---:|---:|---:|
| snapshot-delivery | authoritative | 3.13, 3.14 | 596 | 81 | 9 |
| lifecycle-overhead | non-authoritative | - | 87 | 5 | 10 |
| instance-state | non-authoritative | - | 696 | 4 | 4 |
| write-lowering | non-authoritative | 3.13, 3.14 | 1230 | 0 | 0 |

`cost_report.py --verify recovered/portfolio.json` **exits 0**, states the
amendment, and reports ten advisories: nine timing ceilings over five cells and
one scaling-arm growth, none of them a memory ceiling or a memory *gate*. The run opens with
`snapshot-delivery lock freshness matches`, which names the recorded and the
inspected `lockDigest`, both `99db96b8…`, and then the path of the `uv.lock` it
read. That path is whatever clone ran the command, so it is left out here; the
rest is verbatim.

```text
the capture is amended: 364 re-measured readings changed after the run its provenance names, recorded in the adjustment of conditions.json
advisory: duplicate-include.providerFreeCpu.eager.maxMs is outside its timing ceiling
advisory: duplicate-include.providerFreeCpu.eager.minRootsPerSecond is outside its timing ceiling
advisory: duplicate-include.providerFreeCpu.page32.maxMs is outside its timing ceiling
advisory: duplicate-include.providerFreeCpu.page32.minRootsPerSecond is outside its timing ceiling
advisory: document-heavy.live.eager.maxMs is outside its timing ceiling
advisory: document-heavy.live.eager.minRootsPerSecond is outside its timing ceiling
advisory: versioned-document.live.eager.maxMs is outside its timing ceiling
advisory: versioned-document.live.page32.maxMs is outside its timing ceiling
advisory: versioned-document.live.page32.minRootsPerSecond is outside its timing ceiling
advisory: document-heavy.streamedMemory.page128PeakKiB grows 40.249 KiB between memory arms
```

The block is the amended capture against the gates re-derived from it. The
readings as the run took them, against the ceilings the outgoing basis had set,
carried two more lines: `bitemporal.interior.document.wire.transientBytes`
outside its memory gate on both runtimes (16,914 and 17,166 B/row over 16,907),
a keyed-write reading in a changed window. As amended, they read 16,221 and
16,325 (*Memory*). Against the outgoing capture's twenty
advisories under this tree — its nineteen plus the stale-lock advisory the new
`uv.lock` draws — these are ten. Every memory-ceiling advisory is gone:
`bitemporal-current.eagerMemory.peakKiB` reads 386.7 KiB on 3.14 against its
425 KiB ceiling, and the two `duplicate-include` streamed peaks are 8.8–8.9%
lower. So are the `duplicate-include` live eager and `document-heavy` live
page-32 timings and the `bitemporal-current` arm growth.

### Amendment

The capture is amended in place, an owner-approved exception to taking it once,
and `conditions.json` records the change as its `adjustment`. While the capture
was being integrated, the gate test for `leaf.timestamp.document.typed.retainedBytes`
read 5,912 and then 7,190 B/row against the 5,370 captured. The cause was
CPython's type method cache: each `utcoffset` or `strftime` call that
`_datetime` makes on an aware `datetime` creates a method-name string the cache
keeps, so every byte reading whose path reached `utc_instant` or the Timestamp
Wire spelling retained a process-dependent amount, bounded near 60 KB. PR #205
(`ecbdd36f`, on `main` at `bf287493`) returns a value already in UTC unchanged
and spells a Timestamp from its fields.

With that fix in the tree, 364 byte readings were re-measured through each
member's `--diagnostic` path, value and samples both replaced:

- Every write-lowering byte reading on both runtimes, 360. Three separate
  processes agreed on all of them to the byte. The 126 that moved are the 54
  cases whose path handles an aware timestamp — the `txtime`, `bitemporal` and
  `ancestor` keyed writes, the six acquisition levels, the 24 leaf-type
  acquisitions, and the four Timestamp inserts. 117 fell and 9 rose; the
  largest rise is that Timestamp insert, now 5,904 B/row. The other 234
  reproduced the capture exactly.
- The four `leaf-timestamp` read readings on 3.14. The peaks fell 4.8–4.9%
  (981.0 to 933.7 and 985.9 to 937.4 KiB) and the retained readings 0.2–0.3%.
  They are the only provider-free read cells whose reading children still
  disagree with the fix in place, by up to 2.4%, so the amendment takes the
  first of three runs, chosen before the other two were read.

Every timing, count and ratio reading, and every other byte reading, is as
captured. A trace of every other provider-free read path found none calling the
changed code or an aware-datetime method. `bitemporal-current` is the one live
workload with Timestamp members; its twelve live memory readings, read three
times with the fix and three times at the producing commit's tree, overlap the
unchanged-code runs or differ from them by at most 0.5% in either direction,
with no attribution, so they stay as captured. instance-state, re-measured
whole, reproduced all 258 of its byte readings exactly, and lifecycle-overhead
has none. No budget outcome moved. The scripts, logs, diagnostic documents and
the per-reading account are kept outside Git at
`$HOME/.local/share/parallax/evidence/cor-178/amendment/`, beside the diagnosis
in `timestamp-retained/`.

### Against `before/` and `after/`

`comparison-before.md` and `comparison-after.md` are the renderings. Read as
family medians of the paired per-cell deltas on one runtime, with the range of
those deltas beside each — never a ratio of pooled durations:

| Family, per runtime | Cells | vs `before/` 3.13 | vs `before/` 3.14 | vs `after/` 3.13 | vs `after/` 3.14 |
|---|---:|---|---|---|---|
| Acquisition (`acquisition.*` / `elapsedUs`) † | 6 | −48.8% (−66.3% to −36.3%) | −57.5% (−62.7% to −48.4%) | −72.5% (−76.9% to −60.2%) | −73.8% (−76.4% to −62.5%) |
| Keyed writes (46 cases / `elapsedUs`) † | 46 | −24.2% (−65.5% to +44.0%) | −31.3% (−63.6% to +14.1%) | −20.5% (−60.2% to +32.6%) | −19.8% (−58.4% to +32.2%) |
| Geometry reads (`read-*` / `<layout>.elapsedUsPerRoot`) | 18 | −5.8% (−29.6% to +4.3%) | −2.3% (−26.5% to +10.8%) | −22.3% (−45.9% to −14.4%) | −24.4% (−45.6% to −10.9%) |
| Cold plans (`plan-*` / `<layout>.elapsedUs`) | 6 | −33.9% (−46.4% to −25.7%) | −22.0% (−26.8% to −18.2%) | −20.1% (−22.4% to −16.5%) | −20.1% (−21.6% to −16.7%) |
| Positional materialization (`stress-*`) † | 2 | −2.9% (−6.2% to +0.5%) | +3.2% (−1.4% to +7.8%) | −32.9% (−36.1% to −29.8%) | −38.4% (−41.2% to −35.5%) |
| Eager live delivery (`live.eager.maxMs`) | 5 | +1.4% (−17.5% to +19.2%) | −0.2% (−17.8% to +18.2%) | −15.7% (−21.4% to −6.7%) | −15.5% (−19.3% to −7.1%) |
| Page-32 live delivery (`live.page32.maxMs`) | 5 | −0.1% (−17.9% to +14.9%) | −10.6% (−16.3% to +2.6%) | −13.1% (−14.1% to −6.4%) | −10.9% (−12.7% to −1.3%) |

† A window the source alignment changed: the pair sets a new baseline beside
two captures that measured less of production's path, and is not an
optimization or a regression (*Against COR-173's capture*).

Every family median in an unchanged window is at or below `after/` on both
runtimes. `model.prepared` retains 426,776 and 438,440 B against `after/`'s
415,992 and 427,016, the attributed growth itemized below, and forms in 3,375
and 3,322 µs against 3,738 and 3,673. Timing against these bases also carries
the OS change below; timing evidence for a change is a same-day pair, not these
comparisons.

The rows `--compare` reports missing on the base — 980 in each rendering — are
the 506 leaf-type cells, the 184 current-vocabulary counter cells of the keyed
cases, and the 290 other addresses the instruments gained after those captures
(`control-delivery`, `compact` instance-state, guarded read-plan,
`result-held-metadata`, `model-preparation` and `wire-insert-response` cells).
The 368 rows missing on the head are the legacy `calls.*` cells those captures
recorded. The `incomparable` rows are zero-valued instance-state cells (72
against `before/`, 70 against `after/`).

### Against COR-173's capture

`comparison-cor-173.md` renders `--compare
$HOME/.local/share/parallax/evidence/cor-173/recovered/portfolio.json
recovered/portfolio.json`; the base is byte-identical to `recovered/` at
`9676ec8a` in Git history. It is the program's before/after record for the
cleanup (COR-174, COR-175, COR-176), the quality gates (COR-140, COR-141,
COR-182), the declaration, float, and include work (COR-181, COR-183, COR-184,
COR-185, COR-188), and the source alignment. `--require-compatible` refuses
the pair over snapshot-delivery and write-lowering, as it should: their
envelopes disagree on `workloadDigest`, `lockDigest`, and `os`, their control
and instrument sources differ, and the leaf-type cells are present on the head
alone. The judgements below are what a reader comparing across them relies on;
they do not make the pair strictly compatible.

The rendering reports 506 rows missing on the base, which are the leaf-type
cells (66 reads, 368 keyed-insert cells with their counters, and 72
acquisition cells). The 184 rows missing on the head are the `shapeOfDeclaration`
and `entityShape` counters of the 46 keyed cases on both runtimes. Production
never called them, so the current counter vocabulary dropped them, and the
outgoing capture's vocabulary still verifies whole. The twelve `changed` count
rows are the `txtime.unchanged` counters of the verb's no-op path, and the 70
`incomparable` rows are zero-valued instance-state cells.

**Changed windows establish new baselines.** Each window below measures a
different amount of production's work than the outgoing capture's did, so its
old/new pair is recorded, not labelled a gain or a loss. Medians are per-cell
deltas against the outgoing capture on 3.13 / 3.14 and fold in the program's
production changes as well as the window's.

| Window / cells | What changed | Against COR-173 |
|---|---|---|
| `positional-materialization` (stress) | Production's own read loop: rendered fetch templates, lock, prepared schema, `_retained`; still decodes no document leaf | `maxUsPerProjection` +0.2% / +2.4% |
| instance-state `compact.*` | The model's cached graph construction, built once rather than per call | `callNs` −87.2% / −87.2%; `projectionNs` −32.7% / −32.8%; `peakBytes` −33.8% / −36.2%; retained unchanged |
| `keyed-write` | The public verbs, including the flush, at production's default Optimistic preference; `txtime.unchanged` is the verb's no-op path with no statement; retained through the increment instrument | `elapsedUs` −22.6% / −18.9% (−59.3% to +38.9%); categorical retained −37.1% / −38.1%, `txtime.unchanged` retained −99.1%; categorical transient −27.4% / −26.7% |
| `predicate-acquisition` | Public `tx.wire.update_until_where`, from the call through buffering | `elapsedUs` −30.7% / −32.1%; retained −33.8% / −30.7%; transient −40.1% / −36.9% |
| live `streamedMemory` page-size-1 cells | The warm-up stream runs without page-boundary collection | `document-heavy.page1PeakKiB` +12.4% / +12.0%; the other workloads −0.6% to −16.1% |
| live `streamedMemory.retainedKiB` | Read at page size 128 instead of 1 | −6.4% to −78.4% |
| leaf-type cells | New, on 3.14 only | No prior reading |

**Comparable windows** keep the 5% timing and 3% memory allowances. Against them:

- Geometry reads: `elapsedUsPerRoot` −6.1% / −5.3% (−10.0% to −0.7%);
  `retainedKiB` unchanged to the byte, and peaks 0.1–2.7% lower.
- Cold plans: `elapsedUs` −19.4% / −17.5%; their retained and peak ceilings
  fall 10.7–14.1% (COR-176's single query freeze and COR-183), and the
  guarded cold plans' 6.5–15.6%.
- Live delivery: `live.eager.maxMs` −3.9% / −7.2%, `live.page32.maxMs`
  −4.1% / −4.6%, `bitemporal-current` eager peak −6.7% / −10.4%, and its page-32
  and page-128 streamed peaks −20% to −27% (COR-176).
- `control-delivery` elapsed: −7.2% / −6.2%, except the timing artifact below.
- Instance-state cells outside `compact.*` are at parity. Their `callNs` cells
  are a difference of two timings and move by any amount between runs.
- lifecycle-overhead's ratios read 7–21% higher, because the denominator they
  divide by got faster; its source is unchanged.

**Instrument sources.** `conditions.json` records a digest of every instrument
and control source each member was measured through. Every source differs from
the outgoing capture's except lifecycle-overhead's and
`tests/unit/_delivery_control_support.py`. Each change is judged here:

- COR-141 edited `tests/unit/memory_instruments.py` (`60a9edc4`, `7d7f05c7`,
  `8b6ef9cb`, `e01c5e97`) and `tools/instance_state_overhead.py` (`7d7f05c7`).
  The closure reading moved onto the shared reachability walker, every reader
  refuses a process that no child-interpreter boundary started, and the
  whole-heap and live-graph readers went. Its PR states the readings
  unchanged. The `retained`, `high_water`, and `allocation` readers the
  capture tools call measure what they did.
- COR-140 changed only prose in `tools/instance_state_overhead.py`
  (`99e46dcd`), and its PR reports cost evidence unaffected apart from an
  advisory-only lock change. `90e4bcda` rewrote docstrings in the
  instance-state control and instrument.
- COR-182 routed each snapshot-delivery arm through one parent-side step in
  `tools/snapshot_delivery_overhead.py` (`c2de30ac`). Its PR states that the
  children, their order, command lines, environment, and provisioning are
  unchanged, so the readings are unchanged and comparable.
- COR-174 built `tools/instance_state_reading.py`'s projection Page through
  `PageBuilder.add_claim` (`050767ae`), as the prepared read does. The Page is
  built before `tracemalloc` starts, so no memory reading moves. The same work
  edited only a docstring in `tools/write_lowering_overhead.py` (`f13b8fe8`).
- COR-175 passes the concurrency facts to `wire_roots` in
  `tools/instance_state_reading.py` (`235e20d6`), which follows production's
  new signature in the `direct_wire` sample. COR-181 retyped
  `tests/unit/_instance_state_support.py` onto `OccurrenceMetadata`
  (`f2d26231`) with no runtime statement changed.
- COR-183 and COR-185 changed no instrument or control source. Their effects
  reach the capture only through production code: COR-183's lower
  `model.prepared` and plan retention, and COR-185's compiled `timestamptz`
  loader on the live `bitemporal-current` cells. Its Float32 costs appear
  only in the new `leaf-float32` cells.
- Every other difference is COR-178's source alignment. The changed windows
  above come from `b347f128`, `7dfa3df5`, `995439dd`, `ead78269`, `60794e7b`,
  `739403ea`, `6b4c48a6`, `fdb5f0a9`, and `1606e5aa`, and the leaf-type
  dimension from `6634dbc0`, `0862881b`, and `63e6900f`. Three are
  reading-neutral:
  - `404ce64a` reads document members from the model; all 18 stored rows and
    46 observations are identical.
  - `c5a88c7b` is the counter vocabulary above.
  - `35f49b4a` and `673c93c7` move `FixedClock` and name the write cases'
    sources.

**Accepted increases in unchanged windows.** Two memory readings went beyond
the 3% allowance, `model.prepared.family` and `control-held`
`large.closed.retainedKiB`. Both are attributed and were accepted before this
capture became the basis, as was `model.prepared`, whose rise is inside the
allowance but moves a gate.

- `model.prepared` retains +10,592 / +11,232 B (+2.55% / +2.63%), and
  `model.prepared.family` +1,216 / +1,336 B (+5.46% / +5.92%). A sweep of every
  first-parent commit since the outgoing capture accounts for every byte:
  - COR-176 `56c5ba6d` (one `_OccurrenceFacts` per Value Object occurrence
    path): +9,376 / +10,400;
  - COR-140 `f525fa88` (one `BoundShape` per occurrence and member
    selection): +5,216;
  - COR-176 `b36ad429` (one referential-rank record per Entity): +1,160;
  - COR-175: +328;
  - COR-174 `87c34e66`: −2,688;
  - COR-183: −2,808 / −3,192.

  `.family`'s rise is mostly COR-176's.
- `control-held` `large.closed.retainedKiB` is +12.8% / +12.9% (63.4 to 71.5
  and 68.1 to 76.9 KiB). This is COR-176 `ee51ee78`: a Typed result keeps its
  `EntityGraphConstruction` so that `Snapshot.wire` can skip the
  correspondence check for classes the model proved. The retention is
  intended, and the address is not gated.

**The `control-delivery` timing artifact.** `wire.page32.roots200.elapsedUs`
reads +6.1% to +13.1% on both runtimes and both shapes. The Typed lane moves
by about +15–20% too, hidden by earlier gains. The cause is in the harness, not
production: since `63e6900f`, the snapshot reading child imports the leaf-type
support module for every address, which adds about 70,000 GC-tracked objects
and about 3.5 ms to each full collection. It affects timing only, and timing is
never gated. It is accepted into this baseline. A child that imports only the
support module its address needs will remove it.

**The OS change.** The outgoing capture ran on macOS 26.6.2 and this one on
27.0.1. A diagnostic of the outgoing capture's producing commit on 27.0.1,
against that capture's as-taken readings, found memory OS-invariant: every
delivery, instance-state, and lifecycle byte reading was exact, and
write-lowering stayed within the instrument's same-OS jitter. No non-live
timing cell was more than 5% slower (289 cells, median new/old 0.947), and the
live cells read 0.86–1.01 once OrbStack was restarted. No offset enters this
record. A timing difference under about 5% in an unchanged window is not
credited to code, because OS and thermal state are not separated from it.

### Leaf-type readings

The leaf-type cells have no prior reading; these are their first. On 3.14,
Columns layout (the Document layout's reads are within 2% of these):

| Type | Read (µs/root) | Read retained (KiB) | Typed insert (µs/row) | Wire insert (µs/row) | Acquisition (µs/row) |
|---|---:|---:|---:|---:|---:|
| String (control) | 148.5 | 480.5 | 550.9 | 673.5 | 153.2 |
| Boolean | 110.8 | 162.5 | 486.9 | 555.3 | 118.8 |
| Int32 | 159.5 | 354.5 | 510.0 | 644.7 | 167.8 |
| Int64 | 165.8 | 366.5 | 531.6 | 678.2 | 171.9 |
| Float32 | 811.6 | 212.0 | 1,021.8 | 1,518.0 | 588.3 |
| Float64 | 322.4 | 212.0 | 578.3 | 677.5 | 270.8 |
| Decimal | 935.0 | 271.8 | 1,075.2 | 1,894.2 | 722.5 |
| Bytes | 399.1 | 313.0 | 566.3 | 736.3 | 331.2 |
| Date | 427.2 | 193.0 | 622.8 | 855.6 | 389.1 |
| Time | 567.3 | 278.0 | 678.6 | 945.2 | 479.1 |
| Timestamp | 1,007.1 | 302.8 | 957.5 | 1,443.8 | 819.7 |
| Uuid | 572.0 | 321.3 | 913.0 | 1,264.3 | 433.6 |

The String read and Typed insert are the `read-width-64` and
`geometry.width-64.columns.typed` controls. Float32 reads cost 2.5 times
Float64's because decoding and publication each search for the shortest
spelling that rounds back to the value.

### Memory

**Against the ceilings in force when the capture was taken.** Of the 324
gated readings the outgoing basis had a ceiling for (162 addresses, two
runtimes), all 324 are under it as amended. As the run took them, 322 were: the
two that were not are the `bitemporal.interior.document.wire` high-water marks,
16,914 and 17,166 B/row against 16,907, in the changed `keyed-write` window,
which now includes the verb's Wire validation and the flush. The amendment
reads them at 16,221 and 16,325; the closest to its old ceiling is now
`ancestor.width-64.document.typed`'s high-water mark at 99.1% on 3.14, in the
same window. In unchanged windows, the
closest are `model.prepared.family` retained at 96.3% of its ceiling on 3.14 and
`model.prepared` at 93.3%, both the accepted increases above. The old-ceiling
result is recorded before any re-derivation, so a new basis cannot hide a
regression behind a raised ceiling. The 184 leaf-type readings had no ceiling to
be read against and enter the gates with this derivation.

**Scaling domains.** Both acquisition domains are monotone non-increasing on
both runtimes across the 8, 32 and 128-row levels. `acquisition.columns` retained
1,523.0 → 1,032.5 → 911.9 and transient 4,640.2 → 2,650.8 → 2,003.5 B/row on
3.13, retained 1,742.5 → 1,135.4 → 985.6 and transient 4,822.4 → 2,696.1 →
2,050.8 on 3.14. `acquisition.document` retained 2,547.0 → 2,038.5 → 1,913.4 and
transient 4,862.8 → 3,010.7 → 2,469.8 on 3.13, retained 2,768.5 → 2,141.9 →
1,987.2 and transient 5,052.9 → 3,022.2 → 2,436.3 on 3.14.

**Re-derivation.** The gates were then re-derived from this capture, as
amended, under the
unchanged rule, and `spec/memory-gates.yaml` names this `recovered/portfolio.json`
as its basis with the header, advisory allowances, and scaling domains verbatim.
*Basis* above itemizes the movements.
