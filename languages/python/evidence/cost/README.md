# Python cost evidence

The [current portfolio](current/portfolio.json) is the canonical complete capture
used by the cost verifier and the [memory gates](../../spec/memory-gates.yaml).
The [measurement retention rule](../../../../TESTING.md#measurement-retention)
owns what belongs in Git and how future runs are stored.

## Capture roles and provenance

| Capture | Role | Producing commit | Captured |
|---|---|---|---|
| [current](current/portfolio.json) | Current verification input and memory-gate basis | `01a0ef034f21046d12b654f9e9e9bed6ffa6b8eb`; write lowering `b3ebdfcf3532ecf885783947dbc66e184fe95c31` | 2026-10-29 |
| [structural-metadata-before](structural-metadata-before/portfolio.json) | Fixed recovery reference | `b7abe2d055fd3e0974829616f2de99b94ad5af97` | 2026-09-16 |
| [structural-metadata-after](structural-metadata-after/portfolio.json) | Fixed regression comparison base | `1636e9f0ce072dce25ddd1ebeabd0b1368b65031` | 2026-09-17 |

The historical bases have four members and predate the conditions and duration
writers. Their missing sidecars prevent establishing source and interpreter
compatibility with `--require-compatible`; they remain descriptive comparison
bases with their original provenance.

The current capture has five members: Snapshot delivery, write lowering, instance
state, lifecycle overhead, and feature boundaries, with no errors, incomplete
cells, or collector failures. Write lowering names a clean descendant of the
other members' clean producing commit, as its recorded member-replacement
adjustment assigns. Snapshot delivery is authoritative under its embedded
Budget Contract; the other members have their own protocols and are
non-authoritative.

The recorded commit is the fact of what was captured. Verifying an envelope
reconstructs its embedded Budget Contract and checks internal consistency
without resolving that commit; the ancestry advisory alone consults Git history.
This is an integrity check of reviewed evidence, not an attestation that the
observations cannot be forged.

Rebase and squash merges rewrite branch commits. Snapshot redigest requires an
ancestor of the inspected checkout; write-lowering redigest accepts the exact
resolvable producing commit after proving its captured sources and workload
identity. Prefer capturing at a commit already on `main`, so source history
remains available. The current capture was taken on its change's branch because
that change made the previous capture stale; its producing commits remain the
original branch commits after a rebase merge.

The current collector ran on 2026-10-29, 17:38:54–18:42:46 UTC, in 63m51s
wall time. Its write-lowering children refused to decode the grouped
cross-object cells' zero `largestOrderedInvocation` counts, so that member
produced no envelope. After the decoder accepted zero work counts,
`--replace-member` re-measured write lowering alone at its recorded commit,
19:55:21–20:09:34 UTC, in 14m13s; the adjustment in conditions records both
commits, the replaced failure, and both intervals. Both ran on a Mac17,4 (Apple
M5, 10 cores, 32 GiB), macOS 27.0.1 build 26A434, with CPython 3.13.18 and
3.14.8 and PostgreSQL 18.6 under OrbStack 2.2.5. OrbStack was restarted, and the
compiled loaders were rebuilt and checked on both interpreters, before the
collector ran.
[Conditions](current/conditions.json) record interpreter identities, instrument
source hashes, and the adjustment; [durations](current/durations.json) record
collection telemetry. The dependency lock SHA-256 is
`5b94947c4c258495210274171de2408fcba6c45b4bffc9f6d6074d3f050d2956`.
The portfolio SHA-256 is
`aa58e26cf5e31f240b4db9d0447b00726816612ce3752ae0ea00aec3756fec6c`, and the
conditions SHA-256 is
`b6ca54f9b143fac069a5dc4fb1f5f525a58f3993bab5b2dd1362920be12d8e0d`.

No other session or measurement ran during either run; macOS background
daemons were active. The collector ran on AC power, and the replacement on
battery power with low-power mode off. Before the collector the load average was
3.5 (one minute) and 2.6 (five minutes), 2.6 when the measurement lock was
taken, and 2.9 and 3.1 at the end. Before the replacement it was 4.6 and 8.7,
2.9 when the lock was taken, and 3.0 and 3.3 at the end. The runs are not
evidence of quiet-machine timing stability. The outgoing capture used the same
host, interpreters, PostgreSQL, and dependency lock. The historical bases used
macOS 26.6.2 and CPython 3.13.15/3.14.7 on the same machine, so
current-versus-base timings cross host and interpreter conditions as well as implementation changes.

Against the superseded `731527616` capture, gate addresses grew from 352 to 362:
the `batch-insert` window's 10 gates were added, and none was removed. The
comparison crosses a changed write-lowering workload digest (`9c2ca81c…` to
`ff17d9c8…`) with new cases and counters, changed Snapshot control sources and
instrument, and changed write-lowering, instance-state, and feature-boundary
instruments; `--require-compatible` refuses the Snapshot and write-lowering
pairs. Fourteen write-lowering readings rose past their former gates, and all
were accepted as rebaselines under the unchanged rule:

- Cross-object `execution.transientBytes` and
  `execution.transientBytesPerObject` for
  `bitemporal.deferred-32x32.columns.typed`,
  `bitemporal.deferred-32x12.document.wire`,
  `bitemporal.requesting-32x12.document.wire`,
  `bitemporal.interior-64.document.wire`, and `txtime.changed-130.columns.typed`
  read 12–162% over their former gates. Grouped inserts carry no row cap and a
  Write Group now holds up to 1,024 writes, so one array-bound statement holds a
  whole group's rows: on 3.14 the totals read 458,850, 173,042, 177,290,
  164,711, and 187,719 B. In the same cells, statements fall 97–99.8%,
  `execution.elapsedUs` falls 59–66%, `plan.retainedBytes` falls 7–34%, and
  `binding.transientBytes`, where measured, falls 20–25%. No grouped-insert
  bound was reintroduced.
- `geometry.sparse-64` and `ancestor.sparse-64` Columns and Document
  `retainedBytes` read 2,368 and 1,160 B/row on 3.14 (2,320 and 1,128 on 3.13)
  against 1,602 and 1,021. Nested occurrences keep their full-width form, so
  sparse nested retention grows with declared width.

Rederivation moves 310 gates. Of the 39 that rise, 14 are those readings; six
are `geometry.sparse-64` `transientBytes` (2.7–3.8%, the same cause) and
`model.prepared` and `model.prepared.family` (1.7–4.0%, eager write
preparation), all within their former gates; and 19 rise by at most 2.2%,
within the comparison's byte allowance. Of the 271 that fall, 228 are write
lowering and 37 fall by at most 1%; dense insert `retainedBytes` gates fall up
to 58% (6,222 to 2,605 B/row). Snapshot's advisory Budget Contract timing
outcomes went from 6 to none outside.

Other readings beyond the movements expected of these changes were reviewed and
accepted. All are advisory or ungated. Snapshot live `versioned-document`
`streamedMemory.page1PeakKiB` rose 20% on 3.14 (24.0 to 28.9 KiB) and fell 3% on
3.13. Seven Snapshot timing cells read 5–18% slower: `control-guarded-3` eager
delivery and three read-plan compilations on 3.13, and one per-root cell each
for `read-width-64` and `leaf-float64`. Write-lowering `model.prepared.family`
elapsed rose 17.5% on 3.14, some cross-object `binding.elapsedUs` 5–8%, and
`txtime.target-patch.document.wire` 5.8%. Instance-state microtimings read 49
slower and 66 faster, and feature-boundary timings 7 slower and 18 faster.

On `main`'s history these changes span `39c878576..01a0ef034`, where
`39c878576` carries `731527616`'s tree after its rebase merge; write lowering
also includes `01a0ef034..b3ebdfcf3`, which changed only the decoder and
replacement tooling. The span includes one-pass Page root publication, typed
array binds for memberships, gathered keys, multi-row inserts, and keyed-update
runs, positional write rows prepared through compiled authoring plans, grouped
deletes and temporal effects, and the 1,024-write Write Group bound. No
matched-source reading separates them, so changes are not attributed to
individual commits. All 80 live delivery timing cells read faster. Readings that
touch no database also moved: 30 of 74 provider-free delivery timing cells read
faster and 2 slower, and the lifecycle-overhead arms over their in-memory port
read 15–21% faster at their medians, while their paired differences stayed
within noise, so their relative overhead ratios rose 21–28%. The live movement
is therefore not separated from run conditions. The completed capture and its
invalid first attempt, the frozen predecessor portfolio, conditions, durations,
gates, and README, the automated former-gate assessment and derivation deltas,
the comparison and its compatibility refusal, host and run logs, the helper
scripts, and the exact commands are archived at
`~/.local/share/parallax/evidence/cor-251/cost-capture/`; its `SHA256SUMS`
manifest has SHA-256
`ba75cb79e2b57a7fe03dde8181b4c1e5a8178926cdab47eb6dfff5293e6008b6`.

## Method and interpretation

The executable workload manifests and reading instruments own workload levels,
matrix addresses, and measurement windows. Start with
[`cost_report.py`](../../tools/cost_report.py) and
[`workloads.py`](../../packages/parallax-conformance/src/parallax/conformance/workloads.py).
The [Budget Contract](../../spec/budget-contract.yaml) owns capture authority
and its sampling requirements. Workload digests identify each workload's
measured fixture sections and parsed model, not comments, formatting, or
fixture keys no workload reads; conditions identify the instruments. A workload
digest alone does not establish that two instruments are equivalent.

Isolated cell readers use a fresh child interpreter, `PYTHONHASHSEED=0`, three
warm-ups, and nine measured samples per cell. The value is the median; samples
inside the envelope allow the verifier to recompute it. Structural matrices run
on both supported minors, with leaf-type families on the newest alone.
Lifecycle overhead instead uses 200 warm-ups and 3,000 interleaved plain/observed
pairs on 3.14. Its p95 differences include scheduler and collection differences
between arms and do not bound dispatch-tail latency. With the in-memory port,
relative observation overhead uses a small denominator; database latency changes
that ratio without changing dispatch work. A stable quiet-machine lifecycle
timing baseline remains open as [D-94](../../docs/deferred-ledger.md#d-94--the-execution-lifecycle-overhead-baseline-lacks-stable-quiet-machine-timings).

Timing changes within 5% and byte changes within 3% are noise allowances in the
comparison tool; counts are exact. These allowances came from repeated quiet
write captures, not a confidence interval applicable to every host or workload.
Near-boundary changes are weak evidence. Comparisons pair matching subject,
runtime, window, workload, cell, and unit; missing cells and zero bases need to
be read alongside any delta. Use `--require-compatible` when compatibility must
be established before arithmetic. Even compatible captures are not automatically
isolated causal trials.

Retained checkpoints run separately from uninterrupted elapsed and high-water
windows, after 200 seam warm-ups. They measure newly reachable bytes at the named
production stage. Shared subtrees count once; checkpoints are not additive.
The high-water mark is a net rise over a window floor, not cumulative allocation.
Warmed shared class/model metadata already belongs to that floor.

Instance-state comparisons take all arms in one child on one tree, so both sums
in `1 - sum(after) / sum(before)` use the same object layout. Mixing a frozen
legacy sum from an older layout with a current compact sum charges slots to one
arm alone and distorts the result. The legacy publication fixture and the
ordinary validating constructor answer different comparisons. Ordinary values
carry no synthetic lifecycle state; published values include the state they
actually retain. Instance-state decoded payload leaves are allocated before the
window and excluded structurally: a node counts its references, not those leaves.

Window boundaries matter. Keyed writes include the public verb through commit,
production bind adaptation, and driver serialization, but exclude the preceding
read and caller-authored inputs. Target writes include their own coverage read,
so their delta against observed writes cannot price target addressing alone.
Positional materialization starts after root execution and stops at a finished
Page, before publication; deferred Document leaves are therefore not decoded in
that window. Read-plan
compilation prices one entry in an otherwise empty cache, excluding the cache
shell and model preparation; it says nothing about eviction or mixed-query reuse.
Json-leaf payload size and malformed-read evidence volume are not measured
dimensions. Provider-free delivery excludes parsing and provider work; live
delivery includes them.

October 7 diagnostic pairs on CPython 3.14.7/3.14.8 did not reproduce a consistent
interpreter-patch effect or explain an earlier live slowdown. They were sequential
and host activity remained a confounder. Historical recovered live timings were
excluded as a timing baseline; those diagnostics did not rehabilitate them.
Current cross-day comparisons likewise describe observations under their recorded
conditions rather than attributing every change to production code.

## Collect, compare, reclassify, redigest, and replace a member

Run from the repository root. Capture into a run directory outside Git:

```sh
uv run --project languages/python python languages/python/tools/cost_report.py \
  --out /tmp/parallax-cost-run
```

The collector checks authority before measuring. A canonical capture requires a
clean checkout and matching authority; `--diagnostic` produces explicitly
non-canonical observations. Consult [testing](../../TESTING.md) for verification
ownership and focused iteration commands.

Generate a comparison on demand:

```sh
uv run --project languages/python python languages/python/tools/cost_report.py \
  --compare languages/python/evidence/cost/structural-metadata-before/portfolio.json \
  languages/python/evidence/cost/current/portfolio.json > /tmp/cost-comparison.md
```

For an authority-only contract correction, first copy the capture directory,
including its conditions and durations, to a disposable directory, then run:

```sh
uv run --project languages/python python languages/python/tools/cost_report.py \
  --reclassify /tmp/parallax-cost-run/portfolio.json
```

Reclassification rewrites that portfolio, records the adjustment in conditions,
and regenerates its summary without taking measurements. It requires the same
authority minor, unchanged observations, and no prior adjustment. It does not
require separate member JSON files. Do not reclassify the fixed historical bases.

When the workload digest's definition changes without changing what was
measured, re-state a capture's digest instead of recapturing:

```sh
uv run --project languages/python python languages/python/tools/cost_report.py \
  --redigest languages/python/evidence/cost/current/portfolio.json
```

The command selects stale Snapshot and write-lowering identities independently.
For Snapshot, it proves that the measured inputs at the producing ancestor
digest to HEAD's identity, and that the commit's own code reports HEAD's
generated-key offset, frozen manifests, and generated dataset rows.

For write lowering, it checks each captured workload source hash against the
exact producing commit and reconstructs that commit's recorded digest under
either the legacy raw-source definition or the current definition. It then
proves that executable workload syntax and the commit's frozen structural and
leaf manifests equal HEAD's. The current identity includes the shared workload
spelling helper and ignores comments, formatting, standalone documentation
strings, and only the workload's own digest declaration. Assigned literals and
operational expressions remain part of the identity. Prose edits therefore
need no amendment after migration to the current definition.

All required proofs finish before writing. The command amends only stale
workload digest fields and records their old and new values in conditions;
readings, samples, comparisons, durations, producing provenance, and captured
instrument hashes remain unchanged. It refuses a changed Budget Contract, a
prior adjustment, missing producing history or source proof, or a meaningful
workload or frozen-input change and writes nothing. Use a new capture for a
changed measured workload. Do not amend the fixed historical bases.

When a complete canonical capture failed to produce one member, re-measure that
member alone instead of recapturing every member:

```sh
uv run --project languages/python python languages/python/tools/cost_report.py \
  --replace-member write-lowering --from /tmp/parallax-cost-run \
  --out /tmp/parallax-cost-run-completed
```

The member must be absent from the capture with exactly one recorded collection
failure; a member the capture produced is never re-measured. The checkout must
be clean and descend from the kept members' single producing commit. Before
measuring, the command proves that HEAD changed nothing the kept members
measured through: their recorded instrument and control sources, workload
digests, and Budget Contract equal HEAD's, and no test module those sources
import, production package, the dependency lock, or any tool other than the
collector and the replaced member's own instruments changed. It then passes the canonical authority
preflight and measures the member exactly as collection does, refusing a
repeated failure, a dirty or different producing commit, or an interpreter
other than the kept members'.

It writes a new directory and never the original. The kept envelopes,
conditions, and duration spans are unchanged beside the new member, its
conditions, and its span. The adjustment in conditions records the member, the
original and replacement commits, the replaced failure, and both collection
intervals. Verification accepts the members' differing commits only as that
record assigns them, and verification and comparison state the replacement. It
refuses a capture that already records an adjustment.

The former previous/COR-191 comparisons can be reconstructed using Git revisions
`3535d3e0f` and `dc65ef88`. Export both `portfolio.json` and `conditions.json`
from `languages/python/docs/structural-metadata-envelope/recovered/` at the
chosen revision into the same temporary directory, then compare that portfolio
with the current one. A shallow clone may need those revisions fetched first.
The remaining working-tree files alone do not reproduce those historical views.
The complete retired measurement account remains in
[Git history](https://github.com/davidsunglee/parallax/blob/c7dd36498c31aed00647126bd9c6c99a8c9c5cc7/languages/python/docs/structural-metadata-envelope/README.md).
