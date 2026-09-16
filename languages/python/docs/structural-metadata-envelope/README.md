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
delta near either allowance is therefore weak evidence on its own. Timing
comparisons are advisory everywhere: `cost_report.py --verify` reports a timing
ceiling exceeded and fails only for invalid, incomplete, unpublished, dirty,
stale, or memory-limit-exceeding evidence.

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

Retained checkpoints: `keyed-write` samples with the serialized rows, the
prepared instruction, the buffered item, and the settled plan alive, before
lowering; `predicate-acquisition` samples inside the transaction body with the
group buffered, before any flush; `model-preparation` samples with the prepared
selection alive; a geometry read samples with the delivered results alive.

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
`READ_GEOMETRY_ROOTS`, `STRUCTURAL_LAYOUTS`) and enters the write member's
`workloadDigest` through `structural_digest()` together with the bytes of the
three fixture modules, and the Snapshot member's through `workload_digest()`.
The levels were chosen from diagnostic trial runs on the capture runner and then
frozen; the trials are not part of the baseline.

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
the six categorical Entities, the ten geometry Entities, and the two acquisition
Entities. The Entity Class declarations and their Value Object classes are
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
