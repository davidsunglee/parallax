# Published instance state — the three-arm reading

What one published Typed Entity retains and costs under each backing, measured
on one machine under stated conditions, over COR-111's six canonical scenarios
and on every supported CPython minor. It is that ticket's measurement contract
discharged: retained bytes before and after per scenario, each scenario's own
percentage, the primary and secondary aggregates, construction, attribute-read
and serialization timings, transient allocation and peak memory — plus the
separate warmed scenario the contract requires beside the mix and outside every
aggregate.

**Two different comparisons are recorded here, and every figure says which it
makes.** The aggregates and the regression ratios divide the *legacy* arm into
the compact one: the representation change the ticket asked for, and the pair its
33% target is stated over. The *ordinary* arm — the validating constructor, what
a caller builds for themselves — enters neither, and answers the other question:
what a published node retains against one a caller made. That is the comparison
`spec/python.md` §2's Interface statement is made over, and this reading is what
measures it.

**Not every timing is like for like, and the one that is not is corrected by a
number the report derives.** Retained bytes and the two read timings compare one
node against one node under each arm. Construction does not: a compact node
arrives from a call that does per-node work the legacy fixture reproduces none of,
so the report measures that work as `outside µs` and prints the construction ratio
twice — once arm against arm, once with the difference added to the legacy side.
The second is the before and after, and it is the one the 20% rule grades.

Nothing here gates. `just python-report-instance-state` is a `report`: no number
it computes changes its exit code, because a total in bytes is machine- and
interpreter-relative — `tracemalloc` figures move with CPython, and every CI job
runs the floating `ubuntu-latest` label. What the report does compute is the two
comparisons the contract names, and it DISPLAYS them as an escalation block so a
missed target is read rather than noticed. Neither reaches the exit code — that is
what keeps a `report` non-blocking under `core/spec/language-testing.md` §2 — and
the one thing it exits non-zero on is completeness: a matrix cell with no reading
is named and refused, which says there is nothing here to read.

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
has none to attach. `cells` is what the backing holds — for the two fixture arms
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
a call scope, a writer, root validation and factory buffering, where a fixture
arm builds a node and nothing else — so `call µs` is about 1.3–2.0 µs under the
compact arm and indistinguishable from zero under the other two, and a per-call
figure would charge the compact arm for work no *node* costs.

`outside µs` is the third column, and it is what that split does **not** remove.
A `construct` call's populated check, root validation, per-node resolution view,
buffered attach and root tuple all scale with node count, so they stay inside the
compact arm's `node µs` — and the legacy fixture, which reproduces the node
*building* alone, pays none of them although the pre-flip path paid all of them
through the same call. The compact arm's call is therefore measured a second time
with its own build callback and state factory timed from inside them, and what is
left over is this column: **0.25–0.47 µs per node** across five whole-matrix runs
on both interpreters. It is exactly zero for the two fixture arms, whose call
*is* a loop over their node builder, and it is taken in a separate call so that no
clock runs inside the one `node µs` is measured over.

**So every ratio below is printed twice, and the 20% rule grades the right-hand
one.** *Arm against arm* divides the two `node µs` columns as each was timed.
*Like for like* adds the compact arm's `outside µs` to the legacy side, which is
what the pre-flip path paid; that is the before and after the rule is stated over.
For attribute read and serialization the two columns are equal by construction —
one call against one call on one node — which is what shows which operation needed
a correction rather than asserting it. Two reduction rows follow each scenario,
each naming the arm the compact one is divided into.

### CPython 3.14.7

| scenario | fields | arm | cells | retained B | bare B | lifecycle B | node µs | call µs | outside µs | read ns | dump µs | transient B | peak B |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| shallow | 4 | ordinary | 4 | 584 | 584 | 0 | 0.81 | 0.19 | 0.00 | 28.6 | 0.73 | 936 | 1,520 |
|  |  | legacy | 5 | 720 | 584 | 136 | 2.87 | 0.13 | 0.00 | 27.8 | 0.75 | 602 | 1,322 |
|  |  | compact | 6 | 416 | 280 | 136 | 4.33 | 1.54 | 0.27 | 106.4 | 1.47 | 3,608 | 4,024 |
| | | **vs legacy** | | **42.2%** | **52.1%** | | | | | | | | |
| | | *vs ordinary* | | *28.8%* | *52.1%* | | | | | | | | |
| wide | 16 | ordinary | 16 | 1,376 | 1,376 | 0 | 1.78 | 0.19 | 0.00 | 24.8 | 1.18 | 2,088 | 3,464 |
|  |  | legacy | 17 | 1,000 | 864 | 136 | 7.66 | 0.25 | 0.00 | 24.9 | 1.25 | 784 | 1,784 |
|  |  | compact | 18 | 544 | 408 | 136 | 8.26 | 1.80 | 0.29 | 84.3 | 2.51 | 3,288 | 3,832 |
| | | **vs legacy** | | **45.6%** | **52.8%** | | | | | | | | |
| | | *vs ordinary* | | *60.5%* | *70.3%* | | | | | | | | |
| nested | 5 | ordinary | 5 | 3,208 | 3,208 | 0 | 5.23 | 0.49 | 0.00 | 26.6 | 2.54 | 1,536 | 4,744 |
|  |  | legacy | 6 | 2,920 | 2,784 | 136 | 9.73 | 0.15 | 0.00 | 26.8 | 2.51 | 2,264 | 5,184 |
|  |  | compact | 7 | 1,232 | 1,096 | 136 | 13.71 | 1.95 | 0.26 | 86.9 | 5.98 | 4,553 | 5,785 |
| | | **vs legacy** | | **57.8%** | **60.6%** | | | | | | | | |
| | | *vs ordinary* | | *61.6%* | *65.8%* | | | | | | | | |
| nullable | 10 | ordinary | 10 | 1,184 | 1,184 | 0 | 1.24 | 0.25 | 0.00 | 23.4 | 0.91 | 1,416 | 2,600 |
|  |  | legacy | 11 | 1,000 | 864 | 136 | 5.26 | 0.12 | 0.00 | 23.8 | 0.91 | 832 | 1,832 |
|  |  | compact | 12 | 496 | 360 | 136 | 4.68 | 1.64 | 0.27 | 82.0 | 1.86 | 3,288 | 3,784 |
| | | **vs legacy** | | **50.4%** | **58.3%** | | | | | | | | |
| | | *vs ordinary* | | *58.1%* | *69.6%* | | | | | | | | |
| partial | 10 | ordinary | 10 | 672 | 672 | 0 | 0.98 | 0.20 | 0.00 | 25.9 | 0.89 | 1,040 | 1,712 |
|  |  | legacy | 11 | 1,000 | 864 | 136 | 5.02 | 0.12 | 0.00 | 26.4 | 0.89 | 832 | 1,832 |
|  |  | compact | 12 | 464 | 328 | 136 | 3.73 | 1.54 | 0.32 | 82.7 | 1.83 | 3,344 | 3,808 |
| | | **vs legacy** | | **53.6%** | **62.0%** | | | | | | | | |
| | | *vs ordinary* | | *31.0%* | *51.2%* | | | | | | | | |
| polymorphic | 7 | ordinary | 7 | 1,184 | 1,184 | 0 | 1.10 | 0.18 | 0.00 | 26.7 | 0.81 | 1,368 | 2,552 |
|  |  | legacy | 8 | 808 | 672 | 136 | 4.11 | 0.12 | 0.00 | 26.2 | 0.85 | 624 | 1,432 |
|  |  | compact | 9 | 440 | 304 | 136 | 4.81 | 1.51 | 0.34 | 85.5 | 1.66 | 3,224 | 3,664 |
| | | **vs legacy** | | **45.5%** | **54.8%** | | | | | | | | |
| | | *vs ordinary* | | *62.8%* | *74.3%* | | | | | | | | |
| *warmed* | 4 | ordinary | 5 | 822 | 822 | 0 | 1.77 | 0.24 | 0.00 | 29.3 | 0.77 | 1,050 | 1,872 |
|  |  | legacy | 6 | 1,046 | 910 | 136 | 4.02 | 0.06 | 0.00 | 29.1 | 0.78 | 624 | 1,670 |
|  |  | compact | 6 | 838 | 702 | 136 | 6.59 | 1.87 | 0.40 | 90.4 | 1.85 | 3,370 | 4,208 |
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
| construction (per node) | 1.14x | **1.09x** |
| attribute read | 3.39x | **3.39x** |
| serialization | 2.14x | **2.14x** |

Stated separately, in no aggregate — the ordinary arm divided into the compact
one, which is the comparison §2 states:

| comparison | ordinary | compact | |
|---|---:|---:|---:|
| published against ordinary (lifecycle where each holds it) | 8,208 | 3,592 | **56.2%** less |
| what a published node retains | | | **43.8%** of an ordinary one |

| operation, over the mix | ratio |
|---|---:|
| construction (per node) | 3.55x |
| attribute read | 3.39x |
| serialization | 2.17x |

### CPython 3.13.15

| scenario | fields | arm | cells | retained B | bare B | lifecycle B | node µs | call µs | outside µs | read ns | dump µs | transient B | peak B |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| shallow | 4 | ordinary | 4 | 560 | 560 | 0 | 0.80 | 0.22 | 0.00 | 26.1 | 0.72 | 856 | 1,416 |
|  |  | legacy | 5 | 696 | 560 | 136 | 2.71 | 0.20 | 0.00 | 26.2 | 0.70 | 506 | 1,202 |
|  |  | compact | 6 | 384 | 248 | 136 | 4.14 | 1.51 | 0.28 | 88.4 | 1.36 | 3,368 | 3,752 |
| | | **vs legacy** | | **44.8%** | **55.7%** | | | | | | | | |
| | | *vs ordinary* | | *31.4%* | *55.7%* | | | | | | | | |
| wide | 16 | ordinary | 16 | 1,352 | 1,352 | 0 | 1.70 | 0.22 | 0.00 | 22.4 | 1.12 | 2,008 | 3,360 |
|  |  | legacy | 17 | 976 | 840 | 136 | 7.81 | 0.19 | 0.00 | 22.3 | 1.20 | 688 | 1,664 |
|  |  | compact | 18 | 512 | 376 | 136 | 8.20 | 1.50 | 0.29 | 81.6 | 2.39 | 3,112 | 3,624 |
| | | **vs legacy** | | **47.5%** | **55.2%** | | | | | | | | |
| | | *vs ordinary* | | *62.1%* | *72.2%* | | | | | | | | |
| nested | 5 | ordinary | 5 | 3,080 | 3,080 | 0 | 5.02 | 0.26 | 0.00 | 26.8 | 2.41 | 1,336 | 4,416 |
|  |  | legacy | 6 | 2,792 | 2,656 | 136 | 9.16 | 0.21 | 0.00 | 24.2 | 2.45 | 2,168 | 4,960 |
|  |  | compact | 7 | 1,064 | 928 | 136 | 13.26 | 1.80 | 0.29 | 85.4 | 5.80 | 4,449 | 5,513 |
| | | **vs legacy** | | **61.9%** | **65.1%** | | | | | | | | |
| | | *vs ordinary* | | *65.5%* | *69.9%* | | | | | | | | |
| nullable | 10 | ordinary | 10 | 1,160 | 1,160 | 0 | 1.20 | 0.24 | 0.00 | 24.1 | 0.93 | 1,336 | 2,496 |
|  |  | legacy | 11 | 976 | 840 | 136 | 5.32 | 0.22 | 0.00 | 22.5 | 0.92 | 728 | 1,704 |
|  |  | compact | 12 | 464 | 328 | 136 | 4.60 | 1.44 | 0.27 | 77.5 | 1.83 | 3,112 | 3,576 |
| | | **vs legacy** | | **52.5%** | **61.0%** | | | | | | | | |
| | | *vs ordinary* | | *60.0%* | *71.7%* | | | | | | | | |
| partial | 10 | ordinary | 10 | 648 | 648 | 0 | 0.97 | 0.19 | 0.00 | 22.1 | 0.87 | 960 | 1,608 |
|  |  | legacy | 11 | 976 | 840 | 136 | 4.89 | 0.26 | 0.00 | 20.7 | 0.86 | 728 | 1,704 |
|  |  | compact | 12 | 432 | 296 | 136 | 3.64 | 1.32 | 0.36 | 74.8 | 1.79 | 3,232 | 3,664 |
| | | **vs legacy** | | **55.7%** | **64.8%** | | | | | | | | |
| | | *vs ordinary* | | *33.3%* | *54.3%* | | | | | | | | |
| polymorphic | 7 | ordinary | 7 | 1,160 | 1,160 | 0 | 1.04 | 0.23 | 0.00 | 23.3 | 0.79 | 1,288 | 2,448 |
|  |  | legacy | 8 | 784 | 648 | 136 | 4.07 | 0.17 | 0.00 | 22.9 | 0.80 | 520 | 1,304 |
|  |  | compact | 9 | 408 | 272 | 136 | 4.69 | 1.56 | 0.25 | 87.7 | 1.66 | 3,112 | 3,520 |
| | | **vs legacy** | | **48.0%** | **58.0%** | | | | | | | | |
| | | *vs ordinary* | | *64.8%* | *76.6%* | | | | | | | | |
| *warmed* | 4 | ordinary | 5 | 798 | 798 | 0 | 1.67 | 0.23 | 0.00 | 25.9 | 0.72 | 964 | 1,762 |
|  |  | legacy | 6 | 1,022 | 886 | 136 | 3.72 | 0.14 | 0.00 | 26.2 | 0.74 | 472 | 1,494 |
|  |  | compact | 6 | 806 | 670 | 136 | 6.27 | 1.63 | 0.28 | 91.9 | 1.71 | 3,130 | 3,936 |
| | | *vs legacy* | | *21.1%* | *24.4%* | | | | | | | | |
| | | *vs ordinary* | | *-1.0%* | *16.0%* | | | | | | | | |

| aggregate | before | after | reduction |
|---|---:|---:|---:|
| **primary** (lifecycle included) | 7,200 | 3,264 | **54.7%** |
| **secondary** (lifecycle excluded) | 6,384 | 2,448 | **61.7%** |

| operation, over the mix | arm against arm | like for like |
|---|---:|---:|
| construction (per node) | 1.13x | **1.08x** |
| attribute read | 3.57x | **3.57x** |
| serialization | 2.14x | **2.14x** |

| comparison | ordinary | compact | |
|---|---:|---:|---:|
| published against ordinary (lifecycle where each holds it) | 7,960 | 3,264 | **59.0%** less |
| what a published node retains | | | **41.0%** of an ordinary one |

| operation, over the mix | ratio |
|---|---:|
| construction (per node) | 3.59x |
| attribute read | 3.42x |
| serialization | 2.17x |

The aggregate is `1 - sum(after) / sum(before)` over the summed columns, **never
the mean of the per-scenario percentages**, which would weight a four-field node
like a nested one. Each scenario's own percentage is printed as a diagnostic and
enters no aggregate. The matrix is 3.14 and 3.13, derived from `requires-python`
and the support policy rather than authored: the declared floor is the range's
lower bound and "the latest minor + one prior minor" fixes its width above it.
Which interpreter takes the reading decides nothing — closing the range at
`sys.version_info` instead would silently drop the top row whenever the report
ran on anything but the latest minor.

## What the escalation block said

Both rules the measurement contract names are computed by the report and printed,
so neither depends on a human noticing a number.

**The aggregate target is met on both runtimes.** The primary aggregate is 51.8%
on 3.14 and 54.7% on 3.13, against a 33% minimum; the secondary is 58.1% and
61.7%. No aggregate line appears in the block.

**Two representative operations moved past the 20% review threshold, on both
runtimes**, and the report names each with its worst scenario. The rule grades the
*like-for-like* column, and for these two that column is the arm-against-arm one:
a member read and a `model_dump()` are one call against one call on one node, so
there is no scope to correct. The figures below
are one run's; across five runs the ratios move by a few percent while the byte
readings do not move at all, and neither of the two comes near the threshold from
either side:

| operation | 3.14 | 3.13 | what it is |
|---|---:|---:|---|
| serialization | 2.14x | 2.14x | already accepted as an Interface fact — see below |
| attribute read | 3.39x | 3.57x | a published node has no instance dictionary |

**Construction is not among them, and the 1.20x limit is the one it always was.**
The figure was recorded here at 1.38x and 1.33x before either correction, and the
limit never moved: what changed both times is the measurement. Correcting the
*call* scope came first — the earlier figure divided one whole `construct` call by
one fixture build, charging the compact arm for a call scope, a writer, root
validation and factory buffering that no node costs — and both arms are now timed
per node, which brought the arm-against-arm figure to **1.13–1.15x** across the
five runs recorded here. Two of the six scenarios (`partial` and `nullable`) are
*faster* compact per node.

**Correcting the per-node scope came second, and it is now the report's own
arithmetic rather than a note beside it.** The per-node split cancels a `construct`
call's *fixed* cost and not its per-node one: the populated check, root validation,
a resolution view per node, the buffered attach and the root tuple all scale with
node count, so they stay inside the compact arm's `node µs`. The pre-flip path paid
that work through the same call — that half of `EntityGraphConstruction` is
unchanged either side of the flip — but the legacy arm is a fixture of the node
*building* alone and pays none of it. The report measures the difference as
`outside µs` and prints a second ratio with it added to the legacy side:
**like for like, construction is 1.09x on 3.14 and 1.08x on 3.13**, and that is the
figure the 20% rule grades. Both columns are printed, so the correction is visible
rather than asserted.

**What each of the two columns is still biased by, and by how much.** The
arm-against-arm column carries the whole `outside µs` against the compact arm —
0.25–0.47 µs per node, about five points of ratio. The like-for-like column
carries one quantity the *other* way: the per-node lifecycle attach, a single slot
write of about 0.07 µs, happens in `construct`'s own loop rather than in a callback
the arm can time, so it stays in `outside µs` although the fixture pays one too and
lands on the legacy side twice — worth about one point. The construction cost the
flip actually paid is therefore between the two printed columns and near the
right-hand one: about **1.10x on 3.14 and 1.09x on 3.13**. An earlier hand
measurement of the same residue put it at 0.23 µs per node and the ratio at 1.12x;
net of the attach the report measures 0.18–0.40 µs, so the two agree on the residue
and differ on the ratio by the arm-against-arm figure's own run-to-run movement.

**The ordinary construction ratio needs no correction and gets none, and is 3.55x
and 3.59x.** A
caller building an ordinary instance pays no construction call at all, so what
that ratio compares is what each side actually costs: publishing one node is
about three and a half times the cost of validating one. It is not a regression
from anything — publication has always paid a call the constructor does not — and
no ordinary ratio can reach the escalation block, which grades the representation
change alone.

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
| Callback scope | the compact call measured a second time with its own build callback and state factory timed from inside them, which is what `outside µs` is the remainder of |
| Repeatability | five independent whole-matrix runs returned byte-identical readings on both interpreters — every retained, bare, lifecycle, `cells`, transient and peak figure above is the same in all five, under all three arms; only the wall clock moved, and the ratios with it — against the legacy arm, construction 1.13–1.15x arm against arm and 1.07–1.09x like for like, attribute read 3.22–3.57x, serialization 2.12–2.22x; against the ordinary arm, construction 3.52–3.59x, attribute read 3.08–3.48x, serialization 2.09–2.21x; `outside µs` 0.25–0.47 per node |
| Elapsed | about 12.5 s for the whole matrix, of which roughly 2.5 s is the compact arm's callback timing |

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
