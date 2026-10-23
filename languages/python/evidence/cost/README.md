# Python cost evidence

The [current portfolio](current/portfolio.json) is the canonical complete capture
used by the cost verifier and the [memory gates](../../spec/memory-gates.yaml).
The [measurement retention rule](../../../../TESTING.md#measurement-retention)
owns what belongs in Git and how future runs are stored.

## Capture roles and provenance

| Capture | Role | Producing commit | Captured |
|---|---|---|---|
| [current](current/portfolio.json) | Current verification input and memory-gate basis | `c51ca3eacf1f89b5d039853a9cd66179a8e6d4b7` | 2026-10-23 |
| [structural-metadata-before](structural-metadata-before/portfolio.json) | Fixed recovery reference | `b7abe2d055fd3e0974829616f2de99b94ad5af97` | 2026-09-16 |
| [structural-metadata-after](structural-metadata-after/portfolio.json) | Fixed regression comparison base | `1636e9f0ce072dce25ddd1ebeabd0b1368b65031` | 2026-09-17 |

The historical bases have four members and predate the conditions and duration
writers. Their missing sidecars prevent establishing source and interpreter
compatibility with `--require-compatible`; they remain descriptive comparison
bases with their original provenance.

The current capture has five members: Snapshot delivery, write lowering, instance
state, lifecycle overhead, and feature boundaries. All name the same clean
producing commit, with no errors, incomplete cells, or collector failures.
Snapshot delivery is authoritative under its embedded Budget Contract; the
other members have their own protocols and are non-authoritative.

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

The current collector completed on 2026-10-23, 03:46:44–04:56:15 UTC, in
69m30s wall time. It ran on a Mac17,4 (Apple M5, 10 cores, 32 GiB), macOS
27.0.1, with CPython 3.13.17 and 3.14.8 and PostgreSQL 18.6.
[Conditions](current/conditions.json) record interpreter identities and instrument
source hashes; [durations](current/durations.json) record collection telemetry.
The dependency lock SHA-256 is
`35b64b5d8e2caf6927fe70d5714a73d3bdf9ba4e3d6f2244a8767d054f4af870`.
The portfolio SHA-256 is
`1c1d73f2f5028051f51ea158f21c6c44ac1d6fd97d70dfa2503fa7bd6f7e7707`.

No competing measurements ran, but other interactive sessions were active: the
load average was 3.6 (one minute) and 7.4 (five minutes) at the start. Power
state was not recorded. The run is not evidence of quiet-machine timing
stability. The historical bases used macOS 26.6.2 and CPython 3.13.15/3.14.7 on
the same machine, so current-versus-base timings cross host and interpreter
conditions as well as implementation changes.

Against the superseded `90ff69ccb` capture, no memory reading rose past its
former gate and every gate address was kept; the comparison crosses a CPython
3.13 patch release (3.13.16 to 3.13.17) and a dependency lock change
(`bc4f54c3…` to `35b64b5d…`) as well as implementation changes. Write lowering
adds five deferred-span `cross-object-flush` workloads, whose flushes also
answer a range-binding region and their coverage reads, and 30 gates, for 352.
Rederivation moves 236 existing gates: 208 rise and 28 fall, 156 of the rises
by at most 1%. The largest rises are the changed-ancestor successors' retained
bytes, 924 to 1012 B/row (9.5%), and transient bytes, up to 7.3%; target
writes' transient bytes rise 3.0–5.4%. Read from the source at the base of the
deferred-grouping change, the changed-ancestor retained bytes and a Bitemporal
target replacement's transient bytes already stand at their new levels, so those
rises predate that change. Cross-object plan retention falls 1.9–2.4%, which the
same base-against-result reading attributes to immutable sharing in planning,
and Transaction-Time unchanged amendments' transient bytes fall up to 3.9%.
Snapshot memory gates moved by at most 2%. Snapshot's advisory
Budget Contract timing outcomes went from 16 to 22 outside: eight new live,
first-result, or provider-free cells and two former ones back within. No read
path changed, so these are attributed to run conditions. The cross-object
family took 11m12s of the collection, 9m15s of it the deferred spans. These
span `90ff69ccb..c51ca3eac` and are not attributed to individual commits
except where stated. The raw capture, its frozen predecessor gates, the
automated old-address assessment and derivation deltas, and the per-source
attribution readings are archived at
`~/.local/share/parallax/evidence/cor-227/`; its `SHA256SUMS` manifest has
SHA-256 `024612b5447c013001cbaa3f2d2bb6cebc55c1884154c862871e5dbd649ba8e6`.

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

## Collect, compare, reclassify, and redigest

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

The former previous/COR-191 comparisons can be reconstructed using Git revisions
`3535d3e0f` and `dc65ef88`. Export both `portfolio.json` and `conditions.json`
from `languages/python/docs/structural-metadata-envelope/recovered/` at the
chosen revision into the same temporary directory, then compare that portfolio
with the current one. A shallow clone may need those revisions fetched first.
The remaining working-tree files alone do not reproduce those historical views.
The complete retired measurement account remains in
[Git history](https://github.com/davidsunglee/parallax/blob/c7dd36498c31aed00647126bd9c6c99a8c9c5cc7/languages/python/docs/structural-metadata-envelope/README.md).
