# Published instance state — the two-arm reading

What one published Typed Entity retains and costs under both backings, measured
on one machine under stated conditions, over COR-111's six canonical scenarios
and on every supported CPython minor. It is that ticket's measurement contract
discharged: retained bytes before and after per scenario, each scenario's own
percentage, the primary and secondary aggregates, construction, attribute-read
and serialization timings, transient allocation and peak memory — plus the
separate warmed scenario the contract requires beside the mix and outside every
aggregate.

Nothing here gates. `just python-report-instance-state` is a `report`: no number
it computes changes its exit code, because a total in bytes is machine- and
interpreter-relative — `tracemalloc` figures move with CPython, and every CI job
runs the floating `ubuntu-latest` label. What the report does compute is the two
verdicts the contract names, and it prints them as an escalation block so a
missed target is detected rather than noticed. The one thing it exits non-zero on
is completeness: a matrix cell with no reading is named and refused.

## The two arms

**The compact arm is production.** `EntityGraphConstruction.construct` itself —
one allocation, one positional member row and one relationship row across
`populate`'s door, one complete tuple attached once. There is no fixture to keep
in step with it.

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

**Both arms are read in one child, on one tree, over one object layout**, which
is what makes their ratio the representation's and not an accounting artifact.
Every framework slot a declared class carries is carried by both — an ordinary
value holds the compact and auxiliary pointers exactly as a published one does,
and an Entity of either backing holds the lifecycle slot. See *Four object
layouts* below for why that sentence is load-bearing.

## The figures

Bytes reachable at the seam's innermost point while one node of that arm is held
that were not reachable before the window opened. `retained B` carries the node's
lifecycle state; `bare B` is the same node with none attached; `lifecycle B` is
their difference. `cells` is what the backing holds — for the legacy arm the
entries of its instance storage, and for the compact arm the positions of its one
row, which is the presence bitmap plus every declared member plus every declared
relationship. `read ns` is per declared field read, averaged over every field of
the node. `peak B` is the high-water mark one construction reaches: the state the
node keeps plus what the construction allocated and freed on the way to it.

### CPython 3.14.7

| scenario | fields | arm | cells | retained B | bare B | lifecycle B | build µs | read ns | dump µs | transient B | peak B |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| shallow | 4 | legacy | 5 | 720 | 584 | 136 | 2.80 | 28.5 | 0.72 | 506 | 1,226 |
| | | compact | 6 | 416 | 280 | 136 | 5.50 | 92.1 | 1.43 | 2,056 | 2,472 |
| | | **reduction** | | **42.2%** | **52.1%** | | | | | | |
| wide | 16 | legacy | 17 | 1,000 | 864 | 136 | 7.56 | 25.8 | 1.22 | 968 | 1,968 |
| | | compact | 18 | 544 | 408 | 136 | 9.62 | 82.0 | 2.46 | 2,056 | 2,600 |
| | | **reduction** | | **45.6%** | **52.8%** | | | | | | |
| nested | 5 | legacy | 6 | 2,920 | 2,784 | 136 | 9.68 | 27.0 | 2.52 | 2,616 | 5,536 |
| | | compact | 7 | 1,232 | 1,096 | 136 | 15.03 | 85.6 | 6.02 | 3,057 | 4,289 |
| | | **reduction** | | **57.8%** | **60.6%** | | | | | | |
| nullable | 10 | legacy | 11 | 1,000 | 864 | 136 | 5.18 | 22.8 | 0.89 | 1,016 | 2,016 |
| | | compact | 12 | 496 | 360 | 136 | 5.90 | 77.5 | 1.83 | 2,056 | 2,552 |
| | | **reduction** | | **50.4%** | **58.3%** | | | | | | |
| partial | 10 | legacy | 11 | 1,000 | 864 | 136 | 4.93 | 24.3 | 0.91 | 1,016 | 2,016 |
| | | compact | 12 | 464 | 328 | 136 | 4.85 | 77.4 | 1.87 | 2,056 | 2,520 |
| | | **reduction** | | **53.6%** | **62.0%** | | | | | | |
| polymorphic | 7 | legacy | 8 | 808 | 672 | 136 | 3.94 | 25.1 | 0.81 | 616 | 1,424 |
| | | compact | 9 | 440 | 304 | 136 | 5.96 | 82.4 | 1.64 | 2,056 | 2,496 |
| | | **reduction** | | **45.5%** | **54.8%** | | | | | | |
| *warmed* | 4 | legacy | 6 | 1,046 | 910 | 136 | 3.83 | 28.3 | 0.76 | 670 | 1,716 |
| | | compact | 6 | 838 | 702 | 136 | 7.93 | 94.4 | 1.77 | 1,992 | 2,830 |
| | | *reduction* | | *19.9%* | *22.9%* | | | | | | |

| aggregate | before | after | reduction |
|---|---:|---:|---:|
| **primary** (lifecycle included) | 7,448 | 3,592 | **51.8%** |
| **secondary** (lifecycle excluded) | 6,632 | 2,776 | **58.1%** |

| operation, over the mix | ratio |
|---|---:|
| construction | 1.37x |
| attribute read | 3.24x |
| serialization | 2.16x |

### CPython 3.13.15

| scenario | fields | arm | cells | retained B | bare B | lifecycle B | build µs | read ns | dump µs | transient B | peak B |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| shallow | 4 | legacy | 5 | 696 | 560 | 136 | 2.72 | 26.2 | 0.71 | 538 | 1,234 |
| | | compact | 6 | 384 | 248 | 136 | 5.23 | 90.3 | 1.36 | 1,912 | 2,296 |
| | | **reduction** | | **44.8%** | **55.7%** | | | | | | |
| wide | 16 | legacy | 17 | 976 | 840 | 136 | 7.80 | 22.8 | 1.23 | 1,000 | 1,976 |
| | | compact | 18 | 512 | 376 | 136 | 9.32 | 80.9 | 2.47 | 1,944 | 2,456 |
| | | **reduction** | | **47.5%** | **55.2%** | | | | | | |
| nested | 5 | legacy | 6 | 2,792 | 2,656 | 136 | 9.14 | 26.1 | 2.40 | 2,672 | 5,464 |
| | | compact | 7 | 1,064 | 928 | 136 | 14.53 | 82.8 | 5.71 | 2,873 | 3,937 |
| | | **reduction** | | **61.9%** | **65.1%** | | | | | | |
| nullable | 10 | legacy | 11 | 976 | 840 | 136 | 5.34 | 21.6 | 0.87 | 1,040 | 2,016 |
| | | compact | 12 | 464 | 328 | 136 | 5.65 | 75.7 | 1.85 | 1,944 | 2,408 |
| | | **reduction** | | **52.5%** | **61.0%** | | | | | | |
| partial | 10 | legacy | 11 | 976 | 840 | 136 | 5.23 | 21.7 | 0.89 | 1,040 | 2,016 |
| | | compact | 12 | 432 | 296 | 136 | 4.61 | 78.2 | 1.81 | 1,912 | 2,344 |
| | | **reduction** | | **55.7%** | **64.8%** | | | | | | |
| polymorphic | 7 | legacy | 8 | 784 | 648 | 136 | 4.01 | 24.1 | 0.80 | 640 | 1,424 |
| | | compact | 9 | 408 | 272 | 136 | 5.79 | 80.1 | 1.62 | 1,912 | 2,320 |
| | | **reduction** | | **48.0%** | **58.0%** | | | | | | |
| *warmed* | 4 | legacy | 6 | 1,022 | 886 | 136 | 3.70 | 26.6 | 0.73 | 646 | 1,668 |
| | | compact | 6 | 806 | 670 | 136 | 7.47 | 91.3 | 1.74 | 1,856 | 2,662 |
| | | *reduction* | | *21.1%* | *24.4%* | | | | | | |

| aggregate | before | after | reduction |
|---|---:|---:|---:|
| **primary** (lifecycle included) | 7,200 | 3,264 | **54.7%** |
| **secondary** (lifecycle excluded) | 6,384 | 2,448 | **61.7%** |

| operation, over the mix | ratio |
|---|---:|
| construction | 1.32x |
| attribute read | 3.43x |
| serialization | 2.15x |

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

**Three representative operations moved past the 20% review threshold, on both
runtimes**, and the report names each with its worst scenario. The figures below
are one run's; across three runs the ratios move by up to three percent while the
byte readings do not move at all, and none of the three comes near the threshold
from either side:

| operation | 3.14 | 3.13 | what it is |
|---|---:|---:|---|
| serialization | 2.16x | 2.15x | already accepted as an Interface fact — see below |
| attribute read | 3.24x | 3.43x | a published node has no instance dictionary |
| construction | 1.37x | 1.32x | not like for like — see below |

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

**Construction is not a like-for-like comparison, and the report says so where it
prints the ratio.** Retained bytes and the read and dump timings are one node of
one backing, held or read the same way. The construction figures are not: the
legacy arm is the node-building the flip replaced, while the compact arm is the
whole `EntityGraphConstruction.construct` call — a call scope, a writer, root
validation and factory buffering. Measured directly, by comparing a one-node
graph against an eleven-node one, that scaffolding is **about 1 µs per call**,
which the legacy path paid too and the fixture standing for it does not. The
marginal per-node construction cost the same measurement gives is 3.57 / 7.55 /
13.04 µs for `shallow` / `wide` / `nested` against the legacy arm's 2.75 / 7.55 /
9.69 — 1.30x, 1.00x and 1.35x. So there is a real construction cost under the
scaffolding, roughly a third on the two scenarios that pay one, and the printed
ratio overstates it by pricing a call the fixture never made.

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
declaring none would understate both arms; one apiece keeps that cost uniform
across the mix and attributable to a single position.

`nullable` and `partial` share a class deliberately: presence is the only variable
between them, which is the distinction a compact bitmap has to preserve. On the
frozen tree they were physically identical (see *What this reading surfaced*);
they are not now, and their reductions differ by three points because the compact
arm records what the row carried.

**The `warmed` scenario is reported and excluded from both aggregates**, as the
measurement contract requires. A `PrivateAttr`'s value and a `cached_property`'s
result are state the author asked for; both live in ordinary per-instance storage
under either backing — the private mapping in its own slot, the memoized result
in the auxiliary slot for a published value and in the instance dictionary for an
ordinary one — so charging a representation change with them would credit or debit
it for something neither backing decides. It is held outside `SCENARIOS` rather
than flagged inside it, so no aggregate can pick it up by iterating the mix. Its
reduction is about 20%, which is the same node as `shallow` with roughly 400 bytes
of author-owned state added to both arms.

## Conditions

| | |
|---|---|
| Recorded | 2026-08-26 |
| Machine | Apple M5, 10 cores, 32 GiB, darwin/arm64 |
| OS | macOS 26.5.2 (build 25F84) |
| Interpreters | CPython 3.14.7 (the repository venv) and CPython 3.13.15, both Clang 21.0.0 |
| Pydantic | 2.13.4 / pydantic-core 2.46.4 on both |
| Command | `just python-report-instance-state` |
| Isolation | one fresh child interpreter per complete scenario, both arms inside that child |
| Warm-up | 200 unsampled runs before every window |
| Timing samples | mean of 2,000 repetitions, taken with the line tracer uninstalled |
| Repeatability | three independent whole-matrix runs returned byte-identical readings on both interpreters; only the wall clock moved, and the escalation block's ratios with it — construction 1.31–1.38x, attribute read 3.19–3.43x, serialization 2.12–2.17x across the three |

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
object alone. It is a uniform 136 bytes on every scenario and both arms, because
the state rides a real slot on the `Entity` root under either backing and
attaching it therefore resizes nothing.

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
| all three | **the current tree, and what the two-arm reading above took** | 7,448 | 6,632 |

`fields` and the scenario shapes are unchanged across all four. `cells` and the
sums are not, from the third row to the fourth, and both moved for one reason:
the lifecycle slot is the third pointer every Entity instance now carries, and
what a legacy arm attaches to it no longer lands in the storage mapping — so
each node's storage lost an entry while its layout gained a slot. `lifecycle B`
falls from 224/136 to a uniform 136 with it, because `shallow` no longer crosses
a dictionary growth boundary when its lifecycle state is attached.

**The accounting rule.** The aggregate is `1 - sum(after) / sum(before)` over the
two summed columns, and **both sums must come from the same layout row above**.
The reading above satisfies it by construction rather than by care: both arms are
taken in one child on one tree, so the fourth row is the "before" and the compact
arm measured beside it is the "after". Restating the frozen sums as the "before"
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
two-arm reading above, for the reason the accounting rule gives.

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
a larger denominator.

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
