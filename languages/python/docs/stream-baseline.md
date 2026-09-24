# Streamed-delivery working set — recorded baseline

What a running streamed read holds, measured on one machine under stated
conditions, against what the same delivery would cost a caller that kept every
root. `m-snapshot-read` *What a delivery costs* bounds the Parallax-owned working
set at `O(P_B + G_max)` and names three exclusions; this is the reading that puts
a scale on both halves.

Nothing here gates. This is dated evidence for the Snapshot member of `just
python-report-cost`; current authority and every active ceiling live only in
`spec/budget-contract.yaml`. The report displays outcomes but never turns an
outside-budget observation into its exit status.

The *shape* of the bound is gated instead, in
`tests/unit/snapshot/test_snapshot_stream_retention.py`, which the `cost` class owns and CI
runs on every change through `just python-check-cost`. That suite states the bound
as seven separate readings. Pages do not accumulate: what a delivery retains
at ten times the roots, at a later position of the same delivery, and once
drained, differs from the baseline by less than one retained root costs. One
Page, its `PageRows`, one transient `RootView`, and one published root are alive
at a time, counted by kind at every point of a crossed grid of page sizes and
fan-outs, and the published root carries exactly its own fan-out of children.
The Continuation Order's own width is priced on a grid of its own: the
coordinate the database evaluated for each root of the page is what a delivery
advances on, one object per root position rather than per node — a child has no
coordinate — holding its carriers in one tuple rather than wrapping each cell,
so the page's own cost is `O(B x T)` in the Continuation Order rather than in the
published root below it, while the width itself costs the plan once and the
delivery retains three fixed coordinates whatever the page size or the width.
**There is no term in the total result size and no term in how far the delivery
has got**,
and both absences are read directly as well as by omission — exactly, over
every Parallax-owned survivor, over every survivor whatever defined its type, and
over the references those survivors hold — so a delivery banking one thing per
PAGE fails them whether what grows is objects or references, however small each
one is against the price of a retained root.

Publishing one root peaks at that root's own reachable node closure: the high-water of the region
between two roots is exactly the same at ten times the result, at a later
position, and across a thirty-two-fold spread of page sizes, and what it costs per
node falls at each of eight fan-outs — which rejects a term super-linear in
`G_max` across that grid rather than establishing the asymptote. Page-size
equality is exact rather than
a tolerance, because `m-snapshot-read` gives the page to the first layer alone;
that is what prices Root View judgment the census cannot isolate. A high-water reading
is a maximum, so an allocation that never takes the process above an earlier
moment of the same publication is invisible to it however it scales — which is why
that grid is thirty-two-fold rather than convenient, and why Root View judgment and
the publication it feeds are priced as a pair rather than apart.

Two of the bound's three exclusions are demonstrated rather than asserted: a
caller retaining every root reproduces growth proportional to the result, and a
participating loop's buffered writes cost the same per write at every page size,
so the buffer is the dial's own multiple. The third — what the database and its
driver hold — has no executable witness in that suite, for the same reason it has
none here and under the same heading below.

## The reading

The `survivors` and `inbound` columns are this capture's survivor sample and the
references the heap held into it; the current report takes neither.

```text
  Python    CPython 3.14.7
  Platform  darwin/arm64
  Warm-up   200 unsampled runs before every window
  Shape     384 roots, fan-out 5, one include level,
            sampled inside the third page with the delivery still running

typed delivery
  page    at     held B   at 10x N    delta   roots  survivors  inbound   us/root
     1     2     29,915     29,915       +0    0.00        239      290    1426.6
    32    69    133,798    133,798       +0    0.00        704      941     538.2
   128   261    510,438    513,158   +2,720    0.63      2,134    2,942     532.6

  one caller-retained root = 4,297 B

wire delivery
  page    at     held B   at 10x N    delta   roots  survivors  inbound   us/root
     1     2     29,226     29,226       +0    0.00        220      269    1376.6
    32    69    133,109    133,109       +0    0.00        685      920     500.7
   128   261    509,749    512,469   +2,720    0.81      2,115    2,921     495.2

  one caller-retained root = 3,345 B

caller-retention exclusion (the growth the bound declines to prevent)
  typed     4,297 B/root over 20 -> 200 roots  = 839 KiB at 200 roots
  wire      3,345 B/root over 20 -> 200 roots  = 653 KiB at 200 roots
```

**The `delta` column is the headline.** It is what ten times the roots moved the
working set by, holding the page size and sampled position fixed. It is zero at
pages 1 and 32; at page 128 it is 2,720 bytes in both lanes, less than one
retained root (0.63 Typed roots and 0.81 Wire roots). The report records that
machine-relative level without turning it into a threshold. The gated suite is
what requires every result-size and delivery-position comparison to differ by
less than one retained root, with no term for either dial in its survivor model.

**The page size is the whole cost.** The working set's dominant rate is about
3,784 bytes per root position of the page at fan-out 5, in both lanes, because a
sealed Page holds every projection for that page's roots and their children. The
page decision also captures one evaluated coordinate per root, then releases all
but the continuation boundary before graph assembly. A caller who wants a smaller
working set asks for a smaller page and pays for it in round trips, which the
`us/root` column prices in the other direction: at page size 1 a delivery costs
one round trip per root and reads more than twice as slowly per root as at page
size 32.

**The exclusion is why the delta means anything.** Keeping every root of the same
200-root result costs 839 KiB in the Typed lane, while multiplying the delivered
result by ten moved the sampled working set by less than one retained root. At
page size 32 that working set is worth roughly 31 retained roots. A caller that
appends every root to a list has opted out of the bound; that is its price.

**Typed and Wire differ by a constant, not by a rate.** The Typed lane holds
exactly 689 bytes more at every page size — the same figure at 1, 32, and 128 —
because the Page is the same read either way and only the published root
differs. Retention is a property of the read rather than of the representation.
What differs materially is the exclusion's slope: a retained Wire tree is about a
fifth cheaper than a caller-retained Typed node closure, and a caller keeping the whole
result pays that difference per root.

## What this reading does not prove

Stated so the numbers above are taken for what they are. None of these is a known
defect; each is a shape the report cannot see.

**Anything a real driver holds.** The port answers each page from a counter and
keeps only the page it last answered. A driver's own cursor, connection buffers,
and result-set materialization are outside every window here, and `m-snapshot-read`
does not bound them: what the contract bounds is the Parallax-owned working set,
and a port that read the whole result into memory before answering the first page
would leave every number below unchanged.

**Wall clock.** One process's readings. The `us/root` column is recorded for
direction only — that a larger page reads faster per root — and no number in this
repository is enforced against elapsed time.

**A constant.** Every byte figure here is a level, but the claim it supports is a
difference, and a difference cannot see a Page held one page too long. The
census in the gated suite is what sees it, because it counts each kind a
delivery may hold and how many of it may be alive.

**Deep fan-out.** One include level at fan-out 5. The bound is deliberately
`O(P_B + G_max)` rather than `O(B)` — one root with a hundred thousand line items
dominates both terms — and no reading here varies `G_max` far enough to show that
domination.
