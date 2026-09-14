# Snapshot delivery rebaseline — 2026-09-14

The [old-contract envelope](rebaseline-2026-09-14/old-contract/portfolio.json)
and [summary](rebaseline-2026-09-14/old-contract/summary.md) preserve the clean
authoritative capture produced at `25fbae5d` and committed at `8b3270b4`.

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

The current-contract authoritative capture will replace [portfolio.json](portfolio.json)
and [summary.md](summary.md) after the implementation commit; until then those
files still contain the preserved old-contract capture.
