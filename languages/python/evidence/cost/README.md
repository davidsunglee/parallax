# Python cost evidence

The [current portfolio](current/portfolio.json) is the canonical complete capture
used by the cost verifier and the [memory gates](../../spec/memory-gates.yaml).
The [measurement retention rule](../../../../TESTING.md#measurement-retention)
owns what belongs in Git and how future runs are stored.

## Capture roles and provenance

| Capture | Role | Producing commit | Captured |
|---|---|---|---|
| [current](current/portfolio.json) | Current verification input and memory-gate basis | `bc9add4bea1bc740b60ed4e28bc3413e186f8f17` | 2026-10-19 |
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
Rebase and squash merges rewrite branch commits, so capture at a commit already
on `main` and land the evidence on top of it. This is an integrity check of
reviewed evidence, not an attestation that the observations cannot be forged.

The current collector completed on 2026-10-19, 11:59:25–12:58:45 UTC, in
59m19s wall time. It ran on a Mac17,4 (Apple M5, 10 cores, 32 GiB), macOS
27.0.1 build 26A434, with CPython 3.13.16 and 3.14.8 and PostgreSQL 18.6.
[Conditions](current/conditions.json) record interpreter identities and instrument
source hashes; [durations](current/durations.json) record collection telemetry.
The dependency lock SHA-256 is
`ba94b858fe8d97e5b38e66362623f67e2e6634515530972af4459e0dcee51334`.
The portfolio SHA-256 is
`2131a987df9a18e2c359ee45f0810ed2d3de681f4032b4e8d8fa75683e07f1fd`.

No competing tests, measurements, or agents ran, and the OrbStack VM was
restarted immediately before collection. The run does not establish whether
backup workers were paused. It is not evidence of quiet-machine timing
stability. The historical bases used macOS 26.6.2 and CPython 3.13.15/3.14.7
on the same machine, so current-versus-base timings cross host and interpreter
conditions as well as implementation changes.

Against the superseded `d125a6595` capture, taken under the same host,
interpreters, lock, and Budget Contract, no memory reading rose past its former
gate and every gate address was kept. Keyed target writes retain 152 B/row
less and opening and geometry writes 64 B/row less; read-plan compilation
retains 1.1–1.6 KiB more on the guarded controls, and typed cold-plan peaks in
the feature-boundary member rose 5–12%. These span `5b37f3099..bc9add4be` and
are not attributed to individual commits.

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
Predicate acquisition stops with the group buffered; predicate flush adds the
provider-free flush but excludes driver serialization. Positional materialization
starts after root execution and stops at a finished Page, before publication;
deferred Document leaves are therefore not decoded in that window. Read-plan
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

It proves that the measured workload inputs at the capture's producing commit
digest to HEAD's workload digest, and that the commit's own code reports HEAD's
generated-key offset and frozen manifests. It then amends the members recording
the stale digest and records the adjustment as reclassification does. It
refuses a changed Budget Contract, a prior adjustment, or any unproven input
and writes nothing.

The former previous/COR-191 comparisons can be reconstructed using Git revisions
`3535d3e0f` and `dc65ef88`. Export both `portfolio.json` and `conditions.json`
from `languages/python/docs/structural-metadata-envelope/recovered/` at the
chosen revision into the same temporary directory, then compare that portfolio
with the current one. A shallow clone may need those revisions fetched first.
The remaining working-tree files alone do not reproduce those historical views.
The complete retired measurement account remains in
[Git history](https://github.com/davidsunglee/parallax/blob/c7dd36498c31aed00647126bd9c6c99a8c9c5cc7/languages/python/docs/structural-metadata-envelope/README.md).
