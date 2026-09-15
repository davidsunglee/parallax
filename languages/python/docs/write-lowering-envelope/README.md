# Write-lowering evidence — Phase 6 pre-rebase capture

The [before archive](before/) preserves the Phase 2 capture verbatim. Its write-lowering provenance names production commit `1ceb331851fe06d23ba1d754450972ac532eb5ca` and records `dirty: true` because the measurement repairs and evidence files were uncommitted during capture; no production runtime code differed from the Phase 1 tree.

The [pre-rebase after archive](rebaseline-2026-09-15/pre-rebase/) was produced by the same permanent single-implementation report from clean Phase 5 commit `d330e2e433e8a208493c24876a63ea4fbdafb47b`. Its write-lowering provenance records `dirty: false`, and the envelope is complete on CPython 3.13 and 3.14 with 56 readings, no incomplete cells, and no errors.

Only the Phase 2 before archive and the `d330e2e4` pre-rebase after archive are comparison operands. The root [portfolio](portfolio.json), [summary](summary.md), and [write-lowering envelope](write-lowering.json) still contain the Phase 2 capture at this milestone; after the branch is rebased, a second clean capture will replace them as authoritative current evidence and CI input. That future rebased capture will not be used to calculate the before/after elapsed or transient deltas.

## Protocol

Each supported CPython minor ran the four opening/successor and Columns/Relational Document cases in a fresh child process per case. Every child took three warmups and nine measured samples. Elapsed and transient-memory totals use separate unobserved windows. A separate `sys.monitoring` return-event pass counts the five public document-codec functions without timing them.

The comparison operands have the same workload digest, budget-contract digest, lock digest, machine, CPU, operating system, RAM, core count, and sampling counts. The report measures one production checkout at a time and adds no paired adapter, production probe or flag, monkey-patch, or permanent alternate implementation.

## Whole-lane deltas

Each delta is `pre-rebase after - Phase 2 before`; a negative value means the complete measured lowering lane used less elapsed time or transient memory. These are like-for-like whole-lane observations under the stated conditions. They are not builder-exclusive attribution and are not a replacement threshold.

| Runtime | Case | Elapsed before (µs/row) | Elapsed after (µs/row) | Elapsed delta | Transient before (bytes/row) | Transient after (bytes/row) | Transient delta |
|---|---|---:|---:|---:|---:|---:|---:|
| CPython 3.13 | opening.columns | 123.875 | 105.334 | -18.541 (-14.97%) | 11,490 | 10,451 | -1,039 (-9.04%) |
| CPython 3.13 | opening.document | 128.583 | 103.958 | -24.625 (-19.15%) | 12,450 | 10,962 | -1,488 (-11.95%) |
| CPython 3.13 | successor.columns | 144.625 | 125.500 | -19.125 (-13.22%) | 12,890 | 12,154 | -736 (-5.71%) |
| CPython 3.13 | successor.document | 162.041 | 138.791 | -23.250 (-14.35%) | 14,386 | 13,058 | -1,328 (-9.23%) |
| CPython 3.14 | opening.columns | 136.708 | 116.125 | -20.583 (-15.06%) | 11,190 | 10,934 | -256 (-2.29%) |
| CPython 3.14 | opening.document | 143.500 | 123.709 | -19.791 (-13.79%) | 11,934 | 11,422 | -512 (-4.29%) |
| CPython 3.14 | successor.columns | 164.666 | 148.250 | -16.416 (-9.97%) | 12,663 | 12,479 | -184 (-1.45%) |
| CPython 3.14 | successor.document | 180.916 | 158.166 | -22.750 (-12.57%) | 14,254 | 13,694 | -560 (-3.93%) |

## Call-count changes

The per-row counts are identical on CPython 3.13 and 3.14. The three builder counts fall to zero in every case while the encoder controls remain unchanged, demonstrating removal of the named production calls without claiming that the whole-lane elapsed or transient changes belong exclusively to them.

| Case | shapeOfDeclaration | entityShape | occurrenceShape | encodeDocument | encodeMany |
|---|---:|---:|---:|---:|---:|
| opening.columns | 5 → 0 (-5) | 1 → 0 (-1) | 6 → 0 (-6) | 4 → 4 (0) | 1 → 1 (0) |
| opening.document | 5 → 0 (-5) | 2 → 0 (-2) | 9 → 0 (-9) | 5 → 5 (0) | 1 → 1 (0) |
| successor.columns | 5 → 0 (-5) | 1 → 0 (-1) | 6 → 0 (-6) | 4 → 4 (0) | 1 → 1 (0) |
| successor.document | 5 → 0 (-5) | 2 → 0 (-2) | 9 → 0 (-9) | 4 → 4 (0) | 1 → 1 (0) |

## Remaining Phase 6 work

The pre-rebase evidence still needs its own commit before any history rewrite. Rebase onto current `main`, the clean authoritative rebased capture, the original-to-rebased commit mapping, the final Phase 6 review, and the owner's tradeoff decision remain open. Current `main` changed inheritance effective sets and SQL row identity adapters inside the measured window, so the authoritative rebased capture is not a comparison operand unless material divergence first triggers the outline's exceptional rebased-before recapture.
