# Published instance state — frozen legacy reading

What one published Typed Entity retains today, measured on one machine under
stated conditions, over COR-111's six canonical scenarios. It is the "before"
half of that ticket's measurement contract, taken while a legacy publication path
still exists to take it from.

Nothing here gates. `just python-report-instance-state` is a `report`: it passes
no verdict and belongs to no aggregate, because a total in bytes is machine- and
interpreter-relative — `tracemalloc` figures move with CPython, and every CI job
runs the floating `ubuntu-latest` label.

What *is* gated is the one thing that could go wrong silently. The arm measured
here is a **fixture** — `tests/unit/_instance_state_support.legacy_publication`,
which builds one node the way Entity Graph Construction builds one today — and a
fixture that has drifted still produces numbers. So the report compares every
scenario's fixture against the real publication path before it measures anything
and exits non-zero on any disagreement, and
`tests/unit/test_instance_state_baseline.py`, owned by `just python-test-dbfree`,
grades that comparison from both sides: nothing named over the shipping mix, and
the site named over each of three fixtures that stopped reproducing publication in
a different way.

That check has a stated life. It holds while a legacy publication path exists to
compare against; it runs one last time immediately before the flip that replaces
publication, and retires with it. After that the permanent comparison is the
two-arm one the same tool takes, which reproduces on any machine at any later
commit — where these totals in bytes are valid only for whoever took them.

## Why a fixture rather than the path itself

A materialized node is `cls.model_construct()` with **no arguments** followed by
one `object.__setattr__` per member, which leaves `__pydantic_fields_set__`
permanently empty. Ordinary keyword construction would get every value right and
that wrong, and the empty set is a large share of what a published node currently
retains — so the fixture reproduces the construction call rather than the result.
A Value Object is different and is reproduced differently:
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
| shallow | 4 | 6 | 784 | 560 | 224 | 2.49 | 28.4 | 0.57 | 592 |
| wide | 16 | 18 | 976 | 840 | 136 | 7.29 | 24.7 | 1.01 | 1,016 |
| nested | 5 | 7 | 2,832 | 2,696 | 136 | 8.56 | 26.4 | 1.52 | 2,528 |
| nullable | 10 | 12 | 976 | 840 | 136 | 4.87 | 23.7 | 0.71 | 992 |
| partial | 10 | 12 | 976 | 840 | 136 | 4.64 | 22.7 | 0.72 | 992 |
| polymorphic | 7 | 9 | 784 | 648 | 136 | 82.48 | 26.1 | 0.65 | 6,072 |
| **summed** | | | **7,328** | **6,424** | **904** | | | | |

### CPython 3.13.15

| scenario | fields | slots | retained B | bare B | lifecycle B | build µs | read ns | dump µs | transient B |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| shallow | 4 | 6 | 760 | 536 | 224 | 2.51 | 24.4 | 0.51 | 578 |
| wide | 16 | 18 | 952 | 816 | 136 | 7.59 | 22.4 | 1.00 | 1,040 |
| nested | 5 | 7 | 2,704 | 2,568 | 136 | 8.14 | 24.8 | 1.42 | 2,584 |
| nullable | 10 | 12 | 952 | 816 | 136 | 5.05 | 21.0 | 0.73 | 1,016 |
| partial | 10 | 12 | 952 | 816 | 136 | 4.78 | 23.6 | 0.73 | 1,016 |
| polymorphic | 7 | 9 | 760 | 624 | 136 | 88.56 | 23.4 | 0.62 | 6,368 |
| **summed** | | | **7,080** | **6,176** | **904** | | | | |

`fields` is the declared Pydantic field count; `slots` is the number of entries
the node's instance storage holds, which is the fields plus its one relationship
slot plus the lifecycle slot. `read ns` is per declared field read, averaged over
every field of the node. Timings are recorded for direction only.

The aggregate COR-111 accepts against is `1 - sum(after) / sum(before)` over the
two summed columns, never the mean of per-scenario percentages. The sums are
recorded here and the arithmetic is deliberately not performed: there is no
"after" yet.

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
| Repeatability | three independent processes returned byte-identical readings on 3.14; only the wall clock moved, by a few percent |

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

## Two facts this reading surfaced

Neither is repaired here — this reading exists to record the tree as it stands —
and both bear on how a later comparison is read.

**Publication records no member presence at all today.** `nullable` and `partial`
differ only in which positions the row carried, and their published nodes are
physically identical in shape: the same storage keys, the same declared-field
count, and an empty `__pydantic_fields_set__` on both. Pydantic's zero-argument
`model_construct` fills every absent optional position with its default, and
`object.__setattr__` adds nothing to the field set, so `exclude_unset` on a
materialized node drops everything and `full_row`'s presence read
(`_row_codec.py:110-125`) sees an empty set. The compact representation's presence
bitmap is therefore new information rather than a re-encoding of information the
current backing already holds.

**Every inherited member's Pydantic field default on a subtype is a live
`AttributeExpr`.** `_install_fields` rewrites only the members a class body
declares, and by the time Pydantic collects a subtype's inherited fields the base
class attribute has been replaced by the installed `Attr` descriptor — whose
`__get__(None, owner)` answers an `AttributeExpr`, which Pydantic records as the
field's default. Two consequences are visible here and one is not:

- `model_construct()` `smart_deepcopy`s that default once per inherited member per
  node, which is what puts the polymorphic scenario at 82–89 µs to build against
  2.5–8.6 µs for every other scenario, and its transient allocation at ~6 KB
  against ~0.6–2.6 KB.
- The reading itself is unaffected: the polymorphic scenario carries every
  position, so each deep copy is overwritten and discarded rather than retained.
- Not visible here, and outside this reading's subject: a published subtype whose
  row does **not** carry an inherited optional Attribute reads that member back as
  the `AttributeExpr` object rather than as `None`, and `model_dump()` emits it
  with a `PydanticSerializationUnexpectedValue` warning. Reproduced on this tree
  through the real publication path against the corpus's own `Cat`, whose
  inherited `owner_id` and `license_id` read back as `AttributeExpr` where its
  own-declared `indoor` reads `None`.

A later comparison must not read the polymorphic scenario's construction-time
improvement as a property of compact backing alone: a representation that builds
its defaults from the declaration rather than from Pydantic's collected field
defaults stops paying that deep copy as a side effect.
