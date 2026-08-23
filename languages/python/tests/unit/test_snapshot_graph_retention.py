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

**The measured level is polymorphic.** Its children resolve to the two concretes
of one table-per-hierarchy family, one reached through an intermediate abstract
subtype and one descending from the root, so a graph carries two member layouts
of different widths, two source view layouts, and two merged rows at once — and a
duplicate of either merges onto the logical node its broad projection made.

**Every measured projection also carries Value Object occurrences**, a top-level
One holding a nested One and a nested Many beside a top-level Many, because the
representation this replaced spent more of its per-cell cost inside documents
than on Attributes: a record, an occurrence, and a per-leaf carrier each. Their
shape is pinned across the grid — three more crossed axes would buy nothing the
first three do not already refuse — and read instead as three steps of their own,
one per population: the leaves inside a record, the elements a Many holds, and
the occurrences a projection declares.

**What the readings say, in the order they get stronger.** The whole grid sits on
one affine function of the three parameters fitted from its four smallest points,
which refuses any cross term — a slot cost sized per member, say. Then each step
is graded against exactly what the compact representation can charge: one pointer
per member per row, one per arm where the edge is recorded and one where it
resolves, one per slot in every row a slot widens, one per Value Object leaf in
every record that carries it, one whole positional row and its naming position
per record, and one position and one record per occurrence. Those readings are
the ones that name "no per-cell carrier" in arithmetic, and each is read beside
the control that proves it detects one —
:func:`test_the_member_step_is_what_refuses_a_representation_that_wraps_every_cell`
wraps every member cell, stays exactly affine, and fails only at the member step;
:func:`test_the_leaf_step_is_what_refuses_a_representation_wrapping_every_document_cell`
wraps every Value Object cell and fails only at the leaf step;
:func:`test_the_record_step_is_what_refuses_a_representation_wrapping_every_record`
and
:func:`test_the_occurrence_step_is_what_refuses_a_representation_wrapping_every_occurrence`
wrap what a step holding its own population fixed cannot see at all.

Exported names carry no leading underscore only where another module imports
them; nothing imports this one.
"""

from __future__ import annotations

import struct
import sys
import tracemalloc
from collections.abc import Callable, Mapping
from functools import cache
from typing import Final, NamedTuple, cast

import pytest

from memory_instruments import Seam, retained, survivors, warmed
from parallax.core.entity._layout import CatalogedModel, EntityLayout
from parallax.core.entity._model import model_of
from parallax.core.metamodel import (
    EntityIdentity,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    RelationshipIdentity,
    ValueObjectMetadata,
    entity_by_name,
)
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

_EMPTY_ROW: Final = sys.getsizeof(())
"""What a positional row of no positions costs. A row is a tuple, so its whole
cost is this plus one pointer per position — which is what makes a record's own
price a derived number rather than a constant anyone had to measure by hand.
:func:`test_a_positional_row_costs_the_tuple_that_holds_it_and_nothing_more` is
what holds the interpreter to it."""

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

_ELEMENTS: Final = (2, 3)
"""Elements in each Many occurrence. More than one at the smaller count, so a cost
charged per Value Object RECORD is a different number from one charged per
projection row; read as a step of its own for what one more element costs, which
is the one axis that moves the record and element populations while holding the
leaves inside them fixed."""

_OCCURRENCES: Final = (2, 3)
"""Top-level Value Object members the measured Entity declares: ``mark`` and
``marks`` always, and ``spare`` at the larger count. The axis that moves the
occurrence population alone — one more occurrence per projection, at the same
member, leaf, and element counts — so a cost charged once per occurrence has an
axis it cannot sit still under."""

_LABELS: Final = 1
"""Leaves on each ``marks`` element: its one ``label``. The Many the leaf axis
does not reach into, so its elements stay the narrowest records the workload
has however wide the nested ones grow."""

_VIEWS: Final = ("children", "arms", "extra1", "extra2")
"""The parent's declared relationships, in declaration order. A slot count names
the first ``slots`` of them; the model declares them all at every count, so a
relationship a plan did not use is model-owned metadata and costs no reading."""

_CONCRETES: Final = ("Alpha", "Beta")
"""The resolved concretes of the measured family, taken in turn down each
parent's children. Both are read at the one child source level, so the level is
polymorphic in the sense that costs a reading anything: two layouts of different
widths, two source view layouts, and two merged rows, all inside one graph."""


def _document(members: int, leaves: int, occurrences: int) -> Mapping[str, object]:
    """A model descriptor whose Child family carries ``members`` inherited
    Attributes and ``occurrences`` top-level Value Objects, whose nested records
    carry ``leaves`` each.

    Descriptor-backed rather than class-backed because the axes ARE the member,
    leaf, and occurrence counts: one document generator answers every point of
    the grid, where near-identical class pairs would answer the same question by
    repetition. Nothing here constructs an Entity, so the classes a typed
    materializer would need are not part of what is measured.

    ``Child`` is the ABSTRACT ROOT of a table-per-hierarchy family, so the
    measured level is polymorphic: ``Alpha`` reaches it through the intermediate
    abstract ``Special`` and ``Beta`` descends from the root directly, which
    gives the two concretes different applicable member sets — five positions
    against six at the smallest member count — and therefore different layouts,
    different source view layouts, and different merged rows. Every member the
    axes vary is declared on the root, so widening one widens both concretes'
    rows alike and a step stays a count of rows rather than of concretes.

    The occurrences are what put a document on the measured path: ``mark`` is a
    top-level One holding a nested One and a nested Many, ``marks`` is a
    top-level Many, and ``spare`` is the One the occurrence axis adds. A Many is
    declared at :data:`_ELEMENTS` elements by the rows, so a record count is not
    a row count.
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

    value_objects: list[dict[str, object]] = [
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
    ]
    if occurrences > _OCCURRENCES[0]:
        value_objects.append({"name": "spare", "attributes": leaf_run()})

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
                "inheritance": {
                    "role": "root",
                    "strategy": "table-per-hierarchy",
                    "tag": {"column": "kind"},
                },
                "attributes": [
                    {"name": "id", "type": "int64", "primaryKey": True},
                    {"name": "parentId", "type": "int64"},
                    *(
                        {"name": f"c{index:02d}", "type": "string", "maxLength": 32}
                        for index in range(members - 2)
                    ),
                ],
                "valueObjects": value_objects,
                "relationships": [{"name": "parent", "reverseOf": f"{_NAMESPACE}.Parent.children"}],
                "indices": [{"name": "retention_child_parent", "attributes": ["parentId"]}],
            },
            {
                "name": "Special",
                "namespace": _NAMESPACE,
                "inheritance": {"role": "abstract-subtype", "parent": f"{_NAMESPACE}.Child"},
                "attributes": [{"name": "rank", "type": "int64", "nullable": True}],
            },
            {
                "name": "Alpha",
                "namespace": _NAMESPACE,
                "inheritance": {
                    "role": "concrete-subtype",
                    "parent": f"{_NAMESPACE}.Special",
                    "tagValue": "alpha",
                },
            },
            {
                "name": "Beta",
                "namespace": _NAMESPACE,
                "inheritance": {
                    "role": "concrete-subtype",
                    "parent": f"{_NAMESPACE}.Child",
                    "tagValue": "beta",
                },
                "attributes": [
                    {"name": "weight", "type": "float64", "nullable": True},
                    {"name": "note", "type": "string", "maxLength": 32, "nullable": True},
                ],
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
    """One shape's whole model and its rows, formed once at import.

    Every row a window converts is allocated out here, which is what excludes
    decoded payload leaves from the readings STRUCTURALLY rather than by
    filtering: a compact row that merely references one of these values costs the
    reading the position and not the value.

    ``levels`` is the resolved concrete each child position is read at, in
    position order, so a conversion takes the exact Entity's own layout exactly
    as a polymorphic level's compiled read hands one over per row.
    """

    meta: Metamodel
    parent: LevelContext
    levels: tuple[LevelContext, ...]
    views: tuple[RelationshipViewKey, ...]
    back: RelationshipViewKey
    parents: tuple[dict[str, object], ...]
    children: tuple[tuple[dict[str, object], ...], ...]


def _workload(members: int, leaves: int, elements: int, occurrences: int) -> _Workload:
    meta = model_of(domain_model_from_document(_document(members, leaves, occurrences)))
    catalog = CatalogedModel(meta).layouts
    parent, child = _identity(meta, "Parent"), _identity(meta, "Child")
    concretes = tuple(_level(catalog.entity(_identity(meta, name))) for name in _CONCRETES)
    parent_rows: list[dict[str, object]] = [{"id": 1_000 + cell} for cell in range(_LARGER)]
    child_rows: list[tuple[dict[str, object], ...]] = []
    for cell in range(_LARGER):
        rows: list[dict[str, object]] = []
        for index in range(_CHILDREN):
            row: dict[str, object] = {"id": 10_000 + cell * 100 + index, "parent_id": 1_000 + cell}
            for position in range(members - 2):
                row[f"c{position:02d}"] = f"c{position:02d}-value-{cell}-{index}"
            if index % len(_CONCRETES) == 0:
                row["rank"] = index
            else:
                row["weight"] = float(index)
                row["note"] = f"note-{cell}-{index}"
            row["mark"] = {
                "label": f"mark-{cell}-{index}",
                "inner": _record(leaves, cell, index),
                "inners": [_record(leaves, cell, index) for _ in range(elements)],
            }
            row["marks"] = [
                {"label": f"marks-{cell}-{index}-{element}"} for element in range(elements)
            ]
            if occurrences > _OCCURRENCES[0]:
                row["spare"] = _record(leaves, cell, index)
            rows.append(row)
        child_rows.append(tuple(rows))
    return _Workload(
        meta,
        _level(catalog.entity(parent)),
        tuple(concretes[index % len(_CONCRETES)] for index in range(_CHILDREN)),
        tuple(RelationshipViewKey(RelationshipIdentity(parent, name)) for name in _VIEWS),
        RelationshipViewKey(RelationshipIdentity(child, "parent")),
        tuple(parent_rows),
        tuple(child_rows),
    )


def _record(leaves: int, cell: int, index: int) -> dict[str, object]:
    """One nested Value Object record's stored document."""
    return {f"v{position:02d}": f"v{position:02d}-{cell}-{index}" for position in range(leaves)}


_SHAPES: Final = (
    *((members, _LEAVES[0], _ELEMENTS[0], _OCCURRENCES[0]) for members in _MEMBERS),
    (_MEMBERS[0], _LEAVES[1], _ELEMENTS[0], _OCCURRENCES[0]),
    (_MEMBERS[0], _LEAVES[0], _ELEMENTS[1], _OCCURRENCES[0]),
    (_MEMBERS[0], _LEAVES[0], _ELEMENTS[0], _OCCURRENCES[1]),
)
"""What the model and its rows are formed at: one shape per grid member count,
plus the second point of each of the three document steps. Every step is read at
the smallest member count, which is where every step in this suite is read."""

_WORKLOADS: Final = {shape: _workload(*shape) for shape in _SHAPES}

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
    """One workload the readings are stated over: ``members`` Attributes the
    family root declares, ``slots`` relationship views declared at the root
    source level, ``arms`` projection references in the narrowed view of them,
    ``leaves`` on each nested Value Object record, ``elements`` in each Many
    occurrence, and ``occurrences`` top-level Value Objects on each child
    projection.

    The crossed grid pins the last three; each of the three document steps moves
    exactly one of them."""

    members: int
    slots: int
    arms: int
    leaves: int = _LEAVES[0]
    elements: int = _ELEMENTS[0]
    occurrences: int = _OCCURRENCES[0]

    @property
    def shape(self) -> tuple[int, int, int, int]:
        """The model and rows this point converts, which is what the axes moving
        a document share and the three view axes do not."""
        return self.members, self.leaves, self.elements, self.occurrences


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

_WIDER_LEAVES: Final = _LEAST._replace(leaves=_LEAVES[1])
_WIDER_ELEMENTS: Final = _LEAST._replace(elements=_ELEMENTS[1])
_WIDER_OCCURRENCES: Final = _LEAST._replace(occurrences=_OCCURRENCES[1])
"""The second point of each document step. One axis moves and five stand still,
which is what lets each step name one population of the document rather than a
mixture of them."""

_LEAF_POOL: Final = tuple(f"leaf-{index:02d}" for index in range(max(_LEAVES) + _LABELS))
"""Leaves the row calibration fills its rows from, allocated out here for the
reason every workload row is: what it prices is the row, not the values in it."""

_ROWS: Final = (256, 512)
"""Rows the calibration holds, at two counts, so what it reads is the marginal
cost of one row rather than a total carrying whatever else the seam allocated."""


def _compose(point: _Point, cells: int) -> tuple[SnapshotGraph, GraphMerge]:
    """One whole materialization of ``cells`` cells, built and merged the way a
    read builds and merges one: a fresh slot table and view schema per execution,
    every row converted through the production converter under the concrete its
    own level resolved it to, the builder dropped at sealing, and the sealed graph
    and its merge the only things that come back."""
    workload = _WORKLOADS[point.shape]
    views = workload.views[: point.slots]
    schema = ViewSchema((tuple(ChildSlot(view) for view in views), (ChildSlot(workload.back),)))
    builder = GraphBuilder(schema)
    roots: list[int] = []
    for cell in range(cells):
        parent = convert_row(workload.parents[cell], workload.parent, builder, source=_ROOT_SOURCE)
        children = tuple(
            convert_row(row, level, builder, source=_CHILD_SOURCE)
            for row, level in zip(workload.children[cell], workload.levels, strict=True)
        )
        duplicates = tuple(
            convert_row(
                workload.children[cell][index],
                workload.levels[index],
                builder,
                source=_CHILD_SOURCE,
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
def _at(seam: Callable[[_Point, int], Seam], point: _Point, cells: int) -> int:
    """``seam``'s retained bytes at one point, measured once however many steps
    read it — the smallest point is the baseline all three document steps are
    taken against."""
    tracemalloc.start()
    try:
        return retained(seam(point, cells))
    finally:
        tracemalloc.stop()


def _step(seam: Callable[[_Point, int], Seam], wide: _Point, cells: int) -> int:
    """What moving one document axis from :data:`_LEAST` to ``wide`` costs
    ``seam``.

    Read as a two-point difference rather than off the crossed grid, for the
    reason :data:`_LEAVES` states: every other axis holds the same value at both
    points, so the whole of what moves between them is the one the caller varied.
    """
    return _at(seam, wide, cells) - _at(seam, _LEAST, cells)


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
    return _member_rows(cells) * (1 + _ELEMENTS[0])


def _row_bytes(positions: int) -> int:
    """What one whole positional row of ``positions`` positions costs: the tuple
    itself, plus one pointer for each position it holds."""
    return _EMPTY_ROW + positions * _POINTER


def _element_bytes(leaves: int) -> int:
    """What one more element in every Many occurrence costs one child projection:
    the ``inners`` element's own record and the position naming it in that
    occurrence's row, plus the same for ``marks``, whose elements carry the one
    ``label`` however wide the nested records grow.

    A representation charging anything per RECORD — the pre-cutover graph held a
    ``ValueObjectRecord`` for each — charges it twice more here, which is what
    this reading is stated exactly enough to refuse.
    """
    return _row_bytes(leaves) + _row_bytes(_LABELS) + 2 * _POINTER


def _occurrence_bytes(leaves: int) -> int:
    """What one more top-level occurrence costs one child projection: the position
    it takes in the member row after the Attributes, and the one record that
    position holds.

    A representation charging anything per OCCURRENCE — the pre-cutover graph held
    a ``ValueObjectOccurrenceInput`` for each — is a term this reading has and the
    element and leaf steps do not, because their populations move underneath a
    fixed number of occurrences.
    """
    return _POINTER + _row_bytes(leaves)


def _rows_seam(rows: int, positions: int) -> Seam:
    """``rows`` positional rows of ``positions`` positions, built inside the
    window over leaves allocated outside it and held in one tuple that names
    them — the graph's own arrangement of a record, reduced to what is priced."""

    def run(sample: Callable[[], None]) -> None:
        held = tuple(
            tuple(_LEAF_POOL[position] for position in range(positions)) for _ in range(rows)
        )
        sample()
        assert held is not None

    return run


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


def test_the_measured_level_resolves_two_concretes_of_one_family_to_two_layouts() -> None:
    # The workload is the representative graph's polymorphic half, stated as the
    # facts the readings depend on rather than as the model that produces them.
    # One child source level resolves both concretes of one family; their member
    # layouts are different objects of different widths, so a per-row cost is
    # charged against two layouts rather than one; both are laid out and merged
    # by the one execution-owned schema; and a duplicate of either merges onto the
    # logical node its broad projection already made, which is what keeps the
    # projection and logical-node counts above apart.
    graph, merge = _compose(_LEAST, _CELLS)
    rows = graph_rows(graph)
    children = [
        layout
        for layout, source in zip(rows.layouts, rows.sources, strict=True)
        if source == _CHILD_SOURCE
    ]
    concretes = {layout.concrete.name: layout for layout in children}
    assert sorted(concretes) == sorted(_CONCRETES)
    alpha, beta = (concretes[name] for name in _CONCRETES)
    assert alpha.family == beta.family
    assert alpha.attribute_count != beta.attribute_count
    assert rows.schema.merged(alpha) is not rows.schema.merged(beta)
    assert {id(rows.schema.merged(layout)) for layout in children} == {
        id(rows.schema.merged(alpha)),
        id(rows.schema.merged(beta)),
    }
    per_cell = 1 + _CHILDREN + _DUPLICATES
    for cell in range(_CELLS):
        broad = cell * per_cell + 1
        for index in range(_DUPLICATES):
            duplicate = broad + _CHILDREN + index
            assert rows.logical_ids[duplicate] == rows.logical_ids[broad + index], (cell, index)
    assert not merge.has_issues


def test_a_positional_row_costs_the_tuple_that_holds_it_and_nothing_more() -> None:
    # What the two record readings below are stated in, measured rather than
    # assumed. Every claim about a Value Object record's price rests on a row
    # costing its own tuple and one pointer per position, so the price is derived
    # from the interpreter's own sizing and this is what holds the interpreter to
    # it: the marginal cost of one more row, in a structure that names it, is the
    # row plus the position naming it. An interpreter that ever charged a row
    # differently would fail here rather than silently moving what a record step
    # means.
    tracemalloc.start()
    try:
        for positions in _LEAVES:
            small = retained(_rows_seam(_ROWS[0], positions))
            large = retained(_rows_seam(_ROWS[1], positions))
            grown = (_ROWS[1] - _ROWS[0]) * (_row_bytes(positions) + _POINTER)
            assert large - small == grown, positions
    finally:
        tracemalloc.stop()


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
    # nothing per CELL of one. What a record itself costs, and what an occurrence
    # itself costs, are the two steps below; this one holds their populations
    # still and prices what a leaf adds inside them. Read at two graph sizes for
    # the reason the member step is.
    assert _step(_seam, _WIDER_LEAVES, _CELLS) == _leaf_records(_CELLS) * _POINTER
    assert _step(_seam, _WIDER_LEAVES, _LARGER) == _leaf_records(_LARGER) * _POINTER


def test_a_value_object_record_costs_its_own_row_and_the_position_that_names_it() -> None:
    # The population the leaf step holds still, varied on its own: one more
    # element in every Many occurrence, at the same members, leaves, and
    # occurrences. What it may cost is exactly two more rows per child projection
    # — one `inners` element and one `marks` element — and the two positions
    # naming them. Nothing per record beyond the record, which is the claim the
    # leaf step cannot make, because a fixed cost per record sits still while
    # leaves move and is absorbed by the fit's origin at every graph size.
    small = _member_rows(_CELLS) * _element_bytes(_LEAVES[0])
    large = _member_rows(_LARGER) * _element_bytes(_LEAVES[0])
    assert _step(_seam, _WIDER_ELEMENTS, _CELLS) == small
    assert _step(_seam, _WIDER_ELEMENTS, _LARGER) == large


def test_a_top_level_occurrence_costs_one_position_in_the_row_and_its_own_record() -> None:
    # And the population both other document steps hold still: one more top-level
    # Value Object on the measured Entity, at the same members, leaves, and
    # elements. An occurrence is a position in the member row after the
    # Attributes, holding the one record it reduced to — so it costs a pointer and
    # a row, and the wrapper the replaced representation put around each one costs
    # nothing here because there is no wrapper. Read at two graph sizes for the
    # reason the member step is.
    small = _member_rows(_CELLS) * _occurrence_bytes(_LEAVES[0])
    large = _member_rows(_LARGER) * _occurrence_bytes(_LEAVES[0])
    assert _step(_seam, _WIDER_OCCURRENCES, _CELLS) == small
    assert _step(_seam, _WIDER_OCCURRENCES, _LARGER) == large


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
    workload = _WORKLOADS[_LEAST.shape]
    views = workload.views[: _LEAST.slots]

    def run(sample: Callable[[], None]) -> None:
        cataloged = CatalogedModel(workload.meta)
        parent = _level(cataloged.layouts.entity(workload.parent.concrete_entity))
        levels = tuple(
            _level(cataloged.layouts.entity(level.concrete_entity)) for level in workload.levels
        )
        for _ in range(graphs):
            builder = GraphBuilder(
                ViewSchema((tuple(ChildSlot(view) for view in views), (ChildSlot(workload.back),)))
            )
            root = convert_row(workload.parents[0], parent, builder, source=_ROOT_SOURCE)
            children = tuple(
                convert_row(row, level, builder, source=_CHILD_SOURCE)
                for row, level in zip(workload.children[0], levels, strict=True)
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
    step = _step(_document_wrapping_seam, _WIDER_LEAVES, _CELLS)
    assert step > _leaf_records(_CELLS) * _POINTER
    with pytest.raises(AssertionError):
        assert step == _leaf_records(_CELLS) * _POINTER


def _record_wrapping_seam(point: _Point, cells: int = _CELLS) -> Seam:
    """``point``'s materialization, plus one carrier per Value Object RECORD at
    every depth — a representation that wraps each reduced record rather than each
    of its cells, which is the population the pre-cutover graph's
    ``ValueObjectRecord`` was."""

    def run(sample: Callable[[], None]) -> None:
        graph, merge = _compose(point, cells)
        rows = graph_rows(graph)
        carriers = [
            carrier
            for layout, row in zip(rows.layouts, rows.member_rows, strict=True)
            for position, declared in enumerate(layout.occurrences, start=layout.attribute_count)
            for carrier in _records(row[position], declared)
        ]
        sample()
        assert graph is not None and merge is not None and carriers is not None

    return run


def _occurrence_wrapping_seam(point: _Point, cells: int = _CELLS) -> Seam:
    """``point``'s materialization, plus one carrier per top-level OCCURRENCE of
    every projection — the population the pre-cutover graph's
    ``ValueObjectOccurrenceInput`` was, which is fixed per projection and
    therefore invisible to every reading that varies something inside a
    document."""

    def run(sample: Callable[[], None]) -> None:
        graph, merge = _compose(point, cells)
        rows = graph_rows(graph)
        carriers = [
            _CellCarrier(row[position])
            for layout, row in zip(rows.layouts, rows.member_rows, strict=True)
            for position in range(layout.attribute_count, len(row))
        ]
        sample()
        assert graph is not None and merge is not None and carriers is not None

    return run


def _records(
    value: object, declared: ValueObjectMetadata | NestedValueObjectMetadata
) -> list[_CellCarrier]:
    """One carrier per record reached from one occurrence position: the record
    itself, and each record nested inside it, descending a Many by its elements
    and a One by its single row."""
    if declared.multiplicity is Multiplicity.MANY:
        return [
            carrier
            for element in cast("tuple[object, ...]", value)
            for carrier in _record_carriers(element, declared)
        ]
    return _record_carriers(value, declared)


def _record_carriers(
    row: object, declared: ValueObjectMetadata | NestedValueObjectMetadata
) -> list[_CellCarrier]:
    """One carrier for one record, and one for each record below it."""
    positions = cast("tuple[object, ...]", row)
    return [
        _CellCarrier(row),
        *(
            carrier
            for offset, nested in enumerate(declared.value_objects, start=len(declared.attributes))
            for carrier in _records(positions[offset], nested)
        ),
    ]


def test_the_record_step_is_what_refuses_a_representation_wrapping_every_record() -> None:
    # What the record reading is worth. A seam keeping one carrier per reduced
    # record — no cell wrapped, no occurrence wrapped — moves the element step by
    # a whole object per element and moves nothing else in this suite: the affine
    # shape, the member, slot, and arm steps, and the leaf step all price
    # populations it holds fixed. So a `ValueObjectRecord` returning to the
    # retained graph fails exactly here.
    step = _step(_record_wrapping_seam, _WIDER_ELEMENTS, _CELLS)
    assert step > _member_rows(_CELLS) * _element_bytes(_LEAVES[0])
    with pytest.raises(AssertionError):
        assert step == _member_rows(_CELLS) * _element_bytes(_LEAVES[0])


def test_the_occurrence_step_is_what_refuses_a_representation_wrapping_every_occurrence() -> None:
    # And what the occurrence reading is worth, which is the reading with no
    # substitute at all: a carrier held once per top-level occurrence is a
    # constant per projection, so it stands still down every axis the grid varies
    # and is absorbed whole by the fit's origin at each graph size. It moves this
    # step by an object per occurrence, and nothing else here notices it.
    step = _step(_occurrence_wrapping_seam, _WIDER_OCCURRENCES, _CELLS)
    assert step > _member_rows(_CELLS) * _occurrence_bytes(_LEAVES[0])
    with pytest.raises(AssertionError):
        assert step == _member_rows(_CELLS) * _occurrence_bytes(_LEAVES[0])
