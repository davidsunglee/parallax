# Snapshot delivery rebaseline — 2026-09-14

The [old-contract envelope](rebaseline-2026-09-14/old-contract/portfolio.json)
and [summary](rebaseline-2026-09-14/old-contract/summary.md) preserve the clean
authoritative capture produced at `25fbae5d` and committed at `8b3270b4`.
It was captured before the branch was rebased onto `main` at `88a14fc8`.
The archive retains its original provenance bytes. Corresponding rebased commits
are:

| Original | Rebased | Subject |
|---|---|---|
| `25fbae5d` | `484b89b6` | `fix(snapshot): close delivery cost review findings` |
| `8b3270b4` | `16161477` | `docs(snapshot): recapture delivery cost evidence` |

The preceding current-contract capture was produced at original `47bdda1b`,
whose rebased counterpart is `1a98004e` —
`fix(snapshot): clarify delivery memory sampling`.

The reviewed protocol collects unreachable objects at page boundaries while
retaining the whole-drain peak and only the last root. The ceilings price
Parallax-owned page state and driver-owned Python state; the previous growth
tracked CPython cycle-collector scheduling over per-statement garbage.
The Python workload catalog also offsets generated keys beyond the small-int
cache so both scaling arms price fresh result integers. Both changes participate
in the recorded input digests.

Only `duplicate-include.streamedMemory.page128PeakKiB` is relaxed in the
[Budget Contract](../../spec/budget-contract.yaml). Draining publishes a page
while it is alive, a cost the former first-root protocol omitted. Boundary
collection measured 1110.8 KiB and 1163.8 KiB in the two arms; the reviewed
ceiling provides about 3% headroom above the larger arm. Every other ceiling and
the arm-growth rule are unchanged.

The schema-authoritative Snapshot delivery evidence that closed this contract is
retained in [portfolio.json](portfolio.json) and [summary.md](summary.md),
captured once from clean rebased commit
`5fb9a934f1fb1aedc5b43334d2dc092fff74116b`.
Its lock digest matches the capture checkout's `languages/python/uv.lock`.
It records 89 comparisons within and one outside, with no incomplete cells or
errors. Nineteen of 20 streamed-memory arm-growth comparisons pass over 40 arms;
every arm meets its absolute ceiling.

The repository's canonical current cost portfolio and CI input is the
structural-metadata recovered capture under
[`../structural-metadata-envelope/recovered/`](../structural-metadata-envelope/recovered/portfolio.json),
named once by `cost_report.CANONICAL_PORTFOLIO`; the unification's
after-capture under `../structural-metadata-envelope/after/` is retained
unchanged as its regression baseline. The later
[`db56a19e` portfolio](../write-lowering-envelope/portfolio.json), which retains
a schema-authoritative Snapshot delivery member and adds a write-lowering
member, is likewise retained as historical review evidence.

The outside comparison is `document-heavy.live.eager.minRootsPerSecond`:
9007.065178422185 roots/s against 9091 roots/s. The document-heavy page-128
memory medians are 1199.525390625 and 1237.318359375 KiB, giving 37.79296875 KiB
growth against 16 KiB. The previous duplicate-include provider-free eager timing
miss now reads 14.175832970067859 ms and is within its ceiling.
The archived capture above remains the evidence for the old contract.

## Capture protocol

Run a canonical capture from a clean checkout whose committed
[Budget Contract](../../spec/budget-contract.yaml) authority matches the host
and interpreter. From `languages/python`, use
`uv run python tools/cost_report.py --out /path/to/capture`.
The collector checks known authority facts before starting a member, then checks
PostgreSQL immediately after provisioning and before measuring a workload.
A refusal identifies the mismatch: update the contract's authority first, or use
`--diagnostic` for readings that are not canonical evidence.

For a retained portfolio needing an authority-only contract update, use
`uv run python tools/cost_report.py --reclassify /path/to/capture/portfolio.json`.
Reclassification requires the same authority CPython minor, unchanged readings
and comparisons, and no previous adjustment. It updates the embedded contracts,
recomputes authority, regenerates the summary, and records the adjustment in
`conditions.json`; verification and comparison disclose that adjustment.
This contract-only remedy does not require another capture.

### Live timing and interpreter patches

On 2026-10-07, one sequential diagnostic pair used uv-managed CPython 3.14.7 and
3.14.8 on the same clean tree, `c4a0533f2`, with identical frozen dependencies,
psycopg 3.3.6/libpq 18.6, and the pinned PostgreSQL 18.6 image. Each interpreter
completed 40 live and first-result cells over the five live workloads, using the
contract's 200-root arm, three warmups, and nine measured samples.

The table shows the range of changes in median full-delivery milliseconds from
3.14.7 to 3.14.8 across eager, page-32, and page-128 delivery; positive means
slower.

| Workload | Change in median full-delivery time |
|---|---|
| conventional-fanout | −8.2% to +0.7% |
| duplicate-include | −7.9% to +5.3% |
| document-heavy | −2.5% to +4.3% |
| versioned-document | +0.5% to +6.5% |
| bitemporal-current | +10.6% to +28.8% |

Across the 15 full-delivery cells, the median change was +0.7%. First-result
cells ranged from −27.3% to +14.6%. This pair does not establish a general
interpreter-patch effect or explain the earlier 15–89% live slowdown. The runs
were sequential and the workstation had background application activity, so
host state remains a confounder. Live comparisons need matched host conditions
and a quiet measurement window. The recovered capture's exclusion as a live
timing baseline remains in force; this diagnostic pair does not replace it.
