# Streamed-delivery working set — recorded baseline

What a running streamed read holds, measured on one machine under stated
conditions, against what the same delivery would cost a caller that kept every
root. `m-snapshot-read` *What a delivery costs* bounds the Parallax-owned working
set at `O(P_B + G_max)` and names three exclusions; this is the reading that puts
a scale on both halves.

Nothing here gates. `just python-report-stream-overhead` is a `report`: it passes
no verdict and belongs to no aggregate, because a total in bytes is machine- and
interpreter-relative — `tracemalloc` figures move with CPython, and every CI job
runs the floating `ubuntu-latest` label, so a tight ratio can flip on an
interpreter bump that changed nothing.

The *shape* of the bound is gated instead, in
`tests/unit/test_snapshot_stream_retention.py`, which the `cost` class owns and CI
runs on every change through `just python-check-cost`. That suite states the bound
as six separate readings. Page graphs do not accumulate: what a delivery retains
at ten times the roots, at a later position of the same delivery, and once
drained, differs from the baseline by less than one retained root costs. One page
graph and one published root are alive at a time, counted as objects — one
`SnapshotGraph`, one `GraphRows`, **no** `GraphMerge`, and exactly one root
carrying exactly its own fan-out. The survivor census over a crossed grid of page
sizes and fan-outs is exactly

```text
survivors = fixed + per_page_node x batch_size x (1 + fanout)
                  + per_published_node x (1 + fanout)
```

with the coefficients pinned as literals — 35 / 2 / 2 in the Typed lane, 36 / 2 /
1 in the Wire lane. The Wire lane's one extra fixed object is the frozen sequence
its published root spells the included relationship as, which a Typed root answers
from its node state instead; there is one per relationship the include tree names,
whatever the fan-out inside it, which is what makes it fixed. **There is
no term in the total result size and no term in how far the delivery has got**,
and both absences are read directly as well as by omission — over every survivor
whatever defined its type, and over the references those survivors hold, so a
delivery banking one thing per PAGE fails them even though it adds no object of
Parallax's own and no object at all past the first. And the two
exclusions are demonstrated rather than asserted: a caller retaining every root
reproduces growth proportional to the result, and a participating loop's buffered
writes cost the same per write at every page size, so the buffer is the dial's
own multiple.

## The reading

```text
  Python    CPython 3.14.7
  Platform  darwin/arm64
  Warm-up   200 unsampled runs before every window
  Shape     200 roots, fan-out 4, one include level,
            sampled inside the third page with the delivery still running

typed delivery
  page    at     held B   at 10x N    delta   survivors  inbound   us/root
     1     7     13,608     13,608       +0         129      160    1008.3
     2     9     16,041     16,041       +0         140      172     729.9
     8    21     31,888     31,888       +0         212      244     509.0
    32    69     95,528     95,528       +0         500      532     456.3

wire delivery
  page    at     held B   at 10x N    delta   survivors  inbound   us/root
     1     7     13,052     13,052       +0         113      143     916.1
     2     9     15,485     15,485       +0         124      155     638.6
     8    21     31,332     31,332       +0         196      227     423.3
    32    69     94,972     94,972       +0         484      515     384.4

caller-retention exclusion
  typed     3,641 B/root over 20 -> 200 roots  = 711 KiB at 200 roots
  wire      2,854 B/root over 20 -> 200 roots  = 557 KiB at 200 roots
```

**The `delta` column is the headline.** It is what ten times the roots moved the
working set by, holding the page size and the sampled position fixed, and it is
exactly zero at every page size in both lanes — not "small", and not "within a
tolerance". The bound's independence from the result is a structural property of
where the page loop releases, so the reading is a whole number of bytes rather
than a ratio.

**The page size is the whole cost.** The working set is affine in it — about
2,640 bytes per root position of the page at fan-out 4, in both lanes — because a
page's sealed graph holds every projection for that page's roots and their
children. A caller who wants a smaller working set asks for a smaller page and
pays for it in round trips, which the `us/root` column prices in the other
direction: at page size 1 a delivery costs one round trip per root and reads more
than twice as slowly per root as at page size 32.

**The exclusion is why the delta means anything.** Keeping every root of the same
200-root result costs 711 KiB in the Typed lane against a working set that did
not move at all, so the constant the delivery holds is worth roughly nine
retained roots at page size 8. A caller that appends every root to a list has
opted out of the bound; that is the contract, and this is its price.

**Typed and Wire differ by a constant, not by a rate.** The Typed lane holds
exactly 556 bytes more at every page size — the same figure at 1, 2, 8, and 32 —
because the page graph is the same read either way and only the published root
differs. Retention is a property of the read rather than of the representation.
What differs materially is the exclusion's slope: a retained Wire tree is about a
fifth cheaper than a retained Typed node graph, and a caller keeping the whole
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
difference, and a difference cannot see a page graph held one page too long. The
census in the gated suite is what sees it, which is why its coefficients are
literals rather than a fit.

**Deep fan-out.** One include level at fan-out 4. The bound is deliberately
`O(P_B + G_max)` rather than `O(B)` — one root with a hundred thousand line items
dominates both terms — and no reading here varies `G_max` far enough to show that
domination.
