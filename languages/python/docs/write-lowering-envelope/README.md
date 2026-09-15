# Write-lowering baseline — 2026-09-14

The baseline portfolio was produced from the Phase 1 production tree at
`6b1fad2229e262c5d6c12695737b20cc576a4d63`. The Phase 2 report tooling and
evidence files were present but uncommitted during capture, so provenance
correctly records `dirty: true`; no production runtime code differs from that
commit.

Each supported CPython minor ran the four opening/successor and
Columns/Relational Document cases in a fresh child process per case. Every child
took three warmups and nine measured samples. Timings and transient-memory
windows were separate. The observer counted the five public document-codec
builders in situ and attributed inclusive outermost elapsed and current-size
deltas without retaining per-call or per-row state.

The committed [portfolio](portfolio.json), [summary](summary.md), and
[write-lowering envelope](write-lowering.json) retain the full capture. Builder
shares are evidence only; the envelope declares no comparison and no timing or
memory value controls its exit status.

| Runtime | Case | Elapsed share | Transient share |
|---|---|---:|---:|
| CPython 3.13 | opening.columns | 19.82% | 25.48% |
| CPython 3.13 | opening.document | 25.68% | 31.04% |
| CPython 3.13 | successor.columns | 16.86% | 21.72% |
| CPython 3.13 | successor.document | 18.00% | 26.36% |
| CPython 3.13 | all cases, row-weighted | 19.92% | 26.13% |
| CPython 3.14 | opening.columns | 17.10% | 15.23% |
| CPython 3.14 | opening.document | 21.86% | 19.37% |
| CPython 3.14 | successor.columns | 14.41% | 12.57% |
| CPython 3.14 | successor.document | 16.01% | 15.21% |
| CPython 3.14 | all cases, row-weighted | 17.22% | 15.54% |

The decision rule proceeds when either row-weighted share is at least 10% on any
supported minor. Both shares exceed 10% on both minors, so the evidence selects
the optimization phases.
