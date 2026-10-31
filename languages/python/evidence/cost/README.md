# Python cost evidence

The [current portfolio](current/portfolio.json) is the canonical complete capture
used by the cost verifier and the [memory gates](../../spec/memory-gates.yaml).
The [measurement retention rule](../../../../TESTING.md#measurement-retention)
owns what belongs in Git and how future runs are stored.

## Capture roles and provenance

| Capture | Role | Producing commit | Captured |
|---|---|---|---|
| [current](current/portfolio.json) | Current verification input and memory-gate basis | `c5b49ddd3560a706865d10d631b9de1d74324a50` | 2026-10-31 |
| [structural-metadata-before](structural-metadata-before/portfolio.json) | Fixed recovery reference | `b7abe2d055fd3e0974829616f2de99b94ad5af97` | 2026-09-16 |
| [structural-metadata-after](structural-metadata-after/portfolio.json) | Fixed regression comparison base | `1636e9f0ce072dce25ddd1ebeabd0b1368b65031` | 2026-09-17 |

The historical bases have four members and predate the conditions and duration
writers. Their missing sidecars prevent establishing source and interpreter
compatibility with `--require-compatible`; they remain descriptive comparison
bases with their original provenance.

The current capture has five members: Snapshot delivery, write lowering, instance
state, lifecycle overhead, and feature boundaries, with no errors, incomplete
cells, collector failures, or adjustments. Every member names the same clean
producing commit. Snapshot delivery is authoritative under its embedded Budget
Contract; the other members have their own protocols and are non-authoritative.

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
that change made the previous capture stale; its producing commit remains the
original branch commit after a rebase merge.

The current collector ran on 2026-10-31, 19:08:50–20:13:53 UTC, in 65m04s wall
time, on a Mac17,4 (Apple M5, 10 cores, 32 GiB), macOS 27.0.1 build 26A434,
with CPython 3.13.18 and 3.14.8 and PostgreSQL 18.6 under OrbStack 2.2.5.
Every tracked file and every package source-root file was recorded by digest,
size, and modification time immediately before collection and was unchanged
afterwards. The only compiled extensions under the package source roots were
the `parallax-postgres` loaders, whose sources are unchanged since the outgoing
capture. [Conditions](current/conditions.json) record interpreter identities,
the production origins each member's measuring processes loaded, and instrument
source hashes; [durations](current/durations.json) record collection telemetry.
The dependency lock SHA-256 is
`5b94947c4c258495210274171de2408fcba6c45b4bffc9f6d6074d3f050d2956`.
The portfolio SHA-256 is
`e4c48c1a2759296a021da3b8a5f81ec1029269a5f70bd74439acae90694385b4`, and the
conditions SHA-256 is
`5be0561ea7cfc9694ba30bdef69a0123df3b6577d57999618d783b0b3c88bf0c`.

The machine-wide measurement lock kept other measurements out of the run. Its
quiet-load wait was disabled because macOS background daemons kept the
one-minute load average near 4–5 throughout. The collector ran on AC power.
Before the collector the load average was 4.2 (one minute) and 12.1 (five
minutes, decaying from an earlier spike), and 4.7 and 4.8 at the end. The run is
not evidence of quiet-machine timing stability. The outgoing capture used the
same host, interpreters, PostgreSQL, and dependency lock at a load average near
3. The historical bases used macOS 26.6.2 and CPython 3.13.15/3.14.7 on the same
machine, so current-versus-base timings cross host and interpreter conditions as
well as implementation changes.

The outgoing capture's producing commits carry the trees of `381b72cf8` and, for
write lowering, `d2ff555a8` on `main`'s history after their rebase merge. The
changes since span `381b72cf8..c5b49ddd3`: `main`'s core and conformance fixes
up to `3884dbd81`, then fused read construction (proved rows recorded judged,
Typed graphs published by node index, shared Typed and Wire node provenance,
Wire rendered from prepared facts, stored documents decoded through one
compiled plan, less per-row Page assembly and Typed fill work), the scalar-type
and scaling-root-count renames, and the measurement children's origin checks.
No matched-source reading separates them, so changes are not attributed to
individual commits. Gate addresses compare under the mechanical renames: Snapshot
workload `leaf-<type>` becomes `scalar-<type>`, write-lowering case
`leaf.<type>.<layout>.<ingress>` becomes `scalar.<type>.<layout>.<ingress>`, and
gate keys follow their workloads; every other address is unchanged.

All 362 gate addresses remain, and no reading is past its former gate.
Rederivation moves 154 gates: 105 fall and 49 rise. Of the rises, 29 are at most
1% and 6 are 1–3%. The 14 between 3% and 10% are read-plan and prepared-model
memory and one keyed-write window:

- Snapshot `plan-depth-1`, `plan-depth-8`, and `plan-width-64` Columns
  `retainedKiB` read 7.7% higher and `peakKiB` 4.0% higher, and
  `control-guarded-2` and `-3` `plan.cold.retainedKiB` 3.4% and 3.0% higher.
- Write-lowering `model.prepared` `retainedBytes` and `transientBytes` read
  5.0% and 4.9% higher, and `model.prepared.family` 9.6% and 6.8% higher.
- Write-lowering `txtime.unchanged.columns.wire` and
  `txtime.unchanged.document.wire` `transientBytes` read 6.1% higher (2,769 to
  2,937 B/row on 3.14).

The largest falls are Snapshot scalar-type and nested read peaks, by up to 9.5%.
Snapshot's advisory Budget Contract outcomes stay at none outside, and the
instance-state and lifecycle-overhead outcomes are unchanged. Verification reports
three streamed-memory scaling advisories on 3.14, against two before: between
200 and 2,000 roots, `bitemporal-current` `page32PeakKiB` grows 19.7 KiB (10.4
before), `bitemporal-current` `page128PeakKiB` 19.0 KiB (19.6), and
`document-heavy` `page128PeakKiB` 18.7 KiB (71.5), against a 16 KiB allowance.

Provider-free delivery timings all read faster, at a median of 26%, and control
delivery at a median of 11%. Live delivery is mixed. Every first-result cell
reads slower, 10–111% on both runtimes, while 27 of the 30 other live timing
cells read faster. Read-plan compilation reads 8–20% slower on every cell.
Windows outside the read path also read slower: write lowering at a median of
8%, feature-boundary scalar-collection encoding 10%, and lifecycle overhead 6%.
These timings do not separate an implementation effect from the higher
background load. The completed capture, its measured-input record, audits,
promotion report, memory and timing comparisons, the outgoing evidence, and the
paired final-acceptance runs are archived at
`~/.local/share/parallax/evidence/cor-259/runs/phase7-final-cost/`; its
`SHA256SUMS` manifest has SHA-256
`dc2063c9e55114724f70b0285189f030621fb81b496bab00c58d09f903cf6a41`.

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
on both supported minors, with scalar-type families on the newest alone.
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
scalar-type manifests equal HEAD's. The current identity includes the shared workload
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
