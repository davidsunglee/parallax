# Write-lowering evidence - Phase 6 dual-base capture

The evidence keeps two comparisons separate so unrelated changes from `main` never enter a before/after delta.

- The primary like-for-like comparison uses the [Phase 2 before archive](before/) at original commit `1ceb331851fe06d23ba1d754450972ac532eb5ca` and the [pre-rebase Phase 5 after archive](rebaseline-2026-09-15/pre-rebase/) at original commit `d330e2e433e8a208493c24876a63ea4fbdafb47b`.
- The confound-resolution comparison uses the [clean rebased Phase 2 before archive](rebaseline-2026-09-15/rebased-before/) at `58b19229248bb34af34eb08179216ad53d8f1ebc` and the clean rebased after capture at `db56a19e3f24eba40563d3a28c751e4c30ab8b58`.
- The root [portfolio](portfolio.json), [summary](summary.md), and [write-lowering envelope](write-lowering.json) are the `db56a19e` capture, retained as historical review evidence. The repository's canonical current cost portfolio and CI input is the structural-metadata recovered capture under [`../structural-metadata-envelope/recovered/`](../structural-metadata-envelope/recovered/portfolio.json), named once by `cost_report.CANONICAL_PORTFOLIO`, with the unification's after-capture under `../structural-metadata-envelope/after/` retained unchanged as its regression baseline; that role never confers schema authority on every member. The summary and envelope classify write-lowering as `non-authoritative`, while the portfolio's snapshot-delivery member is `authoritative`. The root write-lowering envelope is also the after operand for the rebased confound-resolution check, but it is never compared with the original Phase 2 before capture.

The original Phase 2 capture records `dirty: true` because the measurement repairs and evidence files were uncommitted during capture; no COR-142 production optimization was present. The other three write-lowering captures record `dirty: false`. The two captures within each comparison have matching workload, budget-contract, and lock digests; three warmups and nine measured samples; and the same machine, CPU, operating system, RAM, and core count.

## Rebase mapping

| Original | Rebased | Subject |
|---|---|---|
| `6b1fad22` | `073e671f` | Measure write-lowering builder calls |
| `1ceb3318` | `54c01697` | Report write-lowering overhead |
| `9c29bd4c` | `e0d2f591` | Withdraw unsupported lowering shares |
| `e1a87080` | `132161aa` | Settle the write-lowering comparison |
| `fdebcabe` | `58b19229` | Correct the write-lowering policy |
| `bf7159cc` | `db4ac8f9` | Retain Value Object metadata document shapes |
| `f3a26a9b` | `0ec4cb64` | Retain entity document shapes |
| `51bc2b87` | `9c0e2fc5` | Preserve document-shape semantics |
| `dda2b5ee` | `c458f286` | Avoid canonical key-tuple allocations |
| `d330e2e4` | `bc98b057` | Retain Value Object class shapes |
| `d370553b` | `db56a19e` | Capture the pre-rebase write-lowering improvement |

## Protocol

Each supported CPython minor ran the four opening/successor and Columns/Relational Document cases in a fresh child process per case. Every child took three warmups and nine measured samples. Elapsed and transient-memory totals use separate unobserved windows. A separate `sys.monitoring` return-event pass counts the five public document-codec functions without timing them.

The report measures one production checkout at a time and adds no paired adapter, production probe or flag, monkey-patch, or permanent alternate implementation. Elapsed and transient changes are whole-lane observations under the stated conditions. They are not builder-exclusive attribution and are not a replacement threshold.

## Primary pre-rebase comparison

Each delta is `d330e2e4 Phase 5 after - 1ceb3318 Phase 2 before`; a negative value means the complete measured lowering lane used less elapsed time or transient memory.

| Runtime | Case | Elapsed before (us/row) | Elapsed after (us/row) | Elapsed delta | Transient before (bytes/row) | Transient after (bytes/row) | Transient delta |
|---|---|---:|---:|---:|---:|---:|---:|
| CPython 3.13 | opening.columns | 123.875 | 105.334 | -18.541 (-14.97%) | 11,490 | 10,451 | -1,039 (-9.04%) |
| CPython 3.13 | opening.document | 128.583 | 103.958 | -24.625 (-19.15%) | 12,450 | 10,962 | -1,488 (-11.95%) |
| CPython 3.13 | successor.columns | 144.625 | 125.500 | -19.125 (-13.22%) | 12,890 | 12,154 | -736 (-5.71%) |
| CPython 3.13 | successor.document | 162.041 | 138.791 | -23.250 (-14.35%) | 14,386 | 13,058 | -1,328 (-9.23%) |
| CPython 3.14 | opening.columns | 136.708 | 116.125 | -20.583 (-15.06%) | 11,190 | 10,934 | -256 (-2.29%) |
| CPython 3.14 | opening.document | 143.500 | 123.709 | -19.791 (-13.79%) | 11,934 | 11,422 | -512 (-4.29%) |
| CPython 3.14 | successor.columns | 164.666 | 148.250 | -16.416 (-9.97%) | 12,663 | 12,479 | -184 (-1.45%) |
| CPython 3.14 | successor.document | 180.916 | 158.166 | -22.750 (-12.57%) | 14,254 | 13,694 | -560 (-3.93%) |

## Rebased confound-resolution comparison

The rebased after capture was 9.28% to 18.06% slower than the pre-rebase after capture while every transient-memory reading, builder count, encoder control, matrix address, and protocol digest remained unchanged. That material elapsed divergence triggered the approved contingency rather than a cross-base comparison claim.

Each delta below is `db56a19e rebased after - 58b19229 rebased before`. The result confirms the optimization on the rebased base: elapsed time and transient memory decrease in every runtime/case cell, all three builder counts fall to zero, and encoder controls remain unchanged.

| Runtime | Case | Elapsed before (us/row) | Elapsed after (us/row) | Elapsed delta | Transient before (bytes/row) | Transient after (bytes/row) | Transient delta |
|---|---|---:|---:|---:|---:|---:|---:|
| CPython 3.13 | opening.columns | 127.334 | 123.875 | -3.459 (-2.72%) | 11,490 | 10,451 | -1,039 (-9.04%) |
| CPython 3.13 | opening.document | 141.125 | 118.250 | -22.875 (-16.21%) | 12,450 | 10,962 | -1,488 (-11.95%) |
| CPython 3.13 | successor.columns | 159.000 | 148.167 | -10.833 (-6.81%) | 12,890 | 12,154 | -736 (-5.71%) |
| CPython 3.13 | successor.document | 168.208 | 151.666 | -16.542 (-9.83%) | 14,386 | 13,058 | -1,328 (-9.23%) |
| CPython 3.14 | opening.columns | 142.791 | 131.208 | -11.583 (-8.11%) | 11,190 | 10,934 | -256 (-2.29%) |
| CPython 3.14 | opening.document | 151.042 | 142.750 | -8.292 (-5.49%) | 11,934 | 11,422 | -512 (-4.29%) |
| CPython 3.14 | successor.columns | 171.000 | 169.625 | -1.375 (-0.80%) | 12,663 | 12,479 | -184 (-1.45%) |
| CPython 3.14 | successor.document | 198.167 | 173.167 | -25.000 (-12.62%) | 14,254 | 13,694 | -560 (-3.93%) |

## Call-count changes

The per-row changes below are identical on CPython 3.13 and 3.14 and in both same-base comparisons. The three builder counts fall to zero in every case while the encoder controls remain unchanged, demonstrating removal of the named production calls without assigning the whole-lane elapsed or transient reductions exclusively to them.

| Case | shapeOfDeclaration | entityShape | occurrenceShape | encodeDocument | encodeMany |
|---|---:|---:|---:|---:|---:|
| opening.columns | 5 -> 0 (-5) | 1 -> 0 (-1) | 6 -> 0 (-6) | 4 -> 4 (0) | 1 -> 1 (0) |
| opening.document | 5 -> 0 (-5) | 2 -> 0 (-2) | 9 -> 0 (-9) | 5 -> 5 (0) | 1 -> 1 (0) |
| successor.columns | 5 -> 0 (-5) | 1 -> 0 (-1) | 6 -> 0 (-6) | 4 -> 4 (0) | 1 -> 1 (0) |
| successor.document | 5 -> 0 (-5) | 2 -> 0 (-2) | 9 -> 0 (-9) | 4 -> 4 (0) | 1 -> 1 (0) |

The original pre-rebase pair remains the primary evidence because it was captured before unrelated inheritance effective-set and SQL row-identity-adapter changes entered the measured window. The clean rebased pair resolves that confound and confirms the same removal on the current base. No delta in this document mixes one lineage's before capture with the other lineage's after capture.
