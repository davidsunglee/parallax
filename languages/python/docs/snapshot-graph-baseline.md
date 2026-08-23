# Snapshot graph retained overhead — recorded baseline

What one materialized Snapshot graph keeps, measured on one machine under stated
conditions, on both sides of the representation cutover that replaced the
per-cell carrier graph with sealed, index-addressed compact rows. COR-108 asks
for "at least 60% lower retained carrier bytes per projection than the frozen
baseline". This is the reading that answers it.

Nothing here gates. `just python-report-snapshot-graph-overhead` is a `report`:
it passes no verdict and belongs to no aggregate, because a total in bytes is
machine- and interpreter-relative — `tracemalloc` figures move with CPython, and
every CI job runs the floating `ubuntu-latest` label, so a tight ratio can flip
on an interpreter bump that changed nothing. The *shape* of what a graph retains
is gated instead, in `tests/unit/test_snapshot_graph_retention.py`, which
`just python-test-dbfree` owns: that suite fits an affine function of members,
declared view slots, and recorded edges over a crossed grid and requires exact
equality at every point of it, grades each of the three steps against the exact
number of pointers a compact row can charge, and asserts that no object of
Parallax's own survives a conforming materialization except the sealed graph's
own structures. A per-cell carrier reappearing fails there, structurally, without
anyone re-taking this reading.

## The figure

| | before | after | change |
|---|---:|---:|---:|
| **Retained bytes per projection** | **4,721.8** | **1,104.2** | **−76.6%** |
| Retained bytes, whole representative graph | 2,115,368 | 494,684 | −76.6% |
| Tracked survivor objects per projection | 63.89 | 4.00 | −93.7% |
| Of which per-cell carriers | 43.28 | **0** | — |
| Build (convert, write, seal), 448 projections | 33.56 ms | 19.99 ms | −40.4% |
| Merge, 448 projections | 5.17 ms | 0.48 ms | −90.7% |

COR-108's ≥60% criterion implies a ceiling of **1,888.7 retained bytes per
projection**. The reading is 1,104.2, which clears it with 42% to spare. The
reduction is above 60% at every point of the size grid below, not only at the one
the headline is taken at.

The companion absolute claim — "zero retained per-cell Snapshot carrier objects
on the conforming path" — is met exactly. The pre-cutover census itemized 43.28
per-cell carriers per projection across four types; none of those types exists,
and the survivor census after the cutover names no Parallax type at all whose
count grows with the graph.

## Conditions

Both readings were taken on the same machine, the same OS build, and the same
interpreter. That is what makes the ratio a measurement of this change rather
than of an interpreter.

| | |
|---|---|
| Recorded | 2026-08-22, both halves within two days of each other |
| Machine | Apple M5, 10 cores, 32 GiB, darwin/arm64 |
| OS | macOS 26.5.2 (build 25F84) |
| Interpreter | CPython 3.12.13 (main, Mar 10 2026) [Clang 21.1.4] |
| Command (after) | `just python-report-snapshot-graph-overhead` |
| Source (before) | base commit `31c5c67e`, in a throwaway worktree |
| Warm-up | 200 unsampled runs before every window |
| Timing samples | mean of 50 build-and-merge repetitions |
| Repeatability | two independent processes returned byte-identical readings on both sides |

The "before" half cannot be re-run against this tree: the representation it
measured — `SnapshotNodeInput`, `SnapshotNodeRef`,
`SnapshotRelationshipViewInput`, `MergedNode`, `MergedRelationshipView` — was
deleted by the same cutover this records. It is transcribed here because a
figure whose other half is unreachable belongs beside the half that is.

## What is measured, and what is excluded

The reading is bytes reachable at the seam's innermost point, while the sealed
graph and its `GraphMerge` are both held, that were not reachable before the
window opened.

**The builder is not held.** It is transient in production — the read executor
lets its scope die at `seal()` — so a reading that kept one would measure
something no read retains. The pre-cutover reading dropped its `MergeScope` for
the same reason.

**Decoded payload leaves are excluded structurally, not by filtering.** Every
column value and every Value Object document is allocated at import time, outside
every window, so a row that merely references one of them costs the reading the
position and not the leaf. The report demonstrates this rather than asserting it:
the identical graph shape with every string leaf padded by 512 characters — an
order of magnitude more payload — reads

```text
lean = 64,936 B   fat = 64,936 B   delta = +0 B (+0.00%)
```

Exactly zero, on both sides of the cutover.

**The shared exact-model catalog is excluded the same way.** The Domain Model,
its accepted Metamodel, and its layout catalog are built before any window opens
and the warm-up passes fill every first-reach memo underneath them. That the
catalog does not grow with the graphs materialized against it is a separate,
gated reading, in the retention suite.

## The size grid

Four graph sizes over an eightfold span, so a fixed cost cannot hide inside a
per-projection one.

| cells | projections | before, B | before, B/proj | after, B | after, B/proj | reduction |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | 56 | 264,728 | 4,727.3 | 64,936 | 1,159.6 | −75.5% |
| 16 | 112 | 528,320 | 4,717.1 | 125,232 | 1,118.1 | −76.3% |
| 32 | 224 | 1,054,776 | 4,708.8 | 245,288 | 1,095.0 | −76.7% |
| 64 | 448 | 2,115,368 | 4,721.8 | 494,684 | 1,104.2 | −76.6% |

Least squares over the grid: **4,721.40 bytes per projection with −695 fixed**
before, **1,096.89 with 2,187 fixed** after. The fixed term after the cutover is
3.4% of the smallest reading and 0.4% of the largest — larger as a share than
before only because the per-projection total it sits beside is four times
smaller. The headline is taken at the 64-cell point on both sides.

### Where the bytes sit

| | before | before B/proj | after | after B/proj |
| --- | ---: | ---: | ---: | ---: |
| The graph alone (merge dropped before the sample) | 1,418,676 | 3,166.7 | 433,992 | 968.7 |
| The merge's own retained state | 696,692 | 1,555.1 | 60,692 | 135.5 |
| **Total** | **2,115,368** | **4,721.8** | **494,684** | **1,104.2** |

The merge's own share falls by 91%: the dictionary-heavy `MergedNode` layer is
gone, and what merging retains is the logical-node-to-allocation mapping, the
projection-to-allocation mapping, the allocation order, the winning projection
per logical node, one fixed view row per logical node, and the accumulated
issues.

### The survivor census

Tracked survivors at the sample point over the representative graph, warmed.
"marginal" is what one more projection costs, with any fixed term removed.

Before:

| type | count | per proj | marginal | per-cell carrier? |
| --- | ---: | ---: | ---: | --- |
| `tuple` | 8,002 | 17.86 | 17.86 | structural |
| `EntityAttributeInput` | 7,872 | 17.57 | 17.57 | **yes** |
| `ValueObjectRecord` | 3,840 | 8.57 | 8.57 | **yes** |
| `ValueObjectAttributeInput` | 3,840 | 8.57 | 8.57 | **yes** |
| `ValueObjectOccurrenceInput` | 3,072 | 6.86 | 6.86 | **yes** |
| `dict` | 770 | 1.72 | 1.71 | merge winner tables |
| `SnapshotNodeInput` | 448 | 1.00 | 1.00 | one per projection |
| `SnapshotNodeRef` | 448 | 1.00 | 1.00 | **yes** |
| `SnapshotRelationshipViewInput` | 320 | 0.71 | 0.71 | **yes** |
| `list` | 7 | 0.02 | 0.00 | fixed |
| `SnapshotGraphInput`, `GraphMerge` | 2 | — | — | the graph and its merge |
| **total** | **28,621** | **63.89** | | |

After:

| type | count | per proj | marginal | what it is |
| --- | ---: | ---: | ---: | --- |
| `tuple` | 1,761 | 3.93 | 3.61 | structural |
| `dict` | 9 | 0.02 | 0.00 | the schema's three memos and the layouts' own maps |
| `mappingproxy` | 6 | 0.01 | 0.00 | the same maps, published |
| `list` | 5 | 0.01 | 0.00 | the merge's own arrays |
| `MergedViewLayout` | 3 | 0.01 | 0.00 | one per resolved concrete Entity |
| `SourceViewLayout` | 3 | 0.01 | 0.00 | interned per admitted slot tuple |
| `SnapshotGraph`, `GraphRows`, `GraphMerge`, `ViewSchema` | 4 | — | — | the graph, its arrays, its merge, the execution's schema |
| **total** | **1,791** | **4.00** | | |

Not one type after the cutover has a marginal cost per projection above zero
except `tuple`, and every `tuple` in that count is a member row, a view row, or a
to-many arm — a position rather than a wrapper. Four of the five per-cell carrier
types are gone from the tree entirely.

The tracked-tuple count is the one figure that is not flat per projection across
the grid (6.71 at 8 cells against 3.93 at 64). That is the collector rather than
the representation: a tuple holding only untracked items is untracked itself when
a collection reaches it, and how many rows have been reached depends on when the
automatic collections landed. The byte reading is what sees all of them, which is
why it is the headline and why the gated suite is stated in bytes.

## The workload

Bespoke, declared inline in `tools/snapshot_graph_overhead.py`, because no model
in the tree carries all six traits COR-108's representative graph names at the
width it names them: the compatibility corpus tops out at eight applicable
Attributes on one Entity, and no document there combines wide scalars with nested
Value Objects, an inheritance family, and relationship fan-out.

| Requirement | Where the workload carries it |
| --- | --- |
| about 20 scalar members | `Alpha` and `Beta` each resolve to exactly 20 applicable Attributes |
| nested One and Many Value Objects | `Tag` has a nested One (`detail`) and a nested Many (`details`); the Entity carries a top-level One (`primary_tag`) and a top-level Many (`tags`) |
| polymorphic projections | table-per-hierarchy `Node` → `Special` → `Alpha` and `Node` → `Beta`; every cell projects both concretes |
| three view slots | on each `Owner`: broad to-many `nodes`, narrowed to-many `special[Alpha]`, to-one `favorite` |
| duplicate logical nodes | the two `Alpha` rows of each cell are converted twice, so 448 projections collapse to 320 logical nodes |
| relationship fan-out | `nodes` holds 4 references, `special[Alpha]` holds 2, `favorite` holds 1, per cell |

Plus a back-reference `owner` view on each duplicate projection, so merging's
view union across duplicate projections is exercised rather than assumed.

```text
Owner  (3 Attributes, 0 Value Objects)                      1 projection
  |-- nodes           -> (child0, child1, child2, child3)   view slot 1, fan-out 4
  |-- special[Alpha]  -> (dup0, dup1)                        view slot 2, fan-out 2
  '-- favorite        -> child0                              view slot 3, to-one

child0, child1 : Alpha  (20 Attributes, 2 VO occurrences)   2 projections
child2, child3 : Beta   (20 Attributes, 2 VO occurrences)   2 projections
dup0, dup1     : Alpha  — the SAME rows as child0, child1   2 projections
  '-- owner -> Owner                                         1 view slot each
```

At 64 cells: **448 projections, 320 logical nodes, 320 written view slots, 64
roots**, one graph, one merge, and `merge.has_issues` false — the conforming path
COR-108's absolute claims are stated over. Every one of those counts is asserted
before any window opens.

The view schema is the full `ViewSchema(slot_table)` form a guarded plan derives,
dense by source level: the root level's parents receive the three views their own
levels attach, and the one level below them receives the back reference. Reaching
for `ViewSchema.of(...)` instead would put every slot on one unguarded level and
give each owner a row it can never fill, inflating the reading against a shape no
execution produces.

### The two drives are the same drive

Only the names moved between the two readings. Both convert every row through the
production converter, write every view as its level lands, seal, and merge.

| before | after |
| --- | --- |
| `MergeScope(META)` | `GraphBuilder(ViewSchema(slot_table))` |
| `LevelContext(identity, documents)` | `LevelContext(layout, documents)` |
| `convert_row(row, level, scope)` | `convert_row(row, level, builder, source=level)` |
| `scope.attach(ref, view, value)` | `builder.write_view(projection, view, value)` |
| `scope.build(roots, pin)` | `builder.seal(roots, pin)` |
| `merge_graph_input(graph, META)` | `merge_graph_input(graph)` |
| `SnapshotNodeRef(i)` | the built-in `int` `i` |

## Rerunning it

```sh
just python-report-snapshot-graph-overhead
```

It takes about ninety seconds and prints the grid, the headline against the
recorded pre-cutover figure, the wall clock, the survivor census, and the
payload-leaf control. Comparing against the tables above needs the same
conditions — the same machine class, the same interpreter, no competing load —
because the absolute numbers are machine-relative even where the ratios are not.
A reading taken on a different CPython is a reading of that CPython as much as of
this representation, and the honest response to one is to re-take both halves,
which the "before" half no longer permits.
