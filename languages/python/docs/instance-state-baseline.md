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

Nothing here gates. `just python-report-instance-state` is a `report`: no number
it computes changes its exit code, because a total in bytes is machine- and
interpreter-relative — `tracemalloc` figures move with CPython, and every CI job
runs the floating `ubuntu-latest` label. What the report does compute is the two
verdicts the contract names, and it prints them as an escalation block so a
missed target is detected rather than noticed. The one thing it exits non-zero on
is completeness: a matrix cell with no reading is named and refused.

## The three arms

**The compact arm is production.** `EntityGraphConstruction.construct` itself —
one allocation, one positional member row and one relationship row across
`populate`'s door, one complete tuple attached once. There is no fixture to keep
in step with it.

**The ordinary arm is the validating constructor**, `cls(**members)`, with the
members the row carried passed by keyword and the absent ones left to their
declared defaults, and its occurrences built the same way. It stands for no
publication path and enters no aggregate. It is here because §2 states what a
published instance retains against an *ordinary* one, which is neither of the two
arms the aggregates divide, and because a claim about a comparison nobody
measured is a claim about nothing. Note that an ordinary node records the
presence a caller stated, where the legacy fixture recorded none — which is why
`partial`, the one scenario whose caller omits most members, retains *less*
ordinary than as a legacy fixture.

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
a published one does, and an Entity of any backing holds the lifecycle slot. See
*Four object layouts* below for why that sentence is load-bearing.

## The figures

Bytes reachable at the seam's innermost point while one node of that arm is held
that were not reachable before the window opened. `retained B` carries the node's
lifecycle state; `bare B` is the same node with none attached; `lifecycle B` is
their difference. `cells` is what the backing holds — for the two fixture arms
the entries of its instance storage, and for the compact arm the positions of its
one row, which is the presence bitmap plus every declared member plus every
declared relationship. `read ns` is per declared field read, averaged over every
field of the node. `peak B` is the high-water mark one construction reaches, read
against the collected floor it starts from, and `transient B` is what it
allocated and freed again on the way there — that mark less what the node keeps,
so neither column counts the node twice and neither leaves it out.

**Construction is two columns, because the arms' calls are not the same size.**
`node µs` is what one MORE node of that arm costs and `call µs` is what one call
costs besides the nodes it builds, separated by timing a one-node build against
an eleven-node one under each arm. The split is what makes construction
comparable at all: a compact node arrives from a `construct` call that also pays
a call scope, a writer, root validation and factory buffering, where a fixture
arm builds a node and nothing else — so `call µs` is about 1.4–1.9 µs under the
compact arm and indistinguishable from zero under the other two, and a per-call
figure would charge the compact arm for work no *node* costs. Every ratio below
is over `node µs`. Two reduction rows follow each scenario, each naming the arm
the compact one is divided into.

### CPython 3.14.7

| scenario | fields | arm | cells | retained B | bare B | lifecycle B | node µs | call µs | read ns | dump µs | transient B | peak B |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| shallow | 4 | ordinary | 4 | 720 | 584 | 136 | 1.22 | 0.23 | 28.9 | 0.77 | 1,000 | 1,720 |
| | | legacy | 5 | 720 | 584 | 136 | 2.74 | 0.20 | 26.5 | 0.75 | 602 | 1,322 |
| | | compact | 6 | 416 | 280 | 136 | 4.28 | 1.59 | 93.4 | 1.44 | 3,608 | 4,024 |
| | | **vs legacy** | | **42.2%** | **52.1%** | | | | | | | |
| | | *vs ordinary* | | *42.2%* | *52.1%* | | | | | | | |
| wide | 16 | ordinary | 16 | 1,512 | 1,376 | 136 | 2.14 | 0.24 | 25.0 | 1.15 | 2,152 | 3,664 |
| | | legacy | 17 | 1,000 | 864 | 136 | 7.53 | 0.19 | 24.8 | 1.23 | 784 | 1,784 |
| | | compact | 18 | 544 | 408 | 136 | 8.19 | 1.68 | 83.3 | 2.48 | 3,288 | 3,832 |
| | | **vs legacy** | | **45.6%** | **52.8%** | | | | | | | |
| | | *vs ordinary* | | *64.0%* | *70.3%* | | | | | | | |
| nested | 5 | ordinary | 5 | 3,344 | 3,208 | 136 | 5.75 | 0.20 | 26.6 | 2.60 | 1,536 | 4,880 |
| | | legacy | 6 | 2,920 | 2,784 | 136 | 9.56 | 0.26 | 26.9 | 2.56 | 2,264 | 5,184 |
| | | compact | 7 | 1,232 | 1,096 | 136 | 13.78 | 1.75 | 88.2 | 6.17 | 4,553 | 5,785 |
| | | **vs legacy** | | **57.8%** | **60.6%** | | | | | | | |
| | | *vs ordinary* | | *63.2%* | *65.8%* | | | | | | | |
| nullable | 10 | ordinary | 10 | 1,320 | 1,184 | 136 | 1.69 | 0.19 | 25.4 | 0.92 | 1,480 | 2,800 |
| | | legacy | 11 | 1,000 | 864 | 136 | 5.11 | 0.15 | 23.2 | 0.91 | 832 | 1,832 |
| | | compact | 12 | 496 | 360 | 136 | 4.61 | 1.49 | 79.2 | 1.83 | 3,288 | 3,784 |
| | | **vs legacy** | | **50.4%** | **58.3%** | | | | | | | |
| | | *vs ordinary* | | *62.4%* | *69.6%* | | | | | | | |
| partial | 10 | ordinary | 10 | 808 | 672 | 136 | 1.39 | 0.23 | 23.7 | 0.89 | 1,104 | 1,912 |
| | | legacy | 11 | 1,000 | 864 | 136 | 4.87 | 0.23 | 23.5 | 0.90 | 832 | 1,832 |
| | | compact | 12 | 464 | 328 | 136 | 3.66 | 1.52 | 78.7 | 1.82 | 3,344 | 3,808 |
| | | **vs legacy** | | **53.6%** | **62.0%** | | | | | | | |
| | | *vs ordinary* | | *42.6%* | *51.2%* | | | | | | | |
| polymorphic | 7 | ordinary | 7 | 1,320 | 1,184 | 136 | 1.51 | 0.17 | 26.7 | 0.83 | 1,432 | 2,752 |
| | | legacy | 8 | 808 | 672 | 136 | 4.06 | 0.18 | 26.4 | 0.86 | 624 | 1,432 |
| | | compact | 9 | 440 | 304 | 136 | 4.76 | 1.51 | 81.5 | 1.71 | 3,224 | 3,664 |
| | | **vs legacy** | | **45.5%** | **54.8%** | | | | | | | |
| | | *vs ordinary* | | *66.7%* | *74.3%* | | | | | | | |
| *warmed* | 4 | ordinary | 5 | 958 | 822 | 136 | 2.23 | 0.16 | 31.0 | 0.76 | 1,114 | 2,072 |
| | | legacy | 6 | 1,046 | 910 | 136 | 3.89 | 0.16 | 30.7 | 0.75 | 624 | 1,670 |
| | | compact | 6 | 838 | 702 | 136 | 6.45 | 1.76 | 89.7 | 1.79 | 3,370 | 4,208 |
| | | *vs legacy* | | *19.9%* | *22.9%* | | | | | | | |
| | | *vs ordinary* | | *12.5%* | *14.6%* | | | | | | | |

The representation change — the legacy arm divided into the compact one, which is
what the ticket's target is stated over:

| aggregate | before | after | reduction |
|---|---:|---:|---:|
| **primary** (lifecycle included) | 7,448 | 3,592 | **51.8%** |
| **secondary** (lifecycle excluded) | 6,632 | 2,776 | **58.1%** |

| operation, over the mix | ratio |
|---|---:|
| construction (per node) | 1.16x |
| attribute read | 3.33x |
| serialization | 2.14x |

Stated separately, in no aggregate — the ordinary arm divided into the compact
one, which is the comparison §2 states:

| comparison | ordinary | compact | |
|---|---:|---:|---:|
| published against ordinary (lifecycle included) | 9,024 | 3,592 | **60.2%** less |
| what a published node retains | | | **39.8%** of an ordinary one |

### CPython 3.13.15

| scenario | fields | arm | cells | retained B | bare B | lifecycle B | node µs | call µs | read ns | dump µs | transient B | peak B |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| shallow | 4 | ordinary | 4 | 696 | 560 | 136 | 1.19 | 0.21 | 25.6 | 0.72 | 912 | 1,608 |
| | | legacy | 5 | 696 | 560 | 136 | 2.67 | 0.18 | 25.8 | 0.70 | 506 | 1,202 |
| | | compact | 6 | 384 | 248 | 136 | 4.16 | 1.41 | 88.7 | 1.36 | 3,368 | 3,752 |
| | | **vs legacy** | | **44.8%** | **55.7%** | | | | | | | |
| | | *vs ordinary* | | *44.8%* | *55.7%* | | | | | | | |
| wide | 16 | ordinary | 16 | 1,488 | 1,352 | 136 | 2.15 | 0.23 | 23.2 | 1.12 | 2,064 | 3,552 |
| | | legacy | 17 | 976 | 840 | 136 | 7.85 | 0.11 | 23.8 | 1.15 | 688 | 1,664 |
| | | compact | 18 | 512 | 376 | 136 | 8.18 | 1.43 | 78.0 | 2.38 | 3,112 | 3,624 |
| | | **vs legacy** | | **47.5%** | **55.2%** | | | | | | | |
| | | *vs ordinary* | | *65.6%* | *72.2%* | | | | | | | |
| nested | 5 | ordinary | 5 | 3,216 | 3,080 | 136 | 5.55 | 0.23 | 25.4 | 2.38 | 1,336 | 4,552 |
| | | legacy | 6 | 2,792 | 2,656 | 136 | 9.05 | 0.19 | 25.6 | 2.39 | 2,168 | 4,960 |
| | | compact | 7 | 1,064 | 928 | 136 | 13.32 | 1.56 | 83.5 | 5.72 | 4,449 | 5,513 |
| | | **vs legacy** | | **61.9%** | **65.1%** | | | | | | | |
| | | *vs ordinary* | | *66.9%* | *69.9%* | | | | | | | |
| nullable | 10 | ordinary | 10 | 1,296 | 1,160 | 136 | 1.63 | 0.25 | 22.5 | 0.90 | 1,392 | 2,688 |
| | | legacy | 11 | 976 | 840 | 136 | 5.16 | 0.36 | 20.9 | 0.88 | 728 | 1,704 |
| | | compact | 12 | 464 | 328 | 136 | 4.64 | 1.39 | 78.3 | 1.82 | 3,112 | 3,576 |
| | | **vs legacy** | | **52.5%** | **61.0%** | | | | | | | |
| | | *vs ordinary* | | *64.2%* | *71.7%* | | | | | | | |
| partial | 10 | ordinary | 10 | 784 | 648 | 136 | 1.35 | 0.25 | 21.8 | 0.86 | 1,016 | 1,800 |
| | | legacy | 11 | 976 | 840 | 136 | 4.88 | 0.21 | 20.8 | 0.87 | 728 | 1,704 |
| | | compact | 12 | 432 | 296 | 136 | 3.58 | 1.36 | 76.0 | 1.78 | 3,232 | 3,664 |
| | | **vs legacy** | | **55.7%** | **64.8%** | | | | | | | |
| | | *vs ordinary* | | *44.9%* | *54.3%* | | | | | | | |
| polymorphic | 7 | ordinary | 7 | 1,296 | 1,160 | 136 | 1.47 | 0.20 | 21.9 | 0.80 | 1,344 | 2,640 |
| | | legacy | 8 | 784 | 648 | 136 | 4.02 | 0.22 | 22.9 | 0.81 | 520 | 1,304 |
| | | compact | 9 | 408 | 272 | 136 | 4.67 | 1.54 | 79.6 | 1.65 | 3,112 | 3,520 |
| | | **vs legacy** | | **48.0%** | **58.0%** | | | | | | | |
| | | *vs ordinary* | | *68.5%* | *76.6%* | | | | | | | |
| *warmed* | 4 | ordinary | 5 | 934 | 798 | 136 | 2.13 | 0.20 | 25.6 | 0.71 | 1,020 | 1,954 |
| | | legacy | 6 | 1,022 | 886 | 136 | 3.72 | 0.18 | 25.8 | 0.72 | 472 | 1,494 |
| | | compact | 6 | 806 | 670 | 136 | 6.20 | 1.70 | 87.2 | 1.70 | 3,130 | 3,936 |
| | | *vs legacy* | | *21.1%* | *24.4%* | | | | | | | |
| | | *vs ordinary* | | *13.7%* | *16.0%* | | | | | | | |

| aggregate | before | after | reduction |
|---|---:|---:|---:|
| **primary** (lifecycle included) | 7,200 | 3,264 | **54.7%** |
| **secondary** (lifecycle excluded) | 6,384 | 2,448 | **61.7%** |

| operation, over the mix | ratio |
|---|---:|
| construction (per node) | 1.15x |
| attribute read | 3.46x |
| serialization | 2.16x |

| comparison | ordinary | compact | |
|---|---:|---:|---:|
| published against ordinary (lifecycle included) | 8,776 | 3,264 | **62.8%** less |
| what a published node retains | | | **37.2%** of an ordinary one |

The aggregate is `1 - sum(after) / sum(before)` over the summed columns, **never
the mean of the per-scenario percentages**, which would weight a four-field node
like a nested one. Each scenario's own percentage is printed as a diagnostic and
enters no aggregate. The matrix is 3.14 and 3.13, derived from `requires-python`
rather than authored: the floor is the range's lower bound and the ceiling is the
interpreter taking the reading, which the support policy makes the latest
supported minor.

## What the escalation block said

Both rules the measurement contract names are computed by the report and printed,
so neither depends on a human noticing a number.

**The aggregate target is met on both runtimes.** The primary aggregate is 51.8%
on 3.14 and 54.7% on 3.13, against a 33% minimum; the secondary is 58.1% and
61.7%. No aggregate line appears in the block.

**Two representative operations moved past the 20% review threshold, on both
runtimes**, and the report names each with its worst scenario. The figures below
are one run's; across four runs the ratios move by a few percent while the byte
readings do not move at all, and neither of the two comes near the threshold from
either side:

| operation | 3.14 | 3.13 | what it is |
|---|---:|---:|---|
| serialization | 2.14x | 2.16x | already accepted as an Interface fact — see below |
| attribute read | 3.33x | 3.46x | a published node has no instance dictionary |

**Construction is not among them, and the threshold did not move.** It was
recorded here at 1.38x and 1.33x, and it is now 1.16x and 1.15x, because the
figure the report prints was corrected to measure what its label claims. The
earlier figure divided *one `construct` call* by *one fixture build*: the call
also pays a call scope, a writer, root validation and factory buffering — about
1.4–1.9 µs of work no node costs — which the fixture arms never pay, so the ratio
charged the compact arm for a difference in scope and reported it as a difference
in cost. The arms are now both timed at the one scope they share, the cost of one
more node, and at that scope the compact arm is 1.11–1.18x across four runs on
both runtimes — inside the 20% limit, and inside it by a narrow enough margin that
a future change could put it back out. Two of the six scenarios (`partial` and
`nullable`) are *faster* compact per node. The limit is 1.20x as it always was;
what changed is the measurement.

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
summed over the mix, **9,024 → 3,592 B on 3.14 and 8,776 → 3,264 B on 3.13** — a
published node retains **39.8%** and **37.2%** of an ordinary one, a 60.2% and
62.8% reduction. It runs slightly ahead of the legacy comparison because an
ordinary node records the presence its caller stated where the legacy fixture
recorded none, and it goes both ways per scenario: `partial`'s ordinary node is
808 B against the fixture's 1,000, so its reduction against ordinary is 42.6%
where its reduction against legacy is 53.6%. Neither figure enters the other's
aggregate, and every table above says which comparison it makes.

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
| Warm-up | 200 unsampled runs before every window |
| Timing samples | mean of 2,000 repetitions, taken with the line tracer uninstalled |
| Construction scope | a 1-node build against an 11-node one under each arm, split into the per-node cost and the per-call remainder |
| Repeatability | four independent whole-matrix runs returned byte-identical readings on both interpreters — every retained, bare, lifecycle, `cells`, transient and peak figure above is the same in all four, under all three arms; only the wall clock moved, and the escalation block's ratios with it — construction 1.11–1.18x, attribute read 3.27–3.46x, serialization 2.13–2.16x across the four |

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
object alone. It is a uniform 136 bytes on every scenario and every arm, because
the state rides a real slot on the `Entity` root under any backing and attaching
it therefore resizes nothing.

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
It is the same figure the two-arm tables print as `cells` for the legacy arm,
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
construction reached and what it freed again. The two-arm tables read the mark
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
a larger denominator. Against the ordinary arm the measured figure is 60.2%,
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

The consequence for the two-arm comparison is that there is none left to make:
the polymorphic scenario's construction time is a property of the backing being
measured rather than partly a defect no longer being paid.
