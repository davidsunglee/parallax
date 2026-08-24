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
is gated instead, in `tests/unit/test_snapshot_graph_retention.py`, which `just
python-test-dbfree` owns: that suite fits an affine function of members,
declared view slots, and recorded edges over a crossed grid and requires exact
equality at every point of it, grades seven steps and one exact total — read at
every point that declares a document and again in every presence state that
document's positions admit — against exactly what a compact representation can
charge, and asserts that no object of Parallax's own survives a conforming
materialization except the sealed graph's own structures. Three of the steps
price a pointer — one per member per row, one per arm where the edge is recorded
and one where it resolves, one per slot in every row a slot widens — and four
price a document: one pointer per Value Object leaf in every record that carries
it, one whole positional row and the position naming it per record, one position
and one record per top-level One occurrence, and one position, one row of
element positions, and one record per element per top-level Many occurrence. Its
projections carry documents for that reason: the representation replaced here
spent more of its per-cell cost inside Value Objects than on Attributes, so a
gate blind to occurrences would be blind to most of what it is refusing — and
the four document steps move those populations one at a time, because a cost
charged per record or per occurrence stands still while leaves move and would
otherwise be absorbed whole by the fit's origin. The two occurrence steps are
two because the production reduction has two branches: a carrier that came back
around Many occurrences alone is fixed per projection and invisible to every
reading that varies a One. What no step can vary at all is how deep a document
nests — an occurrence declared inside another one is a fixed count per
projection, so a carrier charged once per nested occurrence stands still under
every axis and the fit absorbs it into the origin — and that is what the total
is for: what a graph retains above the same graph declaring no Value Object at
all, against the price of the whole declared tree, computed by the same
recursion the reduction descends it with. It closes every depth at once instead
of one level per reading, over a workload whose declaration reaches every shape
that reduction descends: a One and a Many occurrence each at the top and nested
inside another, and a record reached only by descending a Many. What a
declaration cannot close is the state its positions hold — every one of those
readings converts rows whose every member is supplied, so a carrier charged on a
zero-value branch, a Many loaded empty or a One stored null, sits on neither
side of any of them. The same exact total is read once more in each state a
conforming read can leave a position in, priced state-aware, and that those
states are a closed set is asserted rather than claimed: the union of the states
they put each kind of position in is exactly what the read contract admits for
that kind. Its measured level is polymorphic for the same kind of reason: two
concretes of one family, of different widths, are laid out and merged inside one
graph, and each level of its plan produces projections at a source level of its
own, so the slot readings count positions production lays out. Seven negative
controls state what each reading is worth — one wraps every member cell and
fails only the member step, one wraps every Value Object cell and fails only the
leaf step, one wraps every reduced record and fails only the record step, one
per multiplicity wraps every top-level occurrence of that multiplicity and fails
only at that branch's step, one wraps every occurrence a document nests inside
another with no Many between them — the population no axis counts — and fails
only the total, leaving all four document steps exactly at their priced values,
and one wraps every position stored zero — the population a carried document has
none of — and fails only the state readings. A per-cell, per-record, or
per-occurrence carrier reappearing at any depth, on any of those paths, in any
of those states, fails there, structurally, without anyone re-taking this
reading.

## The figure

| | before | after | change |
|---|---:|---:|---:|
| **Retained bytes per projection** | **4,721.8** | **1,079.0** | **−77.1%** |
| Retained bytes, whole representative graph | 2,115,368 | 483,404 | −77.1% |
| Tracked survivor objects per projection | 63.89 | 3.45 | −94.6% |
| Of which per-cell carriers | 43.28 | **0** | — |
| Build (convert, write, seal), 448 projections | 33.56 ms | 22.13 ms | −34% |
| Merge, 448 projections | 5.17 ms | 0.57 ms | −89% |

COR-108's ≥60% criterion implies a ceiling of **1,888.7 retained bytes per
projection**. The reading is 1,079.0, which clears it with 43% to spare. The
reduction is above 60% at every point of the size grid below, not only at the one
the headline is taken at.

The two wall-clock rows are the only ones that are not reproducible, and they are
recorded for visibility rather than compared. Both halves time the same span —
conversion, view writes, and sealing, with the builder and its view schema
constructed before the clock starts, exactly as the pre-cutover half constructed
its `MergeScope` before starting its own — but post-cutover processes have read
anywhere from 19.67 to 22.31 ms where every byte reading was identical, and the
pre-cutover half was taken in a different session. The row is the build time of
the run the rest of this table was taken from, near the slow end of that spread;
the spread's own ends would put the change anywhere between −33.5% and −41.4%.
Read those two percentages as a direction, not as a measurement.

The companion absolute claim — "zero retained per-cell Snapshot carrier objects
on the conforming path" — is met exactly. The pre-cutover census itemized 43.28
per-cell carriers per projection across **six** types. Two of them,
`SnapshotNodeRef` and `SnapshotRelationshipViewInput`, were deleted outright with
the rest of the graph-input representation. The other four —
`EntityAttributeInput`, `ValueObjectRecord`, `ValueObjectAttributeInput`, and
`ValueObjectOccurrenceInput` — still exist in `parallax.core.entity`, and a
typed read still composes them: `member_carriers` translates a merged row into
them at Entity Graph Construction's door. What changed is that they are no longer
part of what a graph *retains*. They are built from the row when an Entity
instance is constructed and die with the frame that constructed it, where before
the cutover the graph held one per cell for the life of the read. The survivor
census after the cutover names no Parallax type at all whose count grows with the
graph.

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
| Timing samples | mean of 50 build-and-merge repetitions, the builder constructed outside the clock on both sides |
| Repeatability | two independent processes returned byte-identical readings on both sides; only the wall clock moved |

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
lean = 64,408 B   fat = 64,408 B   delta = +0 B (+0.00%)
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
| 8 | 56 | 264,728 | 4,727.3 | 64,408 | 1,150.1 | −75.7% |
| 16 | 112 | 528,320 | 4,717.1 | 123,168 | 1,099.7 | −76.7% |
| 32 | 224 | 1,054,776 | 4,708.8 | 240,152 | 1,072.1 | −77.2% |
| 64 | 448 | 2,115,368 | 4,721.8 | 483,404 | 1,079.0 | −77.1% |

Least squares over the grid: **4,721.40 bytes per projection with −695 fixed**
before, **1,069.47 with 3,195 fixed** after. The fixed term after the cutover is
5.0% of the smallest reading and 0.7% of the largest — larger as a share than
before only because the per-projection total it sits beside is four times
smaller. The headline is taken at the 64-cell point on both sides.

### Where the bytes sit

| | before | before B/proj | after | after B/proj |
| --- | ---: | ---: | ---: | ---: |
| The graph alone (merge dropped before the sample) | 1,418,676 | 3,166.7 | 422,712 | 943.6 |
| The merge's own retained state | 696,692 | 1,555.1 | 60,692 | 135.5 |
| **Total** | **2,115,368** | **4,721.8** | **483,404** | **1,079.0** |

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
| `tuple` | 1,514 | 3.38 | 3.04 | structural |
| `dict` | 9 | 0.02 | 0.00 | the schema's three memos and the layouts' own maps |
| `mappingproxy` | 7 | 0.02 | 0.00 | the same maps, published |
| `list` | 5 | 0.01 | 0.00 | the merge's own arrays |
| `SourceViewLayout` | 4 | 0.01 | 0.00 | interned per admitted slot tuple |
| `MergedViewLayout` | 3 | 0.01 | 0.00 | one per resolved concrete Entity |
| `SnapshotGraph`, `GraphRows`, `GraphMerge`, `ViewSchema` | 4 | — | — | the graph, its arrays, its merge, the execution's schema |
| **total** | **1,546** | **3.45** | | |

Not one type after the cutover has a marginal cost per projection above zero
except `tuple`, and every `tuple` in that count is a member row, a Value Object
record, a view row, or a to-many arm — a position rather than a wrapper. Nothing
carrier-shaped survives at all: the two Snapshot-specific carrier types no longer
exist, and the four core ones the previous section names are composed and dropped
inside a construction rather than retained.

The tracked-tuple count is the one figure that is not flat per projection across
the grid (5.79 at 8 cells against 3.38 at 64). That is the collector rather than
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

The view schema is the full `ViewSchema(slot_table)` form, and it is the table
`handle/_read._slot_table` yields for this workload's own plan — four hops under
one root, so five entries, dense by source level:

| source level | what it is | slots its projections carry |
| ---: | --- | --- |
| 0 | the `Owner` root | `nodes`, `special[Alpha]`, `favorite` |
| 1 | the broad `nodes` hop | — |
| 2 | the narrowed `special[Alpha]` hop | `owner` |
| 3 | the `favorite` hop | — |
| 4 | the back-reference `owner` hop | — |

Broad and narrowed are distinct plan levels, so **only the two narrowed
duplicates carry an `owner` slot**; the four broad children carry none, because
no level below them attaches one. A table putting both populations on one child
level would give all six children the slot, four of them permanently `ABSENT`,
and measure a row shape no plan produces. Reaching for `ViewSchema.of(...)`
instead would go further still and put every slot on one unguarded level, giving
each owner a row it can never fill.

The last two levels are empty because a level owns a table entry whether or not
it converts a row: the back-reference hop converts none by contract, and the
`favorite` hop's arm is aliased onto the broad level's first child rather than
converted a second time — the one place this drive simplifies, and the reason a
cell is seven projections rather than eight. The pre-cutover half measured that
same seven-projection cell, which is what makes the two halves comparable.

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

The pre-cutover half had no view schema at all — a view was a keyed attachment,
so an unwritten one cost nothing and there was no slot table to get right. That
asymmetry is why the source levels above are stated so exactly: it is the one
place where a careless post-cutover workload could charge itself for storage the
"before" reading never had.

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
