"""What a materialized Snapshot graph keeps, and what it refuses to keep per cell.

`spec/python.md`'s *Single graph* requirement bounds a read's retained cost by the
projections, logical nodes, relationships, and declared view slots it actually
carries, and forbids a per-cell carrier, a member dictionary, and a second
graph-sized merged representation. This is that requirement measured rather than
reviewed.

**Bytes are the load-bearing instrument here**, which is the opposite of the
lifecycle suites' balance. A compact row is a tuple of decoded leaves and an edge
is a built-in ``int``: a tuple holding only untracked items is untracked itself
after a collection, so a survivor count classified by type sees almost none of
what a graph holds. :func:`~memory_instruments.retained` sees all of it, and
the survivor count is read beside it for the one claim bytes cannot make on their
own — that no OBJECT of Parallax's own survives a conforming materialization
except the sealed graph's own structures.

**The grid varies three workload parameters and pins everything else.** A graph
of a fixed number of projections, logical nodes, and roots is built over member
rows of varying width, under a varying number of declared view slots, with a
varying number of projection references in one to-many arm. Pinning the counts is
what makes the readings exact: the merge's own tables are sized by projections
and logical nodes, and a dictionary that resized between two points would put a
capacity step into a reading that is otherwise pure tuple arithmetic.

**Every measured projection also carries Value Object occurrences**, a top-level
One holding a nested One and a nested Many beside a top-level Many, because the
representation this replaced spent more of its per-cell cost inside documents
than on Attributes: a record, an occurrence, and a per-leaf carrier each. Their
shape is pinned across the grid — a fourth crossed axis would buy nothing the
first three do not already refuse — and read instead as a step of its own, over
the leaf count of the nested records.

**What the readings say, in the order they get stronger.** The whole grid sits on
one affine function of the three parameters fitted from its four smallest points,
which refuses any cross term — a slot cost sized per member, say. Then each step
is graded against the exact number of pointers the compact representation can
charge: one per member per row, one per arm where the edge is recorded and one
where it resolves, one per slot in every row a slot widens, and one per Value
Object leaf in every record that carries it. Those readings are the ones that
name "no per-cell carrier" in arithmetic, and the two controls are what prove
they detect one —
:func:`test_the_member_step_is_what_refuses_a_representation_that_wraps_every_cell`
wraps every member cell, stays exactly affine, and fails only at the member step;
:func:`test_the_leaf_step_is_what_refuses_a_representation_wrapping_every_document_cell`
wraps every Value Object cell and fails only at the leaf step.

Exported names carry no leading underscore only where another module imports
them; nothing imports this one.
"""

from __future__ import annotations

import struct
import tracemalloc
from collections.abc import Callable, Mapping
from functools import cache
from typing import Final, NamedTuple, cast

import pytest

from memory_instruments import Seam, retained, survivors, warmed
from parallax.core.entity._layout import CatalogedModel, EntityLayout
from parallax.core.entity._model import model_of
from parallax.core.metamodel import EntityIdentity, Metamodel, RelationshipIdentity, entity_by_name
from parallax.core.temporal_read import Pin
from parallax.descriptor import domain_model_from_document
from parallax.snapshot.materialize import SnapshotGraph, merge_graph_input
from parallax.snapshot.materialize._convert import LevelContext, convert_row
from parallax.snapshot.materialize._graph import GraphBuilder, GraphRows, graph_rows
from parallax.snapshot.materialize._merge import GraphMerge
from parallax.snapshot.materialize._views import (
    ChildSlot,
    MergedViewLayout,
    RelationshipViewKey,
    SourceViewLayout,
    ViewSchema,
)

_POINTER: Final = struct.calcsize("P")
"""One machine pointer, which is the whole of what a compact row may charge for
one member: a position holds the decoded leaf itself, so a member costs the slot
that points at it and nothing else. A representation that wrapped a cell would
charge this plus a whole object per cell, which is what the grid refuses."""

_NAMESPACE: Final = "snapshot.retention"

_ROOT_SOURCE: Final = 0
_CHILD_SOURCE: Final = 1
"""The two source levels the workload plans: the parents its roots are, and the
one level below them every child projection is read at."""

_CHILDREN: Final = 6
_DUPLICATES: Final = 2
"""Children per parent, and how many of them a second level converts a second
time. Duplicates are what make projections and logical nodes different counts, so
a reading charged per logical node cannot pass for one charged per projection."""

_CELLS: Final = 4
_LARGER: Final = 8
"""Independent parent-and-children cells, at two sizes. The grid is measured at
the first; the second is measured at four points alone, which is all the second
fit needs to say whether each step grew with the rows it charges."""

_MEMBERS: Final = (4, 5, 8, 16)
"""Applicable Attributes on the measured Entity. The two smallest are one apart,
so their difference is what one more member costs rather than a ratio, and the
largest is four times the smallest — far enough that a cost quadratic in the row
width would be whole members off the line rather than within one member of it."""

_SLOTS: Final = (2, 3, 4)
"""Relationship views the plan declares at the root source level. Two are always
written — the broad view holding every child, and the narrowed arm the third axis
varies — and the rest are levels that gathered a parent and found nothing, which
is what a declared-and-empty slot is. Four is the ceiling deliberately: the slot
tables are dictionaries, and a fifth entry in the merged union would resize one
and put a capacity step into a reading that is otherwise exact."""

_ARMS: Final = (1, 2, 4)
"""Projection references in the narrowed arm. The children it does not name are
still reached through the broad view, so the graph's projection and logical-node
counts do not move with this axis — which is what makes it a reading of the edges
alone."""

_LEAVES: Final = (1, 2)
"""Leaves on each NESTED Value Object record. Two counts one apart, read as a
step rather than crossed into the grid: the occurrence shape is the same at every
grid point, so what this axis answers is what one more Value Object leaf costs
and nothing about the other three."""

_NESTED: Final = 2
"""Elements in each Many occurrence. More than one, so a cost charged per Value
Object RECORD is a different number from one charged per projection row."""

_VIEWS: Final = ("children", "arms", "extra1", "extra2")
"""The parent's declared relationships, in declaration order. A slot count names
the first ``slots`` of them; the model declares them all at every count, so a
relationship a plan did not use is model-owned metadata and costs no reading."""


def _document(members: int, leaves: int) -> Mapping[str, object]:
    """A two-Entity model descriptor whose Child carries ``members`` Attributes
    and Value Object occurrences whose nested records carry ``leaves`` each.

    Descriptor-backed rather than class-backed because the axes ARE the member
    and leaf counts: one document generator answers every point of the grid,
    where near-identical class pairs would answer the same question by
    repetition. Nothing here constructs an Entity, so the classes a typed
    materializer would need are not part of what is measured.

    The occurrences are what put a document on the measured path: ``mark`` is a
    top-level One holding a nested One and a nested Many, and ``marks`` is a
    top-level Many. A Many is declared at :data:`_NESTED` elements by the rows,
    so a record count is not a row count.
    """

    def one_to_many(name: str, *, dependent: bool = False) -> dict[str, object]:
        declared: dict[str, object] = {
            "name": name,
            "cardinality": "one-to-many",
            "join": {
                "source": "id",
                "target": {"entity": f"{_NAMESPACE}.Child", "attribute": "parentId"},
            },
        }
        if dependent:
            declared["dependent"] = True
        return declared

    def leaf_run() -> list[dict[str, object]]:
        return [{"name": f"v{index:02d}", "type": "string"} for index in range(leaves)]

    return {
        "entities": [
            {
                "name": "Parent",
                "namespace": _NAMESPACE,
                "table": "retention_parent",
                "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
                "relationships": [
                    one_to_many(_VIEWS[0], dependent=True),
                    *(one_to_many(name) for name in _VIEWS[1:]),
                ],
            },
            {
                "name": "Child",
                "namespace": _NAMESPACE,
                "table": "retention_child",
                "attributes": [
                    {"name": "id", "type": "int64", "primaryKey": True},
                    {"name": "parentId", "type": "int64"},
                    *(
                        {"name": f"c{index:02d}", "type": "string", "maxLength": 32}
                        for index in range(members - 2)
                    ),
                ],
                "valueObjects": [
                    {
                        "name": "mark",
                        "attributes": [{"name": "label", "type": "string"}],
                        "valueObjects": [
                            {"name": "inner", "attributes": leaf_run()},
                            {"name": "inners", "multiplicity": "many", "attributes": leaf_run()},
                        ],
                    },
                    {
                        "name": "marks",
                        "multiplicity": "many",
                        "attributes": [{"name": "label", "type": "string"}],
                    },
                ],
                "relationships": [{"name": "parent", "reverseOf": f"{_NAMESPACE}.Parent.children"}],
                "indices": [{"name": "retention_child_parent", "attributes": ["parentId"]}],
            },
        ]
    }


def _identity(meta: Metamodel, name: str) -> EntityIdentity:
    metadata = entity_by_name(meta, name)
    assert metadata is not None, name
    return metadata.identity


def _level(layout: EntityLayout) -> LevelContext:
    return LevelContext(layout, layout.occurrences)


class _Workload(NamedTuple):
    """One member count's whole model and its rows, formed once at import.

    Every row a window converts is allocated out here, which is what excludes
    decoded payload leaves from the readings STRUCTURALLY rather than by
    filtering: a compact row that merely references one of these values costs the
    reading the position and not the value.
    """

    meta: Metamodel
    parent: LevelContext
    child: LevelContext
    views: tuple[RelationshipViewKey, ...]
    back: RelationshipViewKey
    parents: tuple[dict[str, object], ...]
    children: tuple[tuple[dict[str, object], ...], ...]


def _workload(members: int, leaves: int) -> _Workload:
    meta = model_of(domain_model_from_document(_document(members, leaves)))
    catalog = CatalogedModel(meta).layouts
    parent, child = _identity(meta, "Parent"), _identity(meta, "Child")
    parent_rows: list[dict[str, object]] = [{"id": 1_000 + cell} for cell in range(_LARGER)]
    child_rows: list[tuple[dict[str, object], ...]] = []
    for cell in range(_LARGER):
        rows: list[dict[str, object]] = []
        for index in range(_CHILDREN):
            row: dict[str, object] = {"id": 10_000 + cell * 100 + index, "parent_id": 1_000 + cell}
            for position in range(members - 2):
                row[f"c{position:02d}"] = f"c{position:02d}-value-{cell}-{index}"
            row["mark"] = {
                "label": f"mark-{cell}-{index}",
                "inner": _record(leaves, cell, index),
                "inners": [_record(leaves, cell, index) for _ in range(_NESTED)],
            }
            row["marks"] = [
                {"label": f"marks-{cell}-{index}-{element}"} for element in range(_NESTED)
            ]
            rows.append(row)
        child_rows.append(tuple(rows))
    return _Workload(
        meta,
        _level(catalog.entity(parent)),
        _level(catalog.entity(child)),
        tuple(RelationshipViewKey(RelationshipIdentity(parent, name)) for name in _VIEWS),
        RelationshipViewKey(RelationshipIdentity(child, "parent")),
        tuple(parent_rows),
        tuple(child_rows),
    )


def _record(leaves: int, cell: int, index: int) -> dict[str, object]:
    """One nested Value Object record's stored document."""
    return {f"v{position:02d}": f"v{position:02d}-{cell}-{index}" for position in range(leaves)}


_WORKLOADS: Final = {
    (members, leaves): _workload(members, leaves)
    for members in _MEMBERS
    for leaves in (_LEAVES if members == _MEMBERS[0] else _LEAVES[:1])
}
"""One workload per grid member count, plus the one the leaf step's second point
needs. The leaf axis is read at the smallest member count alone, which is where
every step in this suite is read."""

_PIN: Final = Pin()

_GRAPH_STRUCTURES: Final = (
    SnapshotGraph,
    GraphRows,
    GraphMerge,
    ViewSchema,
    SourceViewLayout,
    MergedViewLayout,
    ChildSlot,
)
"""What a held materialization is allowed to leave alive, by kind.

One sealed graph, its arrays, its merge, and the execution's own view schema with
the slot table and layouts that schema was built from. Every one of them is a
whole-graph or whole-execution structure, which is the claim the counts beside
the list make: not one of them is per projection, per member, or per edge.
"""


class _Point(NamedTuple):
    """One workload the readings are stated over: ``members`` applicable
    Attributes on each child projection, ``slots`` relationship views declared at
    the root source level, ``arms`` projection references in the narrowed view of
    them, and ``leaves`` on each nested Value Object record.

    The crossed grid pins ``leaves``; only the leaf step moves it."""

    members: int
    slots: int
    arms: int
    leaves: int = _LEAVES[0]


_GRID: Final = tuple(
    _Point(members, slots, arms) for members in _MEMBERS for slots in _SLOTS for arms in _ARMS
)
"""Every combination of the three parameters.

What one axis at a time cannot reach: a cost sized per member PER SLOT is affine
down each axis on its own and quadratic in the plane the two make, so a grid
varying one parameter while pinning the others admits it at every column it
reads.
"""

_LEAST: Final = _Point(_MEMBERS[0], _SLOTS[0], _ARMS[0])


def _compose(point: _Point, cells: int) -> tuple[SnapshotGraph, GraphMerge]:
    """One whole materialization of ``cells`` cells, built and merged the way a
    read builds and merges one: a fresh slot table and view schema per execution,
    every row converted through the production converter, the builder dropped at
    sealing, and the sealed graph and its merge the only things that come back."""
    workload = _WORKLOADS[point.members, point.leaves]
    views = workload.views[: point.slots]
    schema = ViewSchema((tuple(ChildSlot(view) for view in views), (ChildSlot(workload.back),)))
    builder = GraphBuilder(schema)
    roots: list[int] = []
    for cell in range(cells):
        parent = convert_row(workload.parents[cell], workload.parent, builder, source=_ROOT_SOURCE)
        children = tuple(
            convert_row(row, workload.child, builder, source=_CHILD_SOURCE)
            for row in workload.children[cell]
        )
        duplicates = tuple(
            convert_row(
                workload.children[cell][index], workload.child, builder, source=_CHILD_SOURCE
            )
            for index in range(_DUPLICATES)
        )
        builder.write_view(parent, views[0], (*children, *duplicates))
        builder.write_view(parent, views[1], children[: point.arms])
        for empty in views[2:]:
            builder.write_view(parent, empty, ())
        for duplicate in duplicates:
            builder.write_view(duplicate, workload.back, parent)
        roots.append(parent)
    graph = builder.seal(tuple(roots), _PIN)
    return graph, merge_graph_input(graph)


def _seam(point: _Point, cells: int = _CELLS) -> Seam:
    """``point``'s materialization, held at the sample point.

    The builder is deliberately not held: it is transient in production, dying
    with the frame that sealed it, so a reading that kept one would measure
    something no read retains.
    """

    def run(sample: Callable[[], None]) -> None:
        graph, merge = _compose(point, cells)
        sample()
        assert graph is not None and merge is not None

    return run


class _Fit(NamedTuple):
    """Retained bytes as one function of the whole workload: ``origin``, plus
    ``member`` for every applicable Attribute, ``slot`` for every declared view,
    and ``arm`` for every projection reference in the narrowed view.

    A sum of three independent terms with no term in any PRODUCT of them, which
    is the whole of what a crossed grid adds to axes read one at a time.
    """

    origin: int
    member: int
    slot: int
    arm: int


def _fitted(measured: Mapping[_Point, int]) -> _Fit:
    """The one function of that shape the four smallest workloads determine.

    Read off unit steps rather than solved for: the two smallest values on every
    axis are one apart, so each difference is what one more of that parameter
    costs. Nothing here grades anything — :func:`_predicts` over the whole grid is
    what does, and a cost of any other shape disagrees with the fit somewhere in
    it.
    """
    least = measured[_LEAST]
    member = measured[_LEAST._replace(members=_MEMBERS[1])] - least
    slot = measured[_LEAST._replace(slots=_SLOTS[1])] - least
    arm = measured[_LEAST._replace(arms=_ARMS[1])] - least
    return _Fit(
        least - _LEAST.members * member - _LEAST.slots * slot - _LEAST.arms * arm,
        member,
        slot,
        arm,
    )


def _predicts(fit: _Fit, point: _Point) -> int:
    """What ``fit`` says the workload at ``point`` retains."""
    return fit.origin + point.members * fit.member + point.slots * fit.slot + point.arms * fit.arm


@cache
def _measured(cells: int) -> dict[_Point, int]:
    """Retained bytes at every grid point, for a graph of ``cells`` cells.

    Cached because the grid is the same reading for every claim stated over it and
    a byte reading costs a warmed repetition of the whole workload.
    """
    tracemalloc.start()
    try:
        return {point: retained(_seam(point, cells)) for point in _GRID}
    finally:
        tracemalloc.stop()


@cache
def _leaf_step(seam: Callable[[_Point, int], Seam], cells: int) -> int:
    """What one more leaf on every nested Value Object record costs ``seam``.

    Read as a two-point difference rather than off the crossed grid, for the
    reason :data:`_LEAVES` states: the occurrence shape is pinned everywhere
    else, so the whole of what moves between these two points is one leaf per
    record.
    """
    tracemalloc.start()
    try:
        wide = retained(seam(_LEAST._replace(leaves=_LEAVES[1]), cells))
        return wide - retained(seam(_LEAST, cells))
    finally:
        tracemalloc.stop()


@cache
def _corner(cells: int) -> _Fit:
    """The fit at ``cells`` cells, from the four points that determine it alone.

    The whole grid is what refuses a cost of the wrong SHAPE; the corner is what
    a second graph size needs, which is only whether each step grew with the rows
    it charges.
    """
    corners = (
        _LEAST,
        _LEAST._replace(members=_MEMBERS[1]),
        _LEAST._replace(slots=_SLOTS[1]),
        _LEAST._replace(arms=_ARMS[1]),
    )
    tracemalloc.start()
    try:
        return _fitted({point: retained(_seam(point, cells)) for point in corners})
    finally:
        tracemalloc.stop()


def _member_rows(cells: int) -> int:
    """The rows one more applicable Attribute widens: every child projection,
    duplicates included, because a duplicate is a projection with a row of its
    own even where it merges onto a logical node that already has one."""
    return cells * (_CHILDREN + _DUPLICATES)


def _arm_positions(cells: int) -> int:
    """The positions one more projection reference occupies: the graph's own edge
    tuple where the fan-back recorded it, and the merged row's tuple where the
    merge resolved it into an allocation index."""
    return cells * 2


def _leaf_records(cells: int) -> int:
    """The Value Object RECORDS one more nested leaf widens: inside every child
    projection's ``mark``, its one ``inner`` record and each of the ``inners``
    elements. A record is a positional row of its own, so this is a count of rows
    rather than of projections — which is what a per-cell carrier inside a
    document would multiply."""
    return _member_rows(cells) * (1 + _NESTED)


def _slot_rows(cells: int) -> int:
    """The rows one more declared view widens: each parent's own source view row,
    and every logical node's merged view row — the merged layout being the union
    over the whole plan, so a node the plan could have reached from a level it was
    not projected at carries that level's slots as well."""
    return cells * (1 + 1 + _CHILDREN)


def _graph_survivors(seam: Seam) -> list[object]:
    """Every object of Parallax's own that ``seam`` leaves alive at its sample
    point, whatever kind it is."""
    return [obj for obj in survivors(seam) if type(obj).__module__.startswith("parallax.")]


def test_the_workload_holds_its_projection_and_logical_node_counts_across_the_whole_grid() -> None:
    # What makes every reading below exact rather than approximate. The merge's
    # own tables are lists and dictionaries sized by projections and logical
    # nodes: a grid point that moved either count would move a capacity, and a
    # capacity step is a reading the affine claim has no way to distinguish from
    # a term nobody wanted. Stated first because every later assertion assumes it.
    for point in _GRID:
        graph, merge = _compose(point, _CELLS)
        rows = graph_rows(graph)
        assert len(rows.layouts) == _CELLS * (1 + _CHILDREN + _DUPLICATES), point
        assert len(rows.roots) == _CELLS, point
        assert len(merge.order) == _CELLS * (1 + _CHILDREN), point
        assert not merge.has_issues, point


def test_retained_bytes_are_affine_in_the_members_slots_and_arms_at_once() -> None:
    # The whole crossing against the shape a compact representation has: a base,
    # plus an independent cost per member, per declared slot, and per recorded
    # edge. Fitted from the four smallest points and then required to be EXACT at
    # all thirty-six, so a cost of any other shape — quadratic down an axis, or
    # carrying a term in the product of two of them — has nowhere in the grid to
    # hide. Exact equality is affordable because the graph's counts are pinned:
    # what varies between two points is tuple arithmetic and nothing else.
    measured = _measured(_CELLS)
    fit = _fitted(measured)
    assert measured == {point: _predicts(fit, point) for point in _GRID}


def test_a_member_costs_one_pointer_in_one_row_and_nothing_else() -> None:
    # "No retained per-cell Snapshot carriers", in arithmetic, for the Attribute
    # half of a row. A compact row holds the decoded leaf itself at each position,
    # so one more applicable Attribute costs one more pointer in each row that
    # carries it and nothing anywhere else — no wrapper, no member dictionary
    # entry, no second copy in the merge, which reads the winning projection's row
    # by reference. Read at two graph sizes because the claim is per ROW: a fixed
    # per-model term would sit in the step at one size and be invisible there.
    assert _corner(_CELLS).member == _member_rows(_CELLS) * _POINTER
    assert _corner(_LARGER).member == _member_rows(_LARGER) * _POINTER


def test_a_value_object_leaf_costs_one_pointer_in_every_record_that_carries_it() -> None:
    # The same claim for the document half, which is where the replaced
    # representation kept most of its per-cell cost: a record object, an
    # occurrence object, and one carrier per leaf. A reduced occurrence is now a
    # positional row exactly as an Entity's members are, at every depth, so one
    # more leaf costs one pointer in each RECORD that declares it — three per
    # child projection here, the one `inner` and the two `inners` elements — and
    # nothing per occurrence, per element, or per cell. Read at two graph sizes
    # for the reason the member step is.
    assert _leaf_step(_seam, _CELLS) == _leaf_records(_CELLS) * _POINTER
    assert _leaf_step(_seam, _LARGER) == _leaf_records(_LARGER) * _POINTER


def test_an_edge_costs_one_pointer_where_it_is_recorded_and_one_where_it_resolves() -> None:
    # The relationships term of the bound. A to-many arm is a tuple of projection
    # indexes in the sealed graph and a tuple of allocation indexes in the merged
    # row the walk translated it into, so one more reference costs exactly those
    # two positions — the translation happens once, where the merged row is
    # built, rather than composing a fresh tuple per read.
    assert _corner(_CELLS).arm == _arm_positions(_CELLS) * _POINTER
    assert _corner(_LARGER).arm == _arm_positions(_LARGER) * _POINTER


def test_a_declared_view_slot_costs_one_pointer_in_every_row_it_widens() -> None:
    # The view-slot term, which unlike the other two carries a fixed
    # per-EXECUTION part as well: a slot is one entry in the plan's slot table and
    # one position in each layout the schema interns, all of which one execution
    # pays once however many rows it lays out. So the reading graded is the part
    # that scales — the difference between two graph sizes — and the part that
    # does not is required to be identical at both, which is what says the schema
    # is execution-owned rather than sized by the graph under it.
    small, large = _corner(_CELLS), _corner(_LARGER)
    assert large.slot - small.slot == (_slot_rows(_LARGER) - _slot_rows(_CELLS)) * _POINTER
    assert small.slot - _slot_rows(_CELLS) * _POINTER == large.slot - _slot_rows(_LARGER) * _POINTER


def test_a_conforming_materialization_leaves_no_object_of_its_own_alive_per_cell() -> None:
    # The absolute claim, as an exact empty list. Every Parallax object a held
    # materialization leaves alive is one of the whole-graph structures: the
    # sealed graph, its arrays, its merge, and the execution's view schema with
    # the slots and layouts it was built from. Not one carrier, record, or
    # occurrence wrapper survives, at any grid point — which is what the byte
    # readings cannot say, because a tuple of decoded leaves is untracked and
    # invisible to a survivor count either way.
    for point in (_LEAST, _GRID[-1]):
        alive = _graph_survivors(warmed(_seam(point)))
        assert [obj for obj in alive if not isinstance(obj, _GRAPH_STRUCTURES)] == [], point


def test_what_a_conforming_materialization_leaves_alive_does_not_grow_with_the_graph() -> None:
    # And that the permitted kinds are not per-row either. Twice the cells, twice
    # the projections and twice the logical nodes, and the same objects of
    # Parallax's own alive at the sample point — so the list above is a bound on
    # what a materialization retains rather than a census of one graph's size.
    small = _graph_survivors(warmed(_seam(_LEAST, _CELLS)))
    large = _graph_survivors(warmed(_seam(_LEAST, _LARGER)))
    assert len(small) == len(large) > 0
    assert sorted(type(obj).__qualname__ for obj in small) == sorted(
        type(obj).__qualname__ for obj in large
    )


def _catalog_seam(graphs: int) -> Seam:
    """``graphs`` whole materializations against one model's catalog, with only
    the catalog held at the sample point.

    The catalog is derived INSIDE the window, over a Metamodel formed outside it,
    so what the reading sees is the catalog and the layouts those graphs reached
    through it — and nothing of the graphs themselves, each of which is
    unreachable again before the next one is built.
    """
    workload = _WORKLOADS[_LEAST.members, _LEAST.leaves]
    views = workload.views[: _LEAST.slots]

    def run(sample: Callable[[], None]) -> None:
        cataloged = CatalogedModel(workload.meta)
        parent = _level(cataloged.layouts.entity(workload.parent.concrete_entity))
        child = _level(cataloged.layouts.entity(workload.child.concrete_entity))
        for _ in range(graphs):
            builder = GraphBuilder(
                ViewSchema((tuple(ChildSlot(view) for view in views), (ChildSlot(workload.back),)))
            )
            root = convert_row(workload.parents[0], parent, builder, source=_ROOT_SOURCE)
            children = tuple(
                convert_row(row, child, builder, source=_CHILD_SOURCE)
                for row in workload.children[0]
            )
            builder.write_view(root, views[0], children)
            builder.write_view(root, views[1], children[: _LEAST.arms])
            merge_graph_input(builder.seal((root,), _PIN))
        sample()
        assert cataloged is not None

    return run


def test_a_models_layout_catalog_is_the_same_size_after_one_graph_and_after_sixty_four() -> None:
    # `python.md`'s "retained layout count and size are independent of the number
    # of graphs materialized", measured. Entries are derived per exact Entity on
    # FIRST reach, so the reading is taken over a warmed catalog — the harness's
    # warm-up passes fill every memo underneath a layout before the window opens —
    # and what is left is whether a second, or a sixty-fourth, graph adds anything
    # to what the model retains. Both instruments are read: a per-graph entry
    # would move the byte count, and a per-graph reference taken by something
    # already alive would move neither unless the objects are counted too.
    tracemalloc.start()
    try:
        one, many = retained(_catalog_seam(1)), retained(_catalog_seam(64))
    finally:
        tracemalloc.stop()
    assert one > 0, "a catalog derived inside the window costs something to derive"
    assert one == many
    assert len(_graph_survivors(warmed(_catalog_seam(1)))) == len(
        _graph_survivors(warmed(_catalog_seam(64)))
    )


class _CellCarrier:
    """One retained wrapper per member cell — the replaced representation, reduced
    to the one property that made it expensive."""

    __slots__ = ("value",)

    def __init__(self, value: object) -> None:
        self.value = value


def _wrapping_seam(point: _Point, cells: int = _CELLS) -> Seam:
    """``point``'s materialization, plus one carrier per cell of every row.

    Held beside the graph rather than inside it, because what it demonstrates is
    a property of the READING rather than of the graph: a representation whose
    per-cell cost is a constant is exactly as affine as one whose per-cell cost is
    a pointer, and only the size of the step tells them apart.
    """

    def run(sample: Callable[[], None]) -> None:
        graph, merge = _compose(point, cells)
        carriers = [
            tuple(_CellCarrier(value) for value in row) for row in graph_rows(graph).member_rows
        ]
        sample()
        assert graph is not None and merge is not None and carriers is not None

    return run


def test_the_member_step_is_what_refuses_a_representation_that_wraps_every_cell() -> None:
    # What the arithmetic above is worth, demonstrated rather than asserted. A
    # control that keeps one wrapper per cell sits on an affine function of the
    # same three parameters just as exactly as the real thing does — the shape
    # reading passes it — and its member step is a whole object per row wider than
    # one pointer, which is the reading that refuses it. Both halves are graded,
    # because a control that failed the shape reading too would prove nothing
    # about which of them is load-bearing.
    tracemalloc.start()
    try:
        measured = {point: retained(_wrapping_seam(point)) for point in _GRID}
    finally:
        tracemalloc.stop()
    fit = _fitted(measured)
    assert measured == {point: _predicts(fit, point) for point in _GRID}
    assert fit.member > _member_rows(_CELLS) * _POINTER
    with pytest.raises(AssertionError):
        assert fit.member == _member_rows(_CELLS) * _POINTER


def _document_wrapping_seam(point: _Point, cells: int = _CELLS) -> Seam:
    """``point``'s materialization, plus one carrier per cell of every Value
    Object record at every depth — the document half of the same control."""

    def run(sample: Callable[[], None]) -> None:
        graph, merge = _compose(point, cells)
        rows = graph_rows(graph)
        carriers = [
            _wrapped(row[position])
            for layout, row in zip(rows.layouts, rows.member_rows, strict=True)
            for position in range(layout.attribute_count, len(row))
        ]
        sample()
        assert graph is not None and merge is not None and carriers is not None

    return run


def _wrapped(value: object) -> list[_CellCarrier]:
    """One carrier per cell of every record reached from one occurrence position,
    descending the elements of a Many and the records of a nested occurrence."""
    if isinstance(value, tuple):
        return [carrier for item in cast("tuple[object, ...]", value) for carrier in _wrapped(item)]
    return [_CellCarrier(value)]


def test_the_leaf_step_is_what_refuses_a_representation_wrapping_every_document_cell() -> None:
    # The document half of the control above, and the one that matters most,
    # because a document is where the replaced representation kept most of its
    # per-cell objects. A seam retaining one wrapper per Value Object cell moves
    # the leaf step by a whole object per record, and nothing else in this suite
    # would notice: the member, slot, and arm steps and the affine shape are all
    # untouched by what happens inside an occurrence. So the leaf step is the only
    # reading standing between that representation and this graph.
    step = _leaf_step(_document_wrapping_seam, _CELLS)
    assert step > _leaf_records(_CELLS) * _POINTER
    with pytest.raises(AssertionError):
        assert step == _leaf_records(_CELLS) * _POINTER
