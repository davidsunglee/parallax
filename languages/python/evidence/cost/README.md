# Python cost evidence

The [current portfolio](current/portfolio.json) is the canonical complete capture
used by the cost verifier and the [memory gates](../../spec/memory-gates.yaml).
The [measurement retention rule](../../../../TESTING.md#measurement-retention)
owns what belongs in Git and how future runs are stored.

## Capture roles and provenance

| Capture | Role | Producing commit | Captured |
|---|---|---|---|
| [current](current/portfolio.json) | Current verification input and memory-gate basis | `51c7f63bc5d8d892e3d3079b418323381344376a` | 2026-11-04 |
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
All 24 representative live-read cells are present, covering conventional graphs
and finite historical transaction-time and bitemporal reads through Typed/Wire
and eager/page32 delivery.

The recorded commit is the fact of what was captured. Verifying an envelope
reconstructs its embedded Budget Contract and checks internal consistency
without resolving that commit; the ancestry advisory alone consults Git history.
This is an integrity check of reviewed evidence, not an attestation that the
observations cannot be forged.

Rebase and squash merges rewrite branch commits. Snapshot redigest requires an
ancestor of the inspected checkout; write-lowering redigest accepts the exact
resolvable producing commit after proving its captured sources and workload
identity. Prefer capturing at a commit already on `main`, so source history
remains available. This capture records its original reviewed branch commit.

The collector ran once on 2026-11-04, 07:16:37–08:17:38 UTC, in 61m00s wall
time, on a Mac17,4 (Apple M5, 10 cores, 32 GiB), macOS 27.0.1 build 26A434,
with CPython 3.14.10 and 3.15.2 and PostgreSQL 18.6 under OrbStack 2.2.5.
Every tracked file and every package source-root file was recorded by digest,
size, and modification time immediately before collection and was unchanged
afterwards. Native-loader sources are unchanged from the outgoing capture.
[Conditions](current/conditions.json) record interpreter identities, production
origins, and instrument source hashes; [durations](current/durations.json)
record collection telemetry. The dependency lock SHA-256 is
`452b94ef99cced1ababe01d43a2a4df79e2e7c311c48d9a37b21d6ca9ec9472e`.
The portfolio SHA-256 is
`e21f47d6676ade3267abf9edb1fc74707d10f71e050f063caeb7cb72692179fb`,
conditions SHA-256 is
`f1efb3fc587cbb9a42c430ee0c02abfcc21efc249543e5fadb1d45d9f0b58a60`,
and durations SHA-256 is
`8ce74acb5cf87d455e8405cff6230ce0e1cef878a2ef6138da866f2e214ca148`.

The machine-wide measurement lock excluded other coordinated heavy work. The
collector began on AC power at one-minute load 2.935; recorded in-run loads
were higher. A quiet start does not establish sustained quiet-host timing
stability. The outgoing October 31 capture used the same host/software with
CPython 3.13.18/3.14.8, but its quiet wait was disabled at load near 4–5.
The structural bases used macOS 26.6.2 and CPython 3.13.15/3.14.7.

## Comparison with the outgoing capture

The outgoing producer `c5b49ddd3560a706865d10d631b9de1d74324a50` has exactly the
tree of `a4378362166f5801a33429bab87b6de5ad87a8b0` on `main` after rebase.
Intervening production changes include routing/acquisition (PR #321), compiled
relationship facts (#333), locking continuation (#337), concurrency and retained
metadata (#338), and retry/lifecycle composition (#339). The earlier fused-read
work is already in the outgoing tree. Dependencies also changed: Pydantic
2.14.1→2.14.2, pydantic-core 2.50.1→2.50.2, botocore 1.43.118→1.43.123,
filelock 4.2.1→4.2.5, SQLGlot 30.24.0→30.26.0, and pip-api 0.0.34→0.0.35.
Both Snapshot sources pin the same PostgreSQL 18.6 Alpine image; an independent
reference-harness Debian preflight does not describe these Snapshot captures.
Historical comparisons do not isolate an interpreter, dependency, or code effect.

The portfolio grows from 3,119 to 3,139 readings: 1,386 matching addresses,
1,733 removed, and 1,753 added. This turnover includes dropping the old minor,
adding the new minor, moving 434 newest-only scalar cells, and adding 20 live
advisory addresses while reusing four existing conventional Wire cells.
All 372 overlapping deterministic count readings are unchanged.

All 362 memory-gate addresses remain, and no new reading exceeds its outgoing
ceiling. Under the unchanged derivation, 147 ceilings move: 69 down and 78 up.
Only four rise more than 3%: bitemporal interior Columns Typed retained bytes
(1,002→1,056; +5.39%) and transient bytes (17,164→17,724; +3.26%), its Wire
transient bytes (17,749→18,309; +3.16%), and two-row Columns Typed insert
transient bytes (5,105→5,265; +3.13%). These are shared ceilings derived across
runtimes, not isolated runtime comparisons.

Verification retains eight timing advisory rows for five unique windows:
duplicate-include page32 and firstResult.page1, document-heavy page32, and
versioned-document page32 and firstResult.page32. Seven streamed-memory scaling
advisories occur on the new authority runtime, versus three on the outgoing
authority; the current older minor has two. A larger scaling slope need not mean
a larger absolute peak: conventional page128 is 421.29/466.76 KiB at 200/2,000
roots on 3.15, versus 495.20/499.21 KiB on 3.14. No allocator cause was isolated.

All 25 matching 3.14 live elapsed cells read higher, by 7.94–128.86%
(median 62.60%). Four matching provider-free elapsed cells improve 7.65–27.87%
(median 10.48%); write and feature timing medians improve about 8%.
A bounded comparison of outgoing and current source on the same CPython 3.14.10
and 94 external dependency versions did not reproduce the two large historical
gaps it investigated. Conventional Wire eager pooled medians were 6.375→6.699 ms
(median paired-round +6.39%, range −0.47…+13.26%, five of six positive);
document-heavy Wire page32 was 27.093→27.768 ms (+3.09%, below 5%). Even outgoing
source under these controlled conditions was well above the historical 4.763 and
16.238 ms. Current source changes alone do not explain most of those two large
historical movements. The diagnostic does not isolate patch, dependency, or host
causes, or generalize to other cells; its near-threshold conventional movement
remains weak evidence of a smaller source effect.

## Paired runtime timing

Same-source pairs compare CPython 3.14.10 with 3.15.2 at the current producing
commit, with matching dependencies, native drivers, fixtures, and semantic
outcomes. Six rounds alternate runtime order. Reads and guarded writes retain
54 samples per runtime/case; W4 retains 30. Timing excludes setup and correctness
probes. These are uncontended success paths, not contention or retry-throughput
measurements. Statement observations match across runtimes: ordinary writes
use four server statements, temporal writes five, including BEGIN/COMMIT.
Derived driver synchronization counts are four and five respectively; they are
not packet-observed network round trips.

Materiality uses the median of paired-round percentage changes, which differs
from the ratio of pooled sample medians. Only conventional Wire page32 among the
12 read cases exceeds 5%: −10.48% (round range −24.24…+1.01%), with pooled
medians 12.938→12.369 ms. The other 11 cases are below the threshold; every read
case's round range crosses zero. Guarded write improvements exceed 5% for
ordinary one-row (−8.63%), transaction-time one-row (−5.58%), and bitemporal
32-row (−5.06%) cases. Their pooled transaction medians are respectively
5.545→5.322, 6.540→6.199, and 16.284→15.616 ms; all six write cases have
sign-changing round ranges, and the latter two classifications are near the
boundary. The other three guarded writes and all three W4 variants remain
below 5%. These observations support only the measured workloads and do not
establish a general runtime speedup.

Accepted suites all satisfy the original load ceiling of 3.0. Writes used the
original scheduling; W4 added 60 seconds idle before each batch; reads also
waited for admission below 2.25 before setup. Reviewed scheduling changes leave
measured windows, sampling, semantic checks, and rejection thresholds unchanged.
Whole attempts that exceeded host limits remain archived and excluded from
accepted timing; no selected batches were substituted.

## Retained archives

Raw evidence, generated comparisons, all accepted and rejected attempts, exact
invocations, script revisions, and audit results live outside Git at
`~/.local/share/parallax/evidence/cor-258/`. Its accepted-evidence index is
`runs/final-acceptance.json`, SHA-256
`8317377a49c9158ca2e40a57d197d487b55cecd292c1c435a2b87dca4d3e266e`.
The canonical `runs/canonical/SHA256SUMS` digest is
`246c94289d987e0e67593552c2708d31bf79ccfcc11bfd4173ad6f4444419572`;
`outgoing-current/SHA256SUMS` is
`65312a3e01b51dfad473bb375ec0e7877df741639e4dcece2099e4f280861d25`.
The index identifies accepted `paired/final-02/writes.json`,
`paired/final-w4-02/w4.json`, and `paired/final-reads-03/reads.json` with their
individual hashes and script commits. The bounded source diagnostic is in
`diagnosis/`, with raw `timing-01/result.json` SHA-256
`50c0e31b00691e51af03dd9746df58c9f3ad01a76e1954091ca1f3afed27fd64`.

The superseded October 31 capture found lower provider-free/control timings,
mixed live timings with slower first results, and slower read-plan compilation,
write, feature, and lifecycle windows. Higher background load prevented causal
attribution. All 362 gate addresses stayed within their former ceilings;
105 derived ceilings fell and 49 rose, with localized read-plan/prepared-model
and keyed-write increases and scalar/nested peak reductions. Its three scaling
advisories and mechanical scalar/root-count renames remain documented in the
archived account. That capture, its predecessor, and comparisons remain at
`~/.local/share/parallax/evidence/cor-259/runs/phase7-final-cost/`, whose
`SHA256SUMS` digest is
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
pairs on the captured primary runtime (3.15.2 in this capture). Its p95 differences include scheduler and collection differences
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

## Deferred-plan gate warmups

A diagnostic on 2026-11-04 measured the
`cross-object.bitemporal.deferred-32x32.columns.typed` gate with 200, 100, 50 and
20 retained-memory warmups. On the same Mac17,4 host, under the machine-wide
measurement lock, the retained stage took 74.72s of the 76.45s Python 3.15.2
baseline. All six byte readings were identical at each screened count. The
200-warmup baseline took 72.08s on Python 3.14.10; three fresh-child baseline
readings at 20 warmups had medians of about 9.5s and 9.1s respectively.

Across 19 fresh-child measurements, including three baseline/seed pairs per
runtime at 20 warmups, normal plan retention was 25,288 bytes. A seeded duplicate
registry of real settled-plan entries raised it to 34,254–34,304 bytes and failed
both plan-retention ceilings at 20 and 200 warmups. Within each runtime, repeated peak readings varied
by about 50 bytes. The gate therefore uses 20 retained warmups
only for this workload, preserving its geometry, work assertions, all ceilings,
three peak samples and both retained sampler runs. The benchmark reader and CLI
still default to 200. These local timings do not predict CI execution time or
establish convergence for other workloads.

Raw diagnostic scripts, source digests and readings are retained outside Git at
`~/.local/share/parallax/evidence/ci-follow-up/warmup-proof-20261104.tar.gz`,
SHA-256 `87b473c3bc445a6c570056a7e44a8bde64f102c4358d656cea9cbc54b363ee51`.
The accepted capture envelopes and workload inputs remain unchanged. The explicit
warmup option changes recorded instrument source hashes; strict compatibility
checks still reject comparisons between old and new instrument sources, even
when both captures use the unchanged default protocol.
