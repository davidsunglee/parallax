# Python cost evidence

The [current portfolio](current/portfolio.json) is the canonical complete capture
used by the cost verifier and the [memory gates](../../spec/memory-gates.yaml).
The [measurement retention rule](../../../../TESTING.md#measurement-retention)
owns what belongs in Git and how future runs are stored.

## Capture roles and provenance

| Capture | Role | Producing commit | Captured |
|---|---|---|---|
| [current](current/portfolio.json) | Current verification input and memory-gate basis | `51243462ff1ec7ce3429677eb51b12dd12247f45` | 2026-11-13 |
| [structural-metadata-before](structural-metadata-before/portfolio.json) | Fixed recovery reference | `b7abe2d055fd3e0974829616f2de99b94ad5af97` | 2026-09-16 |
| [structural-metadata-after](structural-metadata-after/portfolio.json) | Fixed regression comparison base | `1636e9f0ce072dce25ddd1ebeabd0b1368b65031` | 2026-09-17 |

The current portfolio is one clean collection with no replacement adjustment:
five exact member matrices and 3,263 readings, with no collector failures,
member errors, or incomplete cells. It supersedes the November 11 capture
because required database bindings changed the measured setup of the Snapshot
delivery and write-lowering workloads, which a digest restatement cannot
cover. [Conditions](current/conditions.json) record runtime identities and
source hashes. Snapshot delivery is authoritative under its embedded Budget
Contract; the other members have their own protocols and are non-authoritative.

The collection ran from 14:10:28 to 14:55:44 EST on November 13 (45m16s), on
AC power. The host was a Mac17,4 (Apple M5, 10 cores, 32 GiB), macOS 27.0.1,
with CPython 3.14.10 and 3.15.2 and PostgreSQL 18.6 for Snapshot delivery;
lifecycle overhead ran on 3.15.2 alone. Child checkpoints and complete-member
envelopes were saved atomically during collection;
[durations](current/durations.json) retain collection telemetry. Verification
reports four `repeated-fanout` publication timing advisories and seven
streamed-memory scaling advisories.

Snapshot delivery and write lowering changed workload, dependency-lock, and
instrument inputs since the outgoing capture, so
`--compare --require-compatible` refuses the pair; the movement below comes from a plain
`--compare` and does not isolate a code effect. The unchanged 1.10-headroom
derivation keeps all 410 memory-gate addresses: 165 ceilings rise, 49 fall,
and 196 are unchanged. No fresh reading exceeds its outgoing ceiling. The
largest rises are Snapshot read-plan peaks, `plan-*` `document.peakKiB`
+3.4% and `columns.peakKiB` +3.3%, then write-lowering
`model.prepared.family` retained bytes +2.2% and `model.prepared` +1.5%. The
largest falls are transaction-time Columns target writes, whose per-row
transient ceilings drop 15.1–15.6%.

The raw collection, checkpoints, collector and verification logs, outgoing
capture, comparisons, and gate-derivation scripts are outside Git at
`~/.local/share/parallax/evidence/cor-282/capture-20261113/`, with 1,977 files
verified by `SHA256SUMS` (manifest SHA-256
`9dc178ab89ecbc98ec382e10251ab586ec136f54a53008e1285bd80413f2485f`).
The current portfolio SHA-256 is
`d13bb9b64133fb98fe1c6eb7e60c8f2553010aa5afa9d01af217a0d3d2f589b4`,
conditions SHA-256 is
`1dabd4149e8db5f80f0072fc39c78f534f344c6b132c12c623e3ae7e591f0f7d`,
and durations SHA-256 is
`67306f3c5b3c3d3816561c86a8a8dc01a105db27fbc4f87f2d78db7fa5989cd9`.

The following comparison and page-sharing sections describe the November 7
capture. Their historical observations remain tied to its retained archive.

## November 7 comparison with its outgoing capture

The outgoing producer `51c7f63bc5d8d892e3d3079b418323381344376a` is an ancestor
of the fork point `77ea1ada6e33099a4e511d9cac2f545b76057b35`. Intervening
production changes are the family-variant and `_type` naming of Wire nodes, the
retirement of public row delivery and managed lifecycle, and the page-sharing
option itself, whose default mode keeps its per-root path. The dependency lock,
interpreters, host, and PostgreSQL image are unchanged. Instrument sources
changed with the page-sharing cells, so `--compare --require-compatible` refuses
the pair, and the arithmetic below comes from a plain `--compare`. It does not
isolate a code effect from host or day-to-day variation.

The portfolio grows from 3,139 to 3,263 readings: every outgoing address is
read again, and the 124 added readings are the page-sharing cells. Every
overlapping count reading is unchanged.

All 362 outgoing memory-gate addresses remain, and no new reading exceeds its
outgoing ceiling. Under the unchanged derivation, 88 of them move: 81 down and
seven up. The largest rise is write-lowering's family model preparation,
retained 30,895→32,504 B (+5.2%) and transient 35,867→37,406 B (+4.3%), then the
whole model preparation by about 2%; the other three rise by under 0.2%. The 48
added gates price the page-sharing memory readings.

Every provider-free, control, plan, positional, and held-metadata byte reading
of Snapshot delivery is within noise or smaller; the five larger readings are
ungated live-window heap. Snapshot timing movements run both ways: 59 live
timing cells read faster and nine slower, and provider-free and control
elapsed cells split 5 faster and 18 slower beside 107 within noise, none above
30%. Verification now reports one timing advisory, duplicate-include
`firstResult.page1`, against eight before, and the same seven streamed-memory
scaling advisories on the authority runtime. The previous comparison account,
including its bounded source diagnostic of two historical live movements,
remains in [Git history](https://github.com/davidsunglee/parallax/blob/42bbf65896c6079fb2da0088d9b93b05af7b0c3e/languages/python/evidence/cost/README.md).

## Page-sharing delivery evidence

These conclusions come from the capture and from one-off measurements of the
same producing commit; raw output is archived as listed under *Retained
archives*.

The ticket's reductions hold on both runtimes. On `repeated-fanout`, page scope
against root scope lowers Typed retained heap 87.8% on 3.15 and 86.0% on 3.14
(target 50%) and its elapsed time 81.7% and 82.0% (target 20%); Wire retained
heap falls 79.7% and 78.0% (target 30%) and elapsed time 78.1% and 77.9%
(target 10%). Unique nodes read 11,000 and 1,100 Typed and 12,000 and 2,100
Wire, so each cell measured its scope. On `invalid-roots`, page scope costs less
than root scope in every eager retained and peak reading while every tenth root
keeps its own diagnostic graph. Page-scope eager peak also falls, but a
page-scope Wire stream peaks higher than a root-scope one, about 330 against
200 KiB at page 128, because a shared page holds its rows and graph until the
page ends.

The page-mode bound is flat: every `x10` reading of the `page128` block sits
within 1.10 of its base reading or within 512 B of it, on both workloads, for
Typed, Wire, and Typed-to-Wire projection, and every early-close reading is
zero. Holding every delivered Page in a module-level list, a regression these
gates exist to catch, took all 30 `x10` readings past their derived gates on
both runtimes, by roughly 10 MiB each.

Stream retention at page 128 from 1,000 to 20,000 roots stays flat at both
scopes: peak heap rises by at most 22 KiB over that range, the last root
retains the same 3–4 KiB and reaches the same 11 or 12 nodes at both scopes,
and an early close retains nothing. Across a whole stream, page scope publishes
about a ninth of root scope's Typed nodes.

Before/after controls measured the fork point and the producing commit with each
one's own tool, one pair each on the same host. Every provider-free control
memory reading is within noise, and all but three of 68 control timings are,
none beyond 9%. Provider-free conventional fan-out timing is within noise. Live
timings of the same pairs move in opposite directions on the two runtimes, so
one pair cannot separate them from host variation.

A live R3 comparison with SQLAlchemy 2.1.6 `selectinload` passed the
harness's verification first: equal checksums and SQL-oracle counts, equal
final state after every write scenario, and equal conflict outcomes. Over two
timing passes, Parallax read R3 in 64–65 ms at root scope and 21–22 ms at page
scope, against SQLAlchemy's 17–19 ms, a ratio of 3.6–3.8 falling to 1.16–1.18.
Page scope holds 0.78 MiB against 3.04 MiB at root scope and SQLAlchemy's
2.05 MiB, with a 1.85 MiB peak against 3.87 and 2.57 MiB. Page scope publishes
SQLAlchemy's 1,100 objects; root scope publishes 11,000. The R1 and R2 controls
stayed within 0.91–1.06 of SQLAlchemy. These describe this host and seed only.

## Paired runtime timing

Same-source pairs compare CPython 3.14.10 with 3.15.2 at
`51c7f63bc5d8d892e3d3079b418323381344376a`, the previous capture's producing
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

The November 7 capture's raw collector output, input manifests, host records, grading
output, the bound break, the before/after control pairs, the stream retention
readings, the live R3 harness with its history and runs, and the scripts that
produced them live outside Git at
`~/.local/share/parallax/evidence/cor-260/phase7/`, whose `SHA256SUMS` digest is
`e31d9900ceb7068b5860656f3791e29c6f41d8168ace9dcada709f7eb78ba322`.

The previous capture's raw evidence, generated comparisons, all accepted and
rejected attempts, exact invocations, script revisions, and audit results live
outside Git at `~/.local/share/parallax/evidence/cor-258/`. Its accepted-evidence index is
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

The superseded November 11 capture combined three members from
`51a70974bf32238b284e34562ff807601c83c0f3` with Snapshot delivery and write
lowering replaced at `2505775c5652fc03e5e832bc436dd347c6155d17`. Its 410 derived
ceilings rose in 58 places and fell in 120 against its predecessor, led by
write-lowering `model.prepared.family` (+8.7–8.9%), with every reading below
its previous ceiling. Its raw collection, checkpoints, and collector log live
outside Git at `~/.local/share/parallax/evidence/cor-288/recovery-20261111/`,
whose `SHA256SUMS` digest is
`53af45b5398ccd985f6d8ec69f51a23dbb8c650e3152e619e4e0fd679efd6aec`; the failed
first collection remains at `cor-288/failed-20261111/`.

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
pairs on the captured primary runtime (3.15.2 in the November 7 capture). Its p95 differences include scheduler and collection differences
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

The command selects each stale digest family independently: the shared one the
Snapshot, lifecycle, and instance-state members record, write lowering's, and
feature boundaries'. One rule proves every family. The producing commit's own
digest code, run in a checkout of that commit through its frozen environment,
must reproduce the recorded digest, and HEAD's digest code must give the
producing commit's measured inputs exactly HEAD's digest. No older digest
definition is remembered at HEAD. Snapshot also requires its producing commit
to be an ancestor of HEAD, or to have exactly the tree of one of HEAD's nearest
ancestors within the tool's bounded search, which the adjustment names. The
commit's own code must report HEAD's generated-key offset, frozen manifests, and
generated dataset rows. Write lowering and feature boundaries check each
captured workload source hash against the exact producing commit of a clean
tree, and write lowering uses that commit's frozen structural and scalar-type
manifests.

Workload source enters each digest as executable syntax. Comments, formatting,
standalone documentation strings, import statements, and only the workload's
own digest declaration are ignored; assigned literals, names, export strings,
and operational expressions remain part of the identity. Prose edits and moved
imports therefore need no amendment.

All required proofs finish before writing. The command amends only stale
workload digest fields and records their old and new values in conditions;
readings, samples, comparisons, durations, producing provenance, and captured
instrument hashes remain unchanged. It refuses a changed Budget Contract, a
prior adjustment, missing producing history or source proof, proof output of
the wrong shape, or a meaningful workload or frozen-input change and writes
nothing. Use a new capture for a
changed measured workload. Do not amend the fixed historical bases.

When a capture fails to produce required members, replace all failed subjects
in one run while retaining every complete member envelope:

```sh
uv run --project languages/python python languages/python/tools/cost_report.py \
  --replace-member snapshot-delivery --replace-member write-lowering \
  --from /tmp/parallax-cost-run --out /tmp/parallax-cost-run-completed
```

Each selected member must be absent with one recorded collection failure; no
complete member can be replaced. The clean checkout must descend from the kept
members' producing commit. Before measurement, the collector proves their
instrument, workload, production, dependency-lock, and Budget Contract inputs
unchanged. It permits changes only to the collector and selected members' own
instruments. The default full, shard, and replacement paths prepare fresh owned
runtime environments and import the actual workloads on both supported runtimes
before measuring any member. They save atomic child checkpoints and completed
member envelopes under `<out>/checkpoints`; a rerun with the same output reuses
valid saved work. A shard workflow places these checkpoints inside its uploaded
reports directory.

Replacement writes a new directory, preserving the input capture. Kept member
envelopes remain byte-identical. The conditions adjustment records every
replacement, the original and replacement commits, failed subjects, and
collection intervals. Verification accepts differing producer commits only as
that adjustment assigns them. An already adjusted input cannot be replaced.

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
