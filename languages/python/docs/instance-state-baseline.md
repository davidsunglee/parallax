# Published instance state — frozen legacy reading

What one published Typed Entity retained before publication became compact,
measured on one machine under stated conditions, over COR-111's six canonical
scenarios. It is the "before" half of that ticket's measurement contract, taken
while a legacy publication path still existed to take it from.

Nothing here gates. `just python-report-instance-state` is a `report`: it passes
no verdict and belongs to no aggregate, because a total in bytes is machine- and
interpreter-relative — `tracemalloc` figures move with CPython, and every CI job
runs the floating `ubuntu-latest` label.

The arm measured here is a **fixture** —
`tests/unit/_instance_state_support.legacy_publication`, which builds one node the
way Entity Graph Construction built one then — and a fixture that has drifted
still produces numbers. So while that path existed the report compared every
scenario's fixture against it before measuring anything and exited non-zero on any
disagreement.

That check had a stated life. It held while a legacy publication path existed to
compare against; it ran one last time immediately before the flip that replaced
publication, and retired with it. `tests/unit/test_instance_state_baseline.py`,
owned by `just python-test-dbfree`, still grades what the report is asked for and
the mix the measurement contract names. The permanent comparison is now the
two-arm one the same tool will take, which reproduces on any machine at any later
commit — where these totals in bytes are valid only for whoever took them.

## Why a fixture rather than the path itself

A materialized node **was** `cls.model_construct()` with **no arguments**
followed by one `object.__setattr__` per member, which leaves
`__pydantic_fields_set__` permanently empty. Ordinary keyword construction would
get every value right and that wrong, and the empty set is a large share of what a
published node retained then — so the fixture reproduces the construction call
rather than the result. A Value Object was different and is reproduced
differently:
`vo_class.model_construct(present, **values)`, where `present` is exactly the
members the row carried.

## The figures

Bytes reachable at the seam's innermost point while one published node is held
that were not reachable before the window opened. `retained B` carries the node's
lifecycle state; `bare B` is the same node with none attached; `lifecycle B` is
their difference.

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

`fields` is the declared Pydantic field count; `slots` is the number of entries
the node's instance storage held over the frozen tree, which is the fields plus
its one relationship slot plus its lifecycle entry. `read ns` is per declared
field read, averaged over every field of the node. Timings are recorded for
direction only.

The aggregate COR-111 accepts against is `1 - sum(after) / sum(before)` over the
two summed columns, never the mean of per-scenario percentages, and over two
readings taken on the same object layout (*Four object layouts*, below — these
sums are the layout that carries no framework slots). The sums are recorded here
and the arithmetic is deliberately not performed: there is no "after" yet.

## What the scenarios are

| scenario | shape |
|---|---|
| shallow | 4 Attributes, 1 declared relationship left unloaded |
| wide | 16 Attributes, 1 declared relationship left unloaded |
| nested | 3 Attributes, a One occurrence carrying a nested One, and a Many of 2 |
| nullable | 10 Attributes, every one carried as an explicit null |
| partial | the same class as `nullable` — 3 Attributes carried, 7 absent |
| polymorphic | a 3-level Table-per-Hierarchy family, published as the concrete: 7 Attributes across three contributors |

Every root declares one self-referential broad relationship, left unloaded.
Publication writes **every** declared relationship slot on every node, so a mix
declaring none would understate both arms; one apiece keeps that cost uniform
across the mix and attributable to a single position.

`nullable` and `partial` share a class deliberately: presence is the only variable
between them, which is the distinction a compact bitmap has to preserve.

## Conditions

| | |
|---|---|
| Recorded | 2026-08-25 |
| Machine | Apple M5, 10 cores, 32 GiB, darwin/arm64 |
| OS | macOS 26.5.2 (build 25F84) |
| Interpreters | CPython 3.14.7 (the repository venv) and CPython 3.13.15, both Clang 21.0.0 |
| Pydantic | 2.13.4 / pydantic-core 2.46.4 on both |
| Command | `just python-report-instance-state` |
| Isolation | one fresh child interpreter per complete scenario, every arm inside that child |
| Warm-up | 200 unsampled runs before every window |
| Timing samples | mean of 2,000 repetitions, taken with the line tracer uninstalled |
| Repeatability | three independent processes on 3.14 and two on 3.13 returned byte-identical readings; only the wall clock moved, by a few percent |

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
its seam 200 times before opening its window, so a member layout, a class index,
a Value Object shape, and a construction's per-Entity facts are already in the
baseline the sample is compared against.

**The lifecycle state is not excluded, and is measured as a difference.** It is
built inside the window, so the reading that carries it counts it; `lifecycle B`
is the difference between the two readings rather than a measurement of the state
object alone, which is why `shallow` shows 224 where every other scenario shows
136. `shallow` is the one node whose storage crosses a dictionary growth boundary
when the lifecycle slot is added — five entries to six — so its lifecycle figure
carries the resize that attaching the state causes. That is the cost a reader
pays, recorded where a reader pays it.

## Against the ticket's directional figures

COR-111 records earlier directional evidence — roughly 472 bytes for a one-to-four
field object, 1,072 for eight fields, 1,776 for sixteen, and about 1.9 KB for a
nested Address + Geo + two Phone records. The readings here are lower and flatter
for a stated reason: they exclude decoded payload leaves, which the measurement
contract requires and which the earlier figures appear to have included. The
nested scenario is the closest match, at 2.8 KB with lifecycle against 1.9 KB
without it. Read the earlier figures as direction and these as the frozen
comparison basis.

## Four object layouts, and the rule for dividing them

This document carries figures from four different object layouts — the tree
before COR-111, the intermediate one the seam's first take produced, the one the
instance-state presentation added to it, and the current tree. Every summed number
below belongs to exactly one of them, and an aggregate that mixes them is wrong in
a way no reader can see from the number alone. So the layouts are named first and
the rule for using them is stated after.

The tables above are the **frozen reading**, taken over a tree carrying no
publication machinery at all — an instance of a declared class was a Pydantic
model and nothing more. They stand as recorded: they are the "before" the
aggregate divides into, and re-freezing them over a tree COR-111 has already
changed would hide COR-111's own cost inside its own baseline.

Re-running the report on the **current tree** prints higher retained bytes,
because the object in front of the storage grew. The framework root that both
kinds of declared class extend gained two slots, **8 bytes per instance each, on
both backings** — an ordinary value carries the two pointers exactly as a
published one does, which is why the legacy arm this report measures pays them
too:

| slot | what it holds | added with |
|---|---|---|
| `__parallax_compact__` | a published value's whole row, or `None` on an ordinary value | the compact representation |
| `__parallax_auxiliary__` | a published value's `cached_property` results, allocated on the first such write | the instance-state presentation that replaced the schema seam |
| `__parallax_lifecycle__` | a materialized Entity's opaque lifecycle state, on the Entity root alone | the publication flip, which leaves a published node no storage to hold it in |

| layout | tree | summed retained B, lifecycle included | excluded |
|---|---|---:|---:|
| no framework slots | the frozen tables above | 7,328 | 6,424 |
| `__parallax_compact__` only | the first take of the compact seam | 7,408 | 6,504 |
| both instance-state slots | the tree the presentation landed on | 7,488 | 6,584 |
| all three | the current tree, and what `just python-report-instance-state` prints today | 7,448 | 6,632 |

`fields` and the scenario shapes are unchanged across all four. `slots` and the
sums are not, from the third row to the fourth, and both moved for one reason:
the lifecycle slot is the third pointer every Entity instance now carries, and
what a legacy arm attaches to it no longer lands in the storage mapping — so
each node's storage lost an entry while its layout gained a slot. `lifecycle B`
falls from 224/136 to a uniform 136 with it, because `shallow` no longer crosses
a dictionary growth boundary when its lifecycle state is attached.

**The accounting rule.** The aggregate is `1 - sum(after) / sum(before)` over the
two summed columns, and **both sums must come from the same layout row above**.
An "after" measured on the current tree therefore divides the current tree's
legacy arm — 7,448 / 6,632 — and not the frozen 7,328 / 6,424. Restating the
frozen sums as the "before" of a current "after" understates the reduction,
because it charges the compact arm for slots the arm it is compared against does
not carry. A reading that departs from the rule anyway is not wrong for
departing; it is wrong for not saying which two readings it took.

The `dump µs` column moved the other way and by more, because the serialization
seam changed shape: on this machine the six scenarios read 0.57 / 0.99 / 1.54 /
0.73 / 0.70 / 0.65 over the frozen tree, 0.91 / 2.03 / 3.83 / 1.35 / 1.36 / 1.19
over the tree that reached declared members through a computed-field restatement,
and 0.74 / 1.19 / 2.55 / 0.88 / 0.92 / 0.81 over the presentation that replaced
it. Timings are recorded for direction only, and this one is direction: an
ordinary value's serialization is materially cheaper than the seam it replaced
and still above the tree that had none.

## What this reading surfaced

Not repaired here — this reading exists to record the tree as it stands — and it
bears on how a later comparison is read.

**Publication records no member presence at all on the tree these tables were
frozen over**, which is no longer true of the current tree: a published node's
bitmap records exactly what its row carried, so `nullable` and `partial` are now
distinguishable where the frozen reading found them identical. What follows is
the frozen tree's fact, kept because it is what the frozen sums are a reading of.
`nullable` and `partial` differ only in which positions the row carried, and their
published nodes were physically identical in shape: the same storage keys, the
same declared-field count, and an empty `__pydantic_fields_set__` on both.
Pydantic's zero-argument `model_construct` fills every absent optional position
with its default, and `object.__setattr__` adds nothing to the field set, so
`exclude_unset` on a materialized node dropped everything and `full_row`'s
presence read saw an empty set. The compact representation's presence bitmap is
therefore new information rather than a re-encoding of information that backing
already held.

## Why the polymorphic scenario's timings were re-frozen

This reading was first taken over a tree in which a subtype's Pydantic field for
an inherited member was built from the descriptor the declaring class installs,
so class access to that member — its query-authoring seed — was the field's
default. `model_construct()` deep-copied that seed once per inherited member per
node. The defect predates COR-111 and was repaired before any representational
change landed, because a reading taken over it would have credited the
representation with a construction cost the repair removes. The figures above are
the re-derived reading, taken over the repaired tree by re-running the report:
they did not drift, they were re-taken.

What the repair moved is the polymorphic scenario alone, and only its timing and
transient columns: build time from 82.5 µs to 3.8 on 3.14 and from 88.6 to 3.9 on
3.13, and transient allocation from ~6.1 KB to 616 B and from ~6.4 KB to 640 B.
Every retained-byte figure and both sums are unchanged on both interpreters,
which is the reading working as its subject requires: the polymorphic scenario
carries every position, so each deep copy was overwritten and discarded rather
than retained.

The consequence for a later comparison is that there is none left to make: the
polymorphic scenario's construction time is now a property of the backing being
measured rather than partly a defect no longer being paid.
