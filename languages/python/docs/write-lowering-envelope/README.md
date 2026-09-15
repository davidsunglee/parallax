# Write-lowering baseline — 2026-09-15

The baseline portfolio was recaptured during Phase 2 round 1 remediation from
the production tree at `1ceb331851fe06d23ba1d754450972ac532eb5ca`. The
measurement repairs and evidence files were uncommitted during capture, so
provenance records `dirty: true`; no production runtime code differs from the
Phase 1 tree.

Each supported CPython minor ran the four opening/successor and
Columns/Relational Document cases in a fresh child process per case. Every child
took three warmups and nine measured samples. Elapsed and transient-memory totals
use separate unobserved windows. A separate `sys.monitoring` return-event pass
counts the five public document-codec functions without timing them.

The committed [portfolio](portfolio.json), [summary](summary.md), and
[write-lowering envelope](write-lowering.json) retain the full 56-reading
capture. The portfolio preserves its other dated members and replaces only the
write-lowering member. The envelope declares no comparison, and no timing,
memory, or call count controls its exit status.

| Case | shapeOfDeclaration | entityShape | occurrenceShape | encodeDocument | encodeMany |
|---|---:|---:|---:|---:|---:|
| opening.columns | 5 | 1 | 6 | 4 | 1 |
| opening.document | 5 | 2 | 9 | 5 | 1 |
| successor.columns | 5 | 1 | 6 | 4 | 1 |
| successor.document | 5 | 2 | 9 | 4 | 1 |

The former elapsed and transient attribution shares are withdrawn. The elapsed
intervals included monitoring overhead, the accumulator also included the two
encoders, and summed return-time current-size deltas were not comparable with a
whole-window peak. The report now retains only supported totals and counts.

The owner withdrew COR-142's unsupported pre-optimization 10% attribution gate
rather than replacing it. This capture's totals and counts are the before
evidence for Phases 3-5. Phase 6 runs the same permanent report once against the
clean production checkout after those changes and compares the captures;
elapsed and transient differences are whole-lane deltas, not builder-exclusive
attribution. The measurement adds no paired adapter, production probe or flag,
monkey-patch, or permanent alternate implementation.
