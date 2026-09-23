# Published instance state and Typed Wire projection

What one published Typed Entity retains and costs under each backing, measured
on one machine under stated conditions, over COR-111's six canonical scenarios
and on every supported CPython minor. It is that ticket's measurement contract
discharged: retained bytes before and after per scenario, each scenario's own
percentage, the primary and secondary aggregates, construction, attribute-read
and serialization timings, transient allocation and peak memory — plus the
separate warmed scenario the contract requires beside the mix and outside every
aggregate. COR-112 adds a fourth, separate reading: what publishing the retained
Typed envelope as Wire costs. That projection reading does not alter the
three-arm aggregates and has no fabricated pre-projection baseline.

**Two different comparisons are recorded here, and every figure says which it
makes.** The aggregates and the regression ratios divide the *legacy* arm into
the compact one: the representation change the ticket asked for, and the pair its
33% target is stated over. The *ordinary* arm — the validating constructor, what
a caller builds for themselves — enters neither, and answers the other question:
what a published node retains against one a caller made. That is the comparison
`spec/python.md` §2's Interface statement is made over, and this reading is what
measures it.

**Not every timing is like for like, and the one that is not is graded on the
figure that needs no correction.** Retained bytes and the two read timings compare
one node against one node under each arm, and are exact. Construction does not: a
compact node arrives from a call that does per-node work the legacy fixture
reproduces none of, so the report measures what the fixture DOES do, leaves the
rest as `outside µs`, and prints the construction ratio twice — once arm against
arm, once with that remainder added to the legacy side. **The 20% rule is stated
over the arm-against-arm figure**, because the work the fixture never reproduced
is work the pre-flip path did pay: the true before side is at least the legacy
arm's own timing, so the true ratio is at most that figure whatever the remainder
is worth. The corrected column is the closer *estimate* of what the representation
change itself cost and is printed beside it, never graded — it is a remainder of
two independently sampled timings, and one that sampled high would pull the
reading under the limit. *Construction* below says what each column rests on.

Nothing here gates. `just python-report-instance-state` is a `report`: no number
it computes changes its exit code, because a total in bytes is machine- and
interpreter-relative — `tracemalloc` figures move with CPython, and every CI job
runs the floating `ubuntu-latest` label. What the report does compute is the two
comparisons the contract names, and it displays them as an escalation block so a
missed target is read rather than noticed. Saying which side of a stated limit a
measurement fell on is what `core/spec/language-testing.md` §2 leaves a
non-blocking command; deciding anything on the answer is what it does not, and
neither comparison reaches the exit code. The one thing the report exits non-zero
on is completeness: a matrix cell with no reading is named and refused, which says
there is nothing here to read.

## The three arms

**The compact arm is production.** `EntityGraphConstruction.construct` itself —
one allocation, one positional member row and one relationship row across
`populate`'s door, one complete tuple attached once. There is no fixture to keep
in step with it.

**The ordinary arm is the validating constructor**, `cls(**members)`, with the
members the row carried passed by keyword and the absent ones left to their
declared defaults, and its occurrences built the same way. It stands for no
publication path and enters no aggregate. It is here because §2 states what a
published instance costs against an *ordinary* one, which is neither of the two
arms the aggregates divide, and because a claim about a comparison nobody
measured is a claim about nothing. Note that an ordinary node records the
presence a caller stated, where the legacy fixture recorded none — which is why
`partial`, the one scenario whose caller omits most members, retains *less*
ordinary than as a legacy fixture.

**It carries no lifecycle state, and the arm refuses one.** `spec/python.md` §3
says a plainly constructed instance has no views and no lifecycle state to carry,
so its `lifecycle B` is zero on every scenario and its `retained B` and `bare B`
are the same reading. This is the one place where the three arms are deliberately
*not* given identical treatment, and it is what makes the ordinary comparison a
comparison of things that exist: attaching a synthetic `SnapshotNodeState` to an
ordinary node instead — as an earlier take on this reading did — puts 136 bytes
per scenario into a denominator no caller's instance holds, and flatters the
published side by about four points (43.8% would read 39.8% on 3.14, and 41.0%
would read 37.2% on 3.13).

**The legacy arm is a fixture, and has to be.**
`tests/unit/_instance_state_support.legacy_publication` builds one node the way
Entity Graph Construction built one before the flip: `cls.model_construct()` with
**no arguments** followed by one `object.__setattr__` per member, which leaves
`__pydantic_fields_set__` permanently empty. Ordinary keyword construction would
get every value right and that wrong, and the empty set is a large share of what
a published node retained then — so the fixture reproduces the construction call
rather than the result. A Value Object was different and is reproduced
differently: `vo_class.model_construct(present, **values)`, where `present` is
exactly the members the row carried. While the real legacy path existed the
report compared every scenario's fixture against it before measuring anything and
exited non-zero on any disagreement; the flip deleted the path, and that check
retired with it.

**Every arm is read in one child, on one tree, over one object layout**, which
is what makes a ratio between two of them the representation's and not an
accounting artifact. Every framework slot a declared class carries is carried by
all three — an ordinary value holds the compact and auxiliary pointers exactly as
a published one does, and an Entity of any backing holds the lifecycle *slot*.
What differs is what is attached to that slot, which is a fact about the value
rather than about its layout: publication attaches state under either backing and
ordinary construction attaches none. See *Four object layouts* below for why the
layout sentence is load-bearing.

## The figures

Bytes reachable at the seam's innermost point while one node of that arm is held
that were not reachable before the window opened. `retained B` carries the node's
lifecycle state where that arm's node has one; `bare B` is the same node with none
attached; `lifecycle B` is their difference, and zero on the ordinary arm, which
has none to attach. `cells` is what the backing holds — for the ordinary and legacy arms
the entries of its instance storage, and for the compact arm the positions of its
one row, which is the presence bitmap plus every declared member plus every
declared relationship. `read ns` is per declared field read, averaged over every
field of the node. `peak B` is the high-water mark one construction reaches, read
against the collected floor it starts from, and `transient B` is what it
allocated and freed again on the way there — that mark less what the node keeps,
so neither column counts the node twice and neither leaves it out.

**Construction is three columns, because the arms' calls are not the same size.**
`node µs` is what one MORE node of that arm costs and `call µs` is what one call
costs besides the nodes it builds, separated by timing a one-node build against
an eleven-node one under each arm. That split is what makes construction
comparable at all: a compact node arrives from a `construct` call that also pays
a call scope, a writer, root validation and factory buffering, where the ordinary
and legacy arms build a node and nothing else — so `call µs` is about 1.3–2.1 µs
under the compact arm and indistinguishable from zero under the other two, where
it is a remainder of two timings and reads a tenth or two either side of nothing.
A per-call construction figure would charge the compact arm for work no *node*
costs.

`outside µs` is the third column, and it is what that split does **not** remove.
A `construct` call's populated check, root validation, per-node resolution view,
factory buffering and root tuple all scale with node count, so they stay inside
the compact arm's `node µs` — and the legacy fixture, which reproduces the node
*building* alone, pays none of them although the pre-flip path paid all of them
through the same call.

The compact arm's call is therefore measured a second time, with **everything the
fixture also does** timed from inside it. That list is closed because the fixture
is closed: the legacy arm's per-node work is four statements, and each has one
span. Its state creation is timed as the state factory; its node building as the
build callback; its lifecycle attach by repeating the same write, since
`construct` performs its own inside a loop that is no callback; and the result
tuple its graph returns as this arm's own, built and released inside the span
because the caller that receives the real one releases it inside the window that
times it.

**Every one of those spans prices its term high, and that is the direction the
corrected figure's error runs in.** The repeated attach writes a slot that already
holds a value and so releases the state it displaces, where `construct`'s own
write finds that slot empty; each span also carries the clock reads that bound it,
and a call runs one state-factory span per node. So the measured common work
*expects* to exceed the real common work, and the remainder below expects to fall
short of the work the fixture never reproduced. That is a bias and not a bound:
the remainder is one marginal timing subtracted from another taken in a separate
loop, so a single reading of it can land either side of the truth. What is left
over after all of it is this column:
about **0.2 µs per node**, and 0.00–1.71 across the six scenarios of five
whole-matrix runs on both interpreters — a spread that is the column's nature
rather than the work's, since it is one marginal timing subtracted from another
and carries the noise of both, and the reason this correction is reported as a
bound. One of those seventy readings came out below zero and is reported as the
zero it stands for: a negative correction is not a measurement of work, and
carrying it would price the pre-flip path under the fixture standing for it. It is exactly zero for the ordinary and legacy
arms, whose call *is* a loop over their node builder, and it is taken in a
separate call so that no clock runs inside the one `node µs` is measured over.

**So every ratio below is printed twice, and the 20% rule is stated over the
left-hand one.** *Arm against arm* divides the two `node µs` columns as each was
timed, charging the compact arm for the whole of `outside µs`. It is the graded
figure precisely because it uses no remainder: the work the fixture never
reproduced is work the pre-flip path did pay, so the true before side is at least
the legacy `node µs` and the true ratio is at most this column. *Like for like*
adds `outside µs` to the legacy side instead, which is the closer estimate of what
the representation change itself cost — printed, and not graded, because a
remainder that sampled high would put it under the limit while the truth is over
it. Grading the left column instead can surface an operation whose true ratio is
under the limit, which is a line to read rather than a gate that fails. For
attribute read and serialization the two columns are equal by construction — one
call against one call on one node — so those two figures are exact rather than
estimated, which is what shows which operation needed a correction at all. Two reduction rows follow each scenario,
each naming the arm the compact one is divided into.

### CPython 3.14.7

| scenario | fields | arm | cells | retained B | bare B | lifecycle B | node µs | call µs | outside µs | read ns | dump µs | transient B | peak B |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| shallow | 4 | ordinary | 4 | 584 | 584 | 0 | 0.83 | 0.21 | 0.00 | 29.4 | 0.76 | 936 | 1,520 |
|  |  | legacy | 5 | 720 | 584 | 136 | 2.80 | 0.23 | 0.00 | 29.0 | 0.75 | 602 | 1,322 |
|  |  | compact | 6 | 416 | 280 | 136 | 4.37 | 1.47 | 0.28 | 91.7 | 1.42 | 3,608 | 4,024 |
| | | **vs legacy** | | **42.2%** | **52.1%** | | | | | | | | |
| | | *vs ordinary* | | *28.8%* | *52.1%* | | | | | | | | |
| wide | 16 | ordinary | 16 | 1,376 | 1,376 | 0 | 1.74 | 0.24 | 0.00 | 23.7 | 1.17 | 2,088 | 3,464 |
|  |  | legacy | 17 | 1,000 | 864 | 136 | 7.68 | 0.25 | 0.00 | 24.3 | 1.22 | 784 | 1,784 |
|  |  | compact | 18 | 544 | 408 | 136 | 8.14 | 2.06 | 0.18 | 86.4 | 2.51 | 3,288 | 3,832 |
| | | **vs legacy** | | **45.6%** | **52.8%** | | | | | | | | |
| | | *vs ordinary* | | *60.5%* | *70.3%* | | | | | | | | |
| nested | 5 | ordinary | 5 | 3,208 | 3,208 | 0 | 5.30 | 0.21 | 0.00 | 26.6 | 2.52 | 1,536 | 4,744 |
|  |  | legacy | 6 | 2,920 | 2,784 | 136 | 9.78 | 0.07 | 0.00 | 28.2 | 2.51 | 2,264 | 5,184 |
|  |  | compact | 7 | 1,232 | 1,096 | 136 | 13.84 | 1.99 | 0.20 | 85.2 | 5.99 | 4,553 | 5,785 |
| | | **vs legacy** | | **57.8%** | **60.6%** | | | | | | | | |
| | | *vs ordinary* | | *61.6%* | *65.8%* | | | | | | | | |
| nullable | 10 | ordinary | 10 | 1,184 | 1,184 | 0 | 1.27 | 0.20 | 0.00 | 25.5 | 0.92 | 1,416 | 2,600 |
|  |  | legacy | 11 | 1,000 | 864 | 136 | 5.21 | 0.36 | 0.00 | 24.2 | 0.92 | 832 | 1,832 |
|  |  | compact | 12 | 496 | 360 | 136 | 4.75 | 1.59 | 0.22 | 77.3 | 1.82 | 3,288 | 3,784 |
| | | **vs legacy** | | **50.4%** | **58.3%** | | | | | | | | |
| | | *vs ordinary* | | *58.1%* | *69.6%* | | | | | | | | |
| partial | 10 | ordinary | 10 | 672 | 672 | 0 | 0.96 | 0.22 | 0.00 | 25.1 | 0.91 | 1,040 | 1,712 |
|  |  | legacy | 11 | 1,000 | 864 | 136 | 4.96 | 0.17 | 0.00 | 22.5 | 0.90 | 832 | 1,832 |
|  |  | compact | 12 | 464 | 328 | 136 | 3.75 | 1.39 | 0.19 | 79.8 | 1.81 | 3,344 | 3,808 |
| | | **vs legacy** | | **53.6%** | **62.0%** | | | | | | | | |
| | | *vs ordinary* | | *31.0%* | *51.2%* | | | | | | | | |
| polymorphic | 7 | ordinary | 7 | 1,184 | 1,184 | 0 | 1.06 | 0.20 | 0.00 | 25.7 | 0.84 | 1,368 | 2,552 |
|  |  | legacy | 8 | 808 | 672 | 136 | 4.05 | 0.06 | 0.00 | 28.2 | 0.87 | 624 | 1,432 |
|  |  | compact | 9 | 440 | 304 | 136 | 4.90 | 1.41 | 0.31 | 81.1 | 1.61 | 3,224 | 3,664 |
| | | **vs legacy** | | **45.5%** | **54.8%** | | | | | | | | |
| | | *vs ordinary* | | *62.8%* | *74.3%* | | | | | | | | |
| *warmed* | 4 | ordinary | 5 | 822 | 822 | 0 | 1.77 | 0.19 | 0.00 | 28.3 | 0.77 | 1,050 | 1,872 |
|  |  | legacy | 6 | 1,046 | 910 | 136 | 4.02 | 0.11 | 0.00 | 28.2 | 0.75 | 624 | 1,670 |
|  |  | compact | 6 | 838 | 702 | 136 | 6.50 | 1.97 | 0.26 | 95.4 | 1.76 | 3,370 | 4,208 |
| | | *vs legacy* | | *19.9%* | *22.9%* | | | | | | | | |
| | | *vs ordinary* | | *-1.9%* | *14.6%* | | | | | | | | |

The representation change — the legacy arm divided into the compact one, which is
what the ticket's target is stated over:

| aggregate | before | after | reduction |
|---|---:|---:|---:|
| **primary** (lifecycle included) | 7,448 | 3,592 | **51.8%** |
| **secondary** (lifecycle excluded) | 6,632 | 2,776 | **58.1%** |

| operation, over the mix | arm against arm | like for like |
|---|---:|---:|
| construction (per node) | **1.15x** | 1.11x |
| attribute read | **3.21x** | 3.21x |
| serialization | **2.11x** | 2.11x |

Stated separately, in no aggregate — the ordinary arm divided into the compact
one, which is the comparison §2 states:

| comparison | ordinary | compact | |
|---|---:|---:|---:|
| published against ordinary (lifecycle where each holds it) | 8,208 | 3,592 | **56.2%** less |
| what a published node retains | | | **43.8%** of an ordinary one |

| operation, over the mix | ratio |
|---|---:|
| construction (per node) | 3.56x |
| attribute read | 3.22x |
| serialization | 2.13x |

### CPython 3.13.15

| scenario | fields | arm | cells | retained B | bare B | lifecycle B | node µs | call µs | outside µs | read ns | dump µs | transient B | peak B |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| shallow | 4 | ordinary | 4 | 560 | 560 | 0 | 0.81 | 0.18 | 0.00 | 26.5 | 0.70 | 856 | 1,416 |
|  |  | legacy | 5 | 696 | 560 | 136 | 2.69 | 0.21 | 0.00 | 25.1 | 0.71 | 506 | 1,202 |
|  |  | compact | 6 | 384 | 248 | 136 | 4.18 | 1.34 | 0.28 | 87.4 | 1.37 | 3,368 | 3,752 |
| | | **vs legacy** | | **44.8%** | **55.7%** | | | | | | | | |
| | | *vs ordinary* | | *31.4%* | *55.7%* | | | | | | | | |
| wide | 16 | ordinary | 16 | 1,352 | 1,352 | 0 | 1.72 | 0.24 | 0.00 | 21.7 | 1.13 | 2,008 | 3,360 |
|  |  | legacy | 17 | 976 | 840 | 136 | 7.69 | 0.36 | 0.00 | 22.2 | 1.21 | 688 | 1,664 |
|  |  | compact | 18 | 512 | 376 | 136 | 8.10 | 1.77 | 0.24 | 79.5 | 2.44 | 3,112 | 3,624 |
| | | **vs legacy** | | **47.5%** | **55.2%** | | | | | | | | |
| | | *vs ordinary* | | *62.1%* | *72.2%* | | | | | | | | |
| nested | 5 | ordinary | 5 | 3,080 | 3,080 | 0 | 5.03 | 0.25 | 0.00 | 31.0 | 2.38 | 1,336 | 4,416 |
|  |  | legacy | 6 | 2,792 | 2,656 | 136 | 9.16 | 0.05 | 0.00 | 32.6 | 2.41 | 2,168 | 4,960 |
|  |  | compact | 7 | 1,064 | 928 | 136 | 13.12 | 2.03 | 0.21 | 92.2 | 5.83 | 4,449 | 5,513 |
| | | **vs legacy** | | **61.9%** | **65.1%** | | | | | | | | |
| | | *vs ordinary* | | *65.5%* | *69.9%* | | | | | | | | |
| nullable | 10 | ordinary | 10 | 1,160 | 1,160 | 0 | 1.18 | 0.25 | 0.00 | 22.5 | 0.89 | 1,336 | 2,496 |
|  |  | legacy | 11 | 976 | 840 | 136 | 5.43 | 0.07 | 0.00 | 22.8 | 0.88 | 728 | 1,704 |
|  |  | compact | 12 | 464 | 328 | 136 | 4.63 | 1.36 | 0.21 | 76.1 | 1.84 | 3,112 | 3,576 |
| | | **vs legacy** | | **52.5%** | **61.0%** | | | | | | | | |
| | | *vs ordinary* | | *60.0%* | *71.7%* | | | | | | | | |
| partial | 10 | ordinary | 10 | 648 | 648 | 0 | 0.94 | 0.21 | 0.00 | 23.1 | 0.89 | 960 | 1,608 |
|  |  | legacy | 11 | 976 | 840 | 136 | 4.98 | 0.08 | 0.00 | 21.6 | 0.84 | 728 | 1,704 |
|  |  | compact | 12 | 432 | 296 | 136 | 3.62 | 1.34 | 0.17 | 76.4 | 1.84 | 3,232 | 3,664 |
| | | **vs legacy** | | **55.7%** | **64.8%** | | | | | | | | |
| | | *vs ordinary* | | *33.3%* | *54.3%* | | | | | | | | |
| polymorphic | 7 | ordinary | 7 | 1,160 | 1,160 | 0 | 1.06 | 0.21 | 0.00 | 23.2 | 0.79 | 1,288 | 2,448 |
|  |  | legacy | 8 | 784 | 648 | 136 | 4.04 | 0.23 | 0.00 | 23.9 | 0.79 | 520 | 1,304 |
|  |  | compact | 9 | 408 | 272 | 136 | 4.71 | 1.43 | 0.18 | 82.3 | 1.66 | 3,112 | 3,520 |
| | | **vs legacy** | | **48.0%** | **58.0%** | | | | | | | | |
| | | *vs ordinary* | | *64.8%* | *76.6%* | | | | | | | | |
| *warmed* | 4 | ordinary | 5 | 798 | 798 | 0 | 1.73 | 0.26 | 0.00 | 26.8 | 0.76 | 964 | 1,762 |
|  |  | legacy | 6 | 1,022 | 886 | 136 | 3.75 | 0.18 | 0.00 | 25.7 | 0.74 | 472 | 1,494 |
|  |  | compact | 6 | 806 | 670 | 136 | 6.34 | 1.61 | 0.23 | 87.3 | 1.70 | 3,130 | 3,936 |
| | | *vs legacy* | | *21.1%* | *24.4%* | | | | | | | | |
| | | *vs ordinary* | | *-1.0%* | *16.0%* | | | | | | | | |

| aggregate | before | after | reduction |
|---|---:|---:|---:|
| **primary** (lifecycle included) | 7,200 | 3,264 | **54.7%** |
| **secondary** (lifecycle excluded) | 6,384 | 2,448 | **61.7%** |

| operation, over the mix | arm against arm | like for like |
|---|---:|---:|
| construction (per node) | **1.13x** | 1.09x |
| attribute read | **3.33x** | 3.33x |
| serialization | **2.19x** | 2.19x |

| comparison | ordinary | compact | |
|---|---:|---:|---:|
| published against ordinary (lifecycle where each holds it) | 7,960 | 3,264 | **59.0%** less |
| what a published node retains | | | **41.0%** of an ordinary one |

| operation, over the mix | ratio |
|---|---:|
| construction (per node) | 3.57x |
| attribute read | 3.34x |
| serialization | 2.21x |

The aggregate is `1 - sum(after) / sum(before)` over the summed columns, **never
the mean of the per-scenario percentages**, which would weight a four-field node
like a nested one. Each scenario's own percentage is printed as a diagnostic and
enters no aggregate. The matrix is 3.14 and 3.13, derived from `requires-python`
and the support policy rather than authored: the declared floor is the range's
lower bound and "the latest minor + one prior minor" fixes its width above it.
Which interpreter takes the reading decides nothing — closing the range at
`sys.version_info` instead would silently drop the top row whenever the report
ran on anything but the latest minor.

## Typed-envelope Wire projection

COR-112 measures `Snapshot.wire()` from an already completed one-root Typed
envelope. The source envelope, matched direct-Wire Page, model preparation, and
the first correspondence check are outside every measured window. `fresh us`
includes the projection, construction of its public `Snapshot` envelope, and
access to `result()`. `reuse us` repeats the projection within one call's
successful class/layout reuse scope. `direct us` publishes the matched Page
through the canonical Wire walk, constructs the same public envelope, and also
accesses `result()`. The memory columns are caller-owned retained output,
allocation released before return, and their sum at the high-water mark.

### CPython 3.14.7

| scenario | retained B | transient B | peak B | fresh us | reuse us | direct us | fresh/direct |
|---|---:|---:|---:|---:|---:|---:|---:|
| shallow | 438 | 3,424 | 3,862 | 12.72 | 6.90 | 7.71 | 1.65x |
| wide | 672 | 3,192 | 3,864 | 14.97 | 8.87 | 7.27 | 2.06x |
| nested | 1,248 | 7,450 | 8,698 | 25.08 | 15.06 | 11.81 | 2.12x |
| nullable | 480 | 2,640 | 3,120 | 12.35 | 7.61 | 6.07 | 2.03x |
| partial | 392 | 2,608 | 3,000 | 11.53 | 6.85 | 5.37 | 2.15x |
| polymorphic | 480 | 2,808 | 3,288 | 12.64 | 7.58 | 6.59 | 1.92x |

### CPython 3.13.15

| scenario | retained B | transient B | peak B | fresh us | reuse us | direct us | fresh/direct |
|---|---:|---:|---:|---:|---:|---:|---:|
| shallow | 430 | 3,056 | 3,486 | 12.42 | 6.48 | 7.40 | 1.68x |
| wide | 664 | 2,872 | 3,536 | 14.11 | 8.66 | 7.51 | 1.88x |
| nested | 1,240 | 6,496 | 7,736 | 23.11 | 13.61 | 10.96 | 2.11x |
| nullable | 472 | 2,216 | 2,688 | 11.77 | 7.41 | 6.35 | 1.85x |
| partial | 384 | 2,216 | 2,600 | 11.02 | 6.39 | 5.29 | 2.09x |
| polymorphic | 472 | 2,528 | 3,000 | 11.89 | 7.10 | 6.19 | 1.92x |

The output graph, rather than its Typed source, determines retained memory:
384-1,240 B on 3.13 and 392-1,248 B on 3.14. The nested occurrence graph is the
largest retained and transient case; equal-width nullable and partial roots keep
different output sizes because presence is preserved. Peak is exactly retained
plus transient in every cell. The proof suite separately establishes that these
figures retain no reader, memo, encoder, Typed backreference, Page, RootView, or
execution owner.

Fresh projection takes 1.65-2.15x the matched direct publication, with medians of
1.90x on 3.13 and 2.05x on 3.14. Same-call reuse removes 37.1-47.8% of fresh
projection time on 3.13 and 38.4-45.7% on 3.14. It is near the direct publication
cost rather than universally below it: 0.88-1.24x direct on 3.13 and 0.90-1.28x
on 3.14. This is the measured price of projecting an existing Typed graph through
the canonical publisher, not another read and not Pydantic serialization.

## COR-112 before/after controls

The durable captures are the clean instrumented baseline `e372c69c` and the
clean reviewed implementation `77ef7566`. The after capture completed on
2026-09-22 with all required snapshot-delivery, write-lowering, and
instance-state matrices complete on both runtimes. The non-strict arithmetic is
archived outside Git at
`$HOME/.local/share/parallax/evidence/cor-112/comparison.md` (SHA-256
`07dee126dd6364f700ef91102fd34eebbfc317cd68993a0a22791c724668cdb8`).

This is an explicitly qualified comparison, not one mechanically certified by
`--require-compatible`. The strict check correctly refused arithmetic for one
reason and one reason only: the snapshot-delivery control source
`tests/unit/_snapshot_materialization_support.py` has a different digest. The
user reviewed and approved that sole exception as a semantically equivalent API
migration: the driver moved mechanically from `plan.levels` and the level-owned
`attach_key` to `plan.fetch_steps` and the canonical IncludeTree position view's
`narrowed_view` or relationship name. The validator was not weakened. With
`instance-state` explicitly required, it reported no other failure: both
envelopes are valid and clean; workload, budget, lock, sampling protocol,
machine, CPU/core/RAM, OS, in-process Python, PostgreSQL facts, per-runtime
interpreter identities, all other control and instrument sources, cell windows,
units, and sample counts match. The six projection cells are the declared
head-only matrix.

The controls show these directions:

- Existing instance-state retained and bare bytes are identical before and
  after in every scenario on both runtimes. The changed wall-clock readings are
  report-only variation around an unchanged representation matrix.
- Unused Typed retained memory rises by a fixed 0.016 KiB (16 B) in every eager
  cell, including the guarded controls, and is exactly unchanged for page-32
  delivery. Its median timing change is -2.5% for eager and +1.2% for page-32
  delivery; its peak allocation rises by medians of 5.9% and 5.3%.
- Direct Wire retained memory likewise rises by 0.016 KiB (16 B) in every eager
  cell, including the guarded controls, and is exactly unchanged for page-32
  delivery. Direct Wire timing rises by a median 9.4% for eager and 7.8% for
  page-32 delivery across runtime/workload/root-count cells; peak allocation
  rises by medians of 9.0% and 6.8%. The two-point
  200-to-2,000-root slopes move from a median 60.0 to 65.6 us/root eager and
  63.8 to 69.4 us/root page-32. These are directional one-run timing and peak
  observations, not gates; they do not hide retained growth or repeated
  publication, and no arbitrary materiality threshold is introduced here.
- Guarded-plan cold and warm timing remains centered within 1.3% of baseline;
  cold retained/peak memory rises about 2%, while warm retained memory is
  unchanged. Guarded Typed timing is centered 1.3% faster and Wire timing 10.5%
  slower, consistent with the broader delivery controls rather than planning.
- A closed result now retains the required model and IncludeTree metadata:
  about 6.1 KiB over the small model and 12.2-12.4 KiB over the larger model.
  The shared-owner controls move by only 16 B. This is bounded metadata lifetime,
  not an execution-resource survivor.
- Family model preparation remains stable: elapsed time is -4.8%/+0.8%, retained
  memory is +24 B, and transient memory falls 88/96 B on 3.13/3.14. The public
  family-bearing `tx.wire.insert` response retains exactly the same bytes and is
  0.3-3.0% faster, while transient allocation rises 1,421 B (22.6%) on 3.13 and
  2,243 B (34.4%) on 3.14. Response encoding and SQL-bind encoding remain
  distinct measured outputs.

The delivery slope fit is descriptive only. Page-32 fixed intercepts move from
about 7.6 to 8.1 ms for Wire and 7.4 to 8.2 ms for Typed; eager two-point
intercepts straddle zero and therefore do not support a fixed-cost claim. The
per-root slopes and exact retained figures are the useful scaling observations.

The direct-Wire whole-process cost proof read exactly 20 additional objects and
40 additional references with zero additional held bytes at the later delivery
position, and that reading was an artifact of the instrument rather than of what
the delivery holds. The mark collected once, and the collector untracks a tuple
only when every item in it is already untracked, so a read-plan key built from
the query's own dataclasses stayed listed for as many collections as it is deep;
which pass a sample landed after followed the process's allocation history. The
mark now collects until the listing stops moving, which makes the arms exactly
equal over a heap whose held bytes never differed. No threshold was weakened and
the captured readings above are unaffected: the whole-heap mark serves the cost
proofs alone and no reported figure is taken through it.

## COR-172 profile and recovery

The direct-Wire regression the controls above record was diagnosed from the code
and never measured. This section holds what one profiled delivery says about it.

### What was profiled, and on what

One provider-free eager direct-Wire delivery, assembled exactly as the
`control-delivery` window assembles one: the `conventional-fanout` catalog
workload at 2,000 roots behind `CatalogPort`, wrapped in `_SoleRuntime` and
opened as a `Database` over `ORDERS_MODEL`, with the root, the port and the login
scope composed outside the reading. One `database.wire.find(...).results()` was
delivered to warm the process and the read-plan cache, the port was reset, and a
second was taken under `cProfile`. The script that did it is uncommitted and
nothing it produced is checked in beyond this prose, following the precedent
`structural-metadata-envelope/README.md` sets for attributing a per-node
regression: these are readings, not evidence, and not one of the report's
windows.

Taken 2026-09-23 on the machine *Conditions* describes - Apple M5, 10 cores,
32 GiB, darwin/arm64, macOS 26.6.2 build 25G83 - under CPython 3.14.7, the
repository venv. Four runs of the same script agreed to within a tenth of a
percentage point on every share below, and the table is the last of them.

### Where the delivery's time goes

The profiled delivery is 0.395 s, of which the whole Wire walk -
`WireWalk.position` and everything beneath it - is 0.121 s, about 31%. The rest
is the read, row conversion, and Root View construction.

`render_token` is reached through `_admitted_node` and `position` rather than
from `_build`, and the recursive `_related` leg contains the entire subtree below
a node, so a ranking of `_build`'s literal direct callees would both miss the
first and be swallowed by the second. The walk's own five frames are therefore
read as pass-through, and every leg they reach is charged to that leg:

| leg | calls | cumulative | share of the walk |
|---|---:|---:|---:|
| `_trusted_wire_scalar` | 14,000 | 16.3 ms | 13.5% |
| **`IncludeTree.render_token`** | 12,000 | 9.1 ms | 7.5% |
| `_BindingRange.__iter__` | 24,000 | 7.7 ms | 6.3% |
| **`IncludeTree.child_groups`** | 12,000 | 7.0 ms | 5.8% |
| `_frozen_mapping` | 12,000 | 6.1 ms | 5.1% |
| `RootViewReader.layout` | 24,000 | 4.3 ms | 3.6% |
| `RootViewReader.relationship` | 2,000 | 2.9 ms | 2.4% |
| `IndexMemo.put` | 12,000 | 2.8 ms | 2.3% |
| `RootViewReader.origin` | 12,000 | 2.7 ms | 2.3% |
| `RootViewReader.member_values` | 12,000 | 2.4 ms | 2.0% |
| `IndexMemo.get` | 12,000 | 2.4 ms | 2.0% |
| `EntityLayout.attributes` | 12,000 | 2.1 ms | 1.7% |
| `EntityLayout.occurrences` | 12,000 | 2.0 ms | 1.7% |
| `typing.cast` | 52,000 | 1.9 ms | 1.6% |
| **`IncludeTree.admitted_children`** | 2,000 | 1.0 ms | 0.8% |

The three include-tree methods together are 17.1 ms: 14.2% of the walk and 4.3%
of the delivery, and the largest single contributor, just above the 13.5% of
per-attribute scalar conversion. Rendering 2,000 roots renders 12,000 nodes and
asks the tree 26,000 questions to do it. The two reader calls the ticket names
are visible beside them, one of them by its absence: `layout` is called 24,000
times for 12,000 nodes, while `occurrence_carrier` never appears, because no
Entity in this workload carries an occurrence. Hoisting it out of the occurrence
loop is therefore invisible to this cell and will show, if anywhere, on a
workload that has one.

### The profiled share overstates a leg reached many times per row

`snapshot-materialization-baseline.md` records the standing caveat, and here it
bears directly on the ranking rather than decorating it: `cProfile` charges its
own per-call bookkeeping to every call, so the tree methods' 26,000 calls are
inflated more than the 14,000 of the leg they edge out. The order of the first
two rows is a share of profiled time and not a magnitude, and the margin between
them is smaller than the bookkeeping that separates them.

### What an untraced ablation says

So the profiled share was read for magnitude the way the two attributed
regressions in `structural-metadata-envelope/README.md` were. Patched in the
diagnostic process only, with nothing in the repository changed, `IncludeTree`'s
three methods were given memoized bodies - the position's own canonical
`children` mapping returned by reference for a single-position token, one shared
empty mapping for `EMPTY_RENDER`, and a two-level dict over the existing
derivations for everything else - and the same delivery was timed untraced,
median of nine samples after three warm runs:

| reading | as it stands | memoized | delta |
|---|---:|---:|---:|
| elapsed | 90.1 ms | 85.1 ms | -5.6% |
| elapsed, second pairing | 90.0 ms | 85.1 ms | -5.5% |
| `tracemalloc` peak | 12,206.8 KiB | 12,206.8 KiB | -0.0% |

Two things follow, and they point in different directions. The derivation is
real and worth about 5.5% of this delivery against the 9.4% median COR-112 cost
direct Wire eager, so memoizing it recovers a substantial part of the timing
regression but not the whole of it. It recovers none of the peak allocation: the
transient dict, lists, tuples and proxies the three methods build are released as
each node finishes, so they never stand together and the high-water mark does not
see them. Whatever moved eager peak by 9.0% is not these allocations, and
removing them will not bring it back.

### The decision

**Go.** The rule the profile was taken to answer is whether the three tree
methods together are the largest cumulative contributor the walk reaches, and
they are: 14.2% of the walk against 13.5% for the next leg, on every one of four
runs, corroborated untraced by an ablation that recovers 5.5% of the delivery.

### The certified control-slice pair

The cells that grade this ticket are the `control` workload group, which the
report partitions as the `snapshot-controls` shard, so the pair is one
control slice on one host rather than a whole portfolio. Base
`1742bf4746a6a576fe5c83e585e48b8409141f2b` was measured through its own
checkout's tool first and head `3dbaf824bf792cf184930fa4584f4a2c72a6a926`
after, under request `local-8402785399af4c39933552d4422dfe2b` and pair
`3d6ef9b3623f49d9a8cae94221161546`, 354.3 s and 347.0 s of collection on
2026-09-23. The base is the merge-base with `main`: COR-170 had changed both
snapshot-delivery instrument scripts and the lock, so a base before it would
read through a different instrument than the head.

Both sides report the same provenance - Mac17,4 / Apple M5 /
macOS-26.6.2-arm64 / PostgreSQL 18.6, 3.13 = CPython 3.13.15 and 3.14 =
CPython 3.14.7 - and the same workload, contract, and lock digests. The
assembly paired all 206 control cells and left none unpaired. It planned ten
shards and reports nine as not arrived, which is what a slice is: evidence
about the slice, not an incomplete capture.

### What the pair recovered

Across the two provider-free delivery workloads, both root counts and both
runtimes, direct Wire is faster and nothing is slower. Medians of the
per-cell deltas against `1742bf47`:

| Lane | Elapsed | Peak | Retained |
|---|---:|---:|---:|
| `wire.eager` | -5.5% | +0.0% | +0.000 KiB |
| `wire.page32` | -4.9% | -0.0% | +0.000 KiB |
| `typed.eager` | +0.1% | +0.0% | +0.000 KiB |
| `typed.page32` | +0.3% | +0.0% | +0.000 KiB |

Of 206 cells the tool reads 25 as faster, 7 as smaller, and 174 as within
noise; it reads none as slower and none as larger. The guarded delivery
controls, whose overlapping sibling positions ask the tree the most, move
furthest: guarded Wire timing is a median 8.4% faster while guarded Typed
timing stays within 0.3%. The Typed delivery cells are the control that says
what changed: a Typed result that is never projected never enters the walk,
and its timing does not move.

The per-root slope is the reading that settles the ticket, because COR-112's
regression moved the slope rather than an intercept. Two-point 200-to-2,000
slopes, median over workloads and runtimes:

| | eager us/root | page-32 us/root |
|---|---:|---:|
| `e372c69c`, before COR-112 | 60.0 | 63.8 |
| `77ef7566`, after COR-112 | 65.6 | 69.4 |
| `1742bf47`, this pair's base | 64.2 | 68.8 |
| `3dbaf824`, this pair's head | 60.2 | 63.7 |

The per-node publication cost COR-112 added is gone: the head slope sits on
the pre-COR-112 slope on both delivery forms.

Peak allocation did not move, which is what the Phase 1 ablation predicted
and not a shortfall of the memo. The transients the three tree methods built
were released as each node finished, so they never stood together and the
high-water mark never saw them. COR-112's 9.0% eager peak rise has a cause
elsewhere and this change does not address it.

### Against the archived `e372c69c` baseline

The head slice was also compared against the archived pre-COR-112 portfolio,
which holds every control cell. Medians over the same delivery cells, beside
what the COR-112 controls above recorded for the same comparison:

| Cell group | COR-112 read | now |
|---|---:|---:|
| direct Wire eager elapsed | +9.4% | +0.7% |
| direct Wire page-32 elapsed | +7.8% | +0.9% |
| guarded Wire elapsed | +10.5% | +2.0% |
| direct Wire eager peak | +9.0% | +8.7% |
| direct Wire page-32 peak | +6.8% | +5.4% |
| direct Wire eager retained | +0.016 KiB | +0.016 KiB |

Every direct-Wire delivery timing cell is within the tool's 5% allowance.
One guarded cell is not: 3.13 `control-guarded-3 wire.eager.roots256` reads
+5.9%, while its 3.14 twin reads -2.3% and the same cell is 9.0% faster than
this pair's own base. It is one cell of twelve in a window whose median
residual is +2.0%, taken from a nine-sample median against an archive
captured on another day, and it is read as the width of that qualified
comparison rather than as a surviving regression.

### What the memo costs a retained result

The memo rides with the `IncludeTree` into every Typed result envelope, and
the `result-held-metadata` window prices it. Against `1742bf47` the `closed`
reading rises by exactly 0.281 KiB (288 B) on both models and both runtimes,
and the `shared` reading is exactly unchanged. The same fixed 0.281 KiB
appears in `plan.cold` retained and peak at all three guard widths, and
`plan.warm` retained is unchanged at 0.062 KiB. That the figure is one
constant - independent of model, of guard width, and of root count - is the
bound stated in `spec/python.md` and ADR 0012 read off the instrument: the
memo is a function of the includes clause and the model, never of roots.

This control holds an eager Typed result that is never projected, and only the
Wire walk calls the three memoized methods, so 288 B is the three empty memo
dicts a tree carries from construction. A projected result additionally holds
the keys its own walk reached, which the flatness proof in
`tests/unit/snapshot/handle/test_read_include_tree_memo_bound.py`
pins as identical at both memory scaling arms. Against `e372c69c` the `closed`
reading is 6.4 KiB larger on the small model and 12.5-12.7 KiB on the larger
one, which is COR-112's metadata retention with this ticket's 0.281 KiB
inside it.

### The comparison against the archive is qualified, not certified

The archived arithmetic is outside Git at
`$HOME/.local/share/parallax/evidence/cor-172/comparison.md` (SHA-256
`8f776b7b08d3141f528b2e2ae5a1e7945c24eafae99f20034f31191fb03a8347`), beside
the pair's own base, head, and assembled outputs.

`--require-compatible` refuses that comparison and reports four reasons, none
of them a digest, because neither envelope reaches the digest check. The
archived base carries `schemaVersion` 1 for both its snapshot-delivery and
its write-lowering envelope, where the current schema requires 2. The head is
a one-member control slice, so its snapshot-delivery matrix is not exact - it
carries no cell for any of the five heavy workloads - and it carries no
write-lowering envelope at all. Both are properties of comparing a slice
against an older whole portfolio, not of the measurement; the certified
reading is the `1742bf47` pair above, and this one is the ticket's stated
tie back to the baseline it names.

## What the escalation block said

Both rules the measurement contract names are computed by the report and printed,
so neither depends on a human noticing a number.

**The aggregate target is met on both runtimes.** The primary aggregate is 51.8%
on 3.14 and 54.7% on 3.13, against a 33% minimum; the secondary is 58.1% and
61.7%. No aggregate line appears in the block.

**Two representative operations moved past the 20% review threshold, on both
runtimes**, and the report names each with its worst scenario. The rule is stated
over the *arm-against-arm* column, and for these two that column is the
like-for-like one as well: a member read and a `model_dump()` are one call against
one call on one node, so there is no scope to correct and both figures are exact. The figures below are the
recorded run's; across five runs the ratios move by a few percent while the byte
readings do not move at all, and neither of the two comes near the threshold from
either side:

| operation | 3.14 | 3.13 | across five runs | what it is |
|---|---:|---:|---:|---|
| serialization | 2.11x | 2.19x | 2.11–2.19x | already accepted as an Interface fact — see below |
| attribute read | 3.21x | 3.33x | 3.19–3.67x | a published node has no instance dictionary |

**Construction is not among them, and the 1.20x limit is the one it always was.**
The figure was recorded here at 1.38x and 1.33x before either correction, and the
limit never moved: what changed both times is the measurement. Correcting the
*call* scope came first — the earlier figure divided one whole `construct` call by
one fixture build, charging the compact arm for a call scope, a writer, root
validation and factory buffering that no node costs — and both arms are now timed
per node, which brought the arm-against-arm figure to **1.13–1.16x** across the
five runs recorded here. Two of the six scenarios (`partial` and `nullable`) are
*faster* compact per node.

**The arm-against-arm figure is the graded one, and it is 1.15x on 3.14 and 1.13x
on 3.13.** It divides the two `node µs` columns exactly as each was timed and uses
no correction at all, which is why the rule reads it: the per-node work the fixture
never reproduced is work the pre-flip path did pay, so the true "before" is at
least the legacy `node µs`, and the true ratio is at most this figure whatever that
work is worth. Under 1.20x here is therefore under 1.20x in truth. It charges the
compact arm for the whole of that work, so it is a loose bound — the price of
grading a figure that nothing can pull downwards.

**A second, tighter reading is printed beside it and is not graded.** The per-node
split cancels a `construct` call's *fixed* cost and not its per-node one: the
populated check, root validation, a resolution view per node, the factory buffering
and the root tuple all scale with node count, so they stay inside the compact arm's
`node µs`. The pre-flip path paid that work through the same call — that half of
`EntityGraphConstruction` is unchanged either side of the flip — but the legacy arm
is a fixture of the node *building* alone and pays none of it. The report measures
the difference as `outside µs` and prints a second ratio with it added to the
legacy side: **like for like, construction is 1.11x on 3.14 and 1.09x on 3.13**,
1.07–1.11x across the five runs. That is the closest estimate of what the
representation change itself cost, and both columns are printed so the correction
is visible rather than asserted.

**Nothing the fixture also pays is left on the legacy side twice, and the list of
what it pays is closed.** A correction that added common work to the "before"
would flatter the compact arm, so what the fixture does is measured out rather
than named — and what it does is enumerable, because it is a fixture: the legacy
arm's per-node work is four statements of `_instance_state_support`, and each has
exactly one span in the second measurement. It creates a `SnapshotNodeState`; it
builds a node; it attaches that state; and its graph collects the result into a
tuple which its caller then releases. The state creation is timed as the compact
call's state factory and the node building as its build callback. The other two
are no callback of the arm's — the attach happens inside `construct`'s own loop —
so the attach is priced by repeating the same write on the published node, and the
tuple by building this arm's own through the same function the graph uses and
releasing it inside the span.

**The list being closed fixes the direction of the correction's bias, and not its
noise — which is why the rule is not stated over it.** Each of those four spans
prices its term high and none prices one low: repeating an attach releases the
value the slot already holds where the first write finds it empty, and every span
carries the clock reads that bound it, one state-factory span per node among them.
So the measured common work *expects* to exceed the real common work and
`outside µs` expects to fall short of what the fixture never reproduced. But
`outside µs` is one marginal timing subtracted from another taken in an
independent loop, worth about 0.2 µs per node against a 0.00–1.71 spread across
seventy readings: a residue that sampled high enlarges the legacy side it joins and
puts **1.09–1.11x below the true like-for-like ratio rather than above it**. A rule
that must not miss a regression cannot rest on that, so it reads the column that
needs no residue — **1.13–1.16x arm against arm** — and the corrected column is
reported as the closer estimate. The two differ by about four points, which is what
`outside µs` is worth. Measuring the tuple and the attach out at all cost the
compact arm about a point of the corrected figure, from 1.07–1.09x to 1.09–1.11x,
and moved no aggregate. An earlier hand measurement of the same residue put it at
0.23 µs per node and the corrected ratio at 1.12x, against the 0.00–1.71 µs and
1.07–1.11x the report now measures — the two agree on the residue's typical value
and differ on the ratio by about the arm-against-arm figure's own run-to-run
movement.

**The ordinary construction ratio needs no correction and gets none, and is 3.56x
on 3.14 and 3.57x on 3.13.** A caller building an ordinary instance pays no
construction call at all, so both sides of that ratio are the same quantity: the
marginal cost of one *additional* node, which is where publishing one costs about
three and a half times validating one. It is not the whole of either call — each
arm's `call µs` sits outside it, and the compact arm's is the 1.3–2.1 µs a
`construct` call costs however many nodes it builds, which an ordinary caller has
no equivalent of. It is not a regression from anything either — publication has
always paid a call the constructor does not — and no ordinary ratio can reach the
escalation block, which is stated over the representation change alone.

**Serialization is a settled trade rather than a new finding.** A published
value's `model_dump` running roughly twice an ordinary value's is stated at the
seam, in `_instance_state`'s module docstring and in `spec/python.md` §2, because
performance characteristics are part of a Module's Interface. pydantic-core reads
a model's `__dict__` twice per instance per dump and each read builds a
presentation, so no Python-level presentation reaches parity; `docs/deferred-ledger.md`
D-82 is the optimization path and what is known about taking it.

**The attribute read is the same fact from the other side.** A published node has
no instance dictionary at all, so `object.__getattribute__` finds nothing at the
instance and resolves the member through the `Attr` descriptor — a Python frame
where an ordinary value's read is a C-level dictionary hit. This is what buys the
retained-byte reduction above, and it is confined to published values: an
ordinary value's field read is a plain Pydantic model's, unchanged.
`docs/deferred-ledger.md` D-83 carries it.

**What a published node retains against an ordinary one is a different
comparison, and is now measured rather than asserted.** The aggregates above
divide the legacy arm, which is the representation change. §2 and ADR 0011 state
the figure against an *ordinary* instance, which the ordinary arm supplies:
summed over the mix, **8,208 → 3,592 B on 3.14 and 7,960 → 3,264 B on 3.13** — a
published node retains **43.8%** and **41.0%** of an ordinary one, a 56.2% and
59.0% reduction. Each side carries what it holds: the published node its lifecycle
state, the ordinary node none, because it has none. Compare the two backings alone
and the figure is 33.8% and 30.8% — that is `bare B` against `bare B`, and it is
what the row-versus-storage difference costs before the state either kind of node
carries.

The ordinary comparison goes both ways per scenario, because an ordinary node
records the presence its caller stated where the legacy fixture recorded none:
`partial`'s ordinary node is 672 B against the fixture's 1,000, so its reduction
against ordinary is 31.0% where its reduction against legacy is 53.6%. Neither
figure enters the other's aggregate, and every table above says which comparison
it makes.

**The excluded `warmed` scenario retains more published than ordinary**, by 16 B
on 3.14 and 8 B on 3.13 — the only negative reduction anywhere in the reading. A
`cached_property` result that lands in an ordinary node's instance dictionary
lands in a published node's auxiliary slot, which is a fresh mapping rather than
storage that already exists, so author-owned state is where the compact
representation has nothing to save. This is the scenario the measurement contract
holds outside every aggregate, and the direction of its result is why the
disclosure matters rather than only the exclusion.

## What the scenarios are

| scenario | shape |
|---|---|
| shallow | 4 Attributes, 1 declared relationship left unloaded |
| wide | 16 Attributes, 1 declared relationship left unloaded |
| nested | 3 Attributes, a One occurrence carrying a nested One, and a Many of 2 |
| nullable | 10 Attributes, every one carried as an explicit null |
| partial | the same class as `nullable` — 3 Attributes carried, 7 absent |
| polymorphic | a 3-level Table-per-Hierarchy family, published as the concrete: 7 Attributes across three contributors |
| *warmed* | `shallow`'s 4 Attributes plus a `PrivateAttr` and a `cached_property` read before the sample |

Every root declares one self-referential broad relationship, left unloaded.
Publication writes **every** declared relationship slot on every node, so a mix
declaring none would understate the two publication arms; one apiece keeps that
cost uniform across the mix and attributable to a single position. The ordinary
arm writes none, because ordinary construction does not: a relationship is
publication's, and an ordinary node's `cells` is its declared members alone.

`nullable` and `partial` share a class deliberately: presence is the only variable
between them, which is the distinction a compact bitmap has to preserve. On the
frozen tree they were physically identical (see *What this reading surfaced*);
they are not now, and their reductions differ by three points because the compact
arm records what the row carried.

**The `warmed` scenario is reported and excluded from every aggregate**, as the
measurement contract requires. A `PrivateAttr`'s value and a `cached_property`'s
result are state the author asked for; both live in ordinary per-instance storage
under every backing — the private mapping in its own slot, the memoized result
in the auxiliary slot for a published value and in the instance dictionary for an
ordinary one — so charging a representation change with them would credit or debit
it for something no backing decides. It is held outside `SCENARIOS` rather
than flagged inside it, so no aggregate can pick it up by iterating the mix. Its
reduction is about 20%, which is the same node as `shallow` with roughly 400 bytes
of author-owned state added to every arm.

## Conditions

| | |
|---|---|
| Recorded | 2026-08-26 |
| Machine | Apple M5, 10 cores, 32 GiB, darwin/arm64 |
| OS | macOS 26.5.2 (build 25F84) |
| Interpreters | CPython 3.14.7 (the repository venv) and CPython 3.13.15, both Clang 21.0.0 |
| Pydantic | 2.13.4 / pydantic-core 2.46.4 on both |
| Command | `just python-report-instance-state` |
| Isolation | one fresh child interpreter per complete scenario, every arm inside that child |
| Warm-up | 200 unsampled runs before every window, as each child's own instruments declare |
| Timing samples | mean of 2,000 repetitions, taken with the line tracer uninstalled |
| Construction scope | a 1-node build against an 11-node one under each arm, split into the per-node cost and the per-call remainder |
| Common-work scope | the compact call measured a second time with everything the legacy fixture also does timed from inside it — its state factory, its build callback, a repeat of the per-node lifecycle attach, and its graph's result tuple built and released inside the span — which is what `outside µs` is the remainder of, and every span of which prices its term high |
| Repeatability | five independent whole-matrix runs returned byte-identical readings on both interpreters — every retained, bare, lifecycle, `cells`, transient and peak figure above is the same in all five, under all three arms; only the wall clock moved, and the ratios with it — against the legacy arm, construction 1.13–1.16x arm against arm and 1.07–1.11x like for like, attribute read 3.19–3.67x, serialization 2.11–2.19x; against the ordinary arm, construction 3.55–3.67x, attribute read 3.16–3.65x, serialization 2.13–2.21x; `outside µs` 0.00–1.71 per node. The tables above are the FIRST of those five rather than a chosen one |
| Elapsed | about 13 s for the whole matrix, of which roughly 2.5 s is the compact arm's common-work timing |

The matrix is 3.14 and 3.13. The ticket names 3.12 as well, but commit `226db9d3`
— already in this branch — set `requires-python = ">=3.13"` across all five
packages and narrowed the specification's support policy to "current + one prior
minor", so 3.12 cannot be installed and that acceptance line is superseded.

## What is measured, and what is excluded

**Decoded payload leaves are excluded structurally, not by filtering.** Every
scenario's input row and every leaf in it — strings, `Decimal`s, floats, the
nested Value Object rows — is allocated at import time, outside every window, so a
node that merely references one costs the reading the position and not the leaf.

**Shared class and model metadata is excluded the same way.** Every reading warms
its seam 200 times before opening its window, so a member layout, a class index, a
Value Object shape, a construction's per-Entity facts, and the class publication
plan are already in the baseline the sample is compared against.

**The lifecycle state is not excluded, and is measured as a difference.** It is
built inside the window, so the reading that carries it counts it; `lifecycle B`
is the difference between the two readings rather than a measurement of the state
object alone. It is a uniform 136 bytes on every scenario under both publication
arms, because the state rides a real slot on the `Entity` root under any backing
and attaching it therefore resizes nothing — and zero under the ordinary arm,
which has none.

## Four object layouts, and the rule for dividing them

This document carries figures from four different object layouts — the tree
before COR-111, the intermediate one the seam's first take produced, the one the
instance-state presentation added to it, and the current tree. Every summed number
below belongs to exactly one of them, and an aggregate that mixes them is wrong in
a way no reader can see from the number alone. So the layouts are named first and
the rule for using them is stated after.

The framework root that both kinds of declared class extend gained two slots,
**8 bytes per instance each, on both backings** — an ordinary value carries the
two pointers exactly as a published one does — and the `Entity` root gained a
third with the publication flip:

| slot | what it holds | added with |
|---|---|---|
| `__parallax_compact__` | a published value's whole row, or `None` on an ordinary value | the compact representation |
| `__parallax_auxiliary__` | a published value's `cached_property` results, allocated on the first such write | the instance-state presentation that replaced the schema seam |
| `__parallax_lifecycle__` | a materialized Entity's opaque lifecycle state, on the Entity root alone | the publication flip, which leaves a published node no storage to hold it in |

| layout | tree | legacy arm, lifecycle included | excluded |
|---|---|---:|---:|
| no framework slots | the frozen tables below | 7,328 | 6,424 |
| `__parallax_compact__` only | the first take of the compact seam | 7,408 | 6,504 |
| both instance-state slots | the tree the presentation landed on | 7,488 | 6,584 |
| all three | **the current tree, and what the three-arm reading above took** | 7,448 | 6,632 |

`fields` and the scenario shapes are unchanged across all four. `cells` and the
sums are not, from the third row to the fourth, and both moved for one reason:
the lifecycle slot is the third pointer every Entity instance now carries, and
what a legacy arm attaches to it no longer lands in the storage mapping — so
each node's storage lost an entry while its layout gained a slot. `lifecycle B`
falls from 224/136 to a uniform 136 with it, because `shallow` no longer crosses
a dictionary growth boundary when its lifecycle state is attached.

**The accounting rule.** The aggregate is `1 - sum(after) / sum(before)` over the
two summed columns, and **both sums must come from the same layout row above**.
The reading above satisfies it by construction rather than by care: every arm is
taken in one child on one tree, so the fourth row is the "before" and the compact
arm measured beside it is the "after" — and the ordinary comparison, which
divides a third arm taken in that same child, satisfies it the same way. Restating the frozen sums as the "before"
of a current "after" would understate the reduction, because it charges the
compact arm for slots the arm it is compared against does not carry — 51.8%
becomes 51.0% on 3.14, which is the size of the error a reader cannot see. A
reading that departs from the rule anyway is not wrong for departing; it is wrong
for not saying which two readings it took.

## The frozen legacy reading

The reading taken in COR-111's Phase 2, over a tree carrying no publication
machinery at all — an instance of a declared class was a Pydantic model and
nothing more. It stands as recorded: it is the record of the tree it was taken
on, and re-freezing it over a tree COR-111 has already changed would hide
COR-111's own cost inside its own baseline. It is **not** the comparand for the
three-arm reading above, for the reason the accounting rule gives.

### CPython 3.14.7

| scenario | fields | slots | retained B | bare B | lifecycle B | build µs | read ns | dump µs | transient B |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| shallow | 4 | 6 | 784 | 560 | 224 | 2.58 | 26.8 | 0.57 | 592 |
| wide | 16 | 18 | 976 | 840 | 136 | 7.17 | 24.1 | 0.99 | 1,016 |
| nested | 5 | 7 | 2,832 | 2,696 | 136 | 8.72 | 26.7 | 1.54 | 2,528 |
| nullable | 10 | 12 | 976 | 840 | 136 | 4.91 | 22.9 | 0.73 | 992 |
| partial | 10 | 12 | 976 | 840 | 136 | 4.60 | 24.1 | 0.70 | 992 |
| polymorphic | 7 | 9 | 784 | 648 | 136 | 3.83 | 26.9 | 0.65 | 616 |
| **summed** | | | **7,328** | **6,424** | **904** | | | | |

### CPython 3.13.15

| scenario | fields | slots | retained B | bare B | lifecycle B | build µs | read ns | dump µs | transient B |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| shallow | 4 | 6 | 760 | 536 | 224 | 2.50 | 26.2 | 0.53 | 578 |
| wide | 16 | 18 | 952 | 816 | 136 | 7.60 | 22.1 | 1.01 | 1,040 |
| nested | 5 | 7 | 2,704 | 2,568 | 136 | 8.31 | 26.0 | 1.49 | 2,584 |
| nullable | 10 | 12 | 952 | 816 | 136 | 5.05 | 22.2 | 0.72 | 1,016 |
| partial | 10 | 12 | 952 | 816 | 136 | 4.87 | 23.2 | 0.74 | 1,016 |
| polymorphic | 7 | 9 | 760 | 624 | 136 | 3.87 | 23.5 | 0.63 | 640 |
| **summed** | | | **7,080** | **6,176** | **904** | | | | |

`slots` is the number of entries the node's instance storage held over the frozen
tree, which is the fields plus its one relationship slot plus its lifecycle entry.
It is the same figure the three-arm tables print as `cells` for the legacy arm,
which is one lower now that the lifecycle state rides a slot.

Its `build µs` column is **not** the `node µs` column above and cannot be
compared with it either. It is what one whole call of that arm cost, which for
the legacy fixture is a node and nothing else — so the two happen to agree there,
and they would not for any arm whose call does more than build its nodes. The
tables above split that quantity in two on purpose; `build µs` is the unsplit
one.

Its `transient B` column is **not** the column of the same name above, and cannot
be compared with it. It was read as the high-water mark less the total measured
the moment the construction returned, which for a node the collector has not yet
reached is the mark less most of the node — so it understates both what the
construction reached and what it freed again. The three-arm tables read the mark
against the collected floor the run started from and subtract what the node keeps.
There is no `peak B` column here for the same reason: the frozen reading never
recorded one, and one derived from a figure that means something else would not
be a reading of anything.

The `dump µs` column moved twice over COR-111 and by more than any other, because
the serialization seam changed shape: on this machine the six scenarios read
0.57 / 0.99 / 1.54 / 0.73 / 0.70 / 0.65 over the frozen tree, 0.91 / 2.03 / 3.83 /
1.35 / 1.36 / 1.19 over the tree that reached declared members through a
computed-field restatement, and 0.72 / 1.22 / 2.52 / 0.89 / 0.91 / 0.81 over the
presentation that replaced it. Timings are recorded for direction only, and this
one is direction: an ordinary value's serialization is materially cheaper than the
seam it replaced and still above the tree that had none.

## Against the ticket's directional figures

COR-111 records earlier directional evidence — roughly 472 bytes for a one-to-four
field object, 1,072 for eight fields, 1,776 for sixteen, and about 1.9 KB for a
nested Address + Geo + two Phone records, with an eight-field Entity estimated at
about 1,208 bytes before against 412 under the selected full-width bitmap design,
"about 66% saved". The readings here are lower and flatter for a stated reason:
they exclude decoded payload leaves, which the measurement contract requires and
which the earlier figures appear to have included. Read the earlier figures as
direction and these as the measured result. The measured aggregate is 51.8% where
the directional estimate was 66%, and the difference is the same exclusion: the
estimate's "before" carried payload the reading's does not, so the estimate divides
a larger denominator. Against the ordinary arm the measured figure is 56.2%,
which is nearer the estimate — some of that gap was the comparand rather than the
payload — and it is still the exclusion that accounts for most of what is left.

## What this reading surfaced

**Publication recorded no member presence at all on the tree the frozen tables
were taken over**, which is no longer true: a published node's bitmap records
exactly what its row carried, so `nullable` and `partial` are now distinguishable
where the frozen reading found them identical. What follows is the frozen tree's
fact, kept because it is what the frozen sums are a reading of. `nullable` and
`partial` differ only in which positions the row carried, and their published
nodes were physically identical in shape: the same storage keys, the same
declared-field count, and an empty `__pydantic_fields_set__` on both. Pydantic's
zero-argument `model_construct` fills every absent optional position with its
default, and `object.__setattr__` adds nothing to the field set, so
`exclude_unset` on a materialized node dropped everything and `full_row`'s
presence read saw an empty set. The compact representation's presence bitmap is
therefore new information rather than a re-encoding of information that backing
already held.

## Why the polymorphic scenario's timings were re-frozen

The frozen reading was first taken over a tree in which a subtype's Pydantic field
for an inherited member was built from the descriptor the declaring class
installs, so class access to that member — its query-authoring seed — was the
field's default. `model_construct()` deep-copied that seed once per inherited
member per node. The defect predates COR-111 and was repaired before any
representational change landed, because a reading taken over it would have
credited the representation with a construction cost the repair removes. The
frozen figures are the re-derived reading, taken over the repaired tree by
re-running the report: they did not drift, they were re-taken.

What the repair moved is the polymorphic scenario alone, and only its timing and
transient columns: build time from 82.5 µs to 3.8 on 3.14 and from 88.6 to 3.9 on
3.13, and transient allocation from ~6.1 KB to 616 B and from ~6.4 KB to 640 B.
Every retained-byte figure and both sums are unchanged on both interpreters,
which is the reading working as its subject requires: the polymorphic scenario
carries every position, so each deep copy was overwritten and discarded rather
than retained.

The consequence for the legacy-against-compact comparison is that there is none
left to make:
the polymorphic scenario's construction time is a property of the backing being
measured rather than partly a defect no longer being paid.
