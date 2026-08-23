"""What one materialized Snapshot graph retains, and what it costs to build.

The representative graph the recorded baseline is stated over — about twenty
scalar members, nested One and Many Value Objects, polymorphic projections, three
view slots, duplicate logical nodes, and relationship fan-out — driven through
the production converter, builder, and merge with no database anywhere. It is a
`report`: it passes no verdict and joins no aggregate. The SHAPE of what a graph
retains is gated instead, in
``tests/unit/test_snapshot_graph_retention.py``, because references and positions
give a definite answer where a total in bytes is machine- and interpreter-
relative. What has been read off this, and under what conditions, is
``docs/snapshot-graph-baseline.md``.

**What is measured.** Bytes reachable at the seam's innermost point, while the
sealed graph and its ``GraphMerge`` are both held, that were not reachable before
the window opened. The builder is deliberately not held: it is transient in
production, dying with the frame that sealed it, so a reading that kept one would
measure something no read retains.

**How decoded payload leaves are excluded — structurally, not by filtering.**
Every column value and every Value Object document is allocated at import time,
outside every window, so a row that merely references one of them costs the
reading the position and not the leaf. The control at the end of the output is
what demonstrates it rather than asserting it: the identical graph shape with
every string leaf an order of magnitude longer must read identically.

**What it is measured with.** ``memory_instruments``, the one definition the
gated suites read the same claims through: a collection before every sample so a
reading answers what is still REACHABLE, warm-up passes before every window,
survivor OBJECTS bound rather than their addresses, the sampler warmed
separately from the seam, and the line tracer uninstalled for the window.

Run it through `just python-report-snapshot-graph-overhead`.
"""

import platform
import sys
import tracemalloc
from collections import Counter
from collections.abc import Callable
from time import perf_counter
from typing import Final, NamedTuple, cast

from memory_instruments import WARMUP, LiveGraph, Seam, live_graph, retained, untraced, warmed
from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    AbstractRoot,
    AbstractSubtype,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Int32,
    Rel,
    TablePerHierarchy,
    ValueObject,
    attr,
    rel,
)
from parallax.core.entity._model import cataloged_model
from parallax.core.metamodel import EntityIdentity, RelationshipIdentity, entity_by_name
from parallax.core.temporal_read import Pin
from parallax.snapshot.materialize import GraphMerge, SnapshotGraph, merge_graph_input
from parallax.snapshot.materialize._convert import LevelContext, convert_row
from parallax.snapshot.materialize._graph import GraphBuilder, graph_rows
from parallax.snapshot.materialize._views import ChildSlot, RelationshipViewKey, ViewSchema

PRE_CUTOVER_BYTES: Final = 4_721.8
"""Retained bytes per projection this identical workload read on the per-cell
carrier representation, transcribed from ``docs/snapshot-graph-baseline.md``,
which records the conditions it was taken under. A reference figure printed
beside the reading, never a threshold: `tracemalloc` totals move with the
interpreter, so a ratio across two of them measures the interpreter."""

PRE_CUTOVER_SURVIVORS: Final = 63.89
"""Tracked survivor objects per projection the same reading counted, of which
43.28 were per-cell carriers."""

CRITERION: Final = 0.60
"""The reduction the recorded baseline states its ceiling from. Printed as the
ceiling it implies so a reader can see the reading against it without this
judging one."""

REPEATS: Final = 50
"""Timed repetitions of build and merge. Wall clock is recorded for visibility
alone, so this buys a stable mean rather than a distribution."""

GRID: Final = (8, 16, 32, 64)
"""Graph sizes over an eightfold span, so a fixed cost cannot hide inside a
per-projection one."""

REPRESENTATIVE: Final = 64
"""The size the headline is taken at, and the largest of the grid."""


# --------------------------------------------------------------------------- #
# The workload model. Bespoke because no model in the tree carries all six of   #
# the representative graph's traits at the width it names them: the corpus tops #
# out at eight applicable Attributes on one Entity, and no document there       #
# combines wide scalars with nested Value Objects, an inheritance family, and   #
# relationship fan-out.                                                         #
# --------------------------------------------------------------------------- #

NAMESPACE: Final = "snapshot.overhead"


class Leaf(ValueObject):
    """The nested Value Object, one leaf deep."""

    note: Attr[str | None]


class Tag(ValueObject):
    """A Value Object carrying a leaf, a nested One, and a nested Many."""

    label: Attr[str | None]
    detail: Attr[Leaf | None]
    details: Attr[tuple[Leaf, ...]]


class Node(
    Entity,
    table="overhead_node",
    namespace=NAMESPACE,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    """The family root: nineteen applicable Attributes, a top-level One Value
    Object, a top-level Many, and the back reference its children carry."""

    id: Attr[int] = attr(primary_key=True)
    owner_id: Attr[int | None]
    s01: Attr[str | None] = attr(max_length=32)
    s02: Attr[str | None] = attr(max_length=32)
    s03: Attr[str | None] = attr(max_length=32)
    s04: Attr[str | None] = attr(max_length=32)
    s05: Attr[str | None] = attr(max_length=32)
    s06: Attr[str | None] = attr(max_length=32)
    s07: Attr[str | None] = attr(max_length=32)
    s08: Attr[str | None] = attr(max_length=32)
    n01: Attr[int | None] = attr(type=Int32)
    n02: Attr[int | None] = attr(type=Int32)
    n03: Attr[int | None] = attr(type=Int32)
    n04: Attr[int | None] = attr(type=Int32)
    f01: Attr[float | None]
    f02: Attr[float | None]
    b01: Attr[bool | None]
    d01: Attr[str | None] = attr(max_length=32)
    m01: Attr[str | None] = attr(max_length=32)
    primary_tag: Attr[Tag | None]
    tags: Attr[tuple[Tag, ...]]
    owner: Rel["Owner | None"] = rel(reverse_of="nodes")


class Special(Node, namespace=NAMESPACE, inheritance=AbstractSubtype):
    """The abstract middle of the family, which a narrowed view resolves to."""

    rank: Attr[int | None] = attr(type=Int32)


class Alpha(Special, namespace=NAMESPACE, inheritance=ConcreteSubtype(tag_value="alpha")):
    """One concrete of the family, reached both broadly and through the narrowed
    view — which is what gives the graph its duplicate projections."""


class Beta(Node, namespace=NAMESPACE, inheritance=ConcreteSubtype(tag_value="beta")):
    """The family's other concrete, reached broadly alone."""

    weight: Attr[float | None]


class Owner(Entity, table="overhead_owner", namespace=NAMESPACE):
    """The root of every cell, carrying the three view slots: a broad to-many, a
    narrowed to-many, and a to-one into the same family."""

    id: Attr[int] = attr(primary_key=True)
    name: Attr[str | None] = attr(max_length=32)
    favorite_id: Attr[int | None]
    nodes: Rel[tuple[Node, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "owner_id"), dependent=True
    )
    special: Rel[tuple[Special, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "owner_id"))
    favorite: Rel[Node | None] = rel(cardinality=MANY_TO_ONE, join=("favorite_id", "id"))


MODEL: Final = DomainModel(Node, Special, Alpha, Beta, Owner)
CATALOGED: Final = cataloged_model(MODEL)
PIN: Final = Pin()


def _identity(name: str) -> EntityIdentity:
    metadata = entity_by_name(CATALOGED.meta, name)
    assert metadata is not None, name
    return metadata.identity


def _level(name: str) -> LevelContext:
    layout = CATALOGED.layouts.entity(_identity(name))
    return LevelContext(layout, layout.occurrences)


ALPHA_LEVEL: Final = _level("Alpha")
BETA_LEVEL: Final = _level("Beta")
OWNER_LEVEL: Final = _level("Owner")

_OWNER: Final = _identity("Owner")
VIEW_NODES: Final = RelationshipViewKey(RelationshipIdentity(_OWNER, "nodes"))
VIEW_SPECIAL: Final = RelationshipViewKey(RelationshipIdentity(_OWNER, "special"), "special[Alpha]")
VIEW_FAVORITE: Final = RelationshipViewKey(RelationshipIdentity(_OWNER, "favorite"))
VIEW_OWNER: Final = RelationshipViewKey(RelationshipIdentity(_identity("Node"), "owner"))

ROOT_SOURCE: Final = 0
BROAD_SOURCE: Final = 1
NARROWED_SOURCE: Final = 2
SLOT_TABLE: Final = (
    (ChildSlot(VIEW_NODES), ChildSlot(VIEW_SPECIAL), ChildSlot(VIEW_FAVORITE)),
    (),
    (ChildSlot(VIEW_OWNER),),
    (),
    (),
)
"""The slot table ``handle/_read._slot_table`` yields for this workload's plan,
dense by source level.

The plan is four levels under one root: the broad ``nodes`` hop, the narrowed
``special[Alpha]`` hop, the ``favorite`` hop — all three parented by the root,
which is why all three slots land on level 0 — and the back-reference ``owner``
hop parented by the narrowed one, whose slot therefore lands on the level the
narrowed hop's own projections are read at. Broad and narrowed are DISTINCT plan
levels, so only the narrowed duplicates can receive ``owner``; a table putting
both populations on one level would give the four broad children a slot no plan
of theirs attaches.

The last two entries are empty because a level owns an entry whether or not it
converts a row here: the back-reference level converts none by contract, and the
``favorite`` hop's arm is aliased onto the broad level's first child rather than
converted a second time, which is what holds this drive to the seven projections
per cell the recorded pre-cutover half measured.

Built here rather than through ``ViewSchema.of``, which would put every slot on
one level and give each projection a row it can never fill."""

FANOUT: Final = 4
DUPLICATES: Final = 2
PROJECTIONS_PER_CELL: Final = 1 + FANOUT + DUPLICATES
LOGICAL_PER_CELL: Final = 1 + FANOUT
VIEW_SLOTS_PER_CELL: Final = 3 + DUPLICATES


# --------------------------------------------------------------------------- #
# The payloads, built at IMPORT time — which is what excludes decoded payload   #
# leaves from every reading.                                                   #
# --------------------------------------------------------------------------- #


def _tag(seed: int, details: int) -> dict[str, object]:
    return {
        "label": f"label-{seed}",
        "detail": {"note": f"note-{seed}"},
        "details": [{"note": f"detail-{seed}-{index}"} for index in range(details)],
    }


def _node_row(node_id: int, owner_id: int, extra: str, extra_value: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": node_id,
        "owner_id": owner_id,
        "b01": bool(node_id % 2),
        "f01": float(node_id),
        "f02": float(node_id) + 0.5,
        "primary_tag": _tag(node_id, 2),
        "tags": [_tag(node_id * 10 + 1, 1), _tag(node_id * 10 + 2, 1)],
        extra: extra_value,
    }
    for index in range(1, 9):
        row[f"s{index:02d}"] = f"s{index:02d}-value-{node_id}"
    for index in range(1, 5):
        row[f"n{index:02d}"] = node_id * 100 + index
    row["d01"] = f"2026-08-{(node_id % 28) + 1:02d}"
    row["m01"] = f"{node_id}.25"
    return row


class Cell(NamedTuple):
    """One owner, its four children, and the two of them a narrowed view converts
    a second time."""

    owner: dict[str, object]
    children: tuple[tuple[dict[str, object], LevelContext], ...]
    duplicates: tuple[dict[str, object], ...]


def cells(count: int) -> tuple[Cell, ...]:
    """``count`` independent cells' worth of rows."""
    built: list[Cell] = []
    for index in range(count):
        owner_id = 1_000 + index
        base = 10_000 + index * 10
        children: list[tuple[dict[str, object], LevelContext]] = []
        for offset in range(FANOUT):
            node_id = base + offset
            if offset < DUPLICATES:
                children.append((_node_row(node_id, owner_id, "rank", offset), ALPHA_LEVEL))
            else:
                children.append((_node_row(node_id, owner_id, "weight", float(offset)), BETA_LEVEL))
        built.append(
            Cell(
                owner={"id": owner_id, "name": f"owner-{index}", "favorite_id": base},
                children=tuple(children),
                duplicates=tuple(
                    _node_row(base + offset, owner_id, "rank", offset)
                    for offset in range(DUPLICATES)
                ),
            )
        )
    return tuple(built)


def fattened(count: int) -> tuple[Cell, ...]:
    """The identical graph SHAPE with every leaf payload an order of magnitude
    larger. A reading that moves under it is a reading that counts leaves."""
    pad = "x" * 512

    def fatten(value: object) -> object:
        if isinstance(value, str):
            return value + pad
        if isinstance(value, dict):
            return {key: fatten(item) for key, item in cast("dict[str, object]", value).items()}
        if isinstance(value, list):
            return [fatten(item) for item in cast("list[object]", value)]
        return value

    def row(values: dict[str, object]) -> dict[str, object]:
        return {key: fatten(value) for key, value in values.items()}

    return tuple(
        Cell(
            owner=row(cell.owner),
            children=tuple((row(values), level) for values, level in cell.children),
            duplicates=tuple(row(values) for values in cell.duplicates),
        )
        for cell in cells(count)
    )


# --------------------------------------------------------------------------- #
# The seam.                                                                    #
# --------------------------------------------------------------------------- #


def sealed(builder: GraphBuilder, plan: tuple[Cell, ...]) -> SnapshotGraph:
    """Convert every projection into ``builder``, write every view, and seal —
    the shape a read's own level loop has, with the builder dying in this frame.

    Taking the builder rather than making one is what lets the wall clock time
    the same span the pre-cutover reading timed, which constructed its scope
    before starting its own clock.
    """
    roots: list[int] = []
    for cell in plan:
        owner = convert_row(cell.owner, OWNER_LEVEL, builder, source=ROOT_SOURCE)
        children = tuple(
            convert_row(row, level, builder, source=BROAD_SOURCE) for row, level in cell.children
        )
        duplicates = tuple(
            convert_row(row, ALPHA_LEVEL, builder, source=NARROWED_SOURCE)
            for row in cell.duplicates
        )
        builder.write_view(owner, VIEW_NODES, children)
        builder.write_view(owner, VIEW_SPECIAL, duplicates)
        builder.write_view(owner, VIEW_FAVORITE, children[0])
        for duplicate in duplicates:
            builder.write_view(duplicate, VIEW_OWNER, owner)
        roots.append(owner)
    return builder.seal(tuple(roots), PIN)


def build(plan: tuple[Cell, ...]) -> SnapshotGraph:
    """One execution's whole graph: a schema of its own, and every row under it."""
    return sealed(GraphBuilder(ViewSchema(SLOT_TABLE)), plan)


def compose(plan: tuple[Cell, ...]) -> tuple[SnapshotGraph, GraphMerge]:
    """One whole materialization: what a ``FindResult`` and its merge hold."""
    graph = build(plan)
    return graph, merge_graph_input(graph)


def seam_over(plan: tuple[Cell, ...], *, merged: bool = True) -> Seam:
    """The whole pipeline held at the sample point. With ``merged`` false the
    merge is dropped before sampling, so the difference between the two readings
    is what ``GraphMerge`` itself retains."""

    def run(sample: Callable[[], None]) -> None:
        graph, merge = compose(plan)
        if not merged:
            del merge
        sample()
        assert graph is not None

    return run


def timings(plan: tuple[Cell, ...]) -> tuple[float, float]:
    """Mean wall-clock seconds to build the sealed graph, and to merge it.

    Each repetition gets a builder and a view schema of its own, constructed
    OUTSIDE its own clock: the recorded pre-cutover half timed conversion,
    attachment, and composition with its ``MergeScope`` already constructed, and
    a window that also carried the execution's own setup would compare two
    different spans. Every per-row and per-level cost the schema defers — a
    source layout built on a level's first reach, a merged layout on a
    concrete's — still falls inside the timed span, exactly as the scope's own
    per-row caches did.
    """
    building = 0.0
    merging = 0.0
    with untraced():
        for _ in range(REPEATS):
            builder = GraphBuilder(ViewSchema(SLOT_TABLE))
            start = perf_counter()
            graph = sealed(builder, plan)
            building += perf_counter() - start
            start = perf_counter()
            merged = merge_graph_input(graph)
            merging += perf_counter() - start
            assert merged is not None
    return building / REPEATS, merging / REPEATS


def census(plan: tuple[Cell, ...]) -> Counter[str]:
    """The survivors of one held materialization, by type name."""
    return Counter(type(obj).__qualname__ for obj in live_graph(warmed(seam_over(plan))).survivors)


def fit(points: dict[int, int]) -> tuple[float, float]:
    """Least-squares slope and intercept of bytes against projection count."""
    xs = [count * PROJECTIONS_PER_CELL for count in points]
    ys = list(points.values())
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / sum(
        (x - mean_x) ** 2 for x in xs
    )
    return slope, mean_y - slope * mean_x


def _verified(plan: tuple[Cell, ...]) -> None:
    """That the graph the readings are taken over is the one described.

    Every count the workload claims, read off the sealed graph and its merge
    before any window opens — including that the path is CONFORMING, which is the
    path the baseline's absolute claims are stated over.
    """
    graph, merge = compose(plan)
    rows = graph_rows(graph)
    assert len(rows.layouts) == REPRESENTATIVE * PROJECTIONS_PER_CELL, len(rows.layouts)
    assert len(rows.roots) == REPRESENTATIVE, len(rows.roots)
    assert len(merge.order) == REPRESENTATIVE * LOGICAL_PER_CELL, len(merge.order)
    assert not merge.has_issues, "the conforming path carries no stored-data issue"
    assert len(ALPHA_LEVEL.layout.attributes) == 20, "about twenty scalar members"
    assert len(ALPHA_LEVEL.layout.occurrences) == 2, "a top-level One and a top-level Many"


def _conditions() -> list[tuple[str, str]]:
    return [
        ("Python", f"CPython {platform.python_version()}"),
        ("Platform", f"{sys.platform}/{platform.machine()}"),
        ("Warm-up", f"{WARMUP} unsampled runs before every window"),
        (
            "Shape",
            f"{PROJECTIONS_PER_CELL} projections per cell "
            f"({LOGICAL_PER_CELL} logical nodes, {VIEW_SLOTS_PER_CELL} view slots, "
            f"fan-out {FANOUT}, {DUPLICATES} duplicate projections)",
        ),
    ]


def _grid_lines(bytes_at: dict[int, int], live: dict[int, LiveGraph]) -> list[str]:
    header = (
        f"{'cells':>6} {'projections':>12} {'retained B':>12} {'B/proj':>9} "
        f"{'survivors':>10} {'surv/proj':>10} {'inbound':>9}"
    )
    lines = [header]
    for count in GRID:
        projections = count * PROJECTIONS_PER_CELL
        graph = live[count]
        lines.append(
            f"{count:>6} {projections:>12} {bytes_at[count]:>12,} "
            f"{bytes_at[count] / projections:>9.1f} "
            f"{len(graph.survivors):>10,} {len(graph.survivors) / projections:>10.2f} "
            f"{graph.inbound:>9,}"
        )
    slope, intercept = fit(bytes_at)
    lines.append("")
    lines.append(f"  least squares over the grid: {slope:.2f} B/projection + {intercept:.0f} fixed")
    return lines


def _headline_lines(total: int, graph_only: int, survivors: int) -> list[str]:
    projections = REPRESENTATIVE * PROJECTIONS_PER_CELL
    per_projection = total / projections
    return [
        f"headline ({REPRESENTATIVE} cells / {projections} projections)",
        f"  retained bytes                = {total:,}",
        f"  retained bytes per projection = {per_projection:.1f}",
        f"  retained survivors            = {survivors:,} ({survivors / projections:.2f}/proj)",
        f"  sealed graph alone            = {graph_only:,} ({graph_only / projections:.1f} B/proj)",
        f"  the merge's own share         = {total - graph_only:,} "
        f"({(total - graph_only) / projections:.1f} B/proj)",
        "",
        "against the recorded pre-cutover reading of the identical workload",
        f"  pre-cutover                   = {PRE_CUTOVER_BYTES:.1f} B/proj, "
        f"{PRE_CUTOVER_SURVIVORS:.2f} survivors/proj",
        f"  reduction                     = "
        f"{(1 - per_projection / PRE_CUTOVER_BYTES) * 100:.1f}% of the bytes, "
        f"{(1 - survivors / projections / PRE_CUTOVER_SURVIVORS) * 100:.1f}% of the objects",
        f"  the {CRITERION:.0%} criterion implies    <= "
        f"{PRE_CUTOVER_BYTES * (1 - CRITERION):.1f} B/proj",
    ]


def _census_lines(counts: Counter[str], smallest: Counter[str]) -> list[str]:
    projections = REPRESENTATIVE * PROJECTIONS_PER_CELL
    span = projections - GRID[0] * PROJECTIONS_PER_CELL
    lines = ["survivor census by type (representative graph, warmed)"]
    for name, value in counts.most_common():
        marginal = (value - smallest.get(name, 0)) / span
        lines.append(
            f"  {value:>7,}  {value / projections:>7.2f}/proj   "
            f"marginal {marginal:>6.2f}/proj  {name}"
        )
    return lines


def main(argv: list[str]) -> int:
    """Measure and print; never judge.

    Exit codes: 0 — the measurement ran; 2 — usage error. There is no exit code
    for a number that is too large, deliberately.
    """
    if argv:
        print("usage: python tools/snapshot_graph_overhead.py", file=sys.stderr)
        return 2
    plans = {count: cells(count) for count in GRID}
    _verified(plans[REPRESENTATIVE])
    tracemalloc.start()
    try:
        bytes_at = {count: retained(seam_over(plans[count])) for count in GRID}
        graph_only = retained(seam_over(plans[REPRESENTATIVE], merged=False))
        lean = retained(seam_over(plans[GRID[0]]))
        fat = retained(seam_over(fattened(GRID[0])))
    finally:
        tracemalloc.stop()
    live = {count: live_graph(warmed(seam_over(plans[count]))) for count in GRID}
    build_s, merge_s = timings(plans[REPRESENTATIVE])
    projections = REPRESENTATIVE * PROJECTIONS_PER_CELL

    lines = ["parallax snapshot graph retained overhead", ""]
    lines += [f"  {name:<10}{value}" for name, value in _conditions()]
    lines += ["", *_grid_lines(bytes_at, live), ""]
    lines += _headline_lines(
        bytes_at[REPRESENTATIVE], graph_only, len(live[REPRESENTATIVE].survivors)
    )
    lines += ["", f"wall clock (mean of {REPEATS}, {projections} projections)"]
    lines += [
        f"  build (convert, write, seal)  = {build_s * 1e3:.2f} ms "
        f"({build_s / projections * 1e6:.2f} us/projection)",
        f"  merge                         = {merge_s * 1e3:.2f} ms "
        f"({merge_s / projections * 1e6:.2f} us/projection)",
    ]
    lines += ["", *_census_lines(census(plans[REPRESENTATIVE]), census(plans[GRID[0]]))]
    lines += [
        "",
        f"payload-leaf exclusion control ({GRID[0]} cells, every leaf padded by 512 characters)",
        f"  lean = {lean:,} B   fat = {fat:,} B   delta = {fat - lean:+,} B "
        f"({(fat - lean) / lean * 100:+.2f}%)",
    ]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
